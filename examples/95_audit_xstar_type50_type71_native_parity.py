#!/usr/bin/env python3
"""Audit native XSTAR type-50 and type-71 rates on the priority subsystem."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_type50_type71_native_parity import (
    build_type50_type71_native_parity_audit,
    write_type50_type71_native_parity_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-matrix-closure-audit", required=True)
    parser.add_argument("--atdb", required=True, help="Path to XSTAR atdb.fits")
    parser.add_argument(
        "--type50-radiation-context-csv",
        help=(
            "Optional same-capture type-50 radiation context with record, "
            "capture_index, and bremsa_nb1. It is unnecessary when cfrac=1."
        ),
    )
    parser.add_argument("--index-cache")
    parser.add_argument("--rebuild-index-cache", action="store_true")
    parser.add_argument("--relative-rate-tolerance", type=float, default=5.0e-5)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = build_type50_type71_native_parity_audit(
        priority_matrix_closure_audit=args.priority_matrix_closure_audit,
        atdb_fits=args.atdb,
        type50_radiation_context_csv=args.type50_radiation_context_csv,
        relative_rate_tolerance=args.relative_rate_tolerance,
        index_cache_path=args.index_cache,
        rebuild_index_cache=args.rebuild_index_cache,
    )
    paths = write_type50_type71_native_parity_audit(args.out_dir, audit)
    if args.print_summary:
        print("XSTAR native type-50/type-71 selected-system parity audit")
        print("----------------------------------------------------------")
        summary = audit["summary"]
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "selection", "occurrence_rank", "selected_xstar_ipmat2_indices",
            "relative_rate_tolerance", "atdb_fits", "atdb_status",
            "index_cache_status", "probe_density_semantics",
            "type50_radiation_context_source", "type50_radiation_policy",
            "n_selected_type50_ucalc_records", "n_selected_type71_ucalc_records",
            "n_type50_records_decoded", "n_type71_records_decoded",
            "n_type50_records_rate_parity_pass", "n_type71_records_rate_parity_pass",
            "n_type50_compact_matrix_terms", "n_type50_compact_matrix_terms_match",
            "n_type71_compact_matrix_terms", "n_type71_compact_matrix_terms_match",
            "native_type50_selected_system_parity_ready",
            "native_type71_selected_system_parity_ready",
            "native_type50_type71_selected_system_parity_ready",
            "native_priority_subset_matrix_closure_ready", "dominant_next_target",
        ]:
            print(f"{key}={summary.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
