#!/usr/bin/env python3
"""Diagnose whether family-rate replay or population/source closure dominates.

Use this after ``examples/80_scan_xstar_record_level_ucalc_replay_families.py``.
If exact Fortran ``ucalc`` replay of the discrepant families barely moves the
triplet population fractions, the next parity target is XSTAR's population/source
closure rather than another isolated rate-family replacement.
"""
from __future__ import annotations

import argparse
from xstar_atomic.xstar_population_closure_diagnosis import (
    diagnose_population_closure_from_family_scan,
    write_population_closure_diagnosis,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family-scan-csv", required=True, help="Family-scan directory or xstar_record_level_ucalc_replay_family_scan.csv")
    p.add_argument("--ion", default="O VII")
    p.add_argument("--population-delta-threshold", type=float, default=1.0e-4)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args()
    audit = diagnose_population_closure_from_family_scan(
        args.family_scan_csv,
        ion=args.ion,
        population_delta_threshold=args.population_delta_threshold,
    )
    paths = write_population_closure_diagnosis(audit, args.out_dir)
    summary = dict(audit.get("summary", {}) or {})
    if args.print_summary:
        print("XSTAR population/source closure diagnosis")
        print("------------------------------------------------")
        for key in [
            "audit_version", "ion", "status", "n_families", "population_delta_threshold",
            "max_abs_population_delta", "max_abs_population_delta_family",
            "rate_replay_moves_population", "dominant_next_target",
            "source_equivalent_population_closure_ready",
        ]:
            print(f"{key}={summary.get(key)}")
        print("interpretation:")
        print(f"  {summary.get('interpretation')}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
