import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "qualification/python_qualification_continuation_0_6_82_30_6_2/python_qualification_continuation_0_6_82_30_6_2.json"
TEST1 = ROOT / "tools/qualification/run_python_qualification_test1_host_smoke_0_6_82_30_6_2.py"
TEST2 = ROOT / "tools/qualification/run_python_qualification_test2_host_smoke_0_6_82_30_6_2.py"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_test1_exact_26_case_inventory_includes_npass1():
    m = json.loads(MATRIX.read_text())
    assert m["version"] == "0.6.82.30.6.2"
    assert m["test1"]["case_count"] == 26
    assert sum(len(v) for v in m["test1"]["sections"].values()) == 26
    assert m["test1"]["sections"]["npass"] == ["npass1", "npass3", "npass5"]
    mod = load(TEST1, "pyq1_test")
    assert len(mod.ALL_CASES) == 26
    assert mod.NPASS_CASES == ("npass1", "npass3", "npass5")
    assert "fe_reference_ne1e8" not in mod.ALL_CASES
    assert "multi_element_xi1_ne1e12" not in mod.ALL_CASES


def test_test2_exact_six_case_inventory_excludes_fe_and_multi_element():
    m = json.loads(MATRIX.read_text())
    expected = [
        "c5_reference_ne1e8", "c5_lowxi_cf04_ne1e12", "o7_reference_ne1e10",
        "ca19_reference_ne1e8", "c5_low_density_ne1", "c5_high_density_ne1e12",
    ]
    assert m["test2"]["case_count"] == 6
    assert m["test2"]["cases"] == expected
    mod = load(TEST2, "pyq2_test")
    assert list(mod.CASES) == expected
    assert "fe_reference_ne1e8" not in mod.CASES
    assert "multi_element_xi1_ne1e12" not in mod.CASES


def test_both_runners_are_python_only_and_continue_to_summary():
    for path in (TEST1, TEST2):
        text = path.read_text()
        assert "source_port_physical_runner_cli" in text
        assert 'choices=("prepare", "python")' in text
        assert "--fortran-bin" not in text
        assert "xstar-cpp" not in text
        assert "run_final_qualification" in text or "retained FORTRAN" in text
    t1 = TEST1.read_text()
    assert "PYTHON_QUALIFICATION_TEST1_06823062_ACCEPTED=" in t1
    assert "rows.extend(run_npass" in t1
    assert "rows.extend(run_ncn2" in t1
    t2 = TEST2.read_text()
    assert "PYTHON_QUALIFICATION_TEST2_06823062_ACCEPTED=" in t2
