from pathlib import Path
import subprocess
import sys

import pytest


def test_type50_nbinc_source_correction_scope_gate():
    root = Path(__file__).resolve().parents[1]
    gate = root / 'tools/qualification/check_type50_nbinc_source_correction_0_6_82_27_16_5.py'
    p = subprocess.run([sys.executable, str(gate)], cwd=root, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'TYPE50_NBINC_068227165_RESULT=ACCEPT' in p.stdout
    assert 'TYPE50_NBINC_068227165_CHANGED_NUMERICAL_FILES=2' in p.stdout


def test_type50_production_paths_no_longer_use_lower_bracket():
    root = Path(__file__).resolve().parents[1]
    ucalc = (root / 'src/xstar_tools/xstar/ucalc.py').read_text()
    elem = (root / 'src/xstar_tools/xstar/element_equilibrium.py').read_text()
    assert 'brem[_nbinc(endpoint_energy_ev, epi)]' not in ucalc
    assert '_xstar_nbinc_fortran_value(endpoint_energy_ev, epi)' in ucalc
    assert 'bremsa = float(brem[nb1_one_based - 1])' in ucalc
    assert '_reduced_bremsa[_nbinc(abs(' not in elem
    assert 'reduced_bremsa[_nbinc(abs(' not in elem
    assert elem.count('_xstar_nbinc_fortran_value(abs(') >= 2


def test_type50_nbinc_sentinel_indices_when_runtime_dependencies_available():
    pytest.importorskip('astropy')
    from xstar_tools.xstar.source_real_energy_grid import source_ener_grid
    from xstar_tools.xstar.ucalc import _nbinc, _xstar_nbinc_fortran_value

    epi = source_ener_grid(999)
    expected = [
        (2.855687141418457, 215, 217),
        (2.5497331619262695, 208, 210),
        (13.22029972076416, 314, 316),
    ]
    for energy, lower_zero_based, source_one_based in expected:
        assert _nbinc(energy, epi) == lower_zero_based
        assert _xstar_nbinc_fortran_value(energy, epi) == source_one_based
        assert source_one_based - 1 != lower_zero_based
