from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCI=ROOT/'src/xstar_tools/xstar/cpp/xstar_science_fits.cpp'
STAND=ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_13.py'
MAN=ROOT/'qualification/npass_0_6_82_27_13/npass_hotfix_source_scope_0_6_82_27_13.json'

def runner():
    s=importlib.util.spec_from_file_location('npass02713_runner',RUNNER); assert s and s.loader
    m=importlib.util.module_from_spec(s); sys.modules[s.name]=m; s.loader.exec_module(m); return m

def test_version_scope_and_frozen_ids():
    assert any(f'version = "{v}"' in (ROOT/'pyproject.toml').read_text() for v in ('0.6.82.27.13','0.6.82.27.14','0.6.82.27.15'))
    o=json.loads(MAN.read_text())
    assert o['predecessor']=='0.6.82.27.12'
    assert o['intentional_numerical_source_changes']==['src/xstar_tools/xstar/cpp/xstar_science_fits.cpp']
    assert (o['science_revision'],o['c_api_abi'],o['production_zone_abi'],o['fixed_state_abi'])==('0.6.48.12.3.45.3.3.8',60487,6048110,60488)

def test_tauc_native_planes_are_repacked_independently():
    c=SCI.read_text()
    a=c.index('std::vector<double> resize_native_tauc_for_serialized_bridge_v06822713(')
    b=c.index('// XSTAR-FUNCTION-COMMENT-BEGIN',a+1)
    h=c[a:b]
    assert 'const std::size_t native_stride = native_continuum_count + 1u;' in h
    assert 'const std::size_t serialized_stride = expected_count / 2u;' in h
    assert 'values.begin() + static_cast<std::ptrdiff_t>(native_stride)' in h
    assert 'out.begin() + static_cast<std::ptrdiff_t>(serialized_stride)' in h

def test_only_tauc_uses_new_native_stride_repack():
    c=SCI.read_text()
    assert 'if (name == "tauc") {' in c
    assert 'resize_native_tauc_for_serialized_bridge_v06822713' in c
    assert 'if (name == "elumab") return resize_native_array(ws.elumab, expected_count);' in c
    assert 'if (name == "cemab") return resize_native_array(ws.cemab, expected_count);' in c

def test_2712_writer_ownership_is_preserved():
    c=SCI.read_text()
    assert 'merged_line_row(r, &found_diag->second)' in c
    a=c.index('RrcRow merged_rrc_row('); b=c.index('// XSTAR-FUNCTION-COMMENT-BEGIN',a+1); m=c[a:b]
    assert 'out.tau_in = diagnostic->tau_in' not in m
    assert 'out.tau_out = diagnostic->tau_out' not in m
    assert 'source_slot_v06822710' in c and 'state.source_rrc_identities' in c

def test_protected_standalone_semantics_are_untouched():
    s=STAND.read_text()
    assert 'const std::size_t plane = radial_direction > 0 ? 0u : 1u;' in s
    assert 'Persist this post-STPCUT owner directly' in s
    assert 'final_writer_unsmoothed_opakc_v0682278' in s
    assert 'reproject_repeated_pass_source_workspace_v06822711' not in s

def test_runner_requires_rrc_raw_under_one_percent():
    m=runner()
    assert m.REL_LIMIT == 0.01
    c=RUNNER.read_text()
    assert 'compare_rrc_workspace_all_passes' in c
    assert 'stage4 = bool(stage3 and rrc_tau.get("accept") and rrc_workspace.get("accept"))' in c
