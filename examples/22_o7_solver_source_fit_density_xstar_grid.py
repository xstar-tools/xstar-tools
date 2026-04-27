#!/usr/bin/env python3
"""Run the O VII density-grid source-fit diagnostic with density-dependent XSTAR references.

This is a convenience front end for ``examples/21_o7_solver_source_fit_density_grid.py``.
It is intended for the case where separate XSTAR ``xout_lines1.fits`` products
have already been converted to per-density triplet line CSV files.  Instead of
reusing one low-density XSTAR R/G target at all densities, each density is fitted
and validated against its own XSTAR reference.

Reference mapping can be supplied either as repeated ``DENSITY:CSV`` values::

    --xstar-lines-csv-by-density 1:xstar_o7_ne1_lines.csv \
    --xstar-lines-csv-by-density 1e10:xstar_o7_ne1e10_lines.csv

or as a CSV table::

    --xstar-grid-summary-csv xstar_o7_density_grid_references.csv

The mapping CSV should contain a density column such as ``electron_density_cm^-3``,
``density``, or ``ne``, plus a path column such as ``xstar_lines_csv`` or
``path``.  Optional columns are ``xstar_value_column`` and ``xstar_target_label``.

The fitted source weights remain empirical/diagnostic, not physical
level-resolved recombination rates.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def _has_option(argv: Sequence[str], *names: str) -> bool:
    return any(arg in names or any(arg.startswith(name + "=") for name in names) for arg in argv)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        add_help=False,
    )
    parser.add_argument("--help", action="store_true")
    parser.add_argument("--xstar-grid-summary-csv")
    parser.add_argument("--xstar-lines-csv-by-density", action="append", default=[])
    known, remaining = parser.parse_known_args()

    script = Path(__file__).resolve().with_name("21_o7_solver_source_fit_density_grid.py")
    if known.help:
        subprocess.run([sys.executable, str(script), "--help"], check=True)
        print("\nDensity-dependent XSTAR front end:")
        print("  Provide --xstar-grid-summary-csv or repeated --xstar-lines-csv-by-density DENSITY:CSV.")
        return

    if not known.xstar_grid_summary_csv and not known.xstar_lines_csv_by_density:
        raise SystemExit(
            "examples/22 requires density-dependent XSTAR references: "
            "use --xstar-grid-summary-csv or repeated --xstar-lines-csv-by-density DENSITY:CSV"
        )

    cmd = [sys.executable, str(script)] + remaining
    if known.xstar_grid_summary_csv:
        cmd += ["--xstar-grid-summary-csv", known.xstar_grid_summary_csv]
    for item in known.xstar_lines_csv_by_density:
        cmd += ["--xstar-lines-csv-by-density", item]
    if not _has_option(cmd, "--out-dir"):
        cmd += ["--out-dir", "o7_solver_source_fit_density_xstar_grid"]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
