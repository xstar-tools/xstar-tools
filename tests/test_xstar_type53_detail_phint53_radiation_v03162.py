from __future__ import annotations

import csv
from pathlib import Path

from xstar_atomic.xstar_matrix_parity import (
    _evaluate_phint53_photoionization_ans1_detail_continuum,
    audit_type53_detail_phint53_radiation,
    write_type53_detail_phint53_radiation_audit,
)


def _write_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def test_detail_phint53_photo_integrand_positive():
    out = _evaluate_phint53_photoionization_ans1_detail_continuum(
        e_ry=[0.0, 1.0],
        sigma_cm2=[1.0e-18, 1.0e-18],
        threshold_eV=100.0,
        epi_eV=[90.0, 100.0, 106.0, 113.605692, 120.0],
        bremsa=[0.0, 2.0e19, 2.0e19, 2.0e19, 0.0],
    )
    assert out["detail_phint53_photo_status"].startswith("evaluated")
    assert out["detail_phint53_photo_ans1_s^-1"] > 0.0
    assert out["detail_phint53_n_intervals_used"] > 0


def test_type53_detail_phint53_audit_missing_run_dir_writes(tmp_path: Path):
    matrix = tmp_path / "xstar_like_element_solver_full_global_matrix_terms.csv"
    adjacent = tmp_path / "xstar_like_element_solver_adjacent_coupling_terms.csv"
    global_index = tmp_path / "xstar_like_element_solver_global_index.csv"
    _write_csv(matrix, [{
        "data_type": "53",
        "record": "10",
        "full_global_component": "type53_phint53_photoionization_kernel",
        "matrix_term_kind": "offdiag_bound_to_continuum_phint53_gain",
        "matrix_role": "M[continuum_or_parent_global_index,bound_global_index]+=phint53_photoionization_rate",
        "full_global_rate_s^-1": "1.25",
        "bound_global_index": "2",
        "continuum_or_parent_global_index": "3",
        "triplet_component": "r",
    }])
    _write_csv(adjacent, [{
        "data_type": "53",
        "record": "10",
        "type53_raw_reals_full": "[0.0, 1.0, 1.0, 1.0]",
        "idest1_guess": "1",
    }])
    _write_csv(global_index, [
        {"global_index": "2", "level_label": "bound", "binding_from_continuum_eV": "100.0", "triplet_component": "r", "is_triplet_upper": "True"},
        {"global_index": "3", "level_label": "continuum", "is_continuum": "True"},
    ])
    audit = audit_type53_detail_phint53_radiation(
        matrix_terms_csv=matrix,
        adjacent_coupling_csv=adjacent,
        global_index_csv=global_index,
        ion="O VII",
        triplet_only=True,
    )
    assert audit["summary"]["n_type53_photoionization_records"] == 1
    assert audit["summary"]["n_detail_phint53_evaluated"] == 0
    assert audit["rows"][0]["classification"] == "detail_phint53_not_evaluated"
    paths = write_type53_detail_phint53_radiation_audit(audit, tmp_path / "out")
    assert Path(paths["records_csv"]).exists()
    assert Path(paths["markdown"]).exists()
