from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_physical_callback_does_not_precommit_temperature():
    standalone = (ROOT / 'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    thermal = (ROOT / 'src/xstar_tools/xstar/cpp/thermal_kernels.cpp').read_text()
    assert 'evaluation->temperature_t4 = trial_state->temperature_t4;' in standalone
    assert 'committed_temperature_k = input.temperature_k' not in standalone
    assert 'state->temperature_t4 = source_temperature_commit_t4(result.temperature_t4);' in thermal


def test_secant_self_test_reports_single_commit_owner():
    exe = ROOT / 'src/xstar_tools/xstar/cpp/xstar_cpp'
    if not exe.is_file():
        return
    out = subprocess.check_output(
        [str(exe), 'secant-ieee-self-test', '--backend', 'cpp', '--plugin-dir', str(exe.parent)],
        text=True,
    )
    assert 'temperature_rows_ieee_exact=21' in out
    assert 'physical_callback_precommit=false' in out
    assert 'single_commit_owner=thermal_controller' in out
    assert 'RESULT=ACCEPT' in out
