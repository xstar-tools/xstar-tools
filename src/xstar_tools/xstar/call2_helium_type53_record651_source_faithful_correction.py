"""v0.6.48.7.39 Type-53 record 651 source-faithful correction audit."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.39"
SCHEMA = "xstar-tools-v0648738-type53-record651-source-faithful-correction-v1"
SUMMARY = "call2_helium_solve_state_rate_matrix_decomposition_summary.json"
TARGET_RECORD = 651
IEEE_RECORD = 688
ANS_FIELDS = tuple(f"ans{i}" for i in range(1, 7))
EXPECTED_REMAINING_TYPES = [54, 57, 69, 74, 76, 77, 95]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, "nan"))
    except (TypeError, ValueError):
        return math.nan


def integer(row: dict[str, str], key: str) -> int:
    try:
        return int(float(row.get(key, "0")))
    except (TypeError, ValueError):
        return 0


def exact(a: float, b: float) -> bool:
    return math.isfinite(a) and math.isfinite(b) and a == b


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    summary_path = args.output / SUMMARY
    base = json.loads(summary_path.read_text())
    gates = dict(base.get("gates", {}))

    source_rows = read_csv(args.source_capture / "v0472_call2_eval1_he_bound_free_records.csv")
    native_rows = read_csv(args.native_replay / "diagnostics/evaluation_0022_records.csv")
    term_rows = read_csv(args.output / "call2_he_source_order_term_comparison.csv")

    source = {
        integer(row, "record"): row
        for row in source_rows
        if integer(row, "data_type") == 53
    }
    native = {
        integer(row, "record"): row
        for row in native_rows
        if integer(row, "data_type") == 53 and integer(row, "element_z") == 2
    }

    comparisons: list[dict[str, Any]] = []
    exact_record_count = 0
    for record in sorted(source):
        sr = source[record]
        nr = native.get(record, {})
        row: dict[str, Any] = {
            "record": record,
            "source_present": True,
            "native_present": bool(nr),
        }
        answers_exact = bool(nr)
        for name in ANS_FIELDS:
            source_value = number(sr, name)
            native_value = number(nr, name)
            is_exact = exact(source_value, native_value)
            row[f"source_{name}"] = source_value
            row[f"native_{name}"] = native_value
            row[f"{name}_exact"] = is_exact
            answers_exact &= is_exact
        row["answers_exact"] = answers_exact
        row["source_threshold_ev"] = number(sr, "diag_threshold_eV")
        row["native_threshold_ev"] = number(nr, "type53_shadow_threshold_ev")
        row["threshold_exact"] = exact(row["source_threshold_ev"], row["native_threshold_ev"])
        row["source_rnist"] = number(sr, "diag_rnist")
        row["native_rnist"] = number(nr, "type53_shadow_rnist")
        row["rnist_exact"] = exact(row["source_rnist"], row["native_rnist"])
        row["sumc_ieee_nextafter_applied"] = integer(nr, "type53_sumc_ieee_nextafter_applied") == 1
        if answers_exact:
            exact_record_count += 1
        comparisons.append(row)
    write_csv(args.output / "call2_he_type53_record_comparison.csv", comparisons)

    sr651 = source.get(TARGET_RECORD, {})
    nr651 = native.get(TARGET_RECORD, {})
    sr688 = source.get(IEEE_RECORD, {})
    nr688 = native.get(IEEE_RECORD, {})

    context_fields = (
        ("threshold_eV", "type53_shadow_threshold_ev"),
        ("bound_energy_eV", "type53_shadow_bound_energy_ev"),
        ("destination_energy_eV", "type53_shadow_destination_energy_ev"),
        ("bound_statistical_weight", "type53_shadow_bound_g"),
        ("continuum_statistical_weight", "type53_shadow_continuum_g"),
        ("destination_statistical_weight", "type53_shadow_destination_g"),
        ("rnist", "type53_shadow_rnist"),
    )
    context_report: dict[str, Any] = {"record": TARGET_RECORD}
    context_exact = bool(sr651 and nr651)
    for source_suffix, native_field in context_fields:
        source_field = f"diag_{source_suffix}"
        source_value = number(sr651, source_field)
        native_value = number(nr651, native_field)
        field_exact = exact(source_value, native_value)
        context_report[f"source_{source_suffix}"] = source_value
        context_report[f"native_{source_suffix}"] = native_value
        context_report[f"{source_suffix}_exact"] = field_exact
        context_exact &= field_exact
    context_report["context_exact"] = context_exact
    (args.output / "call2_he_type53_record651_context.json").write_text(
        json.dumps(context_report, indent=2, sort_keys=True) + "\n"
    )

    record651_answers_exact = bool(sr651 and nr651) and all(
        exact(number(sr651, name), number(nr651, name)) for name in ANS_FIELDS
    )
    record688_answers_exact = bool(sr688 and nr688) and all(
        exact(number(sr688, name), number(nr688, name)) for name in ANS_FIELDS
    )
    record688_ieee = (
        record688_answers_exact
        and integer(nr688, "type53_sumc_ieee_nextafter_applied") == 1
    )

    record651_terms = [
        row for row in term_rows
        if integer(row, "data_type") == 53 and integer(row, "record") == TARGET_RECORD
    ]
    expected_roles = {"forward_gain", "reverse_gain", "forward_diag_loss", "reverse_diag_loss"}
    term_roles = {row.get("role", "") for row in record651_terms}
    all_term_fields_exact = len(record651_terms) == 4 and all(
        row.get(field) == "True"
        for row in record651_terms
        for field in ("metadata_key_exact", "aj1_exact", "aj2_exact", "cj_exact", "cj2_exact")
    )
    forward_diag = next(
        (row for row in record651_terms if row.get("role") == "forward_diag_loss"), {}
    )
    forward_diag_exact = (
        bool(forward_diag)
        and integer(forward_diag, "compact_row") == 2
        and integer(forward_diag, "compact_column") == 2
        and exact(number(forward_diag, "source_aj1"), number(forward_diag, "native_aj1"))
        and number(forward_diag, "source_aj1") == -number(sr651, "ans1")
    )
    row2_terms = [
        row for row in record651_terms
        if integer(row, "compact_row") == 2 or integer(row, "compact_column") == 2
    ]
    row2_terms_exact = (
        term_roles == expected_roles
        and all_term_fields_exact
        and len(row2_terms) == 3
        and {row.get("role", "") for row in row2_terms}
            == {"forward_gain", "reverse_gain", "forward_diag_loss"}
    )

    all_132 = len(source) == 132 and len(native) == 132 and exact_record_count == 132
    remaining_types = [int(value) for value in base.get("remaining_residual_data_types", [])]
    remaining_types_confirmed = remaining_types == EXPECTED_REMAINING_TYPES
    matrix_exact = int(base.get("dense_matrix_exact_cells", 0))
    matrix_cells = int(base.get("matrix_cells", 6084))
    remaining_cells = matrix_cells - matrix_exact
    type53_matrix_exact = gates.get("CALL2_HE_TYPE53_MATRIX_FIXED") == "ACCEPT"

    gates.update({
        "CALL2_HE_TYPE53_RECORD651_SOURCE_CONTEXT": "ACCEPT" if context_exact else "REJECT",
        "CALL2_HE_TYPE53_RECORD651_ANS1_TO_ANS6_EXACT": "ACCEPT" if record651_answers_exact else "REJECT",
        "CALL2_HE_TYPE53_RECORD651_FORWARD_DIAGONAL_LOSS": "ACCEPT" if forward_diag_exact else "REJECT",
        "CALL2_HE_TYPE53_RECORD651_ROW2_MATRIX_CONTRIBUTIONS": "ACCEPT" if row2_terms_exact else "REJECT",
        "CALL2_HE_TYPE53_RECORD688_IEEE_ACCUMULATION": "ACCEPT" if record688_ieee else "REJECT",
        "CALL2_HE_TYPE53_ALL_132_RECORD_ANSWERS_EXACT": "ACCEPT" if all_132 else "REJECT",
        "CALL2_HE_TYPE53_ROOT_CAUSE": "ACCEPT" if context_exact and record651_answers_exact else "REJECT",
        "CALL2_HE_TYPE53_RATE_MATRIX": "ACCEPT" if type53_matrix_exact and all_132 else "REJECT",
        "CALL2_HE_TYPE53_MATRIX_FIXED": "ACCEPT" if type53_matrix_exact and all_132 else "REJECT",
        "CALL2_HE_REMAINING_RESIDUAL_TYPES_CONFIRMED": "ACCEPT" if remaining_types_confirmed else "REJECT",
        "CALL2_HE_FIXED_STATE_PARITY": f"BLOCKED_BY_{remaining_cells}_MATRIX_CELLS" if remaining_cells else "RUN_ALLOWED",
    })

    accepted = all((
        context_exact,
        record651_answers_exact,
        forward_diag_exact,
        row2_terms_exact,
        record688_ieee,
        all_132,
        gates["CALL2_HE_TYPE53_RATE_MATRIX"] == "ACCEPT",
        matrix_exact == 5962,
        remaining_cells == 122,
        remaining_types_confirmed,
        base.get("metadata_keyed_matched_terms") == 5232,
        base.get("unmatched_source_terms") == 0,
        base.get("unmatched_native_terms") == 0,
    ))

    report = {
        **base,
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if accepted else "REJECT",
        "physics_changed": True,
        "physics_change_scope": (
            "Type-53 source current-ion continuum threshold/Saha context, destination statistical weight, "
            "persistent leveltemp destination semantics for record 651, and record 688 source IEEE sumc closure"
        ),
        "type53_target_record": TARGET_RECORD,
        "type53_ieee_record": IEEE_RECORD,
        "type53_source_record_count": len(source),
        "type53_native_record_count": len(native),
        "type53_exact_record_count": exact_record_count,
        "type53_record651_context_exact": context_exact,
        "type53_record651_answers_exact": record651_answers_exact,
        "type53_record651_forward_diagonal_loss_exact": forward_diag_exact,
        "type53_record651_row2_terms_exact": row2_terms_exact,
        "type53_record688_ieee_exact": record688_ieee,
        "dense_matrix_exact_cells": matrix_exact,
        "remaining_incorrect_matrix_cells": remaining_cells,
        "remaining_residual_data_types": remaining_types,
        "gates": gates,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
