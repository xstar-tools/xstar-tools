import pytest
pytest.importorskip("astropy")
from xstar_atomic.xstar_element_solver import _type50_effective_rates, _build_xstar_output_bremsa_grid


def test_xstar_output_bremsa_grid_applies_trnfrc_dilution():
    rows = [
        {"energy": "100", "transmitted": "1.0e20"},
        {"energy": "1000", "transmitted": "2.0e20"},
    ]
    grid, bremsa, status = _build_xstar_output_bremsa_grid(rows, column="transmitted", radius_cm=1.0e19)
    assert grid == [100.0, 1000.0]
    assert "diluted_by_12p56" in status
    assert abs(bremsa[0] - 1.0e20 / 12.56) / (1.0e20 / 12.56) < 1e-12


def test_type50_pumping_uses_xstar_output_grid_instead_of_proxy():
    row = {"data_type": 50, "rate_type": 4, "rate_s^-1": 1.0e8, "wavelength_A": 10.0, "element": "O"}
    up = {"energy_eV": 1239.84016, "statistical_weight_g": 3.0, "level_label": "upper"}
    lo = {"energy_eV": 0.0, "statistical_weight_g": 1.0, "level_label": "lower"}
    out = _type50_effective_rates(
        row,
        treatment="xstar-line-escape-and-pumping",
        from_state=up,
        to_state=lo,
        temperature_K=1.0e6,
        radiation_field_mode="xstar-output",
        xstar_radiation_epi_grid=[100.0, 1000.0, 2000.0],
        xstar_radiation_bremsa_grid=[0.0, 1.0e5, 0.0],
        xstar_radiation_grid_status="unit-test-grid",
        type50_cfrac=0.0,
    )
    assert out["photoexcitation_rate_s^-1"] > 0.0
    assert out["type50_photoexcitation_status"] == "evaluated_xstar_ucalc_type50_with_explicit_epi_bremsa_grid"
    assert out["type50_photoexcitation_radiation_grid_status"] == "unit-test-grid"


def test_type50_pumping_missing_xstar_output_grid_is_zero_not_proxy():
    row = {"data_type": 50, "rate_type": 4, "rate_s^-1": 1.0e8, "wavelength_A": 10.0, "element": "O"}
    up = {"energy_eV": 1239.84016, "statistical_weight_g": 3.0}
    lo = {"energy_eV": 0.0, "statistical_weight_g": 1.0}
    out = _type50_effective_rates(
        row,
        treatment="xstar-line-escape-and-pumping",
        from_state=up,
        to_state=lo,
        temperature_K=1.0e6,
        radiation_field_mode="xstar-output",
        xstar_radiation_epi_grid=[],
        xstar_radiation_bremsa_grid=[],
        type50_cfrac=0.0,
    )
    assert out["photoexcitation_rate_s^-1"] == 0.0
    assert out["type50_photoexcitation_status"] == "not_evaluated_missing_xstar_output_bremsa_grid"
