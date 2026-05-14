#!/usr/bin/env python3
"""Audit remaining work for full source-code-equivalent local XSTAR closure."""

from __future__ import annotations

import argparse

from xstar_atomic.xstar_full_parity_closure import (
    audit_source_code_equivalent_local_closure,
    write_source_code_equivalent_local_closure_audit,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", default=None, help="example-56 benchmark directory with preserved solver products")
    parser.add_argument("--ion", default="O VII")
    parser.add_argument("--xstar-source-root", default=None, help="XSTAR source root, e.g. /home/.../xstar/xstar")
    parser.add_argument("--matrix-terms-csv", default=None)
    parser.add_argument("--comparisons-csv", default=None)
    parser.add_argument("--out-dir", default="xstar_source_code_equivalent_local_closure_audit")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    audit = audit_source_code_equivalent_local_closure(
        benchmark_dir=args.benchmark_dir,
        ion=args.ion,
        xstar_source_root=args.xstar_source_root,
        matrix_terms_csv=args.matrix_terms_csv,
        comparisons_csv=args.comparisons_csv,
    )
    paths = write_source_code_equivalent_local_closure_audit(audit, args.out_dir)
    if args.print_summary:
        s = audit["summary"]
        print("XSTAR source-code-equivalent local closure audit")
        print("----------------------------------------------------")
        for key in [
            "audit_version",
            "ion",
            "status",
            "matrix_terms_csv",
            "xstar_source_root",
            "n_matrix_terms",
            "n_matrix_families",
            "n_proxy_or_scaffold_terms",
            "n_parent_superlevel_or_inverse_terms",
            "n_high_priority_closure_gap_families",
            "n_source_snippets_matched",
            "n_source_snippets_total",
            "source_equivalent_mode_ready",
        ]:
            print(f"{key}={s.get(key)}")
        print("blocking_gaps:")
        print(f"  1={s.get('blocking_gap_1')}")
        print(f"  2={s.get('blocking_gap_2')}")
        print(f"  3={s.get('blocking_gap_3')}")
        print(f"next={s.get('recommended_next_step')}")
        print(f"family_summary_csv: {paths['family_summary_csv']}")
        print(f"required_fortran_subroutines_csv: {paths['required_fortran_subroutines_csv']}")
        print(f"ucalc_probe_schema_csv: {paths['ucalc_probe_schema_csv']}")
        print(f"calc_hmc_ion_probe_schema_csv: {paths['calc_hmc_ion_probe_schema_csv']}")
        print(f"population_probe_schema_csv: {paths['population_probe_schema_csv']}")
        print(f"implementation_plan_csv: {paths['implementation_plan_csv']}")
        print(f"source_snippets_csv: {paths['source_snippets_csv']}")
        print(f"fortran_probe_template: {paths['fortran_probe_template']}")
        print(f"json: {paths['json']}")
        print(f"markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
