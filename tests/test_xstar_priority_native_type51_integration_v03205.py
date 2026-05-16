from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.xstar_priority_native_type51_integration import (
    build_priority_native_type51_integration_audit,
    write_priority_native_type51_integration_audit,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
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


def _make_balance(root: Path) -> None:
    root.mkdir()
    # Selected equations with x3 fixed at 0.5:
    # -3*x1 + x2 + x3 = 0
    #  2*x1 -4*x2 + 2*x3 = 0
    # Exact selected solution: x1=0.3, x2=0.4.
    rows = [
        {
            "capture_index": 11, "ml_data": 101, "ltyp": 51, "lrtyp": 3,
            "family_key": "type51_rate3", "insertion_kind": "forward_diag_loss",
            "compact_row_ipmat2": 1, "compact_col_ipmat2": 1,
            "ajisi_1_s^-1": -3.0, "population_weighted_contribution": -0.9,
        },
        {
            "capture_index": 12, "ml_data": 201, "ltyp": 53, "lrtyp": 7,
            "family_key": "type53_rate7", "insertion_kind": "forward_offdiag",
            "compact_row_ipmat2": 1, "compact_col_ipmat2": 2,
            "ajisi_1_s^-1": 1.0, "population_weighted_contribution": 0.4,
        },
        {
            "capture_index": 13, "ml_data": 301, "ltyp": 50, "lrtyp": 4,
            "family_key": "type50_rate4", "insertion_kind": "forward_offdiag",
            "compact_row_ipmat2": 1, "compact_col_ipmat2": 3,
            "ajisi_1_s^-1": 1.0, "population_weighted_contribution": 0.5,
        },
        {
            "capture_index": 14, "ml_data": 102, "ltyp": 51, "lrtyp": 3,
            "family_key": "type51_rate3", "insertion_kind": "forward_offdiag",
            "compact_row_ipmat2": 2, "compact_col_ipmat2": 1,
            "ajisi_1_s^-1": 2.0, "population_weighted_contribution": 0.6,
        },
        {
            "capture_index": 15, "ml_data": 103, "ltyp": 51, "lrtyp": 3,
            "family_key": "type51_rate3", "insertion_kind": "reverse_diag_loss",
            "compact_row_ipmat2": 2, "compact_col_ipmat2": 2,
            "ajisi_1_s^-1": -4.0, "population_weighted_contribution": -1.6,
        },
        {
            "capture_index": 16, "ml_data": 302, "ltyp": 50, "lrtyp": 4,
            "family_key": "type50_rate4", "insertion_kind": "forward_offdiag",
            "compact_row_ipmat2": 2, "compact_col_ipmat2": 3,
            "ajisi_1_s^-1": 2.0, "population_weighted_contribution": 1.0,
        },
    ]
    _write_csv(root / "xstar_priority_matrix_balance_audit_record_terms.csv", rows)
    _write_csv(root / "xstar_priority_matrix_balance_audit_population_vector.csv", [
        {"xstar_ipmat2_index": 1, "population": 0.3},
        {"xstar_ipmat2_index": 2, "population": 0.4},
        {"xstar_ipmat2_index": 3, "population": 0.5},
    ])
    _write_csv(root / "xstar_priority_matrix_balance_audit_row_balance.csv", [
        {"xstar_ipmat2_index": 1, "physical_roles": "row1"},
        {"xstar_ipmat2_index": 2, "physical_roles": "row2"},
    ])
    (root / "xstar_priority_matrix_balance_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII",
            "selected_basis_solve_call_id": 219,
            "selection": "latest-per-record",
            "occurrence_rank": -1,
            "population_stage": "after",
            "fortran_priority_subset_row_balance_ready": True,
        }
    }), encoding="utf-8")


def _make_parity(root: Path, *, omit_last: bool = False) -> None:
    root.mkdir()
    selected_row_terms = [
        {
            "capture_index": 11, "record": 101, "insertion_kind": "forward_diag_loss",
            "compact_row_ipmat2": 1, "compact_col_ipmat2": 1,
            "native_expected_ajisi_1_s^-1": -3.0 * (1.0 + 1.0e-8),
            "matrix_term_match": True, "record_parity_status": "pass",
            "relative_difference": 1.0e-8,
        },
        {
            "capture_index": 14, "record": 102, "insertion_kind": "forward_offdiag",
            "compact_row_ipmat2": 2, "compact_col_ipmat2": 1,
            "native_expected_ajisi_1_s^-1": 2.0 * (1.0 + 1.0e-8),
            "matrix_term_match": True, "record_parity_status": "pass",
            "relative_difference": 1.0e-8,
        },
        {
            "capture_index": 15, "record": 103, "insertion_kind": "reverse_diag_loss",
            "compact_row_ipmat2": 2, "compact_col_ipmat2": 2,
            "native_expected_ajisi_1_s^-1": -4.0 * (1.0 + 1.0e-8),
            "matrix_term_match": True, "record_parity_status": "pass",
            "relative_difference": 1.0e-8,
        },
    ]
    if omit_last:
        selected_row_terms = selected_row_terms[:-1]
    # The parity manifest is intentionally broader than the selected-row
    # balance system.  This reciprocal term belongs to an external equation
    # (row 3) with a selected population in its column.  It must be retained
    # as out of scope and must not block selected-system readiness.
    external_row_terms = [
        {
            "capture_index": 11, "record": 101,
            "insertion_kind": "reverse_offdiag",
            "compact_row_ipmat2": 3, "compact_col_ipmat2": 1,
            "row_endpoint_selected": False, "col_endpoint_selected": True,
            "native_expected_ajisi_1_s^-1": 0.25,
            "matrix_term_match": True, "record_parity_status": "pass",
            "relative_difference": 1.0e-8,
        },
    ]
    terms = selected_row_terms + external_row_terms
    _write_csv(root / "xstar_type51_native_parity_audit_matrix_terms.csv", terms)
    (root / "xstar_type51_native_parity_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII",
            "selected_basis_solve_call_id": 219,
            "selection": "latest-per-record",
            "occurrence_rank": -1,
            "native_type51_record_rate_parity_ready": True,
            "native_type51_compact_matrix_parity_ready": True,
            "native_type51_internal_block_assembly_ready": True,
        }
    }), encoding="utf-8")


def test_native_type51_integration_replaces_all_terms_and_resolves(tmp_path: Path) -> None:
    balance = tmp_path / "balance"
    parity = tmp_path / "parity"
    _make_balance(balance)
    _make_parity(parity)

    audit = build_priority_native_type51_integration_audit(
        priority_matrix_balance_audit=balance,
        type51_native_parity_audit=parity,
        relative_population_tolerance=1.0e-6,
        replacement_population_delta_tolerance=1.0e-6,
        relative_row_residual_tolerance=1.0e-6,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.205"
    assert summary["n_type51_balance_terms"] == 3
    assert summary["n_type51_terms_replaced_with_native"] == 3
    assert summary["n_type51_terms_unmatched"] == 0
    assert summary["n_non_type51_probe_backed_terms"] == 3
    assert summary["n_selected_rows_touched_by_native_type51"] == 2
    assert summary["hybrid_matrix_rank"] == 2
    assert summary["n_type51_parity_terms"] == 4
    assert summary["n_type51_parity_terms_in_selected_row_scope"] == 3
    assert summary["n_type51_parity_terms_external_row_out_of_scope"] == 1
    assert summary["n_type51_parity_terms_used"] == 3
    assert summary["n_type51_parity_terms_unused"] == 1
    assert summary["n_type51_parity_terms_unused_in_selected_row_scope"] == 0
    assert summary["n_type51_parity_terms_used_outside_selected_row_scope"] == 0
    assert summary["native_type51_all_selected_row_terms_replaced"] is True
    assert summary["native_type51_all_parity_manifest_terms_accounted_for"] is True
    assert summary["native_type51_all_touching_terms_replaced"] is False
    assert summary["native_type51_external_row_terms_required_for_selected_system"] is False
    assert summary["native_type51_selected_system_integration_ready"] is True
    assert summary["native_priority_subset_matrix_closure_ready"] is False
    assert summary["production_expanded_compact_solver_changed"] is False
    assert summary["max_abs_hybrid_vs_all_probe_relative_population_difference"] < 1.0e-7

    output = tmp_path / "output"
    paths = write_priority_native_type51_integration_audit(output, audit)
    assert all(path.exists() for path in paths.values())
    parity_scope = list(csv.DictReader(paths["parity_scope_csv"].open()))
    assert sum(row["scope_status"] == "selected_row_scope_used" for row in parity_scope) == 3
    assert sum(row["scope_status"] == "external_row_out_of_scope" for row in parity_scope) == 1


def test_native_type51_integration_flags_missing_native_term(tmp_path: Path) -> None:
    balance = tmp_path / "balance"
    parity = tmp_path / "parity"
    _make_balance(balance)
    _make_parity(parity, omit_last=True)

    audit = build_priority_native_type51_integration_audit(
        priority_matrix_balance_audit=balance,
        type51_native_parity_audit=parity,
    )
    summary = audit["summary"]
    assert summary["n_type51_terms_replaced_with_native"] == 2
    assert summary["n_type51_terms_unmatched"] == 1
    assert summary["n_type51_parity_terms_unused_in_selected_row_scope"] == 0
    assert summary["native_type51_all_selected_row_terms_replaced"] is False
    assert summary["native_type51_all_parity_manifest_terms_accounted_for"] is False
    assert summary["native_type51_all_touching_terms_replaced"] is False
    assert summary["native_type51_selected_system_integration_ready"] is False
