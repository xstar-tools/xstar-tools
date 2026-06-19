from __future__ import annotations

import csv
import json
from pathlib import Path

import xstar_tools
from xstar_tools.xstar.call2_helium_bound_free_residual_decomposition import RELEASE, TARGET_TYPES


def test_release_and_abi_are_unchanged() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.19.3"
    assert RELEASE == "0.6.48.7.35"
    assert TARGET_TYPES == (50, 53, 95, 99)
    api = Path("src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert "XSTAR_API_ABI_VERSION 60487u" in api
    fixed = Path("src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h").read_text()
    assert "XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60487u" in fixed
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.19.3"' in api


def test_source_capture_adds_bound_free_record_ledger() -> None:
    text = Path("src/xstar_tools/xstar/v0472_call2_helium_solve_state_capture.py").read_text()
    assert "_HE_BOUND_FREE_RECORDS=[]" in text
    assert "_dtype in {50,53,95,99}" in text
    assert "v0472_call2_eval1_he_bound_free_records.csv" in text
    assert "source_bound_free_records" in text


def test_checked_decomposition_closes_all_diagnostic_coverage() -> None:
    root = Path("v048735_checked_decomposition")
    summary = json.loads((root / "call2_helium_solve_state_rate_matrix_decomposition_summary.json").read_text())
    assert summary["result"] == "ACCEPT"
    assert summary["physics_changed"] is False
    assert summary["matrix_cells"] == 6084
    assert summary["dense_matrix_exact_cells"] == 5487
    assert summary["remaining_incorrect_matrix_cells"] == 597
    assert summary["bound_free_record_count"] == 438
    assert summary["bound_free_record_counts_by_type"] == {"50": 301, "53": 132, "95": 2, "99": 3}
    assert summary["gates"]["CALL2_HE_REMAINING_597_CELL_DECOMPOSITION"] == "ACCEPT"
    assert summary["gates"]["CALL2_HE_EVERY_REMAINING_CELL_ATTRIBUTED"] == "ACCEPT"
    assert summary["gates"]["CALL2_HE_BOUND_FREE_RECORD_ANSWER_RECONSTRUCTION"] == "ACCEPT"
    assert summary["gates"]["CALL2_HE_FIXED_STATE_PARITY"] == "BLOCKED_BY_597_MATRIX_CELLS"
    assert summary["gates"]["THERMAL_PARITY"] == "BLOCKED"


def test_checked_decomposition_identifies_order_only_cells_and_dominant_type99() -> None:
    root = Path("v048735_checked_decomposition")
    with (root / "call2_he_remaining_matrix_cell_summary.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 597
    order_only = {(int(r["compact_row"]), int(r["compact_column"])) for r in rows if r["attribution_kind"] == "ACCUMULATION_ORDER_SEQUENCE"}
    assert order_only == {(31, 46), (71, 71), (74, 74), (76, 76)}
    dominant = max(rows, key=lambda r: abs(float(r["dense_delta"])))
    assert (int(dominant["compact_row"]), int(dominant["compact_column"])) == (31, 31)
    assert int(dominant["dominant_data_type"]) == 99
    assert int(dominant["dominant_record"]) == 780


def test_runner_and_checker_contract() -> None:
    runner = Path("run_v048735_bound_free_matrix_residual_decomposition.sh").read_text()
    checker = Path("check_v048735_bound_free_matrix_residual_decomposition.py").read_text()
    audit = Path("src/xstar_tools/xstar/call2_helium_bound_free_residual_decomposition.py").read_text()
    assert "call2_helium_type56_xpx_restoration" in runner
    assert "call2_helium_bound_free_residual_decomposition" in runner
    assert "CALL2_HE_REMAINING_597_CELL_DECOMPOSITION" in checker
    assert "NOT_EVALUATED_DECOMPOSITION_ONLY" in audit
