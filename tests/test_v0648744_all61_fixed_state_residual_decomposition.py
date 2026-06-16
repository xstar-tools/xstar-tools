from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_tools.xstar.all61_fixed_state_residual_decomposition import decompose


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def test_capture_declares_all61_source_solve_contract() -> None:
    text = Path("src/xstar_tools/xstar/v0472_all61_fixed_state_capture.py").read_text()
    assert 'SOLVE_NAME = "v0472_all61_element_solve_rows.csv"' in text
    assert 'payload["retain_element_results"] = True' in text
    assert "_v048744_capture_solve_rows" in text
    assert "solve_element_inventory" in text


def test_residual_decomposition_synthetic_all61(tmp_path: Path) -> None:
    source = tmp_path / "source"; native = tmp_path / "native"; diag = native / "qualification_diagnostics"
    source.mkdir(); diag.mkdir(parents=True)
    abundances = {1: 1.0, 2: 0.1, 12: 3.5e-5}
    source_states: list[dict[str, object]] = []
    source_ions: list[dict[str, object]] = []
    source_solve: list[dict[str, object]] = []
    native_states: list[dict[str, object]] = []
    for seq in range(1, 62):
        src_by_z: dict[int, list[float]] = {
            1: [0.1, 0.9],
            2: [0.01, 0.09, 0.90],
            12: [0.0] * 10 + [0.50, 0.40, 0.10],
        }
        nat_by_z = {z: list(v) for z, v in src_by_z.items()}
        nat_by_z[1] = [0.2, 0.8]
        if seq != 22:
            nat_by_z[2] = [0.02, 0.08, 0.90]
        nat_by_z[12] = [0.0] * 10 + [1.0, 0.0, 0.0]
        source_xee = sum(abundances[z] * sum(i * p for i, p in enumerate(src_by_z[z])) for z in (1, 2, 12))
        native_xee = sum(abundances[z] * sum(i * p for i, p in enumerate(nat_by_z[z])) for z in (1, 2, 12))
        source_states.append({
            "sequence": seq, "kind": "dsec", "dsec_call_id": 1, "evaluation_index": seq,
            "temperature_k": 1.0e6, "temperature_t4": 100.0,
            "electron_fraction_input": source_xee, "computed_electron_fraction": source_xee,
            "charge_residual": 0.0, "hmctot": 0.0,
        })
        native_states.append({
            "sequence": seq, "kind": "dsec", "call_index": 1, "evaluation_index": seq,
            "temperature_t4": 100.0, "electron_fraction_input": source_xee,
            "computed_electron_fraction": native_xee,
            "charge_residual": source_xee - native_xee, "hmctot": 0.0,
        })
        native_ion_rows: list[dict[str, object]] = []
        native_solve_rows: list[dict[str, object]] = []
        for z in (1, 2, 12):
            for stage, pop in enumerate(src_by_z[z], 1):
                source_ions.append({
                    "sequence": seq, "kind": "dsec", "dsec_call_id": 1, "evaluation_index": seq,
                    "element_z": z, "stage": stage, "ion_charge": stage - 1, "population": pop,
                })
            for stage, pop in enumerate(nat_by_z[z], 1):
                native_ion_rows.append({
                    "evaluation_ordinal": seq, "element_index": (1, 2, 12).index(z), "element_z": z,
                    "stage": stage, "ion_charge": stage - 1, "preliminary_ionization": 0.0,
                    "preliminary_recombination": 0.0, "preliminary_fraction": pop,
                    "final_fraction": pop, "active_stage": 1,
                })
            source_final = 0.5
            native_final = source_final
            if z == 1:
                native_final = 0.4
            source_solve.append({
                "sequence": seq, "kind": "dsec", "dsec_call_id": 1, "evaluation_index": seq,
                "element_z": z, "abundance": abundances[z], "active_min_stage": 1,
                "active_max_stage": 10 if z == 12 else z, "compact_row": 1, "ion": 1,
                "ion_stage": 1, "ion_charge": 0, "superlevel": 1, "is_normalization_row": 0,
                "transformed_initial_population": 0.25, "final_outer_start_population": source_final,
                "final_population": source_final, "rhs": 0.0, "row_residual": 0.0,
                "row_scale": 1.0, "relative_row_residual": 0.0,
                "solver_method": "synthetic", "converged": 1,
            })
            native_solve_rows.append({
                "evaluation_ordinal": seq, "element_index": (1, 2, 12).index(z), "element_z": z,
                "abundance": abundances[z], "active_min_stage": 1,
                "active_max_stage": 10 if z == 12 else z, "compact_row": 1, "full_row": 1,
                "global_level_index": 1, "superlevel": 1, "ion": 1, "ion_charge": 0,
                "is_normalization_row": 0, "raw_global_level_index": 1,
                "raw_call_start_xilevg": 0.25, "loaded_global_level_index": 1,
                "loaded_call_start_xilevg": 0.25, "initial_population": 0.25,
                "final_outer_start_population": native_final, "final_population": native_final,
                "rhs": 0.0, "native_row_residual": 0.0, "native_row_scale": 1.0,
                "native_relative_row_residual": 0.0,
            })
        write_csv(diag / f"evaluation_{seq:04d}_ion_balance.csv", list(native_ion_rows[0]), native_ion_rows)
        write_csv(diag / f"evaluation_{seq:04d}_all_element_solve_rows.csv", list(native_solve_rows[0]), native_solve_rows)
    write_csv(source / "v0472_all61_fixed_state_rows.csv", list(source_states[0]), source_states)
    write_csv(source / "v0472_all61_ion_populations.csv", list(source_ions[0]), source_ions)
    write_csv(source / "v0472_all61_element_solve_rows.csv", list(source_solve[0]), source_solve)
    write_csv(native / "native_dsec_trajectory.csv", list(native_states[0]), native_states)
    (native / "native_dsec_summary.json").write_text(json.dumps({"total_evaluations": 61, "python_callbacks": 0}) + "\n")

    result = decompose(source, native, tmp_path / "out")
    assert result["result"] == "ACCEPT"
    assert result["gates"]["V06487_FIXED_STATE_RESIDUAL_DECOMPOSITION"] == "ACCEPT"
    assert result["gates"]["V06487_FIXED_STATE_PARITY"] == "REJECT"
    assert result["gates"]["THERMAL_PARITY"] == "BLOCKED"
    assert result["gates"]["MG_ACTIVE_WINDOW_TRUNCATION_IDENTIFIED"] == "ACCEPT"
    assert result["gates"]["H_POST_SEED_SOLVE_DIVERGENCE_IDENTIFIED"] == "ACCEPT"
    assert result["gates"]["HE_CALL2_LOCAL_EXACTNESS_CONFIRMED"] == "ACCEPT"
