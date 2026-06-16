from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_tools.xstar.all61_source_compact_basis_seed_restoration import audit


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def test_native_source_compact_oracle_contract() -> None:
    cpp = Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    standalone = Path("src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "XSTAR_QUALIFICATION_SOURCE_COMPACT_BASIS_SEED" in cpp
    assert "XSTAR_QUALIFICATION_SOURCE_SOLVE_ROWS_CSV" in cpp
    assert "XSTAR_QUALIFICATION_SOURCE_SEQUENCE" in cpp
    assert "constexpr double critf = 1.0e-7" in cpp
    assert "XSTAR_FIXED_RUNTIME_STATE_GLOBAL_LEVEL_WORKSPACES" in standalone


def test_all61_source_compact_basis_seed_restoration_synthetic(tmp_path: Path) -> None:
    source = tmp_path / "source"
    native = tmp_path / "native"
    diagnostics = native / "qualification_diagnostics"
    diagnostics.mkdir(parents=True)
    source_rows: list[dict[str, object]] = []
    exact_elements = {(1, 2), (1, 12), (2, 2), (22, 2)}
    element_ordinal = 0
    for sequence in range(1, 62):
        for element_index, z in enumerate((1, 2, 12)):
            element_ordinal += 1
            count = 220 if element_ordinal <= 72 else 219
            source_element: list[dict[str, object]] = []
            native_element: list[dict[str, object]] = []
            for compact_row in range(1, count + 1):
                is_norm = int(compact_row == count)
                initial = 0.0 if sequence == 1 or is_norm else sequence * 1.0e-8 + compact_row * 1.0e-12
                final = 1.0 if is_norm else compact_row / count
                native_final = final if (sequence, z) in exact_elements else final + 1.0e-12
                source_element.append({
                    "sequence": sequence, "kind": "dsec", "dsec_call_id": 1,
                    "evaluation_index": sequence, "element_z": z, "abundance": 1.0,
                    "active_min_stage": 1, "active_max_stage": z if z != 12 else 12,
                    "compact_row": compact_row, "ion": 1, "ion_stage": 1,
                    "ion_charge": 0, "superlevel": compact_row,
                    "is_normalization_row": is_norm,
                    "transformed_initial_population": initial,
                    "final_outer_start_population": final, "final_population": final,
                    "rhs": 0.0, "row_residual": 0.0, "row_scale": 1.0,
                    "relative_row_residual": 0.0, "solver_method": "synthetic", "converged": 1,
                })
                native_element.append({
                    "evaluation_ordinal": sequence, "element_index": element_index,
                    "element_z": z, "abundance": 1.0, "active_min_stage": 1,
                    "active_max_stage": z if z != 12 else 12, "compact_row": compact_row,
                    "full_row": compact_row, "global_level_index": compact_row,
                    "superlevel": compact_row, "ion": 1, "ion_charge": 0,
                    "is_normalization_row": is_norm, "raw_global_level_index": compact_row,
                    "raw_call_start_xilevg": initial, "loaded_global_level_index": compact_row,
                    "loaded_call_start_xilevg": initial, "initial_population": initial,
                    "final_outer_start_population": native_final, "final_population": native_final,
                    "rhs": 0.0, "native_row_residual": 0.0, "native_row_scale": 1.0,
                    "native_relative_row_residual": 0.0,
                })
            source_rows.extend(source_element)
            path = diagnostics / f"evaluation_{sequence:04d}_all_element_solve_rows.csv"
            mode = "a" if path.exists() else "w"
            with path.open(mode, newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(native_element[0]))
                if mode == "w": writer.writeheader()
                writer.writerows(native_element)
    assert len(source_rows) == 40149
    write_csv(source / "v0472_all61_element_solve_rows.csv", list(source_rows[0]), source_rows)
    (native / "native_dsec_summary.json").write_text(json.dumps({"total_evaluations": 61, "python_callbacks": 0}) + "\n")

    result = audit(source, native, tmp_path / "out")
    assert result["result"] == "ACCEPT"
    assert result["basis_exact_elements"] == 183
    assert result["seed_exact_rows"] == 40149
    assert result["normalization_native_zero"] == 183
    assert result["hydrogen_post_seed_divergence_evaluations"] == 61
    assert result["gates"]["V06487_SOURCE_COMPACT_BASIS_SEED_RESTORATION"] == "ACCEPT"
    assert result["gates"]["V06487_FIXED_STATE_PARITY"] == "REJECT"
    assert result["gates"]["THERMAL_PARITY"] == "BLOCKED"
