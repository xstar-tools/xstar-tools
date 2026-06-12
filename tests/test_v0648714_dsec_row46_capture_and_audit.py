from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_tools.xstar import row46_dsec_residual_audit as audit
from xstar_tools.xstar import v0472_dsec_row46_runtime_capture as cap


def test_embedded_probe_scripts_compile() -> None:
    compile(cap._PROBE_RUNTIME, "probe_runtime", "exec")
    compile(cap._DRIVER, "capture_driver", "exec")


def test_target_inventory_matches_row46_fixture(tmp_path: Path) -> None:
    fields = [
        "element_index", "ion_stage", "data_type", "rate_type", "lower_row",
        "upper_row", "record", "source_position",
    ]
    inventory = [
        (53, 7, 46, 78),
        *[(50, 4, 46, 47 + i) for i in range(9)],
        (76, 9, 46, 49),
        (71, 14, 46, 77),
        *[(56, 3, 46, 47 + i) for i in range(8)],
        (57, 5, 46, 78),
        (95, 5, 46, 78),
        (77, 23, 46, 77),
        (95, 15, 46, 46),
    ]
    with (tmp_path / "records.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, (data_type, rate_type, lower, upper) in enumerate(inventory):
            writer.writerow(
                {
                    "element_index": 1,
                    "ion_stage": 2,
                    "data_type": data_type,
                    "rate_type": rate_type,
                    "lower_row": lower,
                    "upper_row": upper,
                    "record": 1000 + index,
                    "source_position": 4000 + 4 * index,
                }
            )
    rows = cap._load_target_inventory(tmp_path)
    assert len(rows) == 24
    literal_types = {row["data_type"] for row in rows}
    assert literal_types == {50, 53, 56, 57, 71, 76, 77, 95}
    assert set(cap.TARGET_TYPE_COUNTS) == {50, 53, 56, 57, 71, 74, 76, 77, 95, 99}
    assert sum(cap.TARGET_TYPE_COUNTS.values()) == cap.TARGET_RECORDS == 154


def _write_complete_bundle(root: Path) -> None:
    records_fields = [
        "global_evaluation_ordinal", "dsec_call_id", "dsec_local_evaluation_index",
        "source_position", "record", "element_z", "ion_stage", "data_type", "rate_type",
        "lower_row", "upper_row", "escape_kind", "escape_index", "tau_in", "tau_out",
        "allow_missing_as_zero", "ptmp1", "ptmp2", "ptmp_sum", "flinabs_ptmp1",
        "covering_fraction", "temperature_k", "hydrogen_density_cm3", "electron_fraction_xee",
        "ans1", "ans2", "ans3", "ans4", "ans5", "ans6", "idest1", "idest2",
        "ucalc_status", "reason", "provenance_branch", "provenance_implementation",
        "diagnostics_json", "compact_lower_row", "compact_upper_row",
        "initial_lower_population", "initial_upper_population", "lte_lower_population",
        "lte_upper_population", "final_outer_lower_population", "final_outer_upper_population",
        "final_lower_population", "final_upper_population", "population_dependency_json",
        "matrix_term_count", "matrix_committed",
    ]
    type_inventory = []
    for data_type, count in cap.TARGET_TYPE_COUNTS.items():
        type_inventory.extend([data_type] * count)
    with (root / cap.RECORDS_NAME).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=records_fields)
        writer.writeheader()
        for index, data_type in enumerate(type_inventory):
            row = {field: 0 for field in records_fields}
            row.update(
                {
                    "global_evaluation_ordinal": 61,
                    "source_position": 6000 + 4 * index,
                    "record": 1600 + index,
                    "element_z": 2,
                    "ion_stage": 2,
                    "data_type": data_type,
                    "rate_type": 4 if data_type == 50 else 3,
                    "lower_row": 46,
                    "upper_row": 47 + index,
                    "ptmp1": 0.5,
                    "ptmp2": 0.5,
                    "ptmp_sum": 1.0,
                    "flinabs_ptmp1": 1.0,
                    "covering_fraction": 1.0,
                    "temperature_k": 64991.0,
                    "hydrogen_density_cm3": 1.0e8,
                    "electron_fraction_xee": 1.2,
                    "matrix_term_count": 4,
                    "matrix_committed": True,
                }
            )
            writer.writerow(row)
    term_fields = [
        "global_evaluation_ordinal", "dsec_call_id", "source_order_index", "source_position",
        "record", "data_type", "rate_type", "term_index", "role", "row", "column",
        "aj1", "aj2", "cj", "cj2", "idest1", "idest2", "lower_endpoint", "upper_endpoint",
        "source_row_unclamped", "source_column_unclamped", "source_ipmat_clamped",
        "touches_row46",
    ]
    roles = ["forward_offdiag", "reverse_offdiag", "forward_diag_loss", "reverse_diag_loss"]
    with (root / cap.TERMS_NAME).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=term_fields)
        writer.writeheader()
        source_index = 1
        for index, data_type in enumerate(type_inventory):
            for role_index, role in enumerate(roles):
                row = {field: 0 for field in term_fields}
                row.update(
                    {
                        "global_evaluation_ordinal": 61,
                        "source_order_index": source_index,
                        "source_position": 6000 + 4 * index,
                        "record": 1600 + index,
                        "data_type": data_type,
                        "rate_type": 4 if data_type == 50 else 3,
                        "term_index": source_index,
                        "role": role,
                        "row": 46 if role_index != 0 else 47 + index,
                        "column": 46,
                        "touches_row46": True,
                    }
                )
                writer.writerow(row)
                source_index += 1
    solve_fields = [
        "global_evaluation_ordinal", "compact_row", "full_row", "is_normalization_row",
        "ion_counter", "superlevel", "initial_population", "lte_population",
        "final_outer_start_population", "final_population", "rhs", "row_residual",
        "row_scale", "relative_row_residual", "roles_json",
    ]
    with (root / cap.SOLVE_ROWS_NAME).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=solve_fields)
        writer.writeheader()
        for row_index in range(1, 79):
            row = {field: 0 for field in solve_fields}
            row.update(
                {
                    "global_evaluation_ordinal": 61,
                    "compact_row": row_index,
                    "full_row": row_index,
                    "is_normalization_row": int(row_index == 78),
                }
            )
            writer.writerow(row)
    matrix_fields = [
        "global_evaluation_ordinal", "matrix_row_kind", "compact_row", "full_row",
        "compact_column", "dense_before_normalization", "normalized_after_commit",
        "heating_value", "heating2_value", "rhs",
    ]
    with (root / cap.ROW46_MATRIX_NAME).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=matrix_fields)
        writer.writeheader()
        for column in range(1, 79):
            writer.writerow(
                {
                    "global_evaluation_ordinal": 61,
                    "matrix_row_kind": "physical_row46",
                    "compact_row": 46,
                    "full_row": 46,
                    "compact_column": column,
                    "dense_before_normalization": 0,
                    "normalized_after_commit": 0,
                    "heating_value": 0,
                    "heating2_value": 0,
                    "rhs": 0,
                }
            )
    with (root / cap.NORMALIZATION_NAME).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=matrix_fields)
        writer.writeheader()
        for column in range(1, 79):
            writer.writerow(
                {
                    "global_evaluation_ordinal": 61,
                    "matrix_row_kind": "normalization",
                    "compact_row": 78,
                    "full_row": 78,
                    "compact_column": column,
                    "dense_before_normalization": 0,
                    "normalized_after_commit": 1,
                    "heating_value": 0,
                    "heating2_value": 0,
                    "rhs": 1,
                }
            )
    trace_fields = [
        "global_evaluation_ordinal", "dsec_call_id", "dsec_local_evaluation_index",
        "temperature_k", "hydrogen_density_cm3", "electron_fraction_xee",
    ]
    with (root / cap.TRACE_NAME).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=trace_fields)
        writer.writeheader()
        for evaluation in range(1, 62):
            writer.writerow(
                {
                    "global_evaluation_ordinal": evaluation,
                    "dsec_call_id": 1,
                    "dsec_local_evaluation_index": evaluation,
                    "temperature_k": 64991,
                    "hydrogen_density_cm3": 1.0e8,
                    "electron_fraction_xee": 1.2,
                }
            )
    (root / cap.REPORT_NAME).write_text(
        json.dumps(
            {
                "actual_dsec_runtime_capture": True,
                "capture_kind": "actual_v06472_dsec_heii_row46_complete_source_order_runtime_capture",
                "target_records_match_actual_terms": True,
                "dsec_evaluations_observed": 61,
            }
        )
        + "\n"
    )


def test_verify_accepts_complete_row46_capture(tmp_path: Path) -> None:
    _write_complete_bundle(tmp_path)
    result = cap.verify(tmp_path)
    assert result["result"] == "ACCEPT"
    assert result["records"] == 154
    assert result["matrix_terms"] == 616
    assert result["normalization_row"] == 78


def test_source_row_reconstruction_exact_for_zero_fixture(tmp_path: Path) -> None:
    _write_complete_bundle(tmp_path)
    terms = list(csv.DictReader((tmp_path / cap.TERMS_NAME).open()))
    row = list(csv.DictReader((tmp_path / cap.ROW46_MATRIX_NAME).open()))
    result = audit._source_row_reconstruction(terms, row)
    assert result["all_ieee_exact"]


def test_probe_reconstructs_normalization_when_retained_copy_is_empty(tmp_path: Path) -> None:
    config = {
        "output_dir": str(tmp_path / "out"),
        "target_evaluation": 61,
        "target_full_row": 46,
        "target_inventory": [],
    }
    runtime = tmp_path / "v048714_probe_runtime.py"
    runtime.write_text(cap._PROBE_RUNTIME)
    (tmp_path / "probe_config.json").write_text(json.dumps(config))
    namespace = {"__file__": str(runtime)}
    exec(compile(cap._PROBE_RUNTIME, str(runtime), "exec"), namespace)

    import numpy as np
    from types import SimpleNamespace

    dense = np.arange(9, dtype=float).reshape(3, 3)
    assembly = SimpleNamespace(
        dense_matrix=dense,
        normalized_matrix=np.empty((0, 0), dtype=float),
    )
    helper = namespace["_normalized_after_commit"]
    assert helper(assembly, 2, 3, 3) == dense[1, 2]
    assert helper(assembly, 3, 1, 3) == 1.0
    assert helper(assembly, 3, 3, 3) == 1.0


def test_native_only_type95_self_loop_is_removed_from_original_dsec_substitution() -> None:
    import numpy as np
    candidate = [{
        "contribution_source_position": "7452",
        "record": "1980",
        "role": "forward_gain",
        "data_type": "95",
        "compact_row": "46",
        "compact_column": "46",
        "aj1": "2.5",
        "cj": "3.5",
        "cj2": "4.5",
    }]
    dense = np.zeros((78, 78)); heat = np.zeros_like(dense); heat2 = np.zeros_like(dense)
    dense[45,45] = 2.5; heat[45,45] = 3.5; heat2[45,45] = 4.5
    out_dense, out_heat, out_heat2, replaced, removed = audit._substitute_terms(
        dense, heat, heat2, candidate, {}
    )
    assert replaced == 0
    assert removed == 1
    assert out_dense[45,45] == 0.0
    assert out_heat[45,45] == 0.0
    assert out_heat2[45,45] == 0.0
