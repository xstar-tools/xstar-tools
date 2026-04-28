import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_example21():
    path = ROOT / "examples" / "21_o7_solver_source_fit_density_grid.py"
    spec = importlib.util.spec_from_file_location("o7_solver_source_fit_density_grid", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_example21_exists_and_documents_density_grid():
    path = ROOT / "examples" / "21_o7_solver_source_fit_density_grid.py"
    text = path.read_text(encoding="utf-8")
    assert "density-grid diagnostic" in text
    assert "fixed-weight baseline" in text
    assert "o7_solver_source_fit_density_grid.csv" in text
    assert "if __name__" in text


def test_example21_compare_weights_reports_changes():
    mod = _load_example21()
    out = mod.compare_weights({2: 0.5, 3: 0.5}, {2: 0.25, 3: 0.75})
    assert abs(out["weight_delta_l1"] - 0.5) < 1e-12
    assert out["weight_delta_l2"] > 0.0
    assert out["weight_delta_max_abs"] == 0.25
    assert out["top_weight_changes"][0]["source_level"] in {2, 3}


def test_example21_dry_run_reorders_reference_density_first(tmp_path):
    script = ROOT / "examples" / "21_o7_solver_source_fit_density_grid.py"
    cmd = [
        sys.executable,
        str(script),
        "dummy_atdb.fits",
        "--dry-run",
        "--electron-densities",
        "1e4",
        "1",
        "1e8",
        "--reference-density",
        "1",
        "--out-dir",
        str(tmp_path / "grid"),
    ]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
    assert "densities: 1, 10000, 1e+08" in result.stdout
    first_cmd = result.stdout.splitlines()[0]
    assert "--electron-density 1 " in first_cmd
