#!/usr/bin/env python3
"""Two-parameter type-68-aware O VII recombination/cascade tuning scan.

This Stage-6 helper extends ``17_o7_type68_cascade_tuning_scan.py`` by scanning
both of the target-map changes suggested by the type-68 results:

* redistribute a fraction of the forbidden target weight from level 2 into the
  intercombination targets 3, 4, and 5, and
* suppress the resonance target level 7.

For a forbidden-to-intercombination shift ``d`` and resonance weight ``r``, the
map is

    2:(1-d), 3:(1+d/3), 4:(1+d/3), 5:(1+d/3), 7:r

so the triplet-target total for levels 2--5 is preserved while the resonance
feeding is varied.  The equal-target map remains the reference baseline.
This remains a prototype because the underlying O VIII -> O VII recombination
records are total rates, not true level-resolved recombination feeds.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def as_float_or_blank(value):
    if value is None:
        return ""
    try:
        return f"{float(value):.10g}"
    except Exception:
        return value


def select_triplet(summary: dict, density: Optional[float] = None) -> dict:
    rows = summary.get("solver_triplet_diagnostics") or []
    if not rows:
        return {}
    if density is None:
        return rows[0]
    return min(rows, key=lambda row: abs(float(row.get("electron_density_cm^-3", 0.0)) - density))


def target_map_from_shift(forbidden_shift: float, resonance_weight: float) -> str:
    f_weight = 1.0 - forbidden_shift
    i_weight = 1.0 + forbidden_shift / 3.0
    return (
        f"2:{f_weight:.10g},"
        f"3:{i_weight:.10g},"
        f"4:{i_weight:.10g},"
        f"5:{i_weight:.10g},"
        f"7:{resonance_weight:.10g}"
    )


def case_label(forbidden_shift: float, resonance_weight: float) -> str:
    return f"f2i{int(round(forbidden_shift * 100)):03d}_r{int(round(resonance_weight * 100)):03d}"


def score_row(row: Dict[str, object]) -> float:
    """Simple relative squared-error score in R and G."""
    try:
        r_over = float(row["R_over_xstar"])
        g_over = float(row["G_over_xstar"])
    except Exception:
        return float("inf")
    return (r_over - 1.0) ** 2 + (g_over - 1.0) ** 2


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--electron-densities", type=float, nargs="+", default=[1.0, 1.0e4, 1.0e8, 1.0e10, 1.0e12])
    parser.add_argument("--compare-density", type=float, default=1.0, help="Density row used for the compact CSV comparison table.")
    parser.add_argument("--source-mode", default="selected-cascade-yield", choices=["selected-statistical", "selected-cascade-yield"])
    parser.add_argument("--cascade-weight-floor", type=float, default=0.02)
    parser.add_argument("--forbidden-shifts", type=float, nargs="+", default=[0.0, 0.10, 0.20, 0.30, 0.40, 0.50], help="Fractions moved from level 2 to levels 3,4,5.")
    parser.add_argument("--resonance-weights", type=float, nargs="+", default=[1.0, 0.75, 0.60, 0.50, 0.40, 0.30, 0.20], help="Target weights for resonance level 7.")
    parser.add_argument("--out-dir", default="o7_type68_2d_cascade_tuning_scan")
    parser.add_argument("--xstar-lines-csv", default="xstar_test_run/xstar_o7_triplet_lines.csv")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    workflow_script = Path(__file__).resolve().with_name("13_o7_recombination_cascade_workflow.py")
    rows: List[Dict[str, object]] = []
    all_density_rows: List[Dict[str, object]] = []
    xstar_ref = None

    cases: List[Tuple[str, float, float, str]] = []
    for d in args.forbidden_shifts:
        if d < 0.0 or d >= 1.0:
            raise SystemExit(f"Forbidden shift must satisfy 0 <= shift < 1; got {d}")
        for r in args.resonance_weights:
            if r <= 0.0:
                raise SystemExit(f"Resonance weight must be positive; got {r}")
            label = "equal" if abs(d) < 1e-15 and abs(r - 1.0) < 1e-15 else case_label(d, r)
            target_map = target_map_from_shift(d, r)
            cases.append((label, d, r, target_map))

    # Remove accidental duplicate labels if users provide repeated grids.
    deduped: List[Tuple[str, float, float, str]] = []
    seen = set()
    for item in cases:
        if item[0] in seen:
            continue
        seen.add(item[0])
        deduped.append(item)

    for label, f_shift, r_weight, target_map in deduped:
        case_dir = out_dir / label
        cmd = [
            sys.executable,
            str(workflow_script),
            args.fitsfile,
            "--source-mode", args.source_mode,
            "--cascade-target-levels", target_map,
            "--cascade-weight-floor", f"{args.cascade_weight_floor:g}",
            "--temperature", f"{args.temperature:g}",
            "--electron-densities", *[f"{x:g}" for x in args.electron_densities],
            "--out-dir", str(case_dir),
            "--xstar-lines-csv", args.xstar_lines_csv,
        ]
        if args.print_summary:
            cmd.append("--print-summary")
        subprocess.run(cmd, check=True)

        summary_path = case_dir / "o7_recomb_cascade_workflow_summary.json"
        summary = read_json(summary_path)
        xstar_ref = xstar_ref or summary.get("xstar_triplet_reference")
        r_x = (xstar_ref or {}).get("R_f_over_i")
        g_x = (xstar_ref or {}).get("G_f_plus_i_over_r")

        for triplet in summary.get("solver_triplet_diagnostics") or []:
            r_val = triplet.get("R_f_over_i")
            g_val = triplet.get("G_f_plus_i_over_r")
            all_density_rows.append({
                "case": label,
                "forbidden_shift": f_shift,
                "resonance_weight": r_weight,
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

        triplet = select_triplet(summary, args.compare_density)
        r_val = triplet.get("R_f_over_i")
        g_val = triplet.get("G_f_plus_i_over_r")
        rows.append({
            "case": label,
            "forbidden_shift": f_shift,
            "resonance_weight": r_weight,
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

    rows_sorted = sorted(rows, key=score_row)

    fieldnames = [
        "case", "forbidden_shift", "resonance_weight", "target_map",
        "temperature_K", "electron_density_cm^-3", "R_f_over_i",
        "G_f_plus_i_over_r", "R_xstar", "G_xstar", "R_over_xstar",
        "G_over_xstar", "summary_json",
    ]
    out_csv = out_dir / "o7_type68_2d_cascade_tuning_scan.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    out_ranked_csv = out_dir / "o7_type68_2d_cascade_tuning_scan_ranked.csv"
    with out_ranked_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames + ["score"])
        writer.writeheader()
        for row in rows_sorted:
            row2 = dict(row)
            row2["score"] = score_row(row)
            writer.writerow(row2)

    out_all_csv = out_dir / "o7_type68_2d_cascade_tuning_scan_all_densities.csv"
    with out_all_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_density_rows)

    out_json = out_dir / "o7_type68_2d_cascade_tuning_scan_summary.json"
    with out_json.open("w", encoding="utf-8") as handle:
        json.dump({
            "fitsfile": args.fitsfile,
            "compare_density_cm^-3": args.compare_density,
            "forbidden_shifts": args.forbidden_shifts,
            "resonance_weights": args.resonance_weights,
            "cases": rows,
            "ranked_cases": [{**row, "score": score_row(row)} for row in rows_sorted],
            "all_density_cases": all_density_rows,
            "xstar_reference": xstar_ref,
            "note": "Two-parameter type-68-aware scan: move target weight from forbidden to intercombination levels and vary resonance target weight.",
        }, handle, indent=2)

    print("O VII type-68 two-parameter cascade tuning scan")
    print("-------------------------------------------------")
    print(f"Wrote: {out_csv}")
    print(f"Wrote ranked table: {out_ranked_csv}")
    print(f"Wrote all-density table: {out_all_csv}")
    print("Top cases by simple relative R/G score:")
    for row in rows_sorted[:10]:
        print(
            f"{row['case']:16s} d={float(row['forbidden_shift']):.3g} r={float(row['resonance_weight']):.3g} "
            f"R={as_float_or_blank(row['R_f_over_i']):>10s} "
            f"G={as_float_or_blank(row['G_f_plus_i_over_r']):>10s} "
            f"R/X={as_float_or_blank(row['R_over_xstar']):>10s} "
            f"G/X={as_float_or_blank(row['G_over_xstar']):>10s} "
            f"score={score_row(row):.5g}"
        )


if __name__ == "__main__":
    main()
