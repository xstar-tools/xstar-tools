"""Sequence-level resumable native replay for v0.6.48.7.46.20.1."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path
from typing import Any

from .all61_thermal_state_consumption_audit import COMMITTED_NATIVE_FIELD, COMPONENT_FIELDS

RELEASE = "0.6.48.7.46.20.1"
SCHEMA = "xstar-tools-v06487461212-native-replay-resume-manifest-v1"
MANIFEST_NAME = "v048746121_native_replay_resume_manifest.json"
PLAN_NAME = "all61_native_replay_resume_plan.tsv"
REQUIRED_EVALUATION_FILES = (
    "native_evaluation_summary.json",
    "native_evaluation.csv",
    "native_evaluation_populations.csv",
    "native_thermal_budget.csv",
    "native_evaluation_spectra.csv",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _bits(value: str | float) -> bytes:
    return struct.pack(">d", float(value))


def _exact(left: str | float, right: str | float) -> bool:
    try:
        a = float(left)
        b = float(right)
    except Exception:
        return False
    return math.isfinite(a) and math.isfinite(b) and _bits(a) == _bits(b)


def _scalar_values(canonical_closure: Path, sequence: int) -> dict[str, str]:
    path = canonical_closure / f"sequence_{sequence:04d}_scalars.csv"
    rows = _read_csv(path)
    values = {row["field"]: row["source_value"] for row in rows}
    if set(values) != {"computed_electron_fraction", "charge_residual"}:
        raise ValueError(f"invalid canonical scalar closure: {path}")
    return values


def _thermal_values(thermal_closure: Path, sequence: int) -> dict[str, str]:
    path = thermal_closure / f"sequence_{sequence:04d}_thermal.csv"
    rows = _read_csv(path)
    if len(rows) != 1:
        raise ValueError(f"invalid thermal closure: {path}")
    return rows[0]


def _compact_values(compact_closure: Path, sequence: int) -> list[dict[str, str]]:
    path = compact_closure / f"sequence_{sequence:04d}_thermal_compact_populations.csv"
    rows = _read_csv(path)
    rows.sort(key=lambda row: (int(row["element_z"]), int(row["compact_row"])))
    if not rows:
        raise ValueError(f"invalid thermal compact-population closure: {path}")
    return rows


def _plan_rows(source_inputs: Path, trajectory: Path, workspaces: Path) -> list[dict[str, Any]]:
    inputs = _read_csv(source_inputs)
    trajectories = _read_csv(trajectory)
    if len(inputs) != 61 or len(trajectories) != 61:
        raise ValueError("expected 61 source and trajectory rows")
    rows: list[dict[str, Any]] = []
    for expected, (row, traj) in enumerate(zip(inputs, trajectories), 1):
        identity = (int(row["sequence"]), row["kind"], int(row["dsec_call_id"]), int(row["evaluation_index"]))
        target = (expected, traj["kind"], int(traj["call_index"]), int(traj["evaluation_index"]))
        if identity != target:
            raise ValueError(f"sequence mismatch {identity} != {target}")
        rows.append({
            "sequence": expected,
            "kind": row["kind"],
            "call_id": int(row["dsec_call_id"]),
            "evaluation_index": int(row["evaluation_index"]),
            "temperature_k": row["temperature_k"],
            "covering_fraction": row["covering_fraction"],
            "workspace": str(workspaces / f"evaluation_{expected:04d}"),
        })
    return rows


def validate_evaluation(
    evaluation_dir: Path,
    plan: dict[str, Any],
    canonical_closure: Path,
    thermal_closure: Path,
    compact_closure: Path | None = None,
    require_thermal_diagonal_ledger: bool = False,
    require_continuum_workspace: bool = False,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    required_files = list(REQUIRED_EVALUATION_FILES)
    if compact_closure is not None:
        required_files.append("native_thermal_compact_populations.csv")
    if require_thermal_diagonal_ledger:
        required_files.append("native_thermal_diagonal_ledger.csv")
    if require_continuum_workspace:
        required_files.append("native_continuum_workspace.csv")
    for name in required_files:
        path = evaluation_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            reasons.append(f"missing:{name}")
    if reasons:
        return False, reasons

    sequence = int(plan["sequence"])
    scalars = _scalar_values(canonical_closure, sequence)
    thermal = _thermal_values(thermal_closure, sequence)
    try:
        summary = json.loads((evaluation_dir / "native_evaluation_summary.json").read_text())
        state_rows = _read_csv(evaluation_dir / "native_evaluation.csv")
        budget_rows = _read_csv(evaluation_dir / "native_thermal_budget.csv")
    except Exception as exc:
        return False, [f"parse:{exc}"]
    if len(state_rows) != 1:
        reasons.append(f"state_rows:{len(state_rows)}")
    if len(budget_rows) != 1:
        reasons.append(f"thermal_rows:{len(budget_rows)}")
    if reasons:
        return False, reasons
    state = state_rows[0]
    budget = budget_rows[0]

    expected_identity = (
        sequence,
        str(plan["kind"]),
        int(plan["call_id"]),
        int(plan["evaluation_index"]),
    )
    state_identity = (
        int(state["sequence"]),
        state["kind"],
        int(state["call_index"]),
        int(state["evaluation_index"]),
    )
    # Each run-fixed-evaluation process writes a local one-process Thermal
    # sequence ordinal of 1.  The aggregate stage canonicalizes it from the
    # source plan, so resume validation keys the local ledger by call/evaluation.
    budget_identity = (
        int(budget["call_index"]),
        int(budget["evaluation_index"]),
    )
    if state_identity != expected_identity:
        reasons.append(f"state_identity:{state_identity}")
    if budget_identity != (int(plan["call_id"]), int(plan["evaluation_index"])):
        reasons.append(f"budget_identity:{budget_identity}")
    if int(summary.get("trajectory_row", -1)) != sequence:
        reasons.append("summary_sequence")
    if int(summary.get("evaluation_index", -1)) != int(plan["evaluation_index"]):
        reasons.append("summary_evaluation")
    if int(summary.get("call_index", -1)) != int(plan["call_id"]):
        reasons.append("summary_call")
    if int(summary.get("python_callbacks", -1)) != 0:
        reasons.append("python_callbacks")
    if summary.get("replay_workspace_applied") is not True:
        reasons.append("workspace_not_applied")
    if budget.get("thermal_component_closure_applied") != "1":
        reasons.append("thermal_closure_not_applied")
    if compact_closure is None:
        if budget.get("thermal_consumed_fixed_state_closure") != "1":
            reasons.append("fixed_state_not_consumed")
    elif budget.get("thermal_consumed_compact_population_closure") != "1":
        reasons.append("compact_population_closure_not_consumed")

    exact_checks = [
        ("summary_electron_fraction", summary.get("native_electron_fraction"), scalars["computed_electron_fraction"]),
        ("summary_charge_residual", summary.get("native_charge_residual"), scalars["charge_residual"]),
        # reference_charge_residual and reference_hmctot in the standalone
        # summary are historical trajectory-oracle metadata.  The canonical
        # v46.12.1 scalar/Thermal closures supersede those embedded values,
        # especially for the four final-call evaluations.  Resume acceptance
        # therefore validates the native result against the canonical closure
        # and does not require the historical reference fields to match it.
        ("summary_hmctot", summary.get("native_hmctot"), thermal["hmctot"]),
        ("state_electron_fraction", state.get("native_electron_fraction"), scalars["computed_electron_fraction"]),
        ("state_charge_residual", state.get("native_charge_residual"), scalars["charge_residual"]),
        ("state_hmctot", state.get("native_hmctot"), thermal["hmctot"]),
        ("budget_charge_residual", budget.get("charge_residual"), scalars["charge_residual"]),
        ("budget_hmctot", budget.get("hmctot"), thermal["hmctot"]),
    ]
    for label, observed, expected in exact_checks:
        if observed is None or not _exact(observed, expected):
            reasons.append(label)

    for field in (name for name in COMPONENT_FIELDS if name in thermal):
        native_field = COMMITTED_NATIVE_FIELD.get(field, field)
        if native_field not in budget or not _exact(budget[native_field], thermal[field]):
            reasons.append(f"component:{field}")
            if len(reasons) >= 25:
                break

    if require_continuum_workspace:
        if budget.get("continuum_workspace_source_faithful") != "1":
            reasons.append("continuum_workspace_not_source_faithful")
        for field in ("continuum_epim_count", "continuum_bremsam_count", "continuum_bremsmap_count"):
            if budget.get(field) != "999":
                reasons.append(f"{field}:{budget.get(field)}")
        continuum_rows = _read_csv(evaluation_dir / "native_continuum_workspace.csv")
        required_columns = {
            "reduced_bin_one_based", "full_bin_one_based", "epim_ev", "bremsam",
            "bin_width_ev", "cmp1_contribution", "cmp2_contribution",
            "htcomp_contribution", "clcomp_contribution", "htfreef_contribution",
            "clbrems_contribution", "running_cmp1", "running_cmp2",
            "running_htcomp", "running_clcomp", "running_htfreef", "running_clbrems",
        }
        if len(continuum_rows) != 999:
            reasons.append(f"continuum_workspace_rows:{len(continuum_rows)}")
        elif not required_columns.issubset(continuum_rows[0]):
            reasons.append("continuum_workspace_schema")
        else:
            indices = [int(row["reduced_bin_one_based"]) for row in continuum_rows]
            mapped = [int(row["full_bin_one_based"]) for row in continuum_rows]
            if indices != list(range(1, 1000)):
                reasons.append("continuum_workspace_reduced_indices")
            if mapped != sorted(mapped) or min(mapped) < 1:
                reasons.append("continuum_workspace_bremsmap_indices")

    if require_thermal_diagonal_ledger:
        if budget.get("thermal_diagonal_source_domain_applied") != "1":
            reasons.append("thermal_diagonal_source_domain_not_applied")
        if budget.get("continuum_secondary_ledger_corrected") != "1":
            reasons.append("continuum_secondary_ledger_not_corrected")
        diagonal_rows = _read_csv(evaluation_dir / "native_thermal_diagonal_ledger.csv")
        required_columns = {
            "source_order_index", "source_position", "record", "data_type", "rate_type",
            "compact_row", "role", "is_normalization_row", "source_domain_included",
            "compact_population", "cj", "cj2", "heating_contribution", "cooling_contribution",
            "heating2_contribution", "cooling2_contribution",
        }
        if not diagonal_rows:
            reasons.append("thermal_diagonal_ledger_empty")
        elif not required_columns.issubset(diagonal_rows[0]):
            reasons.append("thermal_diagonal_ledger_schema")
        elif any(row.get("source_domain_included") != "1" for row in diagonal_rows):
            reasons.append("thermal_diagonal_source_domain_incomplete")
        else:
            by_element: dict[int, list[int]] = {}
            for row in diagonal_rows:
                by_element.setdefault(int(row["element_z"]), []).append(int(row["source_order_index"]))
            for element_z, indexes in by_element.items():
                if indexes != list(range(1, len(indexes) + 1)):
                    reasons.append(f"thermal_diagonal_source_order:{element_z}")
                    break

    if compact_closure is not None:
        expected_rows = _compact_values(compact_closure, sequence)
        native_rows = _read_csv(evaluation_dir / "native_thermal_compact_populations.csv")
        native_rows.sort(key=lambda row: (int(row["element_z"]), int(row["compact_row"])))
        if len(expected_rows) != len(native_rows):
            reasons.append(f"compact_population_rows:{len(native_rows)}")
        else:
            identity_fields = (
                "element_z", "active_min_stage", "active_max_stage", "compact_row", "ion",
                "ion_stage", "ion_charge", "superlevel", "is_normalization_row",
            )
            for index, (expected, native) in enumerate(zip(expected_rows, native_rows), 1):
                if any(str(expected[field]) != str(native.get(field, "")) for field in identity_fields):
                    reasons.append(f"compact_population_topology:{index}")
                    break
                if native.get("closure_applied") != "1":
                    reasons.append(f"compact_population_closure_flag:{index}")
                    break
                if not _exact(expected["final_population"], native.get("thermal_population", "nan")):
                    reasons.append(f"compact_population_value:{index}")
                    break

    population_rows = sum(1 for _ in (evaluation_dir / "native_evaluation_populations.csv").open()) - 1
    spectra_rows = sum(1 for _ in (evaluation_dir / "native_evaluation_spectra.csv").open()) - 1
    if population_rows != 688:
        reasons.append(f"population_rows:{population_rows}")
    if spectra_rows != 9999:
        reasons.append(f"spectra_rows:{spectra_rows}")
    return not reasons, reasons


def build_manifest(
    source_inputs: Path,
    trajectory: Path,
    workspaces: Path,
    evaluations_dir: Path,
    canonical_closure: Path,
    thermal_closure: Path,
    manifest_path: Path,
    plan_path: Path | None = None,
    failed_sequence: int | None = None,
    failed_returncode: int | None = None,
    compact_closure: Path | None = None,
    require_thermal_diagonal_ledger: bool = False,
    require_continuum_workspace: bool = False,
) -> dict[str, Any]:
    plans = _plan_rows(source_inputs, trajectory, workspaces)
    statuses: list[dict[str, Any]] = []
    reusable = 0
    pending = 0
    for plan in plans:
        sequence = int(plan["sequence"])
        evaluation_dir = evaluations_dir / f"evaluation_{sequence:04d}"
        valid, reasons = validate_evaluation(
            evaluation_dir, plan, canonical_closure, thermal_closure, compact_closure,
            require_thermal_diagonal_ledger=require_thermal_diagonal_ledger,
            require_continuum_workspace=require_continuum_workspace,
        ) if evaluation_dir.is_dir() else (False, ["evaluation_directory_absent"])
        action = "reuse" if valid else "run"
        reusable += int(valid)
        pending += int(not valid)
        status = {
            **plan,
            "evaluation_dir": str(evaluation_dir),
            "action": action,
            "validation": "ACCEPT" if valid else "PENDING",
            "reasons": reasons,
        }
        if failed_sequence == sequence:
            status["validation"] = "FAILED"
            status["failed_returncode"] = failed_returncode
        statuses.append(status)

    if plan_path is not None:
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        with plan_path.open("w", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            for status in statuses:
                writer.writerow([
                    status["sequence"], status["kind"], status["call_id"], status["evaluation_index"],
                    status["temperature_k"], status["covering_fraction"], status["workspace"],
                    status["action"], ";".join(status["reasons"]),
                ])

    first_pending = next((row["sequence"] for row in statuses if row["action"] == "run"), None)
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if pending == 0 and failed_sequence is None else "INCOMPLETE",
        "sequences_total": 61,
        "sequences_reusable": reusable,
        "sequences_pending": pending,
        "first_pending_sequence": first_pending,
        "failed_sequence": failed_sequence,
        "failed_returncode": failed_returncode,
        "thermal_compact_population_closure": str(compact_closure) if compact_closure is not None else None,
        "thermal_diagonal_ledger_required": require_thermal_diagonal_ledger,
        "continuum_workspace_required": require_continuum_workspace,
        "statuses": statuses,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    _write_json(manifest_path, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-inputs", type=Path, required=True)
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--workspaces", type=Path, required=True)
    parser.add_argument("--evaluations-dir", type=Path, required=True)
    parser.add_argument("--canonical-closure", type=Path, required=True)
    parser.add_argument("--thermal-closure", type=Path, required=True)
    parser.add_argument("--compact-closure", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--failed-sequence", type=int)
    parser.add_argument("--failed-returncode", type=int)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--require-thermal-diagonal-ledger", action="store_true")
    parser.add_argument("--require-continuum-workspace", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_manifest(
            args.source_inputs,
            args.trajectory,
            args.workspaces,
            args.evaluations_dir,
            args.canonical_closure,
            args.thermal_closure,
            args.manifest,
            args.plan,
            args.failed_sequence,
            args.failed_returncode,
            compact_closure=args.compact_closure,
            require_thermal_diagonal_ledger=args.require_thermal_diagonal_ledger,
            require_continuum_workspace=args.require_continuum_workspace,
        )
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
        _write_json(args.manifest, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    if report.get("result") == "REJECT":
        return 2
    if args.require_complete and report.get("result") != "ACCEPT":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
