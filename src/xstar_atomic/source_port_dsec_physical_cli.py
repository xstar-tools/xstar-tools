"""Call-correlated physical runner for the translated XSTAR ``dsec`` subsystem."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np

from .source_port import (
    CalcHMCAllDsecEvaluator,
    PhysicalDsecCalcKwargsFactory,
    PhysicalDsecContinuumTemplate,
    build_dsec_acceptance,
    build_physical_dsec_runtime_state,
    clone_physical_dsec_runtime_state,
    compare_complete_fixed_state_calc_hmc_all,
    compare_dsec_thermal_decomposition,
    compare_dsec_trajectory,
    dsec,
    initial_state_from_xstar_trajectory,
    load_all_element_fixed_state_plan,
    load_atomic_database_state,
    load_bremem_probe_reference,
    load_calc_hmc_all_final_state_reference,
    load_compton_table,
    load_comp2_probe_reference,
    load_dsec_matching_input_state,
    load_freef_probe_reference,
    load_heatf_probe_reference,
    load_xstar_dsec_thermal_decomposition,
    load_xstar_dsec_trajectory,
    resolve_dsec_calc_hmc_all_calls,
    validate_v0444_complete_fixed_state_regression,
    write_complete_fixed_state_parity_products,
    write_dsec_acceptance_products,
    write_dsec_thermal_parity_products,
    write_dsec_trajectory_parity_products,
    write_dsec_trajectory_products,
    write_fixed_state_calc_hmc_all_products,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the translated calc_hmc_all inside dsec using the exact "
            "call-correlated XSTAR input state, compare every branch and "
            "thermal component, and optionally stop after a fast trajectory prefix."
        )
    )
    parser.add_argument("--atdb", required=True)
    parser.add_argument("--pointer-cache")

    parser.add_argument("--xstar-dsec-trajectory", required=True)
    parser.add_argument("--xstar-dsec-call-id", type=int, default=1)
    parser.add_argument(
        "--xstar-call-correlation",
        help=(
            "CSV or directory containing xstar_dsec_calc_hmc_all_call_correlation.csv; "
            "when supplied, input and post-dsec calc_hmc_all call IDs are resolved automatically"
        ),
    )
    parser.add_argument("--xstar-dsec-input-probe-dir")
    parser.add_argument("--xstar-post-dsec-probe-dir")
    parser.add_argument("--xstar-input-calc-hmc-call-id", type=int)
    parser.add_argument("--xstar-post-dsec-calc-hmc-call-id", type=int)
    parser.add_argument(
        "--xstar-dsec-thermal-decomposition",
        help=(
            "CSV or directory containing xstar_dsec_thermal_decomposition_probe.csv; "
            "defaults to the directory containing --xstar-dsec-trajectory"
        ),
    )

    # Deprecated compatibility spelling.  It may provide a probe directory,
    # but v0.4.48 never assumes that one call ID represents both input and
    # post-dsec state.
    parser.add_argument("--xstar-calc-hmc-probe-dir", help=argparse.SUPPRESS)
    parser.add_argument("--xstar-calc-hmc-call-id", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--live-rate-grid-probe-csv", help=argparse.SUPPRESS)
    parser.add_argument("--live-rate-grid-state", default="last", help=argparse.SUPPRESS)
    parser.add_argument("--escape-npz", help=argparse.SUPPRESS)
    parser.add_argument("--assume-optically-thin", action="store_true", help=argparse.SUPPRESS)

    parser.add_argument("--oxygen-call73-regression-dir", required=True)
    parser.add_argument("--abundance-floor", type=float, default=1.0e-24)
    parser.add_argument(
        "--initial-population-policy",
        choices=("use-available", "require-all", "ignore"),
        default="require-all",
    )

    parser.add_argument(
        "--dsec-runtime-policy",
        choices=("use", "check", "ignore"),
        default="use",
    )
    parser.add_argument("--initial-temperature-t4", type=float)
    parser.add_argument("--initial-electron-fraction-xee", type=float)
    parser.add_argument("--initial-hydrogen-density-cm3", type=float)
    parser.add_argument("--nlim", type=int)
    parser.add_argument("--tinf-t4", type=float)

    parser.add_argument("--covering-fraction", type=float)
    parser.add_argument("--turbulent-velocity-km-s", type=float)
    parser.add_argument("--pressure", type=float)
    parser.add_argument("--lcdd", type=int)
    parser.add_argument("--lfast", type=int, default=2)
    parser.add_argument("--critf", type=float)
    parser.add_argument("--coheat-data")
    parser.add_argument(
        "--first-continuum-workspace-policy",
        choices=("auto", "zero", "probe"),
        default="auto",
        help="auto uses the correlated input-call freef/bremem probe workspaces",
    )
    parser.add_argument("--reset-continuum-workspace", action="store_true")

    parser.add_argument("--runtime-rtol", type=float, default=5.0e-12)
    parser.add_argument("--runtime-atol", type=float, default=1.0e-30)
    parser.add_argument("--residual-rtol", type=float, default=5.0e-3)
    parser.add_argument("--thermal-residual-atol", type=float, default=1.0e-8)
    parser.add_argument("--charge-residual-atol", type=float, default=1.0e-10)
    parser.add_argument("--thermal-component-rtol", type=float, default=5.0e-3)
    parser.add_argument("--thermal-component-atol", type=float, default=1.0e-12)
    parser.add_argument("--final-rtol", type=float, default=5.0e-3)
    parser.add_argument("--final-atol", type=float, default=1.0e-12)
    parser.add_argument("--continuum-rtol", type=float, default=5.0e-12)
    parser.add_argument("--continuum-atol", type=float, default=1.0e-30)
    parser.add_argument("--v0444-regression")

    parser.add_argument(
        "--maximum-evaluations",
        type=int,
        help="fast prefix mode: stop after this many physical calc_hmc_all evaluations",
    )
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def _resolve_probe_inputs(args: argparse.Namespace) -> tuple[Path, Path, int, int, Optional[str]]:
    input_dir_value = args.xstar_dsec_input_probe_dir or args.xstar_calc_hmc_probe_dir
    if input_dir_value is None:
        raise ValueError("--xstar-dsec-input-probe-dir is required")
    input_dir = Path(input_dir_value)
    post_dir = Path(args.xstar_post_dsec_probe_dir or input_dir)

    correlation_source: Optional[str] = None
    if args.xstar_call_correlation:
        correlation = resolve_dsec_calc_hmc_all_calls(
            args.xstar_call_correlation,
            dsec_call_id=args.xstar_dsec_call_id,
        )
        input_call = correlation.input_calc_hmc_all_call_id
        post_call = correlation.post_dsec_calc_hmc_all_call_id
        correlation_source = correlation.source_path
        if args.xstar_input_calc_hmc_call_id is not None and int(
            args.xstar_input_calc_hmc_call_id
        ) != input_call:
            raise ValueError("explicit input calc_hmc_all call ID disagrees with correlation CSV")
        if args.xstar_post_dsec_calc_hmc_call_id is not None and int(
            args.xstar_post_dsec_calc_hmc_call_id
        ) != post_call:
            raise ValueError("explicit post-dsec calc_hmc_all call ID disagrees with correlation CSV")
    else:
        input_call = args.xstar_input_calc_hmc_call_id
        post_call = args.xstar_post_dsec_calc_hmc_call_id
        # A legacy single call ID is accepted only as an explicit fallback for
        # one side; never silently use it for both references.
        if input_call is None and args.xstar_calc_hmc_call_id is not None:
            input_call = args.xstar_calc_hmc_call_id
        if input_call is None or post_call is None:
            raise ValueError(
                "provide --xstar-call-correlation, or provide both "
                "--xstar-input-calc-hmc-call-id and --xstar-post-dsec-calc-hmc-call-id"
            )
    return input_dir, post_dir, int(input_call), int(post_call), correlation_source


def _check_matching_runtime(initial: Any, matching: Any, *, rtol: float, atol: float) -> None:
    checks = {
        "temperature_t4": (initial.temperature_t4, matching.temperature_t4),
        "electron_fraction_xee": (
            initial.electron_fraction_xee,
            matching.electron_fraction_xee,
        ),
        "hydrogen_density_cm3": (
            initial.hydrogen_density_cm3,
            matching.hydrogen_density_cm3,
        ),
    }
    mismatches = [
        f"{name}: dsec={left:.17g}, calc_hmc_all_input={right:.17g}"
        for name, (left, right) in checks.items()
        if not np.isclose(left, right, rtol=rtol, atol=atol)
    ]
    if mismatches:
        raise ValueError("correlated dsec/input runtime mismatch: " + "; ".join(mismatches))


def _thermal_values(result: Any) -> Mapping[str, float]:
    continuum = result.continuum
    return {
        "temperature_t4": float(result.temperature_k) / 1.0e4,
        "temperature_k": float(result.temperature_k),
        "electron_fraction_xee": float(result.electron_fraction_xee),
        "hydrogen_density_cm3": float(result.hydrogen_density_cm3),
        "httot_pre_continuum": float(result.httot_pre_continuum),
        "cltot_pre_continuum": float(result.cltot_pre_continuum),
        "httot2_pre_continuum": float(result.httot2_pre_continuum),
        "cltot2_pre_continuum": float(result.cltot2_pre_continuum),
        "htcomp": float(continuum.htcomp),
        "clcomp": float(continuum.clcomp),
        "htfreef": float(continuum.htfreef),
        "clbrems": float(continuum.clbrems),
        "httot": float(result.httot),
        "cltot": float(result.cltot),
        "httot2": float(result.httot2),
        "cltot2": float(result.cltot2),
        "hmctot": float(result.hmctot),
        "elcter": float(result.elcter),
    }


def _write_evaluation_summary(evaluations: Sequence[Any], out_dir: Path) -> Path:
    path = out_dir / "xstar_dsec_physical_evaluations.csv"
    thermal_fields = list(_thermal_values(evaluations[0].fixed_state_result)) if evaluations else []
    fields = ["evaluation_index", "complete_fixed_state_ready", *thermal_fields]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, evaluation in enumerate(evaluations, start=1):
            result = evaluation.fixed_state_result
            if result is None:
                continue
            writer.writerow(
                {
                    "evaluation_index": index,
                    "complete_fixed_state_ready": bool(result.complete_fixed_state_ready),
                    **_thermal_values(result),
                }
            )
    return path


def _write_runner_summary(
    *,
    out_dir: Path,
    args: argparse.Namespace,
    initial: Any,
    matching_input: Any,
    input_probe_dir: Path,
    post_probe_dir: Path,
    input_call_id: int,
    post_call_id: int,
    correlation_source: Optional[str],
    plan: Any,
    continuum_factory: PhysicalDsecCalcKwargsFactory,
    result: Optional[Any],
    parity: Optional[Any],
    thermal_parity: Optional[Any],
    final_parity: Optional[Any],
    acceptance: Optional[Any],
    frozen: Any,
    paths: Dict[str, str],
) -> Dict[str, Path]:
    prefix_mode = args.maximum_evaluations is not None
    v0448_ready = bool(
        result is not None
        and parity is not None
        and thermal_parity is not None
        and parity.ready
        and thermal_parity.ready
        and (
            prefix_mode
            or (
                final_parity is not None
                and final_parity.ready
                and acceptance is not None
                and acceptance.ready
            )
        )
    )
    summary = {
        "port_version": "v0.4.48",
        "purpose": "call-correlated matching-state physical dsec validation",
        "xstar_dsec_call_id": int(args.xstar_dsec_call_id),
        "correlation_source": correlation_source,
        "xstar_input_probe_dir": str(input_probe_dir),
        "xstar_input_calc_hmc_all_call_id": int(input_call_id),
        "xstar_post_dsec_probe_dir": str(post_probe_dir),
        "xstar_post_dsec_calc_hmc_all_call_id": int(post_call_id),
        "matching_input_phase": matching_input.phase,
        "initial_runtime_source": initial.source,
        "initial_temperature_t4": initial.temperature_t4,
        "initial_electron_fraction_xee": initial.electron_fraction_xee,
        "initial_hydrogen_density_cm3": initial.hydrogen_density_cm3,
        "nlim": initial.nlim,
        "tinf_t4": initial.tinf_t4,
        "abundant_element_z": list(plan.abundant_element_z),
        "population_state_mode": "correlated_global_xilevg_dynamic_compact_remap",
        "initial_global_population_source": "xstar_correlated_dsec_input_global_xilevg",
        "matching_leveltemp_restored": matching_input.leveltemp_workspace is not None,
        "first_continuum_workspace_policy": continuum_factory.template.first_workspace_policy,
        "carry_continuum_workspace": not args.reset_continuum_workspace,
        "continuum_context_build_count": continuum_factory.build_count,
        "prepare_only": bool(args.prepare_only),
        "prefix_mode": prefix_mode,
        "maximum_evaluations": args.maximum_evaluations,
        "frozen_v0444_complete_fixed_state_regression": frozen.ready,
        "python_dsec_converged": None if result is None else result.converged,
        "python_prefix_terminated": None if result is None else result.prefix_terminated,
        "python_ntotit": None if result is None else result.ntotit,
        "python_final_temperature_t4": None if result is None else result.state.temperature_t4,
        "python_final_electron_fraction_xee": None if result is None else result.state.electron_fraction_xee,
        "python_final_hmctot": None if result is None else result.final_hmctot,
        "python_final_elcter": None if result is None else result.final_elcter,
        "dsec_trajectory_parity_ready": None if parity is None else parity.ready,
        "dsec_thermal_parity_ready": None if thermal_parity is None else thermal_parity.ready,
        "final_fixed_state_parity_ready": None if final_parity is None else final_parity.ready,
        "v0445_bounded_dsec_acceptance_ready": None if acceptance is None else acceptance.ready,
        "v0448_call_correlated_matching_state_ready": v0448_ready,
        "products": paths,
    }
    json_path = out_dir / "xstar_dsec_physical_runner_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out_dir / "xstar_dsec_physical_runner_summary.md"
    md_path.write_text(
        "# Call-correlated physical XSTAR/Python `dsec` runner\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items() if key != "products")
        + "\n\n## Products\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in paths.items())
        + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": md_path}


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if args.maximum_evaluations is not None and args.maximum_evaluations <= 0:
        raise ValueError("--maximum-evaluations must be positive")
    if int(args.xstar_dsec_call_id) != 1:
        raise ValueError(
            "v0.4.48 remains bounded to dsec_call_id=1; later calls require "
            "mapping a captured nonzero global xilevg array onto physical level keys"
        )

    input_probe_dir, post_probe_dir, input_call_id, post_call_id, correlation_source = (
        _resolve_probe_inputs(args)
    )
    xstar_reference = load_xstar_dsec_trajectory(
        args.xstar_dsec_trajectory,
        call_id=args.xstar_dsec_call_id,
    )
    initial = initial_state_from_xstar_trajectory(
        xstar_reference,
        temperature_t4=args.initial_temperature_t4,
        electron_fraction_xee=args.initial_electron_fraction_xee,
        hydrogen_density_cm3=args.initial_hydrogen_density_cm3,
        nlim=args.nlim,
        tinf_t4=args.tinf_t4,
        policy=args.dsec_runtime_policy,
        relative_tolerance=args.runtime_rtol,
        absolute_tolerance=args.runtime_atol,
    )
    matching_input = load_dsec_matching_input_state(input_probe_dir, call_id=input_call_id)
    if matching_input.dsec_call_id != int(args.xstar_dsec_call_id):
        raise ValueError("matching input state belongs to a different dsec call")
    if matching_input.dsec_evaluation_index != 1 or matching_input.phase != "dsec_internal":
        raise ValueError("matching input state is not the first internal dsec evaluation")
    _check_matching_runtime(initial, matching_input, rtol=args.runtime_rtol, atol=args.runtime_atol)

    # The first internal dsec call is entered from init.f90's exact zero
    # global xilevg workspace.  The matching compact pre-msolvelucy probes are
    # therefore legitimately all zero.  Keep the general fixed-state loader
    # strict and opt into zero-sum acceptance only for this correlated state.
    plan = load_all_element_fixed_state_plan(
        input_probe_dir,
        oxygen_regression_dir=args.oxygen_call73_regression_dir,
        call_id=input_call_id,
        abundance_floor=args.abundance_floor,
        allow_zero_initial_population_sum=matching_input.global_xilevg_is_zero,
    )
    critf = float(matching_input.critf if args.critf is None else args.critf)
    critf_source = "xstar_correlated_input_probe" if args.critf is None else "command_line"
    covering_fraction = float(
        matching_input.covering_fraction
        if args.covering_fraction is None
        else args.covering_fraction
    )
    turbulent_velocity = float(
        matching_input.turbulent_velocity_km_s
        if args.turbulent_velocity_km_s is None
        else args.turbulent_velocity_km_s
    )
    pressure = float(matching_input.pressure if args.pressure is None else args.pressure)
    lcdd = int(matching_input.lcdd if args.lcdd is None else args.lcdd)

    input_comp2_ref = load_comp2_probe_reference(input_probe_dir, call_id=input_call_id)
    input_freef_ref = load_freef_probe_reference(input_probe_dir, call_id=input_call_id)
    input_bremem_ref = load_bremem_probe_reference(input_probe_dir, call_id=input_call_id)
    input_heatf_ref = load_heatf_probe_reference(input_probe_dir, call_id=input_call_id)
    final_ref = load_calc_hmc_all_final_state_reference(post_probe_dir, call_id=post_call_id)
    table = load_compton_table(args.coheat_data, atdb_path=args.atdb)

    ncn2 = int(matching_input.ncn2)
    epi = np.asarray(matching_input.radiation.epim_eV, dtype=float)
    bremsa = np.asarray(matching_input.radiation.bremsam, dtype=float)
    for name, observed in (
        ("comp2", input_comp2_ref.ncn2),
        ("freef", input_freef_ref.ncn2),
        ("bremem", input_bremem_ref.ncn2),
        ("heatf", input_heatf_ref.ncn2),
    ):
        if int(observed) != ncn2:
            raise ValueError(f"correlated {name} ncn2={observed} does not match input ncn2={ncn2}")
    if not np.array_equal(epi[:ncn2], input_comp2_ref.epi_eV[:ncn2]):
        raise ValueError("matching input continuum and correlated comp2 photon grids differ")
    if not np.array_equal(bremsa[:ncn2], input_comp2_ref.bremsa[:ncn2]):
        raise ValueError("matching input continuum and correlated comp2 radiation fields differ")

    workspace_policy = args.first_continuum_workspace_policy
    if workspace_policy == "auto":
        workspace_policy = "probe"
    continuum_template = PhysicalDsecContinuumTemplate(
        epi_eV=epi,
        bremsa=bremsa,
        compton_table=table,
        radius_cm=matching_input.radius_cm,
        zone_thickness_cm=matching_input.zone_thickness_cm,
        ncn2=ncn2,
        initial_opakc_cm_inv=input_freef_ref.opakc_before_cm_inv,
        initial_brcems=input_bremem_ref.brcems_before,
        source=(
            f"correlated_dsec_call_{args.xstar_dsec_call_id}_input_calc_hmc_all_"
            f"{input_call_id}"
        ),
        first_workspace_policy=workspace_policy,
        carry_continuum_workspace=not args.reset_continuum_workspace,
    )
    continuum_factory = PhysicalDsecCalcKwargsFactory(continuum_template)
    frozen = validate_v0444_complete_fixed_state_regression(args.v0444_regression)
    paths: Dict[str, str] = {}

    if args.prepare_only:
        runner_products = _write_runner_summary(
            out_dir=out,
            args=args,
            initial=initial,
            matching_input=matching_input,
            input_probe_dir=input_probe_dir,
            post_probe_dir=post_probe_dir,
            input_call_id=input_call_id,
            post_call_id=post_call_id,
            correlation_source=correlation_source,
            plan=plan,
            continuum_factory=continuum_factory,
            result=None,
            parity=None,
            thermal_parity=None,
            final_parity=None,
            acceptance=None,
            frozen=frozen,
            paths=paths,
        )
        if args.print_summary:
            print("Call-correlated physical dsec runner preparation")
            print("------------------------------------------------")
            print(f"xstar_dsec_call_id={args.xstar_dsec_call_id}")
            print(f"xstar_input_calc_hmc_all_call_id={input_call_id}")
            print(f"xstar_post_dsec_calc_hmc_all_call_id={post_call_id}")
            print(f"initial_temperature_t4={initial.temperature_t4:.17g}")
            print(f"initial_electron_fraction_xee={initial.electron_fraction_xee:.17g}")
            print(f"initial_hydrogen_density_cm3={initial.hydrogen_density_cm3:.17g}")
            print(f"nlim={initial.nlim}")
            print(f"tinf_t4={initial.tinf_t4:.17g}")
            print(f"abundant_element_z={','.join(map(str, plan.abundant_element_z))}")
            print(f"effective_critf={critf:.17g}")
            print(f"critf_source={critf_source}")
            print("population_state_mode=correlated_global_xilevg_dynamic_compact_remap")
            print("initial_global_population_source=xstar_correlated_dsec_input_global_xilevg")
            for key, value in runner_products.items():
                print(f"{key}={value}")
        return 0 if frozen.ready else 2

    state = build_physical_dsec_runtime_state(
        plan,
        initial=initial,
        radiation=matching_input.radiation,
        escape=matching_input.escape,
        covering_fraction=covering_fraction,
        turbulent_velocity_km_s=turbulent_velocity,
        lfast=args.lfast,
        critf=critf,
        initial_population_policy=args.initial_population_policy,
        pressure=pressure,
        lcdd=lcdd,
        matching_input=matching_input,
    )
    state.provenance.update(
        {
            "critf": critf,
            "critf_source": critf_source,
            "call_correlation_source": correlation_source,
            "input_calc_hmc_all_call_id": input_call_id,
            "post_dsec_calc_hmc_all_call_id": post_call_id,
            "continuum_template_source": continuum_template.source,
        }
    )

    def progress(index: int, runtime_state: Any, result: Any) -> None:
        if args.progress:
            bases = ",".join(
                f"Z{item.request.element_z}:{item.equilibrium.basis.n_rows}"
                for item in result.element_results
            )
            print(
                f"evaluation={index} T4={runtime_state.temperature_t4:.10g} "
                f"xee={runtime_state.electron_fraction_xee:.10g} "
                f"hmctot={result.hmctot:.10g} elcter={result.elcter:.10g} "
                f"basis={bases}",
                flush=True,
            )

    thermal_source = args.xstar_dsec_thermal_decomposition or str(
        Path(args.xstar_dsec_trajectory).parent
    )
    xstar_thermal = load_xstar_dsec_thermal_decomposition(
        thermal_source,
        dsec_call_id=args.xstar_dsec_call_id,
    )

    built = load_atomic_database_state(
        args.atdb,
        pointer_cache=args.pointer_cache,
        use_pointer_cache=True,
    )
    result = parity = thermal_parity = final_parity = acceptance = None
    try:
        evaluator = CalcHMCAllDsecEvaluator(
            master=built.master,
            derived=built.derived,
            calc_kwargs_factory=continuum_factory,
            progress_callback=progress,
        )
        result = dsec(
            state,
            evaluator=evaluator,
            nlim=initial.nlim,
            tinf_t4=initial.tinf_t4,
            maximum_evaluations=args.maximum_evaluations,
        )
        prefix_mode = bool(result.prefix_terminated)
        parity = compare_dsec_trajectory(
            result,
            xstar_reference,
            runtime_rtol=args.runtime_rtol,
            runtime_atol=args.runtime_atol,
            residual_rtol=args.residual_rtol,
            thermal_residual_atol=args.thermal_residual_atol,
            charge_residual_atol=args.charge_residual_atol,
            prefix_mode=prefix_mode,
        )
        thermal_parity = compare_dsec_thermal_decomposition(
            evaluator.evaluations,
            xstar_thermal,
            rtol=args.thermal_component_rtol,
            atol=args.thermal_component_atol,
            prefix_mode=prefix_mode,
        )

        trajectory_products = write_dsec_trajectory_products(result, out, port_version="v0.4.48")
        paths.update({f"python_trajectory_{key}": str(value) for key, value in trajectory_products.items()})
        parity_products = write_dsec_trajectory_parity_products(parity, out, port_version="v0.4.48")
        paths.update({f"trajectory_parity_{key}": str(value) for key, value in parity_products.items()})
        thermal_products = write_dsec_thermal_parity_products(
            thermal_parity, out, port_version="v0.4.48"
        )
        paths.update({f"thermal_parity_{key}": str(value) for key, value in thermal_products.items()})
        paths["physical_evaluations_csv"] = str(_write_evaluation_summary(evaluator.evaluations, out))

        if not prefix_mode:
            dsec_final_result = result.state.last_calc_hmc_all
            if dsec_final_result is None:
                raise RuntimeError("physical dsec completed without a final calc_hmc_all result")
            post_dsec_state = clone_physical_dsec_runtime_state(result.state)
            post_dsec_evaluation = evaluator(post_dsec_state)
            final_result = post_dsec_evaluation.fixed_state_result
            if final_result is None:
                raise RuntimeError("post-dsec calc_hmc_all did not return a fixed-state result")
            final_result.diagnostics.update(
                {
                    "physical_dsec_runner": True,
                    "post_dsec_xstarcalc_evaluation": True,
                    "xstar_dsec_call_id": args.xstar_dsec_call_id,
                    "xstar_input_calc_hmc_all_call_id": input_call_id,
                    "xstar_post_dsec_calc_hmc_all_call_id": post_call_id,
                    "dsec_ntotit": result.ntotit,
                    "dynamic_continuum_contexts": True,
                    "continuum_context_build_count": continuum_factory.build_count,
                }
            )
            final_parity = compare_complete_fixed_state_calc_hmc_all(
                final_result,
                final_ref,
                rtol=args.final_rtol,
                atol=args.final_atol,
                continuum_rtol=args.continuum_rtol,
                continuum_atol=args.continuum_atol,
            )
            acceptance = build_dsec_acceptance(
                parity,
                frozen_v0444=frozen,
                final_fixed_state_parity_ready=(final_parity.ready and thermal_parity.ready),
            )
            fixed_products = write_fixed_state_calc_hmc_all_products(
                final_result, out, port_version="v0.4.48"
            )
            paths.update({f"final_fixed_state_{key}": str(value) for key, value in fixed_products.items()})
            final_parity_products = write_complete_fixed_state_parity_products(
                final_parity, out, port_version="v0.4.48"
            )
            paths.update({f"final_parity_{key}": str(value) for key, value in final_parity_products.items()})
            acceptance_products = write_dsec_acceptance_products(
                acceptance, out, port_version="v0.4.48"
            )
            paths.update({f"acceptance_{key}": str(value) for key, value in acceptance_products.items()})

        runner_products = _write_runner_summary(
            out_dir=out,
            args=args,
            initial=initial,
            matching_input=matching_input,
            input_probe_dir=input_probe_dir,
            post_probe_dir=post_probe_dir,
            input_call_id=input_call_id,
            post_call_id=post_call_id,
            correlation_source=correlation_source,
            plan=plan,
            continuum_factory=continuum_factory,
            result=result,
            parity=parity,
            thermal_parity=thermal_parity,
            final_parity=final_parity,
            acceptance=acceptance,
            frozen=frozen,
            paths=paths,
        )
        paths.update({f"runner_{key}": str(value) for key, value in runner_products.items()})
    finally:
        built.master.close()

    if args.print_summary:
        print("Call-correlated physical XSTAR/Python dsec validation")
        print("------------------------------------------------------")
        print("port_version=v0.4.48")
        print(f"xstar_dsec_call_id={args.xstar_dsec_call_id}")
        print(f"xstar_input_calc_hmc_all_call_id={input_call_id}")
        print(f"xstar_post_dsec_calc_hmc_all_call_id={post_call_id}")
        print(f"python_prefix_terminated={result.prefix_terminated}")
        print(f"python_dsec_converged={result.converged}")
        print(f"python_ntotit={result.ntotit}")
        print(f"python_final_temperature_t4={result.state.temperature_t4:.17g}")
        print(f"python_final_electron_fraction_xee={result.state.electron_fraction_xee:.17g}")
        print(f"python_final_hmctot={result.final_hmctot:.17g}")
        print(f"python_final_elcter={result.final_elcter:.17g}")
        print(f"event_sequence_ready={parity.event_sequence_ready}")
        print(f"dsec_trajectory_parity_ready={parity.ready}")
        print(f"dsec_thermal_parity_ready={thermal_parity.ready}")
        if final_parity is not None:
            print("post_dsec_calc_hmc_all_executed=True")
            print(f"final_fixed_state_parity_ready={final_parity.ready}")
        print(f"frozen_v0444_complete_fixed_state_regression={frozen.ready}")
        if acceptance is not None:
            print(f"v0445_bounded_dsec_acceptance_ready={acceptance.ready}")
        for key, value in paths.items():
            print(f"{key}={value}")

    if result.prefix_terminated:
        return 0 if parity.ready and thermal_parity.ready and frozen.ready else 2
    return 0 if acceptance is not None and acceptance.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
