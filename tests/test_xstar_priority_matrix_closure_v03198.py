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
    activation = [{
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
    }]
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
    ]
    _write_csv(root / "xstar_priority_basis_expansion_activation_manifest.csv", activation)
    _write_csv(root / "xstar_priority_basis_expansion_compact_basis.csv", compact)
    _write_csv(root / "xstar_priority_basis_expansion_closure_requirements.csv", [{"nionp_current": 5}])
    (root / "xstar_priority_basis_expansion.json").write_text(
        json.dumps({"summary": {"ion": "O VII", "selected_basis_solve_call_id": 219}}),
        encoding="utf-8",
    )


def _matrix_rows(cap: int, rec: int, jkk: int, row: int, col: int) -> list[dict]:
    pairs = [
        ("forward_offdiag", row, col),
        ("reverse_offdiag", col, row),
        ("forward_diag_loss", col, col),
        ("reverse_diag_loss", row, row),
    ]
    return [
        {
            "capture_index": cap,
            "matrix_capture_index": cap * 10 + idx,
            "ml_data": rec,
            "ltyp": 50,
            "lrtyp": 4,
            "insertion_index": idx,
            "insertion_kind": kind,
            "indbi_1": i,
            "indbi_2": j,
            "ajisi_1": 1.0,
            "ajisi_2": 0.0,
            "jkk_ion": jkk,
        }
        for idx, (kind, i, j) in enumerate(pairs, start=1)
    ]


def test_whole_run_latest_selection_excludes_unrelated_element_blocks(tmp_path: Path) -> None:
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
            "jkk_ion": 40,
            "idest1": 3,
            "idest2": 2,
            "ans1": 1.0,
            "ans2": 2.0,
        },
        {
            "capture_index": 201,
            "ml_data": 2001,
            "ltyp": 56,
            "lrtyp": 3,
            "jkk_ion": 10,
            "idest1": 3,
            "idest2": 2,
            "ans1": 1.0,
            "ans2": 2.0,
        },
    ])
    rows = _matrix_rows(101, 1001, 40, 3, 2)
    rows.extend(_matrix_rows(201, 2001, 10, 3, 2))
    _write_csv(matrix, rows)

    audit = build_priority_matrix_closure_audit(
        priority_basis_expansion=source,
        ucalc_probe_csv=ucalc,
        matrix_probe_csv=matrix,
        occurrence_rank=-1,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.198"
    assert summary["element_jkk_ions"] == "40;50"
    assert summary["n_all_elements_ucalc_records_selected_at_occurrence"] == 2
    assert summary["n_selected_element_ucalc_records_at_occurrence"] == 1
    assert summary["n_excluded_non_element_ucalc_records"] == 1
    assert summary["n_fortran_matrix_rows_loaded"] == 4
    assert summary["n_unmapped_matrix_endpoints"] == 0
    assert summary["fortran_priority_subset_matrix_manifest_ready"] is True
    assert {row["jkk_ion"] for row in audit["element_filter_rows"]} == {10, 40}
