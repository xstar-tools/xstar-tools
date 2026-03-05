#!/usr/bin/env python3
"""Compare xstar-atomic line/emissivity rows with an external XSTAR CSV table.

The external CSV is intentionally simple and user-defined.  Recommended columns
are:

    ion,wavelength_A,reference_value

where ``reference_value`` may be an XSTAR emissivity, flux, rate, or any other
quantity you want to compare against the nearest xstar-atomic line.  This script
matches by ion and nearest wavelength and reports wavelength offsets plus any
available ratio for a named xstar-atomic column.

Example
-------
PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  ../xstar/data/atdb.fits xstar_reference_lines.csv \
  --ion "O VIII" --wavelength-tolerance 0.01 \
  --atomic-column line_energy_emissivity_coeff_erg_cm3_s
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from pprint import pprint

from xstar_atomic import XSTARAtomic


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


def main():
    p = argparse.ArgumentParser(description="Compare xstar-atomic outputs with an external XSTAR CSV line table.")
    p.add_argument("fitsfile")
    p.add_argument("reference_csv")
    p.add_argument("--ion", required=True)
    p.add_argument("--temperature", type=float, default=1e6)
    p.add_argument("--wavelength-tolerance", type=float, default=0.02)
    p.add_argument("--reference-column", default="reference_value")
    p.add_argument("--atomic-column", default="line_energy_emissivity_coeff_erg_cm3_s")
    args = p.parse_args()

    reference = [r for r in read_csv(args.reference_csv) if str(r.get("ion", args.ion)).strip().lower().replace("_", " ") == args.ion.lower().replace("_", " ")]
    if not reference:
        raise SystemExit(f"No rows for ion {args.ion!r} found in {args.reference_csv}")

    wave_values = [maybe_float(r.get("wavelength_A")) for r in reference]
    wave_values = [w for w in wave_values if w is not None]
    if not wave_values:
        raise SystemExit("Reference CSV must contain wavelength_A values")
    wmin = min(wave_values) - args.wavelength_tolerance
    wmax = max(wave_values) + args.wavelength_tolerance

    db = XSTARAtomic(args.fitsfile)
    emiss = db.emissivity(args.ion, wavelength=(wmin, wmax), temperatures=[args.temperature], include_unmatched_lines=True)
    atomic_rows = emiss["emissivity"]

    comparisons = []
    for ref in reference:
        rw = maybe_float(ref.get("wavelength_A"))
        if rw is None:
            continue
        candidates = [row for row in atomic_rows if maybe_float(row.get("wavelength_A")) is not None]
        if not candidates:
            comparisons.append({"reference_wavelength_A": rw, "status": "no_atomic_candidates"})
            continue
        best = min(candidates, key=lambda row: abs(maybe_float(row.get("wavelength_A")) - rw))
        aw = maybe_float(best.get("wavelength_A"))
        ref_val = maybe_float(ref.get(args.reference_column))
        atom_val = maybe_float(best.get(args.atomic_column))
        ratio = None
        if ref_val not in (None, 0.0) and atom_val is not None:
            ratio = atom_val / ref_val
        comparisons.append({
            "ion": args.ion,
            "reference_wavelength_A": rw,
            "atomic_wavelength_A": aw,
            "delta_wavelength_A": None if aw is None else aw - rw,
            "reference_value": ref_val,
            "atomic_value": atom_val,
            "atomic_over_reference": ratio,
            "atomic_lower_level": best.get("lower_level"),
            "atomic_upper_level": best.get("upper_level"),
            "atomic_eval_method": best.get("collision_eval_method"),
        })

    pprint({"n_reference_rows": len(reference), "n_atomic_rows": len(atomic_rows), "comparisons": comparisons})


if __name__ == "__main__":
    main()
