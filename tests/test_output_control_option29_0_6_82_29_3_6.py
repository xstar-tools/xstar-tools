from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp"
ATDB_H = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.hpp"
ATDB = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp"
STEP = ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp"
PY_PPRINT = ROOT / "src/xstar_tools/xstar/pprint_legacy.py"
RUNNER = ROOT / "tools/qualification/run_output_control_option29_host_smoke_0_6_82_29_3_6.py"


def test_version_and_changelog_identify_option29_candidate():
    assert 'version = "0.6.82.29.3.6"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.6' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert changelog.startswith("## 0.6.82.29.3.6 - Option 29")
    assert "Option 18 as host-closed" in changelog


def test_cpp_retains_private_literal_ucalc_rate_identity_sidecar():
    state = STATE.read_text()
    header = ATDB_H.read_text()
    lower = ATDB.read_text()
    assert "struct RateIdentityState" in state
    assert "source_idest1" in state and "source_idest2" in state
    assert "std::vector<RateIdentityState> source_rate_identities" in state
    assert "std::vector<xstar_run_state::RateIdentityState> source_rate_identities" in header
    assert "source_ucalc_endpoints_v06822936" in lower
    for token in (
        "case 51:", "case 53:", "case 56:", "case 57:", "case 59:",
        "case 60:", "case 62:", "case 63:", "case 69:", "case 72:",
        "case 74:", "case 77:", "case 95:", "case 99:",
        "rate_id.source_idest1=source_pair.first",
        "rate_id.source_idest2=source_pair.second",
    ):
        assert token in lower


def test_cpp_option29_uses_source_endpoints_active_ipmat2_and_9939():
    text = STEP.read_text()
    anchor = text.index('out << "\\n print option:29')
    block = text[anchor:text.index('out << "\\n print option:30', anchor)]
    assert "state.source_rate_identities" in block
    assert "source.source_idest1" in block and "source.source_idest2" in block
    assert "offset += std::max(it->second-1,0)" in block
    assert "std::min(nlev,std::max(idest1,1))" in block
    assert "std::min(nlev,std::max(idest2,1))" in block
    assert "Literal FORTRAN 9939" in block
    assert 'std::setw(25) << lower_label.substr(0,25) << " "' in block
    assert 'std::setw(25) << upper_label.substr(0,25) << " "' in block


def test_python_option29_uses_literal_source_publication_semantics():
    text = PY_PPRINT.read_text()
    anchor = text.index("def _option29_rates")
    block = text[anchor:text.index("def _roman_stage_from_ion_label", anchor)]
    assert 'ans1 = float(row.get("ans1", 0.0)' in block
    assert "ans1_after_calc_hmc_ion_filter" not in block
    assert "label_id1 = min(nlev, max(id1, 1))" in block
    assert "label_id2 = min(nlev, max(id2, 1))" in block
    assert 'ipmat2 = int(getattr(block, "compact_start", 1)) - 1' in block
    assert "shifted1 = id1 + ipmat2" in block
    assert "shifted2 = id2 + ipmat2" in block
    assert "Literal FORTRAN 9939" in block


def test_option29_host_runner_is_full_1954_row_identity_and_payload_gate():
    text = RUNNER.read_text()
    assert 'MARKER = "OUTPUT_CONTROL_OPTION29_06822936_CPP_RESULT"' in text
    assert "EXPECTED_ROWS = 1954" in text
    assert "RTOL = 1.0e-3" in text
    assert 'CASE = "lprint_5"' in text
    assert "identities_match_fortran" in text
    assert "payload_max_relative" in text
    assert "headers_match_fortran" in text
    assert "_first_key_mismatches" in text


def test_science_revision_and_abis_remain_frozen():
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    prod = (ROOT / "src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h").read_text()
    fixed = (ROOT / "src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h").read_text()
    assert "#define XSTAR_API_ABI_VERSION 60487u" in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert "#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110" in prod
    assert "#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u" in fixed


def test_option29_sdist_manifest_includes_self_qualification_artifacts():
    text = (ROOT / "MANIFEST.in").read_text()
    for token in (
        "tools/qualification/check_output_control_option29_0_6_82_29_3_6.py",
        "tools/qualification/run_output_control_option29_host_smoke_0_6_82_29_3_6.py",
        "tests/test_output_control_option29_0_6_82_29_3_6.py",
        "output_control_option29_0_6_82_29_3_6.md",
        "qualification_report_0_6_82_29_3_6.md",
        "xstar_tools-0.6.82.29.3.6_host_validation.md",
    ):
        assert token in text
