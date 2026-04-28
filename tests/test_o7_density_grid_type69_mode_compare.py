import csv
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_example30():
    path = ROOT / "examples" / "30_o7_density_grid_type69_mode_compare.py"
    spec = importlib.util.spec_from_file_location("o7_density_grid_type69_mode_compare", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def write_rows(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_weights(path, weights):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["level_index", "fit_weight_norm"])
        writer.writeheader()
        for level, weight in weights.items():
            writer.writerow({"level_index": level, "fit_weight_norm": weight})


def test_example30_exists_and_documents_experimental_mode():
    path = ROOT / "examples" / "30_o7_density_grid_type69_mode_compare.py"
    text = path.read_text(encoding="utf-8")
    assert "suppress-resonance" in text
    assert "diagnostic/experimental" in text
    assert "o7_density_grid_type69_mode_compare.csv" in text


def test_example30_builds_merged_comparison_rows(tmp_path):
    mod = load_example30()
    include_dir = tmp_path / "mode_include"
    suppress_dir = tmp_path / "mode_suppress_resonance"
    common = {
        "electron_density_cm^-3": "1e12",
        "xstar_R_f_over_i": "0.0830641",
        "xstar_G_f_plus_i_over_r": "4.51966",
    }
    write_rows(include_dir / "o7_solver_source_fit_density_grid.csv", [
        {
            **common,
            "refitted_combined_R_f_over_i": "0.0377954",
            "refitted_combined_G_f_plus_i_over_r": "3.20209",
            "refitted_R_over_xstar": "0.455015",
            "refitted_G_over_xstar": "0.708482",
            "target_reachable": "False",
            "weight_delta_l1_vs_ne1": "1.87259",
        }
    ])
    write_rows(suppress_dir / "o7_solver_source_fit_density_grid.csv", [
        {
            **common,
            "refitted_combined_R_f_over_i": "0.0830685",
            "refitted_combined_G_f_plus_i_over_r": "4.5197",
            "refitted_R_over_xstar": "1.00005",
            "refitted_G_over_xstar": "1.00001",
            "target_reachable": "True",
            "weight_delta_l1_vs_ne1": "0.720805",
        }
    ])
    write_weights(include_dir / "fit_ne_1e12" / "o7_source_fit_weights.csv", {4: 1.0})
    write_weights(suppress_dir / "fit_ne_1e12" / "o7_source_fit_weights.csv", {4: 0.5, 7: 0.5})

    rows = mod.build_comparison_rows(include_dir, suppress_dir)
    assert len(rows) == 1
    row = rows[0]
    assert row["include_target_reachable"] is False
    assert row["suppress_resonance_target_reachable"] is True
    assert row["mismatch_improvement_factor"] > 1000.0
    assert row["include_top_source_level"] == 4
    assert row["suppress_resonance_top_source_level"] in {4, 7}
    assert abs(row["source_weight_l1_change_suppress_minus_include"] - 1.0) < 1e-12


def test_example30_dry_run_invokes_both_modes(tmp_path):
    script = ROOT / "examples" / "30_o7_density_grid_type69_mode_compare.py"
    grid = tmp_path / "grid.csv"
    grid.write_text(
        "electron_density_cm^-3,xstar_lines_csv,xstar_value_column,xstar_target_label\n"
        "1,xstar_test_run/o7_ne1/xstar_o7_triplet_lines.csv,emit_outward,O VII XSTAR ne=1\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "dummy_atdb.fits",
            "--xstar-grid-summary-csv",
            str(grid),
            "--out-dir",
            str(tmp_path / "compare"),
            "--dry-run",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "--collision-type69-ground-excitation-mode include" in result.stdout
    assert "--collision-type69-ground-excitation-mode suppress-resonance" in result.stdout
    assert "dry-run: not merging" in result.stdout
