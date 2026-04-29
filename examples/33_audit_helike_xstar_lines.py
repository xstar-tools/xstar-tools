#!/usr/bin/env python3
"""Audit XSTAR line-output FITS files when a He-like triplet converter is empty.

This helper is intended for cases such as a prepared Ca XIX density grid where
XSTAR completed and wrote ``xout_lines1.fits``, but the generated triplet
converter selected zero rows.  It reads the full XSTAR line table and reports:

* counts by XSTAR ion label;
* all rows in a wavelength window, regardless of ion label;
* all rows for the expected ion, regardless of wavelength;
* rows that look like He-like ground-to-n=2 triplet/resonance transitions based
  on the XSTAR lower/upper-level labels.

It does not modify XSTAR outputs and it does not validate suppress-resonance.
Use it to determine whether the issue is the ion label, wavelength window, or
absence of the desired triplet lines in the XSTAR output.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

def _write_csv(rows: Sequence[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fields: List[str] = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    else:
        fields = ["index", "ion", "lower_level", "upper_level", "wavelength", "emit_inward", "emit_outward", "depth_inward", "depth_outward", "helike_component"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _summarize_lines(rows: Sequence[Dict[str, Any]], fitsfile: str | Path) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    min_wave = None
    max_wave = None
    nonzero_out = 0
    nonzero_in = 0
    for row in rows:
        ion = str(row.get("ion", "")).strip()
        counts[ion] = counts.get(ion, 0) + 1
        w = _as_float(row.get("wavelength"))
        if w is not None:
            min_wave = w if min_wave is None else min(min_wave, w)
            max_wave = w if max_wave is None else max(max_wave, w)
        out = _as_float(row.get("emit_outward"))
        inn = _as_float(row.get("emit_inward"))
        if out not in (None, 0.0):
            nonzero_out += 1
        if inn not in (None, 0.0):
            nonzero_in += 1
    return {
        "fitsfile": str(fitsfile),
        "n_lines": len(rows),
        "n_ions": len([k for k in counts if k]),
        "counts_by_ion": dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "wavelength_min_A": min_wave,
        "wavelength_max_A": max_wave,
        "n_nonzero_emit_outward": nonzero_out,
        "n_nonzero_emit_inward": nonzero_in,
    }


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _norm_ion(text: Any) -> str:
    return str(text or "").strip().lower().replace("_", " ")


def _norm_level(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "").strip().lower())


def _in_window(row: Dict[str, Any], wmin: Optional[float], wmax: Optional[float]) -> bool:
    w = _as_float(row.get("wavelength"))
    if w is None:
        return False
    if wmin is not None and w < wmin:
        return False
    if wmax is not None and w > wmax:
        return False
    return True


def _ion_matches(row: Dict[str, Any], expected_ion: Optional[str]) -> bool:
    if not expected_ion:
        return True
    return _norm_ion(row.get("ion")) == _norm_ion(expected_ion)


def _looks_helike_n2(row: Dict[str, Any]) -> bool:
    lower = _norm_level(row.get("lower_level"))
    upper = _norm_level(row.get("upper_level"))
    if "1s2.1s_0" not in lower and "1s2" not in lower:
        return False
    return ("1s1.2s1.3s_1" in upper or "1s1.2p1.1p_1" in upper or "1s1.2p1.3p_" in upper)


def _component(row: Dict[str, Any]) -> str:
    upper = _norm_level(row.get("upper_level"))
    if "1s1.2s1.3s_1" in upper:
        return "forbidden"
    if "1s1.2p1.1p_1" in upper:
        return "resonance"
    if "1s1.2p1.3p_" in upper:
        return "intercombination"
    return "other"


def _limit(rows: Sequence[Dict[str, Any]], n: Optional[int]) -> List[Dict[str, Any]]:
    out = [dict(r) for r in rows]
    if n is not None:
        out = out[:n]
    return out


def _select_columns(row: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "index", "ion", "lower_level", "upper_level", "wavelength",
        "emit_inward", "emit_outward", "depth_inward", "depth_outward",
    ]
    out = {k: row.get(k, "") for k in keys if k in row}
    out["helike_component"] = _component(row)
    return out


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile", help="XSTAR xout_lines1.fits file to audit")
    parser.add_argument("--expected-ion", help="Expected XSTAR ion label, e.g. 'Ca XIX'")
    parser.add_argument("--wavelength-min", type=float, help="Minimum wavelength for nearby-line audit")
    parser.add_argument("--wavelength-max", type=float, help="Maximum wavelength for nearby-line audit")
    parser.add_argument("--out-dir", default=None, help="Optional output directory for audit CSV/JSON files")
    parser.add_argument("--limit", type=int, default=25, help="Maximum rows printed per section")
    parser.add_argument("--print-rows", action="store_true", help="Print selected rows as JSON")
    args = parser.parse_args(argv)

    from xstar_atomic.xstar_outputs import read_xout_lines

    fitsfile = Path(args.fitsfile)
    rows = read_xout_lines(fitsfile)
    all_summary = _summarize_lines(rows, fitsfile)

    nearby = [_select_columns(r) for r in rows if _in_window(r, args.wavelength_min, args.wavelength_max)]
    ion_rows = [_select_columns(r) for r in rows if _ion_matches(r, args.expected_ion)] if args.expected_ion else []
    ion_nearby = [_select_columns(r) for r in rows if _ion_matches(r, args.expected_ion) and _in_window(r, args.wavelength_min, args.wavelength_max)] if args.expected_ion else []
    helike_like = [_select_columns(r) for r in rows if _looks_helike_n2(r)]
    helike_ion = [_select_columns(r) for r in rows if _looks_helike_n2(r) and _ion_matches(r, args.expected_ion)] if args.expected_ion else []

    components = {"forbidden": 0, "intercombination": 0, "resonance": 0, "other": 0}
    for row in ion_nearby:
        components[row.get("helike_component", "other")] = components.get(row.get("helike_component", "other"), 0) + 1

    summary: Dict[str, Any] = {
        "fitsfile": str(fitsfile),
        "expected_ion": args.expected_ion,
        "wavelength_min_A": args.wavelength_min,
        "wavelength_max_A": args.wavelength_max,
        "n_all_lines": len(rows),
        "counts_by_ion": all_summary.get("counts_by_ion", {}),
        "n_nearby_rows_any_ion": len(nearby),
        "n_expected_ion_rows_any_wavelength": len(ion_rows),
        "n_expected_ion_rows_in_window": len(ion_nearby),
        "n_helike_like_rows_any_ion": len(helike_like),
        "n_helike_like_rows_expected_ion": len(helike_ion),
        "components_in_expected_ion_window": components,
        "has_complete_triplet_target": components.get("forbidden", 0) > 0 and components.get("intercombination", 0) > 0 and components.get("resonance", 0) > 0,
    }

    print("He-like XSTAR line-output audit")
    print("--------------------------------")
    print(f"fitsfile: {fitsfile}")
    if args.expected_ion:
        print(f"expected ion: {args.expected_ion}")
    if args.wavelength_min is not None or args.wavelength_max is not None:
        print(f"wavelength window: {args.wavelength_min} .. {args.wavelength_max} A")
    print(f"all line rows: {len(rows)}")
    print("top ion labels:")
    for ion, count in list(summary["counts_by_ion"].items())[:15]:
        print(f"  {ion or '(blank)'}: {count}")
    print(f"nearby rows, any ion: {len(nearby)}")
    if args.expected_ion:
        print(f"{args.expected_ion} rows, any wavelength: {len(ion_rows)}")
        print(f"{args.expected_ion} rows in window: {len(ion_nearby)}")
        print(f"{args.expected_ion} He-like n=2-looking rows: {len(helike_ion)}")
    print("components in expected-ion window:", components)
    print("complete triplet target:", summary["has_complete_triplet_target"])

    if args.out_dir:
        out_dir = Path(args.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_csv(nearby, out_dir / "nearby_rows_any_ion.csv")
        _write_csv(ion_rows, out_dir / "expected_ion_rows_any_wavelength.csv")
        _write_csv(ion_nearby, out_dir / "expected_ion_rows_in_window.csv")
        _write_csv(helike_like, out_dir / "helike_like_rows_any_ion.csv")
        _write_csv(helike_ion, out_dir / "helike_like_rows_expected_ion.csv")
        _write_json(out_dir / "helike_xstar_line_audit_summary.json", summary)
        print(f"wrote audit files under: {out_dir}")

    if args.print_rows:
        payload = {
            "summary": summary,
            "nearby_rows_any_ion": _limit(nearby, args.limit),
            "expected_ion_rows_any_wavelength": _limit(ion_rows, args.limit),
            "expected_ion_rows_in_window": _limit(ion_nearby, args.limit),
            "helike_like_rows_expected_ion": _limit(helike_ion, args.limit),
        }
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
