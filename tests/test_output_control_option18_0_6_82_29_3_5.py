from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "src/xstar_tools/xstar/cpp/xstar_run_state.hpp"
LOWER = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp"
STEP = ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp"
RUNNER = ROOT / "tools/qualification/run_output_control_option18_host_smoke_0_6_82_29_3_5.py"


def test_version_and_changelog_identify_option18_candidate():
    assert 'version = "0.6.82.29.3.5"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.5' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert changelog.startswith("## 0.6.82.29.3.5 - Option 18")
    assert "Option 10 as host-closed" in changelog


def test_option18_retains_literal_type13_endpoint_metadata():
    state = STATE.read_text()
    lower = LOWER.read_text()
    for token in (
        "lower_excitation_ev", "upper_excitation_ev",
        "lower_statistical_weight", "upper_statistical_weight",
        "lower_effective_n", "upper_effective_n",
        "lower_principal_n", "upper_principal_n",
        "lower_spin_multiplicity", "upper_spin_multiplicity",
        "lower_orbital_l", "upper_orbital_l",
    ):
        assert token in state
    assert "effective_n=rv.size()>2?rv[2]:0.0" in lower
    assert "spin_multiplicity=iv.size()>1?static_cast<int>(iv[1]):0" in lower
    assert "id.lower_excitation_ev=la->energy" in lower
    assert "id.upper_excitation_ev=lc->energy" in lower


def test_option18_prints_full_fortran_9929_payload():
    text = STEP.read_text()
    anchor = text.index('out << "\\n print option:18')
    block = text[anchor:text.index('out << "\\n print option:29', anchor)]
    assert "pprint.f90 9929" in block
    assert "configuration                           index     eex" in block
    assert "id->lower_excitation_ev" in block and "id->upper_excitation_ev" in block
    assert "id->lower_statistical_weight" in block and "id->upper_statistical_weight" in block
    assert "id->lower_effective_n" in block and "id->upper_effective_n" in block
    assert "id->lower_principal_n" in block and "id->upper_principal_n" in block
    assert "id->lower_spin_multiplicity" in block and "id->upper_spin_multiplicity" in block
    assert "id->lower_orbital_l" in block and "id->upper_orbital_l" in block


def test_option10_summary_rows_use_canonical_fixed_label_width():
    text = STEP.read_text()
    assert 'out << "      compton  "' in text
    assert 'out << "      free-free"' in text
    assert 'out << "      total    "' in text


def test_option18_host_runner_is_full_1140_row_payload_gate():
    text = RUNNER.read_text()
    assert 'MARKER = "OUTPUT_CONTROL_OPTION18_06822935_CPP_RESULT"' in text
    assert "EXPECTED_ROWS = 1140" in text
    assert "RTOL = 1.0e-3" in text
    assert 'CASE = "lprint_4"' in text
    assert "headers_match_fortran" in text
    assert "quantum_row_mismatches" in text
    assert "identities_match_fortran" in text


def test_science_revision_and_abis_remain_frozen():
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    prod = (ROOT / "src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h").read_text()
    fixed = (ROOT / "src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h").read_text()
    assert "#define XSTAR_API_ABI_VERSION 60487u" in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert "#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110" in prod
    assert "#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u" in fixed


def test_option18_sdist_manifest_includes_self_qualification_artifacts():
    text = (ROOT / "MANIFEST.in").read_text()
    for token in (
        "tools/qualification/check_output_control_option18_0_6_82_29_3_5.py",
        "tools/qualification/run_output_control_option18_host_smoke_0_6_82_29_3_5.py",
        "tests/test_output_control_option18_0_6_82_29_3_5.py",
        "output_control_option18_0_6_82_29_3_5.md",
        "qualification_report_0_6_82_29_3_5.md",
        "xstar_tools-0.6.82.29.3.5_host_validation.md",
    ):
        assert token in text
