from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.xstar_priority_conditional_solve import (
    build_priority_conditional_solve_audit,
)


def _write(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        fields = ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_conditional_solve_recovers_selected_populations(tmp_path: Path) -> None:
    root = tmp_path / "balance"
    root.mkdir()
    # Selected equations with x3 fixed at 0.5:
    # -3*x1 + x2 + 1*x3 = 0
    #  2*x1 -4*x2 + 2*x3 = 0
    # Exact selected solution is x1=0.3, x2=0.4.
    _write(root / "xstar_priority_matrix_balance_audit_aggregated_matrix_entries.csv", [
        {"compact_row_ipmat2": 1, "compact_col_ipmat2": 1, "coefficient_sum_s^-1": -3.0, "n_record_terms": 1},
        {"compact_row_ipmat2": 1, "compact_col_ipmat2": 2, "coefficient_sum_s^-1": 1.0, "n_record_terms": 1},
        {"compact_row_ipmat2": 1, "compact_col_ipmat2": 3, "coefficient_sum_s^-1": 1.0, "n_record_terms": 1},
        {"compact_row_ipmat2": 2, "compact_col_ipmat2": 1, "coefficient_sum_s^-1": 2.0, "n_record_terms": 1},
        {"compact_row_ipmat2": 2, "compact_col_ipmat2": 2, "coefficient_sum_s^-1": -4.0, "n_record_terms": 1},
        {"compact_row_ipmat2": 2, "compact_col_ipmat2": 3, "coefficient_sum_s^-1": 2.0, "n_record_terms": 1},
    ])
    _write(root / "xstar_priority_matrix_balance_audit_population_vector.csv", [
        {"xstar_ipmat2_index": 1, "population": 0.3},
        {"xstar_ipmat2_index": 2, "population": 0.4},
        {"xstar_ipmat2_index": 3, "population": 0.5},
    ])
    _write(root / "xstar_priority_matrix_balance_audit_row_balance.csv", [
        {"xstar_ipmat2_index": 1, "physical_roles": "row1"},
        {"xstar_ipmat2_index": 2, "physical_roles": "row2"},
    ])
    _write(root / "xstar_priority_matrix_balance_audit_record_terms.csv", [
        {"compact_row_ipmat2": 1, "compact_col_ipmat2": 3, "family_key": "type50_rate4", "population_weighted_contribution": 0.5},
        {"compact_row_ipmat2": 2, "compact_col_ipmat2": 3, "family_key": "type53_rate7", "population_weighted_contribution": 1.0},
    ])
    (root / "xstar_priority_matrix_balance_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII", "selected_basis_solve_call_id": 219,
            "selection": "latest-per-record", "occurrence_rank": -1,
            "population_stage": "after",
            "fortran_priority_subset_row_balance_ready": True,
        }
    }), encoding="utf-8")

    audit = build_priority_conditional_solve_audit(
        priority_matrix_balance_audit=root,
        relative_population_tolerance=1.0e-12,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.201"
    assert summary["matrix_rank"] == 2
    assert summary["fortran_priority_subset_conditional_solve_ready"] is True
    solved = {row["xstar_ipmat2_index"]: row["conditional_solved_population"] for row in audit["solve_comparison_rows"]}
    assert abs(solved[1] - 0.3) < 1.0e-13
    assert abs(solved[2] - 0.4) < 1.0e-13


def test_conditional_solve_flags_rank_deficiency(tmp_path: Path) -> None:
    root = tmp_path / "balance"
    root.mkdir()
    _write(root / "xstar_priority_matrix_balance_audit_aggregated_matrix_entries.csv", [
        {"compact_row_ipmat2": 1, "compact_col_ipmat2": 1, "coefficient_sum_s^-1": -1.0},
        {"compact_row_ipmat2": 1, "compact_col_ipmat2": 2, "coefficient_sum_s^-1": 1.0},
        {"compact_row_ipmat2": 2, "compact_col_ipmat2": 1, "coefficient_sum_s^-1": -2.0},
        {"compact_row_ipmat2": 2, "compact_col_ipmat2": 2, "coefficient_sum_s^-1": 2.0},
    ])
    _write(root / "xstar_priority_matrix_balance_audit_population_vector.csv", [
        {"xstar_ipmat2_index": 1, "population": 0.5},
        {"xstar_ipmat2_index": 2, "population": 0.5},
    ])
    _write(root / "xstar_priority_matrix_balance_audit_row_balance.csv", [
        {"xstar_ipmat2_index": 1}, {"xstar_ipmat2_index": 2},
    ])
    _write(root / "xstar_priority_matrix_balance_audit_record_terms.csv", [])
    (root / "xstar_priority_matrix_balance_audit.json").write_text(json.dumps({
        "summary": {"fortran_priority_subset_row_balance_ready": True}
    }), encoding="utf-8")

    audit = build_priority_conditional_solve_audit(priority_matrix_balance_audit=root)
    assert audit["summary"]["matrix_rank"] == 1
    assert audit["summary"]["solve_method"] == "row_scaled_numpy_lstsq"
    assert audit["summary"]["fortran_priority_subset_conditional_solve_ready"] is False
