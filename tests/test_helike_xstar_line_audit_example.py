import importlib.util
from pathlib import Path


def _load_example():
    root = Path(__file__).resolve().parents[1]
    path = root / "examples" / "33_audit_helike_xstar_lines.py"
    spec = importlib.util.spec_from_file_location("audit_helike_xstar_lines", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_helike_component_classifier_variants():
    mod = _load_example()
    assert mod._component({"upper_level": "1s1.2s1.3S_1"}) == "forbidden"
    assert mod._component({"upper_level": "1s1.2p1.1P_1"}) == "resonance"
    assert mod._component({"upper_level": "1s1.2p1.3P_2"}) == "intercombination"


def test_helike_like_label_detection():
    mod = _load_example()
    assert mod._looks_helike_n2({"lower_level": "1s2.1S_0", "upper_level": "1s1.2p1.3P_1"})
    assert mod._looks_helike_n2({"lower_level": "1s2.1S_0", "upper_level": "1s1.2s1.3S_1"})
    assert not mod._looks_helike_n2({"lower_level": "2s", "upper_level": "2p"})


def test_ion_and_window_helpers():
    mod = _load_example()
    row = {"ion": "Ca XIX", "wavelength": "3.18"}
    assert mod._ion_matches(row, "Ca XIX")
    assert mod._ion_matches({"ion": "ca_xix"}, "Ca XIX")
    assert mod._in_window(row, 3.14, 3.23)
    assert not mod._in_window(row, 3.20, 3.23)
