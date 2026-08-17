from __future__ import annotations

from pathlib import Path
import math

import numpy as np

from xstar_tools.xstar.source_real_energy_grid import source_ener_grid
from xstar_tools.xstar.parameter_contract import coerce_and_validate_parameter
from xstar_tools.xstar.spectrum_contract import (
    SOURCE_BREMS_EV_PER_T7,
    SOURCE_ERGSEV,
    SOURCE_EXP10_LN10,
    apply_source_spectrum_pass,
    initial_source_spectrum,
    read_canonical_spectrum_file,
    canonical_spectrum_mode,
)


def _band_luminosity(z: np.ndarray, e: np.ndarray) -> float:
    total = 0.0
    for i in range(1, e.size):
        if 13.6 <= float(e[i]) <= 1.36e4:
            total += (float(z[i]) + float(z[i - 1])) * (float(e[i]) - float(e[i - 1])) / 2.0
    return total * SOURCE_ERGSEV


def test_public_parameter_contract_accepts_all_modes_and_spectun2(tmp_path: Path):
    for mode in ("pow", "bbody", "brems", "bremss", "file"):
        assert canonical_spectrum_mode(mode) == mode
    assert coerce_and_validate_parameter("spectun", 2) == 2
    p = tmp_path / "spct.dat"
    p.write_text("2\n13.6 0\n13600 -3\n")
    f = read_canonical_spectrum_file(p, 2)
    assert f.spectun == 2


def test_builtin_modes_normalize_to_rlrad38():
    e = source_ener_grid(999)
    xlum = 3.25
    for mode, trad in (("pow", -1.0), ("bbody", 1.2), ("brems", 10.0), ("bremss", 8.61707)):
        z, _ = initial_source_spectrum(mode=mode, trad=trad, luminosity_1e38=xlum, epi_eV=e)
        assert np.isfinite(z).all()
        assert abs(_band_luminosity(z, e) / xlum - 1.0) < 2e-13


def test_bremss_kev_alias_matches_literal_brems_source_temperature():
    e = source_ener_grid(999)
    kev = 3.0
    z_alias, _ = initial_source_spectrum(mode="bremss", trad=kev, luminosity_1e38=1.0, epi_eV=e)
    z_source, _ = initial_source_spectrum(
        mode="brems", trad=1000.0 * kev / SOURCE_BREMS_EV_PER_T7,
        luminosity_1e38=1.0, epi_eV=e,
    )
    assert np.array_equal(z_alias, z_source)


def _write_powerlaw_file(path: Path, e: np.ndarray, *, unit: int) -> None:
    energy_flux = np.power(e, -1.0)
    if unit == 0:
        flux = energy_flux
    elif unit == 1:
        flux = energy_flux / e
    else:
        flux = np.log10(energy_flux)
    with path.open("w") as h:
        h.write(f"{e.size}\n")
        for ee, ff in zip(e, flux):
            h.write(f"{ee:.17g} {ff:.17g}\n")


def test_file_spectun_0_1_2_are_equivalent_and_match_powerlaw(tmp_path: Path):
    e = source_ener_grid(999)
    reference, _ = initial_source_spectrum(mode="pow", trad=-1.0, luminosity_1e38=2.0, epi_eV=e)
    candidates = []
    for unit in (0, 1, 2):
        p = tmp_path / f"spct_{unit}.dat"
        _write_powerlaw_file(p, e, unit=unit)
        z, file_data = initial_source_spectrum(
            mode="file", trad=-1.0, luminosity_1e38=2.0, epi_eV=e,
            spectrum_file=p, spectun=unit,
        )
        assert file_data is not None and file_data.spectun == unit
        candidates.append(z)
        assert np.max(np.abs(z-reference) / np.maximum(np.abs(reference), 1e-300)) < 2.0e-5
    assert np.allclose(candidates[0], candidates[1], rtol=2e-14, atol=0.0)
    assert np.allclose(candidates[0], candidates[2], rtol=2e-14, atol=0.0)


def test_file_interpolation_uses_source_exp10_approximation(tmp_path: Path):
    p = tmp_path / "spct.dat"
    p.write_text("2\n10 1e3\n100 1e2\n")
    f = read_canonical_spectrum_file(p, 0)
    x = math.sqrt(1000.0)
    e = np.asarray([10.0, x, 100.0])
    z = apply_source_spectrum_pass(
        np.zeros(e.size), mode="file", trad=-1.0, luminosity_1e38=1.0,
        epi_eV=e, file_spectrum=f,
    )
    # ispecg.f90 calls exp10.f90, whose implementation is exp(2.30259*x),
    # not the language intrinsic 10**x.  After common normalization, the
    # midpoint/endpoint shape retains that source approximation.
    expected_shape = math.exp(SOURCE_EXP10_LN10 * (2.5 - 2.0))
    assert abs(z[1] / z[2] - expected_shape) < 2e-12


def test_file_log_interpolation_and_zero_outside_endpoints(tmp_path: Path):
    p = tmp_path / "spct.dat"
    p.write_text("3\n10 1e3\n100 1e2\n1000 1e1\n")
    f = read_canonical_spectrum_file(p, 0)
    e = np.asarray([5.0, 10.0, 31.622776601683793, 100.0, 1000.0, 2000.0])
    z = apply_source_spectrum_pass(
        np.zeros(e.size), mode="file", trad=-1.0, luminosity_1e38=1.0,
        epi_eV=e, file_spectrum=f,
    )
    assert z[0] == 0.0
    assert z[-1] == 0.0
    # The interior shape is E^-1 under log-log interpolation.
    ratio = z[2] / z[3]
    assert abs(ratio - math.exp(SOURCE_EXP10_LN10 * 0.5)) < 1e-12


def test_repeated_pass_contract_preserves_source_mode_semantics(tmp_path: Path):
    e = source_ener_grid(999)
    # Additive modes add a new source component before ispecgg.
    z1, _ = initial_source_spectrum(mode="pow", trad=-1.0, luminosity_1e38=1.0, epi_eV=e)
    z2 = apply_source_spectrum_pass(z1, mode="pow", trad=-1.0, luminosity_1e38=1.0, epi_eV=e)
    assert abs(_band_luminosity(z2,e)-1.0) < 2e-13
    # ispec brems assigns a fresh component, so repeated-pass output is exact.
    b1, _ = initial_source_spectrum(mode="brems", trad=10.0, luminosity_1e38=1.0, epi_eV=e)
    b2 = apply_source_spectrum_pass(b1, mode="brems", trad=10.0, luminosity_1e38=1.0, epi_eV=e)
    assert np.array_equal(b1,b2)


def test_cpp_public_path_contains_complete_spectrum_dispatch():
    root = Path(__file__).resolve().parents[1]
    cpp = (root / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    contract = (root / "src/xstar_tools/xstar/cpp/xstar_parameter_contract.hpp").read_text()
    for token in (
        'return "pow";', 'return "bbody";', 'return "brems";', 'return "bremss";', 'return "file";',
        'read_canonical_public_spectrum_file_v068228', 'source_ispecg_component_v068228',
        'source_starf_component_v068228', 'source_ispec_brems_component_v068228',
        'source_spectrum_pass_v068228',
    ):
        assert token in cpp
    assert '{"spectun", ParameterKind::Integer, "0", true, 0.0, true, 2.0}' in contract
