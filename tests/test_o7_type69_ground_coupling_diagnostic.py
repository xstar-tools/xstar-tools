import csv
import importlib.util
from pathlib import Path


def load_example(name):
    path = Path(__file__).resolve().parents[1] / "examples" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_ground_coupling_case_builder_includes_direction_isolation():
    mod = load_example("29_o7_type69_ground_coupling_diagnostic.py")
    cases = mod.build_cases(22490, [0.1, 0.5, 2.0], [0.1], [0.0, 0.5, 2.0])
    names = {c["case"] for c in cases}
    assert "baseline" in names
    assert "record_22490_x0p1" in names
    assert "type69_x0p1" in names
    assert "record_22490_removed" in names
    assert "record_22490_excitation_only" in names
    assert "record_22490_deexcitation_only" in names
    assert any("22490:deexcitation:0" in ";".join(c.get("direction_scales") or []) for c in cases)
    assert any("22490:excitation:0" in ";".join(c.get("direction_scales") or []) for c in cases)


def test_type69_record_audit_annotation_lookup_recursive(tmp_path):
    mod = load_example("28_o7_type69_record_audit.py")
    out = tmp_path / "parent" / "o7_type69_transition_sensitivity"
    out.mkdir(parents=True)
    csv_path = out / "o7_type69_transition_sensitivity.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["case", "record", "scale", "R_over_xstar", "G_over_xstar", "target_reachable"])
        writer.writeheader()
        writer.writerow({"case": "record_22490_x0p1", "record": "22490", "scale": "0.1", "R_over_xstar": "1.0", "G_over_xstar": "1.0", "target_reachable": "True"})
    rows = mod.find_transition_scan_rows(str(tmp_path / "parent"))
    assert 22490 in rows
    best = mod.best_scan_effect(rows[22490])
    assert best["sensitivity_best_case"] == "record_22490_x0p1"
    assert best["sensitivity_n_reachable"] == 1


def test_ground_coupling_top_weight_ignores_empty_directory_path(tmp_path):
    mod = load_example("29_o7_type69_ground_coupling_diagnostic.py")
    fit_dir = tmp_path / "fit_case"
    fit_dir.mkdir()
    weights = fit_dir / "o7_source_fit_weights.csv"
    with weights.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["level_index", "weight"])
        writer.writeheader()
        writer.writerow({"level_index": "4", "weight": "1.0"})
        writer.writerow({"level_index": "7", "weight": "0.0"})

    # Empty summary path used to become Path("") == '.', causing
    # IsADirectoryError.  The diagnostic should ignore it and use the
    # standard case-output weights CSV in fit_dir.
    top_level, top_weight, neff = mod.top_weight({"compatible_weights_csv": ""}, fit_dir)
    assert top_level == 4
    assert top_weight == 1.0
    assert neff == 1.0
