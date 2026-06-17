"""Decompose all-61 post-seed matrix, RHS, solve, and commit residuals.

An ACCEPT result certifies complete attribution of all 183 H/He/Mg element
systems while the source compact basis and transformed seed are held exact.
It does not certify fixed-state, thermal, controller, product, or production
parity.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

RELEASE = "0.6.48.7.46.2"
SCHEMA = "xstar-tools-v0648746-all61-post-seed-system-decomposition-v1"
SUMMARY_NAME = "all61_post_seed_system_decomposition_summary.json"
INVENTORY_NAME = "all61_post_seed_system_inventory.csv"
FIRST_NAME = "all61_first_post_seed_divergence.csv"
MATRIX_NAME = "all61_matrix_exactness_by_element.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _bits(value: float) -> bytes:
    return struct.pack(">d", float(value))


def _exact(a: float, b: float) -> bool:
    return _bits(a) == _bits(b)


def _load_array(root: Path, name: str, expected: int | None = None) -> np.ndarray:
    path = root / name
    if not path.is_file():
        raise FileNotFoundError(path)
    values = np.fromfile(path, dtype=np.float64)
    if expected is not None and values.size != expected:
        raise ValueError(f"{path}: expected {expected} doubles, got {values.size}")
    return values


def _exact_count(source: np.ndarray, native: np.ndarray) -> tuple[int, int, int, float, int]:
    total = max(source.size, native.size)
    if source.size != native.size:
        return 0, total, 0, math.inf, -1
    exact_mask = source.view(np.uint64) == native.view(np.uint64)
    exact = int(np.count_nonzero(exact_mask))
    if exact == total:
        return exact, total, 0, 0.0, -1
    mismatch = np.flatnonzero(~exact_mask)
    first = int(mismatch[0])
    finite = np.isfinite(source) & np.isfinite(native)
    max_abs = float(np.max(np.abs(source[finite] - native[finite]))) if np.any(finite) else math.inf
    return exact, total, total - exact, max_abs, first


def _native_manifests(native_dir: Path) -> list[dict[str, str]]:
    for directory in (native_dir / "qualification_diagnostics", native_dir / "diagnostics", native_dir / "diag"):
        if not directory.is_dir():
            continue
        rows: list[dict[str, str]] = []
        for sequence in range(1, 62):
            path = directory / f"evaluation_{sequence:04d}_all_element_solve_systems.csv"
            if path.is_file():
                for row in _read_csv(path):
                    row = dict(row)
                    row["_root"] = str(directory)
                    rows.append(row)
        if rows:
            return rows
    return []


def _native_solve_rows(native_dir: Path) -> list[dict[str, str]]:
    for directory in (native_dir / "qualification_diagnostics", native_dir / "diagnostics", native_dir / "diag"):
        if not directory.is_dir():
            continue
        rows: list[dict[str, str]] = []
        for sequence in range(1, 62):
            path = directory / f"evaluation_{sequence:04d}_all_element_solve_rows.csv"
            if path.is_file():
                rows.extend(_read_csv(path))
        if rows:
            return rows
    return []


def _native_ions(native_dir: Path) -> dict[tuple[int, int, int], float]:
    result: dict[tuple[int, int, int], float] = {}
    for directory in (native_dir / "qualification_diagnostics", native_dir / "diagnostics", native_dir / "diag"):
        if not directory.is_dir():
            continue
        for sequence in range(1, 62):
            path = directory / f"evaluation_{sequence:04d}_ion_balance.csv"
            if not path.is_file():
                continue
            for row in _read_csv(path):
                z = int(row["element_z"])
                if z in (1, 2, 12):
                    result[(sequence, z, int(row["stage"]))] = float(row["final_fraction"])
        if result:
            return result
    return result


def _native_levels(native_dir: Path) -> dict[tuple[int, int, int], float]:
    result: dict[tuple[int, int, int], float] = {}
    for directory in (native_dir / "qualification_diagnostics", native_dir / "diagnostics", native_dir / "diag"):
        if not directory.is_dir():
            continue
        for sequence in range(1, 62):
            path = directory / f"evaluation_{sequence:04d}_populations.csv"
            if not path.is_file():
                continue
            for row in _read_csv(path):
                z = int(row["element_z"])
                if z in (1, 2, 12):
                    result[(sequence, z, int(row["global_population_row"]))] = float(row["final_population"])
        if result:
            return result
    return result


def _classify(item: dict[str, Any]) -> str:
    if not item["basis_exact"]:
        return "COMPACT_BASIS_DIVERGENCE"
    if not item["initial_exact"]:
        return "TRANSFORMED_SEED_DIVERGENCE"
    if not item["dense_exact"]:
        return "DENSE_MATRIX_DIVERGENCE"
    if not item["heating_exact"]:
        return "HEATING_MATRIX_DIVERGENCE"
    if not item["heating2_exact"]:
        return "HEATING2_MATRIX_DIVERGENCE"
    if not item["rhs_exact"]:
        return "RHS_DIVERGENCE"
    if not item["outer_exact"] or not item["final_exact"]:
        return "SOLVE_RESPONSE_DIVERGENCE"
    if not item["active_ion_exact"]:
        return "ACTIVE_ION_RECONSTRUCTION_DIVERGENCE"
    if not item["ion_boundary_exact"]:
        return "GLOBAL_ION_COMMIT_DIVERGENCE"
    if not item["level_boundary_exact"]:
        return "GLOBAL_LEVEL_COMMIT_DIVERGENCE"
    return "POST_SEED_ELEMENT_BOUNDARY_EXACT"


def decompose(source_dir: Path, native_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    required = {
        "source_systems": source_dir / "v0472_all61_element_solve_systems.csv",
        "source_solve_rows": source_dir / "v0472_all61_element_solve_rows.csv",
        "source_ions": source_dir / "v0472_all61_ion_populations.csv",
        "source_levels": source_dir / "v0472_all61_level_populations.csv",
        "native_summary": native_dir / "native_dsec_summary.json",
    }
    missing = [name for name, path in required.items() if not path.is_file()]
    native_systems = _native_manifests(native_dir)
    native_rows = _native_solve_rows(native_dir)
    native_ions = _native_ions(native_dir)
    native_levels = _native_levels(native_dir)
    if not native_systems:
        missing.append("native_solve_systems")
    if not native_rows:
        missing.append("native_solve_rows")
    if not native_ions:
        missing.append("native_ions")
    if not native_levels:
        missing.append("native_levels")
    if missing:
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [f"missing:{name}" for name in missing],
            "gates": {
                "ALL_61_SOURCE_SOLVE_SYSTEMS_CAPTURED": "REJECT_MISSING_INPUT",
                "ALL_61_NATIVE_SOLVE_SYSTEMS_CAPTURED": "REJECT_MISSING_INPUT",
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
        (output_dir / SUMMARY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result

    source_systems = _read_csv(required["source_systems"])
    native_summary = json.loads(required["native_summary"].read_text())
    source_map = {(int(r["sequence"]), int(r["element_z"])): r for r in source_systems}
    native_map = {(int(r["evaluation_ordinal"]), int(r["element_z"])): r for r in native_systems}
    source_solve_rows = _read_csv(required["source_solve_rows"])
    source_solve_map: dict[tuple[int, int, int], dict[str, str]] = {}
    for row in source_solve_rows:
        source_solve_map[(int(row["sequence"]), int(row["element_z"]), int(row["compact_row"]))] = row
    native_solve_map: dict[tuple[int, int, int], dict[str, str]] = {}
    for row in native_rows:
        sequence = int(row.get("evaluation_ordinal", row.get("sequence", "0")))
        native_solve_map[(sequence, int(row["element_z"]), int(row["compact_row"]))] = row
    source_ions = {(int(r["sequence"]), int(r["element_z"]), int(r["stage"])): float(r["population"]) for r in _read_csv(required["source_ions"])}
    source_levels = {(int(r["sequence"]), int(r["element_z"]), int(r["global_level_index"])): float(r["population"]) for r in _read_csv(required["source_levels"])}

    expected_keys = {(sequence, z) for sequence in range(1, 62) for z in (1, 2, 12)}
    errors: list[str] = []
    if set(source_map) != expected_keys:
        errors.append(f"source_system_inventory={len(source_map)}")
    if set(native_map) != expected_keys:
        errors.append(f"native_system_inventory={len(native_map)}")

    inventory: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []
    first_rows: list[dict[str, Any]] = []
    classifications: Counter[str] = Counter()
    totals = Counter()
    exacts = Counter()

    source_root = source_dir
    for key in sorted(expected_keys):
        sequence, z = key
        src = source_map.get(key)
        nat = native_map.get(key)
        if src is None or nat is None:
            classifications["MISSING_SOLVE_SYSTEM"] += 1
            first_rows.append({"sequence": sequence, "element_z": z, "classification": "MISSING_SOLVE_SYSTEM"})
            continue
        n_src = int(src["n_rows"])
        n_nat = int(nat["n_rows"])
        basis_exact = (
            n_src == n_nat
            and int(src["active_min_stage"]) == int(nat["active_min_stage"])
            and int(src["active_max_stage"]) == int(nat["active_max_stage"])
            and int(src["normalization_row"]) == int(nat["normalization_row"])
        )
        src_root = source_root
        nat_root = Path(nat["_root"])
        arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        specs = {
            "dense": ("dense_file", n_src * n_src, n_nat * n_nat),
            "heating": ("heating_file", n_src * n_src, n_nat * n_nat),
            "heating2": ("heating2_file", n_src * n_src, n_nat * n_nat),
            "rhs": ("rhs_file", n_src, n_nat),
            "initial": ("initial_file", n_src, n_nat),
            "outer": ("outer_file", n_src, n_nat),
            "final": ("final_file", n_src, n_nat),
            "active_ion": ("ion_final_file", None, None),
        }
        item: dict[str, Any] = {
            "sequence": sequence,
            "element_z": z,
            "basis_exact": basis_exact,
            "source_n_rows": n_src,
            "native_n_rows": n_nat,
            "source_active_min_stage": int(src["active_min_stage"]),
            "native_active_min_stage": int(nat["active_min_stage"]),
            "source_active_max_stage": int(src["active_max_stage"]),
            "native_active_max_stage": int(nat["active_max_stage"]),
        }
        for label, (field, src_expected, nat_expected) in specs.items():
            source_values = _load_array(src_root, src[field], src_expected)
            native_values = _load_array(nat_root, nat[field], nat_expected)
            arrays[label] = (source_values, native_values)
            exact, total, mismatches, max_abs, first = _exact_count(source_values, native_values)
            item[f"{label}_exact"] = exact == total and source_values.size == native_values.size
            item[f"{label}_exact_count"] = exact
            item[f"{label}_total"] = total
            item[f"{label}_mismatches"] = mismatches
            item[f"{label}_max_abs_delta"] = max_abs
            item[f"{label}_first_mismatch_index"] = first
            totals[label] += total
            exacts[label] += exact

        item["solver_method_exact"] = src.get("solver_method", "") == nat.get("solver_method", "")
        item["outer_iterations_exact"] = int(src.get("outer_iterations", 0)) == int(nat.get("outer_iterations", 0))
        item["fixed_point_iterations_exact"] = int(src.get("fixed_point_iterations", 0)) == int(nat.get("fixed_point_iterations", 0))
        item["normalization_exact"] = _exact(float(src.get("normalization", "nan")), float(nat.get("normalization", "nan")))
        item["normalization_error_exact"] = _exact(float(src.get("normalization_error", "nan")), float(nat.get("normalization_error", "nan")))
        item["max_relative_row_residual_exact"] = _exact(
            float(src.get("max_relative_row_residual", "nan")),
            float(nat.get("max_relative_row_residual", "nan")),
        )

        stages = range(1, z + 2)
        ion_boundary_exact = all(
            key2 in native_ions and _exact(source_ions.get(key2, float("nan")), native_ions[key2])
            for key2 in ((sequence, z, stage) for stage in stages)
        )
        source_level_keys = {k for k in source_levels if k[0] == sequence and k[1] == z}
        native_level_keys = {k for k in native_levels if k[0] == sequence and k[1] == z}
        common_levels = source_level_keys & native_level_keys
        level_exact_count = sum(_exact(source_levels[k], native_levels[k]) for k in common_levels)
        level_boundary_exact = source_level_keys == native_level_keys and level_exact_count == len(source_level_keys)
        item["ion_boundary_exact"] = ion_boundary_exact
        item["level_boundary_exact"] = level_boundary_exact
        item["level_exact_count"] = level_exact_count
        item["level_source_count"] = len(source_level_keys)
        item["level_native_count"] = len(native_level_keys)
        classification = _classify(item)
        item["classification"] = classification
        classifications[classification] += 1
        inventory.append(item)
        first_rows.append({
            "sequence": sequence,
            "element_z": z,
            "classification": classification,
            "first_dense_mismatch_index": item["dense_first_mismatch_index"],
            "first_rhs_mismatch_index": item["rhs_first_mismatch_index"],
            "first_outer_mismatch_index": item["outer_first_mismatch_index"],
            "first_final_mismatch_index": item["final_first_mismatch_index"],
            "first_active_ion_mismatch_index": item["active_ion_first_mismatch_index"],
            "source_solver_method": src.get("solver_method", ""),
            "native_solver_method": nat.get("solver_method", ""),
            "source_outer_iterations": src.get("outer_iterations", ""),
            "native_outer_iterations": nat.get("outer_iterations", ""),
            "source_fixed_point_iterations": src.get("fixed_point_iterations", ""),
            "native_fixed_point_iterations": nat.get("fixed_point_iterations", ""),
        })
        matrix_rows.append({
            "sequence": sequence,
            "element_z": z,
            "n_rows": n_src,
            "dense_exact": int(item["dense_exact"]),
            "dense_exact_count": item["dense_exact_count"],
            "dense_total": item["dense_total"],
            "heating_exact": int(item["heating_exact"]),
            "heating_exact_count": item["heating_exact_count"],
            "heating_total": item["heating_total"],
            "heating2_exact": int(item["heating2_exact"]),
            "heating2_exact_count": item["heating2_exact_count"],
            "heating2_total": item["heating2_total"],
            "rhs_exact": int(item["rhs_exact"]),
            "rhs_exact_count": item["rhs_exact_count"],
            "rhs_total": item["rhs_total"],
        })

    inventory_fields = [
        "sequence", "element_z", "classification", "basis_exact", "source_n_rows", "native_n_rows",
        "source_active_min_stage", "native_active_min_stage", "source_active_max_stage", "native_active_max_stage",
        "dense_exact", "dense_exact_count", "dense_total", "dense_mismatches", "dense_max_abs_delta", "dense_first_mismatch_index",
        "heating_exact", "heating_exact_count", "heating_total", "heating_mismatches", "heating_max_abs_delta", "heating_first_mismatch_index",
        "heating2_exact", "heating2_exact_count", "heating2_total", "heating2_mismatches", "heating2_max_abs_delta", "heating2_first_mismatch_index",
        "rhs_exact", "rhs_exact_count", "rhs_total", "rhs_mismatches", "rhs_max_abs_delta", "rhs_first_mismatch_index",
        "initial_exact", "initial_exact_count", "initial_total", "initial_mismatches", "initial_first_mismatch_index",
        "outer_exact", "outer_exact_count", "outer_total", "outer_mismatches", "outer_first_mismatch_index",
        "final_exact", "final_exact_count", "final_total", "final_mismatches", "final_first_mismatch_index",
        "active_ion_exact", "active_ion_exact_count", "active_ion_total", "active_ion_mismatches", "active_ion_first_mismatch_index",
        "solver_method_exact", "outer_iterations_exact", "fixed_point_iterations_exact",
        "normalization_exact", "normalization_error_exact", "max_relative_row_residual_exact",
        "ion_boundary_exact", "level_boundary_exact", "level_exact_count", "level_source_count", "level_native_count",
    ]
    _write_csv(output_dir / INVENTORY_NAME, inventory_fields, inventory)
    _write_csv(output_dir / FIRST_NAME, list(first_rows[0].keys()) if first_rows else ["sequence", "element_z", "classification"], first_rows)
    _write_csv(output_dir / MATRIX_NAME, list(matrix_rows[0].keys()) if matrix_rows else ["sequence", "element_z"], matrix_rows)

    inventories_complete = len(source_map) == 183 and len(native_map) == 183
    all_classified = len(first_rows) == 183 and not any(row["classification"] == "MISSING_SOLVE_SYSTEM" for row in first_rows)
    basis_seed_exact = len(inventory) == 183 and all(row["basis_exact"] and row["initial_exact"] for row in inventory)
    dense_exact = len(inventory) == 183 and all(row["dense_exact"] for row in inventory)
    heating_exact = len(inventory) == 183 and all(row["heating_exact"] for row in inventory)
    heating2_exact = len(inventory) == 183 and all(row["heating2_exact"] for row in inventory)
    rhs_exact = len(inventory) == 183 and all(row["rhs_exact"] for row in inventory)
    solver_method_exact = len(inventory) == 183 and all(row["solver_method_exact"] for row in inventory)
    solver_iterations_exact = len(inventory) == 183 and all(
        row["outer_iterations_exact"] and row["fixed_point_iterations_exact"] for row in inventory)
    solver_normalization_exact = len(inventory) == 183 and all(
        row["normalization_exact"] and row["normalization_error_exact"] for row in inventory)
    solve_exact = len(inventory) == 183 and all(row["outer_exact"] and row["final_exact"] for row in inventory)
    ion_reconstruction_exact = len(inventory) == 183 and all(row["active_ion_exact"] for row in inventory)
    global_ion_commit_exact = len(inventory) == 183 and all(row["ion_boundary_exact"] for row in inventory)
    global_level_commit_exact = len(inventory) == 183 and all(row["level_boundary_exact"] for row in inventory)
    global_commit_exact = global_ion_commit_exact and global_level_commit_exact
    solver_input_exact = basis_seed_exact and dense_exact and rhs_exact
    matrix_system_exact = dense_exact and heating_exact and heating2_exact and rhs_exact
    fixed_state_exact = solver_input_exact and solve_exact and ion_reconstruction_exact and global_commit_exact
    qualification_accept = (not errors and inventories_complete and all_classified and basis_seed_exact
                            and int(native_summary.get("total_evaluations", 0)) == 61
                            and int(native_summary.get("python_callbacks", -1)) == 0)

    gates = {
        "ALL_61_NATIVE_EVALUATIONS": "ACCEPT" if int(native_summary.get("total_evaluations", 0)) == 61 else "REJECT",
        "PYTHON_CALLBACKS_ZERO": "ACCEPT" if int(native_summary.get("python_callbacks", -1)) == 0 else "REJECT",
        "ALL_61_SOURCE_SOLVE_SYSTEMS_CAPTURED": "ACCEPT" if len(source_map) == 183 else "REJECT",
        "ALL_61_NATIVE_SOLVE_SYSTEMS_CAPTURED": "ACCEPT" if len(native_map) == 183 else "REJECT",
        "ALL_61_BASIS_AND_SEED_HELD_EXACT": "ACCEPT" if basis_seed_exact else "REJECT",
        "ALL_61_DENSE_MATRIX_EXACT": "ACCEPT" if dense_exact else "REJECT",
        "ALL_61_HEATING_MATRIX_EXACT": "ACCEPT" if heating_exact else "REJECT",
        "ALL_61_HEATING2_MATRIX_EXACT": "ACCEPT" if heating2_exact else "REJECT",
        "ALL_61_RHS_EXACT": "ACCEPT" if rhs_exact else "REJECT",
        "ALL_61_SOLVER_INPUT_EXACT": "ACCEPT" if solver_input_exact else "REJECT",
        "ALL_61_MATRIX_SYSTEM_EXACT": "ACCEPT" if matrix_system_exact else "REJECT",
        "ALL_61_SOLVER_METHOD_EXACT": "ACCEPT" if solver_method_exact else "REJECT",
        "ALL_61_SOLVER_ITERATION_COUNTS_EXACT": "ACCEPT" if solver_iterations_exact else "REJECT",
        "ALL_61_SOLVER_NORMALIZATION_EXACT": "ACCEPT" if solver_normalization_exact else "REJECT",
        "ALL_61_SOLVE_RESPONSE_EXACT": "ACCEPT" if solve_exact else "REJECT",
        "ALL_61_ION_RECONSTRUCTION_EXACT": "ACCEPT" if ion_reconstruction_exact else "REJECT",
        "ALL_61_GLOBAL_ION_COMMIT_EXACT": "ACCEPT" if global_ion_commit_exact else "REJECT",
        "ALL_61_GLOBAL_LEVEL_COMMIT_EXACT": "ACCEPT" if global_level_commit_exact else "REJECT",
        "ALL_61_GLOBAL_ELEMENT_COMMIT_EXACT": "ACCEPT" if global_commit_exact else "REJECT",
        "ALL_61_POST_SEED_DIVERGENCES_CLASSIFIED": "ACCEPT" if all_classified else "REJECT",
        "V06487_POST_SEED_SYSTEM_DECOMPOSITION": "ACCEPT" if qualification_accept else "REJECT",
        "V06487_FIXED_STATE_PARITY": "ACCEPT" if fixed_state_exact else "REJECT",
        "V06488_THERMAL_PARITY_READY": "YES" if fixed_state_exact else "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
        "THERMAL_PARITY": "NOT_RUN_READY_FOR_V06488" if fixed_state_exact else "BLOCKED",
        "CONTROLLER_PARITY": "NOT_RUN_V06489",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    }
    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if qualification_accept else "REJECT",
        "errors": errors,
        "source_solve_systems": len(source_map),
        "native_solve_systems": len(native_map),
        "classification_counts": dict(sorted(classifications.items())),
        "exact_counts": {name: int(exacts[name]) for name in sorted(exacts)},
        "total_counts": {name: int(totals[name]) for name in sorted(totals)},
        "gates": gates,
        "qualification_only": True,
        "thermal_parity_started": False,
        "production_promotion_ready": False,
        "type77_benchmark_math": "runtime pow(10,x) retained only for immutable-reference qualification; exp10 remains the production optimization target after exactness qualification",
    }
    (output_dir / SUMMARY_NAME).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-capture", required=True, type=Path)
    parser.add_argument("--native-run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    result = decompose(args.source_capture, args.native_run, args.output)
    if args.output_json:
        args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
