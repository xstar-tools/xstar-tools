from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/qualification/run_c5_python_fixed_state_population_heating_0_6_82_27_16_2.py"
MAN = ROOT / "qualification/npass_0_6_82_27_16_2/diagnostic_dsec_carried_scope_0_6_82_27_16_2.json"
CHECK = ROOT / "tools/qualification/check_npass_python_dsec_carried_diagnostic_0_6_82_27_16_2.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("fixed_state_068227162", RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_068227162_package_science_version_split():
    sys.path.insert(0, str(ROOT / "src"))
    import xstar_tools
    from xstar_tools.execution import package_version
    assert package_version() in ("0.6.82.27.16.2", "0.6.82.27.16.3", "0.6.82.27.16.4", "0.6.82.27.16.4.1", "0.6.82.27.16.5", "0.6.82.28", "0.6.82.28.1", "0.6.82.29", "0.6.82.29.1")
    assert xstar_tools.__package_version__ in ("0.6.82.27.16.2", "0.6.82.27.16.3", "0.6.82.27.16.4", "0.6.82.27.16.4.1", "0.6.82.27.16.5", "0.6.82.28", "0.6.82.28.1", "0.6.82.29", "0.6.82.29.1")
    assert xstar_tools.__version__ == "0.6.48.12.3.45.3.3.8"


def test_068227162_scope_gate_and_protected_hashes():
    data = json.loads(MAN.read_text())
    assert data["baseline"] == "0.6.82.27.16.1"
    assert data["protected_cpp_baseline"] == "0.6.82.27.13"
    assert data["production_numerical_changed"] == []
    p = subprocess.run([sys.executable, str(CHECK)], cwd=ROOT, text=True, capture_output=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "NPASS_PYTHON_DSEC_CARRIED_068227162_RESULT=ACCEPT" in p.stdout


def test_068227162_reference_state_treats_ion_parameter_as_logxi():
    text = RUNNER.read_text()
    assert 'logxi = float(a["ion_parameter"])' in text
    assert 'xi = 10.0 ** logxi' in text
    assert 'state.control["zeta"] = float(fstate["logxi"])' in text
    assert 'state.control["xi"] = float(fstate["xi"])' in text


def test_068227162_carried_replay_preserves_dsec_runtime_then_resets_only_scalars():
    text = RUNNER.read_text()
    assert 'runtime = runtime_state.control.get("physical_dsec_runtime")' in text
    assert 'carrier["dsec_runtime_before_final"] = _runtime_metadata(runtime)' in text
    assert '_configure_target_state(runtime_state, fstate)' in text
    assert 'return original_final(runtime_state)' in text
    assert 'fixed_state=False' in text


def test_068227162_level_semantics_and_matrix_outputs():
    text = RUNNER.read_text()
    assert 'fresh.global_rnisg_by_index' in text
    assert 'fresh.global_bilevg_by_index' in text
    assert '"fresh_lte_population"' in text
    assert '"fresh_departure_coefficient"' in text
    assert 'fixed_state_matrix_term_deltas.csv' in text
    assert 'fixed_state_matrix_rate_summary.csv' in text


def test_068227162_compatibility_entrypoints_use_same_candidate():
    for name in (
        "run_c5_python_fixed_state_population_heating_0_6_82_27_16.py",
        "run_c5_python_fixed_state_population_heating_0_6_82_27_16_1.py",
        "run_c5_python_fixed_state_population_heating_0_6_82_27_16_2.py",
    ):
        text = (ROOT / "tools/qualification" / name).read_text()
        assert 'EXPECTED_VERSION = "0.6.82.27.16.2"' in text


def test_068227162_progress_is_visible_during_long_work():
    text = RUNNER.read_text()
    assert 'flush=True' in text
    assert 'state.control["progress_debug"] = True' in text
    assert '"DSEC evaluation"' in text
    assert 'def _heartbeat' in text
