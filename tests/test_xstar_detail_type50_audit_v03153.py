from pathlib import Path

import pytest

import xstar_atomic as xa
from xstar_atomic.xstar_detail import (
    pescl_xstar,
    ptmp_from_tau_xstar,
    xstar_nbinc_index,
    type50_vtherm_xstar,
    write_xstar_detail_type50_rate_audit,
)


def test_ptmp_from_tau_xstar_cfrac_limits():
    p1, p2 = ptmp_from_tau_xstar(0.0, 0.0, 1.0)
    assert p1 == 0.0
    assert p2 == 1.0
    p1_open, p2_open = ptmp_from_tau_xstar(0.0, 0.0, 0.0)
    assert p1_open == 0.5
    assert p2_open == 0.5
    assert pescl_xstar(0.0) == 0.5


def test_xstar_nbinc_index_and_vtherm():
    idx, nb1 = xstar_nbinc_index(15.0, [1.0, 10.0, 20.0, 30.0, 40.0])
    assert idx == 1
    assert nb1 == 2
    v = type50_vtherm_xstar(temperature_K=1.0e6, vturb_km_s=100.0, atomic_mass_number=16.0)
    assert v is not None and v > 0.0


def test_type50_audit_writer(tmp_path):
    rows = [{
        "line_kind": "r",
        "detail_wavelength_A": 21.602,
        "tau_in": 7.0,
        "tau_out": 0.0,
        "ptmp_sum": 0.04,
        "atdb_A_s^-1": 3.0e12,
        "ucalc_pre_swap_ans1_escaped_decay_s^-1": 1.2e11,
        "ucalc_pre_swap_ans2_photoexcitation_s^-1": 0.0,
        "matrix_match_status": "not_supplied_or_not_matched",
    }]
    paths = write_xstar_detail_type50_rate_audit(rows, tmp_path)
    assert Path(paths["csv"]).is_file()
    assert Path(paths["json"]).is_file()
    assert Path(paths["markdown"]).is_file()
    assert "ucalc" in Path(paths["markdown"]).read_text()


def test_public_exports_present():
    assert hasattr(xa, "audit_xstar_detail_type50_rates")
    assert hasattr(xa, "write_xstar_detail_type50_rate_audit")


def test_type50_depth_annotation_preserves_detail_cfrac():
    pytest.importorskip("astropy")
    from xstar_atomic.xstar_element_solver import _annotate_type50_transition_depths_from_reference

    transitions = [
        {
            "kind": "radiative_decay",
            "data_type": 50,
            "ion_stage": 7,
            "from_level": 7,
            "to_level": 1,
            "wavelength_A": 21.602,
            "rate_s^-1": 3.309e12,
        }
    ]
    refs = [
        {
            "ion_stage": 7,
            "lower_level": 1,
            "upper_level": 7,
            "wavelength_A": 21.602,
            "depth_inward": 6.893473625,
            "depth_outward": 0.0,
            "record": 22112,
            "cfrac": 1.0,
            "source": "xo01_detal2.fits:last_zone_live_tau0",
        }
    ]
    out = _annotate_type50_transition_depths_from_reference(transitions, refs)
    assert out[0]["depth_inward"] == 6.893473625
    assert out[0]["xstar_cfrac"] == 1.0
    assert out[0]["xstar_reference_cfrac_source"] == "xo01_detal2.fits:last_zone_live_tau0"


def test_type50_line_escape_uses_fallback_cfrac_when_row_lacks_cfrac():
    pytest.importorskip("astropy")
    from xstar_atomic.xstar_element_solver import _type50_effective_rates

    row = {
        "kind": "radiative_decay",
        "data_type": 50,
        "rate_s^-1": 3.309e12,
        "depth_inward": 6.893473625,
        "depth_outward": 0.0,
    }
    rates = _type50_effective_rates(
        row,
        treatment="xstar-line-escape",
        escape_factor=0.35,
        type50_cfrac=1.0,
    )
    expected = 3.309e12 * (2.0 * pescl_xstar(6.893473625))
    assert abs(rates["escaped_decay_rate_s^-1"] - expected) / expected < 1e-12
    assert rates["xstar_cfrac_for_type50_escape"] == 1.0


def test_matrix_summary_classifies_cfrac_mismatch():
    from xstar_atomic.xstar_detail import _matrix_rows_summary

    rows = [
        {
            "rate_s^-1": 1.725969e12,
            "signed_rate_s^-1": 1.725969e12,
            "matrix_role": "bound_bound_gain_to_destination",
            "xstar_cfrac_for_type50_escape": 0.0,
        },
        {
            "rate_s^-1": 1.725969e12,
            "signed_rate_s^-1": -1.725969e12,
            "matrix_role": "bound_bound_loss_from_source",
            "xstar_cfrac_for_type50_escape": 0.0,
        },
    ]
    summary = _matrix_rows_summary(rows, 1.429382084847678e11, expected_cfrac=1.0)
    assert summary["matrix_residual_classification"] == "matrix_cfrac_mismatch"
