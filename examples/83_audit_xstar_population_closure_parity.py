#!/usr/bin/env python3
"""Audit XSTAR population/source closure against preserved Python solve products."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_population_closure_parity import (
    audit_population_closure_parity,
    write_population_closure_parity_audit,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--benchmark-dir", required=True)
    p.add_argument("--ion", default="O VII")
    p.add_argument("--population-probe-csv", required=True, help="raw xstar_population_closure_probe.csv or containing directory")
    p.add_argument("--occurrence-rank", type=int, default=-1, help="Element occurrence rank; default -1/latest")
    p.add_argument("--element-z", type=int, default=None, help="Override element Z inferred from --ion")
    p.add_argument("--population-delta-threshold", type=float, default=1e-4)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args()
    audit = audit_population_closure_parity(
        benchmark_dir=args.benchmark_dir,
        ion=args.ion,
        population_probe_csv=args.population_probe_csv,
        occurrence_rank=args.occurrence_rank,
        element_z=args.element_z,
        population_delta_threshold=args.population_delta_threshold,
    )
    paths = write_population_closure_parity_audit(audit, args.out_dir)
    if args.print_summary:
        s = audit["summary"]
        print("XSTAR population/source closure parity audit")
        print("------------------------------------------------")
        for key in [
            "audit_version", "ion", "status", "selected_element_z", "selection", "occurrence_rank",
            "selected_solve_call_id", "selected_xstar_ipmat2", "selected_xstar_nsp", "selected_xstar_nionp",
            "n_population_pairs_total", "n_element_pairs", "n_xstar_population_rows_selected",
            "n_xstar_nonzero_population_rows_selected", "xstar_population_sum_before", "xstar_population_sum_after",
            "n_python_population_rows", "n_python_rows_with_xstar_ipmat2_index", "n_overlap_rows",
            "n_xstar_rows_without_python_mapping", "n_xstar_unmapped_nonzero_rows",
            "xstar_population_sum_on_python_mapped_rows", "xstar_population_sum_on_unmapped_rows",
            "xstar_unmapped_population_fraction_of_total", "max_abs_diff_python_population_fraction",
            "max_abs_diff_python_superlevel_p", "basis_closure_ready", "overlap_population_fraction_ready",
            "overlap_superlevel_population_ready", "source_equivalent_population_closure_ready",
            "dominant_next_target",
        ]:
            print(f"{key}={s.get(key)}")
        for k, v in paths.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
