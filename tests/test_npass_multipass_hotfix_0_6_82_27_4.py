from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CPP=ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'
FITS=ROOT/'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp'
PY=ROOT/'src/xstar_tools/xstar/radial_transfer.py'
OUTPY=ROOT/'src/xstar_tools/xstar/output_writers.py'
PPRINT=ROOT/'src/xstar_tools/xstar/pprint_legacy.py'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_4.py'
MAN=ROOT/'qualification/npass_0_6_82_27_4/npass_hotfix_source_scope_0_6_82_27_4.json'

def runner():
    spec=importlib.util.spec_from_file_location('npass0274_runner',RUNNER); assert spec and spec.loader
    m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m); return m

def test_0682274_version_abis_and_scope():
    assert any(f'version = "{v}"' in (ROOT/'pyproject.toml').read_text() for v in ('0.6.82.27.4','0.6.82.27.5','0.6.82.27.6','0.6.82.27.7','0.6.82.27.8','0.6.82.27.9','0.6.82.27.10','0.6.82.27.12','0.6.82.27.13'))
    assert any(f'PACKAGE_VERSION ?= {v}' in (ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text() for v in ('0.6.82.27.4','0.6.82.27.5','0.6.82.27.6','0.6.82.27.7','0.6.82.27.8','0.6.82.27.9','0.6.82.27.10','0.6.82.27.12','0.6.82.27.13'))
    obj=json.loads(MAN.read_text()); assert obj['science_revision']=='0.6.48.12.3.45.3.3.8'
    assert obj['c_api_abi']==60487 and obj['production_zone_abi']==6048110 and obj['fixed_state_abi']==60488
    assert obj['numerical_source_count_predecessor']==137 and len(obj['intentional_numerical_source_changes'])==5

def test_0682274_init_zero_only_no_dead_one_over_z_seed():
    c=CPP.read_text(); b=c[c.index('void source_init_repeated_global_workspaces_v0682274'):c.index('void restore_saved_shell_v068227')]
    assert 'std::fill(data.global_xilevg.begin(), data.global_xilevg.end(), 0.0)' in b
    assert '1.0 / static_cast<double>' not in b and 'global_rnisg' not in b and 'global_bilevg' not in b
    p=PY.read_text(); b=p[p.index('def initialize_bounded_radial_pass_state'):p.index('def apply_stpcut_to_state')]
    assert 'np.zeros_like' in b and '1.0 / float(z)' not in b

def test_0682274_even_pass_runs_fresh_fixed_state_before_stpcut():
    c=CPP.read_text(); assert 'source_nlimdt_v068227 == 0' in c
    assert 'evaluate_full_boundary(data, state, 0.0, boundary_radius_cm, 0u)' in c
    assert 'V0682274_EVEN_XSTARCALC_PASS=' in c and 'OPLIN_NONZERO=' in c and 'OPAKAB_NONZERO=' in c

def test_0682274_full_sparse_unsavd_workspaces_are_modeled():
    c=CPP.read_text()
    for t in ('unsavd_rcem_v0682274','unsavd_oplin_v0682274','unsavd_cemab_v0682274','unsavd_cabab_v0682274',
              'unsavd_opakab_v0682274','unsavd_opakc_v0682274','unsavd_rccemis_v0682274'):
        assert t in c
    p=PY.read_text()
    for t in ('result.rcem_after','result.oplin_after','result.cemab_after','result.cabab_after','result.opakab_after','result.opakc_after','result.rccemis_after'):
        assert t in p

def test_0682274_terminal_savd_refreshes_after_final_stpcut_state():
    c=CPP.read_text(); b=c[c.index('terminal_saved_boundary_v0682274'):c.index('V0682274_TERMINAL_SAVD_PASS=')]
    if ('version = "0.6.82.27.10"' in (ROOT/'pyproject.toml').read_text() or 'version = "0.6.82.27.12"' in (ROOT/'pyproject.toml').read_text() or 'version = "0.6.82.27.13"' in (ROOT/'pyproject.toml').read_text()):
        # .27.10 fixes the producer: terminal_transport_boundary is already
        # post-STPCUT, so a second pre-STPCUT refresh is both redundant and stale.
        assert 'retain_pre_stpcut_cumulative_state' not in b
        assert 'make_saved_shell_v068227' in b
    else:
        assert b.index('retain_pre_stpcut_cumulative_state') < b.index('make_saved_shell_v068227')

def test_0682274_pass_source_order_scalar_and_lbol_scientific():
    c=CPP.read_text(); loop=c[c.index('for (std::size_t kk_v068227 = 1u;'):]
    assert loop.index('advance_source_powerlaw_pass_v0682274') < loop.index('initialize_native_radial_pass_v068227') < loop.index('restore_saved_shell_v068227')
    assert 'data.source_incident[i] = data.source_incident[i] + component[i]' in c
    assert 'data.source_incident[i] = data.source_incident[i] * scale' in c
    assert 'std::scientific << std::setprecision(16)' in (ROOT/'src/xstar_tools/xstar/cpp/xstar_step_log.cpp').read_text()
    p=PY.read_text(); assert 'def _repeat_source_powerlaw_pass_v0682274' in p
    assert 'next_source[i] = float(next_source[i]) + float(raw[i]) * scale1' in p
    assert 'ispcg2_passes_v0682274' in PPRINT.read_text()

def test_0682274_rrc_709_762_removed_only_from_detail_inventory():
    c=FITS.read_text(); assert 'detail_inventory && (id.continuum_index == 709 || id.continuum_index == 762)' in c
    p=OUTPY.read_text(); assert 'int(item.continuum_index) in {709, 762}' in p

def test_0682274_pass_detail_writes_use_actual_savd_not_final_bridge():
    c=FITS.read_text(); assert '.source_savd_no_bridge_v0682274' in c
    assert 'final_retained_product_arrays_v0682274' in c

def test_0682274_runner_checks_every_pass_detail_surface(monkeypatch):
    m=runner(); calls=[]
    def fake(path, reference, *, kind='line'):
        calls.append((path.name,kind)); return {'accept':True,'worst_relative':0.0,'errors':[]}
    monkeypatch.setattr(m,'compare_detail_tau',fake)
    monkeypatch.setattr(Path,'is_file',lambda self: True)
    monkeypatch.setattr(Path,'stat',lambda self: type('S',(),{'st_size':1})())
    out=m.compare_all_pass_detail_tau(Path('c'),Path('r'),3)
    assert out['accept'] and len(calls)==9

def test_0682274_runner_marker_and_scientific_parser(tmp_path):
    text=RUNNER.read_text(); assert 'EXPECTED_VERSION = "0.6.82.27.4"' in text
    assert 'C5_NPASS_MULTIPASS_0682274_{b.upper()}_RESULT' in text
    m=runner(); p=tmp_path/'xout_step.log'; p.write_text(' U(1-1.8),U(1.8-4): 1.0e0 2.0e0\n Lbol=   2.3400564756336129e-06\n')
    assert m.parse_ispcg2_blocks(p)==[(1.0,2.0,2.3400564756336129e-06)]
