from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STAND=ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'
SCI=ROOT/'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp'
STEP=ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_10.py'
MAN=ROOT/'qualification/npass_0_6_82_27_10/npass_hotfix_source_scope_0_6_82_27_10.json'
def runner():
    s=importlib.util.spec_from_file_location('npass02710_runner',RUNNER); assert s and s.loader
    m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); return m

def test_version_scope_and_frozen_ids():
    assert ('version = "0.6.82.27.10"' in (ROOT/'pyproject.toml').read_text() or 'version = "0.6.82.27.12"' in (ROOT/'pyproject.toml').read_text() or 'version = "0.6.82.27.13"' in (ROOT/'pyproject.toml').read_text() or ('version = "0.6.82.27.14"' in (ROOT/'pyproject.toml').read_text() or 'version = "0.6.82.27.15"' in (ROOT/'pyproject.toml').read_text()))
    o=json.loads(MAN.read_text()); assert o['predecessor']=='0.6.82.27.9'
    assert set(o['intentional_numerical_source_changes'])=={
        'src/xstar_tools/xstar/cpp/xstar_standalone.cpp','src/xstar_tools/xstar/cpp/xstar_science_fits.cpp'}
    assert (o['science_revision'],o['c_api_abi'],o['production_zone_abi'],o['fixed_state_abi'])==('0.6.48.12.3.45.3.3.8',60487,6048110,60488)

def test_directional_unsavd_restores_27_8_science_lifetime():
    c=STAND.read_text(); start=c.index('retain the scientifically accepted .27.8 repeated-pass')
    end=c.index('const std::size_t grid_stride',start); region=c[start:end]
    assert 'const std::size_t plane = radial_direction > 0 ? 0u : 1u;' in region
    assert 'for (std::size_t plane = 0u; plane < 2u; ++plane)' not in region

def test_terminal_savd_persists_post_stpcut_boundary_without_stale_refresh():
    c=STAND.read_text(); assert 'Persist this post-STPCUT owner directly' in c
    assert 'retain_pre_stpcut_cumulative_state(data, terminal_saved_boundary_v0682274)' not in c

def test_rrc_detail_uses_source_inventory_and_one_based_npconi2_slot():
    c=SCI.read_text(); assert 'detail_rrc_identities_v06822710' in c and 'state.source_rrc_identities' in c
    assert 'const std::size_t source_slot_v06822710 = static_cast<std::size_t>(id.continuum_index);' in c
    assert 'row.tau_in = two_plane_value(tauc, n, 0, source_slot_v06822710, "tauc")' in c
    assert 'row.tau_out = two_plane_value(tauc, n, 1, source_slot_v06822710, "tauc")' in c
    for s in ('208->209','805->806','860->861','863->864'): assert s in c

def test_option27_279_fix_retained_and_option23_formatter_unchanged():
    c=SCI.read_text(); t=STEP.read_text()
    assert 'repeated_final_pass_v0682279' in c and 'zrtmp_rows_v0682279' in c and 'repeated_final_pass_pprint12_overwrite' in c
    assert 'final_pass_v0682279' in t and 'final_line_detail_path_v0682279' in t

def test_runner_has_strict_order_and_requested_sentinels():
    c=RUNNER.read_text()
    assert 'option23_required = pass_count > 1' in c
    assert all(x in c for x in ('stage1 =','stage2 =','stage3 =','stage4 ='))
    assert '208, 209, 805, 806, 860, 861, 863, 864' in c

def test_option22_concat_parser_still_works(tmp_path):
    m=runner(); p=tmp_path/'xout_step.log'
    p.write_text(' ncn2= 999\n print option:22\nhttot=  6.643E-07cltot=  6.643E-07taulc=  2.026E-29taulcb=  0.000E+00\n')
    q=m.parse_step_publication_06822710(p)
    assert q['ncn2']==999 and q['option22']==(6.643e-7,6.643e-7,2.026e-29,0.0)
