#!/usr/bin/env python3
"""Build a 607-row source-aligned XSTAR full-element basis scaffold."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_full_element_basis import (
    build_full_element_basis_scaffold,
    write_full_element_basis_scaffold,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--element-basis-remap-audit", required=True)
    p.add_argument("--priority-population-threshold", type=float, default=1.0e-12)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args()

    audit = build_full_element_basis_scaffold(
        element_basis_remap_audit=args.element_basis_remap_audit,
        priority_population_threshold=args.priority_population_threshold,
    )
    paths = write_full_element_basis_scaffold(args.out_dir, audit)
    if args.print_summary:
        s = audit["summary"]
        print("XSTAR full-element basis scaffold")
        print("----------------------------------")
        for key in [
            "audit_version", "status", "ion", "selected_basis_solve_call_id",
            "n_full_xstar_basis_rows", "n_existing_python_population_rows",
            "n_unique_xstar_rows_represented_by_python", "n_missing_python_basis_rows",
            "n_missing_rows_above_population_threshold", "n_high_population_missing_rows",
            "current_population_coverage", "missing_population_fraction",
            "max_missing_row_ipmat2", "max_missing_row_population",
            "n_shared_alias_rows", "proposed_total_python_rows_after_expansion",
            "proposed_unique_compact_basis_rows", "full_element_basis_scaffold_ready",
            "native_full_element_solver_ready", "dominant_next_target",
        ]:
            print(f"{key}={s.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
