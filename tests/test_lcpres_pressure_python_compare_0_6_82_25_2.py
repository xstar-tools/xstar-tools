from pathlib import Path
import importlib.util
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def _load_runner():
    path = ROOT / "tools/qualification/run_c5_lcpres_pressure_host_smoke_0_6_82_25_2.py"
    spec = importlib.util.spec_from_file_location("lcpres_runner_0682252", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_constant_pressure_factory_uses_calc_hmc_all_resolved_density():
    source = (ROOT / "src/xstar_tools/xstar/physical_runner.py").read_text()
    assert "continuum_xpx = resolve_calc_hmc_all_density(" in source
    assert source.count("hydrogen_density_cm3=continuum_xpx") >= 3

    pressure = float(np.float32(0.03))
    initial_rread1_density = pressure / (1.38e-12 * 100.0)
    # The source helper uses the default-REAL-rounded coefficient; this is
    # intentionally distinct from rread1's double-precision literal.
    expected = pressure / (float(np.float32(1.38e-12)) * 100.0)
    assert expected != initial_rread1_density
    local_zone = (ROOT / "src/xstar_tools/xstar/local_zone.py").read_text()
    assert "XSTAR_CALC_HMC_PRESSURE_COEFFICIENT = float(np.float32(1.38e-12))" in local_zone
    assert "xpx = float(pressure) / (XSTAR_CALC_HMC_PRESSURE_COEFFICIENT * max(t4, 1.0e-24))" in local_zone


def test_compare_requires_complete_products_not_just_directory(tmp_path):
    runner = _load_runner()
    case = tmp_path / "python" / "cp_xim2"
    case.mkdir(parents=True)
    assert not runner.candidate_products_ready(case)
    (case / "xout_step.log").write_text("partial\n")
    assert not runner.candidate_products_ready(case)
    (case / "xout_abund1.fits").write_bytes(b"placeholder")
    assert runner.candidate_products_ready(case)


def test_25_2_runner_has_backend_selector_and_marker():
    source = (ROOT / "tools/qualification/run_c5_lcpres_pressure_host_smoke_0_6_82_25_2.py").read_text()
    assert "--backend" in source
    assert "choices=('cpp','python')" in source
    assert 'EXPECTED_VERSION="0.6.82.25.2"' in source
    assert "C5_LCPRES_PRESSURE_0682252_" in source
