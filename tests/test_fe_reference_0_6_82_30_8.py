from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp"


def test_version_plan_and_fe_scope():
    assert 'version = "0.6.82.30.8"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.82.30.8" in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    plan = json.loads((ROOT / "qualification/fe_reference_0_6_82_30_8/fe_reference_0_6_82_30_8.json").read_text())
    assert plan["case"] == "fe_reference_ne1e8"
    assert plan["fortran_source_audit"]["active_fe_specific_data_types"] == [37, 75, 81, 82, 85, 86, 96, 97]
    assert plan["fortran_source_audit"]["source_metadata_or_disabled_data_types"] == [80, 83, 84]
    assert plan["parameters"]["elements"] == ["h", "he", "fe"]


def test_fe_active_type_inventory_matches_canonical_source_contract():
    text = CPP.read_text()
    m = re.search(r"const std::set<int> kActiveTypes = \{(.*?)\};", text, re.S)
    assert m
    active = {int(x) for x in re.findall(r"\d+", m.group(1))}
    for dt in (37, 75, 81, 82, 85, 86, 96, 97):
        assert dt in active
    for dt in (80, 83, 84):
        assert dt not in active


def test_type75_and_type96_use_packed_kN_not_previous_ion_identity():
    text = CPP.read_text()
    # Both operational lowering blocks must decode idest1 from packed i2=k_N.
    assert text.count("const int id1=std::max<int>(ii[ii.size()-4],1);") >= 2
    assert text.count("const int id2=std::max<int>(ii[ii.size()-2]+b.nlev-1,1);") >= 2
    # Literal source-publication endpoint helper must use the same pair.
    assert "case 75:\n        case 96:" in text
    assert "return {std::max(as_int(ii.size()-4),1)," in text
    assert "std::max(b.nlev+as_int(ii.size()-2)-1,1)};" in text
    # Freeze the exact root-cause explanation to prevent accidental regression.
    assert "ii[nidt-4] = k_N" in text
    assert "ii[nidt-3] = ion_(N-1)" in text


def test_runner_is_cpp_fe_only_and_reuses_fortran():
    runner = (ROOT / "tools/qualification/run_fe_reference_host_smoke_0_6_82_30_8.py").read_text()
    assert 'CASE = "fe_reference_ne1e8"' in runner
    assert 'choices=("prepare", "cpp", "compare", "cpp-compare")' in runner
    assert "FORTRAN xstar" not in runner
    assert "--fortran-reference-root" in runner
    assert "multi_element_xi1_ne1e12" not in runner
    assert "c5_reference_ne1e8" not in runner
    assert "FE_REFERENCE_0682308_NTOTIT_CPP" in runner
    assert "FE_REFERENCE_0682308_NTOTIT_FORTRAN" in runner
