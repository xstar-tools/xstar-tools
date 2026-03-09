#!/usr/bin/env python3
"""Compare xstar-atomic rows with an external XSTAR line-output CSV table.

The external CSV can be generated from ``xout_lines1.fits`` with::

    PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
      xout_lines1.fits --out-csv xstar_lines.csv

Two comparison modes are supported:

``wavelength``
    Validate line identification by matching XSTAR and xstar-atomic rows by
    nearest wavelength.  This is the safest comparison because both outputs
    should agree on atomic wavelengths even when physical emissivity units differ.

``emissivity``
    Also report ratios between an xstar-atomic local atomic coefficient and an
    XSTAR model-output column such as ``emit_outward``.  These are not expected
    to be near unity unless ion fractions, density, volume/column geometry, and
    radiative-transfer assumptions are made consistent.

``both``
    Run wavelength matching and include emissivity-style ratios.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from pprint import pprint


DEFAULT_ATOMIC_COLUMN = "line_energy_emissivity_coeff_erg_cm3_s"


def maybe_float(x):
    try:
        if x in (None, ""):
            return None
        return float(x)
    except Exception:
        return None


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize_ion_name(text: str) -> str:
    return str(text).strip().lower().replace("_", " ").replace("-", " ")


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_parser():
    p = argparse.ArgumentParser(description="Compare xstar-atomic outputs with an external XSTAR CSV line table.")
    p.add_argument("fitsfile")
    p.add_argument("reference_csv")
    p.add_argument("--ion", required=True)
    p.add_argument("--temperature", type=float, default=1e6)
    p.add_argument("--wavelength-tolerance", type=float, default=0.02)
    p.add_argument("--wavelength-column", default=None,
                   help="Reference CSV wavelength column; defaults to wavelength_A if present, otherwise wavelength")
    p.add_argument("--reference-column", default="reference_value",
                   help="Reference value column, e.g. emit_outward from XSTAR xout_lines1.fits CSV")
    p.add_argument("--atomic-column", default=DEFAULT_ATOMIC_COLUMN,
                   help="xstar-atomic column used for emissivity-style ratios")
    p.add_argument("--mode", choices=["wavelength", "emissivity", "both"], default="wavelength",
                   help="Comparison mode. 'wavelength' validates IDs; 'emissivity'/'both' also report value ratios.")
    p.add_argument("--out-csv", help="Write comparison rows to CSV")
    p.add_argument("--out-json", help="Write full comparison payload to JSON")
    p.add_argument("--print-summary", action="store_true", help="Print compact summary instead of full payload")
    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)

    reference_all = read_csv(args.reference_csv)
    wanted_ion = normalize_ion_name(args.ion)
    reference = [
        r for r in reference_all
        if normalize_ion_name(r.get("ion", args.ion)) == wanted_ion
    ]
    if not reference:
        raise SystemExit(f"No rows for ion {args.ion!r} found in {args.reference_csv}")

    wave_col = args.wavelength_column
    if wave_col is None:
        fieldnames = set(reference[0].keys()) if reference else set()
        if "wavelength_A" in fieldnames:
            wave_col = "wavelength_A"
        elif "wavelength" in fieldnames:
            wave_col = "wavelength"
        else:
            raise SystemExit("Reference CSV must contain wavelength_A or wavelength, or pass --wavelength-column")

    wave_values = [maybe_float(r.get(wave_col)) for r in reference]
    wave_values = [w for w in wave_values if w is not None]
    if not wave_values:
        raise SystemExit(f"Reference CSV column {wave_col!r} contains no numeric wavelengths")
    wmin = min(wave_values) - args.wavelength_tolerance
    wmax = max(wave_values) + args.wavelength_tolerance

    from xstar_atomic import XSTARAtomic

    db = XSTARAtomic(args.fitsfile)
    emiss = db.emissivity(
        args.ion,
        wavelength=(wmin, wmax),
        temperatures=[args.temperature],
        include_unmatched_lines=True,
    )
    atomic_rows = emiss["emissivity"]

    comparisons = []
    n_matched_within_tolerance = 0
    for ref in reference:
        rw = maybe_float(ref.get(wave_col))
        if rw is None:
            continue
        candidates = [row for row in atomic_rows if maybe_float(row.get("wavelength_A")) is not None]
        if not candidates:
            comparisons.append({"ion": args.ion, "reference_wavelength_A": rw, "status": "no_atomic_candidates"})
            continue
        best = min(candidates, key=lambda row: abs(maybe_float(row.get("wavelength_A")) - rw))
        aw = maybe_float(best.get("wavelength_A"))
        delta = None if aw is None else aw - rw
        abs_delta = None if delta is None else abs(delta)
        within = abs_delta is not None and abs_delta <= args.wavelength_tolerance
        if within:
            n_matched_within_tolerance += 1

        ref_val = maybe_float(ref.get(args.reference_column))
        atom_val = maybe_float(best.get(args.atomic_column))
        ratio = None
        if args.mode in ("emissivity", "both") and ref_val not in (None, 0.0) and atom_val is not None:
            ratio = atom_val / ref_val

        row = {
            "ion": args.ion,
            "mode": args.mode,
            "match_status": "matched" if within else "nearest_outside_tolerance",
            "reference_wavelength_A": rw,
            "atomic_wavelength_A": aw,
            "delta_wavelength_A": delta,
            "abs_delta_wavelength_A": abs_delta,
            "wavelength_tolerance_A": args.wavelength_tolerance,
            "reference_column": args.reference_column,
            "reference_value": ref_val,
            "atomic_column": args.atomic_column,
            "atomic_value": atom_val if args.mode in ("emissivity", "both") else None,
            "atomic_over_reference": ratio,
            "atomic_lower_level": best.get("lower_level"),
            "atomic_upper_level": best.get("upper_level"),
            "atomic_lower_label": best.get("lower_label"),
            "atomic_upper_label": best.get("upper_label"),
            "atomic_eval_method": best.get("collision_eval_method"),
            "xstar_lower_level": ref.get("lower_level"),
            "xstar_upper_level": ref.get("upper_level"),
        }
        comparisons.append(row)

    summary = {
        "ion": args.ion,
        "mode": args.mode,
        "n_reference_rows": len(reference),
        "n_atomic_rows": len(atomic_rows),
        "n_comparisons": len(comparisons),
        "n_matched_within_tolerance": n_matched_within_tolerance,
        "wavelength_column": wave_col,
        "reference_column": args.reference_column,
        "atomic_column": args.atomic_column,
        "temperature_K": args.temperature,
        "wavelength_tolerance_A": args.wavelength_tolerance,
        "notes": [
            "Wavelength mode validates line identification and wavelength agreement.",
            "Emissivity ratios compare a local xstar-atomic coefficient to an XSTAR model-output column; ratios are not expected to be unity without matching the full plasma model.",
        ],
    }
    payload = {"summary": summary, "comparisons": comparisons}

    if args.out_csv:
        write_csv(args.out_csv, comparisons)
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if args.print_summary:
        pprint(summary)
    else:
        pprint(payload)


if __name__ == "__main__":
    main()
