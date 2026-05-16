from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.xstar_priority_matrix_closure import (
    build_priority_matrix_closure_audit,
    write_priority_matrix_closure_audit,
)


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


def _expansion_fixture(root: Path) -> None:
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
    closure = [{"nionp_current": 5, "selected_xstar_ipmat2_indices": "10;11"}]
    _write_csv(root / "xstar_priority_basis_expansion_activation_manifest.csv", activation)
    _write_csv(root / "xstar_priority_basis_expansion_compact_basis.csv", compact)
    _write_csv(root / "xstar_priority_basis_expansion_closure_requirements.csv", closure)
    (root / "xstar_priority_basis_expansion.json").write_text(
        json.dumps({"summary": {"ion": "O VII", "selected_basis_solve_call_id": 219}}),
        encoding="utf-8",
    )


def _probe_fixture(root: Path) -> tuple[Path, Path]:
    ucalc = root / "xstar_ucalc_record_probe.csv"
    matrix = root / "xstar_calc_hmc_ion_matrix_probe.csv"
    urows = []
    for occurrence, cap in enumerate((101, 201), start=1):
        urows.append({
            "capture_index": cap, "ml_data": 1001, "ltyp": 50, "lrtyp": 4,
            "jkk_ion": 50, "idest1": 1, "idest2": 2,
            "idest3": 0, "idest4": 0, "ans1": occurrence * 2.0, "ans2": occurrence * 3.0,
            "ans3": 0, "ans4": 0, "ans5": 0, "ans6": 0,
        })
    for occurrence, cap in enumerate((102, 202), start=1):
        urows.append({
            "capture_index": cap, "ml_data": 1002, "ltyp": 53, "lrtyp": 7,
            "jkk_ion": 40, "idest1": 2, "idest2": 3,
            "idest3": 0, "idest4": 0, "ans1": occurrence * 0.5, "ans2": occurrence * 0.25,
            "ans3": 0, "ans4": 0, "ans5": 0, "ans6": 0,
        })
    _write_csv(ucalc, urows)

    mrows = []
    specs = [
        ("forward_offdiag", 2, 1),
        ("reverse_offdiag", 1, 2),
        ("forward_diag_loss", 1, 1),
        ("reverse_diag_loss", 2, 2),
    ]
    for cap, rec, ltyp, jkk in ((201, 1001, 50, 50), (202, 1002, 53, 40)):
        for idx, (kind, row, col) in enumerate(specs, start=1):
            # For jkk=40, local level 3 is the selected parent role. Shift the
            # pair so the matrix terms touch compact row 10.
            if jkk == 40:
                row, col = ({1: (3, 2), 2: (2, 3), 3: (2, 2), 4: (3, 3)})[idx]
            mrows.append({
                "capture_index": cap, "matrix_capture_index": cap * 10 + idx,
                "ml_data": rec, "ltyp": ltyp, "lrtyp": 4 if ltyp == 50 else 7,
                "insertion_index": idx, "insertion_kind": kind,
                "indbi_1": row, "indbi_2": col, "ajisi_1": 1.0, "ajisi_2": 0.0,
                "cjisi": 0.0, "cjisi2": 0.0, "idest1": 1, "idest2": 2,
                "llo": 1, "lup": 2, "e1_eV": 0.0, "e2_eV": 1.0,
            })
    _write_csv(matrix, mrows)
    return ucalc, matrix


def test_priority_matrix_manifest_maps_shared_roles(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _expansion_fixture(source)
    ucalc, matrix = _probe_fixture(tmp_path)
    audit = build_priority_matrix_closure_audit(
        priority_basis_expansion=source,
        ucalc_probe_csv=ucalc,
        matrix_probe_csv=matrix,
        occurrence_rank=2,
    )
    summary = audit["summary"]
    assert summary["n_selected_compact_rows"] == 2
    assert summary["n_selected_physical_roles"] == 3
    assert summary["n_selected_ucalc_records"] == 2
    assert summary["n_selected_records_with_four_matrix_rows"] == 2
    assert summary["n_fortran_matrix_rows_loaded"] == 8
    assert summary["n_unmapped_matrix_endpoints"] == 0
    assert summary["n_selected_rows_with_fortran_records"] == 2
    assert summary["fortran_priority_subset_matrix_manifest_ready"] is True
    shared_roles = [row for row in audit["role_rows"] if row["xstar_ipmat2_index"] == 10]
    assert {row["role_kind"] for row in shared_roles} == {"population_role", "parent_continuum_role"}
    assert {row["family_key"] for row in audit["family_rows"]} == {"type50_rate4", "type53_rate7"}


def test_role_manifest_without_raw_probes(tmp_path: Path) -> None:
    _expansion_fixture(tmp_path)
    audit = build_priority_matrix_closure_audit(priority_basis_expansion=tmp_path)
    summary = audit["summary"]
    assert summary["status"] == "priority_matrix_closure_role_manifest_ready_probe_csvs_not_loaded"
    assert summary["priority_role_manifest_ready"] is True
    assert summary["fortran_priority_subset_matrix_manifest_ready"] is False
    assert summary["n_selected_physical_roles"] == 3


def test_writer_creates_products(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _expansion_fixture(source)
    audit = build_priority_matrix_closure_audit(priority_basis_expansion=source)
    paths = write_priority_matrix_closure_audit(tmp_path / "out", audit)
    for path in paths.values():
        assert Path(path).exists()
