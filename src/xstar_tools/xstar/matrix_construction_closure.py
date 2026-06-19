"""Prepare and audit the v0.6.48.7.46.19.1 source-captured matrix closure.

The preparation step consumes a completed v46.9.6 causal-attribution directory.
It emits per-evaluation contribution corrections and exact dense-cell source
values.  The runtime hook is qualification-only: it makes the matrix boundary
literal while the individual family formulas remain subject to later native
promotion audits.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

RELEASE = "0.6.48.7.46.19.1"
SCHEMA = "xstar-tools-v064874610-matrix-construction-closure-v1"
OVERRIDE_DIRNAME = "v04874610_matrix_closure"
REPORT_NAME = "v04874610_matrix_construction_closure_report.json"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _source_answer(rows: list[dict[str, str]], positive: str, negative: str) -> tuple[int, float]:
    for row in rows:
        if row["role"] == positive:
            return 1, float(row["source_value"])
    for row in rows:
        if row["role"] == negative:
            return 1, -float(row["source_value"])
    return 0, 0.0


def prepare(baseline: Path, output: Path) -> dict[str, Any]:
    cell_path = baseline / "all61_dense_matrix_causal_cells.csv"
    record_path = baseline / "all61_dense_matrix_causal_records.csv.gz"
    systems_path = baseline / "all61_matrix_contribution_systems.csv"
    for path in (cell_path, record_path, systems_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    systems = _read_csv(systems_path)
    if len(systems) != 183:
        raise ValueError(f"expected 183 matrix systems; found {len(systems)}")
    baseline_mismatch_cells = sum(int(row["dense_mismatch_cells"]) for row in systems)
    baseline_exact_systems = sum(int(row["dense_matrix_exact"]) for row in systems)

    cells_by_system: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    type_cell_counts: Counter[int] = Counter()
    with cell_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["attributed"]) != 1:
                raise ValueError("unattributed baseline dense cell")
            sequence = int(row["sequence"])
            element_z = int(row["element_z"])
            item = {
                "row": int(row["row"]),
                "column": int(row["column"]),
                "source_value": row["source_value"],
            }
            cells_by_system[(sequence, element_z)].append(item)
            for value in row["causal_data_types"].split(";"):
                if value:
                    type_cell_counts[int(value)] += 1

    records_by_identity: dict[tuple[int, int, int, int, int, int], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(record_path, "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (
                int(row["sequence"]), int(row["element_z"]), int(row["record"]),
                int(row["data_type"]), int(row["rate_type"]), int(row["ion_stage"]),
            )
            records_by_identity[key].append(row)

    corrections_by_system: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    action_counts: Counter[str] = Counter()
    type_action_counts: Counter[tuple[int, str]] = Counter()
    for key, rows in sorted(records_by_identity.items()):
        sequence, element_z, record, data_type, rate_type, ion_stage = key
        classes = {row["classification"] for row in rows}
        if "NATIVE_ONLY_RECORD" in classes:
            action = "remove"
            replace_ans1 = replace_ans2 = 0
            source_ans1 = source_ans2 = 0.0
        elif classes <= {"RATE_VALUE_DELTA"}:
            action = "replace"
            replace_ans1, source_ans1 = _source_answer(rows, "forward_offdiag", "forward_diag_loss")
            replace_ans2, source_ans2 = _source_answer(rows, "reverse_offdiag", "reverse_diag_loss")
            if not replace_ans1 and not replace_ans2:
                raise ValueError(f"rate delta without a recoverable dense answer: {key}")
        else:
            raise ValueError(f"unsupported matrix-closure classification {classes} for {key}")
        corrections_by_system[(sequence, element_z)].append({
            "record": record,
            "data_type": data_type,
            "rate_type": rate_type,
            "ion_stage": ion_stage,
            "action": action,
            "replace_ans1": replace_ans1,
            "source_ans1": format(source_ans1, ".17g"),
            "replace_ans2": replace_ans2,
            "source_ans2": format(source_ans2, ".17g"),
        })
        action_counts[action] += 1
        type_action_counts[(data_type, action)] += 1

    output.mkdir(parents=True, exist_ok=True)
    generated_systems = 0
    for sequence in range(1, 62):
        for element_z in (1, 2, 12):
            stem = f"sequence_{sequence:04d}_element_{element_z:02d}"
            cell_rows = sorted(cells_by_system.get((sequence, element_z), []), key=lambda x: (x["row"], x["column"]))
            correction_rows = corrections_by_system.get((sequence, element_z), [])
            _write_csv(output / f"{stem}_dense.csv", ["row", "column", "source_value"], cell_rows)
            _write_csv(
                output / f"{stem}_contributions.csv",
                ["record", "data_type", "rate_type", "ion_stage", "action", "replace_ans1", "source_ans1", "replace_ans2", "source_ans2"],
                correction_rows,
            )
            generated_systems += 1

    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT",
        "qualification_only": True,
        "baseline_exact_systems": baseline_exact_systems,
        "baseline_mismatch_cells": baseline_mismatch_cells,
        "systems_prepared": generated_systems,
        "dense_cell_overrides": sum(len(v) for v in cells_by_system.values()),
        "contribution_corrections": sum(action_counts.values()),
        "contribution_replacements": action_counts["replace"],
        "native_only_contributions_removed": action_counts["remove"],
        "causal_data_type_cell_counts": {str(k): v for k, v in sorted(type_cell_counts.items())},
        "correction_type_action_counts": {
            f"{data_type}:{action}": count
            for (data_type, action), count in sorted(type_action_counts.items())
        },
        "gates": {
            "BASELINE_SYSTEMS_183": "ACCEPT" if len(systems) == 183 else "REJECT",
            "BASELINE_MISMATCH_CELLS_PRESENT": "ACCEPT" if baseline_mismatch_cells > 0 else "REJECT",
            "ALL_BASELINE_MISMATCH_CELLS_CAPTURED": "ACCEPT" if baseline_mismatch_cells == sum(len(v) for v in cells_by_system.values()) else "REJECT",
            "ALL_CAUSAL_RECORD_IDENTITIES_CLASSIFIED": "ACCEPT",
            "MATRIX_CLOSURE_FILES_183": "ACCEPT" if generated_systems == 183 else "REJECT",
        },
    }
    if any(value != "ACCEPT" for value in report["gates"].values()):
        report["result"] = "REJECT"
    _write_json(output / REPORT_NAME, report)
    return report


def audit(audit_output: Path, preparation_report: Path | None = None) -> dict[str, Any]:
    summary_path = audit_output / "all61_dense_matrix_causal_attribution_summary.json"
    systems_path = audit_output / "all61_matrix_contribution_systems.csv"
    if not summary_path.is_file() or not systems_path.is_file():
        raise FileNotFoundError("completed attribution output is required")
    summary = json.loads(summary_path.read_text())
    systems = _read_csv(systems_path)
    exact_systems = sum(int(row["dense_matrix_exact"]) for row in systems)
    mismatch_cells = sum(int(row["dense_mismatch_cells"]) for row in systems)
    source_reconstruction = sum(int(row["source_reconstruction_exact"]) for row in systems)
    native_reconstruction = sum(int(row["native_reconstruction_exact"]) for row in systems)
    preparation = json.loads(preparation_report.read_text()) if preparation_report else None
    gates = {
        "DENSE_EXACT_SYSTEMS_183": "ACCEPT" if exact_systems == 183 else "REJECT",
        "DENSE_MISMATCH_CELLS_ZERO": "ACCEPT" if mismatch_cells == 0 else "REJECT",
        "SOURCE_MATRIX_RECONSTRUCTION_EXACT_183": "ACCEPT" if source_reconstruction == 183 else "REJECT",
        "NATIVE_MATRIX_RECONSTRUCTION_EXACT_183": "ACCEPT" if native_reconstruction == 183 else "REJECT",
        "CAUSAL_RECORD_ROWS_ZERO": "ACCEPT" if int(summary.get("causal_record_rows_written", -1)) == 0 else "REJECT",
        "CAUSAL_CELL_ROWS_ZERO": "ACCEPT" if int(summary.get("causal_cell_rows_written", -1)) == 0 else "REJECT",
    }
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if all(v == "ACCEPT" for v in gates.values()) else "REJECT",
        "qualification_only": True,
        "systems": len(systems),
        "dense_exact_systems": exact_systems,
        "dense_mismatch_cells": mismatch_cells,
        "source_reconstruction_exact_systems": source_reconstruction,
        "native_reconstruction_exact_systems": native_reconstruction,
        "preparation": preparation,
        "gates": gates,
        "production_promotion_ready": False,
    }
    _write_json(audit_output / REPORT_NAME, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--baseline-audit", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--output-json", type=Path)
    a = sub.add_parser("audit")
    a.add_argument("--audit-output", type=Path, required=True)
    a.add_argument("--preparation-report", type=Path)
    a.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            report = prepare(args.baseline_audit, args.output_dir)
        else:
            report = audit(args.audit_output, args.preparation_report)
        if args.output_json:
            _write_json(args.output_json, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["result"] == "ACCEPT" else 2
    except Exception as exc:
        report = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)]}
        if getattr(args, "output_json", None):
            _write_json(args.output_json, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
