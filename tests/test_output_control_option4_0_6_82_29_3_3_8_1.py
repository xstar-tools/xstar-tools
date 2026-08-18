from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
PYEM = ROOT / "src/xstar_tools/xstar/emergent_emissivity.py"
RUNNER = ROOT / "tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3_8_1.py"


def test_version_bumped_after_rejected_338_host_candidate():
    assert 'version = "0.6.82.29.3.3.8.1"' in (ROOT / 'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3.8.1' in (ROOT / 'src/xstar_tools/xstar/cpp/Makefile').read_text()


def test_3381_keeps_338_cpp_science_contract():
    text = CPP.read_text()
    assert "pprint4_energy_ordered_abundances_v068229338" in text
    assert "endpoint1_energy_v068229338 < endpoint2_energy_v068229338" in text
    assert "source_pprint4_nlbin_v068229336" in text
    assert "flinel_delta_v068229338" in text


def test_3381_keeps_python_energy_order_contract():
    text = PYEM.read_text()
    assert "def _source_energy_ordered_line_endpoints(" in text
    assert "_source_energy_ordered_line_endpoints(levels, idest1, idest2)" in text
    assert "source_line_endpoints_valid_v068229337" in text


def test_host_runner_places_provenance_outside_product_directory():
    text = RUNNER.read_text()
    assert 'EXPECTED_VERSION="0.6.82.29.3.3.8.1"' in text
    assert 'OUTPUT_CONTROL_OPTION4_0682293381_CPP_RESULT' in text
    assert "provenance=(root/'logs'/'pprint4_flinel_provenance_0682293381.csv').resolve()" in text
    assert "env['XSTAR_V068229338_PPRINT4_FLINEL_PROVENANCE_PATH']=str(provenance)" in text
    assert "provenance=root/'logs'/'pprint4_flinel_provenance_0682293381.csv'" in text
    assert "provenance=(out/'pprint4_flinel_provenance_068229338.csv').resolve()" not in text


def test_runner_keeps_record_level_diagnostics_after_product_completion():
    text = RUNNER.read_text()
    assert "provenance rows:" in text
    assert "provenance cpp-only channel" in text
    assert "flinel cpp-only channels:" in text


def test_science_revision_and_abis_remain_frozen():
    api=(ROOT/'src/xstar_tools/xstar/cpp/xstar_api.h').read_text()
    prod=(ROOT/'src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h').read_text()
    fixed=(ROOT/'src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h').read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert '#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110' in prod
    assert '#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u' in fixed
