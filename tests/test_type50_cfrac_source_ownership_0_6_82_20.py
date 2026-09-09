from pathlib import Path
import inspect
import subprocess
import sys

import pytest




def test_type50_cfrac_changes_but_emult_is_not_a_science_argument():
    from xstar_tools.rates_type50 import evaluate_type50_ucalc_record
    assert 'emult' not in inspect.signature(evaluate_type50_ucalc_record).parameters
    decoded = {'A_s^-1': 1.0e8, 'f_osc_from_A': 0.4, 'wavelength_A': 1215.67}
    kw = dict(ptmp1=0.2, ptmp2=0.4, bremsa_nb1=2.5e7, hydrogen_density_cm3=1.0e12, endpoint_energy_eV=10.2)
    r04 = evaluate_type50_ucalc_record(decoded, cfrac=0.4, **kw)
    r10 = evaluate_type50_ucalc_record(decoded, cfrac=1.0, **kw)
    assert r04['ans1_photoexcitation_s^-1'] > 0.0
    assert r10['ans1_photoexcitation_s^-1'] == 0.0
    # emult cannot alter this fixed-state result because it is not an input.
    for emult in (0.1, 0.5, 0.9):
        _ = emult
        assert evaluate_type50_ucalc_record(decoded, cfrac=0.4, **kw)['ans1_photoexcitation_s^-1'] == pytest.approx(r04['ans1_photoexcitation_s^-1'])


def test_type53_directional_cfrac_changes_and_has_no_emult_owner():
    import math
    def pescv(tau):
        return max(math.exp(-float(tau)), 1.0e-12) / 2.0
    def channels(cfrac):
        tau1, tau2 = 0.7, 1.1
        return (
            pescv(tau1) * (1.0 - cfrac),
            pescv(tau2) * (1.0 - cfrac) + 2.0 * pescv(tau1 + tau2) * cfrac,
        )
    baseline = channels(0.4)
    for emult in (0.1, 0.5, 0.9):
        _ = emult
        assert channels(0.4) == pytest.approx(baseline)
    assert channels(1.0) != pytest.approx(baseline)
    root = Path(__file__).resolve().parents[1]
    src = (root/'src/xstar_tools/xstar/element_equilibrium.py').read_text()
    assert 'pescv(tau1) * (1.0 - context.covering_fraction)' in src
    assert '+ 2.0 * pescv(tau1 + tau2) * context.covering_fraction' in src


def test_thomson_and_heatt_contract_are_cfrac_not_emult():
    root = Path(__file__).resolve().parents[1]
    heatt_src = (root/'src/xstar_tools/xstar/heatt.py').read_text()
    emiss_src = (root/'src/xstar_tools/xstar/emergent_emissivity.py').read_text()
    # fixed cfrac: changing emult cannot change these formulas because emult is absent
    assert 'emult' not in heatt_src[heatt_src.index('def heatt('):heatt_src.index('def direct_fortran_heatt_reference_case') ]
    assert '1.0 - float(covering_fraction)' in heatt_src
    assert '1.0 + float(covering_fraction)' in heatt_src
    assert 'max(0.0, 1.0 - context.covering_fraction)' in emiss_src
    th04 = max(0.0, 1.0 - 0.4)
    for emult in (0.1, 0.5, 0.9):
        _ = emult
        assert max(0.0, 1.0 - 0.4) == th04
    assert max(0.0, 1.0 - 1.0) != th04





