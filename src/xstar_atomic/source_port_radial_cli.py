"""CLI for the bounded XSTAR radial-shell source-port milestone."""
from __future__ import annotations

import argparse

from .source_port.radial_transfer import (
    run_bounded_radial_shell_validation,
    write_bounded_radial_shell_validation_products,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate step/trnfrc/gsmooth/heatt/stpcut/trnfrn plus unsavd, "
            "the inline density.dat branch, and the fixed requested-pass contract "
            "without entering detail or final output writers."
        )
    )
    parser.add_argument("--rtol", type=float, default=2.0e-14)
    parser.add_argument("--atol", type=float, default=1.0e-30)
    parser.add_argument(
        "--out-dir",
        default="xstar_bounded_radial_shell_source_validation_v0468",
    )
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_bounded_radial_shell_validation(
        rtol=args.rtol,
        atol=args.atol,
    )
    paths = write_bounded_radial_shell_validation_products(summary, args.out_dir)
    if args.print_summary:
        print("XSTAR bounded radial-shell source validation")
        print("--------------------------------------------")
        for key, value in summary.items():
            print(f"{key}={value}")
        for key, value in paths.items():
            print(f"{key}={value}")
    return 0 if summary["bounded_radial_shell_source_acceptance_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
