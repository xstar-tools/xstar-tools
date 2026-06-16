from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from xstar_tools.xstar.all61_post_seed_system_decomposition import decompose


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_array(path: Path, values: list[float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.asarray(values, dtype=np.float64).tofile(path)


def test_all61_post_seed_system_decomposition_classifies_boundaries(tmp_path: Path) -> None:
    source = tmp_path / "source"
    native = tmp_path / "native"
    diag = native / "qualification_diagnostics"
    output = tmp_path / "audit"
    source_system_rows: list[dict[str, object]] = []
    source_solve_rows: list[dict[str, object]] = []
    source_ion_rows: list[dict[str, object]] = []
    source_level_rows: list[dict[str, object]] = []

    system_fields = [
        "sequence", "kind", "dsec_call_id", "evaluation_index", "element_z", "abundance",
        "active_min_stage", "active_max_stage", "n_rows", "normalization_row",
        "dense_file", "heating_file", "heating2_file", "rhs_file", "initial_file", "outer_file",
        "final_file", "ion_final_file", "solver_method", "converged", "outer_iterations",
        "fixed_point_iterations", "normalization", "normalization_error", "max_relative_row_residual",
    ]
    native_fields = [
        "evaluation_ordinal", "element_index", "element_z", "abundance", "active_min_stage",
        "active_max_stage", "n_rows", "normalization_row", "dense_file", "heating_file",
        "heating2_file", "rhs_file", "initial_file", "outer_file", "final_file", "ion_final_file",
        "solver_method", "solver_status_flags", "outer_iterations", "fixed_point_iterations",
        "normalization", "normalization_error", "max_relative_row_residual",
    ]
    solve_fields = [
        "sequence", "element_z", "compact_row", "active_min_stage", "active_max_stage", "ion",
        "ion_stage", "ion_charge", "superlevel", "is_normalization_row",
        "transformed_initial_population", "final_outer_start_population", "final_population", "rhs",
    ]
    native_solve_fields = [
        "evaluation_ordinal", "element_z", "compact_row", "active_min_stage", "active_max_stage",
        "ion", "ion_charge", "superlevel", "is_normalization_row", "initial_population",
        "final_outer_start_population", "final_population", "rhs",
    ]

    for sequence in range(1, 62):
        native_manifest: list[dict[str, object]] = []
        native_solve: list[dict[str, object]] = []
        native_ions: list[dict[str, object]] = []
        native_levels: list[dict[str, object]] = []
        for element_index, z in enumerate((1, 2, 12)):
            source_prefix = Path("systems") / f"e{sequence:04d}_z{z:02d}"
            native_prefix = f"evaluation_{sequence:04d}_element_z{z:02d}"
            source_values = {
                "dense": [1.0], "heating": [2.0], "heating2": [3.0], "rhs": [0.0],
                "initial": [0.0], "outer": [0.5], "final": [0.5], "ion_final": [0.5],
            }
            native_values = {name: list(values) for name, values in source_values.items()}
            if (sequence, z) == (1, 1):
                native_values["dense"] = [1.25]
            elif (sequence, z) == (1, 2):
                native_values["rhs"] = [0.25]
            elif (sequence, z) == (1, 12):
                native_values["final"] = [0.25]
            elif (sequence, z) == (2, 1):
                native_values["ion_final"] = [0.25]
            elif (sequence, z) == (3, 1):
                native_values["heating"] = [2.25]
            elif (sequence, z) == (3, 2):
                native_values["heating2"] = [3.25]
            for name, values in source_values.items():
                _write_array(source / (str(source_prefix) + f"_{name}.bin"), values)
                _write_array(diag / f"{native_prefix}_{name}.bin", native_values[name])
            source_system_rows.append({
                "sequence": sequence, "kind": "dsec", "dsec_call_id": 1, "evaluation_index": sequence,
                "element_z": z, "abundance": 1.0, "active_min_stage": 1, "active_max_stage": 1,
                "n_rows": 1, "normalization_row": 1,
                **{f"{name}_file": str(source_prefix) + f"_{name}.bin" for name in ("dense", "heating", "heating2", "rhs", "initial", "outer", "final", "ion_final")},
                "solver_method": "source", "converged": 1, "outer_iterations": 1,
                "fixed_point_iterations": 1, "normalization": 1.0, "normalization_error": 0.0,
                "max_relative_row_residual": 0.0,
            })
            native_manifest.append({
                "evaluation_ordinal": sequence, "element_index": element_index, "element_z": z,
                "abundance": 1.0, "active_min_stage": 1, "active_max_stage": 1, "n_rows": 1,
                "normalization_row": 1,
                **{f"{name}_file": f"{native_prefix}_{name}.bin" for name in ("dense", "heating", "heating2", "rhs", "initial", "outer", "final", "ion_final")},
                "solver_method": "native", "solver_status_flags": 0, "outer_iterations": 1,
                "fixed_point_iterations": 1, "normalization": 1.0, "normalization_error": 0.0,
                "max_relative_row_residual": 0.0,
            })
            source_solve_rows.append({
                "sequence": sequence, "element_z": z, "compact_row": 1, "active_min_stage": 1,
                "active_max_stage": 1, "ion": 1, "ion_stage": 1, "ion_charge": 0,
                "superlevel": 1, "is_normalization_row": 1, "transformed_initial_population": 0.0,
                "final_outer_start_population": 0.5, "final_population": 0.5, "rhs": 0.0,
            })
            native_solve.append({
                "evaluation_ordinal": sequence, "element_z": z, "compact_row": 1,
                "active_min_stage": 1, "active_max_stage": 1, "ion": 1, "ion_charge": 0,
                "superlevel": 1, "is_normalization_row": 1, "initial_population": 0.0,
                "final_outer_start_population": 0.5, "final_population": native_values["final"][0], "rhs": native_values["rhs"][0],
            })
            for stage in range(1, z + 2):
                source_population = 1.0 if stage == 1 else 0.0
                native_population = source_population
                if (sequence, z, stage) == (2, 2, 1):
                    native_population = 0.75
                source_ion_rows.append({"sequence": sequence, "element_z": z, "stage": stage, "population": source_population})
                native_ions.append({"element_z": z, "stage": stage, "final_fraction": native_population})
            source_level_rows.append({"sequence": sequence, "element_z": z, "global_level_index": element_index + 1, "population": 0.5})
            native_level_value = 0.25 if (sequence, z) == (2, 12) else 0.5
            native_levels.append({
                "element_z": z, "global_population_row": element_index + 1,
                "final_population": native_level_value,
            })
        _write_csv(diag / f"evaluation_{sequence:04d}_all_element_solve_systems.csv", native_fields, native_manifest)
        _write_csv(diag / f"evaluation_{sequence:04d}_all_element_solve_rows.csv", native_solve_fields, native_solve)
        _write_csv(diag / f"evaluation_{sequence:04d}_ion_balance.csv", ["element_z", "stage", "final_fraction"], native_ions)
        _write_csv(diag / f"evaluation_{sequence:04d}_populations.csv", ["element_z", "global_population_row", "final_population"], native_levels)

    _write_csv(source / "v0472_all61_element_solve_systems.csv", system_fields, source_system_rows)
    _write_csv(source / "v0472_all61_element_solve_rows.csv", solve_fields, source_solve_rows)
    _write_csv(source / "v0472_all61_ion_populations.csv", ["sequence", "element_z", "stage", "population"], source_ion_rows)
    _write_csv(source / "v0472_all61_level_populations.csv", ["sequence", "element_z", "global_level_index", "population"], source_level_rows)
    (native / "native_dsec_summary.json").write_text(json.dumps({"total_evaluations": 61, "python_callbacks": 0}))

    report = decompose(source, native, output)
    assert report["result"] == "ACCEPT"
    assert report["gates"]["ALL_61_BASIS_AND_SEED_HELD_EXACT"] == "ACCEPT"
    assert report["gates"]["ALL_61_POST_SEED_DIVERGENCES_CLASSIFIED"] == "ACCEPT"
    assert report["gates"]["V06487_FIXED_STATE_PARITY"] == "REJECT"
    assert report["gates"]["THERMAL_PARITY"] == "BLOCKED"
    assert report["classification_counts"]["DENSE_MATRIX_DIVERGENCE"] == 1
    assert report["classification_counts"]["HEATING_MATRIX_DIVERGENCE"] == 1
    assert report["classification_counts"]["HEATING2_MATRIX_DIVERGENCE"] == 1
    assert report["classification_counts"]["RHS_DIVERGENCE"] == 1
    assert report["classification_counts"]["SOLVE_RESPONSE_DIVERGENCE"] == 1
    assert report["classification_counts"]["ACTIVE_ION_RECONSTRUCTION_DIVERGENCE"] == 1
    assert report["classification_counts"]["GLOBAL_ION_COMMIT_DIVERGENCE"] == 1
    assert report["classification_counts"]["GLOBAL_LEVEL_COMMIT_DIVERGENCE"] == 1


def test_source_compact_seed_preserves_absolute_ion_counters_and_raw_seed() -> None:
    root = Path(__file__).resolve().parents[1]
    cpp = (root / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "view.element.n_ions = full.n_ions;" in cpp
    assert "bool preserve_exact_initial = false" in cpp
    assert "if (!preserve_exact_initial" in cpp
    assert "source_compact_oracle.has_value());" in cpp
