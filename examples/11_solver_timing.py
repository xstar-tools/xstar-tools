#!/usr/bin/env python3
"""Benchmark xstar-atomic level-population solver execution times.

This example times end-to-end solver calls for representative O VIII and,
optionally, O VII cases.  The timings include database decoding, record
selection, matrix assembly, linear solve, and CSV/JSON output writing, so they
are useful for practical workflow comparisons between ``dense`` and ``sparse``
solver modes.

Examples
--------

O VIII dense/sparse timing::

    PYTHONPATH=src python examples/11_solver_timing.py ../xstar/data/atdb.fits

Include the heavier O VII triplet sparse stress test::

    PYTHONPATH=src python examples/11_solver_timing.py ../xstar/data/atdb.fits \
      --include-o7 --repeat 2 --out-csv solver_timing.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from pathlib import Path
from typing import Iterable

from xstar_atomic.solver import main as solver_main


def _run_solver(argv: list[str], summary_json: Path) -> dict:
    """Run the solver and return its summary JSON."""
    solver_main(argv + ["--summary-json", str(summary_json)])
    with summary_json.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _first_solve(summary: dict) -> dict:
    solves = summary.get("solves") or []
    return solves[0] if solves else {}


def _time_case(case_name: str, argv: list[str], out_dir: Path, repeat: int) -> list[dict]:
    rows: list[dict] = []
    for i in range(repeat):
        run_dir = out_dir / f"{case_name}_run{i + 1}"
        run_dir.mkdir(parents=True, exist_ok=True)
        summary_json = run_dir / "summary.json"
        full_argv = argv + [
            "--out-lines-csv", str(run_dir / "lines.csv"),
            "--out-populations-csv", str(run_dir / "populations.csv"),
        ]
        start = time.perf_counter()
        summary = _run_solver(full_argv, summary_json)
        elapsed = time.perf_counter() - start
        solve = _first_solve(summary)
        rows.append({
            "case": case_name,
            "repeat_index": i + 1,
            "elapsed_s": elapsed,
            "solver_requested": solve.get("solver_requested"),
            "solver_used": solve.get("solver"),
            "sparse_used": solve.get("sparse_used"),
            "matrix_size": solve.get("matrix_size"),
            "matrix_nnz": solve.get("matrix_nnz"),
            "matrix_density": solve.get("matrix_density"),
            "condition_number": solve.get("condition_number"),
            "linear_residual_linf": solve.get("linear_residual_linf"),
            "normalization_residual": solve.get("normalization_residual"),
            "n_levels_selected": summary.get("n_levels_selected"),
            "n_collision_eval_rows_used_in_matrix": summary.get("n_collision_eval_rows_used_in_matrix"),
            "summary_json": str(summary_json),
        })
    return rows


def _print_summary(rows: Iterable[dict]) -> None:
    by_case: dict[str, list[float]] = {}
    for row in rows:
        by_case.setdefault(str(row["case"]), []).append(float(row["elapsed_s"]))
    print("Solver timing summary")
    print("---------------------")
    for case, values in by_case.items():
        mean = statistics.mean(values)
        stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
        print(f"{case:24s} n={len(values):2d} mean={mean:.6g} s  std={stdev:.3g} s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fitsfile", help="Path to XSTAR atdb.fits")
    parser.add_argument("--repeat", type=int, default=1, help="Number of times to repeat each case")
    parser.add_argument("--out-dir", default="solver_timing_example", help="Directory for timing outputs")
    parser.add_argument("--out-csv", default="solver_timing.csv", help="CSV file for timing rows")
    parser.add_argument("--include-o7", action="store_true", help="Also run the heavier O VII triplet sparse case")
    parser.add_argument("--print-json", action="store_true", help="Print timing rows as JSON")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    base_o8 = [
        args.fitsfile,
        "--element", "O",
        "--ion-stage", "8",
        "--wavelength-min", "18.8",
        "--wavelength-max", "19.1",
        "--temperatures", "1e6",
        "--electron-densities", "1.0",
        "--electron-density-for-lmixing", "1.0",
        "--component-mode", "ground",
    ]

    cases: list[tuple[str, list[str]]] = [
        ("o8_dense", base_o8 + ["--linear-solver", "dense"]),
        ("o8_sparse", base_o8 + ["--linear-solver", "sparse"]),
    ]

    if args.include_o7:
        cases.append((
            "o7_triplet_sparse",
            [
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
                "--out-triplet-csv", str(out_dir / "o7_triplet_RG_sparse.csv"),
            ],
        ))

    rows: list[dict] = []
    for case_name, case_argv in cases:
        rows.extend(_time_case(case_name, case_argv, out_dir, max(1, args.repeat)))

    out_csv = Path(args.out_csv)
    if not out_csv.is_absolute():
        out_csv = out_dir / out_csv
    fieldnames = list(rows[0].keys()) if rows else []
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    _print_summary(rows)
    print(f"Wrote timing CSV: {out_csv}")
    if args.print_json:
        print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
