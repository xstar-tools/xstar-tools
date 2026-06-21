"""All-61 compact-population solve-stage parity decomposition for v21.3.

The audit is deliberately earlier than Thermal accounting.  It compares the
source and native compact solve at each numerical boundary, assigns every
(sequence, element) system its earliest divergent stage, and keeps milestone
acceptance (complete decomposition) separate from scientific acceptance
(bit-exact final populations).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

RELEASE = "0.6.48.7.46.21.4"
SCHEMA = "xstar-tools-v0648746213-compact-population-solve-stage-parity-v1"
EXPECTED_ROWS = 40149
EXPECTED_SYSTEMS = 183
EXPECTED_IONS = 1098
EXPECTED_BY_ELEMENT = {1: 2013, 2: 4758, 12: 33378}
ELEMENTS = (1, 2, 12)
SEQUENCES = tuple(range(1, 62))

ROW_SOURCE = "v0472_all61_solve_stage_rows.csv"
SUPER_SOURCE = "v0472_all61_solve_stage_superlevels.csv"
MATRIX_SOURCE = "v0472_all61_solve_stage_condensed_matrix.csv"
MANIFEST_SOURCE = "v0472_all61_solve_stage_manifest.csv"
ION_SOURCE = "v0472_all61_ion_populations.csv"

SYSTEM_COMPARISON = "v048746213_solve_stage_system_comparison.csv"
FIRST_DIVERGENCE = "v048746213_solve_stage_first_divergence.csv"
ROW_MISMATCHES = "v048746213_solve_stage_row_mismatches.csv"
SUPER_MISMATCHES = "v048746213_solve_stage_superlevel_mismatches.csv"
MATRIX_MISMATCHES = "v048746213_solve_stage_matrix_mismatches.csv"
FINGERPRINTS = "v048746213_compact_population_fingerprints.csv"

# This is also the precedence used to classify the first causal boundary.
STAGE_ORDER = (
    "topology",
    "transformed_initial_population",
    "final_outer_iteration_count",
    "final_outer_start_population",
    "population_before_condensed_solve",
    "full_rhs",
    "normalization_metadata",
    "normalized_condensed_matrix",
    "condensed_rhs",
    "first_lu_solution",
    "refinement_residual",
    "refinement_correction",
    "refined_superlevel_solution",
    "population_after_condensed",
    "fixed_point_iteration_count",
    "final_fixed_point_population_before",
    "final_fixed_point_population_after",
    "final_compact_population",
    "ion_reconstruction",
)

ROW_STAGES = (
    ("transformed_initial_population", "transformed_initial_population"),
    ("final_outer_start_population", "final_outer_start_population"),
    ("population_after_condensed", "population_after_condensed"),
    ("final_fixed_point_population_before", "final_fixed_point_population_before"),
    ("final_fixed_point_population_after", "final_fixed_point_population_after"),
    ("final_compact_population", "final_population"),
    ("full_rhs", "rhs"),
)
SUPER_STAGES = (
    ("population_before_condensed_solve", "population_before_condensed_solve"),
    ("condensed_rhs", "condensed_rhs"),
    ("first_lu_solution", "first_lu_solution"),
    ("refinement_residual", "refinement_residual"),
    ("refinement_correction", "refinement_correction"),
    ("refined_superlevel_solution", "refined_superlevel_solution"),
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


def _bits(value: float) -> bytes:
    return struct.pack("<d", float(value))


def _ordered_int(bits: int) -> int:
    return (~bits & 0xFFFFFFFFFFFFFFFF) if bits & (1 << 63) else bits | (1 << 63)


def _ulp(left: float, right: float) -> int:
    if math.isnan(left) or math.isnan(right):
        return 2**64 - 1
    a = struct.unpack("<Q", _bits(left))[0]
    b = struct.unpack("<Q", _bits(right))[0]
    return abs(_ordered_int(a) - _ordered_int(b))


def _exact(left: float, right: float) -> bool:
    return _bits(left) == _bits(right)


def _fnv1a(values: Iterable[float]) -> str:
    value = 1469598103934665603
    for item in values:
        for byte in _bits(item):
            value ^= byte
            value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016x}"


def _native_stage_paths(native_run: Path, sequence: int) -> tuple[Path, Path, Path, Path]:
    root = native_run / "qualification_diagnostics"
    stem = f"evaluation_{sequence:04d}_all_element_solve_stage"
    return (
        root / f"{stem}_rows.csv",
        root / f"{stem}_superlevels.csv",
        root / f"{stem}_condensed_matrix.csv",
        root / f"{stem}_manifest.csv",
    )


def _load_native(native_run: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    all_rows: list[dict[str, str]] = []
    all_super: list[dict[str, str]] = []
    all_matrix: list[dict[str, str]] = []
    all_manifest: list[dict[str, str]] = []
    for sequence in SEQUENCES:
        row_path, super_path, matrix_path, manifest_path = _native_stage_paths(native_run, sequence)
        missing = [str(path) for path in (row_path, super_path, matrix_path, manifest_path) if not path.is_file()]
        if missing:
            raise FileNotFoundError("missing native solve-stage diagnostic: " + ", ".join(missing))
        for target, path in ((all_rows, row_path), (all_super, super_path), (all_matrix, matrix_path), (all_manifest, manifest_path)):
            rows = _read_csv(path)
            for row in rows:
                row = dict(row)
                row["sequence"] = str(sequence)
                target.append(row)
    return all_rows, all_super, all_matrix, all_manifest


def _unique(rows: Iterable[dict[str, str]], key_fn, label: str) -> dict[Any, dict[str, str]]:
    result: dict[Any, dict[str, str]] = {}
    for row in rows:
        key = key_fn(row)
        if key in result:
            raise RuntimeError(f"duplicate {label} key: {key}")
        result[key] = row
    return result


def _value_mismatch(stage: str, key: tuple[int, ...], source: float, native: float) -> dict[str, Any]:
    residual = native - source
    relative = residual / source if source != 0.0 else (0.0 if residual == 0.0 else math.copysign(math.inf, residual))
    return {
        "stage": stage,
        "sequence": key[0],
        "element_z": key[1],
        "index1": key[2] if len(key) > 2 else 0,
        "index2": key[3] if len(key) > 3 else 0,
        "source_value": format(source, ".17g"),
        "native_value": format(native, ".17g"),
        "ulp_distance": _ulp(source, native),
        "absolute_residual": format(residual, ".17g"),
        "relative_residual": format(relative, ".17g"),
    }


def _load_native_ions(native_run: Path) -> dict[tuple[int, int, int], float]:
    root = native_run / "qualification_diagnostics"
    values: dict[tuple[int, int, int], float] = {}
    for sequence in SEQUENCES:
        manifest_path = root / f"evaluation_{sequence:04d}_all_element_solve_system_manifest.csv"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"missing native solve-system manifest: {manifest_path}")
        for row in _read_csv(manifest_path):
            z = int(row["element_z"]); count = int(row["ion_reconstruction_count"])
            path = root / row["ion_reconstruction_path"]
            payload = path.read_bytes()
            if len(payload) != count * 8:
                raise RuntimeError(f"ion reconstruction size mismatch sequence={sequence} element={z}")
            unpacked = struct.unpack("<" + "d" * count, payload)
            for stage, value in enumerate(unpacked, start=1):
                key = (sequence, z, stage)
                if key in values:
                    raise RuntimeError(f"duplicate native ion reconstruction key: {key}")
                values[key] = float(value)
    return values


def audit(source_capture: Path, native_run: Path, output: Path) -> dict[str, Any]:
    source_capture = source_capture.resolve()
    native_run = native_run.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source_paths = [source_capture / name for name in (ROW_SOURCE, SUPER_SOURCE, MATRIX_SOURCE, MANIFEST_SOURCE, ION_SOURCE)]
    missing = [str(path) for path in source_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing source solve-stage capture: " + ", ".join(missing))

    source_rows = _read_csv(source_paths[0])
    source_super = _read_csv(source_paths[1])
    source_matrix = _read_csv(source_paths[2])
    source_manifest_rows = _read_csv(source_paths[3])
    source_ion_rows = _read_csv(source_paths[4])
    native_rows, native_super, native_matrix, native_manifest_rows = _load_native(native_run)
    native_ions = _load_native_ions(native_run)

    row_key = lambda r: (int(r["sequence"]), int(r["element_z"]), int(r["compact_row"]))
    super_key = lambda r: (int(r["sequence"]), int(r["element_z"]), int(r["superlevel"]))
    matrix_key = lambda r: (int(r["sequence"]), int(r["element_z"]), int(r["row_superlevel"]), int(r["column_superlevel"]))
    system_key = lambda r: (int(r["sequence"]), int(r["element_z"]))
    src_rows = _unique(source_rows, row_key, "source row")
    nat_rows = _unique(native_rows, row_key, "native row")
    src_super = _unique(source_super, super_key, "source superlevel")
    nat_super = _unique(native_super, super_key, "native superlevel")
    src_matrix = _unique(source_matrix, matrix_key, "source matrix")
    nat_matrix = _unique(native_matrix, matrix_key, "native matrix")
    src_manifest = _unique(source_manifest_rows, system_key, "source manifest")
    nat_manifest = _unique(native_manifest_rows, system_key, "native manifest")
    source_ions = _unique(
        source_ion_rows,
        lambda r: (int(r["sequence"]), int(r["element_z"]), int(r["stage"])),
        "source ion reconstruction",
    )

    expected_systems = {(seq, z) for seq in SEQUENCES for z in ELEMENTS}
    all_systems = set(src_manifest) | set(nat_manifest)
    inventory_errors: list[str] = []
    if set(src_manifest) != expected_systems:
        inventory_errors.append(f"source_systems={len(src_manifest)}")
    if set(nat_manifest) != expected_systems:
        inventory_errors.append(f"native_systems={len(nat_manifest)}")
    if len(src_rows) != EXPECTED_ROWS:
        inventory_errors.append(f"source_rows={len(src_rows)}")
    if len(nat_rows) != EXPECTED_ROWS:
        inventory_errors.append(f"native_rows={len(nat_rows)}")
    if len(source_ions) != EXPECTED_IONS:
        inventory_errors.append(f"source_ions={len(source_ions)}")
    if len(native_ions) != EXPECTED_IONS:
        inventory_errors.append(f"native_ions={len(native_ions)}")

    stage_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"compared": 0, "exact": 0, "mismatches": 0, "missing": 0})
    stage_first: dict[str, dict[str, Any]] = {}
    system_stage_mismatch: dict[tuple[int, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    row_mismatches: list[dict[str, Any]] = []
    super_mismatches: list[dict[str, Any]] = []
    matrix_mismatches: list[dict[str, Any]] = []

    # Topology and row-valued stages.
    topology_fields = ("active_min_stage", "active_max_stage", "superlevel", "ion", "ion_charge", "is_normalization_row")
    for key in sorted(set(src_rows) | set(nat_rows)):
        src = src_rows.get(key); nat = nat_rows.get(key)
        if src is None or nat is None:
            stage_stats["topology"]["missing"] += 1
            system_stage_mismatch[key[:2]]["topology"] += 1
            continue
        stage_stats["topology"]["compared"] += 1
        topology_ok = all(str(src.get(field, "")) == str(nat.get(field, "")) for field in topology_fields)
        if topology_ok:
            stage_stats["topology"]["exact"] += 1
        else:
            stage_stats["topology"]["mismatches"] += 1
            system_stage_mismatch[key[:2]]["topology"] += 1
            if "topology" not in stage_first:
                stage_first["topology"] = {"sequence": key[0], "element_z": key[1], "compact_row": key[2], "source": {f: src.get(f) for f in topology_fields}, "native": {f: nat.get(f) for f in topology_fields}}
        for stage, field in ROW_STAGES:
            stage_stats[stage]["compared"] += 1
            source_value = float(src[field]); native_value = float(nat[field])
            if _exact(source_value, native_value):
                stage_stats[stage]["exact"] += 1
            else:
                stage_stats[stage]["mismatches"] += 1
                system_stage_mismatch[key[:2]][stage] += 1
                mismatch = _value_mismatch(stage, key, source_value, native_value)
                row_mismatches.append(mismatch)
                stage_first.setdefault(stage, mismatch)

    # Manifest / iteration metadata.
    manifest_exact_fields = (
        "active_min_stage", "active_max_stage", "n_rows", "n_superlevels", "n_ions", "normalization_row"
    )
    for key in sorted(all_systems):
        src = src_manifest.get(key); nat = nat_manifest.get(key)
        if src is None or nat is None:
            for stage in ("normalization_metadata", "final_outer_iteration_count", "fixed_point_iteration_count"):
                stage_stats[stage]["missing"] += 1; system_stage_mismatch[key][stage] += 1
            continue
        stage_stats["normalization_metadata"]["compared"] += 1
        metadata_ok = all(int(src[f]) == int(nat[f]) for f in manifest_exact_fields)
        if metadata_ok:
            stage_stats["normalization_metadata"]["exact"] += 1
        else:
            stage_stats["normalization_metadata"]["mismatches"] += 1
            system_stage_mismatch[key]["normalization_metadata"] += 1
            stage_first.setdefault("normalization_metadata", {"sequence": key[0], "element_z": key[1], "source": {f: src[f] for f in manifest_exact_fields}, "native": {f: nat[f] for f in manifest_exact_fields}})
        for stage, field in (("final_outer_iteration_count", "final_outer_iteration"), ("fixed_point_iteration_count", "total_fixed_point_iterations")):
            stage_stats[stage]["compared"] += 1
            if int(src[field]) == int(nat[field]):
                stage_stats[stage]["exact"] += 1
            else:
                stage_stats[stage]["mismatches"] += 1
                system_stage_mismatch[key][stage] += 1
                stage_first.setdefault(stage, {"sequence": key[0], "element_z": key[1], "source_value": int(src[field]), "native_value": int(nat[field])})
        # Final inner-iteration count is preserved as an additional diagnostic.
        stage = "final_fixed_iteration_count"
        stage_stats[stage]["compared"] += 1
        if int(src["final_fixed_iterations"]) == int(nat["final_fixed_iterations"]):
            stage_stats[stage]["exact"] += 1
        else:
            stage_stats[stage]["mismatches"] += 1
            system_stage_mismatch[key]["fixed_point_iteration_count"] += 1
            stage_first.setdefault(stage, {"sequence": key[0], "element_z": key[1], "source_value": int(src["final_fixed_iterations"]), "native_value": int(nat["final_fixed_iterations"])})

    # Condensed system and solver intermediates.
    for key in sorted(set(src_matrix) | set(nat_matrix)):
        src = src_matrix.get(key); nat = nat_matrix.get(key); stage = "normalized_condensed_matrix"
        if src is None or nat is None:
            stage_stats[stage]["missing"] += 1; system_stage_mismatch[key[:2]][stage] += 1
            continue
        stage_stats[stage]["compared"] += 1
        sv = float(src["normalized_matrix_value"]); nv = float(nat["normalized_matrix_value"])
        if _exact(sv, nv): stage_stats[stage]["exact"] += 1
        else:
            stage_stats[stage]["mismatches"] += 1; system_stage_mismatch[key[:2]][stage] += 1
            mismatch = _value_mismatch(stage, key, sv, nv); matrix_mismatches.append(mismatch); stage_first.setdefault(stage, mismatch)

    for key in sorted(set(src_super) | set(nat_super)):
        src = src_super.get(key); nat = nat_super.get(key)
        for stage, field in SUPER_STAGES:
            if src is None or nat is None:
                stage_stats[stage]["missing"] += 1; system_stage_mismatch[key[:2]][stage] += 1
                continue
            stage_stats[stage]["compared"] += 1
            sv = float(src[field]); nv = float(nat[field])
            if _exact(sv, nv): stage_stats[stage]["exact"] += 1
            else:
                stage_stats[stage]["mismatches"] += 1; system_stage_mismatch[key[:2]][stage] += 1
                mismatch = _value_mismatch(stage, key, sv, nv); super_mismatches.append(mismatch); stage_first.setdefault(stage, mismatch)

    # Ion reconstruction is downstream of the compact vector but still before Thermal accounting.
    for key in sorted(set(source_ions) | set(native_ions)):
        src = source_ions.get(key); native_value = native_ions.get(key); stage = "ion_reconstruction"
        if src is None or native_value is None:
            stage_stats[stage]["missing"] += 1; system_stage_mismatch[key[:2]][stage] += 1
            continue
        stage_stats[stage]["compared"] += 1
        source_value = float(src["population"])
        if _exact(source_value, native_value):
            stage_stats[stage]["exact"] += 1
        else:
            stage_stats[stage]["mismatches"] += 1; system_stage_mismatch[key[:2]][stage] += 1
            mismatch = _value_mismatch(stage, key, source_value, native_value)
            row_mismatches.append(mismatch); stage_first.setdefault(stage, mismatch)

    # Per-system first divergence and final-population fingerprints.
    system_rows: list[dict[str, Any]] = []
    divergence_rows: list[dict[str, Any]] = []
    final_exact_by_element = defaultdict(int)
    final_total_by_element = defaultdict(int)
    sequence_source: dict[int, list[float]] = defaultdict(list)
    sequence_native: dict[int, list[float]] = defaultdict(list)
    fingerprint_rows: list[dict[str, Any]] = []
    localized = 0
    fully_exact_systems = 0
    for key in sorted(expected_systems):
        first = next((stage for stage in STAGE_ORDER if system_stage_mismatch[key].get(stage, 0) > 0), "FULLY_EXACT")
        if first == "FULLY_EXACT": fully_exact_systems += 1
        localized += int(first == "FULLY_EXACT" or first in STAGE_ORDER)
        sequence, z = key
        final_rows = [rkey for rkey in sorted(src_rows) if rkey[:2] == key]
        final_compared = final_exact = 0
        source_values: list[float] = []; native_values: list[float] = []
        for rkey in final_rows:
            if rkey not in nat_rows: continue
            sv = float(src_rows[rkey]["final_population"]); nv = float(nat_rows[rkey]["final_population"])
            final_compared += 1; final_exact += int(_exact(sv, nv))
            final_total_by_element[z] += 1; final_exact_by_element[z] += int(_exact(sv, nv))
            source_values.append(sv); native_values.append(nv)
            sequence_source[sequence].append(sv); sequence_native[sequence].append(nv)
        source_fp = _fnv1a(source_values); native_fp = _fnv1a(native_values)
        system_rows.append({
            "sequence": sequence, "element_z": z, "first_divergence_stage": first,
            "final_population_compared": final_compared, "final_population_exact": final_exact,
            "source_final_fingerprint": source_fp, "native_final_fingerprint": native_fp,
            "final_fingerprint_exact": int(source_fp == native_fp and final_compared == len(final_rows)),
            **{f"{stage}_mismatches": system_stage_mismatch[key].get(stage, 0) for stage in STAGE_ORDER},
        })
        detail = stage_first.get(first, {}) if first != "FULLY_EXACT" else {}
        divergence_rows.append({
            "sequence": sequence, "element_z": z, "first_divergence_stage": first,
            "mismatch_count_at_first_stage": system_stage_mismatch[key].get(first, 0),
            "first_global_example": json.dumps(detail, sort_keys=True) if detail else "",
        })

    sequence_fingerprints_exact = 0
    for seq in SEQUENCES:
        sfp = _fnv1a(sequence_source[seq]); nfp = _fnv1a(sequence_native[seq])
        exact = sfp == nfp and len(sequence_source[seq]) == len(sequence_native[seq])
        sequence_fingerprints_exact += int(exact)
        fingerprint_rows.append({"sequence": seq, "population_count": len(sequence_source[seq]), "source_fingerprint": sfp, "native_fingerprint": nfp, "fingerprint_exact": int(exact)})

    _write_csv(output / SYSTEM_COMPARISON, list(system_rows[0].keys()) if system_rows else ["sequence", "element_z"], system_rows)
    _write_csv(output / FIRST_DIVERGENCE, ["sequence", "element_z", "first_divergence_stage", "mismatch_count_at_first_stage", "first_global_example"], divergence_rows)
    mismatch_fields = ["stage", "sequence", "element_z", "index1", "index2", "source_value", "native_value", "ulp_distance", "absolute_residual", "relative_residual"]
    _write_csv(output / ROW_MISMATCHES, mismatch_fields, row_mismatches)
    _write_csv(output / SUPER_MISMATCHES, mismatch_fields, super_mismatches)
    _write_csv(output / MATRIX_MISMATCHES, mismatch_fields, matrix_mismatches)
    _write_csv(output / FINGERPRINTS, ["sequence", "population_count", "source_fingerprint", "native_fingerprint", "fingerprint_exact"], fingerprint_rows)

    final_total = sum(final_total_by_element.values()); final_exact = sum(final_exact_by_element.values())
    stage_gates = {
        "COMPACT_TOPOLOGY_EXACT": "ACCEPT" if stage_stats["topology"]["exact"] == EXPECTED_ROWS and stage_stats["topology"]["mismatches"] == stage_stats["topology"]["missing"] == 0 else "REJECT",
        "TRANSFORMED_INITIAL_POPULATIONS_EXACT_40149": "ACCEPT" if stage_stats["transformed_initial_population"]["exact"] == EXPECTED_ROWS else "REJECT",
        "FINAL_OUTER_START_POPULATIONS_EXACT_40149": "ACCEPT" if stage_stats["final_outer_start_population"]["exact"] == EXPECTED_ROWS else "REJECT",
        "COMPACT_RHS_EXACT_40149": "ACCEPT" if stage_stats["full_rhs"]["exact"] == EXPECTED_ROWS else "REJECT",
        "NORMALIZATION_ROWS_EXACT_183": "ACCEPT" if stage_stats["normalization_metadata"]["exact"] == EXPECTED_SYSTEMS else "REJECT",
        "FINAL_OUTER_ITERATIONS_EXACT_183": "ACCEPT" if stage_stats["final_outer_iteration_count"]["exact"] == EXPECTED_SYSTEMS else "REJECT",
        "FIXED_POINT_ITERATION_COUNTS_EXACT_183": "ACCEPT" if stage_stats["fixed_point_iteration_count"]["exact"] == EXPECTED_SYSTEMS and stage_stats["final_fixed_iteration_count"]["exact"] == EXPECTED_SYSTEMS else "REJECT",
        "NORMALIZED_CONDENSED_MATRIX_EXACT": "ACCEPT" if stage_stats["normalized_condensed_matrix"]["mismatches"] == stage_stats["normalized_condensed_matrix"]["missing"] == 0 and stage_stats["normalized_condensed_matrix"]["compared"] > 0 else "REJECT",
        "SUPERLEVEL_POPULATIONS_BEFORE_CONDENSED_EXACT": "ACCEPT" if stage_stats["population_before_condensed_solve"]["mismatches"] == stage_stats["population_before_condensed_solve"]["missing"] == 0 and stage_stats["population_before_condensed_solve"]["compared"] > 0 else "REJECT",
        "CONDENSED_RHS_EXACT": "ACCEPT" if stage_stats["condensed_rhs"]["mismatches"] == stage_stats["condensed_rhs"]["missing"] == 0 and stage_stats["condensed_rhs"]["compared"] > 0 else "REJECT",
        "FIRST_LU_SOLUTIONS_EXACT": "ACCEPT" if stage_stats["first_lu_solution"]["mismatches"] == stage_stats["first_lu_solution"]["missing"] == 0 and stage_stats["first_lu_solution"]["compared"] > 0 else "REJECT",
        "REFINEMENT_RESIDUALS_EXACT": "ACCEPT" if stage_stats["refinement_residual"]["mismatches"] == stage_stats["refinement_residual"]["missing"] == 0 and stage_stats["refinement_residual"]["compared"] > 0 else "REJECT",
        "REFINEMENT_CORRECTIONS_EXACT": "ACCEPT" if stage_stats["refinement_correction"]["mismatches"] == stage_stats["refinement_correction"]["missing"] == 0 and stage_stats["refinement_correction"]["compared"] > 0 else "REJECT",
        "REFINED_SUPERLEVEL_SOLUTIONS_EXACT": "ACCEPT" if stage_stats["refined_superlevel_solution"]["mismatches"] == stage_stats["refined_superlevel_solution"]["missing"] == 0 and stage_stats["refined_superlevel_solution"]["compared"] > 0 else "REJECT",
        "POPULATIONS_AFTER_CONDENSED_EXACT_40149": "ACCEPT" if stage_stats["population_after_condensed"]["exact"] == EXPECTED_ROWS else "REJECT",
        "FINAL_FIXED_POINT_BEFORE_EXACT_40149": "ACCEPT" if stage_stats["final_fixed_point_population_before"]["exact"] == EXPECTED_ROWS else "REJECT",
        "FINAL_FIXED_POINT_AFTER_EXACT_40149": "ACCEPT" if stage_stats["final_fixed_point_population_after"]["exact"] == EXPECTED_ROWS else "REJECT",
        "HYDROGEN_FINAL_COMPACT_POPULATIONS_EXACT": "ACCEPT" if final_exact_by_element[1] == EXPECTED_BY_ELEMENT[1] else "REJECT",
        "HELIUM_FINAL_COMPACT_POPULATIONS_EXACT": "ACCEPT" if final_exact_by_element[2] == EXPECTED_BY_ELEMENT[2] else "REJECT",
        "MAGNESIUM_FINAL_COMPACT_POPULATIONS_EXACT": "ACCEPT" if final_exact_by_element[12] == EXPECTED_BY_ELEMENT[12] else "REJECT",
        "FINAL_COMPACT_POPULATIONS_EXACT_40149": "ACCEPT" if final_exact == EXPECTED_ROWS else "REJECT",
        "ALL61_COMPACT_POPULATION_FINGERPRINTS_EXACT": "ACCEPT" if sequence_fingerprints_exact == len(SEQUENCES) else "REJECT",
        "ION_RECONSTRUCTION_EXACT_1098": "ACCEPT" if stage_stats["ion_reconstruction"]["exact"] == EXPECTED_IONS else "REJECT",
    }
    decomposition_gates = {
        "SOURCE_SOLVE_STAGE_CAPTURE_COMPLETE": "ACCEPT" if not inventory_errors and len(src_manifest) == EXPECTED_SYSTEMS and len(src_rows) == EXPECTED_ROWS else "REJECT",
        "NATIVE_SOLVE_STAGE_CAPTURE_COMPLETE": "ACCEPT" if not inventory_errors and len(nat_manifest) == EXPECTED_SYSTEMS and len(nat_rows) == EXPECTED_ROWS else "REJECT",
        "ALL_183_SYSTEMS_CLASSIFIED": "ACCEPT" if localized == EXPECTED_SYSTEMS else "REJECT",
        "FIRST_DIVERGENCE_LOCALIZED_ALL183": "ACCEPT" if localized == EXPECTED_SYSTEMS else "REJECT",
    }
    milestone = "ACCEPT" if all(v == "ACCEPT" for v in decomposition_gates.values()) else "REJECT"
    scientific = "ACCEPT" if stage_gates["FINAL_COMPACT_POPULATIONS_EXACT_40149"] == "ACCEPT" and stage_gates["ALL61_COMPACT_POPULATION_FINGERPRINTS_EXACT"] == "ACCEPT" else "REJECT"
    first_overall = next((stage for stage in STAGE_ORDER if stage_stats[stage]["mismatches"] or stage_stats[stage]["missing"]), "FULLY_EXACT")
    report = {
        "schema": SCHEMA, "release": RELEASE, "result": milestone,
        "milestone_result": milestone, "scientific_result": scientific,
        "errors": inventory_errors,
        "decomposition_gates": decomposition_gates,
        "stage_gates": stage_gates,
        "first_divergence_stage": first_overall,
        "first_divergence_example": stage_first.get(first_overall),
        "systems_expected": EXPECTED_SYSTEMS, "systems_classified": localized,
        "systems_fully_exact": fully_exact_systems,
        "final_compact_population_values_expected": EXPECTED_ROWS,
        "final_compact_population_values_compared": final_total,
        "final_compact_population_values_exact": final_exact,
        "final_compact_population_values_by_element": {
            str(z): {"expected": EXPECTED_BY_ELEMENT[z], "compared": final_total_by_element[z], "exact": final_exact_by_element[z]}
            for z in ELEMENTS
        },
        "sequence_fingerprints_exact": sequence_fingerprints_exact,
        "stage_statistics": {stage: dict(stage_stats[stage]) for stage in sorted(stage_stats)},
        "source_inventory": {"rows": len(src_rows), "superlevels": len(src_super), "matrix_values": len(src_matrix), "systems": len(src_manifest), "ions": len(source_ions)},
        "native_inventory": {"rows": len(nat_rows), "superlevels": len(nat_super), "matrix_values": len(nat_matrix), "systems": len(nat_manifest), "ions": len(native_ions)},
        "downstream_thermal_science": "READY" if scientific == "ACCEPT" else "NOT_RUN_SOLVE_STAGE_PREREQUISITE",
        "qualification_only": True, "production_promotion_ready": False,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.source_capture, args.native_run, args.output)
    except Exception as exc:
        result = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "milestone_result": "REJECT", "scientific_result": "REJECT", "errors": [str(exc)], "qualification_only": True, "production_promotion_ready": False}
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
