"""CLI for generating the bounded XSTAR ``dsec`` trajectory probe."""
from __future__ import annotations

import argparse
from pathlib import Path

from .xstar_dsec_probe import write_dsec_probe_products


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write diagnostic-only XSTAR dsec trajectory probe sources."
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    products = write_dsec_probe_products(args.out_dir)
    for name, path in products.items():
        print(f"{name}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
