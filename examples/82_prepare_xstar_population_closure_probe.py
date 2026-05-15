#!/usr/bin/env python3
"""Prepare or validate the XSTAR calc_hmc_element population-closure probe.

This probe captures XSTAR's element population vector immediately before and
after ``msolvelucy``.  It is the next step after record-level ``ucalc``/matrix
parity when exact rate replay does not move the O VII triplet population.
"""
from __future__ import annotations

import argparse
from xstar_atomic.xstar_population_closure_probe import (
    summarize_population_closure_probe_csv,
    write_population_closure_probe_products,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--population-probe-csv", default="", help="xstar_population_closure_probe.csv or containing directory")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args()
    summary = summarize_population_closure_probe_csv(args.population_probe_csv or None)
    paths = write_population_closure_probe_products(args.out_dir, summary=summary)
    if args.print_summary:
        print("XSTAR population/source closure probe preparation")
        print("----------------------------------------------------")
        for key in [
            "audit_version", "status", "population_probe_csv", "n_rows", "n_captures",
            "n_before_captures", "n_after_captures", "n_before_after_pairs",
            "pairing_mode", "n_bad_ipmat2_captures", "n_paired_bad_ipmat2_captures",
            "n_pair_ipmat2_mismatch", "n_pair_problem_mismatch",
            "n_unpaired_before_captures", "n_unpaired_after_captures",
            "max_abs_population_sum_delta", "probe_ready_for_population_closure_parity",
            "correct_capture_site", "correct_fortran_product",
        ]:
            print(f"{key}={summary.get(key)}")
        missing = summary.get("missing_required_columns") or []
        if missing:
            print("missing_required_columns=" + ";".join(map(str, missing)))
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
