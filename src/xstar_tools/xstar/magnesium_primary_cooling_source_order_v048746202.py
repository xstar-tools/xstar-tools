"""Audit the v46.20.2 Magnesium primary-cooling source-order reduction."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.46.21.1"
SCHEMA = "xstar-tools-v0648746202-magnesium-primary-cooling-source-order-audit-v1"
COMPARISON_NAME = "v048746202_magnesium_primary_cooling_source_order_comparison.csv"
SUMMARY_NAME = "v048746202_magnesium_primary_cooling_source_order_summary.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _exact(a: Any, b: Any) -> bool:
    try:
        return float(a).hex() == float(b).hex()
    except Exception:
        return str(a) == str(b)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["empty"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _native_ledger(native_run: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for sequence in range(1, 62):
        candidates = (
            native_run / "evaluations" / f"evaluation_{sequence:04d}" / "native_thermal_diagonal_ledger.csv",
            native_run / "qualification_diagnostics" / f"evaluation_{sequence:04d}_thermal_diagonal_ledger.csv",
        )
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            raise FileNotFoundError(candidates[0])
        for row in _read_csv(path):
            if int(row.get("element_z", "0")) != 12:
                continue
            if not (float(row.get("cj", "0")) > 0.0):
                continue
            item = dict(row); item["sequence"] = str(sequence); rows.append(item)
    return rows


def _component_counts(path: Path, component: str) -> tuple[int, int, float]:
    rows = [row for row in _read_csv(path) if row.get("component") == component]
    exact = sum(int(row.get("computed_exact", "0")) for row in rows)
    maximum = max((abs(float(row.get("computed_signed_delta", "nan"))) for row in rows), default=float("nan"))
    return exact, len(rows), maximum


def audit(source_capture: Path, native_run: Path, component_comparison: Path,
          baseline_checker: Path, output: Path) -> dict[str, Any]:
    errors: list[str] = []
    gates: dict[str, str] = {}
    capture_report = json.loads((source_capture / "all61_magnesium_primary_cooling_source_order_capture_report.json").read_text())
    source_rows = _read_csv(source_capture / "v0472_all61_magnesium_primary_cooling_source_order_ledger.csv")
    source_family = _read_csv(source_capture / "v0472_all61_magnesium_primary_cooling_source_order_family.csv")
    native_rows = _native_ledger(native_run)
    baseline = json.loads(baseline_checker.read_text())

    gates["SOURCE_CAPTURE_ACCEPTED"] = "ACCEPT" if capture_report.get("result") == "ACCEPT" and capture_report.get("evaluations") == 61 else "REJECT"
    gates["V462011_ACCEPTED_BASELINE"] = "ACCEPT" if baseline.get("result") == "ACCEPT" else "REJECT"

    def source_key(row: dict[str, str]) -> tuple[int, int, str]:
        return int(row["sequence"]), int(row["record"]), row["role"]
    def native_key(row: dict[str, str]) -> tuple[int, int, str]:
        return int(row["sequence"]), int(row["record"]), row["role"]

    source = {source_key(row): row for row in source_rows}
    native = {native_key(row): row for row in native_rows if row.get("magnesium_primary_cooling_source_order_applied") == "1"}
    source_keys_exact = bool(source) and set(source) == set(native)
    gates["MAGNESIUM_PRIMARY_COOLING_SOURCE_KEYS_EXACT"] = "ACCEPT" if source_keys_exact else "REJECT"

    comparison: list[dict[str, Any]] = []
    metadata_exact = contribution_exact = order_exact = 0
    for key in sorted(set(source) | set(native)):
        s = source.get(key); n = native.get(key)
        row: dict[str, Any] = {
            "sequence": key[0], "record": key[1], "role": key[2],
            "source_present": int(s is not None), "native_present": int(n is not None),
        }
        if s is not None and n is not None:
            metadata = (
                int(s["data_type"]) == int(n["data_type"]) and
                int(s["rate_type"]) == int(n["rate_type"]) and
                int(s["compact_row"]) == int(n["compact_row"])
            )
            contribution = _exact(s["cooling_contribution"], n["cooling_contribution"])
            order = int(s["source_order_index"]) == int(n.get("magnesium_primary_cooling_source_order_index", "0"))
            metadata_exact += int(metadata); contribution_exact += int(contribution); order_exact += int(order)
            row.update({
                "source_order_index": s["source_order_index"],
                "native_source_order_index": n.get("magnesium_primary_cooling_source_order_index", ""),
                "source_data_type": s["data_type"], "native_data_type": n["data_type"],
                "source_rate_type": s["rate_type"], "native_rate_type": n["rate_type"],
                "source_compact_row": s["compact_row"], "native_compact_row": n["compact_row"],
                "source_cooling_contribution": s["cooling_contribution"],
                "native_cooling_contribution": n["cooling_contribution"],
                "metadata_exact": int(metadata), "contribution_exact": int(contribution),
                "source_order_exact": int(order),
            })
        comparison.append(row)
    _write_csv(output / COMPARISON_NAME, comparison)
    expected_rows = len(source)
    gates["MAGNESIUM_PRIMARY_COOLING_METADATA_EXACT"] = "ACCEPT" if expected_rows > 0 and metadata_exact == expected_rows else "REJECT"
    gates["MAGNESIUM_PRIMARY_COOLING_CONTRIBUTIONS_EXACT"] = "ACCEPT" if expected_rows > 0 and contribution_exact == expected_rows else "REJECT"
    gates["MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_INDICES_EXACT"] = "ACCEPT" if expected_rows > 0 and order_exact == expected_rows else "REJECT"

    source_by_sequence: dict[int, list[dict[str, str]]] = {}
    native_by_sequence: dict[int, list[dict[str, str]]] = {}
    for row in source_rows: source_by_sequence.setdefault(int(row["sequence"]), []).append(row)
    for row in native.values(): native_by_sequence.setdefault(int(row["sequence"]), []).append(row)
    family_by_sequence = {int(row["sequence"]): row for row in source_family}
    summaries: list[dict[str, Any]] = []
    reduced_exact = 0
    for sequence in range(1, 62):
        srows = sorted(source_by_sequence.get(sequence, []), key=lambda row: int(row["source_order_index"]))
        nrows = sorted(native_by_sequence.get(sequence, []), key=lambda row: int(row["magnesium_primary_cooling_source_order_index"]))
        source_sum = 0.0
        native_sum = 0.0
        for row in srows: source_sum += float(row["cooling_contribution"])
        for row in nrows: native_sum += float(row["cooling_contribution"])
        family = family_by_sequence.get(sequence, {})
        exact = (
            len(srows) == len(nrows) and
            _exact(source_sum, native_sum) and
            _exact(source_sum, family.get("source_mg_cooling", "nan"))
        )
        reduced_exact += int(exact)
        summaries.append({
            "sequence": sequence, "source_rows": len(srows), "native_rows": len(nrows),
            "source_order_reduced_mg_cooling": source_sum,
            "native_source_order_reduced_mg_cooling": native_sum,
            "source_mg_cooling": family.get("source_mg_cooling", ""),
            "exact": int(exact),
        })
    _write_csv(output / SUMMARY_NAME, summaries)
    gates["MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_ALL61_EXACT"] = "ACCEPT" if reduced_exact == 61 else "REJECT"

    mg_exact, mg_total, mg_max = _component_counts(component_comparison, "mg_cooling")
    h_exact, h_total, _ = _component_counts(component_comparison, "h_cooling")
    all_components = _read_csv(component_comparison)
    native_exact = sum(int(row.get("computed_exact", "0")) for row in all_components)
    gates["MAGNESIUM_COOLING_ALL61_EXACT"] = "ACCEPT" if mg_exact == mg_total == 61 else "REJECT"
    gates["HYDROGEN_COOLING_ALL61_PRESERVED"] = "ACCEPT" if h_exact == h_total == 61 else "REJECT"
    gates["NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127"] = "ACCEPT" if native_exact == 1127 and len(all_components) == 2440 else "REJECT"
    gates["PRODUCTION_PROMOTION_BLOCKED"] = "ACCEPT"

    result = "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT"
    return {
        "schema": SCHEMA, "release": RELEASE, "result": result,
        "scientific_result": result,
        "gates": gates, "errors": [name for name, value in gates.items() if value != "ACCEPT"],
        "source_rows": len(source_rows), "native_rows": len(native),
        "metadata_exact_rows": metadata_exact,
        "contribution_exact_rows": contribution_exact,
        "source_order_exact_rows": order_exact,
        "source_order_exact_evaluations": reduced_exact,
        "mg_cooling_exact": mg_exact, "mg_cooling_total": mg_total,
        "mg_cooling_max_abs_delta": mg_max,
        "native_computed_values_exact": native_exact,
        "native_computed_values_total": len(all_components),
        "qualification_only": True, "production_promotion_ready": False,
    }


def main(argv=None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--source-capture",type=Path,required=True)
    p.add_argument("--native-run",type=Path,required=True)
    p.add_argument("--component-comparison",type=Path,required=True)
    p.add_argument("--baseline-checker",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--output-json",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        r=audit(a.source_capture.resolve(),a.native_run.resolve(),a.component_comparison.resolve(),a.baseline_checker.resolve(),a.output.resolve())
    except Exception as exc:
        r={"schema":SCHEMA,"release":RELEASE,"result":"REJECT","scientific_result":"REJECT","gates":{},"errors":[str(exc)],"qualification_only":True,"production_promotion_ready":False}
    a.output_json.parent.mkdir(parents=True,exist_ok=True)
    a.output_json.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print(json.dumps(r,indent=2,sort_keys=True))
    return 0 if r["result"]=="ACCEPT" else 2
if __name__=="__main__": raise SystemExit(main())
