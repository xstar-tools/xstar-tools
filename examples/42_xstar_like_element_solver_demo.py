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
    p.add_argument("--adjacent-coupling-mode", default="recombination-source", choices=["none", "catalog", "recombination-source"], help="How to handle adjacent-ion coupling records")
    p.add_argument("--adjacent-coupling-source-mode", default="record-destination", choices=["ground", "record-destination", "selected-equal", "selected-statistical", "none"], help="Allocation mode for evaluated adjacent recombination source terms")
    p.add_argument("--adjacent-coupling-source-levels", help="Comma-separated source levels for selected-* coupling allocation modes")
    p.add_argument("--include-charge-exchange", action="store_true", help="Evaluate charge-exchange coupling coefficients when present")
    p.add_argument("--type57-energy-convention", default="compare", choices=["ucalc-eth", "abs-rlev4", "threshold-only", "compare"], help="Select the type-57 calt57 convention used for primary python_* audit columns; all modes remain diagnostic-only and are not assembled")
    p.add_argument("--triplet-source-mode", default="none", choices=["none", "type74-direct-diagnostic"], help="Optional diagnostic source injection into the He-like triplet upper levels. Off by default; type74-direct-diagnostic injects evaluated type-74 direct triplet source rates into a before/after solve without changing the baseline matrix outputs.")
    p.add_argument("--triplet-source-scale", default="1", help="Scale factor(s) for --triplet-source-mode type74-direct-diagnostic. Accepts one value or a comma-separated list, e.g. '1,1e2,1e4,1e6,1e8,1e10'.")
    p.add_argument("--type99-proxy-scale", default="0,1e-8,1e-6,1e-4,1e-2,1,1e2", help="Scale factor(s) for the nonphysical type-99 proxy source scan in the global bound-bound+type71 diagnostic block. Accepts one value or a comma-separated list.")
    p.add_argument("--radiation-field-mode", default="none", choices=["none", "flat", "blackbody", "table"], help="Diagnostic radiation context scaffold for type-53 photoionization/Milne audits. Does not evaluate physical rates yet.")
    p.add_argument("--type53-flat-proxy-scale", default="1", help="Scale factor for the nonphysical flat-field type-53 photoionization-rate proxy. Diagnostic only; not used in the solved matrix.")
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
            "adjacent_coupling_mode": args.adjacent_coupling_mode,
            "adjacent_coupling_source_mode": args.adjacent_coupling_source_mode,
            "adjacent_coupling_source_levels": args.adjacent_coupling_source_levels,
            "type57_energy_convention": args.type57_energy_convention,
            "triplet_source_mode": args.triplet_source_mode,
            "triplet_source_scale": args.triplet_source_scale,
            "type99_proxy_scale": args.type99_proxy_scale,
            "radiation_field_mode": args.radiation_field_mode,
            "type53_flat_proxy_scale": args.type53_flat_proxy_scale,
            "status": "dry_run_not_executed",
        }]
        write_csv(out / "xstar_like_element_solver_ion_blocks.csv", [])
        write_csv(out / "xstar_like_element_solver_coupling_candidates.csv", [])
        write_csv(out / "xstar_like_element_solver_adjacent_coupling_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_ucalc_adjacent_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_superlevel_cascade_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_superlevel_branching_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_superlevel_source_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_type74_linkage_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_type74_triplet_source_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_triplet_source_injection_comparison.csv", [])
        write_csv(out / "xstar_like_element_solver_triplet_source_scale_scan.csv", [])
        write_csv(out / "xstar_like_element_solver_populations.csv", [])
        write_csv(out / "xstar_like_element_solver_lines.csv", [])
        write_csv(out / "xstar_like_element_solver_transitions.csv", [])
        write_csv(out / "xstar_like_element_solver_global_bound_bound_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_global_superlevel_source_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_global_bound_bound_solve_comparison.csv", [])
        write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv", [])
        write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_type99_proxy_solve_comparison.csv", [])
        write_csv(out / "xstar_like_element_solver_type99_proxy_scale_scan.csv", [])
        write_csv(out / "xstar_like_element_solver_radiation_context.csv", [])
        write_csv(out / "xstar_like_element_solver_type53_rate_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_type53_flat_proxy_rate_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_global_type53_flat_proxy_matrix_terms.csv", [])
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
        adjacent_coupling_mode=args.adjacent_coupling_mode,
        adjacent_coupling_source_mode=args.adjacent_coupling_source_mode,
        adjacent_coupling_selected_levels=parse_stage_list(args.adjacent_coupling_source_levels),
        include_charge_exchange=args.include_charge_exchange,
        type57_energy_convention=args.type57_energy_convention,
        triplet_source_mode=args.triplet_source_mode,
        triplet_source_scale=args.triplet_source_scale,
        type99_proxy_scale=args.type99_proxy_scale,
        radiation_field_mode=args.radiation_field_mode,
        type53_flat_proxy_scale=args.type53_flat_proxy_scale,
    )
    write_element_solver_outputs(result, out)
    if args.print_summary:
        summ = result["summary"]
        trip = summ.get("he_like_triplet", {})
        print("XSTAR-like element solver")
        print("-------------------------")
        print(f"element={summ.get('element')} stages={summ.get('stages')} coupling={summ.get('adjacent_coupling_status')} assembled={summ.get('n_adjacent_coupling_assembled')}")
        print(f"triplet f/i/r={trip.get('f_fraction'):.6g}/{trip.get('i_fraction'):.6g}/{trip.get('r_fraction'):.6g} R={trip.get('R')} G={trip.get('G')}")
        print(f"wrote: {out / 'xstar_like_element_solver_summary.md'}")


if __name__ == "__main__":
    main()
