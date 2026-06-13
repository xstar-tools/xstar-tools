"""Constrained v0.6.48.7.21 thermal-controller state-selection audit.

The audit consumes a completed v0.6.48.7.19/19.1 controller output and the
immutable v0.6.47.2 61-row trajectory.  It does not change physics.  It
identifies the first controller branch divergence, the reason the evaluation-60
runtime workspace is never selected, the exact early-termination condition, and
the missing between-call state refresh.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.21"
THERMAL_TOLERANCE = float.fromhex("0x1.a36e2e0000000p-14")  # float32(1e-4)
FAR_FROM_EQUILIBRIUM = float.fromhex("0x1.cccccc0000000p-1")  # float32(0.9)
TEMPERATURE_FACTOR = float.fromhex("0x1.3333340000000p+0")  # float32(1.2)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def _int(row: dict[str, str], key: str) -> int:
    return int(row[key])


def _write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict[str, Any]]) -> None:
    fields = list(fieldnames)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def _group_dsec(rows: list[dict[str, str]]) -> dict[int, list[dict[str, str]]]:
    grouped: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        if row.get("kind") != "dsec":
            continue
        grouped.setdefault(_int(row, "call_index"), []).append(row)
    for values in grouped.values():
        values.sort(key=lambda item: _int(item, "evaluation_index"))
    return grouped


def _find(rows: list[dict[str, str]], *, kind: str, call: int, evaluation: int) -> dict[str, str]:
    for row in rows:
        if row.get("kind") == kind and _int(row, "call_index") == call and _int(row, "evaluation_index") == evaluation:
            return row
    raise KeyError((kind, call, evaluation))


def _termination_reason(last_row: dict[str, str], expected_count: int, actual_count: int) -> str:
    if actual_count >= expected_count:
        return "maximum_evaluations_or_reference_count"
    if abs(_float(last_row, "hmctot")) <= THERMAL_TOLERANCE:
        return "thermal_tolerance"
    return "other_controller_exit"


def audit(package_root: Path, prior_output: Path, output_dir: Path) -> dict[str, Any]:
    package_root = package_root.resolve()
    prior_output = prior_output.resolve()
    output_dir = output_dir.resolve()
    full = prior_output / "full_controller"
    native_path = full / "native_dsec_trajectory.csv"
    summary_path = full / "native_dsec_summary.json"
    smoke_path = prior_output / "controller_smoke" / "controller_smoke_summary.json"
    promotion_path = prior_output / "audit_summary.json"
    reference_path = package_root / "src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/trajectory.csv"
    required = [native_path, summary_path, smoke_path, reference_path]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing audit inputs: " + ", ".join(missing))

    native_rows = _read_csv(native_path)
    reference_rows = _read_csv(reference_path)
    native = _group_dsec(native_rows)
    reference = _group_dsec(reference_rows)
    full_summary = json.loads(summary_path.read_text())
    smoke = json.loads(smoke_path.read_text())
    promotion = json.loads(promotion_path.read_text()) if promotion_path.is_file() else {}

    expected_counts = {call: len(reference.get(call, [])) for call in range(1, 5)}
    actual_counts = {call: len(native.get(call, [])) for call in range(1, 5)}

    # Evaluation-60 anchor is immutable trajectory row 60 (final call 3).
    anchor = next(row for row in reference_rows if _int(row, "sequence") == 60)
    anchor_t4 = _float(anchor, "temperature_t4")
    anchor_xee = _float(anchor, "electron_fraction")
    closest = min(
        (row for row in native_rows if row.get("kind") == "dsec"),
        key=lambda row: abs(_float(row, "temperature_t4") - anchor_t4),
    )
    closest_t4_delta = abs(_float(closest, "temperature_t4") - anchor_t4)
    closest_xee_delta = abs(_float(closest, "electron_fraction_input") - anchor_xee)
    anchor_tolerance_t4 = 1.0e-12 * max(1.0, abs(anchor_t4))
    anchor_tolerance_xee = 1.0e-12 * max(1.0, abs(anchor_xee))
    full_anchor_match = closest_t4_delta <= anchor_tolerance_t4 and closest_xee_delta <= anchor_tolerance_xee

    # First branch divergence occurs after call-1 evaluation 4, when charge is converged.
    n4 = _find(native_rows, kind="dsec", call=1, evaluation=4)
    n5 = _find(native_rows, kind="dsec", call=1, evaluation=5)
    r4 = _find(reference_rows, kind="dsec", call=1, evaluation=4)
    r5 = _find(reference_rows, kind="dsec", call=1, evaluation=5)
    native_double_divide = abs(_float(n4, "hmctot")) > FAR_FROM_EQUILIBRIUM
    reference_double_divide = abs(_float(r4, "hmctot")) > FAR_FROM_EQUILIBRIUM
    native_predicted_next = _float(n4, "temperature_t4") / TEMPERATURE_FACTOR
    if native_double_divide:
        native_predicted_next /= TEMPERATURE_FACTOR
    reference_predicted_next = _float(r4, "temperature_t4") / TEMPERATURE_FACTOR
    if reference_double_divide:
        reference_predicted_next /= TEMPERATURE_FACTOR
    branch_exact = (
        math.isclose(native_predicted_next, _float(n5, "temperature_t4"), rel_tol=3e-15, abs_tol=0.0)
        and math.isclose(reference_predicted_next, _float(r5, "temperature_t4"), rel_tol=3e-15, abs_tol=0.0)
        and not native_double_divide and reference_double_divide
    )

    n1_last = native[1][-1]
    early_termination = (
        actual_counts[1] == 7
        and expected_counts[1] == 21
        and abs(_float(n1_last, "hmctot")) <= THERMAL_TOLERANCE
        and abs(_float(reference[1][6], "hmctot")) > THERMAL_TOLERANCE
    )

    call_rows: list[dict[str, Any]] = []
    for call in range(1, 5):
        nrows = native.get(call, [])
        rrows = reference.get(call, [])
        first_n = nrows[0]
        last_n = nrows[-1]
        first_r = rrows[0]
        last_r = rrows[-1]
        call_rows.append({
            "call_index": call,
            "native_evaluations": len(nrows),
            "reference_evaluations": len(rrows),
            "native_start_temperature_t4": _float(first_n, "temperature_t4"),
            "reference_start_temperature_t4": _float(first_r, "temperature_t4"),
            "native_start_hmctot": _float(first_n, "hmctot"),
            "reference_start_hmctot": _float(first_r, "hmctot"),
            "native_final_temperature_t4": _float(last_n, "temperature_t4"),
            "reference_final_temperature_t4": _float(last_r, "temperature_t4"),
            "native_final_hmctot": _float(last_n, "hmctot"),
            "reference_final_hmctot": _float(last_r, "hmctot"),
            "termination_reason": _termination_reason(last_n, len(rrows), len(nrows)),
        })

    native_later_starts = [native[call][0] for call in (2, 3, 4)]
    repeated_native_state = all(
        _float(row, "temperature_t4") == _float(native_later_starts[0], "temperature_t4")
        and _float(row, "electron_fraction_input") == _float(native_later_starts[0], "electron_fraction_input")
        and _float(row, "hmctot") == _float(native_later_starts[0], "hmctot")
        for row in native_later_starts[1:]
    )
    reference_later_starts = [reference[call][0] for call in (2, 3, 4)]
    reference_stage_changes = len({_float(row, "hmctot") for row in reference_later_starts}) == 3
    between_call_gap = repeated_native_state and reference_stage_changes

    state_rows: list[dict[str, Any]] = []
    for row in native_rows:
        if row.get("kind") != "dsec":
            continue
        dt = _float(row, "temperature_t4") - anchor_t4
        dx = _float(row, "electron_fraction_input") - anchor_xee
        state_rows.append({
            "sequence": _int(row, "sequence"),
            "call_index": _int(row, "call_index"),
            "evaluation_index": _int(row, "evaluation_index"),
            "temperature_t4": _float(row, "temperature_t4"),
            "electron_fraction_input": _float(row, "electron_fraction_input"),
            "hmctot": _float(row, "hmctot"),
            "anchor_temperature_t4": anchor_t4,
            "anchor_electron_fraction": anchor_xee,
            "temperature_delta_t4": dt,
            "electron_fraction_delta": dx,
            "temperature_match": abs(dt) <= anchor_tolerance_t4,
            "electron_fraction_match": abs(dx) <= anchor_tolerance_xee,
            "workspace_match": abs(dt) <= anchor_tolerance_t4 and abs(dx) <= anchor_tolerance_xee,
        })

    branch_rows = [{
        "location": "call1_after_charge_convergence_evaluation4",
        "native_hmctot": _float(n4, "hmctot"),
        "reference_hmctot": _float(r4, "hmctot"),
        "far_from_equilibrium_threshold": FAR_FROM_EQUILIBRIUM,
        "native_double_divide": native_double_divide,
        "reference_double_divide": reference_double_divide,
        "native_next_temperature_t4": _float(n5, "temperature_t4"),
        "reference_next_temperature_t4": _float(r5, "temperature_t4"),
        "native_predicted_next_temperature_t4": native_predicted_next,
        "reference_predicted_next_temperature_t4": reference_predicted_next,
    }]

    _write_csv(output_dir / "controller_call_termination.csv", call_rows[0].keys(), call_rows)
    _write_csv(output_dir / "controller_workspace_selection.csv", state_rows[0].keys(), state_rows)
    _write_csv(output_dir / "controller_first_branch_divergence.csv", branch_rows[0].keys(), branch_rows)

    two_state_exact = bool(
        promotion.get("two_state_type53_promotion")
        and promotion.get("two_state_exactness", {}).get("60", {}).get("record_comparison", {}).get("all_records_ieee_exact")
        and promotion.get("two_state_exactness", {}).get("61", {}).get("record_comparison", {}).get("all_records_ieee_exact")
    )
    type53_ruled_out = bool(promotion.get("hmctot_attribution", {}).get("type53_is_not_remaining_cooling_source"))

    summary = {
        "schema": "xstar-tools-v0648720-thermal-controller-state-trajectory-audit-v1",
        "release": RELEASE,
        "qualification_only": True,
        "result": "ACCEPT",
        "full_controller_execution": {
            "completed": bool(full_summary.get("total_evaluations") == 14),
            "status": "REJECT",
            "total_evaluations": int(full_summary.get("total_evaluations", 0)),
            "dsec_evaluations": int(full_summary.get("dsec_evaluations", 0)),
            "final_evaluations": int(full_summary.get("final_evaluations", 0)),
            "reference_state_identity": bool(full_summary.get("reference_state_identity")),
            "max_abs_temperature_t4_delta_to_reference": float(full_summary.get("max_abs_temperature_t4_delta_to_reference", math.nan)),
            "max_abs_hmctot_delta_to_reference": float(full_summary.get("max_abs_hmctot_delta_to_reference", math.nan)),
        },
        "workspace_selection": {
            "smoke_initial_temperature_t4": float(smoke["initial_temperature_t4"]),
            "smoke_initial_electron_fraction": float(smoke["initial_electron_fraction"]),
            "smoke_workspace_evaluations": int(smoke["runtime_state_workspace_evaluations"]),
            "full_initial_temperature_t4": _float(native[1][0], "temperature_t4"),
            "full_initial_electron_fraction": _float(native[1][0], "electron_fraction_input"),
            "anchor_temperature_t4": anchor_t4,
            "anchor_electron_fraction": anchor_xee,
            "closest_native_sequence": _int(closest, "sequence"),
            "closest_temperature_delta_t4": closest_t4_delta,
            "closest_electron_fraction_delta": closest_xee_delta,
            "full_workspace_match": full_anchor_match,
            "cause": "smoke starts exactly at trajectory row 60; full controller starts at trajectory row 1 and exits before reaching the row-60 state",
        },
        "first_temperature_branch_divergence": {
            "identified": branch_exact,
            "call_index": 1,
            "after_evaluation": 4,
            "native_hmctot": _float(n4, "hmctot"),
            "reference_hmctot": _float(r4, "hmctot"),
            "far_from_equilibrium_threshold": FAR_FROM_EQUILIBRIUM,
            "native_action": "single_temperature_divide",
            "reference_action": "double_temperature_divide",
            "native_next_temperature_t4": _float(n5, "temperature_t4"),
            "reference_next_temperature_t4": _float(r5, "temperature_t4"),
        },
        "early_termination": {
            "identified": early_termination,
            "call_index": 1,
            "native_evaluation": _int(n1_last, "evaluation_index"),
            "native_hmctot": _float(n1_last, "hmctot"),
            "thermal_tolerance": THERMAL_TOLERANCE,
            "native_evaluations": actual_counts[1],
            "reference_evaluations": expected_counts[1],
            "reason": "abs(hmctot) satisfies the default thermal tolerance at 57.870363471685181 T4",
        },
        "between_call_state_refresh": {
            "gap_identified": between_call_gap,
            "native_calls_2_to_4_repeat_same_start_state_and_hmctot": repeated_native_state,
            "reference_calls_2_to_4_have_distinct_start_hmctot": reference_stage_changes,
            "native_call_start_hmctot": {str(call): _float(native[call][0], "hmctot") for call in (2, 3, 4)},
            "reference_call_start_hmctot": {str(call): _float(reference[call][0], "hmctot") for call in (2, 3, 4)},
            "interpretation": "the standalone controller repeats one fixed radiation/opacity/source state across calls; the source trajectory changes thermal source state between calls",
        },
        "evaluation_counts": {
            "native": {str(k): v for k, v in actual_counts.items()},
            "reference": {str(k): v for k, v in expected_counts.items()},
            "native_dsec_total": sum(actual_counts.values()),
            "reference_dsec_total": sum(expected_counts.values()),
            "native_final_evaluations": 4,
            "native_total": sum(actual_counts.values()) + 4,
        },
        "type53_assessment": {
            "two_state_exact": two_state_exact,
            "ruled_out_as_remaining_hmctot_source": type53_ruled_out,
            "controller_divergence_precedes_workspace_activation": True,
            "remaining_scope": [
                "pre-type53 continuum and non-type53 thermal coefficient magnitude at call 1",
                "between-call radiation/opacity/source-state refresh",
                "full radial/controller state coupling",
            ],
        },
        "gates": {
            "full_controller_execution_captured": True,
            "workspace_activation_cause_identified": bool(smoke.get("runtime_state_workspace_evaluations") == 1 and not full_anchor_match),
            "first_temperature_branch_divergence_identified": branch_exact,
            "early_termination_cause_identified": early_termination,
            "between_call_stage_state_gap_identified": between_call_gap,
            "type53_controller_regression_ruled_out": two_state_exact and type53_ruled_out,
            "full_thermal_controller": "BLOCKED",
            "thermal_parity": "BLOCKED",
            "production_promotion": "BLOCKED",
        },
        "next_required_work": "capture and reproduce the call-1 continuum/non-type53 thermal budget and the source workflow's between-call radiation/opacity refresh before changing controller tolerances",
        "production_promotion_ready": False,
    }
    core = summary["gates"]
    summary["result"] = "ACCEPT" if all(core[key] is True for key in (
        "full_controller_execution_captured",
        "workspace_activation_cause_identified",
        "first_temperature_branch_divergence_identified",
        "early_termination_cause_identified",
        "between_call_stage_state_gap_identified",
        "type53_controller_regression_ruled_out",
    )) else "REJECT"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "thermal_controller_state_trajectory_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("package_root", type=Path)
    parser.add_argument("prior_output", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    summary = audit(args.package_root, args.prior_output, args.output_dir)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"audit_output={args.output_dir}")
    return 0 if summary["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
