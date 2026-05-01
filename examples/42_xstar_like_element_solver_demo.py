#!/usr/bin/env python3
"""Run the pure-Python XSTAR-like element-solver reference scaffold.

This example starts the transition from isolated-ion source fitting to an
XSTAR-like element-wide population workflow.  It writes ion-block diagnostics,
line emissivities, populations, transition logs, and adjacent-ion coupling
candidate counts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import csv


def write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def parse_stage_list(text: str | None):
    if not text:
        return None
    return [int(float(x.strip())) for x in text.replace(";", ",").split(",") if x.strip()]


def main(argv=None):
    p = argparse.ArgumentParser(description="Pure-Python XSTAR-like element-coupled solver scaffold")
    p.add_argument("fitsfile", nargs="?", help="Path to atdb.fits. May be omitted if configured.")
    p.add_argument("--element", required=True, help="Element symbol or atomic number, e.g. C, O, Mg, Ca")
    p.add_argument("--he-like-stage", type=int, required=True, help="He-like ion stage, e.g. 5 for C V, 7 for O VII")
    p.add_argument("--adjacent-stages", help="Comma-separated stages to include. Default: H-like + He-like.")
    p.add_argument("--temperature", type=float, required=True)
    p.add_argument("--electron-density", type=float, required=True)
    p.add_argument("--wavelength-min", type=float)
    p.add_argument("--wavelength-max", type=float)
    p.add_argument("--max-level", type=int)
    p.add_argument("--component-mode", choices=["all", "ground"], default="all")
    p.add_argument("--no-prune-null-rate-levels", action="store_true")
    p.add_argument("--linear-solver", default="svd", choices=["dense", "svd", "sparse", "auto"])
    p.add_argument("--rank-deficient-action", default="svd", choices=["lstsq", "svd", "error"])
    p.add_argument("--negative-population-action", default="keep", choices=["keep", "clip", "error"])
    p.add_argument("--index-cache", action="store_true")
    p.add_argument("--index-cache-path")
    p.add_argument("--out-dir", default="xstar_like_element_solver")
    p.add_argument("--dry-run", action="store_true", help="Write command/intent files without opening atdb.fits")
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args(argv)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        rows = [{
            "fitsfile": args.fitsfile,
            "element": args.element,
            "he_like_stage": args.he_like_stage,
            "adjacent_stages": args.adjacent_stages or f"{args.he_like_stage + 1},{args.he_like_stage}",
            "temperature_K": args.temperature,
            "electron_density_cm^-3": args.electron_density,
            "wavelength_min": args.wavelength_min,
            "wavelength_max": args.wavelength_max,
            "max_level": args.max_level,
            "status": "dry_run_not_executed",
        }]
        write_csv(out / "xstar_like_element_solver_ion_blocks.csv", [])
        write_csv(out / "xstar_like_element_solver_coupling_candidates.csv", [])
        write_csv(out / "xstar_like_element_solver_populations.csv", [])
        write_csv(out / "xstar_like_element_solver_lines.csv", [])
        write_csv(out / "xstar_like_element_solver_transitions.csv", [])
        write_csv(out / "xstar_like_element_solver_triplet.csv", [])
        write_csv(out / "xstar_like_element_solver_commands.csv", rows)
        summary = {"mode": "dry_run", "status": "not_executed", **rows[0]}
        (out / "xstar_like_element_solver_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (out / "xstar_like_element_solver_summary.md").write_text("# XSTAR-like element-solver dry run\n\nNo FITS file was opened.\n", encoding="utf-8")
        if args.print_summary:
            print("XSTAR-like element solver dry run")
            print("----------------------------------")
            print(f"element={args.element} he_like_stage={args.he_like_stage} stages={summary['adjacent_stages']}")
            print(f"wrote: {out / 'xstar_like_element_solver_summary.md'}")
        return

    from xstar_atomic.xstar_element_solver import solve_element_reference, write_element_solver_outputs

    result = solve_element_reference(
        args.fitsfile,
        element=args.element,
        he_like_stage=args.he_like_stage,
        adjacent_stages=parse_stage_list(args.adjacent_stages),
        temperature=args.temperature,
        electron_density=args.electron_density,
        wavelength_min=args.wavelength_min,
        wavelength_max=args.wavelength_max,
        max_level=args.max_level,
        component_mode=args.component_mode,
        prune_null_rate_levels=not args.no_prune_null_rate_levels,
        linear_solver=args.linear_solver,
        rank_deficient_action=args.rank_deficient_action,
        negative_population_action=args.negative_population_action,
        index_cache=args.index_cache,
        index_cache_path=args.index_cache_path,
    )
    write_element_solver_outputs(result, out)
    if args.print_summary:
        summ = result["summary"]
        trip = summ.get("he_like_triplet", {})
        print("XSTAR-like element solver")
        print("-------------------------")
        print(f"element={summ.get('element')} stages={summ.get('stages')} coupling={summ.get('adjacent_coupling_status')}")
        print(f"triplet f/i/r={trip.get('f_fraction'):.6g}/{trip.get('i_fraction'):.6g}/{trip.get('r_fraction'):.6g} R={trip.get('R')} G={trip.get('G')}")
        print(f"wrote: {out / 'xstar_like_element_solver_summary.md'}")


if __name__ == "__main__":
    main()
