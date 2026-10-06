#!/usr/bin/env python3
"""Produce a performance-only report without changing scientific acceptance."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-manifest", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--baseline-json")
    p.add_argument("--warn-regression", type=float, default=0.20,
                   help="report a warning when median wall time exceeds baseline by this fraction")
    args = p.parse_args(argv)
    rows = list(csv.DictReader(Path(args.run_manifest).open(newline="", encoding="utf-8")))
    grouped: dict[str, list[float]] = {}
    for row in rows:
        key = f"{row['mode']}::{row['case']}"
        grouped.setdefault(key, []).append(float(row.get("wall_seconds") or 0.0))
    medians = {key: median(values) for key, values in sorted(grouped.items())}
    baseline = json.loads(Path(args.baseline_json).read_text()) if args.baseline_json else {}
    warnings = []
    for key, current in medians.items():
        old = baseline.get("medians", {}).get(key) if isinstance(baseline, dict) else None
        if old is not None and float(old) > 0 and current > float(old) * (1.0 + args.warn_regression):
            warnings.append({"key": key, "current": current, "baseline": float(old), "fraction": current / float(old) - 1.0})
    report = {
        "schema": "xstar-tools-performance-report-v1",
        "science_gate": "separate",
        "performance_gate": "report-only",
        "medians": medians,
        "regression_warnings": warnings,
    }
    out = Path(args.out).resolve(); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("CI_PERFORMANCE_REPORT=ACCEPT")
    print(f"CI_PERFORMANCE_SERIES={len(medians)}")
    print(f"CI_PERFORMANCE_WARNINGS={len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
