"""Unrestricted source-zero dsec acceptance with exact post-dsec replay."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .xstar_dsec_physical_cli import main as physical_main


DSEC_SOURCE_THERMAL_TOLERANCE = 1.0e-4


def _strip_option(args: Sequence[str], option: str, *, takes_value: bool) -> List[str]:
    out: List[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        if token == option:
            index += 2 if takes_value else 1
            continue
        if takes_value and token.startswith(option + "="):
            index += 1
            continue
        out.append(token)
        index += 1
    return out


def _clean_passthrough(args: Sequence[str]) -> List[str]:
    cleaned = list(args)
    for option, takes_value in (
        ("--out-dir", True),
        ("--maximum-evaluations", True),
        ("--prepare-only", False),
        ("--global-writeback-mode", True),
        ("--leveltemp-lifecycle", True),
        ("--terminal-continuum-seed-mode", True),
        ("--transition-input-mode", True),
        ("--post-dsec-input-mode", True),
        ("--compare-transition-internals", False),
        ("--transition-internal-evaluation-index", True),
        ("--xstar-transition-internal-probe-dir", True),
        ("--xstar-transition-internal-call-id", True),
        ("--print-summary", False),
    ):
        cleaned = _strip_option(cleaned, option, takes_value=takes_value)
    return cleaned


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required post-final-replay product is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        raise RuntimeError(f"required post-final-replay CSV is missing: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _truth(value: Any) -> bool:
    return str(value).strip().lower() == "true"


def _same_sign(left: float, right: float) -> bool:
    if left == 0.0 or right == 0.0:
        return left == right
    return (left < 0.0) == (right < 0.0)


def _source_control_flow_ready(summary: Mapping[str, Any]) -> bool:
    """Accept the literal dsec branch sequence independently of work-array roundoff."""
    return bool(
        summary.get("event_sequence_ready")
        and summary.get("integer_control_state_ready")
        and summary.get("thermal_residual_sign_ready")
        and summary.get("charge_residual_sign_ready")
    )


def _thermal_semantic_summary(path: Path) -> Dict[str, Any]:
    rows = _read_rows(path)
    component_failures: List[Dict[str, Any]] = []
    residual_failures: List[Dict[str, Any]] = []
    residual_sign_ready = True
    for row in rows:
        item = {
            "evaluation_index": int(row["evaluation_index"]),
            "quantity": row["quantity"],
            "python_value": float(row["python_value"]),
            "xstar_value": float(row["xstar_value"]),
            "absolute_difference": float(row["absolute_difference"]),
            "relative_difference": float(row["relative_difference"]),
        }
        if row["quantity"] == "hmctot":
            if not _same_sign(item["python_value"], item["xstar_value"]):
                residual_sign_ready = False
            if not _truth(row.get("within_tolerance")):
                residual_failures.append(item)
        elif not _truth(row.get("within_tolerance")):
            component_failures.append(item)
    return {
        "thermal_component_trajectory_ready": not component_failures,
        "thermal_residual_sign_ready": residual_sign_ready,
        "normalized_residual_roundoff_only": bool(
            residual_failures and not component_failures and residual_sign_ready
        ),
        "component_failures": component_failures,
        "normalized_residual_failures": residual_failures,
        "n_evaluations": len({int(row["evaluation_index"]) for row in rows}),
    }


def _internal_evaluation2_ready(summary: Mapping[str, Any]) -> bool:
    return bool(
        summary.get("pre_matrix_ready")
        and summary.get("same_call_matrix_active_closure_ready")
        and summary.get("initial_solver_population_ready")
        and summary.get("final_solver_active_population_ready")
        and summary.get("final_solver_outer_start_ready")
        and summary.get("final_solver_source_xtot_ready")
        and summary.get("thermal_family_ready")
        and summary.get("element_array_ready")
    )


def _natural_final_physics_ready(summary: Mapping[str, Any]) -> bool:
    """Require final local-zone physics while allowing a small converged-root drift."""
    return bool(
        summary.get("fixed_state_calc_hmc_all_translated")
        and summary.get("pre_matrix_ready")
        and summary.get("element_loop_ready")
        and summary.get("charge_scope_complete")
        and summary.get("continuum_sequence_complete")
        and summary.get("primary_heating_cooling_totals_parity_ready")
        and summary.get("secondary_heating_cooling_totals_parity_ready")
        and summary.get("electron_contribution_parity_ready")
        and summary.get("charge_residual_parity_ready")
        and summary.get("charge_identity_ready")
        and summary.get("hmctot_parity_ready")
        and summary.get("complete_fixed_state_ready")
    )


def _exact_final_source_semantic_summary(
    summary: Mapping[str, Any],
    rows: Sequence[Mapping[str, str]],
    *,
    source_thermal_tolerance: float = DSEC_SOURCE_THERMAL_TOLERANCE,
) -> Dict[str, Any]:
    """Classify exact post-``dsec`` parity using XSTAR's source decision.

    ``heatf.f90`` defines ``hmctot`` as a normalized difference.  Near thermal
    equilibrium, tiny independently accepted changes in ``httot`` and ``cltot``
    can produce a large relative change in ``hmctot``.  ``dsec.f90`` does not
    compare that residual with a reference value; it tests
    ``abs(hmctot) <= crith`` with ``crith=1.e-4``.  Keep strict residual parity
    visible, but accept the final fixed state when every underlying source
    quantity passes, both residuals reproduce the source expression, and both
    make the same converged source decision.
    """
    by_quantity = {str(row["quantity"]): row for row in rows}
    required = {
        "httot", "cltot", "hmctot", "httot2", "cltot2", "elcter",
        "temperature_t4", "electron_fraction_xee",
    }
    missing = sorted(required - set(by_quantity))
    if missing:
        return {
            "exact_post_dsec_fixed_state_semantic_ready": False,
            "exact_post_dsec_semantic_missing_quantities": missing,
            "exact_post_dsec_source_thermal_tolerance": float(source_thermal_tolerance),
        }

    def value(quantity: str, side: str) -> float:
        return float(by_quantity[quantity][f"{side}_value"])

    py_httot = value("httot", "python")
    py_cltot = value("cltot", "python")
    xs_httot = value("httot", "xstar")
    xs_cltot = value("cltot", "xstar")
    py_hmctot = value("hmctot", "python")
    xs_hmctot = value("hmctot", "xstar")
    py_reconstructed = 2.0 * (py_httot - py_cltot) / (1.0e-37 + py_httot + py_cltot)
    xs_reconstructed = 2.0 * (xs_httot - xs_cltot) / (1.0e-37 + xs_httot + xs_cltot)
    py_formula_ready = math.isclose(py_hmctot, py_reconstructed, rel_tol=5.0e-12, abs_tol=1.0e-15)
    xs_formula_ready = math.isclose(xs_hmctot, xs_reconstructed, rel_tol=5.0e-12, abs_tol=1.0e-15)
    py_converged = abs(py_hmctot) <= float(source_thermal_tolerance)
    xs_converged = abs(xs_hmctot) <= float(source_thermal_tolerance)
    convergence_decision_ready = py_converged == xs_converged
    same_sign = _same_sign(py_hmctot, xs_hmctot)

    strict_failures = [
        str(row["quantity"])
        for row in rows
        if not _truth(row.get("within_tolerance"))
    ]
    residual_only_failure = strict_failures == ["hmctot"]
    underlying_fixed_state_ready = bool(
        summary.get("fixed_state_calc_hmc_all_translated")
        and summary.get("pre_matrix_ready")
        and summary.get("element_loop_ready")
        and summary.get("charge_scope_complete")
        and summary.get("continuum_sequence_complete")
        and summary.get("runtime_state_parity_ready")
        and summary.get("continuum_component_parity_ready")
        and summary.get("primary_heating_cooling_totals_parity_ready")
        and summary.get("secondary_heating_cooling_totals_parity_ready")
        and summary.get("electron_contribution_parity_ready")
        and summary.get("charge_residual_parity_ready")
        and summary.get("charge_identity_ready")
        and summary.get("complete_fixed_state_ready")
    )
    semantic_ready = bool(
        underlying_fixed_state_ready
        and residual_only_failure
        and py_formula_ready
        and xs_formula_ready
        and convergence_decision_ready
        and py_converged
        and xs_converged
        and same_sign
    )
    return {
        "exact_post_dsec_fixed_state_semantic_ready": semantic_ready,
        "exact_post_dsec_underlying_fixed_state_ready": underlying_fixed_state_ready,
        "exact_post_dsec_hmctot_strict_parity_ready": summary.get("hmctot_parity_ready") is True,
        "exact_post_dsec_hmctot_residual_only_failure": residual_only_failure,
        "exact_post_dsec_hmctot_source_expression_ready": bool(py_formula_ready and xs_formula_ready),
        "exact_post_dsec_python_hmctot_source_expression_ready": py_formula_ready,
        "exact_post_dsec_xstar_hmctot_source_expression_ready": xs_formula_ready,
        "exact_post_dsec_python_hmctot_reconstructed": py_reconstructed,
        "exact_post_dsec_xstar_hmctot_reconstructed": xs_reconstructed,
        "exact_post_dsec_python_hmctot_converged": py_converged,
        "exact_post_dsec_xstar_hmctot_converged": xs_converged,
        "exact_post_dsec_hmctot_convergence_decision_ready": convergence_decision_ready,
        "exact_post_dsec_hmctot_sign_ready": same_sign,
        "exact_post_dsec_source_thermal_tolerance": float(source_thermal_tolerance),
        "exact_post_dsec_strict_failure_quantities": strict_failures,
        "exact_post_dsec_semantic_missing_quantities": [],
    }


def _classify(payload: Mapping[str, Any]) -> str:
    if payload.get("python_dsec_converged") is not True:
        return "source_zero_post_replay_dsec_not_converged"
    if payload.get("evaluation_count_ready") is not True:
        return "source_zero_post_replay_evaluation_count_mismatch"
    if payload.get("source_control_flow_ready") is not True:
        return "source_zero_post_replay_control_path_mismatch"
    if payload.get("thermal_component_trajectory_ready") is not True:
        return "source_zero_post_replay_thermal_component_mismatch"
    if payload.get("evaluation2_internal_ready") is not True:
        return "source_zero_post_replay_evaluation2_internal_mismatch"
    if payload.get("natural_final_physics_ready") is not True:
        return "source_zero_post_replay_natural_final_physics_mismatch"
    if payload.get("exact_post_dsec_replay_executed") is not True:
        return "source_zero_post_replay_missing"
    if payload.get("exact_post_dsec_fixed_state_semantic_ready") is not True:
        return "source_zero_post_replay_fixed_state_semantic_mismatch"
    if payload.get("frozen_v0444_complete_fixed_state_regression") is not True:
        return "source_zero_post_replay_frozen_regression_failed"
    if payload.get("strict_trajectory_ready") is True and payload.get(
        "natural_final_fixed_state_parity_ready"
    ) is True:
        return "source_zero_post_replay_strict_ready"
    if payload.get("exact_post_dsec_fixed_state_parity_ready") is not True:
        return "source_zero_post_replay_ready_with_source_converged_residual_roundoff"
    return "source_zero_post_replay_ready_with_converged_root_roundoff"


def _write_products(out: Path, payload: Dict[str, Any]) -> Dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["port_version"] = "v0.4.59"
    payload["diagnostic"] = "unrestricted_source_zero_post_dsec_final_residual_semantics"
    payload["unrestricted_source_semantic_acceptance_ready"] = bool(
        payload.get("python_dsec_converged")
        and payload.get("evaluation_count_ready")
        and payload.get("source_control_flow_ready")
        and payload.get("thermal_component_trajectory_ready")
        and payload.get("thermal_residual_sign_ready")
        and payload.get("evaluation2_internal_ready")
        and payload.get("post_dsec_calc_hmc_all_executed")
        and payload.get("natural_final_physics_ready")
        and payload.get("exact_post_dsec_replay_executed")
        and payload.get("exact_post_dsec_fixed_state_semantic_ready")
        and payload.get("frozen_v0444_complete_fixed_state_regression")
    )
    payload["ready_to_advance_to_bremsmap"] = payload[
        "unrestricted_source_semantic_acceptance_ready"
    ]
    payload["diagnostic_conclusion"] = _classify(payload)

    json_path = out / "xstar_dsec_post_final_replay_summary.json"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    residual_path = out / "xstar_dsec_post_final_replay_residual_failures.csv"
    fields = (
        "evaluation_index",
        "quantity",
        "python_value",
        "xstar_value",
        "absolute_difference",
        "relative_difference",
    )
    with residual_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in payload.get("normalized_residual_failures", []):
            writer.writerow({name: row.get(name) for name in fields})

    md_path = out / "xstar_dsec_post_final_replay_summary.md"
    lines = [
        "# Unrestricted source-zero `dsec` with exact post-dsec replay",
        "",
        f"- Diagnostic conclusion: `{payload['diagnostic_conclusion']}`",
        f"- Source-semantic acceptance: `{payload['unrestricted_source_semantic_acceptance_ready']}`",
        f"- Ready to advance to `bremsmap`: `{payload['ready_to_advance_to_bremsmap']}`",
        f"- Python converged: `{payload.get('python_dsec_converged')}`",
        f"- Python/XSTAR evaluations: `{payload.get('python_evaluation_count')}/{payload.get('xstar_evaluation_count')}`",
        f"- Source control flow: `{payload.get('source_control_flow_ready')}`",
        f"- Thermal components: `{payload.get('thermal_component_trajectory_ready')}`",
        f"- Thermal residual signs: `{payload.get('thermal_residual_sign_ready')}`",
        f"- Normalized-residual roundoff only: `{payload.get('normalized_residual_roundoff_only')}`",
        f"- Evaluation-2 internals: `{payload.get('evaluation2_internal_ready')}`",
        f"- Natural final physics: `{payload.get('natural_final_physics_ready')}`",
        f"- Natural final strict parity: `{payload.get('natural_final_fixed_state_parity_ready')}`",
        f"- Exact post-dsec strict parity: `{payload.get('exact_post_dsec_fixed_state_parity_ready')}`",
        f"- Exact post-dsec source-semantic parity: `{payload.get('exact_post_dsec_fixed_state_semantic_ready')}`",
        f"- Exact residual source expression: `{payload.get('exact_post_dsec_hmctot_source_expression_ready')}`",
        f"- Exact residual convergence decision: `{payload.get('exact_post_dsec_hmctot_convergence_decision_ready')}`",
        f"- Natural final T4/XSTAR T4: `{payload.get('python_final_temperature_t4')}/{payload.get('xstar_final_temperature_t4')}`",
        f"- Natural final xee/XSTAR xee: `{payload.get('python_final_electron_fraction_xee')}/{payload.get('xstar_final_electron_fraction_xee')}`",
        "",
        "The exact post-dsec replay replaces the captured call-entry runtime, radiation, escape, continuum workspaces, dense global populations, and `leveltemp`; Python still recomputes all rates, matrices, populations, and thermal quantities.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "markdown": md_path, "residual_failures_csv": residual_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run unrestricted production dsec, classify the same-sign near-zero "
            "thermal residual separately from component parity, and replay the exact "
            "captured XSTAR post-dsec calc_hmc_all entry state."
        )
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw = list(argv if argv is not None else __import__("sys").argv[1:])
    owned = build_parser().parse_known_args(raw)[0]
    out = Path(owned.out_dir)
    physical_out = out / "unrestricted_source_zero_post_replay"
    passthrough = _clean_passthrough(raw)
    physical_args = [
        *passthrough,
        "--global-writeback-mode", "dense-source",
        "--leveltemp-lifecycle", "reset-per-call",
        "--terminal-continuum-seed-mode", "source-zero",
        "--transition-input-mode", "compare-only",
        "--post-dsec-input-mode", "compare-both",
        "--compare-transition-internals",
        "--out-dir", str(physical_out),
    ]
    physical_exit = physical_main(physical_args)

    runner = _read_json(physical_out / "xstar_dsec_physical_runner_summary.json")
    trajectory = _read_json(physical_out / "xstar_dsec_trajectory_parity_summary.json")
    thermal = _thermal_semantic_summary(
        physical_out / "xstar_dsec_thermal_decomposition_parity.csv"
    )
    internal = _read_json(
        physical_out
        / "evaluation_internal_parity"
        / "xstar_calc_hmc_all_pre_continuum_parity_summary.json"
    )
    natural_final = _read_json(
        physical_out / "xstar_calc_hmc_all_complete_fixed_state_parity_summary.json"
    )
    exact_final = _read_json(
        physical_out
        / "post_dsec_exact_replay"
        / "xstar_calc_hmc_all_complete_fixed_state_parity_summary.json"
    )

    python_count = int(runner.get("python_ntotit") or 0)
    xstar_count = int(thermal["n_evaluations"])
    payload: Dict[str, Any] = {
        "physical_exit_code": int(physical_exit),
        "python_dsec_converged": runner.get("python_dsec_converged") is True,
        "python_ntotit": python_count,
        "python_evaluation_count": python_count,
        "xstar_evaluation_count": xstar_count,
        "evaluation_count_ready": python_count == xstar_count,
        "strict_trajectory_ready": trajectory.get("dsec_trajectory_parity_ready") is True,
        "source_control_flow_ready": _source_control_flow_ready(trajectory),
        "event_sequence_ready": trajectory.get("event_sequence_ready") is True,
        "integer_control_state_ready": trajectory.get("integer_control_state_ready") is True,
        "charge_residual_sign_ready": trajectory.get("charge_residual_sign_ready") is True,
        **thermal,
        "evaluation2_internal_ready": _internal_evaluation2_ready(internal),
        "post_dsec_calc_hmc_all_executed": natural_final.get("calc_hmc_all_call_id") is not None,
        "natural_final_physics_ready": _natural_final_physics_ready(natural_final),
        "natural_final_fixed_state_parity_ready": natural_final.get("complete_fixed_state_parity_ready") is True,
        "exact_post_dsec_replay_executed": exact_final.get("calc_hmc_all_call_id") is not None,
        "exact_post_dsec_fixed_state_parity_ready": exact_final.get("complete_fixed_state_parity_ready") is True,
        "natural_final_max_relative_difference": natural_final.get("max_relative_difference"),
        "exact_final_max_relative_difference": exact_final.get("max_relative_difference"),
        "python_final_temperature_t4": runner.get("python_final_temperature_t4"),
        "python_final_electron_fraction_xee": runner.get("python_final_electron_fraction_xee"),
        "xstar_final_temperature_t4": exact_final.get("diagnostics", {}).get("reference_temperature_t4"),
        "xstar_final_electron_fraction_xee": exact_final.get("diagnostics", {}).get("reference_electron_fraction_xee"),
        "frozen_v0444_complete_fixed_state_regression": runner.get("frozen_v0444_complete_fixed_state_regression") is True,
        "transition_state_ready": runner.get("dsec_transition_state_ready") is True,
    }
    # Reference runtime values are represented directly in parity rows; recover them
    # without adding special fields to the shared comparison format.
    exact_rows = _read_rows(
        physical_out
        / "post_dsec_exact_replay"
        / "xstar_calc_hmc_all_complete_fixed_state_parity.csv"
    )
    for row in exact_rows:
        if row["quantity"] == "temperature_t4":
            payload["xstar_final_temperature_t4"] = float(row["xstar_value"])
        elif row["quantity"] == "electron_fraction_xee":
            payload["xstar_final_electron_fraction_xee"] = float(row["xstar_value"])
    payload.update(_exact_final_source_semantic_summary(exact_final, exact_rows))

    products = _write_products(out, payload)
    if owned.print_summary:
        print("Unrestricted source-zero dsec with exact post-dsec replay")
        print("----------------------------------------------------------")
        print(f"physical_exit_code={physical_exit}")
        print(f"python_dsec_converged={payload['python_dsec_converged']}")
        print(f"python_ntotit={payload['python_ntotit']}")
        print(f"xstar_evaluation_count={payload['xstar_evaluation_count']}")
        print(f"source_control_flow_ready={payload['source_control_flow_ready']}")
        print(f"thermal_component_trajectory_ready={payload['thermal_component_trajectory_ready']}")
        print(f"normalized_residual_roundoff_only={payload['normalized_residual_roundoff_only']}")
        print(f"evaluation2_internal_ready={payload['evaluation2_internal_ready']}")
        print(f"natural_final_physics_ready={payload['natural_final_physics_ready']}")
        print(f"natural_final_fixed_state_parity_ready={payload['natural_final_fixed_state_parity_ready']}")
        print(f"exact_post_dsec_fixed_state_parity_ready={payload['exact_post_dsec_fixed_state_parity_ready']}")
        print(f"exact_post_dsec_fixed_state_semantic_ready={payload['exact_post_dsec_fixed_state_semantic_ready']}")
        data = _read_json(products["json"])
        print(f"unrestricted_source_semantic_acceptance_ready={data['unrestricted_source_semantic_acceptance_ready']}")
        print(f"ready_to_advance_to_bremsmap={data['ready_to_advance_to_bremsmap']}")
        print(f"diagnostic_conclusion={data['diagnostic_conclusion']}")
        print(f"json={products['json']}")
        print(f"markdown={products['markdown']}")
    return 0 if _read_json(products["json"])["unrestricted_source_semantic_acceptance_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
