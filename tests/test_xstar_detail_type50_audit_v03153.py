from pathlib import Path

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
