#!/usr/bin/env python3
"""Prototype O VII recombination/cascade source workflow.

This example implements the current Stage-6 workflow for O VII triplet tests:

1. evaluate total O VIII -> O VII recombination records;
2. distribute the total source into selected O VII excited/high levels using either
   statistical or cascade-yield weighting;
3. redistribute that prototype source through the radiative branching network;
4. feed the cascade source CSV into the sparse level-population solver;
5. compute O VII triplet R=f/i and G=(f+i)/r diagnostics;
6. optionally compare the triplet ratios with an XSTAR ``xout_lines1`` CSV.

Important
---------
This is a *prototype source-distribution workflow*.  The default
``selected-cascade-yield`` mode weights candidate source levels by their
radiative-cascade probability of feeding selected O VII triplet/cascade target
levels.  The XSTAR ATDB records currently decoded for oxygen are still total
recombination rates, not true level-resolved recombination-cascade feeds.  The source redistribution is useful
for sensitivity tests and solver validation, but it should not yet be treated as
a final physical O VII triplet model.

Example
-------

::

  PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
    ../xstar/data/atdb.fits \
    --out-dir o7_recomb_cascade_workflow \
    --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys

from xstar_atomic.recombination import CASCADE_TARGET_PRESETS
from pathlib import Path
from typing import Optional


def _run(cmd: list[str]) -> None:
    print("\n$", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def _maybe_float(x) -> Optional[float]:
    try:
        val = float(x)
    except Exception:
        return None
    return val


def _classify_o7_wavelength(wavelength: float) -> Optional[str]:
    if abs(wavelength - 22.1012) < 0.03:
        return "f"
    if abs(wavelength - 21.8070) < 0.04 or abs(wavelength - 21.8044) < 0.04:
        return "i"
    if abs(wavelength - 21.6020) < 0.03:
        return "r"
    return None


def _xstar_o7_triplet_ratios(path: Path, value_column: str = "emit_outward") -> dict:
    totals = {"f": 0.0, "i": 0.0, "r": 0.0}
    counts = {"f": 0, "i": 0, "r": 0}
    if not path.exists():
        return {"available": False, "path": str(path)}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ion = str(row.get("ion", "")).strip().lower().replace(" ", "")
            if ion not in {"ovii", "o_vii", "o7"}:
                # The converted XSTAR CSV usually uses "O VII".
                if "ovii" not in ion and "o vii" not in str(row.get("ion", "")).lower():
                    continue
            wav = _maybe_float(row.get("wavelength") or row.get("wavelength_A"))
            val = _maybe_float(row.get(value_column))
            if wav is None or val is None:
                continue
            kind = _classify_o7_wavelength(wav)
            if kind is None:
                continue
            totals[kind] += val
            counts[kind] += 1
    f, i, r = totals["f"], totals["i"], totals["r"]
    return {
        "available": True,
        "path": str(path),
        "value_column": value_column,
        "forbidden": f,
        "intercombination": i,
        "resonance": r,
        "R_f_over_i": (f / i) if i > 0 else None,
        "G_f_plus_i_over_r": ((f + i) / r) if r > 0 else None,
        "counts": counts,
        "note": "XSTAR model-output ratio; not directly normalized to local xstar-atomic emissivity coefficients.",
    }


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile")
    parser.add_argument("--temperature", type=float, default=1.0e6)
    parser.add_argument("--electron-densities", type=float, nargs="+", default=[1.0, 1.0e4, 1.0e8])
    parser.add_argument("--source-levels", default="2,3,4,5,7,8,9,10,11,12,13,14,15,16,17,18,19,20")
    parser.add_argument("--source-mode", default="selected-cascade-yield", choices=["selected-statistical", "selected-cascade-yield"], help="Prototype source allocation mode for total O VIII -> O VII recombination")
    parser.add_argument("--cascade-target-levels", default=None, help="Target levels or level:weight pairs for selected-cascade-yield allocation. If omitted and no preset is selected, the recommended equal O VII triplet map is used.")
    parser.add_argument("--cascade-target-preset", default="none", choices=["", "none"] + sorted(CASCADE_TARGET_PRESETS), help="Named cascade target weighting preset for reproducible Stage-6 experiments; manual --cascade-target-levels overrides this")
    parser.add_argument("--cascade-weight-floor", type=float, default=0.02, help="Small fallback source weight for selected levels that do not feed target levels")
    parser.add_argument("--out-dir", default="o7_recomb_cascade_workflow")
    parser.add_argument("--xstar-lines-csv", default="xstar_test_run/xstar_o7_triplet_lines.csv")
    parser.add_argument("--xstar-value-column", default="emit_outward")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    py = sys.executable

    initial_source_csv = out_dir / "o7_recomb_initial_sources.csv"
    cascade_source_csv = out_dir / "o7_recomb_cascade_sources.csv"
    cascade_path_csv = out_dir / "o7_recomb_cascade_paths.csv"
    recomb_summary_json = out_dir / "o7_recomb_cascade_source_summary.json"
    solver_summary_json = out_dir / "o7_triplet_cascade_solver_summary.json"
    solver_lines_csv = out_dir / "o7_triplet_cascade_lines.csv"
    solver_pop_csv = out_dir / "o7_triplet_cascade_populations.csv"
    solver_rg_csv = out_dir / "o7_triplet_cascade_RG.csv"
    xstar_ratio_json = out_dir / "xstar_o7_triplet_ratios.json"
    combined_summary_json = out_dir / "o7_recomb_cascade_workflow_summary.json"

    density_args = [f"{x:g}" for x in args.electron_densities]
    preset = (args.cascade_target_preset or "none").strip()
    explicit_target_levels = args.cascade_target_levels
    default_equal_targets = "2:1.0,3:1.0,4:1.0,5:1.0,7:1.0"
    effective_target_levels = explicit_target_levels
    if effective_target_levels is None and preset.lower() in {"", "none"}:
        # Preserve the recommended Stage-6 baseline for normal runs, but do not
        # pass this default when a non-none preset is requested.  Otherwise the
        # recombination CLI correctly treats --cascade-target-levels as an
        # explicit manual override and the preset would never take effect.
        effective_target_levels = default_equal_targets

    recomb_cmd = [
        py, "-m", "xstar_atomic.recombination", args.fitsfile,
        "--element", "O",
        "--ion-stage", "7",
        "--temperatures", f"{args.temperature:g}",
        "--electron-densities", *density_args,
        "--source-mode", args.source_mode,
        "--source-levels", args.source_levels,
    ]
    if effective_target_levels:
        recomb_cmd += ["--cascade-target-levels", effective_target_levels]
    if preset and preset.lower() != "none":
        recomb_cmd += ["--cascade-target-preset", preset]
    recomb_cmd += [
        "--cascade-weight-floor", f"{args.cascade_weight_floor:g}",
        "--source-csv", str(initial_source_csv),
        "--cascade-mode", "radiative-branching",
        "--cascade-source-csv", str(cascade_source_csv),
        "--cascade-path-csv", str(cascade_path_csv),
        "--summary-json", str(recomb_summary_json),
        "--summary",
    ]
    _run(recomb_cmd)

    _run([
        py, "-m", "xstar_atomic.solver", args.fitsfile,
        "--element", "O",
        "--ion-stage", "7",
        "--wavelength-min", "21.4",
        "--wavelength-max", "22.2",
        "--temperatures", f"{args.temperature:g}",
        "--electron-densities", *density_args,
        "--electron-density-for-lmixing", f"{args.electron_densities[0]:g}",
        "--component-mode", "ground",
        "--prune-unconnected-levels",
        "--linear-solver", "sparse",
        "--recombination-source-csv", str(cascade_source_csv),
        "--out-lines-csv", str(solver_lines_csv),
        "--out-populations-csv", str(solver_pop_csv),
        "--out-triplet-csv", str(solver_rg_csv),
        "--summary-json", str(solver_summary_json),
        "--print-summary",
    ])

    xstar_ratios = _xstar_o7_triplet_ratios(Path(args.xstar_lines_csv), args.xstar_value_column)
    xstar_ratio_json.write_text(json.dumps(xstar_ratios, indent=2), encoding="utf-8")

    workflow_summary = {
        "fitsfile": args.fitsfile,
        "temperature_K": args.temperature,
        "electron_densities_cm^-3": args.electron_densities,
        "source_levels": args.source_levels,
        "source_mode": args.source_mode,
        "cascade_target_levels": effective_target_levels or "",
        "cascade_target_preset": preset or "none",
        "cascade_weight_floor": args.cascade_weight_floor,
        "outputs": {
            "initial_source_csv": str(initial_source_csv),
            "cascade_source_csv": str(cascade_source_csv),
            "cascade_path_csv": str(cascade_path_csv),
            "recombination_summary_json": str(recomb_summary_json),
            "solver_summary_json": str(solver_summary_json),
            "solver_lines_csv": str(solver_lines_csv),
            "solver_populations_csv": str(solver_pop_csv),
            "solver_triplet_csv": str(solver_rg_csv),
            "xstar_ratio_json": str(xstar_ratio_json),
        },
        "recombination_summary": _load_json(recomb_summary_json),
        "solver_triplet_diagnostics": _load_json(solver_summary_json).get("triplet_diagnostics", []),
        "xstar_triplet_reference": xstar_ratios,
        "status_note": "Prototype Stage-6 workflow: total recombination is redistributed over selected levels and radiative cascades; not yet a true level-resolved recombination model.",
    }
    combined_summary_json.write_text(json.dumps(workflow_summary, indent=2), encoding="utf-8")

    print("\nO VII recombination/cascade workflow summary")
    print("-------------------------------------------")
    print(f"Initial source CSV: {initial_source_csv}")
    print(f"Cascade source CSV: {cascade_source_csv}")
    print(f"Solver triplet CSV: {solver_rg_csv}")
    print(f"XSTAR ratio JSON: {xstar_ratio_json}")
    print(f"Combined summary JSON: {combined_summary_json}")
    if args.print_summary:
        print(json.dumps(workflow_summary, indent=2))


if __name__ == "__main__":
    main()
