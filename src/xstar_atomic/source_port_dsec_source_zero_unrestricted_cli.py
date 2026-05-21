"""Unrestricted source-zero dsec convergence and final-state acceptance wrapper."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .source_port_dsec_physical_cli import main as physical_main


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
    """Remove options owned by the unrestricted production wrapper."""
    cleaned = list(args)
    for option, takes_value in (
        ("--out-dir", True),
        ("--maximum-evaluations", True),
        ("--prepare-only", False),
        ("--global-writeback-mode", True),
        ("--leveltemp-lifecycle", True),
        ("--terminal-continuum-seed-mode", True),
        ("--transition-input-mode", True),
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
        raise RuntimeError(f"required unrestricted dsec product is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        raise RuntimeError(f"required unrestricted dsec CSV is missing: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _runtime_failures(path: Path) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    for row in _read_rows(path):
        if row.get("comparison_mode") != "runtime_isclose":
            continue
        if str(row.get("within_tolerance", "")).strip().lower() == "true":
            continue
        failures.append(
            {
                "event_index": int(row["event_index"]),
                "event": row["event"],
                "quantity": row["quantity"],
                "python_value": float(row["python_value"]),
                "xstar_value": float(row["xstar_value"]),
                "absolute_difference": float(row["absolute_difference"]),
                "relative_difference": float(row["relative_difference"]),
            }
        )
    return failures


def _branch_trajectory_ready(summary: Mapping[str, Any]) -> bool:
    """Require identical source branches and residual decisions, not bitwise work arrays."""
    return bool(
        summary.get("event_sequence_ready")
        and summary.get("integer_control_state_ready")
        and summary.get("thermal_residual_value_ready")
        and summary.get("thermal_residual_sign_ready")
        and summary.get("charge_residual_value_ready")
        and summary.get("charge_residual_sign_ready")
        and summary.get("final_state_ready")
    )


def _thermal_by_evaluation(path: Path) -> List[Dict[str, Any]]:
    grouped: Dict[int, List[Dict[str, str]]] = {}
    for row in _read_rows(path):
        grouped.setdefault(int(row["evaluation_index"]), []).append(row)
    output: List[Dict[str, Any]] = []
    for evaluation_index in sorted(grouped):
        rows = grouped[evaluation_index]
        failed = [
            row
            for row in rows
            if str(row.get("within_tolerance", "")).strip().lower() != "true"
        ]
        output.append(
            {
                "evaluation_index": evaluation_index,
                "ready": not failed,
                "n_failed_quantities": len(failed),
                "failed_quantities": [row["quantity"] for row in failed],
                "max_relative_difference": max(
                    (float(row["relative_difference"]) for row in rows),
                    default=0.0,
                ),
                "max_absolute_difference": max(
                    (float(row["absolute_difference"]) for row in rows),
                    default=0.0,
                ),
            }
        )
    return output


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


def _classify(payload: Mapping[str, Any]) -> str:
    if payload.get("python_dsec_converged") is not True:
        return "source_zero_unrestricted_dsec_not_converged"
    if payload.get("evaluation_count_ready") is not True:
        return "source_zero_unrestricted_evaluation_count_mismatch"
    if payload.get("branch_trajectory_ready") is not True:
        return "source_zero_unrestricted_control_path_mismatch"
    if payload.get("thermal_trajectory_ready") is not True:
        return "source_zero_unrestricted_thermal_trajectory_mismatch"
    if payload.get("evaluation2_internal_ready") is not True:
        return "source_zero_unrestricted_evaluation2_internal_mismatch"
    if payload.get("post_dsec_calc_hmc_all_executed") is not True:
        return "source_zero_unrestricted_post_dsec_calc_hmc_all_missing"
    if payload.get("final_fixed_state_parity_ready") is not True:
        return "source_zero_unrestricted_final_fixed_state_mismatch"
    if payload.get("frozen_v0444_complete_fixed_state_regression") is not True:
        return "source_zero_unrestricted_frozen_regression_failed"
    if payload.get("strict_trajectory_ready") is True and payload.get(
        "transition_state_ready"
    ) is True:
        return "source_zero_unrestricted_strict_ready"
    return "source_zero_unrestricted_source_semantic_ready_with_strict_roundoff"


def _write_products(out: Path, payload: Dict[str, Any]) -> Dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["port_version"] = "v0.4.57"
    payload["diagnostic"] = "unrestricted_source_zero_dsec_acceptance"
    payload["unrestricted_source_semantic_acceptance_ready"] = bool(
        payload.get("python_dsec_converged")
        and payload.get("evaluation_count_ready")
        and payload.get("branch_trajectory_ready")
        and payload.get("thermal_trajectory_ready")
        and payload.get("evaluation2_internal_ready")
        and payload.get("post_dsec_calc_hmc_all_executed")
        and payload.get("final_fixed_state_parity_ready")
        and payload.get("frozen_v0444_complete_fixed_state_regression")
    )
    payload["ready_to_advance_to_bremsmap"] = payload[
        "unrestricted_source_semantic_acceptance_ready"
    ]
    payload["diagnostic_conclusion"] = _classify(payload)

    json_path = out / "xstar_dsec_source_zero_unrestricted_summary.json"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    eval_path = out / "xstar_dsec_source_zero_unrestricted_evaluations.csv"
    eval_fields = (
        "evaluation_index",
        "ready",
        "n_failed_quantities",
        "failed_quantities",
        "max_relative_difference",
        "max_absolute_difference",
    )
    with eval_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=eval_fields)
        writer.writeheader()
        for row in payload.get("thermal_evaluations", []):
            item = dict(row)
            item["failed_quantities"] = json.dumps(item.get("failed_quantities", []))
            writer.writerow({name: item.get(name) for name in eval_fields})

    failure_path = out / "xstar_dsec_source_zero_unrestricted_runtime_failures.csv"
    failure_fields = (
        "event_index",
        "event",
        "quantity",
        "python_value",
        "xstar_value",
        "absolute_difference",
        "relative_difference",
    )
    with failure_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=failure_fields)
        writer.writeheader()
        for row in payload.get("runtime_failures", []):
            writer.writerow({name: row.get(name) for name in failure_fields})

    lines = [
        "# Unrestricted source-zero `dsec` acceptance",
        "",
        f"- Diagnostic conclusion: `{payload['diagnostic_conclusion']}`",
        f"- Source-semantic acceptance: `{payload['unrestricted_source_semantic_acceptance_ready']}`",
        f"- Ready to advance to `bremsmap`: `{payload['ready_to_advance_to_bremsmap']}`",
        f"- Python converged: `{payload.get('python_dsec_converged')}`",
        f"- Evaluation count: `{payload.get('python_evaluation_count')}` / `{payload.get('xstar_evaluation_count')}`",
        f"- Strict trajectory parity: `{payload.get('strict_trajectory_ready')}`",
        f"- Branch/residual trajectory parity: `{payload.get('branch_trajectory_ready')}`",
        f"- Thermal trajectory parity: `{payload.get('thermal_trajectory_ready')}`",
        f"- Evaluation-2 internal parity: `{payload.get('evaluation2_internal_ready')}`",
        f"- Final fixed-state parity: `{payload.get('final_fixed_state_parity_ready')}`",
        f"- Natural evaluation-2 strict transition arrays: `{payload.get('transition_state_ready')}`",
        f"- Runtime rows outside strict tolerance: `{len(payload.get('runtime_failures', []))}`",
        "",
        "| Evaluation | Thermal ready | Failed quantities | Max relative difference |",
        "|---:|---|---:|---:|",
    ]
    for row in payload.get("thermal_evaluations", []):
        lines.append(
            f"| {row['evaluation_index']} | {row['ready']} | "
            f"{row['n_failed_quantities']} | {row['max_relative_difference']:.9g} |"
        )
    markdown_path = out / "xstar_dsec_source_zero_unrestricted_summary.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "evaluations_csv": eval_path,
        "runtime_failures_csv": failure_path,
        "json": json_path,
        "markdown": markdown_path,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the unrestricted source-zero physical dsec solve through natural "
            "convergence, compare all captured evaluations, execute the post-dsec "
            "calc_hmc_all call, and report strict and source-semantic acceptance "
            "separately."
        )
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    known, _unknown = parser.parse_known_args(raw)
    out = Path(known.out_dir)
    passthrough = _clean_passthrough(raw)
    run_out = out / "unrestricted_source_zero"
    run_args = [
        *passthrough,
        "--out-dir",
        str(run_out),
        "--global-writeback-mode",
        "dense-source",
        "--leveltemp-lifecycle",
        "reset-per-call",
        "--terminal-continuum-seed-mode",
        "source-zero",
        "--transition-input-mode",
        "compare-only",
        "--compare-transition-internals",
        "--transition-internal-evaluation-index",
        "2",
    ]
    physical_exit_code = int(physical_main(run_args))

    runner = _read_json(run_out / "xstar_dsec_physical_runner_summary.json")
    trajectory = _read_json(run_out / "xstar_dsec_trajectory_parity_summary.json")
    python_trajectory = _read_json(run_out / "xstar_dsec_python_trajectory_summary.json")
    thermal = _read_json(run_out / "xstar_dsec_thermal_decomposition_parity_summary.json")
    transition = _read_json(run_out / "xstar_dsec_transition_state_parity_summary.json")
    internal = _read_json(
        run_out
        / "evaluation_internal_parity"
        / "xstar_calc_hmc_all_pre_continuum_parity_summary.json"
    )
    final = _read_json(
        run_out / "xstar_calc_hmc_all_complete_fixed_state_parity_summary.json"
    )
    strict_acceptance = _read_json(run_out / "xstar_dsec_v0445_acceptance_summary.json")

    runtime_failures = _runtime_failures(run_out / "xstar_dsec_trajectory_parity.csv")
    thermal_evaluations = _thermal_by_evaluation(
        run_out / "xstar_dsec_thermal_decomposition_parity.csv"
    )
    python_count = int(thermal.get("n_python_evaluations", runner.get("python_ntotit", -1)))
    xstar_count = int(thermal.get("n_xstar_evaluations", -1))
    payload: Dict[str, Any] = {
        "physical_exit_code": physical_exit_code,
        "python_dsec_converged": python_trajectory.get("dsec_converged") is True,
        "python_charge_converged": python_trajectory.get("charge_converged") is True,
        "python_thermal_converged": python_trajectory.get("thermal_converged") is True,
        "python_prefix_terminated": python_trajectory.get("prefix_terminated") is True,
        "exact_source_control_flow": python_trajectory.get("exact_source_control_flow") is True,
        "python_ntotit": python_trajectory.get("ntotit"),
        "python_evaluation_count": python_count,
        "xstar_evaluation_count": xstar_count,
        "evaluation_count_ready": bool(
            python_count == xstar_count
            and python_count == int(python_trajectory.get("ntotit", -2))
            and python_count > 4
        ),
        "strict_trajectory_ready": trajectory.get("dsec_trajectory_parity_ready") is True,
        "branch_trajectory_ready": _branch_trajectory_ready(trajectory),
        "thermal_trajectory_ready": thermal.get("dsec_thermal_parity_ready") is True,
        "runtime_state_ready": trajectory.get("runtime_state_ready") is True,
        "runtime_failures": runtime_failures,
        "thermal_evaluations": thermal_evaluations,
        "transition_state_ready": transition.get("dsec_transition_state_ready") is True,
        "transition_runtime_state_ready": transition.get("runtime_state_ready") is True,
        "transition_radiation_state_ready": transition.get("radiation_state_ready") is True,
        "transition_escape_state_ready": transition.get("escape_state_ready") is True,
        "transition_continuum_workspace_ready": transition.get("continuum_workspace_ready") is True,
        "transition_global_mapping_ready": transition.get("global_mapping_ready") is True,
        "transition_leveltemp_source_used_slots_ready": (
            transition.get("leveltemp_source_used_slots_ready") is True
        ),
        "evaluation2_internal_ready": _internal_evaluation2_ready(internal),
        "evaluation2_pre_matrix_ready": internal.get("pre_matrix_ready") is True,
        "evaluation2_active_matrix_closure_ready": (
            internal.get("same_call_matrix_active_closure_ready") is True
        ),
        "evaluation2_initial_solver_population_ready": (
            internal.get("initial_solver_population_ready") is True
        ),
        "evaluation2_final_active_population_ready": (
            internal.get("final_solver_active_population_ready") is True
        ),
        "evaluation2_final_outer_start_ready": (
            internal.get("final_solver_outer_start_ready") is True
        ),
        "evaluation2_source_xtot_ready": (
            internal.get("final_solver_source_xtot_ready") is True
        ),
        "evaluation2_thermal_family_ready": internal.get("thermal_family_ready") is True,
        "evaluation2_element_array_ready": internal.get("element_array_ready") is True,
        "post_dsec_calc_hmc_all_executed": final.get("calc_hmc_all_call_id") is not None,
        "final_fixed_state_parity_ready": final.get("complete_fixed_state_parity_ready") is True,
        "final_fixed_state_max_relative_difference": final.get("max_relative_difference"),
        "frozen_v0444_complete_fixed_state_regression": (
            runner.get("frozen_v0444_complete_fixed_state_regression") is True
        ),
        "legacy_strict_acceptance_ready": (
            strict_acceptance.get("v0445_bounded_dsec_acceptance_ready") is True
        ),
        "python_final_temperature_t4": python_trajectory.get("final_temperature_t4"),
        "python_final_electron_fraction_xee": python_trajectory.get(
            "final_electron_fraction_xee"
        ),
        "python_final_hmctot": python_trajectory.get("final_hmctot"),
        "python_final_elcter": python_trajectory.get("final_elcter"),
    }
    products = _write_products(out, payload)
    summary = _read_json(products["json"])

    if known.print_summary:
        print("Unrestricted source-zero dsec acceptance")
        print("-----------------------------------------")
        print(f"physical_exit_code={physical_exit_code}")
        print(f"python_dsec_converged={summary['python_dsec_converged']}")
        print(f"python_ntotit={summary['python_ntotit']}")
        print(f"xstar_evaluation_count={summary['xstar_evaluation_count']}")
        print(f"strict_trajectory_ready={summary['strict_trajectory_ready']}")
        print(f"branch_trajectory_ready={summary['branch_trajectory_ready']}")
        print(f"thermal_trajectory_ready={summary['thermal_trajectory_ready']}")
        print(f"evaluation2_internal_ready={summary['evaluation2_internal_ready']}")
        print(f"final_fixed_state_parity_ready={summary['final_fixed_state_parity_ready']}")
        print(
            "unrestricted_source_semantic_acceptance_ready="
            f"{summary['unrestricted_source_semantic_acceptance_ready']}"
        )
        print(f"ready_to_advance_to_bremsmap={summary['ready_to_advance_to_bremsmap']}")
        print(f"diagnostic_conclusion={summary['diagnostic_conclusion']}")
        for name, path in products.items():
            print(f"{name}={path}")

    return 0 if summary["unrestricted_source_semantic_acceptance_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
