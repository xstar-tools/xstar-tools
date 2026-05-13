#!/usr/bin/env python3
"""Audit whether type-53 detail phint53 residuals are scale-like.

This script consumes the records CSV from example 67.  It does not alter solver
physics and does not claim XSTAR call-site parity.  It asks a narrower question:
after recomputing ``phint53`` ans1 on the reconstructed detail continuum, are the
matrix/detail differences mostly a single multiplicative radiation-field scale,
or are they strongly record-dependent?
"""

from __future__ import annotations

import argparse
from pathlib import Path

from xstar_atomic.xstar_matrix_parity import (
    audit_type53_detail_phint53_scale,
    write_type53_detail_phint53_scale_audit,
)


def _find_records_csv(path: str | None) -> str | None:
    if path is None:
        return None
    p = Path(path)
    if p.is_file():
        return str(p)
    if p.is_dir():
        direct = p / "xstar_type53_detail_phint53_radiation_audit_records.csv"
        if direct.exists():
            return str(direct)
        matches = sorted(p.rglob("*detail_phint53_radiation_audit_records.csv"))
        if matches:
            return str(matches[0])
    return str(p)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-csv", default=None, help="records CSV from example 67")
    parser.add_argument("--phint53-audit-dir", default=None, help="directory containing the example-67 records CSV")
    parser.add_argument("--ion", default=None, help="optional ion label to override the CSV value")
    parser.add_argument(
        "--scale-choice",
        default="median_ratio",
        choices=["median_ratio", "geometric_median", "least_squares"],
        help="global detail-rate scale used for residual classification",
    )
    parser.add_argument("--out-dir", default="xstar_type53_detail_phint53_scale_audit", help="output directory")
    parser.add_argument("--print-summary", action="store_true", help="print a concise summary")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    records_csv = _find_records_csv(args.records_csv) or _find_records_csv(args.phint53_audit_dir)
    audit = audit_type53_detail_phint53_scale(records_csv=records_csv, ion=args.ion, scale_choice=args.scale_choice)
    paths = write_type53_detail_phint53_scale_audit(audit, args.out_dir)
    summary = audit["summary"]
    if args.print_summary:
        print("XSTAR type-53 detail phint53 scale/shape audit")
        print("--------------------------------------------------")
        print(f"ion={summary.get('ion')}")
        print(f"input_records_csv={summary.get('input_records_csv')}")
        print(f"scale_choice={summary.get('scale_choice')}")
        print(f"n_evaluated_rows={summary.get('n_evaluated_rows')}")
        print(f"median_matrix_over_detail={summary.get('median_matrix_over_detail')}")
        print(f"geometric_median_matrix_over_detail={summary.get('geometric_median_matrix_over_detail')}")
        print(f"least_squares_detail_rate_scale={summary.get('least_squares_detail_rate_scale')}")
        print(f"chosen_detail_rate_scale={summary.get('chosen_detail_rate_scale')}")
        print(f"p16/p84_matrix_over_detail={summary.get('p16_matrix_over_detail')}/{summary.get('p84_matrix_over_detail')}")
        print(f"n_within_5pct_after_scaling={summary.get('n_within_5pct_after_scaling')}")
        print(f"n_within_10pct_after_scaling={summary.get('n_within_10pct_after_scaling')}")
        print(f"n_within_factor2_after_scaling={summary.get('n_within_factor2_after_scaling')}")
        print(f"median_abs_fractional_residual_after_scaling={summary.get('median_abs_fractional_residual_after_scaling')}")
        groups = audit.get("groups") or []
        if groups:
            print("group_summary:")
            for g in groups:
                print(
                    "  comp={comp} n={n} median={median} p16={p16} p84={p84} min={mn} max={mx}".format(
                        comp=g.get("triplet_component"),
                        n=g.get("n_records"),
                        median=g.get("median_matrix_over_detail"),
                        p16=g.get("p16_matrix_over_detail"),
                        p84=g.get("p84_matrix_over_detail"),
                        mn=g.get("min_matrix_over_detail"),
                        mx=g.get("max_matrix_over_detail"),
                    )
                )
        print(f"scaled_records_csv: {paths['scaled_records_csv']}")
        print(f"group_summary_csv: {paths['group_summary_csv']}")
        print(f"json: {paths['json']}")
        print(f"markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
