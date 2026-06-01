"""Physical XSTAR/Python detail and final-output parity comparisons.

This module deliberately compares independently generated output directories;
it never uses an XSTAR output as a production input.  It is therefore suitable
for the final physical all-ATDB acceptance gate once a standard benchmark has
been run through both the original XSTAR executable and the Python source port.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from astropy.io import fits


FINAL_FITS_PRODUCTS = (
    "xout_abund1.fits",
    "xout_spect1.fits",
    "xout_lines1.fits",
    "xout_cont1.fits",
    "xout_rrc1.fits",
)
DETAIL_PATTERNS = (
    "xo*_detail.fits",
    "xo*_detal2.fits",
    "xo*_detal3.fits",
    "xo*_detal4.fits",
)
LEGACY_TEXT_PRODUCTS = ("xout_step.log",)


@dataclass(frozen=True)
class ColumnParity:
    hdu: str
    column: str
    kind: str
    n_values: int
    ready: bool
    max_abs_diff: float = 0.0
    max_rel_diff: float = 0.0
    mismatch_count: int = 0


@dataclass(frozen=True)
class FileParity:
    filename: str
    kind: str
    present_in_xstar: bool
    present_in_python: bool
    schema_ready: bool
    values_ready: bool
    ready: bool
    details: tuple[ColumnParity, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PhysicalOutputParityResult:
    xstar_run_dir: str
    python_run_dir: str
    required_files: tuple[str, ...]
    files: tuple[FileParity, ...]
    inputs_available: bool
    parity_run: bool
    all_files_ready: bool
    source_file: str = "xstar/src/xstar/xstar.f90"
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "xstar_run_dir": self.xstar_run_dir,
            "python_run_dir": self.python_run_dir,
            "required_files": list(self.required_files),
            "inputs_available": self.inputs_available,
            "parity_run": self.parity_run,
            "all_files_ready": self.all_files_ready,
            "source_file": self.source_file,
            "provenance": dict(self.provenance),
            "files": [
                {
                    **{k: v for k, v in asdict(item).items() if k != "details"},
                    "details": [asdict(detail) for detail in item.details],
                }
                for item in self.files
            ],
        }


def _relative_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    scale = np.maximum(np.maximum(np.abs(a), np.abs(b)), 1.0e-300)
    return np.abs(a - b) / scale


def _compare_numeric(
    hdu_name: str,
    column_name: str,
    xstar_values: Any,
    python_values: Any,
    *,
    rtol: float,
    atol: float,
) -> ColumnParity:
    a = np.asarray(xstar_values, dtype=float)
    b = np.asarray(python_values, dtype=float)
    if a.shape != b.shape:
        return ColumnParity(
            hdu_name, column_name, "numeric", int(max(a.size, b.size)), False,
            mismatch_count=int(max(a.size, b.size)),
        )
    finite_equal = np.isclose(a, b, rtol=rtol, atol=atol, equal_nan=True)
    diff = np.abs(a - b)
    rel = _relative_difference(a, b)
    finite_diff = diff[np.isfinite(diff)]
    finite_rel = rel[np.isfinite(rel)]
    return ColumnParity(
        hdu=hdu_name,
        column=column_name,
        kind="numeric",
        n_values=int(a.size),
        ready=bool(np.all(finite_equal)),
        max_abs_diff=float(np.max(finite_diff)) if finite_diff.size else 0.0,
        max_rel_diff=float(np.max(finite_rel)) if finite_rel.size else 0.0,
        mismatch_count=int(np.count_nonzero(~finite_equal)),
    )


def _normalized_strings(values: Any) -> np.ndarray:
    arr = np.asarray(values)
    if arr.dtype.kind == "S":
        arr = np.char.decode(arr, "ascii", errors="replace")
    return np.char.rstrip(arr.astype(str))


def _compare_strings(
    hdu_name: str,
    column_name: str,
    xstar_values: Any,
    python_values: Any,
) -> ColumnParity:
    a = _normalized_strings(xstar_values)
    b = _normalized_strings(python_values)
    if a.shape != b.shape:
        return ColumnParity(
            hdu_name, column_name, "string", int(max(a.size, b.size)), False,
            mismatch_count=int(max(a.size, b.size)),
        )
    equal = a == b
    return ColumnParity(
        hdu=hdu_name,
        column=column_name,
        kind="string",
        n_values=int(a.size),
        ready=bool(np.all(equal)),
        mismatch_count=int(np.count_nonzero(~equal)),
    )




_HEADER_EXACT_EXCLUDE = {
    "", "SIMPLE", "XTENSION", "BITPIX", "EXTEND", "PCOUNT", "GCOUNT",
    "TFIELDS", "EXTNAME", "CHECKSUM", "DATASUM", "DATE", "CREATOR",
    "ORIGIN", "COMMENT", "HISTORY",
}
_HEADER_PREFIX_EXCLUDE = (
    "NAXIS", "TTYPE", "TFORM", "TUNIT", "TDISP", "TSCAL", "TZERO",
    "TNULL", "TDIM", "TBCOL",
)


def _physical_header_values(header: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in header.items():
        name = str(key).strip().upper()
        if name in _HEADER_EXACT_EXCLUDE or any(name.startswith(prefix) for prefix in _HEADER_PREFIX_EXCLUDE):
            continue
        if isinstance(value, (str, int, float, bool, np.integer, np.floating, np.bool_)):
            values[name] = value
    return values


def _compare_headers(
    hdu_name: str,
    xheader: Any,
    pheader: Any,
    *,
    rtol: float,
    atol: float,
) -> tuple[bool, list[ColumnParity], list[str]]:
    xv = _physical_header_values(xheader)
    pv = _physical_header_values(pheader)
    ready = True
    details: list[ColumnParity] = []
    notes: list[str] = []
    for key in sorted(set(xv) | set(pv)):
        if key not in xv or key not in pv:
            ready = False
            notes.append(f"{hdu_name} header keyword {key} missing on one side")
            continue
        a, b = xv[key], pv[key]
        if isinstance(a, (int, float, bool, np.integer, np.floating, np.bool_)) and isinstance(
            b, (int, float, bool, np.integer, np.floating, np.bool_)
        ):
            detail = _compare_numeric(
                hdu_name, f"HEADER:{key}", np.asarray([a]), np.asarray([b]),
                rtol=rtol, atol=atol,
            )
        else:
            detail = _compare_strings(
                hdu_name, f"HEADER:{key}", np.asarray([str(a)]), np.asarray([str(b)])
            )
        details.append(detail)
        ready = ready and detail.ready
    return ready, details, notes


def compare_fits_product(
    xstar_path: str | Path,
    python_path: str | Path,
    *,
    rtol: float = 5.0e-5,
    atol: float = 1.0e-30,
) -> FileParity:
    """Compare stable headers, HDU/column schemas, and all persisted values."""
    xp = Path(xstar_path)
    pp = Path(python_path)
    present_x = xp.is_file()
    present_p = pp.is_file()
    if not (present_x and present_p):
        return FileParity(
            filename=xp.name,
            kind="fits",
            present_in_xstar=present_x,
            present_in_python=present_p,
            schema_ready=False,
            values_ready=False,
            ready=False,
            notes=("required file missing",),
        )

    details: list[ColumnParity] = []
    notes: list[str] = []
    schema_ready = True
    with fits.open(xp, memmap=False) as xh, fits.open(pp, memmap=False) as ph:
        if len(xh) != len(ph):
            schema_ready = False
            notes.append(f"HDU count differs: {len(xh)} != {len(ph)}")
        for index in range(min(len(xh), len(ph))):
            xa = xh[index]
            pa = ph[index]
            xname = str(xa.name)
            pname = str(pa.name)
            if xname != pname:
                schema_ready = False
                notes.append(f"HDU {index + 1} name differs: {xname!r} != {pname!r}")
            header_ready, header_details, header_notes = _compare_headers(
                xname, xa.header, pa.header, rtol=rtol, atol=atol
            )
            schema_ready = schema_ready and header_ready
            details.extend(header_details)
            notes.extend(header_notes)
            if not hasattr(xa, "columns") and not hasattr(pa, "columns"):
                xdata = np.asarray([]) if xa.data is None else np.asarray(xa.data)
                pdata = np.asarray([]) if pa.data is None else np.asarray(pa.data)
                if xdata.size or pdata.size:
                    details.append(
                        _compare_numeric(xname, "IMAGE_DATA", xdata, pdata, rtol=rtol, atol=atol)
                    )
                continue
            xcols = tuple(getattr(xa.columns, "names", ()) or ())
            pcols = tuple(getattr(pa.columns, "names", ()) or ())
            if xcols != pcols:
                schema_ready = False
                notes.append(f"{xname} columns differ")
            xrows = 0 if xa.data is None else len(xa.data)
            prows = 0 if pa.data is None else len(pa.data)
            if xrows != prows:
                schema_ready = False
                notes.append(f"{xname} row count differs: {xrows} != {prows}")
            for col in (name for name in xcols if name in pcols):
                xv = xa.data[col] if xa.data is not None else np.asarray([])
                pv = pa.data[col] if pa.data is not None else np.asarray([])
                kind = np.asarray(xv).dtype.kind
                if kind in "iufcb":
                    details.append(
                        _compare_numeric(xname, col, xv, pv, rtol=rtol, atol=atol)
                    )
                else:
                    details.append(_compare_strings(xname, col, xv, pv))
    values_ready = bool(details) and all(item.ready for item in details)
    # Empty primary-only products are schema-comparable even with no columns.
    if not details and schema_ready:
        values_ready = True
    return FileParity(
        filename=xp.name,
        kind="fits",
        present_in_xstar=True,
        present_in_python=True,
        schema_ready=schema_ready,
        values_ready=values_ready,
        ready=bool(schema_ready and values_ready),
        details=tuple(details),
        notes=tuple(notes),
    )


_ZONE_LINE = re.compile(
    r"^\s*" + r"\s+".join([r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?)"] * 11)
    # Current XSTAR passes only ``ntotit`` to a historical ``2i3`` FORMAT.
    # Accept an optional second integer from older/debug writers, but exclude it
    # from the structured comparison so both source variants normalize to the
    # same 12-value row.
    + r"\s+([+-]?\d+)(?:\s+[+-]?\d+)?\s*$"
)
_FINAL_ASSIGNMENT = re.compile(
    r"=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?)"
)


def _step_log_vectors(text: str) -> tuple[list[np.ndarray], list[np.ndarray]]:
    zones: list[np.ndarray] = []
    finals: list[np.ndarray] = []
    for raw in text.splitlines():
        match = _ZONE_LINE.match(raw)
        if match:
            zones.append(np.asarray([float(v.replace("D", "E").replace("d", "e")) for v in match.groups()], dtype=float))
            continue
        stripped = raw.lstrip()
        if stripped.startswith(("r=", "httot=", "log(Xi)=")):
            vals = [
                float(v.replace("D", "E").replace("d", "e"))
                for v in _FINAL_ASSIGNMENT.findall(raw)
            ]
            finals.append(np.asarray(vals, dtype=float))
    return zones, finals


def compare_step_log(
    xstar_path: str | Path,
    python_path: str | Path,
    *,
    rtol: float = 5.0e-3,
    atol: float = 5.0e-3,
) -> FileParity:
    """Compare source-formatted zone rows and final scalar summaries."""
    xp = Path(xstar_path)
    pp = Path(python_path)
    present_x = xp.is_file()
    present_p = pp.is_file()
    if not (present_x and present_p):
        return FileParity(
            filename=xp.name,
            kind="text",
            present_in_xstar=present_x,
            present_in_python=present_p,
            schema_ready=False,
            values_ready=False,
            ready=False,
            notes=("required file missing",),
        )
    xzones, xfinal = _step_log_vectors(xp.read_text(errors="replace"))
    pzones, pfinal = _step_log_vectors(pp.read_text(errors="replace"))
    schema = len(xzones) == len(pzones) and len(xfinal) == len(pfinal)
    details: list[ColumnParity] = []
    for index, (a, b) in enumerate(zip(xzones, pzones), start=1):
        details.append(_compare_numeric("xout_step.log", f"zone_{index}", a, b, rtol=rtol, atol=atol))
    for index, (a, b) in enumerate(zip(xfinal, pfinal), start=1):
        details.append(_compare_numeric("xout_step.log", f"final_{index}", a, b, rtol=rtol, atol=atol))
    values = bool(details) and all(item.ready for item in details)
    return FileParity(
        filename=xp.name,
        kind="text",
        present_in_xstar=True,
        present_in_python=True,
        schema_ready=schema,
        values_ready=values,
        ready=bool(schema and values),
        details=tuple(details),
        notes=(() if schema else ("zone/final row counts differ",)),
    )


def _discover_required_files(xstar_dir: Path, python_dir: Path) -> tuple[str, ...]:
    names = set(FINAL_FITS_PRODUCTS) | set(LEGACY_TEXT_PRODUCTS)
    for pattern in DETAIL_PATTERNS:
        names.update(path.name for path in xstar_dir.glob(pattern))
        names.update(path.name for path in python_dir.glob(pattern))
    return tuple(sorted(names))


def compare_physical_output_directories(
    xstar_run_dir: str | Path,
    python_run_dir: str | Path,
    *,
    rtol: float = 5.0e-5,
    atol: float = 1.0e-30,
    step_rtol: float = 5.0e-3,
    step_atol: float = 5.0e-3,
    required_files: Sequence[str] | None = None,
) -> PhysicalOutputParityResult:
    """Compare standard all-ATDB detail/final products from two runs."""
    xd = Path(xstar_run_dir)
    pd = Path(python_run_dir)
    required = (
        tuple(dict.fromkeys(str(name) for name in required_files))
        if required_files is not None
        else _discover_required_files(xd, pd)
    )
    files: list[FileParity] = []
    for name in required:
        if name.endswith(".fits"):
            files.append(compare_fits_product(xd / name, pd / name, rtol=rtol, atol=atol))
        else:
            files.append(compare_step_log(xd / name, pd / name, rtol=step_rtol, atol=step_atol))
    inputs = xd.is_dir() and pd.is_dir() and all((xd / name).is_file() and (pd / name).is_file() for name in required)
    parity_run = bool(inputs and files)
    all_ready = bool(parity_run and all(item.ready for item in files))
    return PhysicalOutputParityResult(
        xstar_run_dir=str(xd),
        python_run_dir=str(pd),
        required_files=required,
        files=tuple(files),
        inputs_available=inputs,
        parity_run=parity_run,
        all_files_ready=all_ready,
        provenance={
            "role": "diagnostic oracle only",
            "production_inputs_from_xstar": False,
            "fits_rtol": float(rtol),
            "fits_atol": float(atol),
            "step_rtol": float(step_rtol),
            "step_atol": float(step_atol),
            "required_files_explicit": required_files is not None,
        },
    )


def run_physical_parity_harness_self_test(
    generated_dir: str | Path,
    *,
    rtol: float = 5.0e-5,
    atol: float = 1.0e-30,
) -> dict[str, bool]:
    """Validate the comparator without claiming a physical XSTAR run."""
    root = Path(generated_dir)
    result = compare_physical_output_directories(root, root, rtol=rtol, atol=atol)
    return {
        "physical_output_parity_fits_schema_comparator_ready": bool(result.parity_run),
        "physical_output_parity_numeric_comparator_ready": bool(result.all_files_ready),
        "physical_output_parity_step_log_comparator_ready": any(item.filename == "xout_step.log" and item.ready for item in result.files),
        "physical_standard_benchmark_parity_harness_ready": bool(result.all_files_ready),
    }


__all__ = [
    "FINAL_FITS_PRODUCTS", "DETAIL_PATTERNS", "LEGACY_TEXT_PRODUCTS",
    "ColumnParity", "FileParity", "PhysicalOutputParityResult",
    "compare_fits_product", "compare_step_log",
    "compare_physical_output_directories", "run_physical_parity_harness_self_test",
]
