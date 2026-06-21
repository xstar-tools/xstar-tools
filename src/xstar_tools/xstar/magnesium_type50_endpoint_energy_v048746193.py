"""Audit v46.19.3 source-faithful Mg Type-50 endpoint-energy transport."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.4"
SCHEMA = "xstar-tools-v0648746193-magnesium-type50-endpoint-energy-audit-v1"
EXPECTED_EVALUATIONS = 61
EXPECTED_UNIQUE_RECORDS = 2420
EXPECTED_SEQUENCE_COUNTS = {
    **{sequence: 2196 for sequence in range(1, 5)},
    **{sequence: 2201 for sequence in range(5, 7)},
    **{sequence: 2420 for sequence in range(7, EXPECTED_EVALUATIONS + 1)},
}
EXPECTED_ROWS = sum(EXPECTED_SEQUENCE_COUNTS.values())
EXPECTED_COMMITTED_REVERSE_ROWS = EXPECTED_ROWS
SOURCE_ERG_PER_EV = 1.602176634e-12


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _exact(a: Any, b: Any) -> bool:
    try:
        return float(a).hex() == float(b).hex()
    except Exception:
        return str(a) == str(b)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def audit(source_capture: Path, native_run: Path, component_comparison: Path,
          output: Path) -> dict[str, Any]:
    errors: list[str] = []
    output.mkdir(parents=True, exist_ok=True)
    source_path = source_capture / "v0472_all61_magnesium_type50_endpoint_escape.csv"
    endpoint_map_path = source_capture / "v0472_magnesium_type50_endpoint_energy_map.csv"
    if not source_path.is_file() or not endpoint_map_path.is_file():
        missing = [str(path) for path in (source_path, endpoint_map_path) if not path.is_file()]
        return {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [f"missing:{path}" for path in missing], "gates": {},
            "qualification_only": True, "production_promotion_ready": False,
        }

    source_rows = _rows(source_path)
    source = {(int(row["sequence"]), int(row["record"])): row for row in source_rows}
    endpoint_rows = _rows(endpoint_map_path)
    endpoints = {int(row["record"]): row for row in endpoint_rows}
    source_counts: dict[int, int] = {}
    for sequence, _record in source:
        source_counts[sequence] = source_counts.get(sequence, 0) + 1
    source_unique_records = {record for _sequence, record in source}
    if len(source_rows) != len(source):
        errors.append(f"duplicate_source_keys={len(source_rows) - len(source)}")
    if len(endpoint_rows) != len(endpoints):
        errors.append(f"duplicate_endpoint_records={len(endpoint_rows) - len(endpoints)}")
    if source_counts != EXPECTED_SEQUENCE_COUNTS:
        errors.append(f"source_records_by_sequence={source_counts}")
    if len(source_unique_records) != EXPECTED_UNIQUE_RECORDS:
        errors.append(f"source_unique_records={len(source_unique_records)}")
    if set(endpoints) != source_unique_records:
        errors.append(
            f"endpoint_source_domain_mismatch=endpoint:{len(endpoints)},source:{len(source_unique_records)}"
        )

    endpoint_map_valid = 0
    source_endpoint_rows_exact = 0
    source_ans3_identity = 0
    source_ans4_identity = 0
    for record, row in endpoints.items():
        try:
            endpoint = float(row["source_endpoint_energy_ev"])
            endpoint1 = float(row["source_endpoint1_energy_ev"])
            endpoint2 = float(row["source_endpoint2_energy_ev"])
            if endpoint > 0.0 and math.isfinite(endpoint) and endpoint.hex() == row["source_endpoint_energy_hex"] and abs(endpoint1 - endpoint2).hex() == endpoint.hex():
                endpoint_map_valid += 1
        except Exception:
            pass
    for key, row in source.items():
        endpoint = endpoints.get(key[1])
        if endpoint and all(str(row[name]) == str(endpoint[name]) for name in (
            "idest1", "idest2", "source_endpoint1_energy_ev",
            "source_endpoint2_energy_ev", "source_endpoint_energy_ev",
            "source_endpoint_energy_hex",
        )):
            source_endpoint_rows_exact += 1
        energy = float(row["source_endpoint_energy_ev"])
        if (-float(row["ans2"]) * energy * SOURCE_ERG_PER_EV).hex() == float(row["ans3"]).hex():
            source_ans3_identity += 1
        if (-float(row["ans1"]) * energy * SOURCE_ERG_PER_EV).hex() == float(row["ans4"]).hex():
            source_ans4_identity += 1

    native: dict[tuple[int, int], dict[str, str]] = {}
    density_scale: dict[tuple[int, int], float] = {}
    for sequence in range(1, EXPECTED_EVALUATIONS + 1):
        path = native_run / "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
        if not path.is_file():
            errors.append(f"missing_native_records:{sequence}")
            continue
        for row in _rows(path):
            if (int(row.get("element_z", "0")) == 12 and
                    int(row.get("data_type", "0")) == 50 and
                    row.get("type50_magnesium_escape_state_applied") == "1"):
                key = (sequence, int(row["record"]))
                native[key] = row
                density_scale[key] = float(row["density_scale"])
    if set(native) != set(source):
        errors.append(
            f"native_source_domain_mismatch=missing:{len(set(source)-set(native))},extra:{len(set(native)-set(source))}"
        )

    counts = {
        "line": 0, "tau_in": 0, "tau_out": 0, "ptmp1": 0, "ptmp2": 0,
        "endpoint": 0, "endpoint1": 0, "endpoint2": 0, "endpoint_ids": 0,
        **{f"ans{i}": 0 for i in range(1, 7)},
    }
    comparison_rows: list[dict[str, Any]] = []
    for key, source_row in sorted(source.items()):
        native_row = native.get(key)
        if native_row is None:
            continue
        endpoint = endpoints[key[1]]
        exact = {
            "line": int(source_row["line_index"]) == int(native_row["type50_line_index_one_based"]),
            "tau_in": _exact(source_row["tau_in"], native_row["type50_line_tau_in"]),
            "tau_out": _exact(source_row["tau_out"], native_row["type50_line_tau_out"]),
            "ptmp1": _exact(source_row["ptmp1"], native_row["type50_ptmp1"]),
            "ptmp2": _exact(source_row["ptmp2"], native_row["type50_ptmp2"]),
            "endpoint": _exact(endpoint["source_endpoint_energy_ev"], native_row["type50_endpoint_energy_ev"]),
            "endpoint1": _exact(endpoint["source_endpoint1_energy_ev"], native_row["type50_source_endpoint1_energy_ev"]),
            "endpoint2": _exact(endpoint["source_endpoint2_energy_ev"], native_row["type50_source_endpoint2_energy_ev"]),
            "endpoint_ids": (
                int(endpoint["idest1"]) == int(native_row["type50_source_idest1"]) and
                int(endpoint["idest2"]) == int(native_row["type50_source_idest2"]) and
                native_row.get("type50_magnesium_source_endpoint_energy_applied") == "1"
            ),
        }
        for i in range(1, 7):
            exact[f"ans{i}"] = _exact(source_row[f"ans{i}"], native_row[f"type50_shadow_ans{i}"])
        for name, value in exact.items():
            counts[name] += int(value)
        comparison_rows.append({
            "sequence": key[0], "call_index": source_row["call_index"], "record": key[1],
            "source_position": native_row.get("source_position", ""),
            "source_idest1": endpoint["idest1"], "source_idest2": endpoint["idest2"],
            "native_idest1": native_row["type50_source_idest1"],
            "native_idest2": native_row["type50_source_idest2"],
            "source_endpoint1_energy_ev": endpoint["source_endpoint1_energy_ev"],
            "native_endpoint1_energy_ev": native_row["type50_source_endpoint1_energy_ev"],
            "source_endpoint2_energy_ev": endpoint["source_endpoint2_energy_ev"],
            "native_endpoint2_energy_ev": native_row["type50_source_endpoint2_energy_ev"],
            "source_endpoint_energy_ev": endpoint["source_endpoint_energy_ev"],
            "native_endpoint_energy_ev": native_row["type50_endpoint_energy_ev"],
            **{f"source_ans{i}": source_row[f"ans{i}"] for i in range(1, 7)},
            **{f"native_ans{i}": native_row[f"type50_shadow_ans{i}"] for i in range(1, 7)},
            **{f"{name}_exact": int(value) for name, value in exact.items()},
        })

    comparison_fields = [
        "sequence", "call_index", "record", "source_position",
        "source_idest1", "source_idest2", "native_idest1", "native_idest2",
        "source_endpoint1_energy_ev", "native_endpoint1_energy_ev",
        "source_endpoint2_energy_ev", "native_endpoint2_energy_ev",
        "source_endpoint_energy_ev", "native_endpoint_energy_ev",
    ] + [f"source_ans{i}" for i in range(1, 7)] + [
        f"native_ans{i}" for i in range(1, 7)
    ] + [f"{name}_exact" for name in counts]
    with (output / "v048746193_magnesium_type50_endpoint_comparison.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=comparison_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(comparison_rows)

    ledger_path = native_run / "native_all61_thermal_diagonal_ledger.csv"
    committed_rows = committed_cj_exact = committed_cooling_exact = 0
    closure_rows: list[dict[str, Any]] = []
    if not ledger_path.is_file():
        errors.append(f"missing:{ledger_path}")
    else:
        for row in _rows(ledger_path):
            if not (int(row.get("element_z", "0")) == 12 and
                    int(row.get("data_type", "0")) == 50 and
                    row.get("role") == "reverse_diag_loss"):
                continue
            key = (int(row["sequence"]), int(row["record"]))
            source_row = source.get(key)
            if source_row is None:
                errors.append(f"missing_source_for_diagonal:{key[0]}:{key[1]}")
                continue
            committed_rows += 1
            expected_cj = -float(source_row["ans3"]) * density_scale[key]
            expected_cooling = float(row["weighted_population"]) * expected_cj
            cj_exact = _exact(expected_cj, row["cj"])
            cooling_exact = _exact(expected_cooling, row["cooling_contribution"])
            committed_cj_exact += int(cj_exact)
            committed_cooling_exact += int(cooling_exact)
            closure_rows.append({
                "sequence": key[0], "call_index": row["call_index"],
                "source_position": row["source_position"], "record": key[1],
                "compact_row": row["compact_row"], "weighted_population": row["weighted_population"],
                "source_ans3": source_row["ans3"], "density_scale": density_scale[key],
                "expected_cj": expected_cj, "native_cj": row["cj"],
                "expected_cooling_contribution": expected_cooling,
                "native_cooling_contribution": row["cooling_contribution"],
                "cj_exact": int(cj_exact), "cooling_contribution_exact": int(cooling_exact),
            })
    with (output / "v048746193_magnesium_type50_matrix_closure_comparison.csv").open("w", newline="") as handle:
        fields = [
            "sequence", "call_index", "source_position", "record", "compact_row",
            "weighted_population", "source_ans3", "density_scale", "expected_cj",
            "native_cj", "expected_cooling_contribution", "native_cooling_contribution",
            "cj_exact", "cooling_contribution_exact",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(closure_rows)

    components = _rows(component_comparison)
    mg = [row for row in components if row.get("component") == "mg_cooling"]
    hydrogen = [row for row in components if row.get("component") == "h_cooling"]
    mg_exact = sum(int(row.get("computed_exact", "0")) for row in mg)
    h_exact = sum(int(row.get("computed_exact", "0")) for row in hydrogen)
    native_exact = sum(int(row.get("computed_exact", "0")) for row in components)
    total = len(components)

    all_answers_exact = sum(counts[f"ans{i}"] for i in range(1, 7)) == 6 * EXPECTED_ROWS
    gates = {
        "ALL_61_MAGNESIUM_TYPE50_ENDPOINT_STATES_CAPTURED": "ACCEPT" if len(source) == EXPECTED_ROWS and source_counts == EXPECTED_SEQUENCE_COUNTS else "REJECT",
        "MAGNESIUM_TYPE50_SOURCE_ENDPOINT_MAP_EXACT_2420": "ACCEPT" if endpoint_map_valid == EXPECTED_UNIQUE_RECORDS and len(endpoints) == EXPECTED_UNIQUE_RECORDS else "REJECT",
        "MAGNESIUM_TYPE50_SOURCE_ENDPOINT_ROWS_EXACT_146286": "ACCEPT" if source_endpoint_rows_exact == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_SOURCE_ANS3_ENDPOINT_IDENTITY_EXACT_146286": "ACCEPT" if source_ans3_identity == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_SOURCE_ANS4_ENDPOINT_IDENTITY_EXACT_146286": "ACCEPT" if source_ans4_identity == EXPECTED_ROWS else "REJECT",
        "ALL_61_MAGNESIUM_TYPE50_NATIVE_RECORDS_ATTRIBUTED": "ACCEPT" if set(native) == set(source) and len(native) == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ENDPOINT_IDS_EXACT_146286": "ACCEPT" if counts["endpoint_ids"] == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ENDPOINT_ENERGIES_EXACT_438858": "ACCEPT" if counts["endpoint"] + counts["endpoint1"] + counts["endpoint2"] == 3 * EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_LINE_INDICES_EXACT_146286": "ACCEPT" if counts["line"] == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_LINE_TAU_VALUES_EXACT_292572": "ACCEPT" if counts["tau_in"] + counts["tau_out"] == 2 * EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ESCAPE_FACTORS_EXACT_292572": "ACCEPT" if counts["ptmp1"] + counts["ptmp2"] == 2 * EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ANS1_EXACT_146286": "ACCEPT" if counts["ans1"] == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ANS2_EXACT_146286": "ACCEPT" if counts["ans2"] == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ANS3_EXACT_146286": "ACCEPT" if counts["ans3"] == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ANS4_EXACT_146286": "ACCEPT" if counts["ans4"] == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ANS5_EXACT_146286": "ACCEPT" if counts["ans5"] == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ANS6_EXACT_146286": "ACCEPT" if counts["ans6"] == EXPECTED_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_ANSWERS_EXACT_877716": "ACCEPT" if all_answers_exact else "REJECT",
        "MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286": "ACCEPT" if committed_rows == committed_cj_exact == EXPECTED_COMMITTED_REVERSE_ROWS else "REJECT",
        "MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286": "ACCEPT" if committed_rows == committed_cooling_exact == EXPECTED_COMMITTED_REVERSE_ROWS else "REJECT",
        "MAGNESIUM_COOLING_ALL61_EXACT": "ACCEPT" if len(mg) == mg_exact == EXPECTED_EVALUATIONS else "REJECT",
        "HYDROGEN_COOLING_ALL61_PRESERVED": "ACCEPT" if len(hydrogen) == h_exact == EXPECTED_EVALUATIONS else "REJECT",
        "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127": "ACCEPT" if native_exact == 1127 and total == 2440 else "REJECT",
        "MAGNESIUM_TYPE50_UNEXPLAINED_DELTAS_ZERO": "ACCEPT" if all_answers_exact and committed_rows == committed_cj_exact == committed_cooling_exact == EXPECTED_COMMITTED_REVERSE_ROWS else "REJECT",
    }
    errors.extend(name for name, value in gates.items() if value != "ACCEPT")
    return {
        "schema": SCHEMA, "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT", "errors": errors,
        "gates": gates,
        "source_rows": len(source), "source_unique_records": len(source_unique_records),
        "endpoint_map_rows": len(endpoint_rows), "endpoint_map_valid": endpoint_map_valid,
        "source_endpoint_rows_exact": source_endpoint_rows_exact,
        "source_ans3_endpoint_identity_exact": source_ans3_identity,
        "source_ans4_endpoint_identity_exact": source_ans4_identity,
        "native_rows": len(native), "comparison_rows": len(comparison_rows),
        "field_exact_counts": counts,
        "committed_reverse_rows": committed_rows,
        "committed_reverse_cj_exact": committed_cj_exact,
        "committed_reverse_cooling_exact": committed_cooling_exact,
        "mg_cooling_exact": mg_exact, "mg_cooling_total": len(mg),
        "hydrogen_cooling_exact": h_exact, "hydrogen_cooling_total": len(hydrogen),
        "native_computed_values_exact": native_exact,
        "native_computed_values_total": total,
        "qualification_only": True, "production_promotion_ready": False,
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
        result = audit(args.source_capture.resolve(), args.native_run.resolve(),
                       args.component_comparison.resolve(), args.output.resolve())
    except Exception as exc:
        result = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [str(exc)], "gates": {}, "qualification_only": True,
            "production_promotion_ready": False,
        }
    _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
