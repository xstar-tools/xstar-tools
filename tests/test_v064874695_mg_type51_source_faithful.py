from __future__ import annotations

import math
from pathlib import Path

import xstar_tools
from xstar_tools.rates_type51 import evaluate_type51_ucalc_record, splinem_5
from xstar_tools.xstar import mg_type51_source_faithful_attribution as audit


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def sample_row() -> dict[str, float | int]:
    return {
        "eij_rdat_Ryd": 2.0,
        "bt_scaling_c": 1.5,
        "bt_transition_type": 2,
        "g_lower": 3.0,
        "g_upper": 5.0,
    }


def sample_grid() -> list[dict[str, float | int | str]]:
    return [
        {"grid_kind": "BT_scaled", "grid_index": index + 1, "bt_x": index / 4.0, "bt_y": value}
        for index, value in enumerate((0.1, 0.2, 0.35, 0.5, 0.7))
    ]


def test_release_and_native_api_version() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.14.1"
    assert audit.RELEASE == "0.6.48.7.46.14.1"
    api = (root() / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.14.1"' in api
    assert "XSTAR_API_ABI_VERSION 60487u" in api


def test_type51_ieee_envelope_accepts_observed_limit_only() -> None:
    base = 1.9
    value = base
    for _ in range(5):
        value = math.nextafter(value, math.inf)
    accepted, ulps, _, relative = audit.type51_binary64_ieee_equivalent(base, value)
    assert accepted and ulps == 5 and relative <= audit.MAX_RELATIVE_DELTA
    value = math.nextafter(value, math.inf)
    assert not audit.type51_binary64_ieee_equivalent(base, value)[0]
    assert not audit.type51_binary64_ieee_equivalent(0.0, math.nextafter(0.0, 1.0))[0]
    assert not audit.type51_binary64_ieee_equivalent(1.0, -1.0)[0]
    assert not audit.type51_binary64_ieee_equivalent(float("inf"), 1.0)[0]


def test_exact_five_point_splinem_is_non_linear() -> None:
    points = (0.1, 0.2, 0.35, 0.5, 0.7)
    value = splinem_5(points, 0.42)
    linear = points[1] + (0.42 - 0.25) / 0.25 * (points[2] - points[1])
    assert math.isfinite(value)
    assert value != linear


def test_wavelength_temperature_floor_is_applied_only_to_bt_fit() -> None:
    low = evaluate_type51_ucalc_record(sample_row(), 100.0, 1.0e8, sample_grid())
    high = evaluate_type51_ucalc_record(sample_row(), 1.0e6, 1.0e8, sample_grid())
    assert low["status"] == high["status"] == "evaluated"
    assert low["bt_temperature_floor_applied"] is True
    assert low["bt_effective_temperature_K"] > low["temperature_K"]
    assert high["bt_temperature_floor_applied"] is False
    assert high["bt_effective_temperature_K"] == high["temperature_K"]


def test_record_energy_controls_maxwellian_and_energy_channels() -> None:
    result = evaluate_type51_ucalc_record(sample_row(), 5.0e4, 2.0e8, sample_grid())
    eij_ev = 2.0 * 13.605692
    assert result["eij_rdat_eV"] == eij_ev
    assert result["ans6_excitation_energy_erg_s^-1"] == (
        result["ans1_excitation_s^-1"] * eij_ev * 1.602197e-12
    )
    assert result["ans5_deexcitation_energy_erg_s^-1"] == (
        result["ans2_deexcitation_s^-1"] * eij_ev * 1.602197e-12
    )


def test_native_type51_block_contains_literal_source_contract() -> None:
    cpp = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    block = cpp.split("case XSTAR_FIXED_OPCODE_TYPE51_BT_COLLISION", 1)[1].split(
        "case XSTAR_FIXED_OPCODE_TYPE54_ANGULAR_REDIS", 1
    )[0]
    for marker in (
        "XSTAR_QUALIFICATION_MG_TYPE51_SOURCE_FAITHFUL",
        "type51_upsilon(",
        "bt.eij_ev",
        "input.temperature_k / 1.0e4",
        "source_ans1",
        "source_ans2",
    ):
        assert marker in block
    assert "type51_splinem5" in cpp
    assert "2.71828" in cpp


def test_release_gates_are_fail_closed() -> None:
    text = (root() / "src/xstar_tools/xstar/mg_type51_source_faithful_attribution.py").read_text()
    for marker in (
        "MG_TYPE51_SOURCE_RECORD_ORDER_EXACT",
        "MG_TYPE51_ENDPOINTS_EXACT",
        "MG_TYPE51_CONTRIBUTIONS_IEEE_EQUIVALENT",
        "MG_TYPE51_IEEE_ROUNDOFF_ENVELOPE",
        "MG_TYPE51_UNEXPLAINED_RATE_DELTAS_ZERO",
        "MG_TYPE51_RUNTIME_CONTEXT_COMPLETE",
        "MG_TYPE51_COMMITTED_NONFINITE_ZERO",
    ):
        assert marker in text


def test_type50_block_is_unchanged_by_type51_release() -> None:
    cpp = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    block = cpp.split("case XSTAR_FIXED_OPCODE_TYPE50_RADIATIVE_LINE", 1)[1].split(
        "case XSTAR_FIXED_OPCODE_TYPE51_BT_COLLISION", 1
    )[0]
    assert "MG_TYPE51_SOURCE_FAITHFUL" not in block
    assert "type51_splinem5" not in block


def test_runner_replays_native_only_and_defers_type50() -> None:
    runner = (root() / "run_v04874695_mg_type51_source_faithful_closure.sh").read_text()
    assert "XSTAR_QUALIFICATION_MG_TYPE51_SOURCE_FAITHFUL=1" in runner
    assert "source_capture_replayed=false" in runner
    assert "native_replay_replayed=true" in runner
    checker = (root() / "check_v04874695_mg_type51_source_faithful.py").read_text()
    assert '"MG_TYPE50_ORIENTATION_CORRECTION": "DEFERRED"' in checker
