#!/usr/bin/env python3
"""
xstar_atomic_hierarchy.py

Build a parent/child hierarchy over XSTAR's packed atdb.fits database.

This complements xstar_atomic_reader_inspect.py.  The FITS file is not a set of
semantic tables; it is four packed arrays.  This script follows the same
record-order idea used by XSTAR's setptrs.f90: element records (rate type 11)
contain ion records (rate type 12), which contain levels (rate type 13) and all
process records until the next ion/element header.

It does NOT implement ucalc physics formulas.  It is an indexing and extraction
layer.  The output is meant to be the bridge between raw atdb.fits and later
physics-specific parsers for lines, PI cross sections, recombination, Auger, etc.

Examples
--------

# Fast summary of hierarchy; loads POINTERS, INTEGERS, CHARS, but not REALS
python xstar_atomic_hierarchy.py ./xstar/data/atdb.fits --summary

# Write one indexed row per database record
python xstar_atomic_hierarchy.py ./xstar/data/atdb.fits --index-csv atdb_index.csv

# List elements and ions found by the hierarchy scan
python xstar_atomic_hierarchy.py ./xstar/data/atdb.fits --elements-csv atdb_elements.csv --ions-csv atdb_ions.csv

# Dump all O VIII records, excluding the huge real arrays
python xstar_atomic_hierarchy.py ./xstar/data/atdb.fits --element O --ion-stage 8 --dump --no-reals --limit 50

# Dump only radiative line records for O VIII
python xstar_atomic_hierarchy.py ./xstar/data/atdb.fits --element O --ion-stage 8 --rate-type 4 --dump --limit 20

Dependencies
------------
pip install astropy numpy
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import pickle
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
from astropy.io import fits


ELEMENT_SYMBOLS = [
    "", "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg",
    "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr",
    "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
]
SYMBOL_TO_Z = {s.upper(): z for z, s in enumerate(ELEMENT_SYMBOLS) if s}
Z_TO_SYMBOL = {z: s for z, s in enumerate(ELEMENT_SYMBOLS) if s}

RATE_TYPES: Dict[int, str] = {
    1: "ground state ionization",
    2: "level ionization/recombination",
    3: "bound-bound collision",
    4: "bound-bound radiative",
    5: "bound-free collision (level)",
    6: "total recombination",
    7: "bound-free radiative (level)",
    8: "total recombination",
    9: "2 photon decay",
    11: "element data",
    12: "ion data",
    13: "level data",
    14: "radiative superlevel->spectroscopic level",
    15: "CI total rate",
    23: "collisional superlevel->spectroscopic level",
    40: "CI from superlevels",
    41: "Auger decay / Fe K Auger",
    42: "fluorescence / Auger-related",
}

DATA_TYPES: Dict[int, str] = {
    1: "radiative recombination: Aldrovandi & Pequignot",
    2: "charge exchange H0: Kingdon & Ferland",
    6: "level data",
    7: "dielectronic recombination: Aldrovandi & Pequignot",
    9: "charge exchange H0 Kingdon & Ferland",
    10: "charge exchange H+ Kingdon & Ferland",
    13: "element data",
    14: "ion data",
    22: "dielectronic recombination: Storey",
    30: "radiative recombination hydrogenic: Gould & Thakur",
    49: "OP PI cross sections for inner shells",
    50: "OP line radiative rates",
    51: "OP and CHIANTI line collisional rates",
    53: "OP PI cross sections",
    54: "H-like Cij, Bautista, H-like ion",
    56: "tabulated collision strength, Bautista",
    57: "effective charge for collisional ionization",
    59: "Verner PI cross sections",
    60: "Calloway H-like collision strength",
    62: "Calloway H-like collision strength",
    63: "H-like Cij, Bautista, H-like ion",
    66: "like type 69 but fine-structure data",
    68: "He-like collision strengths by Zhang & Sampson",
    69: "Kato & Nakazaki fit to He-like collision strengths",
    70: "coefficients for photoionization cross sections of superlevels",
    71: "transition rates from superlevel to spectroscopic levels",
    72: "autoionization rates for satellite levels",
    73: "fit to collisional strengths, satellite levels, He-like ions",
    74: "delta functions added to photoionization cross sections for DR",
    75: "autoionization data for Fe XXIV satellites",
    76: "2 photon decay",
    77: "collisional rates from 71",
    81: "Bhatia Fe XIX collision strengths",
    82: "Fe UTA radiative rates",
    83: "Fe UTA level data",
    85: "Iron K PI cross sections, spectator Auger summed",
    86: "Iron K Auger data",
    88: "unlabeled XSTAR data type 88",
    91: "unlabeled XSTAR data type 91",
    92: "unlabeled XSTAR data type 92",
    95: "Bryans collisional ionization / CI total rates",
    98: "CHIANTI 2016 collisional excitation rates",
    99: "unlabeled XSTAR data type 99",
}


def roman(n: Optional[int]) -> str:
    if n is None or n <= 0:
        return ""
    vals = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
            (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
            (5, "V"), (4, "IV"), (1, "I")]
    out = []
    for v, s in vals:
        while n >= v:
            out.append(s)
            n -= v
    return "".join(out)


def ion_label(symbol: str, stage: Optional[int]) -> str:
    return f"{symbol} {roman(stage)}" if symbol and stage else ""


def charge_label(symbol: str, stage: Optional[int]) -> str:
    if not symbol or not stage:
        return ""
    return f"{symbol}{stage-1}p"


def decode_chars(byte_arr: np.ndarray) -> str:
    return bytes(byte_arr.astype(np.uint8).tolist()).decode("ascii", errors="replace").strip()


@dataclass
class Header:
    recno: int
    raw0: int
    data_type: int
    rate_type: int
    continuation: int
    nreal: int
    nint: int
    nchar: int
    real_ptr: int
    int_ptr: int
    char_ptr: int


@dataclass
class IndexedRecord:
    recno: int
    data_type: int
    rate_type: int
    continuation: int
    nreal: int
    nint: int
    nchar: int
    real_ptr: int
    int_ptr: int
    char_ptr: int
    element_z: Optional[int]
    element_symbol: str
    element_name: str
    element_record: Optional[int]
    ion_global_index: Optional[int]
    ion_stage: Optional[int]
    ion_label: str
    charge_label: str
    ion_record: Optional[int]
    level_index: Optional[int]
    parent_kind: str
    data_type_label: str
    rate_type_label: str


@dataclass
class ElementInfo:
    z: int
    symbol: str
    name: str
    record: int
    abundance: Optional[float]
    atomic_weight: Optional[float]
    raw_integers: List[int]


@dataclass
class IonInfo:
    global_index: int
    z: int
    symbol: str
    element_name: str
    ion_stage: int
    label: str
    charge_label: str
    record: int
    n_levels: int
    raw_reals: List[float]
    raw_integers: List[int]
    raw_chars: str


INDEX_CACHE_FORMAT_VERSION = 1
INDEX_CACHE_NPZ_FORMAT_VERSION = 1


def default_index_cache_path(fitsfile: str | Path, cache_format: str = "npz") -> Path:
    """Return the default on-disk index-cache path for an ``atdb.fits`` file.

    Parameters
    ----------
    fitsfile:
        Path to the packed XSTAR ``atdb.fits`` file.
    cache_format:
        ``"npz"`` for the compact NumPy cache or ``"pickle"`` for the
        legacy Python-object cache.
    """
    path = Path(fitsfile)
    fmt = (cache_format or "npz").lower()
    suffix = ".xstar_atomic_index.pkl" if fmt == "pickle" else ".xstar_atomic_index.npz"
    return path.with_name(path.name + suffix)


def _file_signature(path: Path) -> dict:
    """Return stable metadata used to validate an index cache."""
    st = path.stat()
    return {
        "path": str(path.resolve()),
        "size": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
    }


def _cache_metadata(db: "ATDB") -> dict:
    """Build metadata stored alongside cached hierarchy objects."""
    return {
        "format_version": INDEX_CACHE_FORMAT_VERSION,
        "fits_signature": _file_signature(db.filename),
        "date": db.date,
        "creator": db.creator,
        "n_records": db.n_records,
        "n_reals": db.n_reals,
        "n_integers": db.n_integers,
        "n_chars": db.n_chars,
    }


def _cache_metadata_matches(db: "ATDB", metadata: dict) -> bool:
    """Return True when cache metadata describes the currently opened FITS file."""
    if not isinstance(metadata, dict):
        return False
    expected = _cache_metadata(db)
    for key in ("format_version", "fits_signature", "n_records", "n_reals", "n_integers", "n_chars"):
        if metadata.get(key) != expected.get(key):
            return False
    return True


def _safe_int_array(values, dtype=np.int64) -> np.ndarray:
    return np.asarray([(-1 if v is None else int(v)) for v in values], dtype=dtype)


def _safe_str_array(values) -> np.ndarray:
    vals = ["" if v is None else str(v) for v in values]
    max_len = max((len(v) for v in vals), default=1)
    return np.asarray(vals, dtype=f"U{max(1, max_len)}")


def _restore_optional_int(value: int) -> Optional[int]:
    value = int(value)
    return None if value < 0 else value


def _dataclass_dict_list_json(rows: list[object]) -> str:
    return json.dumps([asdict(row) for row in rows], separators=(",", ":"))


def _write_npz_index_cache(path: Path, db: "ATDB", records: List[IndexedRecord], elements: List[ElementInfo], ions: List[IonInfo]) -> None:
    """Write a compact NumPy/NPZ hierarchy index cache.

    The full record list is stored column-wise so loading avoids unpickling more
    than one million Python objects.  Element and ion tables are tiny, so they are
    stored as compact JSON payloads inside the NPZ file.
    """
    metadata = _cache_metadata(db)
    metadata["format_version"] = INDEX_CACHE_NPZ_FORMAT_VERSION
    metadata["cache_kind"] = "npz"

    tmp_file = path.with_suffix(path.suffix + ".tmp")
    with tmp_file.open("wb") as handle:
        np.savez(
            handle,
        metadata_json=np.asarray(json.dumps(metadata, separators=(",", ":"))),
        elements_json=np.asarray(_dataclass_dict_list_json(elements)),
        ions_json=np.asarray(_dataclass_dict_list_json(ions)),
        recno=np.asarray([r.recno for r in records], dtype=np.int32),
        data_type=np.asarray([r.data_type for r in records], dtype=np.int16),
        rate_type=np.asarray([r.rate_type for r in records], dtype=np.int16),
        continuation=np.asarray([r.continuation for r in records], dtype=np.int16),
        nreal=np.asarray([r.nreal for r in records], dtype=np.int32),
        nint=np.asarray([r.nint for r in records], dtype=np.int32),
        nchar=np.asarray([r.nchar for r in records], dtype=np.int32),
        real_ptr=np.asarray([r.real_ptr for r in records], dtype=np.int64),
        int_ptr=np.asarray([r.int_ptr for r in records], dtype=np.int64),
        char_ptr=np.asarray([r.char_ptr for r in records], dtype=np.int64),
        element_z=_safe_int_array([r.element_z for r in records], dtype=np.int16),
        element_symbol=_safe_str_array([r.element_symbol for r in records]),
        element_name=_safe_str_array([r.element_name for r in records]),
        element_record=_safe_int_array([r.element_record for r in records], dtype=np.int32),
        ion_global_index=_safe_int_array([r.ion_global_index for r in records], dtype=np.int32),
        ion_stage=_safe_int_array([r.ion_stage for r in records], dtype=np.int16),
        ion_label=_safe_str_array([r.ion_label for r in records]),
        charge_label=_safe_str_array([r.charge_label for r in records]),
        ion_record=_safe_int_array([r.ion_record for r in records], dtype=np.int32),
        level_index=_safe_int_array([r.level_index for r in records], dtype=np.int32),
        parent_kind=_safe_str_array([r.parent_kind for r in records]),
        data_type_label=_safe_str_array([r.data_type_label for r in records]),
            rate_type_label=_safe_str_array([r.rate_type_label for r in records]),
        )
    os.replace(tmp_file, path)


def _load_npz_index_cache(path: Path, db: "ATDB") -> Tuple[List[IndexedRecord], List[ElementInfo], List[IonInfo]]:
    """Load a compact NumPy/NPZ hierarchy index cache."""
    with np.load(path, allow_pickle=False) as z:
        metadata = json.loads(str(z["metadata_json"].item()))
        metadata_for_check = dict(metadata)
        metadata_for_check["format_version"] = INDEX_CACHE_FORMAT_VERSION
        if not _cache_metadata_matches(db, metadata_for_check):
            raise ValueError("stale NPZ index cache")
        elements = [ElementInfo(**row) for row in json.loads(str(z["elements_json"].item()))]
        ions = [IonInfo(**row) for row in json.loads(str(z["ions_json"].item()))]
        n = len(z["recno"])
        records = [
            IndexedRecord(
                recno=int(z["recno"][i]),
                data_type=int(z["data_type"][i]),
                rate_type=int(z["rate_type"][i]),
                continuation=int(z["continuation"][i]),
                nreal=int(z["nreal"][i]),
                nint=int(z["nint"][i]),
                nchar=int(z["nchar"][i]),
                real_ptr=int(z["real_ptr"][i]),
                int_ptr=int(z["int_ptr"][i]),
                char_ptr=int(z["char_ptr"][i]),
                element_z=_restore_optional_int(z["element_z"][i]),
                element_symbol=str(z["element_symbol"][i]),
                element_name=str(z["element_name"][i]),
                element_record=_restore_optional_int(z["element_record"][i]),
                ion_global_index=_restore_optional_int(z["ion_global_index"][i]),
                ion_stage=_restore_optional_int(z["ion_stage"][i]),
                ion_label=str(z["ion_label"][i]),
                charge_label=str(z["charge_label"][i]),
                ion_record=_restore_optional_int(z["ion_record"][i]),
                level_index=_restore_optional_int(z["level_index"][i]),
                parent_kind=str(z["parent_kind"][i]),
                data_type_label=str(z["data_type_label"][i]),
                rate_type_label=str(z["rate_type_label"][i]),
            )
            for i in range(n)
        ]
    return records, elements, ions


class ATDB:
    def __init__(self, filename: str | Path, load_reals: bool = False):
        self.filename = Path(filename)
        self.hdul = fits.open(self.filename, memmap=True, lazy_load_hdus=True)
        self.date = self.hdul[0].header.get("DATE")
        self.creator = self.hdul[0].header.get("CREATOR")
        self.n_records = int(self.hdul["POINTERS"].header["LENGTH"])
        self.n_reals = int(self.hdul["REALS"].header["LENGTH"])
        self.n_integers = int(self.hdul["INTEGERS"].header["LENGTH"])
        self.n_chars = int(self.hdul["CHARS"].header["LENGTH"])
        ptr = np.asarray(self.hdul["POINTERS"].data[0][0], dtype=np.int64)
        self.pointers = ptr.reshape(self.n_records, 10)
        self._reals = None
        self._integers = None
        self._chars = None
        self._index_records = None
        self._index_elements = None
        self._index_ions = None
        self._last_index_cache_path = None
        self._last_index_cache_status = "not_used"
        if load_reals:
            self.load_reals()

    def close(self):
        self.hdul.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    @property
    def integers(self) -> np.ndarray:
        if self._integers is None:
            self._integers = np.asarray(self.hdul["INTEGERS"].data[0][0], dtype=np.int64)
        return self._integers

    @property
    def chars(self) -> np.ndarray:
        if self._chars is None:
            self._chars = np.asarray(self.hdul["CHARS"].data[0][0], dtype=np.uint8)
        return self._chars

    @property
    def reals(self) -> np.ndarray:
        if self._reals is None:
            self.load_reals()
        return self._reals

    def load_reals(self) -> np.ndarray:
        self._reals = np.asarray(self.hdul["REALS"].data[0][0], dtype=np.float32)
        return self._reals

    def header(self, recno: int) -> Header:
        p = self.pointers[recno - 1]
        return Header(recno, *[int(x) for x in p])

    def real_slice(self, h: Header) -> List[float]:
        if h.nreal <= 0:
            return []
        i0 = h.real_ptr - 1
        return self.reals[i0:i0 + h.nreal].astype(float).tolist()

    def int_slice(self, h: Header) -> List[int]:
        if h.nint <= 0:
            return []
        i0 = h.int_ptr - 1
        return self.integers[i0:i0 + h.nint].astype(int).tolist()

    def char_slice(self, h: Header) -> str:
        if h.nchar <= 0:
            return ""
        i0 = h.char_ptr - 1
        return decode_chars(self.chars[i0:i0 + h.nchar])

    def level_index_from_ints(self, ints: List[int]) -> Optional[int]:
        # XSTAR setptrs.f90 uses idat(nidt-1) for nclev: the second-to-last
        # integer in the unpacked record.
        if len(ints) >= 2:
            return int(ints[-2])
        return None

    def build_index(
        self,
        *,
        use_cache: bool = False,
        cache_path: str | Path | None = None,
        rebuild_cache: bool = False,
        cache_format: str = "npz",
    ) -> Tuple[List[IndexedRecord], List[ElementInfo], List[IonInfo]]:
        """Build the hierarchy index and optionally use an on-disk cache.

        Parameters
        ----------
        use_cache:
            If ``True``, try to load ``(records, elements, ions)`` from a pickle
            cache before scanning the full ATDB pointer table.
        cache_path:
            Optional explicit cache filename.  If omitted and ``use_cache`` is
            true, the default is ``atdb.fits.xstar_atomic_index.npz`` next to the
            FITS file.
        rebuild_cache:
            If ``True``, ignore an existing cache and write a fresh one after
            scanning.
        cache_format:
            ``"npz"`` for the compact NumPy cache, or ``"pickle"`` for the
            legacy Python-object cache.
        """
        if self._index_records is not None and not rebuild_cache:
            self._last_index_cache_status = "memory"
            return self._index_records, self._index_elements, self._index_ions

        fmt = (cache_format or "npz").lower()
        if fmt not in {"npz", "pickle"}:
            raise ValueError(f"Unsupported index cache format: {cache_format!r}")
        cache_file = Path(cache_path) if cache_path is not None else default_index_cache_path(self.filename, fmt)
        if use_cache:
            self._last_index_cache_path = cache_file
            if cache_file.exists() and not rebuild_cache:
                try:
                    if fmt == "npz":
                        records, elements, ions = _load_npz_index_cache(cache_file, self)
                        self._index_records = records
                        self._index_elements = elements
                        self._index_ions = ions
                    else:
                        with cache_file.open("rb") as handle:
                            payload = pickle.load(handle)
                        if not _cache_metadata_matches(self, payload.get("metadata", {})):
                            raise ValueError("stale pickle index cache")
                        self._index_records = payload["records"]
                        self._index_elements = payload["elements"]
                        self._index_ions = payload["ions"]
                    self._last_index_cache_status = f"{fmt}_hit"
                    return self._index_records, self._index_elements, self._index_ions
                except ValueError:
                    self._last_index_cache_status = f"{fmt}_stale"
                except Exception:
                    self._last_index_cache_status = f"{fmt}_read_failed"
            elif rebuild_cache:
                self._last_index_cache_status = "rebuild_requested"
            else:
                self._last_index_cache_status = "miss"
        else:
            self._last_index_cache_status = "disabled"

        records: List[IndexedRecord] = []
        elements: List[ElementInfo] = []
        ions: List[IonInfo] = []

        current_element: Optional[ElementInfo] = None
        current_ion: Optional[IonInfo] = None
        ion_ordinal_within_element: Dict[int, int] = {}
        global_ion_index = 0
        levels_for_ion: Dict[int, int] = {}

        for recno in range(1, self.n_records + 1):
            h = self.header(recno)
            ints = self.int_slice(h) if h.nint else []
            chars = self.char_slice(h) if h.nchar else ""

            if h.rate_type == 11 and h.data_type == 13:
                reals = self.real_slice(h)
                z = ints[0] if ints else None
                symbol = ELEMENT_SYMBOLS[z] if z and z < len(ELEMENT_SYMBOLS) else str(z or "")
                current_element = ElementInfo(
                    z=int(z or 0),
                    symbol=symbol,
                    name=chars,
                    record=recno,
                    abundance=float(reals[0]) if len(reals) > 0 else None,
                    atomic_weight=float(reals[1]) if len(reals) > 1 else None,
                    raw_integers=ints,
                )
                elements.append(current_element)
                current_ion = None
                ion_ordinal_within_element[current_element.z] = 0

            elif h.rate_type == 12 and h.data_type == 14 and current_element is not None:
                global_ion_index += 1
                ion_ordinal_within_element[current_element.z] += 1
                # Usually the first ion-data integer is the ion stage.  If this ever
                # disagrees with the sorted order, keep both in raw_integers for checking.
                stage = int(ints[0]) if ints else ion_ordinal_within_element[current_element.z]
                current_ion = IonInfo(
                    global_index=global_ion_index,
                    z=current_element.z,
                    symbol=current_element.symbol,
                    element_name=current_element.name,
                    ion_stage=stage,
                    label=ion_label(current_element.symbol, stage),
                    charge_label=charge_label(current_element.symbol, stage),
                    record=recno,
                    n_levels=0,
                    raw_reals=self.real_slice(h),
                    raw_integers=ints,
                    raw_chars=chars,
                )
                ions.append(current_ion)
                levels_for_ion[global_ion_index] = 0

            level_idx: Optional[int] = None
            if h.rate_type == 13 and current_ion is not None:
                level_idx = self.level_index_from_ints(ints)
                levels_for_ion[current_ion.global_index] = max(
                    levels_for_ion.get(current_ion.global_index, 0),
                    int(level_idx or 0),
                )
                current_ion.n_levels = levels_for_ion[current_ion.global_index]
            elif h.rate_type in (1, 7) and current_ion is not None:
                # PI/RRC records also carry a level index in the same position in setptrs.
                level_idx = self.level_index_from_ints(ints)

            if h.rate_type == 11:
                parent_kind = "element"
            elif h.rate_type == 12:
                parent_kind = "ion"
            elif h.rate_type == 13:
                parent_kind = "level"
            elif h.rate_type in (1, 7):
                parent_kind = "continuum_level"
            elif h.rate_type in (4, 9, 14):
                parent_kind = "line"
            else:
                parent_kind = "ion_process" if current_ion is not None else "global"

            records.append(IndexedRecord(
                recno=recno,
                data_type=h.data_type,
                rate_type=h.rate_type,
                continuation=h.continuation,
                nreal=h.nreal,
                nint=h.nint,
                nchar=h.nchar,
                real_ptr=h.real_ptr,
                int_ptr=h.int_ptr,
                char_ptr=h.char_ptr,
                element_z=current_element.z if current_element else None,
                element_symbol=current_element.symbol if current_element else "",
                element_name=current_element.name if current_element else "",
                element_record=current_element.record if current_element else None,
                ion_global_index=current_ion.global_index if current_ion else None,
                ion_stage=current_ion.ion_stage if current_ion else None,
                ion_label=current_ion.label if current_ion else "",
                charge_label=current_ion.charge_label if current_ion else "",
                ion_record=current_ion.record if current_ion else None,
                level_index=level_idx,
                parent_kind=parent_kind,
                data_type_label=DATA_TYPES.get(h.data_type, ""),
                rate_type_label=RATE_TYPES.get(h.rate_type, ""),
            ))

        self._index_records = records
        self._index_elements = elements
        self._index_ions = ions

        if use_cache:
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                if fmt == "npz":
                    _write_npz_index_cache(cache_file, self, records, elements, ions)
                else:
                    tmp_file = cache_file.with_suffix(cache_file.suffix + ".tmp")
                    payload = {
                        "metadata": _cache_metadata(self),
                        "records": records,
                        "elements": elements,
                        "ions": ions,
                    }
                    with tmp_file.open("wb") as handle:
                        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
                    os.replace(tmp_file, cache_file)
                self._last_index_cache_status = f"{fmt}_rebuilt" if rebuild_cache else f"{fmt}_written"
                self._last_index_cache_path = cache_file
            except Exception as exc:
                self._last_index_cache_status = f"{fmt}_write_failed:{exc.__class__.__name__}"

        return records, elements, ions

    @property
    def index_cache_status(self) -> str:
        """Status string from the most recent ``build_index`` call."""
        return self._last_index_cache_status

    @property
    def index_cache_path(self) -> Optional[Path]:
        """Cache path used by the most recent cached ``build_index`` call."""
        return self._last_index_cache_path

    def select_records(self, indexed: List[IndexedRecord], element: Optional[str], ion_stage: Optional[int],
                       data_type: Optional[int], rate_type: Optional[int], limit: Optional[int]) -> List[IndexedRecord]:
        z_filter = None
        if element:
            e = element.strip()
            z_filter = int(e) if e.isdigit() else SYMBOL_TO_Z.get(e.upper())
            if z_filter is None:
                raise ValueError(f"Unknown element: {element}")
        out: List[IndexedRecord] = []
        for r in indexed:
            if z_filter is not None and r.element_z != z_filter:
                continue
            if ion_stage is not None and r.ion_stage != ion_stage:
                continue
            if data_type is not None and r.data_type != data_type:
                continue
            if rate_type is not None and r.rate_type != rate_type:
                continue
            out.append(r)
            if limit is not None and len(out) >= limit:
                break
        return out

    def dump_record(self, r: IndexedRecord, include_reals: bool = True, max_values: int = 20) -> None:
        h = self.header(r.recno)
        ints = self.int_slice(h)
        chars = self.char_slice(h)
        reals = self.real_slice(h) if include_reals else []

        def preview(x):
            if len(x) <= max_values:
                return x
            return x[:max_values] + [f"... ({len(x)-max_values} more)"]

        print(f"\nRecord {r.recno}  {r.ion_label or r.element_symbol}  kind={r.parent_kind}")
        print("-" * 72)
        print(f"data_type={r.data_type}  {r.data_type_label}")
        print(f"rate_type={r.rate_type}  {r.rate_type_label}")
        print(f"element={r.element_symbol} Z={r.element_z} ion={r.ion_label} charge={r.charge_label}")
        print(f"nreal={r.nreal} nint={r.nint} nchar={r.nchar}")
        if include_reals:
            print(f"reals:    {preview(reals)}")
        print(f"integers: {preview(ints)}")
        print(f"chars:    {chars!r}")


def write_dataclass_csv(path: str | Path, rows: Iterable[object]) -> None:
    rows = list(rows)
    if not rows:
        Path(path).write_text("")
        return
    fieldnames = list(asdict(rows[0]).keys())
    with Path(path).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def summarize(records: List[IndexedRecord], elements: List[ElementInfo], ions: List[IonInfo], db: ATDB) -> Dict[str, object]:
    by_rate: Dict[int, int] = {}
    by_data: Dict[int, int] = {}
    for r in records:
        by_rate[r.rate_type] = by_rate.get(r.rate_type, 0) + 1
        by_data[r.data_type] = by_data.get(r.data_type, 0) + 1
    max_levels = max((ion.n_levels for ion in ions), default=0)
    return {
        "filename": str(db.filename),
        "date": db.date,
        "creator": db.creator,
        "n_records": db.n_records,
        "n_reals": db.n_reals,
        "n_integers": db.n_integers,
        "n_chars": db.n_chars,
        "n_elements": len(elements),
        "n_ions": len(ions),
        "max_levels_per_ion_from_level_records": max_levels,
        "elements": [asdict(e) for e in elements],
        "counts_by_rate_type": {str(k): {"count": v, "label": RATE_TYPES.get(k, "")} for k, v in sorted(by_rate.items())},
        "counts_by_data_type": {str(k): {"count": v, "label": DATA_TYPES.get(k, "")} for k, v in sorted(by_data.items())},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build hierarchy index for XSTAR atdb.fits")
    ap.add_argument("fitsfile")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--summary-json")
    ap.add_argument("--index-csv")
    ap.add_argument("--elements-csv")
    ap.add_argument("--ions-csv")
    ap.add_argument("--element", help="Element symbol or atomic number, e.g. O or 8")
    ap.add_argument("--ion-stage", type=int, help="Ion stage, e.g. 8 for O VIII")
    ap.add_argument("--data-type", type=int)
    ap.add_argument("--rate-type", type=int)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--no-reals", action="store_true", help="Do not load/dump REALS")
    ap.add_argument("--max-values", type=int, default=20)
    ap.add_argument("--index-cache", nargs="?", const=True, default=False,
                    help="Use an on-disk hierarchy index cache. Optionally provide a cache filename; default is atdb.fits.xstar_atomic_index.npz")
    ap.add_argument("--rebuild-index-cache", action="store_true", help="Rebuild the hierarchy index cache")
    ap.add_argument("--index-cache-format", choices=["npz", "pickle"], default="npz",
                    help="On-disk index cache format; npz is compact and preferred, pickle is legacy")
    args = ap.parse_args()

    with ATDB(args.fitsfile, load_reals=False) as db:
        cache_setting = args.index_cache
        use_cache = bool(cache_setting) or bool(args.rebuild_index_cache)
        cache_path = None if cache_setting is True or cache_setting is False else cache_setting
        records, elements, ions = db.build_index(
            use_cache=use_cache,
            cache_path=cache_path,
            rebuild_cache=args.rebuild_index_cache,
            cache_format=getattr(args, "index_cache_format", "npz"),
        )

        if args.summary or args.summary_json:
            s = summarize(records, elements, ions, db)
            s["index_cache_status"] = db.index_cache_status
            s["index_cache_path"] = str(db.index_cache_path) if db.index_cache_path is not None else None
            if args.summary:
                print(json.dumps(s, indent=2))
            if args.summary_json:
                Path(args.summary_json).write_text(json.dumps(s, indent=2))
                print(f"Wrote {args.summary_json}")

        if args.index_csv:
            write_dataclass_csv(args.index_csv, records)
            print(f"Wrote {args.index_csv}")
        if args.elements_csv:
            write_dataclass_csv(args.elements_csv, elements)
            print(f"Wrote {args.elements_csv}")
        if args.ions_csv:
            write_dataclass_csv(args.ions_csv, ions)
            print(f"Wrote {args.ions_csv}")

        if args.dump or any(x is not None for x in [args.element, args.ion_stage, args.data_type, args.rate_type]):
            selected = db.select_records(records, args.element, args.ion_stage, args.data_type, args.rate_type, args.limit)
            print(f"Selected {len(selected)} records")
            if args.dump:
                for r in selected:
                    db.dump_record(r, include_reals=not args.no_reals, max_values=args.max_values)
            else:
                for r in selected:
                    print(f"{r.recno:8d} {r.element_symbol:>2} {r.ion_label:>8} "
                          f"dt={r.data_type:3d} rt={r.rate_type:3d} kind={r.parent_kind} "
                          f"n=({r.nreal},{r.nint},{r.nchar})")

        if not any([args.summary, args.summary_json, args.index_csv, args.elements_csv,
                    args.ions_csv, args.dump, args.element, args.ion_stage,
                    args.data_type, args.rate_type]):
            print(json.dumps(summarize(records, elements, ions, db), indent=2))


if __name__ == "__main__":
    main()
