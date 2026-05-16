#!/usr/bin/env python3
"""Build a compact XSTAR matrix-closure manifest for activated priority basis rows."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_priority_matrix_closure import (
    build_priority_matrix_closure_audit,
    write_priority_matrix_closure_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-basis-expansion", required=True)
    parser.add_argument("--ucalc-probe-csv")
    parser.add_argument("--matrix-probe-csv")
    parser.add_argument(
        "--occurrence-rank", type=int, default=-1,
        help="Per-record occurrence rank; -1 selects the latest occurrence and is recommended for full-element multi-ion manifests.",
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = build_priority_matrix_closure_audit(
        priority_basis_expansion=args.priority_basis_expansion,
        ucalc_probe_csv=args.ucalc_probe_csv,
        matrix_probe_csv=args.matrix_probe_csv,
        occurrence_rank=args.occurrence_rank,
    )
    paths = write_priority_matrix_closure_audit(args.out_dir, audit)
    if args.print_summary:
        summary = audit["summary"]
        print("XSTAR priority-subset matrix closure audit")
        print("--------------------------------------------")
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "selection", "occurrence_rank", "ucalc_probe_status", "matrix_probe_status",
            "element_jkk_ions", "n_all_elements_ucalc_records_selected_at_occurrence",
            "n_selected_element_ucalc_records_at_occurrence",
            "n_excluded_non_element_ucalc_records", "element_probe_filter_mode",
            "n_selected_compact_rows", "selected_xstar_ipmat2_indices",
            "n_selected_physical_roles", "n_selected_shared_alias_rows",
            "n_selected_ucalc_records", "n_selected_matrix_ucalc_records",
            "n_selected_nonmatrix_ucalc_metadata_records",
            "n_selected_records_with_expected_matrix_row_count",
            "n_selected_records_with_four_matrix_rows",
            "n_fortran_matrix_rows_loaded", "n_compact_matrix_terms_touching_selected_rows",
            "compact_endpoint_mapping_mode", "n_unmapped_matrix_endpoints",
            "n_selected_rows_with_fortran_matrix_terms",
            "n_selected_rows_without_fortran_matrix_terms", "n_rate_families",
            "priority_role_manifest_ready", "fortran_priority_subset_matrix_manifest_ready",
            "native_priority_subset_matrix_closure_ready", "dominant_next_target",
        ]:
            print(f"{key}={summary.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
