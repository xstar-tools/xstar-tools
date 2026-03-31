from pathlib import Path
import csv
import json


def _root():
    return Path(__file__).resolve().parents[1]


def test_neon_xstar_test_run_artifacts_present():
    root = _root()
    required = [
        root / "xstar_test_run" / "ne_xi25" / "xout_lines1.fits",
        root / "xstar_test_run" / "ne_xi35" / "xout_lines1.fits",
        root / "xstar_test_run" / "xstar_ne9_triplet_lines.csv",
        root / "xstar_test_run" / "xstar_ne10_lya_lines.csv",
        root / "docs" / "validation" / "xstar_outputs" / "compare_ne9_triplet_wavelength.csv",
        root / "docs" / "validation" / "xstar_outputs" / "compare_ne10_lya_wavelength.csv",
    ]
    for path in required:
        assert path.exists(), path


def test_neon_wavelength_comparison_artifacts():
    root = _root()
    checks = [
        ("compare_ne9_triplet_wavelength", 5),
        ("compare_ne10_lya_wavelength", 2),
    ]
    for stem, expected_rows in checks:
        csv_path = root / "docs" / "validation" / "xstar_outputs" / f"{stem}.csv"
        json_path = root / "docs" / "validation" / "xstar_outputs" / f"{stem}.json"
        rows = list(csv.DictReader(csv_path.open(newline="")))
        assert len(rows) == expected_rows
        assert all(row["match_status"] == "matched" for row in rows)
        assert max(float(row["abs_delta_wavelength_A"]) for row in rows) < 0.02
        data = json.loads(json_path.read_text())
        assert data["summary"]["n_matched_within_tolerance"] == expected_rows
