"""Audit source-order Thermal diagonal reduction and secondary ledgers for v0.6.48.7.46.14.1."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.14.1"
SCHEMA = "xstar-tools-v064874614-thermal-diagonal-domain-secondary-ledger-audit-v1"
COMPONENT_FIELDS = (
    "h_heating", "h_cooling", "h_heating2", "h_cooling2",
    "he_heating", "he_cooling", "he_heating2", "he_cooling2",
    "he_type53_heating", "he_type53_cooling", "he_type53_heating2", "he_type53_cooling2",
    "he_non_type53_heating", "he_non_type53_cooling", "he_non_type53_heating2", "he_non_type53_cooling2",
    "mg_heating", "mg_cooling", "mg_heating2", "mg_cooling2",
    "element_heating", "element_cooling", "element_heating2", "element_cooling2",
    "continuum_heating", "continuum_cooling", "continuum_heating2", "continuum_cooling2",
    "httot", "cltot", "httot2", "cltot2", "hmctot", "elcter",
)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _bits(value: str | float) -> bytes:
    return struct.pack(">d", float(value))


def _exact(a: str | float, b: str | float) -> bool:
    try:
        x, y = float(a), float(b)
    except Exception:
        return False
    return math.isfinite(x) and math.isfinite(y) and _bits(x) == _bits(y)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def audit(native_run: Path, baseline_v04874613: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    budget_path = native_run / "native_all61_thermal_budget.csv"
    diagonal_path = native_run / "native_all61_thermal_diagonal_ledger.csv"
    compact_path = native_run / "native_all61_thermal_compact_populations.csv"
    baseline_budget_path = baseline_v04874613 / "native_all61" / "native_all61_thermal_budget.csv"
    native_summary_path = native_run / "native_dsec_summary.json"
    errors: list[str] = []
    for path in (budget_path, diagonal_path, compact_path, baseline_budget_path, native_summary_path):
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing:{path}")
    if errors:
        report = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": errors,
                  "qualification_only": True, "production_promotion_ready": False}
        _write_json(output / "v04874614_thermal_diagonal_domain_report.json", report)
        return report

    native_summary = json.loads(native_summary_path.read_text())
    budgets = _read(budget_path)
    baseline = _read(baseline_budget_path)
    diagonals = _read(diagonal_path)
    compact = _read(compact_path)
    budgets.sort(key=lambda r: int(r["sequence"]))
    baseline.sort(key=lambda r: int(r["sequence"]))

    flags_exact = sum(
        row.get("thermal_diagonal_source_domain_applied") == "1" and
        row.get("continuum_secondary_ledger_corrected") == "1"
        for row in budgets
    )
    normalization_excluded_zero = sum(row.get("thermal_diagonal_normalization_rows_excluded") == "0" for row in budgets)
    secondary_exact = 0
    for row in budgets:
        if (
            _exact(row["computed_continuum_heating2"], float(row["computed_htcomp"]) + float(row["computed_htfreef"])) and
            _exact(row["computed_continuum_cooling2"], float(row["computed_clcomp"]) + float(row["computed_clbrems"]))
        ):
            secondary_exact += 1

    by_seq_element: dict[tuple[int, int], list[dict[str, str]]] = defaultdict(list)
    source_included = 0
    normalization_terms = 0
    valid_roles = 0
    for row in diagonals:
        key = (int(row["sequence"]), int(row["element_z"]))
        by_seq_element[key].append(row)
        source_included += row.get("source_domain_included") == "1"
        normalization_terms += row.get("is_normalization_row") == "1"
        valid_roles += row.get("role") in {"forward_diag_loss", "reverse_diag_loss"}

    source_order_exact = 0
    for rows in by_seq_element.values():
        indexes = [int(row["source_order_index"]) for row in rows]
        if indexes == list(range(1, len(indexes) + 1)):
            source_order_exact += 1

    committed_exact = committed_total = 0
    if len(budgets) == len(baseline) == 61:
        for current, old in zip(budgets, baseline):
            if int(current["sequence"]) != int(old["sequence"]):
                errors.append("baseline_sequence_inventory")
                break
            for field in COMPONENT_FIELDS:
                if field in current and field in old:
                    committed_total += 1
                    committed_exact += _exact(current[field], old[field])

    compact_sequences = {int(row["sequence"]) for row in compact}
    dominant = sorted(
        diagonals,
        key=lambda row: abs(float(row.get("heating2_contribution", 0.0))) + abs(float(row.get("cooling2_contribution", 0.0))),
        reverse=True,
    )[:25]
    dominant_rows = [
        {key: row.get(key) for key in (
            "sequence", "element_z", "source_order_index", "source_position", "record", "data_type",
            "rate_type", "compact_row", "role", "is_normalization_row", "compact_population", "cj2",
            "heating2_contribution", "cooling2_contribution",
        )}
        for row in dominant
    ]
    with (output / "v04874614_dominant_thermal_diagonal_terms.csv").open("w", newline="") as handle:
        fields = list(dominant_rows[0]) if dominant_rows else ["sequence"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(dominant_rows)

    gates = {
        "ALL_61_THERMAL_DIAGONAL_SOURCE_DOMAIN_APPLIED": "ACCEPT" if flags_exact == 61 else "REJECT",
        "THERMAL_DIAGONAL_SOURCE_ORDER_STREAMS_EXACT_183": "ACCEPT" if source_order_exact == 183 else "REJECT",
        "THERMAL_DIAGONAL_TERMS_ALL_INCLUDED": "ACCEPT" if source_included == len(diagonals) and len(diagonals) > 0 else "REJECT",
        "THERMAL_DIAGONAL_ROLES_SOURCE_FAITHFUL": "ACCEPT" if valid_roles == len(diagonals) and len(diagonals) > 0 else "REJECT",
        "NORMALIZATION_TERMS_RETAINED_SOURCE_FAITHFULLY": "ACCEPT" if normalization_terms > 0 and normalization_excluded_zero == 61 else "REJECT",
        "CONTINUUM_SECONDARY_LEDGER_EXACT_61": "ACCEPT" if secondary_exact == 61 else "REJECT",
        "COMMITTED_THERMAL_CLOSURE_UNCHANGED": "ACCEPT" if committed_total > 0 and committed_exact == committed_total else "REJECT",
        "COMPACT_POPULATION_TRANSPORT_PRESERVED_40149": "ACCEPT" if len(compact) == 40149 and compact_sequences == set(range(1, 62)) else "REJECT",
        "PYTHON_CALLBACKS_ZERO": "ACCEPT" if native_summary.get("python_callbacks") == 0 else "REJECT",
    }
    result = "ACCEPT" if not errors and all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": result,
        "milestone_scope": "qualification-only source-order Thermal diagonal-domain and independent secondary-ledger correction",
        "thermal_evaluations": len(budgets),
        "diagonal_terms": len(diagonals),
        "diagonal_source_order_streams_exact": source_order_exact,
        "normalization_terms_retained": normalization_terms,
        "continuum_secondary_ledgers_exact": secondary_exact,
        "committed_thermal_values_exact": committed_exact,
        "committed_thermal_values_total": committed_total,
        "compact_population_values": len(compact),
        "python_callbacks": native_summary.get("python_callbacks", -1),
        "dominant_remaining_term": dominant_rows[0] if dominant_rows else None,
        "gates": gates,
        "errors": errors + [name for name, value in gates.items() if value != "ACCEPT"],
        "qualification_only": True,
        "production_promotion_ready": False,
        "independent_native_thermal_parity": "NOT_ACCEPTED",
    }
    _write_json(output / "v04874614_thermal_diagonal_domain_report.json", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--baseline-v04874613", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(args.native_run, args.baseline_v04874613, args.output)
    except Exception as exc:
        report = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "qualification_only": True, "production_promotion_ready": False}
    if args.output_json:
        _write_json(args.output_json, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
