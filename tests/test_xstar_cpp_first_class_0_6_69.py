from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from xstar_tools.execution import C_API_ABI_VERSION, SCIENCE_REVISION, ZONE_ABI_VERSION, package_version

ROOT=Path(__file__).resolve().parents[1]
FRONTEND=ROOT/'src/xstar_tools/xstar/native/xstar_cpp_frontend.cpp'
CPP=ROOT/'src/xstar_tools/xstar/cpp'


def _compiler():
    cxx=shutil.which('g++')
    if not cxx:
        pytest.skip('g++ is required for native frontend characterization')
    return cxx


def _build_stub_frontend(tmp_path:Path, zone_abi:int=ZONE_ABI_VERSION)->Path:
    cxx=_compiler()
    (tmp_path/'api_stub.cpp').write_text(
        '#include <cstdint>\n'
        f'extern "C" std::uint32_t xstar_api_abi_version(void){{return {C_API_ABI_VERSION}u;}}\n'
        f'extern "C" const char* xstar_api_version_string(void){{return "{SCIENCE_REVISION}";}}\n',encoding='utf-8')
    (tmp_path/'zone_stub.cpp').write_text(
        '#include <cstdint>\n'
        f'extern "C" std::int32_t xstar_production_zone_abi_version_v0648110(void){{return {zone_abi};}}\n',encoding='utf-8')
    subprocess.run([cxx,'-shared','-fPIC','-o',str(tmp_path/'libxstar_api.so'),str(tmp_path/'api_stub.cpp')],check=True)
    subprocess.run([cxx,'-shared','-fPIC','-o',str(tmp_path/'libxstar_production_zone.so'),str(tmp_path/'zone_stub.cpp')],check=True)
    exe=tmp_path/'xstar-cpp'
    proc=subprocess.run([
        cxx,'-std=c++17','-Wall','-Wextra','-Wpedantic','-O0',
        f'-DXSTAR_TOOLS_PACKAGE_VERSION="{package_version()}"',
        '-o',str(exe),str(FRONTEND),'-L',str(tmp_path),'-lxstar_api','-lxstar_production_zone',
        '-lstdc++fs','-Wl,-rpath,$ORIGIN',
    ],text=True,capture_output=True)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert 'warning:' not in proc.stdout+proc.stderr
    return exe


def test_milestone6_manifest_checker_accepts():
    proc=subprocess.run([sys.executable,str(ROOT/'tools/qualification/check_xstar_cpp_first_class.py')],cwd=ROOT,text=True,capture_output=True)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert 'XSTAR_CPP_FIRST_CLASS_RESULT=ACCEPT' in proc.stdout
    assert 'XSTAR_CPP_FIRST_CLASS_CORE_FILES=130' in proc.stdout
    assert 'XSTAR_CPP_FIRST_CLASS_FROZEN_FITS_PAIRS=186/186' in proc.stdout
    assert 'XSTAR_CPP_FIRST_CLASS_FROZEN_STEP_PAIRS=186/186' in proc.stdout


def test_frontend_accepts_par_data_output_and_structured_extensions(tmp_path):
    exe=_build_stub_frontend(tmp_path)
    sibling=tmp_path/'xstar_cpp'
    sibling.write_text(
        '#!/bin/sh\nout=.\nparams=\nwhile [ $# -gt 0 ]; do\n'
        ' case "$1" in --output-dir) out=$2; shift 2;; --parameters) params=$2; shift 2;; *) shift;; esac\n'
        'done\nmkdir -p "$out"\n'
        'printf "print option: 23\\nalpha\\nprint option: 24\\nrrc-one\\nrrc-two\\nprint option: 25\\nomega\\n" > "$out/xout_step.log"\n'
        'printf fake > "$out/xout_abund1.fits"\nexit 0\n',encoding='utf-8')
    sibling.chmod(0o755)
    data=tmp_path/'data'; data.mkdir(); (data/'atdb.fits').write_bytes(b'atdb'); (data/'coheat.dat').write_bytes(b'coheat')
    par=tmp_path/'xstar.par'
    par.write_text('spectrum,s,h,pow,,,spectrum\ncolumn,r,h,1.23456789E+22,0,,column\nmodelname,s,h,"test, model",,,model\n',encoding='utf-8')
    out=tmp_path/'run'; summary=tmp_path/'summary.json'; prov=tmp_path/'prov.json'; profile=tmp_path/'profile.json'
    proc=subprocess.run([
        str(exe),'--input',str(par),'--data-dir',str(data),'--output',str(out),
        '--json-summary',str(summary),'--provenance',str(prov),'--profile',str(profile),
        '--progress','json','--threads','2','--deterministic','--print-option','24',
    ],text=True,capture_output=True)
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert '"event":"run_started"' in proc.stdout
    assert '"event":"run_completed"' in proc.stdout
    assert 'print option: 24' in proc.stdout and 'rrc-two' in proc.stdout
    envelope=json.loads((out/'.xstar-cpp-parameters.json').read_text())
    assert envelope['column']=='1.23456789E+22'
    assert envelope['modelname']=='test, model'
    assert envelope['atomic_database']==str(data/'atdb.fits')
    assert envelope['coheat_file']==str(data/'coheat.dat')
    summary_data=json.loads(summary.read_text())
    assert summary_data['success'] is True and summary_data['package_version']=='0.6.69'
    assert summary_data['produced_fits']==['xout_abund1.fits']
    prov_data=json.loads(prov.read_text())
    assert prov_data['c_api_abi']==C_API_ABI_VERSION and prov_data['zone_abi']==ZONE_ABI_VERSION
    assert prov_data['threads']==2 and prov_data['deterministic_requested'] is True
    assert json.loads(profile.read_text())['scope']=='frontend-orchestration'


def test_frontend_fails_before_science_on_zone_abi_mismatch(tmp_path):
    exe=_build_stub_frontend(tmp_path,ZONE_ABI_VERSION-1)
    proc=subprocess.run([str(exe),'--abi'],text=True,capture_output=True)
    assert proc.returncode==70
    assert f'frontend expects {ZONE_ABI_VERSION}' in proc.stderr
    assert f'reports {ZONE_ABI_VERSION-1}' in proc.stderr


def test_makefile_links_frontend_to_runtime_abi_libraries():
    makefile=(CPP/'Makefile').read_text(encoding='utf-8')
    rule=makefile.split('$(PUBLIC_EXECUTABLE_TARGET):',1)[1].split('\n\n',1)[0]
    for token in ('$(API_TARGET)','$(PRODUCTION_ZONE_TARGET)','-lxstar_api','-lxstar_production_zone','$(RPATH_ORIGIN)'):
        assert token in rule


def test_all_three_native_modes_share_one_scientific_production_operator():
    source=(CPP/'xstar_standalone.cpp').read_text(encoding='utf-8')
    assert source.count('command_run_standalone_production_v67') >= 5
    assert 'xstar_production_zone_run_all_v0648110' in source
    assert 'xstar_production_zone_context_create_v0648110' in source
    assert 'if (options.command == "run-production") return command_run_standalone_production_v67' in source


def test_package_version_is_productization_only():
    assert package_version()=='0.6.69'
    assert SCIENCE_REVISION=='0.6.48.12.3.45.3.3.8'
    assert C_API_ABI_VERSION==60487
    assert ZONE_ABI_VERSION==6048110
