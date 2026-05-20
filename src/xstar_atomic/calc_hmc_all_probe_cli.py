"""CLI for writing the bounded XSTAR ``calc_hmc_all`` probe products."""
from __future__ import annotations

import argparse

from .xstar_calc_hmc_all_probe import write_calc_hmc_all_probe_products


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write diagnostic-only XSTAR calc_hmc_all pre-continuum probe instrumentation."
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    outputs = write_calc_hmc_all_probe_products(args.out_dir)
    if args.print_summary:
        print("XSTAR calc_hmc_all pre-continuum probe preparation")
        print("----------------------------------------------------")
        print("port_version=v0.4.37")
        print("status=calc_hmc_all_probe_products_written")
        for key, path in outputs.items():
            print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
