"""v0.6.48.7.40 final helium rate-family coefficient closure audit.

This qualification milestone closes the remaining Type-54, Type-57, Type-69,
Type-76, and Type-77 coefficient differences.  Dense-matrix cells that remain
non-exact after every aligned coefficient is exact are classified separately as
source/native accumulation-order differences.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.40"
SCHEMA = "xstar-tools-v0648740-final-rate-families-source-faithful-correction-v1"
SUMMARY = "call2_helium_solve_state_rate_matrix_decomposition_summary.json"
TARGET_TYPES = (54, 57, 69, 76, 77)
EXPECTED_COUNTS = {
    54: (29, 116),
    57: (74, 296),
    69: (6, 24),
    76: (5, 20),
    77: (74, 296),
}
TERM_FIELDS = ("metadata_key_exact", "aj1_exact", "aj2_exact", "cj_exact", "cj2_exact")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def integer(row: dict[str, str], key: str) -> int:
    try:
        return int(float(row.get(key, "0")))
    except (TypeError, ValueError):
        return 0


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
    term_rows = read_csv(args.output / "call2_he_metadata_keyed_term_comparison.csv")
    cell_rows = read_csv(args.output / "call2_he_remaining_matrix_cell_summary.csv")

    family_rows: list[dict[str, Any]] = []
    family_exact: dict[int, bool] = {}
    family_records: dict[int, list[int]] = {}
    for data_type in TARGET_TYPES:
        rows = [row for row in term_rows if integer(row, "data_type") == data_type]
        records = sorted({integer(row, "record") for row in rows})
        expected_records, expected_terms = EXPECTED_COUNTS[data_type]
        exact = len(records) == expected_records and len(rows) == expected_terms and rows_exact(rows)
        family_exact[data_type] = exact
        family_records[data_type] = records
        mismatch_fields = Counter()
        for row in rows:
            for field in TERM_FIELDS[1:]:
                if row.get(field) != "True":
                    mismatch_fields[field.removesuffix("_exact")] += 1
        family_rows.append({
            "data_type": data_type,
            "record_count": len(records),
            "expected_record_count": expected_records,
            "term_count": len(rows),
            "expected_term_count": expected_terms,
            "all_terms_exact": exact,
            "mismatched_aj1": mismatch_fields["aj1"],
            "mismatched_aj2": mismatch_fields["aj2"],
            "mismatched_cj": mismatch_fields["cj"],
            "mismatched_cj2": mismatch_fields["cj2"],
            "first_record": records[0] if records else 0,
            "last_record": records[-1] if records else 0,
        })
    write_csv(args.output / "call2_he_final_rate_family_exactness.csv", family_rows)

    record1947 = [
        row for row in term_rows
        if integer(row, "data_type") == 57 and integer(row, "record") == 1947
    ]
    record1947_exact = len(record1947) == 4 and rows_exact(record1947)

    type69_records_exact = family_exact[69] and family_records[69] == [1536, 1537, 1538, 1539, 1540, 1541]
    type77_exp10_records = [
        row for row in term_rows
        if integer(row, "data_type") == 77 and integer(row, "record") in (1962, 1963)
    ]
    type77_exp10_exact = len(type77_exp10_records) == 8 and rows_exact(type77_exp10_records)

    all_coefficients_exact = (
        len(term_rows) == 5232
        and all(row.get(field) == "True" for row in term_rows for field in TERM_FIELDS)
        and all(family_exact.values())
    )
    remaining_types = sorted({
        integer(row, "data_type") for row in term_rows
        if any(row.get(field) != "True" for field in TERM_FIELDS[1:])
    })
    accumulation_only = bool(cell_rows) and all(
        row.get("attribution_kind") == "ACCUMULATION_ORDER_SEQUENCE"
        and integer(row, "mismatched_contribution_count") == 0
        for row in cell_rows
    )
    matrix_cells = int(base.get("matrix_cells", 6084))
    matrix_exact = int(base.get("dense_matrix_exact_cells", 0))
    remaining_cells = matrix_cells - matrix_exact

    gates.update({
        "CALL2_HE_TYPE54_ALL_29_RECORD_TERMS_EXACT": "ACCEPT" if family_exact[54] else "REJECT",
        "CALL2_HE_TYPE54_SOURCE_KT_AND_ENERGY_CONSTANTS": "ACCEPT" if family_exact[54] else "REJECT",
        "CALL2_HE_TYPE54_THERMAL_CHANNEL_EXACT": "ACCEPT" if family_exact[54] else "REJECT",
        "CALL2_HE_TYPE57_RECORD1947_SOURCE_LOCAL_ZERO_GATE": "ACCEPT" if record1947_exact else "REJECT",
        "CALL2_HE_TYPE57_ALL_74_RECORD_TERMS_EXACT": "ACCEPT" if family_exact[57] else "REJECT",
        "CALL2_HE_TYPE57_RATE_MATRIX": "ACCEPT" if family_exact[57] else "REJECT",
        "CALL2_HE_TYPE69_SOURCE_Q_RATE_IEEE_ORDER": "ACCEPT" if type69_records_exact else "REJECT",
        "CALL2_HE_TYPE69_ALL_6_RECORD_TERMS_EXACT": "ACCEPT" if type69_records_exact else "REJECT",
        "CALL2_HE_TYPE69_RATE_MATRIX": "ACCEPT" if type69_records_exact else "REJECT",
        "CALL2_HE_TYPE76_ALL_5_RECORD_TERMS_EXACT": "ACCEPT" if family_exact[76] else "REJECT",
        "CALL2_HE_TYPE76_LEGACY_ENERGY_CONVERSION": "ACCEPT" if family_exact[76] else "REJECT",
        "CALL2_HE_TYPE76_THERMAL_CHANNEL_EXACT": "ACCEPT" if family_exact[76] else "REJECT",
        "CALL2_HE_TYPE77_FORTRAN_EXP10_AND_INTERPOLATION": "ACCEPT" if type77_exp10_exact else "REJECT",
        "CALL2_HE_TYPE77_ALL_74_RECORD_TERMS_EXACT": "ACCEPT" if family_exact[77] else "REJECT",
        "CALL2_HE_TYPE77_RATE_MATRIX": "ACCEPT" if family_exact[77] else "REJECT",
        "CALL2_HE_ALL_5232_RATE_TERMS_EXACT": "ACCEPT" if all_coefficients_exact else "REJECT",
        "CALL2_HE_ALL_RATE_FAMILY_COEFFICIENTS_EXACT": "ACCEPT" if all_coefficients_exact else "REJECT",
        "CALL2_HE_RATE_EVALUATION": "ACCEPT" if all_coefficients_exact else "REJECT",
        "CALL2_HE_FIRST_CAUSAL_RECORD_IDENTIFIED": "SUPERSEDED_ALL_RATE_FAMILIES_EXACT" if all_coefficients_exact else "REJECT",
        "CALL2_HE_REMAINING_COEFFICIENT_RESIDUAL_TYPES": "NONE" if not remaining_types else "REJECT",
        "CALL2_HE_REMAINING_RESIDUAL_TYPES_CONFIRMED": "ACCEPT" if not remaining_types else "REJECT",
        "CALL2_HE_REMAINING_64_CELL_DECOMPOSITION": "SUPERSEDED_BY_44_CELL_DECOMPOSITION",
        "CALL2_HE_REMAINING_44_CELL_DECOMPOSITION": "ACCEPT" if remaining_cells == 44 else "REJECT",
        "CALL2_HE_REMAINING_44_CELLS_ACCUMULATION_ORDER_ONLY": "ACCEPT" if remaining_cells == 44 and accumulation_only else "REJECT",
        "CALL2_HE_DENSE_MATRIX_ASSEMBLY": "REJECT_ACCUMULATION_ORDER_SEQUENCE" if remaining_cells else "ACCEPT",
        "CALL2_HE_MATRIX_SYSTEM_READY": "REJECT_ACCUMULATION_ORDER_SEQUENCE" if remaining_cells else "ACCEPT",
        "CALL2_HE_MATRIX_THERMAL_ACCUMULATION": "BLOCKED_BY_ACCUMULATION_ORDER_SEQUENCE" if remaining_cells else "ACCEPT",
        "CALL2_HE_FIXED_STATE_PARITY": f"BLOCKED_BY_{remaining_cells}_ACCUMULATION_ORDER_CELLS" if remaining_cells else "RUN_ALLOWED",
        "CALL2_HE_POST_SOLVE_POPULATION_EXACT": "BLOCKED_BY_ACCUMULATION_ORDER_SEQUENCE" if remaining_cells else "RUN_ALLOWED",
        "CALL2_HE_FINAL_OUTER_START_STATE": "BLOCKED_BY_ACCUMULATION_ORDER_SEQUENCE" if remaining_cells else "RUN_ALLOWED",
    })

    accepted = all((
        all_coefficients_exact,
        record1947_exact,
        type69_records_exact,
        type77_exp10_exact,
        not remaining_types,
        matrix_exact == 6040,
        remaining_cells == 44,
        accumulation_only,
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
            "Type-54 exact kT/energy constants; Type-57 source-local level gate; "
            "Type-69 calt69 and q-rate IEEE operation order; Type-76 legacy energy conversion; "
            "Type-77 source interpolation and FORTRAN exp10 semantics"
        ),
        "type54_record_count": len(family_records[54]),
        "type54_term_count": EXPECTED_COUNTS[54][1],
        "type54_all_terms_exact": family_exact[54],
        "type57_record_count": len(family_records[57]),
        "type57_term_count": EXPECTED_COUNTS[57][1],
        "type57_record1947_exact": record1947_exact,
        "type57_all_terms_exact": family_exact[57],
        "type69_record_count": len(family_records[69]),
        "type69_term_count": EXPECTED_COUNTS[69][1],
        "type69_all_terms_exact": family_exact[69],
        "type76_record_count": len(family_records[76]),
        "type76_term_count": EXPECTED_COUNTS[76][1],
        "type76_all_terms_exact": family_exact[76],
        "type77_record_count": len(family_records[77]),
        "type77_term_count": EXPECTED_COUNTS[77][1],
        "type77_exp10_records_exact": type77_exp10_exact,
        "type77_all_terms_exact": family_exact[77],
        "all_rate_terms_exact": all_coefficients_exact,
        "remaining_residual_data_types": remaining_types,
        "dense_matrix_exact_cells": matrix_exact,
        "remaining_incorrect_matrix_cells": remaining_cells,
        "remaining_matrix_cells_attribution": "ACCUMULATION_ORDER_SEQUENCE" if accumulation_only else "MIXED_OR_UNRESOLVED",
        "gates": gates,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
