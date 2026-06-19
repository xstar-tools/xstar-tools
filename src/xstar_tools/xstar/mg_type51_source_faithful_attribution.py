#!/usr/bin/env python3
"""All-61 Mg Type-51 source-faithful contribution and runtime-context audit."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from .all61_dense_matrix_causal_attribution import (
    _binary64_ieee_equivalent,
    _load_system,
    _native_manifests,
    _source_manifests,
)

RELEASE = "0.6.48.7.46.17"
EXPECTED_CONTRIBUTION_VECTORS = 67_149
EXPECTED_UNIQUE_ACTIVE_RECORDS = 1_101
EXPECTED_RUNTIME_RECORD_EVALUATIONS = 72_651
EXPECTED_UNIQUE_RUNTIME_RECORDS = 1_191
MAX_ULPS = 5
MAX_RELATIVE_DELTA = 6.0e-16
NONZERO_ABSOLUTE_TOLERANCE = 0.0
ROUNDING_FIELDS = tuple(f"real_{index}" for index in range(16))


def _i(row: dict[str, str], key: str) -> int:
    try:
        return int(float(row.get(key, "0") or 0))
    except (TypeError, ValueError):
        return 0


def _f(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, "nan"))
    except (TypeError, ValueError):
        return float("nan")


def type51_binary64_ieee_equivalent(left: float, right: float) -> tuple[bool, int, float, float]:
    """Apply the demonstrated Mg Type-51 binary64 qualification envelope.

    The envelope is intentionally local to this family and workload.  It has
    no nonzero absolute tolerance and rejects nonfinite, sign-changing, and
    zero-to-nonzero comparisons.
    """
    _, ulps, absolute_delta, relative_delta = _binary64_ieee_equivalent(left, right)
    if left == right:
        return True, 0, 0.0, 0.0
    if not math.isfinite(left) or not math.isfinite(right):
        return False, ulps, absolute_delta, relative_delta
    if left == 0.0 or right == 0.0:
        return False, ulps, absolute_delta, relative_delta
    if math.copysign(1.0, left) != math.copysign(1.0, right):
        return False, ulps, absolute_delta, relative_delta
    return (
        ulps <= MAX_ULPS and relative_delta <= MAX_RELATIVE_DELTA,
        ulps,
        absolute_delta,
        relative_delta,
    )


def type51_ieee_equivalence_self_test() -> dict[str, Any]:
    base = 1.9
    five = base
    for _ in range(5):
        five = math.nextafter(five, math.inf)
    six = math.nextafter(five, math.inf)
    errors: list[str] = []
    if not type51_binary64_ieee_equivalent(base, five)[0]:
        errors.append("five-ULP representative was rejected")
    if type51_binary64_ieee_equivalent(base, six)[0]:
        errors.append("six-ULP representative was accepted")
    if type51_binary64_ieee_equivalent(0.0, math.nextafter(0.0, 1.0))[0]:
        errors.append("zero-to-nonzero transition was accepted")
    if type51_binary64_ieee_equivalent(1.0, -1.0)[0]:
        errors.append("sign transition was accepted")
    if type51_binary64_ieee_equivalent(float("inf"), 1.0)[0]:
        errors.append("nonfinite transition was accepted")
    accepted, ulps, _, relative = type51_binary64_ieee_equivalent(base, five)
    return {
        "schema": "xstar-tools-v064874695-mg-type51-ieee-self-test-v1",
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "five_ulp_accepted": accepted,
        "six_ulp_rejected": not type51_binary64_ieee_equivalent(base, six)[0],
        "max_ulp_distance": ulps,
        "relative_delta": relative,
        "limits": {
            "max_ulps": MAX_ULPS,
            "max_relative_delta": MAX_RELATIVE_DELTA,
            "nonzero_absolute_tolerance": NONZERO_ABSOLUTE_TOLERANCE,
            "finite_required": True,
            "same_sign_required": True,
            "zero_to_nonzero_rejected": True,
        },
    }


def _runtime_context(native_run: Path, errors: list[str]) -> dict[str, Any]:
    root = native_run / "qualification_diagnostics"
    files = sorted(root.glob("evaluation_*_records.csv"))
    if len(files) != 61:
        errors.append(f"Type-51 diagnostic files={len(files)} expected=61")
    counts: Counter[str] = Counter()
    points: Counter[int] = Counter()
    stages: Counter[int] = Counter()
    unique_records: set[int] = set()
    invalid_rows: list[dict[str, Any]] = []
    for path in files:
        sequence = int(path.name.split("_")[1])
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("element_z") != "12" or row.get("data_type") != "51":
                    continue
                counts["records"] += 1
                record = _i(row, "record")
                unique_records.add(record)
                points[_i(row, "type51_point_count")] += 1
                stages[_i(row, "ion_stage")] += 1
                flags = {
                    "shadow_valid": _i(row, "type51_shadow_valid"),
                    "source_faithful_mode": _i(row, "type51_source_faithful_mode"),
                    "replacement_applied": _i(row, "type51_replacement_applied"),
                    "endpoint_order_exact": _i(row, "type51_endpoint_order_exact"),
                    "committed_nonfinite": _i(row, "type51_committed_nonfinite"),
                }
                for name in ("shadow_valid", "source_faithful_mode", "replacement_applied", "endpoint_order_exact"):
                    counts[name] += flags[name]
                counts["committed_nonfinite"] += flags["committed_nonfinite"]
                counts["temperature_floor_applied"] += _i(row, "type51_temperature_floor_applied")
                committed_exact = all(
                    _f(row, f"ans{index}") == _f(row, f"type51_shadow_ans{index}")
                    for index in range(1, 7)
                )
                counts["committed_shadow_exact"] += int(committed_exact)
                finite_context = all(
                    math.isfinite(_f(row, field))
                    for field in (
                        "type51_eij_ryd", "type51_eij_ev", "type51_scaling_c",
                        "type51_physical_temperature_k", "type51_floor_temperature_k",
                        "type51_effective_temperature_k", "type51_scaled_temperature",
                        "type51_transformed_temperature", "type51_scaled_upsilon",
                        "type51_upsilon", "type51_lower_g", "type51_upper_g",
                        "type51_electron_density_cm3", "type51_q_excitation_cm3_s",
                        "type51_q_deexcitation_cm3_s",
                    )
                )
                counts["finite_context"] += int(finite_context)
                point_count = _i(row, "type51_point_count")
                valid = (
                    all(flags[name] == 1 for name in ("shadow_valid", "source_faithful_mode", "replacement_applied", "endpoint_order_exact"))
                    and flags["committed_nonfinite"] == 0
                    and point_count in (5, 9)
                    and committed_exact
                    and finite_context
                )
                if not valid and len(invalid_rows) < 100:
                    invalid_rows.append({
                        "sequence": sequence,
                        "record": record,
                        "ion_stage": _i(row, "ion_stage"),
                        "point_count": point_count,
                        **flags,
                        "committed_shadow_exact": int(committed_exact),
                        "finite_context": int(finite_context),
                    })
    counts["unique_records"] = len(unique_records)
    return {
        "diagnostic_files": len(files),
        "record_evaluations": counts["records"],
        "unique_records": len(unique_records),
        "shadow_valid": counts["shadow_valid"],
        "source_faithful_mode": counts["source_faithful_mode"],
        "replacement_applied": counts["replacement_applied"],
        "endpoint_order_exact": counts["endpoint_order_exact"],
        "committed_nonfinite": counts["committed_nonfinite"],
        "committed_shadow_exact": counts["committed_shadow_exact"],
        "finite_context": counts["finite_context"],
        "temperature_floor_applied": counts["temperature_floor_applied"],
        "point_count_distribution": {str(key): value for key, value in sorted(points.items())},
        "ion_stage_distribution": {str(key): value for key, value in sorted(stages.items())},
        "invalid_rows": invalid_rows,
    }


def analyze(source_capture: Path, native_run: Path, output: Path) -> dict[str, Any]:
    errors: list[str] = []
    source_manifests = _source_manifests(source_capture)
    native_manifests = _native_manifests(native_run)
    if set(source_manifests) != set(native_manifests):
        errors.append("source/native solve-system manifest keys differ")

    expected = present = endpoints = exact = equivalent = 0
    roundoff_vectors = roundoff_fields = 0
    max_ulps = 0
    max_absolute = 0.0
    max_relative = 0.0
    source_unique: set[tuple[int, int, int, int]] = set()
    native_unique: set[tuple[int, int, int, int]] = set()
    order_exact_systems = 0
    system_counts: Counter[int] = Counter()
    stage_counts: Counter[int] = Counter()
    roundoff_rows: list[dict[str, Any]] = []
    unexplained_rows: list[dict[str, Any]] = []

    for key in sorted(set(source_manifests) & set(native_manifests)):
        sequence, element_z = key
        if element_z != 12:
            continue
        source = _load_system(source_manifests[key], source=True)
        native = _load_system(native_manifests[key], source=False)
        source_type51 = [item for item in source.contributions if item.data_type == 51]
        native_type51 = [item for item in native.contributions if item.data_type == 51]
        source_order = [item.identity for item in source_type51]
        native_order = [item.identity for item in native_type51]
        order_exact_systems += int(source_order == native_order)
        system_counts[len(source_type51)] += 1
        source_map = {item.identity: item for item in source_type51}
        native_map = {item.identity: item for item in native_type51}
        source_unique.update(source_map)
        native_unique.update(native_map)
        identities = sorted(set(source_map) | set(native_map))
        for identity in identities:
            expected += 1
            source_item = source_map.get(identity)
            native_item = native_map.get(identity)
            if source_item is None or native_item is None:
                if len(unexplained_rows) < 500:
                    unexplained_rows.append({
                        "sequence": sequence, "record": identity[0], "ion_stage": identity[3],
                        "classification": "PRESENCE_MISMATCH",
                        "source_present": int(source_item is not None),
                        "native_present": int(native_item is not None),
                    })
                continue
            present += 1
            stage_counts[identity[3]] += 1
            if (source_item.lower, source_item.upper) == (native_item.lower, native_item.upper):
                endpoints += 1
            else:
                if len(unexplained_rows) < 500:
                    unexplained_rows.append({
                        "sequence": sequence, "record": identity[0], "ion_stage": identity[3],
                        "classification": "ENDPOINT_MISMATCH",
                        "source_lower": source_item.lower, "source_upper": source_item.upper,
                        "native_lower": native_item.lower, "native_upper": native_item.upper,
                    })
                continue
            if source_item.reals == native_item.reals:
                exact += 1
                equivalent += 1
                continue
            vector_equivalent = True
            differing_fields = 0
            vector_max_ulps = 0
            vector_max_absolute = 0.0
            vector_max_relative = 0.0
            differences: list[dict[str, Any]] = []
            for index, (left, right) in enumerate(zip(source_item.reals, native_item.reals)):
                if left == right:
                    continue
                differing_fields += 1
                accepted, ulps, absolute_delta, relative_delta = type51_binary64_ieee_equivalent(left, right)
                vector_equivalent = vector_equivalent and accepted
                vector_max_ulps = max(vector_max_ulps, ulps)
                vector_max_absolute = max(vector_max_absolute, absolute_delta)
                vector_max_relative = max(vector_max_relative, relative_delta)
                differences.append({
                    "field": ROUNDING_FIELDS[index],
                    "source_value": left,
                    "native_value": right,
                    "delta": right - left,
                    "ulp_distance": ulps,
                    "absolute_delta": absolute_delta,
                    "relative_delta": relative_delta,
                    "accepted": int(accepted),
                })
            max_ulps = max(max_ulps, vector_max_ulps)
            max_absolute = max(max_absolute, vector_max_absolute)
            max_relative = max(max_relative, vector_max_relative)
            if vector_equivalent:
                equivalent += 1
                roundoff_vectors += 1
                roundoff_fields += differing_fields
                roundoff_rows.append({
                    "sequence": sequence,
                    "record": identity[0],
                    "data_type": identity[1],
                    "rate_type": identity[2],
                    "ion_stage": identity[3],
                    "source_order_index": source_item.order,
                    "native_order_index": native_item.order,
                    "lower_row": source_item.lower,
                    "upper_row": source_item.upper,
                    "differing_real_fields": differing_fields,
                    "max_ulp_distance": vector_max_ulps,
                    "max_absolute_delta": vector_max_absolute,
                    "max_relative_delta": vector_max_relative,
                    "differences_json": json.dumps(differences, separators=(",", ":"), sort_keys=True),
                })
            else:
                unexplained_rows.append({
                    "sequence": sequence,
                    "record": identity[0],
                    "data_type": identity[1],
                    "rate_type": identity[2],
                    "ion_stage": identity[3],
                    "classification": "MATERIAL_VALUE_DELTA",
                    "differing_real_fields": differing_fields,
                    "max_ulp_distance": vector_max_ulps,
                    "max_absolute_delta": vector_max_absolute,
                    "max_relative_delta": vector_max_relative,
                    "differences_json": json.dumps(differences, separators=(",", ":"), sort_keys=True),
                })

    runtime = _runtime_context(native_run, errors)
    output.mkdir(parents=True, exist_ok=True)
    roundoff_path = output / "all61_mg_type51_source_faithful_roundoff.csv"
    roundoff_fields_out = [
        "sequence", "record", "data_type", "rate_type", "ion_stage",
        "source_order_index", "native_order_index", "lower_row", "upper_row",
        "differing_real_fields", "max_ulp_distance", "max_absolute_delta",
        "max_relative_delta", "differences_json",
    ]
    with roundoff_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=roundoff_fields_out)
        writer.writeheader()
        writer.writerows(roundoff_rows)
    unexplained_path = output / "all61_mg_type51_source_faithful_unexplained.csv"
    unexplained_fields = sorted({key for row in unexplained_rows for key in row}) or ["classification"]
    with unexplained_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=unexplained_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(unexplained_rows)

    runtime_total = int(runtime.get("record_evaluations", -1))
    runtime_complete = (
        runtime.get("diagnostic_files") == 61
        and runtime_total == EXPECTED_RUNTIME_RECORD_EVALUATIONS
        and runtime.get("unique_records") == EXPECTED_UNIQUE_RUNTIME_RECORDS
        and all(runtime.get(name) == runtime_total for name in (
            "shadow_valid", "source_faithful_mode", "replacement_applied",
            "endpoint_order_exact", "committed_shadow_exact", "finite_context",
        ))
        and runtime.get("committed_nonfinite") == 0
        and not runtime.get("invalid_rows")
        and set(runtime.get("point_count_distribution", {})).issubset({"5", "9"})
    )
    contribution_inventory_exact = (
        expected == present == EXPECTED_CONTRIBUTION_VECTORS
        and len(source_unique) == len(native_unique) == EXPECTED_UNIQUE_ACTIVE_RECORDS
    )
    gates = {
        "MG_TYPE51_RECORDS_EXPECTED": "ACCEPT" if contribution_inventory_exact else "REJECT",
        "MG_TYPE51_RECORDS_ATTRIBUTED": "ACCEPT" if present == EXPECTED_CONTRIBUTION_VECTORS else "REJECT",
        "MG_TYPE51_SOURCE_RECORD_ORDER_EXACT": "ACCEPT" if order_exact_systems == 61 else "REJECT",
        "MG_TYPE51_ENDPOINTS_EXACT": "ACCEPT" if endpoints == EXPECTED_CONTRIBUTION_VECTORS else "REJECT",
        "MG_TYPE51_CONTRIBUTIONS_BIT_EXACT": "ACCEPT" if exact == EXPECTED_CONTRIBUTION_VECTORS else "REJECT",
        "MG_TYPE51_CONTRIBUTIONS_IEEE_EQUIVALENT": "ACCEPT" if equivalent == EXPECTED_CONTRIBUTION_VECTORS else "REJECT",
        "MG_TYPE51_IEEE_ROUNDOFF_ENVELOPE": "ACCEPT" if (
            equivalent == EXPECTED_CONTRIBUTION_VECTORS
            and max_ulps <= MAX_ULPS and max_relative <= MAX_RELATIVE_DELTA
        ) else "REJECT",
        "MG_TYPE51_FORWARD_UNEXPLAINED_ROWS_ZERO": "ACCEPT" if not unexplained_rows else "REJECT",
        "MG_TYPE51_REVERSE_UNEXPLAINED_ROWS_ZERO": "ACCEPT" if not unexplained_rows else "REJECT",
        "MG_TYPE51_UNEXPLAINED_RATE_DELTAS_ZERO": "ACCEPT" if not unexplained_rows else "REJECT",
        "MG_TYPE51_RUNTIME_CONTEXT_COMPLETE": "ACCEPT" if runtime_complete else "REJECT",
        "MG_TYPE51_SOURCE_FAITHFUL_MODE_ALL": "ACCEPT" if runtime_complete else "REJECT",
        "MG_TYPE51_ENDPOINT_ORDER_RUNTIME_EXACT": "ACCEPT" if runtime_complete else "REJECT",
        "MG_TYPE51_COMMITTED_NONFINITE_ZERO": "ACCEPT" if runtime.get("committed_nonfinite") == 0 else "REJECT",
        "MG_TYPE51_COMMITTED_SHADOW_EXACT": "ACCEPT" if runtime.get("committed_shadow_exact") == runtime_total else "REJECT",
    }
    required = [value for key, value in gates.items() if key != "MG_TYPE51_CONTRIBUTIONS_BIT_EXACT"]
    result = "ACCEPT" if not errors and all(value == "ACCEPT" for value in required) else "REJECT"
    report = {
        "schema": "xstar-tools-v064874695-mg-type51-source-faithful-attribution-v1",
        "release": RELEASE,
        "result": result,
        "errors": errors,
        "contribution_vectors_expected": expected,
        "contribution_vectors_present": present,
        "unique_source_records": len(source_unique),
        "unique_native_records": len(native_unique),
        "endpoints_exact": endpoints,
        "relative_order_exact_systems": order_exact_systems,
        "contributions_bit_exact": exact,
        "contributions_ieee_equivalent": equivalent,
        "roundoff_record_vectors": roundoff_vectors,
        "roundoff_real_fields": roundoff_fields,
        "unexplained_record_vectors": len(unexplained_rows),
        "max_ulp_distance": max_ulps,
        "max_absolute_delta": max_absolute,
        "max_relative_delta": max_relative,
        "ieee_tolerance": {
            "max_ulps": MAX_ULPS,
            "max_relative_delta": MAX_RELATIVE_DELTA,
            "nonzero_absolute_tolerance": NONZERO_ABSOLUTE_TOLERANCE,
            "finite_required": True,
            "same_sign_required": True,
            "zero_to_nonzero_rejected": True,
        },
        "per_evaluation_contribution_counts": {str(key): value for key, value in sorted(system_counts.items())},
        "active_ion_stage_distribution": {str(key): value for key, value in sorted(stage_counts.items())},
        "runtime_context": runtime,
        "roundoff_csv": roundoff_path.name,
        "unexplained_csv": unexplained_path.name,
        "gates": gates,
        "qualification_only": True,
        "thermal_parity_started": False,
        "production_promotion_ready": False,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.source_capture, args.native_run, args.output)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
