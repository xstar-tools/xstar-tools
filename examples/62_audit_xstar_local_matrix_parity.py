#!/usr/bin/env python3
"""Rank local XSTAR matrix rate families for source-code parity audits."""

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

from xstar_atomic.xstar_matrix_parity import audit_local_matrix_parity, find_solver_product_paths, write_local_matrix_parity_audit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Audit local matrix rate-family coverage for source-code parity work.")
    parser.add_argument("--benchmark-dir", help="Output directory from example 56 with preserved solver products")
    parser.add_argument("--ion", default="O VII", help="Ion label used to select products from the benchmark directory")
    parser.add_argument("--matrix-terms-csv", help="Explicit xstar_like_element_solver_full_global_matrix_terms.csv path")
    parser.add_argument("--normalized-solve-csv", help="Explicit xstar_like_element_solver_full_global_normalized_solve_comparison.csv path")
    parser.add_argument("--comparisons-csv", help="Optional example-56 comparisons CSV")
    parser.add_argument("--type50-audit-csv", help="Optional detail-state type-50 audit CSV from example 61")
    parser.add_argument("--out-dir", default="xstar_local_matrix_parity_audit", help="Output directory")
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

    result = audit_local_matrix_parity(
        matrix_terms_csv=matrix_csv,
        normalized_solve_csv=solve_csv,
        ion=args.ion,
        type50_audit_csv=args.type50_audit_csv,
    )
    paths = write_local_matrix_parity_audit(result, args.out_dir)
    if args.print_summary:
        overall = result["overall"]
        print("XSTAR local matrix parity audit")
        print("--------------------------------")
        print(f"ion={args.ion}")
        print(f"matrix_terms_csv={matrix_csv}")
        print(f"normalized_solve_csv={solve_csv or ''}")
        print(f"n_matrix_terms={overall.get('n_matrix_terms')}")
        print(f"n_rate_families={overall.get('n_rate_families')}")
        print(f"n_triplet_upper_levels={overall.get('n_triplet_upper_levels')}")
        if overall.get("type50_audit_rows"):
            print(
                "type50_audit_rows={rows} type50_matrix_matches={matches} classifications={cls}".format(
                    rows=overall.get("type50_audit_rows"),
                    matches=overall.get("type50_audit_matrix_matches"),
                    cls=overall.get("type50_audit_classifications"),
                )
            )
        print("top_triplet_touching_families:")
        for row in result["family_rows"][:10]:
            if int(row.get("n_terms_touching_triplet_levels") or 0) <= 0:
                continue
            print(
                "  data_type={dt} source={src} n_terms={n} touching={t} f/i/r={f}/{i}/{r} status={status}".format(
                    dt=row.get("data_type"),
                    src=row.get("source_label"),
                    n=row.get("n_matrix_terms"),
                    t=row.get("n_terms_touching_triplet_levels"),
                    f=row.get("n_terms_touching_f"),
                    i=row.get("n_terms_touching_i"),
                    r=row.get("n_terms_touching_r"),
                    status=row.get("parity_status"),
                )
            )
        for key, path in paths.items():
            print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
