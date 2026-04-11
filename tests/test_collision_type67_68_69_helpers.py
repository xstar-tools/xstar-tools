import math

import pytest

pytest.importorskip("astropy")

from xstar_atomic.collisions import (
    calt67_upsilon,
    calt68_upsilon,
    calt69_upsilon,
    evaluate_collision_row,
)


def test_calt67_polynomial():
    # gamma = 1 + 2 logT + 3 logT^2 at logT=6
    assert math.isclose(calt67_upsilon([1.0, 2.0, 3.0], 1.0e6), 121.0)


def test_calt68_polynomial_uses_z_cubed_scaling():
    # z=2, T=8e6 => log10(T/z^3)=6
    assert math.isclose(calt68_upsilon([1.0, 2.0, 3.0], [10, 20, 2], 8.0e6), 121.0)


def test_calt69_returns_nonnegative_for_simple_six_coefficients():
    val = calt69_upsilon([10.0, 1.0, 0.1, 0.01, 0.001, 0.0001], 1.0e6)
    assert val is not None
    assert val >= 0.0


def test_evaluate_type67_row_produces_rates():
    row = {
        "record": 1,
        "element": "O",
        "ion_stage": 7,
        "ion_roman": "VII",
        "data_type": 67,
        "rate_type": 3,
        "source_format": "helike_keenan_mccann_kingston_type67",
        "lower_level": 2,
        "upper_level": 3,
        "lower_label": "a",
        "upper_label": "b",
        "n_lower": 2,
        "l_lower": 0,
        "n_upper": 2,
        "l_upper": 1,
        "type63_iq": None,
        "delta_e_level_eV": 1.0,
        "wavelength_from_levels_A": 12398.4,
        "g_lower": 3.0,
        "g_upper": 9.0,
        "helike_fit_reals": "[1.0, 0.0, 0.0]",
        "helike_fit_ints": "[2, 3, 8]",
    }
    out = evaluate_collision_row(row, 1.0e6, [])
    assert out["eval_method"] == "helike_calt67_keenan_polynomial"
    assert out["upsilon"] == 1.0
    assert out["q_excitation_cm3_s"] > 0
    assert out["q_deexcitation_cm3_s"] > 0
