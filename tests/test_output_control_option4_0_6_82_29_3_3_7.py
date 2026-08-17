from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
PYEM = ROOT / "src/xstar_tools/xstar/emergent_emissivity.py"
PYBROAD = ROOT / "src/xstar_tools/xstar/emissivity.py"


def test_version_bumped_after_rejected_336_host_candidate():
    assert 'version = "0.6.82.29.3.3.7"' in (ROOT / 'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3.7' in (ROOT / 'src/xstar_tools/xstar/cpp/Makefile').read_text()


def test_cpp_broad_line_rank_applies_literal_source_local_endpoint_gate():
    text = CPP.read_text()
    anchor = text.index("0.6.82.29.3.3.7: literal calc_emisab_ion line eligibility")
    block = text[anchor:anchor + 3200]
    assert "source_nlev_v068229337" in block
    assert "source_idest1_v068229337 = source_idest_for_full_row(" in block
    assert "source_idest2_v068229337 = source_idest_for_full_row(" in block
    assert "source_idest1_v068229337 < source_nlev_v068229337" in block
    assert "source_idest2_v068229337 < source_nlev_v068229337" in block
    assert block.index("source_idest1_v068229337") < block.index("sc.abundance_lower")


def test_cpp_gate_is_line_only_and_before_existing_abundance_gate():
    text = CPP.read_text()
    anchor = text.index("0.6.82.29.3.3.7: literal calc_emisab_ion line eligibility")
    block = text[anchor:anchor + 3600]
    assert "!evaluated[k].bound_free_spectral" in block
    assert "rec.rate_type == 4 || rec.rate_type == 9 || rec.rate_type == 14" in block
    assert "continue;" in block
    assert block.index("source_nlev_v068229337") < block.index("floor_v064812314")


def test_cpp_retains_prior_option4_elmn_nbinc_width_and_pass_lifetime_repairs():
    local = CPP.read_text()
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text()
    assert "source_pprint4_nlbin_v068229336" in local
    assert "pprint4_elmn_wavelength_v068229336" in local
    assert "lower_one_based_v068229336 = std::max(1, nb1_v068229336 - 1)" in local
    assert "pprint4_flinel_accumulator_v068229334" in standalone


def test_python_broad_calc_emisab_already_has_source_strict_endpoint_gate():
    text = PYBROAD.read_text()
    assert "if 0 < idest1 < ion.nlev and 0 < idest2 < ion.nlev:" in text


def test_python_compact_and_final_consumers_mirror_strict_source_invariant():
    text = PYEM.read_text()
    anchor = text.index("0.6.82.29.3.3.7: calc_emisab_ion can seed nlbin only when")
    block = text[anchor:anchor + 1500]
    assert "0 < idest1 < int(ion.nlev)" in block
    assert "0 < idest2 < int(ion.nlev)" in block
    assert text.count("source_line_endpoints_valid_v068229337") >= 2
    assert "0 < idest1 < ion.nlev and 0 < idest2 < ion.nlev" in text


def test_host_runner_tracks_337_and_keeps_flinel_inventory_diagnostics():
    runner = (ROOT / 'tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3_7.py').read_text()
    assert 'EXPECTED_VERSION="0.6.82.29.3.3.7"' in runner
    assert 'OUTPUT_CONTROL_OPTION4_068229337_CPP_RESULT' in runner
    assert 'flinel nonzero: fortran=' in runner
    assert 'flinel cpp-only channels:' in runner


def test_science_revision_and_abis_remain_frozen():
    api=(ROOT/'src/xstar_tools/xstar/cpp/xstar_api.h').read_text()
    prod=(ROOT/'src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h').read_text()
    fixed=(ROOT/'src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h').read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert '#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110' in prod
    assert '#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u' in fixed
