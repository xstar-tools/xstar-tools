"""CLI for the complete local XSTAR ``xstarcalc`` source-port milestone."""
from __future__ import annotations

import argparse

from .xstar.xstarcalc import (
    run_complete_local_xstarcalc_validation,
    write_complete_local_xstarcalc_validation_products,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate complete local xstarcalc ordering, dsec skip semantics, "
            "shared workspaces, reduced/full continuum ownership, and nry."
        )
    )
    parser.add_argument("--rtol", type=float, default=2.0e-14)
    parser.add_argument("--atol", type=float, default=1.0e-30)
    parser.add_argument(
        "--out-dir",
        default="xstar_complete_local_xstarcalc_source_validation_v0463",
    )
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_complete_local_xstarcalc_validation(
        rtol=args.rtol,
        atol=args.atol,
    )
    paths = write_complete_local_xstarcalc_validation_products(
        summary,
        args.out_dir,
    )
    if args.print_summary:
        print("XSTAR complete local xstarcalc source validation")
        print("------------------------------------------------")
        for key, value in summary.items():
            print(f"{key}={value}")
        for key, value in paths.items():
            print(f"{key}={value}")
    return 0 if summary["complete_local_xstarcalc_source_acceptance_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
