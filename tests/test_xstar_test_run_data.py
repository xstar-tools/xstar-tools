from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
XSTAR_TEST_RUN = ROOT / "xstar_test_run"


def read_csv_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_xstar_test_run_files_are_packaged():
    assert (XSTAR_TEST_RUN / "README.md").is_file()
    assert (XSTAR_TEST_RUN / "o_ne_xi3" / "xout_lines1.fits").is_file()
    assert (XSTAR_TEST_RUN / "o7_xi15" / "xout_lines1.fits").is_file()
    assert (XSTAR_TEST_RUN / "o7_xi15_highdens" / "xout_lines1.fits").is_file()
    assert (XSTAR_TEST_RUN / "xstar_o_ne_xi3_lines.csv").is_file()
    assert (XSTAR_TEST_RUN / "xstar_o8_lya_lines.csv").is_file()
    assert (XSTAR_TEST_RUN / "xstar_o7_triplet_lines.csv").is_file()


def test_xstar_test_run_filtered_csv_contents():
    o8 = read_csv_rows(XSTAR_TEST_RUN / "xstar_o8_lya_lines.csv")
    assert len(o8) == 2
    assert {row["ion"].strip().lower().replace("_", " ") for row in o8} == {"o viii"}
    waves = sorted(float(row["wavelength"]) for row in o8)
    assert abs(waves[0] - 18.9671) < 1.0e-4
    assert abs(waves[1] - 18.9725) < 1.0e-4

    o7 = read_csv_rows(XSTAR_TEST_RUN / "xstar_o7_triplet_lines.csv")
    assert len(o7) == 5
    assert {row["ion"].strip().lower().replace("_", " ") for row in o7} == {"o vii"}
    o7_waves = sorted(float(row["wavelength"]) for row in o7)
    assert any(abs(w - 22.1012) < 1.0e-4 for w in o7_waves)
    assert any(abs(w - 21.6020) < 1.0e-4 for w in o7_waves)


def test_xstar_test_run_fits_conversion_matches_csv(tmp_path):
    import pytest

    pytest.importorskip("astropy")
    from xstar_atomic.xstar_outputs import load_xstar_lines, write_csv

    rows = load_xstar_lines(
        XSTAR_TEST_RUN / "o_ne_xi3" / "xout_lines1.fits",
        ion="O VIII",
        wavelength_min=18.8,
        wavelength_max=19.1,
    )
    assert len(rows) == 2

    out = tmp_path / "o8_from_fits.csv"
    write_csv(out, rows)
    converted = read_csv_rows(out)
    packaged = read_csv_rows(XSTAR_TEST_RUN / "xstar_o8_lya_lines.csv")
    assert [float(r["wavelength"]) for r in converted] == [float(r["wavelength"]) for r in packaged]
