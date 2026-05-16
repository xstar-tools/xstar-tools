#!/usr/bin/env python3
"""Activate the highest-impact missing rows in an XSTAR full-element basis scaffold."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_priority_basis_expansion import (
    build_priority_basis_expansion,
    write_priority_basis_expansion,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-element-basis-scaffold", required=True)
    parser.add_argument("--target-population-coverage", type=float, default=0.999999)
    parser.add_argument("--max-additional-rows", type=int)
    parser.add_argument("--xstar-ipmat2-index", type=int, action="append", default=[])
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = build_priority_basis_expansion(
        full_element_basis_scaffold=args.full_element_basis_scaffold,
        target_population_coverage=args.target_population_coverage,
        max_additional_rows=args.max_additional_rows,
        explicit_xstar_ipmat2_indices=args.xstar_ipmat2_index,
    )
    paths = write_priority_basis_expansion(args.out_dir, audit)
    if args.print_summary:
        summary = audit["summary"]
        print("XSTAR priority full-element basis expansion")
        print("-------------------------------------------")
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "selection_mode", "target_population_coverage", "current_population_coverage",
            "n_selected_missing_rows", "selected_xstar_ipmat2_indices",
            "selected_population", "achieved_population_coverage",
            "target_population_coverage_met", "n_selected_shared_parent_rows",
            "n_selected_single_role_rows", "n_selected_nionp_blocks",
            "selected_nionp_blocks", "n_active_python_population_identities",
            "n_active_unique_compact_basis_rows", "n_deferred_missing_rows",
            "n_full_xstar_basis_rows", "priority_basis_expansion_ready",
            "native_priority_subset_matrix_closure_ready", "native_full_element_solver_ready",
            "dominant_next_target",
        ]:
            print(f"{key}={summary.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
