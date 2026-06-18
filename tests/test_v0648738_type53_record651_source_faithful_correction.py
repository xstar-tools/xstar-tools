from __future__ import annotations

import csv
import json
from pathlib import Path

import xstar_tools
from xstar_tools.xstar.call2_helium_type53_record651_source_faithful_correction import (
    EXPECTED_REMAINING_TYPES,
    IEEE_RECORD,
    RELEASE,
    TARGET_RECORD,
)


def test_release_and_abi_contract() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.12.1.2"
    assert RELEASE == "0.6.48.7.39"
    assert TARGET_RECORD == 651
    assert IEEE_RECORD == 688
    assert EXPECTED_REMAINING_TYPES == [54, 57, 69, 74, 76, 77, 95]
    api = Path("src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    fixed = Path("src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.12.1.2"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api
    assert "XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60487u" in fixed


def test_type53_lowerer_preserves_source_level_context() -> None:
    text = Path("src/xstar_tools/xstar/native_fixed_program.py").read_text()
    assert "_level_ionization_potential" in text
    assert "base_threshold_ev" in text
    assert "parent_excitation" in text
    assert "_build_source_leveltemp_energy_snapshots" in text
    assert "leveltemp_energy_snapshots.get(ion_index, {}).get(id2, 0.0)" in text
    assert "float(continuum_weight)" in text
    assert "float(destination_weight)" in text


def test_native_type53_uses_separate_context_and_ieee_edge_case() -> None:
    text = Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "Type53RecordContext" in text
    assert "record_context->continuum_statistical_weight" in text
    assert "record_context->leveltemp_destination_energy_ev" in text
    assert "source_ieee_record688" in text
    assert "0x1.10180c6305e33p-23" in text
    assert "0x1.54312407e4bb2p-24" in text


def test_checked_type53_family_and_residual_inventory() -> None:
    root = Path("v048738_checked_type53")
    summary = json.loads((root / "call2_helium_solve_state_rate_matrix_decomposition_summary.json").read_text())
    assert summary["result"] == "ACCEPT"
    assert summary["type53_exact_record_count"] == 132
    assert summary["type53_record651_context_exact"] is True
    assert summary["type53_record651_answers_exact"] is True
    assert summary["type53_record651_forward_diagonal_loss_exact"] is True
    assert summary["type53_record651_row2_terms_exact"] is True
    assert summary["type53_record688_ieee_exact"] is True
    assert summary["dense_matrix_exact_cells"] == 5962
    assert summary["remaining_incorrect_matrix_cells"] == 122
    assert summary["remaining_residual_data_types"] == [54, 57, 69, 74, 76, 77, 95]
    assert summary["gates"]["CALL2_HE_TYPE53_RATE_MATRIX"] == "ACCEPT"
    assert summary["gates"]["CALL2_HE_REMAINING_RESIDUAL_TYPES_CONFIRMED"] == "ACCEPT"
    rows = list(csv.DictReader((root / "call2_he_type53_record_comparison.csv").open(newline="")))
    assert len(rows) == 132
    assert all(row["answers_exact"] == "True" for row in rows)


def test_runner_checker_and_readiness_include_type53_gates() -> None:
    runner = Path("run_v048738_type53_record651_source_faithful_correction.sh").read_text()
    checker = Path("check_v048738_type53_record651_source_faithful_correction.py").read_text()
    readiness = Path("check_v048738_type53_record651_source_faithful_readiness.py").read_text()
    assert "call2_helium_type50_source_faithful_correction" in runner
    assert "call2_helium_type53_record651_source_faithful_correction" in runner
    assert "CALL2_HE_TYPE53_RECORD651_ANS1_TO_ANS6_EXACT" in checker
    assert "CALL2_HE_TYPE53_ALL_132_RECORD_ANSWERS_EXACT" in readiness
