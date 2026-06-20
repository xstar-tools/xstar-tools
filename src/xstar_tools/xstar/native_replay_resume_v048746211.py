"""Resumable all-61 replay manifest for v46.21 independent Thermal parity."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.2"
SCHEMA = "xstar-tools-v0648746211-independent-native-replay-resume-v1"
REQUIRED_OUTPUTS = (
    "native_evaluation.csv", "native_evaluation_summary.json", "native_thermal_budget.csv",
    "native_thermal_diagonal_ledger.csv", "native_continuum_workspace.csv",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _valid_evaluation(root: Path, sequence: int) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for name in REQUIRED_OUTPUTS:
        if not (root / name).is_file(): reasons.append(f"missing:{name}")
    if reasons: return False, reasons
    try:
        state = _read_csv(root / "native_evaluation.csv")
        thermal = _read_csv(root / "native_thermal_budget.csv")
        summary = json.loads((root / "native_evaluation_summary.json").read_text())
        if len(state) != 1 or len(thermal) != 1: reasons.append("row_inventory")
        else:
            row = thermal[0]
            if row.get("independent_thermal_parity") != "1": reasons.append("independent_mode_not_applied")
            if row.get("source_scalar_override_used") != "0": reasons.append("source_scalar_override_used")
            for field in (
                "thermal_consumed_fixed_state_closure",
                "thermal_consumed_compact_population_closure",
                "thermal_component_closure_applied",
            ):
                if row.get(field) != "0": reasons.append(f"closure_used:{field}")
            if row.get("thermal_diagonal_source_domain_applied") != "1": reasons.append("source_order_stream_missing")
        if int(summary.get("python_callbacks", -1)) != 0: reasons.append("python_callbacks_nonzero")
        if int(summary.get("evaluation_index", sequence)) <= 0: reasons.append("invalid_evaluation_index")
    except Exception as exc:
        reasons.append(f"parse:{exc}")
    return not reasons, reasons


def build(source_inputs: Path, trajectory: Path, workspaces: Path, evaluations_dir: Path,
          manifest: Path, plan: Path | None, failed_sequence: int | None,
          failed_returncode: int | None, require_complete: bool) -> dict[str, Any]:
    source = _read_csv(source_inputs); source.sort(key=lambda row: int(row["sequence"]))
    trajectory_rows = _read_csv(trajectory)
    trajectory_by_sequence = {int(row.get("sequence", index + 1)): row for index, row in enumerate(trajectory_rows)}
    plan_rows: list[list[str]] = []
    entries: list[dict[str, Any]] = []
    reusable = 0
    for item in source:
        sequence = int(item["sequence"])
        row = trajectory_by_sequence.get(sequence, {})
        call_id = item.get("dsec_call_id", item.get("call_index", row.get("call_index", "")))
        eval_index = item.get("evaluation_index", row.get("evaluation_index", ""))
        temperature = item.get("temperature_k", "")
        covering = item.get("covering_fraction", "")
        # The all-61 source capture stores one workspace per canonical
        # evaluation.  Accept the older sequence spelling and finally the
        # absolute path recorded by the source input ledger.
        workspace = workspaces / f"evaluation_{sequence:04d}"
        if not workspace.is_dir():
            workspace = workspaces / f"sequence_{sequence:04d}"
        if not workspace.is_dir():
            candidate = item.get("workspace_directory", "")
            if candidate:
                workspace = Path(candidate)
        eval_root = evaluations_dir / f"evaluation_{sequence:04d}"
        valid, reasons = _valid_evaluation(eval_root, sequence)
        action = "reuse" if valid else "run"
        reusable += int(valid)
        entries.append({"sequence": sequence, "action": action, "reasons": reasons, "evaluation_dir": str(eval_root)})
        plan_rows.append([
            str(sequence), item.get("kind", row.get("kind", "dsec")), str(call_id), str(eval_index),
            str(temperature), str(covering), str(workspace), action, ";".join(reasons),
        ])
    result = "ACCEPT"
    errors: list[str] = []
    if len(entries) != 61: errors.append(f"sequence_inventory={len(entries)}")
    if require_complete and reusable != 61: errors.append(f"complete_replay_required:{reusable}/61")
    if errors: result = "REJECT"
    report = {
        "schema": SCHEMA, "release": RELEASE, "result": result, "errors": errors,
        "evaluations": len(entries), "reusable_evaluations": reusable,
        "pending_evaluations": len(entries) - reusable,
        "failed_sequence": failed_sequence, "failed_returncode": failed_returncode,
        "entries": entries, "qualification_only": True, "production_promotion_ready": False,
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if plan is not None:
        plan.parent.mkdir(parents=True, exist_ok=True)
        with plan.open("w", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerows(plan_rows)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-inputs", type=Path, required=True)
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--workspaces", type=Path, required=True)
    parser.add_argument("--evaluations-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--failed-sequence", type=int)
    parser.add_argument("--failed-returncode", type=int)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build(args.source_inputs, args.trajectory, args.workspaces, args.evaluations_dir,
                       args.manifest, args.plan, args.failed_sequence, args.failed_returncode,
                       args.require_complete)
    except Exception as exc:
        result = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)], "qualification_only": True, "production_promotion_ready": False}
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
