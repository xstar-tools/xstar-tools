import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REF_CSV = ROOT / "examples" / "reference_outputs" / "o7_density_grid_type69_mode_compare.csv"
REF_JSON = ROOT / "examples" / "reference_outputs" / "o7_density_grid_type69_mode_compare_summary.json"
DOC_CSV = ROOT / "docs" / "validation" / "xstar_outputs" / "o7_density_grid_type69_mode_compare.csv"
DOC_JSON = ROOT / "docs" / "validation" / "xstar_outputs" / "o7_density_grid_type69_mode_compare_summary.json"


def _read_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _row_for_density(rows, density):
    for row in rows:
        if abs(float(row["electron_density_cm^-3"]) - float(density)) / float(density) < 1e-9:
            return row
    raise AssertionError(f"density {density} not found")


def test_o7_type69_mode_compare_reference_snapshots_exist_and_match_docs():
    assert REF_CSV.is_file()
    assert REF_JSON.is_file()
    assert DOC_CSV.is_file()
    assert DOC_JSON.is_file()
    assert REF_CSV.read_text(encoding="utf-8") == DOC_CSV.read_text(encoding="utf-8")
    assert json.loads(REF_JSON.read_text(encoding="utf-8"))["note"].startswith("Diagnostic/experimental comparison")
    assert json.loads(DOC_JSON.read_text(encoding="utf-8"))["note"].startswith("Diagnostic/experimental comparison")


def test_o7_type69_mode_compare_reference_high_density_behavior():
    rows = _read_rows(REF_CSV)
    assert len(rows) == 5
    high = _row_for_density(rows, 1e12)
    assert high["include_target_reachable"] == "False"
    assert high["suppress_resonance_target_reachable"] == "True"
    assert float(high["include_R_f_over_i"]) < 0.05
    assert abs(float(high["suppress_resonance_R_f_over_i"]) / float(high["xstar_R_f_over_i"]) - 1.0) < 1e-3
    assert abs(float(high["suppress_resonance_G_f_plus_i_over_r"]) / float(high["xstar_G_f_plus_i_over_r"]) - 1.0) < 1e-3
    assert float(high["mismatch_improvement_factor"]) > 1000.0
    assert float(high["source_weight_l1_change_suppress_minus_include"]) > 0.5


def test_o7_type69_mode_compare_reference_low_density_remains_reachable():
    rows = _read_rows(REF_CSV)
    for density in [1, 1e4, 1e8, 1e10]:
        row = _row_for_density(rows, density)
        assert row["include_target_reachable"] == "True"
        assert row["suppress_resonance_target_reachable"] == "True"
        assert 0.9 < float(row["mismatch_improvement_factor"]) < 1.2
