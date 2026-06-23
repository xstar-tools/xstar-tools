"""Focused v21.17 audit for source-order charge accumulation and controller closure."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.46.21.17"
SCHEMA = "xstar-tools-v0648746227-source-order-electron-controller-closure-audit-v1"
ZERO_FLOOR = 1.0e-30


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def canonical_e7(value: Any) -> str:
    numeric = float(value)
    if math.isfinite(numeric) and abs(numeric) < ZERO_FLOOR:
        numeric = 0.0
    return format(numeric, ".7e")


def residual_value(row: dict[str, Any]) -> float:
    """Read either source ``elcter`` or normalized ``charge_residual`` schema."""
    for key in ("charge_residual", "elcter"):
        value = row.get(key)
        if value not in (None, ""):
            return float(value)
    raise KeyError("charge_residual/elcter")


def first_row(rows: Iterable[dict[str, str]], **identity: Any) -> dict[str, str]:
    for row in rows:
        if all(str(row.get(key, "")) == str(value) for key, value in identity.items()):
            return row
    labels = ", ".join(f"{key}={value}" for key, value in identity.items())
    raise LookupError(f"row not found: {labels}")


def audit(
    source_capture: Path,
    native_evaluations: Path,
    native_controller: Path,
    audit_output: Path,
) -> dict[str, Any]:
    canonical = json.loads((audit_output / "v048746217_thermal_controller_report.json").read_text())

    source_budget_rows = read_csv(source_capture / "v0472_all61_thermal_budget.csv")
    source_trace_rows = read_csv(source_capture / "v0472_dsec_thermal_trace.csv")
    native_fixed_rows = read_csv(
        native_evaluations / "evaluation_0004" / "native_thermal_budget.csv"
    )
    native_trajectory_rows = read_csv(native_controller / "native_dsec_trajectory.csv")
    native_event_rows = read_csv(native_controller / "native_dsec_controller_events.csv")

    source_fixed4 = first_row(source_budget_rows, sequence=4)
    native_fixed4 = native_fixed_rows[0]
    source_call1_eval4 = first_row(
        source_trace_rows, dsec_call_id=1, dsec_local_evaluation_index=4
    )
    native_call1_eval4 = first_row(
        native_trajectory_rows, kind="dsec", call_index=1, evaluation_index=4
    )
    native_call1_eval4_event = first_row(
        native_event_rows,
        call_index=1,
        evaluation_index=4,
        event_name="after_evaluation",
    )

    source_call3_eval6 = first_row(
        source_trace_rows, dsec_call_id=3, dsec_local_evaluation_index=6
    )
    native_call3_eval6 = first_row(
        native_trajectory_rows, kind="dsec", call_index=3, evaluation_index=6
    )
    native_call3_eval6_event = first_row(
        native_event_rows,
        call_index=3,
        evaluation_index=6,
        event_name="after_evaluation",
    )

    source_fixed_elcter = residual_value(source_fixed4)
    native_fixed_elcter = residual_value(native_fixed4)
    source_controller_elcter = residual_value(source_call1_eval4)
    native_controller_elcter = residual_value(native_call1_eval4)
    native_controller_event_elcter = residual_value(native_call1_eval4_event)

    source_secant_xee = float(source_call1_eval4["electron_fraction_xee"])
    native_secant_xee = float(native_call1_eval4["electron_fraction_input"])

    source_hmctot = float(source_call3_eval6["hmctot"])
    native_hmctot = float(native_call3_eval6["hmctot"])
    native_event_hmctot = float(native_call3_eval6_event["hmctot"])

    schema_aliases_ok = (
        residual_value({"elcter": "1.25"}) == 1.25
        and residual_value({"charge_residual": "1.25"}) == 1.25
    )
    rejected_zero = (
        int(canonical.get("rejected_differences", -1)) == 0
        and canonical.get("gates", {}).get("REJECTED_SCIENTIFIC_DIFFERENCES_ZERO") == "ACCEPT"
    )

    gates = {
        "CANONICAL_E7_RETAINED": (
            "ACCEPT" if canonical.get("canonical_digits_after_decimal") == 7 else "REJECT"
        ),
        "ZERO_FLOOR_1E30_RETAINED": (
            "ACCEPT"
            if float(canonical.get("canonical_zero_floor", 0.0)) == ZERO_FLOOR
            else "REJECT"
        ),
        "SEQUENCE4_FIXED_ELCTER_BIT_EXACT": (
            "ACCEPT" if bits(source_fixed_elcter) == bits(native_fixed_elcter) else "REJECT"
        ),
        "CALL1_CHARGE_SECANT_XEE_BIT_EXACT": (
            "ACCEPT" if bits(source_secant_xee) == bits(native_secant_xee) else "REJECT"
        ),
        "SEQUENCE4_CONTROLLER_RESIDUAL_BIT_EXACT": (
            "ACCEPT"
            if bits(source_controller_elcter) == bits(native_controller_elcter)
            and bits(source_controller_elcter) == bits(native_controller_event_elcter)
            else "REJECT"
        ),
        "CALL3_EVALUATION6_HMCTOT_IEEE_E7": (
            "ACCEPT"
            if canonical_e7(source_hmctot) == canonical_e7(native_hmctot)
            and canonical_e7(source_hmctot) == canonical_e7(native_event_hmctot)
            else "REJECT"
        ),
        "FOCUSED_AUDIT_SCHEMA_COMPATIBLE": "ACCEPT" if schema_aliases_ok else "REJECT",
        "REJECTED_SCIENTIFIC_DIFFERENCES_ZERO": "ACCEPT" if rejected_zero else "REJECT",
    }
    required = (
        "SEQUENCE4_FIXED_ELCTER_BIT_EXACT",
        "CALL1_CHARGE_SECANT_XEE_BIT_EXACT",
        "SEQUENCE4_CONTROLLER_RESIDUAL_BIT_EXACT",
        "CALL3_EVALUATION6_HMCTOT_IEEE_E7",
        "FOCUSED_AUDIT_SCHEMA_COMPATIBLE",
        "REJECTED_SCIENTIFIC_DIFFERENCES_ZERO",
    )
    result = "ACCEPT" if all(gates[name] == "ACCEPT" for name in required) else "REJECT"
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "gates": gates,
        "canonical_digits_after_decimal": 7,
        "canonical_zero_floor": ZERO_FLOOR,
        "sequence4": {
            "source_fixed_elcter": source_fixed_elcter,
            "native_fixed_elcter": native_fixed_elcter,
            "source_controller_elcter": source_controller_elcter,
            "native_controller_elcter": native_controller_elcter,
            "native_controller_event_elcter": native_controller_event_elcter,
            "source_charge_secant_xee": source_secant_xee,
            "native_charge_secant_xee": native_secant_xee,
        },
        "call3_evaluation6": {
            "source_hmctot": source_hmctot,
            "native_hmctot": native_hmctot,
            "native_event_hmctot": native_event_hmctot,
            "source_e7": canonical_e7(source_hmctot),
            "native_e7": canonical_e7(native_hmctot),
            "native_event_e7": canonical_e7(native_event_hmctot),
        },
        "canonical_rejected_differences": int(canonical.get("rejected_differences", -1)),
        "qualification_only": True,
        "product_level_parity": "NOT_RUN",
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-evaluations", type=Path, required=True)
    parser.add_argument("--native-controller", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = audit(
            args.source_capture.resolve(),
            args.native_evaluations.resolve(),
            args.native_controller.resolve(),
            args.audit_output.resolve(),
        )
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "qualification_only": True,
            "product_level_parity": "NOT_RUN",
            "production_promotion_ready": False,
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
