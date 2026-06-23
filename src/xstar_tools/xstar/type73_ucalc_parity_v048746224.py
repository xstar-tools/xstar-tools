from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.14"
SCHEMA = "xstar-tools-v06487462114-type73-ucalc-parity-v1"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def canonical(value: Any, digits: int) -> str:
    number = float(value)
    if not math.isfinite(number):
        return str(number)
    return format(number, f".{digits}e")


def case_record_types(native_case: Path) -> dict[tuple[int, int], int]:
    elements = {
        int(row["element_index"]): int(row["element_z"])
        for row in read_csv(native_case / "elements.csv")
    }
    result: dict[tuple[int, int], int] = {}
    for row in read_csv(native_case / "records.csv"):
        z = elements[int(row["element_index"])]
        result[(z, int(row["record"]))] = int(row["data_type"])
    return result


def parse_answer_identity(identity: str) -> tuple[int, int] | None:
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
    if "element_z" not in values or "record" not in values:
        return None
    return values["element_z"], values["record"]


def audit(native_case: Path, canonical_rejections: Path, canonical_report: Path | None = None) -> dict[str, Any]:
    record_types = case_record_types(native_case)
    family_counts: Counter[tuple[int, int]] = Counter()
    family_fields: dict[tuple[int, int], Counter[str]] = defaultdict(Counter)
    family_records: dict[tuple[int, int], set[int]] = defaultdict(set)
    family_sequences: dict[tuple[int, int], set[int]] = defaultdict(set)
    type73_rows: list[dict[str, Any]] = []
    type73_e8_rejections = 0
    relative_errors: list[float] = []

    for row in read_csv(canonical_rejections):
        if row.get("category") != "canonical_answer_channels":
            continue
        parsed = parse_answer_identity(row.get("identity", ""))
        if parsed is None:
            continue
        z, record = parsed
        data_type = record_types.get((z, record), -1)
        key = (z, data_type)
        family_counts[key] += 1
        family_fields[key][row.get("field", "")] += 1
        family_records[key].add(record)
        family_sequences[key].add(int(row["sequence"]))
        if key == (12, 73) and row.get("field") in {"ans5", "ans6"}:
            source = float(row["source_value"])
            native = float(row["native_value"])
            source_e8 = canonical(source, 8)
            native_e8 = canonical(native, 8)
            if source_e8 != native_e8:
                type73_e8_rejections += 1
            if source != 0.0:
                relative_errors.append((native - source) / source)
            type73_rows.append({
                **row,
                "source_e8": source_e8,
                "native_e8": native_e8,
                "e8_equal": int(source_e8 == native_e8),
                "data_type": 73,
                "element_z": 12,
                "record": record,
            })

    type73_e10_rejections = len(type73_rows)
    gates = {
        "MAGNESIUM_TYPE73_ANS5_ANS6_IEEE_E10": "ACCEPT" if type73_e10_rejections == 0 else "REJECT",
        "MAGNESIUM_TYPE73_ANS5_ANS6_IEEE_E8": "ACCEPT" if type73_e8_rejections == 0 else "REJECT",
        "MAGNESIUM_TYPE73_RESIDUAL_RECORDS_ZERO": "ACCEPT" if not family_records[(12, 73)] else "REJECT",
    }
    focused_result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"

    labels = {
        (12, 72): "magnesium_type72",
        (12, 73): "magnesium_type73",
        (12, 95): "magnesium_type95",
        (2, 53): "helium_type53",
    }
    residuals: dict[str, Any] = {}
    for key, label in labels.items():
        seqs = sorted(family_sequences[key])
        residuals[label] = {
            "rejected_values": family_counts[key],
            "fields": dict(sorted(family_fields[key].items())),
            "records": len(family_records[key]),
            "first_sequence": seqs[0] if seqs else None,
            "last_sequence": seqs[-1] if seqs else None,
        }

    canonical_summary: dict[str, Any] = {}
    if canonical_report is not None and canonical_report.is_file():
        report = json.loads(canonical_report.read_text())
        canonical_summary = {
            "result": report.get("result"),
            "rejected_differences": report.get("rejected_differences"),
            "first_rejection": report.get("first_rejection"),
            "controller_summary": report.get("controller_summary"),
        }

    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": focused_result,
        "required_gates": gates,
        "comparison_semantics": {
            "canonical_host_report": ".10e",
            "additional_user_requested_view": ".8e",
        },
        "magnesium_type73": {
            "e10_rejected_values": type73_e10_rejections,
            "e8_rejected_values": type73_e8_rejections,
            "records": len(family_records[(12, 73)]),
            "sequences": len(family_sequences[(12, 73)]),
            "relative_error_min": min(relative_errors) if relative_errors else None,
            "relative_error_median": statistics.median(relative_errors) if relative_errors else None,
            "relative_error_max": max(relative_errors) if relative_errors else None,
            "source_contract": "ucalc.py Type-73 literal wavelength energy and legacy collision constants",
        },
        "residual_family_attribution": residuals,
        "canonical": canonical_summary,
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-case", type=Path, required=True)
    parser.add_argument("--canonical-rejections", type=Path, required=True)
    parser.add_argument("--canonical-report", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    args = parser.parse_args()

    report = audit(args.native_case, args.canonical_rejections, args.canonical_report)
    rows: list[dict[str, Any]] = []
    record_types = case_record_types(args.native_case)
    for row in read_csv(args.canonical_rejections):
        if row.get("category") != "canonical_answer_channels":
            continue
        parsed = parse_answer_identity(row.get("identity", ""))
        if parsed is None:
            continue
        z, record = parsed
        if z != 12 or record_types.get((z, record)) != 73 or row.get("field") not in {"ans5", "ans6"}:
            continue
        source = float(row["source_value"])
        native = float(row["native_value"])
        rows.append({
            **row,
            "element_z": z,
            "data_type": 73,
            "record": record,
            "source_e8": canonical(source, 8),
            "native_e8": canonical(native, 8),
            "e8_equal": int(canonical(source, 8) == canonical(native, 8)),
        })
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else [
        "category", "sequence", "identity", "field", "source_value", "native_value",
        "source_e10", "native_e10", "bit_exact", "e10_equal", "ulp_distance",
        "classification", "detail", "element_z", "data_type", "record",
        "source_e8", "native_e8", "e8_equal",
    ]
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
