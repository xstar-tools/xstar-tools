from pathlib import Path


def test_two_state_promotion_sources_present():
    root = Path(__file__).resolve().parents[1]
    fixed = (root / 'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    standalone = (root / 'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    assert 'XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION' in fixed
    assert '--controller-smoke-evaluations' in standalone
    assert 'runtime_state_workspace_evaluations' in standalone


def test_embedded_evaluation60_workspace_present():
    root = Path(__file__).resolve().parents[1]
    bundle = root / 'src/xstar_tools/benchmarks/v0648719_type53_two_state_promotion/evaluation60'
    assert (bundle / 'type53_independent_state_runtime_records.csv').is_file()
    assert (bundle / 'type53_independent_state_runtime_matrix_terms.csv').is_file()
    assert (bundle / 'dsec_radiation_workspace.csv').is_file()
    assert (bundle / 'dsec_continuum_tau_workspace.csv').is_file()
