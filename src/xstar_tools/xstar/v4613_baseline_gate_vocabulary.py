"""Validate accepted v46.13 checker reports across equivalent fixed-state gate vocabularies."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21"
BASELINE_RELEASE = "0.6.48.7.46.13"
SCHEMA = "xstar-tools-v0648746141-v4613-baseline-gate-vocabulary-v1"

CORE_GATES = (
    "ALL_61_THERMAL_EVALUATIONS",
    "ALL_61_THERMAL_POPULATION_STATE_EXACT",
    "THERMAL_COMPACT_POPULATION_VALUES_EXACT_40149",
    "ALL_61_THERMAL_COMPACT_POPULATION_FINGERPRINTS_EXACT",
    "THERMAL_COMPONENT_CLOSURE_AUDIT",
    "PYTHON_CALLBACKS_ZERO",
    "V06488_THERMAL_PARITY",
)

FIXED_STATE_ALIAS = "V06487_FIXED_STATE_PARITY_PRESERVED"
FIXED_STATE_CONCRETE_GATES = (
    "BASELINE_V461212_QUALIFICATION_PRESERVED",
    "FULL_LEVEL_FIXED_STATE_PRODUCT_UNCHANGED_41968",
    "ION_STAGE_PRODUCT_UNCHANGED_1098",
    "DENSE_EXACT_SYSTEMS_183_PRESERVED",
    "DENSE_MISMATCH_CELLS_ZERO_PRESERVED",
)


def validate_report(report: dict[str, Any]) -> dict[str, Any]:
    gates = report.get("gates")
    if not isinstance(gates, dict):
        gates = {}

    errors: list[str] = []
    if report.get("release") != BASELINE_RELEASE:
        errors.append("baseline_release")

    missing_core = [name for name in CORE_GATES if gates.get(name) != "ACCEPT"]
    errors.extend(missing_core)

    alias_accept = gates.get(FIXED_STATE_ALIAS) == "ACCEPT"
    concrete_missing = [
        name for name in FIXED_STATE_CONCRETE_GATES if gates.get(name) != "ACCEPT"
    ]
    concrete_accept = not concrete_missing

    if alias_accept:
        fixed_state_mode = "aggregate_alias"
    elif concrete_accept:
        fixed_state_mode = "concrete_v4613_gates"
    else:
        fixed_state_mode = "missing"
        errors.append(FIXED_STATE_ALIAS)
        errors.extend(f"fixed_state:{name}" for name in concrete_missing)

    result = "ACCEPT" if not errors else "REJECT"
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "baseline_release": BASELINE_RELEASE,
        "result": result,
        "fixed_state_gate_mode": fixed_state_mode,
        "aggregate_alias_accept": alias_accept,
        "concrete_gate_accept": concrete_accept,
        "core_gates": {name: gates.get(name) for name in CORE_GATES},
        "fixed_state_concrete_gates": {
            name: gates.get(name) for name in FIXED_STATE_CONCRETE_GATES
        },
        "qualification_only": True,
        "production_promotion_ready": False,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checker_report", type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()

    report = json.loads(args.checker_report.read_text())
    result = validate_report(report)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text)
    print(text, end="")
    print(
        "V04874614_BASELINE_FIXED_STATE_GATE_MODE="
        + result["fixed_state_gate_mode"]
    )
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
