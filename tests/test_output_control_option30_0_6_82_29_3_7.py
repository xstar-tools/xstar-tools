from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp"
PY_PPRINT = ROOT / "src/xstar_tools/xstar/pprint_legacy.py"
RUNNER = ROOT / "tools/qualification/run_output_control_option30_host_smoke_0_6_82_29_3_7.py"


def test_version_and_changelog_identify_option30_candidate():
    assert 'version = "0.6.82.29.3.7"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.7' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert changelog.startswith("## 0.6.82.29.3.7 - Option 30")
    assert "Option 29 as host-closed" in changelog


def test_cpp_option30_uses_literal_ucalc_endpoints_and_next_ion_k_shell():
    text = STEP.read_text()
    anchor = text.index('out << "\\n print option:30')
    block = text[anchor:text.index("out.unsetf", anchor)]
    assert "source_rate_by_record.find(row->record)" in block
    assert "source.source_idest1" in block
    assert "source.source_idest2" in block
    assert "const int nlev = std::max(static_cast<int>(source.nlev), 1)" in block
    assert "const int next_local = std::max(1, idest2 - nlev + 1)" in block
    assert "level_role(z, stage + 1, next_local)" in block
    assert "current_k_pi += row->ans[0] * lower_population" in block


def test_cpp_option30_fluorescence_auger_and_source_population_are_literal():
    text = STEP.read_text()
    anchor = text.index('out << "\\n print option:30')
    block = text[anchor:text.index("out.unsetf", anchor)]
    assert "retained_population(lower)" in block
    assert "row->rate_type == 4 || row->rate_type == 41" in block
    assert "level_role(z, stage, idest2)" in block
    assert "fluorescence += row->ans[1] * lower_population" in block
    assert "auger += row->ans[0] * lower_population" in block
    assert "const double pirttoto = previous_k_pi" in block
    assert "previous_k_pi = current_k_pi" in block


def test_cpp_option30_restores_literal_header_and_9822_spacing():
    text = STEP.read_text()
    anchor = text.index('out << "\\n print option:30')
    block = text[anchor:text.index("out.unsetf", anchor)]
    assert "k fluorescence rateauger rate fluorescence yield" in block
    assert "Literal FORTRAN 9822" in block
    assert 'std::setw(8) << label.substr(0,8) << " " << std::right' in block


def test_python_option30_mirrors_literal_source_ownership_now():
    text = PY_PPRINT.read_text()
    anchor = text.index("def _option30_auger_fluorescence")
    block = text[anchor:text.index("# XSTAR-FUNCTION-COMMENT-BEGIN", anchor)]
    assert 'ans1 = float(row.get("ans1", 0.0)' in block
    assert 'ans2 = float(row.get("ans2", 0.0)' in block
    assert "ans1_after_calc_hmc_ion_filter" not in block
    assert "next_local = max(1, id2 - nlev + 1)" in block
    assert "next_ion_index = int(ion.ion_index) + 1" in block
    assert 'next_label.startswith("1s1")' in block
    assert 'lower_label.startswith("1s1") or upper_label.startswith("1s1")' in block
    assert "previous_k_pi = current_k_pi" in block
    assert "k fluorescence rateauger rate fluorescence yield" in block


def test_option30_host_runner_is_strict_four_row_payload_gate():
    text = RUNNER.read_text()
    assert 'MARKER = "OUTPUT_CONTROL_OPTION30_06822937_CPP_RESULT"' in text
    assert "EXPECTED_ROWS = 4" in text
    assert "RTOL = 1.0e-3" in text
    assert 'CASE = "lprint_5"' in text
    assert "identities_match_fortran" in text
    assert "payload_max_relative" in text
    assert "headers_match_fortran" in text


def test_science_revision_and_abis_remain_frozen():
    api = (ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h").read_text()
    prod = (ROOT / "src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h").read_text()
    fixed = (ROOT / "src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h").read_text()
    assert "#define XSTAR_API_ABI_VERSION 60487u" in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert "#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110" in prod
    assert "#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u" in fixed
