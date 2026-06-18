from pathlib import Path
import xstar_tools

def root(): return Path(__file__).resolve().parents[1]
def test_release_and_native_api_version():
    assert xstar_tools.__version__=='0.6.48.7.46.11.1'
    assert 'XSTAR_API_VERSION_STRING "0.6.48.7.46.11.1"' in (root()/'src/xstar_tools/xstar/cpp/xstar_api.h').read_text()
def test_mg_bound_free_source_contract_and_fail_closed_guards():
    text=(root()/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    assert 'XSTAR_QUALIFICATION_MG_BOUND_FREE_FINITE_STATE' in text
    assert 'Mg Type-49 finite-state replacement remained nonfinite or implausibly large' in text
    assert 'Mg Type-53 finite-state replacement remained nonfinite or implausibly large' in text
    assert 'phextrap_pairs' in text
    assert 'kImplausibleBoundFreeRate' in text
def test_lowerer_carries_type49_and_type53_continuum_context():
    text=(root()/'src/xstar_tools/xstar/native_fixed_program.py').read_text()
    assert 'type49 record {rec} has no canonical continuum index' in text
    assert 'type53 record {rec} has no canonical continuum index' in text
    assert text.count('derived.npconi2[rec]')>=2
def test_evaluation_summary_uses_live_runtime_abi():
    text=(root()/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    assert 'live_runtime_state_abi' in text
    assert 'live_dsec_radiation_bins' in text
    assert 'live_continuum_tau_count' in text
def test_type50_orientation_is_deferred():
    text=(root()/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    block=text.split('case XSTAR_FIXED_OPCODE_TYPE50_RADIATIVE_LINE',1)[1].split('case XSTAR_FIXED_OPCODE_TYPE54_HYDROGENIC_DECAY',1)[0]
    assert 'MG_BOUND_FREE' not in block
    assert 'magnesium_finite_state' not in block
def test_runner_reuses_source_and_regenerates_native():
    text=(root()/'run_v04874693_mg_type49_type53_finite_state_and_regression_protection.sh').read_text()
    assert 'XSTAR_QUALIFICATION_MG_BOUND_FREE_FINITE_STATE=1' in text
    assert 'v0472_all61_post_seed_system_capture capture' not in text
    assert 'source_capture_replayed=false' in text
    assert 'native_replay_replayed=true' in text

def test_hydrogen_type53_observed_roundoff_is_strictly_ieee_equivalent():
    from xstar_tools.xstar import all61_dense_matrix_causal_attribution as causal
    pairs = [
        (1.7648023082206567e-08, 1.7648023082206564e-08, 1),
        (-1.7648023082206567e-08, -1.7648023082206564e-08, 1),
        (2.2096863507018874e-13, 2.2096863507018870e-13, 2),
        (1.1937722916711257e-09, 1.1937722916711255e-09, 1),
        (2.1881659622280428e-11, 2.1881659622280434e-11, 2),
        (8.9060683811322620e-11, 8.9060683811322590e-11, 2),
        (2.1881371018023603e-11, 2.1881371018023600e-11, 1),
    ]
    for source, native, expected_ulps in pairs:
        accepted, ulps, _absolute, relative = causal._binary64_ieee_equivalent(source, native)
        assert accepted
        assert ulps == expected_ulps
        assert relative <= 4.0e-16


def test_hydrogen_type53_tolerance_fails_closed():
    import math
    import numpy as np
    from xstar_tools.xstar import all61_dense_matrix_causal_attribution as causal

    three_ulps = 1.0
    for _ in range(3):
        three_ulps = float(np.nextafter(three_ulps, math.inf))
    assert not causal._binary64_ieee_equivalent(1.0, three_ulps)[0]
    assert not causal._binary64_ieee_equivalent(0.0, float(np.nextafter(0.0, 1.0)))[0]
    assert not causal._binary64_ieee_equivalent(1.0, -1.0)[0]
    assert not causal._binary64_ieee_equivalent(math.inf, math.inf * -1.0)[0]
    assert causal.hydrogen_type53_ieee_equivalence_self_test()["result"] == "ACCEPT"


def test_ieee_hotfix_runner_does_not_repeat_physics():
    text = (root() / 'run_v048746931_hydrogen_type53_ieee_equivalence_resume.sh').read_text()
    assert 'RESUME_ONLY_NO_SOURCE_OR_NATIVE_REPLAY=1' in text
    assert 'xstar_cpp run-fixed-evaluation' not in text
    assert 'native_fixed_program lower-atdb' not in text
    assert 'source_capture_replayed=false' in text
    assert 'native_replay_replayed=false' in text

def test_checker_accepts_observed_ieee_roundoff_envelope(tmp_path):
    import json
    import subprocess
    attribution = {
        'hydrogen_type53': {
            'result': 'ACCEPT',
            'records_expected': 1891,
            'contributions_exact': 1885,
            'contributions_ieee_equivalent': 1891,
            'roundoff_record_vectors': 6,
            'roundoff_real_fields': 9,
            'max_ulp_distance': 2,
            'max_relative_delta': 2.9533173658319817e-16,
            'phase_exact': {'call3': 143, 'call4': 136, 'final_call3': 8, 'final_call4': 8},
            'phase_ieee_equivalent': {'call3': 144, 'call4': 136, 'final_call3': 8, 'final_call4': 8},
            'phase_expected': {'call3': 144, 'call4': 136, 'final_call3': 8, 'final_call4': 8},
        },
        'gates': {'CANONICAL_RECORD_ALIGNMENT': 'ACCEPT'},
    }
    (tmp_path / 'all61_dense_matrix_causal_attribution_summary.json').write_text(json.dumps(attribution))
    (tmp_path / 'v04874693_mg_bound_free_finite_state_report.json').write_text(json.dumps({
        'result': 'ACCEPT', 'metrics': {'committed_nonfinite': 0, 'committed_implausible': 0}
    }))
    (tmp_path / 'v04874693_exact_system_regression_report.json').write_text(json.dumps({'result': 'ACCEPT'}))
    evaluations = tmp_path / 'native_all61' / 'evaluations'
    for sequence in range(1, 62):
        path = evaluations / f'evaluation_{sequence:04d}'
        path.mkdir(parents=True)
        (path / 'native_evaluation_summary.json').write_text(json.dumps({
            'dsec_runtime_state_abi': True,
            'dsec_radiation_bins': 9999,
            'continuum_tau_count': 301301,
        }))
    output = tmp_path / 'checker.json'
    completed = subprocess.run([
        'python', str(root() / 'check_v048746931_hydrogen_type53_ieee_equivalence.py'),
        '--audit-output', str(tmp_path), '--output-json', str(output)
    ], cwd=root(), capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads(output.read_text())
    assert report['result'] == 'ACCEPT'
    assert report['gates']['HYDROGEN_TYPE53_CONTRIBUTIONS_BIT_EXACT'] == 'REJECT'
    assert report['gates']['HYDROGEN_TYPE53_CONTRIBUTIONS_IEEE_EQUIVALENT'] == 'ACCEPT'
    assert report['gates']['V0648746931_HYDROGEN_TYPE53_IEEE_EQUIVALENCE_HOTFIX'] == 'ACCEPT'
