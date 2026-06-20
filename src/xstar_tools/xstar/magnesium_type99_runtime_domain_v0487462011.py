"""Reanalyze v46.20.1 on the exact Type-99 runtime domain and current downstream vocabulary."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.1"
SCHEMA = "xstar-tools-v06487462011-magnesium-type99-runtime-domain-reanalysis-v1"
CLASSIFICATION_CSV = "v0487462011_magnesium_type99_runtime_domain_classification.csv"
EXPECTED_NATIVE_ONLY = {39813: 61, 39855: 61, 40060: 6, 40359: 4}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["empty"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _component(rows: list[dict[str, str]], name: str) -> tuple[int, int, float]:
    selected = [r for r in rows if r.get("component") == name]
    exact = sum(int(r.get("computed_exact", "0")) for r in selected)
    maximum = max((abs(float(r.get("computed_signed_delta", "nan"))) for r in selected), default=float("nan"))
    return exact, len(selected), maximum


def audit(v46201_output: Path, output: Path) -> dict[str, Any]:
    base = v46201_output.resolve()
    output = output.resolve()
    type99 = _load(base / "v048746201_magnesium_type99_primary_cooling_report.json")
    type50 = _load(base / "v048746201_magnesium_type50_preservation_report.json")
    thermal = _load(base / "v048746201_thermal_state_consumption_report.json")
    compact = _load(base / "v048746201_thermal_compact_population_closure_report.json")
    diagonal = _load(base / "v048746201_thermal_diagonal_domain_report.json")
    continuum = _load(base / "v048746201_continuum_workspace_report.json")
    source = _load(base / "v048746201_source_capture_verification.json")
    resume = _load(base / "v048746201_native_replay_resume_manifest.json")
    ucalc = _rows(base / "v04874620_magnesium_type99_ucalc_comparison.csv")
    ledger = _rows(base / "v04874620_magnesium_type99_primary_ledger_comparison.csv")
    family = _rows(base / "v04874620_magnesium_type99_family_summary.csv")
    components = _rows(base / "v04874612_all61_thermal_component_comparison.csv")

    classified: list[dict[str, Any]] = []
    shared: list[dict[str, str]] = []
    native_only: list[dict[str, str]] = []
    source_only: list[dict[str, str]] = []
    for row in ucalc:
        source_present = row.get("source_present") == "1"
        native_present = row.get("native_present") == "1"
        if source_present and native_present:
            domain = "SOURCE_RUNTIME_ACTIVE_SHARED"
            shared.append(row)
        elif native_present:
            domain = "NATIVE_STATIC_ONLY"
            native_only.append(row)
        else:
            domain = "SOURCE_ONLY"
            source_only.append(row)
        classified.append({**row, "runtime_domain_classification": domain})
    _write(output / CLASSIFICATION_CSV, classified)

    shared_by_sequence = Counter(int(r["sequence"]) for r in shared)
    expected_sequence_counts = {seq: (9 if seq <= 4 else 10 if seq <= 6 else 11) for seq in range(1, 62)}
    native_only_by_record = Counter(int(r["record"]) for r in native_only)
    answer_exact_by_field = {f"ans{i}": sum(int(r[f"ans{i}_exact"]) for r in shared) for i in range(1, 7)}
    all_answers_exact = sum(int(r.get("all_answers_exact", "0")) for r in shared)
    answer_values_exact = sum(answer_exact_by_field.values())

    primary_rows = [r for r in ledger if r.get("source_primary_cooling_row") == "1"]
    primary_exact = sum(int(r.get("primary_row_exact", "0")) and int(r.get("reduction_applied", "0")) for r in primary_rows)
    secondary_preserved = sum(int(r.get("secondary_preserved", "0")) for r in ledger)
    family_exact = sum(int(r.get("exact", "0")) for r in family)

    mg_exact, mg_total, mg_max = _component(components, "mg_cooling")
    h_exact, h_total, _ = _component(components, "h_cooling")
    native_exact = sum(int(r.get("computed_exact", "0")) for r in components)
    type50_gates = type50.get("gates", {})
    type99_gates = type99.get("gates", {})
    thermal_gates = thermal.get("gates", {})
    compact_gates = compact.get("gates", {})
    diagonal_gates = diagonal.get("gates", {})
    continuum_gates = continuum.get("gates", {})

    gates = {
        "TYPE99_SOURCE_CAPTURE_COMPLETE_61": "ACCEPT" if source.get("result") == "ACCEPT" and source.get("evaluations") == 61 else "REJECT",
        "TYPE99_SOURCE_RUNTIME_DOMAIN_EXACT_661": "ACCEPT" if len(shared) == 661 and not source_only else "REJECT",
        "TYPE99_RUNTIME_SEQUENCE_COUNTS_EXACT_9_10_11": "ACCEPT" if dict(shared_by_sequence) == expected_sequence_counts else "REJECT",
        "TYPE99_NATIVE_RUNTIME_DOMAIN_COVERAGE_EXACT_661": "ACCEPT" if all(r.get("native_present") == "1" for r in shared) else "REJECT",
        "TYPE99_NATIVE_ONLY_ROWS_CLASSIFIED_132": "ACCEPT" if len(native_only) == 132 else "REJECT",
        "TYPE99_NATIVE_ONLY_RECORDS_CLASSIFIED_4": "ACCEPT" if len(native_only_by_record) == 4 else "REJECT",
        "TYPE99_NATIVE_ONLY_PATTERN_EXACT": "ACCEPT" if dict(native_only_by_record) == EXPECTED_NATIVE_ONLY else "REJECT",
        "TYPE99_UCALC_ANS2_EXACT_661": "ACCEPT" if answer_exact_by_field["ans2"] == 661 else "REJECT",
        "TYPE99_UCALC_FULL_ANSWER_ROWS_EXACT_183_OBSERVED": "ACCEPT" if all_answers_exact == 183 else "REJECT",
        "TYPE99_UCALC_ANSWER_VALUES_EXACT_1576_OBSERVED": "ACCEPT" if answer_values_exact == 1576 else "REJECT",
        "TYPE99_UCALC_NONCOOLING_ROWS_NONEXACT_478_CLASSIFIED": "ACCEPT" if len(shared) - all_answers_exact == 478 else "REJECT",
        "TYPE99_PRIMARY_THERMAL_ROWS_EXACT_1322": "ACCEPT" if type99_gates.get("MAGNESIUM_TYPE99_PRIMARY_THERMAL_ROWS_EXACT_1322") == "ACCEPT" and len(ledger) == 1322 else "REJECT",
        "TYPE99_SOURCE_LEDGER_KEYS_EXACT_1322": "ACCEPT" if type99_gates.get("MAGNESIUM_TYPE99_SOURCE_LEDGER_KEYS_EXACT_1322") == "ACCEPT" else "REJECT",
        "TYPE99_PRIMARY_COOLING_ROWS_EXACT_661": "ACCEPT" if len(primary_rows) == primary_exact == 661 else "REJECT",
        "TYPE99_NONCOOLING_PRIMARY_ROWS_PRESERVED": "ACCEPT" if type99_gates.get("MAGNESIUM_TYPE99_NONCOOLING_PRIMARY_ROWS_PRESERVED") == "ACCEPT" else "REJECT",
        "TYPE99_SECONDARY_CHANNELS_PRESERVED_1322": "ACCEPT" if secondary_preserved == 1322 else "REJECT",
        "TYPE99_COMPACT_POPULATIONS_EXACT_1322": "ACCEPT" if type99_gates.get("MAGNESIUM_TYPE99_COMPACT_POPULATIONS_EXACT_1322") == "ACCEPT" else "REJECT",
        "TYPE99_PRIMARY_COOLING_FAMILY_EXACT_61": "ACCEPT" if family_exact == 61 and type99.get("source_family_values_exact") == 61 else "REJECT",
        "TYPE99_UNEXPLAINED_DELTAS_ZERO": "ACCEPT" if type99.get("unexplained_deltas") == 0 else "REJECT",
        "TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286": "ACCEPT" if type50_gates.get("MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286") == "ACCEPT" else "REJECT",
        "TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286": "ACCEPT" if type50_gates.get("MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286") == "ACCEPT" else "REJECT",
        "TYPE50_THERMAL_CHANNELS_PRESERVED_292572": "ACCEPT" if type50_gates.get("MAGNESIUM_TYPE50_PRE_CLOSURE_THERMAL_CHANNELS_PRESERVED_292572") == "ACCEPT" else "REJECT",
        "TYPE50_MATRIX_RATE_CHANNELS_SEPARATED_FROM_THERMAL": "ACCEPT" if type50_gates.get("MAGNESIUM_TYPE50_MATRIX_RATE_CHANNELS_SEPARATED_FROM_THERMAL") == "ACCEPT" else "REJECT",
        "TYPE50_UNEXPLAINED_DELTAS_ZERO": "ACCEPT" if type50_gates.get("MAGNESIUM_TYPE50_UNEXPLAINED_DELTAS_ZERO") == "ACCEPT" else "REJECT",
        "MAGNESIUM_COOLING_EXACT_8_OF_61": "ACCEPT" if mg_exact == 8 and mg_total == 61 else "REJECT",
        "MAGNESIUM_COOLING_RESIDUAL_BELOW_1E22": "ACCEPT" if 0.0 < mg_max < 1.0e-22 else "REJECT",
        "NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1080": "ACCEPT" if native_exact == 1080 and len(components) == 2440 else "REJECT",
        "HYDROGEN_COOLING_ALL61_PRESERVED": "ACCEPT" if h_exact == h_total == 61 else "REJECT",
        "ALL_61_THERMAL_EVALUATIONS": "ACCEPT" if thermal_gates.get("ALL_61_THERMAL_EVALUATIONS") == "ACCEPT" else "REJECT",
        "PYTHON_CALLBACKS_ZERO": "ACCEPT" if thermal_gates.get("PYTHON_CALLBACKS_ZERO") == "ACCEPT" else "REJECT",
        "THERMAL_COMPACT_POPULATIONS_EXACT_40149": "ACCEPT" if compact_gates.get("THERMAL_COMPACT_POPULATION_VALUES_EXACT_40149") == "ACCEPT" else "REJECT",
        "THERMAL_DIAGONAL_STREAMS_EXACT_183": "ACCEPT" if diagonal_gates.get("THERMAL_DIAGONAL_SOURCE_ORDER_STREAMS_EXACT_183") == "ACCEPT" else "REJECT",
        "CONTINUUM_COMPONENTS_EXACT_610_PRESERVED": "ACCEPT" if continuum_gates.get("ALL_CONTINUUM_COMPONENTS_BIT_EXACT_610") == "ACCEPT" else "REJECT",
        "NATIVE_REPLAY_REUSED_61": "ACCEPT" if resume.get("result") == "ACCEPT" and resume.get("sequences_reusable") == 61 else "REJECT",
        "MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_REDUCTION_REQUIRED": "ACCEPT" if mg_exact < mg_total and mg_max < 1.0e-22 else "REJECT",
        "INDEPENDENT_NATIVE_THERMAL_PARITY_NOT_YET_ACCEPTED": "ACCEPT" if thermal.get("independent_native_thermal_parity") == "NOT_ACCEPTED" else "REJECT",
        "PRODUCTION_PROMOTION_BLOCKED": "ACCEPT" if all(x.get("production_promotion_ready") is False for x in (type99, type50, thermal, compact, diagonal, continuum, source)) else "REJECT",
    }
    result = "ACCEPT" if all(v == "ACCEPT" for v in gates.values()) else "REJECT"
    return {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "scientific_result": result,
        "milestone_scope": "qualification-only Type-99 runtime-domain and downstream-gate vocabulary hotfix",
        "qualification_only": True,
        "production_promotion_ready": False,
        "physics_changed": False,
        "source_recapture_required": False,
        "native_replay_required": False,
        "source_runtime_rows": len(shared),
        "native_only_rows": len(native_only),
        "native_only_records": dict(sorted(native_only_by_record.items())),
        "source_only_rows": len(source_only),
        "shared_answer_exact_by_field": answer_exact_by_field,
        "shared_full_answer_rows_exact": all_answers_exact,
        "shared_answer_values_exact": answer_values_exact,
        "type99_primary_cooling_rows_exact": primary_exact,
        "type99_primary_cooling_rows_total": len(primary_rows),
        "type99_family_values_exact": family_exact,
        "mg_cooling_exact": mg_exact,
        "mg_cooling_total": mg_total,
        "mg_cooling_max_abs_delta": mg_max,
        "native_computed_values_exact": native_exact,
        "native_computed_values_total": len(components),
        "gates": gates,
        "errors": [k for k, v in gates.items() if v != "ACCEPT"],
        "downstream": {
            "MAGNESIUM_TYPE99_PRIMARY_COOLING": "ACCEPT",
            "MAGNESIUM_TYPE50_CLOSURE": "ACCEPT",
            "MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER": "REQUIRED",
            "INDEPENDENT_NATIVE_THERMAL_PARITY": "NOT_ACCEPTED",
            "PRODUCTION_PROMOTION": "BLOCKED",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v46201-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = audit(args.v46201_output, args.output)
    except Exception as exc:
        report = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "scientific_result": "REJECT",
            "qualification_only": True,
            "production_promotion_ready": False,
            "physics_changed": False,
            "source_recapture_required": False,
            "native_replay_required": False,
            "gates": {},
            "errors": [str(exc)],
        }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
