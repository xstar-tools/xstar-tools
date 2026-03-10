from pathlib import Path
import csv
import json


def test_saved_xstar_comparison_artifacts_exist_and_parse():
    root = Path(__file__).resolve().parents[1]
    base = root / "docs" / "validation" / "xstar_outputs"
    expected = [
        "compare_o8_lya_wavelength.csv",
        "compare_o8_lya_wavelength.json",
        "compare_o8_lya_both.csv",
        "compare_o8_lya_both.json",
        "compare_o7_triplet_wavelength.csv",
        "compare_o7_triplet_wavelength.json",
    ]
    for name in expected:
        assert (base / name).is_file(), name

    with (base / "compare_o8_lya_wavelength.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert max(abs(float(r["delta_wavelength_A"])) for r in rows) < 2.0e-5

    with (base / "compare_o7_triplet_wavelength.json").open() as f:
        data = json.load(f)
    comparisons = data.get("comparisons", data if isinstance(data, list) else [])
    assert len(comparisons) >= 4
    assert max(abs(float(r["delta_wavelength_A"])) for r in comparisons) < 1.0e-5
