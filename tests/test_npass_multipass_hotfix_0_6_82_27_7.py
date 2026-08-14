from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STEP=ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp'
STAND=ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_7.py'
MAN=ROOT/'qualification/npass_0_6_82_27_7/npass_hotfix_source_scope_0_6_82_27_7.json'
def runner():
    s=importlib.util.spec_from_file_location('npass0277_runner',RUNNER); assert s and s.loader
    m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); return m
def test_version_scope_and_frozen_ids():
    assert any(f'version = "{v}"' in (ROOT/'pyproject.toml').read_text() for v in ('0.6.82.27.7','0.6.82.27.8','0.6.82.27.9','0.6.82.27.10','0.6.82.27.12','0.6.82.27.13'))
    o=json.loads(MAN.read_text()); assert o['predecessor']=='0.6.82.27.6'
    assert o['intentional_numerical_source_changes']==['src/xstar_tools/xstar/cpp/xstar_standalone.cpp','src/xstar_tools/xstar/cpp/xstar_step_log.cpp']
    assert (o['science_revision'],o['c_api_abi'],o['production_zone_abi'],o['fixed_state_abi'])==('0.6.48.12.3.45.3.3.8',60487,6048110,60488)
def test_ncn2_is_not_hardcoded():
    t=STEP.read_text(); assert 'out << " ncn2= 9999\\n";' not in t
    assert 'parameter_number(state, "ncn2", 9999.0)' in t
def test_option5_selects_final_pass_detail():
    t=STEP.read_text(); assert 'final_pass_detal4_path_v0682277' in t
    assert 'detail_path_v0682277 = final_pass_detal4_path_v0682277(output_dir, state)' in t
    assert 'read_spectrum_column(detail_path_v0682277' in t
def test_option22_uses_final_writer_depth_and_final_stpcut_is_retained():
    s=STEP.read_text(); c=STAND.read_text()
    assert 'final_dpthc_v0682277' in s
    assert 'eval.source_workspace.dpthc' in s
    assert 'opacity_v0682277 * final_writer_delr' in c
    assert 'final_pprint_data.radial_direction_v068227 > 0 ? 1u : 0u' in c
def test_runner_publication_parser(tmp_path):
    m=runner(); p=tmp_path/'xout_step.log'
    p.write_text(' ncn2= 999\n print option:22\n r=  1.000E+00 t=  1.000E+00 log(xi)=  1.000E+00 n_e=  1.000E+00 n_p=  1.000E+00\nhttot=  1.000E-06 cltot=  1.000E-06 taulc=  2.026E-29taulcb=  0.000E+00\n print option: 5\n energy sums: abs, cont, line, err:  9.20863E-12  1.63137E-13  1.86252E-09 -2.01275E+02\n')
    q=m.parse_step_publication_0682277(p)
    assert q['ncn2']==999 and q['option5'][0]==9.20863e-12 and q['option22'][2]==2.026e-29
