#!/usr/bin/env python3
"""Conditionally solve activated compact rows with external XSTAR populations fixed."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_priority_conditional_solve import (
    build_priority_conditional_solve_audit,
    write_priority_conditional_solve_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-matrix-balance-audit", required=True)
    parser.add_argument("--relative-population-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--rank-rcond", type=float, default=1.0e-12)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = build_priority_conditional_solve_audit(
        priority_matrix_balance_audit=args.priority_matrix_balance_audit,
        relative_population_tolerance=args.relative_population_tolerance,
        rank_rcond=args.rank_rcond,
    )
    paths = write_priority_conditional_solve_audit(args.out_dir, audit)
    if args.print_summary:
        print("XSTAR priority conditional compact solve audit")
        print("------------------------------------------------")
        summary = audit["summary"]
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "selection", "occurrence_rank", "population_stage",
            "n_population_rows", "n_selected_compact_rows",
            "selected_xstar_ipmat2_indices", "n_fixed_external_population_rows",
            "n_internal_aggregated_matrix_entries",
            "n_external_aggregated_matrix_entries", "n_missing_population_columns",
            "matrix_rank", "matrix_dimension", "scaled_matrix_condition_number",
            "solve_method", "n_negative_solution_rows",
            "captured_selected_population_sum", "conditional_solved_population_sum",
            "selected_population_sum_relative_difference",
            "max_abs_relative_population_difference",
            "l1_relative_population_difference", "l2_relative_population_difference",
            "relative_population_tolerance",
            "n_selected_rows_within_population_tolerance",
            "n_selected_rows_outside_population_tolerance",
            "max_abs_conditional_linear_solve_relative_residual",
            "fortran_priority_subset_row_balance_ready",
            "fortran_priority_subset_conditional_solve_ready",
            "native_priority_subset_matrix_closure_ready", "dominant_next_target",
        ]:
            print(f"{key}={summary.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
