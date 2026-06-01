"""CLI for the bounded XSTAR ``bremsmap`` source-port milestone."""
from __future__ import annotations
import argparse
from .xstar.radiation import run_direct_fortran_reference_validation, write_bremsmap_validation_products


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Validate the source-faithful bremsmap/nbinc/huntf translation against frozen direct-Fortran cases.")
    p.add_argument("--rtol", type=float, default=2.0e-15)
    p.add_argument("--atol", type=float, default=0.0)
    p.add_argument("--out-dir", default="xstar_bremsmap_source_validation_v0460")
    p.add_argument("--print-summary", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    summary = run_direct_fortran_reference_validation(rtol=a.rtol, atol=a.atol)
    paths = write_bremsmap_validation_products(summary, a.out_dir)
    if a.print_summary:
        print("XSTAR bremsmap source validation")
        print("--------------------------------")
        for k, v in summary.items():
            print(f"{k}={v}")
        for k, v in paths.items():
            print(f"{k}={v}")
    return 0 if summary["bremsmap_source_acceptance_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
