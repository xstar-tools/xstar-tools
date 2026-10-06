#!/usr/bin/env python3
"""Fail-closed validation for Tier-1/2/3 benchmark results and provenance."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

SCIENCE_REVISION = "0.6.90.5.5"
ZONE_ABI = 6048110


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-root", required=True)
    p.add_argument("--comparison-root", required=True)
    p.add_argument("--require-mode", action="append", default=[])
    p.add_argument("--require-case", action="append", default=[])
    p.add_argument("--require-cpp44-exact", action="store_true")
    p.add_argument("--require-current-backend-science", action="store_true")
    args = p.parse_args(argv)

    run_root = Path(args.run_root).resolve()
    comparison = Path(args.comparison_root).resolve()
    summary = json.loads((comparison / "comparison_summary.json").read_text())
    model_rows = _csv(comparison / "fortran_model_summary.csv")
    product_rows = _csv(comparison / "fortran_product_summary.csv")

    errors: list[str] = []
    if not summary.get("fortran_all_science_accept"):
        errors.append("Fortran material science summary rejected")
    for row in product_rows:
        if row.get("gate") != "ACCEPT":
            errors.append(f"publication/material product rejected: {row.get('mode')} {row.get('case')} {row.get('product')}")
    modes = {row.get("mode", "") for row in model_rows}
    cases = {row.get("case", "") for row in model_rows}
    for mode in args.require_mode:
        if mode not in modes:
            errors.append(f"required mode absent from comparison: {mode}")
    for case in args.require_case:
        if case not in cases:
            errors.append(f"required case absent from comparison: {case}")

    if args.require_cpp44_exact and not summary.get("cpp44_all_exact_accept"):
        errors.append("frozen C++44 exact regression rejected")
    if args.require_current_backend_science and not summary.get("current_backend_all_science"):
        errors.append("current selected-backend material parity rejected")

    provenance_count = 0
    for mode in sorted(modes):
        mode_root = run_root / "runs" / mode
        if not mode_root.is_dir():
            continue
        for case in sorted(cases):
            path = mode_root / case / "runner_summary.json"
            if not path.is_file():
                if mode == "xstar-cpp":
                    # Native mode provenance is embedded in native products/state;
                    # public_suite does not currently write a Python runner summary.
                    continue
                errors.append(f"missing runner summary: {mode} {case}")
                continue
            doc = json.loads(path.read_text())
            prov = doc.get("provenance", {})
            execution = prov.get("execution", {}) if isinstance(prov, dict) else {}
            data = prov.get("data", {}) if isinstance(prov, dict) else {}
            if execution.get("science_revision") != SCIENCE_REVISION:
                errors.append(f"science revision mismatch: {mode} {case}")
            if int(execution.get("zone_abi", -1)) != ZONE_ABI:
                errors.append(f"zone ABI mismatch: {mode} {case}")
            requested = execution.get("requested_mode")
            if requested != mode:
                errors.append(f"requested-mode provenance mismatch: {mode} {case}: {requested}")
            if not data.get("atdb_sha256") or not data.get("coheat_sha256"):
                errors.append(f"atomic-data provenance incomplete: {mode} {case}")
            provenance_count += 1

    if errors:
        print("CI_SCIENCE_RESULTS=REJECT")
        for error in errors:
            print("CI_SCIENCE_ERROR=" + error)
        return 1
    print("CI_SCIENCE_RESULTS=ACCEPT")
    print(f"CI_SCIENCE_MODEL_ROWS={len(model_rows)}")
    print(f"CI_SCIENCE_PRODUCT_ROWS={len(product_rows)}")
    print(f"CI_SCIENCE_PROVENANCE_ROWS={provenance_count}")
    print(f"CI_SCIENCE_PUBLICATION_DIAGNOSTIC_ROWS={sum(1 for r in product_rows if r.get('inventory_gate') == '0')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
