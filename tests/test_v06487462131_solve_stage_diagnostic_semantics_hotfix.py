from __future__ import annotations

import csv
import importlib.util
import json
import struct
from pathlib import Path

from xstar_tools.xstar import compact_population_solve_stage_parity_v0487462131 as parity

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _small_mg(monkeypatch) -> None:
    monkeypatch.setattr(parity, "EXPECTED_ROWS", 1)
    monkeypatch.setattr(parity, "EXPECTED_SYSTEMS", 1)
    monkeypatch.setattr(parity, "EXPECTED_IONS", 13)
    monkeypatch.setattr(parity, "EXPECTED_NATIVE_BOUND_IONS", 12)
    monkeypatch.setattr(parity, "EXPECTED_SUPERLEVELS", 1)
    monkeypatch.setattr(parity, "EXPECTED_MATRIX_VALUES", 1)
    monkeypatch.setattr(parity, "EXPECTED_BY_ELEMENT", {1: 0, 2: 0, 12: 1})
    monkeypatch.setattr(parity, "ELEMENTS", (12,))
    monkeypatch.setattr(parity, "SEQUENCES", (1,))


def _fixture(
    tmp_path: Path,
    *,
    native_local_ion: int = 1,
    native_outer_iterations: int = 1,
    omit_native_ion_payload: bool = False,
) -> tuple[Path, Path]:
    source = tmp_path / "source"
    native = tmp_path / "native"
    diag = native / "qualification_diagnostics"
    source_row = {
        "sequence": 1, "element_z": 12,
        "active_min_stage": 5, "active_max_stage": 12,
        "compact_row": 1, "superlevel": 1,
        "ion": 5, "ion_stage": 5, "ion_charge": 4,
        "is_normalization_row": 0,
        "transformed_initial_population": 0.0,
        "final_outer_start_population": 1.0,
        "population_after_condensed": 1.0,
        "final_fixed_point_population_before": 1.0,
        "final_fixed_point_population_after": 1.0,
        "final_population": 1.0,
        "rhs": 0.0,
    }
    native_row = {k: v for k, v in source_row.items() if k not in ("sequence", "ion_stage")}
    native_row["ion"] = native_local_ion
    source_super = {
        "sequence": 1, "element_z": 12, "final_outer_iteration": 1,
        "superlevel": 1, "population_before_condensed_solve": 1.0,
        "condensed_rhs": 0.0, "first_lu_solution": 1.0,
        "refinement_residual": 0.0, "refinement_correction": 0.0,
        "refined_superlevel_solution": 1.0,
    }
    native_super = {k: v for k, v in source_super.items() if k != "sequence"}
    source_matrix = {
        "sequence": 1, "element_z": 12, "final_outer_iteration": 1,
        "row_superlevel": 1, "column_superlevel": 1,
        "normalized_matrix_value": 1.0,
    }
    native_matrix = {k: v for k, v in source_matrix.items() if k != "sequence"}
    source_manifest = {
        "sequence": 1, "element_z": 12,
        "active_min_stage": 5, "active_max_stage": 12,
        "n_rows": 1, "n_superlevels": 1,
        "n_ions": 12, "normalization_row": 1,
        "final_outer_iteration": 1, "final_fixed_iterations": 1,
        "total_fixed_point_iterations": 1,
        "solver_method": "source", "converged": 1,
    }
    native_manifest = {
        "element_z": 12,
        "active_min_stage": 5, "active_max_stage": 12,
        "n_rows": 1, "n_superlevels": 1,
        "n_ions": 8, "normalization_row": 1,
        "final_outer_iteration": native_outer_iterations,
        "final_fixed_iterations": 1,
        "total_fixed_point_iterations": native_outer_iterations,
        "solver_method": "native", "trace_captured": 1,
    }
    _write(source / parity.ROW_SOURCE, [source_row])
    _write(source / parity.SUPER_SOURCE, [source_super])
    _write(source / parity.MATRIX_SOURCE, [source_matrix])
    _write(source / parity.MANIFEST_SOURCE, [source_manifest])
    source_ions = [
        {"sequence": 1, "element_z": 12, "stage": stage,
         "ion_charge": stage - 1, "population": 0.0 if stage <= 12 else 1.0}
        for stage in range(1, 14)
    ]
    _write(source / parity.ION_SOURCE, source_ions)

    stem = "evaluation_0001_all_element_solve_stage"
    _write(diag / f"{stem}_rows.csv", [native_row])
    _write(diag / f"{stem}_superlevels.csv", [native_super])
    _write(diag / f"{stem}_condensed_matrix.csv", [native_matrix])
    _write(diag / f"{stem}_manifest.csv", [native_manifest])
    ion_rel = "evaluation_0001_all_element_solve_systems/element_12_ion_reconstruction.bin"
    if not omit_native_ion_payload:
        ion_path = diag / ion_rel
        ion_path.parent.mkdir(parents=True, exist_ok=True)
        ion_path.write_bytes(struct.pack("<" + "d" * 12, *([0.0] * 12)))
    _write(diag / "evaluation_0001_all_element_solve_system_manifest.csv", [{
        "element_z": 12,
        "ion_reconstruction_path": ion_rel,
        "ion_reconstruction_count": 12,
    }])
    return source, native


def test_physical_stage_and_local_ordinal_semantics(monkeypatch, tmp_path: Path) -> None:
    _small_mg(monkeypatch)
    source, native = _fixture(tmp_path)
    result = parity.audit(source, native, tmp_path / "out")
    assert result["stage_gates"]["COMPACT_TOPOLOGY_EXACT"] == "ACCEPT"
    assert result["stage_gates"]["SOURCE_TOTAL_BOUND_ION_COUNTS_VALID_183"] == "ACCEPT"
    assert result["stage_gates"]["ACTIVE_ION_STAGE_COUNTS_EXACT_183"] == "ACCEPT"
    assert result["stage_gates"]["NORMALIZATION_ROWS_EXACT_183"] == "ACCEPT"


def test_local_ordinal_is_compared_separately(monkeypatch, tmp_path: Path) -> None:
    _small_mg(monkeypatch)
    source, native = _fixture(tmp_path, native_local_ion=2)
    result = parity.audit(source, native, tmp_path / "out")
    assert result["stage_gates"]["COMPACT_TOPOLOGY_EXACT"] == "REJECT"
    example = result["first_divergence_example"]
    assert example["source"]["derived_local_ion_ordinal"] == 1
    assert example["native"]["local_ion_ordinal"] == 2


def test_fully_stripped_native_population_is_reconstructed(monkeypatch, tmp_path: Path) -> None:
    _small_mg(monkeypatch)
    source, native = _fixture(tmp_path)
    result = parity.audit(source, native, tmp_path / "out")
    assert result["native_inventory"]["bound_ion_values"] == 12
    assert result["native_inventory"]["reconstructed_ion_values"] == 13
    assert result["stage_gates"]["ION_RECONSTRUCTION_INVENTORY_COMPLETE_1098"] == "ACCEPT"
    assert result["stage_gates"]["ION_RECONSTRUCTION_EXACT_1098"] == "ACCEPT"


def test_capture_inventory_errors_are_separate(monkeypatch, tmp_path: Path) -> None:
    _small_mg(monkeypatch)
    source, native = _fixture(tmp_path, omit_native_ion_payload=True)
    result = parity.audit(source, native, tmp_path / "out")
    assert result["decomposition_gates"]["SOURCE_SOLVE_STAGE_CAPTURE_COMPLETE"] == "ACCEPT"
    assert result["decomposition_gates"]["NATIVE_SOLVE_STAGE_CAPTURE_COMPLETE"] == "REJECT"
    assert result["source_capture_inventory_errors"] == []
    assert result["native_capture_inventory_errors"]


def test_outer_iteration_boundary_is_aliased(monkeypatch, tmp_path: Path) -> None:
    _small_mg(monkeypatch)
    source, native = _fixture(tmp_path, native_outer_iterations=2)
    result = parity.audit(source, native, tmp_path / "out")
    assert result["result"] == "ACCEPT"
    assert result["first_captured_divergence_stage"] == "outer_iteration_trajectory"
    assert result["first_detailed_divergence_stage"] == "final_outer_iteration_count"


def _load_script(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_checker_emits_corrected_summary(tmp_path: Path) -> None:
    checker = _load_script(
        ROOT / "check_v0487462131_solve_stage_diagnostic_semantics_hotfix.py",
        "v2131_checker",
    )
    out = tmp_path / "out"
    out.mkdir()
    (out / "v0487462131_solve_stage_parity_report.json").write_text(json.dumps({
        "result": "ACCEPT", "scientific_result": "REJECT",
        "decomposition_gates": {name: "ACCEPT" for name in checker.DECOMPOSITION_GATES},
        "stage_gates": {
            "COMPACT_TOPOLOGY_EXACT": "ACCEPT",
            "NORMALIZATION_ROWS_EXACT_183": "ACCEPT",
            "ION_RECONSTRUCTION_INVENTORY_COMPLETE_1098": "ACCEPT",
        },
        "first_captured_divergence_stage": "outer_iteration_trajectory",
        "first_detailed_divergence_stage": "final_outer_iteration_count",
        "systems_classified": 183, "systems_expected": 183,
        "systems_fully_exact": 11,
        "final_compact_population_values_exact": 3501,
        "final_compact_population_values_expected": 40149,
        "sequence_fingerprints_exact": 0,
    }))
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"result":"ACCEPT"}')
    source = tmp_path / "source.json"
    source.write_text('{"result":"ACCEPT"}')
    result = checker.check(out, baseline, source)
    assert result["result"] == "ACCEPT"
    assert result["scientific_result"] == "REJECT"
    assert result["first_captured_divergence_stage"] == "outer_iteration_trajectory"
    assert result["systems_fully_exact"] == 11
    assert result["final_compact_population_values_exact"] == 3501


def test_readiness_contract() -> None:
    readiness = _load_script(
        ROOT / "check_v0487462131_solve_stage_diagnostic_semantics_hotfix_readiness.py",
        "v2131_readiness",
    )
    result = readiness.check(ROOT)
    assert result["result"] == "ACCEPT", result["errors"]
