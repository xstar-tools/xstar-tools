"""Validate the causal v46.17 production-host boundary for v46.17.1."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RELEASE = "0.6.48.7.46.20"
SCHEMA = "xstar-tools-v0648746171-v4617-causal-baseline-v1"
ACCEPTED_GATES = (
    "ALL_61_CONTINUUM_WORKSPACES_RECONSTRUCTED",
    "ALL_61_THERMAL_EVALUATIONS",
    "COMMITTED_THERMAL_VALUES_EXACT_2440",
    "CONTINUUM_BREMSAM_VALUES_EXACT_60939",
    "CONTINUUM_BREMSMAP_INDICES_EXACT_60939",
    "CONTINUUM_EPIM_CANONICAL_VALUES_EXACT_999",
    "CONTINUUM_EPIM_VALUES_EXACT_60939",
    "CONTINUUM_WORKSPACE_SOURCE_FAITHFUL_61",
    "DENSE_EXACT_SYSTEMS_183_PRESERVED",
    "DENSE_MISMATCH_CELLS_ZERO_PRESERVED",
    "PRODUCTION_PROMOTION_BLOCKED",
    "PYTHON_CALLBACKS_ZERO",
    "RESUMABLE_NATIVE_REPLAY_COMPLETE_61",
    "THERMAL_COMPACT_POPULATIONS_EXACT_40149",
    "THERMAL_DIAGONAL_STREAMS_EXACT_183",
    "V04616_BASELINE_PRESERVED",
    "V06487_FIXED_STATE_PARITY_PRESERVED",
)
EXPECTED_REJECTED_GATES = (
    "COMPTON_COMPONENTS_SOURCE_SCALE_61",
    "FREE_FREE_COMPONENTS_SOURCE_SCALE_61",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("checker", type=Path)
    parser.add_argument("--output-json", type=Path, required=True)
    arguments = parser.parse_args(argv)
    errors: list[str] = []
    try:
        source = json.loads(arguments.checker.read_text())
    except Exception as error:
        source = {}
        errors.append(str(error))
    gates = source.get("gates", {})
    checked = {
        name: "ACCEPT" if gates.get(name) == "ACCEPT" else "REJECT"
        for name in ACCEPTED_GATES
    }
    rejected = {
        name: "ACCEPT" if gates.get(name) == "REJECT" else "REJECT"
        for name in EXPECTED_REJECTED_GATES
    }
    if source.get("release") != "0.6.48.7.46.17":
        errors.append("baseline_release")
    if source.get("result") != "REJECT" or source.get("scientific_result") != "REJECT":
        errors.append("baseline_expected_reject_boundary")
    if source.get("native_computed_values_exact") != 419:
        errors.append("baseline_native_exact_count")
    if sorted(source.get("errors", [])) != sorted(EXPECTED_REJECTED_GATES):
        errors.append("baseline_reject_set")
    errors.extend(name for name, value in checked.items() if value != "ACCEPT")
    errors.extend(name for name, value in rejected.items() if value != "ACCEPT")
    result = "ACCEPT" if not errors else "REJECT"
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "baseline_release": source.get("release"),
        "result": result,
        "accepted_gates": checked,
        "expected_rejected_gates": rejected,
        "errors": errors,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    arguments.output_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if result == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
