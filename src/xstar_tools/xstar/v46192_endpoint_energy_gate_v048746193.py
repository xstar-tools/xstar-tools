"""Classify the accepted v46.19.2 Mg Type-50 endpoint-energy failure."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.19.3"
SCHEMA = "xstar-tools-v0648746193-v46192-endpoint-energy-causal-baseline-v1"
EXPECTED_REJECTED_GATES = {
    "MAGNESIUM_TYPE50_ANSWERS_EXACT_146286",
    "MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286",
    "MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286",
    "MAGNESIUM_COOLING_ALL61_EXACT",
    "MAGNESIUM_TYPE50_UNEXPLAINED_DELTAS_ZERO",
    "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def classify(bundle: Path) -> dict[str, Any]:
    checker_path = bundle / "v048746192_checker_report.json"
    audit_path = bundle / "v04874619_magnesium_type50_cooling_report.json"
    resume_path = bundle / "v04874619_native_replay_resume_manifest.json"
    comparison_path = bundle / "v04874619_magnesium_type50_escape_comparison.csv"
    missing = [str(path) for path in (checker_path, audit_path, resume_path, comparison_path) if not path.is_file()]
    if missing:
        return {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [f"missing:{path}" for path in missing],
            "qualification_only": True, "production_promotion_ready": False,
        }
    checker = _load(checker_path)
    audit = _load(audit_path)
    resume = _load(resume_path)
    rows = _rows(comparison_path)
    field_exact = {
        i: sum(float(row[f"ans{i}"]).hex() == float(row[f"native_ans{i}"]).hex() for row in rows)
        for i in range(1, 7)
    }
    ans3_mismatch_records = {
        int(row["record"]) for row in rows
        if float(row["ans3"]).hex() != float(row["native_ans3"]).hex()
    }
    rejected = {name for name, value in checker.get("gates", {}).items() if value != "ACCEPT"}
    gates = {
        "V46192_SCIENTIFIC_REJECT": "ACCEPT" if checker.get("result") == "REJECT" and checker.get("scientific_result") == "REJECT" else "REJECT",
        "V46192_ALL61_REPLAY_COMPLETE": "ACCEPT" if checker.get("thermal_evaluations") == 61 and resume.get("result") == "ACCEPT" and resume.get("sequences_reusable") == 61 else "REJECT",
        "V46192_REJECTED_GATE_SET_EXACT": "ACCEPT" if rejected == EXPECTED_REJECTED_GATES else "REJECT",
        "V46192_SOURCE_DOMAIN_EXACT_146286": "ACCEPT" if audit.get("source_rows") == 146286 and audit.get("native_rows") == 146286 else "REJECT",
        "V46192_LINE_TAU_ESCAPE_EXACT": "ACCEPT" if audit.get("line_indices_exact") == 146286 and audit.get("tau_values_exact") == 292572 and audit.get("escape_factors_exact") == 292572 else "REJECT",
        "V46192_ONLY_ANS3_MISMATCHES": "ACCEPT" if field_exact == {1: 146286, 2: 146286, 3: 95331, 4: 146286, 5: 146286, 6: 146286} else "REJECT",
        "V46192_ANS3_MISMATCH_ROWS_50955": "ACCEPT" if len(rows) - field_exact[3] == 50955 else "REJECT",
        "V46192_ANS3_MISMATCH_RECORDS_857": "ACCEPT" if len(ans3_mismatch_records) == 857 else "REJECT",
        "V46192_COMMITTED_CJ_EXACT_88637": "ACCEPT" if audit.get("committed_reverse_cj_exact") == 88637 else "REJECT",
        "V46192_COMMITTED_COOLING_EXACT_100781": "ACCEPT" if audit.get("committed_reverse_cooling_exact") == 100781 else "REJECT",
        "V46192_NATIVE_EXACT_1066": "ACCEPT" if audit.get("native_computed_values_exact") == 1066 and audit.get("native_computed_values_total") == 2440 else "REJECT",
        "V46192_MG_COOLING_EXACT_0_OF_61": "ACCEPT" if audit.get("mg_cooling_exact") == 0 and audit.get("mg_cooling_total") == 61 else "REJECT",
    }
    result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    return {
        "schema": SCHEMA, "release": RELEASE, "result": result,
        "failure_classification": "MAGNESIUM_TYPE50_SOURCE_ENDPOINT_ENERGY_AND_MATRIX_CLOSURE_RECONSTRUCTION",
        "gates": gates,
        "field_exact_counts": {f"ans{i}": field_exact[i] for i in range(1, 7)},
        "ans3_mismatch_rows": len(rows) - field_exact[3],
        "ans3_mismatch_records": len(ans3_mismatch_records),
        "source_recapture_required": True,
        "native_replay_required": True,
        "physics_changed": False,
        "errors": [] if result == "ACCEPT" else [name for name, value in gates.items() if value != "ACCEPT"],
        "qualification_only": True, "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = classify(args.bundle.resolve())
    except Exception as exc:
        result = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [str(exc)], "qualification_only": True,
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
