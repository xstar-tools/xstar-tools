from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.46.21.8.1"
SCHEMA = "xstar-tools-v0648746218-focused-thermal-answer-correction-v1"
H_TYPE51_RECORDS = tuple(range(469, 492))


def canonical_e10(value: Any) -> str:
    number = float(value)
    if not math.isfinite(number):
        return str(number)
    return format(number, ".10e")


def bit_exact(left: Any, right: Any) -> bool:
    return struct.pack("!d", float(left)) == struct.pack("!d", float(right))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def compare_numeric(
    differences: list[dict[str, Any]], domain: str, sequence: int,
    identity: str, field: str, source: Any, native: Any,
) -> bool:
    source_e10 = canonical_e10(source)
    native_e10 = canonical_e10(native)
    equal = source_e10 == native_e10
    if not equal:
        differences.append({
            "domain": domain, "sequence": sequence, "identity": identity,
            "field": field, "source_value": source, "native_value": native,
            "source_e10": source_e10, "native_e10": native_e10,
            "bit_exact": int(bit_exact(source, native)),
        })
    return equal


def audit(
    source_capture: Path,
    native_evaluations: Path,
    controller: Path | None,
    output_csv: Path,
    sequences: Iterable[int] = range(1, 62),
) -> dict[str, Any]:
    selected = tuple(int(value) for value in sequences)
    selected_set = set(selected)
    differences: list[dict[str, Any]] = []
    source_budget = {
        int(row["sequence"]): row
        for row in read_csv(source_capture / "v0472_all61_thermal_budget.csv")
        if int(row["sequence"]) in selected_set
    }
    budget_counts = {
        "h_cooling2": {"compared": 0, "rejected": 0},
        "he_non_type53_cooling": {"compared": 0, "rejected": 0},
    }
    for sequence in selected:
        native_path = native_evaluations / f"evaluation_{sequence:04d}" / "native_thermal_budget.csv"
        rows = read_csv(native_path)
        if sequence not in source_budget or len(rows) != 1:
            differences.append({
                "domain": "inventory", "sequence": sequence, "identity": "thermal_budget",
                "field": "single_row", "source_value": 1, "native_value": len(rows),
                "source_e10": "", "native_e10": "", "bit_exact": 0,
            })
            continue
        source = source_budget[sequence]
        native = rows[0]
        for field in budget_counts:
            budget_counts[field]["compared"] += 1
            if not compare_numeric(differences, "thermal_budget", sequence, "fixed_evaluation", field, source[field], native[field]):
                budget_counts[field]["rejected"] += 1

    source_h: dict[tuple[int, int], dict[str, str]] = {}
    source_he50: dict[tuple[int, int], dict[str, str]] = {}
    answer_path = source_capture / "v0472_all61_thermal_answer_channels.csv"
    with answer_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            sequence = int(row["sequence"])
            if sequence not in selected_set:
                continue
            element_z = int(row["element_z"])
            record = int(row["record"])
            if element_z == 1 and record in H_TYPE51_RECORDS:
                source_h[(sequence, record)] = row
            if element_z == 2 and int(row["data_type"]) == 50:
                source_he50[(sequence, record)] = row

    h_rejected = 0
    he50_rejected = 0
    native_h_keys: set[tuple[int, int]] = set()
    native_he50_keys: set[tuple[int, int]] = set()
    for sequence in selected:
        diagnostic_path = (
            native_evaluations / f"evaluation_{sequence:04d}" /
            "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
        )
        native_rows = read_csv(diagnostic_path)
        for row in native_rows:
            element_z = int(row.get("element_z", "0"))
            record = int(row.get("record", "0"))
            key = (sequence, record)
            if key in source_h:
                native_h_keys.add(key)
                if not compare_numeric(
                    differences, "hydrogen_type51", sequence, f"record={record}",
                    "ans6", source_h[key]["ans6"], row["ans6"],
                ):
                    h_rejected += 1
            if key in source_he50:
                native_he50_keys.add(key)
                for field in ("ans3", "ans4"):
                    if not compare_numeric(
                        differences, "helium_type50", sequence, f"record={record}",
                        field, source_he50[key][field], row[field],
                    ):
                        he50_rejected += 1

    expected_h = len(selected) * len(H_TYPE51_RECORDS)
    h_source_type_exact = (
        len(source_h) == expected_h
        and all(int(row["data_type"]) == 51 for row in source_h.values())
    )
    h_inventory_exact = h_source_type_exact and set(source_h) == native_h_keys
    he50_inventory_exact = bool(source_he50) and set(source_he50) == native_he50_keys
    gates = {
        "HYDROGEN_TYPE51_SOURCE_DOMAIN_EXACT": "ACCEPT" if h_source_type_exact else "REJECT",
        "HYDROGEN_TYPE51_NATIVE_INVENTORY_EXACT": "ACCEPT" if h_inventory_exact else "REJECT",
        "HYDROGEN_TYPE51_ANS6_IEEE_E10": "ACCEPT" if h_inventory_exact and h_rejected == 0 else "REJECT",
        "HYDROGEN_COOLING2_ALL_SELECTED_IEEE_E10": "ACCEPT" if budget_counts["h_cooling2"]["compared"] == len(selected) and budget_counts["h_cooling2"]["rejected"] == 0 else "REJECT",
        "HELIUM_TYPE50_NATIVE_INVENTORY_EXACT": "ACCEPT" if he50_inventory_exact else "REJECT",
        "HELIUM_TYPE50_ANS3_ANS4_IEEE_E10": "ACCEPT" if he50_inventory_exact and he50_rejected == 0 else "REJECT",
        "HELIUM_NON_TYPE53_COOLING_ALL_SELECTED_IEEE_E10": "ACCEPT" if budget_counts["he_non_type53_cooling"]["compared"] == len(selected) and budget_counts["he_non_type53_cooling"]["rejected"] == 0 else "REJECT",
    }
    focused_result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    controller_summary: dict[str, Any] = {}
    if controller is not None and (controller / "native_dsec_summary.json").is_file():
        controller_summary = json.loads((controller / "native_dsec_summary.json").read_text())
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = ("domain", "sequence", "identity", "field", "source_value", "native_value", "source_e10", "native_e10", "bit_exact")
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(differences)
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": focused_result,
        "focused_scientific_result": focused_result,
        "sequences": list(selected),
        "gates": gates,
        "hydrogen_type51": {
            "records_per_sequence": len(H_TYPE51_RECORDS),
            "source_rows": len(source_h),
            "native_rows": len(native_h_keys),
            "ans6_rejections": h_rejected,
        },
        "helium_type50": {
            "source_rows": len(source_he50),
            "native_rows": len(native_he50_keys),
            "ans3_ans4_values": 2 * len(source_he50),
            "ans3_ans4_rejections": he50_rejected,
        },
        "thermal_budget": budget_counts,
        "focused_rejections": len(differences),
        "first_focused_rejection": differences[0] if differences else None,
        "controller": {
            "result": controller_summary.get("result", "NOT_RUN"),
            "source_trajectory_diverged": controller_summary.get("source_trajectory_diverged", False),
            "divergence_sequence": controller_summary.get("divergence_sequence"),
            "total_evaluations": controller_summary.get("total_evaluations", 0),
            "python_callbacks": controller_summary.get("python_callbacks"),
        },
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def parse_sequences(text: str) -> tuple[int, ...]:
    values: set[int] = set()
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            first, last = token.split("-", 1)
            values.update(range(int(first), int(last) + 1))
        else:
            values.add(int(token))
    return tuple(sorted(values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-evaluations", type=Path, required=True)
    parser.add_argument("--native-controller", type=Path)
    parser.add_argument("--sequences", default="1-61")
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(
            args.source_capture.resolve(), args.native_evaluations.resolve(),
            args.native_controller.resolve() if args.native_controller else None,
            args.output_csv.resolve(), parse_sequences(args.sequences),
        )
    except Exception as exc:
        report = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "focused_scientific_result": "REJECT",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "qualification_only": True, "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
