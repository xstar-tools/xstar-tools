"""Capture all-61 v0.6.47.2 compact-population solve stages for v21.3.1.

This qualification-only probe is observational.  It enables the existing Lucy
iteration trace, records the final outer iteration, and reconstructs the
source-order ``ludcmp``/``lubksb``/``mprove`` intermediates without replacing
the source solver result.
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

from . import v0472_all61_fixed_state_capture as base

RELEASE = "0.6.48.7.46.21.5"
SCHEMA = "xstar-tools-v06487462131-v0472-all61-solve-stage-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v06487462131-v0472-all61-solve-stage-oracle-v1"
ROW_NAME = "v0472_all61_solve_stage_rows.csv"
SUPERLEVEL_NAME = "v0472_all61_solve_stage_superlevels.csv"
MATRIX_NAME = "v0472_all61_solve_stage_condensed_matrix.csv"
MANIFEST_NAME = "v0472_all61_solve_stage_manifest.csv"
REPORT_NAME = "all61_solve_stage_capture_report.json"
VERIFY_NAME = "all61_solve_stage_capture_verification.json"
BUNDLE_MANIFEST_NAME = "all61_solve_stage_capture_manifest.json"

_PROBE = base._PROBE
_PROBE = _PROBE.replace(
    '"all61_solve_rows": [], "final_counter": 0}',
    '"all61_solve_rows": [], "all61_solve_stage_rows": [], '
    '"all61_solve_stage_superlevels": [], "all61_solve_stage_condensed_matrix": [], '
    '"all61_solve_stage_manifest": [], "linear_solve_trace_current": [], "final_counter": 0}',
)

_STAGE_FIELDS = r'''
ALL61_SOLVE_STAGE_ROW_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","active_min_stage","active_max_stage",
 "compact_row","superlevel","ion","ion_stage","ion_charge","is_normalization_row",
 "transformed_initial_population","final_outer_start_population","population_after_condensed",
 "final_fixed_point_population_before","final_fixed_point_population_after","final_population","rhs"
]
ALL61_SOLVE_STAGE_SUPERLEVEL_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","final_outer_iteration","superlevel",
 "population_before_condensed_solve","condensed_rhs","first_lu_solution","refinement_residual",
 "refinement_correction","refined_superlevel_solution"
]
ALL61_SOLVE_STAGE_MATRIX_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","final_outer_iteration",
 "row_superlevel","column_superlevel","normalized_matrix_value"
]
ALL61_SOLVE_STAGE_MANIFEST_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","active_min_stage","active_max_stage",
 "n_rows","n_superlevels","n_ions","normalization_row","final_outer_iteration",
 "final_fixed_iterations","total_fixed_point_iterations","solver_method","converged"
]

def _v048746213_capture_solve_stages(kind, call_id, evaluation_index, sequence, result):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    for item in tuple(getattr(result, "element_results", ()) or ()):
        request = getattr(item, "request", None)
        z = int(_field(request, "element_z") or 0)
        if z not in (1, 2, 12):
            continue
        eq = getattr(item, "equilibrium", None)
        assembly = getattr(eq, "assembly", None)
        solve = getattr(eq, "solve", None)
        if assembly is None or solve is None or getattr(solve, "trace", None) is None:
            continue
        basis = assembly.basis
        n = int(basis.n_rows)
        nsp = int(basis.n_superlevels)
        rows = tuple(basis.rows)
        ion_stages = np.asarray(basis.ion_stage, dtype=np.int32)
        initial = np.asarray(assembly.initial_populations[1:n+1], dtype=float)
        final = np.asarray(solve.populations, dtype=float)
        rhs = np.asarray(assembly.rhs, dtype=float)
        final_outer = int(solve.outer_iterations)
        outer_rows = {
          int(row["compact_index"]): row for row in solve.trace.outer_level_rows
          if int(row["outer_iteration"]) == final_outer
        }
        super_rows = {
          int(row["superlevel"]): row for row in solve.trace.superlevel_rows
          if int(row["outer_iteration"]) == final_outer
        }
        matrix_rows = [row for row in solve.trace.condensed_matrix_rows
                       if int(row["outer_iteration"]) == final_outer]
        fixed_rows = [row for row in solve.trace.fixed_point_rows
                      if int(row["outer_iteration"]) == final_outer]
        final_fixed_iteration = max((int(row["fixed_iteration"]) for row in fixed_rows), default=0)
        fixed_final = {int(row["compact_index"]): row for row in fixed_rows
                       if int(row["fixed_iteration"]) == final_fixed_iteration}
        linear_traces = list(getattr(solve, "_v048746213_linear_solve_traces", ()) or ())
        linear = linear_traces[final_outer - 1] if 1 <= final_outer <= len(linear_traces) else None
        if len(outer_rows) != n or len(super_rows) != nsp or len(matrix_rows) != nsp*nsp or linear is None:
            raise RuntimeError(
              f"incomplete source solve-stage trace sequence={sequence} element={z} "
              f"rows={len(outer_rows)}/{n} superlevels={len(super_rows)}/{nsp} "
              f"matrix={len(matrix_rows)}/{nsp*nsp} linear={linear is not None}"
            )
        active_stages = [int(ion_stages[i]) for i in range(1, min(n + 1, ion_stages.size))]
        active_min = min(active_stages) if active_stages else 0
        active_max = max(active_stages) if active_stages else 0
        _STATE["all61_solve_stage_manifest"].append({
          "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
          "evaluation_index": int(evaluation_index), "element_z": z,
          "active_min_stage": active_min, "active_max_stage": active_max,
          "n_rows": n, "n_superlevels": nsp, "n_ions": int(basis.n_ions),
          "normalization_row": int(basis.normalization_row), "final_outer_iteration": final_outer,
          "final_fixed_iterations": final_fixed_iteration,
          "total_fixed_point_iterations": int(solve.fixed_point_iterations),
          "solver_method": str(solve.solver_method), "converged": int(bool(solve.converged)),
        })
        for i in range(n):
            meta = rows[i]
            stage = int(ion_stages[i + 1]) if i + 1 < ion_stages.size else 0
            outer_row = outer_rows[i + 1]
            fixed_row = fixed_final.get(i + 1)
            fixed_before = float(fixed_row["population_before"]) if fixed_row else float(outer_row["population_after_condensed"])
            fixed_after = float(fixed_row["population_after"]) if fixed_row else float(outer_row["population_after_fixed_point"])
            _STATE["all61_solve_stage_rows"].append({
              "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
              "evaluation_index": int(evaluation_index), "element_z": z,
              "active_min_stage": active_min, "active_max_stage": active_max,
              "compact_row": i + 1, "superlevel": int(meta.superlevel),
              "ion": int(meta.ion_counter), "ion_stage": stage, "ion_charge": max(0, stage - 1),
              "is_normalization_row": 1 if i + 1 == int(basis.normalization_row) else 0,
              "transformed_initial_population": float(initial[i]),
              "final_outer_start_population": float(outer_row["population_outer_start"]),
              "population_after_condensed": float(outer_row["population_after_condensed"]),
              "final_fixed_point_population_before": fixed_before,
              "final_fixed_point_population_after": fixed_after,
              "final_population": float(final[i]), "rhs": float(rhs[i]),
            })
        first = np.asarray(linear["first_lu_solution"], dtype=float)
        lres = np.asarray(linear["refinement_residual"], dtype=float)
        corr = np.asarray(linear["refinement_correction"], dtype=float)
        refined = np.asarray(linear["refined_solution"], dtype=float)
        lrhs = np.asarray(linear["rhs"], dtype=float)
        if any(arr.size != nsp for arr in (first, lres, corr, refined, lrhs)):
            raise RuntimeError(f"source linear trace dimension mismatch sequence={sequence} element={z}")
        for sp in range(1, nsp + 1):
            source_row = super_rows[sp]
            _STATE["all61_solve_stage_superlevels"].append({
              "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
              "evaluation_index": int(evaluation_index), "element_z": z,
              "final_outer_iteration": final_outer, "superlevel": sp,
              "population_before_condensed_solve": float(source_row["population_before_condensed_solve"]),
              "condensed_rhs": float(lrhs[sp-1]), "first_lu_solution": float(first[sp-1]),
              "refinement_residual": float(lres[sp-1]), "refinement_correction": float(corr[sp-1]),
              "refined_superlevel_solution": float(refined[sp-1]),
            })
        for row in matrix_rows:
            _STATE["all61_solve_stage_condensed_matrix"].append({
              "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
              "evaluation_index": int(evaluation_index), "element_z": z,
              "final_outer_iteration": final_outer,
              "row_superlevel": int(row["row_superlevel"]),
              "column_superlevel": int(row["column_superlevel"]),
              "normalized_matrix_value": float(row["normalized_matrix_value"]),
            })
'''
_PROBE = _PROBE.replace("ALL61_INPUT_FIELDS = [", _STAGE_FIELDS + "\nALL61_INPUT_FIELDS = [", 1)

# Run the stage capture after the ordinary fixed-state row capture.
_PROBE = _PROBE.replace(
    '    _v048744_capture_solve_rows(kind, call_id, evaluation_index, sequence, result)\n',
    '    _v048744_capture_solve_rows(kind, call_id, evaluation_index, sequence, result)\n'
    '    _v048746213_capture_solve_stages(kind, call_id, evaluation_index, sequence, result)\n',
    1,
)

# Add stage tables to the generated writer.
_PROBE = _PROBE.replace(
    '      "v0472_all61_element_solve_rows.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["compact_row"])),\n',
    '      "v0472_all61_element_solve_rows.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["compact_row"])),\n'
    '      "v0472_all61_solve_stage_rows.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["compact_row"])),\n'
    '      "v0472_all61_solve_stage_superlevels.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["superlevel"])),\n'
    '      "v0472_all61_solve_stage_condensed_matrix.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["row_superlevel"]), int(row["column_superlevel"])),\n'
    '      "v0472_all61_solve_stage_manifest.csv": lambda row: (int(row["sequence"]), int(row["element_z"])),\n',
    1,
)
_PROBE = _PROBE.replace(
    '      ("v0472_all61_element_solve_rows.csv", ALL61_SOLVE_FIELDS, _STATE["all61_solve_rows"]),\n',
    '      ("v0472_all61_element_solve_rows.csv", ALL61_SOLVE_FIELDS, _STATE["all61_solve_rows"]),\n'
    '      ("v0472_all61_solve_stage_rows.csv", ALL61_SOLVE_STAGE_ROW_FIELDS, _STATE["all61_solve_stage_rows"]),\n'
    '      ("v0472_all61_solve_stage_superlevels.csv", ALL61_SOLVE_STAGE_SUPERLEVEL_FIELDS, _STATE["all61_solve_stage_superlevels"]),\n'
    '      ("v0472_all61_solve_stage_condensed_matrix.csv", ALL61_SOLVE_STAGE_MATRIX_FIELDS, _STATE["all61_solve_stage_condensed_matrix"]),\n'
    '      ("v0472_all61_solve_stage_manifest.csv", ALL61_SOLVE_STAGE_MANIFEST_FIELDS, _STATE["all61_solve_stage_manifest"]),\n',
    1,
)

_INSTALL_TRACE = r'''
    from xstar_tools.xstar import element_equilibrium as _v213_eq
    from xstar_tools.xstar import linear_algebra as _v213_la
    _v213_original_solve_normalized = _v213_eq._solve_normalized
    _v213_original_msolvelucy = _v213_eq.msolvelucy

    def _v213_traced_solve_normalized(matrix, normalization_row, *, allow_lstsq, compute_rank=True):
        a = np.asarray(matrix, dtype=float).copy()
        n = int(a.shape[0])
        b = np.zeros(n, dtype=float)
        row = int(normalization_row) - 1
        a[row, :] = 1.0
        b[row] = 1.0
        decomp = _v213_la.ludcmp(a)
        if decomp.singular_rows:
            return _v213_original_solve_normalized(
                matrix, normalization_row, allow_lstsq=allow_lstsq, compute_rank=compute_rank)
        first = _v213_la.lubksb(decomp, b)
        residual = np.zeros(n, dtype=float)
        for i in range(n):
            total = -float(b[i])
            for j in range(n):
                total = total + float(a[i, j]) * float(first[j])
            residual[i] = total
        correction = _v213_la.lubksb(decomp, residual)
        refined = first.copy()
        for i in range(n):
            refined[i] = float(refined[i]) - float(correction[i])
        result = _v213_original_solve_normalized(
            matrix, normalization_row, allow_lstsq=allow_lstsq, compute_rank=compute_rank)
        _STATE["linear_solve_trace_current"].append({
          "rhs": b.copy(), "first_lu_solution": first.copy(),
          "refinement_residual": residual.copy(), "refinement_correction": correction.copy(),
          "refined_solution": refined.copy(),
        })
        return result

    def _v213_traced_msolvelucy(assembly, context):
        previous_trace = bool(getattr(context, "capture_lucy_trace", False))
        context.capture_lucy_trace = True
        _STATE["linear_solve_trace_current"] = []
        try:
            result = _v213_original_msolvelucy(assembly, context)
        finally:
            context.capture_lucy_trace = previous_trace
        result._v048746213_linear_solve_traces = list(_STATE["linear_solve_trace_current"])
        return result

    _v213_eq._solve_normalized = _v213_traced_solve_normalized
    _v213_eq.msolvelucy = _v213_traced_msolvelucy
'''
_PROBE = _PROBE.replace(
    '    from xstar_tools.xstar import dsec as dsec_mod\n    original = dsec_mod.CalcHMCAllDsecEvaluator.__call__\n',
    '    from xstar_tools.xstar import dsec as dsec_mod\n' + _INSTALL_TRACE +
    '    original = dsec_mod.CalcHMCAllDsecEvaluator.__call__\n',
    1,
)
_PROBE = _PROBE.replace('"schema": "xstar-tools-v0648744-v0472-all61-fixed-state-capture-v1"', f'"schema": "{SCHEMA}"')

_DRIVER = base._DRIVER.replace("import v048744_all61_probe_runtime as probe", "import v048746213_solve_stage_probe_runtime as probe")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def verify(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    errors: list[str] = []
    required = (ROW_NAME, SUPERLEVEL_NAME, MATRIX_NAME, MANIFEST_NAME, REPORT_NAME)
    for name in required:
        if not (bundle / name).is_file():
            errors.append(f"missing:{name}")
    if errors:
        return {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": errors,
                "qualification_only": True, "production_promotion_ready": False}
    rows = _read_csv(bundle / ROW_NAME)
    superlevels = _read_csv(bundle / SUPERLEVEL_NAME)
    matrix = _read_csv(bundle / MATRIX_NAME)
    manifest = _read_csv(bundle / MANIFEST_NAME)
    systems = {(int(r["sequence"]), int(r["element_z"])) for r in manifest}
    if len(manifest) != 183 or systems != {(s, z) for s in range(1, 62) for z in (1, 2, 12)}:
        errors.append(f"system_inventory={len(manifest)}")
    if len(rows) != 40149:
        errors.append(f"row_inventory={len(rows)} expected=40149")
    if {(int(r["sequence"]), int(r["element_z"])) for r in rows} != systems:
        errors.append("row_system_inventory")
    expected_super = sum(int(r["n_superlevels"]) for r in manifest)
    expected_matrix = sum(int(r["n_superlevels"]) ** 2 for r in manifest)
    if len(superlevels) != expected_super:
        errors.append(f"superlevel_inventory={len(superlevels)} expected={expected_super}")
    if len(matrix) != expected_matrix:
        errors.append(f"matrix_inventory={len(matrix)} expected={expected_matrix}")
    if any(int(r["final_outer_iteration"]) <= 0 or int(r["total_fixed_point_iterations"]) <= 0 for r in manifest):
        errors.append("invalid_iteration_inventory")
    report = json.loads((bundle / REPORT_NAME).read_text())
    if not report.get("actual_v0472_runtime_capture"):
        errors.append("not_actual_v0472_runtime_capture")
    return {
        "schema": VERIFY_SCHEMA, "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT", "errors": errors,
        "actual_v0472_runtime_capture": bool(report.get("actual_v0472_runtime_capture")),
        "evaluations": len({int(r["sequence"]) for r in manifest}), "systems": len(manifest),
        "solve_stage_rows": len(rows), "solve_stage_superlevels": len(superlevels),
        "solve_stage_condensed_matrix_values": len(matrix),
        "qualification_only": True, "production_promotion_ready": False,
    }


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if base.base.base._sha256(source_archive) != base.base.base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v048746213_source_") as tmp:
        tmp_path = Path(tmp)
        base.base.base._safe_extract(source_archive, tmp_path / "source")
        root = base.base.base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        (probe_dir / "v048746213_solve_stage_probe_runtime.py").write_text(_PROBE)
        (probe_dir / "probe_config.json").write_text(json.dumps({"output_dir": str(output_dir)}, indent=2))
        (probe_dir / "driver.py").write_text(_DRIVER)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(probe_dir), str(root / "src")])
        env.update({"PYTHONFAULTHANDLER": "1", "PYTHONUNBUFFERED": "1", "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
        cmd = [sys.executable, str(probe_dir / "driver.py"), "--parameters-json", str(parameters_json.resolve()),
               "--atdb-path", str(atdb_path.resolve()), "--output-dir", str(output_dir / "physical_run")]
        if coheat_path is not None:
            cmd += ["--coheat-path", str(coheat_path.resolve())]
        log = output_dir / "v0472_all61_solve_stage_capture_run.log"
        with log.open("w") as handle:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 solve-stage capture failed with exit {completed.returncode}; see {log}")
    historical = output_dir / "capture_report.json"
    if historical.is_file():
        historical.replace(output_dir / REPORT_NAME)
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    files: dict[str, Any] = {}
    for name in (ROW_NAME, SUPERLEVEL_NAME, MATRIX_NAME, MANIFEST_NAME, REPORT_NAME, VERIFY_NAME):
        path = output_dir / name
        files[name] = {"sha256": base.base.base._sha256(path), "size_bytes": path.stat().st_size}
    _write_json(output_dir / BUNDLE_MANIFEST_NAME, {**result, "immutable": result["result"] == "ACCEPT", "files": files})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("source_archive", type=Path)
    cap.add_argument("atdb_path", type=Path)
    cap.add_argument("output_dir", type=Path)
    cap.add_argument("parameters_json", type=Path)
    cap.add_argument("--coheat-path", type=Path)
    cap.add_argument("--output-json", type=Path)
    ver = sub.add_parser("verify")
    ver.add_argument("bundle", type=Path)
    ver.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = capture(args.source_archive, args.atdb_path, args.output_dir, args.parameters_json, args.coheat_path) \
            if args.command == "capture" else verify(args.bundle)
    except Exception as exc:
        result = {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "qualification_only": True, "production_promotion_ready": False}
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
