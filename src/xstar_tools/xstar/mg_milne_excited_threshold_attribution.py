#!/usr/bin/env python3
"""All-61 Mg Type-49 Milne / Type-53 excited-threshold qualification audit."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .all61_dense_matrix_causal_attribution import _binary64_ieee_equivalent

RELEASE = "0.6.48.7.46.9.4.1"
EXPECTED = {49: 49_349, 53: 53_436}
MAX_ULPS = 2
MAX_RELATIVE_DELTA = 4.0e-16


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


def _iter_causal(path: Path) -> Iterable[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as handle:
        yield from csv.DictReader(handle)


def _prefix(data_type: int) -> tuple[str, str]:
    return ("type49_", "type49_") if data_type == 49 else ("mg_type53_", "type53_shadow_")


def _direction(role: str) -> str:
    if role.startswith("forward"):
        return "forward"
    if role.startswith("reverse"):
        return "reverse"
    return "other"


def analyze(audit_output: Path) -> dict[str, Any]:
    errors: list[str] = []
    diagnostics_dir = audit_output / "native_all61" / "qualification_diagnostics"
    diagnostic_files = sorted(diagnostics_dir.glob("evaluation_*_records.csv"))
    if len(diagnostic_files) != 61:
        errors.append(f"diagnostic_files={len(diagnostic_files)} expected=61")

    type_counts: Counter[int] = Counter()
    source_zero: Counter[int] = Counter()
    context_counts: Counter[str] = Counter()
    invalid_context: Counter[str] = Counter()
    max_committed = 0.0
    max_legacy = 0.0

    context_fields = [
        "sequence", "record", "data_type", "ion_index", "ion_stage",
        "lower_row", "upper_row", "base_threshold_ev", "corrected_threshold_ev",
        "bound_energy_ev", "milne_partition_energy_ev", "destination_energy_ev",
        "excited_parent_energy_ev", "bound_g", "milne_partition_g",
        "destination_g", "excited_parent_g", "rnist", "exponent_energy_ev",
        "exponent_dimensionless", "electron_density_cm3", "hydrogen_density_cm3",
        "matrix_density_scale", "source_zero_gate", "phextrap_applied",
        "phextrap_source_reference_order", "phextrap_input_pair_count",
        "phextrap_output_pair_count", "milne_partition_context_used",
        "excited_threshold_context_used", "corrected_threshold_before_mapping",
        "source_faithful_mode", "replacement_applied", "runtime_state_abi_used",
        "committed_nonfinite", "committed_implausible", "legacy_max_abs",
        "committed_max_abs", "continuum_index_one_based",
        "dsec_radiation_bin_count", "continuum_tau_count",
    ]
    context_csv = audit_output / "all61_mg_type49_milne_type53_excited_threshold_context.csv"
    context_csv.parent.mkdir(parents=True, exist_ok=True)
    with context_csv.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=context_fields, lineterminator="\n")
        writer.writeheader()
        for path in diagnostic_files:
            sequence = int(path.name.split("_")[1])
            with path.open(newline="") as handle:
                for row in csv.DictReader(handle):
                    if row.get("element_z") != "12" or row.get("data_type") not in {"49", "53"}:
                        continue
                    dt = int(row["data_type"])
                    prefix, shadow = _prefix(dt)
                    values = {
                        "sequence": sequence,
                        "record": _i(row, "record"),
                        "data_type": dt,
                        "ion_index": _i(row, "ion_index"),
                        "ion_stage": _i(row, "ion_stage"),
                        "lower_row": _i(row, "lower_row"),
                        "upper_row": _i(row, "upper_row"),
                        "base_threshold_ev": _f(row, shadow + "base_threshold_ev"),
                        "corrected_threshold_ev": _f(row, shadow + "threshold_ev"),
                        "bound_energy_ev": _f(row, shadow + "bound_energy_ev"),
                        "milne_partition_energy_ev": _f(row, shadow + "continuum_energy_ev"),
                        "destination_energy_ev": _f(row, shadow + "destination_energy_ev"),
                        "excited_parent_energy_ev": _f(row, shadow + "excited_parent_energy_ev"),
                        "bound_g": _f(row, shadow + "bound_g"),
                        "milne_partition_g": _f(row, shadow + "continuum_g"),
                        "destination_g": _f(row, shadow + "destination_g"),
                        "excited_parent_g": _f(row, shadow + "excited_parent_g"),
                        "rnist": _f(row, shadow + "rnist"),
                        "exponent_energy_ev": _f(row, prefix + "exponent_energy_ev"),
                        "exponent_dimensionless": _f(row, prefix + "exponent_dimensionless"),
                        "electron_density_cm3": _f(row, prefix + "electron_density_cm3"),
                        "hydrogen_density_cm3": _f(row, prefix + "hydrogen_density_cm3"),
                        "matrix_density_scale": _f(row, prefix + "matrix_density_scale"),
                        "source_zero_gate": _i(row, "type49_source_zero_gate") if dt == 49 else 0,
                        "phextrap_applied": _i(row, "type49_phextrap_applied") if dt == 49 else 0,
                        "phextrap_source_reference_order": _i(row, shadow + "phextrap_source_reference_order"),
                        "phextrap_input_pair_count": _i(row, shadow + "phextrap_input_pair_count"),
                        "phextrap_output_pair_count": _i(row, shadow + "phextrap_output_pair_count"),
                        "milne_partition_context_used": _i(row, shadow + "milne_partition_context_used"),
                        "excited_threshold_context_used": _i(row, shadow + "excited_threshold_context_used"),
                        "corrected_threshold_before_mapping": _i(row, shadow + "corrected_threshold_before_mapping"),
                        "source_faithful_mode": _i(row, "type49_source_faithful_mode" if dt == 49 else "mg_type53_source_faithful_mode"),
                        "replacement_applied": _i(row, prefix + "replacement_applied"),
                        "runtime_state_abi_used": _i(row, "type49_runtime_state_abi_used" if dt == 49 else "type53_runtime_state_abi_used"),
                        "committed_nonfinite": _i(row, prefix + "committed_nonfinite"),
                        "committed_implausible": _i(row, prefix + "committed_implausible"),
                        "legacy_max_abs": _f(row, prefix + "legacy_max_abs"),
                        "committed_max_abs": _f(row, prefix + "committed_max_abs"),
                        "continuum_index_one_based": _i(row, "type49_continuum_index_one_based" if dt == 49 else "type53_continuum_index_one_based"),
                        "dsec_radiation_bin_count": _i(row, "type49_dsec_radiation_bin_count" if dt == 49 else "type53_dsec_radiation_bin_count"),
                        "continuum_tau_count": _i(row, "type49_continuum_tau_count" if dt == 49 else "type53_continuum_tau_count"),
                    }
                    writer.writerow(values)
                    type_counts[dt] += 1
                    source_zero[dt] += int(values["source_zero_gate"])
                    for key in (
                        "source_faithful_mode", "replacement_applied", "runtime_state_abi_used",
                        "committed_nonfinite", "committed_implausible", "milne_partition_context_used",
                        "phextrap_applied", "phextrap_source_reference_order",
                        "excited_threshold_context_used", "corrected_threshold_before_mapping",
                    ):
                        context_counts[f"{dt}:{key}"] += int(values[key])
                    if values["excited_parent_energy_ev"] > 0.0:
                        context_counts[f"{dt}:excited_parent_records"] += 1
                        if not values["excited_threshold_context_used"] and dt == 53:
                            invalid_context["type53_excited_threshold_not_used"] += 1
                    numeric = (
                        "base_threshold_ev", "corrected_threshold_ev", "bound_energy_ev",
                        "milne_partition_energy_ev", "destination_energy_ev",
                        "excited_parent_energy_ev", "bound_g", "milne_partition_g",
                        "destination_g", "excited_parent_g", "rnist", "exponent_energy_ev",
                        "exponent_dimensionless", "electron_density_cm3", "hydrogen_density_cm3",
                        "matrix_density_scale", "legacy_max_abs", "committed_max_abs",
                    )
                    for key in numeric:
                        if not math.isfinite(float(values[key])):
                            invalid_context[f"nonfinite:{key}"] += 1
                    if values["bound_g"] <= 0.0 or values["milne_partition_g"] <= 0.0 or values["destination_g"] <= 0.0:
                        invalid_context["nonpositive_statistical_weight"] += 1
                    if not values["milne_partition_context_used"]:
                        invalid_context["milne_partition_context_not_used"] += 1
                    if dt == 53 and not values["corrected_threshold_before_mapping"]:
                        invalid_context["type53_corrected_threshold_not_before_mapping"] += 1
                    if dt == 53:
                        expected_threshold = values["base_threshold_ev"] + values["excited_parent_energy_ev"]
                        if values["corrected_threshold_ev"] != expected_threshold:
                            invalid_context["type53_corrected_threshold_relation"] += 1
                    elif values["corrected_threshold_ev"] != values["base_threshold_ev"]:
                        invalid_context["type49_threshold_changed"] += 1
                    if values["continuum_index_one_based"] <= 0:
                        invalid_context["missing_continuum_index"] += 1
                    if values["dsec_radiation_bin_count"] != 9999:
                        invalid_context["radiation_bin_count"] += 1
                    if values["continuum_tau_count"] != 301301:
                        invalid_context["continuum_tau_count"] += 1
                    if dt == 49 and values["phextrap_applied"] and not values["phextrap_source_reference_order"]:
                        invalid_context["type49_phextrap_source_order"] += 1
                    if dt == 49 and values["source_zero_gate"]:
                        for ans_index in range(1, 7):
                            if _f(row, f"type49_shadow_ans{ans_index}") != 0.0:
                                invalid_context["source_zero_nonzero_shadow"] += 1
                            if _f(row, f"ans{ans_index}") != 0.0:
                                invalid_context["source_zero_nonzero_commit"] += 1
                    max_legacy = max(max_legacy, values["legacy_max_abs"] if math.isfinite(values["legacy_max_abs"]) else 0.0)
                    max_committed = max(max_committed, values["committed_max_abs"] if math.isfinite(values["committed_max_abs"]) else 0.0)

    causal_path = audit_output / "all61_dense_matrix_causal_records.csv.gz"
    if not causal_path.exists():
        fallback = audit_output / "all61_dense_matrix_causal_records.csv"
        causal_path = fallback if fallback.exists() else causal_path
    unexplained: list[dict[str, Any]] = []
    ieee_rows: list[dict[str, Any]] = []
    unexplained_by_type: Counter[int] = Counter()
    unexplained_by_type_direction: Counter[str] = Counter()
    classification_counts: Counter[str] = Counter()
    max_ulps = 0
    max_relative = 0.0
    max_absolute = 0.0
    if not causal_path.exists():
        errors.append(f"causal record output not found: {causal_path}")
    else:
        for row in _iter_causal(causal_path):
            if row.get("element_z") != "12" or row.get("data_type") not in {"49", "53"}:
                continue
            classification = row.get("classification", "")
            if classification == "ACCUMULATION_ORDER_ONLY":
                continue
            dt = int(row["data_type"])
            role = row.get("role", "")
            direction = _direction(role)
            classification_counts[f"{dt}:{classification}"] += 1
            accepted = False
            ulps = 0
            absolute = float("inf")
            relative = float("inf")
            if classification == "RATE_VALUE_DELTA" and row.get("source_present") == "1" and row.get("native_present") == "1":
                source_value = float(row["source_value"])
                native_value = float(row["native_value"])
                accepted, ulps, absolute, relative = _binary64_ieee_equivalent(source_value, native_value)
                accepted = accepted and ulps <= MAX_ULPS and relative <= MAX_RELATIVE_DELTA
            out = {
                "sequence": _i(row, "sequence"), "record": _i(row, "record"),
                "data_type": dt, "ion_stage": _i(row, "ion_stage"), "role": role,
                "direction": direction, "classification": classification,
                "source_value": row.get("source_value", ""), "native_value": row.get("native_value", ""),
                "delta": row.get("delta", ""), "ulp_distance": ulps,
                "absolute_delta": absolute, "relative_delta": relative,
            }
            if accepted:
                ieee_rows.append(out)
                max_ulps = max(max_ulps, ulps)
                max_relative = max(max_relative, relative)
                max_absolute = max(max_absolute, absolute)
            else:
                unexplained.append(out)
                unexplained_by_type[dt] += 1
                unexplained_by_type_direction[f"{dt}:{direction}"] += 1

    residual_csv = audit_output / "all61_mg_type49_milne_type53_excited_threshold_residuals.csv"
    residual_fields = [
        "sequence", "record", "data_type", "ion_stage", "role", "direction",
        "classification", "source_value", "native_value", "delta", "ulp_distance",
        "absolute_delta", "relative_delta",
    ]
    with residual_csv.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=residual_fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(ieee_rows); writer.writerows(unexplained)

    total_expected = sum(EXPECTED.values())
    for dt, expected in EXPECTED.items():
        if type_counts[dt] != expected:
            errors.append(f"Mg Type-{dt} records={type_counts[dt]} expected={expected}")
        for key in ("source_faithful_mode", "replacement_applied", "runtime_state_abi_used", "milne_partition_context_used"):
            if context_counts[f"{dt}:{key}"] != expected:
                errors.append(f"Type-{dt} {key}={context_counts[f'{dt}:{key}']} expected={expected}")
    if context_counts["49:phextrap_applied"] != EXPECTED[49] - source_zero[49]:
        errors.append("Type-49 phextrap application inventory mismatch")
    if context_counts["53:corrected_threshold_before_mapping"] != EXPECTED[53]:
        errors.append("Type-53 corrected-threshold-before-mapping inventory mismatch")
    if context_counts["49:committed_nonfinite"] or context_counts["53:committed_nonfinite"]:
        errors.append("committed nonfinite Mg bound-free values")
    if context_counts["49:committed_implausible"] or context_counts["53:committed_implausible"]:
        errors.append("committed implausible Mg bound-free values")
    if invalid_context:
        errors.append("invalid source context: " + json.dumps(dict(invalid_context), sort_keys=True))
    if unexplained:
        errors.append(f"unexplained Mg Type-49/53 causal rows={len(unexplained)}")

    gates = {
        "MG_TYPE49_FORWARD_UNEXPLAINED_ROWS_ZERO": "ACCEPT" if unexplained_by_type_direction["49:forward"] == 0 else "REJECT",
        "MG_TYPE49_REVERSE_UNEXPLAINED_ROWS_ZERO": "ACCEPT" if unexplained_by_type_direction["49:reverse"] == 0 else "REJECT",
        "MG_TYPE53_FORWARD_UNEXPLAINED_ROWS_ZERO": "ACCEPT" if unexplained_by_type_direction["53:forward"] == 0 else "REJECT",
        "MG_TYPE53_REVERSE_UNEXPLAINED_ROWS_ZERO": "ACCEPT" if unexplained_by_type_direction["53:reverse"] == 0 else "REJECT",
        "MG_TYPE49_PHEXTRAP_SOURCE_ORDER_EXACT": "ACCEPT" if not invalid_context.get("type49_phextrap_source_order") else "REJECT",
        "MG_MILNE_PARTITION_WEIGHT_CONTEXT_EXACT": "ACCEPT" if not invalid_context.get("milne_partition_context_not_used") and not invalid_context.get("nonpositive_statistical_weight") else "REJECT",
        "MG_TYPE53_EXCITED_THRESHOLD_CONTEXT_EXACT": "ACCEPT" if not invalid_context.get("type53_excited_threshold_not_used") and not invalid_context.get("type53_corrected_threshold_relation") else "REJECT",
        "MG_TYPE53_CORRECTED_THRESHOLD_USED_BEFORE_NBINC": "ACCEPT" if not invalid_context.get("type53_corrected_threshold_not_before_mapping") else "REJECT",
        "MG_BOUND_FREE_UNEXPLAINED_RATE_DELTAS_ZERO": "ACCEPT" if not unexplained else "REJECT",
        "MG_BOUND_FREE_SOURCE_CONTEXT_COMPLETE": "ACCEPT" if not invalid_context else "REJECT",
        "MG_BOUND_FREE_SOURCE_ZERO_GATE_EXACT": "ACCEPT" if not invalid_context.get("source_zero_nonzero_commit") and not invalid_context.get("source_zero_nonzero_shadow") else "REJECT",
        "MG_BOUND_FREE_COMMITTED_NONFINITE_ZERO": "ACCEPT" if context_counts["49:committed_nonfinite"] + context_counts["53:committed_nonfinite"] == 0 else "REJECT",
        "MG_BOUND_FREE_COMMITTED_IMPLAUSIBLE_ZERO": "ACCEPT" if context_counts["49:committed_implausible"] + context_counts["53:committed_implausible"] == 0 else "REJECT",
        "MG_TYPE50_ORIENTATION_CORRECTION": "DEFERRED",
    }
    accepted = not errors
    return {
        "schema": "xstar-tools-v0648746941-mg-milne-excited-threshold-v1",
        "release": RELEASE,
        "result": "ACCEPT" if accepted else "REJECT",
        "errors": errors,
        "record_counts": {str(k): v for k, v in sorted(type_counts.items())},
        "source_zero_counts": {str(k): v for k, v in sorted(source_zero.items())},
        "context_metrics": dict(context_counts),
        "invalid_context": dict(invalid_context),
        "residual_classification_counts": dict(classification_counts),
        "ieee_equivalent_rows": len(ieee_rows),
        "unexplained_rows": len(unexplained),
        "unexplained_by_type": {str(k): v for k, v in sorted(unexplained_by_type.items())},
        "unexplained_by_type_direction": dict(unexplained_by_type_direction),
        "max_ulp_distance": max_ulps,
        "max_absolute_delta": max_absolute,
        "max_relative_delta": max_relative,
        "max_legacy_abs": max_legacy,
        "max_committed_abs": max_committed,
        "context_output_csv": context_csv.name,
        "residual_output_csv": residual_csv.name,
        "gates": gates,
        "expected_total_records": total_expected,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.audit_output)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
