#!/usr/bin/env python3
"""Run an O VII triplet sparse level-population solver stress test.

This example exercises the Stage-3 solver options: sparse solving, XSTAR
same-n l-mixing density, optional connectivity pruning, and O VII triplet
R/G diagnostics.  The resulting R and G ratios are prototype solver outputs;
physical interpretation requires a complete recombination/cascade source model.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from xstar_atomic.solver import main as solver_main


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile", help="Path to XSTAR atdb.fits")
    parser.add_argument("--out-dir", default="o7_triplet_solver_example", help="Output directory")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    solver_main([
        args.fitsfile,
        "--element", "O",
        "--ion-stage", "7",
        "--wavelength-min", "21.4",
        "--wavelength-max", "22.2",
        "--temperatures", "1e6",
        "--electron-densities", "1.0", "1e4", "1e8",
        "--electron-density-for-lmixing", "1.0",
        "--component-mode", "ground",
        "--prune-unconnected-levels",
        "--linear-solver", "sparse",
        "--out-lines-csv", str(out / "o7_triplet_lines_sparse.csv"),
        "--out-populations-csv", str(out / "o7_triplet_populations_sparse.csv"),
        "--out-triplet-csv", str(out / "o7_triplet_RG_sparse.csv"),
        "--summary-json", str(out / "o7_triplet_sparse_summary.json"),
        "--print-summary",
    ])


if __name__ == "__main__":
    main()
