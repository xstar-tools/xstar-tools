from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def load_example_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "28_o7_type69_record_audit.py"
    spec = importlib.util.spec_from_file_location("o7_type69_record_audit", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_parse_lists_and_preview():
    mod = load_example_module()
    assert mod.parse_int_list("22490,22491;22492") == [22490, 22491, 22492]
    assert mod.parse_float_list("1e5,3e5;1e6") == [1e5, 3e5, 1e6]
    assert mod.preview_json([1, 2, 3], max_n=2).startswith("[1,2")


def test_best_scan_effect_finds_reachable_case():
    mod = load_example_module()
    rows = [
        {"case": "a", "scale": "1", "R_over_xstar": "0.45", "G_over_xstar": "0.70", "target_reachable": "False"},
        {"case": "b", "scale": "0.1", "R_over_xstar": "1.00005", "G_over_xstar": "1.00001", "target_reachable": "True"},
    ]
    out = mod.best_scan_effect(rows)
    assert out["sensitivity_best_case"] == "b"
    assert out["sensitivity_n_reachable"] == 1
    assert out["sensitivity_reachable_scales"] == "0.1"


def test_temperature_grid_direct_rows_are_well_formed():
    mod = load_example_module()
    raw = [{
        "record": 22490,
        "lower_level": 1,
        "upper_level": 7,
        "lower_label": "1s2 1S0",
        "upper_label": "1s.2p 1P1",
        "delta_e_level_eV": 573.0,
        "delta_e_rdat0_eV": 573.0,
        "lower_g": 1.0,
        "upper_g": 3.0,
        "raw_rdat_json": "[573.0,1,2,3,4,5]",
    }]
    rows = mod.direct_record_temperature_rows(raw, [1e6, 3e6], 1e12)
    assert len(rows) == 2
    assert rows[0]["record"] == 22490
    assert "upsilon_calt69" in rows[0]
    assert "detailed_balance_ratio_over_expected" in rows[0]
