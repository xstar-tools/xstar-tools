"""Validate the rejected v46.20 Mg Type-99 capture as a runtime-inventory boundary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.2"
SCHEMA = "xstar-tools-v0648746201-v4620-runtime-inventory-causal-baseline-v1"
EXPECTED_COUNTS = {
    **{sequence: 9 for sequence in range(1, 5)},
    **{sequence: 10 for sequence in range(5, 7)},
    **{sequence: 11 for sequence in range(7, 62)},
}
EXPECTED_ROWS = sum(EXPECTED_COUNTS.values())
EXPECTED_UNIQUE = 11
EXPECTED_OLD_ERRORS = {
    "ucalc_rows=661 expected=793",
    f"ucalc_records_by_sequence={EXPECTED_COUNTS}",
    "ucalc_unique_records=11",
}


def validate(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text())
    errors: list[str] = []
    observed = set(report.get("errors", []))
    if report.get("result") != "REJECT":
        errors.append("v4620_result_not_reject")
    if observed != EXPECTED_OLD_ERRORS:
        errors.append(f"unexpected_v4620_errors={sorted(observed)}")
    checks = {
        "evaluations_61": report.get("evaluations") == 61,
        "ucalc_rows_661": report.get("magnesium_type99_ucalc_rows") == EXPECTED_ROWS,
        "ucalc_unique_records_11": report.get("magnesium_type99_unique_ucalc_records") == EXPECTED_UNIQUE,
        "runtime_counts_exact": report.get("magnesium_type99_active_records_by_sequence") == {str(k): v for k, v in EXPECTED_COUNTS.items()} or report.get("magnesium_type99_active_records_by_sequence") == EXPECTED_COUNTS,
        "runtime_union_11": report.get("magnesium_type99_active_record_union") == 11,
        "thermal_rows_1322": report.get("magnesium_type99_primary_thermal_rows") == 1322,
        "family_rows_61": report.get("magnesium_type99_family_rows") == 61,
        "type50_capture_accept": report.get("type50_endpoint_capture_result") == "ACCEPT",
        "qualification_only": report.get("qualification_only") is True,
        "production_blocked": report.get("production_promotion_ready") is False,
    }
    for name, accepted in checks.items():
        if not accepted:
            errors.append(name)
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "baseline_release": "0.6.48.7.46.20",
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "accepted_gates": {name.upper(): "ACCEPT" if value else "REJECT" for name, value in checks.items()},
        "old_errors_exact": observed == EXPECTED_OLD_ERRORS,
        "physics_changed": False,
        "native_replay_required": True,
        "source_recapture_required": False,
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = validate(args.report.resolve())
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "physics_changed": False,
            "source_recapture_required": False,
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
