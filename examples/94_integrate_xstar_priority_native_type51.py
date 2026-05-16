#!/usr/bin/env python3
"""Integrate native type-51 terms into the priority conditional system."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_priority_native_type51_integration import (
    build_priority_native_type51_integration_audit,
    write_priority_native_type51_integration_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-matrix-balance-audit", required=True)
    parser.add_argument("--type51-native-parity-audit", required=True)
    parser.add_argument("--relative-population-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--replacement-population-delta-tolerance", type=float, default=5.0e-5)
    parser.add_argument("--relative-row-residual-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--rank-rcond", type=float, default=1.0e-12)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = build_priority_native_type51_integration_audit(
        priority_matrix_balance_audit=args.priority_matrix_balance_audit,
        type51_native_parity_audit=args.type51_native_parity_audit,
        relative_population_tolerance=args.relative_population_tolerance,
        replacement_population_delta_tolerance=args.replacement_population_delta_tolerance,
        relative_row_residual_tolerance=args.relative_row_residual_tolerance,
        rank_rcond=args.rank_rcond,
    )
    paths = write_priority_native_type51_integration_audit(args.out_dir, audit)
    if args.print_summary:
        print("XSTAR priority native type-51 integration audit")
        print("------------------------------------------------")
        summary = audit["summary"]
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "selection", "occurrence_rank", "population_stage",
            "n_population_rows", "n_selected_compact_rows",
            "selected_xstar_ipmat2_indices", "n_balance_record_terms",
            "n_type51_balance_terms", "n_type51_terms_replaced_with_native",
            "n_type51_terms_unmatched", "n_non_type51_probe_backed_terms",
            "n_type51_parity_terms", "n_type51_parity_terms_used",
            "n_type51_parity_terms_unused", "n_duplicate_type51_parity_exact_keys",
            "n_selected_rows_touched_by_native_type51",
            "n_selected_rows_not_touched_by_native_type51",
            "n_missing_population_columns", "probe_matrix_rank",
            "hybrid_matrix_rank", "matrix_dimension",
            "hybrid_scaled_matrix_condition_number", "hybrid_solve_method",
            "n_negative_hybrid_solution_rows",
            "max_abs_hybrid_captured_relative_row_residual",
            "max_abs_hybrid_vs_captured_relative_population_difference",
            "max_abs_hybrid_vs_all_probe_relative_population_difference",
            "max_abs_hybrid_linear_solve_relative_residual",
            "parent_fortran_priority_subset_row_balance_ready",
            "parent_native_type51_parity_ready",
            "native_type51_all_touching_terms_replaced",
            "native_type51_all_selected_rows_touched",
            "native_type51_selected_system_integration_ready",
            "hybrid_selected_system_contains_probe_backed_non_type51_terms",
            "native_priority_subset_matrix_closure_ready",
            "production_expanded_compact_solver_changed",
            "dominant_next_target", "type53_scale44_status",
        ]:
            print(f"{key}={summary.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
