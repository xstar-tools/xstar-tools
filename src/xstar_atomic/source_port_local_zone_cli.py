"""CLI for the fixed-state ``calc_hmc_all`` Milestone-4 core."""

from __future__ import annotations

import argparse
from pathlib import Path

from .source_port import (
    FixedStateElementRequest,
    calc_hmc_all,
    load_atomic_database_state,
    load_xstar_runtime_context_reference,
    write_fixed_state_calc_hmc_all_products,
    compare_calc_hmc_all_pre_continuum_probe,
    load_calc_hmc_all_probe_critf,
    load_calc_hmc_all_probe_element_reference,
    write_calc_hmc_all_pre_continuum_parity_products,
)
from .source_port_element_cli import _load_escape_npz, _select_live_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the fixed-temperature/fixed-electron-fraction calc_hmc_all "
            "element-loop core. Continuum leaves and dsec remain explicit "
            "Milestone-4 work."
        )
    )
    parser.add_argument("--atdb", required=True)
    parser.add_argument("--pointer-cache")
    parser.add_argument("--element-z", type=int, default=8)
    parser.add_argument("--min-ion-stage", type=int, default=3)
    parser.add_argument("--max-ion-stage", type=int, default=8)
    parser.add_argument(
        "--abundance", type=float, default=None,
        help=(
            "Element abundance. If omitted and an XSTAR calc_hmc_all element "
            "probe is supplied, use its captured abundance; otherwise use 1.0."
        ),
    )
    parser.add_argument("--temperature-k", type=float, required=True)
    parser.add_argument("--hydrogen-density-cm3", type=float, required=True)
    parser.add_argument("--electron-fraction-xee", type=float, required=True)
    parser.add_argument("--covering-fraction", type=float, default=1.0)
    parser.add_argument("--turbulent-velocity-km-s", type=float, default=0.0)
    parser.add_argument("--pressure", type=float, default=0.0)
    parser.add_argument("--lcdd", type=int, default=1)
    parser.add_argument("--lfast", type=int, default=2)
    parser.add_argument(
        "--critf", type=float, default=None,
        help=(
            "Ion-fraction selection threshold. If omitted and an XSTAR "
            "calc_hmc_all probe is supplied, use its captured critf; otherwise "
            "use the source-aligned package default 1e-7."
        ),
    )
    parser.add_argument(
        "--ion-stage-selection", choices=("source", "explicit"), default="source",
        help="Use calc_ion_rates/istruc-derived mml/mmu or the explicit stage range.",
    )
    parser.add_argument("--live-rate-grid-probe-csv")
    parser.add_argument("--live-rate-grid-state", default="last")
    parser.add_argument("--escape-npz")
    parser.add_argument("--assume-optically-thin", action="store_true")
    parser.add_argument("--xstar-population-probe-csv")
    parser.add_argument("--xstar-population-solve-call-id")
    parser.add_argument(
        "--population-probe-runtime-policy",
        choices=("use", "check", "ignore"),
        default="use",
    )
    parser.add_argument("--xstar-calc-hmc-probe-dir")
    parser.add_argument("--xstar-calc-hmc-call-id", type=int)
    parser.add_argument("--xstar-calc-hmc-parity-rtol", type=float, default=5.0e-3)
    parser.add_argument("--xstar-calc-hmc-parity-atol", type=float, default=1.0e-12)
    parser.add_argument(
        "--xstar-calc-hmc-matrix-closure-active-row-scale-threshold",
        type=float,
        default=1.0e-12,
        help=(
            "Row-scale threshold used by the diagnostic A_python @ x_XSTAR "
            "matrix-closure acceptance gate."
        ),
    )
    parser.add_argument(
        "--xstar-calc-hmc-active-population-threshold",
        type=float,
        default=1.0e-12,
        help=(
            "Population threshold used by the milestone global-level gate. "
            "Strict comparisons for all mapped levels are still written."
        ),
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    temperature_k = float(args.temperature_k)
    xpx = float(args.hydrogen_density_cm3)
    xee = float(args.electron_fraction_xee)
    cfrac = float(args.covering_fraction)
    runtime_source = "command_line"

    if args.xstar_population_probe_csv:
        ref = load_xstar_runtime_context_reference(
            args.xstar_population_probe_csv,
            element_z=args.element_z,
            solve_call_id=args.xstar_population_solve_call_id,
        )
        policy = args.population_probe_runtime_policy
        if policy == "use":
            temperature_k = ref.temperature_k
            xpx = ref.hydrogen_density_cm3
            xee = ref.electron_fraction_xee
            cfrac = ref.covering_fraction
            runtime_source = "xstar_population_probe"
        elif policy == "check":
            values = (
                ("temperature_k", temperature_k, ref.temperature_k),
                ("hydrogen_density_cm3", xpx, ref.hydrogen_density_cm3),
                ("electron_fraction_xee", xee, ref.electron_fraction_xee),
                ("covering_fraction", cfrac, ref.covering_fraction),
            )
            mismatches = [
                f"{name}: requested={got:.16g}, probe={expected:.16g}"
                for name, got, expected in values
                if abs(got - expected) > max(1.0e-12, 1.0e-10 * abs(expected))
            ]
            if mismatches:
                raise ValueError("runtime state differs from population probe: " + "; ".join(mismatches))
            runtime_source = "command_line_checked_against_xstar_population_probe"

    requested_critf = args.critf
    effective_hmc_call_id = args.xstar_calc_hmc_call_id
    if requested_critf is not None:
        effective_critf = float(requested_critf)
        critf_source = "command_line"
    elif args.xstar_calc_hmc_probe_dir:
        critf_reference = load_calc_hmc_all_probe_critf(
            args.xstar_calc_hmc_probe_dir,
            element_z=args.element_z,
            call_id=effective_hmc_call_id,
        )
        effective_critf = float(critf_reference.critf)
        effective_hmc_call_id = int(critf_reference.call_id)
        critf_source = "xstar_calc_hmc_probe"
    else:
        effective_critf = 1.0e-7
        critf_source = "package_default"

    requested_abundance = args.abundance
    if requested_abundance is not None:
        effective_abundance = float(requested_abundance)
        abundance_source = "command_line"
    elif args.xstar_calc_hmc_probe_dir:
        abundance_reference = load_calc_hmc_all_probe_element_reference(
            args.xstar_calc_hmc_probe_dir,
            element_z=args.element_z,
            call_id=effective_hmc_call_id,
        )
        effective_abundance = float(abundance_reference.abundance)
        effective_hmc_call_id = int(abundance_reference.call_id)
        abundance_source = "xstar_calc_hmc_element_probe"
    else:
        effective_abundance = 1.0
        abundance_source = "package_default"

    radiation = _select_live_state(args.live_rate_grid_probe_csv, args.live_rate_grid_state)
    escape = _load_escape_npz(args.escape_npz, args.assume_optically_thin)
    request = FixedStateElementRequest(
        element_z=args.element_z,
        min_ion_stage=args.min_ion_stage,
        max_ion_stage=args.max_ion_stage,
        abundance=effective_abundance,
        radiation=radiation,
        escape=escape,
        covering_fraction=cfrac,
        turbulent_velocity_km_s=args.turbulent_velocity_km_s,
        lfast=args.lfast,
        critf=effective_critf,
        use_source_ion_limits=args.ion_stage_selection == "source",
        strict_context=True,
    )

    built = load_atomic_database_state(
        args.atdb,
        pointer_cache=args.pointer_cache,
        use_pointer_cache=True,
    )
    try:
        result = calc_hmc_all(
            built.master,
            built.derived,
            elements=(request,),
            temperature_k=temperature_k,
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=xee,
            pressure=args.pressure,
            lcdd=args.lcdd,
        )
        result.diagnostics["runtime_context_source"] = runtime_source
        result.diagnostics["requested_critf"] = requested_critf
        result.diagnostics["effective_critf"] = effective_critf
        result.diagnostics["critf_source"] = critf_source
        result.diagnostics["requested_abundance"] = requested_abundance
        result.diagnostics["effective_abundance"] = effective_abundance
        result.diagnostics["abundance_source"] = abundance_source
        paths = write_fixed_state_calc_hmc_all_products(result, args.out_dir)
        parity = None
        if args.xstar_calc_hmc_probe_dir:
            parity = compare_calc_hmc_all_pre_continuum_probe(
                result,
                args.xstar_calc_hmc_probe_dir,
                call_id=effective_hmc_call_id,
                rtol=args.xstar_calc_hmc_parity_rtol,
                atol=args.xstar_calc_hmc_parity_atol,
                active_population_threshold=args.xstar_calc_hmc_active_population_threshold,
                matrix_closure_active_row_scale_threshold=(
                    args.xstar_calc_hmc_matrix_closure_active_row_scale_threshold
                ),
            )
            paths.update({
                f"pre_continuum_parity_{key}": value
                for key, value in write_calc_hmc_all_pre_continuum_parity_products(
                    parity, args.out_dir
                ).items()
            })
    finally:
        built.master.close()

    if args.print_summary:
        print("XSTAR fixed-state calc_hmc_all core")
        print("-----------------------------------")
        print("port_version=v0.4.32")
        print(f"runtime_context_source={runtime_source}")
        print(f"requested_critf={requested_critf}")
        print(f"effective_critf={effective_critf}")
        print(f"critf_source={critf_source}")
        print(f"requested_abundance={requested_abundance}")
        print(f"effective_abundance={effective_abundance}")
        print(f"abundance_source={abundance_source}")
        print(f"temperature_k={result.temperature_k}")
        print(f"hydrogen_density_cm3={result.hydrogen_density_cm3}")
        print(f"electron_fraction_xee={result.electron_fraction_xee}")
        print(f"n_elements={len(result.element_results)}")
        for item in result.element_results:
            print(f"element_{item.request.element_z}_selected_ion_stage_range={item.selected_min_ion_stage}..{item.selected_max_ion_stage}")
        print(f"pre_matrix_ready={result.pre_matrix_ready}")
        print(f"element_loop_ready={result.element_loop_ready}")
        print(f"charge_closure_scope_complete={result.charge_closure_scope_complete}")
        print(f"continuum_complete={result.continuum.complete}")
        print(f"complete_fixed_state_ready={result.complete_fixed_state_ready}")
        print(f"httot={result.httot}")
        print(f"cltot={result.cltot}")
        print(f"hmctot={result.hmctot}")
        print(f"elcter={result.elcter}")
        if parity is not None:
            print(f"xstar_pre_matrix_parity_ready={parity.pre_matrix_ready}")
            print(f"xstar_pre_continuum_state_parity_ready={parity.pre_continuum_state_ready}")
            print(f"xstar_pre_continuum_summary_parity_status={parity.pre_continuum_summary_status}")
            print(f"xstar_pre_continuum_summary_parity_ready={parity.pre_continuum_summary_ready}")
            print(f"xstar_element_array_parity_status={parity.element_array_status}")
            print(f"xstar_element_array_parity_ready={parity.element_array_ready}")
            print(f"xstar_global_ion_parity_ready={parity.global_ion_ready}")
            print(f"xstar_global_level_primary_parity_ready={parity.global_level_primary_ready}")
            print(f"xstar_global_level_active_parity_ready={parity.global_level_active_ready}")
            print(f"xstar_global_level_derived_parity_ready={parity.global_level_derived_ready}")
            print(f"xstar_global_level_strict_parity_ready={parity.global_level_ready}")
            print(f"xstar_global_array_parity_ready={parity.global_arrays_ready}")
            print(f"xstar_vector_matrix_closure_status={parity.matrix_closure_status}")
            print(f"xstar_vector_matrix_closure_ready={parity.matrix_closure_ready}")
            print(f"xstar_element_thermal_diagnostic_ready={parity.element_thermal_diagnostic_ready}")
            print(f"xstar_same_call_matrix_status={parity.same_call_matrix_status}")
            print(f"xstar_same_call_matrix_ready={parity.same_call_matrix_ready}")
            print(f"xstar_same_call_matrix_topology_ready={parity.same_call_matrix_topology_ready}")
            print(f"xstar_same_call_matrix_coefficient_ready={parity.same_call_matrix_coefficient_ready}")
            print(f"xstar_same_call_matrix_active_closure_ready={parity.same_call_matrix_active_closure_ready}")
            print(f"xstar_thermal_family_parity_status={parity.thermal_family_status}")
            print(f"xstar_thermal_family_parity_ready={parity.thermal_family_ready}")
            print(f"xstar_final_solver_snapshot_status={parity.final_solver_snapshot_status}")
            print(f"xstar_final_solver_snapshot_ready={parity.final_solver_snapshot_ready}")
            print(f"xstar_final_solver_same_iteration_ready={parity.final_solver_same_iteration_ready}")
            print(f"xstar_final_solver_topology_ready={parity.final_solver_topology_ready}")
            print(f"xstar_final_solver_active_population_ready={parity.final_solver_active_population_ready}")
            print(f"xstar_final_solver_outer_start_ready={parity.final_solver_outer_start_ready}")
            print(f"xstar_final_solver_source_xtot_ready={parity.final_solver_source_xtot_ready}")
            print(f"xstar_rate7_cj2_status={parity.rate7_cj2_status}")
            print(f"xstar_rate7_cj2_ready={parity.rate7_cj2_ready}")
            print(f"xstar_type53_rate7_cj2_ready={parity.type53_rate7_cj2_ready}")
            print(f"xstar_oxygen_reassessment_status={parity.oxygen_reassessment_status}")
            print(f"xstar_oxygen_reassessment_ready={parity.oxygen_reassessment_ready}")
            print(f"xstar_oxygen_pre_continuum_acceptance_ready={parity.oxygen_pre_continuum_acceptance_ready}")
            print(f"xstar_acceptance_gate_ready={parity.acceptance_gate_ready}")
            print(f"xstar_strict_parity_ready={parity.strict_parity_ready}")
            print(f"xstar_pre_continuum_parity_ready={parity.parity_ready}")
            print(f"xstar_pre_continuum_parity_outside_tolerance={parity.n_outside_tolerance}")
            print(f"xstar_pre_continuum_parity_blocking_outside_tolerance={parity.n_blocking_outside_tolerance}")
        for key, value in paths.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
