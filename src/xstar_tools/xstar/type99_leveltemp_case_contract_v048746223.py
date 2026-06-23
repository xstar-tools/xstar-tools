from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.13"
SCHEMA = "xstar-tools-v0648746223-type99-leveltemp-energy-weight-case-contract-v1"
EXPECTED_MAGNESIUM_TYPE99_RECORDS = 13
LAYOUT_MAGIC = 223
CANDIDATE_COUNT = 12
CONTEXT_REAL_COUNT = 83
CONTEXT_INT_COUNT = 8


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


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
    missing = [name for name in required if not (case_dir / name).is_file()]
    if missing:
        return {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [f"missing {name}" for name in missing],
            "case_dir": str(case_dir),
        }

    elements = _read_csv(case_dir / "elements.csv")
    mg = next((row for row in elements if int(row["element_z"]) == 12), None)
    if mg is None:
        return {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": ["native case has no Magnesium element"],
            "case_dir": str(case_dir),
        }
    element_index = int(mg["element_index"])
    reals = _read_vector(case_dir / "reals.txt", float)
    ints = _read_vector(case_dir / "ints.txt", int)

    total = 0
    valid = 0
    errors: list[str] = []
    modes: set[int] = set()
    bound_columns: set[int] = set()
    parent_columns: set[int] = set()
    destination_columns: set[int] = set()
    mask_counts = {"bound": set(), "parent": set(), "destination": set()}
    real_counts: set[int] = set()
    int_counts: set[int] = set()

    for row in _read_csv(case_dir / "records.csv"):
        if int(row["element_index"]) != element_index or int(row["data_type"]) != 99:
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
        if int_count < 3 + CONTEXT_INT_COUNT or int_offset + int_count > len(ints):
            record_errors.append("short integer payload")
        if real_offset + real_count > len(reals):
            record_errors.append("short real payload")
        if record_errors:
            errors.extend(f"record {record}: {message}" for message in record_errors)
            continue

        nden, ntem, nxs = (int(ints[int_offset + i]) for i in range(3))
        if nden <= 0 or ntem <= 1 or nxs <= 1:
            record_errors.append("invalid calt99 dimensions")
            core = -1
        else:
            core = nden + ntem + nden * ntem + 2 * nxs
        if core >= 0 and real_count != core + CONTEXT_REAL_COUNT:
            record_errors.append(
                f"real payload {real_count} != calt99 core {core} + context {CONTEXT_REAL_COUNT}"
            )

        ibase = int_offset + int_count - CONTEXT_INT_COUNT
        bound_column = int(ints[ibase + 0])
        parent_column = int(ints[ibase + 1])
        destination_column = int(ints[ibase + 2])
        bound_mask = int(ints[ibase + 3])
        parent_mask = int(ints[ibase + 4])
        destination_mask = int(ints[ibase + 5])
        mode = int(ints[ibase + 6])
        magic = int(ints[ibase + 7])
        if magic != LAYOUT_MAGIC:
            record_errors.append(f"layout magic {magic} != {LAYOUT_MAGIC}")
        if min(bound_column, parent_column, destination_column) <= 0:
            record_errors.append("non-positive leveltemp column")
        for label, mask in (
            ("bound", bound_mask),
            ("parent", parent_mask),
            ("destination", destination_mask),
        ):
            if mask < 0 or mask > 0x0FFF:
                record_errors.append(f"{label} mask outside 12 stages")
            mask_counts[label].add(mask.bit_count() if mask >= 0 else -1)
        if mode not in (0, 1):
            record_errors.append("invalid excited-parent mode")

        if core >= 0 and real_count == core + CONTEXT_REAL_COUNT:
            base = real_offset + core
            incoming = [float(reals[base + i]) for i in range(3, 11)]
            if not all(math.isfinite(value) for value in incoming):
                record_errors.append("non-finite incoming/literal context")
            candidate_groups = (
                ("bound", bound_mask, 11, 23),
                ("parent", parent_mask, 35, 47),
                ("destination", destination_mask, 59, 71),
            )
            for label, mask, energy_start, weight_start in candidate_groups:
                for stage in range(CANDIDATE_COUNT):
                    if not (mask & (1 << stage)):
                        continue
                    energy = float(reals[base + energy_start + stage])
                    weight = float(reals[base + weight_start + stage])
                    if not math.isfinite(energy) or not math.isfinite(weight) or weight <= 0.0:
                        record_errors.append(f"invalid {label} stage-{stage + 1} candidate")
            if bound_mask == 0 and incoming[1] <= 0.0:
                record_errors.append("unresolvable bound weight")
            if parent_mask == 0 and incoming[3] <= 0.0 and mode == 0:
                record_errors.append("unresolvable parent weight")
            if destination_mask == 0 and incoming[5] <= 0.0:
                record_errors.append("unresolvable destination weight")
            if mode == 1 and incoming[7] <= 0.0:
                record_errors.append("invalid excited-parent statistical weight")

        if record_errors:
            errors.extend(f"record {record}: {message}" for message in record_errors)
        else:
            valid += 1
            modes.add(mode)
            bound_columns.add(bound_column)
            parent_columns.add(parent_column)
            destination_columns.add(destination_column)

    if total != EXPECTED_MAGNESIUM_TYPE99_RECORDS:
        errors.append(
            f"Magnesium Type-99 inventory {total} != {EXPECTED_MAGNESIUM_TYPE99_RECORDS}"
        )
    if valid != total:
        errors.append(f"valid Magnesium Type-99 payloads {valid} != inventory {total}")

    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "case_dir": str(case_dir),
        "magnesium_type99_records": total,
        "valid_type99_records": valid,
        "expected_magnesium_type99_records": EXPECTED_MAGNESIUM_TYPE99_RECORDS,
        "layout_magic": LAYOUT_MAGIC,
        "context_real_count": CONTEXT_REAL_COUNT,
        "context_int_count": CONTEXT_INT_COUNT,
        "candidate_slots_per_column": CANDIDATE_COUNT,
        "excited_parent_modes": sorted(modes),
        "bound_columns_distinct": len(bound_columns),
        "parent_columns_distinct": len(parent_columns),
        "destination_columns_distinct": len(destination_columns),
        "candidate_presence_counts": {
            key: sorted(values) for key, values in mask_counts.items()
        },
        "real_count_values": sorted(real_counts),
        "int_count_values": sorted(int_counts),
        "qualification_only": True,
        "production_promotion_ready": False,
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
