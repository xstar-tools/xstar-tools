#!/usr/bin/env python3
"""Reproduce same-run XSTAR local targets from xout_abund1/xout_lines1.

This example is the benchmark anchor for C V, O VII, Mg XI, and Ca XIX after the
API reorganization.  It extracts the exact local state from ``xout_abund1.fits``
and exact He-like triplet target from ``xout_lines1.fits``.  Optionally, it can
run the current xstar-atomic population solver and write residuals, but it does
not inject any new type-50 line-pumping physics.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

from xstar_atomic.benchmark import (
    default_helike_benchmark_cases,
    read_cases_csv,
    reproduce_xstar_run,
    run_xstar_benchmark_suite,
    write_default_helike_cases_csv,
    write_xstar_benchmark_outputs,
    write_xstar_benchmark_suite,
)


def _parse_window(text: str | None):
    if not text:
        return None
    parts = [float(x) for x in text.replace(",", " ").split()]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("wavelength window must contain two numbers")
    return (parts[0], parts[1])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", help="One XSTAR run directory containing xout_abund1.fits and xout_lines1.fits")
    p.add_argument("--ion", help="Ion label, e.g. 'O VII'")
    p.add_argument("--cases-csv", help="CSV with columns ion,run_dir and optional zone_index,selection,wavelength_window_A")
    p.add_argument("--standard-helike-suite", action="store_true", help="Run the built-in C V / O VII / Mg XI / Ca XIX benchmark suite")
    p.add_argument("--xstar-runs-root", default="xstar_runs", help="Root directory used by --standard-helike-suite")
    p.add_argument("--write-standard-cases-csv", help="Write the built-in four-ion case table to this CSV and exit")
    p.add_argument("--zone-index", type=int, help="Explicit XSTAR zone index to select from xout_abund1.fits")
    p.add_argument("--selection", default="max_fraction", help="Zone selection policy when zone-index is not given")
    p.add_argument("--wavelength", type=_parse_window, help="Two-number wavelength window in Angstrom, e.g. '21 23'")
    p.add_argument("--value-column", default="emit_outward", help="XSTAR xout_lines1 value column to use")
    p.add_argument("--run-solver", action="store_true", help="Also run the current population solver and compare residuals")
    p.add_argument("--solver-preset", default="workflow-default", choices=["workflow-default", "xstar-local-state"], help="Solver settings for --run-solver. workflow-default uses the lightweight public wrapper; xstar-local-state mirrors examples/51 local-state validation flags.")
    p.add_argument("--atdb", help="Path to XSTAR atdb.fits if --run-solver is used")
    p.add_argument("--out-dir", default="xstar_local_reproduction_benchmark", help="Output directory")
    p.add_argument("--print-summary", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    out_dir = Path(args.out_dir)
    solver_atdb = None
    if args.run_solver:
        from xstar_atomic.data import resolve_atdb_path

        # Resolve once here so --run-solver works from explicit --atdb,
        # XSTAR_ATDB_FITS, XSTAR_ATDB, or the configured datapath file.
        solver_atdb = resolve_atdb_path(args.atdb or None, prompt=False)
    if args.write_standard_cases_csv:
        path = write_default_helike_cases_csv(args.write_standard_cases_csv, xstar_runs_root=args.xstar_runs_root)
        if args.print_summary:
            print(f"Wrote standard C/O/Mg/Ca cases CSV: {path}")
        return
    if args.cases_csv or args.standard_helike_suite:
        if args.standard_helike_suite:
            cases = default_helike_benchmark_cases(args.xstar_runs_root)
        else:
            cases = read_cases_csv(args.cases_csv)
        comparisons = run_xstar_benchmark_suite(
            cases,
            value_column=args.value_column,
            run_solver=args.run_solver,
            fitsfile=solver_atdb,
            solver_preset=args.solver_preset,
        )
        paths = write_xstar_benchmark_suite(comparisons, out_dir)
        if args.print_summary:
            print("XSTAR local-output reproduction benchmark suite")
            print("------------------------------------------------")
            print(f"n_cases={len(comparisons)}")
            if solver_atdb is not None:
                print(f"solver_atdb={solver_atdb}")
            for comparison in comparisons:
                row = comparison.comparison_row()
                print(
                    f"ion={row.get('ion')} T={row.get('temperature_K')} K "
                    f"ne={row.get('electron_density_cm^-3')} cm^-3 "
                    f"logxi={row.get('log_xi')} "
                    f"xstar_f/i/r={row.get('xstar_f_fraction')}/{row.get('xstar_i_fraction')}/{row.get('xstar_r_fraction')} "
                    f"xstar_R/G/L2={row.get('xstar_R_f_over_i')}/{row.get('xstar_G_f_plus_i_over_r')}/{row.get('xstar_L2_to_xstar')} "
                    f"solver_f/i/r={row.get('solver_f_fraction')}/{row.get('solver_i_fraction')}/{row.get('solver_r_fraction')} "
                    f"solver_R/G/L2={row.get('solver_R_f_over_i')}/{row.get('solver_G_f_plus_i_over_r')}/{row.get('solver_L2_to_xstar')} "
                    f"source={row.get('solver_triplet_source')} "
                    f"status={comparison.status}"
                )
                if row.get("comparison_warnings"):
                    print(f"  warnings={row.get('comparison_warnings')}")
            for key, path in paths.items():
                print(f"{key}: {path}")
        return

    if not args.run_dir or not args.ion:
        raise SystemExit("Either --standard-helike-suite, --cases-csv, or both --run-dir and --ion are required")
    comparison = reproduce_xstar_run(
        args.run_dir,
        ion=args.ion,
        zone_index=args.zone_index,
        selection=args.selection,
        wavelength=args.wavelength,
        value_column=args.value_column,
        run_solver=args.run_solver,
        fitsfile=solver_atdb,
        solver_preset=args.solver_preset,
    )
    paths = write_xstar_benchmark_outputs(comparison, out_dir)
    if args.print_summary:
        print("XSTAR local-output reproduction benchmark")
        print("-----------------------------------------")
        for key, path in paths.items():
            print(f"{key}: {path}")
        row = comparison.comparison_row()
        print(f"ion={row.get('ion')}")
        print(f"T={row.get('temperature_K')} K")
        print(f"ne={row.get('electron_density_cm^-3')} cm^-3")
        print(f"logxi={row.get('log_xi')}")
        print(f"xstar_f/i/r={row.get('xstar_f_fraction')}/{row.get('xstar_i_fraction')}/{row.get('xstar_r_fraction')}")
        print(f"xstar_R/G/L2={row.get('xstar_R_f_over_i')}/{row.get('xstar_G_f_plus_i_over_r')}/{row.get('xstar_L2_to_xstar')}")
        print(f"solver_f/i/r={row.get('solver_f_fraction')}/{row.get('solver_i_fraction')}/{row.get('solver_r_fraction')}")
        print(f"solver_R/G/L2={row.get('solver_R_f_over_i')}/{row.get('solver_G_f_plus_i_over_r')}/{row.get('solver_L2_to_xstar')}")
        print(f"solver_triplet_source={row.get('solver_triplet_source')}")
        if solver_atdb is not None:
            print(f"solver_atdb={solver_atdb}")
        print(f"status={comparison.status}")
        if row.get("comparison_warnings"):
            print(f"warnings={row.get('comparison_warnings')}")


if __name__ == "__main__":
    main()
