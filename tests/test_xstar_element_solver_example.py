from pathlib import Path
import subprocess
import sys


def test_xstar_like_element_solver_dry_run(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "element_solver_dry"
    cmd = [
        sys.executable,
        str(root / "examples" / "42_xstar_like_element_solver_demo.py"),
        "../xstar/data/atdb.fits",
        "--element", "C",
        "--he-like-stage", "5",
        "--temperature", "1000000",
        "--electron-density", "1e8",
        "--wavelength-min", "40",
        "--wavelength-max", "42",
        "--out-dir", str(out),
        "--dry-run",
        "--print-summary",
    ]
    result = subprocess.run(cmd, cwd=root, text=True, capture_output=True, check=True)
    assert "dry run" in result.stdout.lower()
    assert (out / "xstar_like_element_solver_summary.md").exists()
    assert (out / "xstar_like_element_solver_commands.csv").exists()
    assert (out / "xstar_like_element_solver_adjacent_coupling_terms.csv").exists()
    assert (out / "xstar_like_element_solver_ucalc_adjacent_audit.csv").exists()
    assert (out / "xstar_like_element_solver_superlevel_cascade_audit.csv").exists()
    assert (out / "xstar_like_element_solver_superlevel_branching_audit.csv").exists()
    assert (out / "xstar_like_element_solver_superlevel_source_audit.csv").exists()
