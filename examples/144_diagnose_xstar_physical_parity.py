#!/usr/bin/env python3
from __future__ import annotations

import argparse

from xstar_atomic.source_port.physical_output_diagnostics import (
    diagnose_physical_output_mismatch,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose original/Python XSTAR physical output mismatches")
    parser.add_argument("--original-run-dir", required=True)
    parser.add_argument("--python-output-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--print-summary", action="store_true")
    parser.add_argument(
        "--python-detail-guard-shift",
        action="store_true",
        help="correct the known one-row detail-population shift in v0.4.75 products",
    )
    args = parser.parse_args()
    result = diagnose_physical_output_mismatch(
        args.original_run_dir,
        args.python_output_dir,
        output_dir=args.out_dir,
        python_detail_guard_shift=args.python_detail_guard_shift,
    )
    if args.print_summary:
        for key, value in result.summary.items():
            print(f"{key}={value}")
        for key, path in result.products.items():
            print(f"{key}={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
