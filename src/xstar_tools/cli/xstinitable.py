"""Compatibility CLI for the native xstar_tools 0.6.83 xstinitable planner."""

from __future__ import annotations

import argparse
import sys

from xstar_tools.tables.init import build_xstinitable


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="xstar-tools-xstinitable",
        description="Create canonical-compatible xstinitable.lis and xstinitable.fits.",
    )
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("parameters", nargs="*", help="historical xstinitable key=value arguments")
    ns = parser.parse_args()
    if not ns.parameters:
        parser.error("at least one key=value parameter is required")
    completed = build_xstinitable(ns.parameters, ns.output_dir)
    if completed.stdout:
        sys.stdout.write(completed.stdout)
    if completed.stderr:
        sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
