import importlib.util
from pathlib import Path


def load_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "26_o7_high_density_rate_sensitivity.py"
    spec = importlib.util.spec_from_file_location("o7_rate_sensitivity", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_build_scan_cases_includes_expected_families():
    mod = load_module()
    cases = mod.build_scan_cases(["metastable", "type68", "type69"], [0.5, 1.0, 2.0])
    names = {case["case"] for case in cases}
    assert "baseline" in names
    assert "metastable_2_345_x0p5" in names
    assert "metastable_2_345_x2" in names
    assert "type68_x0p5" in names
    assert "type69_x2" in names
    # Factor 1.0 is represented by baseline, not duplicate scan rows.
    assert all(not name.endswith("x1") for name in names if name != "baseline")


def test_metastable_case_scales_level_2_to_345_pairs():
    mod = load_module()
    cases = mod.build_scan_cases(["metastable"], [0.2])
    case = next(c for c in cases if c["case"] != "baseline")
    assert case["pair_scales"] == ["2:3:0.2", "2:4:0.2", "2:5:0.2"]
    assert case["data_type_scales"] == []


def test_type68_case_uses_data_type_scale():
    mod = load_module()
    cases = mod.build_scan_cases(["type68"], [5.0])
    case = next(c for c in cases if c["case"] != "baseline")
    assert case["data_type_scales"] == ["68:5"]
    assert case["pair_scales"] == []
