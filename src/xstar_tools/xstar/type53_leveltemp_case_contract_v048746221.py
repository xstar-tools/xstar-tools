from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.13"
SCHEMA = "xstar-tools-v0648746221-type53-leveltemp-case-contract-v1"
EXPECTED_MAGNESIUM_TYPE53_RECORDS = 876
LAYOUT_MAGIC = 221
CONTEXT_REALS = 22
CANDIDATE_COUNT = 12


def _read_vector(path: Path, cast: type[float] | type[int]) -> list[float] | list[int]:
    values: list[float] | list[int] = []
    with path.open() as handle:
        for line in handle:
            text = line.strip()
            if text:
                values.append(cast(text))
    return values


def audit_case(case_dir: Path) -> dict[str, Any]:
    required = ("elements.csv", "records.csv", "reals.txt", "ints.txt")
    errors = [f"missing {name}" for name in required if not (case_dir / name).is_file()]
    if errors:
        return {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": errors, "case_dir": str(case_dir),
        }

    with (case_dir / "elements.csv").open(newline="") as handle:
        elements = list(csv.DictReader(handle))
    mg = next((row for row in elements if int(row["element_z"]) == 12), None)
    if mg is None:
        return {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": ["native case has no Magnesium element"], "case_dir": str(case_dir),
        }
    element_index = int(mg["element_index"])
    reals = _read_vector(case_dir / "reals.txt", float)
    ints = _read_vector(case_dir / "ints.txt", int)

    total = 0
    valid = 0
    masks: set[int] = set()
    destination_columns: set[int] = set()
    candidate_counts: set[int] = set()
    real_counts: set[int] = set()
    int_counts: set[int] = set()
    errors = []
    with (case_dir / "records.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["element_index"]) != element_index or int(row["data_type"]) != 53:
                continue
            total += 1
            record = int(row["record"])
            real_offset = int(row["real_offset"])
            real_count = int(row["real_count"])
            int_offset = int(row["int_offset"])
            int_count = int(row["int_count"])
            real_counts.add(real_count)
            int_counts.add(int_count)
            record_errors: list[str] = []
            if int_count < 4 or int_offset + int_count > len(ints):
                record_errors.append("short integer payload")
            if real_count < 4 + CONTEXT_REALS or real_offset + real_count > len(reals):
                record_errors.append("short real payload")
            if real_count >= CONTEXT_REALS and (real_count - CONTEXT_REALS) % 2 != 0:
                record_errors.append("non-paired Type-53 cross-section payload")
            if not record_errors:
                magic = int(ints[int_offset + 3])
                destination_column = int(ints[int_offset + 1])
                mask = int(ints[int_offset + 2])
                if magic != LAYOUT_MAGIC:
                    record_errors.append(f"layout magic {magic} != {LAYOUT_MAGIC}")
                if destination_column <= 0:
                    record_errors.append("non-positive destination column")
                if mask < 0 or mask > 0x0FFF:
                    record_errors.append("candidate mask outside 12 stages")
                context_base = real_offset + real_count - CONTEXT_REALS
                candidates = [float(reals[context_base + 10 + stage]) for stage in range(CANDIDATE_COUNT)]
                present = 0
                for stage, value in enumerate(candidates, start=1):
                    if mask & (1 << (stage - 1)):
                        present += 1
                        if not math.isfinite(value):
                            record_errors.append(f"stage-{stage} candidate is non-finite")
                incoming = float(reals[context_base + 7])
                if not math.isfinite(incoming):
                    record_errors.append("incoming persistent destination energy is non-finite")
                masks.add(mask)
                destination_columns.add(destination_column)
                candidate_counts.add(present)
            if record_errors:
                errors.extend(f"record {record}: {message}" for message in record_errors)
            else:
                valid += 1

    if total != EXPECTED_MAGNESIUM_TYPE53_RECORDS:
        errors.append(
            f"Magnesium Type-53 inventory {total} != {EXPECTED_MAGNESIUM_TYPE53_RECORDS}"
        )
    if valid != total:
        errors.append(f"valid Magnesium Type-53 payloads {valid} != inventory {total}")

    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "case_dir": str(case_dir),
        "magnesium_type53_records": total,
        "valid_type53_records": valid,
        "expected_magnesium_type53_records": EXPECTED_MAGNESIUM_TYPE53_RECORDS,
        "layout_magic": LAYOUT_MAGIC,
        "candidate_slots": CANDIDATE_COUNT,
        "candidate_presence_counts": sorted(candidate_counts),
        "candidate_masks_distinct": len(masks),
        "destination_columns_distinct": len(destination_columns),
        "real_count_values": sorted(real_counts),
        "int_count_values": sorted(int_counts),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    report = audit_case(args.case_dir.resolve())
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
