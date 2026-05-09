import pytest

pytest.importorskip("astropy")

from xstar_atomic.collisions import (
    calt67_upsilon,
    calt68_upsilon,
    xstar_helike_calt67_68_effective_temperature,
)


def test_xstar_helike_calt67_68_temperature_floor_applies_for_short_wavelength():
    assert xstar_helike_calt67_68_effective_temperature(1.0e5, 3.0) == 2.8777e6 / 3.0


def test_xstar_helike_calt67_68_temperature_floor_does_not_apply_for_high_temperature():
    assert xstar_helike_calt67_68_effective_temperature(1.0e6, 3.0) == 1.0e6


def test_calt67_uses_xstar_effective_temperature_floor():
    # gamma = log10(T_eff) for this synthetic coefficient set.
    g = calt67_upsilon([0.0, 1.0, 0.0], 1.0e5, wavelength_A=3.0)
    assert abs(g - __import__('math').log10(2.8777e6 / 3.0)) < 1e-12


def test_calt68_uses_xstar_effective_temperature_floor():
    # gamma = log10(T_eff / Z^3), with Z=20 from ints[2].
    import math
    g = calt68_upsilon([0.0, 1.0, 0.0], [0, 0, 20], 1.0e5, wavelength_A=3.0)
    assert abs(g - math.log10((2.8777e6 / 3.0) / (20.0 ** 3))) < 1e-12
