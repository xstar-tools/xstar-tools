import csv
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "22_o7_solver_source_fit_density_xstar_grid.py"


def load_module():
    spec = importlib.util.spec_from_file_location("density_xstar_grid", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_repair_stale_c5_mapping(tmp_path, monkeypatch):
    mod = load_module()
    monkeypatch.chdir(tmp_path)
    for dirname in ["c5_ne1", "c5_ne1e12"]:
        p = tmp_path / "xstar_test_run" / dirname / "xstar_c5_triplet_lines.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("ion,lower_level,upper_level,wavelength,emit_outward\n", encoding="utf-8")
    mapping = tmp_path / "xstar_test_run" / "xstar_c5_density_grid_references.csv"
    mapping.parent.mkdir(parents=True, exist_ok=True)
    mapping.write_text(
        "electron_density_cm^-3,xstar_lines_csv,xstar_value_column,xstar_target_label\n"
        "1,xstar_test_run/xstar_o7_triplet_lines.csv,emit_outward,stale\n"
        "1e12,xstar_test_run/xstar_o7_triplet_lines.csv,emit_outward,stale\n",
        encoding="utf-8",
    )
    mod._repair_stale_helike_grid_csv(mapping, ["--element", "C", "--ion-stage", "5"])
    rows = list(csv.DictReader(mapping.open(newline="", encoding="utf-8")))
    assert rows[0]["xstar_lines_csv"] == "xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv"
    assert rows[1]["xstar_lines_csv"] == "xstar_test_run/c5_ne1e12/xstar_c5_triplet_lines.csv"
    assert mapping.with_suffix(mapping.suffix + ".bak").exists()


def test_write_c5_template_uses_c5_paths(tmp_path, monkeypatch):
    mod = load_module()
    monkeypatch.chdir(tmp_path)
    mapping = tmp_path / "xstar_test_run" / "xstar_c5_density_grid_references.csv"
    mod.write_xstar_grid_template(mapping, element="C", ion_stage=5)
    rows = list(csv.DictReader(mapping.open(newline="", encoding="utf-8")))
    assert rows[0]["xstar_lines_csv"] == "xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv"
    assert rows[1]["xstar_lines_csv"] == "xstar_test_run/c5_ne1e4/xstar_c5_triplet_lines.csv"
    assert rows[-1]["xstar_lines_csv"] == "xstar_test_run/c5_ne1e12/xstar_c5_triplet_lines.csv"
    assert all("O VII" not in row["xstar_target_label"] for row in rows)
    assert rows[-1]["xstar_target_label"] == "C 5 XSTAR ne=1e+12 cm^-3"


def test_validate_c5_mapping_reports_missing_converted_files(tmp_path, monkeypatch):
    mod = load_module()
    monkeypatch.chdir(tmp_path)
    mapping = tmp_path / "xstar_test_run" / "xstar_c5_density_grid_references.csv"
    mapping.parent.mkdir(parents=True, exist_ok=True)
    mapping.write_text(
        "electron_density_cm^-3,xstar_lines_csv,xstar_value_column,xstar_target_label\n"
        "1,xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv,emit_outward,C 5\n",
        encoding="utf-8",
    )
    import pytest
    with pytest.raises(SystemExit) as exc:
        mod._validate_grid_csv_paths(mapping, ["--element", "C", "--ion-stage", "5"])
    msg = str(exc.value)
    assert "missing converted XSTAR triplet CSV" in msg
    assert "xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv" in msg
    assert "copy those c5_ne* folders here" in msg


def test_validate_c5_mapping_reports_stale_o7_path(tmp_path, monkeypatch):
    mod = load_module()
    monkeypatch.chdir(tmp_path)
    mapping = tmp_path / "xstar_test_run" / "xstar_c5_density_grid_references.csv"
    mapping.parent.mkdir(parents=True, exist_ok=True)
    mapping.write_text(
        "electron_density_cm^-3,xstar_lines_csv,xstar_value_column,xstar_target_label\n"
        "1,xstar_test_run/xstar_o7_triplet_lines.csv,emit_outward,stale\n",
        encoding="utf-8",
    )
    import pytest
    with pytest.raises(SystemExit) as exc:
        mod._validate_grid_csv_paths(mapping, ["--element", "C", "--ion-stage", "5"])
    msg = str(exc.value)
    assert "still references O VII" in msg
    assert "expected paths look like xstar_test_run/c5_ne*/xstar_c5_triplet_lines.csv" in msg
