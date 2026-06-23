"""Focused v21.17.1 audit for electron accumulation and controller closure."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.17.1"
SCHEMA = "xstar-tools-v06487462271-source-order-electron-controller-closure-audit-v2"
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


def residual_value(row: dict[str, str]) -> float:
    """Read either historical residual spelling without schema assumptions."""
    for key in ("charge_residual", "elcter"):
        value = row.get(key)
        if value not in (None, ""):
            return float(value)
    raise KeyError("charge_residual/elcter")


def _row_by_sequence(rows: list[dict[str, str]], sequence: int) -> dict[str, str]:
    return next(row for row in rows if int(row.get("sequence", 0) or 0) == sequence)


def _controller_row(rows: list[dict[str, str]], call: int, evaluation: int) -> dict[str, str]:
    return next(
        row for row in rows
        if int(row.get("call_index", 0) or 0) == call
        and int(row.get("evaluation_index", 0) or 0) == evaluation
        and row.get("kind", "dsec") == "dsec"
    )


def audit(
    source_capture: Path,
    native_evaluations: Path,
    native_controller: Path,
    canonical_report: Path,
    canonical_return_code: int,
) -> dict[str, Any]:
    errors: list[str] = []
    dependency = {
        "canonical_return_code": canonical_return_code,
        "canonical_report": str(canonical_report),
        "canonical_report_available": canonical_report.is_file(),
        "native_controller": str(native_controller),
        "native_controller_available": native_controller.is_dir(),
    }
    if canonical_return_code != 0:
        errors.append(f"canonical_dependency_return_code:{canonical_return_code}")
    if not canonical_report.is_file():
        errors.append(f"canonical_report_missing:{canonical_report}")
    trajectory_path = native_controller / "native_dsec_trajectory.csv"
    if not trajectory_path.is_file():
        errors.append(f"native_controller_trajectory_missing:{trajectory_path}")

    if errors:
        gates = {
            "SEQUENCE4_FIXED_ELCTER_BIT_EXACT": "BLOCKED_BY_CANONICAL_DEPENDENCY",
            "CALL1_CHARGE_SECANT_XEE_BIT_EXACT": "BLOCKED_BY_CANONICAL_DEPENDENCY",
            "SEQUENCE4_CONTROLLER_RESIDUAL_BIT_EXACT": "BLOCKED_BY_CANONICAL_DEPENDENCY",
            "CALL3_EVALUATION6_HMCTOT_IEEE_E7": "BLOCKED_BY_CANONICAL_DEPENDENCY",
            "FOCUSED_AUDIT_SCHEMA_COMPATIBLE": "ACCEPT",
            "REJECTED_SCIENTIFIC_DIFFERENCES_ZERO": "BLOCKED_BY_CANONICAL_DEPENDENCY",
        }
        return {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": errors,
            "dependency": dependency,
            "gates": gates,
            "qualification_only": True,
            "product_level_parity": "NOT_IN_SCOPE",
            "production_promotion_ready": False,
        }

    canonical = json.loads(canonical_report.read_text())
    source_inputs = read_csv(source_capture / "v0472_all61_input_states.csv")
    source_budget = read_csv(source_capture / "v0472_all61_thermal_budget.csv")
    native_budget4 = read_csv(
        native_evaluations / "evaluation_0004" / "native_thermal_budget.csv"
    )[0]
    controller_rows = read_csv(trajectory_path)

    source4_input = _row_by_sequence(source_inputs, 4)
    source4_budget = _row_by_sequence(source_budget, 4)
    source28_budget = _row_by_sequence(source_budget, 28)
    controller4 = _controller_row(controller_rows, 1, 4)
    controller28 = _controller_row(controller_rows, 3, 6)

    source4_residual = residual_value(source4_budget)
    native4_residual = residual_value(native_budget4)
    controller4_residual = residual_value(controller4)
    source4_xee = float(source4_input["electron_fraction_input"])
    controller4_xee = float(controller4["electron_fraction_input"])
    source28_hmctot = float(source28_budget["hmctot"])
    controller28_hmctot = float(controller28["hmctot"])

    schema_compatible = True
    try:
        residual_value({"elcter": "1.0"})
        residual_value({"charge_residual": "1.0"})
    except Exception:
        schema_compatible = False

    gates = {
        "SEQUENCE4_FIXED_ELCTER_BIT_EXACT": (
            "ACCEPT" if bits(source4_residual) == bits(native4_residual) else "REJECT"
        ),
        "CALL1_CHARGE_SECANT_XEE_BIT_EXACT": (
            "ACCEPT" if bits(source4_xee) == bits(controller4_xee) else "REJECT"
        ),
        "SEQUENCE4_CONTROLLER_RESIDUAL_BIT_EXACT": (
            "ACCEPT" if bits(source4_residual) == bits(controller4_residual) else "REJECT"
        ),
        "CALL3_EVALUATION6_HMCTOT_IEEE_E7": (
            "ACCEPT" if canonical_e7(source28_hmctot) == canonical_e7(controller28_hmctot) else "REJECT"
        ),
        "FOCUSED_AUDIT_SCHEMA_COMPATIBLE": "ACCEPT" if schema_compatible else "REJECT",
        "REJECTED_SCIENTIFIC_DIFFERENCES_ZERO": (
            "ACCEPT"
            if canonical.get("scientific_result") == "ACCEPT"
            and int(canonical.get("rejected_differences", -1)) == 0
            else "REJECT"
        ),
    }
    result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "errors": [],
        "dependency": dependency,
        "gates": gates,
        "canonical_digits_after_decimal": 7,
        "canonical_zero_floor": ZERO_FLOOR,
        "source_sequence4_elcter": source4_residual,
        "native_sequence4_elcter": native4_residual,
        "controller_sequence4_residual": controller4_residual,
        "source_call1_charge_secant_xee": source4_xee,
        "native_call1_charge_secant_xee": controller4_xee,
        "source_call3_evaluation6_hmctot": source28_hmctot,
        "native_call3_evaluation6_hmctot": controller28_hmctot,
        "canonical_rejected_differences": int(canonical.get("rejected_differences", -1)),
        "qualification_only": True,
        "product_level_parity": "NOT_IN_SCOPE",
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-evaluations", type=Path, required=True)
    parser.add_argument("--native-controller", type=Path, required=True)
    parser.add_argument("--canonical-report", type=Path, required=True)
    parser.add_argument("--canonical-return-code", type=int, default=0)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = audit(
            args.source_capture.resolve(),
            args.native_evaluations.resolve(),
            args.native_controller.resolve(),
            args.canonical_report.resolve(),
            args.canonical_return_code,
        )
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [f"focused_audit_internal_error:{type(exc).__name__}:{exc}"],
            "gates": {
                "FOCUSED_AUDIT_SCHEMA_COMPATIBLE": "REJECT",
            },
            "qualification_only": True,
            "product_level_parity": "NOT_IN_SCOPE",
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
