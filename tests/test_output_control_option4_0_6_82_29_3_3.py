from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def _load():
    p=ROOT/'tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3.py'
    spec=importlib.util.spec_from_file_location('oc433_test',p); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def test_version_and_changelog():
    assert 'version = "0.6.82.29.3.3"' in (ROOT/'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.3' in (ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text()
    assert '0.6.82.29.3.3 - Option 4 full continuum opacity/emissivity payload' in (ROOT/'CHANGELOG.md').read_text()

def test_cpp_option4_full_payload_and_tails_present():
    text=(ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp').read_text()
    for token in ('sigma*e**3','option4_brcems','vector_value(ws.opakcont, i)','vector_value(ws.flinel, i)','opsum cont=','rosseland mean opacity=','option4_rsum1','option4_source_planck_coeff'):
        assert token in text

def test_python_option4_full_payload_and_tails_present():
    text=(ROOT/'src/xstar_tools/xstar/pprint_legacy.py').read_text()
    for token in ('sigma*e**3','scattered = opakcont[i]','flinel[i]','opsum cont=','rosseland mean opacity=','source_planck_coeff','rsum1'):
        assert token in text

def test_private_cpp_retains_flinel_without_public_abi_change():
    state=(ROOT/'src/xstar_tools/xstar/cpp/xstar_run_state.hpp').read_text()
    stand=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    assert 'std::vector<double> flinel;' in state
    assert 'source_workspace.flinel = source.flinel' in stand or 'ws.flinel = source.flinel' in stand

def test_option4_parser_rejects_old_short_rows_and_missing_tails(tmp_path:Path):
    mod=_load(); full=mod._load(ROOT); good=tmp_path/'good'; old=tmp_path/'old'; good.mkdir(); old.mkdir()
    (good/'xout_step.log').write_text(
        ' print option: 4\n continuum opacity and emissivities (/cm**3/sec/10**38)\n channel, energy,      opacity,    sigma*e**3,scattered,  rec. in,   rec. out,  brem. em., source, bbe,photon occ\n'
        '      2 1.0E-1 5.0E-22 5.0E-42 0.0 0.0 2.0E-6 1.4E2 2.0E22 2.7E22 7.5E-1 0.0\n'
        ' opsum cont= 6.0E-13\n rosseland mean opacity= 1.0E2 6.0E-15\n print option: 6\n')
    (old/'xout_step.log').write_text(
        ' print option: 4\n continuum opacity and emissivities (/cm**3/sec/10**38)\n channel, energy, opacity, scattered, rec. in, rec. out, source\n'
        '      2 1.0E-1 5.0E-22 0.0 0.0 2.0E-6\n print option: 6\n')
    gs=mod.option4_shape(full,good); os=mod.option4_shape(full,old)
    assert gs['rows']==1 and gs['opsum'] is not None and gs['rosseland'] is not None
    assert os['rows']==0 and os['opsum'] is None and os['rosseland'] is None

def test_option4_parser_accepts_fortran_missing_e_exponent(tmp_path:Path):
    mod=_load(); full=mod._load(ROOT); p=tmp_path/'x'; p.mkdir()
    (p/'xout_step.log').write_text(
        ' print option: 4\n continuum opacity and emissivities (/cm**3/sec/10**38)\n channel, energy,      opacity,    sigma*e**3,scattered,  rec. in,   rec. out,  brem. em., source, bbe,photon occ\n'
        '      2 1.0E-1 3.63124-270 5.0E-42 0.0 0.0 2.0E-6 1.4E2 2.0E22 2.7E22 7.5E-1 0.0\n'
        ' opsum cont= 6.0E-13\n rosseland mean opacity= 1.0E2 6.0E-15\n print option: 6\n')
    sh=mod.option4_shape(full,p)
    assert sh['rows']==1 and sh['payload'][0][1][1]==3.63124e-270

def test_option4_narrow_host_gate_marker():
    text=(ROOT/'tools/qualification/run_output_control_option4_host_smoke_0_6_82_29_3_3.py').read_text()
    assert 'CASE="lprint_3"' in text
    assert 'OUTPUT_CONTROL_OPTION4_06822933_CPP_RESULT' in text
    assert "ref_shape['rows']==998" in text
    assert 'tails_match_fortran' in text
