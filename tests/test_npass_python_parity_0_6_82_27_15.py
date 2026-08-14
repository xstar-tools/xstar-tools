from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RADIAL = ROOT / 'src/xstar_tools/xstar/radial_transfer.py'
RUNNER = ROOT / 'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_15.py'
MAN = ROOT / 'qualification/npass_0_6_82_27_15/npass_hotfix_source_scope_0_6_82_27_15.json'


def runner():
    spec = importlib.util.spec_from_file_location('npass02715_runner', RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def helper_namespace():
    tree = ast.parse(RADIAL.read_text())
    wanted = {
        '_source_global_level_capacity_v06822715',
        '_dense_level_array_v06822715',
        '_guard_level_array_v06822715',
    }
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    assert {node.name for node in funcs} == wanted
    module = ast.Module(body=funcs, type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {'np': np, 'XSTARPythonState': object}
    exec(compile(module, str(RADIAL), 'exec'), ns)
    return ns


def fake_state(capacity: int = 4):
    derived = SimpleNamespace(
        n_level_records=capacity,
        npilev=np.asarray([[0, 0], [0, capacity]], dtype=np.int64),
    )
    return SimpleNamespace(atomic=SimpleNamespace(derived=derived), control={})


def test_06822715_version_scope_and_protected_cpp_baseline():
    py = (ROOT / 'pyproject.toml').read_text()
    mk = (ROOT / 'src/xstar_tools/xstar/cpp/Makefile').read_text()
    assert any(f'version = "{v}"' in py for v in ('0.6.82.27.15','0.6.82.27.16'))
    assert any(f'PACKAGE_VERSION ?= {v}' in mk for v in ('0.6.82.27.15','0.6.82.27.16'))
    o = json.loads(MAN.read_text())
    assert o['predecessor'] == '0.6.82.27.14'
    assert o['protected_cpp_baseline'] == '0.6.82.27.13'
    assert o['intentional_numerical_source_changes'] == ['src/xstar_tools/xstar/radial_transfer.py']
    assert (o['science_revision'], o['c_api_abi'], o['production_zone_abi'], o['fixed_state_abi']) == (
        '0.6.48.12.3.45.3.3.8', 60487, 6048110, 60488
    )


def test_06822715_guarded_source_to_dense_runtime_roundtrip():
    ns = helper_namespace()
    state = fake_state(4)
    guarded = np.asarray([0.0, 10.0, 20.0, 30.0, 40.0])
    dense = ns['_dense_level_array_v06822715'](state, guarded)
    assert np.array_equal(dense, [10.0, 20.0, 30.0, 40.0])
    assert np.array_equal(ns['_guard_level_array_v06822715'](state, dense), guarded)
    # Dense DSEC vectors are not accidentally stripped.
    assert np.array_equal(ns['_dense_level_array_v06822715'](state, dense), dense)


def test_06822715_sparse_savd_one_based_indices_select_correct_physical_levels():
    ns = helper_namespace()
    state = fake_state(4)
    guarded = np.asarray([0.0, 10.0, 20.0, 30.0, 40.0])
    dense = ns['_dense_level_array_v06822715'](state, guarded)
    level_indices_one_based = np.asarray([1, 3, 4], dtype=np.int64)
    saved = dense[level_indices_one_based - 1]
    assert np.array_equal(saved, [10.0, 30.0, 40.0])
    # This is the .27.14 failure mode: guarded[N-1] saved the prior level.
    assert np.array_equal(guarded[level_indices_one_based - 1], [0.0, 20.0, 30.0])


def test_06822715_unsavd_public_state_is_reguarded_but_dsec_runtime_stays_dense():
    text = RADIAL.read_text()
    apply = text[text.index('def apply_unsavd_to_state'):text.index('def _repeat_source_powerlaw_pass_v0682274')]
    assert 'guarded_xilev = _guard_level_array_v06822715(state, result.xilev_after)' in apply
    assert 'guarded_rnist = _guard_level_array_v06822715(state, result.rnist_after)' in apply
    assert 'state.local_zone.source_arrays["xilevg"] = guarded_xilev' in apply
    assert 'state.local_zone.source_arrays["rnisg"] = guarded_rnist' in apply
    assert 'physical_runtime.global_xilevg_by_index = np.asarray(\n                result.xilev_after, dtype=float\n            ).copy()' in apply
    assert 'physical_runtime.global_rnisg_by_index = np.asarray(\n                result.rnist_after, dtype=float\n            ).copy()' in apply


def test_06822715_repeated_pass_init_preserves_dense_dsec_layout():
    text = RADIAL.read_text()
    block = text[text.index('def initialize_bounded_radial_pass_state'):text.index('def apply_stpcut_to_state')]
    assert 'physical_runtime.global_xilevg_by_index = zero.copy()' not in block
    assert 'physical_runtime.global_xilevg_by_index = np.zeros_like(' in block
    assert 'prior_dense = getattr(physical_runtime, "global_xilevg_by_index", None)' in block


def test_06822715_inherits_02714_e3_scalar_persistence_without_new_saved_state_change():
    o = json.loads(MAN.read_text())
    saved = ROOT / 'src/xstar_tools/xstar/saved_radial_state.py'
    assert '_savd_keyword_e3_real4_scalar' in saved.read_text()
    assert o['predecessor_sha256']['src/xstar_tools/xstar/saved_radial_state.py'] == '69c4c29ca807d4ad41796849ea4316d9e9d2a5a3c8c291062e0fdacf1a9a86f1'


def test_06822715_runner_targets_pure_python_npass3_first():
    mod = runner()
    assert mod.EXPECTED_VERSION == '0.6.82.27.15'
    assert mod.REL_LIMIT == 0.01
    text = RUNNER.read_text()
    assert '"--mode", "pure-python"' in text
    assert 'compare_savd_scalar_keywords_file' in text
    assert 'compare_rrc_workspace_all_passes' in text
    assert 'stage1 =' in text and 'stage2 =' in text and 'stage3 =' in text and 'stage4 =' in text
