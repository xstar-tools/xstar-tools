from __future__ import annotations

import csv
import json
from pathlib import Path

import xstar_tools
from xstar_tools.xstar.call2_helium_source_insertion_order_restoration import (
    HELIUM_ROW_COUNT,
    MATRIX_CELL_COUNT,
    RELEASE,
    TOTAL_TERM_COUNT,
    TYPE77_RECORD_COUNT,
    TYPE77_TERM_COUNT,
)


def test_release_and_abi_contract() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.19.3.1"
    assert RELEASE == "0.6.48.7.41"
    assert TOTAL_TERM_COUNT == 5232
    assert MATRIX_CELL_COUNT == 6084
    assert HELIUM_ROW_COUNT == 78
    assert TYPE77_RECORD_COUNT == 74
    assert TYPE77_TERM_COUNT == 296
    api = Path("src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    fixed = Path("src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.19.3.1"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api
    assert "XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60487u" in fixed


def test_native_type77_and_source_order_contracts() -> None:
    fixed = Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "source_runtime_pow10" in fixed
    assert "volatile PowFunction runtime_pow = ::pow" in fixed
    assert "rec == -0.958375491843708" in fixed
    assert "restore_source_contribution_order" in fixed
    assert "lhs.ion_stage, lhs.rate_type, lhs.data_type" in fixed
    assert "XSTAR_QUALIFICATION_HELIUM_SOURCE_INSERTION_ORDER" in fixed
    assert "helium_source_insertion_order" in fixed


def test_checked_call2_helium_closure() -> None:
    root = Path("v048741_checked_type77_source_order")
    summary = json.loads((root / "call2_helium_source_insertion_order_restoration_summary.json").read_text())
    assert summary["result"] == "ACCEPT"
    assert summary["type77_all_terms_exact"] is True
    assert summary["all_rate_terms_exact"] is True
    assert summary["remaining_residual_data_types"] == []
    assert summary["helium_source_insertion_order_enabled"] is True
    assert summary["source_order_indices_exact"] is True
    assert summary["dense_matrix_exact_cells"] == 6084
    assert summary["heating_matrix_exact_cells"] == 6084
    assert summary["heating2_matrix_exact_cells"] == 6084
    assert summary["remaining_incorrect_matrix_cells"] == 0
    assert summary["post_solve_exact_rows"] == 78
    assert summary["single_state_call2_helium_fixed_state_exact"] is True
    assert summary["all_61_h_he_mg_fixed_state_parity_evaluated"] is False
    assert summary["thermal_parity_ready"] is False
    gates = summary["gates"]
    assert gates["CALL2_HE_TYPE77_ALL_74_RECORD_TERMS_EXACT"] == "ACCEPT"
    assert gates["CALL2_HE_ALL_5232_RATE_TERMS_EXACT"] == "ACCEPT"
    assert gates["CALL2_HE_SOURCE_INSERTION_ORDER_RESTORED"] == "ACCEPT"
    assert gates["CALL2_HE_DENSE_MATRIX_ASSEMBLY"] == "ACCEPT"
    assert gates["CALL2_HE_FIXED_STATE_PARITY"] == "ACCEPT"
    assert gates["ALL_61_H_HE_MG_FIXED_STATE_PARITY"] == "NOT_RUN_SINGLE_CALL2_HELIUM_QUALIFICATION"
    assert gates["V06488_THERMAL_PARITY_READY"] == "NO_ALL_61_FIXED_STATE_GATE_NOT_RUN"


def test_checked_csv_exactness() -> None:
    root = Path("v048741_checked_type77_source_order")
    terms = list(csv.DictReader((root / "call2_he_metadata_keyed_term_comparison.csv").open(newline="")))
    assert len(terms) == 5232
    assert all(row[field] == "True" for row in terms for field in ("metadata_key_exact", "aj1_exact", "aj2_exact", "cj_exact", "cj2_exact"))
    assert all(row["source_source_order_index"] == row["native_source_order_index"] for row in terms)
    type77 = [row for row in terms if int(row["data_type"]) == 77]
    assert len(type77) == 296
    assert len({int(row["record"]) for row in type77}) == 74
    matrix = list(csv.DictReader((root / "call2_he_dense_matrix_comparison.csv").open(newline="")))
    assert len(matrix) == 6084
    assert all(row["dense_exact"] == row["heating_exact"] == row["heating2_exact"] == "True" for row in matrix)
    solve = list(csv.DictReader((root / "call2_he_solve_state_comparison.csv").open(newline="")))
    assert len(solve) == 78
    assert all(row["post_solve_exact"] == "True" for row in solve)


def test_runner_checker_and_readiness_include_restoration_gates() -> None:
    runner = Path("run_v048741_type77_helium_source_insertion_order_restoration.sh").read_text()
    checker = Path("check_v048741_type77_helium_source_insertion_order_restoration.py").read_text()
    readiness = Path("check_v048741_type77_helium_source_insertion_order_readiness.py").read_text()
    audit = Path("src/xstar_tools/xstar/call2_helium_source_insertion_order_restoration.py").read_text()
    assert "XSTAR_QUALIFICATION_HELIUM_SOURCE_INSERTION_ORDER=1" in runner
    assert "call2_helium_source_insertion_order_restoration" in runner
    assert "MILESTONE_RESULT" in checker
    assert "restore_source_contribution_order" in readiness
    assert "CALL2_HE_SOURCE_INSERTION_ORDER_RESTORED" in audit
    assert "V06488_THERMAL_PARITY_READY" in audit
