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
    read_cases_csv,
    reproduce_xstar_run,
    run_xstar_benchmark_suite,
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
    p.add_argument("--zone-index", type=int, help="Explicit XSTAR zone index to select from xout_abund1.fits")
    p.add_argument("--selection", default="max_fraction", help="Zone selection policy when zone-index is not given")
    p.add_argument("--wavelength", type=_parse_window, help="Two-number wavelength window in Angstrom, e.g. '21 23'")
    p.add_argument("--value-column", default="emit_outward", help="XSTAR xout_lines1 value column to use")
    p.add_argument("--run-solver", action="store_true", help="Also run the current population solver and compare residuals")
    p.add_argument("--atdb", help="Path to XSTAR atdb.fits if --run-solver is used")
    p.add_argument("--out-dir", default="xstar_local_reproduction_benchmark", help="Output directory")
    p.add_argument("--print-summary", action="store_true")
    return p


def main() -> None:
    args = build_parser().parse_args()
    out_dir = Path(args.out_dir)
    if args.cases_csv:
        cases = read_cases_csv(args.cases_csv)
        comparisons = run_xstar_benchmark_suite(
            cases,
            value_column=args.value_column,
            run_solver=args.run_solver,
            fitsfile=args.atdb,
        )
        paths = write_xstar_benchmark_suite(comparisons, out_dir)
        if args.print_summary:
            print("XSTAR local-output reproduction benchmark suite")
            print("------------------------------------------------")
            print(f"n_cases={len(comparisons)}")
            for key, path in paths.items():
                print(f"{key}: {path}")
        return

    if not args.run_dir or not args.ion:
        raise SystemExit("Either --cases-csv or both --run-dir and --ion are required")
    comparison = reproduce_xstar_run(
        args.run_dir,
        ion=args.ion,
        zone_index=args.zone_index,
        selection=args.selection,
        wavelength=args.wavelength,
        value_column=args.value_column,
        run_solver=args.run_solver,
        fitsfile=args.atdb,
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
        print(f"status={comparison.status}")


if __name__ == "__main__":
    main()
