#!/usr/bin/env python3
"""Validate the bounded v0.4.38 xiin/final-x versus xtot/xo correction."""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"missing required product: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _ion_key(text: str) -> tuple[int, int] | None:
    match = re.search(r"Z=(\d+),stage=(\d+)", text)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate v0.4.38 final-x xiin and final-outer-start xtot semantics."
    )
    parser.add_argument("output_dir", help="Completed example-108 v0.4.38 output directory")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.output_dir)
    summary_path = root / "xstar_calc_hmc_all_pre_continuum_parity_summary.json"
    scope_path = root / "xstar_calc_hmc_all_all_element_scope_summary.json"
    if not summary_path.is_file():
        raise SystemExit(f"missing required product: {summary_path}")
    if not scope_path.is_file():
        raise SystemExit(f"missing required product: {scope_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    scope = json.loads(scope_path.read_text(encoding="utf-8"))

    detail_rows = _rows(root / "xstar_calc_hmc_all_pre_continuum_parity_details.csv")
    total_rows = _rows(root / "xstar_calc_hmc_all_msolvelucy_final_ion_totals.csv")
    final_rows = _rows(root / "xstar_calc_hmc_all_msolvelucy_final_population_parity.csv")
    thermal_rows = _rows(root / "xstar_calc_hmc_all_xstar_thermal_family_parity.csv")

    xiin_rows = [row for row in detail_rows if row.get("component") == "global_ion_xiin"]
    xiin_bad = [row for row in xiin_rows if not _bool(row.get("within_tolerance"))]
    xiin_ready = bool(xiin_rows) and not xiin_bad

    detail_xiin: dict[tuple[int, int], float] = {}
    for row in xiin_rows:
        key = _ion_key(row.get("key", ""))
        if key is not None:
            detail_xiin[key] = float(row["python_value"])

    final_total_match = True
    source_xtot_ready = bool(total_rows)
    distinct_semantics_seen = False
    for row in total_rows:
        z = int(row["element_z"])
        stage = int(row["ion_stage"])
        final_total = float(row["python_final_vector_xtot"])
        source_total = float(row["python_source_xtot"])
        if (z, stage) not in detail_xiin:
            final_total_match = False
        else:
            scale = max(abs(final_total), abs(detail_xiin[(z, stage)]), 1.0e-300)
            if abs(detail_xiin[(z, stage)] - final_total) > 1.0e-12 + 5.0e-3 * scale:
                final_total_match = False
        source_xtot_ready = source_xtot_ready and _bool(row.get("source_xtot_within_tolerance"))
        if z == 1 and abs(final_total - source_total) > 1.0e-12:
            distinct_semantics_seen = True

    active_rows = [row for row in final_rows if _bool(row.get("active_population"))]
    active_solver_ready = bool(active_rows) and all(
        _bool(row.get("final_population_within_tolerance"))
        and _bool(row.get("outer_start_population_within_tolerance"))
        for row in active_rows
    )
    thermal_ready = bool(thermal_rows) and all(_bool(row.get("within_tolerance")) for row in thermal_rows)
    blockers = [
        row for row in detail_rows
        if _bool(row.get("milestone_blocking")) and not _bool(row.get("within_tolerance"))
    ]

    gate_ready = summary.get("all_element_pre_continuum_acceptance_ready") is True
    oxygen_regression_ready = scope.get("oxygen_call73_regression_ready") is True
    ready = bool(
        xiin_ready
        and final_total_match
        and source_xtot_ready
        and distinct_semantics_seen
        and active_solver_ready
        and thermal_ready
        and not blockers
        and gate_ready
        and oxygen_regression_ready
    )

    print(f"global_ion_xiin_rows={len(xiin_rows)}")
    print(f"global_ion_xiin_rows_outside_tolerance={len(xiin_bad)}")
    print(f"global_ion_xiin_final_vector_parity_ready={xiin_ready}")
    print(f"xiin_matches_python_final_vector_totals={final_total_match}")
    print(f"source_xtot_outer_start_parity_ready={source_xtot_ready}")
    print(f"hydrogen_final_x_and_outer_start_xtot_are_distinct={distinct_semantics_seen}")
    print(f"all_element_active_solver_ready={active_solver_ready}")
    print(f"all_element_thermal_ready={thermal_ready}")
    print(f"milestone_blocking_rows={len(blockers)}")
    print(f"oxygen_call73_regression_ready={oxygen_regression_ready}")
    print(f"all_element_pre_continuum_acceptance_ready={gate_ready}")
    print(f"v0438_xiin_final_vector_validation_ready={ready}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
