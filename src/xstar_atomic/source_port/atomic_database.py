"""Source-faithful port of XSTAR's packed atomic-database initialization.

This module translates the runtime-relevant behavior of ``readtbl.f90`` and
``setptrs.f90``.  The packed FITS vectors stay memory mapped so the roughly
GiB-scale production ``atdb.fits`` file does not need a second in-memory copy.
All public record and pointer indices use the original one-based Fortran
convention.

``dbwk2.f90`` is an interactive database maintenance utility rather than part
of the normal XSTAR setup path.  Its runtime-relevant pointer rebuild and
non-mutating report operations are exposed through :func:`dbwk2`; destructive
editing/sorting instructions deliberately remain unsupported for immutable
FITS input.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, MutableMapping, Optional, Sequence, Tuple

import csv
import json
import os
import tempfile

import numpy as np
from astropy.io import fits

from .state import XSTARAtomicState, XSTARPythonState


class AtomicDatabaseError(RuntimeError):
    """Raised when the packed database violates an XSTAR source invariant."""


@dataclass(frozen=True)
class PackedRecordHeader:
    """One packed ``nptrs(:,record)`` header using Fortran indices."""

    recno: int
    raw_pointer: int
    data_type: int
    rate_type: int
    continuation: int
    nreal: int
    nint: int
    nchar: int
    real_ptr: int
    int_ptr: int
    char_ptr: int


class FortranPackedVector:
    """Read-mostly one-based view of a packed FITS vector.

    The FITS array is retained without a guard-cell copy.  Integer indexing is
    translated from Fortran's ``1..N`` domain.  Sparse overrides support the
    only mutation performed by ``setptrs`` (absolute line wavelengths) without
    copying the complete REALS extension.
    """

    def __init__(self, data: np.ndarray, *, name: str):
        self._data = np.asarray(data).reshape(-1)
        self.name = name
        self._overrides: Dict[int, Any] = {}
        # Sparse mutations are accumulated by setptrs and then read many times.
        # Keep a lazily rebuilt sorted NumPy representation so range overlays
        # use searchsorted/vector assignment instead of scanning the full dict.
        self._override_indices_cache: np.ndarray | None = None
        self._override_values_cache: np.ndarray | None = None

    def _invalidate_override_cache(self) -> None:
        self._override_indices_cache = None
        self._override_values_cache = None

    def _sorted_overrides(self) -> tuple[np.ndarray, np.ndarray]:
        if self._override_indices_cache is None or self._override_values_cache is None:
            if not self._overrides:
                self._override_indices_cache = np.asarray([], dtype=np.int64)
                self._override_values_cache = np.asarray([], dtype=self._data.dtype)
            else:
                indices = np.fromiter(self._overrides.keys(), dtype=np.int64, count=len(self._overrides))
                order = np.argsort(indices, kind="stable")
                indices = indices[order]
                values = np.asarray(
                    [self._overrides[int(index)] for index in indices],
                    dtype=self._data.dtype,
                )
                self._override_indices_cache = indices
                self._override_values_cache = values
        return self._override_indices_cache, self._override_values_cache

    def __len__(self) -> int:
        return int(self._data.size)

    def _check(self, index: int) -> None:
        if index < 1 or index > len(self):
            raise IndexError(f"{self.name} index {index} outside 1..{len(self)}")

    def __getitem__(self, index: int) -> Any:
        if not isinstance(index, (int, np.integer)):
            raise TypeError(f"{self.name} requires a one-based integer index")
        idx = int(index)
        self._check(idx)
        if idx in self._overrides:
            return self._overrides[idx]
        value = self._data[idx - 1]
        return value.item() if isinstance(value, np.generic) else value

    def __setitem__(self, index: int, value: Any) -> None:
        idx = int(index)
        self._check(idx)
        self._overrides[idx] = value
        self._invalidate_override_cache()

    def set_overrides(self, indices: Sequence[int] | np.ndarray, values: Sequence[Any] | np.ndarray) -> None:
        """Install multiple one-based sparse overrides with one cache invalidation."""
        idx = np.asarray(indices, dtype=np.int64).reshape(-1)
        val = np.asarray(values).reshape(-1)
        if idx.size != val.size:
            raise ValueError("override indices and values differ in length")
        if idx.size == 0:
            return
        if int(idx.min()) < 1 or int(idx.max()) > len(self):
            raise IndexError(f"{self.name} override outside 1..{len(self)}")
        for packed_index, value in zip(idx.tolist(), val.tolist()):
            self._overrides[int(packed_index)] = value
        self._invalidate_override_cache()

    def gather(self, indices: Sequence[int] | np.ndarray, *, dtype: Any = None) -> np.ndarray:
        """Vectorized one-based indexed read with sparse overrides applied."""
        idx = np.asarray(indices, dtype=np.int64)
        flat = idx.reshape(-1)
        if flat.size == 0:
            return np.asarray([], dtype=dtype).reshape(idx.shape)
        if int(flat.min()) < 1 or int(flat.max()) > len(self):
            raise IndexError(f"{self.name} gather outside 1..{len(self)}")
        out = np.asarray(self._data[flat - 1]).copy()
        if self._overrides:
            override_indices, override_values = self._sorted_overrides()
            positions = np.searchsorted(override_indices, flat)
            valid = positions < override_indices.size
            if np.any(valid):
                valid_positions = positions[valid]
                matches = override_indices[valid_positions] == flat[valid]
                if np.any(matches):
                    target = np.flatnonzero(valid)[matches]
                    out[target] = override_values[valid_positions[matches]]
        if dtype is not None:
            out = out.astype(dtype, copy=False)
        return out.reshape(idx.shape)

    def slice(self, start: int, count: int, *, dtype: Any = None) -> np.ndarray:
        """Return ``count`` values beginning at one-based ``start``.

        Sparse overrides are selected by two binary searches and applied with
        vectorized assignment.  Runtime is O(log M + K), where M is the total
        override count and K is the number intersecting this slice, rather than
        O(M) for every packed record.
        """
        if count < 0:
            raise ValueError("count must be non-negative")
        if count == 0:
            return np.asarray([], dtype=dtype)
        self._check(start)
        self._check(start + count - 1)
        out = np.asarray(self._data[start - 1 : start - 1 + count])
        if self._overrides:
            override_indices, override_values = self._sorted_overrides()
            lo = int(np.searchsorted(override_indices, start, side="left"))
            hi = int(np.searchsorted(override_indices, start + count, side="left"))
            if hi > lo:
                out = out.copy()
                out[override_indices[lo:hi] - int(start)] = override_values[lo:hi]
        if dtype is not None:
            out = out.astype(dtype, copy=False)
        return out

    def numpy(self, *, copy: bool = False) -> np.ndarray:
        """Return the zero-based packed vector, applying sparse overrides."""
        if not copy and not self._overrides:
            return self._data
        out = np.asarray(self._data).copy()
        if self._overrides:
            indices, values = self._sorted_overrides()
            out[indices - 1] = values
        return out

    @property
    def overrides(self) -> Mapping[int, Any]:
        return dict(self._overrides)


class FortranPointerTable:
    """One-based ``nptrs(field, record)`` view over a ``(records, 10)`` array."""

    def __init__(self, pointers: np.ndarray):
        array = np.asarray(pointers)
        if array.ndim != 2 or array.shape[1] != 10:
            raise ValueError(f"POINTERS must have shape (n_records, 10), got {array.shape}")
        self._data = array

    @property
    def n_records(self) -> int:
        return int(self._data.shape[0])

    def __getitem__(self, key: Tuple[int, int]) -> int:
        field, recno = (int(key[0]), int(key[1]))
        if field < 1 or field > 10:
            raise IndexError(f"nptrs field {field} outside 1..10")
        if recno < 1 or recno > self.n_records:
            raise IndexError(f"nptrs record {recno} outside 1..{self.n_records}")
        return int(self._data[recno - 1, field - 1])

    def record(self, recno: int) -> np.ndarray:
        if recno < 1 or recno > self.n_records:
            raise IndexError(f"record {recno} outside 1..{self.n_records}")
        return np.asarray(self._data[recno - 1])

    def numpy(self, *, copy: bool = False) -> np.ndarray:
        return np.asarray(self._data).copy() if copy else np.asarray(self._data)


@dataclass
class XSTARMasterData:
    """Packed arrays loaded by the Python translation of ``readtbl``."""

    path: Path
    hdul: fits.HDUList
    nptrs: FortranPointerTable
    rdat1: FortranPackedVector
    idat1: FortranPackedVector
    kdat1: FortranPackedVector
    creation_date: str = ""
    creator: str = ""
    np2: int = 0
    np1r: int = 0
    np1i: int = 0
    np1k: int = 0
    closed: bool = False

    def close(self) -> None:
        if not self.closed:
            self.hdul.close()
            self.closed = True

    def __enter__(self) -> "XSTARMasterData":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def header(self, recno: int) -> PackedRecordHeader:
        p = self.nptrs.record(recno)
        return PackedRecordHeader(
            recno=int(recno),
            raw_pointer=int(p[0]),
            data_type=int(p[1]),
            rate_type=int(p[2]),
            continuation=int(p[3]),
            nreal=int(p[4]),
            nint=int(p[5]),
            nchar=int(p[6]),
            real_ptr=int(p[7]),
            int_ptr=int(p[8]),
            char_ptr=int(p[9]),
        )

    def record_reals(self, recno: int, *, dtype: Any = np.float64) -> np.ndarray:
        h = self.header(recno)
        return self.rdat1.slice(h.real_ptr, h.nreal, dtype=dtype) if h.nreal else np.asarray([], dtype=dtype)

    def record_integers(self, recno: int, *, dtype: Any = np.int64) -> np.ndarray:
        h = self.header(recno)
        return self.idat1.slice(h.int_ptr, h.nint, dtype=dtype) if h.nint else np.asarray([], dtype=dtype)

    def record_chars(self, recno: int) -> bytes:
        h = self.header(recno)
        if h.nchar <= 0:
            return b""
        values = self.kdat1.slice(h.char_ptr, h.nchar)
        if values.dtype.kind == "S":
            return b"".join(values.astype("S1").tolist())
        if values.dtype.kind == "U":
            return "".join(values.astype(str).tolist()).encode("latin-1", errors="replace")
        return bytes(np.asarray(values, dtype=np.uint8).tolist())

    def local_level_index(self, recno: int) -> int:
        """Return ``idat(nidt-1)`` used by ``setptrs.f90``."""
        h = self.header(recno)
        if h.nint < 2:
            raise AtomicDatabaseError(
                f"record {recno} rate type {h.rate_type} has {h.nint} integers; "
                "setptrs requires idat(nidt-1)"
            )
        return int(self.idat1[h.int_ptr + h.nint - 2])

    def validate_pointer_spans(self) -> None:
        """Check every packed record span before pointer construction."""
        for recno in range(1, self.np2 + 1):
            h = self.header(recno)
            for name, ptr, count, length in (
                ("REALS", h.real_ptr, h.nreal, self.np1r),
                ("INTEGERS", h.int_ptr, h.nint, self.np1i),
                ("CHARS", h.char_ptr, h.nchar, self.np1k),
            ):
                if count < 0:
                    raise AtomicDatabaseError(f"record {recno} has negative {name} count {count}")
                if count == 0:
                    continue
                if ptr < 1 or ptr + count - 1 > length:
                    raise AtomicDatabaseError(
                        f"record {recno} {name} span {ptr}..{ptr + count - 1} "
                        f"outside 1..{length}"
                    )


@dataclass
class XSTARDerivedPointers:
    """Pointer arrays produced by the translation of ``setptrs.f90``.

    All arrays contain a zero guard at index 0.  Two-dimensional arrays retain
    the Fortran axis order, e.g. ``npfi[rate_type, ion_index]``.
    """

    npar: np.ndarray
    npnxt: np.ndarray
    npfirst: np.ndarray
    npfi: np.ndarray
    npfe: np.ndarray
    nplin: np.ndarray
    nplini: np.ndarray
    npcon: np.ndarray
    npconi2: np.ndarray
    npconi: np.ndarray
    npilev: np.ndarray
    npilevi: np.ndarray
    nlevs: np.ndarray
    nptrt: np.ndarray
    element_records: np.ndarray
    ion_records: np.ndarray
    ion_element_z: np.ndarray
    ion_stage: np.ndarray
    level_record_by_global_index: np.ndarray
    level_global_index_by_record: np.ndarray
    nlsvn: int
    ncsvn: int
    n_ions: int
    n_elements: int
    n_level_records: int
    max_rate_type: int
    provenance: Dict[str, Any] = field(default_factory=dict)

    def validate(self, master: XSTARMasterData) -> Dict[str, int]:
        """Validate source-level pointer invariants and return counts."""
        n_records = master.np2
        if self.npar.shape != (n_records + 1,):
            raise AtomicDatabaseError("npar shape does not match packed record count")
        if self.npnxt.shape != (n_records + 1,):
            raise AtomicDatabaseError("npnxt shape does not match packed record count")
        if np.any(self.npar < 0) or np.any(self.npar > n_records):
            raise AtomicDatabaseError("npar contains an out-of-range record index")
        if np.any(self.npnxt < 0) or np.any(self.npnxt > n_records):
            raise AtomicDatabaseError("npnxt contains an out-of-range record index")
        if np.any(self.nplin[1:] < 1) or np.any(self.nplin[1:] > n_records):
            raise AtomicDatabaseError("nplin contains an out-of-range record index")
        if np.any(self.npcon[1:] < 1) or np.any(self.npcon[1:] > n_records):
            raise AtomicDatabaseError("npcon contains an out-of-range record index")

        line_roundtrip = 0
        for line_index in range(1, self.nlsvn + 1):
            recno = int(self.nplin[line_index])
            if int(self.nplini[recno]) != line_index:
                raise AtomicDatabaseError(
                    f"line pointer roundtrip failed: nplin({line_index})={recno}, "
                    f"nplini({recno})={self.nplini[recno]}"
                )
            line_roundtrip += 1

        continuum_roundtrip = 0
        for continuum_index in range(1, self.ncsvn + 1):
            recno = int(self.npcon[continuum_index])
            if int(self.npconi2[recno]) != continuum_index:
                raise AtomicDatabaseError(
                    f"continuum pointer roundtrip failed: npcon({continuum_index})={recno}, "
                    f"npconi2({recno})={self.npconi2[recno]}"
                )
            continuum_roundtrip += 1

        level_roundtrip = 0
        for global_index in range(1, self.n_level_records + 1):
            recno = int(self.level_record_by_global_index[global_index])
            if recno <= 0:
                raise AtomicDatabaseError(f"missing level record for global level {global_index}")
            if int(self.level_global_index_by_record[recno]) != global_index:
                raise AtomicDatabaseError(f"level pointer roundtrip failed at global level {global_index}")
            level_roundtrip += 1

        return {
            "n_line_roundtrips": line_roundtrip,
            "n_continuum_roundtrips": continuum_roundtrip,
            "n_level_roundtrips": level_roundtrip,
        }


@dataclass(frozen=True)
class AtomicDatabaseBuildResult:
    """Result returned by :func:`load_atomic_database_state`."""

    atomic_state: XSTARAtomicState
    master: XSTARMasterData
    derived: XSTARDerivedPointers


class DBWK2Instruction(IntEnum):
    """Runtime-relevant ``dbwk2`` instruction numbers."""

    BUILD_POINTERS = 7
    RECORD_INVENTORY = 12
    POINTER_REPORT = 25
    RECORDS_PER_ION = 28


@dataclass(frozen=True)
class DBWK2Result:
    instruction: int
    payload: Any
    source_routine: str = "dbwk2.f90"


def _find_hdu(hdul: fits.HDUList, name: str, fallback_index: int) -> fits.hdu.base.ExtensionHDU:
    try:
        return hdul[name]
    except (KeyError, IndexError):
        try:
            return hdul[fallback_index]
        except IndexError as exc:
            raise AtomicDatabaseError(f"atdb.fits is missing the {name} extension") from exc


def _packed_column(hdu: fits.hdu.base.ExtensionHDU) -> np.ndarray:
    if hdu.data is None:
        raise AtomicDatabaseError(f"FITS extension {hdu.name!r} has no data")
    data = hdu.data
    # Production atdb.fits stores one vector-valued column and one row.  This
    # also accepts a simple image/vector HDU for compact synthetic tests.
    if getattr(data, "dtype", None) is not None and data.dtype.names:
        first_name = data.dtype.names[0]
        return np.asarray(data[first_name][0]).reshape(-1)
    array = np.asarray(data)
    if array.ndim > 1 and array.shape[0] == 1:
        array = array[0]
    return array.reshape(-1)


def readtbl(
    filename: str | Path,
    *,
    memmap: bool = True,
    validate: bool = True,
) -> XSTARMasterData:
    """Translate ``readtbl.f90`` and return the packed master arrays.

    Parameters
    ----------
    filename:
        XSTAR ``atdb.fits`` path.
    memmap:
        Keep large FITS vectors memory mapped.  This should remain true for the
        production database.
    validate:
        Check FITS LENGTH keywords and every packed record span.
    """

    path = Path(filename).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"XSTAR atomic database not found: {path}")

    hdul = fits.open(path, mode="readonly", memmap=memmap, lazy_load_hdus=True)
    try:
        pointers_hdu = _find_hdu(hdul, "POINTERS", 1)
        reals_hdu = _find_hdu(hdul, "REALS", 2)
        integers_hdu = _find_hdu(hdul, "INTEGERS", 3)
        chars_hdu = _find_hdu(hdul, "CHARS", 4)

        n_records = int(pointers_hdu.header.get("LENGTH", 0))
        n_reals = int(reals_hdu.header.get("LENGTH", 0))
        n_integers = int(integers_hdu.header.get("LENGTH", 0))
        n_chars = int(chars_hdu.header.get("LENGTH", 0))

        packed_pointers = _packed_column(pointers_hdu)
        packed_reals = _packed_column(reals_hdu)
        packed_integers = _packed_column(integers_hdu)
        packed_chars = _packed_column(chars_hdu)

        if n_records <= 0:
            if packed_pointers.size % 10:
                raise AtomicDatabaseError("POINTERS vector length is not divisible by 10")
            n_records = packed_pointers.size // 10
        if n_reals <= 0:
            n_reals = packed_reals.size
        if n_integers <= 0:
            n_integers = packed_integers.size
        if n_chars <= 0:
            n_chars = packed_chars.size

        expected_pointers = 10 * n_records
        if packed_pointers.size != expected_pointers:
            raise AtomicDatabaseError(
                f"POINTERS size {packed_pointers.size} != 10*LENGTH {expected_pointers}"
            )
        for name, actual, expected in (
            ("REALS", packed_reals.size, n_reals),
            ("INTEGERS", packed_integers.size, n_integers),
            ("CHARS", packed_chars.size, n_chars),
        ):
            if actual < expected:
                raise AtomicDatabaseError(f"{name} size {actual} is smaller than LENGTH {expected}")

        master = XSTARMasterData(
            path=path,
            hdul=hdul,
            nptrs=FortranPointerTable(packed_pointers.reshape(n_records, 10)),
            rdat1=FortranPackedVector(packed_reals[:n_reals], name="rdat1"),
            idat1=FortranPackedVector(packed_integers[:n_integers], name="idat1"),
            kdat1=FortranPackedVector(packed_chars[:n_chars], name="kdat1"),
            creation_date=str(hdul[0].header.get("DATE", "")),
            creator=str(hdul[0].header.get("CREATOR", "")),
            np2=n_records,
            np1r=n_reals,
            np1i=n_integers,
            np1k=n_chars,
        )
        if validate:
            master.validate_pointer_spans()
        return master
    except Exception:
        hdul.close()
        raise


def _first_integer(master: XSTARMasterData, recno: int, *, default: int = 0) -> int:
    h = master.header(recno)
    if h.nint <= 0:
        return int(default)
    return int(master.idat1[h.int_ptr])


def _second_integer(master: XSTARMasterData, recno: int, *, default: int = 0) -> int:
    h = master.header(recno)
    if h.nint < 2:
        return int(default)
    return int(master.idat1[h.int_ptr + 1])


def _prescan_dimensions(master: XSTARMasterData) -> Dict[str, int]:
    rates = master.nptrs.numpy()[:, 2].astype(np.int64, copy=False)
    n_ions = int(np.count_nonzero(rates == 12))
    n_elements = int(np.count_nonzero(rates == 11))
    n_levels = int(np.count_nonzero(rates == 13))
    n_lines = int(np.count_nonzero(np.isin(rates, (4, 9, 14))))
    n_continua = int(np.count_nonzero(np.isin(rates, (1, 7))))
    max_rate_type = max(102, int(rates.max(initial=0)))
    max_local_level = 0
    for recno in np.flatnonzero(rates == 13) + 1:
        try:
            max_local_level = max(max_local_level, master.local_level_index(int(recno)))
        except AtomicDatabaseError:
            pass
    return {
        "n_ions": n_ions,
        "n_elements": n_elements,
        "n_levels": n_levels,
        "n_lines": n_lines,
        "n_continua": n_continua,
        "max_rate_type": max_rate_type,
        "max_local_level": max(max_local_level, 1),
    }


def _apply_line_wavelength_absolute_values(
    master: XSTARMasterData, derived: XSTARDerivedPointers
) -> int:
    """Apply XSTAR's optional ``llinabs`` mutation using vectorized overrides."""
    if int(derived.nlsvn) <= 0:
        return 0
    records = np.asarray(derived.nplin[1 : int(derived.nlsvn) + 1], dtype=np.int64)
    pointer_rows = master.nptrs.numpy()[records - 1]
    valid = np.asarray(pointer_rows[:, 4] > 0, dtype=bool)
    if not np.any(valid):
        return 0
    packed_indices = np.asarray(pointer_rows[valid, 7], dtype=np.int64)
    wavelengths = master.rdat1.gather(packed_indices, dtype=np.float64)
    negative = wavelengths < 0.0
    if not np.any(negative):
        return 0
    master.rdat1.set_overrides(packed_indices[negative], np.abs(wavelengths[negative]))
    return int(np.count_nonzero(negative))


def setptrs(
    master: XSTARMasterData,
    *,
    abundances: Optional[Sequence[float]] = None,
    llinabs: bool = False,
    validate: bool = True,
) -> XSTARDerivedPointers:
    """Translate the active pointer-construction path of ``setptrs.f90``.

    The original routine assumes the records are grouped as element header,
    ion header, levels, and rate families.  This translation preserves that
    ordering and raises on malformed input instead of silently walking beyond
    the packed table.
    """

    dims = _prescan_dimensions(master)
    n_records = master.np2
    n_ions = dims["n_ions"]
    n_elements = dims["n_elements"]
    n_levels = dims["n_levels"]
    max_rate = dims["max_rate_type"]
    max_local_level = dims["max_local_level"]

    if abundances is not None and len(abundances) < n_elements:
        raise ValueError(
            f"abundances has {len(abundances)} values but database contains {n_elements} elements"
        )

    npar = np.zeros(n_records + 1, dtype=np.int32)
    npnxt = np.zeros(n_records + 1, dtype=np.int32)
    npfirst = np.zeros(max_rate + 1, dtype=np.int32)
    npfi = np.zeros((max_rate + 1, n_ions + 1), dtype=np.int32)
    npfe = np.zeros((max(30, n_elements) + 1, max_rate + 1), dtype=np.int32)
    nplin = np.zeros(dims["n_lines"] + 1, dtype=np.int32)
    nplini = np.zeros(n_records + 1, dtype=np.int32)
    npcon = np.zeros(dims["n_continua"] + 1, dtype=np.int32)
    npconi2 = np.zeros(n_records + 1, dtype=np.int32)
    npconi = np.zeros(n_records + 1, dtype=np.int32)
    npilev = np.zeros((max_local_level + 1, n_ions + 1), dtype=np.int32)
    npilevi = np.zeros(n_levels + 1, dtype=np.int32)
    nlevs = np.zeros(n_ions + 1, dtype=np.int32)
    nptrt = np.arange(n_records + 1, dtype=np.int32)
    element_records = np.zeros(n_elements + 1, dtype=np.int32)
    ion_records = np.zeros(n_ions + 1, dtype=np.int32)
    ion_element_z = np.zeros(n_ions + 1, dtype=np.int16)
    ion_stage = np.zeros(n_ions + 1, dtype=np.int16)
    level_record_by_global = np.zeros(n_levels + 1, dtype=np.int32)
    level_global_by_record = np.zeros(n_records + 1, dtype=np.int32)

    mlold = np.zeros(max_rate + 1, dtype=np.int32)
    indx = 1
    iion = 1
    global_level = 1
    icon = 1
    iline = 1
    element_ordinal = 0

    def rate_type(recno: int) -> int:
        if recno < 1 or recno > n_records:
            return 0
        return master.nptrs[3, recno]

    def chain_start(rate: int, recno: int, ion_index: Optional[int] = None) -> None:
        if rate < 0 or rate > max_rate:
            raise AtomicDatabaseError(f"rate type {rate} outside allocated range")
        if npfirst[rate] == 0:
            npfirst[rate] = recno
        elif mlold[rate] != 0:
            npnxt[mlold[rate]] = recno
        if ion_index is not None and npfi[rate, ion_index] == 0:
            npfi[rate, ion_index] = recno

    while indx <= n_records:
        while indx <= n_records and rate_type(indx) not in (11, 0):
            indx += 1
        if indx > n_records or rate_type(indx) == 0:
            break

        # Element header (rate type 11).
        element_ordinal += 1
        element_rec = indx
        chain_start(11, element_rec)
        mlold[11] = element_rec
        npar[element_rec] = 0
        if element_ordinal < element_records.size:
            element_records[element_ordinal] = element_rec
        element_z = _first_integer(master, element_rec, default=element_ordinal)
        indx += 1

        # Ion blocks belonging to this element.
        while indx <= n_records and rate_type(indx) == 12:
            if iion > n_ions:
                raise AtomicDatabaseError("setptrs encountered more ion headers than prescan")
            ion_rec = indx
            chain_start(12, ion_rec)
            mlold[12] = ion_rec
            npar[ion_rec] = element_rec
            ion_records[iion] = ion_rec
            ion_element_z[iion] = element_z
            ion_stage[iion] = _first_integer(master, ion_rec, default=iion)
            indx += 1

            # Level records, rate type 13.
            local_level_records: Dict[int, int] = {}
            if indx <= n_records and rate_type(indx) == 13:
                chain_start(13, indx, iion)
                local_ordinal = 1
                while indx <= n_records and rate_type(indx) == 13:
                    npar[indx] = ion_rec
                    npnxt[indx] = indx + 1 if indx < n_records else 0
                    nclev = master.local_level_index(indx)
                    nlevs[iion] = max(nlevs[iion], nclev)
                    if local_ordinal >= npilev.shape[0]:
                        raise AtomicDatabaseError(
                            f"ion {iion} has more level records than allocated local-level dimension"
                        )
                    npilev[local_ordinal, iion] = global_level
                    npilevi[global_level] = local_ordinal
                    level_record_by_global[global_level] = indx
                    level_global_by_record[indx] = global_level
                    local_level_records[nclev] = indx
                    local_ordinal += 1
                    global_level += 1
                    indx += 1
                mlold[13] = indx - 1
                npnxt[indx - 1] = 0

            # Photoionization/recombination records, rate types 7 then 1.
            for current_rate in (7, 1):
                if indx <= n_records and rate_type(indx) == current_rate:
                    chain_start(current_rate, indx, iion)
                    while indx <= n_records and rate_type(indx) == current_rate:
                        npar[indx] = ion_rec
                        npnxt[indx] = indx + 1 if indx < n_records else 0
                        if icon >= npcon.size:
                            raise AtomicDatabaseError("continuum pointer count exceeded prescan")
                        npcon[icon] = indx
                        nclev = master.local_level_index(indx)
                        level_rec = local_level_records.get(nclev, 0)
                        if level_rec == 0:
                            raise AtomicDatabaseError(
                                f"photoionization record {indx} references missing local level {nclev} "
                                f"in ion {iion}"
                            )
                        npconi2[indx] = icon
                        npconi[level_rec] = icon
                        indx += 1
                        icon += 1
                    mlold[current_rate] = indx - 1
                    npnxt[indx - 1] = 0

            # Bound-bound line families.
            for current_rate in (4, 9, 14):
                if indx <= n_records and rate_type(indx) == current_rate:
                    chain_start(current_rate, indx, iion)
                    while indx <= n_records and rate_type(indx) == current_rate:
                        npar[indx] = ion_rec
                        npnxt[indx] = indx + 1 if indx < n_records else 0
                        if iline >= nplin.size:
                            raise AtomicDatabaseError("line pointer count exceeded prescan")
                        nplin[iline] = indx
                        nplini[indx] = iline
                        indx += 1
                        iline += 1
                    mlold[current_rate] = indx - 1
                    npnxt[indx - 1] = 0

            # Rate families called out explicitly in setptrs.f90.
            for current_rate in (6, 8, 3, 5, 40):
                if indx <= n_records and rate_type(indx) == current_rate:
                    chain_start(current_rate, indx, iion)
                    while indx <= n_records and rate_type(indx) == current_rate:
                        npar[indx] = ion_rec
                        npnxt[indx] = indx + 1 if indx < n_records else 0
                        indx += 1
                    mlold[current_rate] = indx - 1
                    npnxt[indx - 1] = 0

            # All remaining ion-local rate families until next ion/element.
            while indx <= n_records and rate_type(indx) not in (0, 11, 12):
                current_rate = rate_type(indx)
                npar[indx] = ion_rec
                chain_start(current_rate, indx, iion)
                mlold[current_rate] = indx
                indx += 1

            iion += 1

    nlsvn = iline - 1
    ncsvn = icon - 1
    actual_ions = iion - 1
    actual_levels = global_level - 1

    if actual_ions != n_ions:
        raise AtomicDatabaseError(f"setptrs built {actual_ions} ions; prescan found {n_ions}")
    if actual_levels != n_levels:
        raise AtomicDatabaseError(f"setptrs built {actual_levels} levels; prescan found {n_levels}")
    if nlsvn != dims["n_lines"]:
        raise AtomicDatabaseError(f"setptrs built {nlsvn} lines; prescan found {dims['n_lines']}")
    if ncsvn != dims["n_continua"]:
        raise AtomicDatabaseError(
            f"setptrs built {ncsvn} continua; prescan found {dims['n_continua']}"
        )

    derived = XSTARDerivedPointers(
        npar=npar,
        npnxt=npnxt,
        npfirst=npfirst,
        npfi=npfi,
        npfe=npfe,
        nplin=nplin,
        nplini=nplini,
        npcon=npcon,
        npconi2=npconi2,
        npconi=npconi,
        npilev=npilev,
        npilevi=npilevi,
        nlevs=nlevs,
        nptrt=nptrt,
        element_records=element_records,
        ion_records=ion_records,
        ion_element_z=ion_element_z,
        ion_stage=ion_stage,
        level_record_by_global_index=level_record_by_global,
        level_global_index_by_record=level_global_by_record,
        nlsvn=nlsvn,
        ncsvn=ncsvn,
        n_ions=actual_ions,
        n_elements=element_ordinal,
        n_level_records=actual_levels,
        max_rate_type=max_rate,
        provenance={
            "source_routine": "setptrs.f90",
            "record_order_policy": "source_faithful_grouped_scan",
            "dynamic_allocation": True,
            "llinabs": bool(llinabs),
            "abundance_filter_applied": False,
        },
    )
    if llinabs:
        derived.provenance["n_line_wavelengths_made_absolute"] = (
            _apply_line_wavelength_absolute_values(master, derived)
        )
    if validate:
        checks = derived.validate(master)
        derived.provenance.update(checks)
    return derived


def _record_inventory(master: XSTARMasterData, derived: Optional[XSTARDerivedPointers]) -> List[Dict[str, int]]:
    rows: List[Dict[str, int]] = []
    for recno in range(1, master.np2 + 1):
        h = master.header(recno)
        rows.append(
            {
                "record": recno,
                "data_type": h.data_type,
                "rate_type": h.rate_type,
                "parent_record": int(derived.npar[recno]) if derived is not None else 0,
                "next_record": int(derived.npnxt[recno]) if derived is not None else 0,
                "line_index": int(derived.nplini[recno]) if derived is not None else 0,
                "continuum_index": int(derived.npconi2[recno]) if derived is not None else 0,
            }
        )
    return rows


def _records_per_ion(master: XSTARMasterData, derived: XSTARDerivedPointers) -> List[Dict[str, int]]:
    rows: List[Dict[str, int]] = []
    for ion_index in range(1, derived.n_ions + 1):
        ion_rec = int(derived.ion_records[ion_index])
        counts: Dict[int, int] = {}
        for recno in range(1, master.np2 + 1):
            if int(derived.npar[recno]) == ion_rec or recno == ion_rec:
                rate = master.header(recno).rate_type
                counts[rate] = counts.get(rate, 0) + 1
        rows.append(
            {
                "ion_index": ion_index,
                "element_z": int(derived.ion_element_z[ion_index]),
                "ion_stage": int(derived.ion_stage[ion_index]),
                "ion_record": ion_rec,
                "n_levels": int(derived.nlevs[ion_index]),
                "n_records": int(sum(counts.values())),
                **{f"rate_type_{rate}": count for rate, count in sorted(counts.items())},
            }
        )
    return rows


def dbwk2(
    instruction: int | DBWK2Instruction,
    master: XSTARMasterData,
    *,
    derived: Optional[XSTARDerivedPointers] = None,
    abundances: Optional[Sequence[float]] = None,
    llinabs: bool = False,
) -> DBWK2Result:
    """Port runtime-relevant, non-interactive ``dbwk2.f90`` operations.

    Instructions 2, 3, 8, and other editing/terminal modes are intentionally
    rejected: normal XSTAR execution never calls them, and mutating a packed
    read-only FITS database would slow the full physics port without advancing
    source-equivalent model execution.
    """

    value = int(instruction)
    if value == int(DBWK2Instruction.BUILD_POINTERS):
        built = setptrs(master, abundances=abundances, llinabs=llinabs, validate=True)
        return DBWK2Result(value, built)
    if value == int(DBWK2Instruction.RECORD_INVENTORY):
        return DBWK2Result(value, _record_inventory(master, derived))
    if value == int(DBWK2Instruction.POINTER_REPORT):
        if derived is None:
            raise ValueError("dbwk2 pointer report requires derived pointers")
        payload = {
            "npfirst": derived.npfirst.copy(),
            "npar": derived.npar.copy(),
            "npnxt": derived.npnxt.copy(),
            "npfi": derived.npfi.copy(),
            "nplin": derived.nplin.copy(),
            "npcon": derived.npcon.copy(),
            "nlevs": derived.nlevs.copy(),
        }
        return DBWK2Result(value, payload)
    if value == int(DBWK2Instruction.RECORDS_PER_ION):
        if derived is None:
            raise ValueError("dbwk2 records-per-ion report requires derived pointers")
        return DBWK2Result(value, _records_per_ion(master, derived))
    raise NotImplementedError(
        f"dbwk2 instruction {value} is an interactive/editing utility mode and is not "
        "part of the XSTAR runtime setup path"
    )



POINTER_CACHE_FORMAT_VERSION = 2


def default_derived_pointer_cache_path(fitsfile: str | Path) -> Path:
    """Return the default vectorized source-port pointer-cache sidecar."""
    path = Path(fitsfile)
    return path.with_name(path.name + ".xstar_atomic_source_port.npz")


def atomic_database_fingerprint(master: XSTARMasterData) -> Dict[str, Any]:
    """Return a lightweight identity record for cache validation."""
    stat = master.path.stat()
    return {
        "format_version": POINTER_CACHE_FORMAT_VERSION,
        "file_size": int(stat.st_size),
        "file_mtime_ns": int(stat.st_mtime_ns),
        "creation_date": master.creation_date,
        "creator": master.creator,
        "n_records": master.np2,
        "n_reals": master.np1r,
        "n_integers": master.np1i,
        "n_chars": master.np1k,
    }


def save_derived_pointer_cache(
    master: XSTARMasterData,
    derived: XSTARDerivedPointers,
    path: str | Path,
) -> Path:
    """Persist the translated ``setptrs`` products as a compact NPZ file."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "fingerprint": atomic_database_fingerprint(master),
        "nlsvn": derived.nlsvn,
        "ncsvn": derived.ncsvn,
        "n_ions": derived.n_ions,
        "n_elements": derived.n_elements,
        "n_level_records": derived.n_level_records,
        "max_rate_type": derived.max_rate_type,
        "provenance": derived.provenance,
    }
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            # Uncompressed NPZ is intentionally used here: these dense numeric
            # arrays are startup caches, and decompression cost dominated repeat
            # physical runs on production ATDB files.
            np.savez(
                handle,
                metadata_json=np.asarray(json.dumps(metadata, separators=(",", ":"))),
                npar=derived.npar,
                npnxt=derived.npnxt,
                npfirst=derived.npfirst,
                npfi=derived.npfi,
                npfe=derived.npfe,
                nplin=derived.nplin,
                nplini=derived.nplini,
                npcon=derived.npcon,
                npconi2=derived.npconi2,
                npconi=derived.npconi,
                npilev=derived.npilev,
                npilevi=derived.npilevi,
                nlevs=derived.nlevs,
                nptrt=derived.nptrt,
                element_records=derived.element_records,
                ion_records=derived.ion_records,
                ion_element_z=derived.ion_element_z,
                ion_stage=derived.ion_stage,
                level_record_by_global_index=derived.level_record_by_global_index,
                level_global_index_by_record=derived.level_global_index_by_record,
            )
        os.replace(temporary_name, target)
    except Exception:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise
    return target


def load_derived_pointer_cache(
    master: XSTARMasterData,
    path: str | Path,
    *,
    validate: bool = True,
) -> XSTARDerivedPointers:
    """Load a cached pointer hierarchy after validating ATDB identity."""
    source = Path(path)
    with np.load(source, allow_pickle=False) as z:
        metadata = json.loads(str(z["metadata_json"].item()))
        cached = metadata.get("fingerprint", {})
        current = atomic_database_fingerprint(master)
        if cached != current:
            raise AtomicDatabaseError(
                f"stale pointer cache {source}: ATDB fingerprint does not match"
            )
        derived = XSTARDerivedPointers(
            npar=np.asarray(z["npar"], dtype=np.int32),
            npnxt=np.asarray(z["npnxt"], dtype=np.int32),
            npfirst=np.asarray(z["npfirst"], dtype=np.int32),
            npfi=np.asarray(z["npfi"], dtype=np.int32),
            npfe=np.asarray(z["npfe"], dtype=np.int32),
            nplin=np.asarray(z["nplin"], dtype=np.int32),
            nplini=np.asarray(z["nplini"], dtype=np.int32),
            npcon=np.asarray(z["npcon"], dtype=np.int32),
            npconi2=np.asarray(z["npconi2"], dtype=np.int32),
            npconi=np.asarray(z["npconi"], dtype=np.int32),
            npilev=np.asarray(z["npilev"], dtype=np.int32),
            npilevi=np.asarray(z["npilevi"], dtype=np.int32),
            nlevs=np.asarray(z["nlevs"], dtype=np.int32),
            nptrt=np.asarray(z["nptrt"], dtype=np.int32),
            element_records=np.asarray(z["element_records"], dtype=np.int32),
            ion_records=np.asarray(z["ion_records"], dtype=np.int32),
            ion_element_z=np.asarray(z["ion_element_z"], dtype=np.int16),
            ion_stage=np.asarray(z["ion_stage"], dtype=np.int16),
            level_record_by_global_index=np.asarray(z["level_record_by_global_index"], dtype=np.int32),
            level_global_index_by_record=np.asarray(z["level_global_index_by_record"], dtype=np.int32),
            nlsvn=int(metadata["nlsvn"]),
            ncsvn=int(metadata["ncsvn"]),
            n_ions=int(metadata["n_ions"]),
            n_elements=int(metadata["n_elements"]),
            n_level_records=int(metadata["n_level_records"]),
            max_rate_type=int(metadata["max_rate_type"]),
            provenance={**metadata.get("provenance", {}), "pointer_cache_status": "hit"},
        )
    if validate:
        derived.validate(master)
    return derived


def write_atomic_database_products(
    master: XSTARMasterData,
    derived: XSTARDerivedPointers,
    out_dir: str | Path,
) -> Dict[str, str]:
    """Write reusable pointer products and a concise source-port report."""
    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    cache_path = save_derived_pointer_cache(
        master, derived, output / "xstar_atomic_derived_pointers.npz"
    )
    ions_path = output / "xstar_atomic_ions.csv"
    with ions_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ion_index", "element_z", "ion_stage", "ion_record",
                "n_levels", "first_level_record",
            ],
        )
        writer.writeheader()
        for ion_index in range(1, derived.n_ions + 1):
            writer.writerow(
                {
                    "ion_index": ion_index,
                    "element_z": int(derived.ion_element_z[ion_index]),
                    "ion_stage": int(derived.ion_stage[ion_index]),
                    "ion_record": int(derived.ion_records[ion_index]),
                    "n_levels": int(derived.nlevs[ion_index]),
                    "first_level_record": int(derived.npfi[13, ion_index]),
                }
            )

    rate_path = output / "xstar_atomic_rate_type_summary.csv"
    rates = master.nptrs.numpy()[:, 2].astype(int, copy=False)
    with rate_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["rate_type", "n_records", "first_record"]
        )
        writer.writeheader()
        for rate_type in sorted(set(rates.tolist())):
            if rate_type <= 0:
                continue
            writer.writerow(
                {
                    "rate_type": rate_type,
                    "n_records": int(np.count_nonzero(rates == rate_type)),
                    "first_record": int(derived.npfirst[rate_type])
                    if rate_type < derived.npfirst.size else 0,
                }
            )

    summary = {
        "port_version": "v0.4.1",
        "status": "readtbl_setptrs_completed",
        "atdb_path": str(master.path),
        "creation_date": master.creation_date,
        "creator": master.creator,
        "n_records": master.np2,
        "n_reals": master.np1r,
        "n_integers": master.np1i,
        "n_chars": master.np1k,
        "n_elements": derived.n_elements,
        "n_ions": derived.n_ions,
        "n_level_records": derived.n_level_records,
        "n_lines": derived.nlsvn,
        "n_continua": derived.ncsvn,
        "max_rate_type": derived.max_rate_type,
        "pointer_initialization_ready": True,
        "dbwk2_runtime_pointer_mode_ready": True,
        "dbwk2_interactive_editing_modes_ported": False,
        "next_source_port_target": "complete_ucalc_dispatch_and_called_rate_routines",
        "provenance": derived.provenance,
    }
    json_path = output / "xstar_atomic_database_port_summary.json"
    json_path.write_text(json.dumps(summary, indent=2) + "\n")
    markdown_path = output / "xstar_atomic_database_port_summary.md"
    markdown_path.write_text(
        "# XSTAR atomic-database source port\n\n"
        + "\n".join(f"- **{key}:** `{value}`" for key, value in summary.items() if key != "provenance")
        + "\n"
    )
    return {
        "pointer_cache": str(cache_path),
        "ions_csv": str(ions_path),
        "rate_type_summary_csv": str(rate_path),
        "json": str(json_path),
        "markdown": str(markdown_path),
    }

def populate_atomic_state(
    atomic: XSTARAtomicState,
    master: XSTARMasterData,
    derived: XSTARDerivedPointers,
) -> XSTARAtomicState:
    """Attach translated master/derived data to :class:`XSTARAtomicState`."""

    atomic.atdb_path = str(master.path)
    atomic.master = master
    atomic.derived = derived
    atomic.tables.update(
        {
            "nptrs": master.nptrs,
            "rdat1": master.rdat1,
            "idat1": master.idat1,
            "kdat1": master.kdat1,
        }
    )
    atomic.pointers.update(
        {
            "npar": derived.npar,
            "npnxt": derived.npnxt,
            "npfirst": derived.npfirst,
            "npfi": derived.npfi,
            "npfe": derived.npfe,
            "nplin": derived.nplin,
            "nplini": derived.nplini,
            "npcon": derived.npcon,
            "npconi": derived.npconi,
            "npconi2": derived.npconi2,
            "npilev": derived.npilev,
            "npilevi": derived.npilevi,
            "nlevs": derived.nlevs,
        }
    )
    atomic.provenance.update(
        {
            "source_routines": ["readtbl.f90", "setptrs.f90"],
            "creation_date": master.creation_date,
            "creator": master.creator,
            "n_records": master.np2,
            "n_reals": master.np1r,
            "n_integers": master.np1i,
            "n_chars": master.np1k,
            "n_elements": derived.n_elements,
            "n_ions": derived.n_ions,
            "n_level_records": derived.n_level_records,
            "n_lines": derived.nlsvn,
            "n_continua": derived.ncsvn,
            "pointer_initialization_ready": True,
        }
    )
    return atomic


def load_atomic_database_state(
    filename: str | Path,
    *,
    abundances: Optional[Sequence[float]] = None,
    llinabs: bool = False,
    memmap: bool = True,
    validate: bool = True,
    pointer_cache: str | Path | None = None,
    use_pointer_cache: bool = True,
    rebuild_pointer_cache: bool = False,
) -> AtomicDatabaseBuildResult:
    """Execute ``readtbl -> setptrs`` and return a populated atomic state.

    When ``pointer_cache`` is supplied, validated derived arrays are reused.
    A missing or explicitly rebuilt cache is written after source translation.
    """

    master = readtbl(filename, memmap=memmap, validate=validate)
    try:
        cache_path = Path(pointer_cache) if pointer_cache is not None else None
        derived: XSTARDerivedPointers
        cache_failure: str | None = None
        loaded_from_cache = False
        if (
            cache_path is not None
            and use_pointer_cache
            and cache_path.is_file()
            and not rebuild_pointer_cache
        ):
            try:
                derived = load_derived_pointer_cache(master, cache_path, validate=validate)
                loaded_from_cache = True
            except (AtomicDatabaseError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                cache_failure = exc.__class__.__name__
        if not loaded_from_cache:
            derived = setptrs(
                master,
                abundances=abundances,
                llinabs=llinabs,
                validate=validate,
            )
            if rebuild_pointer_cache:
                status = "rebuilt"
            elif cache_failure is not None:
                status = "stale_rebuilt"
            else:
                status = "miss"
            derived.provenance["pointer_cache_status"] = status
            if cache_failure is not None:
                derived.provenance["pointer_cache_failure"] = cache_failure
            if cache_path is not None and use_pointer_cache:
                save_derived_pointer_cache(master, derived, cache_path)
        else:
            derived.provenance["llinabs"] = bool(llinabs)
            if llinabs:
                derived.provenance["n_line_wavelengths_made_absolute"] = (
                    _apply_line_wavelength_absolute_values(master, derived)
                )
        if cache_path is not None:
            derived.provenance["pointer_cache_path"] = str(cache_path)
        atomic = populate_atomic_state(XSTARAtomicState(), master, derived)
        return AtomicDatabaseBuildResult(atomic_state=atomic, master=master, derived=derived)
    except Exception:
        master.close()
        raise


def register_atomic_database_stages(
    driver: Any,
    *,
    atdb_path: str | Path,
    abundances: Optional[Sequence[float]] = None,
    llinabs: bool = False,
    memmap: bool = True,
    validate: bool = True,
) -> None:
    """Register translated setup/read/pointer stages on ``XSTARPythonDriver``."""

    # Local import avoids a circular import at module initialization.
    from .driver import XSTARStage

    path = str(Path(atdb_path).expanduser().resolve())

    def setup_handler(state: XSTARPythonState) -> None:
        state.control["atdb_path"] = path
        state.control["atomic_abundances"] = list(abundances) if abundances is not None else None
        state.control["llinabs"] = bool(llinabs)

    def read_handler(state: XSTARPythonState) -> None:
        master = readtbl(path, memmap=memmap, validate=validate)
        state.atomic.atdb_path = path
        state.atomic.master = master
        state.atomic.tables.update(
            {"nptrs": master.nptrs, "rdat1": master.rdat1, "idat1": master.idat1, "kdat1": master.kdat1}
        )
        state.atomic.provenance.update(
            {
                "readtbl_ready": True,
                "creation_date": master.creation_date,
                "n_records": master.np2,
            }
        )

    def pointer_handler(state: XSTARPythonState) -> None:
        master = state.atomic.master
        if master is None:
            raise AtomicDatabaseError("BUILD_POINTERS stage requires readtbl master data")
        derived = setptrs(
            master,
            abundances=abundances,
            llinabs=llinabs,
            validate=validate,
        )
        populate_atomic_state(state.atomic, master, derived)

    driver.register(XSTARStage.SETUP, setup_handler, source_routines=("xstarsetup",))
    driver.register(
        XSTARStage.READ_ATOMIC_DATABASE,
        read_handler,
        source_routines=("readtbl",),
    )
    driver.register(
        XSTARStage.BUILD_POINTERS,
        pointer_handler,
        source_routines=("setptrs", "dbwk2[7]"),
    )
