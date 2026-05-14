#!/usr/bin/env python3
"""Prepare or validate XSTAR ucalc/calc_hmc_ion full-parity probes."""

from __future__ import annotations

import argparse

from xstar_atomic.xstar_full_parity_probes import prepare_full_parity_probe_products


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xstar-source-root", default=None)
    parser.add_argument("--ucalc-probe-csv", default=None)
    parser.add_argument("--matrix-probe-csv", default=None)
    parser.add_argument("--out-dir", default="xstar_full_parity_probe_o7")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    result = prepare_full_parity_probe_products(
        out_dir=args.out_dir,
        ucalc_probe_csv=args.ucalc_probe_csv,
        matrix_probe_csv=args.matrix_probe_csv,
        xstar_source_root=args.xstar_source_root,
    )
    s = result["summary"]
    paths = result["paths"]
    if args.print_summary:
        print("XSTAR full local parity probe preparation")
        print("------------------------------------------")
        for key in [
            "audit_version",
            "status",
            "ucalc_probe_status",
            "matrix_probe_status",
            "ucalc_probe_csv",
            "matrix_probe_csv",
            "n_ucalc_rows",
            "n_matrix_rows",
            "n_ucalc_record_keys",
            "n_matrix_record_keys",
            "n_ucalc_keys_without_matrix_rows",
            "n_matrix_keys_without_ucalc_rows",
            "n_matrix_record_keys_with_four_rows",
            "n_matrix_record_keys_not_four_rows",
            "probe_ready_for_record_level_matrix_parity",
            "correct_capture_site",
            "correct_fortran_products",
        ]:
            print(f"{key}={s.get(key)}")
        if s.get("ucalc_missing_required_columns"):
            print(f"ucalc_missing_required_columns={s.get('ucalc_missing_required_columns')}")
        if s.get("matrix_missing_required_columns"):
            print(f"matrix_missing_required_columns={s.get('matrix_missing_required_columns')}")
        print(f"helper_fortran: {paths['helper_fortran']}")
        print(f"after_ucalc_insertion: {paths['after_ucalc_insertion']}")
        print(f"matrix_insertion_notes: {paths['matrix_insertion_notes']}")
        print(f"ucalc_schema_csv: {paths['ucalc_schema_csv']}")
        print(f"matrix_schema_csv: {paths['matrix_schema_csv']}")
        print(f"family_summary_csv: {paths['family_summary_csv']}")
        print(f"json: {paths['json']}")
        print(f"markdown: {paths['markdown']}")


if __name__ == "__main__":
    main()
