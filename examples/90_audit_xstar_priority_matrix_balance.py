#!/usr/bin/env python3
"""Evaluate XSTAR steady-state row balance for activated priority compact rows."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_priority_matrix_balance import (
    build_priority_matrix_balance_audit,
    write_priority_matrix_balance_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-matrix-closure-audit", required=True)
    parser.add_argument("--population-closure-parity-audit", required=True)
    parser.add_argument("--population-stage", choices=("before", "after"), default="after")
    parser.add_argument("--relative-residual-tolerance", type=float, default=5.0e-3)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = build_priority_matrix_balance_audit(
        priority_matrix_closure_audit=args.priority_matrix_closure_audit,
        population_closure_parity_audit=args.population_closure_parity_audit,
        population_stage=args.population_stage,
        relative_residual_tolerance=args.relative_residual_tolerance,
    )
    paths = write_priority_matrix_balance_audit(args.out_dir, audit)
    if args.print_summary:
        print("XSTAR priority compact-matrix row-balance audit")
        print("------------------------------------------------")
        summary = audit["summary"]
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "selection", "occurrence_rank", "population_stage",
            "n_population_rows", "population_sum", "n_selected_compact_rows",
            "selected_xstar_ipmat2_indices", "n_record_level_matrix_terms",
            "n_unique_compact_matrix_entries", "n_missing_population_columns",
            "relative_residual_tolerance", "n_selected_rows_passing_balance",
            "n_selected_rows_not_passing_balance", "max_abs_relative_row_residual",
            "fortran_priority_subset_matrix_manifest_ready",
            "population_vector_complete_for_manifest",
            "fortran_priority_subset_row_balance_ready",
            "native_priority_subset_matrix_closure_ready", "dominant_next_target",
        ]:
            print(f"{key}={summary.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
