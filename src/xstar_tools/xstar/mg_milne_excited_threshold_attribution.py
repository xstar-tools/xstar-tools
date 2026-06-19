#!/usr/bin/env python3
"""All-61 Mg Type-49 extrapolated-grid / Type-53 context qualification audit."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .all61_dense_matrix_causal_attribution import _binary64_ieee_equivalent

RELEASE = "0.6.48.7.46.17.2.1"
EXPECTED = {49: 49_349, 53: 53_436}
EXPECTED_UNIQUE_TYPE49 = 809
TYPE49_PHEXTRAP_MAX_POINTS = 999
MAX_ULPS = 3
MAX_RELATIVE_DELTA = 4.5e-16
_FNV_OFFSET = 1469598103934665603
_FNV_PRIME = 1099511628211
_FNV_MASK = (1 << 64) - 1


def _i(row: dict[str, str], key: str) -> int:
    try:
        return int(float(row.get(key, "0") or 0))
    except (TypeError, ValueError):
        return 0


def _u64(row: dict[str, str], key: str) -> int:
    try:
        return int(str(row.get(key, "0") or "0"), 10)
    except (TypeError, ValueError):
        return 0


def _f(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, "nan"))
    except (TypeError, ValueError):
        return float("nan")



def _mg_binary64_ieee_equivalent(left: float, right: float) -> tuple[bool, int, float, float]:
    # Reuse the canonical ULP calculation, but apply the explicitly reported
    # Mg bound-free envelope.  The hydrogen helper has a deliberately tighter
    # two-ULP release contract and must not silently constrain this audit.
    _, ulps, absolute_delta, relative_delta = _binary64_ieee_equivalent(left, right)
    if left == right:
        return True, 0, 0.0, 0.0
    if not math.isfinite(left) or not math.isfinite(right):
        return False, ulps, absolute_delta, relative_delta
    if left == 0.0 or right == 0.0 or math.copysign(1.0, left) != math.copysign(1.0, right):
        return False, ulps, absolute_delta, relative_delta
    return ulps <= MAX_ULPS and relative_delta <= MAX_RELATIVE_DELTA, ulps, absolute_delta, relative_delta

def _iter_causal(path: Path) -> Iterable[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as handle:
        yield from csv.DictReader(handle)


def _prefixes(data_type: int) -> tuple[str, str, str]:
    """Return value, source-shadow, and ordinary diagnostic prefixes.

    Type-53 numeric shadow fields use ``type53_shadow_`` while its context
    flags and pair counters use ``type53_``.  v46.9.4.1 incorrectly used the
    shadow prefix for both groups, silently converting every flag to zero.
    """
    if data_type == 49:
        return "type49_", "type49_", "type49_"
    return "mg_type53_", "type53_shadow_", "type53_"


def _direction(role: str) -> str:
    if role.startswith("forward"):
        return "forward"
    if role.startswith("reverse"):
        return "reverse"
    return "other"


def _binary64_sequence_fnv1a(values: Iterable[float]) -> int:
    value_hash = _FNV_OFFSET
    for value in values:
        for byte in struct.pack("<d", float(value)):
            value_hash ^= byte
            value_hash = (value_hash * _FNV_PRIME) & _FNV_MASK
    return value_hash


def _read_numeric_lines(path: Path, cast: type[float] | type[int]) -> list[float] | list[int]:
    with path.open() as handle:
        if cast is int:
            return [int(line.strip()) for line in handle if line.strip()]
        return [float(line.strip()) for line in handle if line.strip()]


def _reference_phextrap(
    energy_ryd: list[float], sigma_cm2: list[float], threshold_ev: float, max_points: int
) -> tuple[list[float], list[float]]:
    """Literal frozen v0.6.47.2 phextrap behavior.

    The Python reference appends from the penultimate physical point and uses
    the reduced mapped-grid length (999) as its capacity.  Records already
    longer than that capacity are left unchanged.
    """
    energy = list(energy_ryd)
    sigma = [max(0.0, value) for value in sigma_cm2]
    if len(energy) < 2 or len(energy) != len(sigma):
        return energy, sigma
    base = max(len(energy) - 2, 0)
    e1 = energy[base] * 13.6 + threshold_ev
    s1 = sigma[base]
    while s1 > 1.0e-27 and len(energy) < max_points and e1 < 2.0e5:
        e2 = e1 * 1.3
        s2 = s1 / (1.3 * 1.3 * 1.3)
        energy.append((e2 - threshold_ev) / 13.6)
        sigma.append(s2)
        e1 = e2
        s1 = s2
    return energy, sigma


def _load_type49_grid_reference(case_dir: Path, errors: list[str]) -> dict[int, dict[str, Any]]:
    records_path = case_dir / "records.csv"
    reals_path = case_dir / "reals.txt"
    ints_path = case_dir / "ints.txt"
    if not records_path.exists() or not reals_path.exists() or not ints_path.exists():
        errors.append(f"lowered program missing Type-49 grid inputs: {case_dir}")
        return {}
    reals = _read_numeric_lines(reals_path, float)
    ints = _read_numeric_lines(ints_path, int)
    result: dict[int, dict[str, Any]] = {}
    with records_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("data_type") != "49" or row.get("element_index") != "2":
                continue
            record = int(row["record"])
            real_offset = int(row["real_offset"])
            real_count = int(row["real_count"])
            int_offset = int(row["int_offset"])
            int_count = int(row["int_count"])
            # Production v2 payloads append ten source-context reals.  Retain
            # v1 compatibility for synthetic/older lowered fixtures.
            if real_count >= 14 and (real_count - 10) % 2 == 0:
                pair_real_count = real_count - 10
                context_count = 10
            elif real_count >= 11 and (real_count - 7) % 2 == 0:
                pair_real_count = real_count - 7
                context_count = 7
            else:
                errors.append(f"Type-49 record {record} has invalid real_count={real_count}")
                continue
            payload = reals[real_offset:real_offset + real_count]
            if len(payload) != real_count:
                errors.append(f"Type-49 record {record} real payload truncated")
                continue
            payload_ints = ints[int_offset:int_offset + int_count]
            threshold_ev = payload[pair_real_count + (1 if context_count == 10 else 0)]
            max_points = payload_ints[1] if len(payload_ints) >= 2 else TYPE49_PHEXTRAP_MAX_POINTS
            pair_energy = [payload[index] for index in range(0, pair_real_count, 2)]
            pair_sigma = [max(0.0, payload[index]) for index in range(1, pair_real_count, 2)]
            output_energy, output_sigma = _reference_phextrap(
                pair_energy, pair_sigma, threshold_ev, max_points
            )
            result[record] = {
                "record": record,
                "threshold_ev": threshold_ev,
                "max_points": max_points,
                "input_pair_count": len(pair_energy),
                "output_pair_count": len(output_energy),
                "input_energy_hash": _binary64_sequence_fnv1a(pair_energy),
                "input_sigma_hash": _binary64_sequence_fnv1a(pair_sigma),
                "output_energy_hash": _binary64_sequence_fnv1a(output_energy),
                "output_sigma_hash": _binary64_sequence_fnv1a(output_sigma),
            }
    if len(result) != EXPECTED_UNIQUE_TYPE49:
        errors.append(f"unique Mg Type-49 lowered records={len(result)} expected={EXPECTED_UNIQUE_TYPE49}")
    return result


def analyze(audit_output: Path) -> dict[str, Any]:
    errors: list[str] = []
    diagnostics_dir = audit_output / "native_all61" / "qualification_diagnostics"
    diagnostic_files = sorted(diagnostics_dir.glob("evaluation_*_records.csv"))
    if len(diagnostic_files) != 61:
        errors.append(f"diagnostic_files={len(diagnostic_files)} expected=61")

    grid_reference = _load_type49_grid_reference(audit_output / "native_case_all61", errors)
    type_counts: Counter[int] = Counter()
    source_zero: Counter[int] = Counter()
    context_counts: Counter[str] = Counter()
    invalid_context: Counter[str] = Counter()
    grid_metrics: Counter[str] = Counter()
    grid_divergences: list[dict[str, Any]] = []
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
        "phextrap_output_pair_count", "phextrap_max_points",
        "phextrap_input_energy_hash", "phextrap_input_sigma_hash",
        "phextrap_output_energy_hash", "phextrap_output_sigma_hash",
        "milne_partition_context_used", "excited_threshold_context_used",
        "corrected_threshold_before_mapping", "source_faithful_mode",
        "replacement_applied", "runtime_state_abi_used", "committed_nonfinite",
        "committed_implausible", "legacy_max_abs", "committed_max_abs",
        "continuum_index_one_based", "dsec_radiation_bin_count", "continuum_tau_count",
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
                    value_prefix, shadow_prefix, flag_prefix = _prefixes(dt)
                    values = {
                        "sequence": sequence,
                        "record": _i(row, "record"),
                        "data_type": dt,
                        "ion_index": _i(row, "ion_index"),
                        "ion_stage": _i(row, "ion_stage"),
                        "lower_row": _i(row, "lower_row"),
                        "upper_row": _i(row, "upper_row"),
                        "base_threshold_ev": _f(row, shadow_prefix + "base_threshold_ev"),
                        "corrected_threshold_ev": _f(row, shadow_prefix + "threshold_ev"),
                        "bound_energy_ev": _f(row, shadow_prefix + "bound_energy_ev"),
                        "milne_partition_energy_ev": _f(row, shadow_prefix + "continuum_energy_ev"),
                        "destination_energy_ev": _f(row, shadow_prefix + "destination_energy_ev"),
                        "excited_parent_energy_ev": _f(row, shadow_prefix + "excited_parent_energy_ev"),
                        "bound_g": _f(row, shadow_prefix + "bound_g"),
                        "milne_partition_g": _f(row, shadow_prefix + "continuum_g"),
                        "destination_g": _f(row, shadow_prefix + "destination_g"),
                        "excited_parent_g": _f(row, shadow_prefix + "excited_parent_g"),
                        "rnist": _f(row, shadow_prefix + "rnist"),
                        "exponent_energy_ev": _f(row, value_prefix + "exponent_energy_ev"),
                        "exponent_dimensionless": _f(row, value_prefix + "exponent_dimensionless"),
                        "electron_density_cm3": _f(row, value_prefix + "electron_density_cm3"),
                        "hydrogen_density_cm3": _f(row, value_prefix + "hydrogen_density_cm3"),
                        "matrix_density_scale": _f(row, value_prefix + "matrix_density_scale"),
                        "source_zero_gate": _i(row, "type49_source_zero_gate") if dt == 49 else 0,
                        "phextrap_applied": _i(row, "type49_phextrap_applied") if dt == 49 else 0,
                        "phextrap_source_reference_order": _i(row, flag_prefix + "phextrap_source_reference_order"),
                        "phextrap_input_pair_count": _i(row, flag_prefix + "phextrap_input_pair_count"),
                        "phextrap_output_pair_count": _i(row, flag_prefix + "phextrap_output_pair_count"),
                        "phextrap_max_points": _i(row, "type49_phextrap_max_points") if dt == 49 else 0,
                        "phextrap_input_energy_hash": _u64(row, "type49_phextrap_input_energy_hash") if dt == 49 else 0,
                        "phextrap_input_sigma_hash": _u64(row, "type49_phextrap_input_sigma_hash") if dt == 49 else 0,
                        "phextrap_output_energy_hash": _u64(row, "type49_phextrap_output_energy_hash") if dt == 49 else 0,
                        "phextrap_output_sigma_hash": _u64(row, "type49_phextrap_output_sigma_hash") if dt == 49 else 0,
                        "milne_partition_context_used": _i(row, flag_prefix + "milne_partition_context_used"),
                        "excited_threshold_context_used": _i(row, flag_prefix + "excited_threshold_context_used"),
                        "corrected_threshold_before_mapping": _i(row, flag_prefix + "corrected_threshold_before_mapping"),
                        "source_faithful_mode": _i(row, "type49_source_faithful_mode" if dt == 49 else "mg_type53_source_faithful_mode"),
                        "replacement_applied": _i(row, value_prefix + "replacement_applied"),
                        "runtime_state_abi_used": _i(row, "type49_runtime_state_abi_used" if dt == 49 else "type53_runtime_state_abi_used"),
                        "committed_nonfinite": _i(row, value_prefix + "committed_nonfinite"),
                        "committed_implausible": _i(row, value_prefix + "committed_implausible"),
                        "legacy_max_abs": _f(row, value_prefix + "legacy_max_abs"),
                        "committed_max_abs": _f(row, value_prefix + "committed_max_abs"),
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

                    if dt == 49:
                        expected = grid_reference.get(int(values["record"]))
                        if expected is None:
                            invalid_context["type49_grid_reference_missing"] += 1
                        else:
                            source_zero_gate = bool(values["source_zero_gate"])
                            expected_output_count = 0 if source_zero_gate else expected["output_pair_count"]
                            expected_output_energy_hash = _binary64_sequence_fnv1a(()) if source_zero_gate else expected["output_energy_hash"]
                            expected_output_sigma_hash = _binary64_sequence_fnv1a(()) if source_zero_gate else expected["output_sigma_hash"]
                            checks = {
                                "max_points": values["phextrap_max_points"] == expected["max_points"] == TYPE49_PHEXTRAP_MAX_POINTS,
                                "input_pair_count": values["phextrap_input_pair_count"] == expected["input_pair_count"],
                                "input_energy_hash": values["phextrap_input_energy_hash"] == expected["input_energy_hash"],
                                "input_sigma_hash": values["phextrap_input_sigma_hash"] == expected["input_sigma_hash"],
                                "output_pair_count": values["phextrap_output_pair_count"] == expected_output_count,
                                "output_energy_hash": values["phextrap_output_energy_hash"] == expected_output_energy_hash,
                                "output_sigma_hash": values["phextrap_output_sigma_hash"] == expected_output_sigma_hash,
                            }
                            for check, exact in checks.items():
                                grid_metrics[f"{check}_exact"] += int(exact)
                            if not all(checks.values()):
                                grid_metrics["divergent_record_evaluations"] += 1
                                grid_divergences.append({
                                    "sequence": sequence,
                                    "record": values["record"],
                                    "source_zero_gate": int(source_zero_gate),
                                    "expected_max_points": expected["max_points"],
                                    "native_max_points": values["phextrap_max_points"],
                                    "expected_input_pair_count": expected["input_pair_count"],
                                    "native_input_pair_count": values["phextrap_input_pair_count"],
                                    "expected_output_pair_count": expected_output_count,
                                    "native_output_pair_count": values["phextrap_output_pair_count"],
                                    "expected_input_energy_hash": expected["input_energy_hash"],
                                    "native_input_energy_hash": values["phextrap_input_energy_hash"],
                                    "expected_input_sigma_hash": expected["input_sigma_hash"],
                                    "native_input_sigma_hash": values["phextrap_input_sigma_hash"],
                                    "expected_output_energy_hash": expected_output_energy_hash,
                                    "native_output_energy_hash": values["phextrap_output_energy_hash"],
                                    "expected_output_sigma_hash": expected_output_sigma_hash,
                                    "native_output_sigma_hash": values["phextrap_output_sigma_hash"],
                                    "failed_checks": ";".join(key for key, exact in checks.items() if not exact),
                                })
                    max_legacy = max(max_legacy, values["legacy_max_abs"] if math.isfinite(values["legacy_max_abs"]) else 0.0)
                    max_committed = max(max_committed, values["committed_max_abs"] if math.isfinite(values["committed_max_abs"]) else 0.0)

    grid_csv = audit_output / "all61_mg_type49_phextrap_grid_parity.csv"
    grid_fields = [
        "sequence", "record", "source_zero_gate", "expected_max_points", "native_max_points",
        "expected_input_pair_count", "native_input_pair_count", "expected_output_pair_count",
        "native_output_pair_count", "expected_input_energy_hash", "native_input_energy_hash",
        "expected_input_sigma_hash", "native_input_sigma_hash", "expected_output_energy_hash",
        "native_output_energy_hash", "expected_output_sigma_hash", "native_output_sigma_hash",
        "failed_checks",
    ]
    with grid_csv.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=grid_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(grid_divergences)

    causal_path = audit_output / "all61_dense_matrix_causal_records.csv.gz"
    if not causal_path.exists():
        fallback = audit_output / "all61_dense_matrix_causal_records.csv"
        causal_path = fallback if fallback.exists() else causal_path
    unexplained: list[dict[str, Any]] = []
    ieee_rows: list[dict[str, Any]] = []
    unexplained_by_type: Counter[int] = Counter()
    ieee_by_type: Counter[int] = Counter()
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
                accepted, ulps, absolute, relative = _mg_binary64_ieee_equivalent(source_value, native_value)
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
                ieee_by_type[dt] += 1
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
        writer.writeheader()
        writer.writerows(ieee_rows)
        writer.writerows(unexplained)

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
    if context_counts["53:excited_threshold_context_used"] != context_counts["53:excited_parent_records"]:
        errors.append("Type-53 excited-threshold context inventory mismatch")
    if context_counts["49:committed_nonfinite"] or context_counts["53:committed_nonfinite"]:
        errors.append("committed nonfinite Mg bound-free values")
    if context_counts["49:committed_implausible"] or context_counts["53:committed_implausible"]:
        errors.append("committed implausible Mg bound-free values")
    if grid_metrics["divergent_record_evaluations"]:
        errors.append(f"Type-49 extrapolated-grid divergent record evaluations={grid_metrics['divergent_record_evaluations']}")
    if invalid_context:
        errors.append("invalid source context: " + json.dumps(dict(invalid_context), sort_keys=True))
    if unexplained:
        errors.append(f"unexplained Mg Type-49/53 causal rows={len(unexplained)}")

    all_type49_grid_exact = (
        type_counts[49] == EXPECTED[49]
        and grid_metrics["max_points_exact"] == EXPECTED[49]
        and grid_metrics["input_pair_count_exact"] == EXPECTED[49]
        and grid_metrics["input_energy_hash_exact"] == EXPECTED[49]
        and grid_metrics["input_sigma_hash_exact"] == EXPECTED[49]
        and grid_metrics["output_pair_count_exact"] == EXPECTED[49]
        and grid_metrics["output_energy_hash_exact"] == EXPECTED[49]
        and grid_metrics["output_sigma_hash_exact"] == EXPECTED[49]
        and grid_metrics["divergent_record_evaluations"] == 0
    )
    gates = {
        "MG_TYPE49_FORWARD_UNEXPLAINED_ROWS_ZERO": "ACCEPT" if unexplained_by_type_direction["49:forward"] == 0 else "REJECT",
        "MG_TYPE49_REVERSE_UNEXPLAINED_ROWS_ZERO": "ACCEPT" if unexplained_by_type_direction["49:reverse"] == 0 else "REJECT",
        "MG_TYPE53_FORWARD_UNEXPLAINED_ROWS_ZERO": "ACCEPT" if unexplained_by_type_direction["53:forward"] == 0 else "REJECT",
        "MG_TYPE53_REVERSE_UNEXPLAINED_ROWS_ZERO": "ACCEPT" if unexplained_by_type_direction["53:reverse"] == 0 else "REJECT",
        "MG_TYPE49_PHEXTRAP_SOURCE_ORDER_EXACT": "ACCEPT" if not invalid_context.get("type49_phextrap_source_order") else "REJECT",
        "MG_TYPE49_PHEXTRAP_MAX_POINTS_EXACT": "ACCEPT" if grid_metrics["max_points_exact"] == EXPECTED[49] else "REJECT",
        "MG_TYPE49_PHEXTRAP_INPUT_HASH_EXACT": "ACCEPT" if grid_metrics["input_energy_hash_exact"] == grid_metrics["input_sigma_hash_exact"] == EXPECTED[49] else "REJECT",
        "MG_TYPE49_PHEXTRAP_OUTPUT_HASH_EXACT": "ACCEPT" if grid_metrics["output_energy_hash_exact"] == grid_metrics["output_sigma_hash_exact"] == EXPECTED[49] else "REJECT",
        "MG_TYPE49_FIRST_DIVERGENT_GRID_POINT_COUNT_ZERO": "ACCEPT" if grid_metrics["divergent_record_evaluations"] == 0 else "REJECT",
        "MG_TYPE49_EXTRAPOLATED_GRID_PARITY": "ACCEPT" if all_type49_grid_exact else "REJECT",
        "MG_MILNE_PARTITION_WEIGHT_CONTEXT_EXACT": "ACCEPT" if not invalid_context.get("milne_partition_context_not_used") and not invalid_context.get("nonpositive_statistical_weight") else "REJECT",
        "MG_TYPE53_EXCITED_THRESHOLD_CONTEXT_EXACT": "ACCEPT" if not invalid_context.get("type53_excited_threshold_not_used") and not invalid_context.get("type53_corrected_threshold_relation") else "REJECT",
        "MG_TYPE53_CORRECTED_THRESHOLD_USED_BEFORE_NBINC": "ACCEPT" if not invalid_context.get("type53_corrected_threshold_not_before_mapping") else "REJECT",
        "MG_TYPE53_AUDIT_PREFIX_CORRECT": "ACCEPT" if context_counts["53:milne_partition_context_used"] == EXPECTED[53] else "REJECT",
        "MG_BOUND_FREE_UNEXPLAINED_RATE_DELTAS_ZERO": "ACCEPT" if not unexplained else "REJECT",
        "MG_BOUND_FREE_IEEE_ROUNDOFF_ENVELOPE": "ACCEPT" if max_ulps <= MAX_ULPS and max_relative <= MAX_RELATIVE_DELTA else "REJECT",
        "MG_BOUND_FREE_SOURCE_CONTEXT_COMPLETE": "ACCEPT" if not invalid_context else "REJECT",
        "MG_BOUND_FREE_SOURCE_ZERO_GATE_EXACT": "ACCEPT" if not invalid_context.get("source_zero_nonzero_commit") and not invalid_context.get("source_zero_nonzero_shadow") else "REJECT",
        "MG_BOUND_FREE_COMMITTED_NONFINITE_ZERO": "ACCEPT" if context_counts["49:committed_nonfinite"] + context_counts["53:committed_nonfinite"] == 0 else "REJECT",
        "MG_BOUND_FREE_COMMITTED_IMPLAUSIBLE_ZERO": "ACCEPT" if context_counts["49:committed_implausible"] + context_counts["53:committed_implausible"] == 0 else "REJECT",
        "MG_TYPE50_ORIENTATION_CORRECTION": "DEFERRED",
    }
    accepted = not errors
    return {
        "schema": "xstar-tools-v0648746942-type53-audit-type49-grid-parity-v1",
        "release": RELEASE,
        "result": "ACCEPT" if accepted else "REJECT",
        "errors": errors,
        "record_counts": {str(k): v for k, v in sorted(type_counts.items())},
        "source_zero_counts": {str(k): v for k, v in sorted(source_zero.items())},
        "context_metrics": dict(context_counts),
        "invalid_context": dict(invalid_context),
        "type49_grid_metrics": dict(grid_metrics),
        "type49_unique_grid_references": len(grid_reference),
        "type49_grid_divergent_record_evaluations": len(grid_divergences),
        "residual_classification_counts": dict(classification_counts),
        "ieee_equivalent_rows": len(ieee_rows),
        "ieee_equivalent_by_type": {str(k): v for k, v in sorted(ieee_by_type.items())},
        "ieee_limits": {"max_ulps": MAX_ULPS, "max_relative_delta": MAX_RELATIVE_DELTA, "nonzero_absolute_tolerance": 0.0},
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
        "type49_grid_output_csv": grid_csv.name,
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
