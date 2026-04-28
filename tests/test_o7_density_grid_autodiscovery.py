from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_packaged_o7_density_reference_csvs_exist():
    expected = {
        "1": ROOT / "xstar_test_run" / "o7_ne1" / "xstar_o7_triplet_lines.csv",
        "10000": ROOT / "xstar_test_run" / "o7_ne1e4" / "xstar_o7_triplet_lines.csv",
        "1e8": ROOT / "xstar_test_run" / "o7_ne1e8" / "xstar_o7_triplet_lines.csv",
        "1e10": ROOT / "xstar_test_run" / "o7_ne1e10" / "xstar_o7_triplet_lines.csv",
        "1e12": ROOT / "xstar_test_run" / "o7_ne1e12" / "xstar_o7_triplet_lines.csv",
    }
    for density, path in expected.items():
        assert path.exists(), f"missing density {density} reference: {path}"
        rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
        assert rows, path


def test_example22_help_documents_auto_xstar_test_run_grid():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "22_o7_solver_source_fit_density_xstar_grid.py"), "--help"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    assert "--auto-xstar-test-run-grid" in proc.stdout
    assert "Preferred packaged-input mode" in proc.stdout


def test_example26_rejects_stale_high_density_grid_target(tmp_path):
    grid = tmp_path / "stale_grid"
    grid.mkdir()
    stale_csv = grid / "o7_solver_source_fit_density_grid.csv"
    xstar_csv = ROOT / "xstar_test_run" / "o7_ne1e12" / "xstar_o7_triplet_lines.csv"
    stale_csv.write_text(
        "electron_density_cm^-3,xstar_lines_csv,xstar_value_column,xstar_R_f_over_i,xstar_G_f_plus_i_over_r\n"
        f"1e12,{xstar_csv},emit_outward,3.20837,10.5622\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples" / "26_o7_high_density_rate_sensitivity.py"),
            "dummy_atdb.fits",
            "--density-grid-dir",
            str(grid),
            "--density",
            "1e12",
            "--out-dir",
            str(tmp_path / "out"),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.returncode != 0
    assert "stale or placeholder" in (proc.stdout + proc.stderr)
