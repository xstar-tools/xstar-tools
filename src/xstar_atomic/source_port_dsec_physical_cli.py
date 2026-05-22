"""Call-correlated physical runner for the translated XSTAR ``dsec`` subsystem."""
from __future__ import annotations

import argparse
import copy
import csv
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np

from .source_port import (
    CalcHMCAllDsecEvaluator,
    PhysicalDsecCalcKwargsFactory,
    PhysicalDsecContinuumTemplate,
    apply_dsec_matching_input_state,
    build_dsec_acceptance,
    build_physical_dsec_runtime_state,
    clone_physical_dsec_runtime_state,
    compare_calc_hmc_all_pre_continuum_probe,
    compare_complete_fixed_state_calc_hmc_all,
    compare_dsec_thermal_decomposition,
    compare_dsec_trajectory,
    compare_dsec_transition_state,
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
    write_calc_hmc_all_pre_continuum_parity_products,
    write_dsec_acceptance_products,
    write_dsec_thermal_parity_products,
    write_dsec_trajectory_parity_products,
    write_dsec_transition_state_products,
    write_dsec_input_snapshot_products,
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
    parser.add_argument(
        "--xstar-transition-input-probe-dir",
        help=(
            "optional probe directory containing the XSTAR state entering a later "
            "internal dsec evaluation; v0.4.51 initially targets evaluation 2"
        ),
    )
    parser.add_argument(
        "--xstar-transition-call-correlation",
        help=(
            "correlation CSV for the transition-state probe run; defaults to the "
            "correlation CSV in --xstar-transition-input-probe-dir or the main one"
        ),
    )
    parser.add_argument("--xstar-transition-calc-hmc-call-id", type=int)
    parser.add_argument("--xstar-transition-evaluation-index", type=int, default=2)
    parser.add_argument(
        "--transition-input-mode",
        choices=("compare-only", "replay-exact"),
        default="compare-only",
        help=(
            "compare-only records the Python state entering the selected later "
            "evaluation; replay-exact replaces that call entry with the captured "
            "XSTAR runtime, radiation, escape, continuum workspace, global arrays, "
            "and leveltemp state before Python recomputes rates, matrices, and cooling"
        ),
    )
    parser.add_argument(
        "--xstar-transition-internal-probe-dir",
        help=(
            "optional same-call calc_hmc_all probe directory for a selected dsec "
            "evaluation; defaults to --xstar-transition-input-probe-dir when "
            "--compare-transition-internals is requested"
        ),
    )
    parser.add_argument(
        "--xstar-transition-internal-call-id",
        type=int,
        help=(
            "calc_hmc_all call ID in the detailed matrix/population/thermal probe; "
            "defaults to the resolved transition call ID"
        ),
    )
    parser.add_argument(
        "--transition-internal-evaluation-index",
        type=int,
        help=(
            "Python evaluation whose exact rates, matrix, Lucy populations, and "
            "thermal channels are compared; defaults to the transition evaluation"
        ),
    )
    parser.add_argument(
        "--compare-transition-internals",
        action="store_true",
        help=(
            "run the existing complete same-call calc_hmc_all parity audit on the "
            "selected dsec evaluation, including matrix terms, initial/final Lucy "
            "populations, and thermal families"
        ),
    )
    parser.add_argument(
        "--transition-internal-active-population-threshold",
        type=float,
        default=1.0e-12,
    )
    parser.add_argument(
        "--transition-internal-row-scale-threshold",
        type=float,
        default=1.0e-12,
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
    parser.add_argument(
        "--global-writeback-mode",
        choices=("legacy-selected", "dense-source"),
        default="dense-source",
        help=(
            "global population ownership between dsec evaluations; dense-source "
            "replays the complete calc_hmc_element/calc_hmc_all alias writeback"
        ),
    )
    parser.add_argument(
        "--leveltemp-lifecycle",
        choices=("carry", "reset-per-call"),
        default="reset-per-call",
        help=(
            "carry preserves the v0.4.51 diagnostic behavior; reset-per-call "
            "restores the captured calc_hmc_all entry workspace before each trial"
        ),
    )

    parser.add_argument(
        "--terminal-continuum-seed-mode",
        choices=("legacy-global", "source-zero"),
        default="source-zero",
        help=(
            "source-zero reproduces calc_hmc_element.f90 x(ipmat2+1)=0 before "
            "msolvelucy; legacy-global retains the pre-v0.4.55 diagnostic seed"
        ),
    )

    parser.add_argument(
        "--post-dsec-input-mode",
        choices=("natural", "compare-both"),
        default="natural",
        help=(
            "natural evaluates the post-dsec calc_hmc_all at the naturally converged "
            "Python state; compare-both also replays the complete captured XSTAR "
            "call-entry state for the correlated post-dsec call and recomputes it in Python"
        ),
    )

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
    parser.add_argument("--transition-runtime-rtol", type=float, default=5.0e-12)
    parser.add_argument("--transition-runtime-atol", type=float, default=1.0e-30)
    parser.add_argument("--transition-array-rtol", type=float, default=5.0e-12)
    parser.add_argument("--transition-array-atol", type=float, default=1.0e-30)
    parser.add_argument("--transition-population-rtol", type=float, default=5.0e-12)
    parser.add_argument("--transition-population-atol", type=float, default=1.0e-30)
    parser.add_argument("--transition-leveltemp-rtol", type=float, default=5.0e-12)
    parser.add_argument("--transition-leveltemp-atol", type=float, default=1.0e-30)
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


def _resolve_transition_input(args: argparse.Namespace) -> tuple[Optional[Path], Optional[int], Optional[Any], Optional[str]]:
    value = args.xstar_transition_input_probe_dir
    if value is None:
        return None, None, None, None
    probe_dir = Path(value)
    evaluation_index = int(args.xstar_transition_evaluation_index)
    if evaluation_index <= 1:
        raise ValueError("--xstar-transition-evaluation-index must be at least 2")

    call_id = args.xstar_transition_calc_hmc_call_id
    source = args.xstar_transition_call_correlation
    if source is None:
        local = probe_dir / "xstar_dsec_calc_hmc_all_call_correlation.csv"
        if local.is_file():
            source = str(local)
        elif args.xstar_call_correlation:
            source = args.xstar_call_correlation
    if call_id is None:
        if source is None:
            raise ValueError(
                "transition-state capture requires --xstar-transition-call-correlation "
                "or --xstar-transition-calc-hmc-call-id"
            )
        correlation = resolve_dsec_calc_hmc_all_calls(
            source,
            dsec_call_id=args.xstar_dsec_call_id,
            input_evaluation_index=evaluation_index,
        )
        call_id = correlation.input_calc_hmc_all_call_id
        source = correlation.source_path
    matching = load_dsec_matching_input_state(probe_dir, call_id=int(call_id))
    if matching.dsec_call_id != int(args.xstar_dsec_call_id):
        raise ValueError("transition input state belongs to a different dsec call")
    if matching.dsec_evaluation_index != evaluation_index:
        raise ValueError(
            "transition input state evaluation mismatch: "
            f"requested={evaluation_index}, captured={matching.dsec_evaluation_index}"
        )
    if matching.phase != "dsec_internal":
        raise ValueError("transition input state is not an internal dsec evaluation")
    return probe_dir, int(call_id), matching, source


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


def _write_element_evaluation_summary(
    evaluations: Sequence[Any], out_dir: Path
) -> Path:
    """Write source-order element thermal and solver diagnostics per trial."""

    path = out_dir / "xstar_dsec_element_thermal_decomposition.csv"
    fieldnames = (
        "evaluation_index",
        "element_order",
        "element_z",
        "abundance",
        "selected_min_ion_stage",
        "selected_max_ion_stage",
        "basis_size",
        "n_superlevels",
        "heating_per_abundance",
        "cooling_per_abundance",
        "heating2_per_abundance",
        "cooling2_per_abundance",
        "heating",
        "cooling",
        "heating2",
        "cooling2",
        "electron_contribution",
        "solver_converged",
        "solver_method",
        "outer_iterations",
        "fixed_point_iterations",
        "final_outer_difference",
        "final_fixed_point_difference",
        "normalization",
        "normalization_error",
        "max_active_relative_row_residual",
        "dense_condition_number",
        "used_dense_fallback",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for evaluation_index, evaluation in enumerate(evaluations, start=1):
            result = evaluation.fixed_state_result
            if result is None:
                continue
            for element_order, item in enumerate(result.element_results, start=1):
                equilibrium = item.equilibrium
                assembly = getattr(equilibrium, "assembly", None)
                basis = getattr(assembly, "basis", None)
                solve = getattr(equilibrium, "solve", None)
                notes = list(getattr(solve, "notes", ()) or ()) if solve is not None else []
                writer.writerow(
                    {
                        "evaluation_index": evaluation_index,
                        "element_order": element_order,
                        "element_z": int(item.request.element_z),
                        "abundance": float(item.request.abundance),
                        "selected_min_ion_stage": int(item.selected_min_ion_stage),
                        "selected_max_ion_stage": int(item.selected_max_ion_stage),
                        "basis_size": int(getattr(basis, "n_rows", 0) or 0),
                        "n_superlevels": int(
                            getattr(basis, "n_superlevels", 0) or 0
                        ),
                        "heating_per_abundance": float(item.heating_per_abundance),
                        "cooling_per_abundance": float(item.cooling_per_abundance),
                        "heating2_per_abundance": float(item.heating2_per_abundance),
                        "cooling2_per_abundance": float(item.cooling2_per_abundance),
                        "heating": float(item.heating),
                        "cooling": float(item.cooling),
                        "heating2": float(item.heating2),
                        "cooling2": float(item.cooling2),
                        "electron_contribution": float(item.electron_contribution),
                        "solver_converged": (
                            None if solve is None else bool(solve.converged)
                        ),
                        "solver_method": (
                            "" if solve is None else str(solve.solver_method)
                        ),
                        "outer_iterations": (
                            0 if solve is None else int(solve.outer_iterations)
                        ),
                        "fixed_point_iterations": (
                            0 if solve is None else int(solve.fixed_point_iterations)
                        ),
                        "final_outer_difference": (
                            float("nan")
                            if solve is None
                            else float(solve.final_outer_difference)
                        ),
                        "final_fixed_point_difference": (
                            float("nan")
                            if solve is None
                            else float(solve.final_fixed_point_difference)
                        ),
                        "normalization": (
                            float("nan")
                            if solve is None
                            else float(solve.normalization)
                        ),
                        "normalization_error": (
                            float("nan")
                            if solve is None
                            else float(solve.normalization_error)
                        ),
                        "max_active_relative_row_residual": (
                            float("nan")
                            if solve is None
                            else float(solve.max_active_relative_row_residual)
                        ),
                        "dense_condition_number": (
                            float("nan")
                            if solve is None
                            else float(solve.dense_condition_number)
                        ),
                        "used_dense_fallback": any(
                            "dense" in note.lower() and "fallback" in note.lower()
                            for note in notes
                        ),
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
    transition_input: Optional[Any],
    transition_parity: Optional[Any],
    transition_internal_parity: Optional[Any],
    final_parity: Optional[Any],
    exact_final_parity: Optional[Any],
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
        "port_version": "v0.4.58",
        "purpose": "call-correlated physical dsec and evaluation-transition validation",
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
        "global_writeback_mode": args.global_writeback_mode,
        "leveltemp_lifecycle": args.leveltemp_lifecycle,
        "terminal_continuum_seed_mode": args.terminal_continuum_seed_mode,
        "transition_input_mode": args.transition_input_mode,
        "post_dsec_input_mode": args.post_dsec_input_mode,
        "v0452_dense_native_global_alias_writeback_ready": (
            args.global_writeback_mode == "dense-source"
        ),
        "v0452_leveltemp_per_call_reset_ready": (
            args.leveltemp_lifecycle == "reset-per-call"
        ),
        "v0455_terminal_continuum_zero_seed_ready": (
            args.terminal_continuum_seed_mode == "source-zero"
        ),
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
        "transition_evaluation_index": (
            None if transition_input is None else transition_input.dsec_evaluation_index
        ),
        "transition_calc_hmc_all_call_id": (
            None if transition_input is None else transition_input.calc_hmc_all_call_id
        ),
        "dsec_transition_state_ready": (
            None if transition_parity is None else transition_parity.ready
        ),
        "transition_internal_parity_ready": (
            None
            if transition_internal_parity is None
            else transition_internal_parity.parity_ready
        ),
        "transition_internal_pre_matrix_ready": (
            None
            if transition_internal_parity is None
            else transition_internal_parity.pre_matrix_ready
        ),
        "transition_internal_same_call_matrix_ready": (
            None
            if transition_internal_parity is None
            else transition_internal_parity.same_call_matrix_ready
        ),
        "transition_internal_initial_solver_population_ready": (
            None
            if transition_internal_parity is None
            else transition_internal_parity.initial_solver_population_ready
        ),
        "transition_internal_final_solver_snapshot_ready": (
            None
            if transition_internal_parity is None
            else transition_internal_parity.final_solver_snapshot_ready
        ),
        "transition_internal_thermal_family_ready": (
            None
            if transition_internal_parity is None
            else transition_internal_parity.thermal_family_ready
        ),
        "transition_runtime_state_ready": (
            None if transition_parity is None else transition_parity.runtime_state_ready
        ),
        "transition_radiation_state_ready": (
            None if transition_parity is None else transition_parity.radiation_state_ready
        ),
        "transition_escape_state_ready": (
            None if transition_parity is None else transition_parity.escape_state_ready
        ),
        "transition_continuum_workspace_ready": (
            None if transition_parity is None else transition_parity.continuum_workspace_ready
        ),
        "transition_global_mapping_ready": (
            None if transition_parity is None else transition_parity.global_mapping_ready
        ),
        "transition_global_xilevg_ready": (
            None if transition_parity is None else transition_parity.global_xilevg_ready
        ),
        "transition_global_bilevg_ready": (
            None if transition_parity is None else transition_parity.global_bilevg_ready
        ),
        "transition_global_rnisg_ready": (
            None if transition_parity is None else transition_parity.global_rnisg_ready
        ),
        "transition_leveltemp_source_used_slots_ready": (
            None
            if transition_parity is None
            else transition_parity.leveltemp_source_used_slots_ready
        ),
        "final_fixed_state_parity_ready": None if final_parity is None else final_parity.ready,
        "exact_post_dsec_fixed_state_parity_ready": (
            None if exact_final_parity is None else exact_final_parity.ready
        ),
        "v0445_bounded_dsec_acceptance_ready": None if acceptance is None else acceptance.ready,
        "v0448_call_correlated_matching_state_ready": v0448_ready,
        "v0451_evaluation_transition_diagnostic_ready": (
            None if transition_parity is None else transition_parity.ready
        ),
        "v0454_evaluation_internal_parity_diagnostic_ready": (
            None
            if transition_internal_parity is None
            else transition_internal_parity.parity_ready
        ),
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


def _format_element_basis_sizes(result: Any) -> str:
    """Return source-order element compact-basis sizes for progress output."""
    return ",".join(
        f"Z{item.request.element_z}:{item.equilibrium.assembly.basis.n_rows}"
        for item in result.element_results
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if args.maximum_evaluations is not None and args.maximum_evaluations <= 0:
        raise ValueError("--maximum-evaluations must be positive")
    if int(args.xstar_dsec_call_id) != 1:
        raise ValueError(
            "v0.4.58 remains bounded to dsec_call_id=1; later calls require "
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
    transition_probe_dir, transition_call_id, transition_input, transition_correlation_source = (
        _resolve_transition_input(args)
    )
    transition_internal_probe_dir: Optional[Path] = None
    transition_internal_call_id: Optional[int] = None
    transition_internal_evaluation_index: Optional[int] = None
    if args.compare_transition_internals:
        if transition_input is None or transition_probe_dir is None or transition_call_id is None:
            raise ValueError(
                "--compare-transition-internals requires a resolved "
                "--xstar-transition-input-probe-dir"
            )
        transition_internal_probe_dir = Path(
            args.xstar_transition_internal_probe_dir or transition_probe_dir
        )
        transition_internal_call_id = int(
            args.xstar_transition_internal_call_id or transition_call_id
        )
        transition_internal_evaluation_index = int(
            args.transition_internal_evaluation_index
            or transition_input.dsec_evaluation_index
        )
        if transition_internal_evaluation_index < 1:
            raise ValueError(
                "--transition-internal-evaluation-index must be positive"
            )
    transition_freef_ref = transition_bremem_ref = None
    if transition_input is not None:
        transition_freef_ref = load_freef_probe_reference(
            transition_probe_dir, call_id=int(transition_call_id)
        )
        transition_bremem_ref = load_bremem_probe_reference(
            transition_probe_dir, call_id=int(transition_call_id)
        )
    if args.transition_input_mode == "replay-exact" and transition_input is None:
        raise ValueError(
            "--transition-input-mode replay-exact requires "
            "--xstar-transition-input-probe-dir"
        )
    if matching_input.dsec_call_id != int(args.xstar_dsec_call_id):
        raise ValueError("matching input state belongs to a different dsec call")
    if matching_input.dsec_evaluation_index != 1 or matching_input.phase != "dsec_internal":
        raise ValueError("matching input state is not the first internal dsec evaluation")
    _check_matching_runtime(initial, matching_input, rtol=args.runtime_rtol, atol=args.runtime_atol)
    if transition_input is not None and args.maximum_evaluations is not None:
        if int(args.maximum_evaluations) < int(transition_input.dsec_evaluation_index):
            raise ValueError(
                "--maximum-evaluations must reach the requested transition evaluation "
                f"{transition_input.dsec_evaluation_index}"
            )

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
    post_matching_input = post_freef_ref = post_bremem_ref = None
    if args.post_dsec_input_mode == "compare-both":
        post_matching_input = load_dsec_matching_input_state(
            post_probe_dir, call_id=post_call_id
        )
        if post_matching_input.phase != "post_dsec":
            raise ValueError(
                "correlated post-dsec matching input does not have phase=post_dsec"
            )
        post_freef_ref = load_freef_probe_reference(
            post_probe_dir, call_id=post_call_id
        )
        post_bremem_ref = load_bremem_probe_reference(
            post_probe_dir, call_id=post_call_id
        )
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
            transition_input=transition_input,
            transition_parity=None,
            transition_internal_parity=None,
            final_parity=None,
            exact_final_parity=None,
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
            if transition_input is not None:
                print(f"xstar_transition_evaluation_index={transition_input.dsec_evaluation_index}")
                print(f"xstar_transition_calc_hmc_all_call_id={transition_input.calc_hmc_all_call_id}")
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
        terminal_continuum_seed_mode=args.terminal_continuum_seed_mode,
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
    state.source_global_alias_writeback = args.global_writeback_mode == "dense-source"
    state.reset_leveltemp_each_calc_hmc_all = args.leveltemp_lifecycle == "reset-per-call"
    state.provenance.update(
        {
            "global_writeback_mode": args.global_writeback_mode,
            "leveltemp_lifecycle": args.leveltemp_lifecycle,
            "terminal_continuum_seed_mode": args.terminal_continuum_seed_mode,
        }
    )

    transition_replay_diagnostics: Dict[str, Any] = {}

    def pre_evaluation(index: int, runtime_state: Any) -> None:
        if (
            args.transition_input_mode == "replay-exact"
            and transition_input is not None
            and int(index) == int(transition_input.dsec_evaluation_index)
        ):
            transition_replay_diagnostics.update(
                apply_dsec_matching_input_state(
                    runtime_state,
                    transition_input,
                    opakc_before_cm_inv=transition_freef_ref.opakc_before_cm_inv,
                    brcems_before=transition_bremem_ref.brcems_before,
                    continuum_factory=continuum_factory,
                )
            )

    def progress(index: int, runtime_state: Any, result: Any) -> None:
        if args.progress:
            bases = _format_element_basis_sizes(result)
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
    result = parity = thermal_parity = transition_parity = None
    transition_internal_parity = final_parity = exact_final_parity = acceptance = None
    try:
        evaluator = CalcHMCAllDsecEvaluator(
            master=built.master,
            derived=built.derived,
            calc_kwargs_factory=continuum_factory,
            pre_evaluation_callback=pre_evaluation,
            progress_callback=progress,
            capture_input_snapshot_indices=(
                ()
                if transition_input is None
                else (int(transition_input.dsec_evaluation_index),)
            ),
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

        trajectory_products = write_dsec_trajectory_products(result, out, port_version="v0.4.58")
        paths.update({f"python_trajectory_{key}": str(value) for key, value in trajectory_products.items()})
        parity_products = write_dsec_trajectory_parity_products(parity, out, port_version="v0.4.58")
        paths.update({f"trajectory_parity_{key}": str(value) for key, value in parity_products.items()})
        thermal_products = write_dsec_thermal_parity_products(
            thermal_parity, out, port_version="v0.4.58"
        )
        paths.update({f"thermal_parity_{key}": str(value) for key, value in thermal_products.items()})
        paths["physical_evaluations_csv"] = str(_write_evaluation_summary(evaluator.evaluations, out))
        paths["element_thermal_decomposition_csv"] = str(
            _write_element_evaluation_summary(evaluator.evaluations, out)
        )
        if transition_replay_diagnostics:
            replay_path = out / "xstar_dsec_transition_replay_applied.json"
            replay_path.write_text(
                json.dumps(transition_replay_diagnostics, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            paths["transition_replay_applied_json"] = str(replay_path)

        if transition_input is not None:
            target = int(transition_input.dsec_evaluation_index)
            transition_snapshot = next(
                (
                    item
                    for item in evaluator.input_snapshots
                    if int(item.evaluation_index) == target
                ),
                None,
            )
            if transition_snapshot is None:
                captured = ",".join(
                    str(item.evaluation_index) for item in evaluator.input_snapshots
                ) or "none"
                raise RuntimeError(
                    f"Python run did not capture transition evaluation {target}; "
                    f"captured={captured}"
                )
            transition_parity = compare_dsec_transition_state(
                transition_snapshot,
                transition_input,
                runtime_rtol=args.transition_runtime_rtol,
                runtime_atol=args.transition_runtime_atol,
                array_rtol=args.transition_array_rtol,
                array_atol=args.transition_array_atol,
                population_rtol=args.transition_population_rtol,
                population_atol=args.transition_population_atol,
                leveltemp_rtol=args.transition_leveltemp_rtol,
                leveltemp_atol=args.transition_leveltemp_atol,
                xstar_opakc_before_cm_inv=transition_freef_ref.opakc_before_cm_inv,
                xstar_brcems_before=transition_bremem_ref.brcems_before,
            )
            transition_products = write_dsec_transition_state_products(
                transition_parity, out, port_version="v0.4.58"
            )
            paths.update(
                {f"transition_parity_{key}": str(value) for key, value in transition_products.items()}
            )
            transition_state_products = write_dsec_input_snapshot_products(
                transition_snapshot, transition_input, out
            )
            paths.update(
                {f"transition_state_{key}": str(value) for key, value in transition_state_products.items()}
            )

        if args.compare_transition_internals:
            assert transition_internal_probe_dir is not None
            assert transition_internal_call_id is not None
            assert transition_internal_evaluation_index is not None
            if transition_internal_evaluation_index > len(evaluator.evaluations):
                raise RuntimeError(
                    "requested internal-parity evaluation was not executed: "
                    f"requested={transition_internal_evaluation_index}, "
                    f"executed={len(evaluator.evaluations)}"
                )
            internal_evaluation = evaluator.evaluations[
                transition_internal_evaluation_index - 1
            ]
            internal_result = internal_evaluation.fixed_state_result
            if internal_result is None:
                raise RuntimeError(
                    "selected dsec evaluation did not return a fixed-state result"
                )
            transition_internal_parity = compare_calc_hmc_all_pre_continuum_probe(
                internal_result,
                transition_internal_probe_dir,
                call_id=transition_internal_call_id,
                rtol=args.thermal_component_rtol,
                atol=args.thermal_component_atol,
                active_population_threshold=(
                    args.transition_internal_active_population_threshold
                ),
                matrix_closure_active_row_scale_threshold=(
                    args.transition_internal_row_scale_threshold
                ),
            )
            internal_out = out / "evaluation_internal_parity"
            internal_products = write_calc_hmc_all_pre_continuum_parity_products(
                transition_internal_parity,
                internal_out,
                port_version="v0.4.58",
            )
            paths.update(
                {
                    f"transition_internal_{key}": str(value)
                    for key, value in internal_products.items()
                }
            )

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
                    "post_dsec_input_mode": "natural",
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
            fixed_products = write_fixed_state_calc_hmc_all_products(
                final_result, out, port_version="v0.4.58"
            )
            paths.update({f"final_fixed_state_{key}": str(value) for key, value in fixed_products.items()})
            final_parity_products = write_complete_fixed_state_parity_products(
                final_parity, out, port_version="v0.4.58"
            )
            paths.update({f"final_parity_{key}": str(value) for key, value in final_parity_products.items()})

            if args.post_dsec_input_mode == "compare-both":
                assert post_matching_input is not None
                assert post_freef_ref is not None
                assert post_bremem_ref is not None
                exact_state = clone_physical_dsec_runtime_state(result.state)
                exact_factory = PhysicalDsecCalcKwargsFactory(
                    copy.deepcopy(continuum_template)
                )
                replay_details = apply_dsec_matching_input_state(
                    exact_state,
                    post_matching_input,
                    opakc_before_cm_inv=post_freef_ref.opakc_before_cm_inv,
                    brcems_before=post_bremem_ref.brcems_before,
                    continuum_factory=exact_factory,
                )
                exact_evaluator = CalcHMCAllDsecEvaluator(
                    master=built.master,
                    derived=built.derived,
                    calc_kwargs_factory=exact_factory,
                )
                exact_evaluation = exact_evaluator(exact_state)
                exact_final_result = exact_evaluation.fixed_state_result
                if exact_final_result is None:
                    raise RuntimeError(
                        "exact post-dsec replay did not return a fixed-state result"
                    )
                exact_final_result.diagnostics.update(
                    {
                        "physical_dsec_runner": True,
                        "post_dsec_xstarcalc_evaluation": True,
                        "post_dsec_input_mode": "replay-exact",
                        "xstar_dsec_call_id": args.xstar_dsec_call_id,
                        "xstar_post_dsec_calc_hmc_all_call_id": post_call_id,
                        "dsec_ntotit": result.ntotit,
                        "exact_post_dsec_replay": True,
                    }
                )
                exact_final_parity = compare_complete_fixed_state_calc_hmc_all(
                    exact_final_result,
                    final_ref,
                    rtol=args.final_rtol,
                    atol=args.final_atol,
                    continuum_rtol=args.continuum_rtol,
                    continuum_atol=args.continuum_atol,
                )
                exact_out = out / "post_dsec_exact_replay"
                exact_fixed_products = write_fixed_state_calc_hmc_all_products(
                    exact_final_result, exact_out, port_version="v0.4.58"
                )
                paths.update(
                    {
                        f"exact_final_fixed_state_{key}": str(value)
                        for key, value in exact_fixed_products.items()
                    }
                )
                exact_parity_products = write_complete_fixed_state_parity_products(
                    exact_final_parity, exact_out, port_version="v0.4.58"
                )
                paths.update(
                    {
                        f"exact_final_parity_{key}": str(value)
                        for key, value in exact_parity_products.items()
                    }
                )
                replay_path = exact_out / "xstar_post_dsec_exact_replay_applied.json"
                replay_path.write_text(
                    json.dumps(replay_details, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                paths["exact_final_replay_applied_json"] = str(replay_path)

            acceptance = build_dsec_acceptance(
                parity,
                frozen_v0444=frozen,
                final_fixed_state_parity_ready=(final_parity.ready and thermal_parity.ready),
            )
            acceptance_products = write_dsec_acceptance_products(
                acceptance, out, port_version="v0.4.58"
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
            transition_input=transition_input,
            transition_parity=transition_parity,
            transition_internal_parity=transition_internal_parity,
            final_parity=final_parity,
            exact_final_parity=exact_final_parity,
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
        print("port_version=v0.4.58")
        print(f"global_writeback_mode={args.global_writeback_mode}")
        print(f"leveltemp_lifecycle={args.leveltemp_lifecycle}")
        print(
            f"terminal_continuum_seed_mode={args.terminal_continuum_seed_mode}"
        )
        print(f"transition_input_mode={args.transition_input_mode}")
        print(f"post_dsec_input_mode={args.post_dsec_input_mode}")
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
        if transition_parity is not None:
            print(f"dsec_transition_state_ready={transition_parity.ready}")
            print(f"transition_runtime_state_ready={transition_parity.runtime_state_ready}")
            print(f"transition_radiation_state_ready={transition_parity.radiation_state_ready}")
            print(f"transition_escape_state_ready={transition_parity.escape_state_ready}")
            print(
                "transition_continuum_workspace_ready="
                f"{transition_parity.continuum_workspace_ready}"
            )
            print(f"transition_global_mapping_ready={transition_parity.global_mapping_ready}")
            print(f"transition_global_xilevg_ready={transition_parity.global_xilevg_ready}")
            print(f"transition_global_bilevg_ready={transition_parity.global_bilevg_ready}")
            print(f"transition_global_rnisg_ready={transition_parity.global_rnisg_ready}")
            print(
                "transition_leveltemp_source_used_slots_ready="
                f"{transition_parity.leveltemp_source_used_slots_ready}"
            )
        if transition_internal_parity is not None:
            print(
                "transition_internal_parity_ready="
                f"{transition_internal_parity.parity_ready}"
            )
            print(
                "transition_internal_same_call_matrix_ready="
                f"{transition_internal_parity.same_call_matrix_ready}"
            )
            print(
                "transition_internal_initial_solver_population_ready="
                f"{transition_internal_parity.initial_solver_population_ready}"
            )
            print(
                "transition_internal_final_solver_snapshot_ready="
                f"{transition_internal_parity.final_solver_snapshot_ready}"
            )
            print(
                "transition_internal_thermal_family_ready="
                f"{transition_internal_parity.thermal_family_ready}"
            )
        if final_parity is not None:
            print("post_dsec_calc_hmc_all_executed=True")
            print(f"final_fixed_state_parity_ready={final_parity.ready}")
        if exact_final_parity is not None:
            print("exact_post_dsec_replay_executed=True")
            print(
                "exact_post_dsec_fixed_state_parity_ready="
                f"{exact_final_parity.ready}"
            )
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
