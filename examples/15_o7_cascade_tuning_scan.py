#!/usr/bin/env python3
"""Scan prototype O VII recombination/cascade target maps.

This helper runs ``examples/13_o7_recombination_cascade_workflow.py`` for the
recommended equal-target Stage-6 baseline and for several target maps that shift
source weight from the forbidden upper level into the intercombination upper
levels while preserving the resonance target and approximately preserving the
total triplet/resonance balance.  It then collects the resulting O VII
triplet diagnostics and compares them with the XSTAR reference ratios when the
``xstar_test_run/xstar_o7_triplet_lines.csv`` file is available.

The scan is intended for sensitivity studies.  The underlying source model still
redistributes total O VIII -> O VII recombination rates and is not yet a true
level-resolved recombination-cascade model.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from xstar_atomic.recombination import CASCADE_TARGET_PRESETS

DEFAULT_CASES = [
    ("equal", "o7-triplet-equal"),
    ("f2i010_rkeep", "o7-triplet-f2i010-rkeep"),
    ("f2i015_rkeep", "o7-triplet-f2i015-rkeep"),
    ("f2i025_rkeep", "o7-triplet-f2i025-rkeep"),
    ("f2i050_rkeep", "o7-triplet-f2i050-rkeep"),
    # Keep the old simple fdown grid as comparison cases; these usually reduce
    # R but also move G away from XSTAR because the total triplet/resonance
    # balance is not preserved.
    ("fdown090_rkeep", "o7-triplet-fdown090-rkeep"),
    ("fdown085_rkeep", "o7-triplet-fdown085-rkeep"),
    ("fdown075_rkeep", "o7-triplet-fdown075-rkeep"),
    ("fdown050_rkeep", "o7-triplet-fdown-rkeep"),
]


def read_summary(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def first_density_triplet(summary: dict) -> dict:
    rows = summary.get("solver_triplet_diagnostics") or []
    if not rows:
        return {}
    return rows[0]


def as_float_or_blank(value):
    if value is None:
        return ""
    try:
        return f"{float(value):.10g}"
    except Exception:
        return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--electron-densities", type=float, nargs="+", default=[1.0, 1.0e4, 1.0e8])
    parser.add_argument("--source-mode", default="selected-cascade-yield", choices=["selected-statistical", "selected-cascade-yield"])
    parser.add_argument("--cascade-weight-floor", type=float, default=0.02)
    parser.add_argument("--out-dir", default="o7_cascade_tuning_scan")
    parser.add_argument("--xstar-lines-csv", default="xstar_test_run/xstar_o7_triplet_lines.csv")
    parser.add_argument("--cases", nargs="*", default=[], help="Optional case list as label:preset or label:levelmap. If omitted, runs the built-in Stage-6 tuning grid.")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = []
    if args.cases:
        for item in args.cases:
            if ":" not in item:
                raise SystemExit(f"Bad --cases entry {item!r}; use label:preset or label:levelmap")
            label, spec = item.split(":", 1)
            cases.append((label, spec))
    else:
        cases = DEFAULT_CASES

    script = Path(__file__).resolve().with_name("13_o7_recombination_cascade_workflow.py")
    rows: List[Dict[str, object]] = []
    xstar_ref = None

    for label, spec in cases:
        case_dir = out_dir / label
        cmd = [
            sys.executable,
            str(script),
            args.fitsfile,
            "--source-mode", args.source_mode,
            "--cascade-weight-floor", f"{args.cascade_weight_floor:g}",
            "--temperature", f"{args.temperature:g}",
            "--electron-densities", *[f"{x:g}" for x in args.electron_densities],
            "--out-dir", str(case_dir),
            "--xstar-lines-csv", args.xstar_lines_csv,
        ]
        if spec in CASCADE_TARGET_PRESETS:
            cmd += ["--cascade-target-preset", spec]
            target_map = CASCADE_TARGET_PRESETS[spec]
            preset = spec
        else:
            cmd += ["--cascade-target-levels", spec]
            target_map = spec
            preset = ""
        if args.print_summary:
            cmd.append("--print-summary")
        subprocess.run(cmd, check=True)

        summary_path = case_dir / "o7_recomb_cascade_workflow_summary.json"
        summary = read_summary(summary_path)
        triplet = first_density_triplet(summary)
        xstar_ref = xstar_ref or summary.get("xstar_triplet_reference")
        r_val = triplet.get("R_f_over_i")
        g_val = triplet.get("G_f_plus_i_over_r")
        r_x = (xstar_ref or {}).get("R_f_over_i")
        g_x = (xstar_ref or {}).get("G_f_plus_i_over_r")
        rows.append({
            "case": label,
            "preset": preset,
            "target_map": target_map,
            "temperature_K": triplet.get("temperature_K", args.temperature),
            "electron_density_cm^-3": triplet.get("electron_density_cm^-3"),
            "R_f_over_i": r_val,
            "G_f_plus_i_over_r": g_val,
            "R_xstar": r_x,
            "G_xstar": g_x,
            "R_over_xstar": (float(r_val) / float(r_x)) if r_val is not None and r_x else None,
            "G_over_xstar": (float(g_val) / float(g_x)) if g_val is not None and g_x else None,
            "summary_json": str(summary_path),
        })

    out_csv = out_dir / "o7_cascade_tuning_scan.csv"
    fieldnames = [
        "case", "preset", "target_map", "temperature_K", "electron_density_cm^-3",
        "R_f_over_i", "G_f_plus_i_over_r", "R_xstar", "G_xstar", "R_over_xstar",
        "G_over_xstar", "summary_json",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    out_json = out_dir / "o7_cascade_tuning_scan_summary.json"
    with out_json.open("w", encoding="utf-8") as handle:
        json.dump({"fitsfile": args.fitsfile, "cases": rows, "xstar_reference": xstar_ref}, handle, indent=2)

    print("O VII cascade tuning scan")
    print("---------------------------")
    print(f"Wrote: {out_csv}")
    for row in rows:
        print(
            f"{row['case']:18s} R={as_float_or_blank(row['R_f_over_i']):>10s} "
            f"G={as_float_or_blank(row['G_f_plus_i_over_r']):>10s} "
            f"R/X={as_float_or_blank(row['R_over_xstar']):>10s} "
            f"G/X={as_float_or_blank(row['G_over_xstar']):>10s}"
        )


if __name__ == "__main__":
    main()
