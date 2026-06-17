from __future__ import annotations
import csv,json
from pathlib import Path
import xstar_tools
from xstar_tools.xstar.call2_helium_type99_source_faithful_correction import RELEASE,TARGET_RECORDS

def test_release_and_abi_contract() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.9.1"
    assert RELEASE == "0.6.48.7.36"
    assert TARGET_RECORDS == (779,780,1695)
    api=Path("src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    fixed=Path("src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.9.1"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api
    assert "XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60487u" in fixed

def test_type99_lowerer_preserves_pre_alias_destination_metadata() -> None:
    text=Path("src/xstar_tools/xstar/native_fixed_program.py").read_text()
    assert "source leveltemp" in text
    assert "destination_energy" in text
    assert "threshold_ev" in text
    assert "destination_weight" in text
    assert "payload_reals = list(raw_reals) +" in text

def test_native_type99_uses_reduced_workspace_and_source_arithmetic() -> None:
    text=Path("src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "build_type99_reduced_radiation" in text
    assert "reduced_count = 999" in text
    assert "std::pow(s1, 3.0)" in text
    assert "type99_cached_atmp22_stale_reuses" in text
    assert "destination_energy_ev" in text

def test_checked_type99_records_are_bit_exact() -> None:
    root=Path("v048736_checked_type99")
    summary=json.loads((root/"call2_helium_solve_state_rate_matrix_decomposition_summary.json").read_text())
    assert summary["result"] == "ACCEPT"
    assert summary["type99_exact_records"] == 3
    assert summary["type99_answers_exact"] is True
    assert summary["type99_intermediates_exact"] is True
    assert summary["dense_matrix_exact_cells"] == 5489
    assert summary["remaining_incorrect_matrix_cells"] == 595
    assert summary["gates"]["CALL2_HE_TYPE99_RATE_MATRIX"] == "ACCEPT"
    assert summary["gates"]["CALL2_HE_TYPE99_ROOT_CAUSE"] == "ACCEPT"
    assert summary["gates"]["CALL2_HE_FIXED_STATE_PARITY"] == "BLOCKED_BY_595_MATRIX_CELLS"
    rows=list(csv.DictReader((root/"call2_he_type99_record_comparison.csv").open(newline="")))
    assert {int(row["record"]) for row in rows} == {779,780,1695}
    assert all(row["answers_exact"] == "True" and row["intermediates_exact"] == "True" for row in rows)

def test_runner_invokes_full_lineage_and_type99_gate() -> None:
    runner=Path("run_v048736_type99_source_faithful_correction.sh").read_text()
    assert "call2_helium_bound_free_residual_decomposition" in runner
    assert "call2_helium_type99_source_faithful_correction" in runner
    checker=Path("check_v048736_type99_source_faithful_correction.py").read_text()
    readiness=Path("check_v048736_type99_source_faithful_readiness.py").read_text()
    assert "CALL2_HE_TYPE99_ANS1_TO_ANS6_EXACT" in checker
    assert "CALL2_HE_TYPE99_PHINT53HUNT_REDUCED_GRID" in readiness
