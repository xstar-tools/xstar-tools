"""Classify the v46.19.3 Mg Type-50 matrix-closure Thermal-channel failure."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21"
SCHEMA = "xstar-tools-v06487461931-v46193-thermal-channel-causal-baseline-v1"
CLASSIFICATION = "MAGNESIUM_TYPE50_MATRIX_CLOSURE_THERMAL_CHANNEL_RECOMPUTATION"


def _load(path: Path) -> Any:
    return json.loads(path.read_text())


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def classify(base: Path) -> dict[str, Any]:
    errors: list[str] = []
    report_path = base / "v048746193_magnesium_type50_endpoint_energy_report.json"
    checker_path = base / "v048746193_checker_report.json"
    thermal_path = base / "v048746193_thermal_state_consumption_report.json"
    comparison_path = base / "v048746193_magnesium_type50_matrix_closure_comparison.csv"
    resume_path = base / "v048746193_native_replay_resume_manifest.json"
    for path in (report_path, checker_path, thermal_path, comparison_path, resume_path):
        if not path.is_file():
            errors.append(f"missing:{path.name}")
    if errors:
        return {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "failure_classification": "UNCLASSIFIED", "errors": errors,
            "qualification_only": True, "production_promotion_ready": False,
        }

    report = _load(report_path)
    checker = _load(checker_path)
    thermal = _load(thermal_path)
    resume = _load(resume_path)
    rows = _rows(comparison_path)
    cj_mismatch = [row for row in rows if row.get("cj_exact") != "1"]
    cooling_mismatch = [
        row for row in rows if row.get("cooling_contribution_exact") != "1"
    ]
    field_counts = report.get("field_exact_counts", {})
    gates = {
        "V46193_ALL61_REPLAY_COMPLETE": "ACCEPT" if
            resume.get("result") == "ACCEPT" and resume.get("sequences_reusable") == 61
            else "REJECT",
        "V46193_SCIENTIFIC_REJECT": "ACCEPT" if
            checker.get("result") == "REJECT" and checker.get("scientific_result") == "REJECT"
            else "REJECT",
        "V46193_INITIAL_ANSWERS_EXACT_877716": "ACCEPT" if
            all(field_counts.get(f"ans{i}") == 146286 for i in range(1, 7))
            else "REJECT",
        "V46193_ENDPOINT_AND_ESCAPE_EXACT": "ACCEPT" if
            all(field_counts.get(name) == expected for name, expected in {
                "endpoint": 146286, "endpoint1": 146286, "endpoint2": 146286,
                "endpoint_ids": 146286, "line": 146286,
                "tau_in": 146286, "tau_out": 146286,
                "ptmp1": 146286, "ptmp2": 146286,
            }.items()) else "REJECT",
        "V46193_COMMITTED_CJ_EXACT_138242": "ACCEPT" if
            report.get("committed_reverse_rows") == 146286 and
            report.get("committed_reverse_cj_exact") == 138242 else "REJECT",
        "V46193_COMMITTED_COOLING_EXACT_138249": "ACCEPT" if
            report.get("committed_reverse_rows") == 146286 and
            report.get("committed_reverse_cooling_exact") == 138249 else "REJECT",
        "V46193_CJ_MISMATCH_ROWS_8044": "ACCEPT" if
            len(cj_mismatch) == 8044 else "REJECT",
        "V46193_COOLING_MISMATCH_ROWS_8037": "ACCEPT" if
            len(cooling_mismatch) == 8037 else "REJECT",
        "V46193_MISMATCH_RECORDS_222": "ACCEPT" if
            len({int(row["record"]) for row in cj_mismatch}) == 222 and
            len({int(row["record"]) for row in cooling_mismatch}) == 222
            else "REJECT",
        "V46193_MISMATCH_SEQUENCES_37": "ACCEPT" if
            len({int(row["sequence"]) for row in cj_mismatch}) == 37 and
            len({int(row["sequence"]) for row in cooling_mismatch}) == 37
            else "REJECT",
        "V46193_MISMATCH_CALLS_3_4": "ACCEPT" if
            {int(row["call_index"]) for row in cj_mismatch} == {3, 4} and
            {int(row["call_index"]) for row in cooling_mismatch} == {3, 4}
            else "REJECT",
        "V46193_MG_COOLING_EXACT_0_OF_61": "ACCEPT" if
            report.get("mg_cooling_exact") == 0 and report.get("mg_cooling_total") == 61
            else "REJECT",
        "V46193_NATIVE_EXACT_1066": "ACCEPT" if
            thermal.get("native_computed_values_exact") == 1066 and
            thermal.get("native_computed_values_total") == 2440 else "REJECT",
        "V46193_REJECTED_GATE_SET_EXACT": "ACCEPT" if
            set(checker.get("errors", [])) == {
                "MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286",
                "MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286",
                "MAGNESIUM_COOLING_ALL61_EXACT",
                "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127",
                "MAGNESIUM_TYPE50_UNEXPLAINED_DELTAS_ZERO",
            } else "REJECT",
    }
    result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "failure_classification": CLASSIFICATION if result == "ACCEPT" else "UNCLASSIFIED",
        "gates": gates,
        "errors": [name for name, value in gates.items() if value != "ACCEPT"],
        "committed_reverse_rows": report.get("committed_reverse_rows"),
        "committed_reverse_cj_exact": report.get("committed_reverse_cj_exact"),
        "committed_reverse_cooling_exact": report.get("committed_reverse_cooling_exact"),
        "cj_mismatch_rows": len(cj_mismatch),
        "cooling_mismatch_rows": len(cooling_mismatch),
        "mismatch_records": len({int(row["record"]) for row in cj_mismatch}),
        "mismatch_sequences": len({int(row["sequence"]) for row in cj_mismatch}),
        "affected_calls": sorted({int(row["call_index"]) for row in cj_mismatch}),
        "native_replay_required": True,
        "source_recapture_required": False,
        "physics_changed": False,
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = classify(args.base.resolve())
    except Exception as exc:
        report = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "failure_classification": "UNCLASSIFIED", "errors": [str(exc)],
            "qualification_only": True, "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
