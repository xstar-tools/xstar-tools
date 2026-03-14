import pytest

pytest.importorskip("astropy")

from xstar_atomic.export import parse_band_specs, compute_band_emissivity_rows


def test_parse_band_specs():
    bands = parse_band_specs(["soft:0.5:2.0", "hard:2.0:10.0"])
    assert bands == [
        {"band_name": "soft", "energy_min_keV": 0.5, "energy_max_keV": 2.0},
        {"band_name": "hard", "energy_min_keV": 2.0, "energy_max_keV": 10.0},
    ]


def test_compute_band_emissivity_rows():
    rows = [
        {
            "ion": "O VIII",
            "temperature_K": 1.0e6,
            "energy_keV": 0.653,
            "line_energy_emissivity_coeff_erg_cm3_s": 2.0,
            "line_photon_emissivity_coeff_cm3_s": 3.0,
            "collision_eval_method": "linear_logT_type56",
        },
        {
            "ion": "O VIII",
            "temperature_K": 1.0e6,
            "energy_keV": 6.7,
            "line_energy_emissivity_coeff_erg_cm3_s": 5.0,
            "line_photon_emissivity_coeff_cm3_s": 7.0,
            "collision_eval_method": "other",
        },
    ]
    bands = parse_band_specs("soft:0.5:2.0 hard:2.0:10.0")
    out = compute_band_emissivity_rows(rows, bands)
    soft = [r for r in out if r["band_name"] == "soft"][0]
    hard = [r for r in out if r["band_name"] == "hard"][0]
    assert soft["n_lines_in_band"] == 1
    assert soft["energy_emissivity_coeff_erg_cm3_s"] == 2.0
    assert hard["n_lines_in_band"] == 1
    assert hard["photon_emissivity_coeff_cm3_s"] == 7.0
