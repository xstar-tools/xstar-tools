#!/usr/bin/env python3
"""Diagnose XSTAR element-population basis mapping gaps."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_population_basis_mapping import (
    diagnose_population_basis_mapping,
    write_population_basis_mapping_diagnosis,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--population-closure-parity-audit", required=True,
                   help="Directory from examples/83, or its population-closure parity audit products")
    p.add_argument("--population-fraction-threshold", type=float, default=1e-4)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args()
    audit = diagnose_population_basis_mapping(
        population_closure_parity_audit=args.population_closure_parity_audit,
        population_fraction_threshold=args.population_fraction_threshold,
    )
    paths = write_population_basis_mapping_diagnosis(audit, args.out_dir)
    if args.print_summary:
        s = audit["summary"]
        print("XSTAR population-basis mapping diagnosis")
        print("------------------------------------------")
        for key in [
            "audit_version", "status", "ion", "selected_solve_call_id", "occurrence_rank",
            "selected_xstar_ipmat2", "selected_xstar_nsp", "selected_xstar_nionp",
            "n_xstar_population_rows_selected", "n_python_population_rows",
            "n_python_rows_with_xstar_ipmat2_index", "n_xstar_rows_without_python_mapping",
            "n_dominant_unmapped_blocks", "xstar_population_sum_on_python_mapped_rows",
            "xstar_population_sum_on_unmapped_rows", "xstar_unmapped_population_fraction_of_total",
            "max_unmapped_row_ipmat2", "max_unmapped_row_nion", "max_unmapped_row_nsup",
            "max_unmapped_row_population", "mapping_diagnosis", "dominant_next_target",
        ]:
            print(f"{key}={s.get(key)}")
        for k, v in paths.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
