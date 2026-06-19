from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from xstar_tools.xstar import all61_post_seed_system_decomposition as decomp
from xstar_tools.xstar import v0472_all61_post_seed_system_capture as capture


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_generated_probe_contains_real_system_capture() -> None:
    assert capture.RELEASE == "0.6.48.7.46.18.1"
    assert len(capture._PROBE) > 25_000
    assert capture._PROBE.count("def _v048746_capture_solve_system") == 1
    assert capture._PROBE.count("_v048746_capture_solve_system(kind") >= 2
    assert "Fixture full post-seed" not in capture.__doc__
    compile(capture._PROBE, "<v0487466-probe>", "exec")


def test_all61_exact_synthetic_systems(tmp_path: Path) -> None:
    source = tmp_path / "source"
    native = tmp_path / "native"
    diagnostics = native / "qualification_diagnostics"
    source.mkdir(); diagnostics.mkdir(parents=True)

    source_manifest: list[dict[str, object]] = []
    source_solve: list[dict[str, object]] = []
    source_ions: list[dict[str, object]] = []
    source_levels: list[dict[str, object]] = []
    program_rows: list[dict[str, object]] = []
    global_index_by_z = {1: 1, 2: 2, 12: 3}
    for element_index, z in enumerate((1, 2, 12)):
        program_rows.append({
            "element_index": element_index, "row": 1, "superlevel": 1,
            "ion": 1, "ion_charge": 0, "initial_population": 1.0,
            "energy_ev": 0.0, "statistical_weight": 1.0,
            "principal_n": 1, "orbital_l": 0,
            "global_level_index": global_index_by_z[z],
        })

    for sequence in range(1, 62):
        native_manifest: list[dict[str, object]] = []
        native_solve: list[dict[str, object]] = []
        native_ions: list[dict[str, object]] = []
        native_pops: list[dict[str, object]] = []
        for element_index, z in enumerate((1, 2, 12)):
            value = float(sequence * 100 + z)
            source_rel = Path("systems") / f"evaluation_{sequence:04d}" / f"element_{z:02d}"
            native_rel = Path(f"evaluation_{sequence:04d}_all_element_solve_systems")
            source_paths: dict[str, str] = {}
            native_paths: dict[str, str] = {}
            for name in decomp.ARRAY_NAMES:
                source_path = source / source_rel / f"{name}.bin"
                native_path = diagnostics / native_rel / f"element_{z:02d}_{name}.bin"
                source_path.parent.mkdir(parents=True, exist_ok=True)
                native_path.parent.mkdir(parents=True, exist_ok=True)
                np.asarray([value], dtype=np.float64).tofile(source_path)
                np.asarray([value], dtype=np.float64).tofile(native_path)
                source_paths[name] = str(source_path.relative_to(source))
                native_paths[name] = str(native_path.relative_to(diagnostics))
            common = {
                "element_z": z, "abundance": 1.0, "active_min_stage": 1,
                "active_max_stage": 1, "n_rows": 1, "n_ions": 1,
                "normalization_row": 1, "solver_method": "synthetic",
                "outer_iterations": 1, "fixed_point_iterations": 1,
                "normalization": 1.0, "normalization_error": 0.0,
            }
            source_row: dict[str, object] = {
                "sequence": sequence, "kind": "dsec", "dsec_call_id": 1,
                "evaluation_index": sequence, "converged": 1, **common,
            }
            native_row: dict[str, object] = {
                "evaluation_ordinal": sequence, "element_index": element_index,
                "solver_status_flags": 1, **common,
            }
            for name in decomp.ARRAY_NAMES:
                source_row[f"{name}_path"] = source_paths[name]
                source_row[f"{name}_count"] = 1
                source_row[f"{name}_sha256"] = "unused"
                native_row[f"{name}_path"] = native_paths[name]
                native_row[f"{name}_count"] = 1
            source_manifest.append(source_row)
            native_manifest.append(native_row)
            source_solve.append({
                "sequence": sequence, "kind": "dsec", "dsec_call_id": 1,
                "evaluation_index": sequence, "element_z": z, "abundance": 1.0,
                "active_min_stage": 1, "active_max_stage": 1,
                "compact_row": 1, "ion": 1, "ion_stage": 1, "ion_charge": 0,
                "superlevel": 1, "is_normalization_row": 1,
                "transformed_initial_population": value,
                "final_outer_start_population": value,
                "final_population": value, "rhs": value,
                "row_residual": 0.0, "row_scale": 1.0,
                "relative_row_residual": 0.0, "solver_method": "synthetic",
                "converged": 1,
            })
            native_solve.append({
                "evaluation_ordinal": sequence, "element_index": element_index,
                "element_z": z, "abundance": 1.0,
                "active_min_stage": 1, "active_max_stage": 1,
                "compact_row": 1, "full_row": 1,
                "global_level_index": global_index_by_z[z], "superlevel": 1,
                "ion": 1, "ion_charge": 0, "is_normalization_row": 1,
                "raw_global_level_index": global_index_by_z[z],
                "raw_call_start_xilevg": value,
                "loaded_global_level_index": global_index_by_z[z],
                "loaded_call_start_xilevg": value,
                "initial_population": value,
                "final_outer_start_population": value,
                "final_population": value, "rhs": value,
                "native_row_residual": 0.0, "native_row_scale": 1.0,
                "native_relative_row_residual": 0.0,
            })
            for stage in range(1, z + 2):
                population = 1.0 if stage == 1 else 0.0
                source_ions.append({
                    "sequence": sequence, "kind": "dsec", "dsec_call_id": 1,
                    "evaluation_index": sequence, "element_z": z,
                    "stage": stage, "ion_charge": stage - 1,
                    "population": population,
                })
                native_ions.append({
                    "evaluation_ordinal": sequence, "element_index": element_index,
                    "element_z": z, "stage": stage, "ion_charge": stage - 1,
                    "preliminary_ionization": 0.0, "preliminary_recombination": 0.0,
                    "preliminary_fraction": population, "final_fraction": population,
                    "active_stage": 1,
                })
            source_levels.append({
                "sequence": sequence, "kind": "dsec", "dsec_call_id": 1,
                "evaluation_index": sequence, "element_z": z, "stage": 1,
                "local_level_ordinal": 1,
                "global_level_index": global_index_by_z[z],
                "population": value, "bilevg": 0.0, "rnisg": 0.0,
            })
            native_pops.append({
                "evaluation_ordinal": sequence, "global_population_row": element_index + 1,
                "element_index": element_index, "element_z": z, "element_row": 1,
                "superlevel": 1, "ion": 1, "ion_charge": 0,
                "energy_ev": 0.0, "statistical_weight": 1.0,
                "initial_population": value, "final_population": value,
                "active_row": 1,
            })
        write_csv(diagnostics / f"evaluation_{sequence:04d}_all_element_solve_system_manifest.csv", native_manifest)
        write_csv(diagnostics / f"evaluation_{sequence:04d}_all_element_solve_rows.csv", native_solve)
        write_csv(diagnostics / f"evaluation_{sequence:04d}_ion_balance.csv", native_ions)
        write_csv(diagnostics / f"evaluation_{sequence:04d}_populations.csv", native_pops)

    write_csv(source / "v0472_all61_solve_system_manifest.csv", source_manifest)
    write_csv(source / "v0472_all61_element_solve_rows.csv", source_solve)
    write_csv(source / "v0472_all61_ion_populations.csv", source_ions)
    write_csv(source / "v0472_all61_level_populations.csv", source_levels)
    write_csv(tmp_path / "rows.csv", program_rows)
    (native / "native_dsec_summary.json").write_text(
        '{"total_evaluations":61,"python_callbacks":0}\n'
    )
    result = decomp.decompose(source, native, tmp_path / "out", tmp_path / "rows.csv")
    assert result["result"] == "ACCEPT"
    assert result["gates"]["ALL_61_SOURCE_SOLVE_SYSTEMS_CAPTURED"] == "ACCEPT"
    assert result["gates"]["ALL_61_NATIVE_SOLVE_SYSTEMS_CAPTURED"] == "ACCEPT"
    assert result["gates"]["ALL_61_BASIS_AND_SEED_HELD_EXACT"] == "ACCEPT"
    assert result["gates"]["ALL_61_MATRIX_SYSTEM_EXACT"] == "ACCEPT"
    assert result["gates"]["ALL_61_SOLVE_RESPONSE_EXACT"] == "ACCEPT"
    assert result["gates"]["ALL_61_GLOBAL_ELEMENT_COMMIT_EXACT"] == "ACCEPT"
    assert result["gates"]["V06487_FIXED_STATE_PARITY"] == "ACCEPT"
