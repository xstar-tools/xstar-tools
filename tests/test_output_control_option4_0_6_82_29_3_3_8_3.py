from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP_LOWER = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp"
CPP_ZONE = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
PY_LOWER = ROOT / "src/xstar_tools/xstar/native_fixed_program.py"
PY_RUNNER = ROOT / "src/xstar_tools/xstar/physical_runner.py"
RUNNER = ROOT / "tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3_8_3.py"


def test_version_bumped_after_3382_host_rejection():
    assert 'version = "0.6.82.29.3.3.8.3"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3.8.3' in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()


def test_cpp_type54_lowerer_retains_raw_rdat1_elmn_sidecar():
    text = CPP_LOWER.read_text()
    assert 'else if (dt==54)' in text
    assert 'out.reals={rr.empty()?0.0:rr[0]};' in text
    assert 'out.ints={ni,nf,li,lf,iq,caller_idest1,caller_idest2,a,c,kType54DualEndpointLayoutMagicV0682293382};' in text
    assert 'energy=std::abs(row_energy(l,upper)-row_energy(l,lower));' in text


def test_python_native_type54_lowerer_retains_same_raw_rdat1_sidecar():
    text = PY_LOWER.read_text()
    assert 'elif dt == 54:' in text
    assert 'payload_reals = [float(raw_reals[0]) if raw_reals else 0.0]' in text
    assert 'TYPE54_DUAL_ENDPOINT_LAYOUT_MAGIC_V0682293382' in text


def test_private_option4_elmn_helper_uses_raw_type54_rdat1_only_on_private_surface():
    text = CPP_ZONE.read_text()
    assert 'source_pprint4_elmn_wavelength_v0682293383' in text
    assert 'if (record.rate_type == 9 || record.rate_type == 14) return 0.0;' in text
    assert 'if (record.data_type == 54 &&' in text
    assert 'const double source_rdat1 = program.reals[record.real_offset];' in text
    assert 'return std::isfinite(source_rdat1) ? source_rdat1 : 0.0;' in text


def test_private_option4_rlbin_rank_uses_source_elmn_not_endpoint_wavelength():
    text = CPP_ZONE.read_text()
    assert 'c_v068229336.wavelength_a = source_pprint4_elmn_wavelength_v0682293383(' in text
    assert 'ctx.program, source_record_v068229338, c_v068229336.wavelength_a' in text
    assert 'source_pprint4_nlbin_v068229336 = source_rlbin_exact_audit(' in text
    assert 'pprint4_line_candidates_v068229336, input.radiation_energy_ev' in text


def test_private_option4_final_flinel_replay_uses_same_source_elmn():
    text = CPP_ZONE.read_text()
    assert 'source_pprint4_elmn_wavelength_v0682293383(' in text
    assert 'ctx.program, source_record_v068229338, operational_line_wavelength_v82_patch5208' in text
    assert 'source_calc_emis_consumer(' in text
    assert 'source_pprint4_nlbin_v068229336' in text


def test_operational_line_coordinate_remains_frozen():
    text = CPP_ZONE.read_text()
    assert 'source_line_wavelength_by_identity_v82_patch5208' in text
    assert 'operational_line_wavelength_v82_patch5208' in text
    assert 'source_calc_emis_nlbin_v82_patch5208' in text
    assert 'Keep the operational selected-line replay on its established' in text


def test_pure_python_calc_emis_elmn_already_uses_raw_source_line_metadata():
    text = PY_RUNNER.read_text()
    assert 'def _source_calc_emis_line_wavelengths' in text
    assert 'if int(row.rate_type) in (9, 14):' in text
    assert 'out[index] = float(row.wavelength_angstrom)' in text
    # SourceOutputMetadata is built by gathering RDAT(1), so Type-54's zero
    # line coordinate is retained instead of deriving a wavelength from levels.
    assert 'wavelengths[line_has_real] = np.abs(' in text
    assert 'master.rdat1.gather(line_rptr[line_has_real], dtype=np.float64)' in text


def test_host_runner_keeps_provenance_outside_file_silent_product_directory():
    text = RUNNER.read_text()
    assert 'OUTPUT_CONTROL_OPTION4_0682293383_CPP_RESULT' in text
    assert "provenance=(root/'logs'/'pprint4_flinel_provenance_0682293383.csv').resolve()" in text
    assert "XSTAR_V0682293383_PPRINT4_FLINEL_PROVENANCE_PATH" in text
    assert 'provenance type54 selected rows:' in text


def test_science_revision_and_abis_remain_frozen():
    api = (ROOT / 'src/xstar_tools/xstar/cpp/xstar_api.h').read_text()
    prod = (ROOT / 'src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h').read_text()
    fixed = (ROOT / 'src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h').read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert '#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110' in prod
    assert '#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u' in fixed
