from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STAND=ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'
SCI=ROOT/'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp'
STEP=ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_11.py'
MAN=ROOT/'qualification/npass_0_6_82_27_11/npass_hotfix_source_scope_0_6_82_27_11.json'
def runner():
    s=importlib.util.spec_from_file_location('npass02711_runner',RUNNER); assert s and s.loader
    m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); return m

def test_06822711_version_scope_and_frozen_ids():
    assert 'version = "0.6.82.27.11"' in (ROOT/'pyproject.toml').read_text()
    o=json.loads(MAN.read_text()); assert o['predecessor']=='0.6.82.27.10'
    assert set(o['intentional_numerical_source_changes'])=={'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'}
    assert (o['science_revision'],o['c_api_abi'],o['production_zone_abi'],o['fixed_state_abi'])==('0.6.48.12.3.45.3.3.8',60487,6048110,60488)

def test_06822711_preserves_directional_unsavd_and_does_not_touch_tau_in_reproject():
    c=STAND.read_text(); start=c.index('retain the scientifically accepted .27.8 repeated-pass'); end=c.index('const std::size_t grid_stride',start)
    assert 'const std::size_t plane = radial_direction > 0 ? 0u : 1u;' in c[start:end]
    r0=c.index('void repair_repeated_pass_source_opacity_ownership_v06822711'); r1=c.index('// XSTAR-FUNCTION-COMMENT-BEGIN\n// Purpose: Emit opt-in repeated-pass ownership diagnostics',r0); r=c[r0:r1]
    assert 'boundary.tau0' not in r and 'boundary.tauc' not in r
    assert 'data.line_tau_in' not in r and 'data.source_tau_in' not in r

def test_06822711_reprojects_only_repeated_source_opacity_slots():
    c=STAND.read_text(); r0=c.index('void repair_repeated_pass_source_opacity_ownership_v06822711'); r1=c.index('// XSTAR-FUNCTION-COMMENT-BEGIN\n// Purpose: Emit opt-in repeated-pass ownership diagnostics',r0); r=c[r0:r1]
    assert 'data.radial_pass_index_v068227 <= 1u' in r
    assert 'std::fill(boundary.oplin.begin(), boundary.oplin.end(), 0.0);' in r
    assert 'std::fill(boundary.opakab.begin(), boundary.opakab.end(), 0.0);' in r
    assert 'record.type50_line_index_one_based' in r
    assert 'record.continuum_index_one_based' in r
    assert 'boundary.oplin[source_slot] = canonical_line_opacity_v06822711' in r
    assert 'boundary.opakab[source_slot] = canonical_rrc_opacity_v06822711' in r

def test_06822711_reproject_occurs_after_heatt_before_savd_and_stpcut():
    c=STAND.read_text()
    repair=c.index('repair_repeated_pass_source_opacity_ownership_v06822711(data, boundary);',c.index('write_ca13_lifetime_probe'))
    retain=c.index('retain_pre_stpcut_cumulative_state(data, boundary);',repair)
    savd=c.index('make_saved_shell_v068227(',retain)
    stpcut=c.index('advance_stpcut_depths(',savd)
    assert repair < retain < savd < stpcut

def test_06822711_trace_covers_requested_lifetime_boundaries_and_sentinels():
    c=STAND.read_text()
    for token in ('post_solve_pre_reproject','post_reproject_pre_savd','make_saved_shell_pre_stpcut','immediately_pre_stpcut','immediately_post_stpcut','terminal_transport_boundary_capture','make_saved_shell_terminal'):
        assert token in c
    for token in ('208,209,661,662,663,664,665,805,806,860,861,863,864','XSTAR_V06822711_NPASS_OWNERSHIP_TRACE'):
        assert token in c

def test_06822711_keeps_option27_and_rrc_slot_n_writer_and_option23_reader():
    s=SCI.read_text(); t=STEP.read_text()
    assert all(x in s for x in ('repeated_final_pass_v0682279','zrtmp_rows_v0682279','repeated_final_pass_pprint12_overwrite'))
    assert 'source_slot_v06822710 = static_cast<std::size_t>(id.continuum_index)' in s
    assert 'row.tau_in = two_plane_value(tauc, n, 0, source_slot_v06822710, "tauc")' in s
    assert 'final_line_detail_path_v0682279' in t

def test_06822711_runner_has_ordered_host_gate_and_parser(tmp_path):
    m=runner(); c=RUNNER.read_text()
    assert all(x in c for x in ('stage1 =','stage2 =','stage3 =','stage4 ='))
    assert '208, 209, 805, 806, 860, 861, 863, 864' in c
    p=tmp_path/'xout_step.log'; p.write_text(' ncn2= 999\n print option:22\nhttot=  6.643E-07cltot=  6.643E-07taulc=  2.026E-29taulcb=  0.000E+00\n')
    q=m.parse_step_publication_06822711(p)
    assert q['ncn2']==999 and q['option22']==(6.643e-7,6.643e-7,2.026e-29,0.0)
