from __future__ import annotations

import csv
import json
from pathlib import Path

import xstar_tools
from xstar_tools.xstar.call2_helium_final_rate_families_source_faithful_correction import (
    EXPECTED_COUNTS,
    RELEASE,
    TARGET_TYPES,
)


def test_release_and_abi_contract() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.17.2.1"
    assert RELEASE == "0.6.48.7.40"
    assert TARGET_TYPES == (54, 57, 69, 76, 77)
    assert EXPECTED_COUNTS == {54: (29, 116), 57: (74, 296), 69: (6, 24), 76: (5, 20), 77: (74, 296)}
    api = Path("src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    fixed = Path("src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.17.2.1"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api
    assert "XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60487u" in fixed


def test_native_final_family_source_contracts() -> None:
    lower = Path("src/xstar_tools/xstar/native_fixed_program.py").read_text()
    fixed = Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "payload_ints = [i57, principal_n, local]" in lower
    assert "source-local level ordinal" in lower
    assert "source_local_level" in fixed
    assert "q * (1.0 - exp_tail)" in fixed
    assert "kCollisionRateCoefficientPerSqrtK" in fixed
    assert "kSourceCollisionBoltzmannEvPerK" in fixed
    assert "kLegacyCollisionErgPerEv" in fixed
    assert "::exp10(rec)" in fixed


def test_checked_final_family_closure_and_accumulation_inventory() -> None:
    root = Path("v048740_checked_final_rate_families")
    summary = json.loads((root / "call2_helium_solve_state_rate_matrix_decomposition_summary.json").read_text())
    assert summary["result"] == "ACCEPT"
    assert summary["all_rate_terms_exact"] is True
    assert summary["remaining_residual_data_types"] == []
    assert summary["dense_matrix_exact_cells"] == 6040
    assert summary["remaining_incorrect_matrix_cells"] == 44
    assert summary["remaining_matrix_cells_attribution"] == "ACCUMULATION_ORDER_SEQUENCE"
    assert summary["gates"]["CALL2_HE_ALL_5232_RATE_TERMS_EXACT"] == "ACCEPT"
    assert summary["gates"]["CALL2_HE_REMAINING_44_CELLS_ACCUMULATION_ORDER_ONLY"] == "ACCEPT"
    rows = list(csv.DictReader((root / "call2_he_final_rate_family_exactness.csv").open(newline="")))
    assert [int(row["data_type"]) for row in rows] == [54, 57, 69, 76, 77]
    assert all(row["all_terms_exact"] == "True" for row in rows)
    cells = list(csv.DictReader((root / "call2_he_remaining_matrix_cell_summary.csv").open(newline="")))
    assert len(cells) == 44
    assert all(row["attribution_kind"] == "ACCUMULATION_ORDER_SEQUENCE" for row in cells)
    assert all(int(row["mismatched_contribution_count"]) == 0 for row in cells)


def test_runner_checker_and_readiness_include_final_gates() -> None:
    runner = Path("run_v048740_final_rate_families_source_faithful_correction.sh").read_text()
    checker = Path("check_v048740_final_rate_families_source_faithful_correction.py").read_text()
    readiness = Path("check_v048740_final_rate_families_source_faithful_readiness.py").read_text()
    audit = Path("src/xstar_tools/xstar/call2_helium_final_rate_families_source_faithful_correction.py").read_text()
    assert "call2_helium_final_rate_families_source_faithful_correction" in runner
    assert "MILESTONE_RESULT" in checker
    assert "CALL2_HE_TYPE57_RECORD1947_SOURCE_LOCAL_ZERO_GATE" in readiness
    assert "CALL2_HE_TYPE77_ALL_74_RECORD_TERMS_EXACT" in readiness
    assert "CALL2_HE_REMAINING_44_CELLS_ACCUMULATION_ORDER_ONLY" in audit
