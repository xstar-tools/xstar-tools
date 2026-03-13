"""Readers for standard XSTAR output FITS files.

This module focuses on lightweight conversion of XSTAR model-output files into
plain Python rows and CSV tables for comparison with :mod:`xstar_atomic` atomic
rates and emissivity products.

Currently implemented
---------------------

* ``xout_lines1.fits``: reads the ``XSTAR_LINES`` extension with columns such as
  ``ion``, ``lower_level``, ``upper_level``, ``wavelength``, ``emit_inward``,
  ``emit_outward``, ``depth_inward``, and ``depth_outward``.

The line-emission columns in XSTAR outputs are model-dependent radiative-transfer
quantities.  They should not be compared directly to local atomic emissivity
coefficients without applying the same ion fractions, geometry, density, and
radiative-transfer assumptions.  For first validation, compare line presence,
ion labels, level labels, and wavelengths.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
from astropy.io import fits


def _decode_value(value: Any) -> Any:
    """Return a JSON/CSV-friendly scalar from a FITS table value."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, np.bytes_):
        return bytes(value).decode("utf-8", errors="replace").strip()
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, str):
        return value.strip()
    return value


def _normalize_column_name(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def table_hdu_to_rows(hdu: fits.hdu.base.ExtensionHDU) -> List[Dict[str, Any]]:
    """Convert a FITS table HDU to a list of dictionaries.

    Parameters
    ----------
    hdu:
        FITS table HDU, usually ``XSTAR_LINES`` or ``PARAMETERS``.

    Returns
    -------
    list of dict
        Rows with normalized lower-case column names and decoded string values.
    """
    if getattr(hdu, "data", None) is None or getattr(hdu, "columns", None) is None:
        return []
    names = list(hdu.columns.names)
    out: List[Dict[str, Any]] = []
    for rec in hdu.data:
        row: Dict[str, Any] = {}
        for name in names:
            row[_normalize_column_name(name)] = _decode_value(rec[name])
        out.append(row)
    return out


def read_xout_lines(path: str | Path, hdu_name: str = "XSTAR_LINES") -> List[Dict[str, Any]]:
    """Read an XSTAR ``xout_lines*.fits`` line table.

    Parameters
    ----------
    path:
        Path to an XSTAR line-output FITS file, commonly ``xout_lines1.fits``.
    hdu_name:
        Name of the line-table HDU.  Defaults to ``"XSTAR_LINES"``.

    Returns
    -------
    list of dict
        Line rows with columns such as ``ion``, ``lower_level``,
        ``upper_level``, ``wavelength``, ``emit_inward`` and ``emit_outward``.
    """
    path = Path(path)
    with fits.open(path) as hdul:
        if hdu_name in hdul:
            hdu = hdul[hdu_name]
        else:
            # Fall back to the first table HDU with a wavelength-like column.
            hdu = None
            for candidate in hdul[1:]:
                cols = [c.lower() for c in getattr(getattr(candidate, "columns", None), "names", []) or []]
                if "wavelength" in cols:
                    hdu = candidate
                    break
            if hdu is None:
                raise ValueError(f"No {hdu_name!r} or wavelength table found in {path}")
        return table_hdu_to_rows(hdu)


def read_xout_parameters(path: str | Path, hdu_name: str = "PARAMETERS") -> List[Dict[str, Any]]:
    """Read the ``PARAMETERS`` table from an XSTAR output FITS file if present."""
    path = Path(path)
    with fits.open(path) as hdul:
        if hdu_name not in hdul:
            return []
        return table_hdu_to_rows(hdul[hdu_name])


def filter_rows(
    rows: Sequence[Dict[str, Any]],
    ion: Optional[str] = None,
    wavelength_min: Optional[float] = None,
    wavelength_max: Optional[float] = None,
    min_emit_outward: Optional[float] = None,
    min_emit_inward: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Filter XSTAR line rows by ion, wavelength, and emission columns."""
    out: List[Dict[str, Any]] = []
    ion_norm = ion.strip().lower().replace("_", " ") if ion else None
    for row in rows:
        if ion_norm:
            row_ion = str(row.get("ion", "")).strip().lower().replace("_", " ")
            if row_ion != ion_norm:
                continue
        wave = row.get("wavelength")
        try:
            wave_f = float(wave)
        except Exception:
            continue
        if wavelength_min is not None and wave_f < wavelength_min:
            continue
        if wavelength_max is not None and wave_f > wavelength_max:
            continue
        if min_emit_outward is not None:
            try:
                if float(row.get("emit_outward", 0.0)) < min_emit_outward:
                    continue
            except Exception:
                continue
        if min_emit_inward is not None:
            try:
                if float(row.get("emit_inward", 0.0)) < min_emit_inward:
                    continue
            except Exception:
                continue
        out.append(dict(row))
    return out


def write_csv(rows: Sequence[Dict[str, Any]] | str | Path, path: str | Path | Sequence[Dict[str, Any]]) -> None:
    """Write a list of dictionaries to CSV.

    Parameters
    ----------
    rows, path:
        Preferred order is ``write_csv(rows, path)``.  For compatibility with
        early test/example code, ``write_csv(path, rows)`` is also accepted.
    """
    if isinstance(rows, (str, Path)) and not isinstance(path, (str, Path)):
        rows, path = path, rows
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fields: List[str] = []
        seen = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    fields.append(key)
    else:
        fields = ["index", "ion", "lower_level", "upper_level", "wavelength", "emit_inward", "emit_outward", "depth_inward", "depth_outward"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize_lines(rows: Sequence[Dict[str, Any]], fitsfile: str | Path) -> Dict[str, Any]:
    """Return a compact summary for XSTAR line-output rows."""
    counts_by_ion: Dict[str, int] = {}
    nonzero_out = 0
    nonzero_in = 0
    min_wave = None
    max_wave = None
    for row in rows:
        ion = str(row.get("ion", "")).strip()
        counts_by_ion[ion] = counts_by_ion.get(ion, 0) + 1
        try:
            w = float(row.get("wavelength"))
            min_wave = w if min_wave is None else min(min_wave, w)
            max_wave = w if max_wave is None else max(max_wave, w)
        except Exception:
            pass
        try:
            if float(row.get("emit_outward", 0.0)) != 0.0:
                nonzero_out += 1
        except Exception:
            pass
        try:
            if float(row.get("emit_inward", 0.0)) != 0.0:
                nonzero_in += 1
        except Exception:
            pass
    return {
        "fitsfile": str(fitsfile),
        "n_lines": len(rows),
        "n_ions": len([k for k, v in counts_by_ion.items() if k]),
        "counts_by_ion": dict(sorted(counts_by_ion.items(), key=lambda kv: (-kv[1], kv[0]))),
        "wavelength_min_A": min_wave,
        "wavelength_max_A": max_wave,
        "n_nonzero_emit_outward": nonzero_out,
        "n_nonzero_emit_inward": nonzero_in,
    }


def load_xstar_lines(
    fitsfile: str | Path,
    ion: Optional[str] = None,
    wavelength_min: Optional[float] = None,
    wavelength_max: Optional[float] = None,
    min_emit_outward: Optional[float] = None,
    min_emit_inward: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Read an XSTAR line-output FITS file and optionally filter rows.

    This is a stable convenience alias for the common validation workflow.
    It reads the ``XSTAR_LINES`` table from an ``xout_lines*.fits`` file and
    returns rows filtered by ion, wavelength range, and emission thresholds.
    """
    rows = read_xout_lines(fitsfile)
    return filter_rows(
        rows,
        ion=ion,
        wavelength_min=wavelength_min,
        wavelength_max=wavelength_max,
        min_emit_outward=min_emit_outward,
        min_emit_inward=min_emit_inward,
    )


def convert_xout_lines(
    fitsfile: str | Path,
    out_csv: Optional[str | Path] = None,
    ion: Optional[str] = None,
    wavelength_min: Optional[float] = None,
    wavelength_max: Optional[float] = None,
    min_emit_outward: Optional[float] = None,
    min_emit_inward: Optional[float] = None,
) -> Dict[str, Any]:
    """Read, optionally filter, summarize, and optionally export XSTAR lines."""
    all_rows = read_xout_lines(fitsfile)
    rows = filter_rows(all_rows, ion=ion, wavelength_min=wavelength_min, wavelength_max=wavelength_max,
                       min_emit_outward=min_emit_outward, min_emit_inward=min_emit_inward)
    if out_csv:
        write_csv(rows, out_csv)
    return {"summary": summarize_lines(rows, fitsfile), "rows": rows}


def main(argv: Optional[Sequence[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Convert XSTAR xout_lines*.fits outputs to CSV/JSON for xstar-atomic validation.")
    p.add_argument("fitsfile", help="XSTAR line output FITS file, e.g. xout_lines1.fits")
    p.add_argument("--out-csv", help="Write selected XSTAR line rows to CSV")
    p.add_argument("--summary-json", help="Write compact summary JSON")
    p.add_argument("--ion", help="Optional ion filter matching the XSTAR ion column, e.g. 'O VIII'")
    p.add_argument("--wavelength-min", type=float, help="Minimum wavelength in Angstrom")
    p.add_argument("--wavelength-max", type=float, help="Maximum wavelength in Angstrom")
    p.add_argument("--min-emit-outward", type=float, help="Minimum emit_outward value")
    p.add_argument("--min-emit-inward", type=float, help="Minimum emit_inward value")
    p.add_argument("--print-summary", action="store_true", help="Print summary JSON to stdout")
    p.add_argument("--print-rows", action="store_true", help="Print selected rows as JSON to stdout")
    p.add_argument("--limit", type=int, default=None, help="Limit printed rows")
    args = p.parse_args(argv)

    result = convert_xout_lines(
        args.fitsfile,
        out_csv=args.out_csv,
        ion=args.ion,
        wavelength_min=args.wavelength_min,
        wavelength_max=args.wavelength_max,
        min_emit_outward=args.min_emit_outward,
        min_emit_inward=args.min_emit_inward,
    )
    if args.summary_json:
        Path(args.summary_json).write_text(json.dumps(result["summary"], indent=2), encoding="utf-8")
    if args.print_summary or not args.print_rows:
        print(json.dumps(result["summary"], indent=2))
    if args.print_rows:
        rows = result["rows"] if args.limit is None else result["rows"][: args.limit]
        print(json.dumps({"rows": rows, "n_rows": len(result["rows"])}, indent=2))


if __name__ == "__main__":
    main()
