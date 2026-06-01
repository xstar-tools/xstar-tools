"""CLI for the bounded XSTAR ``calc_emisab_all`` source-port milestone."""
from __future__ import annotations
import argparse
from .xstar.emissivity import run_source_order_validation, write_calc_emisab_validation_products


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Validate calc_emisab_all/calc_emisab_element/calc_emisab_ion "
            "source ordering, array ownership, aliases, and rate-type branches."
        )
    )
    p.add_argument("--rtol", type=float, default=2.0e-14)
    p.add_argument("--atol", type=float, default=1.0e-30)
    p.add_argument("--out-dir", default="xstar_calc_emisab_all_source_validation_v0461")
    p.add_argument("--print-summary", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    summary = run_source_order_validation(rtol=a.rtol, atol=a.atol)
    paths = write_calc_emisab_validation_products(summary, a.out_dir)
    if a.print_summary:
        print("XSTAR calc_emisab_all source validation")
        print("-----------------------------------------")
        for key, value in summary.items():
            print(f"{key}={value}")
        for key, value in paths.items():
            print(f"{key}={value}")
    return 0 if summary["calc_emisab_all_source_acceptance_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
