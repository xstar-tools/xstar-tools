from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.xstar_priority_native_type50_type71_integration import (
    build_priority_native_type50_type71_integration_audit,
    write_priority_native_type50_type71_integration_audit,
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


def _parent_term(*, capture: int, record: int, ltyp: int, lrtyp: int,
                 family: str, kind: str, row: int, col: int,
                 coeff: float, population: float, provenance: str) -> dict:
    return {
        "capture_index": capture, "record": record, "ltyp": ltyp, "lrtyp": lrtyp,
        "family_key": family, "insertion_kind": kind,
        "compact_row_ipmat2": row, "compact_col_ipmat2": col,
        "partition": "selected_internal" if col in {1, 2} else "fixed_external",
        "coefficient_provenance": provenance,
        "probe_coefficient_s^-1": coeff,
        "hybrid_coefficient_s^-1": coeff,
        "column_population": population,
        "probe_population_weighted_contribution": coeff * population,
        "hybrid_population_weighted_contribution": coeff * population,
    }


def _make_parent(root: Path) -> None:
    root.mkdir()
    # Captured populations: x1=.3, x2=.4; fixed x3=.5, x4=.2.
    # row1: -4*x1 + 1*x2 + 1.2*x3 + 1*x4 = 0
    # row2:  2*x1 - 2*x2 + .4*x3 = 0
    rows = [
        _parent_term(capture=1, record=101, ltyp=51, lrtyp=3,
                     family="type51_rate3", kind="forward_diag_loss",
                     row=1, col=1, coeff=-4.0, population=.3, provenance="native_type51"),
        _parent_term(capture=2, record=501, ltyp=50, lrtyp=4,
                     family="type50_rate4", kind="reverse_offdiag",
                     row=1, col=2, coeff=1.0, population=.4, provenance="fortran_probe"),
        _parent_term(capture=3, record=502, ltyp=50, lrtyp=4,
                     family="type50_rate4", kind="reverse_offdiag",
                     row=1, col=3, coeff=1.2, population=.5, provenance="fortran_probe"),
        _parent_term(capture=4, record=701, ltyp=71, lrtyp=14,
                     family="type71_rate14", kind="reverse_offdiag",
                     row=1, col=4, coeff=1.0, population=.2, provenance="fortran_probe"),
        _parent_term(capture=5, record=102, ltyp=51, lrtyp=3,
                     family="type51_rate3", kind="forward_offdiag",
                     row=2, col=1, coeff=2.0, population=.3, provenance="native_type51"),
        _parent_term(capture=6, record=702, ltyp=71, lrtyp=14,
                     family="type71_rate14", kind="reverse_diag_loss",
                     row=2, col=2, coeff=-2.0, population=.4, provenance="fortran_probe"),
        _parent_term(capture=7, record=503, ltyp=50, lrtyp=4,
                     family="type50_rate4", kind="reverse_offdiag",
                     row=2, col=3, coeff=.4, population=.5, provenance="fortran_probe"),
        # Preserve one other family so complete native closure remains false.
        _parent_term(capture=8, record=801, ltyp=53, lrtyp=7,
                     family="type53_rate7", kind="forward_offdiag",
                     row=2, col=4, coeff=0.0, population=.2, provenance="fortran_probe"),
    ]
    _write_csv(root / "xstar_priority_native_type51_integration_audit_term_replacements.csv", rows)
    _write_csv(root / "xstar_priority_native_type51_integration_audit_row_balance.csv", [
        {"xstar_ipmat2_index": 1, "physical_roles": "row1", "captured_population": .3},
        {"xstar_ipmat2_index": 2, "physical_roles": "row2", "captured_population": .4},
    ])
    _write_csv(root / "xstar_priority_native_type51_integration_audit_solve_comparison.csv", [
        {"xstar_ipmat2_index": 1, "physical_roles": "row1", "captured_xstar_population": .3,
         "hybrid_native_type51_conditional_population": .3},
        {"xstar_ipmat2_index": 2, "physical_roles": "row2", "captured_xstar_population": .4,
         "hybrid_native_type51_conditional_population": .4},
    ])
    (root / "xstar_priority_native_type51_integration_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII", "selected_basis_solve_call_id": 219,
            "selection": "latest-per-record", "occurrence_rank": -1,
            "population_stage": "after",
            "native_type51_selected_system_integration_ready": True,
        }
    }), encoding="utf-8")


def _make_parity(root: Path, *, omit_record: int | None = None) -> None:
    root.mkdir()
    selected_terms = [
        ("type50_rate4", 2, 501, "reverse_offdiag", 1, 2, 1.0),
        ("type50_rate4", 3, 502, "reverse_offdiag", 1, 3, 1.2),
        ("type50_rate4", 7, 503, "reverse_offdiag", 2, 3, .4),
        ("type71_rate14", 4, 701, "reverse_offdiag", 1, 4, 1.0),
        ("type71_rate14", 6, 702, "reverse_diag_loss", 2, 2, -2.0),
    ]
    rows = []
    for family, capture, record, kind, row, col, value in selected_terms:
        if record == omit_record:
            continue
        rows.append({
            "family_key": family, "capture_index": capture, "record": record,
            "insertion_kind": kind, "compact_row_ipmat2": row,
            "compact_col_ipmat2": col, "row_endpoint_selected": True,
            "col_endpoint_selected": col in {1, 2},
            "selected_system_partition": "selected_internal" if col in {1, 2} else "fixed_external",
            "native_expected_ajisi_1_s^-1": value,
            "matrix_term_match": True, "record_parity_status": "pass",
            "relative_difference": 0.0,
        })
    # Both families retain one reciprocal external-row insertion for future
    # expanded-system work. They must be accounted for but not consumed here.
    rows.extend([
        {"family_key": "type50_rate4", "capture_index": 2, "record": 501,
         "insertion_kind": "forward_offdiag", "compact_row_ipmat2": 9,
         "compact_col_ipmat2": 1, "row_endpoint_selected": False,
         "col_endpoint_selected": True, "selected_system_partition": "external_row_out_of_scope",
         "native_expected_ajisi_1_s^-1": 0.1, "matrix_term_match": True,
         "record_parity_status": "pass", "relative_difference": 0.0},
        {"family_key": "type71_rate14", "capture_index": 4, "record": 701,
         "insertion_kind": "forward_offdiag", "compact_row_ipmat2": 10,
         "compact_col_ipmat2": 1, "row_endpoint_selected": False,
         "col_endpoint_selected": True, "selected_system_partition": "external_row_out_of_scope",
         "native_expected_ajisi_1_s^-1": 0.0, "matrix_term_match": True,
         "record_parity_status": "pass", "relative_difference": 0.0},
    ])
    _write_csv(root / "xstar_type50_type71_native_parity_audit_matrix_terms.csv", rows)
    (root / "xstar_type50_type71_native_parity_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII", "selected_basis_solve_call_id": 219,
            "selection": "latest-per-record", "occurrence_rank": -1,
            "native_type50_selected_system_parity_ready": omit_record not in {501, 502, 503},
            "native_type71_selected_system_parity_ready": omit_record not in {701, 702},
            "native_type50_type71_selected_system_parity_ready": omit_record is None,
        }
    }), encoding="utf-8")


def test_type50_type71_integration_replaces_internal_and_external_terms(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parity = tmp_path / "parity"
    _make_parent(parent)
    _make_parity(parity)
    audit = build_priority_native_type50_type71_integration_audit(
        priority_native_type51_integration_audit=parent,
        type50_type71_native_parity_audit=parity,
        relative_population_tolerance=1.0e-12,
        replacement_population_delta_tolerance=1.0e-12,
        relative_row_residual_tolerance=1.0e-12,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.206"
    assert summary["n_type50_balance_terms"] == 3
    assert summary["n_type50_terms_replaced_with_native"] == 3
    assert summary["n_type50_terms_unmatched"] == 0
    assert summary["n_type71_balance_terms"] == 2
    assert summary["n_type71_terms_replaced_with_native"] == 2
    assert summary["n_type71_terms_unmatched"] == 0
    assert summary["native_type50_selected_system_integration_ready"] is True
    assert summary["native_type71_selected_system_integration_ready"] is True
    assert summary["native_type50_external_rhs_ready"] is True
    assert summary["native_type71_external_rhs_ready"] is True
    assert summary["native_type50_type71_external_rhs_ready"] is True
    assert summary["native_type50_type71_selected_system_integration_ready"] is True
    assert summary["n_remaining_probe_backed_terms"] == 1
    assert summary["native_priority_subset_matrix_closure_ready"] is False
    assert summary["production_expanded_compact_solver_changed"] is False
    assert summary["max_abs_hybrid_vs_parent_native_type51_relative_population_difference"] < 1.0e-14

    paths = write_priority_native_type50_type71_integration_audit(tmp_path / "out", audit)
    assert all(path.exists() for path in paths.values())
    scopes = list(csv.DictReader(paths["parity_scope_csv"].open()))
    assert sum(r["scope_status"] == "selected_row_scope_used" for r in scopes) == 5
    assert sum(r["scope_status"] == "external_row_out_of_scope" for r in scopes) == 2


def test_type50_type71_integration_flags_missing_selected_term(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    parity = tmp_path / "parity"
    _make_parent(parent)
    _make_parity(parity, omit_record=503)
    audit = build_priority_native_type50_type71_integration_audit(
        priority_native_type51_integration_audit=parent,
        type50_type71_native_parity_audit=parity,
    )
    summary = audit["summary"]
    assert summary["n_type50_terms_replaced_with_native"] == 2
    assert summary["n_type50_terms_unmatched"] == 1
    assert summary["native_type50_selected_system_integration_ready"] is False
    assert summary["native_type50_type71_selected_system_integration_ready"] is False
