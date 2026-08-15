from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/qualification/run_c5_python_fixed_state_msolvelucy_forensic_0_6_82_27_16_3.py"
MAN = ROOT / "qualification/npass_0_6_82_27_16_3/diagnostic_msolvelucy_forensic_scope_0_6_82_27_16_3.json"
CHECK = ROOT / "tools/qualification/check_npass_python_msolvelucy_forensic_0_6_82_27_16_3.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("msolvelucy_068227163", RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_068227163_package_science_version_split():
    sys.path.insert(0, str(ROOT / "src"))
    import xstar_tools
    from xstar_tools.execution import package_version

    assert package_version() in ("0.6.82.27.16.3", "0.6.82.27.16.4")
    assert xstar_tools.__package_version__ in ("0.6.82.27.16.3", "0.6.82.27.16.4")
    assert xstar_tools.__version__ == "0.6.48.12.3.45.3.3.8"


def test_068227163_scope_gate_protects_all_production_numerical_sources():
    data = json.loads(MAN.read_text())
    assert data["baseline"] == "0.6.82.27.16.2"
    assert data["protected_cpp_baseline"] == "0.6.82.27.13"
    assert data["production_numerical_changed"] == []
    assert data["production_numerical_files_checked"] == 135
    p = subprocess.run([sys.executable, str(CHECK)], cwd=ROOT, text=True, capture_output=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "NPASS_PYTHON_MSOLVELUCY_FORENSIC_068227163_RESULT=ACCEPT" in p.stdout


def test_068227163_reuses_only_source_faithful_carried_replay():
    text = RUNNER.read_text()
    assert "_run_carried_replay(" in text
    assert "_run_fresh_replay(" not in text
    assert "DSEC-carried first-zone replay" in text


def test_068227163_native_same_input_contract_and_trace_outputs_are_explicit():
    text = RUNNER.read_text()
    assert "run_element_engine_cpp" in text
    assert "copy.deepcopy(element.equilibrium.assembly)" in text
    assert "XSTAR_QUALIFICATION_ITERATION_RESOLVED_TRACE" in text
    assert "XSTAR_QUALIFICATION_ITERATION_TRACE_DIR" in text
    assert "XSTAR_NATIVE_SOURCE_SEQUENCE" in text
    assert "msolvelucy_python_outer_trace.csv" in text
    assert "msolvelucy_python_fixed_trace.csv" in text
    assert "msolvelucy_python_superlevel_trace.csv" in text
    assert "msolvelucy_python_condensed_matrix.csv" in text


def test_068227163_comparison_helper_identical_and_divergent_rows():
    mod = load_runner()
    identical, summary = mod._compare_rows(
        [{"element_z": 1, "outer_iteration": 1, "compact_row": 2, "x": 3.0}],
        [{"element_z": "1", "outer_iteration": "1", "compact_row": "2", "x": "3.0"}],
        key_fields=("element_z", "outer_iteration", "compact_row"),
        value_fields=("x",),
    )
    assert len(identical) == 1
    assert summary["key_inventory_equal"] is True
    assert summary["max_relative"] == 0.0
    assert summary["first_divergence"] is None

    _, divergent = mod._compare_rows(
        [{"element_z": 1, "outer_iteration": 1, "compact_row": 2, "x": 3.0}],
        [{"element_z": 1, "outer_iteration": 1, "compact_row": 2, "x": 3.3}],
        key_fields=("element_z", "outer_iteration", "compact_row"),
        value_fields=("x",),
    )
    assert divergent["max_relative"] > 0.09
    assert divergent["first_divergence"] is not None


def test_068227163_localization_is_solver_vs_upstream_not_a_science_patch():
    text = RUNNER.read_text()
    assert "UPSTREAM_OF_MSOLVELUCY" in text
    assert "INSIDE_OR_AT_MSOLVELUCY" in text
    assert '"production_numerical_source_changes": 0' in text
    assert '"science_status": "OPEN"' in text
    assert '"diagnostic_result": "ACCEPT"' in text
