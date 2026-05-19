#!/usr/bin/env python3
"""Inventory the original XSTAR source tree and write the Python port ledger."""

from __future__ import annotations

import argparse
from pathlib import Path

from xstar_atomic.source_port import (
    build_source_inventory,
    default_port_ledger,
    write_source_inventory,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory the XSTAR Fortran source and initialize the source-port ledger."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--source-root", help="Extracted XSTAR source-tree root")
    group.add_argument("--source-tar", help="XSTAR source tarball")
    parser.add_argument("--out-dir", default="xstar_python_source_port_inventory_v0424")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    inventory = build_source_inventory(
        source_root=args.source_root,
        source_tar=args.source_tar,
    )
    outputs = write_source_inventory(inventory, args.out_dir)
    ledger_outputs = default_port_ledger().write(args.out_dir)

    if args.print_summary:
        print("XSTAR source-faithful Python port inventory")
        print("-------------------------------------------")
        print("port_version=v0.4.28")
        print(f"source={inventory.source_label}")
        print(f"n_source_files={inventory.n_files}")
        print(f"n_routines={inventory.n_routines}")
        print(f"ledger_status_counts={default_port_ledger().status_counts()}")
        for key, value in outputs.items():
            print(f"{key}: {value}")
        for key, value in ledger_outputs.items():
            print(f"ledger_{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
