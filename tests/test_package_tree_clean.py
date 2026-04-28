from pathlib import Path


def test_generated_density_grid_output_not_bundled_as_files():
    root = Path(__file__).resolve().parents[1]
    generated = root / "o7_solver_source_fit_density_xstar_grid"
    # Some example smoke tests may create an empty output directory at runtime.
    # The package must not bundle generated density-grid products as inputs.
    if generated.exists():
        assert not any(path.is_file() for path in generated.rglob("*"))


def test_compact_o7_density_inputs_bundled_under_xstar_test_run():
    root = Path(__file__).resolve().parents[1]
    expected = [
        "o7_ne1",
        "o7_ne1e4",
        "o7_ne1e8",
        "o7_ne1e10",
        "o7_ne1e12",
    ]
    for dirname in expected:
        assert (root / "xstar_test_run" / dirname / "xstar_o7_triplet_lines.csv").exists()
    assert (root / "xstar_test_run" / "xstar_o7_density_grid_references.csv").exists()
