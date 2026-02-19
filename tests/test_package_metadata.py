from pathlib import Path


def test_package_layout_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "pyproject.toml").exists()
    assert (root / "src" / "xstar_atomic" / "__init__.py").exists()
    assert (root / "src" / "xstar_atomic" / "hierarchy.py").exists()
    assert (root / "src" / "xstar_atomic" / "api.py").exists()


def test_console_modules_exist():
    root = Path(__file__).resolve().parents[1]
    modules = [
        "inspect.py",
        "hierarchy.py",
        "lines.py",
        "photoionization.py",
        "collisions.py",
        "recombination.py",
        "emissivity.py",
        "solver.py",
        "api.py",
    ]
    for module in modules:
        assert (root / "src" / "xstar_atomic" / module).exists()
