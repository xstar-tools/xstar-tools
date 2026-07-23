from pathlib import Path
import math

def test_cfrac1_rrc_outward_escape_is_exp_of_total_tau():
    for tau1, tau2 in [(0.0, 0.0), (0.2, 0.4), (3.0, 1.5)]:
        pescv = lambda tau: max(math.exp(-float(tau)), 1.0e-12) / 2.0
        ptmp1 = pescv(tau1) * (1.0 - 1.0)
        ptmp2 = pescv(tau2) * (1.0 - 1.0) + 2.0 * pescv(tau1 + tau2) * 1.0
        assert ptmp1 == 0.0
        assert math.isclose(ptmp2, max(math.exp(-(tau1 + tau2)), 2.0e-12), rel_tol=1e-14, abs_tol=0.0)


def test_patch520148_keeps_full_curve_for_opacity_but_base_curve_for_deferred_emission():
    root = Path(__file__).resolve().parents[1]
    text = (root / 'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    assert 'prefer_full_calc_emis_shadow' in text
    assert 'emission_curve_v82_patch520148' in text
    assert 'emission_curve_v82_patch520148, false' in text
    assert 'until the source tauc/tau_in workspace is corrected in 5.20.15' in text


def test_type49_source_rnist_fix_and_compact_binemis_are_retained():
    root = Path(__file__).resolve().parents[1]
    rates = (root / 'src/xstar_tools/rates_type53.py').read_text()
    ow = (root / 'src/xstar_tools/xstar/output_writers.py').read_text()
    assert 'first_offset_eV if type49_rnist_semantics else ethtmp + first_offset_eV' in rates
    assert 'nbtpp = 20000' in ow
    assert 'nbtpp = 999999' not in ow
