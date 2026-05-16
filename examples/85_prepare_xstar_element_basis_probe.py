#!/usr/bin/env python3
"""Prepare or validate the XSTAR calc_hmc_element element-basis probe."""
from __future__ import annotations

import argparse
from xstar_atomic.xstar_element_basis_probe import (
    summarize_element_basis_probe_csv,
    write_element_basis_probe_products,
)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--element-basis-probe-csv", default="", help="xstar_element_basis_probe.csv or containing directory")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args()
    audit = summarize_element_basis_probe_csv(args.element_basis_probe_csv or None)
    paths = write_element_basis_probe_products(args.out_dir, summary=audit)
    if args.print_summary:
        s = audit["summary"]
        print("XSTAR element-basis mapping probe preparation")
        print("------------------------------------------------")
        for key in [
            "audit_version", "status", "element_basis_probe_csv", "n_rows",
            "n_basis_solve_calls", "n_ready_basis_solve_calls", "n_basis_begin_rows",
            "n_ion_population_rows", "n_parent_continuum_link_rows",
            "n_final_parent_continuum_slot_rows", "n_unique_solver_population_rows_total_over_solves",
            "n_duplicate_row_roles_total", "probe_ready_for_element_basis_mapping",
            "correct_capture_site", "correct_fortran_product",
        ]:
            print(f"{key}={s.get(key)}")
        missing = s.get("missing_required_columns") or []
        if missing:
            print("missing_required_columns=" + ";".join(map(str, missing)))
        for key, value in paths.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
