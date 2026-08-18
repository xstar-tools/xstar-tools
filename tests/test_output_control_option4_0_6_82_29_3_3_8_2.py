from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP_LOWER = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp"
CPP_ZONE = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"
PY_LOWER = ROOT / "src/xstar_tools/xstar/native_fixed_program.py"
PY_UCALC = ROOT / "src/xstar_tools/xstar/ucalc.py"
PY_EMIS = ROOT / "src/xstar_tools/xstar/emissivity.py"
RUNNER = ROOT / "tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3_8_2.py"


def test_version_bumped_after_3381_host_rejection():
    assert 'version = "0.6.82.29.3.3.8.2"' in (ROOT / 'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3.8.2' in (ROOT / 'src/xstar_tools/xstar/cpp/Makefile').read_text()


def test_cpp_atdb_lowerer_preserves_both_type54_endpoint_pairs():
    text = CPP_LOWER.read_text()
    assert 'kType54DualEndpointLayoutMagicV0682293382 = 228' in text
    assert 'const int caller_idest1=ii[0], caller_idest2=ii[1];' in text
    assert 'const int a=ii[ii.size()-4], c=ii[ii.size()-3], iq=ii[ii.size()-2];' in text
    assert 'out.ints={ni,nf,li,lf,iq,caller_idest1,caller_idest2,a,c,kType54DualEndpointLayoutMagicV0682293382};' in text


def test_python_native_lowerer_preserves_same_type54_layout():
    text = PY_LOWER.read_text()
    assert 'TYPE54_DUAL_ENDPOINT_LAYOUT_MAGIC_V0682293382 = 228' in text
    assert 'caller_idest1, caller_idest2 = int(raw_ints[0]), int(raw_ints[1])' in text
    assert 'a, b, iq = int(raw_ints[-4]), int(raw_ints[-3]), int(raw_ints[-2])' in text
    assert 'TYPE54_DUAL_ENDPOINT_LAYOUT_MAGIC_V0682293382,' in text


def test_type54_ucalc_evaluator_still_owns_first_five_internal_payload_values():
    text = CPP_ZONE.read_text()
    assert 'case XSTAR_FIXED_OPCODE_TYPE54_ANGULAR_REDIS' in text
    assert 'const int ni0=static_cast<int>(ints[0]), nf0=static_cast<int>(ints[1]);' in text
    assert 'const int li=static_cast<int>(ints[2]), lf=static_cast<int>(ints[3]), iq=static_cast<int>(ints[4]);' in text
    assert 'xstar_engine_anl1_v1(ni0,nf0,lf,iq' in text


def test_cpp_calc_emis_publication_uses_caller_pair_not_ucalc_pair():
    text = CPP_ZONE.read_text()
    assert 'SourceLineEndpointOwnershipV0682293382' in text
    assert 'out.caller_idest1 = static_cast<int>(ints[5]);' in text
    assert 'out.caller_idest2 = static_cast<int>(ints[6]);' in text
    assert 'out.ucalc_idest1 = static_cast<int>(ints[7]);' in text
    assert 'out.ucalc_idest2 = static_cast<int>(ints[8]);' in text
    assert 'abundance_lower_row_v0682293382' in text
    assert 'abundance_upper_row_v0682293382' in text
    assert 'line_owner_v0682293382.caller_idest1 < source_nlev_v0682293382' in text
    assert 'line_owner_v0682293382.caller_idest2 < source_nlev_v0682293382' in text


def test_private_option4_rank_and_flinel_use_caller_owned_populations():
    text = CPP_ZONE.read_text()
    assert 'pprint4_energy_ordered_abundances_v068229338' in text
    assert 'source_line_endpoint_ownership_v0682293382(' in text
    assert 'endpoint_owner_v0682293382.lower_row' in text
    assert 'endpoint_owner_v0682293382.upper_row' in text
    assert 'c.ans2 * source_abund2_cm3_v068229338' in text
    assert 'c.ans1 * source_abund1_cm3_v068229338' in text


def test_pure_python_already_keeps_caller_and_ucalc_endpoint_roles_distinct():
    emis = PY_EMIS.read_text()
    ucalc = PY_UCALC.read_text()
    assert 'idest1, idest2 = int(ints[0]), int(ints[1])' in emis
    assert 'a,b=r.integers[-4],r.integers[-3]' in ucalc


def test_host_provenance_reports_both_endpoint_pairs_outside_product_dir():
    runner = RUNNER.read_text()
    zone = CPP_ZONE.read_text()
    assert 'OUTPUT_CONTROL_OPTION4_0682293382_CPP_RESULT' in runner
    assert "provenance=(root/'logs'/'pprint4_flinel_provenance_0682293382.csv').resolve()" in runner
    assert "XSTAR_V0682293382_PPRINT4_FLINEL_PROVENANCE_PATH" in runner
    for token in ('caller_idest1','caller_idest2','ucalc_idest1','ucalc_idest2','dual_type54'):
        assert token in zone
        assert token in runner


def test_science_revision_and_abis_remain_frozen():
    api=(ROOT/'src/xstar_tools/xstar/cpp/xstar_api.h').read_text()
    prod=(ROOT/'src/xstar_tools/xstar/cpp/xstar_production_zone_bridge.h').read_text()
    fixed=(ROOT/'src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h').read_text()
    assert '#define XSTAR_API_ABI_VERSION 60487u' in api
    assert '#define XSTAR_API_VERSION_STRING "0.6.48.12.3.45.3.3.8"' in api
    assert '#define XSTAR_PRODUCTION_ZONE_ABI_V0648110 6048110' in prod
    assert '#define XSTAR_FIXED_STATE_ENGINE_ABI_VERSION 60488u' in fixed
