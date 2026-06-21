"""Capture iteration-resolved v0.6.47.2 Lucy trajectories for v21.4.

The probe is observational.  It records selected outer and fixed-point
iterations without changing source solver inputs, arithmetic, convergence, or
returned populations.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import v0472_all61_solve_stage_capture_v0487462131 as base

RELEASE = "0.6.48.7.46.21.5"
SCHEMA = "xstar-tools-v0648746214-v0472-iteration-resolved-trajectory-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v0648746214-v0472-iteration-resolved-trajectory-oracle-v1"
DEFAULT_TARGETS = ((1, 1), (6, 1), (1, 2), (1, 12))
MANIFEST_NAME = "v0472_iteration_resolved_manifest.csv"
OUTER_NAME = "v0472_iteration_resolved_outer_rows.csv"
SUPERLEVEL_NAME = "v0472_iteration_resolved_superlevels.csv"
MATRIX_NAME = "v0472_iteration_resolved_condensed_matrix.csv"
FIXED_NAME = "v0472_iteration_resolved_fixed_rows.csv"
REPORT_NAME = "iteration_resolved_capture_report.json"
VERIFY_NAME = "iteration_resolved_capture_verification.json"
BUNDLE_MANIFEST_NAME = "iteration_resolved_capture_manifest.json"

_PROBE = base._PROBE
_PROBE = _PROBE.replace(
    '"linear_solve_trace_current": [], "final_counter": 0}',
    '"linear_solve_trace_current": [], "iteration_manifest": [], '
    '"iteration_outer_rows": [], "iteration_superlevels": [], '
    '"iteration_condensed_matrix": [], "iteration_fixed_rows": [], "final_counter": 0}',
    1,
)

_FIELDS_AND_CAPTURE = r'''
from xstar_tools.xstar import element_equilibrium as _v213_eq

ITERATION_MANIFEST_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","n_rows","n_superlevels",
 "normalization_row","max_outer_iterations","max_fixed_iterations","lucy_tolerance",
 "fixed_point_tolerance","outer_iterations","total_fixed_point_iterations",
 "outer_trace_records","fixed_trace_records","converged"
]
ITERATION_OUTER_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","outer_iteration",
 "compact_row","superlevel","ion","outer_start_population","row_fraction",
 "population_after_condensed","population_after_fixed_point","fixed_iterations_this_outer",
 "total_fixed_iterations_after_outer","fixed_difference","outer_difference",
 "fixed_termination_reason","outer_termination_reason"
]
ITERATION_SUPERLEVEL_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","outer_iteration",
 "superlevel","population_before_condensed_solve","condensed_rhs","first_lu_solution",
 "refinement_residual","refinement_correction","refined_superlevel_solution"
]
ITERATION_MATRIX_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","outer_iteration",
 "row_superlevel","column_superlevel","normalized_matrix_value"
]
ITERATION_FIXED_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","outer_iteration",
 "fixed_iteration","global_fixed_iteration","compact_row","superlevel","ion",
 "population_before","riu","rui","ril","rli","population_after","fixed_difference",
 "termination_reason"
]

def _v048746214_targets():
    values = _CONFIG.get("targets", ["1:1", "6:1", "1:2", "1:12"])
    out = set()
    for value in values:
        seq, z = str(value).split(":", 1)
        out.add((int(seq), int(z)))
    return out

def _v048746214_fixed_reason(diff, iteration, maximum, tolerance):
    if float(diff) >= 1.0e3: return "divergence_guard"
    if float(diff) < float(tolerance): return "tolerance"
    if int(iteration) >= int(maximum): return "max_iterations"
    return "continue"

def _v048746214_outer_reason(diff, iteration, maximum, tolerance):
    if float(diff) <= float(tolerance): return "tolerance"
    if int(iteration) >= int(maximum): return "max_iterations"
    return "continue"

def _v048746214_capture_iteration_trajectories(kind, call_id, evaluation_index, sequence, result):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    targets = _v048746214_targets()
    for item in tuple(getattr(result, "element_results", ()) or ()):
        request = getattr(item, "request", None)
        z = int(_field(request, "element_z") or 0)
        if (int(sequence), z) not in targets:
            continue
        eq = getattr(item, "equilibrium", None)
        assembly = getattr(eq, "assembly", None)
        solve = getattr(eq, "solve", None)
        trace = getattr(solve, "trace", None)
        if assembly is None or solve is None or trace is None:
            raise RuntimeError(f"missing source iteration trace sequence={sequence} element={z}")
        basis = assembly.basis
        n = int(basis.n_rows)
        nsp = int(basis.n_superlevels)
        rows = tuple(basis.rows)
        nsup = np.asarray(basis.nsup[1:n+1], dtype=np.int32)
        nion = np.asarray(basis.nion[1:n+1], dtype=np.int32)
        max_outer = int(getattr(solve, "_v048746214_max_lucy_iterations", 0) or 0)
        max_fixed = int(getattr(solve, "_v048746214_max_fixed_point_iterations", 0) or 0)
        lucy_tol = float(getattr(solve, "_v048746214_lucy_tolerance", 0.0) or 0.0)
        fixed_tol = float(getattr(solve, "_v048746214_fixed_point_tolerance", 0.0) or 0.0)
        linear_traces = list(getattr(solve, "_v048746213_linear_solve_traces", ()) or ())
        outer_iterations = int(solve.outer_iterations)
        total_fixed = int(solve.fixed_point_iterations)
        if len(linear_traces) != outer_iterations:
            raise RuntimeError(
                f"source linear trace count mismatch sequence={sequence} element={z} "
                f"count={len(linear_traces)} expected={outer_iterations}"
            )
        outer_trace_records = 0
        fixed_trace_records = 0
        _STATE["iteration_manifest"].append({
          "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
          "evaluation_index": int(evaluation_index), "element_z": z,
          "n_rows": n, "n_superlevels": nsp, "normalization_row": int(basis.normalization_row),
          "max_outer_iterations": max_outer, "max_fixed_iterations": max_fixed,
          "lucy_tolerance": lucy_tol, "fixed_point_tolerance": fixed_tol,
          "outer_iterations": outer_iterations, "total_fixed_point_iterations": total_fixed,
          "outer_trace_records": outer_iterations, "fixed_trace_records": total_fixed,
          "converged": int(bool(solve.converged)),
        })
        for outer in range(1, outer_iterations + 1):
            outer_rows = sorted(
                (row for row in trace.outer_level_rows if int(row["outer_iteration"]) == outer),
                key=lambda row: int(row["compact_index"]),
            )
            super_rows = sorted(
                (row for row in trace.superlevel_rows if int(row["outer_iteration"]) == outer),
                key=lambda row: int(row["superlevel"]),
            )
            matrix_rows = sorted(
                (row for row in trace.condensed_matrix_rows if int(row["outer_iteration"]) == outer),
                key=lambda row: (int(row["row_superlevel"]), int(row["column_superlevel"])),
            )
            fixed_rows = sorted(
                (row for row in trace.fixed_point_rows if int(row["outer_iteration"]) == outer),
                key=lambda row: (int(row["fixed_iteration"]), int(row["compact_index"])),
            )
            if len(outer_rows) != n or len(super_rows) != nsp or len(matrix_rows) != nsp*nsp:
                raise RuntimeError(
                    f"incomplete source outer trace sequence={sequence} element={z} outer={outer} "
                    f"rows={len(outer_rows)}/{n} superlevels={len(super_rows)}/{nsp} "
                    f"matrix={len(matrix_rows)}/{nsp*nsp}"
                )
            fixed_iterations = max((int(row["fixed_iteration"]) for row in fixed_rows), default=0)
            if len(fixed_rows) != fixed_iterations * n:
                raise RuntimeError(
                    f"incomplete source fixed trace sequence={sequence} element={z} outer={outer} "
                    f"rows={len(fixed_rows)} expected={fixed_iterations*n}"
                )
            start = np.asarray([float(row["population_outer_start"]) for row in outer_rows], dtype=float)
            after = np.asarray([float(row["population_after_fixed_point"]) for row in outer_rows], dtype=float)
            outer_diff = float(_v213_eq._source_outer_difference(start, after, epsilon=1.0e-6))
            fixed_diff = float(outer_rows[0]["fixed_difference"])
            global_fixed = max((int(row["global_fixed_iteration"]) for row in fixed_rows), default=0)
            fixed_reason = _v048746214_fixed_reason(fixed_diff, fixed_iterations, max_fixed, fixed_tol)
            outer_reason = _v048746214_outer_reason(outer_diff, outer, max_outer, lucy_tol)
            for index, row in enumerate(outer_rows):
                _STATE["iteration_outer_rows"].append({
                  "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
                  "evaluation_index": int(evaluation_index), "element_z": z,
                  "outer_iteration": outer, "compact_row": index + 1,
                  "superlevel": int(nsup[index]), "ion": int(nion[index]),
                  "outer_start_population": float(row["population_outer_start"]),
                  "row_fraction": float(row["rr"]),
                  "population_after_condensed": float(row["population_after_condensed"]),
                  "population_after_fixed_point": float(row["population_after_fixed_point"]),
                  "fixed_iterations_this_outer": fixed_iterations,
                  "total_fixed_iterations_after_outer": global_fixed,
                  "fixed_difference": fixed_diff, "outer_difference": outer_diff,
                  "fixed_termination_reason": fixed_reason,
                  "outer_termination_reason": outer_reason,
                })
            linear = linear_traces[outer - 1]
            first = np.asarray(linear["first_lu_solution"], dtype=float)
            residual = np.asarray(linear["refinement_residual"], dtype=float)
            correction = np.asarray(linear["refinement_correction"], dtype=float)
            refined = np.asarray(linear["refined_solution"], dtype=float)
            lrhs = np.asarray(linear["rhs"], dtype=float)
            if any(arr.size != nsp for arr in (first, residual, correction, refined, lrhs)):
                raise RuntimeError(f"source linear dimension mismatch sequence={sequence} element={z} outer={outer}")
            for index, row in enumerate(super_rows):
                _STATE["iteration_superlevels"].append({
                  "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
                  "evaluation_index": int(evaluation_index), "element_z": z,
                  "outer_iteration": outer, "superlevel": index + 1,
                  "population_before_condensed_solve": float(row["population_before_condensed_solve"]),
                  "condensed_rhs": float(lrhs[index]), "first_lu_solution": float(first[index]),
                  "refinement_residual": float(residual[index]),
                  "refinement_correction": float(correction[index]),
                  "refined_superlevel_solution": float(refined[index]),
                })
            for row in matrix_rows:
                _STATE["iteration_condensed_matrix"].append({
                  "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
                  "evaluation_index": int(evaluation_index), "element_z": z,
                  "outer_iteration": outer, "row_superlevel": int(row["row_superlevel"]),
                  "column_superlevel": int(row["column_superlevel"]),
                  "normalized_matrix_value": float(row["normalized_matrix_value"]),
                })
            for row in fixed_rows:
                fixed_iteration = int(row["fixed_iteration"])
                diff = float(row["fixed_difference"])
                reason = _v048746214_fixed_reason(diff, fixed_iteration, max_fixed, fixed_tol)
                _STATE["iteration_fixed_rows"].append({
                  "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
                  "evaluation_index": int(evaluation_index), "element_z": z,
                  "outer_iteration": outer, "fixed_iteration": fixed_iteration,
                  "global_fixed_iteration": int(row["global_fixed_iteration"]),
                  "compact_row": int(row["compact_index"]),
                  "superlevel": int(row["superlevel"]), "ion": int(row["ion_counter"]),
                  "population_before": float(row["population_before"]), "riu": float(row["riu"]),
                  "rui": float(row["rui"]), "ril": float(row["ril"]), "rli": float(row["rli"]),
                  "population_after": float(row["population_after"]), "fixed_difference": diff,
                  "termination_reason": reason,
                })
'''
_PROBE = _PROBE.replace("ALL61_INPUT_FIELDS = [", _FIELDS_AND_CAPTURE + "\nALL61_INPUT_FIELDS = [", 1)
_PROBE = _PROBE.replace(
    '    _v048746213_capture_solve_stages(kind, call_id, evaluation_index, sequence, result)\n',
    '    _v048746213_capture_solve_stages(kind, call_id, evaluation_index, sequence, result)\n'
    '    _v048746214_capture_iteration_trajectories(kind, call_id, evaluation_index, sequence, result)\n',
    1,
)
_PROBE = _PROBE.replace(
    '      "v0472_all61_solve_stage_manifest.csv": lambda row: (int(row["sequence"]), int(row["element_z"])),\n',
    '      "v0472_all61_solve_stage_manifest.csv": lambda row: (int(row["sequence"]), int(row["element_z"])),\n'
    '      "v0472_iteration_resolved_manifest.csv": lambda row: (int(row["sequence"]), int(row["element_z"])),\n'
    '      "v0472_iteration_resolved_outer_rows.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["outer_iteration"]), int(row["compact_row"])),\n'
    '      "v0472_iteration_resolved_superlevels.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["outer_iteration"]), int(row["superlevel"])),\n'
    '      "v0472_iteration_resolved_condensed_matrix.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["outer_iteration"]), int(row["row_superlevel"]), int(row["column_superlevel"])),\n'
    '      "v0472_iteration_resolved_fixed_rows.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["outer_iteration"]), int(row["fixed_iteration"]), int(row["compact_row"])),\n',
    1,
)
_PROBE = _PROBE.replace(
    '      ("v0472_all61_solve_stage_manifest.csv", ALL61_SOLVE_STAGE_MANIFEST_FIELDS, _STATE["all61_solve_stage_manifest"]),\n',
    '      ("v0472_all61_solve_stage_manifest.csv", ALL61_SOLVE_STAGE_MANIFEST_FIELDS, _STATE["all61_solve_stage_manifest"]),\n'
    '      ("v0472_iteration_resolved_manifest.csv", ITERATION_MANIFEST_FIELDS, _STATE["iteration_manifest"]),\n'
    '      ("v0472_iteration_resolved_outer_rows.csv", ITERATION_OUTER_FIELDS, _STATE["iteration_outer_rows"]),\n'
    '      ("v0472_iteration_resolved_superlevels.csv", ITERATION_SUPERLEVEL_FIELDS, _STATE["iteration_superlevels"]),\n'
    '      ("v0472_iteration_resolved_condensed_matrix.csv", ITERATION_MATRIX_FIELDS, _STATE["iteration_condensed_matrix"]),\n'
    '      ("v0472_iteration_resolved_fixed_rows.csv", ITERATION_FIXED_FIELDS, _STATE["iteration_fixed_rows"]),\n',
    1,
)
# Attach exact source context settings to each solve result.
_PROBE = _PROBE.replace(
    '        result._v048746213_linear_solve_traces = list(_STATE["linear_solve_trace_current"])\n        return result\n',
    '        result._v048746213_linear_solve_traces = list(_STATE["linear_solve_trace_current"])\n'
    '        result._v048746214_max_lucy_iterations = int(context.max_lucy_iterations)\n'
    '        result._v048746214_max_fixed_point_iterations = int(context.max_fixed_point_iterations)\n'
    '        result._v048746214_lucy_tolerance = float(context.lucy_tolerance)\n'
    '        result._v048746214_fixed_point_tolerance = float(context.fixed_point_tolerance)\n'
    '        return result\n',
    1,
)
_PROBE = _PROBE.replace(
    '"schema": "xstar-tools-v06487462131-v0472-all61-solve-stage-capture-v1", "release": "0.6.48.7.46.21.5",',
    f'"schema": "{SCHEMA}", "release": "{RELEASE}",',
    1,
)
_DRIVER = base._DRIVER.replace(
    "import v048746213_solve_stage_probe_runtime as probe",
    "import v048746214_iteration_trajectory_probe_runtime as probe",
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _target_strings(targets: tuple[tuple[int, int], ...]) -> list[str]:
    return [f"{sequence}:{z}" for sequence, z in targets]


def verify(bundle: Path, targets: tuple[tuple[int, int], ...] = DEFAULT_TARGETS) -> dict[str, Any]:
    bundle = bundle.resolve()
    errors: list[str] = []
    required = (MANIFEST_NAME, OUTER_NAME, SUPERLEVEL_NAME, MATRIX_NAME, FIXED_NAME, REPORT_NAME)
    for name in required:
        if not (bundle / name).is_file():
            errors.append(f"missing:{name}")
    if errors:
        return {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": errors,
                "qualification_only": True, "production_promotion_ready": False}
    manifest = _read_csv(bundle / MANIFEST_NAME)
    outer = _read_csv(bundle / OUTER_NAME)
    superlevels = _read_csv(bundle / SUPERLEVEL_NAME)
    matrix = _read_csv(bundle / MATRIX_NAME)
    fixed = _read_csv(bundle / FIXED_NAME)
    target_set = set(targets)
    systems = {(int(row["sequence"]), int(row["element_z"])) for row in manifest}
    if systems != target_set or len(manifest) != len(target_set):
        errors.append(f"target_system_inventory={sorted(systems)} expected={sorted(target_set)}")
    expected_outer = sum(int(row["n_rows"]) * int(row["outer_iterations"]) for row in manifest)
    expected_super = sum(int(row["n_superlevels"]) * int(row["outer_iterations"]) for row in manifest)
    expected_matrix = sum(int(row["n_superlevels"]) ** 2 * int(row["outer_iterations"]) for row in manifest)
    expected_fixed = sum(int(row["n_rows"]) * int(row["total_fixed_point_iterations"]) for row in manifest)
    if len(outer) != expected_outer: errors.append(f"outer_rows={len(outer)} expected={expected_outer}")
    if len(superlevels) != expected_super: errors.append(f"superlevel_rows={len(superlevels)} expected={expected_super}")
    if len(matrix) != expected_matrix: errors.append(f"matrix_rows={len(matrix)} expected={expected_matrix}")
    if len(fixed) != expected_fixed: errors.append(f"fixed_rows={len(fixed)} expected={expected_fixed}")
    report = json.loads((bundle / REPORT_NAME).read_text())
    if not report.get("actual_v0472_runtime_capture"):
        errors.append("not_actual_v0472_runtime_capture")
    return {
        "schema": VERIFY_SCHEMA, "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT", "errors": errors,
        "actual_v0472_runtime_capture": bool(report.get("actual_v0472_runtime_capture")),
        "target_systems": len(manifest), "targets": _target_strings(targets),
        "outer_rows": len(outer), "superlevel_rows": len(superlevels),
        "condensed_matrix_values": len(matrix), "fixed_rows": len(fixed),
        "qualification_only": True, "production_promotion_ready": False,
    }


def capture(source_archive: Path, atdb_path: Path, output_dir: Path, parameters_json: Path,
            coheat_path: Path | None, targets: tuple[tuple[int, int], ...] = DEFAULT_TARGETS) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if base.base.base.base._sha256(source_archive) != base.base.base.base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v048746214_source_") as tmp:
        tmp_path = Path(tmp)
        base.base.base.base._safe_extract(source_archive, tmp_path / "source")
        root = base.base.base.base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        (probe_dir / "v048746214_iteration_trajectory_probe_runtime.py").write_text(_PROBE)
        (probe_dir / "probe_config.json").write_text(json.dumps({
            "output_dir": str(output_dir), "targets": _target_strings(targets)}, indent=2))
        (probe_dir / "driver.py").write_text(_DRIVER)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(probe_dir), str(root / "src")])
        env.update({"PYTHONFAULTHANDLER": "1", "PYTHONUNBUFFERED": "1", "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
        cmd = [sys.executable, str(probe_dir / "driver.py"), "--parameters-json", str(parameters_json.resolve()),
               "--atdb-path", str(atdb_path.resolve()), "--output-dir", str(output_dir / "physical_run")]
        if coheat_path is not None:
            cmd += ["--coheat-path", str(coheat_path.resolve())]
        log = output_dir / "v0472_iteration_resolved_capture_run.log"
        with log.open("w") as handle:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 iteration capture failed with exit {completed.returncode}; see {log}")
    historical = output_dir / "capture_report.json"
    if historical.is_file():
        historical.replace(output_dir / REPORT_NAME)
    result = verify(output_dir, targets)
    _write_json(output_dir / VERIFY_NAME, result)
    files: dict[str, Any] = {}
    for name in (*required_names(), VERIFY_NAME):
        path = output_dir / name
        files[name] = {"sha256": base.base.base.base._sha256(path), "size_bytes": path.stat().st_size}
    _write_json(output_dir / BUNDLE_MANIFEST_NAME, {**result, "immutable": result["result"] == "ACCEPT", "files": files})
    return result


def required_names() -> tuple[str, ...]:
    return (MANIFEST_NAME, OUTER_NAME, SUPERLEVEL_NAME, MATRIX_NAME, FIXED_NAME, REPORT_NAME)


def _parse_targets(values: list[str] | None) -> tuple[tuple[int, int], ...]:
    if not values:
        return DEFAULT_TARGETS
    result = []
    for value in values:
        sequence, z = value.split(":", 1)
        result.append((int(sequence), int(z)))
    return tuple(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("source_archive", type=Path)
    cap.add_argument("atdb_path", type=Path)
    cap.add_argument("output_dir", type=Path)
    cap.add_argument("parameters_json", type=Path)
    cap.add_argument("--coheat-path", type=Path)
    cap.add_argument("--target", action="append")
    cap.add_argument("--output-json", type=Path)
    ver = sub.add_parser("verify")
    ver.add_argument("bundle", type=Path)
    ver.add_argument("--target", action="append")
    ver.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    targets = _parse_targets(args.target)
    try:
        result = capture(args.source_archive, args.atdb_path, args.output_dir, args.parameters_json,
                         args.coheat_path, targets) if args.command == "capture" else verify(args.bundle, targets)
    except Exception as exc:
        result = {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "qualification_only": True, "production_promotion_ready": False}
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
