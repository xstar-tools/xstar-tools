"""CLI for the full positive-abundance fixed-state ``calc_hmc_all`` loop."""

from __future__ import annotations

import argparse

from .source_port import (
    compare_calc_hmc_all_pre_continuum_probe,
    load_all_element_fixed_state_plan,
    load_atomic_database_state,
    load_calc_hmc_all_probe_critf,
    load_xstar_runtime_context_reference,
    run_all_element_fixed_state,
    write_all_element_fixed_state_products,
    write_calc_hmc_all_pre_continuum_parity_products,
    write_fixed_state_calc_hmc_all_products,
)
from .source_port_element_cli import _load_escape_npz, _select_live_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the complete positive-abundance element loop of fixed-state "
            "calc_hmc_all. The accepted oxygen call-73 result is mandatory. "
            "Continuum leaves and dsec remain deferred."
        )
    )
    parser.add_argument("--atdb", required=True)
    parser.add_argument("--pointer-cache")
    parser.add_argument("--temperature-k", type=float, required=True)
    parser.add_argument("--hydrogen-density-cm3", type=float, required=True)
    parser.add_argument("--electron-fraction-xee", type=float, required=True)
    parser.add_argument("--covering-fraction", type=float, default=1.0)
    parser.add_argument("--turbulent-velocity-km-s", type=float, default=0.0)
    parser.add_argument("--pressure", type=float, default=0.0)
    parser.add_argument("--lcdd", type=int, default=1)
    parser.add_argument("--lfast", type=int, default=2)
    parser.add_argument("--critf", type=float)
    parser.add_argument("--live-rate-grid-probe-csv")
    parser.add_argument("--live-rate-grid-state", default="last")
    parser.add_argument("--escape-npz")
    parser.add_argument("--assume-optically-thin", action="store_true")
    parser.add_argument("--xstar-population-probe-csv")
    parser.add_argument("--xstar-population-solve-call-id")
    parser.add_argument(
        "--population-probe-runtime-policy",
        choices=("use", "check", "ignore"),
        default="check",
    )
    parser.add_argument("--runtime-reference-element-z", type=int, default=8)
    parser.add_argument("--xstar-calc-hmc-probe-dir", required=True)
    parser.add_argument("--xstar-calc-hmc-call-id", type=int, default=73)
    parser.add_argument(
        "--oxygen-call73-regression-dir",
        required=True,
        help=(
            "Accepted v0.4.34 oxygen output directory or exact parity-summary "
            "JSON. The all-element run is refused unless this gate passes."
        ),
    )
    parser.add_argument(
        "--initial-population-policy",
        choices=("use-available", "require-all", "ignore"),
        default="use-available",
        help=(
            "Use same-call xileve seeds where present, require seeds for every "
            "positive-abundance element, or ignore all captured seeds."
        ),
    )
    parser.add_argument("--abundance-floor", type=float, default=1.0e-24)
    parser.add_argument("--xstar-calc-hmc-parity-rtol", type=float, default=5.0e-3)
    parser.add_argument("--xstar-calc-hmc-parity-atol", type=float, default=1.0e-12)
    parser.add_argument(
        "--xstar-calc-hmc-active-population-threshold",
        type=float,
        default=1.0e-12,
    )
    parser.add_argument(
        "--xstar-calc-hmc-matrix-closure-active-row-scale-threshold",
        type=float,
        default=1.0e-12,
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def _resolve_runtime(args: argparse.Namespace) -> tuple[float, float, float, float, str]:
    temperature_k = float(args.temperature_k)
    xpx = float(args.hydrogen_density_cm3)
    xee = float(args.electron_fraction_xee)
    cfrac = float(args.covering_fraction)
    source = "command_line"
    if not args.xstar_population_probe_csv or args.population_probe_runtime_policy == "ignore":
        return temperature_k, xpx, xee, cfrac, source

    ref = load_xstar_runtime_context_reference(
        args.xstar_population_probe_csv,
        element_z=args.runtime_reference_element_z,
        solve_call_id=args.xstar_population_solve_call_id,
    )
    if args.population_probe_runtime_policy == "use":
        return (
            ref.temperature_k,
            ref.hydrogen_density_cm3,
            ref.electron_fraction_xee,
            ref.covering_fraction,
            "xstar_population_probe",
        )
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
    return temperature_k, xpx, xee, cfrac, "command_line_checked_against_xstar_population_probe"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    temperature_k, xpx, xee, cfrac, runtime_source = _resolve_runtime(args)

    plan = load_all_element_fixed_state_plan(
        args.xstar_calc_hmc_probe_dir,
        oxygen_regression_dir=args.oxygen_call73_regression_dir,
        call_id=args.xstar_calc_hmc_call_id,
        abundance_floor=args.abundance_floor,
    )
    if args.critf is None:
        critf_ref = load_calc_hmc_all_probe_critf(
            args.xstar_calc_hmc_probe_dir,
            element_z=8,
            call_id=plan.call_id,
        )
        critf = float(critf_ref.critf)
        critf_source = "xstar_calc_hmc_probe"
    else:
        critf = float(args.critf)
        critf_source = "command_line"

    radiation = _select_live_state(args.live_rate_grid_probe_csv, args.live_rate_grid_state)
    escape = _load_escape_npz(args.escape_npz, args.assume_optically_thin)

    built = load_atomic_database_state(
        args.atdb,
        pointer_cache=args.pointer_cache,
        use_pointer_cache=True,
    )
    try:
        run = run_all_element_fixed_state(
            built.master,
            built.derived,
            plan=plan,
            temperature_k=temperature_k,
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=xee,
            radiation=radiation,
            escape=escape,
            covering_fraction=cfrac,
            turbulent_velocity_km_s=args.turbulent_velocity_km_s,
            pressure=args.pressure,
            lcdd=args.lcdd,
            lfast=args.lfast,
            critf=critf,
            initial_population_policy=args.initial_population_policy,
        )
        result = run.result
        result.diagnostics.update(
            {
                "runtime_context_source": runtime_source,
                "effective_critf": critf,
                "critf_source": critf_source,
            }
        )
        paths = write_fixed_state_calc_hmc_all_products(
            result, args.out_dir, port_version="v0.4.35"
        )
        paths.update(
            {
                f"all_element_scope_{key}": str(value)
                for key, value in write_all_element_fixed_state_products(
                    run, args.out_dir
                ).items()
            }
        )
        parity = compare_calc_hmc_all_pre_continuum_probe(
            result,
            args.xstar_calc_hmc_probe_dir,
            call_id=plan.call_id,
            rtol=args.xstar_calc_hmc_parity_rtol,
            atol=args.xstar_calc_hmc_parity_atol,
            active_population_threshold=args.xstar_calc_hmc_active_population_threshold,
            matrix_closure_active_row_scale_threshold=(
                args.xstar_calc_hmc_matrix_closure_active_row_scale_threshold
            ),
        )
        paths.update(
            {
                f"pre_continuum_parity_{key}": str(value)
                for key, value in write_calc_hmc_all_pre_continuum_parity_products(
                    parity, args.out_dir, port_version="v0.4.35"
                ).items()
            }
        )
    finally:
        built.master.close()

    if args.print_summary:
        print("XSTAR full abundant-element fixed-state calc_hmc_all")
        print("-------------------------------------------------")
        print("port_version=v0.4.35")
        print(f"runtime_context_source={runtime_source}")
        print(f"calc_hmc_all_call_id={plan.call_id}")
        print(f"oxygen_call73_regression_ready={plan.oxygen_regression.ready}")
        print(f"abundant_element_z={','.join(map(str, plan.abundant_element_z))}")
        print(f"n_abundant_elements={len(plan.elements)}")
        print(f"initial_population_policy={args.initial_population_policy}")
        print(f"initial_population_elements={','.join(map(str, plan.initial_population_elements)) or 'none'}")
        print(f"missing_initial_population_elements={','.join(map(str, plan.missing_initial_population_elements)) or 'none'}")
        print(f"pre_matrix_ready={result.pre_matrix_ready}")
        print(f"element_loop_ready={result.element_loop_ready}")
        print(f"charge_closure_scope_complete={result.charge_closure_scope_complete}")
        print(f"all_element_execution_ready={run.all_element_execution_ready}")
        print(f"all_element_detailed_parity_probe_ready={run.all_element_detailed_parity_probe_ready}")
        print(f"continuum_complete={result.continuum.complete}")
        print(f"complete_fixed_state_ready={result.complete_fixed_state_ready}")
        print(f"xstar_pre_continuum_summary_status={parity.pre_continuum_summary_status}")
        print(f"xstar_pre_continuum_summary_ready={parity.pre_continuum_summary_ready}")
        print(f"xstar_global_array_parity_ready={parity.global_arrays_ready}")
        print(f"xstar_oxygen_pre_continuum_acceptance_ready={parity.oxygen_pre_continuum_acceptance_ready}")
        print(f"xstar_pre_continuum_parity_ready={parity.parity_ready}")
        for key, value in paths.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
