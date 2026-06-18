from __future__ import annotations
import csv,json
from pathlib import Path
import xstar_tools
from xstar_tools.xstar.call2_helium_type50_source_faithful_correction import RELEASE,TARGET_RECORDS


def test_release_and_abi_contract() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.9.6"
    assert RELEASE == "0.6.48.7.37"
    assert TARGET_RECORDS == (781,917)
    api=Path("src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    fixed=Path("src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.9.6"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api
    assert "XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60487u" in fixed


def test_type50_lowerer_retains_literal_wavelength() -> None:
    text=Path("src/xstar_tools/xstar/native_fixed_program.py").read_text()
    assert "payload_reals = [aij, oscillator, wavelength]" in text
    assert "stored wavelength" in text


def test_native_type50_uses_dsec_covering_and_post_swap_signs() -> None:
    text=Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "has_dsec_covering" in text
    assert "photoexcitation_zero_covering" in text
    assert "c.ans3 = -escaped" in text
    assert "c.ans4 = -photo" in text
    assert "type50_shadow" in text


def test_checked_type50_records_and_family_are_exact() -> None:
    root=Path("v048737_checked_type50")
    summary=json.loads((root/"call2_helium_solve_state_rate_matrix_decomposition_summary.json").read_text())
    assert summary["result"] == "ACCEPT"
    assert summary["type50_exact_record_count"] == 301
    assert summary["type50_record781_zero_return_exact"] is True
    assert summary["type50_record917_forward_diagonal_loss_exact"] is True
    assert summary["dense_matrix_exact_cells"] == 5784
    assert summary["remaining_incorrect_matrix_cells"] == 300
    assert summary["gates"]["CALL2_HE_TYPE50_RATE_MATRIX"] == "ACCEPT"
    assert summary["gates"]["CALL2_HE_TYPE50_ROOT_CAUSE"] == "ACCEPT"
    assert summary["gates"]["CALL2_HE_FIXED_STATE_PARITY"] == "BLOCKED_BY_300_MATRIX_CELLS"
    rows=list(csv.DictReader((root/"call2_he_type50_record_comparison.csv").open(newline="")))
    assert len(rows) == 301
    assert all(row["answers_exact"] == "True" and row["context_exact"] == "True" for row in rows)


def test_runner_invokes_full_lineage_and_type50_gate() -> None:
    runner=Path("run_v048737_type50_source_faithful_correction.sh").read_text()
    assert "call2_helium_type99_source_faithful_correction" in runner
    assert "call2_helium_type50_source_faithful_correction" in runner
    checker=Path("check_v048737_type50_source_faithful_correction.py").read_text()
    readiness=Path("check_v048737_type50_source_faithful_readiness.py").read_text()
    assert "CALL2_HE_TYPE50_RECORD781_SOURCE_ZERO_RETURN" in checker
    assert "CALL2_HE_TYPE50_ALL_301_RECORD_ANSWERS_EXACT" in readiness
