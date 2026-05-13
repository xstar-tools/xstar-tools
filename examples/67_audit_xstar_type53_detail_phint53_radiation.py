#!/usr/bin/env python3
"""Audit XSTAR type-53 photoionization against same-run detail continuum.

This is a source-code-parity diagnostic, not a triplet-ratio tuning script.  It
uses preserved full-global matrix products from example 56 and, when available,
reads ``xo01_detal4.fits`` from the matching XSTAR run.  It then recomputes the
photoionization ``ans1`` side of ``phint53.f90`` on the reconstructed detail
continuum and compares it with the matrix type-53 photoionization rate.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from xstar_atomic.xstar_matrix_parity import (
    audit_type53_detail_phint53_radiation,
    write_type53_detail_phint53_radiation_audit,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", default=None, help="example-56 output directory with preserved solver products")
    parser.add_argument("--ion", default="O VII", help='ion label, e.g. "O VII"')
    parser.add_argument("--run-dir", default=None, help="XSTAR run directory containing xo01_detal4.fits; inferred from benchmark when possible")
    parser.add_argument("--matrix-terms-csv", default=None, help="explicit full-global matrix terms CSV")
    parser.add_argument("--adjacent-coupling-csv", default=None, help="explicit adjacent coupling terms CSV")
    parser.add_argument("--global-index-csv", default=None, help="explicit global index CSV")
    parser.add_argument("--comparisons-csv", default=None, help="optional benchmark comparisons CSV")
    parser.add_argument("--zone-index", default="last", help="detail zone index, 1-based, or 'last'")
    parser.add_argument("--triplet-only", action="store_true", help="audit only type-53 rows touching f/i/r upper levels")
    parser.add_argument("--max-records", type=int, default=None, help="optional limit for quick scans")
    parser.add_argument("--out-dir", default="xstar_type53_detail_phint53_radiation_audit", help="output directory")
    parser.add_argument("--print-summary", action="store_true", help="print a concise summary")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    audit = audit_type53_detail_phint53_radiation(
        benchmark_dir=args.benchmark_dir,
        ion=args.ion,
        run_dir=args.run_dir,
        matrix_terms_csv=args.matrix_terms_csv,
        adjacent_coupling_csv=args.adjacent_coupling_csv,
        global_index_csv=args.global_index_csv,
        comparisons_csv=args.comparisons_csv,
        zone_index=args.zone_index,
        triplet_only=args.triplet_only,
        max_records=args.max_records,
    )
    paths = write_type53_detail_phint53_radiation_audit(audit, args.out_dir)
    summary = audit["summary"]
    if args.print_summary:
        print("XSTAR type-53 detail-continuum phint53 radiation audit")
        print("---------------------------------------------------------")
        print(f"ion={summary.get('ion')}")
        print(f"matrix_terms_csv={summary.get('matrix_terms_csv')}")
        print(f"adjacent_coupling_csv={summary.get('adjacent_coupling_csv')}")
        print(f"global_index_csv={summary.get('global_index_csv')}")
        print(f"run_dir={summary.get('run_dir')}")
        print(f"detail_continuum_status={summary.get('detail_continuum_status')}")
        print(f"detail_zone_index={summary.get('detail_zone_index')}")
        print(f"triplet_only={summary.get('triplet_only')}")
        print(f"n_type53_photoionization_records={summary.get('n_type53_photoionization_records')}")
        print(f"n_detail_phint53_evaluated={summary.get('n_detail_phint53_evaluated')}")
        print(f"n_detail_phint53_matches={summary.get('n_detail_phint53_matches')}")
        print(f"n_detail_phint53_differs={summary.get('n_detail_phint53_differs')}")
        top = summary.get("top_records_by_abs_matrix_minus_detail") or []
        if top:
            print("largest_records:")
            for row in top[:10]:
                print(
                    "  record={record} bound={bound} comp={comp} matrix={matrix} detail={detail} "
                    "ratio={ratio} class={cls}".format(
                        record=row.get("record"),
                        bound=row.get("bound_level_label"),
                        comp=row.get("triplet_component"),
                        matrix=row.get("matrix_photoionization_rate_s^-1"),
                        detail=row.get("detail_phint53_photo_ans1_s^-1"),
                        ratio=row.get("matrix_over_detail_phint53_ans1"),
                        cls=row.get("classification"),
                    )
                )
        print(f"records_csv: {paths['records_csv']}")
        print(f"json: {paths['json']}")
        print(f"markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
