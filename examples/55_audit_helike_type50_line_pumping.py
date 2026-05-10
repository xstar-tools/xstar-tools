#!/usr/bin/env python3
"""CLI wrapper for :func:`xstar_atomic.audit.type50_line_pumping`.

The reusable v0.3.128 implementation lives in ``src/xstar_atomic/audit.py`` so
future API users can call the audit directly from Python.  This script preserves
the v0.3.127 command-line interface and output products.
"""
from __future__ import annotations

import argparse

from xstar_atomic.audit import type50_line_pumping


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Audit missing He-like type-50 line-pumping/photoexcitation source-code path.")
    ap.add_argument("--cases-csv", required=True, help="helike_local_state_cases.csv from example 51")
    ap.add_argument("--solver-root", default=".", help="root containing solver output directories")
    ap.add_argument("--xstar-source-root", default="", help="optional XSTAR source tree for provenance")
    ap.add_argument("--out-dir", default="helike_type50_line_pumping_audit_v03128")
    ap.add_argument("--print-summary", action="store_true")
    args = ap.parse_args(argv)

    type50_line_pumping(
        args.cases_csv,
        solver_root=args.solver_root,
        xstar_source_root=args.xstar_source_root or None,
        out_dir=args.out_dir,
        write_outputs=True,
        print_summary=args.print_summary,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
