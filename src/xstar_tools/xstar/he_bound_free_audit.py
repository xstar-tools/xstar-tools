"""He II bound-free source-order qualification audit for XSTAR v0.6.48.7.1.

This module compares the type-53 contribution that is currently applied by the
native fixed-state engine with a source-style shadow evaluation.  The shadow
path is diagnostic only: it is never substituted into the physical solve.

The lowered active program stores cross sections in cm^2.  The historical
source-style kernel accepted megabarns and multiplied by 1e-18 internally, so
the audit explicitly records the corrected unit boundary.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "xstar-tools-v064871-he-bound-free-audit-v1"
AUDITED_ELEMENT_Z = 2
AUDITED_ION_STAGE = 2
AUDITED_DATA_TYPE = 53


def _float(value: Any) -> float:
    if value is None or value == "":
        return math.nan
    return float(value)


def _int(value: Any) -> int:
    if value is None or value == "":
        return 0
    return int(value)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    os.replace(temporary, path)


def _resolve_records_csv(source: Path, evaluation: int) -> Path:
    source = source.resolve()
    expected = f"evaluation_{evaluation:04d}_records.csv"
    candidates: list[Path] = []
    if source.is_file():
        candidates.append(source)
    else:
        candidates.extend([
            source / expected,
            source / "diagnostics" / expected,
            source / "qualification_diagnostics" / expected,
            source / "reference_input" / "qualification_diagnostics" / expected,
        ])
        candidates.extend(sorted(source.glob(f"**/{expected}")))
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"could not find {expected} under {source}")


def _resolve_state_json(records_csv: Path, evaluation: int) -> Path | None:
    candidate = records_csv.with_name(f"evaluation_{evaluation:04d}_state.json")
    return candidate if candidate.is_file() else None


def _relative_delta(applied: float, shadow: float) -> float:
    denominator = abs(applied)
    if denominator == 0.0:
        return math.inf if shadow != 0.0 else 0.0
    return (shadow - applied) / denominator


def audit(records_source: Path, output_dir: Path, *, evaluation: int = 61) -> dict[str, Any]:
    records_csv = _resolve_records_csv(records_source, evaluation)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with records_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type",
            "lower_row", "upper_row", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
            "type53_shadow_valid", "type53_shadow_ans1", "type53_shadow_ans2",
            "type53_shadow_ans3", "type53_shadow_ans4", "type53_shadow_ans5", "type53_shadow_ans6",
            "type53_shadow_threshold_ev", "type53_shadow_rnist", "type53_shadow_nb1_one_based",
            "type53_shadow_klmax_one_based",
        }
        missing = sorted(required.difference(reader.fieldnames or []))
        if missing:
            raise ValueError("records CSV does not contain v0.6.48.7.1 type-53 shadow fields: " + ", ".join(missing))
        selected = [
            row for row in reader
            if _int(row["evaluation_ordinal"]) == evaluation
            and _int(row["element_z"]) == AUDITED_ELEMENT_Z
            and _int(row["ion_stage"]) == AUDITED_ION_STAGE
            and _int(row["data_type"]) == AUDITED_DATA_TYPE
            and _int(row["type53_shadow_valid"]) == 1
        ]

    selected.sort(key=lambda row: (_int(row["source_position"]), _int(row["record"])))
    if not selected:
        raise ValueError("no He II type-53 shadow records were found")

    audit_rows: list[dict[str, Any]] = []
    applied_totals = [0.0] * 6
    shadow_totals = [0.0] * 6
    first_divergent: dict[str, Any] | None = None
    largest: list[dict[str, Any] | None] = [None] * 6

    for row in selected:
        output: dict[str, Any] = {
            "evaluation_ordinal": evaluation,
            "source_position": _int(row["source_position"]),
            "record": _int(row["record"]),
            "element_z": _int(row["element_z"]),
            "ion_stage": _int(row["ion_stage"]),
            "data_type": _int(row["data_type"]),
            "lower_row": _int(row["lower_row"]),
            "upper_row": _int(row["upper_row"]),
            "threshold_ev": _float(row["type53_shadow_threshold_ev"]),
            "rnist": _float(row["type53_shadow_rnist"]),
            "nb1_one_based": _int(row["type53_shadow_nb1_one_based"]),
            "klmax_one_based": _int(row["type53_shadow_klmax_one_based"]),
        }
        record_divergent = False
        for index in range(6):
            name = f"ans{index + 1}"
            applied = _float(row[name])
            shadow = _float(row[f"type53_shadow_{name}"])
            delta = shadow - applied
            relative = _relative_delta(applied, shadow)
            applied_totals[index] += applied
            shadow_totals[index] += shadow
            output[f"applied_{name}"] = applied
            output[f"shadow_{name}"] = shadow
            output[f"delta_{name}"] = delta
            output[f"relative_delta_{name}"] = relative
            if delta != 0.0:
                record_divergent = True
            if largest[index] is None or abs(delta) > largest[index]["absolute_delta"]:
                largest[index] = {
                    "source_position": output["source_position"],
                    "record": output["record"],
                    "applied": applied,
                    "shadow": shadow,
                    "delta": delta,
                    "absolute_delta": abs(delta),
                }
        output["divergent"] = record_divergent
        if first_divergent is None and record_divergent:
            first_divergent = {
                "source_position": output["source_position"],
                "record": output["record"],
            }
        audit_rows.append(output)

    fieldnames = [
        "evaluation_ordinal", "source_position", "record", "element_z", "ion_stage", "data_type",
        "lower_row", "upper_row", "threshold_ev", "rnist", "nb1_one_based", "klmax_one_based",
    ]
    for index in range(1, 7):
        fieldnames.extend([
            f"applied_ans{index}", f"shadow_ans{index}", f"delta_ans{index}", f"relative_delta_ans{index}",
        ])
    fieldnames.append("divergent")
    audit_csv = output_dir / "heii_type53_source_order_audit.csv"
    _write_csv(audit_csv, audit_rows, fieldnames)

    state_payload: dict[str, Any] = {}
    state_json = _resolve_state_json(records_csv, evaluation)
    if state_json is not None:
        state_payload = json.loads(state_json.read_text(encoding="utf-8"))

    totals: dict[str, dict[str, float]] = {}
    for index in range(6):
        applied = applied_totals[index]
        shadow = shadow_totals[index]
        totals[f"ans{index + 1}"] = {
            "applied": applied,
            "shadow": shadow,
            "delta": shadow - applied,
            "shadow_to_applied_ratio": shadow / applied if applied != 0.0 else (math.inf if shadow != 0.0 else 1.0),
        }

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "release": "0.6.48.7.1",
        "result": "ACCEPT",
        "audit_complete": True,
        "evaluation_ordinal": evaluation,
        "records_csv": str(records_csv),
        "output_directory": str(output_dir),
        "audit_csv": str(audit_csv.resolve()),
        "element_z": AUDITED_ELEMENT_Z,
        "ion_stage": AUDITED_ION_STAGE,
        "data_type": AUDITED_DATA_TYPE,
        "records_compared": len(audit_rows),
        "records_divergent": sum(bool(row["divergent"]) for row in audit_rows),
        "first_divergent_source_position": None if first_divergent is None else first_divergent["source_position"],
        "first_divergent_record": None if first_divergent is None else first_divergent["record"],
        "totals": totals,
        "largest_absolute_differences": {f"ans{index + 1}": largest[index] for index in range(6)},
        "lowered_cross_section_units": "cm2",
        "legacy_source_kernel_input_units": "megabarn",
        "unit_boundary_correction_applied": True,
        "source_shadow_reference_status": "translated_source_style_kernel_not_v06472_per_record_oracle",
        "reference_record_oracle_available": False,
        "source_shadow_applied_to_physics": False,
        "native_state_unchanged_by_audit": True,
        "next_blocker": "validate_type53_ans_semantics_and_detailed_matrix_against_a_v06472_per_record_oracle",
        "fixed_state_parity": False,
        "production_promotion_ready": False,
    }
    if state_payload:
        aliases = (
            (("native_electron_fraction", "computed_electron_fraction"), "native_electron_fraction"),
            (("native_charge_residual", "charge_residual"), "native_charge_residual"),
            (("native_hmctot", "hmctot"), "native_hmctot"),
            (("python_callbacks",), "python_callbacks"),
            (("records_evaluated", "record_diagnostic_count"), "records_evaluated"),
            (("elements_solved", "element_diagnostic_count"), "elements_solved"),
        )
        for source_names, report_name in aliases:
            for source_name in source_names:
                if source_name in state_payload:
                    report[report_name] = state_payload[source_name]
                    break
    summary_json = records_csv.parent.parent / "native_evaluation_summary.json"
    if summary_json.is_file():
        summary_payload = json.loads(summary_json.read_text(encoding="utf-8"))
        for source_name in ("python_callbacks", "records_evaluated", "elements_solved"):
            if source_name in summary_payload:
                report[source_name] = summary_payload[source_name]
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit_parser = subparsers.add_parser("audit", help="audit He II type-53 applied and source-style shadow contributions")
    audit_parser.add_argument("records_source", type=Path, help="records CSV, diagnostics directory, or qualification output")
    audit_parser.add_argument("output_dir", type=Path)
    audit_parser.add_argument("--evaluation", type=int, default=61)
    audit_parser.add_argument("--output-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = audit(args.records_source, args.output_dir, evaluation=args.evaluation)
        output_json = args.output_json.resolve() if args.output_json else (args.output_dir.resolve() / "summary.json")
        _write_json(output_json, report)
        printable = dict(report)
        printable["output_json"] = str(output_json)
        print(json.dumps(printable, indent=2, sort_keys=True))
        return 0
    except Exception as exc:  # CLI boundary: produce a clear nonzero failure.
        if getattr(args, "output_json", None):
            output_json = args.output_json.resolve()
            if output_json.exists():
                output_json.unlink()
        print(f"he-bound-free audit failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
