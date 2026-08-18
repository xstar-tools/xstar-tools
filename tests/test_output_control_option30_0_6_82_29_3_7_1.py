from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATDB = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp"
STEP = ROOT / "src/xstar_tools/xstar/cpp/xstar_step_log.cpp"
PY_PPRINT = ROOT / "src/xstar_tools/xstar/pprint_legacy.py"
RUNNER = ROOT / "tools/qualification/run_output_control_option30_host_smoke_0_6_82_29_3_7_1.py"


def test_version_and_changelog_identify_rejected_37_and_hotfix_371():
    assert 'version = "0.6.82.29.3.7.1"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.7.1' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert changelog.startswith("## 0.6.82.29.3.7.1 - Option 30 radiative endpoint ownership hotfix")
    assert "Treats `0.6.82.29.3.7` as host-rejected" in changelog


def test_cpp_type50_type91_and_type76_publish_ucalc_upper_first_endpoint():
    text = ATDB.read_text()
    anchor = text.index("source_ucalc_endpoints_v06822936")
    block = text[anchor:text.index("case 51:", anchor)]
    assert "0.6.82.29.3.7.1" in block
    assert "case 50:" in block
    assert "case 76:" in block
    assert "case 91:" in block
    assert "return energy_order(as_int(0),as_int(1),true);" in block
    assert "K-fluorescence multiply A by the ground/lower-level population" in block


def test_cpp_option30_still_consumes_private_source_endpoints_not_matrix_rows():
    text = STEP.read_text()
    anchor = text.index('out << "\\n print option:30')
    block = text[anchor:text.index("out.unsetf", anchor)]
    assert "source_rate_by_record.find(row->record)" in block
    assert "source.source_idest1" in block
    assert "source.source_idest2" in block
    assert "retained_population(lower)" in block
    assert "fluorescence += row->ans[1] * lower_population" in block
    assert "auger += row->ans[0] * lower_population" in block
    assert "const int next_local = std::max(1, idest2 - nlev + 1)" in block
    assert "level_role(z, stage + 1, next_local)" in block


def test_python_publication_mirrors_upper_first_radiative_endpoint_without_solver_change():
    text = PY_PPRINT.read_text()
    helper_anchor = text.index("def _source_ucalc_publication_endpoints")
    helper = text[helper_anchor:text.index("def _option29_rates", helper_anchor)]
    assert "diag_source_upper_id_after_energy_swap" in helper
    assert "diag_source_lower_id_after_energy_swap" in helper
    assert "data_type in {50, 91}" in helper
    assert "data_type in {50, 76, 91}" in helper
    assert "if e1 is not None and e2 is not None and e1 < e2" in helper
    assert "return id2, id1" in helper
    # The correction is publication-only: do not change Python UCalc solver ownership here.
    assert "def _eval_type50" not in helper
    assert "def _eval_type76" not in helper


def test_python_option30_uses_shared_source_endpoint_helper_and_raw_rates():
    text = PY_PPRINT.read_text()
    anchor = text.index("def _option30_auger_fluorescence")
    block = text[anchor:text.index("# XSTAR-FUNCTION-COMMENT-BEGIN", anchor)]
    assert "_source_ucalc_publication_endpoints(" in block
    assert 'ans1 = float(row.get("ans1", 0.0)' in block
    assert 'ans2 = float(row.get("ans2", 0.0)' in block
    assert "ans1_after_calc_hmc_ion_filter" not in block
    assert "next_local = max(1, id2 - nlev + 1)" in block
    assert 'next_label.startswith("1s1")' in block
    assert 'lower_label.startswith("1s1") or upper_label.startswith("1s1")' in block


def test_option30_hotfix_runner_remains_strict_four_row_payload_gate():
    text = RUNNER.read_text()
    assert 'EXPECTED_VERSION = "0.6.82.29.3.7.1"' in text
    assert 'MARKER = "OUTPUT_CONTROL_OPTION30_068229371_CPP_RESULT"' in text
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
