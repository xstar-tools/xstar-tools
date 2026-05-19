#!/usr/bin/env python3
"""Audit the six bounded v0.4.34 oxygen correction gates."""
from __future__ import annotations

import argparse
from pathlib import Path

from xstar_atomic.source_port.v0434_regression import (
    assess_v0434_oxygen_correction_gates,
    write_v0434_regression_gate_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    result = assess_v0434_oxygen_correction_gates(args.output_dir)
    print("xstar-atomic v0.4.34 focused oxygen correction gates")
    print("---------------------------------------------------")
    for key, value in result.counts.items():
        print(f"{key}={value}")
    print(f"baseline_target_match={result.baseline_target_match}")
    print(f"closure_ready={result.closure_ready}")
    if args.json:
        path = write_v0434_regression_gate_summary(result, args.json)
        print(f"json: {path}")
    return 0 if (result.baseline_target_match or result.closure_ready) else 1


if __name__ == "__main__":
    raise SystemExit(main())
