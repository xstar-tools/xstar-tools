"""Validate the accepted v46.19.3.1 Type-50 closure baseline for v46.20."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.20"
SCHEMA = "xstar-tools-v064874620-v461931-baseline-v1"

REQUIRED_GATES = (
    "ALL_61_THERMAL_EVALUATIONS",
    "MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286",
    "MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286",
    "MAGNESIUM_TYPE50_PRE_CLOSURE_THERMAL_CHANNELS_PRESERVED_292572",
    "MAGNESIUM_TYPE50_MATRIX_RATE_CHANNELS_SEPARATED_FROM_THERMAL",
    "MAGNESIUM_COOLING_REMAINS_NONEXACT_0_OF_61",
    "HYDROGEN_COOLING_ALL61_PRESERVED",
    "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1066",
    "PYTHON_CALLBACKS_ZERO",
    "V06487_FIXED_STATE_PARITY_PRESERVED",
    "DENSE_EXACT_SYSTEMS_183_PRESERVED",
    "DENSE_MISMATCH_CELLS_ZERO_PRESERVED",
    "ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610_PRESERVED",
    "THERMAL_COMPACT_POPULATIONS_EXACT_40149",
    "THERMAL_DIAGONAL_STREAMS_EXACT_183",
    "RESUMABLE_NATIVE_REPLAY_COMPLETE_61",
    "PRODUCTION_PROMOTION_BLOCKED",
)

def validate(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        report = json.loads(path.read_text())
    except Exception as exc:
        report = {}
        errors.append(f"cannot_read_baseline:{exc}")
    gates = report.get("gates", {}) if isinstance(report, dict) else {}
    if report.get("release") != "0.6.48.7.46.19.3.1":
        errors.append(f"baseline_release={report.get('release')}")
    if report.get("result") != "ACCEPT" or report.get("scientific_result") != "ACCEPT":
        errors.append("baseline_not_accepted")
    for name in REQUIRED_GATES:
        if gates.get(name) != "ACCEPT":
            errors.append(f"missing_gate:{name}")
    if report.get("native_computed_values_exact") != 1066 or report.get("native_computed_values_total") != 2440:
        errors.append("native_exactness_not_1066_of_2440")
    if report.get("production_promotion_ready") is not False:
        errors.append("production_not_blocked")
    accepted = {name: gates.get(name, "REJECT") for name in REQUIRED_GATES}
    return {
        "schema": SCHEMA, "release": RELEASE,
        "baseline_release": report.get("release"),
        "result": "ACCEPT" if not errors else "REJECT", "errors": errors,
        "accepted_gates": accepted,
        "native_computed_values_exact": report.get("native_computed_values_exact", -1),
        "native_computed_values_total": report.get("native_computed_values_total", -1),
        "qualification_only": True, "production_promotion_ready": False,
    }

def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("checker_report", type=Path); parser.add_argument("--output-json", type=Path, required=True)
    args=parser.parse_args(argv); result=validate(args.checker_report.resolve())
    args.output_json.parent.mkdir(parents=True, exist_ok=True); args.output_json.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["result"]=="ACCEPT" else 2
if __name__ == "__main__": raise SystemExit(main())
