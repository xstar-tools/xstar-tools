from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCI=ROOT/'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp'
STAND=ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'
STEP=ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_12.py'
MAN=ROOT/'qualification/npass_0_6_82_27_12/npass_hotfix_source_scope_0_6_82_27_12.json'
def runner():
    s=importlib.util.spec_from_file_location('npass02712_runner',RUNNER); assert s and s.loader
    m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); return m

def test_version_scope_and_frozen_ids():
    assert any(f'version = "{v}"' in (ROOT/'pyproject.toml').read_text() for v in ('0.6.82.27.12','0.6.82.27.13','0.6.82.27.14','0.6.82.27.15','0.6.82.27.16'))
    o=json.loads(MAN.read_text())
    assert o['predecessor']=='0.6.82.27.10'
    assert o['predecessor_sdist_sha256']=='c15345b381e0ec774b88ca8274bd787ca0eb41a4a2064b66c8b2596da60128f9'
    assert o['intentional_numerical_source_changes']==['src/xstar_tools/xstar/cpp/xstar_science_fits.cpp']
    assert (o['science_revision'],o['c_api_abi'],o['production_zone_abi'],o['fixed_state_abi'])==('0.6.48.12.3.45.3.3.8',60487,6048110,60488)

def test_generic_line_detail_keeps_source_savd_tau_owner():
    c=SCI.read_text()
    assert 'merged_line_row(r, &found_diag->second)' in c
    assert 'merged_line_row(found_diag->second, &r)' not in c

def test_rrc_merge_never_overwrites_source_savd_tauc():
    c=SCI.read_text(); a=c.index('RrcRow merged_rrc_row('); b=c.index('// XSTAR-FUNCTION-COMMENT-BEGIN',a+1); m=c[a:b]
    assert 'out.tau_in = diagnostic->tau_in' not in m
    assert 'out.tau_out = diagnostic->tau_out' not in m
    for token in ('diagnostic->energy_ev','diagnostic->emis_in','diagnostic->emis_out','diagnostic->absorption','diagnostic->opacity'):
        assert token in m

def test_2710_npconi2_and_option27_are_retained():
    c=SCI.read_text()
    assert 'const std::size_t source_slot_v06822710 = static_cast<std::size_t>(id.continuum_index);' in c
    assert 'state.source_rrc_identities' in c
    assert 'repeated_final_pass_v0682279' in c and 'zrtmp_rows_v0682279' in c

def test_protected_standalone_and_step_are_2710_semantics():
    s=STAND.read_text(); t=STEP.read_text()
    assert 'const std::size_t plane = radial_direction > 0 ? 0u : 1u;' in s
    assert 'Persist this post-STPCUT owner directly' in s
    assert 'final_writer_unsmoothed_opakc_v0682278' in s
    assert 'reproject_repeated_pass_source_workspace_v06822711' not in s
    assert 'final_line_detail_path_v0682279' in t

def test_runner_has_strict_four_stage_order_and_sentinels():
    c=RUNNER.read_text()
    assert all(x in c for x in ('stage1 =','stage2 =','stage3 =','stage4 ='))
    assert 'option23_required = pass_count > 1' in c
    assert '208, 209, 805, 806, 860, 861, 863, 864' in c

def test_option22_concat_parser_still_works(tmp_path):
    m=runner(); p=tmp_path/'xout_step.log'
    p.write_text(' ncn2= 999\n print option:22\nhttot=  6.643E-07cltot=  6.643E-07taulc=  2.026E-29taulcb=  0.000E+00\n')
    q=m.parse_step_publication_06822712(p)
    assert q['ncn2']==999 and q['option22']==(6.643e-7,6.643e-7,2.026e-29,0.0)
