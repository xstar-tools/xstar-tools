from pathlib import Path
import importlib.util


def load_example_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "27_o7_type69_transition_sensitivity.py"
    spec = importlib.util.spec_from_file_location("o7_type69_transition_sensitivity", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_build_record_cases_and_safe_names():
    mod = load_example_module()
    transitions = [
        {"record": 101, "lower_level": 2, "upper_level": 7, "rate_strength_s^-1": 10.0},
        {"record": 102, "lower_level": 4, "upper_level": 7, "rate_strength_s^-1": 5.0},
    ]
    cases = mod.build_scan_cases(transitions, [0.1, 0.5, 1.0], "record", 1)
    names = [c["case"] for c in cases]
    assert names[0] == "baseline"
    assert "record_101_x0p1" in names
    assert "record_101_x0p5" in names
    assert not any("record_102" in n for n in names)
    rec_case = next(c for c in cases if c["case"] == "record_101_x0p1")
    assert rec_case["record_scales"] == ["101:0.1"]


def test_build_pair_cases_groups_by_level_pair():
    mod = load_example_module()
    transitions = [
        {"record": 101, "lower_level": 7, "upper_level": 4, "rate_strength_s^-1": 10.0},
        {"record": 102, "lower_level": 4, "upper_level": 7, "rate_strength_s^-1": 2.0},
    ]
    cases = mod.build_scan_cases(transitions, [0.2], "pair", 0)
    assert len(cases) == 2
    pair_case = cases[1]
    assert pair_case["case"] == "pair_4_7_x0p2"
    assert pair_case["pair_scales"] == ["4:7:0.2"]
    assert pair_case["transition"]["record"] == 101


def test_density_grid_reference_resolution(tmp_path):
    mod = load_example_module()
    grid = tmp_path / "grid"
    grid.mkdir()
    xstar = tmp_path / "xstar.csv"
    xstar.write_text("wavelength,emit_outward\n", encoding="utf-8")
    (grid / "o7_solver_source_fit_density_grid.csv").write_text(
        "electron_density_cm^-3,xstar_lines_csv,xstar_value_column\n"
        f"1e12,{xstar},emit_outward\n",
        encoding="utf-8",
    )
    path, col, row = mod.xstar_reference_for_density(grid, 1e12)
    assert Path(path) == xstar
    assert col == "emit_outward"
    assert row["electron_density_cm^-3"] == "1e12"
