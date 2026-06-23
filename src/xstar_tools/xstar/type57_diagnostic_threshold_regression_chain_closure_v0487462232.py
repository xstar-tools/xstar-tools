from __future__ import annotations

import argparse
import csv
import json
import math
import struct
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from . import post_type99_type68_residual_audit_v0487462231 as v2231

RELEASE = "0.6.48.7.46.21.13.2"
SCHEMA = "xstar-tools-v06487462232-type57-diagnostic-threshold-regression-chain-closure-v1"
EXPECTED_MAGNESIUM_TYPE57_RECORDS = 368


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def bit_exact(left: Any, right: Any) -> bool:
    return struct.pack("!d", float(left)) == struct.pack("!d", float(right))


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

    with tempfile.TemporaryDirectory(prefix="v0487462232_v2231_") as tmp:
        baseline_csv = Path(tmp) / "v2231_differences.csv"
        baseline = v2231.audit(
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
    source_keys: set[tuple[int, int]] = set()
    active_source_keys: set[tuple[int, int]] = set()
    source_counts: Counter[int] = Counter()
    for row in read_csv(source_capture / "v0472_all61_thermal_answer_channels.csv"):
        sequence = int(row["sequence"])
        if sequence not in selected_set:
            continue
        if int(row["element_z"]) != 12 or int(row["data_type"]) != 57:
            continue
        key = (sequence, int(row["record"]))
        source_keys.add(key)
        source_counts[sequence] += 1
        if abs(float(row["ans5"])) > 0.0 or abs(float(row["ans6"])) > 0.0:
            active_source_keys.add(key)

    native_keys: set[tuple[int, int]] = set()
    native_counts: Counter[int] = Counter()
    threshold_mismatches: list[dict[str, Any]] = []
    nonpositive_active = 0
    missing_serialized = 0
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
            record = int(row["record"])
            key = (sequence, record)
            native_keys.add(key)
            native_counts[sequence] += 1
            serialized = thresholds.get(record)
            if serialized is None:
                missing_serialized += 1
                continue
            diagnostic = float(row["line_energy_ev"])
            if not bit_exact(serialized, diagnostic):
                threshold_mismatches.append(
                    {
                        "domain": "magnesium_type57_threshold",
                        "sequence": sequence,
                        "identity": f"record={record}",
                        "field": "line_energy_ev",
                        "serialized_value": format(serialized, ".17g"),
                        "diagnostic_value": format(diagnostic, ".17g"),
                        "serialized_hex": float(serialized).hex(),
                        "diagnostic_hex": float(diagnostic).hex(),
                    }
                )
            if key in active_source_keys and not diagnostic > 0.0:
                nonpositive_active += 1

    source_domain_exact = (
        bool(source_keys)
        and all(source_counts[sequence] == EXPECTED_MAGNESIUM_TYPE57_RECORDS for sequence in selected)
    )
    native_inventory_exact = (
        source_domain_exact
        and source_keys == native_keys
        and all(native_counts[sequence] == EXPECTED_MAGNESIUM_TYPE57_RECORDS for sequence in selected)
        and missing_serialized == 0
    )
    diagnostic_exact = native_inventory_exact and not threshold_mismatches
    active_positive = diagnostic_exact and nonpositive_active == 0

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
        "MAGNESIUM_TYPE57_DIAGNOSTIC_THRESHOLD_BIT_EXACT": (
            "ACCEPT" if diagnostic_exact else "REJECT"
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
        "serialized_value",
        "diagnostic_value",
        "serialized_hex",
        "diagnostic_hex",
    )
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(threshold_mismatches)

    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "focused_scientific_result": result,
        "required_gates": required_gates,
        "magnesium_type57_threshold_transport": {
            "serialized_records": len(thresholds),
            "source_rows": len(source_keys),
            "native_rows": len(native_keys),
            "active_source_rows": len(active_source_keys),
            "source_counts_by_sequence": dict(sorted(source_counts.items())),
            "native_counts_by_sequence": dict(sorted(native_counts.items())),
            "missing_serialized_records": missing_serialized,
            "diagnostic_threshold_mismatches": len(threshold_mismatches),
            "nonpositive_active_threshold_rows": nonpositive_active,
            "serialized_threshold_min_ev": min(thresholds.values()),
            "serialized_threshold_max_ev": max(thresholds.values()),
        },
        "v21_13_1_regression": {
            "result": baseline.get("result", "REJECT"),
            "required_gates": prior,
        },
        "residual_family_attribution": baseline.get("residual_family_attribution", {}),
        "canonical": baseline.get("canonical", {}),
        "focused_rejections": len(threshold_mismatches),
        "first_focused_rejection": threshold_mismatches[0] if threshold_mismatches else None,
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
            "errors": [f"{type(exc).__name__}: {exc}"],
            "diagnostic_only": True,
            "physics_changes": [],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
