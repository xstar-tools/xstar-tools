from __future__ import annotations

import csv
import importlib.util
import json
import struct
from pathlib import Path

from xstar_tools.xstar import compact_population_solve_stage_parity_v048746213 as parity
from xstar_tools.xstar import v0472_all61_solve_stage_capture_v048746213 as capture

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def _fixture(tmp_path: Path, *, mismatch_stage: str | None = None) -> tuple[Path, Path]:
    source = tmp_path / "source"; native = tmp_path / "native"; diag = native / "qualification_diagnostics"
    common_row = {
        "sequence": 1, "element_z": 1, "active_min_stage": 1, "active_max_stage": 1,
        "compact_row": 1, "superlevel": 1, "ion": 1, "ion_stage": 1, "ion_charge": 0,
        "is_normalization_row": 1, "transformed_initial_population": 1.0,
        "final_outer_start_population": 1.0, "population_after_condensed": 1.0,
        "final_fixed_point_population_before": 1.0, "final_fixed_point_population_after": 1.0,
        "final_population": 1.0, "rhs": 1.0,
    }
    native_row = {k: v for k, v in common_row.items() if k not in ("sequence", "ion_stage")}
    if mismatch_stage in native_row:
        native_row[mismatch_stage] = 0.5
    common_super = {
        "sequence": 1, "element_z": 1, "final_outer_iteration": 1, "superlevel": 1,
        "population_before_condensed_solve": 1.0, "condensed_rhs": 1.0,
        "first_lu_solution": 1.0, "refinement_residual": 0.0,
        "refinement_correction": 0.0, "refined_superlevel_solution": 1.0,
    }
    native_super = {k: v for k, v in common_super.items() if k != "sequence"}
    if mismatch_stage in native_super:
        native_super[mismatch_stage] = 0.5
    common_matrix = {"sequence": 1, "element_z": 1, "final_outer_iteration": 1, "row_superlevel": 1, "column_superlevel": 1, "normalized_matrix_value": 1.0}
    native_matrix = {k: v for k, v in common_matrix.items() if k != "sequence"}
    if mismatch_stage == "normalized_matrix_value": native_matrix["normalized_matrix_value"] = 0.5
    common_manifest = {
        "sequence": 1, "element_z": 1, "active_min_stage": 1, "active_max_stage": 1,
        "n_rows": 1, "n_superlevels": 1, "n_ions": 1, "normalization_row": 1,
        "final_outer_iteration": 1, "final_fixed_iterations": 1,
        "total_fixed_point_iterations": 1, "solver_method": "lu", "converged": 1,
    }
    native_manifest = {k: v for k, v in common_manifest.items() if k not in ("sequence", "converged")}
    native_manifest["trace_captured"] = 1
    if mismatch_stage in native_manifest: native_manifest[mismatch_stage] = 2
    _write(source / parity.ROW_SOURCE, [common_row])
    _write(source / parity.SUPER_SOURCE, [common_super])
    _write(source / parity.MATRIX_SOURCE, [common_matrix])
    _write(source / parity.MANIFEST_SOURCE, [common_manifest])
    _write(source / parity.ION_SOURCE, [{"sequence": 1, "element_z": 1, "stage": 1, "ion_charge": 0, "population": 1.0}])
    stem = "evaluation_0001_all_element_solve_stage"
    _write(diag / f"{stem}_rows.csv", [native_row])
    _write(diag / f"{stem}_superlevels.csv", [native_super])
    _write(diag / f"{stem}_condensed_matrix.csv", [native_matrix])
    _write(diag / f"{stem}_manifest.csv", [native_manifest])
    ion_rel = "evaluation_0001_all_element_solve_systems/element_01_ion_reconstruction.bin"
    ion_path = diag / ion_rel; ion_path.parent.mkdir(parents=True, exist_ok=True)
    ion_path.write_bytes(struct.pack("<d", 1.0))
    _write(diag / "evaluation_0001_all_element_solve_system_manifest.csv", [{
        "element_z": 1, "ion_reconstruction_path": ion_rel, "ion_reconstruction_count": 1
    }])
    return source, native


def _small(monkeypatch) -> None:
    monkeypatch.setattr(parity, "EXPECTED_ROWS", 1)
    monkeypatch.setattr(parity, "EXPECTED_SYSTEMS", 1)
    monkeypatch.setattr(parity, "EXPECTED_IONS", 1)
    monkeypatch.setattr(parity, "EXPECTED_BY_ELEMENT", {1: 1, 2: 0, 12: 0})
    monkeypatch.setattr(parity, "ELEMENTS", (1,))
    monkeypatch.setattr(parity, "SEQUENCES", (1,))


def test_exact_synthetic_solve_stage(monkeypatch, tmp_path: Path) -> None:
    _small(monkeypatch); source, native = _fixture(tmp_path)
    result = parity.audit(source, native, tmp_path / "out")
    assert result["result"] == "ACCEPT"
    assert result["scientific_result"] == "ACCEPT"
    assert result["first_divergence_stage"] == "FULLY_EXACT"
    assert result["final_compact_population_values_exact"] == 1


def test_first_divergence_is_initial_population(monkeypatch, tmp_path: Path) -> None:
    _small(monkeypatch); source, native = _fixture(tmp_path, mismatch_stage="transformed_initial_population")
    result = parity.audit(source, native, tmp_path / "out")
    assert result["result"] == "ACCEPT"
    assert result["scientific_result"] == "ACCEPT"  # final value remains exact
    assert result["first_divergence_stage"] == "transformed_initial_population"
    assert result["systems_classified"] == 1


def test_first_divergence_is_lu_solution(monkeypatch, tmp_path: Path) -> None:
    _small(monkeypatch); source, native = _fixture(tmp_path, mismatch_stage="first_lu_solution")
    result = parity.audit(source, native, tmp_path / "out")
    assert result["first_divergence_stage"] == "first_lu_solution"
    assert result["stage_gates"]["FIRST_LU_SOLUTIONS_EXACT"] == "REJECT"


def test_final_population_mismatch_preserves_milestone_acceptance(monkeypatch, tmp_path: Path) -> None:
    _small(monkeypatch); source, native = _fixture(tmp_path, mismatch_stage="final_population")
    result = parity.audit(source, native, tmp_path / "out")
    assert result["result"] == "ACCEPT"
    assert result["scientific_result"] == "REJECT"
    assert result["first_divergence_stage"] == "final_compact_population"
    assert result["downstream_thermal_science"] == "NOT_RUN_SOLVE_STAGE_PREREQUISITE"


def test_source_probe_contains_observational_trace() -> None:
    compile(capture._PROBE, "probe", "exec")
    assert "_v213_traced_solve_normalized" in capture._PROBE
    assert "first_lu_solution" in capture._PROBE
    assert "refinement_correction" in capture._PROBE
    assert "_v213_original_solve_normalized" in capture._PROBE


def test_native_trace_contract_present() -> None:
    level = (ROOT / "src/xstar_tools/xstar/cpp/level_population.cpp").read_text()
    header = (ROOT / "src/xstar_tools/xstar/cpp/xstar_element_engine.h").read_text()
    fixed = (ROOT / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "xstar_solver_leqt2f_trace_v1" in level
    assert "xstar_element_solve_stage_trace_v1" in header
    assert "_all_element_solve_stage_rows.csv" in fixed
    assert "_all_element_solve_stage_condensed_matrix.csv" in fixed


def _load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_checker_accepts_complete_decomposition_with_scientific_reject(tmp_path: Path) -> None:
    checker = _load_script(ROOT / "check_v048746213_compact_population_solve_stage_parity.py", "v213_checker")
    out = tmp_path / "out"; out.mkdir()
    (out / "v048746213_solve_stage_parity_report.json").write_text(json.dumps({
        "result": "ACCEPT", "scientific_result": "REJECT",
        "decomposition_gates": {name: "ACCEPT" for name in checker.DECOMPOSITION_GATES},
        "stage_gates": {"FINAL_COMPACT_POPULATIONS_EXACT_40149": "REJECT"},
        "first_divergence_stage": "first_lu_solution", "systems_classified": 183,
        "systems_expected": 183, "final_compact_population_values_exact": 3501,
        "final_compact_population_values_expected": 40149, "sequence_fingerprints_exact": 0,
    }))
    baseline = tmp_path / "baseline.json"; baseline.write_text('{"result":"ACCEPT"}')
    source = tmp_path / "source.json"; source.write_text('{"result":"ACCEPT"}')
    result = checker.check(out, baseline, source)
    assert result["result"] == "ACCEPT"
    assert result["scientific_result"] == "REJECT"
    assert result["downstream_thermal_science"] == "NOT_RUN_SOLVE_STAGE_PREREQUISITE"


def test_readiness_contract(tmp_path: Path) -> None:
    readiness = _load_script(ROOT / "check_v048746213_compact_population_solve_stage_parity_readiness.py", "v213_readiness")
    result = readiness.check(ROOT)
    assert result["result"] == "ACCEPT", result["errors"]
