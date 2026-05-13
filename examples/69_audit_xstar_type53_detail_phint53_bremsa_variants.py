#!/usr/bin/env python3
"""Audit type-53 phint53 rates for several xo01_detal4 bremsa reconstructions.

This is a source-code triage tool.  It checks whether the v0.3.162/v0.3.163
matrix/detail type-53 photoionization normalization gap can be removed by using
a different available detail-continuum column/attenuation/geometric conversion.
If all available variants still require a large free scale, the likely missing
quantity is the live outward ``zremsz`` continuum used by ``trnfrc.f90`` rather
than any ``zrems(1:5)`` column written by ``fstepr4.f90``.
"""

from __future__ import annotations

import argparse

from xstar_atomic.xstar_matrix_parity import (
    audit_type53_detail_phint53_bremsa_variants,
    write_type53_detail_phint53_bremsa_variants_audit,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", default=None, help="example-56 benchmark directory with preserved solver products")
    parser.add_argument("--ion", default="O VII", help="ion label, e.g. 'O VII'")
    parser.add_argument("--run-dir", default=None, help="same-run XSTAR directory containing xo01_detal4.fits")
    parser.add_argument("--matrix-terms-csv", default=None, help="explicit full-global matrix terms CSV")
    parser.add_argument("--adjacent-coupling-csv", default=None, help="explicit adjacent coupling terms CSV")
    parser.add_argument("--global-index-csv", default=None, help="explicit global-index CSV")
    parser.add_argument("--comparisons-csv", default=None, help="optional benchmark comparisons CSV")
    parser.add_argument("--zone-index", default="last", help="detail zone index, or 'last'")
    parser.add_argument("--triplet-only", action="store_true", help="restrict to f/i/r triplet-bound type-53 rows")
    parser.add_argument("--max-records", type=int, default=None, help="optional maximum type-53 records for quick smoke tests")
    parser.add_argument("--out-dir", default="xstar_type53_detail_phint53_bremsa_variants_audit", help="output directory")
    parser.add_argument("--print-summary", action="store_true", help="print a concise summary")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    audit = audit_type53_detail_phint53_bremsa_variants(
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
    paths = write_type53_detail_phint53_bremsa_variants_audit(audit, args.out_dir)
    summary = audit["summary"]
    if args.print_summary:
        print("XSTAR type-53 detail phint53 bremsa-variant audit")
        print("------------------------------------------------------")
        print(f"ion={summary.get('ion')}")
        print(f"triplet_only={summary.get('triplet_only')}")
        print(f"detail_continuum_status={summary.get('detail_continuum_status')}")
        print(f"detail_zone_index={summary.get('detail_zone_index')}")
        print(f"n_type53_photoionization_records={summary.get('n_type53_photoionization_records')}")
        print(f"n_bremsa_variants={summary.get('n_bremsa_variants')}")
        print(f"best_bremsa_variant_without_free_scale={summary.get('best_bremsa_variant_without_free_scale')}")
        print(f"best_variant_median_matrix_over_detail={summary.get('best_variant_median_matrix_over_detail')}")
        print(f"best_variant_n_within_10pct_without_free_scale={summary.get('best_variant_n_within_10pct_without_free_scale')}")
        print(f"status={summary.get('status')}")
        print("top_variants:")
        for row in (audit.get("variant_summaries") or [])[:10]:
            print(
                "  variant={variant} n={n} median={median} p16={p16} p84={p84} "
                "within10_no_scale={w0} within10_scaled={ws} med_abs_frac_scaled={maf}".format(
                    variant=row.get("bremsa_variant"),
                    n=row.get("n_evaluated_rows"),
                    median=row.get("median_matrix_over_variant_detail"),
                    p16=row.get("p16_matrix_over_variant_detail"),
                    p84=row.get("p84_matrix_over_variant_detail"),
                    w0=row.get("n_within_10pct_without_free_scale"),
                    ws=row.get("n_within_10pct_after_variant_scale"),
                    maf=row.get("median_abs_fractional_residual_after_variant_scale"),
                )
            )
        print(f"variant_summary_csv: {paths['variant_summary_csv']}")
        print(f"records_csv: {paths['records_csv']}")
        print(f"json: {paths['json']}")
        print(f"markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
