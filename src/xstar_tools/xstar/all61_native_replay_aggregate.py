"""Aggregate 61 independent run-fixed-evaluation outputs for v0.6.48.7.46.13."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.13"
SCHEMA = "xstar-tools-v064874612-all61-native-replay-aggregate-v1"
THERMAL_LEDGER_NAME = "native_all61_thermal_budget.csv"
THERMAL_COMPACT_POPULATION_NAME = "native_all61_thermal_compact_populations.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def aggregate(source_inputs: Path, evaluations_dir: Path, output: Path, *, require_compact_populations: bool = False) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    source = _read_csv(source_inputs)
    source.sort(key=lambda row: int(row["sequence"]))
    trajectory_rows: list[dict[str, Any]] = []
    thermal_rows: list[dict[str, Any]] = []
    thermal_fields: list[str] | None = None
    compact_population_rows: list[dict[str, Any]] = []
    compact_population_fields: list[str] | None = None
    callbacks = records = elements = 0
    errors: list[str] = []
    trajectory_fields = [
        "sequence", "kind", "call_index", "evaluation_index", "temperature_t4",
        "electron_fraction_input", "computed_electron_fraction", "charge_residual", "hmctot",
    ]
    for item in source:
        sequence = int(item["sequence"])
        root = evaluations_dir / f"evaluation_{sequence:04d}"
        state_path = root / "native_evaluation.csv"
        summary_path = root / "native_evaluation_summary.json"
        thermal_path = root / "native_thermal_budget.csv"
        compact_population_path = root / "native_thermal_compact_populations.csv"
        required_paths = [state_path, summary_path, thermal_path]
        if require_compact_populations:
            required_paths.append(compact_population_path)
        missing = [str(path.name) for path in required_paths if not path.is_file()]
        if missing:
            errors.append(f"evaluation_{sequence:04d}:missing:{','.join(missing)}")
            continue
        state_rows = _read_csv(state_path)
        ledger_rows = _read_csv(thermal_path)
        if len(state_rows) != 1 or len(ledger_rows) != 1:
            errors.append(
                f"evaluation_{sequence:04d}:row_inventory:state={len(state_rows)},thermal={len(ledger_rows)}"
            )
            continue
        state = state_rows[0]
        ledger = dict(ledger_rows[0])
        summary = json.loads(summary_path.read_text())
        callbacks += int(summary.get("python_callbacks", 0))
        records += int(summary.get("records_evaluated", 0))
        elements += int(summary.get("elements_solved", 0))
        kind = item.get("kind", "")
        call_index = item.get("dsec_call_id", item.get("call_index", ""))
        evaluation_index = item.get("evaluation_index", "")
        trajectory_rows.append({
            "sequence": sequence,
            "kind": kind,
            "call_index": call_index,
            "evaluation_index": evaluation_index,
            "temperature_t4": item["temperature_t4"],
            "electron_fraction_input": item["electron_fraction_input"],
            "computed_electron_fraction": state["native_electron_fraction"],
            "charge_residual": state["native_charge_residual"],
            "hmctot": state["native_hmctot"],
        })
        # The standalone command receives canonical identity from the source row,
        # so normalize the ledger rather than trusting any local one-process ordinal.
        ledger.update({
            "sequence": str(sequence),
            "kind": kind,
            "call_index": str(call_index),
            "evaluation_index": str(evaluation_index),
        })
        if thermal_fields is None:
            thermal_fields = list(ledger.keys())
        elif list(ledger.keys()) != thermal_fields:
            errors.append(f"evaluation_{sequence:04d}:thermal_schema_mismatch")
            continue
        thermal_rows.append(ledger)
        if compact_population_path.is_file():
            compact_rows = _read_csv(compact_population_path)
            for compact in compact_rows:
                compact.update({
                    "sequence": str(sequence),
                    "kind": kind,
                    "call_index": str(call_index),
                    "evaluation_index": str(evaluation_index),
                })
                if compact_population_fields is None:
                    compact_population_fields = list(compact.keys())
                elif list(compact.keys()) != compact_population_fields:
                    errors.append(f"evaluation_{sequence:04d}:compact_population_schema_mismatch")
                    break
                compact_population_rows.append(compact)

    _write_csv(output / "native_dsec_trajectory.csv", trajectory_fields, trajectory_rows)
    if thermal_fields is None:
        thermal_fields = ["sequence", "kind", "call_index", "evaluation_index"]
    _write_csv(output / THERMAL_LEDGER_NAME, thermal_fields, thermal_rows)
    if compact_population_fields is None:
        compact_population_fields = [
            "sequence", "kind", "call_index", "evaluation_index", "element_index", "element_z",
            "active_min_stage", "active_max_stage", "compact_row", "ion", "ion_stage",
            "ion_charge", "superlevel", "is_normalization_row", "thermal_population", "closure_applied",
        ]
    _write_csv(output / THERMAL_COMPACT_POPULATION_NAME, compact_population_fields, compact_population_rows)
    sequences = [int(row["sequence"]) for row in trajectory_rows]
    thermal_sequences = [int(row["sequence"]) for row in thermal_rows]
    canonical_inventory = sequences == list(range(1, 62)) and thermal_sequences == list(range(1, 62))
    summary = {
        "schema": SCHEMA,
        "release": RELEASE,
        "trajectory_mode": "all61_independent_reference_input_state_qualification",
        "total_evaluations": len(trajectory_rows),
        "thermal_ledger_rows": len(thermal_rows),
        "thermal_compact_population_rows": len(compact_population_rows),
        "thermal_compact_population_required": require_compact_populations,
        "canonical_sequence_inventory": canonical_inventory,
        "python_callbacks": callbacks,
        "records_evaluated": records,
        "elements_solved": elements,
        "errors": errors,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    compact_ok = (not require_compact_populations) or len(compact_population_rows) == 40149
    summary["result"] = "ACCEPT" if len(trajectory_rows) == len(thermal_rows) == 61 and compact_ok and callbacks == 0 and canonical_inventory and not errors else "REJECT"
    (output / "native_dsec_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-inputs", type=Path, required=True)
    parser.add_argument("--evaluations-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-compact-populations", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = aggregate(
            args.source_inputs, args.evaluations_dir, args.output,
            require_compact_populations=args.require_compact_populations,
        )
    except Exception as exc:
        result = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
            "qualification_only": True, "production_promotion_ready": False,
        }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
