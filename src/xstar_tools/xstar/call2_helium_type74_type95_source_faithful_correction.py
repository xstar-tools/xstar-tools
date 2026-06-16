"""v0.6.48.7.39 Type-74/Type-95 correction and Type-53 host IEEE hotfix audit."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.39"
SCHEMA = "xstar-tools-v0648739-type74-type95-source-faithful-correction-v1"
SUMMARY = "call2_helium_solve_state_rate_matrix_decomposition_summary.json"
TYPE53_IEEE_RECORD = 688
TYPE74_TARGET_RECORD = 757
TYPE95_TARGET_RECORD = 1585
EXPECTED_REMAINING_TYPES = [54, 57, 69, 76, 77]
ANS_FIELDS = tuple(f"ans{i}" for i in range(1, 7))
TERM_FIELDS = ("metadata_key_exact", "aj1_exact", "aj2_exact", "cj_exact", "cj2_exact")


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


def rows_exact(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and all(row.get(field) == "True" for row in rows for field in TERM_FIELDS)


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
    bound_free = read_csv(args.output / "call2_he_bound_free_record_answer_comparison.csv")

    source_by_key = {
        (integer(row, "data_type"), integer(row, "record")): row
        for row in source_rows
    }
    native_by_key = {
        (integer(row, "data_type"), integer(row, "record")): row
        for row in native_rows if integer(row, "element_z") == 2
    }

    type53_source = source_by_key.get((53, TYPE53_IEEE_RECORD), {})
    type53_native = native_by_key.get((53, TYPE53_IEEE_RECORD), {})
    type53_ieee_exact = bool(type53_source and type53_native) and all(
        exact(number(type53_source, field), number(type53_native, field)) for field in ANS_FIELDS
    )

    type74_terms = [row for row in term_rows if integer(row, "data_type") == 74]
    type74_records = sorted({integer(row, "record") for row in type74_terms})
    type74_all_terms_exact = len(type74_terms) == 168 and len(type74_records) == 42 and rows_exact(type74_terms)
    type74_target_terms = [row for row in type74_terms if integer(row, "record") == TYPE74_TARGET_RECORD]
    type74_target_roles = {row.get("role", "") for row in type74_target_terms}
    type74_target_exact = (
        len(type74_target_terms) == 4
        and type74_target_roles == {"forward_gain", "reverse_gain", "forward_diag_loss", "reverse_diag_loss"}
        and rows_exact(type74_target_terms)
    )
    type74_target_forward = next((row for row in type74_target_terms if row.get("role") == "forward_gain"), {})
    type74_target_diag = next((row for row in type74_target_terms if row.get("role") == "forward_diag_loss"), {})
    type74_target_rate_exact = (
        bool(type74_target_forward and type74_target_diag)
        and exact(number(type74_target_forward, "source_aj1"), number(type74_target_forward, "native_aj1"))
        and exact(number(type74_target_diag, "source_aj1"), number(type74_target_diag, "native_aj1"))
        and number(type74_target_diag, "source_aj1") == -number(type74_target_forward, "source_aj1")
    )

    type95_rows = [row for row in bound_free if integer(row, "data_type") == 95]
    type95_exact_count = sum(row.get("record_answers_exact") == "True" for row in type95_rows)
    type95_all_answers_exact = len(type95_rows) == 2 and type95_exact_count == 2
    type95_target = next((row for row in type95_rows if integer(row, "record") == TYPE95_TARGET_RECORD), {})
    type95_target_exact = bool(type95_target) and type95_target.get("record_answers_exact") == "True"
    type95_terms = [row for row in term_rows if integer(row, "data_type") == 95]
    type95_terms_exact = len(type95_terms) == 8 and rows_exact(type95_terms)

    comparison_rows: list[dict[str, Any]] = []
    for record in type74_records:
        rr = [row for row in type74_terms if integer(row, "record") == record]
        comparison_rows.append({
            "data_type": 74,
            "record": record,
            "term_count": len(rr),
            "terms_exact": rows_exact(rr),
            "source_ans1": number(next((r for r in rr if r.get("role") == "forward_gain"), {}), "source_aj1"),
            "native_ans1": number(next((r for r in rr if r.get("role") == "forward_gain"), {}), "native_aj1"),
        })
    for row in type95_rows:
        comparison_rows.append({
            "data_type": 95,
            "record": integer(row, "record"),
            "term_count": 4,
            "terms_exact": rows_exact([r for r in type95_terms if integer(r, "record") == integer(row, "record")]),
            "answers_exact": row.get("record_answers_exact") == "True",
            **{f"source_{field}": number(row, f"source_{field}") for field in ANS_FIELDS},
            **{f"native_{field}": number(row, f"native_{field}") for field in ANS_FIELDS},
        })
    write_csv(args.output / "call2_he_type74_type95_record_comparison.csv", comparison_rows)

    remaining_types = [int(value) for value in base.get("remaining_residual_data_types", [])]
    remaining_types_confirmed = remaining_types == EXPECTED_REMAINING_TYPES
    matrix_exact = int(base.get("dense_matrix_exact_cells", 0))
    matrix_cells = int(base.get("matrix_cells", 6084))
    remaining_cells = matrix_cells - matrix_exact
    type74_absent = 74 not in remaining_types
    type95_absent = 95 not in remaining_types
    type53_absent = 53 not in remaining_types

    gates.update({
        "CALL2_HE_TYPE53_RECORD688_HOST_IEEE_CANONICALIZATION": "ACCEPT" if type53_ieee_exact else "REJECT",
        "CALL2_HE_TYPE53_RECORD688_IEEE_ACCUMULATION": "ACCEPT" if type53_ieee_exact else "REJECT",
        "CALL2_HE_TYPE53_ALL_132_RECORD_ANSWERS_EXACT": "ACCEPT" if type53_absent and gates.get("CALL2_HE_TYPE53_ALL_132_RECORD_ANSWERS_EXACT") == "ACCEPT" else "REJECT",
        "CALL2_HE_TYPE53_RATE_MATRIX": "ACCEPT" if type53_absent else "REJECT",
        "CALL2_HE_TYPE53_MATRIX_FIXED": "ACCEPT" if type53_absent else "REJECT",
        "CALL2_HE_TYPE74_RECORD757_REDUCED_RADIATION": "ACCEPT" if type74_target_rate_exact else "REJECT",
        "CALL2_HE_TYPE74_RECORD757_MATRIX_TERMS": "ACCEPT" if type74_target_exact else "REJECT",
        "CALL2_HE_TYPE74_ALL_42_RECORD_TERMS_EXACT": "ACCEPT" if type74_all_terms_exact else "REJECT",
        "CALL2_HE_TYPE74_RATE_MATRIX": "ACCEPT" if type74_all_terms_exact and type74_absent else "REJECT",
        "CALL2_HE_TYPE95_RECORD1585_ANS1_TO_ANS6_EXACT": "ACCEPT" if type95_target_exact else "REJECT",
        "CALL2_HE_TYPE95_ALL_2_RECORD_ANSWERS_EXACT": "ACCEPT" if type95_all_answers_exact else "REJECT",
        "CALL2_HE_TYPE95_LEGACY_TEMPERATURE_AND_ENERGY_CONSTANTS": "ACCEPT" if type95_target_exact and type95_all_answers_exact else "REJECT",
        "CALL2_HE_TYPE95_RATE_MATRIX": "ACCEPT" if type95_all_answers_exact and type95_terms_exact and type95_absent else "REJECT",
        "CALL2_HE_BOUND_FREE_SUBSYSTEM_EXACT": "ACCEPT" if type53_absent and type95_absent else "REJECT",
        "CALL2_HE_FIRST_BOUND_FREE_CAUSAL_RECORD_IDENTIFIED": "SUPERSEDED_BOUND_FREE_SUBSYSTEM_EXACT" if type53_absent and type95_absent else "REJECT",
        "CALL2_HE_REMAINING_122_CELL_DECOMPOSITION": "SUPERSEDED_BY_64_CELL_DECOMPOSITION",
        "CALL2_HE_REMAINING_64_CELL_DECOMPOSITION": "ACCEPT" if remaining_cells == 64 else "REJECT",
        "CALL2_HE_REMAINING_RESIDUAL_TYPES_CONFIRMED": "ACCEPT" if remaining_types_confirmed else "REJECT",
        "CALL2_HE_FIXED_STATE_PARITY": f"BLOCKED_BY_{remaining_cells}_MATRIX_CELLS" if remaining_cells else "RUN_ALLOWED",
    })

    accepted = all((
        type53_ieee_exact,
        type53_absent,
        type74_target_exact,
        type74_target_rate_exact,
        type74_all_terms_exact,
        type74_absent,
        type95_target_exact,
        type95_all_answers_exact,
        type95_terms_exact,
        type95_absent,
        remaining_types_confirmed,
        matrix_exact == 6020,
        remaining_cells == 64,
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
            "Type-53 record 688 host-independent immutable-reference IEEE canonicalization; "
            "Type-74 source 999-bin epim/bremsam reconstruction; Type-95 legacy scaled-temperature "
            "and collision-energy constants"
        ),
        "type53_record688_host_ieee_exact": type53_ieee_exact,
        "type74_target_record": TYPE74_TARGET_RECORD,
        "type74_record_count": len(type74_records),
        "type74_term_count": len(type74_terms),
        "type74_record757_exact": type74_target_exact,
        "type74_all_terms_exact": type74_all_terms_exact,
        "type95_target_record": TYPE95_TARGET_RECORD,
        "type95_record_count": len(type95_rows),
        "type95_exact_record_count": type95_exact_count,
        "type95_record1585_exact": type95_target_exact,
        "type95_all_terms_exact": type95_terms_exact,
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
