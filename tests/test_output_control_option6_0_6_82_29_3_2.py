from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def _load_runner():
    p=ROOT/'tools/qualification/run_output_control_host_smoke_0_6_82_29_3_2.py'
    spec=importlib.util.spec_from_file_location('oc632_test',p); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def test_version_and_changelog():
    assert 'version = "0.6.82.29.3.2"' in (ROOT/'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.82.29.3.2' in (ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text()
    assert '0.6.82.29.3.2 - Option 6 full continuum payload' in (ROOT/'CHANGELOG.md').read_text()

def test_cpp_option6_full_header_and_columns_present():
    text=(ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp').read_text()
    for token in (
        '1 ) photon energy in eV',
        '2) Incident radiation field',
        '10) Planck function at local gas temperature',
        '11) ratio of the xstar internal radiation field',
        'vector_value(ws.zremsz, i)',
        'source_planck_coeff',
        'option6_fpr2',
        'source_expo',
    ): assert token in text

def test_python_option6_full_header_and_columns_present():
    text=(ROOT/'src/xstar_tools/xstar/pprint_legacy.py').read_text()
    for token in (
        '1 ) photon energy in eV',
        '2) Incident radiation field',
        '10) Planck function at local gas temperature',
        '11) ratio of the xstar internal radiation field',
        'source_planck_coeff',
        'source_radius_scale',
        'incident = zremsz[i]',
    ): assert token in text

def test_option6_parser_rejects_old_short_rows(tmp_path:Path):
    mod=_load_runner(); ref=tmp_path/'ref'; old=tmp_path/'old'; ref.mkdir(); old.mkdir()
    (ref/'xout_step.log').write_text(
        ' print option: 6\n'
        ' continuum luminosities (/sec/10**38) and depths\n'
        ' real quantities are as follows:\n'
        '      1 1.0E-1 9.0E5 9.0E5 0.0 2.0E-2 0.0 2.0E-2 4.0E-13 0.0 2.6E22 2.0E-4\n'
        ' norms:\n                    1.0 2.0 3.0 4.0\n'
        ' print option:18\n')
    (old/'xout_step.log').write_text(
        ' print option: 6\n'
        ' continuum luminosities (/sec/10**38) and depths\n'
        ' real quantities are as follows:\n'
        '      1 1.0E-1 9.0E5 0.0 2.0E-2 0.0 2.0E-2 4.0E-13 0.0\n'
        ' norms:\n                    1.0 2.0 3.0 4.0\n'
        ' print option:18\n')
    assert mod.verbose_shape(ref,6)['rows']==1
    assert mod.verbose_shape(old,6)['rows']==0
    assert not mod.shape_matches(mod.verbose_shape(ref,6),mod.verbose_shape(old,6),6)

def test_option6_parser_accepts_fortran_missing_e_exponent(tmp_path:Path):
    mod=_load_runner(); p=tmp_path/'x'; p.mkdir()
    (p/'xout_step.log').write_text(
        ' print option: 6\n'
        '      1 1.0E-1 9.0E5 9.0E5 0.0 3.63124-270 0.0 3.63124-270 4.0E-13 0.0 2.6E22 2.0E-4\n'
        ' norms:\n                    1.0 2.0 3.0 4.0\n'
        ' print option:18\n')
    sh=mod.verbose_shape(p,6)
    assert sh['rows']==1
    assert sh['payload'][0][1][4] == 3.63124e-270

def test_option6_narrow_host_gate():
    text=(ROOT/'tools/qualification/run_output_control_option6_host_smoke_0_6_82_29_3_2.py').read_text()
    assert 'CASE="lprint_3"' in text
    assert 'OUTPUT_CONTROL_OPTION6_06822932_CPP_RESULT' in text
    assert 'header_matches_fortran' in text
    assert "cpp_shape.get('rows')==999" in text
