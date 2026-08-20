from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
ATDB = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp"


def test_version_plan_and_fe_only_scope():
    assert 'version = "0.6.82.30.8.4"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.82.30.8.4" in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    plan = json.loads((ROOT / "qualification/fe_reference_0_6_82_30_8_4/fe_reference_0_6_82_30_8_4.json").read_text())
    assert plan["case"] == "fe_reference_ne1e8"
    assert plan["diagnostic_evidence"]["type82_records"] == 462
    assert plan["diagnostic_evidence"]["type82_mismatched_terms"] == 1848
    assert plan["parameters"]["elements"] == ["h", "he", "fe"]


def test_type82_uses_fixed_program_low_high_abi():
    text = ATDB.read_text()
    block = text.split("case 82: {", 1)[1].split("case 85:", 1)[0]
    assert "energy_order_pair(ii[0],ii[1]);" in block
    assert "upper_lower_pair(ii[0],ii[1]);" not in block
    assert "calc_hmc_ion.f90" in block
    assert "(upper_row,lower_row)" in block
    assert "462 Fe UTA records (1848 matrix terms)" in block


def test_type75_and_type92_are_not_changed_by_3084():
    text = ATDB.read_text()
    type75 = text.split("case 75: {", 1)[1].split("case 79:", 1)[0]
    type92 = text.split("case 92:", 1)[1].split("case 96:", 1)[0]
    assert "const int id1=std::max<int>(ii[ii.size()-4],1);" in type75
    assert 'need(ii.size()>=3&&rr.size()>=42,"short payload"); set_pair(ii[0],ii[1]); break;' in type92


def test_corrected_matrix_comparator_is_fe_only_and_uses_physical_stage():
    text = (ROOT / "tools/qualification/diagnostics/fe_call1_06823083_v2/compare_fe_call1_matrix_diag_06823083_v2.py").read_text()
    assert "target=(4456,33,519720)" in text
    assert "tags_for_fe_solver" in text
    assert "int(r['ion_charge'])+1" in text
    assert "FE2_MATRIX_IDENT_FAMILY" in text


def test_3084_runner_is_focused_cpp_fe_gate():
    runner = (ROOT / "tools/qualification/run_fe_reference_host_smoke_0_6_82_30_8_4.py").read_text()
    assert 'EXPECTED_VERSION = "0.6.82.30.8.4"' in runner
    assert 'CASE = "fe_reference_ne1e8"' in runner
    assert 'reference = args.fortran_reference_root.resolve() / CASE' in runner
    assert "FE_REFERENCE_06823084_NTOTIT_CPP" in runner
    assert "FE_REFERENCE_06823084_NTOTIT_FORTRAN" in runner
    assert "multi_element_xi1_ne1e12" not in runner
