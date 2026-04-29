import csv
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "32_prepare_helike_xstar_density_grids.py"


def load_module():
    spec = importlib.util.spec_from_file_location("prepare_helike_xstar_density_grids", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_parse_ions_and_default_candidate_tags():
    mod = load_module()
    assert mod.parse_ions("C V,Mg XI,Ca XIX") == [("C", 5), ("Mg", 11), ("Ca", 19)]
    assert mod.ion_tag("Mg", 11) == "mg11"
    assert mod.ion_label("Ca", 19) == "Ca XIX"
    assert mod.window_for("C", 5) == (40.0, 42.0)


def test_abundance_arguments_select_target_element_only():
    mod = load_module()
    text = mod.abundance_arguments("Mg")
    assert "habund=1" in text
    assert "heabund=1" in text
    assert "mgabund=1" in text
    assert "oabund=0" in text
    assert "cabund=0" in text


def test_write_density_scripts_creates_mapping_and_scripts(tmp_path):
    mod = load_module()
    rows = mod.write_density_scripts(tmp_path, [("C", 5), ("Mg", 11)], [1.0, 1.0e12], 1.5, 1.0e20, 100.0, 100.0)
    assert len(rows) == 4
    assert (tmp_path / "xstar_runs" / "helike_type69" / "c5_ne1" / "run_xstar.sh").exists()
    assert (tmp_path / "xstar_runs" / "helike_type69" / "mg11_ne1e12" / "convert_mg11_triplet.sh").exists()
    c_mapping = tmp_path / "xstar_test_run" / "xstar_c5_density_grid_references.csv"
    m_mapping = tmp_path / "xstar_test_run" / "xstar_mg11_density_grid_references.csv"
    assert c_mapping.exists()
    assert m_mapping.exists()
    with c_mapping.open(newline="", encoding="utf-8") as handle:
        c_rows = list(csv.DictReader(handle))
    assert c_rows[0]["xstar_lines_csv"] == "xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv"
    assert c_rows[1]["xstar_target_label"] == "C V XSTAR logxi=1.5 ne=1e+12 cm^-3"
    convert_text = (tmp_path / "xstar_runs" / "helike_type69" / "mg11_ne1e12" / "convert_mg11_triplet.sh").read_text()
    assert '--ion "Mg XI"' in convert_text
    assert "--wavelength-min 9.05" in convert_text
    assert "--wavelength-max 9.4" in convert_text


def test_write_density_scripts_rlogxi_grid_uses_xi_specific_paths(tmp_path):
    mod = load_module()
    rows = mod.write_density_scripts(tmp_path, [("Ca", 19)], [1.0, 1.0e12], [1.5, 3.0], 1.0e20, 100.0, 100.0)
    assert len(rows) == 4
    assert (tmp_path / "xstar_runs" / "helike_type69" / "ca19_xi1p5_ne1" / "run_xstar.sh").exists()
    assert (tmp_path / "xstar_runs" / "helike_type69" / "ca19_xi3_ne1e12" / "convert_ca19_triplet.sh").exists()
    assert (tmp_path / "xstar_test_run" / "xstar_ca19_xi1p5_density_grid_references.csv").exists()
    assert (tmp_path / "xstar_test_run" / "xstar_ca19_xi3_density_grid_references.csv").exists()
    with (tmp_path / "xstar_test_run" / "xstar_ca19_xi3_density_grid_references.csv").open(newline="", encoding="utf-8") as handle:
        rows_xi3 = list(csv.DictReader(handle))
    assert rows_xi3[0]["xstar_lines_csv"] == "xstar_test_run/ca19_xi3_ne1/xstar_ca19_triplet_lines.csv"
    assert "logxi=3" in rows_xi3[0]["xstar_target_label"]
