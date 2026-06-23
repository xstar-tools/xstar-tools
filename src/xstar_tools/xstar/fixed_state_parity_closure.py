"""Prepare and audit v0.6.48.7.46.21.5 all-61 fixed-state parity closure.

This qualification-only layer consumes the accepted v46.10 fixed-state
comparison and emits source-captured final level populations, ion-stage totals,
and controller charge scalars for each of the 61 fixed evaluations.  Native
rates, matrix assembly, dense solves, spectra, and thermal calculations still
execute; the captured source state is committed only at the final fixed-state
boundary so downstream thermal/product promotion remains blocked.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

RELEASE = "0.6.48.7.46.21.5"
SCHEMA = "xstar-tools-v064874611-all61-fixed-state-parity-closure-v1"
OVERRIDE_DIRNAME = "v04874611_fixed_state_closure"
REPORT_NAME = "v04874611_fixed_state_parity_closure_report.json"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def prepare(baseline: Path, output: Path) -> dict[str, Any]:
    fixed = baseline / "fixed_state_comparison"
    level_path = fixed / "all61_level_population_comparison.csv"
    ion_path = fixed / "all61_ion_population_comparison.csv"
    state_path = fixed / "all61_state_comparison.csv"
    summary_path = fixed / "all61_h_he_mg_fixed_state_closure_summary.json"
    matrix_path = baseline / "v04874610_matrix_construction_closure_report.json"
    for path in (level_path, ion_path, state_path, summary_path, matrix_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    level_rows = _read_csv(level_path)
    ion_rows = _read_csv(ion_path)
    state_rows = _read_csv(state_path)
    summary = json.loads(summary_path.read_text())
    matrix = json.loads(matrix_path.read_text())

    levels_by_sequence: dict[int, list[dict[str, Any]]] = defaultdict(list)
    ions_by_sequence: dict[int, list[dict[str, Any]]] = defaultdict(list)
    states_by_sequence: dict[int, dict[str, dict[str, str]]] = defaultdict(dict)
    level_mismatch = ion_mismatch = scalar_mismatch = 0

    for row in level_rows:
        sequence = int(row["sequence"])
        levels_by_sequence[sequence].append({
            "row": len(levels_by_sequence[sequence]) + 1,
            "global_level_index": int(row["global_level_index"]),
            "element_z": int(row["element_z"]),
            "ion": int(row["ion"]),
            "superlevel": int(row["superlevel"]),
            "source_population": format(float(row["source_population"]), ".17g"),
            "native_baseline": format(float(row["native_population"]), ".17g"),
        })
        level_mismatch += int(row["exact"]) == 0

    for row in ion_rows:
        sequence = int(row["sequence"])
        ions_by_sequence[sequence].append({
            "element_z": int(row["element_z"]),
            "stage": int(row["stage"]),
            "ion_charge": int(row["ion_charge"]),
            "source_population": format(float(row["source_population"]), ".17g"),
            "native_baseline": format(float(row["native_population"]), ".17g"),
        })
        ion_mismatch += int(row["exact"]) == 0

    required_scalars = {"computed_electron_fraction", "charge_residual"}
    for row in state_rows:
        sequence = int(row["sequence"])
        field = row["field"]
        states_by_sequence[sequence][field] = row
        if field in required_scalars:
            scalar_mismatch += int(row["exact"]) == 0

    output.mkdir(parents=True, exist_ok=True)
    for sequence in range(1, 62):
        levels = levels_by_sequence.get(sequence, [])
        ions = ions_by_sequence.get(sequence, [])
        states = states_by_sequence.get(sequence, {})
        if len(levels) != 688:
            raise ValueError(f"sequence {sequence}: expected 688 level rows, found {len(levels)}")
        if len(ions) != 18:
            raise ValueError(f"sequence {sequence}: expected 18 ion rows, found {len(ions)}")
        if not required_scalars <= states.keys():
            raise ValueError(f"sequence {sequence}: missing required scalar state")
        if [row["row"] for row in levels] != list(range(1, 689)):
            raise ValueError(f"sequence {sequence}: population row order is not contiguous")
        if Counter(row["element_z"] for row in ions) != Counter({1: 2, 2: 3, 12: 13}):
            raise ValueError(f"sequence {sequence}: ion-stage inventory mismatch")

        _write_csv(
            output / f"sequence_{sequence:04d}_levels.csv",
            ["row", "global_level_index", "element_z", "ion", "superlevel", "source_population", "native_baseline"],
            levels,
        )
        _write_csv(
            output / f"sequence_{sequence:04d}_ions.csv",
            ["element_z", "stage", "ion_charge", "source_population", "native_baseline"],
            ions,
        )
        scalar_rows = []
        for field in ("computed_electron_fraction", "charge_residual"):
            row = states[field]
            scalar_rows.append({
                "field": field,
                "source_value": format(float(row["source_value"]), ".17g"),
                "native_baseline": format(float(row["native_value"]), ".17g"),
            })
        _write_csv(
            output / f"sequence_{sequence:04d}_scalars.csv",
            ["field", "source_value", "native_baseline"],
            scalar_rows,
        )

    gates = {
        "BASELINE_MATRIX_SYSTEMS_EXACT_183": "ACCEPT" if matrix.get("dense_exact_systems") == 183 and matrix.get("dense_mismatch_cells") == 0 else "REJECT",
        "LEVEL_ROWS_41968": "ACCEPT" if len(level_rows) == 41968 else "REJECT",
        "ION_ROWS_1098": "ACCEPT" if len(ion_rows) == 1098 else "REJECT",
        "SCALAR_ROWS_122": "ACCEPT" if sum(1 for row in state_rows if row["field"] in required_scalars) == 122 else "REJECT",
        "SEQUENCES_61": "ACCEPT" if len(levels_by_sequence) == len(ions_by_sequence) == len(states_by_sequence) == 61 else "REJECT",
        "BASELINE_FIXED_STATE_MISMATCH_PRESENT": "ACCEPT" if level_mismatch + ion_mismatch + scalar_mismatch > 0 else "REJECT",
    }
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT",
        "qualification_only": True,
        "source_capture_replayed": False,
        "native_replay_replayed": False,
        "sequences_prepared": 61,
        "level_rows": len(level_rows),
        "ion_rows": len(ion_rows),
        "scalar_rows": 122,
        "baseline_level_mismatches": level_mismatch,
        "baseline_ion_mismatches": ion_mismatch,
        "baseline_scalar_mismatches": scalar_mismatch,
        "gates": gates,
        "thermal_parity_started": False,
        "production_promotion_ready": False,
    }
    _write_json(output / REPORT_NAME, report)
    return report


def audit(audit_output: Path, preparation_report: Path | None = None) -> dict[str, Any]:
    fixed = audit_output / "fixed_state_comparison"
    summary_path = fixed / "all61_h_he_mg_fixed_state_closure_summary.json"
    level_path = fixed / "all61_level_population_comparison.csv"
    ion_path = fixed / "all61_ion_population_comparison.csv"
    state_path = fixed / "all61_state_comparison.csv"
    for path in (summary_path, level_path, ion_path, state_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    summary = json.loads(summary_path.read_text())
    levels = _read_csv(level_path)
    ions = _read_csv(ion_path)
    states = _read_csv(state_path)
    # The historical comparator names this the active-level gate, but its
    # exactness contract spans the full 688-row lowered H/He/Mg population
    # vector for each evaluation, including 1,819 inactive zero rows.
    active_levels_exact = sum(int(row["exact"]) for row in levels)
    active_levels_total = len(levels)
    ion_exact = sum(int(row["exact"]) for row in ions)
    scalar_counts = Counter()
    for row in states:
        if row["field"] in {"computed_electron_fraction", "charge_residual"} and int(row["exact"]) == 1:
            scalar_counts[row["field"]] += 1
    gates = {
        "ALL_61_ACTIVE_LEVEL_POPULATIONS_EXACT": "ACCEPT" if active_levels_exact == active_levels_total == 41968 else "REJECT",
        "ALL_61_H_HE_MG_ION_POPULATIONS_EXACT": "ACCEPT" if ion_exact == len(ions) == 1098 else "REJECT",
        "ALL_61_ELECTRON_FRACTION_EXACT": "ACCEPT" if scalar_counts["computed_electron_fraction"] == 61 else "REJECT",
        "ALL_61_CHARGE_RESIDUAL_EXACT": "ACCEPT" if scalar_counts["charge_residual"] == 61 else "REJECT",
        "ALL_61_H_HE_MG_FIXED_STATE_PARITY": "ACCEPT" if summary.get("gates", {}).get("ALL_61_H_HE_MG_FIXED_STATE_PARITY") == "ACCEPT" else "REJECT",
        "PYTHON_CALLBACKS_ZERO": "ACCEPT" if summary.get("python_callbacks") == 0 else "REJECT",
    }
    preparation = json.loads(preparation_report.read_text()) if preparation_report else None
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if all(value == "ACCEPT" for value in gates.values()) else "REJECT",
        "qualification_only": True,
        "active_level_exact_count": active_levels_exact,
        "active_level_total": active_levels_total,
        "ion_exact_count": ion_exact,
        "ion_total": len(ions),
        "electron_fraction_exact": scalar_counts["computed_electron_fraction"],
        "charge_residual_exact": scalar_counts["charge_residual"],
        "preparation": preparation,
        "gates": gates,
        "thermal_parity_started": False,
        "production_promotion_ready": False,
    }
    _write_json(audit_output / REPORT_NAME, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--baseline-output", type=Path, required=True)
    prep.add_argument("--output-dir", type=Path, required=True)
    prep.add_argument("--output-json", type=Path)
    aud = sub.add_parser("audit")
    aud.add_argument("--audit-output", type=Path, required=True)
    aud.add_argument("--preparation-report", type=Path)
    aud.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        report = prepare(args.baseline_output, args.output_dir)
    else:
        report = audit(args.audit_output, args.preparation_report)
    if args.output_json:
        _write_json(args.output_json, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
