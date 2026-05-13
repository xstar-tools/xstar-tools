#!/usr/bin/env python
"""Audit XSTAR source-code provenance for live bremsa(:) versus detail output."""

from __future__ import annotations

import argparse

from xstar_atomic.xstar_source_provenance import (
    audit_xstar_live_bremsa_source_path,
    write_xstar_live_bremsa_source_path_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xstar-source-root", required=True, help="Extracted XSTAR source root, e.g. xstar_source/xstar")
    parser.add_argument(
        "--variant-summary-csv",
        default=None,
        help="Optional example-69 xstar_type53_detail_phint53_bremsa_variants_audit_variant_summary.csv",
    )
    parser.add_argument("--out-dir", default="xstar_live_bremsa_source_path_audit_v03168")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = audit_xstar_live_bremsa_source_path(
        xstar_source_root=args.xstar_source_root,
        variant_summary_csv=args.variant_summary_csv,
    )
    paths = write_xstar_live_bremsa_source_path_audit(audit, args.out_dir)
    if args.print_summary:
        summary = audit["summary"]
        print("XSTAR live bremsa source-path audit")
        print("-----------------------------------")
        print(f"audit_version={summary.get('audit_version')}")
        print(f"status={summary.get('status')}")
        print(f"xstar_source_root={summary.get('xstar_source_root')}")
        print(f"n_source_snippets_matched={summary.get('n_source_snippets_matched')}/{summary.get('n_source_snippet_specs')}")
        print(f"variant_summary_status={summary.get('variant_summary_status')}")
        print(f"variant_summary_source={summary.get('variant_summary_source')}")
        print(f"best_variant={summary.get('best_variant')}")
        print(f"best_median_matrix_over_detail={summary.get('best_median_matrix_over_detail')}")
        print(f"best_within10_without_scale={summary.get('best_within10_without_scale')}")
        print("source_conclusion:")
        print(f"  live_bremsa={summary.get('fortran_live_bremsa_outward_formula')}")
        print(f"  detail4={summary.get('detail4_content')}")
        print(f"  next={summary.get('recommended_next_step')}")
        print(f"snippets_csv: {paths['snippets_csv']}")
        print(f"json: {paths['json']}")
        print(f"markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
