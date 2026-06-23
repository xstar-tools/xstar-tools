from __future__ import annotations

import csv
import json
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import xstar_tools.xstar as xstar_package

from xstar_tools.xstar import iteration_resolved_trajectory_parity_v048746215 as parity
from xstar_tools.xstar import v0472_iteration_resolved_trajectory_capture_v048746214 as source_capture

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ((1, 1), (6, 1), (1, 2), (1, 12))


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _records(sequence: int, z: int) -> tuple[dict[str, object], ...]:
    manifest = {
        "sequence": sequence,
        "element_z": z,
        "n_rows": 1,
        "n_superlevels": 1,
        "normalization_row": 1,
        "max_outer_iterations": 200,
        "max_fixed_iterations": 200,
        "lucy_tolerance": 1.0e-2,
        "fixed_point_tolerance": 1.0e-2,
        "outer_iterations": 1,
        "total_fixed_point_iterations": 1,
        "outer_trace_records": 1,
        "fixed_trace_records": 1,
        "trace_complete": 1,
    }
    outer = {
        "sequence": sequence,
        "element_z": z,
        "outer_iteration": 1,
        "compact_row": 1,
        "superlevel": 1,
        "ion": 5 if z == 12 else 1,
        "outer_start_population": 1.0,
        "row_fraction": 1.0,
        "population_after_condensed": 1.0,
        "population_after_fixed_point": 1.0,
        "fixed_iterations_this_outer": 1,
        "total_fixed_iterations_after_outer": 1,
        "fixed_difference": 0.0,
        "outer_difference": 0.0,
        "fixed_termination_reason": "tolerance",
        "outer_termination_reason": "tolerance",
    }
    superlevel = {
        "sequence": sequence,
        "element_z": z,
        "outer_iteration": 1,
        "superlevel": 1,
        "population_before_condensed_solve": 1.0,
        "condensed_rhs": 1.0,
        "first_lu_solution": 1.0,
        "refinement_residual": 0.0,
        "refinement_correction": 0.0,
        "refined_superlevel_solution": 1.0,
    }
    matrix = {
        "sequence": sequence,
        "element_z": z,
        "outer_iteration": 1,
        "row_superlevel": 1,
        "column_superlevel": 1,
        "normalized_matrix_value": 1.0,
    }
    fixed = {
        "sequence": sequence,
        "element_z": z,
        "outer_iteration": 1,
        "fixed_iteration": 1,
        "global_fixed_iteration": 1,
        "compact_row": 1,
        "superlevel": 1,
        "ion": 5 if z == 12 else 1,
        "population_before": 1.0,
        "riu": 0.0,
        "rui": 0.0,
        "ril": 0.0,
        "rli": 0.0,
        "population_after": 1.0,
        "fixed_difference": 0.0,
        "termination_reason": "tolerance",
    }
    return manifest, outer, superlevel, matrix, fixed


def _fixture(
    tmp_path: Path,
    *,
    control_mismatch: bool = False,
    h6_matrix_mismatch: bool = False,
) -> tuple[Path, Path]:
    source = tmp_path / "source"
    source_rows: dict[str, list[dict[str, object]]] = {
        "manifest": [], "outer": [], "super": [], "matrix": [], "fixed": []
    }
    native_root = tmp_path / "native"

    for sequence, z in TARGETS:
        manifest, outer, superlevel, matrix, fixed = _records(sequence, z)
        source_rows["manifest"].append(manifest)
        source_rows["outer"].append(outer)
        source_rows["super"].append(superlevel)
        source_rows["matrix"].append(matrix)
        source_rows["fixed"].append(fixed)

        native_manifest = dict(manifest)
        native_outer = dict(outer)
        native_superlevel = dict(superlevel)
        native_matrix = dict(matrix)
        native_fixed = dict(fixed)
        if z == 12:
            native_outer["ion"] = 1
            native_fixed["ion"] = 1
        if control_mismatch:
            native_manifest["max_outer_iterations"] = 100
            native_manifest["max_fixed_iterations"] = 40
            native_manifest["lucy_tolerance"] = 1.0e-12
            native_manifest["fixed_point_tolerance"] = 1.0e-11
        if h6_matrix_mismatch and (sequence, z) == (6, 1):
            native_matrix["normalized_matrix_value"] = 1.0000000000000002
            # Deliberately include downstream differences. Ranked attribution must
            # still report condensed_matrix as the first arithmetic divergence.
            native_outer["population_after_condensed"] = 1.0000000000000002
            native_fixed["population_before"] = 1.0000000000000002

        directory = native_root / f"evaluation_{sequence:04d}" / "iteration_trace"
        stem = f"sequence_{sequence:04d}_element_{z:02d}"
        _write(directory / f"{stem}{parity.NATIVE_SUFFIXES['manifest']}", [native_manifest])
        _write(directory / f"{stem}{parity.NATIVE_SUFFIXES['outer']}", [native_outer])
        _write(directory / f"{stem}{parity.NATIVE_SUFFIXES['super']}", [native_superlevel])
        _write(directory / f"{stem}{parity.NATIVE_SUFFIXES['matrix']}", [native_matrix])
        _write(directory / f"{stem}{parity.NATIVE_SUFFIXES['fixed']}", [native_fixed])

    for name, rows in source_rows.items():
        _write(source / parity.SOURCE_FILES[name], rows)
    (source / source_capture.REPORT_NAME).write_text(json.dumps({
        "result": "ACCEPT",
        "actual_v0472_runtime_capture": True,
    }))
    return source, native_root


def test_restored_contract_gates_are_exact_for_all_four_targets(tmp_path: Path) -> None:
    source, native = _fixture(tmp_path, h6_matrix_mismatch=True)
    result = parity.analyze(source, native, tmp_path / "out", TARGETS)
    gates = result["solver_control_gates"]
    for name in (
        "SOLVER_CONTROL_CONTRACT_EXACT",
        "MAX_OUTER_ITERATIONS_EXACT",
        "MAX_FIXED_ITERATIONS_EXACT",
        "LUCY_TOLERANCE_EXACT",
        "FIXED_POINT_TOLERANCE_EXACT",
    ):
        assert gates[name] == {"exact": 4, "total": 4, "accepted": True}
    assert result["milestone_result"] == "ACCEPT"
    assert result["scientific_result"] == "REJECT"
    assert result["systems_fully_exact"] == 3


def test_ranked_attribution_keeps_h6_condensed_matrix_first(tmp_path: Path) -> None:
    source, native = _fixture(tmp_path, h6_matrix_mismatch=True)
    out = tmp_path / "out"
    result = parity.analyze(source, native, out, TARGETS)
    assert result["first_divergence_stage"] == "condensed_matrix"
    assert result["first_divergence_sequence"] == 6
    assert result["first_divergence_element_z"] == 1
    assert result["first_divergence_outer_iteration"] == 1
    assert result["first_divergence_identity"] == "cell=1,1"
    systems = list(csv.DictReader((out / "v048746215_iteration_trajectory_system_comparison.csv").open()))
    exact = {(int(row["sequence"]), int(row["element_z"])) for row in systems if row["classification"] == "FULLY_EXACT"}
    assert exact == {(1, 1), (1, 2), (1, 12)}



def test_mg_physical_stage_maps_to_native_local_ordinal(tmp_path: Path) -> None:
    source, native = _fixture(tmp_path, h6_matrix_mismatch=True)
    result = parity.analyze(source, native, tmp_path / "out", TARGETS)
    assert result["stage_exactness"]["local_ion_ordinal"] == {"exact": 4, "total": 4}
    assert result["first_divergence_stage"] == "condensed_matrix"

def test_old_production_controls_reject_contract_milestone(tmp_path: Path) -> None:
    source, native = _fixture(tmp_path, control_mismatch=True)
    result = parity.analyze(source, native, tmp_path / "out", TARGETS)
    assert result["milestone_result"] == "REJECT"
    assert result["first_divergence_stage"] == "solver_control_contract"
    assert result["first_divergence_identity"] == "max_outer_iterations"
    gates = result["solver_control_gates"]
    assert gates["SOLVER_CONTROL_CONTRACT_EXACT"] == {"exact": 0, "total": 4, "accepted": False}
    assert gates["MAX_OUTER_ITERATIONS_EXACT"] == {"exact": 0, "total": 4, "accepted": False}


def test_source_probe_runtime_import_executes_outer_difference(monkeypatch) -> None:
    fake = types.ModuleType("xstar_tools.xstar.element_equilibrium")

    def source_outer_difference(previous, current, *, epsilon):
        del epsilon
        return float(np.sum((previous - current) ** 2))

    fake._source_outer_difference = source_outer_difference
    monkeypatch.setitem(sys.modules, "xstar_tools.xstar.element_equilibrium", fake)
    monkeypatch.setattr(xstar_package, "element_equilibrium", fake, raising=False)
    namespace: dict[str, object] = {}
    exec(source_capture._FIELDS_AND_CAPTURE, namespace)
    module = namespace["_v213_eq"]
    value = module._source_outer_difference(
        np.array([1.0], dtype=np.float64),
        np.array([1.0], dtype=np.float64),
        epsilon=1.0e-6,
    )
    assert value == 0.0


def test_cpp_inputs_match_python_source_contract() -> None:
    fixed = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    element = (ROOT / "src/xstar_tools/xstar/cpp/element_engine.cpp").read_text()
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "ein.max_lucy_iterations = 200;" in fixed
    assert "ein.max_fixed_point_iterations = 200;" in fixed
    assert "ein.lucy_tolerance = 1.0e-2;" in fixed
    assert "ein.fixed_point_tolerance = 1.0e-2;" in fixed
    assert "ein.max_lucy_iterations = 100;" not in fixed
    assert "ein.max_fixed_point_iterations = 40;" not in fixed
    assert "input->max_lucy_iterations = 200;" in element
    assert "input.max_lucy_iterations = 200;" in standalone


def test_checker_requires_all_solver_control_gates(tmp_path: Path) -> None:
    source, native = _fixture(tmp_path, h6_matrix_mismatch=True)
    audit = tmp_path / "audit"
    parity.analyze(source, native, audit, TARGETS)
    baseline = tmp_path / "baseline.json"
    capture = tmp_path / "capture.json"
    output = tmp_path / "checker.json"
    baseline.write_text('{"result":"ACCEPT"}')
    capture.write_text('{"result":"ACCEPT"}')
    completed = subprocess.run([
        sys.executable,
        str(ROOT / "check_v048746215_source_faithful_element_convergence_contract.py"),
        "--audit-output", str(audit),
        "--baseline-report", str(baseline),
        "--source-capture-report", str(capture),
        "--output-json", str(output),
    ], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(output.read_text())
    assert result["milestone_result"] == "ACCEPT"
    assert result["scientific_result"] == "REJECT"
    assert result["solver_control_gates"]["SOLVER_CONTROL_CONTRACT_EXACT"]["exact"] == 4


def test_static_readiness_accepts() -> None:
    completed = subprocess.run([
        sys.executable,
        str(ROOT / "check_v048746215_source_faithful_element_convergence_contract_readiness.py"),
        "--package-dir", str(ROOT),
    ], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["result"] == "ACCEPT"
    assert result["module_contract"]["source_probe_runtime_import"] >= 1
    assert result["module_contract"]["abi_60487"] >= 1
