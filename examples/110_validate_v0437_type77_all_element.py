#!/usr/bin/env python3
"""Validate the bounded v0.4.37 type-77 H/He/O production rerun."""
from __future__ import annotations

import argparse
import csv
import json
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate v0.4.37 type-77 source-zero and all-element gates."
    )
    parser.add_argument("output_dir", help="Completed example-108 v0.4.37 output directory")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.output_dir)
    summary_path = root / "xstar_calc_hmc_all_pre_continuum_parity_summary.json"
    if not summary_path.is_file():
        raise SystemExit(f"missing required product: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    scope_path = root / "xstar_calc_hmc_all_all_element_scope_summary.json"
    if not scope_path.is_file():
        raise SystemExit(f"missing required product: {scope_path}")
    scope = json.loads(scope_path.read_text(encoding="utf-8"))

    matrix_rows = _rows(root / "xstar_calc_hmc_all_same_call_matrix_term_parity.csv")
    detail_rows = _rows(root / "xstar_calc_hmc_all_pre_continuum_parity_details.csv")
    initial_rows = _rows(root / "xstar_calc_hmc_all_msolvelucy_initial_population_parity.csv")
    final_rows = _rows(root / "xstar_calc_hmc_all_msolvelucy_final_population_parity.csv")
    thermal_rows = _rows(root / "xstar_calc_hmc_all_xstar_thermal_family_parity.csv")
    target_rows = _rows(root / "xstar_calc_hmc_all_hydrogen_records_488_491.csv")

    type77_rows = [
        row for row in matrix_rows
        if int(row.get("element_z", 0)) in {1, 2}
        and int(row.get("data_type", 0)) == 77
    ]
    type77_bad = [row for row in type77_rows if not _bool(row.get("within_tolerance"))]
    type77_ready = bool(type77_rows) and not type77_bad

    h_type77 = [row for row in type77_rows if int(row.get("element_z", 0)) == 1]
    he_type77 = [row for row in type77_rows if int(row.get("element_z", 0)) == 2]

    initial_counts = {
        z: sum(int(row.get("element_z", 0)) == z for row in initial_rows)
        for z in (1, 2, 8)
    }
    initial_ready = initial_counts == {1: 33, 2: 78, 8: 607}
    initial_ready = initial_ready and all(_bool(row.get("within_tolerance")) for row in initial_rows)

    active_rows = [row for row in final_rows if _bool(row.get("active_population"))]
    solver_ready = bool(active_rows) and all(
        _bool(row.get("final_population_within_tolerance"))
        and _bool(row.get("outer_start_population_within_tolerance"))
        for row in active_rows
    )
    thermal_ready = bool(thermal_rows) and all(_bool(row.get("within_tolerance")) for row in thermal_rows)
    blockers = [
        row for row in detail_rows
        if _bool(row.get("milestone_blocking")) and not _bool(row.get("within_tolerance"))
    ]

    target_by_record = {int(row.get("record", 0)): row for row in target_rows}
    type62_ready = set(target_by_record) == {488, 489, 490, 491}
    type62_ready = type62_ready and all(
        row.get("status") == "evaluated" and int(row.get("n_matrix_terms", 0)) == 4
        for row in target_by_record.values()
    )

    gate_ready = summary.get("all_element_pre_continuum_acceptance_ready") is True
    oxygen_regression_ready = scope.get("oxygen_call73_regression_ready") is True
    ready = bool(
        type77_ready and type62_ready and initial_ready and solver_ready
        and thermal_ready and not blockers and gate_ready and oxygen_regression_ready
    )

    print(f"hydrogen_type77_matrix_rows={len(h_type77)}")
    print(f"helium_type77_matrix_rows={len(he_type77)}")
    print(f"type77_rows_outside_tolerance={len(type77_bad)}")
    print(f"type77_source_gate_parity_ready={type77_ready}")
    print(f"hydrogen_type62_records_488_491_ready={type62_ready}")
    print(f"initial_population_counts={initial_counts}")
    print(f"all_718_initial_populations_ready={initial_ready}")
    print(f"all_element_active_solver_ready={solver_ready}")
    print(f"all_element_thermal_ready={thermal_ready}")
    print(f"milestone_blocking_rows={len(blockers)}")
    print(f"oxygen_call73_regression_ready={oxygen_regression_ready}")
    print(f"all_element_pre_continuum_acceptance_ready={gate_ready}")
    print(f"v0437_type77_all_element_validation_ready={ready}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
