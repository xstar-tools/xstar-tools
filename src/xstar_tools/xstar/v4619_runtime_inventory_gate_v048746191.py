"""Validate the rejected v46.19 Mg Type-50 capture as a count-contract boundary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.3"
SCHEMA = "xstar-tools-v0648746191-v4619-runtime-inventory-causal-baseline-v1"
EXPECTED_ROWS = 146286
EXPECTED_UNIQUE_RECORDS = 2420
EXPECTED_COUNT_SET = [2196, 2201, 2420]
EXPECTED_OLD_ERRORS = {
    "escape_rows=146286 expected=149694",
    "records_per_evaluation=[2196, 2201, 2420]",
    "line_map_rows=2420 unique=2420",
}


def validate(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text())
    errors: list[str] = []
    observed_errors = set(report.get("errors", []))
    if report.get("result") != "REJECT":
        errors.append("v4619_result_not_reject")
    if observed_errors != EXPECTED_OLD_ERRORS:
        errors.append(f"unexpected_v4619_errors={sorted(observed_errors)}")
    checks = {
        "evaluations_61": report.get("evaluations") == 61,
        "runtime_rows_146286": report.get("magnesium_type50_escape_rows") == EXPECTED_ROWS,
        "runtime_count_set_2196_2201_2420": sorted(report.get("records_per_evaluation", EXPECTED_COUNT_SET)) == EXPECTED_COUNT_SET
        if "records_per_evaluation" in report else True,
        "line_map_rows_2420": report.get("line_index_map_rows") == EXPECTED_UNIQUE_RECORDS,
        "line_workspace_files_122": report.get("line_workspace_files") == 122,
        "thermal_capture_accept": report.get("thermal_capture_result") == "ACCEPT",
        "qualification_only": report.get("qualification_only") is True,
        "production_blocked": report.get("production_promotion_ready") is False,
    }
    for name, accepted in checks.items():
        if not accepted:
            errors.append(name)
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "baseline_release": "0.6.48.7.46.19",
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "accepted_gates": {name.upper(): "ACCEPT" if value else "REJECT" for name, value in checks.items()},
        "old_errors_exact": observed_errors == EXPECTED_OLD_ERRORS,
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
