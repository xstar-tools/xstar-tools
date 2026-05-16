#!/usr/bin/env python3
"""Integrate native type-50/type-71 terms after native type 51."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_priority_native_type50_type71_integration import (
    build_priority_native_type50_type71_integration_audit,
    write_priority_native_type50_type71_integration_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-native-type51-integration-audit", required=True)
    parser.add_argument("--type50-type71-native-parity-audit", required=True)
    parser.add_argument("--relative-population-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--replacement-population-delta-tolerance", type=float, default=5.0e-5)
    parser.add_argument("--relative-row-residual-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--rank-rcond", type=float, default=1.0e-12)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = build_priority_native_type50_type71_integration_audit(
        priority_native_type51_integration_audit=args.priority_native_type51_integration_audit,
        type50_type71_native_parity_audit=args.type50_type71_native_parity_audit,
        relative_population_tolerance=args.relative_population_tolerance,
        replacement_population_delta_tolerance=args.replacement_population_delta_tolerance,
        relative_row_residual_tolerance=args.relative_row_residual_tolerance,
        rank_rcond=args.rank_rcond,
    )
    paths = write_priority_native_type50_type71_integration_audit(args.out_dir, audit)
    if args.print_summary:
        print("XSTAR priority native type-50/type-71 integration audit")
        print("--------------------------------------------------------")
        summary = audit["summary"]
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "selection", "occurrence_rank", "population_stage",
            "n_population_rows_represented_by_term_columns",
            "n_selected_compact_rows", "selected_xstar_ipmat2_indices",
            "n_parent_record_terms", "n_type50_balance_terms",
            "n_type50_terms_replaced_with_native", "n_type50_terms_unmatched",
            "n_type71_balance_terms", "n_type71_terms_replaced_with_native",
            "n_type71_terms_unmatched", "n_non_type50_type71_terms",
            "n_remaining_probe_backed_terms", "n_duplicate_parity_exact_keys",
            "n_missing_population_columns", "probe_matrix_rank",
            "parent_native_type51_matrix_rank", "hybrid_matrix_rank",
            "matrix_dimension", "hybrid_scaled_matrix_condition_number",
            "hybrid_solve_method", "n_negative_hybrid_solution_rows",
            "n_hybrid_rows_passing_captured_balance",
            "max_abs_hybrid_captured_relative_row_residual",
            "n_hybrid_rows_within_population_tolerance",
            "max_abs_hybrid_vs_captured_relative_population_difference",
            "n_hybrid_rows_within_parent_delta_tolerance",
            "max_abs_hybrid_vs_parent_native_type51_relative_population_difference",
            "max_abs_hybrid_linear_solve_relative_residual",
            "parent_native_type51_selected_system_integration_ready",
            "parent_native_type50_type71_parity_ready",
            "native_type50_selected_system_integration_ready",
            "native_type71_selected_system_integration_ready",
            "native_type50_external_rhs_ready", "native_type71_external_rhs_ready",
            "native_type50_type71_external_rhs_ready",
            "native_type50_type71_selected_system_integration_ready",
            "hybrid_selected_system_contains_probe_backed_other_terms",
            "native_priority_subset_matrix_closure_ready",
            "production_expanded_compact_solver_changed",
            "dominant_next_target", "type53_scale44_status",
        ]:
            print(f"{key}={summary.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
