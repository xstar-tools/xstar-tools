from __future__ import annotations

import math
import os
import sys
import types

import numpy as np


def _install_astropy_stub() -> None:
    try:
        import astropy.io.fits  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    astropy = types.ModuleType("astropy")
    io = types.ModuleType("astropy.io")
    fits = types.ModuleType("astropy.io.fits")
    astropy.io = io
    io.fits = fits
    sys.modules.setdefault("astropy", astropy)
    sys.modules.setdefault("astropy.io", io)
    sys.modules.setdefault("astropy.io.fits", fits)


def test_native_spectral_scalar_contributions_are_exact(monkeypatch) -> None:
    from xstar_tools.xstar.cpp_backend_spectral import apply_spectral_contributions_cpp

    rcem = np.zeros((2, 8), dtype=np.float64)
    oplin = np.zeros(8, dtype=np.float64)
    cemab = np.zeros((2, 8), dtype=np.float64)
    cabab = np.zeros(8, dtype=np.float64)
    opakab = np.zeros(8, dtype=np.float64)
    rccemis = np.zeros((2, 64), dtype=np.float64)
    opakc = np.zeros(64, dtype=np.float64)
    opakcont = np.zeros(64, dtype=np.float64)
    fline = np.zeros((2, 8), dtype=np.float64)
    flinel = np.zeros(64, dtype=np.float64)
    epi = np.arange(64, dtype=np.float64) * 10.0 + 100.0

    rows = [
        {
            "source_position": 1, "record": 1, "kind": 1, "output_index": 1,
            "ptmp1": 0.75, "ptmp2": 0.25, "abundance_lower": 0.4,
            "abundance_upper": 0.6, "hydrogen_density": 2.0,
            "ans3": -3.0, "ans4": -5.0, "opakab": 7.0,
        },
        {
            "source_position": 2, "record": 2, "kind": 2, "rate_type": 4,
            "output_index": 2, "ptmp1": 0.6, "ptmp2": 0.4,
            "abundance_lower": 0.3, "abundance_upper": 0.7,
            "ans3": -2.0, "opakab": 11.0,
        },
        {"source_position": 3, "record": 3, "kind": 3, "output_index": 3, "opakab": 13.0},
    ]
    metrics = apply_spectral_contributions_cpp(
        rows, rcem=rcem, oplin=oplin, cemab=cemab, cabab=cabab,
        opakab=opakab, rccemis=rccemis, opakc=opakc, opakcont=opakcont,
        fline=fline, flinel=flinel, epi_eV=epi,
    )
    assert metrics["contributions_committed"] == 3
    assert metrics["source_order_violations"] == 0
    assert opakab[1] == 7.0
    assert cabab[1] == abs(-5.0) * 0.4 * 2.0
    assert cemab[0, 1] == 0.75 * abs(-3.0) * 0.6 * 2.0
    assert cemab[1, 1] == 0.25 * abs(-3.0) * 0.6 * 2.0
    assert rcem[0, 2] == -0.7 * -2.0 * 0.6
    assert rcem[1, 2] == -0.7 * -2.0 * 0.4
    assert oplin[2] == 11.0 * 0.3
    assert opakab[3] == 13.0


def test_native_line_profile_and_product_source_validations(monkeypatch) -> None:
    from xstar_tools.xstar.cpp_backend_spectral import apply_spectral_contributions_cpp

    rcem = np.zeros((2, 8), dtype=np.float64)
    oplin = np.zeros(8, dtype=np.float64)
    cemab = np.zeros((2, 8), dtype=np.float64)
    cabab = np.zeros(8, dtype=np.float64)
    opakab = np.zeros(8, dtype=np.float64)
    rccemis = np.zeros((2, 128), dtype=np.float64)
    opakc = np.zeros(128, dtype=np.float64)
    opakcont = np.zeros(128, dtype=np.float64)
    fline = np.zeros((2, 8), dtype=np.float64)
    flinel = np.zeros(128, dtype=np.float64)
    epi = np.arange(128, dtype=np.float64) * 2.0 + 250.0
    seed = np.exp(-0.25 * np.square(np.arange(21, dtype=np.float64) - 10.0))
    row = {
        "source_position": 1, "record": 4, "kind": 4, "rate_type": 4,
        "output_index": 4, "bin_one_based": 76,
        "ptmp1": 0.55, "ptmp2": 0.45,
        "abundance_lower": 0.2, "abundance_upper": 0.8,
        "ans1": 1.0, "ans2": 2.0, "opakab": 0.5,
        "line_energy_eV": 400.0, "bin_width_eV": 2.0,
        "atomic_mass_amu": 24.0, "natural_width_eV": 1.0e-3,
        "turbulent_velocity_km_s": 100.0, "temperature_1e4K": 6.5,
        "seed_profiles": seed,
    }
    metrics = apply_spectral_contributions_cpp(
        [row], rcem=rcem, oplin=oplin, cemab=cemab, cabab=cabab,
        opakab=opakab, rccemis=rccemis, opakc=opakc, opakcont=opakcont,
        fline=fline, flinel=flinel, epi_eV=epi,
    )
    assert metrics["line_profiles"] == 1
    assert oplin[4] == 0.1
    assert fline[0, 4] > 0.0 and fline[1, 4] > 0.0
    assert flinel[75] > 0.0
    assert np.count_nonzero(opakc) > 0
    assert np.all(np.isfinite(opakc))

    _install_astropy_stub()
    monkeypatch.setenv("XSTAR_ATOMIC_SPECTRAL_ENGINE_CPP", "1")
    monkeypatch.setenv("XSTAR_ATOMIC_SPECTRAL_ENGINE_CPP_PRODUCT", "1")
    monkeypatch.setenv("XSTAR_ATOMIC_SPECTRAL_ENGINE_CPP_STRICT", "1")
    from xstar_tools.xstar.emissivity import run_source_order_validation
    from xstar_tools.xstar.emergent_emissivity import run_calc_emis_source_order_validation
    assert run_source_order_validation()["calc_emisab_all_source_acceptance_ready"] is True
    assert run_calc_emis_source_order_validation()["calc_emis_all_source_acceptance_ready"] is True
