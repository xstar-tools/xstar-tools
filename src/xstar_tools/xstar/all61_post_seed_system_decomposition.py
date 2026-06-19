"""Compare all 61 source/native H/He/Mg post-seed solve systems.

An ACCEPT result means that all 183 element systems were captured and every
remaining post-seed divergence was assigned to matrix, RHS, solve response,
active-ion reconstruction, or global commit.  It does not by itself certify
fixed-state or thermal parity.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np

RELEASE = "0.6.48.7.46.17.2"
SCHEMA = "xstar-tools-v06487466-all61-post-seed-system-decomposition-v1"
SUMMARY_NAME = "all61_post_seed_system_decomposition_summary.json"
SYSTEM_COMPARISON_NAME = "all61_post_seed_system_comparison.csv"
FIRST_DIVERGENCE_NAME = "all61_post_seed_first_divergence.csv"
ARRAY_NAMES = (
    "dense_matrix",
    "heating_matrix",
    "heating_matrix2",
    "rhs",
    "solver_input",
    "outer",
    "final",
    "ion_reconstruction",
)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def _float_exact(left: float, right: float) -> bool:
    return _bits(left) == _bits(right)


def _array_report(source_path: Path, native_path: Path, expected_count: int) -> dict[str, Any]:
    report: dict[str, Any] = {
        "source_path": str(source_path),
        "native_path": str(native_path),
        "expected_count": int(expected_count),
        "source_count": 0,
        "native_count": 0,
        "exact": False,
        "first_mismatch_index": -1,
        "mismatch_count": 0,
        "max_abs_delta": float("nan"),
    }
    if not source_path.is_file() or not native_path.is_file():
        return report
    source_bytes = source_path.read_bytes()
    native_bytes = native_path.read_bytes()
    if len(source_bytes) % 8 or len(native_bytes) % 8:
        return report
    source = np.frombuffer(source_bytes, dtype=np.float64)
    native = np.frombuffer(native_bytes, dtype=np.float64)
    report["source_count"] = int(source.size)
    report["native_count"] = int(native.size)
    if source.size != expected_count or native.size != expected_count:
        return report
    exact_mask = source.view(np.uint64) == native.view(np.uint64)
    mismatch = np.flatnonzero(~exact_mask)
    report["mismatch_count"] = int(mismatch.size)
    report["first_mismatch_index"] = int(mismatch[0]) if mismatch.size else -1
    report["exact"] = bool(mismatch.size == 0)
    if mismatch.size:
        delta = np.abs(native[mismatch] - source[mismatch])
        report["max_abs_delta"] = float(np.nanmax(delta)) if delta.size else 0.0
    else:
        report["max_abs_delta"] = 0.0
    return report


def _source_manifest(source_dir: Path) -> list[dict[str, str]]:
    return _read_csv(source_dir / "v0472_all61_solve_system_manifest.csv")


def _native_manifests(native_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    diagnostics = native_dir / "qualification_diagnostics"
    for sequence in range(1, 62):
        path = diagnostics / f"evaluation_{sequence:04d}_all_element_solve_system_manifest.csv"
        if path.is_file():
            rows.extend(_read_csv(path))
    return rows


def _native_solve_rows(native_dir: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    diagnostics = native_dir / "qualification_diagnostics"
    for sequence in range(1, 62):
        path = diagnostics / f"evaluation_{sequence:04d}_all_element_solve_rows.csv"
        if path.is_file():
            rows.extend(_read_csv(path))
    return rows


def _native_ions(native_dir: Path) -> dict[tuple[int, int, int], float]:
    values: dict[tuple[int, int, int], float] = {}
    diagnostics = native_dir / "qualification_diagnostics"
    for sequence in range(1, 62):
        path = diagnostics / f"evaluation_{sequence:04d}_ion_balance.csv"
        if not path.is_file():
            continue
        for row in _read_csv(path):
            z = int(row["element_z"])
            if z in (1, 2, 12):
                values[(sequence, z, int(row["stage"]))] = float(row["final_fraction"])
    return values


def _native_levels(native_dir: Path, program_rows: Path) -> dict[tuple[int, int], float]:
    mapping: dict[tuple[int, int], int] = {}
    for row in _read_csv(program_rows):
        global_index = int(row.get("global_level_index", "0") or 0)
        if global_index > 0:
            mapping[(int(row["element_index"]), int(row["row"]))] = global_index
    values: dict[tuple[int, int], float] = {}
    diagnostics = native_dir / "qualification_diagnostics"
    for sequence in range(1, 62):
        path = diagnostics / f"evaluation_{sequence:04d}_populations.csv"
        if not path.is_file():
            continue
        for row in _read_csv(path):
            key = (int(row["element_index"]), int(row["element_row"]))
            global_index = mapping.get(key, 0)
            if global_index > 0:
                values[(sequence, global_index)] = float(row["final_population"])
    return values


def _basis_seed_exact(
    source_rows: list[dict[str, str]], native_rows: list[dict[str, str]]
) -> tuple[bool, dict[str, int]]:
    source = {
        (int(row["sequence"]), int(row["element_z"]), int(row["compact_row"])): row
        for row in source_rows
    }
    native = {
        (int(row["evaluation_ordinal"]), int(row["element_z"]), int(row["compact_row"])): row
        for row in native_rows
    }
    counters = Counter()
    all_exact = len(source) == len(native) and set(source) == set(native)

    def canonical_superlevels(rows: dict[tuple[int, int, int], dict[str, str]]) -> dict[tuple[int, int, int], int]:
        result: dict[tuple[int, int, int], int] = {}
        grouped: dict[tuple[int, int], list[tuple[tuple[int, int, int], dict[str, str]]]] = {}
        for key, row in rows.items():
            grouped.setdefault((key[0], key[1]), []).append((key, row))
        for items in grouped.values():
            mapping: dict[int, int] = {}
            for key, row in sorted(items, key=lambda item: item[0][2]):
                raw = int(row["superlevel"])
                if raw not in mapping:
                    mapping[raw] = len(mapping) + 1
                result[key] = mapping[raw]
        return result

    source_superlevels = canonical_superlevels(source)
    native_superlevels = canonical_superlevels(native)
    for key in sorted(set(source) | set(native)):
        left = source.get(key)
        right = native.get(key)
        counters["rows_total"] += 1
        if left is None or right is None:
            counters["missing_rows"] += 1
            all_exact = False
            continue
        basis_exact = (
            int(left["active_min_stage"]) == int(right["active_min_stage"])
            and int(left["active_max_stage"]) == int(right["active_max_stage"])
            and int(left["compact_row"]) == int(right["compact_row"])
            and int(left["ion"]) == int(right["ion"])
            and int(left["ion_charge"]) == int(right["ion_charge"])
            and source_superlevels[key] == native_superlevels[key]
            and int(left["is_normalization_row"]) == int(right["is_normalization_row"])
        )
        seed_exact = _float_exact(
            float(left["transformed_initial_population"]),
            float(right["initial_population"]),
        )
        counters["basis_exact"] += int(basis_exact)
        counters["seed_exact"] += int(seed_exact)
        if not basis_exact or not seed_exact:
            all_exact = False
    return all_exact, dict(counters)


def _global_commit_exactness(
    source_dir: Path,
    native_dir: Path,
    program_rows: Path,
) -> tuple[dict[tuple[int, int], bool], dict[tuple[int, int], bool]]:
    source_ions = {
        (int(row["sequence"]), int(row["element_z"]), int(row["stage"])): float(row["population"])
        for row in _read_csv(source_dir / "v0472_all61_ion_populations.csv")
    }
    native_ions = _native_ions(native_dir)
    ion_exact: dict[tuple[int, int], bool] = {}
    for sequence in range(1, 62):
        for z in (1, 2, 12):
            ion_exact[(sequence, z)] = all(
                key in native_ions and _float_exact(source_ions[key], native_ions[key])
                for key in ((sequence, z, stage) for stage in range(1, z + 2))
            )

    source_levels = {
        (int(row["sequence"]), int(row["global_level_index"])): (
            int(row["element_z"]), float(row["population"])
        )
        for row in _read_csv(source_dir / "v0472_all61_level_populations.csv")
    }
    native_levels = _native_levels(native_dir, program_rows)
    level_exact: dict[tuple[int, int], bool] = {}
    for sequence in range(1, 62):
        for z in (1, 2, 12):
            keys = [key for key, value in source_levels.items() if key[0] == sequence and value[0] == z]
            level_exact[(sequence, z)] = bool(keys) and all(
                key in native_levels and _float_exact(source_levels[key][1], native_levels[key])
                for key in keys
            )
    return ion_exact, level_exact


def decompose(
    source_dir: Path,
    native_dir: Path,
    output_dir: Path,
    program_rows: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    required = (
        source_dir / "v0472_all61_solve_system_manifest.csv",
        source_dir / "v0472_all61_element_solve_rows.csv",
        source_dir / "v0472_all61_ion_populations.csv",
        source_dir / "v0472_all61_level_populations.csv",
        native_dir / "native_dsec_summary.json",
        program_rows,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [f"missing:{path}" for path in missing],
            "gates": {
                "ALL_61_SOURCE_SOLVE_SYSTEMS_CAPTURED": "REJECT_MISSING_INPUT",
                "ALL_61_NATIVE_SOLVE_SYSTEMS_CAPTURED": "NOT_RUN_MISSING_INPUT",
                "ALL_61_BASIS_AND_SEED_HELD_EXACT": "NOT_RUN_MISSING_INPUT",
                "ALL_61_POST_SEED_DIVERGENCES_CLASSIFIED": "NOT_RUN_MISSING_INPUT",
                "V06487_POST_SEED_SYSTEM_DECOMPOSITION": "REJECT",
                "V06487_FIXED_STATE_PARITY": "REJECT",
                "V06488_THERMAL_PARITY_READY": "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
                "THERMAL_PARITY": "BLOCKED",
                "PRODUCTION_PROMOTION": "BLOCKED",
            },
            "qualification_only": True,
            "production_promotion_ready": False,
            "thermal_parity_started": False,
        }
        _write_json(output_dir / SUMMARY_NAME, result)
        return result

    source_rows = _source_manifest(source_dir)
    native_rows = _native_manifests(native_dir)
    source_map = {(int(row["sequence"]), int(row["element_z"])): row for row in source_rows}
    native_map = {(int(row["evaluation_ordinal"]), int(row["element_z"])): row for row in native_rows}
    expected_keys = {(sequence, z) for sequence in range(1, 62) for z in (1, 2, 12)}
    source_complete = len(source_rows) == 183 and set(source_map) == expected_keys
    native_complete = len(native_rows) == 183 and set(native_map) == expected_keys

    source_solve_rows = _read_csv(source_dir / "v0472_all61_element_solve_rows.csv")
    native_solve_rows = _native_solve_rows(native_dir)
    basis_seed_exact, basis_seed_counts = _basis_seed_exact(source_solve_rows, native_solve_rows)
    ion_commit, level_commit = _global_commit_exactness(source_dir, native_dir, program_rows)

    comparison_rows: list[dict[str, Any]] = []
    first_rows: list[dict[str, Any]] = []
    classifications = Counter()
    array_exact_systems = Counter()
    metadata_exact_systems = Counter()
    for sequence, z in sorted(expected_keys):
        source = source_map.get((sequence, z))
        native = native_map.get((sequence, z))
        row: dict[str, Any] = {"sequence": sequence, "element_z": z}
        if source is None or native is None:
            classification = "SOURCE_SYSTEM_MISSING" if source is None else "NATIVE_SYSTEM_MISSING"
            row["classification"] = classification
            comparison_rows.append(row)
            first_rows.append({"sequence": sequence, "element_z": z, "first_divergence": classification})
            classifications[classification] += 1
            continue
        n = int(source["n_rows"])
        n_ions = int(source["n_ions"])
        dimensions_exact = (
            n == int(native["n_rows"])
            and n_ions == int(native["n_ions"])
            and int(source["active_min_stage"]) == int(native["active_min_stage"])
            and int(source["active_max_stage"]) == int(native["active_max_stage"])
            and int(source["normalization_row"]) == int(native["normalization_row"])
        )
        row["dimensions_exact"] = int(dimensions_exact)
        reports: dict[str, dict[str, Any]] = {}
        for name in ARRAY_NAMES:
            expected_count = n * n if name in {"dense_matrix", "heating_matrix", "heating_matrix2"} else (
                n_ions if name == "ion_reconstruction" else n
            )
            source_path = source_dir / source[f"{name}_path"]
            native_path = native_dir / "qualification_diagnostics" / native[f"{name}_path"]
            reports[name] = _array_report(source_path, native_path, expected_count)
            row[f"{name}_exact"] = int(reports[name]["exact"])
            row[f"{name}_mismatch_count"] = reports[name]["mismatch_count"]
            row[f"{name}_first_mismatch_index"] = reports[name]["first_mismatch_index"]
            row[f"{name}_max_abs_delta"] = reports[name]["max_abs_delta"]
            array_exact_systems[name] += int(reports[name]["exact"])

        method_exact = source["solver_method"] == native["solver_method"]
        iterations_exact = (
            int(source["outer_iterations"]) == int(native["outer_iterations"])
            and int(source["fixed_point_iterations"]) == int(native["fixed_point_iterations"])
        )
        normalization_exact = (
            _float_exact(float(source["normalization"]), float(native["normalization"]))
            and _float_exact(float(source["normalization_error"]), float(native["normalization_error"]))
        )
        row["solver_method_exact"] = int(method_exact)
        row["solver_iterations_exact"] = int(iterations_exact)
        row["solver_normalization_exact"] = int(normalization_exact)
        metadata_exact_systems["method"] += int(method_exact)
        metadata_exact_systems["iterations"] += int(iterations_exact)
        metadata_exact_systems["normalization"] += int(normalization_exact)
        row["global_ion_commit_exact"] = int(ion_commit.get((sequence, z), False))
        row["global_level_commit_exact"] = int(level_commit.get((sequence, z), False))

        if not dimensions_exact:
            classification = "COMPACT_BASIS_DIMENSION_DIVERGENCE"
        elif not reports["dense_matrix"]["exact"]:
            classification = "DENSE_MATRIX_DIVERGENCE"
        elif not reports["heating_matrix"]["exact"]:
            classification = "HEATING_MATRIX_DIVERGENCE"
        elif not reports["heating_matrix2"]["exact"]:
            classification = "HEATING2_MATRIX_DIVERGENCE"
        elif not reports["rhs"]["exact"]:
            classification = "RHS_DIVERGENCE"
        elif not reports["solver_input"]["exact"]:
            classification = "SOLVER_INPUT_DIVERGENCE"
        elif not (
            method_exact
            and iterations_exact
            and normalization_exact
            and reports["outer"]["exact"]
            and reports["final"]["exact"]
        ):
            classification = "SOLVE_RESPONSE_DIVERGENCE"
        elif not reports["ion_reconstruction"]["exact"]:
            classification = "ACTIVE_ION_RECONSTRUCTION_DIVERGENCE"
        elif not ion_commit.get((sequence, z), False):
            classification = "GLOBAL_ION_COMMIT_DIVERGENCE"
        elif not level_commit.get((sequence, z), False):
            classification = "GLOBAL_LEVEL_COMMIT_DIVERGENCE"
        else:
            classification = "POST_SEED_ELEMENT_BOUNDARY_EXACT"
        row["classification"] = classification
        comparison_rows.append(row)
        first_rows.append(
            {
                "sequence": sequence,
                "element_z": z,
                "first_divergence": classification,
                "first_matrix_index": reports["dense_matrix"]["first_mismatch_index"],
                "first_rhs_index": reports["rhs"]["first_mismatch_index"],
                "first_outer_index": reports["outer"]["first_mismatch_index"],
                "first_final_index": reports["final"]["first_mismatch_index"],
                "first_ion_index": reports["ion_reconstruction"]["first_mismatch_index"],
            }
        )
        classifications[classification] += 1

    comparison_fields = [
        "sequence", "element_z", "classification", "dimensions_exact",
        *[field for name in ARRAY_NAMES for field in (
            f"{name}_exact", f"{name}_mismatch_count", f"{name}_first_mismatch_index", f"{name}_max_abs_delta"
        )],
        "solver_method_exact", "solver_iterations_exact", "solver_normalization_exact",
        "global_ion_commit_exact", "global_level_commit_exact",
    ]
    _write_csv(output_dir / SYSTEM_COMPARISON_NAME, comparison_fields, comparison_rows)
    _write_csv(
        output_dir / FIRST_DIVERGENCE_NAME,
        [
            "sequence", "element_z", "first_divergence", "first_matrix_index",
            "first_rhs_index", "first_outer_index", "first_final_index", "first_ion_index",
        ],
        first_rows,
    )

    native_summary = json.loads((native_dir / "native_dsec_summary.json").read_text())
    all61_native = int(native_summary.get("total_evaluations", 0)) == 61
    callbacks_zero = int(native_summary.get("python_callbacks", -1)) == 0
    classified = len(first_rows) == 183 and all(
        row.get("first_divergence") not in {"SOURCE_SYSTEM_MISSING", "NATIVE_SYSTEM_MISSING"}
        for row in first_rows
    )
    dense_exact = array_exact_systems["dense_matrix"] == 183
    heating_exact = array_exact_systems["heating_matrix"] == 183
    heating2_exact = array_exact_systems["heating_matrix2"] == 183
    rhs_exact = array_exact_systems["rhs"] == 183
    solver_input_exact = array_exact_systems["solver_input"] == 183
    matrix_system_exact = dense_exact and heating_exact and heating2_exact and rhs_exact and solver_input_exact
    method_exact = metadata_exact_systems["method"] == 183
    iteration_exact = metadata_exact_systems["iterations"] == 183
    normalization_exact = metadata_exact_systems["normalization"] == 183
    solve_response_exact = (
        method_exact
        and iteration_exact
        and normalization_exact
        and array_exact_systems["outer"] == 183
        and array_exact_systems["final"] == 183
    )
    ion_reconstruction_exact = array_exact_systems["ion_reconstruction"] == 183
    global_ion_exact = sum(ion_commit.values()) == 183
    global_level_exact = sum(level_commit.values()) == 183
    global_element_exact = global_ion_exact and global_level_exact
    decomposition_complete = (
        source_complete
        and native_complete
        and basis_seed_exact
        and all61_native
        and callbacks_zero
        and classified
    )
    fixed_state_exact = matrix_system_exact and solve_response_exact and ion_reconstruction_exact and global_element_exact

    gates = {
        "ALL_61_NATIVE_EVALUATIONS": "ACCEPT" if all61_native else "REJECT",
        "PYTHON_CALLBACKS_ZERO": "ACCEPT" if callbacks_zero else "REJECT",
        "ALL_61_SOURCE_SOLVE_SYSTEMS_CAPTURED": "ACCEPT" if source_complete else "REJECT",
        "ALL_61_NATIVE_SOLVE_SYSTEMS_CAPTURED": "ACCEPT" if native_complete else "REJECT",
        "ALL_61_BASIS_AND_SEED_HELD_EXACT": "ACCEPT" if basis_seed_exact else "REJECT",
        "ALL_61_DENSE_MATRIX_EXACT": "ACCEPT" if dense_exact else "REJECT",
        "ALL_61_HEATING_MATRIX_EXACT": "ACCEPT" if heating_exact else "REJECT",
        "ALL_61_HEATING2_MATRIX_EXACT": "ACCEPT" if heating2_exact else "REJECT",
        "ALL_61_RHS_EXACT": "ACCEPT" if rhs_exact else "REJECT",
        "ALL_61_SOLVER_INPUT_EXACT": "ACCEPT" if solver_input_exact else "REJECT",
        "ALL_61_MATRIX_SYSTEM_EXACT": "ACCEPT" if matrix_system_exact else "REJECT",
        "ALL_61_SOLVER_METHOD_EXACT": "ACCEPT" if method_exact else "REJECT",
        "ALL_61_SOLVER_ITERATION_COUNTS_EXACT": "ACCEPT" if iteration_exact else "REJECT",
        "ALL_61_SOLVER_NORMALIZATION_EXACT": "ACCEPT" if normalization_exact else "REJECT",
        "ALL_61_SOLVE_RESPONSE_EXACT": "ACCEPT" if solve_response_exact else "REJECT",
        "ALL_61_ION_RECONSTRUCTION_EXACT": "ACCEPT" if ion_reconstruction_exact else "REJECT",
        "ALL_61_GLOBAL_ION_COMMIT_EXACT": "ACCEPT" if global_ion_exact else "REJECT",
        "ALL_61_GLOBAL_LEVEL_COMMIT_EXACT": "ACCEPT" if global_level_exact else "REJECT",
        "ALL_61_GLOBAL_ELEMENT_COMMIT_EXACT": "ACCEPT" if global_element_exact else "REJECT",
        "ALL_61_POST_SEED_DIVERGENCES_CLASSIFIED": "ACCEPT" if classified else "REJECT",
        "V06487_POST_SEED_SYSTEM_DECOMPOSITION": "ACCEPT" if decomposition_complete else "REJECT",
        "V06487_FIXED_STATE_PARITY": "ACCEPT" if fixed_state_exact else "REJECT",
        "V06488_THERMAL_PARITY_READY": "ACCEPT" if fixed_state_exact else "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
        "THERMAL_PARITY": "NOT_RUN_V06488" if fixed_state_exact else "BLOCKED",
        "CONTROLLER_PARITY": "NOT_RUN_V06489",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    }
    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if decomposition_complete else "REJECT",
        "gates": gates,
        "source_systems": len(source_rows),
        "native_systems": len(native_rows),
        "basis_seed_counts": basis_seed_counts,
        "array_exact_systems": dict(array_exact_systems),
        "metadata_exact_systems": dict(metadata_exact_systems),
        "global_ion_commit_exact_systems": sum(ion_commit.values()),
        "global_level_commit_exact_systems": sum(level_commit.values()),
        "classification_counts": dict(sorted(classifications.items())),
        "qualification_only": True,
        "production_promotion_ready": False,
        "thermal_parity_started": False,
    }
    _write_json(output_dir / SUMMARY_NAME, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--program-rows", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = decompose(
            args.source_capture,
            args.native_run,
            args.output,
            args.program_rows,
        )
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "gates": {
                "V06487_POST_SEED_SYSTEM_DECOMPOSITION": "REJECT",
                "V06487_FIXED_STATE_PARITY": "REJECT",
                "V06488_THERMAL_PARITY_READY": "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
                "THERMAL_PARITY": "BLOCKED",
                "PRODUCTION_PROMOTION": "BLOCKED",
            },
            "qualification_only": True,
            "production_promotion_ready": False,
            "thermal_parity_started": False,
        }
        _write_json(args.output / SUMMARY_NAME, result)
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
