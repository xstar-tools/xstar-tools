from __future__ import annotations

import csv
import json
from pathlib import Path

import xstar_tools
from xstar_tools.xstar.call2_helium_type74_type95_source_faithful_correction import (
    EXPECTED_REMAINING_TYPES,
    RELEASE,
    TYPE53_IEEE_RECORD,
    TYPE74_TARGET_RECORD,
    TYPE95_TARGET_RECORD,
)


def test_release_and_abi_contract() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.17.2"
    assert RELEASE == "0.6.48.7.39"
    assert TYPE53_IEEE_RECORD == 688
    assert TYPE74_TARGET_RECORD == 757
    assert TYPE95_TARGET_RECORD == 1585
    assert EXPECTED_REMAINING_TYPES == [54, 57, 69, 76, 77]
    api = Path("src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    fixed = Path("src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.17.2"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api
    assert "XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60487u" in fixed


def test_native_type53_type74_type95_source_contracts() -> None:
    text = Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "0x1.10180c6305e33p-23" in text
    assert "0x1.54312407e4bb2p-24" in text
    assert "build_type99_reduced_radiation" in text
    assert "source 999-bin epim/bremsam workspace" in text
    assert "kLegacyBoltzmannEvPerT4" in text
    assert "kLegacyCollisionErgPerEv" in text
    assert "std::nextafter(sumc, 0.0)" not in text


def test_checked_family_closure_and_residual_inventory() -> None:
    root = Path("v048739_checked_type74_type95")
    summary = json.loads((root / "call2_helium_solve_state_rate_matrix_decomposition_summary.json").read_text())
    assert summary["result"] == "ACCEPT"
    assert summary["type53_record688_host_ieee_exact"] is True
    assert summary["type74_record_count"] == 42
    assert summary["type74_term_count"] == 168
    assert summary["type74_record757_exact"] is True
    assert summary["type74_all_terms_exact"] is True
    assert summary["type95_record_count"] == 2
    assert summary["type95_exact_record_count"] == 2
    assert summary["type95_record1585_exact"] is True
    assert summary["dense_matrix_exact_cells"] == 6020
    assert summary["remaining_incorrect_matrix_cells"] == 64
    assert summary["remaining_residual_data_types"] == [54, 57, 69, 76, 77]
    assert summary["gates"]["CALL2_HE_BOUND_FREE_SUBSYSTEM_EXACT"] == "ACCEPT"
    rows = list(csv.DictReader((root / "call2_he_type74_type95_record_comparison.csv").open(newline="")))
    assert len([row for row in rows if row["data_type"] == "74"]) == 42
    assert len([row for row in rows if row["data_type"] == "95"]) == 2


def test_runner_checker_and_readiness_include_new_gates() -> None:
    runner = Path("run_v048739_type74_type95_source_faithful_correction.sh").read_text()
    checker = Path("check_v048739_type74_type95_source_faithful_correction.py").read_text()
    readiness = Path("check_v048739_type74_type95_source_faithful_readiness.py").read_text()
    assert "call2_helium_type74_type95_source_faithful_correction" in runner
    assert "SUPERSEDED_BOUND_FREE_SUBSYSTEM_EXACT" in Path("src/xstar_tools/xstar/call2_helium_type74_type95_source_faithful_correction.py").read_text()
    assert "MILESTONE_RESULT" in checker
    assert "CALL2_HE_TYPE74_ALL_42_RECORD_TERMS_EXACT" in readiness
    assert "CALL2_HE_TYPE95_ALL_2_RECORD_ANSWERS_EXACT" in readiness
