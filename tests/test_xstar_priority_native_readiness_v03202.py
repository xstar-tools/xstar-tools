from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.xstar_priority_native_readiness import (
    build_priority_native_readiness_audit,
    write_priority_native_readiness_audit,
)


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_priority_native_readiness_ranks_internal_and_external(tmp_path: Path) -> None:
    cond = tmp_path / "cond"
    cond.mkdir()
    (cond / "xstar_priority_conditional_solve_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII",
            "selected_basis_solve_call_id": 219,
            "selected_xstar_ipmat2_indices": "79;80",
            "n_selected_compact_rows": 2,
            "fortran_priority_subset_conditional_solve_ready": True,
        }
    }), encoding="utf-8")
    _write_csv(cond / "xstar_priority_conditional_solve_audit_solve_comparison.csv", [
        {"xstar_ipmat2_index": 79, "physical_roles": "a", "captured_xstar_population": 1e-3},
        {"xstar_ipmat2_index": 80, "physical_roles": "b", "captured_xstar_population": 2e-3},
    ])
    _write_csv(cond / "xstar_priority_conditional_solve_audit_external_rhs_family_contributions.csv", [
        {"xstar_ipmat2_index": 79, "family_key": "type50_rate4", "n_record_terms": 2, "external_population_weighted_sum": 9.0},
        {"xstar_ipmat2_index": 79, "family_key": "type71_rate14", "n_record_terms": 1, "external_population_weighted_sum": 1.0},
        {"xstar_ipmat2_index": 80, "family_key": "type50_rate4", "n_record_terms": 1, "external_population_weighted_sum": 10.0},
    ])
    bal = tmp_path / "bal"
    bal.mkdir()
    _write_csv(bal / "xstar_priority_matrix_balance_audit_record_terms.csv", [
        {"family_key": "type51_rate3", "compact_col_ipmat2": 79, "ajisi_1_s^-1": 3.0, "population_weighted_contribution": -8.0},
        {"family_key": "type53_rate7", "compact_col_ipmat2": 80, "ajisi_1_s^-1": 2.0, "population_weighted_contribution": 2.0},
        {"family_key": "type50_rate4", "compact_col_ipmat2": 1, "ajisi_1_s^-1": 5.0, "population_weighted_contribution": 5.0},
    ])

    audit = build_priority_native_readiness_audit(
        priority_conditional_solve_audit=cond,
        priority_matrix_balance_audit=bal,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.202"
    assert summary["dominant_internal_family"] == "type51_rate3"
    assert summary["dominant_external_rhs_family"] == "type50_rate4"
    assert summary["conditional_solve_ready"] is True
    assert audit["external_family_rows"][0]["native_status"] == "partial"
    assert audit["internal_family_rows"][0]["native_status"] == "evaluator_ready_integration_pending"
    paths = write_priority_native_readiness_audit(tmp_path / "out", audit)
    assert Path(paths["markdown"]).exists()
    assert Path(paths["implementation_phases_csv"]).exists()
