"""Audit v46.19.3.1 Mg Type-50 matrix-closure Thermal-channel preservation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .magnesium_type50_endpoint_energy_v048746193 import audit as endpoint_audit

RELEASE = "0.6.48.7.46.21"
SCHEMA = "xstar-tools-v06487461931-magnesium-type50-thermal-channel-preservation-audit-v1"


def audit(source_capture: Path, native_run: Path, component_comparison: Path,
          output: Path) -> dict[str, Any]:
    base = endpoint_audit(source_capture, native_run, component_comparison, output)
    bg = base.get("gates", {})
    required_exact = (
        "ALL_61_MAGNESIUM_TYPE50_ENDPOINT_STATES_CAPTURED",
        "MAGNESIUM_TYPE50_SOURCE_ENDPOINT_MAP_EXACT_2420",
        "MAGNESIUM_TYPE50_SOURCE_ENDPOINT_ROWS_EXACT_146286",
        "MAGNESIUM_TYPE50_SOURCE_ANS3_ENDPOINT_IDENTITY_EXACT_146286",
        "MAGNESIUM_TYPE50_SOURCE_ANS4_ENDPOINT_IDENTITY_EXACT_146286",
        "ALL_61_MAGNESIUM_TYPE50_NATIVE_RECORDS_ATTRIBUTED",
        "MAGNESIUM_TYPE50_ENDPOINT_IDS_EXACT_146286",
        "MAGNESIUM_TYPE50_ENDPOINT_ENERGIES_EXACT_438858",
        "MAGNESIUM_TYPE50_LINE_INDICES_EXACT_146286",
        "MAGNESIUM_TYPE50_LINE_TAU_VALUES_EXACT_292572",
        "MAGNESIUM_TYPE50_ESCAPE_FACTORS_EXACT_292572",
        "MAGNESIUM_TYPE50_ANS1_EXACT_146286",
        "MAGNESIUM_TYPE50_ANS2_EXACT_146286",
        "MAGNESIUM_TYPE50_ANS3_EXACT_146286",
        "MAGNESIUM_TYPE50_ANS4_EXACT_146286",
        "MAGNESIUM_TYPE50_ANS5_EXACT_146286",
        "MAGNESIUM_TYPE50_ANS6_EXACT_146286",
        "MAGNESIUM_TYPE50_ANSWERS_EXACT_877716",
        "MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286",
        "MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286",
        "HYDROGEN_COOLING_ALL61_PRESERVED",
        "MAGNESIUM_TYPE50_UNEXPLAINED_DELTAS_ZERO",
    )
    gates = {
        name: ("ACCEPT" if bg.get(name) == "ACCEPT" else "REJECT")
        for name in required_exact
    }
    gates.update({
        "MAGNESIUM_TYPE50_PRE_CLOSURE_THERMAL_CHANNELS_PRESERVED_292572":
            "ACCEPT" if
            base.get("field_exact_counts", {}).get("ans3") == 146286 and
            base.get("field_exact_counts", {}).get("ans4") == 146286 and
            base.get("committed_reverse_cj_exact") == 146286 and
            base.get("committed_reverse_cooling_exact") == 146286
            else "REJECT",
        "MAGNESIUM_TYPE50_MATRIX_RATE_CHANNELS_SEPARATED_FROM_THERMAL":
            "ACCEPT" if
            base.get("committed_reverse_rows") == 146286 and
            base.get("committed_reverse_cj_exact") == 146286 and
            base.get("committed_reverse_cooling_exact") == 146286
            else "REJECT",
        "MAGNESIUM_COOLING_REMAINS_NONEXACT_0_OF_61":
            "ACCEPT" if base.get("mg_cooling_exact") == 0 and
            base.get("mg_cooling_total") == 61 else "REJECT",
        "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1066":
            "ACCEPT" if base.get("native_computed_values_exact") == 1066 and
            base.get("native_computed_values_total") == 2440 else "REJECT",
        "NEXT_CAUSAL_FAMILY_REQUIRES_SEPARATE_ATTRIBUTION":
            "ACCEPT" if base.get("mg_cooling_exact") == 0 and
            base.get("committed_reverse_cooling_exact") == 146286 else "REJECT",
    })
    result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "gates": gates,
        "errors": [name for name, value in gates.items() if value != "ACCEPT"],
        "source_rows": base.get("source_rows"),
        "native_rows": base.get("native_rows"),
        "field_exact_counts": base.get("field_exact_counts", {}),
        "committed_reverse_rows": base.get("committed_reverse_rows"),
        "committed_reverse_cj_exact": base.get("committed_reverse_cj_exact"),
        "committed_reverse_cooling_exact": base.get("committed_reverse_cooling_exact"),
        "mg_cooling_exact": base.get("mg_cooling_exact"),
        "mg_cooling_total": base.get("mg_cooling_total"),
        "hydrogen_cooling_exact": base.get("hydrogen_cooling_exact"),
        "hydrogen_cooling_total": base.get("hydrogen_cooling_total"),
        "native_computed_values_exact": base.get("native_computed_values_exact"),
        "native_computed_values_total": base.get("native_computed_values_total"),
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--component-comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = audit(
            args.source_capture.resolve(), args.native_run.resolve(),
            args.component_comparison.resolve(), args.output.resolve()
        )
    except Exception as exc:
        report = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "gates": {}, "errors": [str(exc)], "qualification_only": True,
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
