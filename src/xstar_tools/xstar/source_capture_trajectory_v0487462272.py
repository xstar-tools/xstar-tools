"""Build one coherent 61-state trajectory from a verified v0.6.47.2 capture.

The fixed replay, live DSEC controller, and canonical audit must consume the
same source-capture state.  This module replaces the old packaged trajectory
fixture whenever a verified all-61 capture is selected.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.17.2"
SCHEMA = "xstar-tools-v06487462272-source-capture-trajectory-v1"
FIELDS = [
    "sequence", "kind", "call_index", "evaluation_index", "temperature_t4",
    "electron_fraction", "hmctot", "elcter", "lnerr",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def build(source_capture: Path, output_csv: Path) -> dict[str, Any]:
    source_capture = source_capture.resolve()
    inputs = _read_csv(source_capture / "v0472_all61_input_states.csv")
    budgets = _read_csv(source_capture / "v0472_all61_thermal_budget.csv")
    budget_by_sequence = {int(row["sequence"]): row for row in budgets}
    errors: list[str] = []
    if len(inputs) != 61:
        errors.append(f"input_state_rows:{len(inputs)}")
    if len(budget_by_sequence) != 61:
        errors.append(f"thermal_budget_sequences:{len(budget_by_sequence)}")

    rows: list[dict[str, str]] = []
    identities: set[tuple[str, int, int]] = set()
    call_counts: dict[int, int] = {}
    for source in sorted(inputs, key=lambda row: int(row["sequence"])):
        sequence = int(source["sequence"])
        budget = budget_by_sequence.get(sequence)
        if budget is None:
            errors.append(f"missing_budget_sequence:{sequence}")
            continue
        kind = source["kind"]
        call_index = int(source["dsec_call_id"])
        evaluation_index = int(source["evaluation_index"])
        identity = (kind, call_index, evaluation_index)
        if identity in identities:
            errors.append(f"duplicate_identity:{identity}")
        identities.add(identity)
        if kind == "dsec":
            call_counts[call_index] = call_counts.get(call_index, 0) + 1
        rows.append({
            "sequence": str(sequence),
            "kind": kind,
            "call_index": str(call_index),
            "evaluation_index": str(evaluation_index),
            # Preserve the source decimal text.  Parsing that text in C++ gives
            # the exact binary64 value captured from v0.6.47.2.
            "temperature_t4": source["temperature_t4"],
            "electron_fraction": source["electron_fraction_input"],
            "hmctot": budget["hmctot"],
            "elcter": budget["elcter"],
            "lnerr": "0",
        })

    expected_counts = {1: 21, 2: 1, 3: 18, 4: 17}
    if call_counts != expected_counts:
        errors.append(f"dsec_call_counts:{call_counts}")
    if [int(row["sequence"]) for row in rows] != list(range(1, 62)):
        errors.append("sequence_inventory_not_dense_1_to_61")

    if errors:
        return {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": errors,
            "source_capture": str(source_capture),
            "rows": len(rows),
            "qualification_only": True,
            "production_promotion_ready": False,
        }

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    temp = output_csv.with_name(f".{output_csv.name}.tmp")
    with temp.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(output_csv)

    sequence28 = rows[27]
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "source_capture": str(source_capture),
        "output_csv": str(output_csv.resolve()),
        "rows": 61,
        "dsec_call_counts": call_counts,
        "sequence28_temperature_t4": sequence28["temperature_t4"],
        "sequence28_hmctot": sequence28["hmctot"],
        "qualification_only": True,
        "product_level_parity": "NOT_IN_SCOPE",
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build(args.source_capture, args.output_csv)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
