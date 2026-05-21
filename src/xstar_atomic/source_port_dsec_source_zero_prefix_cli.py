"""Natural four-evaluation dsec prefix after the source terminal-zero correction."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .source_port_dsec_physical_cli import main as physical_main

_DERIVED_BRACKET_FIELDS = frozenset({"elctrl", "elctrh", "hmcttl", "hmctth"})


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
    return json.loads(path.read_text(encoding="utf-8"))


def _read_rows(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _false_runtime_rows(path: Path) -> List[Dict[str, Any]]:
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
    """Whether source branches/residual decisions match, independent of bitwise work bounds."""
    return bool(
        summary.get("event_sequence_ready")
        and summary.get("integer_control_state_ready")
        and summary.get("thermal_residual_value_ready")
        and summary.get("thermal_residual_sign_ready")
        and summary.get("charge_residual_value_ready")
        and summary.get("charge_residual_sign_ready")
        and summary.get("final_state_ready")
    )


def _derived_bracket_drift_only(failures: Sequence[Mapping[str, Any]]) -> bool:
    return bool(failures) and all(
        str(row.get("quantity")) in _DERIVED_BRACKET_FIELDS for row in failures
    )


def _thermal_by_evaluation(path: Path) -> List[Dict[str, Any]]:
    rows = _read_rows(path)
    grouped: Dict[int, List[Dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(int(row["evaluation_index"]), []).append(row)
    out: List[Dict[str, Any]] = []
    for evaluation_index in sorted(grouped):
        items = grouped[evaluation_index]
        failed = [
            row for row in items
            if str(row.get("within_tolerance", "")).strip().lower() != "true"
        ]
        max_rel = max((float(row["relative_difference"]) for row in items), default=0.0)
        max_abs = max((float(row["absolute_difference"]) for row in items), default=0.0)
        out.append(
            {
                "evaluation_index": evaluation_index,
                "ready": not failed,
                "n_failed_quantities": len(failed),
                "failed_quantities": [row["quantity"] for row in failed],
                "max_relative_difference": max_rel,
                "max_absolute_difference": max_abs,
            }
        )
    return out


def _classify(payload: Mapping[str, Any]) -> str:
    if payload.get("branch_trajectory_ready") is not True:
        return "source_zero_natural_prefix_control_path_mismatch"
    if payload.get("thermal_prefix_ready") is not True:
        return "source_zero_natural_prefix_thermal_mismatch"
    for key, label in (
        ("initial_solver_population_ready", "solver_entry"),
        ("final_solver_active_population_ready", "solver_output"),
        ("thermal_family_ready", "thermal_family"),
        ("element_array_ready", "element_accumulation"),
    ):
        if payload.get(key) is not True:
            return f"source_zero_natural_evaluation2_{label}_mismatch"
    if payload.get("transition_state_ready") is not True:
        return "source_zero_four_evaluation_prefix_ready_transition_arrays_not_strict"
    if payload.get("strict_trajectory_ready") is True:
        return "source_zero_four_evaluation_prefix_strict_ready"
    if payload.get("derived_bracket_drift_only") is True:
        return "source_zero_four_evaluation_prefix_ready_with_derived_bracket_roundoff"
    return "source_zero_four_evaluation_prefix_ready_with_runtime_roundoff"


def _write_products(out: Path, payload: Dict[str, Any]) -> Dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["port_version"] = "v0.4.56"
    payload["diagnostic"] = "natural_source_zero_four_evaluation_prefix"
    payload["diagnostic_conclusion"] = _classify(payload)
    payload["bounded_four_evaluation_acceptance_ready"] = bool(
        payload.get("branch_trajectory_ready")
        and payload.get("thermal_prefix_ready")
        and payload.get("initial_solver_population_ready")
        and payload.get("final_solver_active_population_ready")
        and payload.get("thermal_family_ready")
        and payload.get("element_array_ready")
    )

    json_path = out / "xstar_dsec_source_zero_prefix_summary.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    eval_rows = payload.get("thermal_evaluations", [])
    csv_path = out / "xstar_dsec_source_zero_prefix_evaluations.csv"
    fields = (
        "evaluation_index", "ready", "n_failed_quantities", "failed_quantities",
        "max_relative_difference", "max_absolute_difference",
    )
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in eval_rows:
            item = dict(row)
            item["failed_quantities"] = json.dumps(item.get("failed_quantities", []))
            writer.writerow({name: item.get(name) for name in fields})

    lines = [
        "# Natural source-zero four-evaluation `dsec` prefix",
        "",
        f"- Diagnostic conclusion: `{payload['diagnostic_conclusion']}`",
        f"- Bounded four-evaluation acceptance: `{payload['bounded_four_evaluation_acceptance_ready']}`",
        f"- Strict trajectory parity: `{payload.get('strict_trajectory_ready')}`",
        f"- Branch/residual trajectory parity: `{payload.get('branch_trajectory_ready')}`",
        f"- Derived bracket drift only: `{payload.get('derived_bracket_drift_only')}`",
        f"- Natural evaluation-2 transition state: `{payload.get('transition_state_ready')}`",
        f"- Evaluation-2 initial solver population: `{payload.get('initial_solver_population_ready')}`",
        f"- Evaluation-2 final active population: `{payload.get('final_solver_active_population_ready')}`",
        f"- Evaluation-2 thermal families: `{payload.get('thermal_family_ready')}`",
        f"- Evaluation-2 element arrays: `{payload.get('element_array_ready')}`",
        "",
        "| Evaluation | Thermal ready | Failed quantities | Max relative difference |",
        "|---:|---|---:|---:|",
    ]
    for row in eval_rows:
        lines.append(
            f"| {row['evaluation_index']} | {row['ready']} | "
            f"{row['n_failed_quantities']} | {row['max_relative_difference']:.9g} |"
        )
    md_path = out / "xstar_dsec_source_zero_prefix_summary.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "markdown": md_path}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run four natural dsec calc_hmc_all evaluations with the source terminal "
            "continuum zero seed, while comparing the natural evaluation-2 entry and "
            "same-call internals against the captured XSTAR state."
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
    run_args = [
        *passthrough,
        "--out-dir", str(out / "natural_source_zero_prefix"),
        "--maximum-evaluations", "4",
        "--global-writeback-mode", "dense-source",
        "--leveltemp-lifecycle", "reset-per-call",
        "--terminal-continuum-seed-mode", "source-zero",
        "--transition-input-mode", "compare-only",
        "--compare-transition-internals",
        "--transition-internal-evaluation-index", "2",
    ]
    physical_exit_code = int(physical_main(run_args))
    run_out = out / "natural_source_zero_prefix"
    runner = _read_json(run_out / "xstar_dsec_physical_runner_summary.json")
    trajectory = _read_json(run_out / "xstar_dsec_trajectory_parity_summary.json")
    thermal = _read_json(run_out / "xstar_dsec_thermal_decomposition_parity_summary.json")
    transition = _read_json(run_out / "xstar_dsec_transition_state_parity_summary.json")
    internal = _read_json(
        run_out / "evaluation_internal_parity" /
        "xstar_calc_hmc_all_pre_continuum_parity_summary.json"
    )
    runtime_failures = _false_runtime_rows(run_out / "xstar_dsec_trajectory_parity.csv")
    thermal_evaluations = _thermal_by_evaluation(
        run_out / "xstar_dsec_thermal_decomposition_parity.csv"
    )

    payload: Dict[str, Any] = {
        "physical_exit_code": physical_exit_code,
        "strict_trajectory_ready": trajectory.get("dsec_trajectory_parity_ready") is True,
        "branch_trajectory_ready": _branch_trajectory_ready(trajectory),
        "runtime_state_ready": trajectory.get("runtime_state_ready") is True,
        "runtime_failures": runtime_failures,
        "derived_bracket_drift_only": _derived_bracket_drift_only(runtime_failures),
        "thermal_prefix_ready": thermal.get("dsec_thermal_parity_ready") is True,
        "thermal_evaluations": thermal_evaluations,
        "transition_state_ready": transition.get("dsec_transition_state_ready") is True,
        "transition_runtime_state_ready": transition.get("runtime_state_ready") is True,
        "transition_global_xilevg_ready": transition.get("global_xilevg_ready") is True,
        "transition_global_bilevg_ready": transition.get("global_bilevg_ready") is True,
        "transition_global_rnisg_ready": transition.get("global_rnisg_ready") is True,
        "transition_leveltemp_ready": transition.get("leveltemp_source_used_slots_ready") is True,
        "pre_matrix_ready": internal.get("pre_matrix_ready") is True,
        "same_call_matrix_active_closure_ready": (
            internal.get("same_call_matrix_active_closure_ready") is True
        ),
        "initial_solver_population_ready": (
            internal.get("initial_solver_population_ready") is True
        ),
        "final_solver_active_population_ready": (
            internal.get("final_solver_active_population_ready") is True
        ),
        "final_solver_outer_start_ready": (
            internal.get("final_solver_outer_start_ready") is True
        ),
        "final_solver_source_xtot_ready": (
            internal.get("final_solver_source_xtot_ready") is True
        ),
        "thermal_family_ready": internal.get("thermal_family_ready") is True,
        "element_array_ready": internal.get("element_array_ready") is True,
        "frozen_v0444_complete_fixed_state_regression": (
            runner.get("frozen_v0444_complete_fixed_state_regression") is True
        ),
        "python_ntotit": runner.get("python_ntotit"),
        "python_prefix_terminated": runner.get("python_prefix_terminated"),
    }
    products = _write_products(out, payload)

    if known.print_summary:
        summary = _read_json(products["json"])
        print("Natural source-zero four-evaluation dsec prefix")
        print("------------------------------------------------")
        print(f"physical_exit_code={physical_exit_code}")
        print(f"strict_trajectory_ready={summary['strict_trajectory_ready']}")
        print(f"branch_trajectory_ready={summary['branch_trajectory_ready']}")
        print(f"derived_bracket_drift_only={summary['derived_bracket_drift_only']}")
        print(f"thermal_prefix_ready={summary['thermal_prefix_ready']}")
        print(f"transition_state_ready={summary['transition_state_ready']}")
        print(f"initial_solver_population_ready={summary['initial_solver_population_ready']}")
        print(f"final_solver_active_population_ready={summary['final_solver_active_population_ready']}")
        print(f"bounded_four_evaluation_acceptance_ready={summary['bounded_four_evaluation_acceptance_ready']}")
        print(f"diagnostic_conclusion={summary['diagnostic_conclusion']}")
        for name, path in products.items():
            print(f"{name}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
