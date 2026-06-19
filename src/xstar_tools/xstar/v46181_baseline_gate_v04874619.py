"""Validate the accepted v46.18.1 post-Hydrogen baseline for v46.19."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RELEASE = "0.6.48.7.46.19.2"
SCHEMA = "xstar-tools-v064874619-v46181-baseline-v1"
REQUIRED = (
    "ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610_PRESERVED",
    "HYDROGEN_TYPE50_ANSWERS_EXACT_8113",
    "HYDROGEN_COOLING_ALL61_EXACT",
    "V06487_FIXED_STATE_PARITY_PRESERVED",
    "DENSE_EXACT_SYSTEMS_183_PRESERVED",
    "DENSE_MISMATCH_CELLS_ZERO_PRESERVED",
    "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1066",
    "PRODUCTION_PROMOTION_BLOCKED",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checker", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    errors: list[str] = []
    try:
        source = json.loads(args.checker.read_text())
    except Exception as exc:
        source = {}
        errors.append(f"checker_read:{exc}")
    gates = source.get("gates", {})
    if source.get("result") != "ACCEPT" or source.get("scientific_result") != "ACCEPT":
        errors.append("baseline_result")
    accepted = {name: ("ACCEPT" if gates.get(name) == "ACCEPT" else "REJECT") for name in REQUIRED}
    errors.extend(name for name, value in accepted.items() if value != "ACCEPT")
    if source.get("native_computed_values_exact") != 1066 or source.get("native_computed_values_total") != 2440:
        errors.append("baseline_exact_1066")
    report = {
        "schema": SCHEMA, "release": RELEASE,
        "baseline_release": "0.6.48.7.46.18.1",
        "result": "ACCEPT" if not errors else "REJECT", "errors": errors,
        "accepted_gates": accepted,
        "native_computed_values_exact": source.get("native_computed_values_exact"),
        "native_computed_values_total": source.get("native_computed_values_total"),
        "qualification_only": True, "production_promotion_ready": False,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
