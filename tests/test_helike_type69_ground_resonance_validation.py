import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "examples" / "31_helike_type69_ground_resonance_validation.py"


def load_module():
    spec = importlib.util.spec_from_file_location("helike_type69_validation", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_parse_ion_spec_variants():
    mod = load_module()
    assert mod.parse_ion_spec("O VII") == ("O", 7)
    assert mod.parse_ion_spec("Ne IX") == ("Ne", 9)
    assert mod.parse_ion_spec("Mg:11") == ("Mg", 11)
    assert mod.parse_ion_spec("Fe XXV") == ("Fe", 25)


def test_resonance_label_detection():
    mod = load_module()
    assert mod.text_is_resonance_1p1("1s1.2p1.1P_1")
    assert mod.text_is_resonance_1p1("1s.2p 1P_1")
    assert not mod.text_is_resonance_1p1("1s1.2p1.3P_1")


def test_o7_validation_status_with_packaged_references():
    mod = load_module()
    status, note, nrefs = mod.validation_status_for_ion("O", 7, 1, Path("xstar_test_run"))
    assert status == "validated_o7_density_grid"
    assert nrefs >= 5
    assert "validated" in note.lower()


def test_non_o7_status_pending_without_references(tmp_path):
    mod = load_module()
    status, note, nrefs = mod.validation_status_for_ion("Ne", 9, 1, tmp_path)
    assert status == "pending_xstar_density_grid"
    assert nrefs == 0
    assert "xstar" in note.lower()
