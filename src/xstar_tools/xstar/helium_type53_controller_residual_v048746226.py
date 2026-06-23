"""Focused v21.16 closure audit for helium Type-53 and controller elcter."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.16"
SCHEMA = "xstar-tools-v0648746226-helium-type53-controller-residual-audit-v1"
AFFECTED_RECORDS = (651, 663, 669, 672, 721, 1689)
ZERO_FLOOR = 1.0e-30


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def canonical_e7(value: float) -> str:
    value = float(value)
    if math.isfinite(value) and abs(value) < ZERO_FLOOR:
        value = 0.0
    return format(value, ".7e")


def audit(source_capture: Path, native_evaluations: Path, audit_output: Path) -> dict[str, Any]:
    canonical = json.loads((audit_output / "v048746217_thermal_controller_report.json").read_text())
    rejections_path = audit_output / "v048746217_thermal_controller_rejections.csv"
    rejections = read_csv(rejections_path) if rejections_path.is_file() else []
    type53_rejections = [
        row for row in rejections
        if row.get("category") == "canonical_answer_channels"
        and int(row.get("record", row.get("identity", "record=0").split("record=")[-1].split(";")[0]) or 0) in AFFECTED_RECORDS
    ]
    sequence4_rejections = [
        row for row in rejections
        if int(row.get("sequence", 0) or 0) == 4
        and row.get("field") in {"elcter", "charge_residual"}
    ]

    diagnostic_rows = 0
    interval_rows = 0
    live_escape_rows = 0
    records_seen: set[int] = set()
    for sequence in range(1, 62):
        path = native_evaluations / f"evaluation_{sequence:04d}" / "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
        if not path.is_file():
            continue
        for row in read_csv(path):
            if row.get("element_z") != "2" or row.get("data_type") != "53":
                continue
            record = int(row.get("record", 0) or 0)
            if record not in AFFECTED_RECORDS:
                continue
            diagnostic_rows += 1
            records_seen.add(record)
            if int(row.get("type53_integration_intervals", 0) or 0) > 0:
                interval_rows += 1
            if int(row.get("type53_helium_live_escape_state_applied", 0) or 0) == 1:
                live_escape_rows += 1

    source_budget = {int(row["sequence"]): row for row in read_csv(source_capture / "v0472_all61_thermal_budget.csv")}
    native_budget = read_csv(native_evaluations / "evaluation_0004" / "native_thermal_budget.csv")[0]
    source_elcter = float(source_budget[4]["charge_residual"])
    native_elcter = float(native_budget["charge_residual"])
    elcter_bit_exact = bits(source_elcter) == bits(native_elcter)
    elcter_e7_equal = canonical_e7(source_elcter) == canonical_e7(native_elcter)

    gates = {
        "CANONICAL_E7_RETAINED": "ACCEPT" if canonical.get("canonical_digits_after_decimal") == 7 else "REJECT",
        "ZERO_FLOOR_1E30_RETAINED": "ACCEPT" if float(canonical.get("canonical_zero_floor", 0.0)) == ZERO_FLOOR else "REJECT",
        "ALL_SIX_HELIUM_TYPE53_RECORDS_OBSERVED": "ACCEPT" if records_seen == set(AFFECTED_RECORDS) else "REJECT",
        "HELIUM_TYPE53_INTERVAL_DIAGNOSTICS_COMPLETE": "ACCEPT" if diagnostic_rows > 0 and interval_rows == diagnostic_rows else "REJECT",
        "HELIUM_TYPE53_LIVE_ESCAPE_STATE_APPLIED": "ACCEPT" if diagnostic_rows > 0 and live_escape_rows == diagnostic_rows else "REJECT",
        "HELIUM_TYPE53_REJECTIONS_ZERO": "ACCEPT" if not type53_rejections else "REJECT",
        "SEQUENCE4_ELECTRON_RESIDUAL_BIT_EXACT": "ACCEPT" if elcter_bit_exact else "REJECT",
        "SEQUENCE4_ELECTRON_RESIDUAL_E7": "ACCEPT" if elcter_e7_equal else "REJECT",
        "SEQUENCE4_CONTROLLER_RESIDUAL_REJECTIONS_ZERO": "ACCEPT" if not sequence4_rejections else "REJECT",
        "ALL_SCIENTIFIC_REJECTIONS_ZERO": "ACCEPT" if int(canonical.get("rejected_differences", -1)) == 0 else "REJECT",
    }
    result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "gates": gates,
        "canonical_digits_after_decimal": 7,
        "canonical_zero_floor": ZERO_FLOOR,
        "affected_records": list(AFFECTED_RECORDS),
        "affected_diagnostic_rows": diagnostic_rows,
        "affected_interval_rows": interval_rows,
        "affected_live_escape_rows": live_escape_rows,
        "helium_type53_rejections": len(type53_rejections),
        "sequence4_residual_rejections": len(sequence4_rejections),
        "source_sequence4_elcter": source_elcter,
        "native_sequence4_elcter": native_elcter,
        "sequence4_elcter_bit_exact": elcter_bit_exact,
        "canonical_rejected_differences": int(canonical.get("rejected_differences", -1)),
        "expected_removed_rows": {"helium_type53_and_downstream": 195, "electron_residual_and_downstream": 3},
        "qualification_only": True,
        "product_level_parity": "NOT_RUN",
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-evaluations", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = audit(args.source_capture.resolve(), args.native_evaluations.resolve(), args.audit_output.resolve())
    except Exception as exc:
        report = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [f"{type(exc).__name__}: {exc}"], "qualification_only": True,
            "product_level_parity": "NOT_RUN", "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
