"""Compatibility CLI for the native xstar_tools 0.6.83.1 xstinitable planner."""

from __future__ import annotations

import argparse
import sys

from xstar_tools.tables.init import build_xstinitable


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="xstar-tools-xstinitable",
        description="Create xstinitable.lis and xstinitable.fits for xstar-cpp or Fortran XSTAR.",
    )
    parser.add_argument("--xstar", choices=("cpp", "fortran"), default="cpp")
    parser.add_argument("--input")
    parser.add_argument("--data-dir", "-data-dir", dest="data_dir")
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("parameters", nargs="*", help="xstinitable key=value overrides")
    ns = parser.parse_args()
    if not ns.input and not ns.parameters:
        parser.error("provide --input xstinitable.par or at least one key=value parameter")
    completed = build_xstinitable(
        ns.parameters,
        ns.output_dir,
        input_file=ns.input,
        xstar=ns.xstar,
        data_dir=ns.data_dir,
    )
    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
