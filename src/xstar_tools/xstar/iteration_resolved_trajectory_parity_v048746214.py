"""Compare source and native iteration-resolved Lucy trajectories for v21.4."""
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
SCHEMA = "xstar-tools-v0648746214-iteration-resolved-trajectory-parity-v1"
DEFAULT_TARGETS = ((1, 1), (6, 1), (1, 2), (1, 12))

SOURCE_FILES = {
    "manifest": "v0472_iteration_resolved_manifest.csv",
    "outer": "v0472_iteration_resolved_outer_rows.csv",
    "super": "v0472_iteration_resolved_superlevels.csv",
    "matrix": "v0472_iteration_resolved_condensed_matrix.csv",
    "fixed": "v0472_iteration_resolved_fixed_rows.csv",
}
NATIVE_SUFFIXES = {
    "manifest": "_manifest.csv",
    "outer": "_outer_rows.csv",
    "super": "_superlevels.csv",
    "matrix": "_condensed_matrix.csv",
    "fixed": "_fixed_rows.csv",
}

STAGE_ORDER = [
    "manifest",
    "outer_start_population",
    "superlevel_population_before",
    "row_fraction",
    "condensed_matrix",
    "condensed_rhs",
    "first_lu_solution",
    "refinement_residual",
    "refinement_correction",
    "refined_superlevel_solution",
    "population_after_condensed",
    "fixed_population_before",
    "fixed_riu",
    "fixed_rui",
    "fixed_ril",
    "fixed_rli",
    "fixed_population_after",
    "fixed_difference",
    "fixed_termination_decision",
    "fixed_iteration_count",
    "population_after_fixed_point",
    "outer_difference",
    "outer_termination_decision",
    "outer_iteration_count",
]
STAGE_RANK = {name: index for index, name in enumerate(STAGE_ORDER)}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _bits(value: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", float(value)))[0]


def _exact(a: str | float, b: str | float) -> bool:
    aa, bb = float(a), float(b)
    if math.isnan(aa) or math.isnan(bb):
        return math.isnan(aa) and math.isnan(bb) and _bits(aa) == _bits(bb)
    return _bits(aa) == _bits(bb)


def _ulp_distance(a: str | float, b: str | float) -> int | None:
    aa, bb = float(a), float(b)
    if not math.isfinite(aa) or not math.isfinite(bb):
        return 0 if _exact(aa, bb) else None
    def ordered(v: float) -> int:
        raw = _bits(v)
        return (~raw & ((1 << 64) - 1)) if raw >> 63 else raw | (1 << 63)
    return abs(ordered(aa) - ordered(bb))


def _parse_targets(values: list[str] | None) -> tuple[tuple[int, int], ...]:
    if not values:
        return DEFAULT_TARGETS
    return tuple((int(value.split(":", 1)[0]), int(value.split(":", 1)[1])) for value in values)


def _system(row: dict[str, str]) -> tuple[int, int]:
    return int(row["sequence"]), int(row["element_z"])


def _load_source(root: Path) -> dict[str, list[dict[str, str]]]:
    return {name: _read_csv(root / filename) for name, filename in SOURCE_FILES.items()}


def _load_native(root: Path, targets: tuple[tuple[int, int], ...]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {name: [] for name in NATIVE_SUFFIXES}
    for sequence, z in targets:
        stem = f"sequence_{sequence:04d}_element_{z:02d}"
        candidates = list(root.glob(f"**/iteration_trace/{stem}_manifest.csv"))
        if len(candidates) != 1:
            raise FileNotFoundError(f"native trace manifest inventory for {sequence}:{z} is {len(candidates)}, expected 1")
        directory = candidates[0].parent
        for name, suffix in NATIVE_SUFFIXES.items():
            path = directory / f"{stem}{suffix}"
            if not path.is_file():
                raise FileNotFoundError(path)
            result[name].extend(_read_csv(path))
    return result


def analyze(source_capture: Path, native_run: Path, output: Path,
            targets: tuple[tuple[int, int], ...] = DEFAULT_TARGETS) -> dict[str, Any]:
    source_capture, native_run, output = source_capture.resolve(), native_run.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    try:
        source = _load_source(source_capture)
        native = _load_native(native_run, targets)
    except Exception as exc:
        result = {"schema": SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "milestone_result": "REJECT", "scientific_result": "NOT_RUN_CAPTURE_INCOMPLETE",
                  "qualification_only": True, "production_promotion_ready": False}
        _write_json(output / "v048746214_iteration_trajectory_report.json", result)
        return result

    target_set = set(targets)
    source_manifest = {_system(row): row for row in source["manifest"]}
    native_manifest = {_system(row): row for row in native["manifest"]}
    source_complete = set(source_manifest) == target_set
    native_complete = set(native_manifest) == target_set
    if not source_complete:
        errors.append(f"source_target_inventory={sorted(source_manifest)} expected={sorted(target_set)}")
    if not native_complete:
        errors.append(f"native_target_inventory={sorted(native_manifest)} expected={sorted(target_set)}")

    source_maps = {
        "outer": {(_system(r), int(r["outer_iteration"]), int(r["compact_row"])): r for r in source["outer"]},
        "super": {(_system(r), int(r["outer_iteration"]), int(r["superlevel"])): r for r in source["super"]},
        "matrix": {(_system(r), int(r["outer_iteration"]), int(r["row_superlevel"]), int(r["column_superlevel"])): r for r in source["matrix"]},
        "fixed": {(_system(r), int(r["outer_iteration"]), int(r["fixed_iteration"]), int(r["compact_row"])): r for r in source["fixed"]},
    }
    native_maps = {
        "outer": {(_system(r), int(r["outer_iteration"]), int(r["compact_row"])): r for r in native["outer"]},
        "super": {(_system(r), int(r["outer_iteration"]), int(r["superlevel"])): r for r in native["super"]},
        "matrix": {(_system(r), int(r["outer_iteration"]), int(r["row_superlevel"]), int(r["column_superlevel"])): r for r in native["matrix"]},
        "fixed": {(_system(r), int(r["outer_iteration"]), int(r["fixed_iteration"]), int(r["compact_row"])): r for r in native["fixed"]},
    }

    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"exact": 0, "total": 0})
    iteration1_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"exact": 0, "total": 0})
    mismatch_rows: list[dict[str, Any]] = []
    system_rows: list[dict[str, Any]] = []

    def compare_value(system: tuple[int, int], stage: str, source_value: str | float,
                      native_value: str | float, outer: int = 0, fixed: int = 0,
                      identity: str = "") -> bool:
        exact = _exact(source_value, native_value)
        stats[stage]["total"] += 1
        stats[stage]["exact"] += int(exact)
        if outer == 1:
            iteration1_stats[stage]["total"] += 1
            iteration1_stats[stage]["exact"] += int(exact)
        if not exact and len(mismatch_rows) < 10000:
            mismatch_rows.append({
                "sequence": system[0], "element_z": system[1], "stage": stage,
                "outer_iteration": outer, "fixed_iteration": fixed, "identity": identity,
                "source_value": source_value, "native_value": native_value,
                "ulp_distance": _ulp_distance(source_value, native_value),
            })
        return exact

    for system in targets:
        first: dict[str, Any] | None = None
        def note(stage: str, outer: int = 0, fixed: int = 0, identity: str = "",
                 source_value: Any = "", native_value: Any = "") -> None:
            nonlocal first
            if first is None:
                first = {"stage": stage, "outer_iteration": outer, "fixed_iteration": fixed,
                         "identity": identity, "source_value": source_value, "native_value": native_value}

        sm, nm = source_manifest.get(system), native_manifest.get(system)
        if sm is None or nm is None:
            note("manifest")
            system_rows.append({"sequence": system[0], "element_z": system[1],
                                "classification": "CAPTURE_INCOMPLETE", "first_divergence_stage": "manifest"})
            continue
        manifest_exact = True
        for field in ("n_rows", "n_superlevels", "normalization_row", "max_outer_iterations", "max_fixed_iterations"):
            same = int(sm[field]) == int(nm[field])
            stats["manifest"]["total"] += 1; stats["manifest"]["exact"] += int(same)
            manifest_exact &= same
            if not same: note("manifest", identity=field, source_value=sm[field], native_value=nm[field])
        for field in ("lucy_tolerance", "fixed_point_tolerance"):
            same = compare_value(system, "manifest", sm[field], nm[field], identity=field)
            manifest_exact &= same
            if not same: note("manifest", identity=field, source_value=sm[field], native_value=nm[field])
        nrows, nsp = int(sm["n_rows"]), int(sm["n_superlevels"])
        source_outer_count, native_outer_count = int(sm["outer_iterations"]), int(nm["outer_iterations"])
        common_outer = min(source_outer_count, native_outer_count)
        for outer in range(1, common_outer + 1):
            # Outer row vector stages.
            for row in range(1, nrows + 1):
                key = (system, outer, row)
                sr, nr = source_maps["outer"].get(key), native_maps["outer"].get(key)
                if sr is None or nr is None:
                    note("outer_start_population", outer, identity=f"row={row}")
                    continue
                for field, stage in (
                    ("outer_start_population", "outer_start_population"),
                    ("row_fraction", "row_fraction"),
                    ("population_after_condensed", "population_after_condensed"),
                    ("population_after_fixed_point", "population_after_fixed_point"),
                ):
                    same = compare_value(system, stage, sr[field], nr[field], outer, identity=f"row={row}")
                    if not same: note(stage, outer, identity=f"row={row}", source_value=sr[field], native_value=nr[field])
                for field in ("superlevel", "ion"):
                    same = int(sr[field]) == int(nr[field])
                    stats["manifest"]["total"] += 1; stats["manifest"]["exact"] += int(same)
                    if not same: note("manifest", outer, identity=f"row={row}:{field}", source_value=sr[field], native_value=nr[field])
            # Superlevel and matrix stages.
            for sp in range(1, nsp + 1):
                key = (system, outer, sp)
                sr, nr = source_maps["super"].get(key), native_maps["super"].get(key)
                if sr is None or nr is None:
                    note("superlevel_population_before", outer, identity=f"superlevel={sp}")
                    continue
                for field, stage in (
                    ("population_before_condensed_solve", "superlevel_population_before"),
                    ("condensed_rhs", "condensed_rhs"),
                    ("first_lu_solution", "first_lu_solution"),
                    ("refinement_residual", "refinement_residual"),
                    ("refinement_correction", "refinement_correction"),
                    ("refined_superlevel_solution", "refined_superlevel_solution"),
                ):
                    same = compare_value(system, stage, sr[field], nr[field], outer, identity=f"superlevel={sp}")
                    if not same: note(stage, outer, identity=f"superlevel={sp}", source_value=sr[field], native_value=nr[field])
                for col in range(1, nsp + 1):
                    mkey = (system, outer, sp, col)
                    smr, nmr = source_maps["matrix"].get(mkey), native_maps["matrix"].get(mkey)
                    if smr is None or nmr is None:
                        note("condensed_matrix", outer, identity=f"cell={sp},{col}")
                        continue
                    same = compare_value(system, "condensed_matrix", smr["normalized_matrix_value"],
                                         nmr["normalized_matrix_value"], outer, identity=f"cell={sp},{col}")
                    if not same: note("condensed_matrix", outer, identity=f"cell={sp},{col}",
                                      source_value=smr["normalized_matrix_value"], native_value=nmr["normalized_matrix_value"])
            # Fixed iterations aligned inside this outer iteration.
            source_fixed = int(source_maps["outer"][(system, outer, 1)]["fixed_iterations_this_outer"])
            native_fixed = int(native_maps["outer"][(system, outer, 1)]["fixed_iterations_this_outer"])
            common_fixed = min(source_fixed, native_fixed)
            for fixed in range(1, common_fixed + 1):
                for row in range(1, nrows + 1):
                    key = (system, outer, fixed, row)
                    sr, nr = source_maps["fixed"].get(key), native_maps["fixed"].get(key)
                    if sr is None or nr is None:
                        note("fixed_population_before", outer, fixed, f"row={row}")
                        continue
                    for field, stage in (
                        ("population_before", "fixed_population_before"),
                        ("riu", "fixed_riu"), ("rui", "fixed_rui"),
                        ("ril", "fixed_ril"), ("rli", "fixed_rli"),
                        ("population_after", "fixed_population_after"),
                    ):
                        same = compare_value(system, stage, sr[field], nr[field], outer, fixed, f"row={row}")
                        if not same: note(stage, outer, fixed, f"row={row}", sr[field], nr[field])
                sr = source_maps["fixed"].get((system, outer, fixed, 1))
                nr = native_maps["fixed"].get((system, outer, fixed, 1))
                if sr and nr:
                    same = compare_value(system, "fixed_difference", sr["fixed_difference"], nr["fixed_difference"], outer, fixed)
                    if not same: note("fixed_difference", outer, fixed, source_value=sr["fixed_difference"], native_value=nr["fixed_difference"])
                    decision_same = sr["termination_reason"] == nr["termination_reason"]
                    stats["fixed_termination_decision"]["total"] += 1
                    stats["fixed_termination_decision"]["exact"] += int(decision_same)
                    if outer == 1:
                        iteration1_stats["fixed_termination_decision"]["total"] += 1
                        iteration1_stats["fixed_termination_decision"]["exact"] += int(decision_same)
                    if not decision_same: note("fixed_termination_decision", outer, fixed,
                                               source_value=sr["termination_reason"], native_value=nr["termination_reason"])
            count_same = source_fixed == native_fixed
            stats["fixed_iteration_count"]["total"] += 1; stats["fixed_iteration_count"]["exact"] += int(count_same)
            if outer == 1:
                iteration1_stats["fixed_iteration_count"]["total"] += 1
                iteration1_stats["fixed_iteration_count"]["exact"] += int(count_same)
            if not count_same: note("fixed_iteration_count", outer, source_value=source_fixed, native_value=native_fixed)
            sor = source_maps["outer"].get((system, outer, 1)); nor = native_maps["outer"].get((system, outer, 1))
            if sor and nor:
                same = compare_value(system, "outer_difference", sor["outer_difference"], nor["outer_difference"], outer)
                if not same: note("outer_difference", outer, source_value=sor["outer_difference"], native_value=nor["outer_difference"])
                decision_same = sor["outer_termination_reason"] == nor["outer_termination_reason"]
                stats["outer_termination_decision"]["total"] += 1
                stats["outer_termination_decision"]["exact"] += int(decision_same)
                if outer == 1:
                    iteration1_stats["outer_termination_decision"]["total"] += 1
                    iteration1_stats["outer_termination_decision"]["exact"] += int(decision_same)
                if not decision_same: note("outer_termination_decision", outer,
                                           source_value=sor["outer_termination_reason"], native_value=nor["outer_termination_reason"])
        outer_count_same = source_outer_count == native_outer_count
        stats["outer_iteration_count"]["total"] += 1; stats["outer_iteration_count"]["exact"] += int(outer_count_same)
        if not outer_count_same: note("outer_iteration_count", common_outer + 1,
                                      source_value=source_outer_count, native_value=native_outer_count)
        classification = "FULLY_EXACT" if first is None else first["stage"]
        system_rows.append({
            "sequence": system[0], "element_z": system[1],
            "source_outer_iterations": source_outer_count, "native_outer_iterations": native_outer_count,
            "source_total_fixed_iterations": int(sm["total_fixed_point_iterations"]),
            "native_total_fixed_iterations": int(nm["total_fixed_point_iterations"]),
            "classification": classification,
            "first_divergence_stage": "FULLY_EXACT" if first is None else first["stage"],
            "first_divergence_outer_iteration": 0 if first is None else first["outer_iteration"],
            "first_divergence_fixed_iteration": 0 if first is None else first["fixed_iteration"],
            "first_divergence_identity": "" if first is None else first["identity"],
            "first_source_value": "" if first is None else first["source_value"],
            "first_native_value": "" if first is None else first["native_value"],
        })

    classified = len(system_rows)
    fully_exact = sum(row["classification"] == "FULLY_EXACT" for row in system_rows)
    divergent = [row for row in system_rows if row["classification"] != "FULLY_EXACT"]
    first_global = min(
        divergent,
        key=lambda row: (STAGE_RANK.get(str(row["first_divergence_stage"]), 999),
                         int(row["first_divergence_outer_iteration"]),
                         int(row["first_divergence_fixed_iteration"]),
                         targets.index((int(row["sequence"]), int(row["element_z"])))),
        default=None,
    )
    capture_complete = source_complete and native_complete and classified == len(targets) and not errors
    milestone = capture_complete
    scientific = milestone and fully_exact == len(targets)

    def gate(stage: str) -> dict[str, int | bool]:
        value = iteration1_stats.get(stage, {"exact": 0, "total": 0})
        return {"exact": value["exact"], "total": value["total"],
                "accepted": value["total"] > 0 and value["exact"] == value["total"]}

    iteration1_gates = {
        "OUTER_ITERATION_1_START_EXACT": gate("outer_start_population"),
        "OUTER_ITERATION_1_SUPERLEVEL_POPULATIONS_EXACT": gate("superlevel_population_before"),
        "OUTER_ITERATION_1_ROW_FRACTIONS_EXACT": gate("row_fraction"),
        "OUTER_ITERATION_1_CONDENSED_MATRIX_EXACT": gate("condensed_matrix"),
        "OUTER_ITERATION_1_CONDENSED_RHS_EXACT": gate("condensed_rhs"),
        "OUTER_ITERATION_1_LU_SOLUTION_EXACT": gate("first_lu_solution"),
        "OUTER_ITERATION_1_REFINEMENT_RESIDUAL_EXACT": gate("refinement_residual"),
        "OUTER_ITERATION_1_REFINEMENT_CORRECTION_EXACT": gate("refinement_correction"),
        "OUTER_ITERATION_1_REFINED_SOLUTION_EXACT": gate("refined_superlevel_solution"),
        "OUTER_ITERATION_1_EXPANDED_POPULATION_EXACT": gate("population_after_condensed"),
        "OUTER_ITERATION_1_FIXED_POINT_INPUT_EXACT": gate("fixed_population_before"),
        "OUTER_ITERATION_1_FIXED_POINT_OUTPUT_EXACT": gate("fixed_population_after"),
        "OUTER_ITERATION_1_FIXED_POINT_DECISION_EXACT": gate("fixed_termination_decision"),
        "OUTER_ITERATION_1_OUTER_DECISION_EXACT": gate("outer_termination_decision"),
    }
    result = {
        "schema": SCHEMA, "release": RELEASE,
        "result": "ACCEPT" if milestone else "REJECT", "errors": errors,
        "milestone_result": "ACCEPT" if milestone else "REJECT",
        "scientific_result": "ACCEPT" if scientific else "REJECT",
        "source_capture_complete": source_complete, "native_capture_complete": native_complete,
        "targets": [f"{sequence}:{z}" for sequence, z in targets],
        "systems_classified": classified, "systems_fully_exact": fully_exact,
        "first_divergence_stage": "FULLY_EXACT" if first_global is None else first_global["first_divergence_stage"],
        "first_divergence_sequence": None if first_global is None else first_global["sequence"],
        "first_divergence_element_z": None if first_global is None else first_global["element_z"],
        "first_divergence_outer_iteration": None if first_global is None else first_global["first_divergence_outer_iteration"],
        "first_divergence_fixed_iteration": None if first_global is None else first_global["first_divergence_fixed_iteration"],
        "iteration1_gates": iteration1_gates,
        "stage_exactness": dict(stats),
        "downstream_thermal_science": "NOT_RUN_ITERATION_TRAJECTORY_PREREQUISITE" if not scientific else "READY_FOR_POPULATION_GATE",
        "qualification_only": True, "production_promotion_ready": False,
    }
    _write_csv(output / "v048746214_iteration_trajectory_system_comparison.csv", [
        "sequence", "element_z", "source_outer_iterations", "native_outer_iterations",
        "source_total_fixed_iterations", "native_total_fixed_iterations", "classification",
        "first_divergence_stage", "first_divergence_outer_iteration", "first_divergence_fixed_iteration",
        "first_divergence_identity", "first_source_value", "first_native_value"], system_rows)
    _write_csv(output / "v048746214_iteration_trajectory_mismatches.csv", [
        "sequence", "element_z", "stage", "outer_iteration", "fixed_iteration", "identity",
        "source_value", "native_value", "ulp_distance"], mismatch_rows)
    _write_json(output / "v048746214_iteration_trajectory_report.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--target", action="append")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    result = analyze(args.source_capture, args.native_run, args.output, _parse_targets(args.target))
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
