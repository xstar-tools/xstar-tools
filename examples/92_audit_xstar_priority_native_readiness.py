#!/usr/bin/env python3
"""Rank native-rate implementation priorities for the selected compact subsystem."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_priority_native_readiness import (
    build_priority_native_readiness_audit,
    write_priority_native_readiness_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-conditional-solve-audit", required=True)
    parser.add_argument("--priority-matrix-balance-audit")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = build_priority_native_readiness_audit(
        priority_conditional_solve_audit=args.priority_conditional_solve_audit,
        priority_matrix_balance_audit=args.priority_matrix_balance_audit,
    )
    paths = write_priority_native_readiness_audit(args.out_dir, audit)
    if args.print_summary:
        print("XSTAR priority native-assembly readiness audit")
        print("-----------------------------------------------")
        summary = audit["summary"]
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "selected_xstar_ipmat2_indices", "n_selected_compact_rows",
            "conditional_solve_ready", "record_terms_status",
            "n_internal_rate_families", "n_external_rhs_rate_families",
            "internal_absolute_population_weighted_total",
            "external_rhs_absolute_population_weighted_total",
            "dominant_internal_family", "dominant_internal_family_fraction",
            "dominant_external_rhs_family", "dominant_external_rhs_family_fraction",
            "internal_top4_cumulative_fraction", "external_top3_cumulative_fraction",
            "native_priority_subset_rate_assembly_ready",
            "native_priority_subset_matrix_closure_ready",
            "type53_scale44_status", "dominant_next_target",
        ]:
            print(f"{key}={summary.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
