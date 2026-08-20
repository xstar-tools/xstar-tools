from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
ATDB = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp"
ZONE = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"


def test_version_plan_and_fe_only_scope():
    assert 'version = "0.6.82.30.8.1"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.82.30.8.1" in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    plan = json.loads((ROOT / "qualification/fe_reference_0_6_82_30_8_1/fe_reference_0_6_82_30_8_1.json").read_text())
    assert plan["case"] == "fe_reference_ne1e8"
    assert plan["fortran_source_audit"]["type_57_final_evaluations_in_fortran_fe_reference"] == 16948
    assert plan["parameters"]["elements"] == ["h", "he", "fe"]


def test_type57_uses_literal_packed_i1_for_calt57_not_type13_metadata():
    text = ZONE.read_text()
    assert "const int i57=static_cast<int>(ints[0]);" in text
    assert "const int n=i57;" in text
    assert "type57_coefficients(n,input.temperature_k,ne,e1,eth,cion,crec)" in text
    assert "Type-83 level records carry i1=1 as a fixed metadata field" in text
    # The rejected predecessor used the duplicated Type-13 integer directly.
    assert "const int n=static_cast<int>(ints[1]);" not in text


def test_type57_lowerer_preserves_raw_i1_and_labels_level_n_provenance_only():
    text = ATDB.read_text()
    assert "else if (dt==57)" in text
    assert "int i57=ii[0]" in text
    assert "out.ints={i57,pn,local}" in text
    # Lowering already preserves raw Type-57 i1 as ints[0]; only the evaluator
    # changes in this revision.  Keep the ATDB/lowering translation byte-stable.


def test_runner_is_cpp_fe_only_and_uses_parent_fortran_root():
    runner = (ROOT / "tools/qualification/run_fe_reference_host_smoke_0_6_82_30_8_1.py").read_text()
    assert 'EXPECTED_VERSION = "0.6.82.30.8.1"' in runner
    assert 'CASE = "fe_reference_ne1e8"' in runner
    assert 'choices=("prepare", "cpp", "compare", "cpp-compare")' in runner
    assert "FORTRAN xstar" not in runner
    assert 'reference = args.fortran_reference_root.resolve() / CASE' in runner
    assert "multi_element_xi1_ne1e12" not in runner
    assert "FE_REFERENCE_06823081_NTOTIT_CPP" in runner
    assert "FE_REFERENCE_06823081_NTOTIT_FORTRAN" in runner
