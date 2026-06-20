"""Aggregate 61 independent run-fixed-evaluation outputs for v0.6.48.7.46.21.3."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.3"
SCHEMA = "xstar-tools-v064874612-all61-native-replay-aggregate-v1"
THERMAL_LEDGER_NAME = "native_all61_thermal_budget.csv"
THERMAL_COMPACT_POPULATION_NAME = "native_all61_thermal_compact_populations.csv"
THERMAL_DIAGONAL_LEDGER_NAME = "native_all61_thermal_diagonal_ledger.csv"
CONTINUUM_WORKSPACE_LEDGER_NAME = "native_all61_continuum_workspace.csv"
CANONICAL_THERMAL_TERM_LEDGER_NAME = "native_all61_canonical_thermal_terms.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def aggregate(source_inputs: Path, evaluations_dir: Path, output: Path, *, require_compact_populations: bool = False, require_thermal_diagonal_ledger: bool = False, require_continuum_workspace: bool = False, require_canonical_thermal_ledger: bool = False) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    source = _read_csv(source_inputs)
    source.sort(key=lambda row: int(row["sequence"]))
    trajectory_rows: list[dict[str, Any]] = []
    thermal_rows: list[dict[str, Any]] = []
    thermal_fields: list[str] | None = None
    compact_population_rows: list[dict[str, Any]] = []
    compact_population_fields: list[str] | None = None
    diagonal_rows_all: list[dict[str, Any]] = []
    diagonal_fields: list[str] | None = None
    continuum_rows_all: list[dict[str, Any]] = []
    continuum_fields: list[str] | None = None
    canonical_rows_all: list[dict[str, Any]] = []
    canonical_fields: list[str] | None = None
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
        diagonal_path = root / "native_thermal_diagonal_ledger.csv"
        continuum_path = root / "native_continuum_workspace.csv"
        canonical_path = root / "native_canonical_thermal_terms.csv"
        required_paths = [state_path, summary_path, thermal_path]
        if require_compact_populations:
            required_paths.append(compact_population_path)
        if require_thermal_diagonal_ledger:
            required_paths.append(diagonal_path)
        if require_continuum_workspace:
            required_paths.append(continuum_path)
        if require_canonical_thermal_ledger:
            required_paths.append(canonical_path)
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
        if diagonal_path.is_file():
            diagonal_rows = _read_csv(diagonal_path)
            for diagonal in diagonal_rows:
                diagonal.update({
                    "sequence": str(sequence),
                    "kind": kind,
                    "call_index": str(call_index),
                    "evaluation_index": str(evaluation_index),
                })
                if diagonal_fields is None:
                    diagonal_fields = list(diagonal.keys())
                elif list(diagonal.keys()) != diagonal_fields:
                    errors.append(f"evaluation_{sequence:04d}:thermal_diagonal_schema_mismatch")
                    break
                diagonal_rows_all.append(diagonal)


        if canonical_path.is_file():
            canonical_rows = _read_csv(canonical_path)
            seen_elements: set[int] = set()
            for canonical in canonical_rows:
                canonical.update({
                    "sequence": str(sequence),
                    "kind": kind,
                    "call_index": str(call_index),
                    "evaluation_index": str(evaluation_index),
                })
                if canonical_fields is None:
                    canonical_fields = list(canonical.keys())
                elif list(canonical.keys()) != canonical_fields:
                    errors.append(f"evaluation_{sequence:04d}:canonical_thermal_schema_mismatch")
                    break
                if canonical.get("shared_ownership") != "1" or (
                    canonical.get("ledger_fingerprint") != canonical.get("element_consumer_fingerprint") or
                    canonical.get("ledger_fingerprint") != canonical.get("fixed_state_consumer_fingerprint")
                ):
                    errors.append(f"evaluation_{sequence:04d}:canonical_thermal_ownership_mismatch")
                    break
                seen_elements.add(int(canonical["element_z"]))
                canonical_rows_all.append(canonical)
            if require_canonical_thermal_ledger and seen_elements != {1, 2, 12}:
                errors.append(f"evaluation_{sequence:04d}:canonical_thermal_elements:{sorted(seen_elements)}")

        if continuum_path.is_file():
            continuum_rows = _read_csv(continuum_path)
            if require_continuum_workspace and len(continuum_rows) != 999:
                errors.append(f"evaluation_{sequence:04d}:continuum_workspace_rows:{len(continuum_rows)}")
            for continuum in continuum_rows:
                continuum.update({
                    "sequence": str(sequence),
                    "kind": kind,
                    "call_index": str(call_index),
                    "evaluation_index": str(evaluation_index),
                })
                if continuum_fields is None:
                    continuum_fields = list(continuum.keys())
                elif list(continuum.keys()) != continuum_fields:
                    errors.append(f"evaluation_{sequence:04d}:continuum_workspace_schema_mismatch")
                    break
                continuum_rows_all.append(continuum)


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
    if diagonal_fields is None:
        diagonal_fields = [
            "sequence", "kind", "call_index", "evaluation_index", "evaluation_ordinal",
            "element_z", "source_order_index", "source_position", "record", "data_type",
            "rate_type", "compact_row", "role", "is_normalization_row",
            "source_domain_included", "compact_population", "cj", "cj2",
            "heating_contribution", "cooling_contribution", "heating2_contribution",
            "cooling2_contribution",
        ]
    _write_csv(output / THERMAL_DIAGONAL_LEDGER_NAME, diagonal_fields, diagonal_rows_all)
    if continuum_fields is None:
        continuum_fields = [
            "sequence", "kind", "call_index", "evaluation_index", "evaluation_ordinal",
            "reduced_bin_one_based", "full_bin_one_based", "epim_ev", "bremsam",
            "bin_width_ev", "cmp1_contribution", "cmp2_contribution",
            "htcomp_contribution", "clcomp_contribution", "htfreef_contribution",
            "clbrems_contribution", "running_cmp1", "running_cmp2",
            "running_htcomp", "running_clcomp", "running_htfreef", "running_clbrems",
        ]
    if canonical_fields is None:
        canonical_fields = [
            "sequence", "kind", "call_index", "evaluation_index", "evaluation_ordinal",
            "element_index", "element_z", "ledger_fingerprint",
            "element_consumer_fingerprint", "fixed_state_consumer_fingerprint",
            "shared_ownership", "term_index", "source_position", "record",
            "data_type", "rate_type", "ion_index", "ion_stage", "compact_row",
            "native_compact_row", "source_compact_row", "role", "is_type53",
            "is_normalization_row", "source_domain_included", "matrix_insertion_captured",
            "type99_source_corrected", "primary_source_ordered", "primary_source_order_index", "cj", "cj2",
            "native_cj", "source_cj",
        ]
    _write_csv(output / CANONICAL_THERMAL_TERM_LEDGER_NAME, canonical_fields, canonical_rows_all)
    _write_csv(output / CONTINUUM_WORKSPACE_LEDGER_NAME, continuum_fields, continuum_rows_all)
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
        "thermal_diagonal_ledger_rows": len(diagonal_rows_all),
        "thermal_diagonal_ledger_required": require_thermal_diagonal_ledger,
        "continuum_workspace_rows": len(continuum_rows_all),
        "continuum_workspace_required": require_continuum_workspace,
        "canonical_thermal_term_rows": len(canonical_rows_all),
        "canonical_thermal_ledger_required": require_canonical_thermal_ledger,
        "canonical_sequence_inventory": canonical_inventory,
        "python_callbacks": callbacks,
        "records_evaluated": records,
        "elements_solved": elements,
        "errors": errors,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    compact_ok = (not require_compact_populations) or len(compact_population_rows) == 40149
    diagonal_ok = (not require_thermal_diagonal_ledger) or len(diagonal_rows_all) > 0
    continuum_ok = (not require_continuum_workspace) or len(continuum_rows_all) == 60939
    canonical_ok = (not require_canonical_thermal_ledger) or len(canonical_rows_all) > 0
    summary["result"] = "ACCEPT" if len(trajectory_rows) == len(thermal_rows) == 61 and compact_ok and diagonal_ok and continuum_ok and canonical_ok and callbacks == 0 and canonical_inventory and not errors else "REJECT"
    (output / "native_dsec_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-inputs", type=Path, required=True)
    parser.add_argument("--evaluations-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-compact-populations", action="store_true")
    parser.add_argument("--require-thermal-diagonal-ledger", action="store_true")
    parser.add_argument("--require-continuum-workspace", action="store_true")
    parser.add_argument("--require-canonical-thermal-ledger", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = aggregate(
            args.source_inputs, args.evaluations_dir, args.output,
            require_compact_populations=args.require_compact_populations,
            require_thermal_diagonal_ledger=args.require_thermal_diagonal_ledger,
            require_continuum_workspace=args.require_continuum_workspace,
            require_canonical_thermal_ledger=args.require_canonical_thermal_ledger,
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
