#!/usr/bin/env python3
"""Compare Python matrix rows against XSTAR ucalc/calc_hmc_ion probes."""

from __future__ import annotations

import argparse

from xstar_atomic.xstar_record_level_parity import (
    audit_record_level_matrix_parity,
    write_record_level_matrix_parity_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", required=True)
    parser.add_argument("--ion", required=True)
    parser.add_argument("--ucalc-probe-csv", required=True)
    parser.add_argument("--matrix-probe-csv", required=True)
    parser.add_argument("--matrix-terms-csv", default=None)
    parser.add_argument("--selection", default="latest-per-record", choices=["latest-per-record", "occurrence-rank"])
    parser.add_argument("--occurrence-rank", type=int, default=None, help="1-based common ucalc occurrence rank; use -1 for latest within each record")
    parser.add_argument("--scan-occurrence-ranks", action="store_true", help="scan common occurrence ranks and write a rank-selection diagnostic CSV")
    parser.add_argument("--max-occurrence-rank", type=int, default=None, help="optional cap for occurrence-rank scan")
    parser.add_argument("--out-dir", default="xstar_record_level_matrix_parity_audit")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    audit = audit_record_level_matrix_parity(
        benchmark_dir=args.benchmark_dir,
        ion=args.ion,
        ucalc_probe_csv=args.ucalc_probe_csv,
        matrix_probe_csv=args.matrix_probe_csv,
        matrix_terms_csv=args.matrix_terms_csv,
        selection=args.selection,
        occurrence_rank=args.occurrence_rank,
        scan_occurrence_ranks=args.scan_occurrence_ranks,
        max_occurrence_rank=args.max_occurrence_rank,
    )
    paths = write_record_level_matrix_parity_audit(out_dir=args.out_dir, audit=audit)
    s = audit["summary"]
    if args.print_summary:
        print("XSTAR record-level local matrix parity audit")
        print("------------------------------------------------")
        for key in [
            "audit_version",
            "ion",
            "status",
            "selection",
            "occurrence_rank",
            "scan_occurrence_ranks",
            "best_occurrence_rank_by_scan",
            "best_scan_median_abs_log10_ratio",
            "python_matrix_terms_csv",
            "ucalc_probe_csv",
            "matrix_probe_csv",
            "n_python_matrix_terms_with_record",
            "n_python_records",
            "n_python_records_with_fortran_ucalc",
            "n_python_records_without_fortran_ucalc",
            "n_python_records_with_selected_four_fortran_rows",
            "n_python_records_without_selected_four_fortran_rows",
            "n_fortran_self_check_pass_records",
            "n_fortran_self_check_nonpass_records",
            "n_family_rows",
            "n_python_proxy_or_scaffold_records",
            "median_python_over_fortran_abs_sum",
            "record_level_source_equivalent_ready",
        ]:
            print(f"{key}={s.get(key)}")
        print(f"record_summary_csv: {paths['record_summary_csv']}")
        print(f"family_summary_csv: {paths['family_summary_csv']}")
        print(f"occurrence_scan_csv: {paths['occurrence_scan_csv']}")
        print(f"json: {paths['json']}")
        print(f"markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
