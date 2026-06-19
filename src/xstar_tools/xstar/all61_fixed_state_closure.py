"""Strict all-61 H/He/Mg fixed-state and electron-fraction comparator."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.46.17"
SCHEMA = "xstar-tools-v0648744-all61-h-he-mg-fixed-state-closure-v1"
SUMMARY_NAME = "all61_h_he_mg_fixed_state_closure_summary.json"
STATE_DIFF_NAME = "all61_state_comparison.csv"
ION_DIFF_NAME = "all61_ion_population_comparison.csv"
LEVEL_DIFF_NAME = "all61_level_population_comparison.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def _exact(left: float, right: float) -> bool:
    return _bits(left) == _bits(right)


def _float(row: dict[str, str], name: str) -> float:
    return float(row[name])


def _gate(flag: bool, blocked: str = "REJECT") -> str:
    return "ACCEPT" if flag else blocked


def compare(source_dir: Path, native_dir: Path, program_rows_csv: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    required = {
        "source_states": source_dir / "v0472_all61_fixed_state_rows.csv",
        "source_inputs": source_dir / "v0472_all61_input_states.csv",
        "source_ions": source_dir / "v0472_all61_ion_populations.csv",
        "source_levels": source_dir / "v0472_all61_level_populations.csv",
        "native_states": native_dir / "native_dsec_trajectory.csv",
        "native_summary": native_dir / "native_dsec_summary.json",
        "program_rows": program_rows_csv,
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    if missing:
        result = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [f"missing:{name}" for name in missing],
            "gates": {
                "ALL_61_NATIVE_EVALUATIONS": "NOT_RUN_MISSING_INPUT",
                "ALL_61_H_HE_MG_FIXED_STATE_PARITY": "NOT_RUN_MISSING_INPUT",
                "V06488_THERMAL_PARITY_READY": "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
                "THERMAL_PARITY": "BLOCKED",
                "PRODUCTION_PROMOTION": "BLOCKED",
            },
            "qualification_only": True, "production_promotion_ready": False,
        }
        (output_dir / SUMMARY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    source_states = _read_csv(required["source_states"])
    source_inputs = _read_csv(required["source_inputs"])
    native_states = _read_csv(required["native_states"])
    native_summary = json.loads(required["native_summary"].read_text())
    state_fields = ["temperature_t4", "electron_fraction_input", "computed_electron_fraction", "charge_residual"]
    source_state_by_sequence = {int(row["sequence"]): row for row in source_states}
    source_input_by_sequence = {int(row["sequence"]): row for row in source_inputs}
    native_state_by_sequence = {int(row["sequence"]): row for row in native_states}
    state_rows: list[dict[str, Any]] = []
    state_field_exact = {field: 0 for field in state_fields}
    for sequence in range(1, 62):
        source_state = source_state_by_sequence.get(sequence)
        source_input = source_input_by_sequence.get(sequence)
        native = native_state_by_sequence.get(sequence)
        identity = source_input or source_state or {}
        for field in state_fields:
            source_row = source_input if field in ("temperature_t4", "electron_fraction_input") else source_state
            source_value = float("nan") if source_row is None else _float(source_row, field)
            native_value = float("nan") if native is None else _float(native, field)
            exact = source_row is not None and native is not None and _exact(source_value, native_value)
            state_field_exact[field] += int(exact)
            state_rows.append({
                "sequence": sequence, "kind": identity.get("kind", ""), "call_index": identity.get("dsec_call_id", ""),
                "evaluation_index": identity.get("evaluation_index", ""), "field": field,
                "source_value": source_value, "native_value": native_value,
                "signed_delta": native_value - source_value, "exact": int(exact),
            })
    _write_csv(output_dir / STATE_DIFF_NAME,
               ["sequence","kind","call_index","evaluation_index","field","source_value","native_value","signed_delta","exact"], state_rows)

    source_ions = _read_csv(required["source_ions"])
    source_ion_map = {(int(r["sequence"]), int(r["element_z"]), int(r["stage"])): float(r["population"]) for r in source_ions}
    native_ion_map: dict[tuple[int,int,int], float] = {}
    diagnostics_dir = native_dir / "qualification_diagnostics"
    if not diagnostics_dir.is_dir():
        diagnostics_dir = native_dir / "diagnostics"
    for sequence in range(1, 62):
        path = diagnostics_dir / f"evaluation_{sequence:04d}_ion_balance.csv"
        if not path.is_file():
            continue
        for row in _read_csv(path):
            z = int(row["element_z"])
            if z in (1, 2, 12):
                native_ion_map[(sequence, z, int(row["stage"]))] = float(row["final_fraction"])
    ion_rows: list[dict[str, Any]] = []
    ion_exact = {1: 0, 2: 0, 12: 0}
    ion_total = {1: 0, 2: 0, 12: 0}
    for key in sorted(source_ion_map):
        sequence, z, stage = key; source_value = source_ion_map[key]
        native_value = native_ion_map.get(key, float("nan"))
        exact = key in native_ion_map and _exact(source_value, native_value)
        ion_total[z] += 1; ion_exact[z] += int(exact)
        ion_rows.append({"sequence": sequence, "element_z": z, "stage": stage, "ion_charge": stage-1,
                         "source_population": source_value, "native_population": native_value,
                         "signed_delta": native_value-source_value, "exact": int(exact)})
    _write_csv(output_dir / ION_DIFF_NAME,
               ["sequence","element_z","stage","ion_charge","source_population","native_population","signed_delta","exact"], ion_rows)

    program_rows = _read_csv(required["program_rows"])
    local_to_global = {index + 1: int(row["global_level_index"]) for index, row in enumerate(program_rows)}
    source_levels = _read_csv(required["source_levels"])
    source_level_map = {(int(r["sequence"]), int(r["global_level_index"])): float(r["population"]) for r in source_levels}
    native_level_map: dict[tuple[int,int], tuple[float,int,int,int,int]] = {}
    for sequence in range(1, 62):
        path = diagnostics_dir / f"evaluation_{sequence:04d}_populations.csv"
        if not path.is_file():
            continue
        for row in _read_csv(path):
            local = int(row["global_population_row"])
            global_index = local_to_global.get(local)
            if global_index is None:
                continue
            native_level_map[(sequence, global_index)] = (
                float(row["final_population"]), int(row["element_z"]), int(row["ion"]),
                int(row["superlevel"]), int(row["active_row"]),
            )
    level_rows: list[dict[str, Any]] = []
    level_exact_count = 0
    level_expected_count = 0
    for key in sorted(native_level_map):
        sequence, global_index = key
        native_value, z, ion, superlevel, active = native_level_map[key]
        if z not in (1, 2, 12):
            continue
        source_value = source_level_map.get(key, float("nan"))
        exact = key in source_level_map and _exact(source_value, native_value)
        level_expected_count += 1; level_exact_count += int(exact)
        level_rows.append({"sequence": sequence, "global_level_index": global_index, "element_z": z,
                           "ion": ion, "superlevel": superlevel, "active_row": active,
                           "source_population": source_value, "native_population": native_value,
                           "signed_delta": native_value-source_value, "exact": int(exact)})
    _write_csv(output_dir / LEVEL_DIFF_NAME,
               ["sequence","global_level_index","element_z","ion","superlevel","active_row","source_population","native_population","signed_delta","exact"], level_rows)

    total_evaluations = int(native_summary.get("total_evaluations", len(native_states)))
    python_callbacks = int(native_summary.get("python_callbacks", -1))
    all61 = len(source_states) == 61 and len(source_inputs) == 61 and len(native_states) == 61 and total_evaluations == 61
    callbacks_zero = python_callbacks == 0
    input_states_exact = state_field_exact["temperature_t4"] == 61 and state_field_exact["electron_fraction_input"] == 61
    electron_exact = state_field_exact["computed_electron_fraction"] == 61
    charge_exact = state_field_exact["charge_residual"] == 61
    h_exact = ion_total[1] == 122 and ion_exact[1] == ion_total[1]
    he_exact = ion_total[2] == 183 and ion_exact[2] == ion_total[2]
    mg_exact = ion_total[12] == 793 and ion_exact[12] == ion_total[12]
    ions_exact = h_exact and he_exact and mg_exact
    levels_exact = level_expected_count == 61 * len(program_rows) and level_exact_count == level_expected_count
    fixed_state_exact = all61 and callbacks_zero and input_states_exact and ions_exact and levels_exact and electron_exact and charge_exact
    gates = {
        "ALL_61_NATIVE_EVALUATIONS": _gate(all61),
        "PYTHON_CALLBACKS_ZERO": _gate(callbacks_zero),
        "ALL_61_REFERENCE_INPUT_STATES_EXACT": _gate(input_states_exact),
        "ALL_61_H_ION_POPULATIONS_EXACT": _gate(h_exact),
        "ALL_61_HE_ION_POPULATIONS_EXACT": _gate(he_exact),
        "ALL_61_MG_ION_POPULATIONS_EXACT": _gate(mg_exact),
        "ALL_61_H_HE_MG_ION_POPULATIONS_EXACT": _gate(ions_exact),
        "ALL_61_ACTIVE_LEVEL_POPULATIONS_EXACT": _gate(levels_exact),
        "ALL_61_ELECTRON_FRACTION_EXACT": _gate(electron_exact),
        "ALL_61_CHARGE_RESIDUAL_EXACT": _gate(charge_exact),
        "ALL_61_H_HE_MG_FIXED_STATE_PARITY": _gate(fixed_state_exact),
        "V06487_FIXED_STATE_PARITY": _gate(fixed_state_exact),
        "V06488_THERMAL_PARITY_READY": "ACCEPT" if fixed_state_exact else "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
        "THERMAL_PARITY": "NOT_RUN_READY_FOR_V06488" if fixed_state_exact else "BLOCKED",
        "CONTROLLER_PARITY": "NOT_RUN_V06489",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    }
    result = {
        "schema": SCHEMA, "release": RELEASE, "result": "ACCEPT" if fixed_state_exact else "REJECT",
        "gates": gates, "source_evaluations": len(source_states), "native_evaluations": len(native_states),
        "native_summary_total_evaluations": total_evaluations, "python_callbacks": python_callbacks,
        "state_exact_counts": state_field_exact,
        "ion_exact_counts": {str(z): {"exact": ion_exact[z], "total": ion_total[z]} for z in (1,2,12)},
        "active_level_exact_count": level_exact_count, "active_level_total": level_expected_count,
        "active_program_rows": len(program_rows),
        "qualification_only": True, "production_promotion_ready": False,
        "thermal_parity_started": False,
        "type77_benchmark_math": "runtime pow(10,x) retained only for immutable-reference qualification; exp10 remains the production optimization target after exactness qualification",
    }
    (output_dir / SUMMARY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--program-rows", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.source_capture, args.native_run, args.program_rows, args.output)
    except Exception as exc:
        result = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "gates": {"ALL_61_H_HE_MG_FIXED_STATE_PARITY": "REJECT", "V06488_THERMAL_PARITY_READY": "NO_FIXED_STATE_GATE_NOT_ACCEPTED", "THERMAL_PARITY": "BLOCKED", "PRODUCTION_PROMOTION": "BLOCKED"},
                  "qualification_only": True, "production_promotion_ready": False}
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / SUMMARY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.output_json:
        args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
