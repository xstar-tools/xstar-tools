"""Legacy MPI_XSTAR-style local-process compatibility wrapper.

This Python command does not launch MPI ranks: ``--np`` remains a compatibility
alias for local ``xstar-xspec --workers``.  For true MPI in 0.6.86, build
``xstar-xspec-mpi`` with ``make mpi`` and launch it with ``mpirun``/``mpiexec``.
"""

from __future__ import annotations

import argparse
import sys

from xstar_tools.tables.pipeline import run_xstar2xspec


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="xstar-tools-mpixstar",
        description="Legacy MPI_XSTAR-style local-process wrapper (not true MPI; use xstar-xspec-mpi for MPI).",
    )
    parser.add_argument("--input")
    parser.add_argument("--data-dir", "-data-dir", dest="data_dir")
    parser.add_argument("--output-dir", "--output", default=".")
    parser.add_argument("--workers", "--np", "-j", dest="workers", type=int, default=1)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("parameters", nargs="*", help="xstinitable key=value overrides")
    ns = parser.parse_args()
    if ns.workers < 1:
        parser.error("--workers/--np must be >= 1")
    if not ns.input and not ns.parameters:
        parser.error("provide --input xstinitable.par or at least one key=value parameter")
    completed = run_xstar2xspec(
        ns.parameters,
        ns.output_dir,
        input_file=ns.input,
        data_dir=ns.data_dir,
        workers=ns.workers,
        save=ns.save,
        restart=ns.restart,
        verbose=ns.verbose,
    )
    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
