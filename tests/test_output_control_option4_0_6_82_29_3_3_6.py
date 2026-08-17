from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
PHYSICAL = ROOT / "src/xstar_tools/xstar/physical_runner.py"


def test_version_bumped_after_rejected_335_host_candidate():
    assert 'version = "0.6.82.29.3.3.6"' in (ROOT / 'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3.6' in (ROOT / 'src/xstar_tools/xstar/cpp/Makefile').read_text()


def test_cpp_builds_private_pprint4_nlbin_from_xstarsetup_elmn():
    text = CPP.read_text()
    assert "source_pprint4_nlbin_v068229336" in text
    assert "c_v068229336.rate_type == 9 || c_v068229336.rate_type == 14" in text
    assert "c_v068229336.wavelength_a = 0.0" in text
    assert "source_pprint4_nlbin_v068229336 = source_rlbin_exact_audit" in text


def test_cpp_private_revisit_uses_xstarsetup_slot_coordinate():
    text = CPP.read_text()
    anchor = text.index("0.6.82.29.3.3.6: reproduce the literal xstarsetup")
    block = text[anchor:anchor + 5000]
    assert "pprint4_elmn_wavelength_v068229336" in block
    assert "(original_c.rate_type == 9 || original_c.rate_type == 14)" in block
    assert "? 0.0 : operational_line_wavelength_v82_patch5208" in block
    assert "source_pprint4_nlbin_v068229336" in block


def test_cpp_private_pprint4_uses_slot_owned_energy_and_two_sided_width():
    text = CPP.read_text()
    anchor = text.index("const int nb1_v068229336")
    block = text[anchor:anchor + 3500]
    assert "lower_one_based_v068229336 = std::max(1, nb1_v068229336 - 1)" in block
    assert "line_energy_v068229336" in block
    assert "source_hc_v068229336 / (pprint4_elmn_wavelength_v068229336 + 1.0e-36)" in block
    assert "width_v068229336 / ergsev_v068229336" in block


def test_cpp_operational_selected_line_replay_remains_unfiltered():
    text = CPP.read_text()
    anchor = text.index("std::vector<double> pprint4_flinel_v068229334")
    block = text[anchor:text.index("std::vector<double> selected_rcem", anchor)]
    assert "if (original_c.rate_type != 4 && original_c.rate_type != 9)\n                    continue;" not in block
    assert "selected_lines_v82_patch5206.push_back(c);" in block


def test_python_calc_emis_context_mirrors_xstarsetup_elmn_without_rewriting_public_metadata():
    text = PHYSICAL.read_text()
    helper = text[text.index("def _source_calc_emis_line_wavelengths"):text.index("def _bind_emissivity_contexts")]
    assert "if int(row.rate_type) in (9, 14):" in helper
    assert "continue" in helper
    assert "out[index] = float(row.wavelength_angstrom)" in helper
    bind = text[text.index("def _bind_emissivity_contexts"):text.index("def _bind_", text.index("def _bind_emissivity_contexts") + 10) if "def _bind_" in text[text.index("def _bind_emissivity_contexts") + 10:] else len(text)]
    assert "line_wavelength = _source_calc_emis_line_wavelengths(" in bind


def test_host_runner_tracks_336_and_full_option4_diagnostics():
    runner = (ROOT / 'tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3_6.py').read_text()
    assert 'EXPECTED_VERSION="0.6.82.29.3.3.6"' in runner
    assert 'OUTPUT_CONTROL_OPTION4_068229336_CPP_RESULT' in runner
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
