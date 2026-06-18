#!/usr/bin/env python3
"""Audit the v46.9.6 Mg Type-50 endpoint-orientation correction."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.9.6"
TARGET_RECORDS = (40066, 40095, 40108, 40134, 41209)
EXPECTED_BASELINE_ROWS = 1124
EXPECTED_RECORD_EVALUATIONS = 281


def _read_causal(path: Path):
    candidate = path / "all61_dense_matrix_causal_records.csv.gz"
    if candidate.exists():
        with gzip.open(candidate, "rt", newline="") as handle:
            yield from csv.DictReader(handle)
        return
    candidate = path / "all61_dense_matrix_causal_records.csv"
    with candidate.open(newline="") as handle:
        yield from csv.DictReader(handle)


def _case_rows(root: Path) -> dict[int, dict[str, str]]:
    with (root / "native_case_all61" / "records.csv").open(newline="") as handle:
        return {int(row["record"]): row for row in csv.DictReader(handle)}


def analyze(baseline: Path, current: Path) -> dict[str, Any]:
    errors: list[str] = []
    targets = set(TARGET_RECORDS)
    baseline_rows = [r for r in _read_causal(baseline)
                     if int(r["element_z"]) == 12 and int(r["data_type"]) == 50
                     and r["classification"] == "ENDPOINT_ORIENTATION_DELTA"]
    current_orientation = [r for r in _read_causal(current)
                           if int(r["element_z"]) == 12 and int(r["data_type"]) == 50
                           and r["classification"] == "ENDPOINT_ORIENTATION_DELTA"]
    current_target = [r for r in _read_causal(current)
                      if int(r["element_z"]) == 12 and int(r["data_type"]) == 50
                      and int(r["record"]) in targets]
    baseline_pairs = {(int(r["sequence"]), int(r["record"])) for r in baseline_rows}
    baseline_records = {int(r["record"]) for r in baseline_rows}

    before = _case_rows(baseline)
    after = _case_rows(current)
    changed: list[dict[str, Any]] = []
    non_endpoint_changes: list[dict[str, Any]] = []
    for record in sorted(set(before) & set(after)):
        left, right = before[record], after[record]
        differing = [key for key in left if left[key] != right.get(key)]
        if differing:
            changed.append({"record": record, "fields": differing,
                            "before_lower": left["lower_row"], "before_upper": left["upper_row"],
                            "after_lower": right["lower_row"], "after_upper": right["upper_row"]})
            if set(differing) - {"lower_row", "upper_row"}:
                non_endpoint_changes.append(changed[-1])

    changed_records = {row["record"] for row in changed}
    swapped_exact = all(
        before[r]["lower_row"] == after[r]["upper_row"]
        and before[r]["upper_row"] == after[r]["lower_row"]
        for r in targets
    )
    gates = {
        "MG_TYPE50_BASELINE_ORIENTATION_ROWS_EXPECTED": "ACCEPT" if len(baseline_rows) == EXPECTED_BASELINE_ROWS else "REJECT",
        "MG_TYPE50_BASELINE_RECORD_EVALUATIONS_EXPECTED": "ACCEPT" if len(baseline_pairs) == EXPECTED_RECORD_EVALUATIONS else "REJECT",
        "MG_TYPE50_TARGET_RECORDS_EXACT": "ACCEPT" if baseline_records == targets else "REJECT",
        "MG_TYPE50_ENDPOINT_ORIENTATION_DELTAS_ZERO": "ACCEPT" if not current_orientation else "REJECT",
        "MG_TYPE50_TARGET_RESIDUAL_ROWS_ZERO": "ACCEPT" if not current_target else "REJECT",
        "MG_TYPE50_ONLY_TARGET_ENDPOINT_FIELDS_CHANGED": "ACCEPT" if changed_records == targets and not non_endpoint_changes else "REJECT",
        "MG_TYPE50_TARGET_ENDPOINTS_SWAPPED_EXACT": "ACCEPT" if swapped_exact else "REJECT",
        "MG_TYPE50_ORIENTATION_CORRECTION": "ACCEPT",
    }
    if any(value != "ACCEPT" for key, value in gates.items() if key != "MG_TYPE50_ORIENTATION_CORRECTION"):
        gates["MG_TYPE50_ORIENTATION_CORRECTION"] = "REJECT"
        errors.append("one or more Type-50 endpoint-orientation gates rejected")
    return {
        "schema": "xstar-tools-v064874696-mg-type50-endpoint-orientation-v1",
        "release": RELEASE,
        "result": gates["MG_TYPE50_ORIENTATION_CORRECTION"],
        "errors": errors,
        "baseline_orientation_rows": len(baseline_rows),
        "baseline_record_evaluations": len(baseline_pairs),
        "baseline_target_records": sorted(baseline_records),
        "current_orientation_rows": len(current_orientation),
        "current_target_residual_rows": len(current_target),
        "changed_case_records": changed,
        "non_endpoint_changes": non_endpoint_changes,
        "classification_counts_current": dict(Counter(r["classification"] for r in current_target)),
        "gates": gates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-audit", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.baseline_audit, args.audit_output)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
