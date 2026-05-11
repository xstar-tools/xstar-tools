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

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    np = None  # type: ignore

try:
    from astropy.io import fits  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    fits = None  # type: ignore


def _decode_value(value: Any) -> Any:
    """Return a JSON/CSV-friendly scalar from a FITS table value."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if np is not None:
        if isinstance(value, np.bytes_):
            return bytes(value).decode("utf-8", errors="replace").strip()
        if isinstance(value, np.generic):
            value = value.item()
    if isinstance(value, str):
        return value.strip()
    return value


def _normalize_column_name(name: str) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")




def _parse_fits_value(raw: str) -> Any:
    """Parse a simple FITS header value from an 80-character card."""
    text = raw.strip()
    if not text:
        return ""
    if text.startswith("'"):
        # FITS strings are quoted with doubled quotes for literal quotes.  The
        # first closing quote terminates the value; comments after it are
        # ignored by the caller before this function is invoked.
        out = []
        i = 1
        while i < len(text):
            ch = text[i]
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    out.append("'")
                    i += 2
                    continue
                break
            out.append(ch)
            i += 1
        return "".join(out).strip()
    low = text.lower()
    if text in ("T", "F"):
        return text == "T"
    try:
        if any(c in low for c in (".", "e", "d")):
            return float(text.replace("D", "E").replace("d", "e"))
        return int(text)
    except Exception:
        return text


def _parse_header_cards(header_bytes: bytes) -> Dict[str, Any]:
    header: Dict[str, Any] = {}
    cards = header_bytes.decode("ascii", errors="replace")
    for i in range(0, len(cards), 80):
        card = cards[i:i + 80]
        key = card[:8].strip()
        if not key:
            continue
        if key == "END":
            break
        if len(card) >= 10 and card[8:10] == "= ":
            value_part = card[10:80]
            # Remove comments outside quoted strings.
            in_quote = False
            cut = len(value_part)
            j = 0
            while j < len(value_part):
                ch = value_part[j]
                if ch == "'":
                    if in_quote and j + 1 < len(value_part) and value_part[j + 1] == "'":
                        j += 2
                        continue
                    in_quote = not in_quote
                elif ch == "/" and not in_quote:
                    cut = j
                    break
                j += 1
            header[key] = _parse_fits_value(value_part[:cut])
    return header


def _raw_fits_hdus(path: str | Path) -> List[Dict[str, Any]]:
    """Return raw FITS HDU metadata and data blocks without astropy.

    This intentionally implements only the small subset required for XSTAR
    ASCII-table products such as ``xout_abund1.fits``.  It is not a general FITS
    replacement, but it lets diagnostics run on minimal systems where astropy is
    unavailable.
    """
    path = Path(path)
    hdus: List[Dict[str, Any]] = []
    with path.open("rb") as handle:
        idx = 0
        while True:
            first = handle.read(2880)
            if not first:
                break
            if len(first) < 2880:
                break
            header_bytes = bytearray(first)
            while b"END" not in header_bytes[-2880:]:
                block = handle.read(2880)
                if not block:
                    break
                header_bytes.extend(block)
            header = _parse_header_cards(bytes(header_bytes))
            data_offset = handle.tell()
            naxis = int(header.get("NAXIS", 0) or 0)
            pcount = int(header.get("PCOUNT", 0) or 0)
            gcount = int(header.get("GCOUNT", 1) or 1)
            if str(header.get("XTENSION", "")).strip().upper() in {"TABLE", "BINTABLE"}:
                rowlen = int(header.get("NAXIS1", 0) or 0)
                nrows = int(header.get("NAXIS2", 0) or 0)
                data_len = rowlen * nrows + pcount
            elif naxis > 0:
                bitpix = abs(int(header.get("BITPIX", 8) or 8))
                nvals = 1
                for ax in range(1, naxis + 1):
                    nvals *= int(header.get(f"NAXIS{ax}", 0) or 0)
                data_len = (bitpix // 8) * nvals * gcount + pcount
            else:
                data_len = 0
            pad = (2880 - (data_len % 2880)) % 2880
            data = handle.read(data_len)
            if pad:
                handle.seek(pad, 1)
            hdus.append({"index": idx, "header": header, "data_offset": data_offset, "data_size": data_len, "data": data})
            idx += 1
    return hdus


def _fits_form_width(form: str, next_start: int | None, start: int, rowlen: int) -> int:
    text = str(form or "").strip().upper()
    import re
    m = re.match(r"(\d*)([AIFED])\s*(\d+)?(?:\.\d+)?", text)
    if m:
        repeat = int(m.group(1) or "1")
        code = m.group(2)
        width = int(m.group(3) or "0")
        if code == "A" and width == 0:
            width = repeat
            repeat = 1
        if width > 0:
            return repeat * width
    if next_start is not None:
        return max(0, next_start - start)
    return max(0, rowlen - start + 1)


def _parse_ascii_table_hdu(hdu: Dict[str, Any]) -> List[Dict[str, Any]]:
    header = hdu["header"]
    if str(header.get("XTENSION", "")).strip().upper() != "TABLE":
        return []
    rowlen = int(header.get("NAXIS1", 0) or 0)
    nrows = int(header.get("NAXIS2", 0) or 0)
    nfields = int(header.get("TFIELDS", 0) or 0)
    cols: List[Dict[str, Any]] = []
    for idx in range(1, nfields + 1):
        name = str(header.get(f"TTYPE{idx}", f"col{idx}")).strip()
        start = int(header.get(f"TBCOL{idx}", 1) or 1)
        form = str(header.get(f"TFORM{idx}", "")).strip()
        cols.append({"name": _normalize_column_name(name), "start": start, "form": form})
    starts = [int(c["start"]) for c in cols]
    for i, col in enumerate(cols):
        next_start = starts[i + 1] if i + 1 < len(starts) else None
        col["width"] = _fits_form_width(str(col["form"]), next_start, int(col["start"]), rowlen)
    text = hdu["data"].decode("ascii", errors="replace")
    rows: List[Dict[str, Any]] = []
    for ridx in range(nrows):
        rec = text[ridx * rowlen:(ridx + 1) * rowlen]
        row: Dict[str, Any] = {}
        for col in cols:
            start0 = int(col["start"]) - 1
            end = start0 + int(col["width"])
            raw = rec[start0:end].strip()
            form = str(col["form"]).upper().strip()
            if not raw:
                value: Any = None
            elif "A" in form:
                value = raw
            elif "I" in form:
                try:
                    value = int(raw)
                except Exception:
                    value = raw
            else:
                try:
                    value = float(raw.replace("D", "E").replace("d", "e"))
                except Exception:
                    value = raw
            row[str(col["name"])] = value
        rows.append(row)
    return rows


def _read_fits_table_fallback(path: str | Path, hdu_name: str) -> List[Dict[str, Any]]:
    wanted = hdu_name.strip().lower()
    for hdu in _raw_fits_hdus(path):
        header = hdu["header"]
        name = str(header.get("EXTNAME", "")).strip().lower()
        if name == wanted:
            return _parse_ascii_table_hdu(hdu)
    return []

def table_hdu_to_rows(hdu: Any) -> List[Dict[str, Any]]:
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
    if fits is None:
        # A minimal fallback is available for XSTAR ASCII TABLE HDUs.
        rows = _read_fits_table_fallback(path, hdu_name)
        if rows:
            return rows
        raise ImportError("astropy is required to read this FITS table; the built-in fallback only supports XSTAR ASCII TABLE HDUs")
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


def read_xout_spectra(path: str | Path, hdu_name: str = "XSTAR_SPECTRA") -> List[Dict[str, Any]]:
    """Read an XSTAR continuum/spectrum table such as ``xout_cont1.fits``.

    The XSTAR writer ``writespectra3.f90`` stores an ASCII table named
    ``XSTAR_SPECTRA`` with columns normally called ``energy``, ``incident``,
    ``transmitted``, ``emit_inward`` and ``emit_outward``.  This lightweight
    reader returns normalized lower-case column names and works with the
    built-in ASCII-table fallback when ``astropy`` is unavailable.
    """
    path = Path(path)
    if fits is None:
        rows = _read_fits_table_fallback(path, hdu_name)
        if rows:
            return rows
        raise ImportError("astropy is required to read this FITS table; the built-in fallback only supports XSTAR ASCII TABLE HDUs")
    with fits.open(path) as hdul:
        if hdu_name in hdul:
            hdu = hdul[hdu_name]
        else:
            hdu = None
            for candidate in hdul[1:]:
                cols = [c.lower() for c in getattr(getattr(candidate, "columns", None), "names", []) or []]
                if "energy" in cols and ("incident" in cols or "transmitted" in cols):
                    hdu = candidate
                    break
            if hdu is None:
                raise ValueError(f"No {hdu_name!r} or continuum spectrum table found in {path}")
        return table_hdu_to_rows(hdu)


def write_xout_spectra_csv(rows: Sequence[Mapping[str, Any]], path: str | Path) -> Path:
    """Write XSTAR spectrum rows to CSV for lower-level solver routines."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["energy", "incident", "transmitted", "emit_inward", "emit_outward"]
    extra = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames and key not in extra:
                extra.append(str(key))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames + extra)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames + extra})
    return path


def read_xout_parameters(path: str | Path, hdu_name: str = "PARAMETERS") -> List[Dict[str, Any]]:
    """Read the ``PARAMETERS`` table from an XSTAR output FITS file if present."""
    path = Path(path)
    if fits is None:
        return _read_fits_table_fallback(path, hdu_name)
    with fits.open(path) as hdul:
        if hdu_name not in hdul:
            return []
        return table_hdu_to_rows(hdul[hdu_name])



def list_fits_hdus(path: str | Path) -> List[Dict[str, Any]]:
    """Return a compact inventory of HDUs and table columns in a FITS file.

    This is useful for XSTAR local-state products whose exact HDU names can vary
    between run modes, such as ``xout_abund1.fits`` and ``xout_detail.fits``.
    If astropy is unavailable, a lightweight FITS ASCII-table fallback is used.
    """
    path = Path(path)
    rows: List[Dict[str, Any]] = []
    if fits is None:
        for hdu in _raw_fits_hdus(path):
            header = hdu["header"]
            nfields = int(header.get("TFIELDS", 0) or 0)
            columns = [str(header.get(f"TTYPE{i}", f"col{i}")).strip() for i in range(1, nfields + 1)]
            rows.append({
                "index": hdu["index"],
                "name": str(header.get("EXTNAME", "") or ""),
                "class": str(header.get("XTENSION", "PRIMARY") or "PRIMARY"),
                "n_rows": int(header.get("NAXIS2", 0) or 0),
                "n_columns": len(columns),
                "columns": ";".join(columns),
            })
        return rows
    with fits.open(path) as hdul:
        for idx, hdu in enumerate(hdul):
            columns = []
            if getattr(hdu, "columns", None) is not None:
                columns = list(getattr(hdu.columns, "names", []) or [])
            nrows = None
            if getattr(hdu, "data", None) is not None and hasattr(hdu.data, "__len__"):
                try:
                    nrows = len(hdu.data)
                except Exception:
                    nrows = None
            rows.append({
                "index": idx,
                "name": str(getattr(hdu, "name", "") or ""),
                "class": hdu.__class__.__name__,
                "n_rows": nrows,
                "n_columns": len(columns),
                "columns": ";".join(str(c) for c in columns),
            })
    return rows


def read_fits_table(path: str | Path, hdu_name: str) -> List[Dict[str, Any]]:
    """Read a named FITS table HDU into normalized row dictionaries.

    Unlike :func:`read_xout_lines`, this routine is deliberately generic and is
    used by diagnostics for ``xout_abund1.fits`` and related local-state files.
    If astropy is unavailable, XSTAR ASCII TABLE extensions are parsed by a
    lightweight built-in reader.
    """
    path = Path(path)
    if fits is None:
        return _read_fits_table_fallback(path, hdu_name)
    with fits.open(path) as hdul:
        if hdu_name not in hdul:
            return []
        return table_hdu_to_rows(hdul[hdu_name])


def read_xout_abundances(path: str | Path) -> Dict[str, List[Dict[str, Any]]]:
    """Read XSTAR ``xout_abund1.fits`` local-state tables.

    XSTAR writes this file in ``pprint.f90``.  The ``ABUNDANCES`` extension
    carries one row per radial zone with columns such as ``radius``,
    ``delta_r``, ``ion_parameter``, ``x_e``, ``n_p``, ``pressure``,
    ``temperature`` (in units of 10^4 K), ``frac_heat_error`` and one column per
    ion.  The ``COLUMNS`` extension stores integrated ionic columns, while
    ``HEATING`` and ``COOLING`` contain thermal-balance terms.
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    for hdu_name in ("ABUNDANCES", "COLUMNS", "HEATING", "COOLING"):
        rows = read_fits_table(path, hdu_name)
        if rows:
            out[hdu_name.lower()] = rows
    return out

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
