from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_package_science_version_split():
    sys.path.insert(0, str(ROOT / "src"))
    import xstar_tools
    from xstar_tools.execution import package_version
    assert package_version() in ("0.6.82.27.16.1", "0.6.82.27.16.2", "0.6.82.27.16.3", "0.6.82.27.16.4", "0.6.82.27.16.4.1", "0.6.82.27.16.5", "0.6.82.28", "0.6.82.28.1", "0.6.82.29", "0.6.82.29.1")
    assert xstar_tools.__package_version__ in ("0.6.82.27.16.1", "0.6.82.27.16.2", "0.6.82.27.16.3", "0.6.82.27.16.4", "0.6.82.27.16.4.1", "0.6.82.27.16.5", "0.6.82.28", "0.6.82.28.1", "0.6.82.29", "0.6.82.29.1")
    assert xstar_tools.__version__ == "0.6.48.12.3.45.3.3.8"


def test_fixed_state_runner_uses_package_version_not_science_revision():
    p = ROOT / "tools/qualification/run_c5_python_fixed_state_population_heating_0_6_82_27_16_1.py"
    text = p.read_text()
    assert any(f'EXPECTED_VERSION = "{v}"' in text for v in ("0.6.82.27.16.1", "0.6.82.27.16.2", "0.6.82.27.16.3", "0.6.82.27.16.4", "0.6.82.27.16.4.1", "0.6.82.27.16.5", "0.6.82.28", "0.6.82.28.1", "0.6.82.29", "0.6.82.29.1"))
    assert 'from xstar_tools.execution import package_version' in text
    assert 'active_package_version = str(package_version()).strip()' in text
    assert 'xstar_tools.__version__) != EXPECTED_VERSION' not in text


def test_old_runner_filename_is_compatible_with_hotfix():
    p = ROOT / "tools/qualification/run_c5_python_fixed_state_population_heating_0_6_82_27_16.py"
    text = p.read_text()
    assert any(f'EXPECTED_VERSION = "{v}"' in text for v in ("0.6.82.27.16.1", "0.6.82.27.16.2", "0.6.82.27.16.3", "0.6.82.27.16.4", "0.6.82.27.16.4.1", "0.6.82.27.16.5", "0.6.82.28", "0.6.82.28.1", "0.6.82.29", "0.6.82.29.1"))
    assert 'from xstar_tools.execution import package_version' in text


def test_no_production_numerical_source_changed():
    import json
    p = ROOT / "qualification/npass_0_6_82_27_16_1/diagnostic_wrapper_hotfix_scope_0_6_82_27_16_1.json"
    data = json.loads(p.read_text())
    assert data["production_numerical_changed"] == []
