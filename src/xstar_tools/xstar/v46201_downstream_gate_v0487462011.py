"""Classify the exact v46.20.1 post-Type-99 vocabulary failure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.4"
SCHEMA = "xstar-tools-v06487462011-v46201-downstream-gate-causal-baseline-v1"
EXPECTED_CHECKER_ERRORS = {
    "ALL_61_MAGNESIUM_TYPE99_SOURCE_STATES_CAPTURED",
    "MAGNESIUM_TYPE99_UCALC_ROWS_EXACT_661",
    "MAGNESIUM_TYPE99_UCALC_ANSWERS_EXACT_3966",
    "MAGNESIUM_COOLING_ALL61_EXACT",
    "MAGNESIUM_TYPE50_CLOSURE_PRESERVED",
    "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127",
    "TYPE50_PRESERVATION_AUDIT_ACCEPTED",
}
EXPECTED_TYPE99_ERRORS = {
    "ALL_61_MAGNESIUM_TYPE99_SOURCE_STATES_CAPTURED",
    "MAGNESIUM_TYPE99_UCALC_ROWS_EXACT_661",
    "MAGNESIUM_TYPE99_UCALC_ANSWERS_EXACT_3966",
    "MAGNESIUM_COOLING_ALL61_EXACT",
    "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127",
    "MAGNESIUM_TYPE50_CLOSURE_PRESERVED",
}
EXPECTED_TYPE50_ERRORS = {
    "MAGNESIUM_COOLING_REMAINS_NONEXACT_0_OF_61",
    "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1066",
    "NEXT_CAUSAL_FAMILY_REQUIRES_SEPARATE_ATTRIBUTION",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def validate(output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    checker = _load(output_dir / "v048746201_checker_report.json")
    type99 = _load(output_dir / "v048746201_magnesium_type99_primary_cooling_report.json")
    type50 = _load(output_dir / "v048746201_magnesium_type50_preservation_report.json")
    thermal = _load(output_dir / "v048746201_thermal_state_consumption_report.json")

    gates = {
        "V46201_REPLAY_COMPLETE_61": "ACCEPT" if thermal.get("native_evaluations") == 61 else "REJECT",
        "V46201_CHECKER_REJECTED": "ACCEPT" if checker.get("result") == "REJECT" else "REJECT",
        "V46201_CHECKER_ERROR_SET_EXACT": "ACCEPT" if set(checker.get("errors", [])) == EXPECTED_CHECKER_ERRORS else "REJECT",
        "V46201_TYPE99_ERROR_SET_EXACT": "ACCEPT" if set(type99.get("errors", [])) == EXPECTED_TYPE99_ERRORS else "REJECT",
        "V46201_TYPE50_ERROR_SET_EXACT": "ACCEPT" if set(type50.get("errors", [])) == EXPECTED_TYPE50_ERRORS else "REJECT",
        "V46201_TYPE99_PHYSICAL_ROWS_EXACT_661": "ACCEPT" if type99.get("primary_cooling_rows_exact") == type99.get("primary_cooling_rows") == 661 else "REJECT",
        "V46201_TYPE99_FAMILY_EXACT_61": "ACCEPT" if type99.get("source_family_values_exact") == 61 else "REJECT",
        "V46201_TYPE99_UNEXPLAINED_ZERO": "ACCEPT" if type99.get("unexplained_deltas") == 0 else "REJECT",
        "V46201_MG_COOLING_EXACT_8_OF_61": "ACCEPT" if type99.get("mg_cooling_exact") == 8 and type99.get("mg_cooling_total") == 61 else "REJECT",
        "V46201_NATIVE_EXACT_1080": "ACCEPT" if checker.get("native_computed_values_exact") == 1080 and checker.get("native_computed_values_total") == 2440 else "REJECT",
        "V46201_TYPE50_CORE_EXACT": "ACCEPT" if type50.get("committed_reverse_cj_exact") == type50.get("committed_reverse_cooling_exact") == type50.get("committed_reverse_rows") == 146286 else "REJECT",
    }
    result = "ACCEPT" if all(v == "ACCEPT" for v in gates.values()) else "REJECT"
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "failure_classification": "TYPE99_RUNTIME_DOMAIN_AND_DOWNSTREAM_GATE_VOCABULARY",
        "physics_changed": False,
        "source_recapture_required": False,
        "native_replay_required": False,
        "qualification_only": True,
        "production_promotion_ready": False,
        "gates": gates,
        "errors": [k for k, v in gates.items() if v != "ACCEPT"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v46201-output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = validate(args.v46201_output)
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "failure_classification": "UNCLASSIFIED",
            "physics_changed": False,
            "source_recapture_required": False,
            "native_replay_required": False,
            "qualification_only": True,
            "production_promotion_ready": False,
            "gates": {},
            "errors": [str(exc)],
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
