"""CLI for the bounded XSTAR ``calc_emis_all`` source-port milestone."""
from __future__ import annotations
import argparse
from .source_port.emergent_emissivity import (
    run_calc_emis_source_order_validation,
    write_calc_emis_validation_products,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate calc_emis_all/rlbin/calc_emis_element/calc_emis_ion "
            "source ordering, ranking, array ownership, and continuum slots."
        )
    )
    parser.add_argument("--rtol", type=float, default=2.0e-14)
    parser.add_argument("--atol", type=float, default=1.0e-30)
    parser.add_argument("--out-dir", default="xstar_calc_emis_all_source_validation_v0462")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_calc_emis_source_order_validation(rtol=args.rtol, atol=args.atol)
    paths = write_calc_emis_validation_products(summary, args.out_dir)
    if args.print_summary:
        print("XSTAR calc_emis_all source validation")
        print("---------------------------------------")
        for key, value in summary.items():
            print(f"{key}={value}")
        for key, value in paths.items():
            print(f"{key}={value}")
    return 0 if summary["calc_emis_all_source_acceptance_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
