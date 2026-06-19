"""Prepare and audit v0.6.48.7.46.17.2.1 all-61 Thermal component closure.

This is a qualification-only source-captured boundary.  It does not replace the
native evaluation: matrix construction, dense solves, state consumption, and
native Thermal arithmetic still execute and are retained as ``computed_*``
ledger columns.  The captured source components are committed separately so the
interface can be compared exactly without claiming independent native parity.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from .v0472_all61_thermal_state_capture import BUDGET_NAME

RELEASE = "0.6.48.7.46.17.2.1"
SCHEMA = "xstar-tools-v064874612-all61-thermal-component-parity-closure-v1"
REPORT_NAME = "v04874612_thermal_component_closure_report.json"
OVERRIDE_DIRNAME = "v04874612_thermal_component_closure"

CLOSURE_FIELDS = [
    "sequence", "kind", "call_index", "evaluation_index",
    "h_heating", "h_cooling", "h_heating2", "h_cooling2",
    "he_heating", "he_cooling", "he_heating2", "he_cooling2",
    "he_type53_heating", "he_type53_cooling", "he_type53_heating2", "he_type53_cooling2",
    "mg_heating", "mg_cooling", "mg_heating2", "mg_cooling2",
    "element_heating", "element_cooling", "element_heating2", "element_cooling2",
    "continuum_heating", "continuum_cooling", "continuum_heating2", "continuum_cooling2",
    "cmp1", "cmp2", "htcomp", "clcomp", "htfreef", "clbrems",
    "httot", "cltot", "httot2", "cltot2", "hmctot", "elcter",
]
NUMERIC_FIELDS = [field for field in CLOSURE_FIELDS if field not in {"kind"}]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CLOSURE_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def prepare(source_capture: Path, output_dir: Path) -> dict[str, Any]:
    source_path = source_capture / BUDGET_NAME
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    rows = _read_csv(source_path)
    rows.sort(key=lambda row: int(row["sequence"]))
    errors: list[str] = []
    if [int(row["sequence"]) for row in rows] != list(range(1, 62)):
        errors.append(f"sequence_inventory={len(rows)}")
    kinds = [row.get("kind", "") for row in rows]
    if kinds.count("dsec") != 57 or kinds.count("final") != 4:
        errors.append(f"kind_inventory=dsec:{kinds.count('dsec')},final:{kinds.count('final')}")
    missing = sorted(set(CLOSURE_FIELDS) - set(rows[0].keys())) if rows else CLOSURE_FIELDS
    if missing:
        errors.append("missing_fields=" + ",".join(missing))
    for row in rows:
        for field in NUMERIC_FIELDS:
            try:
                if not math.isfinite(float(row[field])):
                    raise ValueError
            except Exception:
                errors.append(f"nonfinite:{row.get('sequence')}:{field}")
                break
    output_dir.mkdir(parents=True, exist_ok=True)
    if not errors:
        for row in rows:
            sequence = int(row["sequence"])
            normalized: dict[str, Any] = {}
            for field in CLOSURE_FIELDS:
                value = row[field]
                if field == "kind":
                    normalized[field] = value
                elif field in {"sequence", "call_index", "evaluation_index"}:
                    normalized[field] = int(float(value))
                else:
                    normalized[field] = format(float(value), ".17g")
            _write_csv(output_dir / f"sequence_{sequence:04d}_thermal.csv", [normalized])
    gates = {
        "SOURCE_THERMAL_ROWS_61": "ACCEPT" if len(rows) == 61 else "REJECT",
        "SOURCE_THERMAL_SEQUENCE_CANONICAL": "ACCEPT" if not errors or not any(item.startswith("sequence_inventory") for item in errors) else "REJECT",
        "SOURCE_THERMAL_KIND_INVENTORY": "ACCEPT" if kinds.count("dsec") == 57 and kinds.count("final") == 4 else "REJECT",
        "SOURCE_THERMAL_COMPONENTS_FINITE": "ACCEPT" if not any(item.startswith("nonfinite:") for item in errors) else "REJECT",
        "THERMAL_CLOSURE_FILES_61": "ACCEPT" if not errors and len(list(output_dir.glob("sequence_*_thermal.csv"))) == 61 else "REJECT",
    }
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT",
        "errors": errors,
        "source_capture": str(source_capture),
        "sequences_prepared": len(list(output_dir.glob("sequence_*_thermal.csv"))),
        "component_fields_per_sequence": len(CLOSURE_FIELDS) - 4,
        "gates": gates,
        "qualification_only": True,
        "source_capture_replayed": False,
        "native_replay_replayed": False,
        "independent_native_thermal_parity_proven": False,
        "production_promotion_ready": False,
    }
    _write_json(output_dir / REPORT_NAME, report)
    return report


def audit(audit_output: Path, preparation_report: Path | None = None) -> dict[str, Any]:
    comparison_path = audit_output / "v04874612_all61_thermal_state_consumption_summary.json"
    if not comparison_path.is_file():
        raise FileNotFoundError(comparison_path)
    comparison = json.loads(comparison_path.read_text())
    preparation = json.loads(preparation_report.read_text()) if preparation_report else None
    comparison_gates = comparison.get("gates", {})
    required = [
        "ALL_61_THERMAL_INPUT_STATE_FINGERPRINTS_EXACT",
        "ALL_61_THERMAL_POPULATION_STATE_EXACT",
        "ALL_61_H_HE_MG_COMPONENTS_EXACT",
        "ALL_61_CONTINUUM_COMPONENTS_EXACT",
        "ALL_61_THERMAL_TOTALS_EXACT",
        "ALL_61_HMCTOT_EXACT",
        "THERMAL_COMPONENT_CLOSURE_APPLIED_61",
        "PYTHON_CALLBACKS_ZERO",
        "V06488_THERMAL_PARITY",
    ]
    if comparison_gates.get("THERMAL_COMPACT_POPULATION_CLOSURE_APPLIED_61") != "NOT_APPLICABLE_PRE_V064874613":
        required.append("THERMAL_COMPACT_POPULATION_CLOSURE_APPLIED_61")
    gates = {name: "ACCEPT" if comparison_gates.get(name) == "ACCEPT" else "REJECT" for name in required}
    if preparation is not None:
        gates["THERMAL_CLOSURE_PREPARATION_ACCEPTED"] = "ACCEPT" if preparation.get("result") == "ACCEPT" else "REJECT"
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT",
        "gates": gates,
        "thermal_component_values_exact": comparison.get("thermal_component_values_exact", 0),
        "thermal_component_values_total": comparison.get("thermal_component_values_total", 0),
        "native_computed_values_exact": comparison.get("native_computed_values_exact", 0),
        "native_computed_values_total": comparison.get("native_computed_values_total", 0),
        "independent_native_thermal_parity": comparison.get("independent_native_thermal_parity", "NOT_ACCEPTED"),
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    _write_json(audit_output / REPORT_NAME, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--source-capture", type=Path, required=True)
    prep.add_argument("--output-dir", type=Path, required=True)
    prep.add_argument("--output-json", type=Path)
    aud = sub.add_parser("audit")
    aud.add_argument("--audit-output", type=Path, required=True)
    aud.add_argument("--preparation-report", type=Path)
    aud.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = prepare(args.source_capture, args.output_dir) if args.command == "prepare" else audit(args.audit_output, args.preparation_report)
    except Exception as exc:
        result = {
            "schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
            "qualification_only": True, "production_promotion_ready": False,
        }
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
