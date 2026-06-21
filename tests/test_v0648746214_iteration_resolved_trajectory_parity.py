from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from xstar_tools.xstar import iteration_resolved_trajectory_parity_v048746214 as parity
from xstar_tools.xstar import v0472_iteration_resolved_trajectory_capture_v048746214 as source_capture

ROOT = Path(__file__).resolve().parents[1]
TARGET = ((1, 1),)


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path, *, row_fraction_native: float = 1.0,
             fixed_reason_native: str = "tolerance") -> tuple[Path, Path]:
    source = tmp_path / "source"
    native = tmp_path / "native" / "evaluation_0001" / "iteration_trace"
    manifest = {
        "sequence": 1, "element_z": 1, "n_rows": 1, "n_superlevels": 1,
        "normalization_row": 1, "max_outer_iterations": 10,
        "max_fixed_iterations": 20, "lucy_tolerance": 1.0e-7,
        "fixed_point_tolerance": 1.0e-7, "outer_iterations": 1,
        "total_fixed_point_iterations": 1, "outer_trace_records": 1,
        "fixed_trace_records": 1, "trace_complete": 1,
    }
    outer = {
        "sequence": 1, "element_z": 1, "outer_iteration": 1,
        "compact_row": 1, "superlevel": 1, "ion": 1,
        "outer_start_population": 1.0, "row_fraction": 1.0,
        "population_after_condensed": 1.0,
        "population_after_fixed_point": 1.0,
        "fixed_iterations_this_outer": 1,
        "total_fixed_iterations_after_outer": 1,
        "fixed_difference": 0.0, "outer_difference": 0.0,
        "fixed_termination_reason": "tolerance",
        "outer_termination_reason": "tolerance",
    }
    superlevel = {
        "sequence": 1, "element_z": 1, "outer_iteration": 1,
        "superlevel": 1, "population_before_condensed_solve": 1.0,
        "condensed_rhs": 1.0, "first_lu_solution": 1.0,
        "refinement_residual": 0.0, "refinement_correction": 0.0,
        "refined_superlevel_solution": 1.0,
    }
    matrix = {
        "sequence": 1, "element_z": 1, "outer_iteration": 1,
        "row_superlevel": 1, "column_superlevel": 1,
        "normalized_matrix_value": 1.0,
    }
    fixed = {
        "sequence": 1, "element_z": 1, "outer_iteration": 1,
        "fixed_iteration": 1, "global_fixed_iteration": 1,
        "compact_row": 1, "superlevel": 1, "ion": 1,
        "population_before": 1.0, "riu": 0.0, "rui": 0.0,
        "ril": 0.0, "rli": 0.0, "population_after": 1.0,
        "fixed_difference": 0.0, "termination_reason": "tolerance",
    }
    _write(source / parity.SOURCE_FILES["manifest"], [manifest])
    _write(source / parity.SOURCE_FILES["outer"], [outer])
    _write(source / parity.SOURCE_FILES["super"], [superlevel])
    _write(source / parity.SOURCE_FILES["matrix"], [matrix])
    _write(source / parity.SOURCE_FILES["fixed"], [fixed])
    (source / source_capture.REPORT_NAME).write_text(json.dumps({
        "result": "ACCEPT", "actual_v0472_runtime_capture": True,
    }))

    stem = "sequence_0001_element_01"
    native_outer = dict(outer)
    native_outer["row_fraction"] = row_fraction_native
    native_fixed = dict(fixed)
    native_fixed["termination_reason"] = fixed_reason_native
    _write(native / f"{stem}{parity.NATIVE_SUFFIXES['manifest']}", [manifest])
    _write(native / f"{stem}{parity.NATIVE_SUFFIXES['outer']}", [native_outer])
    _write(native / f"{stem}{parity.NATIVE_SUFFIXES['super']}", [superlevel])
    _write(native / f"{stem}{parity.NATIVE_SUFFIXES['matrix']}", [matrix])
    _write(native / f"{stem}{parity.NATIVE_SUFFIXES['fixed']}", [native_fixed])
    return source, tmp_path / "native"


def test_exact_iteration_trajectory_accepts_science(tmp_path: Path) -> None:
    source, native = _fixture(tmp_path)
    result = parity.analyze(source, native, tmp_path / "out", TARGET)
    assert result["milestone_result"] == "ACCEPT"
    assert result["scientific_result"] == "ACCEPT"
    assert result["systems_fully_exact"] == 1
    assert result["first_divergence_stage"] == "FULLY_EXACT"
    assert result["iteration1_gates"]["OUTER_ITERATION_1_START_EXACT"]["accepted"] is True
    assert result["iteration1_gates"]["OUTER_ITERATION_1_FIXED_POINT_DECISION_EXACT"]["accepted"] is True


def test_first_one_ulp_row_fraction_is_localized(tmp_path: Path) -> None:
    source, native = _fixture(tmp_path, row_fraction_native=1.0000000000000002)
    result = parity.analyze(source, native, tmp_path / "out", TARGET)
    assert result["milestone_result"] == "ACCEPT"
    assert result["scientific_result"] == "REJECT"
    assert result["first_divergence_stage"] == "row_fraction"
    assert result["first_divergence_outer_iteration"] == 1
    assert result["iteration1_gates"]["OUTER_ITERATION_1_ROW_FRACTIONS_EXACT"]["accepted"] is False
    mismatches = list(csv.DictReader((tmp_path / "out" / "v048746214_iteration_trajectory_mismatches.csv").open()))
    assert mismatches[0]["stage"] == "row_fraction"
    assert mismatches[0]["ulp_distance"] == "1"


def test_fixed_point_decision_is_separate_stage(tmp_path: Path) -> None:
    source, native = _fixture(tmp_path, fixed_reason_native="continue")
    result = parity.analyze(source, native, tmp_path / "out", TARGET)
    assert result["first_divergence_stage"] == "fixed_termination_decision"
    assert result["first_divergence_fixed_iteration"] == 1
    assert result["iteration1_gates"]["OUTER_ITERATION_1_FIXED_POINT_DECISION_EXACT"]["accepted"] is False


def test_source_capture_verifier_counts_all_iterations(tmp_path: Path) -> None:
    source, _ = _fixture(tmp_path)
    result = source_capture.verify(source, TARGET)
    assert result["result"] == "ACCEPT", result["errors"]
    assert result["target_systems"] == 1
    assert result["outer_rows"] == 1
    assert result["superlevel_rows"] == 1
    assert result["condensed_matrix_values"] == 1
    assert result["fixed_rows"] == 1


def test_checker_accepts_diagnostic_milestone_with_scientific_reject(tmp_path: Path) -> None:
    source, native = _fixture(tmp_path, row_fraction_native=1.0000000000000002)
    audit = tmp_path / "audit"
    parity.analyze(source, native, audit, TARGET)
    baseline = tmp_path / "baseline.json"
    capture_report = tmp_path / "capture.json"
    output = tmp_path / "checker.json"
    baseline.write_text('{"result":"ACCEPT"}')
    capture_report.write_text('{"result":"ACCEPT"}')
    completed = subprocess.run([
        sys.executable, str(ROOT / "check_v048746214_iteration_resolved_trajectory_parity.py"),
        "--audit-output", str(audit), "--baseline-report", str(baseline),
        "--source-capture-report", str(capture_report), "--output-json", str(output),
    ], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(output.read_text())
    assert result["milestone_result"] == "ACCEPT"
    assert result["scientific_result"] == "REJECT"
    assert result["first_divergence_stage"] == "row_fraction"


def _load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_readiness_contract() -> None:
    readiness = _load_script(
        ROOT / "check_v048746214_iteration_resolved_trajectory_parity_readiness.py",
        "v214_readiness",
    )
    # The module exposes its contract through main only; run it as distributed.
    completed = subprocess.run([
        sys.executable, str(ROOT / "check_v048746214_iteration_resolved_trajectory_parity_readiness.py"),
        "--package-dir", str(ROOT),
    ], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["result"] == "ACCEPT"
