from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
PYEM = ROOT / "src/xstar_tools/xstar/emergent_emissivity.py"
PYBROAD = ROOT / "src/xstar_tools/xstar/emissivity.py"
RUNNER = ROOT / "tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3_8.py"


def test_version_bumped_after_rejected_337_host_candidate():
    assert 'version = "0.6.82.29.3.3.8"' in (ROOT / 'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3.8' in (ROOT / 'src/xstar_tools/xstar/cpp/Makefile').read_text()


def test_cpp_private_option4_rank_uses_energy_ordered_endpoint_populations():
    text = CPP.read_text()
    anchor = text.index("0.6.82.29.3.3.8: calc_emisab_ion and calc_emis_ion both define")
    block = text[anchor:]
    assert "pprint4_energy_ordered_abundances_v068229338" in block
    assert "endpoint1_energy_v068229338 < endpoint2_energy_v068229338" in block
    assert "source_post_mapback_population_for_full_row(" in block
    assert "source_abund1_cm3_v068229338" in block
    assert "source_abund2_cm3_v068229338" in block
    assert "source_spectral_v068229338.opakab * source_abund1_cm3_v068229338" in block
    assert "-source_abund2_cm3_v068229338 * source_spectral_v068229338.ans3" in block


def test_cpp_private_option4_flinel_uses_same_energy_ordered_abundances():
    text = CPP.read_text()
    anchor = text.index("const char* pprint4_provenance_path_v068229338")
    block = text[anchor:anchor + 9000]
    assert "pprint4_energy_ordered_abundances_v068229338(source_record_v068229338)" in block
    assert "c.ans2 * source_abund2_cm3_v068229338" in block
    assert "c.ans1 * source_abund1_cm3_v068229338" in block
    assert "flinel_delta_v068229338" in block


def test_cpp_energy_order_uses_full_source_rows_and_committed_population_view():
    text = CPP.read_text()
    assert "pprint4_full_element_v068229338" in text
    assert "ctx.program.elements" in text
    assert "ctx.last_element_diagnostics" in text
    assert "diagnostic_v068229338->active_final_populations" in text
    assert "source_record_v068229338.lower_row - 1" in text
    assert "source_record_v068229338.upper_row - 1" in text


def test_cpp_retains_prior_endpoint_elmn_nbinc_width_and_pass_lifetime_repairs():
    local = CPP.read_text()
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "source_idest1_v068229337" in local
    assert "source_idest2_v068229337" in local
    assert "source_pprint4_nlbin_v068229336" in local
    assert "pprint4_elmn_wavelength_v068229336" in local
    assert "lower_one_based_v068229336 = std::max(1, nb1_v068229336 - 1)" in local
    assert "pprint4_flinel_accumulator_v068229334" in standalone


def test_cpp_provenance_is_diagnostic_only_and_host_runner_enables_it():
    local = CPP.read_text()
    runner = RUNNER.read_text()
    assert "XSTAR_V068229338_PPRINT4_FLINEL_PROVENANCE_PATH" in local
    assert "pprint4_flinel_provenance_068229338.csv" in runner
    assert "XSTAR_V068229338_PPRINT4_FLINEL_PROVENANCE_PATH" in runner


def test_python_broad_calc_emisab_keeps_source_strict_endpoint_gate():
    text = PYBROAD.read_text()
    assert "if 0 < idest1 < ion.nlev and 0 < idest2 < ion.nlev:" in text


def test_python_final_calc_emis_makes_energy_order_contract_explicit():
    text = PYEM.read_text()
    assert "def _source_energy_ordered_line_endpoints(" in text
    helper = text[text.index("def _source_energy_ordered_line_endpoints("):]
    helper = helper[:helper.index("# XSTAR-FUNCTION-COMMENT-BEGIN", 20)]
    assert "if e1 < e2:" in helper
    assert "return int(idest1), int(idest2), e1, e2" in helper
    assert "return int(idest2), int(idest1), e1, e2" in helper
    assert "_source_energy_ordered_line_endpoints(levels, idest1, idest2)" in text
    assert "source_line_endpoints_valid_v068229337" in text


def test_host_runner_tracks_338_and_keeps_flinel_inventory_diagnostics():
    runner = RUNNER.read_text()
    assert 'EXPECTED_VERSION="0.6.82.29.3.3.8"' in runner
    assert 'OUTPUT_CONTROL_OPTION4_068229338_CPP_RESULT' in runner
    assert 'flinel nonzero: fortran=' in runner
    assert 'flinel cpp-only channels:' in runner
    assert 'provenance rows:' in runner


def test_science_revision_and_abis_remain_frozen():
    api=(ROOT/'src/xstar_tools/xstar/cpp/xstar_api.h').read_text()
    prod=(ROOT/'src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h').read_text()
    fixed=(ROOT/'src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h').read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert '#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110' in prod
    assert '#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u' in fixed
