#!/usr/bin/env python
"""Audit the XSTAR live rate-grid bremsa(:) path used by phint53/type-53 rates."""

from __future__ import annotations

import argparse

from xstar_atomic.xstar_source_provenance import (
    audit_xstar_live_rate_grid_bremsa_path,
    write_xstar_live_rate_grid_bremsa_path_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xstar-source-root", required=True, help="Extracted XSTAR source root, e.g. /path/to/xstar")
    parser.add_argument(
        "--variant-summary-csv",
        default=None,
        help=(
            "Optional example-69 variant summary source: direct CSV, audit output directory, or audit tar.gz. "
            "When supplied, the audit combines source provenance with the observed matrix/detail normalization gap."
        ),
    )
    parser.add_argument("--out-dir", default="xstar_live_rate_grid_bremsa_path_audit_v03169")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = audit_xstar_live_rate_grid_bremsa_path(
        xstar_source_root=args.xstar_source_root,
        variant_summary_csv=args.variant_summary_csv,
    )
    paths = write_xstar_live_rate_grid_bremsa_path_audit(audit, args.out_dir)
    if args.print_summary:
        summary = audit["summary"]
        print("XSTAR live rate-grid bremsa path audit")
        print("---------------------------------------")
        print(f"audit_version={summary.get('audit_version')}")
        print(f"status={summary.get('status')}")
        print(f"xstar_source_root={summary.get('xstar_source_root')}")
        print(f"n_source_snippets_matched={summary.get('n_source_snippets_matched')}/{summary.get('n_source_snippet_specs')}")
        print(f"variant_summary_status={summary.get('variant_summary_status')}")
        print(f"variant_summary_source={summary.get('variant_summary_source')}")
        print(f"best_variant={summary.get('best_variant')}")
        print(f"best_median_matrix_over_detail={summary.get('best_median_matrix_over_detail')}")
        print(f"best_within10_without_scale={summary.get('best_within10_without_scale')}")
        print("rate_grid_conclusion:")
        print(f"  correct_live_rate_field={summary.get('correct_live_rate_field')}")
        print(f"  high_resolution_provenance={summary.get('high_resolution_provenance')}")
        print(f"  detail4_limitation={summary.get('detail4_limitation')}")
        print(f"  next={summary.get('recommended_next_step')}")
        print(f"snippets_csv: {paths['snippets_csv']}")
        print(f"capture_columns_csv: {paths['capture_columns_csv']}")
        print(f"instrumentation_steps_csv: {paths['instrumentation_steps_csv']}")
        print(f"probe_notes: {paths['probe_notes']}")
        print(f"json: {paths['json']}")
        print(f"markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
