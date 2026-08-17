from __future__ import annotations

import importlib.util
import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SAVED = ROOT / 'src/xstar_tools/xstar/saved_radial_state.py'
RUNNER = ROOT / 'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_14.py'
MAN = ROOT / 'qualification/npass_0_6_82_27_14/npass_hotfix_source_scope_0_6_82_27_14.json'


def runner():
    spec = importlib.util.spec_from_file_location('npass02714_runner', RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def source_roundtrip(value: float) -> float:
    r4 = struct.unpack('=f', struct.pack('=f', value))[0]
    return struct.unpack('=f', struct.pack('=f', float(f'{r4:.3E}')))[0]


def load_saved_module():
    sys.path.insert(0, str(ROOT / 'src'))
    try:
        from xstar_tools.xstar import saved_radial_state as mod
        return mod
    finally:
        sys.path.pop(0)


def test_06822714_version_scope_and_protected_cpp_baseline():
    py = (ROOT / 'pyproject.toml').read_text()
    mk = (ROOT / 'src/xstar_tools/xstar/cpp/Makefile').read_text()
    assert any(f'version = "{v}"' in py for v in ('0.6.82.27.14','0.6.82.27.15','0.6.82.27.16'))
    assert any(f'PACKAGE_VERSION ?= {v}' in mk for v in ('0.6.82.27.14','0.6.82.27.15','0.6.82.27.16'))
    o = json.loads(MAN.read_text())
    assert o['predecessor'] == '0.6.82.27.13'
    assert o['protected_cpp_baseline'] == '0.6.82.27.13'
    assert o['intentional_numerical_source_changes'] == ['src/xstar_tools/xstar/saved_radial_state.py']
    assert (o['science_revision'], o['c_api_abi'], o['production_zone_abi'], o['fixed_state_abi']) == (
        '0.6.48.12.3.45.3.3.8', 60487, 6048110, 60488
    )


def test_06822714_python_savd_scalar_e3_roundtrip_matches_cpp_fortran_values():
    mod = load_saved_module()
    assert mod._savd_keyword_e3_real4_scalar(1.2017343044281006) == 1.2020000219345093
    assert mod._savd_keyword_e3_real4_scalar(4.6960086822509766) == 4.696000099182129
    assert mod._savd_keyword_e3_real4_scalar(316227780608.0) == 316199993344.0
    for value in (0.03, 1.0e8, 0.0, -1.0):
        assert mod._savd_keyword_e3_real4_scalar(value) == source_roundtrip(value)


def test_06822714_snapshot_uses_e3_for_all_nine_scalars_but_plain_real4_for_arrays():
    text = SAVED.read_text()
    fields = (
        'temperature', 'pressure', 'radius', 'radial_depth', 'step_size',
        'column', 'electron_fraction', 'hydrogen_density', 'zeta',
    )
    for field in fields:
        assert f'{field}=_savd_keyword_e3_real4_scalar({field}),' in text
    for field in ('xilev','rnist','rcem','oplin','tau0','cemab','cabab','opakab','tauc','elumab'):
        assert f'{field}=_real4_array(' in text


def test_06822714_snapshot_numeric_contract_is_e3_only_for_scalars():
    mod = load_saved_module()
    snap = mod.make_saved_shell_snapshot(
        pass_index=3,
        zone_index=1,
        terminal_record=False,
        temperature=4.6960086822509766,
        pressure=0.03,
        radius=316227780608.0,
        radial_depth=0.0,
        step_size=1.0e11,
        column=1.0e19,
        electron_fraction=1.2017343044281006,
        hydrogen_density=1.0e8,
        zeta=1.23456,
        xilev=[1.23456789],
        rnist=[2.34567891],
        rcem=[[3.45678912], [4.56789123]],
        oplin=[5.67891234],
        tau0=[[6.78912345], [7.89123456]],
        cemab=[[8.91234567], [9.12345678]],
        cabab=[1.23456789e-3],
        opakab=[2.34567891e-4],
        tauc=[[3.45678912e-5], [4.56789123e-6]],
        elumab=[[5.67891234e-7], [6.78912345e-8]],
        zrems=np.ones((5, 4)),
        dpthc=np.ones((2, 4)) * 2.0,
        dpthcont=np.ones((2, 4)) * 3.0,
        zremsz=np.ones(4) * 4.0,
        opakc=np.ones(4) * 5.0,
        rccemis=np.ones((2, 4)) * 6.0,
        ncn2=4,
    )
    assert snap.temperature == 4.696000099182129
    assert snap.electron_fraction == 1.2020000219345093
    assert snap.radius == 316199993344.0
    assert snap.xilev[0] == float(np.float32(1.23456789))
    assert snap.xilev[0] != mod._savd_keyword_e3_real4_scalar(1.23456789)


def test_06822714_runner_targets_pure_python_and_retains_all_four_npass_stages():
    mod = runner()
    assert mod.EXPECTED_VERSION == '0.6.82.27.14'
    assert mod.REL_LIMIT == 0.01
    text = RUNNER.read_text()
    assert '"--mode", "pure-python"' in text
    assert 'compare_savd_scalar_keywords_file' in text
    assert 'compare_rrc_workspace_all_passes' in text
    assert 'stage1 =' in text and 'stage2 =' in text and 'stage3 =' in text and 'stage4 =' in text
