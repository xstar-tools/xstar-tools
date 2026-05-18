#!/usr/bin/env python3
"""Write one-time Fortran instrumentation for XSTAR msolvelucy state parity."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_msolvelucy_state_probe import write_msolvelucy_state_probe_products


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    outputs = write_msolvelucy_state_probe_products(args.out_dir)
    if args.print_summary:
        print("XSTAR msolvelucy state-probe preparation")
        print("-----------------------------------------")
        print("port_version=v0.4.18")
        print("status=msolvelucy_state_probe_products_written")
        for key, path in outputs.items():
            print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
