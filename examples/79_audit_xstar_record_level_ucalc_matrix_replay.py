#!/usr/bin/env python3
"""Controlled matrix replay using XSTAR ucalc ans1/ans2 record-level probes."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_record_level_replay import (
    audit_record_level_ucalc_matrix_replay,
    write_record_level_ucalc_matrix_replay_audit,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--benchmark-dir", required=True)
    p.add_argument("--ion", default="O VII")
    p.add_argument("--record-level-audit-csv", required=True, help="v0.3.183+ record-level parity audit directory or records CSV")
    p.add_argument("--matrix-terms-csv", default=None)
    p.add_argument("--global-index-csv", default=None)
    p.add_argument("--line-rows-csv", default=None)
    p.add_argument("--calc-ion-rates-csv", default=None)
    p.add_argument("--replacement-mode", default="blockers", choices=["blockers", "differs", "all", "families"])
    p.add_argument("--families", default="", help="Comma-separated substrings used when --replacement-mode families")
    p.add_argument("--run-solver", action="store_true", help="Also solve original and replay matrices")
    p.add_argument("--linear-solver", default="xstar-lucy", choices=["solve", "dense", "lstsq", "svd", "xstar-lucy"])
    p.add_argument("--rank-deficient-action", default="svd")
    p.add_argument("--negative-population-action", default="keep")
    p.add_argument("--no-prune-null-rate-levels", action="store_true")
    p.add_argument("--full-global-topology", default="xstar-continuum-alias-superlevels")
    p.add_argument("--ion-fraction-closure", default="xstar-calc-ion-rates")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args()
    families = [s.strip() for s in args.families.split(",") if s.strip()]
    audit = audit_record_level_ucalc_matrix_replay(
        benchmark_dir=args.benchmark_dir,
        ion=args.ion,
        record_level_audit_csv=args.record_level_audit_csv,
        matrix_terms_csv=args.matrix_terms_csv,
        global_index_csv=args.global_index_csv,
        line_rows_csv=args.line_rows_csv,
        calc_ion_rates_csv=args.calc_ion_rates_csv,
        replacement_mode=args.replacement_mode,
        families=families,
        run_solver=args.run_solver,
        linear_solver=args.linear_solver,
        rank_deficient_action=args.rank_deficient_action,
        negative_population_action=args.negative_population_action,
        prune_null_rate_levels=not args.no_prune_null_rate_levels,
        full_global_topology=args.full_global_topology,
        ion_fraction_closure=args.ion_fraction_closure,
    )
    paths = write_record_level_ucalc_matrix_replay_audit(audit, args.out_dir)
    if args.print_summary:
        s = audit["summary"]
        print("XSTAR record-level ucalc matrix replay audit")
        print("------------------------------------------------")
        for k in [
            "audit_version", "ion", "status", "replacement_mode", "n_original_matrix_terms",
            "n_replay_matrix_terms", "n_replayed_terms", "n_replayed_families",
            "median_old_over_new", "p16_old_over_new", "p84_old_over_new", "run_solver",
            "solve_status", "solver",
        ]:
            print(f"{k}={s.get(k)}")
        for k, v in paths.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
