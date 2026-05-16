from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.rates_type51 import evaluate_type51_ucalc_record
from xstar_atomic.xstar_type51_native_parity import build_type51_native_parity_audit


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


def _decoded(record: int) -> dict:
    return {
        "record": record,
        "element": "O",
        "ion_stage": 4,
        "ion_roman": "IV",
        "lower_level": 1,
        "upper_level": 2,
        "lower_label": "lower",
        "upper_label": "upper",
        "g_lower": 2.0,
        "g_upper": 4.0,
        "eij_rdat_Ryd": 1.0,
        "bt_scaling_c": 1.0,
        "bt_transition_type": 2,
    }


def _grid(record: int) -> list[dict]:
    return [
        {"record": record, "grid_index": index + 1, "grid_kind": "BT_scaled", "bt_x": x, "bt_y": 1.0}
        for index, x in enumerate([0.0, 0.25, 0.5, 0.75, 1.0])
    ]


def test_type51_ucalc_formula_constant_upsilon() -> None:
    result = evaluate_type51_ucalc_record(_decoded(101), 1.0e6, 1.2e8, _grid(101))
    assert result["status"] == "evaluated"
    assert result["spline_method"] == "upsil_5point"
    assert abs(result["upsilon"] - 1.0) < 1.0e-12
    assert result["ans1_excitation_s^-1"] > 0.0
    ratio = result["ans1_excitation_s^-1"] / result["ans2_deexcitation_s^-1"]
    expected = (4.0 / 2.0) * __import__("math").exp(-result["delta_e_over_kT"])
    assert abs(ratio - expected) < 1.0e-12


def test_native_type51_audit_matches_synthetic_probe(tmp_path: Path) -> None:
    closure = tmp_path / "closure"
    closure.mkdir()
    temperature_k = 7.665519e4
    xpx = 1.0e8
    xee = 1.204656
    decoded_rows = [_decoded(101), _decoded(102)]
    grid_rows = _grid(101) + _grid(102)
    native = {
        row["record"]: evaluate_type51_ucalc_record(row, temperature_k, xpx * xee, _grid(row["record"]))
        for row in decoded_rows
    }
    ucalc_rows = []
    matrix_rows = []
    for capture, record in enumerate([101, 102], start=1):
        ans1 = native[record]["ans1_excitation_s^-1"]
        ans2 = native[record]["ans2_deexcitation_s^-1"]
        ucalc_rows.append({
            "capture_index": capture,
            "ml_data": record,
            "ltyp": 51,
            "lrtyp": 3,
            "jkk_ion": 32,
            "idest1": 2,
            "idest2": 1,
            "ans1": ans1,
            "ans2": ans2,
            "xpx": xpx,
            "xnx": xee,
            "t_xstar_1e4K": temperature_k / 1.0e4,
        })
        for kind, row_ip, col_ip, value in [
            ("forward_offdiag", 80, 79, ans1),
            ("reverse_offdiag", 79, 80, ans2),
            ("forward_diag_loss", 79, 79, -ans1),
            ("reverse_diag_loss", 80, 80, -ans2),
        ]:
            matrix_rows.append({
                "capture_index": capture,
                "ml_data": record,
                "ltyp": 51,
                "lrtyp": 3,
                "insertion_kind": kind,
                "compact_row_ipmat2": row_ip,
                "compact_col_ipmat2": col_ip,
                "row_endpoint_selected": True,
                "col_endpoint_selected": True,
                "ajisi_1": value,
            })
    _write_csv(closure / "xstar_priority_matrix_closure_audit_ucalc_records.csv", ucalc_rows)
    _write_csv(closure / "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv", matrix_rows)
    (closure / "xstar_priority_matrix_closure_audit.json").write_text(json.dumps({
        "summary": {
            "ion": "O VII",
            "selected_basis_solve_call_id": 219,
            "selection": "latest-per-record",
            "occurrence_rank": -1,
            "selected_xstar_ipmat2_indices": "79;80",
        }
    }), encoding="utf-8")

    audit = build_type51_native_parity_audit(
        priority_matrix_closure_audit=closure,
        decoded_type51_rows=decoded_rows,
        decoded_type51_grid_rows=grid_rows,
        relative_rate_tolerance=1.0e-12,
    )
    summary = audit["summary"]
    assert summary["audit_version"] == "v0.3.203"
    assert summary["n_selected_type51_ucalc_records"] == 2
    assert summary["n_type51_records_rate_parity_pass"] == 2
    assert summary["n_type51_compact_matrix_terms_match"] == 8
    assert summary["n_selected_rows_touched_by_native_type51"] == 2
    assert summary["native_type51_record_rate_parity_ready"] is True
    assert summary["native_type51_compact_matrix_parity_ready"] is True
    assert summary["native_type51_internal_block_assembly_ready"] is True
