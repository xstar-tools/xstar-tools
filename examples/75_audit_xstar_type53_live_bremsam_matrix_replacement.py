#!/usr/bin/env python3
"""Controlled solve audit replacing type-53 photoionization rates with live phint53.

This example consumes the live-bremsam type-53 audit from example 74 and a
preserved full-global solver product from example 56.  It creates a diagnostic
matrix in which only type-53 photoionization gain/loss rates are replaced by
live XSTAR ``phint53`` ans1 values evaluated on the instrumented rate grid.  It
then re-solves the full-global normalized matrix to show how the f/i/r fractions
move.  This is a controlled diagnostic, not a default solver-physics change.
"""

from __future__ import annotations

import argparse

from xstar_atomic.xstar_matrix_parity import (
    audit_type53_live_bremsam_matrix_replacement,
    write_type53_live_bremsam_matrix_replacement_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", default=None, help="example-56 benchmark directory with preserved solver products")
    parser.add_argument("--ion", default="O VII")
    parser.add_argument("--live-phint53-audit-csv", required=True, help="example-74 records CSV or output directory")
    parser.add_argument("--matrix-terms-csv", default=None)
    parser.add_argument("--global-index-csv", default=None)
    parser.add_argument("--line-rows-csv", default=None)
    parser.add_argument("--calc-ion-rates-csv", default=None)
    parser.add_argument("--comparisons-csv", default=None)
    parser.add_argument("--normalized-solve-csv", default=None)
    parser.add_argument("--linear-solver", default="xstar-lucy")
    parser.add_argument("--rank-deficient-action", default="svd")
    parser.add_argument("--negative-population-action", default="keep")
    parser.add_argument("--no-prune-null-rate-levels", action="store_true")
    parser.add_argument("--full-global-topology", default="xstar-continuum-alias-superlevels")
    parser.add_argument("--ion-fraction-closure", default="xstar-calc-ion-rates")
    parser.add_argument("--out-dir", default="xstar_type53_live_bremsam_matrix_replacement_audit")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = audit_type53_live_bremsam_matrix_replacement(
        benchmark_dir=args.benchmark_dir,
        ion=args.ion,
        live_phint53_audit_csv=args.live_phint53_audit_csv,
        matrix_terms_csv=args.matrix_terms_csv,
        global_index_csv=args.global_index_csv,
        line_rows_csv=args.line_rows_csv,
        calc_ion_rates_csv=args.calc_ion_rates_csv,
        comparisons_csv=args.comparisons_csv,
        normalized_solve_csv=args.normalized_solve_csv,
        linear_solver=args.linear_solver,
        rank_deficient_action=args.rank_deficient_action,
        negative_population_action=args.negative_population_action,
        prune_null_rate_levels=not args.no_prune_null_rate_levels,
        full_global_topology=args.full_global_topology,
        ion_fraction_closure=args.ion_fraction_closure,
    )
    paths = write_type53_live_bremsam_matrix_replacement_audit(audit, args.out_dir)

    if args.print_summary:
        s = audit["summary"]
        print("XSTAR type-53 live-bremsam matrix replacement audit")
        print("--------------------------------------------------------")
        for key in [
            "audit_version",
            "ion",
            "status",
            "he_like_stage",
            "n_original_matrix_terms",
            "n_replacement_matrix_terms",
            "n_type53_photoionization_terms_replaced",
            "median_original_over_live_replacement_rate",
            "p16_original_over_live_replacement_rate",
            "p84_original_over_live_replacement_rate",
            "original_f_fraction",
            "original_i_fraction",
            "original_r_fraction",
            "replacement_f_fraction",
            "replacement_i_fraction",
            "replacement_r_fraction",
            "delta_f_replacement_minus_original",
            "delta_i_replacement_minus_original",
            "delta_r_replacement_minus_original",
            "original_l2_distance_to_target",
            "replacement_l2_distance_to_target",
            "delta_l2_replacement_minus_original",
            "solver",
            "full_global_topology",
            "ion_fraction_closure",
        ]:
            print(f"{key}={s.get(key)}")
        print(f"changed_terms_csv: {paths['changed_terms_csv']}")
        print(f"replacement_matrix_terms_csv: {paths['matrix_terms_csv']}")
        print(f"solve_comparison_csv: {paths['solve_comparison_csv']}")
        print(f"replacement_normalized_solve_comparison_csv: {paths['replacement_normalized_solve_comparison_csv']}")
        print(f"json: {paths['json']}")
        print(f"markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
