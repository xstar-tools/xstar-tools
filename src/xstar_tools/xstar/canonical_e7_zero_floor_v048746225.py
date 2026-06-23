from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.15"
SCHEMA = "xstar-tools-v06487462115-canonical-e7-zero-floor-audit-v1"
CANONICAL_DIGITS = 7
CANONICAL_ZERO_FLOOR = 1.0e-30


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def normalize(value: Any) -> tuple[float, bool]:
    number = float(value)
    if not math.isfinite(number):
        return number, False
    zeroed = abs(number) < CANONICAL_ZERO_FLOOR
    return (0.0 if zeroed else number), zeroed


def canonical_e7(value: Any) -> str:
    number, _ = normalize(value)
    if not math.isfinite(number):
        return str(number).lower()
    return format(number, f".{CANONICAL_DIGITS}e")


def parse_identity(identity: str) -> tuple[int, int] | None:
    values: dict[str, int] = {}
    for token in identity.split(";"):
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key in {"element_z", "record"}:
            try:
                values[key] = int(value)
            except ValueError:
                return None
    if set(values) != {"element_z", "record"}:
        return None
    return values["element_z"], values["record"]


def record_types(native_case: Path) -> dict[tuple[int, int], int]:
    elements = {
        int(row["element_index"]): int(row["element_z"])
        for row in read_csv(native_case / "elements.csv")
    }
    return {
        (elements[int(row["element_index"])], int(row["record"])): int(row["data_type"])
        for row in read_csv(native_case / "records.csv")
    }


def audit(native_case: Path, input_rejections: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    types = record_types(native_case)
    retained: list[dict[str, Any]] = []
    newly_accepted: list[dict[str, Any]] = []
    accepted_zero_floor = 0
    accepted_e7_roundoff = 0
    numeric_magnitudes_accepted: list[float] = []
    numeric_magnitudes_retained: list[float] = []

    for original in read_csv(input_rejections):
        row: dict[str, Any] = dict(original)
        try:
            source = float(row["source_value"])
            native = float(row["native_value"])
            source_cmp, source_zeroed = normalize(source)
            native_cmp, native_zeroed = normalize(native)
            source_e7 = canonical_e7(source)
            native_e7 = canonical_e7(native)
            acceptable = math.isfinite(source) and math.isfinite(native) and source_e7 == native_e7
            row.update({
                "source_e7": source_e7,
                "native_e7": native_e7,
                "e7_equal": int(acceptable),
                "source_zero_normalized": int(source_zeroed),
                "native_zero_normalized": int(native_zeroed),
            })
            magnitude = max(abs(source), abs(native))
            if acceptable:
                row["e7_classification"] = (
                    "E7_ZERO_FLOOR_ACCEPTED" if source_zeroed or native_zeroed
                    else "E7_ACCEPTED_ROUNDOFF"
                )
                accepted_zero_floor += int(source_zeroed or native_zeroed)
                accepted_e7_roundoff += int(not (source_zeroed or native_zeroed))
                numeric_magnitudes_accepted.append(magnitude)
                newly_accepted.append(row)
            else:
                row["e7_classification"] = "NUMERIC_REJECT"
                numeric_magnitudes_retained.append(magnitude)
                retained.append(row)
        except Exception:
            row.update({
                "source_e7": "", "native_e7": "", "e7_equal": 0,
                "source_zero_normalized": 0, "native_zero_normalized": 0,
                "e7_classification": "STRUCTURAL_REJECT",
            })
            retained.append(row)

    family_counts: Counter[tuple[int, int, str]] = Counter()
    family_records: dict[tuple[int, int], set[int]] = defaultdict(set)
    family_sequences: dict[tuple[int, int], set[int]] = defaultdict(set)
    for row in retained:
        if row.get("category") != "canonical_answer_channels":
            continue
        parsed = parse_identity(str(row.get("identity", "")))
        if parsed is None:
            continue
        z, record = parsed
        dtype = types.get((z, record), -1)
        family_counts[(z, dtype, str(row.get("field", "")))] += 1
        family_records[(z, dtype)].add(record)
        try:
            family_sequences[(z, dtype)].add(int(row.get("sequence", 0)))
        except ValueError:
            pass

    by_category = Counter(str(row.get("category", "")) for row in retained)
    family_summary: dict[str, Any] = {}
    labels = {(12, 73): "magnesium_type73", (12, 95): "magnesium_type95", (2, 53): "helium_type53"}
    for key, label in labels.items():
        fields = {field: count for (z, dtype, field), count in sorted(family_counts.items()) if (z, dtype) == key}
        sequences = sorted(family_sequences[key])
        family_summary[label] = {
            "rejected_values": sum(fields.values()),
            "fields": fields,
            "records": sorted(family_records[key]),
            "first_sequence": sequences[0] if sequences else None,
            "last_sequence": sequences[-1] if sequences else None,
        }

    max_zeroed_magnitude = max(
        (max(abs(float(row["source_value"])), abs(float(row["native_value"])))
         for row in newly_accepted
         if row.get("e7_classification") == "E7_ZERO_FLOOR_ACCEPTED"),
        default=None,
    )
    min_retained_numeric_magnitude = min(numeric_magnitudes_retained, default=None)
    gates = {
        "CANONICAL_E7_FORMATTER_ACTIVE": "ACCEPT",
        "CANONICAL_ZERO_FLOOR_1E30_ACTIVE": "ACCEPT",
        "MAGNESIUM_TYPE73_REJECTIONS_ZERO": "ACCEPT" if family_summary["magnesium_type73"]["rejected_values"] == 0 else "REJECT",
        "MAGNESIUM_TYPE95_ANS6_NEAR_ZERO_REJECTIONS_ZERO": "ACCEPT" if family_summary["magnesium_type95"]["rejected_values"] == 0 else "REJECT",
        "RETAINED_ROWS_REALLY_DIFFER_AT_E7": "ACCEPT" if all(row.get("e7_equal") in (0, "0") for row in retained) else "REJECT",
    }
    result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "comparison_semantics": ".7e after per-value abs(value) < 1e-30 normalization to zero",
        "canonical_digits_after_decimal": CANONICAL_DIGITS,
        "canonical_zero_floor": CANONICAL_ZERO_FLOOR,
        "input_rejections": len(retained) + len(newly_accepted),
        "newly_accepted": len(newly_accepted),
        "accepted_zero_floor": accepted_zero_floor,
        "accepted_e7_roundoff": accepted_e7_roundoff,
        "retained_rejections": len(retained),
        "retained_by_category": dict(sorted(by_category.items())),
        "family_summary": family_summary,
        "max_zero_floor_accepted_magnitude": max_zeroed_magnitude,
        "min_retained_numeric_magnitude": min_retained_numeric_magnitude,
        "gates": gates,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    return report, retained, newly_accepted


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        fields = ["category", "sequence", "identity", "field", "source_value", "native_value", "source_e7", "native_e7", "e7_equal", "e7_classification"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-case", type=Path, required=True)
    parser.add_argument("--input-rejections", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--retained-csv", type=Path, required=True)
    parser.add_argument("--accepted-csv", type=Path, required=True)
    args = parser.parse_args()
    report, retained, accepted = audit(args.native_case, args.input_rejections)
    write_csv(args.retained_csv, retained)
    write_csv(args.accepted_csv, accepted)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
