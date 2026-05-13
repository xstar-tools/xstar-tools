#!/usr/bin/env python3
"""Prepare local XSTAR instrumentation files for the live rate-grid probe.

This helper does not modify XSTAR automatically. It writes a standalone Fortran
helper subroutine and a small call block to insert immediately after
``call bremsmap(...)`` in ``xstarcalc.f90``. The resulting local/debug XSTAR
build can write ``xstar_live_rate_grid_probe.csv`` for validation by example 72
and for the next type-53 live ``phint53`` audit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xstar_atomic.xstar_live_rate_grid_probe import prepare_live_rate_grid_probe_patch_products


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xstar-source-root", default=None, help="Optional XSTAR source root used to locate xstarcalc.f90 and the bremsmap call.")
    ap.add_argument("--out-dir", default="xstar_live_rate_grid_probe_patch_v03171")
    ap.add_argument("--probe-filename", default="xstar_live_rate_grid_probe.csv")
    ap.add_argument("--zone-expression", default="-1", help="Fortran expression for zone_index; replace with real shell counter if available.")
    ap.add_argument("--pass-expression", default="1", help="Fortran expression for pass_index.")
    ap.add_argument("--ldir-expression", default="0", help="Fortran expression for ldir if available.")
    ap.add_argument("--guarded", action="store_true", help="Wrap the call in an if (lpri2.lt.0) debug guard.")
    ap.add_argument("--print-summary", action="store_true")
    args = ap.parse_args()

    outputs = prepare_live_rate_grid_probe_patch_products(
        args.out_dir,
        xstar_source_root=args.xstar_source_root,
        filename=args.probe_filename,
        zone_expression=args.zone_expression,
        pass_expression=args.pass_expression,
        ldir_expression=args.ldir_expression,
        guarded=args.guarded,
    )
    if args.print_summary:
        summary = json.loads(Path(outputs["json"]).read_text(encoding="utf-8"))["summary"]
        print("XSTAR live rate-grid probe patch preparation")
        print("--------------------------------------------")
        print(f"audit_version={summary.get('audit_version')}")
        print(f"capture_site_status={summary.get('capture_site_status')}")
        if summary.get("xstarcalc_path"):
            print(f"xstarcalc_path={summary.get('xstarcalc_path')}")
        if summary.get("bremsmap_line_number"):
            print(f"bremsmap_line_number={summary.get('bremsmap_line_number')}")
        print(f"probe_output_csv={summary.get('probe_output_csv')}")
        print(f"zone_expression={summary.get('zone_expression')}")
        print(f"guarded_by_lpri2_negative={summary.get('guarded_by_lpri2_negative')}")
        print(f"helper_fortran: {outputs['helper_fortran']}")
        print(f"insertion_block: {outputs['insertion_block']}")
        print(f"json: {outputs['json']}")
        print(f"markdown: {outputs['markdown']}")


if __name__ == "__main__":
    main()
