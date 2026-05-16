from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.xstar_priority_matrix_closure import build_priority_matrix_closure_audit


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _expansion(root: Path) -> None:
    activation = [
        {
            "activation_order": 1,
            "xstar_ipmat2_index": 10,
            "proposed_python_global_index": 100,
            "primary_nionp_current": 5,
            "primary_jkk_ion": 50,
            "primary_local_level_index": 1,
            "population_role_nionp": 5,
            "population_role_local_level_index": 1,
            "parent_role_nionp": 4,
            "parent_role_local_level_index": 3,
            "sharing_class": "parent_continuum_shared_with_next_ion_population",
            "xstar_after_population": 0.01,
        },
        {
            "activation_order": 2,
            "xstar_ipmat2_index": 11,
            "proposed_python_global_index": 101,
            "primary_nionp_current": 5,
            "primary_jkk_ion": 50,
            "primary_local_level_index": 2,
            "population_role_nionp": 5,
            "population_role_local_level_index": 2,
            "sharing_class": "single_role",
            "xstar_after_population": 0.001,
        },
    ]
    compact = [
        {
            "xstar_ipmat2_index": 8,
            "primary_nionp_current": 4,
            "primary_jkk_ion": 40,
            "primary_local_level_index": 1,
            "population_role_nionp": 4,
            "population_role_local_level_index": 1,
        },
        {
            "xstar_ipmat2_index": 9,
            "primary_nionp_current": 4,
            "primary_jkk_ion": 40,
            "primary_local_level_index": 2,
            "population_role_nionp": 4,
            "population_role_local_level_index": 2,
        },
        {
            "xstar_ipmat2_index": 10,
            "primary_nionp_current": 5,
            "primary_jkk_ion": 50,
            "primary_local_level_index": 1,
            "population_role_nionp": 5,
            "population_role_local_level_index": 1,
            "parent_role_nionp": 4,
            "parent_role_local_level_index": 3,
        },
        {
            "xstar_ipmat2_index": 11,
            "primary_nionp_current": 5,
            "primary_jkk_ion": 50,
            "primary_local_level_index": 2,
            "population_role_nionp": 5,
            "population_role_local_level_index": 2,
        },
        {
            "xstar_ipmat2_index": 12,
            "primary_nionp_current": 5,
            "primary_jkk_ion": 50,
            "primary_local_level_index": 3,
            "population_role_nionp": 5,
            "population_role_local_level_index": 3,
        },
    ]
    _write_csv(root / "xstar_priority_basis_expansion_activation_manifest.csv", activation)
    _write_csv(root / "xstar_priority_basis_expansion_compact_basis.csv", compact)
    _write_csv(root / "xstar_priority_basis_expansion_closure_requirements.csv", [{"nionp_current": 5}])
    (root / "xstar_priority_basis_expansion.json").write_text(
        json.dumps({"summary": {"ion": "O VII", "selected_basis_solve_call_id": 219}}),
        encoding="utf-8",
    )


def _matrix_rows(cap: int, rec: int, ltyp: int, lrtyp: int, pairs: list[tuple[str, int, int]]) -> list[dict]:
    rows = []
    for idx, (kind, row, col) in enumerate(pairs, start=1):
        rows.append({
            "capture_index": cap,
            "matrix_capture_index": cap * 10 + idx,
            "ml_data": rec,
            "ltyp": ltyp,
            "lrtyp": lrtyp,
            "insertion_index": idx,
            "insertion_kind": kind,
            "indbi_1": row,
            "indbi_2": col,
            "ajisi_1": 1.0,
            "ajisi_2": 0.0,
        })
    return rows


def test_cross_block_indbi_uses_calc_hmc_element_offset(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _expansion(source)
    ucalc = tmp_path / "xstar_ucalc_record_probe.csv"
    matrix = tmp_path / "xstar_calc_hmc_ion_matrix_probe.csv"
    # jkk=40 has compact offset 7.  indbi=4 therefore maps to compact row 11,
    # even though the primary nionp=4 block itself only has rows 8--9.
    _write_csv(ucalc, [{
        "capture_index": 101,
        "ml_data": 1001,
        "ltyp": 53,
        "lrtyp": 7,
        "jkk_ion": 40,
        "idest1": 4,
        "idest2": 3,
        "idest3": 0,
        "idest4": 0,
        "ans1": 1.0,
        "ans2": 2.0,
        "ans3": 0.0,
        "ans4": 0.0,
        "ans5": 0.0,
        "ans6": 0.0,
    }])
    pairs = [
        ("forward_offdiag", 4, 3),
        ("reverse_offdiag", 3, 4),
        ("forward_diag_loss", 3, 3),
        ("reverse_diag_loss", 4, 4),
    ]
    _write_csv(matrix, _matrix_rows(101, 1001, 53, 7, pairs))
    audit = build_priority_matrix_closure_audit(
        priority_basis_expansion=source,
        ucalc_probe_csv=ucalc,
        matrix_probe_csv=matrix,
        occurrence_rank=1,
    )
    summary = audit["summary"]
    assert summary["compact_endpoint_mapping_mode"] == "calc_hmc_element_ipmat2_offset_plus_indbi"
    assert summary["n_unmapped_matrix_endpoints"] == 0
    assert summary["n_selected_rows_with_fortran_matrix_terms"] == 2
    assert summary["fortran_priority_subset_matrix_manifest_ready"] is True
    endpoints = {
        (row["compact_row_ipmat2"], row["compact_col_ipmat2"])
        for row in audit["compact_matrix_rows"]
    }
    assert (11, 10) in endpoints
    assert (10, 11) in endpoints


def test_nonmatrix_ucalc_metadata_does_not_fail_four_row_check(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _expansion(source)
    ucalc = tmp_path / "xstar_ucalc_record_probe.csv"
    matrix = tmp_path / "xstar_calc_hmc_ion_matrix_probe.csv"
    _write_csv(ucalc, [
        {
            "capture_index": 101,
            "ml_data": 1001,
            "ltyp": 50,
            "lrtyp": 4,
            "jkk_ion": 50,
            "idest1": 1,
            "idest2": 2,
            "idest3": 0,
            "idest4": 0,
            "ans1": 1.0,
            "ans2": 2.0,
            "ans3": 0.0,
            "ans4": 0.0,
            "ans5": 0.0,
            "ans6": 0.0,
        },
        {
            "capture_index": 102,
            "ml_data": 1002,
            "ltyp": 6,
            "lrtyp": 13,
            "jkk_ion": 50,
            "idest1": 1,
            "idest2": 0,
            "idest3": 0,
            "idest4": 0,
            "ans1": 0.0,
            "ans2": 0.0,
            "ans3": 0.0,
            "ans4": 0.0,
            "ans5": 0.0,
            "ans6": 0.0,
        },
    ])
    pairs = [
        ("forward_offdiag", 2, 1),
        ("reverse_offdiag", 1, 2),
        ("forward_diag_loss", 1, 1),
        ("reverse_diag_loss", 2, 2),
    ]
    _write_csv(matrix, _matrix_rows(101, 1001, 50, 4, pairs))
    audit = build_priority_matrix_closure_audit(
        priority_basis_expansion=source,
        ucalc_probe_csv=ucalc,
        matrix_probe_csv=matrix,
        occurrence_rank=1,
    )
    summary = audit["summary"]
    assert summary["n_selected_matrix_ucalc_records"] == 1
    assert summary["n_selected_nonmatrix_ucalc_metadata_records"] == 1
    assert summary["n_selected_records_with_expected_matrix_row_count"] == 2
    assert summary["n_selected_records_with_four_matrix_rows"] == 1
    assert summary["fortran_priority_subset_matrix_manifest_ready"] is True
    metadata = audit["nonmatrix_ucalc_rows"]
    assert len(metadata) == 1
    assert metadata[0]["record_manifest_class"] == "nonmatrix_ucalc_metadata"
    assert metadata[0]["expected_fortran_matrix_row_count"] == 0
