"""Validate the accepted v0.6.48.7.46.15 qualification baseline."""
from __future__ import annotations
import argparse, json
from pathlib import Path

RELEASE = "0.6.48.7.46.17.1"
SCHEMA = "xstar-tools-v064874616-v4615-baseline-v1"
REQUIRED_GATES = (
    "ALL_61_THERMAL_EVALUATIONS",
    "THERMAL_COMPONENT_CLOSURE_AUDIT",
    "THERMAL_COMPACT_POPULATION_VALUES_EXACT_40149",
    "ALL_61_THERMAL_DIAGONAL_SOURCE_DOMAIN_APPLIED",
    "THERMAL_DIAGONAL_SOURCE_ORDER_STREAMS_EXACT_183",
    "CORRECTED_MG_TYPE99_ANS5_SOURCE_SCALE",
    "NEGATIVE_SIGNED_DENOMINATORS_CORRECTED_166",
    "ONLY_ANS5_CHANGED_IN_166_ROWS",
    "RECORD_41154_SEQUENCE23_CORRECTED",
    "PYTHON_CALLBACKS_ZERO",
    "V06487_FIXED_STATE_PARITY_PRESERVED",
    "V06488_THERMAL_PARITY",
    "DENSE_EXACT_SYSTEMS_183_PRESERVED",
    "DENSE_MISMATCH_CELLS_ZERO_PRESERVED",
    "PRODUCTION_PROMOTION_BLOCKED",
)

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("checker", type=Path)
    p.add_argument("--output-json", type=Path, required=True)
    a = p.parse_args(argv)
    errors: list[str] = []
    try:
        src = json.loads(a.checker.read_text())
    except Exception as exc:
        src = {}
        errors.append(str(exc))
    gates = src.get("gates", {}) if isinstance(src, dict) else {}
    checked = {name: "ACCEPT" if gates.get(name) == "ACCEPT" else "REJECT" for name in REQUIRED_GATES}
    if src.get("release") != "0.6.48.7.46.15": errors.append("baseline_release")
    if src.get("result") != "ACCEPT": errors.append("baseline_result")
    errors.extend(name for name, value in checked.items() if value != "ACCEPT")
    result = "ACCEPT" if not errors else "REJECT"
    report = {
        "schema": SCHEMA, "release": RELEASE, "baseline_release": src.get("release"),
        "result": result, "gates": checked, "errors": errors,
        "qualification_only": True, "production_promotion_ready": False,
    }
    a.output_json.parent.mkdir(parents=True, exist_ok=True)
    a.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if result == "ACCEPT" else 2

if __name__ == "__main__":
    raise SystemExit(main())
