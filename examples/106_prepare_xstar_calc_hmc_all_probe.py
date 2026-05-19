#!/usr/bin/env python3
"""Write bounded XSTAR instrumentation for pre-continuum calc_hmc_all parity."""
from __future__ import annotations

import argparse

from xstar_atomic.xstar_calc_hmc_all_probe import write_calc_hmc_all_probe_products


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)
    outputs = write_calc_hmc_all_probe_products(args.out_dir)
    if args.print_summary:
        print("XSTAR calc_hmc_all pre-continuum probe preparation")
        print("----------------------------------------------------")
        print("port_version=v0.4.28")
        print("status=calc_hmc_all_probe_products_written")
        for key, path in outputs.items():
            print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
