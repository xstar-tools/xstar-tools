from __future__ import annotations

import argparse
import csv
import json
import math
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from . import post_type99_type68_residual_audit_v0487462231 as v2331

RELEASE = "0.6.48.7.46.21.13.2.1"
SCHEMA = "xstar-tools-v064874622321-type57-diagnostic-threshold-e10-gate-semantics-v1"
EXPECTED_MAGNESIUM_TYPE57_RECORDS = 368


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def canonical_e10(value: Any) -> str:
    number = float(value)
    if not math.isfinite(number):
        return str(number)
    return format(number, ".10e")


def _case_type57_thresholds(native_case: Path) -> dict[int, float]:
    elements = {
        int(row["element_index"]): int(row["element_z"])
        for row in read_csv(native_case / "elements.csv")
    }
    thresholds: dict[int, float] = {}
    for row in read_csv(native_case / "records.csv"):
        if elements.get(int(row["element_index"])) != 12 or int(row["data_type"]) != 57:
            continue
        record = int(row["record"])
        threshold = float(row["line_energy_ev"])
        if record in thresholds:
            raise ValueError(f"duplicate Magnesium Type-57 record {record}")
        if not math.isfinite(threshold) or not threshold > 0.0:
            raise ValueError(
                f"Magnesium Type-57 record {record} has invalid serialized threshold {threshold}"
            )
        thresholds[record] = threshold
    if len(thresholds) != EXPECTED_MAGNESIUM_TYPE57_RECORDS:
        raise ValueError(
            "Magnesium Type-57 serialized inventory mismatch: "
            f"expected {EXPECTED_MAGNESIUM_TYPE57_RECORDS}, found {len(thresholds)}"
        )
    return thresholds


def audit(
    source_capture: Path,
    native_evaluations: Path,
    native_case: Path,
    controller: Path | None,
    canonical_report: Path | None,
    canonical_rejections: Path | None,
    output_csv: Path,
    sequences: Iterable[int] = range(1, 62),
) -> dict[str, Any]:
    selected = tuple(int(value) for value in sequences)
    selected_set = set(selected)

    with tempfile.TemporaryDirectory(prefix="v04874622321_v2331_") as tmp:
        baseline_csv = Path(tmp) / "v2331_differences.csv"
        baseline = v2331.audit(
            source_capture,
            native_evaluations,
            native_case,
            controller,
            canonical_report,
            canonical_rejections,
            baseline_csv,
            selected,
        )

    thresholds = _case_type57_thresholds(native_case)
    serialized_records = set(thresholds)

    source_keys: set[tuple[int, int]] = set()
    active_source_keys: set[tuple[int, int]] = set()
    source_counts: Counter[int] = Counter()
    source_rows_total = 0
    duplicate_source_rows = 0
    unknown_source_records: set[int] = set()
    for row in read_csv(source_capture / "v0472_all61_thermal_answer_channels.csv"):
        sequence = int(row["sequence"])
        if sequence not in selected_set:
            continue
        if int(row["element_z"]) != 12 or int(row["data_type"]) != 57:
            continue
        source_rows_total += 1
        record = int(row["record"])
        key = (sequence, record)
        if key in source_keys:
            duplicate_source_rows += 1
        source_keys.add(key)
        source_counts[sequence] += 1
        if record not in serialized_records:
            unknown_source_records.add(record)
        if abs(float(row["ans5"])) > 0.0 or abs(float(row["ans6"])) > 0.0:
            active_source_keys.add(key)

    native_keys: set[tuple[int, int]] = set()
    native_counts: Counter[int] = Counter()
    native_thresholds: dict[tuple[int, int], float] = {}
    native_rows_total = 0
    duplicate_native_rows = 0
    missing_serialized = 0
    e10_mismatches: list[dict[str, Any]] = []
    bit_different_e10_equal = 0
    for sequence in selected:
        path = (
            native_evaluations
            / f"evaluation_{sequence:04d}"
            / "qualification_diagnostics"
            / f"evaluation_{sequence:04d}_records.csv"
        )
        for row in read_csv(path):
            if int(row.get("element_z", "0")) != 12 or int(row.get("data_type", "0")) != 57:
                continue
            native_rows_total += 1
            record = int(row["record"])
            key = (sequence, record)
            if key in native_keys:
                duplicate_native_rows += 1
            native_keys.add(key)
            native_counts[sequence] += 1
            diagnostic = float(row["line_energy_ev"])
            native_thresholds[key] = diagnostic
            serialized = thresholds.get(record)
            if serialized is None:
                missing_serialized += 1
                continue
            serialized_e10 = canonical_e10(serialized)
            diagnostic_e10 = canonical_e10(diagnostic)
            if serialized_e10 != diagnostic_e10:
                e10_mismatches.append(
                    {
                        "domain": "magnesium_type57_threshold",
                        "sequence": sequence,
                        "identity": f"record={record}",
                        "field": "line_energy_ev",
                        "source_value": format(serialized, ".17g"),
                        "native_value": format(diagnostic, ".17g"),
                        "source_e10": serialized_e10,
                        "native_e10": diagnostic_e10,
                    }
                )
            elif serialized.hex() != diagnostic.hex():
                bit_different_e10_equal += 1

    source_domain_exact = (
        bool(source_keys)
        and source_rows_total == len(source_keys)
        and duplicate_source_rows == 0
        and not unknown_source_records
        and all(source_counts[sequence] > 0 for sequence in selected)
        and source_keys.issubset(native_keys)
    )
    native_inventory_exact = (
        bool(native_keys)
        and native_rows_total == len(native_keys)
        and duplicate_native_rows == 0
        and all(native_counts[sequence] == EXPECTED_MAGNESIUM_TYPE57_RECORDS for sequence in selected)
        and len(native_keys) == EXPECTED_MAGNESIUM_TYPE57_RECORDS * len(selected)
        and missing_serialized == 0
    )
    diagnostic_e10 = native_inventory_exact and not e10_mismatches

    missing_active_native = active_source_keys - native_keys
    nonpositive_active_keys = {
        key for key in active_source_keys
        if key in native_thresholds and not native_thresholds[key] > 0.0
    }
    active_positive = (
        source_domain_exact
        and not missing_active_native
        and not nonpositive_active_keys
    )

    prior = baseline.get("required_gates", {})
    v21_11 = prior.get("V21_11_TYPE53_TYPE57_AND_V21_9_REGRESSION") == "ACCEPT"
    v21_12 = prior.get("V21_12_TYPE49_REGRESSION") == "ACCEPT"
    v21_13 = prior.get("V21_13_TYPE99_AND_PRIOR_REGRESSION") == "ACCEPT"
    v21_13_1 = bool(prior) and all(value == "ACCEPT" for value in prior.values())

    required_gates = {
        "MAGNESIUM_TYPE57_SERIALIZED_THRESHOLD_INVENTORY_EXACT": (
            "ACCEPT" if len(thresholds) == EXPECTED_MAGNESIUM_TYPE57_RECORDS else "REJECT"
        ),
        "MAGNESIUM_TYPE57_THRESHOLD_SOURCE_DOMAIN_EXACT": (
            "ACCEPT" if source_domain_exact else "REJECT"
        ),
        "MAGNESIUM_TYPE57_THRESHOLD_NATIVE_INVENTORY_EXACT": (
            "ACCEPT" if native_inventory_exact else "REJECT"
        ),
        "MAGNESIUM_TYPE57_DIAGNOSTIC_THRESHOLD_IEEE_E10": (
            "ACCEPT" if diagnostic_e10 else "REJECT"
        ),
        "MAGNESIUM_TYPE57_ACTIVE_SOURCE_THRESHOLDS_POSITIVE": (
            "ACCEPT" if active_positive else "REJECT"
        ),
        "V21_11_TYPE53_TYPE57_AND_V21_9_REGRESSION": "ACCEPT" if v21_11 else "REJECT",
        "V21_12_TYPE49_REGRESSION": "ACCEPT" if v21_12 else "REJECT",
        "V21_13_TYPE99_AND_PRIOR_REGRESSION": "ACCEPT" if v21_13 else "REJECT",
        "V21_13_1_TYPE68_AND_PRIOR_REGRESSION": "ACCEPT" if v21_13_1 else "REJECT",
    }
    result = "ACCEPT" if all(value == "ACCEPT" for value in required_gates.values()) else "REJECT"

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "domain",
        "sequence",
        "identity",
        "field",
        "source_value",
        "native_value",
        "source_e10",
        "native_e10",
    )
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(e10_mismatches)

    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "focused_scientific_result": result,
        "comparison_semantics": "canonical normalized E-notation with 10 digits after decimal (.10e)",
        "required_gates": required_gates,
        "magnesium_type57_threshold_transport": {
            "serialized_records": len(thresholds),
            "source_rows": len(source_keys),
            "native_rows": len(native_keys),
            "active_source_rows": len(active_source_keys),
            "source_counts_by_sequence": dict(sorted(source_counts.items())),
            "native_counts_by_sequence": dict(sorted(native_counts.items())),
            "source_capture_rows_total": source_rows_total,
            "native_diagnostic_rows_total": native_rows_total,
            "duplicate_source_rows": duplicate_source_rows,
            "duplicate_native_rows": duplicate_native_rows,
            "unknown_source_records": sorted(unknown_source_records),
            "missing_serialized_records": missing_serialized,
            "diagnostic_threshold_e10_mismatches": len(e10_mismatches),
            "bit_different_e10_equal": bit_different_e10_equal,
            "missing_active_native_rows": len(missing_active_native),
            "nonpositive_active_threshold_rows": len(nonpositive_active_keys),
            "serialized_threshold_min_ev": min(thresholds.values()),
            "serialized_threshold_max_ev": max(thresholds.values()),
        },
        "v21_13_1_regression": {
            "result": baseline.get("result", "REJECT"),
            "required_gates": prior,
        },
        "residual_family_attribution": baseline.get("residual_family_attribution", {}),
        "canonical": baseline.get("canonical", {}),
        "focused_rejections": len(e10_mismatches),
        "first_focused_rejection": e10_mismatches[0] if e10_mismatches else None,
        "diagnostic_only": True,
        "physics_changes": [],
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
    parser.add_argument("--native-case", type=Path, required=True)
    parser.add_argument("--native-controller", type=Path)
    parser.add_argument("--canonical-report", type=Path)
    parser.add_argument("--canonical-rejections", type=Path)
    parser.add_argument("--sequences", default="1-61")
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(
            args.source_capture.resolve(),
            args.native_evaluations.resolve(),
            args.native_case.resolve(),
            args.native_controller.resolve() if args.native_controller else None,
            args.canonical_report.resolve() if args.canonical_report else None,
            args.canonical_rejections.resolve() if args.canonical_rejections else None,
            args.output_csv.resolve(),
            parse_sequences(args.sequences),
        )
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "focused_scientific_result": "REJECT",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
