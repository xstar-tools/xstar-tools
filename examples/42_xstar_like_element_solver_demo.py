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
    p.add_argument("--radiation-field-mode", default="none", choices=["none", "flat", "blackbody", "table", "powerlaw", "xstar-powerlaw"], help="Diagnostic XSTAR-style radiation/bremsa context for type-53/type-74 audits. The bremsa array has XSTAR units but is still a diagnostic continuum unless supplied by a future physical transfer context.")
    p.add_argument("--radiation-bremsa-scale", default="1", help="Absolute scale for the diagnostic bremsa array in XSTAR units erg s^-1 cm^-2 erg^-1. This replaces ad hoc post-hoc phint53 scaling for source-code-aligned radiation tests.")
    p.add_argument("--radiation-energy-min-eV", type=float, default=None, help="Minimum energy for the diagnostic epi/bremsa grid. Default 1 eV.")
    p.add_argument("--radiation-energy-max-eV", type=float, default=None, help="Maximum energy for the diagnostic epi/bremsa grid. Default 1e5 eV.")
    p.add_argument("--radiation-n-energy-grid", type=int, default=256, help="Number of points in the diagnostic log-spaced epi/bremsa grid.")
    p.add_argument("--radiation-powerlaw-index", type=float, default=1.0, help="Power-law index for --radiation-field-mode powerlaw/xstar-powerlaw, bremsa(E)=scale*(E/1keV)^(-index).")
    p.add_argument("--type53-flat-proxy-scale", default="1", help="Scale factor for the nonphysical flat-field type-53 photoionization-rate proxy. Diagnostic only; retained for comparison with the phint53 kernel path.")
    p.add_argument("--type53-phint53-scale", default="1", help="Scale factor(s) for the type-53 phint53 photoionization-kernel diagnostic and v0.3.54 scale scan. Accepts one value or a comma-separated list, e.g. 1,1e5,1e10,1e15,1e18,1e20. The kernel is ported, but the radiation field is still placeholder unless a future physical continuum is supplied.")
    p.add_argument("--inverse-recombination-mode", default="none", choices=["none", "type53-milne-diagnostic", "type74-direct-diagnostic", "type53-type74", "xstar-ucalc"], help="Inverse-recombination mode. Legacy type53/type74 modes retain diagnostic proxy rates. xstar-ucalc assembles source-code-aligned type-53 phint53 Milne ans2 and type-74 calt74 alpha*gglo/ggup rates into the full-global matrix as an experimental direct XSTAR-code path.")
    p.add_argument("--type53-milne-scale", default="1", help="Scale factor(s) for the diagnostic type-53 Milne inverse-recombination scaffold. Accepts one value or a comma-separated list, e.g. 1,1e10,1e20,1e30. The first value is used for the primary matrix; all values are used in the inverse-recombination scale scan.")
    p.add_argument("--type74-inverse-scale", default="1", help="Scale factor(s) for the diagnostic type-74 DR-delta inverse-recombination scaffold. Accepts one value or a comma-separated list, e.g. 1,1e5,1e10,1e15. The first value is used for the primary matrix; all values are used in the inverse-recombination scale scan.")
    p.add_argument("--type53-milne-refined-scale", default="1e9,3e9,1e10,3e10,1e11", help="Refined diagnostic type-53 Milne scale grid around the v0.3.58 good C V region. Used only for xstar_like_element_solver_inverse_recombination_refined_scale_scan.csv.")
    p.add_argument("--type74-inverse-refined-scale", default="1e8,3e8,1e9,3e9,1e10,3e10,1e11,3e11,1e12", help="Refined diagnostic type-74 inverse scale grid around the v0.3.58 good C V region. Used only for xstar_like_element_solver_inverse_recombination_refined_scale_scan.csv.")
    p.add_argument("--triplet-coupling-treatment", default="normal", choices=["normal", "audit-only", "suppress-3p-to-3s-radiative"], help="v0.3.63 diagnostic treatment for suspicious type-50 1s2p 3P_J -> 1s2s 3S1 radiative drains. normal/audit-only leave the primary solve unchanged; suppress-3p-to-3s-radiative removes only those matrix terms from the primary full-global solve and always writes a normal-vs-suppressed comparison CSV.")
    p.add_argument("--type50-bound-bound-treatment", default="raw-A", choices=["raw-A", "xstar-escape", "xstar-escape-photoexcitation"], help="v0.3.67 diagnostic treatment for type-50 bound-bound population rates. raw-A preserves v0.3.66. xstar-escape multiplies downward A-values by a proxy ptmp1+ptmp2 escape factor. xstar-escape-photoexcitation also adds a lower->upper pumping proxy. Diagnostic until real ucalc tau/pescl/bremsa/flinabs context is ported.")
    p.add_argument("--type50-escape-factor", default="1", help="Proxy total escape factor ptmp1+ptmp2 used by --type50-bound-bound-treatment xstar-escape modes. Clipped to [0,1]. Default 1 preserves raw-A when the treatment is raw-A.")
    p.add_argument("--type50-photoexcitation-scale", default="0", help="Proxy lower->upper pumping rate as a multiple of raw A for --type50-bound-bound-treatment xstar-escape-photoexcitation. Default 0.")
    p.add_argument("--type50-escape-factor-scan", default="0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.75,1", help="Comma-separated proxy escape factors for xstar_like_element_solver_type50_escape_factor_scan.csv. The scan always uses the diagnostic xstar-escape type-50 treatment and holds other primary matrix terms fixed.")
    p.add_argument("--full-global-linear-solver", default="xstar-lucy", choices=["solve", "dense", "lstsq", "svd", "xstar-lucy"], help="Linear solver for the diagnostic full-global normalized proxy-topology solve. Use xstar-lucy to follow the XSTAR msolvelucy structure: condensed superlevel matrix, number-conservation row, LU solve, and iterative-improvement diagnostics.")
    p.add_argument("--full-global-rank-deficient-action", default="svd", choices=["solve", "lstsq", "svd", "error"], help="Fallback/action for the diagnostic full-global normalized solve when the proxy-topology matrix is rank deficient.")
    p.add_argument("--full-global-negative-population-action", default="keep", choices=["keep", "clip", "error"], help="How to handle negative populations in the diagnostic full-global normalized solve.")
    p.add_argument("--full-global-topology", default="explicit-current", choices=["explicit-current", "xstar-continuum-alias", "xstar-continuum-alias-superlevels"], help="v0.3.76 experimental XSTAR element-matrix topology membership for the xstar-lucy full-global solve. explicit-current preserves previous behavior; xstar-continuum-alias aliases continuum rows to the parent ground group; xstar-continuum-alias-superlevels also groups levels 2..nlev-1 into one excited nsup group per ion.")
    p.add_argument("--ion-fraction-closure", default="none", choices=["none", "xstar-istruc"], help="v0.3.79 experimental XSTAR calc_ion_rates/istruc-style adjacent-stage ion-fraction closure. xstar-istruc derives two-stage fractions from summed inter-stage matrix rates and applies them during the xstar-lucy population iteration.")
    p.add_argument("--no-full-global-prune-null-rate-levels", action="store_true", help="Disable pruning of null-rate global_index rows before the diagnostic full-global normalized solve.")
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
            "radiation_bremsa_scale": args.radiation_bremsa_scale,
            "radiation_energy_min_eV": args.radiation_energy_min_eV,
            "radiation_energy_max_eV": args.radiation_energy_max_eV,
            "radiation_n_energy_grid": args.radiation_n_energy_grid,
            "radiation_powerlaw_index": args.radiation_powerlaw_index,
            "type53_flat_proxy_scale": args.type53_flat_proxy_scale,
            "type53_phint53_scale": args.type53_phint53_scale,
            "inverse_recombination_mode": args.inverse_recombination_mode,
            "type53_milne_scale": args.type53_milne_scale,
            "type74_inverse_scale": args.type74_inverse_scale,
            "type53_milne_refined_scale": args.type53_milne_refined_scale,
            "type74_inverse_refined_scale": args.type74_inverse_refined_scale,
            "triplet_coupling_treatment": args.triplet_coupling_treatment,
            "type50_bound_bound_treatment": args.type50_bound_bound_treatment,
            "type50_escape_factor": args.type50_escape_factor,
            "type50_photoexcitation_scale": args.type50_photoexcitation_scale,
            "type50_escape_factor_scan": args.type50_escape_factor_scan,
            "full_global_linear_solver": args.full_global_linear_solver,
            "full_global_rank_deficient_action": args.full_global_rank_deficient_action,
            "full_global_negative_population_action": args.full_global_negative_population_action,
            "full_global_topology": args.full_global_topology,
            "ion_fraction_closure": args.ion_fraction_closure,
            "full_global_prune_null_rate_levels": not args.no_full_global_prune_null_rate_levels,
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
        write_csv(out / "xstar_like_element_solver_xstar_matrix_topology_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_type50_ucalc_rate_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_type50_escape_factor_scan.csv", [])
        write_csv(out / "xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_global_superlevel_source_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_global_bound_bound_solve_comparison.csv", [])
        write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv", [])
        write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_type99_proxy_solve_comparison.csv", [])
        write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_type99_type53_proxy_solve_comparison.csv", [])
        write_csv(out / "xstar_like_element_solver_type99_proxy_scale_scan.csv", [])
        write_csv(out / "xstar_like_element_solver_radiation_context.csv", [])
        write_csv(out / "xstar_like_element_solver_bremsa_context.csv", [])
        write_csv(out / "xstar_like_element_solver_type53_rate_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_type53_flat_proxy_rate_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_global_type53_flat_proxy_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_type53_phint53_rate_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_global_type53_phint53_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_type53_milne_inverse_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_global_type53_milne_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_type74_inverse_recombination_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_global_type74_inverse_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_type74_calt74_rate_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_global_type74_calt74_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_type53_type74_ucalc_closure_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_phint53_milne_integral_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_inverse_recombination_scale_scan.csv", [])
        write_csv(out / "xstar_like_element_solver_inverse_recombination_refined_scale_scan.csv", [])
        write_csv(out / "xstar_like_element_solver_calc_emis_triplet_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_calc_emis_context_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_triplet_coupling_suppression_comparison.csv", [])
        write_csv(out / "xstar_like_element_solver_radiation_normalization_audit.csv", [])
        write_csv(out / "xstar_like_element_solver_type53_phint53_scale_scan.csv", [])
        write_csv(out / "xstar_like_element_solver_full_global_matrix_terms.csv", [])
        write_csv(out / "xstar_like_element_solver_full_global_normalized_solve_comparison.csv", [])
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
        radiation_bremsa_scale=args.radiation_bremsa_scale,
        radiation_energy_min_eV=args.radiation_energy_min_eV,
        radiation_energy_max_eV=args.radiation_energy_max_eV,
        radiation_n_energy_grid=args.radiation_n_energy_grid,
        radiation_powerlaw_index=args.radiation_powerlaw_index,
        type53_flat_proxy_scale=args.type53_flat_proxy_scale,
        type53_phint53_scale=args.type53_phint53_scale,
        inverse_recombination_mode=args.inverse_recombination_mode,
        type53_milne_scale=args.type53_milne_scale,
        type74_inverse_scale=args.type74_inverse_scale,
        type53_milne_refined_scale=args.type53_milne_refined_scale,
        type74_inverse_refined_scale=args.type74_inverse_refined_scale,
        triplet_coupling_treatment=args.triplet_coupling_treatment,
        type50_bound_bound_treatment=args.type50_bound_bound_treatment,
        type50_escape_factor=args.type50_escape_factor,
        type50_photoexcitation_scale=args.type50_photoexcitation_scale,
        type50_escape_factor_scan=args.type50_escape_factor_scan,
        full_global_linear_solver=args.full_global_linear_solver,
        full_global_rank_deficient_action=args.full_global_rank_deficient_action,
        full_global_negative_population_action=args.full_global_negative_population_action,
        full_global_topology=args.full_global_topology,
        ion_fraction_closure=args.ion_fraction_closure,
        full_global_prune_null_rate_levels=not args.no_full_global_prune_null_rate_levels,
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
