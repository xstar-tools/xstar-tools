"""Audit v46.21 independent source-faithful Thermal parity."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .all61_native_replay_aggregate import THERMAL_LEDGER_NAME, THERMAL_DIAGONAL_LEDGER_NAME
from .v0472_all61_magnesium_primary_cooling_source_order_capture import LEDGER_NAME as MG_SOURCE_LEDGER_NAME
from .v0472_all61_independent_thermal_capture_v048746211 import ANSWER_LEDGER_NAME

RELEASE = "0.6.48.7.46.21.1"
SCHEMA = "xstar-tools-v0648746211-independent-thermal-parity-audit-v1"
ANSWER_COMPARISON_NAME = "v048746211_thermal_answer_channel_comparison.csv"
COMPONENT_SUMMARY_NAME = "v048746211_independent_component_summary.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["empty"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _exact(left: Any, right: Any) -> bool:
    try:
        a = float(left); b = float(right)
        return math.isfinite(a) and math.isfinite(b) and struct.pack(">d", a) == struct.pack(">d", b)
    except Exception:
        return False


def _native_record_rows(native_run: Path) -> list[dict[str, str]]:
    roots = [native_run / "qualification_diagnostics", native_run.parent / "qualification_diagnostics"]
    rows: list[dict[str, str]] = []
    for sequence in range(1, 62):
        candidates = [root / f"evaluation_{sequence:04d}_records.csv" for root in roots]
        candidates.extend([
            native_run / "evaluations" / f"evaluation_{sequence:04d}" / "native_records.csv",
            native_run / "evaluations" / f"evaluation_{sequence:04d}" / f"evaluation_{sequence:04d}_records.csv",
        ])
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            raise FileNotFoundError(candidates[0])
        for row in _read_csv(path):
            if int(row.get("element_z", "0")) not in (1, 2, 12):
                continue
            item = dict(row); item["sequence"] = str(sequence); rows.append(item)
    return rows


def audit(source_capture: Path, native_run: Path, component_comparison: Path, output: Path) -> dict[str, Any]:
    errors: list[str] = []
    gates: dict[str, str] = {}
    source_answers = _read_csv(source_capture / ANSWER_LEDGER_NAME)
    native_answers = _native_record_rows(native_run)
    source_mg_rows = _read_csv(source_capture / MG_SOURCE_LEDGER_NAME)
    native_diagonal_rows = _read_csv(native_run / THERMAL_DIAGONAL_LEDGER_NAME)
    components = _read_csv(component_comparison)
    thermal_rows = _read_csv(native_run / THERMAL_LEDGER_NAME)
    native_summary = json.loads((native_run / "native_dsec_summary.json").read_text())

    def key(row: dict[str, str]) -> tuple[int, int, int]:
        return int(row["sequence"]), int(row["element_z"]), int(row["record"])

    source: dict[tuple[int, int, int], dict[str, str]] = {}
    for row in source_answers:
        k = key(row)
        if k in source:
            errors.append(f"duplicate_source_answer_key:{k}")
        source[k] = row
    native: dict[tuple[int, int, int], dict[str, str]] = {}
    for row in native_answers:
        k = key(row)
        # The source runtime domain is authoritative.  Static native-only rows
        # are classified below rather than allowed to fail source completeness.
        if k in native:
            errors.append(f"duplicate_native_answer_key:{k}")
        native[k] = row

    source_missing_native = sorted(set(source) - set(native))
    native_only = sorted(set(native) - set(source))
    if source_missing_native:
        errors.append(f"source_rows_missing_native:{len(source_missing_native)}")
    comparison_rows: list[dict[str, Any]] = []
    field_exact = Counter()
    field_total = Counter()
    element_field_exact: dict[int, Counter[str]] = defaultdict(Counter)
    element_field_total: dict[int, Counter[str]] = defaultdict(Counter)
    all_exact_rows = 0
    for k in sorted(source):
        src = source[k]; nat = native.get(k)
        row: dict[str, Any] = {
            "sequence": k[0], "element_z": k[1], "record": k[2],
            "native_present": int(nat is not None),
            "source_data_type": src.get("data_type", ""),
            "source_rate_type": src.get("rate_type", ""),
        }
        row_exact = nat is not None
        if nat is not None:
            row["native_data_type"] = nat.get("data_type", "")
            row["native_rate_type"] = nat.get("rate_type", "")
            metadata_exact = (
                int(src.get("data_type", "0")) == int(nat.get("data_type", "0")) and
                int(src.get("rate_type", "0")) == int(nat.get("rate_type", "0"))
            )
            row["metadata_exact"] = int(metadata_exact); row_exact &= metadata_exact
            for field in ("ans3", "ans4", "ans5", "ans6"):
                exact = _exact(src[field], nat[field])
                field_total[field] += 1; field_exact[field] += int(exact)
                element_field_total[k[1]][field] += 1
                element_field_exact[k[1]][field] += int(exact)
                row[f"source_{field}"] = src[field]; row[f"native_{field}"] = nat[field]
                row[f"{field}_exact"] = int(exact); row_exact &= exact
        row["all_fields_exact"] = int(row_exact)
        all_exact_rows += int(row_exact)
        comparison_rows.append(row)
    _write_csv(output / ANSWER_COMPARISON_NAME, comparison_rows)

    answer_values_total = sum(field_total.values())
    answer_values_exact = sum(field_exact.values())
    gates["THERMAL_ANSWER_SOURCE_ROWS_COVERED"] = "ACCEPT" if source and not source_missing_native else "REJECT"
    gates["THERMAL_ANSWER_ANS3_ANS6_ALL_EXACT"] = "ACCEPT" if answer_values_total and answer_values_exact == answer_values_total else "REJECT"
    gates["HYDROGEN_SECONDARY_CHANNELS_EXACT"] = "ACCEPT" if all(
        element_field_exact[1][field] == element_field_total[1][field] > 0 for field in ("ans5", "ans6")
    ) else "REJECT"
    gates["MAGNESIUM_SECONDARY_CHANNELS_EXACT"] = "ACCEPT" if all(
        element_field_exact[12][field] == element_field_total[12][field] > 0 for field in ("ans5", "ans6")
    ) else "REJECT"
    gates["HELIUM_ANSWER_CHANNELS_EXACT"] = "ACCEPT" if all(
        element_field_exact[2][field] == element_field_total[2][field] > 0 for field in ("ans3", "ans4", "ans5", "ans6")
    ) else "REJECT"

    # Magnesium source-order arithmetic: compare unweighted products and
    # apply abundance only after the complete ordered sum.
    def mg_key(row: dict[str, str]) -> tuple[int, int, str]:
        return int(row["sequence"]), int(row["record"]), row["role"]
    source_mg = {mg_key(row): row for row in source_mg_rows}
    native_mg = {
        mg_key(row): row for row in native_diagonal_rows
        if int(row.get("element_z", "0")) == 12
        and float(row.get("cj", "0")) > 0.0
        and row.get("magnesium_primary_cooling_source_order_applied") == "1"
    }
    mg_keys_exact = bool(source_mg) and set(source_mg) == set(native_mg)
    mg_product_exact = 0
    mg_order_exact = 0
    for k, src in source_mg.items():
        nat = native_mg.get(k)
        if nat is None: continue
        source_product = float(src["compact_population"]) * float(src["cj"])
        native_product = nat.get("unweighted_cooling_contribution", "nan")
        mg_product_exact += int(_exact(source_product, native_product))
        mg_order_exact += int(int(src["source_order_index"]) == int(nat.get("magnesium_primary_cooling_source_order_index", "0")))
    source_mg_by_sequence: dict[int, list[dict[str, str]]] = defaultdict(list)
    native_mg_by_sequence: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in source_mg.values(): source_mg_by_sequence[int(row["sequence"])].append(row)
    for row in native_mg.values(): native_mg_by_sequence[int(row["sequence"])].append(row)
    mg_reduced_exact = 0
    for sequence in range(1, 62):
        src_rows = sorted(source_mg_by_sequence[sequence], key=lambda row: int(row["source_order_index"]))
        nat_rows = sorted(native_mg_by_sequence[sequence], key=lambda row: int(row["magnesium_primary_cooling_source_order_index"]))
        if not src_rows or len(src_rows) != len(nat_rows): continue
        source_unweighted = 0.0
        native_unweighted = 0.0
        for row in src_rows: source_unweighted += float(row["compact_population"]) * float(row["cj"])
        for row in nat_rows: native_unweighted += float(row["unweighted_cooling_contribution"])
        abundance = float(src_rows[0]["abundance"])
        source_total = source_unweighted * abundance
        native_total = native_unweighted * abundance
        source_component = next((row.get("source_value", "nan") for row in components if int(row.get("sequence", "0")) == sequence and row.get("component") == "mg_cooling"), "nan")
        if _exact(source_unweighted, native_unweighted) and _exact(source_total, native_total) and _exact(native_total, source_component):
            mg_reduced_exact += 1
    gates["MAGNESIUM_PRIMARY_COOLING_SOURCE_KEYS_EXACT"] = "ACCEPT" if mg_keys_exact else "REJECT"
    gates["MAGNESIUM_PRIMARY_COOLING_UNWEIGHTED_PRODUCTS_EXACT"] = "ACCEPT" if source_mg and mg_product_exact == len(source_mg) else "REJECT"
    gates["MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_INDICES_EXACT"] = "ACCEPT" if source_mg and mg_order_exact == len(source_mg) else "REJECT"
    gates["MAGNESIUM_PRIMARY_COOLING_ABUNDANCE_AFTER_SUM_ALL61"] = "ACCEPT" if mg_reduced_exact == 61 else "REJECT"

    component_counts: dict[str, tuple[int, int]] = {}
    component_summary: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in components: grouped[row.get("component", "")].append(row)
    for name, rows in sorted(grouped.items()):
        exact = sum(int(row.get("computed_exact", "0")) for row in rows)
        component_counts[name] = (exact, len(rows))
        component_summary.append({"component": name, "exact": exact, "total": len(rows)})
    _write_csv(output / COMPONENT_SUMMARY_NAME, component_summary)
    computed_exact = sum(int(row.get("computed_exact", "0")) for row in components)
    gates["NATIVE_COMPUTED_THERMAL_VALUES_EXACT_2440"] = "ACCEPT" if computed_exact == len(components) == 2440 else "REJECT"

    def component_gate(names: tuple[str, ...]) -> bool:
        return all(component_counts.get(name) == (61, 61) for name in names)
    gates["MAGNESIUM_COOLING_ALL61_EXACT"] = "ACCEPT" if component_gate(("mg_cooling",)) else "REJECT"
    gates["UNIFIED_HELIUM_ATTRIBUTION_ALL61_EXACT"] = "ACCEPT" if component_gate((
        "he_heating", "he_cooling", "he_heating2", "he_cooling2",
        "he_type53_heating", "he_type53_cooling", "he_type53_heating2", "he_type53_cooling2",
        "he_non_type53_heating", "he_non_type53_cooling", "he_non_type53_heating2", "he_non_type53_cooling2",
    )) else "REJECT"
    gates["SOURCE_ORDER_GLOBAL_TOTALS_ALL61_EXACT"] = "ACCEPT" if component_gate((
        "element_heating", "element_cooling", "element_heating2", "element_cooling2",
        "httot", "cltot", "httot2", "cltot2", "hmctot",
    )) else "REJECT"
    gates["ELCTER_CHARGE_RESIDUAL_ALL61_EXACT"] = "ACCEPT" if component_gate(("elcter",)) else "REJECT"

    independent_rows = sum(row.get("independent_thermal_parity") == "1" for row in thermal_rows)
    source_scalar_rows = sum(row.get("source_scalar_override_used") == "1" for row in thermal_rows)
    fixed_closure_rows = sum(row.get("thermal_consumed_fixed_state_closure") == "1" for row in thermal_rows)
    compact_closure_rows = sum(row.get("thermal_consumed_compact_population_closure") == "1" for row in thermal_rows)
    component_closure_rows = sum(row.get("thermal_component_closure_applied") == "1" for row in thermal_rows)
    gates["INDEPENDENT_THERMAL_MODE_ALL61"] = "ACCEPT" if independent_rows == len(thermal_rows) == 61 else "REJECT"
    gates["SOURCE_SCALAR_OVERRIDE_USED_ZERO"] = "ACCEPT" if source_scalar_rows == 0 and len(thermal_rows) == 61 else "REJECT"
    gates["FIXED_STATE_SCALAR_CLOSURE_USED_ZERO"] = "ACCEPT" if fixed_closure_rows == 0 and len(thermal_rows) == 61 else "REJECT"
    gates["THERMAL_COMPONENT_CLOSURE_USED_ZERO"] = "ACCEPT" if component_closure_rows == 0 and len(thermal_rows) == 61 else "REJECT"
    gates["THERMAL_COMPACT_POPULATION_CLOSURE_USED_ZERO"] = "ACCEPT" if compact_closure_rows == 0 and len(thermal_rows) == 61 else "REJECT"
    gates["PYTHON_CALLBACKS_ZERO"] = "ACCEPT" if int(native_summary.get("python_callbacks", -1)) == 0 else "REJECT"
    gates["ALL_61_EVALUATIONS"] = "ACCEPT" if int(native_summary.get("total_evaluations", 0)) == 61 else "REJECT"
    gates["PRODUCTION_PROMOTION_BLOCKED"] = "ACCEPT"

    result = "ACCEPT" if not errors and all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    return {
        "schema": SCHEMA, "release": RELEASE, "result": result, "scientific_result": result,
        "gates": gates, "errors": errors + [name for name, value in gates.items() if value != "ACCEPT"],
        "source_answer_rows": len(source), "native_answer_rows": len(native),
        "native_only_answer_rows": len(native_only), "source_rows_missing_native": len(source_missing_native),
        "answer_rows_all_exact": all_exact_rows, "answer_values_exact": answer_values_exact,
        "answer_values_total": answer_values_total,
        "answer_field_counts": {field: {"exact": field_exact[field], "total": field_total[field]} for field in ("ans3", "ans4", "ans5", "ans6")},
        "answer_element_field_counts": {
            str(z): {field: {"exact": element_field_exact[z][field], "total": element_field_total[z][field]} for field in ("ans3", "ans4", "ans5", "ans6")}
            for z in (1, 2, 12)
        },
        "magnesium_primary_cooling_source_rows": len(source_mg),
        "magnesium_primary_cooling_unweighted_products_exact": mg_product_exact,
        "magnesium_primary_cooling_source_order_indices_exact": mg_order_exact,
        "magnesium_primary_cooling_abundance_after_sum_exact": mg_reduced_exact,
        "native_computed_values_exact": computed_exact, "native_computed_values_total": len(components),
        "independent_rows": independent_rows, "source_scalar_override_rows": source_scalar_rows,
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
        result = audit(args.source_capture.resolve(), args.native_run.resolve(), args.component_comparison.resolve(), args.output.resolve())
    except Exception as exc:
        result = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "scientific_result": "REJECT", "gates": {}, "errors": [str(exc)], "qualification_only": True, "production_promotion_ready": False}
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
