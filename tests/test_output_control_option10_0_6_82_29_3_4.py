from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP_ZONE = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
CPP_ATDB = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp"
PY_LOWER = ROOT / "src/xstar_tools/xstar/native_fixed_program.py"
PY_PHYSICAL = ROOT / "src/xstar_tools/xstar/physical_runner.py"
RUNNER = ROOT / "tools/qualification/run_output_control_option10_host_smoke_0_6_82_29_3_4.py"


def test_version_and_changelog_identify_option10_only_candidate():
    assert 'version = "0.6.82.29.3.4"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.4' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert changelog.startswith("## 0.6.82.29.3.4 - Option 10")
    assert "mixed pirt/rrrt ownership" in changelog
    assert "Option 4 remains host-closed" in changelog


def test_cpp_option10_reconstructs_calc_hmc_element_mixed_owner():
    text = CPP_ZONE.read_text()
    anchor = text.index("0.6.82.29.3.4: pprint(10) consumes the mixed calc_hmc_element")
    block = text[anchor:text.index("v82 patch 5.20.9", anchor)]
    assert "detailed_pirt_v06822934" in block
    assert "detailed_rrrt_v06822934" in block
    assert "active.min_stage" in block and "active.max_stage" in block
    assert "c_v06822934.rate_type == 7" in block
    assert "c_v06822934.rate_type == 1" in block
    assert "c_v06822934.rate_type == 40" in block
    assert "c_v06822934.rate_type == 42" in block
    assert "c_v06822934.rate_type == 15" in block
    assert "c_v06822934.rate_type == 8" in block
    assert "mixed_pirt_v06822934[slot_v06822934] =" in block
    assert "mixed_rrrt_v06822934[slot_v06822934] =" in block


def test_cpp_option10_uses_ucalc_returned_endpoint_helper_not_matrix_rows_directly():
    text = CPP_ZONE.read_text()
    assert "struct CalcHmcIonEndpointsV06822934" in text
    assert "calc_hmc_ion_endpoints_v06822934" in text
    for token in ("case 53:", "case 52:", "case 59:", "case 72:", "case 74:", "case 99:"):
        assert token in text
    anchor = text.index("0.6.82.29.3.4: pprint(10) consumes the mixed calc_hmc_element")
    block = text[anchor:text.index("v82 patch 5.20.9", anchor)]
    assert "calc_hmc_ion_endpoints_v06822934(" in block
    assert "endpoints_v06822934.idest1" in block
    assert "endpoints_v06822934.idest2" in block


def test_type72_payload_preserves_evaluator_prefix_and_literal_ucalc_endpoints_in_both_lowerers():
    cpp = CPP_ATDB.read_text()
    assert "const int source_idest1=ii[ii.size()-4];" in cpp
    assert "const int source_idest2=ii[ii.size()-3];" in cpp
    assert "source_idest1,source_idest2" in cpp
    py = PY_LOWER.read_text()
    assert "payload_ints = [ground_row, parent_row, int(raw_ints[-4]), int(raw_ints[-3])]" in py


def test_python_option10_publishes_mixed_solver_arrays_not_preliminary_arrays():
    text = PY_PHYSICAL.read_text()
    anchor = text.index('"pirt": _ion_rate_array')
    block = text[anchor:anchor + 260]
    assert "result.pirt" in block
    assert "result.rrrt" in block
    assert "result.preliminary_pirt" not in block
    assert "result.preliminary_rrrt" not in block


def test_option10_host_runner_is_strict_15_row_payload_gate_and_externalizes_provenance():
    text = RUNNER.read_text()
    assert 'MARKER = "OUTPUT_CONTROL_OPTION10_06822934_CPP_RESULT"' in text
    assert "EXPECTED_ROWS = 15" in text
    assert "RTOL = 1.0e-3" in text
    assert 'CASE = "lprint_2"' in text
    assert "option10_rate_ownership_06822934.csv" in text
    assert "XSTAR_V06822934_OPTION10_RATE_OWNERSHIP_PATH" in text
    assert "root / \"logs\"" in text
    assert "identities_match_fortran" in text
    assert "payload_max_relative" in text


def test_science_revision_and_abis_remain_frozen():
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    prod = (ROOT / "src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h").read_text()
    fixed = (ROOT / "src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h").read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert '#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110' in prod
    assert '#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u' in fixed
