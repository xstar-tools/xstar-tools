from pathlib import Path
import importlib.util
import sys
import numpy as np
import pytest


def load_example():
    pytest.importorskip("astropy")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    path = root / "examples" / "19_o7_cascade_source_fit.py"
    spec = importlib.util.spec_from_file_location("o7_source_fit", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_project_to_simplex_basic():
    mod = load_example()
    w = mod.project_to_simplex(np.array([0.2, -1.0, 3.0]))
    assert np.all(w >= 0.0)
    assert abs(float(w.sum()) - 1.0) < 1e-12


def test_fit_nonnegative_simplex_exact_basis():
    mod = load_example()
    Y = np.eye(3)
    target = np.array([0.2, 0.3, 0.5])
    w, info = mod.fit_nonnegative_simplex(Y, target, max_iter=5000)
    assert np.all(w >= 0.0)
    assert abs(float(w.sum()) - 1.0) < 1e-12
    assert np.linalg.norm(w - target) < 1e-5
    assert info["status"] in {"converged", "max_iter"}
