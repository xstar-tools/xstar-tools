from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_type50_python_preserves_literal_zero_wavelength_source_exit():
    from xstar_tools.rates_type50 import evaluate_type50_ucalc_record

    # A deliberately huge A-value makes this regression sensitive to the old
    # bug: without the source wavelength gate the escaped-decay channel is
    # large even though canonical ucalc.f90 exits before evaluating A.
    result = evaluate_type50_ucalc_record(
        {
            "A_s^-1": 1.79e10,
            "f_osc_from_A": 0.0,
            "wavelength_A": 0.0,
        },
        ptmp1=0.3,
        ptmp2=0.7,
        cfrac=0.4,
        bremsa_nb1=1.0e8,
        hydrogen_density_cm3=1.0e12,
        endpoint_energy_eV=10.0,
    )
    assert result["status"] == "evaluated"
    assert result["source_zero_wavelength_gate"] is True
    assert result["ans1_photoexcitation_s^-1"] == 0.0
    assert result["ans2_escaped_decay_s^-1"] == 0.0
    assert result["ans3_cooling_signed_erg_s^-1"] == 0.0
    assert result["ans4_heating_signed_erg_s^-1"] == 0.0
    assert result["radiation_context_required"] is False


def test_type50_nonzero_wavelength_path_is_unchanged():
    from xstar_tools.rates_type50 import evaluate_type50_ucalc_record

    result = evaluate_type50_ucalc_record(
        {
            "A_s^-1": 1.0e8,
            "f_osc_from_A": 0.4,
            "wavelength_A": 1215.67,
        },
        ptmp1=0.2,
        ptmp2=0.4,
        cfrac=0.4,
        bremsa_nb1=2.5e7,
        hydrogen_density_cm3=1.0e12,
        endpoint_energy_eV=10.2,
    )
    assert result["source_zero_wavelength_gate"] is False
    assert result["ans2_escaped_decay_s^-1"] > 0.0
    assert result["ans1_photoexcitation_s^-1"] > 0.0


def test_type56_python_interpolation_floors_only_source_lower_ordinate():
    collisions_src = (ROOT / "src/xstar_tools/collisions.py").read_text()
    assert "y0 = max(1.0e-48, ys[i])" in collisions_src
    assert "y1 = ys[i + 1]" in collisions_src
    pytest.importorskip("astropy")
    from xstar_tools.collisions import interp_type56_upsilon

    # At x=4.5, literal label 56 uses y0=max(1e-48,1)=1 and raw y1=-1,
    # giving zero after the final max(0,cijpp).  Flooring y1 as well (the old
    # Python/C++ behavior) incorrectly leaves a positive value near 0.5.
    value = interp_type56_upsilon([4.0, 5.0], [1.0, -1.0], 10.0**4.5)
    assert value == 0.0
    # nrdt=2 / ntmp=1 is a valid source record.
    assert interp_type56_upsilon([4.0], [3.5], 1.0e6) == pytest.approx(3.5)


def test_cpp_type50_and_type56_literal_source_gates_are_present():
    src = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text()
    assert "has_source_wavelength && stored_wavelength_a <= 1.0e-34" in src
    assert "if (delta_ev <= 1.0e-16) break;" in src
    assert "if (!r || n < 2 || (n % 2) != 0" in src
    assert "const double y1 = r[points + i + 1];" in src


def test_python_ucalc_type56_literal_degenerate_energy_gate_is_present():
    src = (ROOT / "src/xstar_tools/xstar/ucalc.py").read_text()
    assert "r.data_type == 56 and de <= 1.0e-16" in src
    assert "ucalc_label56_degenerate_energy_gate" in src
