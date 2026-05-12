#!/usr/bin/env python3
"""Rank individual He-like triplet matrix-row terms for parity work."""

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
    audit_triplet_rate_terms,
    find_solver_product_paths,
    write_triplet_rate_term_audit,
)


def _parse_data_types(text: str | None):
    if not text:
        return None
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Rank individual triplet-row matrix terms as concrete source-code parity targets."
    )
    parser.add_argument("--benchmark-dir", help="Output directory from example 56 with preserved solver products")
    parser.add_argument("--ion", default="O VII", help="Ion label used to select products from the benchmark directory")
    parser.add_argument("--matrix-terms-csv", help="Explicit xstar_like_element_solver_full_global_matrix_terms.csv path")
    parser.add_argument("--normalized-solve-csv", help="Explicit xstar_like_element_solver_full_global_normalized_solve_comparison.csv path")
    parser.add_argument("--comparisons-csv", help="Optional example-56 comparisons CSV")
    parser.add_argument("--data-types", help="Optional comma-separated data type filter, e.g. 63 or 53,63,68")
    parser.add_argument("--max-rows", type=int, default=200, help="Maximum ranked term rows to write; <=0 writes all")
    parser.add_argument("--out-dir", default="xstar_triplet_rate_term_audit", help="Output directory")
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

    result = audit_triplet_rate_terms(
        matrix_terms_csv=matrix_csv,
        normalized_solve_csv=solve_csv,
        ion=args.ion,
        data_types=_parse_data_types(args.data_types),
        max_rows=None if args.max_rows <= 0 else args.max_rows,
    )
    paths = write_triplet_rate_term_audit(result, args.out_dir)

    if args.print_summary:
        overall = result["overall"]
        print("XSTAR triplet row rate-term audit")
        print("-----------------------------------")
        print(f"ion={args.ion}")
        print(f"matrix_terms_csv={matrix_csv}")
        print(f"normalized_solve_csv={solve_csv or ''}")
        if overall.get("data_type_filter"):
            print(f"data_type_filter={overall.get('data_type_filter')}")
        print(f"n_triplet_upper_levels={overall.get('n_triplet_upper_levels')}")
        print(f"n_triplet_row_terms_total={overall.get('n_triplet_row_terms_total')}")
        print(f"n_triplet_row_terms_written={overall.get('n_triplet_row_terms_written')}")
        print("top_families_by_triplet_row_abs_signed_sum:")
        for row in result["family_rows"][:10]:
            print(
                "  data_type={dt} source={src} n_terms={n} gains/losses={g}/{l} abs_sum={s} largest={mx} partner_issues={pi}".format(
                    dt=row.get("data_type"),
                    src=row.get("source_label"),
                    n=row.get("n_triplet_row_terms"),
                    g=row.get("n_row_gain_terms"),
                    l=row.get("n_row_loss_terms"),
                    s=row.get("abs_signed_sum_s^-1"),
                    mx=row.get("largest_abs_signed_rate_s^-1"),
                    pi=row.get("n_partner_mismatches_or_missing"),
                )
            )
        print("largest_terms:")
        for row in result["term_rows"][:12]:
            print(
                "  {comp} g={gi} {label} {direction} dt={dt} rate={rate} record={rec} partner={partner} role={role}".format(
                    comp=row.get("triplet_component"),
                    gi=row.get("triplet_global_index"),
                    label=row.get("triplet_level_label"),
                    direction=row.get("direction"),
                    dt=row.get("data_type"),
                    rate=row.get("signed_rate_s^-1"),
                    rec=row.get("record"),
                    partner=row.get("partner_status"),
                    role=row.get("matrix_role"),
                )
            )
        for key, path in paths.items():
            print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
