from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.xstar_priority_native_type53_integration import (
    build_priority_native_type53_integration_audit,
    write_priority_native_type53_integration_audit,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)


def _term(capture: int, record: int, ltyp: int, lrtyp: int, family: str,
          kind: str, row: int, col: int, coeff: float, pop: float,
          provenance: str) -> dict:
    return {
        "capture_index": capture, "record": record, "ltyp": ltyp, "lrtyp": lrtyp,
        "family_key": family, "insertion_kind": kind,
        "compact_row_ipmat2": row, "compact_col_ipmat2": col,
        "partition": "selected_internal" if col in {1, 2} else "fixed_external",
        "coefficient_provenance": provenance,
        "probe_coefficient_s^-1": coeff,
        "hybrid_coefficient_s^-1": coeff,
        "column_population": pop,
        "probe_population_weighted_contribution": coeff * pop,
        "hybrid_population_weighted_contribution": coeff * pop,
    }


def _make_parent(root: Path) -> None:
    root.mkdir()
    # x1=.3, x2=.4, external x3=.5, x4=.2
    # row1: -4*.3 + 1*.4 + 1.2*.5 + 1*.2 = 0
    # row2:  2*.3 - 2*.4 + .4*.5 + 0*.2 = 0
    rows = [
        _term(1, 101, 51, 3, "type51_rate3", "forward_diag_loss", 1, 1, -4, .3, "native_type51"),
        _term(2, 501, 50, 4, "type50_rate4", "reverse_offdiag", 1, 2, 1, .4, "native_type50"),
        _term(3, 5301, 53, 7, "type53_rate7", "forward_offdiag", 1, 3, 1.2, .5, "fortran_probe_non_type50_type71"),
        _term(4, 701, 71, 14, "type71_rate14", "reverse_offdiag", 1, 4, 1, .2, "native_type71"),
        _term(5, 102, 51, 3, "type51_rate3", "forward_offdiag", 2, 1, 2, .3, "native_type51"),
        _term(6, 5302, 53, 7, "type53_rate7", "reverse_diag_loss", 2, 2, -2, .4, "fortran_probe_non_type50_type71"),
        _term(7, 503, 50, 4, "type50_rate4", "reverse_offdiag", 2, 3, .4, .5, "native_type50"),
        _term(8, 9901, 99, 7, "type99_rate7", "forward_offdiag", 2, 4, 0, .2, "fortran_probe_non_type50_type71"),
    ]
    _write_csv(root / "xstar_priority_native_type50_type71_integration_audit_term_replacements.csv", rows)
    _write_csv(root / "xstar_priority_native_type50_type71_integration_audit_row_balance.csv", [
        {"xstar_ipmat2_index": 1, "physical_roles": "row1", "captured_population": .3},
        {"xstar_ipmat2_index": 2, "physical_roles": "row2", "captured_population": .4},
    ])
    _write_csv(root / "xstar_priority_native_type50_type71_integration_audit_solve_comparison.csv", [
        {"xstar_ipmat2_index": 1, "physical_roles": "row1", "captured_xstar_population": .3,
         "hybrid_native_type51_type50_type71_conditional_population": .3},
        {"xstar_ipmat2_index": 2, "physical_roles": "row2", "captured_xstar_population": .4,
         "hybrid_native_type51_type50_type71_conditional_population": .4},
    ])
    (root / "xstar_priority_native_type50_type71_integration_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII", "selected_basis_solve_call_id": 219,
            "selection": "latest-per-record", "occurrence_rank": -1,
            "population_stage": "after",
            "native_type50_type71_selected_system_integration_ready": True,
        }
    }), encoding="utf-8")


def _make_parity(root: Path, omit: int | None = None) -> None:
    root.mkdir()
    rows = []
    for capture, record, kind, row, col, coeff in [
        (3, 5301, "forward_offdiag", 1, 3, 1.2),
        (6, 5302, "reverse_diag_loss", 2, 2, -2.0),
    ]:
        if record == omit:
            continue
        rows.append({
            "family_key": "type53_rate7", "capture_index": capture, "record": record,
            "insertion_kind": kind, "compact_row_ipmat2": row,
            "compact_col_ipmat2": col, "row_endpoint_selected": True,
            "col_endpoint_selected": col in {1, 2},
            "selected_system_partition": "selected_internal" if col in {1, 2} else "fixed_external",
            "native_expected_ajisi_1_s^-1": coeff,
            "matrix_term_match": True, "record_rate_parity_status": "pass",
            "relative_difference": 0.0,
        })
    rows.append({
        "family_key": "type53_rate7", "capture_index": 3, "record": 5301,
        "insertion_kind": "forward_diag_loss", "compact_row_ipmat2": 9,
        "compact_col_ipmat2": 9, "row_endpoint_selected": False,
        "col_endpoint_selected": False, "selected_system_partition": "external_row_out_of_scope",
        "native_expected_ajisi_1_s^-1": -1.2,
        "matrix_term_match": True, "record_rate_parity_status": "pass",
        "relative_difference": 0.0,
    })
    _write_csv(root / "xstar_type53_live_native_parity_audit_matrix_terms.csv", rows)
    (root / "xstar_type53_live_native_parity_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII", "native_type53_selected_system_parity_ready": omit is None,
            "type53_scale44_resolved_by_exact_live_state": omit is None,
        }
    }), encoding="utf-8")


def test_type53_integration_replaces_internal_and_external_terms(tmp_path: Path) -> None:
    parent, parity = tmp_path / "parent", tmp_path / "parity"
    _make_parent(parent); _make_parity(parity)
    audit = build_priority_native_type53_integration_audit(
        priority_native_type50_type71_integration_audit=parent,
        type53_live_native_parity_audit=parity,
        relative_population_tolerance=1e-12,
        replacement_population_delta_tolerance=1e-12,
        relative_row_residual_tolerance=1e-12,
    )
    s = audit["summary"]
    assert s["audit_version"] == "v0.3.209"
    assert s["n_type53_balance_terms"] == 2
    assert s["n_type53_terms_replaced_with_native"] == 2
    assert s["n_type53_terms_unmatched"] == 0
    assert s["native_type53_selected_system_integration_ready"] is True
    assert s["native_type53_external_rhs_ready"] is True
    assert s["native_type51_type50_type71_type53_selected_system_integration_ready"] is True
    assert s["n_remaining_probe_backed_terms"] == 1
    assert s["native_priority_subset_matrix_closure_ready"] is False
    assert s["type53_scale44_status"] == "resolved_by_exact_live_state_no_empirical_factor"
    assert s["max_abs_hybrid_vs_parent_native_type50_type71_relative_population_difference"] < 1e-14
    paths = write_priority_native_type53_integration_audit(tmp_path / "out", audit)
    assert all(Path(v).exists() for v in paths.values())


def test_type53_integration_flags_missing_term(tmp_path: Path) -> None:
    parent, parity = tmp_path / "parent", tmp_path / "parity"
    _make_parent(parent); _make_parity(parity, omit=5301)
    audit = build_priority_native_type53_integration_audit(
        priority_native_type50_type71_integration_audit=parent,
        type53_live_native_parity_audit=parity,
    )
    s = audit["summary"]
    assert s["n_type53_terms_replaced_with_native"] == 1
    assert s["n_type53_terms_unmatched"] == 1
    assert s["native_type53_selected_system_integration_ready"] is False
    assert s["native_type51_type50_type71_type53_selected_system_integration_ready"] is False
