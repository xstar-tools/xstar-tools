#!/usr/bin/env python3
"""Audit native XSTAR type-51 rates on the selected compact subsystem."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_type51_native_parity import (
    build_type51_native_parity_audit,
    write_type51_native_parity_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-matrix-closure-audit", required=True)
    parser.add_argument("--atdb", required=True, help="Path to XSTAR atdb.fits")
    parser.add_argument("--index-cache")
    parser.add_argument("--rebuild-index-cache", action="store_true")
    parser.add_argument("--relative-rate-tolerance", type=float, default=5.0e-5)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = build_type51_native_parity_audit(
        priority_matrix_closure_audit=args.priority_matrix_closure_audit,
        atdb_fits=args.atdb,
        relative_rate_tolerance=args.relative_rate_tolerance,
        index_cache_path=args.index_cache,
        rebuild_index_cache=args.rebuild_index_cache,
    )
    paths = write_type51_native_parity_audit(args.out_dir, audit)
    if args.print_summary:
        print("XSTAR native type-51 selected-block parity audit")
        print("------------------------------------------------")
        summary = audit["summary"]
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "selection", "occurrence_rank", "selected_xstar_ipmat2_indices",
            "relative_rate_tolerance", "atdb_fits", "atdb_status",
            "index_cache_status", "probe_density_semantics",
            "n_selected_type51_ucalc_records", "n_type51_records_decoded",
            "n_type51_records_native_evaluated",
            "n_type51_records_endpoint_order_match",
            "n_type51_records_rate_parity_pass",
            "n_type51_records_rate_parity_nonpass",
            "max_ans1_relative_difference", "max_ans2_relative_difference",
            "n_type51_compact_matrix_terms", "n_type51_compact_matrix_terms_match",
            "n_type51_compact_matrix_terms_nonmatch",
            "max_matrix_term_relative_difference",
            "n_type51_internal_compact_entries",
            "n_type51_internal_compact_entries_match",
            "n_type51_internal_compact_entries_nonmatch",
            "max_internal_entry_relative_difference",
            "n_selected_rows_touched_by_native_type51",
            "n_selected_rows_not_touched_by_native_type51",
            "native_type51_record_rate_parity_ready",
            "native_type51_compact_matrix_parity_ready",
            "native_type51_internal_block_assembly_ready",
            "native_priority_subset_matrix_closure_ready",
            "dominant_next_target",
        ]:
            print(f"{key}={summary.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
