from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STAND=ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'
STEP=ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_8.py'
MAN=ROOT/'qualification/npass_0_6_82_27_8/npass_hotfix_source_scope_0_6_82_27_8.json'
def runner():
    s=importlib.util.spec_from_file_location('npass0278_runner',RUNNER); assert s and s.loader
    m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); return m
def test_version_scope_and_frozen_ids():
    assert any(f'version = "{v}"' in (ROOT/'pyproject.toml').read_text() for v in ('0.6.82.27.8','0.6.82.27.9'))
    o=json.loads(MAN.read_text()); assert o['predecessor']=='0.6.82.27.7'
    assert o['intentional_numerical_source_changes']==['src/xstar_tools/xstar/cpp/xstar_standalone.cpp']
    assert (o['science_revision'],o['c_api_abi'],o['production_zone_abi'],o['fixed_state_abi'])==('0.6.48.12.3.45.3.3.8',60487,6048110,60488)
def test_final_option22_stpcut_uses_pre_gsmooth_opakc():
    c=STAND.read_text()
    capture=c.index('const auto final_writer_unsmoothed_opakc_v0682278 = final_pprint.opakc;')
    generic=c.index('advance_source_continuum_radiation(',capture)
    consume=c.index('final_writer_unsmoothed_opakc_v0682278[i_v0682277]',generic)
    assert capture < generic < consume
    assert 'canonical xstar.f90 does NOT call GSSMOOTH' in c
def test_27_7_option5_and_ncn2_repairs_are_retained():
    t=STEP.read_text()
    assert 'parameter_number(state, "ncn2", 9999.0)' in t
    assert 'out << " ncn2= 9999\\n";' not in t
    assert 'final_pass_detal4_path_v0682277' in t
    assert 'detail_path_v0682277 = final_pass_detal4_path_v0682277(output_dir, state)' in t
def test_runner_option22_parser(tmp_path):
    m=runner(); p=tmp_path/'xout_step.log'
    p.write_text(' ncn2= 999\n print option:22\n r=  1.000E+00 t=  1.000E+00 log(xi)=  1.000E+00 n_e=  1.000E+00 n_p=  1.000E+00\nhttot=  1.000E-06 cltot=  1.000E-06 taulc=  2.026E-29taulcb=  0.000E+00\n print option: 5\n energy sums: abs, cont, line, err:  9.20863E-12  1.63137E-13  1.86252E-09 -2.01275E+02\n')
    q=m.parse_step_publication_0682278(p)
    assert q['ncn2']==999 and q['option22'][2]==2.026e-29 and q['option5'][0]==9.20863e-12
def test_no_physics_kernel_change_declared():
    o=json.loads(MAN.read_text())
    assert 'src/xstar_tools/xstar/cpp/local_zone_engine.cpp' not in o['intentional_numerical_source_changes']
    assert 'src/xstar_tools/xstar/cpp/thermal_kernels.cpp' not in o['intentional_numerical_source_changes']
