from pathlib import Path


def test_solver_profile_and_stage6_examples_exist():
    root = Path(__file__).resolve().parents[1]
    for rel in [
        "examples/12_profile_solver_steps.py",
        "examples/13_o7_recombination_cascade_workflow.py",
        "examples/21_o7_solver_source_fit_density_grid.py",
    ]:
        path = root / rel
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "if __name__" in text


def test_user_guide_mentions_stage6_workflow():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs/user_guide.md").read_text(encoding="utf-8")
    assert "Solver step profiling" in text
    assert "Prototype O VII recombination/cascade workflow" in text
    assert "O VII density-grid source-fit diagnostic" in text


def test_profile_solver_namespace_defaults():
    """The solver profiler should define all source/sink attributes required by solver helpers."""
    import ast
    from pathlib import Path

    source = Path("examples/12_profile_solver_steps.py").read_text()
    assert "auto_recombination_cascade=False" in source
    assert "recombination_source_csv=None" in source
    assert "adjacent_ion_source_csv=None" in source
