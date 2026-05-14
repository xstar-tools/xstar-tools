#!/usr/bin/env python3
"""Audit type-53 phint53 photoionization against live XSTAR bremsam(:).

This example consumes the live-rate-grid probe CSV produced by an instrumented
XSTAR run.  It recomputes the photoionization ans1 side of phint53.f90 on the
captured epim(:)/bremsam(:) rate grid and compares the result with preserved
full-global type-53 matrix photoionization rows.
"""

from __future__ import annotations

import argparse

from xstar_atomic.xstar_matrix_parity import (
    audit_type53_live_bremsam_phint53,
    write_type53_live_bremsam_phint53_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", default=None, help="example-56 benchmark directory with preserved solver products")
    parser.add_argument("--ion", default="O VII")
    parser.add_argument("--probe-csv", required=True, help="instrumented XSTAR live-rate-grid probe CSV")
    parser.add_argument("--probe-state", default="last", help="probe state to use: last, first, or 1-based index")
    parser.add_argument("--matrix-terms-csv", default=None)
    parser.add_argument("--adjacent-coupling-csv", default=None)
    parser.add_argument("--global-index-csv", default=None)
    parser.add_argument("--comparisons-csv", default=None)
    parser.add_argument("--triplet-only", action="store_true")
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--out-dir", default="xstar_type53_live_bremsam_phint53_audit")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = audit_type53_live_bremsam_phint53(
        benchmark_dir=args.benchmark_dir,
        ion=args.ion,
        probe_csv=args.probe_csv,
        probe_state=args.probe_state,
        matrix_terms_csv=args.matrix_terms_csv,
        adjacent_coupling_csv=args.adjacent_coupling_csv,
        global_index_csv=args.global_index_csv,
        comparisons_csv=args.comparisons_csv,
        triplet_only=args.triplet_only,
        max_records=args.max_records,
    )
    paths = write_type53_live_bremsam_phint53_audit(audit, args.out_dir)
    if args.print_summary:
        s = audit["summary"]
        print("XSTAR type-53 live-bremsam phint53 audit")
        print("-------------------------------------------")
        for key in [
            "audit_version",
            "ion",
            "probe_status",
            "n_probe_states",
            "probe_state_selector",
            "probe_state_selection_status",
            "probe_capture_index",
            "probe_zone_index",
            "probe_pass_index",
            "probe_ldir",
            "triplet_only",
            "n_type53_photoionization_records",
            "n_live_phint53_evaluated",
            "n_live_phint53_matches",
            "n_live_phint53_differs",
            "median_matrix_over_live_phint53_ans1",
            "p16_matrix_over_live_phint53_ans1",
            "p84_matrix_over_live_phint53_ans1",
            "n_live_epim",
            "live_epim_min_eV",
            "live_epim_max_eV",
            "status",
        ]:
            print(f"{key}={s.get(key)}")
        print("largest_records:")
        for row in s.get("top_records_by_abs_matrix_minus_live") or []:
            print(
                "  record={record} bound={bound_level_label} comp={triplet_component} "
                "matrix={matrix_photoionization_rate_s^-1} live={live_phint53_photo_ans1_s^-1} "
                "ratio={matrix_over_live_phint53_ans1} class={classification}".format(**row)
            )
        print(f"records_csv: {paths['records_csv']}")
        print(f"json: {paths['json']}")
        print(f"markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
