from types import SimpleNamespace
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from xstar_tools.xstar import cpp_backend_thermal as _thermal_backend
from xstar_tools.xstar.cpp_backend_thermal import (
    apply_heatt_cpp,
    run_dsec_cpp,
    thermal_engine_status,
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_native_thermal_library():
    """Build only the native thermal test dependency when it is not prebuilt."""
    root = Path(__file__).resolve().parents[1]
    cpp_dir = root / "src/xstar_tools/xstar/cpp"
    library = cpp_dir / "libxstar_thermal.so"
    built_here = not library.exists()
    if built_here:
        if shutil.which("g++") is None or shutil.which("make") is None:
            pytest.skip("native thermal characterization requires g++ and make")
        proc = subprocess.run(
            ["make", "-C", str(cpp_dir), "libxstar_thermal.so"],
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            pytest.skip("could not build native thermal characterization library: " + proc.stderr[-1000:])
    _thermal_backend._LIB = None
    try:
        yield
    finally:
        _thermal_backend._LIB = None
        if built_here:
            library.unlink(missing_ok=True)


def test_native_thermal_engine_status():
    status = thermal_engine_status()
    assert status["available"]
    assert status["abi_version"] == 60471
    assert status["feature_flags"] & 1
    assert status["feature_flags"] & 2


def test_native_dsec_orchestration_converges():
    state = SimpleNamespace(
        temperature_t4=1.0,
        electron_fraction_xee=1.0,
        hydrogen_density_cm3=1.0e8,
        calc_hmc_all_call_count=0,
    )

    def evaluator(runtime):
        runtime.calc_hmc_all_call_count += 1
        return SimpleNamespace(
            hmctot=2.0 - runtime.temperature_t4,
            elcter=runtime.electron_fraction_xee - 1.5,
        )

    result = run_dsec_cpp(
        state,
        evaluator,
        nlim=24,
        tinf_t4=0.099,
        charge_tolerance=float(np.float32(1.0e-4)),
        thermal_tolerance=float(np.float32(1.0e-4)),
        temperature_stagnation_tolerance=float(np.float32(2.0e-9)),
    )
    assert result["charge_converged"]
    assert result["thermal_converged"]
    assert result["evaluations_completed"] == state.calc_hmc_all_call_count
    assert state.temperature_t4 == 2.0
    assert state.electron_fraction_xee == 1.5



def test_native_dsec_propagates_callback_committed_state():
    state = SimpleNamespace(
        temperature_t4=1.0,
        electron_fraction_xee=1.0,
        hydrogen_density_cm3=1.0e8,
        calc_hmc_all_call_count=0,
    )

    def evaluator(runtime):
        runtime.calc_hmc_all_call_count += 1
        runtime.temperature_t4 = 1.25
        runtime.electron_fraction_xee = 1.125
        runtime.hydrogen_density_cm3 = 2.0e8
        return SimpleNamespace(hmctot=0.0, elcter=0.0)

    result = run_dsec_cpp(
        state, evaluator, nlim=0, tinf_t4=0.099,
        charge_tolerance=float(np.float32(1.0e-4)),
        thermal_tolerance=float(np.float32(1.0e-4)),
        temperature_stagnation_tolerance=float(np.float32(2.0e-9)),
    )
    assert result["callback_state_propagation"]
    assert result["evaluations_completed"] == 1
    assert result["trace_count"] >= 3
    assert state.temperature_t4 == 1.25
    assert state.electron_fraction_xee == 1.125
    assert state.hydrogen_density_cm3 == 2.0e8
    assert result["final_temperature_t4"] == 1.25
    assert result["final_electron_fraction_xee"] == 1.125

def test_native_heatt_matches_frozen_fortran_fixture():
    n, nl, nc = 4, 2, 2
    epi = np.array([1.0, 10.0, 100.0, 1000.0])
    incident = np.array([2.0, 3.0, 4.0, 5.0])
    opakc = np.array([0.02, 0.1, 1.0, 0.04])
    opakcont = np.array([0.01, 0.2, 0.8, 0.4])
    flinel = np.array([1.0, 2.0, 3.0, 4.0])
    brcems = np.array([0.005, 0.006, 0.007, 0.008])
    rccemis = np.array([[0.01, 0.02, 0.03, 0.04], [0.04, 0.03, 0.02, 0.01]])
    zrems = np.empty((5, n))
    zremso = np.empty((5, n))
    for row in range(5):
        for col in range(n):
            zrems[row, col] = -1000.0 * (row + 1) - (col + 1)
            zremso[row, col] = 100.0 * (row + 1) + (col + 1)
    elum = np.full((2, nl), -900.0)
    elumo = np.array([[5.0, 7.0], [6.0, 8.0]])
    rcem = np.array([[0.1, 0.3], [0.2, 0.4]])
    elumab = np.full((2, nc), -600.0)
    elumabo = np.array([[9.0, 11.0], [10.0, 12.0]])
    cemab = np.array([[0.03, 0.0], [0.05, 0.0]])
    result = apply_heatt_cpp(
        lines=[
            {"record": 4, "rate_type": 4, "wavelength_angstrom": 10.0},
            {"record": 5, "rate_type": 50, "wavelength_angstrom": 20.0},
        ],
        rrcs=[
            {"record": 6, "continuum_index_one_based": 1, "destination_level": 1, "active": True},
            {"record": 7, "continuum_index_one_based": 2, "destination_level": 1, "active": False},
        ],
        temperature_1e4K=2.0,
        radius_cm=2.0e19,
        covering_fraction=0.3,
        zone_thickness_cm=0.25,
        electron_fraction_xee=1.2,
        hydrogen_density_cm3=5.0,
        epi_eV=epi,
        bremsa=incident,
        opakc=opakc,
        opakcont=opakcont,
        flinel=flinel,
        brcems=brcems,
        zrems=zrems,
        zremso=zremso,
        elum=elum,
        elumo=elumo,
        rcem=rcem,
        elumab=elumab,
        elumabo=elumabo,
        cemab=cemab,
        rccemis=rccemis,
        ncn2=n,
        n_lines=nl,
        n_continua=nc,
    )
    assert result["native_heatt"]
    np.testing.assert_allclose(
        zrems,
        np.array([
            [109.17404856295778, 107.00339898608938, 66.50385820812258, 110.60463113327397],
            [202.85360492385408, 205.44313626153624, 207.5293677704822, 210.71820750863256],
            [307.82284365588839, 307.28155290796735, 306.42668655671304, 306.38590547035551],
            [402.85360492385405, 405.40063059293834, 407.63968123502218, 410.42523910229369],
            [507.82284365588839, 507.21635190500496, 506.51014404683497, 506.28186061576787],
        ]),
        rtol=0.0,
        atol=2e-12,
    )
    np.testing.assert_allclose(elum[:, 0], [5.75600004196167, 8.51200008392334], rtol=0.0, atol=2e-12)
    np.testing.assert_allclose(elumab[:, 0], [9.502400016784668, 10.502400016784668], rtol=0.0, atol=2e-12)
