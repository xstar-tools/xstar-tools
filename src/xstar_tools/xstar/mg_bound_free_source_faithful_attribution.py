#!/usr/bin/env python3
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

RELEASE = "0.6.48.7.46.18.1"
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


def _diagnostic_prefix(data_type: int) -> tuple[str, str]:
    if data_type == 49:
        return "type49_", "type49_"
    return "mg_type53_", "type53_shadow_"


def analyze(audit_output: Path) -> dict[str, Any]:
    errors: list[str] = []
    diagnostics_dir = audit_output / "native_all61" / "qualification_diagnostics"
    diagnostic_files = sorted(diagnostics_dir.glob("evaluation_*_records.csv"))
    if len(diagnostic_files) != 61:
        errors.append(f"diagnostic_files={len(diagnostic_files)} expected=61")

    context_counts: Counter[str] = Counter()
    type_counts: Counter[int] = Counter()
    source_zero_by_type: Counter[int] = Counter()
    phextrap_by_type: Counter[int] = Counter()
    invalid_context: Counter[str] = Counter()
    max_committed = 0.0
    max_legacy = 0.0

    context_csv = audit_output / "all61_mg_type49_type53_source_faithful_context.csv"
    context_fields = [
        "sequence", "record", "data_type", "ion_index", "ion_stage",
        "lower_row", "upper_row", "threshold_ev", "bound_energy_ev",
        "continuum_energy_ev", "destination_energy_ev", "bound_g",
        "continuum_g", "destination_g", "rnist", "exponent_energy_ev",
        "exponent_dimensionless", "electron_density_cm3",
        "hydrogen_density_cm3", "matrix_density_scale", "source_zero_gate",
        "phextrap_applied", "source_faithful_mode", "replacement_applied",
        "runtime_state_abi_used", "committed_nonfinite",
        "committed_implausible", "legacy_max_abs", "committed_max_abs",
        "continuum_index_one_based", "dsec_radiation_bin_count",
        "continuum_tau_count",
    ]
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
                    data_type = int(row["data_type"])
                    prefix, context_prefix = _diagnostic_prefix(data_type)
                    source_zero = _i(row, "type49_source_zero_gate") if data_type == 49 else 0
                    values = {
                        "sequence": sequence,
                        "record": _i(row, "record"),
                        "data_type": data_type,
                        "ion_index": _i(row, "ion_index"),
                        "ion_stage": _i(row, "ion_stage"),
                        "lower_row": _i(row, "lower_row"),
                        "upper_row": _i(row, "upper_row"),
                        "threshold_ev": _f(row, context_prefix + "threshold_ev"),
                        "bound_energy_ev": _f(row, context_prefix + "bound_energy_ev"),
                        "continuum_energy_ev": _f(row, context_prefix + "continuum_energy_ev"),
                        "destination_energy_ev": _f(row, context_prefix + "destination_energy_ev"),
                        "bound_g": _f(row, context_prefix + "bound_g"),
                        "continuum_g": _f(row, context_prefix + "continuum_g"),
                        "destination_g": _f(row, context_prefix + "destination_g"),
                        "rnist": _f(row, context_prefix + "rnist"),
                        "exponent_energy_ev": _f(row, prefix + "exponent_energy_ev"),
                        "exponent_dimensionless": _f(row, prefix + "exponent_dimensionless"),
                        "electron_density_cm3": _f(row, prefix + "electron_density_cm3"),
                        "hydrogen_density_cm3": _f(row, prefix + "hydrogen_density_cm3"),
                        "matrix_density_scale": _f(row, prefix + "matrix_density_scale"),
                        "source_zero_gate": source_zero,
                        "phextrap_applied": _i(row, "type49_phextrap_applied") if data_type == 49 else 0,
                        "source_faithful_mode": _i(row, "type49_source_faithful_mode" if data_type == 49 else "mg_type53_source_faithful_mode"),
                        "replacement_applied": _i(row, prefix + "replacement_applied"),
                        "runtime_state_abi_used": _i(row, "type49_runtime_state_abi_used" if data_type == 49 else "type53_runtime_state_abi_used"),
                        "committed_nonfinite": _i(row, prefix + "committed_nonfinite"),
                        "committed_implausible": _i(row, prefix + "committed_implausible"),
                        "legacy_max_abs": _f(row, prefix + "legacy_max_abs"),
                        "committed_max_abs": _f(row, prefix + "committed_max_abs"),
                        "continuum_index_one_based": _i(row, "type49_continuum_index_one_based" if data_type == 49 else "type53_continuum_index_one_based"),
                        "dsec_radiation_bin_count": _i(row, "type49_dsec_radiation_bin_count" if data_type == 49 else "type53_dsec_radiation_bin_count"),
                        "continuum_tau_count": _i(row, "type49_continuum_tau_count" if data_type == 49 else "type53_continuum_tau_count"),
                    }
                    writer.writerow(values)
                    type_counts[data_type] += 1
                    source_zero_by_type[data_type] += source_zero
                    phextrap_by_type[data_type] += int(values["phextrap_applied"])
                    for key in (
                        "source_faithful_mode", "replacement_applied",
                        "runtime_state_abi_used", "committed_nonfinite",
                        "committed_implausible",
                    ):
                        context_counts[key] += int(values[key])
                    for key in (
                        "threshold_ev", "bound_energy_ev", "continuum_energy_ev",
                        "destination_energy_ev", "bound_g", "continuum_g",
                        "destination_g", "rnist", "exponent_energy_ev",
                        "exponent_dimensionless", "electron_density_cm3",
                        "hydrogen_density_cm3", "matrix_density_scale",
                        "legacy_max_abs", "committed_max_abs",
                    ):
                        if not math.isfinite(float(values[key])):
                            invalid_context[key] += 1
                    if values["bound_g"] <= 0 or values["continuum_g"] <= 0 or values["destination_g"] <= 0:
                        invalid_context["nonpositive_statistical_weight"] += 1
                    if values["continuum_index_one_based"] <= 0:
                        invalid_context["missing_continuum_index"] += 1
                    if values["dsec_radiation_bin_count"] != 9999:
                        invalid_context["radiation_bin_count"] += 1
                    if values["continuum_tau_count"] != 301301:
                        invalid_context["continuum_tau_count"] += 1
                    if data_type == 49 and source_zero:
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
    residual_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    type_residual_counts: Counter[int] = Counter()
    ieee_rows: list[dict[str, Any]] = []
    unexplained_rows: list[dict[str, Any]] = []
    unexplained_by_type: Counter[int] = Counter()
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
            data_type = int(row["data_type"])
            role = row.get("role", "")
            residual_counts[classification] += 1
            role_counts[f"{data_type}:{role}"] += 1
            type_residual_counts[data_type] += 1
            accepted = False
            ulps = 0
            absolute = float("inf")
            relative = float("inf")
            if classification == "RATE_VALUE_DELTA" and row.get("source_present") == "1" and row.get("native_present") == "1":
                source_value = float(row["source_value"])
                native_value = float(row["native_value"])
                accepted, ulps, absolute, relative = _binary64_ieee_equivalent(source_value, native_value)
                accepted = accepted and ulps <= MAX_ULPS and relative <= MAX_RELATIVE_DELTA
            output_row = {
                "sequence": _i(row, "sequence"),
                "record": _i(row, "record"),
                "data_type": data_type,
                "ion_stage": _i(row, "ion_stage"),
                "role": role,
                "classification": classification,
                "source_value": row.get("source_value", ""),
                "native_value": row.get("native_value", ""),
                "delta": row.get("delta", ""),
                "ulp_distance": ulps,
                "absolute_delta": absolute,
                "relative_delta": relative,
            }
            if accepted:
                ieee_rows.append(output_row)
                max_ulps = max(max_ulps, ulps)
                max_absolute = max(max_absolute, absolute)
                max_relative = max(max_relative, relative)
            else:
                unexplained_rows.append(output_row)
                unexplained_by_type[data_type] += 1

    residual_csv = audit_output / "all61_mg_type49_type53_source_faithful_residuals.csv"
    residual_fields = [
        "sequence", "record", "data_type", "ion_stage", "role",
        "classification", "source_value", "native_value", "delta",
        "ulp_distance", "absolute_delta", "relative_delta",
    ]
    with residual_csv.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=residual_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(ieee_rows)
        writer.writerows(unexplained_rows)

    total_expected = sum(EXPECTED.values())
    for data_type, expected in EXPECTED.items():
        if type_counts[data_type] != expected:
            errors.append(f"Mg Type-{data_type} records={type_counts[data_type]} expected={expected}")
    if context_counts["source_faithful_mode"] != total_expected:
        errors.append(f"source_faithful_mode={context_counts['source_faithful_mode']} expected={total_expected}")
    if context_counts["replacement_applied"] != total_expected:
        errors.append(f"replacement_applied={context_counts['replacement_applied']} expected={total_expected}")
    if context_counts["runtime_state_abi_used"] != total_expected:
        errors.append(f"runtime_state_abi_used={context_counts['runtime_state_abi_used']} expected={total_expected}")
    if context_counts["committed_nonfinite"]:
        errors.append(f"committed_nonfinite={context_counts['committed_nonfinite']}")
    if context_counts["committed_implausible"]:
        errors.append(f"committed_implausible={context_counts['committed_implausible']}")
    expected_phextrap = EXPECTED[49] - source_zero_by_type[49]
    if phextrap_by_type[49] != expected_phextrap:
        errors.append(f"type49_phextrap_applied={phextrap_by_type[49]} expected={expected_phextrap}")
    if invalid_context:
        errors.append("invalid source context: " + json.dumps(dict(invalid_context), sort_keys=True))
    if unexplained_rows:
        errors.append(f"unexplained Mg Type-49/53 causal rows={len(unexplained_rows)}")

    accepted = not errors
    gates = {
        "MG_TYPE49_SOURCE_FAITHFUL_RESIDUAL_CLOSURE": "ACCEPT" if unexplained_by_type[49] == 0 else "REJECT",
        "MG_TYPE53_SOURCE_FAITHFUL_RESIDUAL_CLOSURE": "ACCEPT" if unexplained_by_type[53] == 0 else "REJECT",
        "MG_BOUND_FREE_UNEXPLAINED_RATE_DELTAS_ZERO": "ACCEPT" if not unexplained_rows else "REJECT",
        "MG_BOUND_FREE_SOURCE_CONTEXT_COMPLETE": "ACCEPT" if not invalid_context else "REJECT",
        "MG_BOUND_FREE_SOURCE_ZERO_GATE_EXACT": "ACCEPT" if not invalid_context.get("source_zero_nonzero_commit") and not invalid_context.get("source_zero_nonzero_shadow") else "REJECT",
        "MG_BOUND_FREE_COMMITTED_NONFINITE_ZERO": "ACCEPT" if context_counts["committed_nonfinite"] == 0 else "REJECT",
        "MG_BOUND_FREE_COMMITTED_IMPLAUSIBLE_ZERO": "ACCEPT" if context_counts["committed_implausible"] == 0 else "REJECT",
        "MG_TYPE50_ORIENTATION_CORRECTION": "DEFERRED",
    }
    return {
        "schema": "xstar-tools-v064874694-mg-bound-free-source-faithful-v1",
        "release": RELEASE,
        "result": "ACCEPT" if accepted else "REJECT",
        "errors": errors,
        "record_counts": {str(k): v for k, v in sorted(type_counts.items())},
        "source_zero_counts": {str(k): v for k, v in sorted(source_zero_by_type.items())},
        "phextrap_counts": {str(k): v for k, v in sorted(phextrap_by_type.items())},
        "context_metrics": dict(context_counts),
        "invalid_context": dict(invalid_context),
        "residual_classification_counts": dict(residual_counts),
        "residual_role_counts": dict(role_counts),
        "residual_data_type_counts": {str(k): v for k, v in sorted(type_residual_counts.items())},
        "ieee_equivalent_rows": len(ieee_rows),
        "unexplained_rows": len(unexplained_rows),
        "unexplained_by_type": {str(k): v for k, v in sorted(unexplained_by_type.items())},
        "max_ulp_distance": max_ulps,
        "max_absolute_delta": max_absolute,
        "max_relative_delta": max_relative,
        "max_legacy_abs": max_legacy,
        "max_committed_abs": max_committed,
        "context_output_csv": context_csv.name,
        "residual_output_csv": residual_csv.name,
        "gates": gates,
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
