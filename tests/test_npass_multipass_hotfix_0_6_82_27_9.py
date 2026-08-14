from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STAND=ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'
SCI=ROOT/'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp'
STEP=ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_9.py'
MAN=ROOT/'qualification/npass_0_6_82_27_9/npass_hotfix_source_scope_0_6_82_27_9.json'
def runner():
    s=importlib.util.spec_from_file_location('npass0279_runner',RUNNER); assert s and s.loader
    m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); return m

def test_version_scope_and_frozen_ids():
    assert any(f'version = "{v}"' in (ROOT/'pyproject.toml').read_text() for v in ('0.6.82.27.9','0.6.82.27.10'))
    o=json.loads(MAN.read_text()); assert o['predecessor']=='0.6.82.27.8'
    assert set(o['intentional_numerical_source_changes'])=={
        'src/xstar_tools/xstar/cpp/xstar_standalone.cpp',
        'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp',
        'src/xstar_tools/xstar/cpp/xstar_step_log.cpp'}
    assert (o['science_revision'],o['c_api_abi'],o['production_zone_abi'],o['fixed_state_abi'])==('0.6.48.12.3.45.3.3.8',60487,6048110,60488)

def test_unsavd_restore_history_is_preserved_or_source_faithfully_superseded():
    c=STAND.read_text(); py=(ROOT/'pyproject.toml').read_text()
    if 'version = "0.6.82.27.9"' in py:
        assert 'literal rstepr2.f90 restores BOTH tau0 columns' in c
        assert 'rstepr3.f90 likewise restores both tauc columns' in c
        region=c[c.index('literal rstepr2.f90 restores BOTH tau0 columns'):c.index('const std::size_t grid_stride', c.index('literal rstepr2.f90 restores BOTH tau0 columns'))]
        assert region.count('for (std::size_t plane = 0u; plane < 2u; ++plane)')==2
    else:
        # .27.10 deliberately rejects the .27.9 two-plane experiment because it
        # regressed the accepted .27.8 Option-17 thermal trajectory.
        region=c[c.index('retain the scientifically accepted .27.8 repeated-pass'):c.index('const std::size_t grid_stride', c.index('retain the scientifically accepted .27.8 repeated-pass'))]
        assert 'const std::size_t plane = radial_direction > 0 ? 0u : 1u;' in region
        assert 'for (std::size_t plane = 0u; plane < 2u; ++plane)' not in region

def test_rrc_mapping_is_source_one_based_or_canonical_compact_only():
    c=SCI.read_text()
    start=c.index('double rrc_workspace_value_v0682279(')
    end=c.index('struct RrcBridgeArrays',start)
    fn=c[start:end]
    assert 'source_index_one_based' in fn and 'canonical_compact_index' in fn
    assert 'values[identity_index]' not in fn
    assert 'A physical' in fn and 'zero is authoritative' in fn
    assert ('const std::size_t source_slot_v0682279 = static_cast<std::size_t>(id.continuum_index);' in c or 'const std::size_t source_slot_v06822710 = static_cast<std::size_t>(id.continuum_index);' in c)

def test_option23_uses_final_pass_detal2():
    t=STEP.read_text()
    assert 'final_pass_v0682279' in t
    assert 'final_line_detail_name_v0682279' in t
    assert '"_detal2.fits"' in t
    assert 'fits_open_file(&detail,final_line_detail_path_v0682279.c_str()' in t

def test_option27_repeated_pass_does_not_append_synthetic_terminal_row():
    c=SCI.read_text()
    assert 'const bool repeated_final_pass_v0682279' in c
    assert '? state.radial_zones.size() - 1u : state.radial_zones.size()' in c
    assert 'repeated_final_pass_pprint12_overwrite' in c
    # ABUNDANCES, HEATING, COOLING share the source zrtmp row ledger.
    assert c.count('static_cast<long>(zrtmp_rows_v0682279)') >= 3

def test_runner_option22_parser_accepts_concatenated_fortran_fields(tmp_path):
    m=runner(); p=tmp_path/'xout_step.log'
    p.write_text(' ncn2= 999\n print option:22\nhttot=  6.643E-07cltot=  6.643E-07taulc=  2.026E-29taulcb=  0.000E+00\n print option: 5\n energy sums: abs, cont, line, err:  9.20863E-12  1.63137E-13  1.86252E-09 -2.01275E+02\n')
    q=m.parse_step_publication_0682279(p)
    assert q['ncn2']==999
    assert q['option22']==(6.643e-7,6.643e-7,2.026e-29,0.0)
    assert q['option5'][0]==9.20863e-12

def test_27_8_option22_unsmoothed_fix_retained():
    assert 'final_writer_unsmoothed_opakc_v0682278' in STAND.read_text()
