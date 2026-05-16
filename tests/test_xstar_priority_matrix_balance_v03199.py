from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.xstar_priority_matrix_balance import build_priority_matrix_balance_audit


def _write(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_priority_row_balance_passes_for_exact_two_state_equilibrium(tmp_path: Path) -> None:
    closure = tmp_path / "closure"
    parity = tmp_path / "parity"
    closure.mkdir(); parity.mkdir()
    _write(closure / "xstar_priority_matrix_closure_audit_selected_row_summary.csv", [
        {"xstar_ipmat2_index": 2, "activation_order": 1, "physical_roles": "population_role:1:2"},
    ])
    # Row 2: +2*x1 -1*x2 = 0 for x=(1/3, 2/3).
    _write(closure / "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv", [
        {"capture_index": 1, "ml_data": 10, "ltyp": 50, "lrtyp": 4,
         "insertion_kind": "reverse_offdiag", "compact_row_ipmat2": 2,
         "compact_col_ipmat2": 1, "ajisi_1": 2.0},
        {"capture_index": 1, "ml_data": 10, "ltyp": 50, "lrtyp": 4,
         "insertion_kind": "reverse_diag_loss", "compact_row_ipmat2": 2,
         "compact_col_ipmat2": 2, "ajisi_1": -1.0},
    ])
    (closure / "xstar_priority_matrix_closure_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII", "selected_basis_solve_call_id": 219,
            "selection": "latest-per-record", "occurrence_rank": -1,
            "fortran_priority_subset_matrix_manifest_ready": True,
        }
    }), encoding="utf-8")
    _write(parity / "xstar_population_closure_parity_audit_overlap_rows.csv", [
        {"xstar_ipmat2_index": 1, "xstar_before_population": 0.3, "xstar_after_population": 1/3},
    ])
    _write(parity / "xstar_population_closure_parity_audit_unmapped_xstar_rows.csv", [
        {"xstar_ipmat2_index": 2, "xstar_before_population": 0.7, "xstar_after_population": 2/3},
    ])
    (parity / "xstar_population_closure_parity_audit.json").write_text(json.dumps({
        "summary": {"selected_solve_call_id": 219, "occurrence_rank": 73, "ion": "O VII"}
    }), encoding="utf-8")

    audit = build_priority_matrix_balance_audit(
        priority_matrix_closure_audit=closure,
        population_closure_parity_audit=parity,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.199"
    assert summary["n_selected_rows_passing_balance"] == 1
    assert summary["fortran_priority_subset_row_balance_ready"] is True
    assert abs(audit["row_balance_rows"][0]["net_population_weighted_residual"]) < 1e-14


def test_priority_row_balance_flags_incomplete_population_vector(tmp_path: Path) -> None:
    closure = tmp_path / "closure"; parity = tmp_path / "parity"
    closure.mkdir(); parity.mkdir()
    _write(closure / "xstar_priority_matrix_closure_audit_selected_row_summary.csv", [
        {"xstar_ipmat2_index": 2},
    ])
    _write(closure / "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv", [
        {"compact_row_ipmat2": 2, "compact_col_ipmat2": 3, "ajisi_1": 1.0, "ltyp": 50, "lrtyp": 4},
    ])
    (closure / "xstar_priority_matrix_closure_audit.json").write_text(json.dumps({
        "summary": {"fortran_priority_subset_matrix_manifest_ready": True}
    }), encoding="utf-8")
    _write(parity / "xstar_population_closure_parity_audit_overlap_rows.csv", [
        {"xstar_ipmat2_index": 2, "xstar_after_population": 1.0},
    ])
    _write(parity / "xstar_population_closure_parity_audit_unmapped_xstar_rows.csv", [])
    audit = build_priority_matrix_balance_audit(
        priority_matrix_closure_audit=closure,
        population_closure_parity_audit=parity,
    )
    assert audit["summary"]["n_missing_population_columns"] == 1
    assert audit["summary"]["fortran_priority_subset_row_balance_ready"] is False
