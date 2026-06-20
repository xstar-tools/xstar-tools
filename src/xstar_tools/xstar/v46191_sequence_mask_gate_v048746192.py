"""Causal gate for the v46.19.1 Mg Type-50 sequence-mask failure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RELEASE = "0.6.48.7.46.20.2"
SCHEMA = "xstar-tools-v0648746192-v46191-sequence-mask-causal-baseline-v1"
EXPECTED_MESSAGE = "fixed evaluation failed: magnesium Type-50 record is missing from source line-index map"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("run_log", type=Path)
    parser.add_argument("--source-capture-report", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    source = json.loads(args.source_capture_report.read_text())
    log_text = args.run_log.read_text(errors="replace")
    checks = {
        "FAILED_SEQUENCE_1": manifest.get("failed_sequence") == 1,
        "FAILED_RETURNCODE_7": manifest.get("failed_returncode") == 7,
        "FIRST_PENDING_SEQUENCE_1": manifest.get("first_pending_sequence") == 1,
        "NO_REUSABLE_EVALUATIONS": manifest.get("sequences_reusable") == 0,
        "ALL_61_PENDING": manifest.get("sequences_pending") == 61 and manifest.get("sequences_total") == 61,
        "MANIFEST_INCOMPLETE": manifest.get("result") == "INCOMPLETE",
        "SOURCE_CAPTURE_ACCEPTED": (
            source.get("result") == "ACCEPT"
            and source.get("magnesium_type50_escape_rows") == 146286
            and source.get("magnesium_type50_unique_runtime_records") == 2420
        ),
        "EXACT_MISSING_LINE_MAP_FAILURE": log_text.count(EXPECTED_MESSAGE) == 1,
        "NO_COMPLETED_FIXED_EVALUATION": "fixed evaluation completed" not in log_text,
    }
    errors = [name for name, accepted in checks.items() if not accepted]
    result = "ACCEPT" if not errors else "REJECT"
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "errors": errors,
        "accepted_gates": {name: "ACCEPT" if accepted else "REJECT" for name, accepted in checks.items()},
        "baseline_release": "0.6.48.7.46.19.1",
        "failure_classification": "MISSING_RUNTIME_ACTIVE_SEQUENCE_MASK" if result == "ACCEPT" else "UNRESOLVED",
        "physics_changed": False,
        "native_replay_required": True,
        "source_recapture_required": False,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if result == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
