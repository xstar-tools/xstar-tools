from pathlib import Path
from xstar_tools.xstar.v0472_call2_helium_solve_state_capture import RELEASE as CAPTURE_RELEASE, _PROBE
from xstar_tools.xstar.call2_helium_solve_state_rate_matrix_decomposition import RELEASE

def test_release_and_probe_scope():
    assert RELEASE == '0.6.48.7.31.3'
    assert CAPTURE_RELEASE == '0.6.48.7.31.3'
    assert 'v048731_he_solve_capture_enable call=' in _PROBE
    assert 'capture_lucy_trace_element_z = (2,)' in _PROBE
    assert 'v0472_call2_eval1_he_solve_matrix.csv' in _PROBE
    assert 'v0472_call2_eval1_he_source_order_matrix_terms.csv' in _PROBE

def test_runner_requires_fresh_source_and_native_replay():
    text=Path('run_v048731_call2_helium_solve_state_rate_matrix_decomposition.sh').read_text()
    assert 'v0472_call2_helium_solve_state_capture' in text
    assert 'native_fixed_program lower-atdb' in text
    assert 'XSTAR_QUALIFICATION_SOLVE_RESPONSE=1' in text
    assert 'call2_helium_solve_state_rate_matrix_decomposition' in text
