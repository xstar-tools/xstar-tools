#!/usr/bin/env python3
"""Prepare or validate an XSTAR live rate-grid probe product.

This example is the v0.3.170 follow-up to the source-code audits in examples
70 and 71.  It does not change solver physics.  It writes a compact schema and
Fortran probe template for capturing the actual rate-grid arrays used by
``phint53``: ``epim(:), bremsam(:), bremsint(:)`` after ``bremsmap`` and before
``calc_hmc_all``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from xstar_atomic.xstar_live_rate_grid_probe import prepare_live_rate_grid_probe_products


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--probe-csv", default=None, help="Optional live-rate-grid probe CSV to validate/summarize.")
    ap.add_argument("--out-dir", default="xstar_live_rate_grid_probe_v03170")
    ap.add_argument("--print-summary", action="store_true")
    args = ap.parse_args()

    outputs = prepare_live_rate_grid_probe_products(args.out_dir, probe_csv=args.probe_csv)
    if args.print_summary:
        summary = json.loads(Path(outputs["json"]).read_text(encoding="utf-8"))["summary"]
        print("XSTAR live rate-grid probe preparation")
        print("--------------------------------------")
        print(f"audit_version={summary.get('audit_version')}")
        print(f"probe_status={summary.get('probe_status')}")
        if summary.get("probe_csv"):
            print(f"probe_csv={summary.get('probe_csv')}")
        print(f"n_probe_states={summary.get('n_probe_states')}")
        print(f"n_probe_grid_points_total={summary.get('n_probe_grid_points_total')}")
        print(f"probe_ready_for_type53_phint53_live_bremsam_audit={summary.get('probe_ready_for_type53_phint53_live_bremsam_audit')}")
        print(f"correct_capture_site={summary.get('correct_capture_site')}")
        print(f"correct_live_rate_field={summary.get('correct_live_rate_field')}")
        print(f"schema_csv: {outputs['schema_csv']}")
        print(f"fortran_template: {outputs['fortran_template']}")
        print(f"json: {outputs['json']}")
        print(f"markdown: {outputs['markdown']}")


if __name__ == "__main__":
    main()
