import pytest

pytest.importorskip("astropy")

from xstar_atomic.xstar_element_solver import _type50_effective_rates


def _type50_row(from_level=4, to_level=2, rate=57.14):
    return {
        "kind": "radiative_decay",
        "data_type": 50,
        "from_level": from_level,
        "to_level": to_level,
        "rate_s^-1": rate,
    }


def test_xstar_line_escape_uses_optically_thin_fallback_for_helike_3p_to_3s():
    row = _type50_row()
    rates = _type50_effective_rates(
        row,
        treatment="xstar-line-escape",
        escape_factor=0.35,
        from_state={"level_label": "1s1.2p1.3P_1"},
        to_state={"level_label": "1s1.2s1.3S_1"},
    )
    assert rates["type50_bound_bound_treatment"] == "xstar-line-escape"
    assert rates["type50_is_helike_3p_to_3s_drain"] is True
    assert rates["type50_line_escape_fallback_used"] is True
    assert rates["ptmp_sum_proxy"] == 1.0
    assert rates["escaped_decay_rate_s^-1"] == row["rate_s^-1"]
    assert "optically_thin_helike_3p_to_3s" in rates["ucalc_context_status"]


def test_xstar_line_escape_preserves_scalar_fallback_for_other_missing_tau_lines():
    row = _type50_row(from_level=7, to_level=1, rate=20.0)
    rates = _type50_effective_rates(
        row,
        treatment="xstar-line-escape",
        escape_factor=0.35,
        from_state={"level_label": "1s1.2p1.1P_1"},
        to_state={"level_label": "1s2.1S_0"},
    )
    assert rates["type50_is_helike_3p_to_3s_drain"] is False
    assert rates["ptmp_sum_proxy"] == 0.35
    assert rates["escaped_decay_rate_s^-1"] == 7.0
    assert "scalar_proxy_fallback" in rates["ucalc_context_status"]


def test_xstar_line_escape_uses_row_tau_when_present():
    row = _type50_row(from_level=7, to_level=1, rate=20.0)
    row["tau1"] = 0.0
    row["tau2"] = 0.0
    rates = _type50_effective_rates(
        row,
        treatment="xstar-line-escape",
        escape_factor=0.35,
    )
    assert rates["type50_line_escape_fallback_used"] is False
    assert rates["ptmp_sum_proxy"] == 1.0
    assert rates["escaped_decay_rate_s^-1"] == 20.0
    assert rates["ucalc_context_status"] == "xstar_line_escape_from_row_tau0_pescl"
