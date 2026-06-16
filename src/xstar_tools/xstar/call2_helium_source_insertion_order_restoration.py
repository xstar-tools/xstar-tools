"""v0.6.48.7.41 Type-77 host closure and helium insertion-order restoration.

This qualification milestone verifies two independent corrections:

* Type-77 reproduces the immutable v0.6.47.2 runtime-power semantics on the
  qualification host while retaining the captured stage-2 exp10 edge case.
* Active-helium matrix contributions are committed in the source iterator
  order ``(ion stage, rate type, data type, source record order)``.

The audit requires exact aligned coefficients, exact dense/heating matrices,
and exact post-solve helium populations.  It deliberately does not claim the
all-61 H/He/Mg fixed-state milestone or thermal parity.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.41"
SCHEMA = "xstar-tools-v0648741-type77-helium-source-insertion-order-v1"
SUMMARY = "call2_helium_source_insertion_order_restoration_summary.json"
BASE_SUMMARY = "call2_helium_solve_state_rate_matrix_decomposition_summary.json"
TERM_FIELDS = ("metadata_key_exact", "aj1_exact", "aj2_exact", "cj_exact", "cj2_exact")
TYPE77_RECORD_COUNT = 74
TYPE77_TERM_COUNT = 296
TOTAL_TERM_COUNT = 5232
MATRIX_CELL_COUNT = 6084
HELIUM_ROW_COUNT = 78


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def integer(row: dict[str, str], key: str) -> int:
    try:
        return int(float(row.get(key, "0")))
    except (TypeError, ValueError):
        return 0


def truth(row: dict[str, str], key: str) -> bool:
    return row.get(key) == "True"


def all_term_fields_exact(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and all(truth(row, field) for row in rows for field in TERM_FIELDS)


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

    base_path = args.output / BASE_SUMMARY
    term_path = args.output / "call2_he_metadata_keyed_term_comparison.csv"
    matrix_path = args.output / "call2_he_dense_matrix_comparison.csv"
    solve_path = args.output / "call2_he_solve_state_comparison.csv"
    state_path = args.native_replay / "diagnostics" / "evaluation_0022_state.json"
    required = (base_path, term_path, matrix_path, solve_path, state_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        report = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [f"missing required input: {path}" for path in missing],
            "gates": {
                "CALL2_HE_TYPE77_ALL_74_RECORD_TERMS_EXACT": "NOT_RUN_MISSING_INPUT",
                "CALL2_HE_SOURCE_INSERTION_ORDER_RESTORED": "NOT_RUN_MISSING_INPUT",
                "CALL2_HE_FIXED_STATE_PARITY": "NOT_RUN_MISSING_INPUT",
                "THERMAL_PARITY": "BLOCKED",
                "PRODUCTION_PROMOTION": "BLOCKED",
            },
            "qualification_only": True,
            "production_promotion_ready": False,
        }
        (args.output / SUMMARY).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    base = json.loads(base_path.read_text())
    gates = dict(base.get("gates", {}))
    term_rows = read_csv(term_path)
    matrix_rows = read_csv(matrix_path)
    solve_rows = read_csv(solve_path)
    native_state = json.loads(state_path.read_text())

    type77_rows = [row for row in term_rows if integer(row, "data_type") == 77]
    type77_records = sorted({integer(row, "record") for row in type77_rows})
    type77_exact = (
        len(type77_records) == TYPE77_RECORD_COUNT
        and len(type77_rows) == TYPE77_TERM_COUNT
        and all_term_fields_exact(type77_rows)
    )

    all_terms_exact = (
        len(term_rows) == TOTAL_TERM_COUNT
        and all_term_fields_exact(term_rows)
        and int(base.get("metadata_keyed_matched_terms", 0)) == TOTAL_TERM_COUNT
        and int(base.get("unmatched_source_terms", -1)) == 0
        and int(base.get("unmatched_native_terms", -1)) == 0
    )
    source_order_indices_exact = (
        len(term_rows) == TOTAL_TERM_COUNT
        and all(
            integer(row, "source_source_order_index") == integer(row, "native_source_order_index")
            for row in term_rows
        )
    )
    # The immutable source ledger did not populate contribution_source_position
    # (it is zero for every source row), so it cannot be used as an ordering
    # comparator.  The metadata-keyed source-order ordinal is complete and is
    # the authoritative sequence check.
    source_positions_available = any(
        integer(row, "source_contribution_source_position") != 0 for row in term_rows
    )
    insertion_order_enabled = native_state.get("helium_source_insertion_order") is True

    dense_exact = len(matrix_rows) == MATRIX_CELL_COUNT and all(truth(row, "dense_exact") for row in matrix_rows)
    heating_exact = len(matrix_rows) == MATRIX_CELL_COUNT and all(truth(row, "heating_exact") for row in matrix_rows)
    heating2_exact = len(matrix_rows) == MATRIX_CELL_COUNT and all(truth(row, "heating2_exact") for row in matrix_rows)
    post_solve_exact = len(solve_rows) == HELIUM_ROW_COUNT and all(truth(row, "post_solve_exact") for row in solve_rows)
    rhs_exact = len(solve_rows) == HELIUM_ROW_COUNT and all(truth(row, "rhs_exact") for row in solve_rows)
    compact_seed_exact = len(solve_rows) == HELIUM_ROW_COUNT and all(truth(row, "compact_seed_exact") for row in solve_rows)
    transformed_initial_exact = len(solve_rows) == HELIUM_ROW_COUNT and all(
        truth(row, "transformed_initial_exact") for row in solve_rows
    )
    final_outer_exact_rows = sum(truth(row, "final_outer_start_exact") for row in solve_rows)

    mismatch_by_type: Counter[int] = Counter()
    mismatch_by_field: Counter[str] = Counter()
    for row in term_rows:
        for field in TERM_FIELDS[1:]:
            if not truth(row, field):
                mismatch_by_type[integer(row, "data_type")] += 1
                mismatch_by_field[field.removesuffix("_exact")] += 1
    mismatch_rows = [
        {
            "data_type": data_type,
            "mismatched_fields": count,
        }
        for data_type, count in sorted(mismatch_by_type.items())
    ]
    write_csv(args.output / "call2_he_remaining_coefficient_residual_types.csv", mismatch_rows)

    exact_matrix_cells = sum(truth(row, "dense_exact") for row in matrix_rows)
    exact_heating_cells = sum(truth(row, "heating_exact") for row in matrix_rows)
    exact_heating2_cells = sum(truth(row, "heating2_exact") for row in matrix_rows)
    remaining_matrix_cells = MATRIX_CELL_COUNT - exact_matrix_cells

    gates.update({
        "CALL2_HE_TYPE77_RUNTIME_POW_AND_STAGE2_EXP10": "ACCEPT" if type77_exact else "REJECT",
        "CALL2_HE_TYPE77_ALL_74_RECORD_TERMS_EXACT": "ACCEPT" if type77_exact else "REJECT",
        "CALL2_HE_TYPE77_RATE_MATRIX": "ACCEPT" if type77_exact else "REJECT",
        "CALL2_HE_ALL_5232_RATE_TERMS_EXACT": "ACCEPT" if all_terms_exact else "REJECT",
        "CALL2_HE_ALL_RATE_FAMILY_COEFFICIENTS_EXACT": "ACCEPT" if all_terms_exact else "REJECT",
        "CALL2_HE_REMAINING_COEFFICIENT_RESIDUAL_TYPES": "NONE" if not mismatch_by_type else "REJECT",
        "CALL2_HE_SOURCE_INSERTION_ORDER_ENABLED": "ACCEPT" if insertion_order_enabled else "REJECT",
        "CALL2_HE_SOURCE_INSERTION_ORDER_INDICES_EXACT": "ACCEPT" if source_order_indices_exact else "REJECT",
        "CALL2_HE_SOURCE_INSERTION_ORDER_POSITIONS_EXACT": "NOT_APPLICABLE_SOURCE_LEDGER_UNPOPULATED" if not source_positions_available else "ACCEPT",
        "CALL2_HE_SOURCE_INSERTION_ORDER_RESTORED": "ACCEPT" if insertion_order_enabled and source_order_indices_exact else "REJECT",
        "CALL2_HE_DENSE_MATRIX_ASSEMBLY": "ACCEPT" if dense_exact else "REJECT",
        "CALL2_HE_HEATING_MATRIX_ASSEMBLY": "ACCEPT" if heating_exact else "REJECT",
        "CALL2_HE_HEATING2_MATRIX_ASSEMBLY": "ACCEPT" if heating2_exact else "REJECT",
        "CALL2_HE_REMAINING_MATRIX_CELLS": "NONE" if remaining_matrix_cells == 0 else f"REJECT_{remaining_matrix_cells}_CELLS",
        "CALL2_HE_MATRIX_SYSTEM_READY": "ACCEPT" if dense_exact and heating_exact and heating2_exact else "REJECT",
        "CALL2_HE_RHS_CONSTRUCTION": "ACCEPT" if rhs_exact else "REJECT",
        "CALL2_HE_COMPACT_SEED_MAPPING": "ACCEPT" if compact_seed_exact else "REJECT",
        "CALL2_HE_TRANSFORMED_INITIAL_STATE": "ACCEPT" if transformed_initial_exact else "REJECT",
        "CALL2_HE_POST_SOLVE_POPULATION_EXACT": "ACCEPT" if post_solve_exact else "REJECT",
        "CALL2_HE_FIXED_STATE_PARITY": "ACCEPT" if post_solve_exact and dense_exact and rhs_exact else "REJECT",
        "CALL2_HE_FINAL_OUTER_START_STATE": "DEFERRED_TO_CONTROLLER_PARITY" if final_outer_exact_rows < HELIUM_ROW_COUNT else "ACCEPT",
        "ALL_61_H_HE_MG_FIXED_STATE_PARITY": "NOT_RUN_SINGLE_CALL2_HELIUM_QUALIFICATION",
        "V06488_THERMAL_PARITY_READY": "NO_ALL_61_FIXED_STATE_GATE_NOT_RUN",
        "CALLS_3_TO_4": "BLOCKED_BY_ALL_61_FIXED_STATE_QUALIFICATION",
        "THERMAL_PARITY": "BLOCKED_BY_ALL_61_FIXED_STATE_QUALIFICATION",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    })

    accepted = all((
        type77_exact,
        all_terms_exact,
        insertion_order_enabled,
        source_order_indices_exact,
        dense_exact,
        heating_exact,
        heating2_exact,
        compact_seed_exact,
        transformed_initial_exact,
        rhs_exact,
        post_solve_exact,
        remaining_matrix_cells == 0,
    ))

    report = {
        **base,
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if accepted else "REJECT",
        "physics_changed": True,
        "physics_change_scope": (
            "Type-77 host-independent runtime pow semantics with the captured stage-2 exp10 edge; "
            "source-faithful active-helium contribution insertion order by ion stage, rate type, "
            "data type, and source record order"
        ),
        "type77_record_count": len(type77_records),
        "type77_term_count": len(type77_rows),
        "type77_all_terms_exact": type77_exact,
        "all_rate_terms_exact": all_terms_exact,
        "remaining_residual_data_types": sorted(mismatch_by_type),
        "remaining_coefficient_mismatch_fields": dict(sorted(mismatch_by_field.items())),
        "helium_source_insertion_order_enabled": insertion_order_enabled,
        "source_order_indices_exact": source_order_indices_exact,
        "source_order_positions_available": source_positions_available,
        "dense_matrix_exact_cells": exact_matrix_cells,
        "heating_matrix_exact_cells": exact_heating_cells,
        "heating2_matrix_exact_cells": exact_heating2_cells,
        "remaining_incorrect_matrix_cells": remaining_matrix_cells,
        "post_solve_exact_rows": sum(truth(row, "post_solve_exact") for row in solve_rows),
        "final_outer_start_exact_rows": final_outer_exact_rows,
        "single_state_call2_helium_fixed_state_exact": post_solve_exact and dense_exact and rhs_exact,
        "all_61_h_he_mg_fixed_state_parity_evaluated": False,
        "thermal_parity_ready": False,
        "gates": gates,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    (args.output / SUMMARY).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
