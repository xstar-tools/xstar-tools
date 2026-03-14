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


def test_compute_band_emissivity_rows_preserves_zero_line_metadata():
    rows = [
        {
            "ion": "O VIII",
            "temperature_K": 1.0e6,
            "energy_keV": 0.653,
            "line_energy_emissivity_coeff_erg_cm3_s": 2.0,
            "line_photon_emissivity_coeff_cm3_s": 3.0,
            "collision_eval_method": "linear_logT_type56",
        }
    ]
    bands = parse_band_specs("osoft:0.3:0.6 soft:0.5:2.0")
    out = compute_band_emissivity_rows(rows, bands)
    zero = [r for r in out if r["band_name"] == "osoft"][0]
    assert zero["n_lines_in_band"] == 0
    assert zero["ion"] == "O VIII"
    assert zero["methods_used"] == "none"


def test_real_atdb_band_export_has_no_blank_metadata(tmp_path):
    import csv
    import os
    from pathlib import Path

    fitsfile = os.environ.get("XSTAR_ATDB_FITS")
    if not fitsfile:
        pytest.skip("Set XSTAR_ATDB_FITS to run real export test")
    if not Path(fitsfile).exists():
        pytest.skip(f"XSTAR_ATDB_FITS does not exist: {fitsfile}")

    from xstar_atomic import XSTARAtomic
    from xstar_atomic.export import export_ion_products, parse_band_specs

    db = XSTARAtomic(fitsfile)
    out_dir = tmp_path / "atomic_export"
    bands = parse_band_specs("osoft:0.3:0.6 soft:0.5:2.0")
    export_ion_products(
        db,
        "O VIII",
        out_dir,
        temperatures=[1.0e6],
        wavelength=(1.0, 40.0),
        formats=("csv",),
        bands=bands,
    )

    band_csv = out_dir / "o_viii_band_emissivity.csv"
    assert band_csv.exists()
    with band_csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert all(row.get("ion") == "O VIII" for row in rows)
    assert all(row.get("methods_used") for row in rows)
    assert any(row.get("methods_used") == "none" and int(row.get("n_lines_in_band", "-1")) == 0 for row in rows)
