#!/usr/bin/env python3
"""Reconstruct XSTAR's compact element basis and remap Python population rows."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_element_basis_remap import (
    audit_element_basis_remap,
    write_element_basis_remap_products,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--benchmark-dir", required=True)
    p.add_argument("--ion", required=True)
    p.add_argument("--element-basis-probe-csv", required=True)
    p.add_argument("--population-probe-csv", default="", help="Optional paired population-closure probe CSV for solved-population coverage")
    p.add_argument("--occurrence-rank", type=int, default=-1, help="1-based element occurrence, or -1/latest")
    p.add_argument("--basis-solve-call-id", type=int, default=None, help="Explicit basis solve id; overrides occurrence rank")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args()

    audit = audit_element_basis_remap(
        benchmark_dir=args.benchmark_dir,
        ion=args.ion,
        element_basis_probe_csv=args.element_basis_probe_csv,
        population_probe_csv=args.population_probe_csv or None,
        occurrence_rank=args.occurrence_rank,
        basis_solve_call_id=args.basis_solve_call_id,
    )
    paths = write_element_basis_remap_products(args.out_dir, audit)
    if args.print_summary:
        s = audit["summary"]
        print("XSTAR element-basis remap audit")
        print("---------------------------------")
        for key in [
            "audit_version", "status", "ion", "selection", "occurrence_rank",
            "selected_basis_solve_call_id", "n_selected_probe_role_rows",
            "n_unique_xstar_basis_rows", "max_xstar_ipmat2_index", "n_ion_blocks",
            "n_xstar_compact_rows_with_multiple_roles", "n_python_population_rows",
            "n_python_rows_mapped_by_ion_stage_level", "n_python_rows_unmapped",
            "n_unique_xstar_rows_represented_by_python", "n_python_alias_groups",
            "n_old_python_ipmat2_indices_already_correct",
            "n_old_python_ipmat2_indices_requiring_remap",
            "n_xstar_basis_rows_not_represented_by_python",
            "xstar_after_population_total",
            "xstar_after_population_on_corrected_python_mapped_rows",
            "xstar_after_population_on_unrepresented_basis_rows",
            "xstar_unrepresented_population_fraction_of_total",
            "exact_xstar_basis_reconstruction_ready", "python_to_xstar_basis_remap_ready",
            "source_equivalent_basis_mapping_ready", "dominant_next_target",
        ]:
            print(f"{key}={s.get(key)}")
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
