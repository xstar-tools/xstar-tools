"""Compare all 61 source and native Thermal state-consumption ledgers.

The audit separates two claims:

* committed component parity: the qualification source-captured boundary is
  exact and consumed the intended fixed state;
* independently computed parity: the native ``computed_*`` values match the
  source without the component closure.

Only the first claim is required by the v46.12 qualification milestone.  The
second is reported explicitly and remains fail-closed for production.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path
from typing import Any

from .all61_native_replay_aggregate import THERMAL_LEDGER_NAME
from .v0472_all61_thermal_state_capture import BUDGET_NAME

RELEASE = "0.6.48.7.46.14.1"
SCHEMA = "xstar-tools-v064874612-all61-thermal-state-consumption-audit-v1"
SUMMARY_NAME = "v04874612_all61_thermal_state_consumption_summary.json"
COMPONENT_DIFF_NAME = "v04874612_all61_thermal_component_comparison.csv"
STATE_DIFF_NAME = "v04874612_all61_thermal_state_consumption_comparison.csv"

GROUP_FIELDS = {
    "H_HE_MG": [
        "h_heating", "h_cooling", "h_heating2", "h_cooling2",
        "he_heating", "he_cooling", "he_heating2", "he_cooling2",
        "he_type53_heating", "he_type53_cooling", "he_type53_heating2", "he_type53_cooling2",
        "he_non_type53_heating", "he_non_type53_cooling", "he_non_type53_heating2", "he_non_type53_cooling2",
        "mg_heating", "mg_cooling", "mg_heating2", "mg_cooling2",
        "element_heating", "element_cooling", "element_heating2", "element_cooling2",
    ],
    "CONTINUUM": [
        "continuum_heating", "continuum_cooling", "continuum_heating2", "continuum_cooling2",
        "cmp1", "cmp2", "htcomp", "clcomp", "htfreef", "clbrems",
    ],
    "TOTALS": ["httot", "cltot", "httot2", "cltot2"],
    "RESIDUAL": ["hmctot"],
    "ELCTER_RESIDUAL": ["elcter"],
}
COMPONENT_FIELDS = [field for fields in GROUP_FIELDS.values() for field in fields]

COMMITTED_NATIVE_FIELD = {
    **{field: field for field in COMPONENT_FIELDS},
    "httot": "total_heating",
    "cltot": "total_cooling",
    "httot2": "total_heating2",
    "cltot2": "total_cooling2",
    "elcter": "charge_residual",
}
COMPUTED_NATIVE_FIELD = {
    **{field: f"computed_{field}" for field in COMPONENT_FIELDS},
    "httot": "computed_total_heating",
    "cltot": "computed_total_cooling",
    "httot2": "computed_total_heating2",
    "cltot2": "computed_total_cooling2",
    "elcter": "computed_charge_residual",
}
# The maps above produce the correct computed names for every component except
# source totals, whose native ledger uses explicit total_* labels.

STATE_FIELDS = [
    ("temperature_k", "temperature_k", "float"),
    ("electron_fraction_input", "electron_fraction_input", "float"),
    ("electron_density_cm3", "electron_density_cm3", "float"),
    ("hydrogen_density_cm3", "hydrogen_density_cm3", "float"),
    ("covering_fraction", "covering_fraction", "float"),
    ("turbulent_velocity_km_s", "turbulent_velocity_km_s", "float"),
    ("input_dsec_radiation_count", "input_dsec_radiation_count", "integer"),
    ("input_dsec_radiation_fingerprint", "input_dsec_radiation_fingerprint", "fingerprint"),
    ("input_bremsa_count", "input_bremsa_count", "integer"),
    ("input_bremsa_fingerprint", "input_bremsa_fingerprint", "fingerprint"),
    ("input_tau_count", "input_tau_count", "integer"),
    ("input_tau_in_fingerprint", "input_tau_in_fingerprint", "fingerprint"),
    ("input_tau_out_fingerprint", "input_tau_out_fingerprint", "fingerprint"),
    ("input_global_level_count", "input_global_level_count", "integer"),
    ("input_xilevg_fingerprint", "input_xilevg_fingerprint", "fingerprint"),
    ("input_bilevg_fingerprint", "input_bilevg_fingerprint", "fingerprint"),
    ("input_rnisg_fingerprint", "input_rnisg_fingerprint", "fingerprint"),
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def _float_exact(left: str | float, right: str | float) -> bool:
    try:
        a = float(left); b = float(right)
    except Exception:
        return False
    return math.isfinite(a) and math.isfinite(b) and _bits(a) == _bits(b)


def _fingerprint(value: str) -> str:
    text = str(value).strip().lower()
    return text[2:] if text.startswith("0x") else text


def _identity(row: dict[str, str]) -> tuple[int, str, int, int]:
    return (int(row["sequence"]), row.get("kind", ""), int(row["call_index"]), int(row["evaluation_index"]))


def _classification(committed_exact: bool, computed_exact: bool) -> str:
    if committed_exact and computed_exact:
        return "COMMITTED_EXACT_NATIVE_COMPUTED_EXACT"
    if committed_exact:
        return "COMMITTED_EXACT_NATIVE_COMPUTED_DELTA"
    if computed_exact:
        return "COMMITTED_DELTA_NATIVE_COMPUTED_EXACT"
    return "COMMITTED_DELTA_NATIVE_COMPUTED_DELTA"


def compare(source_capture: Path, native_run: Path, output: Path) -> dict[str, Any]:
    source_path = source_capture / BUDGET_NAME
    native_path = native_run / THERMAL_LEDGER_NAME
    native_summary_path = native_run / "native_dsec_summary.json"
    for path in (source_path, native_path, native_summary_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    source_rows = _read_csv(source_path)
    native_rows = _read_csv(native_path)
    source_by_sequence = {int(row["sequence"]): row for row in source_rows}
    native_by_sequence = {int(row["sequence"]): row for row in native_rows}
    native_summary = json.loads(native_summary_path.read_text())
    compact_transport_present = any(
        "thermal_consumed_compact_population_closure" in row for row in native_rows
    )
    output.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    if sorted(source_by_sequence) != list(range(1, 62)):
        errors.append(f"source_sequence_inventory={len(source_by_sequence)}")
    if sorted(native_by_sequence) != list(range(1, 62)):
        errors.append(f"native_sequence_inventory={len(native_by_sequence)}")

    state_rows: list[dict[str, Any]] = []
    state_exact = 0
    state_total = 0
    population_exact = 0
    closure_applied = 0
    fixed_state_consumed = 0
    compact_population_consumed = 0
    identity_exact = 0
    for sequence in range(1, 62):
        source = source_by_sequence.get(sequence)
        native = native_by_sequence.get(sequence)
        if source is None or native is None:
            continue
        identity_ok = _identity(source) == _identity(native)
        identity_exact += int(identity_ok)
        state_rows.append({
            "sequence": sequence, "kind": source.get("kind", ""), "call_index": source.get("call_index", ""),
            "evaluation_index": source.get("evaluation_index", ""), "field": "canonical_identity",
            "source_value": str(_identity(source)), "native_value": str(_identity(native)), "exact": int(identity_ok),
        })
        for source_field, native_field, kind in STATE_FIELDS:
            state_total += 1
            left = source.get(source_field, "")
            right = native.get(native_field, "")
            if kind == "float":
                exact = _float_exact(left, right)
            elif kind == "integer":
                try: exact = int(float(left)) == int(float(right))
                except Exception: exact = False
            else:
                exact = bool(left) and _fingerprint(left) == _fingerprint(right)
            state_exact += int(exact)
            state_rows.append({
                "sequence": sequence, "kind": source.get("kind", ""), "call_index": source.get("call_index", ""),
                "evaluation_index": source.get("evaluation_index", ""), "field": source_field,
                "source_value": left, "native_value": right, "exact": int(exact),
            })
        try:
            pop_ok = (
                int(float(source["thermal_population_count"])) == int(float(native["thermal_population_count"]))
                and _fingerprint(source["thermal_population_fingerprint"]) == _fingerprint(native["thermal_population_fingerprint"])
            )
        except Exception:
            pop_ok = False
        population_exact += int(pop_ok)
        state_rows.append({
            "sequence": sequence, "kind": source.get("kind", ""), "call_index": source.get("call_index", ""),
            "evaluation_index": source.get("evaluation_index", ""), "field": "thermal_population_state",
            "source_value": f"{source.get('thermal_population_count','')}:{source.get('thermal_population_fingerprint','')}",
            "native_value": f"{native.get('thermal_population_count','')}:{native.get('thermal_population_fingerprint','')}",
            "exact": int(pop_ok),
        })
        closure_ok = native.get("thermal_component_closure_applied") == "1"
        consumed_ok = native.get("thermal_consumed_fixed_state_closure") == "1"
        compact_consumed_ok = native.get("thermal_consumed_compact_population_closure") == "1"
        closure_applied += int(closure_ok)
        fixed_state_consumed += int(consumed_ok)
        compact_population_consumed += int(compact_consumed_ok)
        closure_state_fields = [
            ("thermal_component_closure_applied", closure_ok),
            ("thermal_consumed_fixed_state_closure", consumed_ok),
        ]
        if compact_transport_present:
            closure_state_fields.append(("thermal_consumed_compact_population_closure", compact_consumed_ok))
        for field, ok in closure_state_fields:
            state_rows.append({
                "sequence": sequence, "kind": source.get("kind", ""), "call_index": source.get("call_index", ""),
                "evaluation_index": source.get("evaluation_index", ""), "field": field,
                "source_value": "1", "native_value": native.get(field, ""), "exact": int(ok),
            })

    _write_csv(
        output / STATE_DIFF_NAME,
        ["sequence", "kind", "call_index", "evaluation_index", "field", "source_value", "native_value", "exact"],
        state_rows,
    )

    component_rows: list[dict[str, Any]] = []
    committed_exact = 0
    computed_exact = 0
    component_total = 0
    group_counts = {name: {"exact": 0, "total": 0} for name in GROUP_FIELDS}
    computed_group_counts = {name: {"exact": 0, "total": 0} for name in GROUP_FIELDS}
    for sequence in range(1, 62):
        source = source_by_sequence.get(sequence)
        native = native_by_sequence.get(sequence)
        if source is None or native is None:
            continue
        for group, fields in GROUP_FIELDS.items():
            for field in fields:
                component_total += 1
                group_counts[group]["total"] += 1
                computed_group_counts[group]["total"] += 1
                source_value = source.get(field, "")
                committed_field = COMMITTED_NATIVE_FIELD.get(field, field)
                computed_field = COMPUTED_NATIVE_FIELD.get(field, f"computed_{field}")
                committed_value = native.get(committed_field, "")
                computed_value = native.get(computed_field, "")
                committed_ok = _float_exact(source_value, committed_value)
                computed_ok = _float_exact(source_value, computed_value)
                committed_exact += int(committed_ok)
                computed_exact += int(computed_ok)
                group_counts[group]["exact"] += int(committed_ok)
                computed_group_counts[group]["exact"] += int(computed_ok)
                try:
                    committed_delta = float(committed_value) - float(source_value)
                except Exception:
                    committed_delta = float("nan")
                try:
                    computed_delta = float(computed_value) - float(source_value)
                except Exception:
                    computed_delta = float("nan")
                component_rows.append({
                    "sequence": sequence, "kind": source.get("kind", ""), "call_index": source.get("call_index", ""),
                    "evaluation_index": source.get("evaluation_index", ""), "group": group, "component": field,
                    "source_value": source_value, "computed_native_value": computed_value,
                    "committed_native_value": committed_value, "computed_signed_delta": computed_delta,
                    "committed_signed_delta": committed_delta, "computed_exact": int(computed_ok),
                    "committed_exact": int(committed_ok), "classification": _classification(committed_ok, computed_ok),
                })
    _write_csv(
        output / COMPONENT_DIFF_NAME,
        ["sequence", "kind", "call_index", "evaluation_index", "group", "component", "source_value",
         "computed_native_value", "committed_native_value", "computed_signed_delta", "committed_signed_delta",
         "computed_exact", "committed_exact", "classification"],
        component_rows,
    )

    all61 = len(source_by_sequence) == len(native_by_sequence) == int(native_summary.get("total_evaluations", 0)) == 61
    callbacks_zero = int(native_summary.get("python_callbacks", -1)) == 0
    state_ok = state_exact == state_total == 61 * len(STATE_FIELDS) and identity_exact == 61
    populations_ok = population_exact == 61 and (
        compact_population_consumed == 61 if compact_transport_present else fixed_state_consumed == 61
    )
    component_groups_ok = {
        name: counts["exact"] == counts["total"] == 61 * len(GROUP_FIELDS[name])
        for name, counts in group_counts.items()
    }
    committed_ok = committed_exact == component_total == 61 * len(COMPONENT_FIELDS)
    independent_ok = computed_exact == component_total == 61 * len(COMPONENT_FIELDS)
    gates = {
        "ALL_61_THERMAL_EVALUATIONS": "ACCEPT" if all61 else "REJECT",
        "ALL_61_CANONICAL_IDENTITIES_EXACT": "ACCEPT" if identity_exact == 61 else "REJECT",
        "ALL_61_THERMAL_INPUT_STATE_FINGERPRINTS_EXACT": "ACCEPT" if state_ok else "REJECT",
        "ALL_61_THERMAL_POPULATION_STATE_EXACT": "ACCEPT" if populations_ok else "REJECT",
        "ALL_61_H_HE_MG_COMPONENTS_EXACT": "ACCEPT" if component_groups_ok["H_HE_MG"] else "REJECT",
        "ALL_61_CONTINUUM_COMPONENTS_EXACT": "ACCEPT" if component_groups_ok["CONTINUUM"] else "REJECT",
        "ALL_61_THERMAL_TOTALS_EXACT": "ACCEPT" if component_groups_ok["TOTALS"] else "REJECT",
        "ALL_61_HMCTOT_EXACT": "ACCEPT" if component_groups_ok["RESIDUAL"] else "REJECT",
        "ALL_61_THERMAL_ELCTER_RESIDUALS_EXACT": "ACCEPT" if component_groups_ok["ELCTER_RESIDUAL"] else "REJECT",
        "THERMAL_COMPONENT_CLOSURE_APPLIED_61": "ACCEPT" if closure_applied == 61 else "REJECT",
        "THERMAL_COMPACT_POPULATION_CLOSURE_APPLIED_61": (
            "ACCEPT" if compact_population_consumed == 61 else
            "NOT_APPLICABLE_PRE_V064874613" if not compact_transport_present else "REJECT"
        ),
        "PYTHON_CALLBACKS_ZERO": "ACCEPT" if callbacks_zero else "REJECT",
        "V06488_THERMAL_PARITY": "ACCEPT" if all61 and state_ok and populations_ok and committed_ok and closure_applied == 61 and callbacks_zero else "REJECT",
        "INDEPENDENT_NATIVE_THERMAL_PARITY": "ACCEPT" if independent_ok else "NOT_ACCEPTED",
        "CONTROLLER_PARITY": "NOT_RUN_V06489",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    }
    required_gate_names = [
        "ALL_61_THERMAL_EVALUATIONS", "ALL_61_CANONICAL_IDENTITIES_EXACT",
        "ALL_61_THERMAL_INPUT_STATE_FINGERPRINTS_EXACT", "ALL_61_THERMAL_POPULATION_STATE_EXACT",
        "ALL_61_H_HE_MG_COMPONENTS_EXACT", "ALL_61_CONTINUUM_COMPONENTS_EXACT",
        "ALL_61_THERMAL_TOTALS_EXACT", "ALL_61_HMCTOT_EXACT", "ALL_61_THERMAL_ELCTER_RESIDUALS_EXACT",
        "THERMAL_COMPONENT_CLOSURE_APPLIED_61",
        "PYTHON_CALLBACKS_ZERO", "V06488_THERMAL_PARITY",
    ]
    if compact_transport_present:
        required_gate_names.append("THERMAL_COMPACT_POPULATION_CLOSURE_APPLIED_61")
    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors and all(gates[name] == "ACCEPT" for name in required_gate_names) else "REJECT",
        "errors": errors,
        "gates": gates,
        "source_evaluations": len(source_by_sequence),
        "native_evaluations": len(native_by_sequence),
        "thermal_input_state_fields_exact": state_exact,
        "thermal_input_state_fields_total": state_total,
        "thermal_population_states_exact": population_exact,
        "thermal_component_closure_applied": closure_applied,
        "thermal_fixed_state_consumed": fixed_state_consumed,
        "thermal_compact_population_consumed": compact_population_consumed,
        "thermal_component_values_exact": committed_exact,
        "thermal_component_values_total": component_total,
        "native_computed_values_exact": computed_exact,
        "native_computed_values_total": component_total,
        "committed_group_counts": group_counts,
        "native_computed_group_counts": computed_group_counts,
        "independent_native_thermal_parity": "ACCEPT" if independent_ok else "NOT_ACCEPTED",
        "qualification_only": True,
        "source_captured_component_closure": True,
        "controller_parity_started": False,
        "production_promotion_ready": False,
    }
    (output / SUMMARY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.source_capture, args.native_run, args.output)
    except Exception as exc:
        result = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
            "gates": {"V06488_THERMAL_PARITY": "REJECT", "CONTROLLER_PARITY": "NOT_RUN_V06489",
                      "PRODUCT_PARITY": "BLOCKED", "PRODUCTION_PROMOTION": "BLOCKED"},
            "qualification_only": True, "production_promotion_ready": False,
        }
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / SUMMARY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.output_json:
        args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
