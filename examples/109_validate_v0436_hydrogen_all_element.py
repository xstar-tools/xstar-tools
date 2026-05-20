#!/usr/bin/env python3
"""Validate the bounded v0.4.36 H/He/O production rerun products."""
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
        description="Validate v0.4.36 hydrogen and all-element pre-continuum gates."
    )
    parser.add_argument("output_dir", help="Completed example-108 v0.4.36 output directory")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.output_dir)
    summary_path = root / "xstar_calc_hmc_all_pre_continuum_parity_summary.json"
    if not summary_path.is_file():
        raise SystemExit(f"missing required product: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    target_rows = _rows(root / "xstar_calc_hmc_all_hydrogen_records_488_491.csv")
    matrix_rows = _rows(root / "xstar_calc_hmc_all_same_call_matrix_term_parity.csv")
    initial_rows = _rows(root / "xstar_calc_hmc_all_msolvelucy_initial_population_parity.csv")
    final_rows = _rows(root / "xstar_calc_hmc_all_msolvelucy_final_population_parity.csv")
    thermal_rows = _rows(root / "xstar_calc_hmc_all_xstar_thermal_family_parity.csv")
    detail_rows = _rows(root / "xstar_calc_hmc_all_pre_continuum_parity_details.csv")

    by_record = {int(row["record"]): row for row in target_rows}
    target_ready = set(by_record) == {488, 489, 490, 491}
    target_ready = target_ready and all(
        int(row.get("data_type", 0)) == 62
        and int(row.get("rate_type", 0)) == 3
        and row.get("status") == "evaluated"
        and int(row.get("n_matrix_terms", 0)) == 4
        for row in by_record.values()
    )
    endpoint_pairs = {
        record: (int(row.get("idest1", 0)), int(row.get("idest2", 0)))
        for record, row in by_record.items()
    }
    target_ready = target_ready and endpoint_pairs == {
        488: (1, 4), 489: (1, 7), 490: (1, 8), 491: (1, 9)
    }

    h_matrix = [row for row in matrix_rows if int(row.get("element_z", 0)) == 1]
    matrix_ready = bool(h_matrix) and all(_bool(row.get("topology_match")) for row in h_matrix)
    target_matrix_rows = [row for row in h_matrix if int(row.get("record", 0)) in by_record]
    matrix_ready = matrix_ready and len(target_matrix_rows) == 16

    initial_counts = {
        z: sum(int(row.get("element_z", 0)) == z for row in initial_rows)
        for z in (1, 2, 8)
    }
    initial_ready = initial_counts == {1: 33, 2: 78, 8: 607}
    initial_ready = initial_ready and all(_bool(row.get("within_tolerance")) for row in initial_rows)

    h_active = [
        row for row in final_rows
        if int(row.get("element_z", 0)) == 1 and _bool(row.get("active_population"))
    ]
    hydrogen_solver_ready = bool(h_active) and all(
        _bool(row.get("final_population_within_tolerance"))
        and _bool(row.get("outer_start_population_within_tolerance"))
        for row in h_active
    )
    h_level4 = [row for row in h_active if int(row.get("representative_local_level", 0)) == 4]
    hydrogen_solver_ready = hydrogen_solver_ready and len(h_level4) == 1

    h_thermal = [row for row in thermal_rows if int(row.get("element_z", 0)) == 1]
    hydrogen_thermal_ready = bool(h_thermal) and all(
        _bool(row.get("within_tolerance")) for row in h_thermal
    )
    blockers = [
        row for row in detail_rows
        if _bool(row.get("milestone_blocking")) and not _bool(row.get("within_tolerance"))
    ]

    gate_ready = summary.get("all_element_pre_continuum_acceptance_ready") is True
    ready = bool(
        target_ready and matrix_ready and initial_ready and hydrogen_solver_ready
        and hydrogen_thermal_ready and not blockers and gate_ready
    )

    print(f"hydrogen_records_488_491_ready={target_ready}")
    print(f"hydrogen_target_matrix_terms={len(target_matrix_rows)}")
    print(f"record_keyed_hydrogen_matrix_ready={matrix_ready}")
    print(f"initial_population_counts={initial_counts}")
    print(f"all_718_initial_populations_ready={initial_ready}")
    print(f"hydrogen_active_population_rows={len(h_active)}")
    print(f"hydrogen_solver_ready={hydrogen_solver_ready}")
    print(f"hydrogen_thermal_ready={hydrogen_thermal_ready}")
    print(f"milestone_blocking_rows={len(blockers)}")
    print(f"all_element_pre_continuum_acceptance_ready={gate_ready}")
    print(f"v0436_hydrogen_all_element_validation_ready={ready}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
