#!/usr/bin/env python3
"""Validate the compact v0.4.34 oxygen regression gates."""
from __future__ import annotations

from collections import Counter
from importlib import resources
import csv
import json


def _rows(root, name):
    with root.joinpath(name).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    root = resources.files("xstar_atomic.benchmarks").joinpath("oxygen_v0434")
    manifest = json.loads(root.joinpath("benchmark_manifest.json").read_text(encoding="utf-8"))
    expected = manifest["expected_counts"]

    global_rows = _rows(root, "v0433_global_level_remaining_rows.csv")
    observed = {
        "rnisg_rows": Counter(row["component"] for row in global_rows)["global_level_rnisg"],
        "bilevg_rows": Counter(row["component"] for row in global_rows)["global_level_bilevg"],
        "type53_leveltemp_rows": len(_rows(root, "v0433_type53_leveltemp_remaining_rows.csv")),
        "type53_cj2_records": len(_rows(root, "v0433_type53_cj2_remaining_records.csv")),
        "type99_ans5_records": len(_rows(root, "v0433_type99_ans5_rows.csv")),
        "thermal_family_rows": len(_rows(root, "v0433_thermal_family_remaining_rows.csv")),
    }
    ready = observed == expected
    print("xstar-atomic v0.4.34 bounded oxygen regression")
    print("------------------------------------------------")
    for key in expected:
        print(f"{key}={observed[key]} expected={expected[key]}")
    print(f"v0434_regression_gate_inventory_ready={ready}")
    print("production_probe_values_enter_operator=False")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
