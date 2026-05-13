#!/usr/bin/env python3
"""Audit XSTAR type-53 photoionization/recombination source-sink matrix closure."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    here = Path(__file__).resolve()
    root = here.parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


_bootstrap_src_path()

from xstar_atomic.xstar_matrix_parity import (  # noqa: E402
    audit_type53_source_sink_rates,
    find_solver_product_paths,
    write_type53_source_sink_rate_audit,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check type-53 photoionization/recombination source-sink closure against full-global matrix terms."
    )
    parser.add_argument("--benchmark-dir", help="Output directory from example 56 with preserved solver products")
    parser.add_argument("--ion", default="O VII", help="Ion label used to select products from the benchmark directory")
    parser.add_argument("--matrix-terms-csv", help="Explicit xstar_like_element_solver_full_global_matrix_terms.csv path")
    parser.add_argument("--normalized-solve-csv", help="Explicit xstar_like_element_solver_full_global_normalized_solve_comparison.csv path")
    parser.add_argument("--comparisons-csv", help="Optional example-56 comparisons CSV")
    parser.add_argument("--triplet-only", action="store_true", help="Only write type-53 rows that touch He-like triplet upper levels")
    parser.add_argument("--max-rows", type=int, default=500, help="Maximum term rows to write; <=0 writes all")
    parser.add_argument("--out-dir", default="xstar_type53_source_sink_rate_audit", help="Output directory")
    parser.add_argument("--print-summary", action="store_true", help="Print a compact summary")
    args = parser.parse_args(argv)

    matrix_csv = args.matrix_terms_csv
    solve_csv = args.normalized_solve_csv
    if args.benchmark_dir and not matrix_csv:
        found = find_solver_product_paths(args.benchmark_dir, ion=args.ion, comparisons_csv=args.comparisons_csv)
        matrix_csv = str(found.get("matrix_terms_csv") or "")
        solve_csv = solve_csv or (str(found.get("normalized_solve_csv")) if found.get("normalized_solve_csv") else None)
    if not matrix_csv:
        parser.error("provide --matrix-terms-csv or --benchmark-dir with preserved solver products")

    result = audit_type53_source_sink_rates(
        matrix_terms_csv=matrix_csv,
        normalized_solve_csv=solve_csv,
        ion=args.ion,
        triplet_only=args.triplet_only,
        max_rows=None if args.max_rows <= 0 else args.max_rows,
    )
    paths = write_type53_source_sink_rate_audit(result, args.out_dir)

    if args.print_summary:
        overall = result["overall"]
        print("XSTAR type-53 source/sink rate audit")
        print("---------------------------------------")
        print(f"ion={args.ion}")
        print(f"matrix_terms_csv={matrix_csv}")
        print(f"normalized_solve_csv={solve_csv or ''}")
        print(f"triplet_only={overall.get('triplet_only')}")
        print(f"n_type53_matrix_terms={overall.get('n_type53_matrix_terms')}")
        print(f"n_type53_record_branches={overall.get('n_type53_record_branches')}")
        print(f"n_type53_photoionization_terms={overall.get('n_type53_photoionization_terms')}")
        print(f"n_type53_milne_terms={overall.get('n_type53_milne_terms')}")
        print(f"n_type53_partner_matches={overall.get('n_type53_partner_matches')}")
        print(f"n_type53_gain_loss_record_pairs_matching={overall.get('n_type53_gain_loss_record_pairs_matching')}")
        print(f"n_type53_milne_matrix_matches_phint53_ans2={overall.get('n_type53_milne_matrix_matches_phint53_ans2')}")
        print(f"n_type53_triplet_touching_terms={overall.get('n_type53_triplet_touching_terms')}")
        print(f"n_type53_triplet_population_row_terms={overall.get('n_type53_triplet_population_row_terms')}")
        print("largest_records:")
        for row in result["record_rows"][:10]:
            print(
                "  record={rec} branch={br} bound={b} cont={c} comps={comp} gains/losses={g}/{l} largest={mx} pair={cls}".format(
                    rec=row.get("record"),
                    br=row.get("branch"),
                    b=row.get("bound_global_index"),
                    c=row.get("continuum_or_parent_global_index"),
                    comp=row.get("touched_triplet_components"),
                    g=row.get("n_gain_terms"),
                    l=row.get("n_loss_terms"),
                    mx=row.get("largest_abs_rate_s^-1"),
                    cls=row.get("record_pair_classification"),
                )
            )
        print("largest_terms:")
        for row in result["term_rows"][:10]:
            print(
                "  record={rec} {direction} {branch} bound={b} cont={c} rate={rate} expected={exp} class={cls} partner={partner}".format(
                    rec=row.get("record"),
                    direction=row.get("direction"),
                    branch=row.get("branch"),
                    b=row.get("bound_global_index"),
                    c=row.get("continuum_or_parent_global_index"),
                    rate=row.get("matrix_rate_s^-1"),
                    exp=row.get("expected_rate_s^-1"),
                    cls=row.get("rate_classification"),
                    partner=row.get("partner_status"),
                )
            )
        for key, path in paths.items():
            print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
