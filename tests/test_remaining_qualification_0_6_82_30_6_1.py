import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "qualification/remaining_qualification_0_6_82_30_6_1/remaining_qualification_0_6_82_30_6_1.json"
RUNNER = ROOT / "tools/qualification/run_remaining_qualification_host_smoke_0_6_82_30_6_1.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("remaining06823061_test", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_exactly_eleven_unexecuted_cases():
    m = json.loads(MATRIX.read_text())
    assert m["version"] == "0.6.82.30.6.1"
    assert m["case_count"] == 11
    assert m["fortran_cpp_execution_count"] == 22
    assert m["sections"]["spectrum"] == ["pow", "bbody", "bremss", "file_e0", "file_p1", "file_log2"]
    assert m["sections"]["ncn2"] == ["ncn2_999", "ncn2_9999", "ncn2_19999"]
    assert m["sections"]["density"] == ["c5_low_density_ne1", "c5_high_density_ne1e12"]


def test_deferred_and_accepted_cases_are_not_selected():
    m = json.loads(MATRIX.read_text())
    selected = {x for values in m["sections"].values() for x in values}
    forbidden = {
        "npass1", "npass3", "npass5", "fe_reference_ne1e8", "multi_element_xi1_ne1e12",
        "output_lprint6", "output_lstep1", "element_c", "element_o", "element_ca", "element_fe",
        "c5_reference_ne1e8", "c5_lowxi_cf04_ne1e12", "o7_reference_ne1e10", "ca19_reference_ne1e8",
    }
    assert not (selected & forbidden)
    text = RUNNER.read_text()
    for old_axis in ("run_c5_emult_sweep", "run_c5_niter_modes", "run_c5_lcpres_pressure",
                     "run_c5_radexp_density", "run_c5_npass_multipass"):
        assert old_axis not in text


def test_runner_case_inventory_and_continue_policy():
    mod = load_runner()
    assert len(mod.ALL_CASES) == 11
    assert len(mod.SPECTRUM_CASES) == 6
    assert len(mod.NCN2_CASES) == 3
    assert len(mod.DENSITY_CASES) == 2
    assert set(mod.ALL_CASES) == {
        "pow", "bbody", "bremss", "file_e0", "file_p1", "file_log2",
        "ncn2_999", "ncn2_9999", "ncn2_19999",
        "c5_low_density_ne1", "c5_high_density_ne1e12",
    }
    text = RUNNER.read_text()
    assert "REMAINING_QUALIFICATION_06823061_ACCEPTED=" in text
    assert "continue after individual rejection" in text
    assert "rows.extend(run_ncn2" in text
    assert "rows.extend(run_density" in text
