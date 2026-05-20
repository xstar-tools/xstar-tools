"""Physical bounded runner for the translated XSTAR ``dsec`` subsystem."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from .source_port import (
    CalcHMCAllDsecEvaluator,
    PhysicalDsecCalcKwargsFactory,
    PhysicalDsecContinuumTemplate,
    build_dsec_acceptance,
    build_physical_dsec_runtime_state,
    clone_physical_dsec_runtime_state,
    compare_complete_fixed_state_calc_hmc_all,
    compare_dsec_trajectory,
    dsec,
    initial_state_from_xstar_trajectory,
    load_all_element_fixed_state_plan,
    load_atomic_database_state,
    load_bremem_probe_reference,
    load_calc_hmc_all_final_state_reference,
    load_calc_hmc_all_probe_critf,
    load_compton_table,
    load_comp2_probe_reference,
    load_freef_probe_reference,
    load_heatf_probe_reference,
    load_xstar_dsec_trajectory,
    validate_v0444_complete_fixed_state_regression,
    write_complete_fixed_state_parity_products,
    write_dsec_acceptance_products,
    write_dsec_trajectory_parity_products,
    write_dsec_trajectory_products,
    write_fixed_state_calc_hmc_all_products,
)
from .source_port_element_cli import _load_escape_npz, _select_live_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the real translated calc_hmc_all inside dsec, compare the full "
            "Python trajectory with one instrumented XSTAR dsec call, and write "
            "the bounded v0.4.45 acceptance products."
        )
    )
    parser.add_argument("--atdb", required=True)
    parser.add_argument("--pointer-cache")

    parser.add_argument("--live-rate-grid-probe-csv", required=True)
    parser.add_argument("--live-rate-grid-state", default="last")
    parser.add_argument("--escape-npz")
    parser.add_argument("--assume-optically-thin", action="store_true")

    parser.add_argument("--xstar-calc-hmc-probe-dir", required=True)
    parser.add_argument("--xstar-calc-hmc-call-id", type=int, default=73)
    parser.add_argument("--oxygen-call73-regression-dir", required=True)
    parser.add_argument("--abundance-floor", type=float, default=1.0e-24)
    parser.add_argument(
        "--initial-population-policy",
        choices=("use-available", "require-all", "ignore"),
        default="require-all",
    )

    parser.add_argument("--xstar-dsec-trajectory", required=True)
    parser.add_argument("--xstar-dsec-call-id", type=int, default=1)
    parser.add_argument(
        "--dsec-runtime-policy",
        choices=("use", "check", "ignore"),
        default="use",
        help=(
            "use the XSTAR begin row (default), check explicit initial/control "
            "values against it, or ignore the begin row and use explicit values"
        ),
    )
    parser.add_argument("--initial-temperature-t4", type=float)
    parser.add_argument("--initial-electron-fraction-xee", type=float)
    parser.add_argument("--initial-hydrogen-density-cm3", type=float)
    parser.add_argument("--nlim", type=int)
    parser.add_argument("--tinf-t4", type=float)

    parser.add_argument("--covering-fraction", type=float, default=1.0)
    parser.add_argument("--turbulent-velocity-km-s", type=float, default=0.0)
    parser.add_argument("--pressure", type=float, default=0.0)
    parser.add_argument("--lcdd", type=int, default=1)
    parser.add_argument("--lfast", type=int, default=2)
    parser.add_argument("--critf", type=float)
    parser.add_argument("--coheat-data")
    parser.add_argument(
        "--first-continuum-workspace-policy",
        choices=("zero", "call73-probe"),
        default="zero",
        help=(
            "initial local opakc/brcems scratch policy; later trials always carry "
            "the previous returned workspace unless --reset-continuum-workspace is used"
        ),
    )
    parser.add_argument("--reset-continuum-workspace", action="store_true")

    parser.add_argument("--runtime-rtol", type=float, default=5.0e-12)
    parser.add_argument("--runtime-atol", type=float, default=1.0e-30)
    parser.add_argument("--residual-rtol", type=float, default=5.0e-3)
    parser.add_argument("--thermal-residual-atol", type=float, default=1.0e-8)
    parser.add_argument("--charge-residual-atol", type=float, default=1.0e-10)
    parser.add_argument("--final-rtol", type=float, default=5.0e-3)
    parser.add_argument("--final-atol", type=float, default=1.0e-12)
    parser.add_argument("--continuum-rtol", type=float, default=5.0e-12)
    parser.add_argument("--continuum-atol", type=float, default=1.0e-30)
    parser.add_argument("--v0444-regression")

    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def _write_evaluation_summary(result: Any, out_dir: Path) -> Path:
    """Write one row for every post-calc_hmc_all trajectory event."""

    path = out_dir / "xstar_dsec_physical_evaluations.csv"
    fields = [
        "evaluation_index",
        "ntotit",
        "temperature_t4",
        "temperature_k",
        "electron_fraction_xee",
        "hydrogen_density_cm3",
        "hmctot",
        "elcter",
        "normalized_charge_residual",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for event in result.trajectory:
            if event.event != "after_calc_hmc_all":
                continue
            writer.writerow({name: getattr(event, name) for name in fields})
    return path


def _write_runner_summary(
    *,
    out_dir: Path,
    args: argparse.Namespace,
    initial: Any,
    plan: Any,
    continuum_factory: PhysicalDsecCalcKwargsFactory,
    result: Optional[Any],
    parity: Optional[Any],
    final_parity: Optional[Any],
    acceptance: Optional[Any],
    frozen: Any,
    paths: Dict[str, str],
) -> Dict[str, Path]:
    summary = {
        "port_version": "v0.4.46",
        "purpose": "physical runner for bounded v0.4.45 dsec acceptance",
        "xstar_dsec_call_id": int(args.xstar_dsec_call_id),
        "xstar_calc_hmc_all_call_id": int(args.xstar_calc_hmc_call_id),
        "initial_runtime_source": initial.source,
        "initial_temperature_t4": initial.temperature_t4,
        "initial_electron_fraction_xee": initial.electron_fraction_xee,
        "initial_hydrogen_density_cm3": initial.hydrogen_density_cm3,
        "nlim": initial.nlim,
        "tinf_t4": initial.tinf_t4,
        "abundant_element_z": list(plan.abundant_element_z),
        "initial_population_policy": args.initial_population_policy,
        "first_continuum_workspace_policy": args.first_continuum_workspace_policy,
        "carry_continuum_workspace": not args.reset_continuum_workspace,
        "continuum_context_build_count": continuum_factory.build_count,
        "prepare_only": bool(args.prepare_only),
        "frozen_v0444_complete_fixed_state_regression": frozen.ready,
        "python_dsec_converged": None if result is None else result.converged,
        "python_ntotit": None if result is None else result.ntotit,
        "python_final_temperature_t4": None if result is None else result.state.temperature_t4,
        "python_final_electron_fraction_xee": None if result is None else result.state.electron_fraction_xee,
        "python_final_hmctot": None if result is None else result.final_hmctot,
        "python_final_elcter": None if result is None else result.final_elcter,
        "dsec_trajectory_parity_ready": None if parity is None else parity.ready,
        "final_fixed_state_parity_ready": None if final_parity is None else final_parity.ready,
        "v0445_bounded_dsec_acceptance_ready": None if acceptance is None else acceptance.ready,
        "products": paths,
    }
    json_path = out_dir / "xstar_dsec_physical_runner_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out_dir / "xstar_dsec_physical_runner_summary.md"
    md_path.write_text(
        "# Physical XSTAR/Python `dsec` runner\n\n"
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

    probe_dir = Path(args.xstar_calc_hmc_probe_dir)
    plan = load_all_element_fixed_state_plan(
        probe_dir,
        oxygen_regression_dir=args.oxygen_call73_regression_dir,
        call_id=args.xstar_calc_hmc_call_id,
        abundance_floor=args.abundance_floor,
    )
    if args.critf is None:
        critf = float(
            load_calc_hmc_all_probe_critf(
                probe_dir,
                element_z=8,
                call_id=args.xstar_calc_hmc_call_id,
            ).critf
        )
        critf_source = "xstar_calc_hmc_probe"
    else:
        critf = float(args.critf)
        critf_source = "command_line"

    radiation = _select_live_state(args.live_rate_grid_probe_csv, args.live_rate_grid_state)
    escape = _load_escape_npz(args.escape_npz, args.assume_optically_thin)

    comp2_ref = load_comp2_probe_reference(probe_dir, call_id=args.xstar_calc_hmc_call_id)
    freef_ref = load_freef_probe_reference(probe_dir, call_id=args.xstar_calc_hmc_call_id)
    bremem_ref = load_bremem_probe_reference(probe_dir, call_id=args.xstar_calc_hmc_call_id)
    heatf_ref = load_heatf_probe_reference(probe_dir, call_id=args.xstar_calc_hmc_call_id)
    final_ref = load_calc_hmc_all_final_state_reference(
        probe_dir, call_id=args.xstar_calc_hmc_call_id
    )
    table = load_compton_table(args.coheat_data, atdb_path=args.atdb)

    ncn2 = int(comp2_ref.ncn2)
    for name, observed in (
        ("freef", freef_ref.ncn2),
        ("bremem", bremem_ref.ncn2),
        ("heatf", heatf_ref.ncn2),
    ):
        if int(observed) != ncn2:
            raise ValueError(f"{name} ncn2={observed} does not match comp2 ncn2={ncn2}")
    if not np.array_equal(comp2_ref.epi_eV[:ncn2], freef_ref.epi_eV[:ncn2]):
        raise ValueError("comp2 and freef photon grids differ")
    if not np.array_equal(comp2_ref.epi_eV[:ncn2], bremem_ref.epi_eV[:ncn2]):
        raise ValueError("comp2 and bremem photon grids differ")
    if not np.array_equal(comp2_ref.epi_eV[:ncn2], heatf_ref.epi_eV[:ncn2]):
        raise ValueError("comp2 and heatf photon grids differ")

    continuum_template = PhysicalDsecContinuumTemplate(
        epi_eV=comp2_ref.epi_eV,
        bremsa=comp2_ref.bremsa,
        compton_table=table,
        radius_cm=heatf_ref.radius_cm,
        zone_thickness_cm=heatf_ref.zone_thickness_cm,
        ncn2=ncn2,
        initial_opakc_cm_inv=freef_ref.opakc_before_cm_inv,
        initial_brcems=bremem_ref.brcems_before,
        source="bounded_call73_zone_input_recomputed_per_dsec_trial",
        first_workspace_policy=args.first_continuum_workspace_policy,
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
            plan=plan,
            continuum_factory=continuum_factory,
            result=None,
            parity=None,
            final_parity=None,
            acceptance=None,
            frozen=frozen,
            paths=paths,
        )
        paths.update({f"runner_{key}": str(value) for key, value in runner_products.items()})
        if args.print_summary:
            print("Physical dsec runner preparation")
            print("--------------------------------")
            print(f"initial_runtime_source={initial.source}")
            print(f"initial_temperature_t4={initial.temperature_t4:.17g}")
            print(f"initial_electron_fraction_xee={initial.electron_fraction_xee:.17g}")
            print(f"initial_hydrogen_density_cm3={initial.hydrogen_density_cm3:.17g}")
            print(f"nlim={initial.nlim}")
            print(f"tinf_t4={initial.tinf_t4:.17g}")
            print(f"abundant_element_z={','.join(map(str, plan.abundant_element_z))}")
            print(f"effective_critf={critf:.17g}")
            print(f"critf_source={critf_source}")
            for key, value in runner_products.items():
                print(f"{key}={value}")
        return 0 if frozen.ready else 2

    state = build_physical_dsec_runtime_state(
        plan,
        initial=initial,
        radiation=radiation,
        escape=escape,
        covering_fraction=args.covering_fraction,
        turbulent_velocity_km_s=args.turbulent_velocity_km_s,
        lfast=args.lfast,
        critf=critf,
        initial_population_policy=args.initial_population_policy,
        pressure=args.pressure,
        lcdd=args.lcdd,
    )
    state.provenance.update(
        {
            "critf": critf,
            "critf_source": critf_source,
            "continuum_template_source": continuum_template.source,
            "first_continuum_workspace_policy": args.first_continuum_workspace_policy,
            "carry_continuum_workspace": not args.reset_continuum_workspace,
        }
    )

    built = load_atomic_database_state(
        args.atdb,
        pointer_cache=args.pointer_cache,
        use_pointer_cache=True,
    )
    try:
        evaluator = CalcHMCAllDsecEvaluator(
            master=built.master,
            derived=built.derived,
            calc_kwargs_factory=continuum_factory,
        )
        result = dsec(
            state,
            evaluator=evaluator,
            nlim=initial.nlim,
            tinf_t4=initial.tinf_t4,
        )
        parity = compare_dsec_trajectory(
            result,
            xstar_reference,
            runtime_rtol=args.runtime_rtol,
            runtime_atol=args.runtime_atol,
            residual_rtol=args.residual_rtol,
            thermal_residual_atol=args.thermal_residual_atol,
            charge_residual_atol=args.charge_residual_atol,
        )
        dsec_final_result = result.state.last_calc_hmc_all
        if dsec_final_result is None:
            raise RuntimeError("physical dsec completed without a final calc_hmc_all result")

        # Source order in xstarcalc.f90 is dsec -> calc_hmc_all.  The accepted
        # call-73 oracle is this post-dsec evaluation, not necessarily the last
        # evaluation internal to dsec.  Evaluate it on a clone so the dsec
        # trajectory and its ntotit/call-count invariant remain unchanged.
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
                "dsec_ntotit": result.ntotit,
                "dynamic_continuum_contexts": True,
                "continuum_context_build_count": continuum_factory.build_count,
                "dsec_final_hmctot": float(dsec_final_result.hmctot),
                "dsec_final_elcter": float(dsec_final_result.elcter),
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
            final_fixed_state_parity_ready=final_parity.ready,
        )

        trajectory_products = write_dsec_trajectory_products(result, out, port_version="v0.4.46")
        paths.update({f"python_trajectory_{key}": str(value) for key, value in trajectory_products.items()})
        parity_products = write_dsec_trajectory_parity_products(parity, out, port_version="v0.4.46")
        paths.update({f"trajectory_parity_{key}": str(value) for key, value in parity_products.items()})
        fixed_products = write_fixed_state_calc_hmc_all_products(
            final_result, out, port_version="v0.4.46"
        )
        paths.update({f"final_fixed_state_{key}": str(value) for key, value in fixed_products.items()})
        final_parity_products = write_complete_fixed_state_parity_products(
            final_parity, out, port_version="v0.4.46"
        )
        paths.update({f"final_parity_{key}": str(value) for key, value in final_parity_products.items()})
        acceptance_products = write_dsec_acceptance_products(
            acceptance, out, port_version="v0.4.46"
        )
        paths.update({f"acceptance_{key}": str(value) for key, value in acceptance_products.items()})
        paths["physical_evaluations_csv"] = str(_write_evaluation_summary(result, out))

        runner_products = _write_runner_summary(
            out_dir=out,
            args=args,
            initial=initial,
            plan=plan,
            continuum_factory=continuum_factory,
            result=result,
            parity=parity,
            final_parity=final_parity,
            acceptance=acceptance,
            frozen=frozen,
            paths=paths,
        )
        paths.update({f"runner_{key}": str(value) for key, value in runner_products.items()})
    finally:
        built.master.close()

    if args.print_summary:
        print("Physical XSTAR/Python dsec acceptance")
        print("--------------------------------------")
        print("port_version=v0.4.46")
        print(f"xstar_dsec_call_id={args.xstar_dsec_call_id}")
        print(f"xstar_calc_hmc_all_call_id={args.xstar_calc_hmc_call_id}")
        print(f"initial_runtime_source={initial.source}")
        print(f"initial_temperature_t4={initial.temperature_t4:.17g}")
        print(f"initial_electron_fraction_xee={initial.electron_fraction_xee:.17g}")
        print(f"nlim={initial.nlim}")
        print(f"tinf_t4={initial.tinf_t4:.17g}")
        print(f"python_dsec_converged={result.converged}")
        print(f"python_ntotit={result.ntotit}")
        print(f"python_final_temperature_t4={result.state.temperature_t4:.17g}")
        print(f"python_final_electron_fraction_xee={result.state.electron_fraction_xee:.17g}")
        print(f"python_final_hmctot={result.final_hmctot:.17g}")
        print(f"python_final_elcter={result.final_elcter:.17g}")
        print(f"event_sequence_ready={parity.event_sequence_ready}")
        print(f"integer_control_state_ready={parity.integer_control_state_ready}")
        print(f"runtime_state_ready={parity.runtime_state_ready}")
        print(f"thermal_residual_value_ready={parity.thermal_residual_value_ready}")
        print(f"thermal_residual_sign_ready={parity.thermal_residual_sign_ready}")
        print(f"charge_residual_value_ready={parity.charge_residual_value_ready}")
        print(f"charge_residual_sign_ready={parity.charge_residual_sign_ready}")
        print(f"final_state_ready={parity.final_state_ready}")
        print(f"dsec_trajectory_parity_ready={parity.ready}")
        print("post_dsec_calc_hmc_all_executed=True")
        print(f"final_fixed_state_parity_ready={final_parity.ready}")
        print(f"frozen_v0444_complete_fixed_state_regression={frozen.ready}")
        print(f"v0445_bounded_dsec_acceptance_ready={acceptance.ready}")
        for key, value in paths.items():
            print(f"{key}={value}")

    return 0 if acceptance.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
