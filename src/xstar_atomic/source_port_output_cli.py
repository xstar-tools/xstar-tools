"""CLI for the bounded XSTAR detail and final output-writer milestone."""
from __future__ import annotations

import argparse

from .source_port.output_writers import (
    run_output_writer_validation,
    write_output_writer_validation_products,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the source-order savd/fstepr detail writers and final "
            "writespectra sequence on the accepted bounded radial state. "
            "Legacy pprint ASCII reports and physical all-ATDB spectral "
            "parity remain explicit downstream work."
        )
    )
    parser.add_argument("--rtol", type=float, default=2.0e-7)
    parser.add_argument("--atol", type=float, default=0.0)
    parser.add_argument(
        "--out-dir",
        default="xstar_output_writer_source_validation_v0469",
    )
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_output_writer_validation(
        out_dir=args.out_dir,
        rtol=args.rtol,
        atol=args.atol,
    )
    paths = write_output_writer_validation_products(summary, args.out_dir)
    if args.print_summary:
        print("XSTAR detail and final output-writer source validation")
        print("------------------------------------------------------")
        for key, value in summary.items():
            print(f"{key}={value}")
        for key, value in paths.items():
            print(f"{key}={value}")
    return 0 if summary["detail_and_final_output_writer_source_acceptance_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
