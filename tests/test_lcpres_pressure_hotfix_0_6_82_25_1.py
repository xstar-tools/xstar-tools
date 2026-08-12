from pathlib import Path

import numpy as np

from xstar_tools.xstar.radiation import apply_bremsmap_to_state
from xstar_tools.xstar.state import XSTARPythonState

ROOT = Path(__file__).resolve().parents[1]


def test_cpp_step_uses_retained_xcol_and_fortran_tau_floor():
    step = (ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp").read_text()
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "safe_log(r.column,-10.0)" in step
    assert "safe_log(r.density*r.dr,-10.0)" not in step
    assert "zone.column_density_cm2, logxi" in step
    assert "std::log10(std::max(fwd, 1.0e-10))" in step
    assert "std::log10(std::max(rev, 1.0e-10))" in step
    assert "log_fwd = std::log10(std::max(fwd, 1.0e-10));" in standalone
    assert "log_rev = std::log10(std::max(rev, 1.0e-10));" in standalone


def test_python_bremsmap_minimum_ncn2_keeps_source_tail_capacity():
    n = 999
    state = XSTARPythonState()
    state.control["ncn2"] = n
    state.control["ncn2m"] = n
    state.radiation.epi = np.geomspace(0.1, 1.0e6, n)
    state.radiation.bremsa = np.linspace(10.0, 1.0, n)
    state.radiation.epim = np.geomspace(0.1, 1.0e6, n)
    state.radiation.bremsam = np.zeros(n)
    state.radiation.bremsint = np.zeros(n + 1)
    result = apply_bremsmap_to_state(state)
    assert result.ncn2 == n
    assert result.ncn2m == n
    assert result.bremsint_after.size == n + 1
    assert np.all(np.isfinite(result.bremsint_after))
    assert state.radiation.bremsint.size == n + 1


def test_physical_runner_allocates_bremsint_tail_for_ncn2_999():
    source = (ROOT / "src/xstar_tools/xstar/physical_runner.py").read_text()
    assert "bremsint_capacity = max(ncn2, ncn2m + 1)" in source
    emis = (ROOT / "src/xstar_tools/xstar/emergent_emissivity.py").read_text()
    assert "bremsint.size < epi.size" in emis
    assert "bremsint = bremsint[: epi.size]" in emis
