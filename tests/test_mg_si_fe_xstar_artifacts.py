from pathlib import Path
import csv
import json


def _root():
    return Path(__file__).resolve().parents[1]


def test_mg_si_fe_xstar_test_run_artifacts_present():
    root = _root()
    required = [
        root / "xstar_test_run" / "mg_xi25" / "xout_lines1.fits",
        root / "xstar_test_run" / "mg_xi35" / "xout_lines1.fits",
        root / "xstar_test_run" / "si_xi30" / "xout_lines1.fits",
        root / "xstar_test_run" / "si_xi40" / "xout_lines1.fits",
        root / "xstar_test_run" / "fe_xi35" / "xout_lines1.fits",
        root / "xstar_test_run" / "fe_xi45" / "xout_lines1.fits",
        root / "xstar_test_run" / "xstar_mg11_triplet_lines.csv",
        root / "xstar_test_run" / "xstar_mg12_lya_lines.csv",
        root / "xstar_test_run" / "xstar_si13_triplet_lines.csv",
        root / "xstar_test_run" / "xstar_si14_lya_lines.csv",
        root / "xstar_test_run" / "xstar_fe25_ka_lines.csv",
        root / "xstar_test_run" / "xstar_fe26_lya_lines.csv",
    ]
    for path in required:
        assert path.exists(), path


def test_mg_si_fe_wavelength_comparison_artifacts():
    root = _root()
    checks = [
        ("compare_mg11_triplet_wavelength", 5),
        ("compare_mg12_lya_wavelength", 2),
        ("compare_si13_triplet_wavelength", 5),
        ("compare_si14_lya_wavelength", 2),
        ("compare_fe25_ka_wavelength", 4),
        ("compare_fe26_lya_wavelength", 2),
    ]
    base = root / "docs" / "validation" / "xstar_outputs"
    for stem, expected_rows in checks:
        csv_path = base / f"{stem}.csv"
        json_path = base / f"{stem}.json"
        rows = list(csv.DictReader(csv_path.open(newline="")))
        assert len(rows) == expected_rows
        assert all(row["match_status"] == "matched" for row in rows)
        assert max(float(row["abs_delta_wavelength_A"]) for row in rows) < 0.02
        data = json.loads(json_path.read_text())
        assert data["summary"]["n_matched_within_tolerance"] == expected_rows
