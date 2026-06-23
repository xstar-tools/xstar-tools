from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "run_v048746226_helium_type53_controller_residual.sh"
READINESS = ROOT / "check_v048746226_helium_type53_controller_residual_readiness.py"


def test_default_runner_does_not_reuse_stale_v21_3_case():
    text = RUNNER.read_text()
    assert '$BASE13/native_case_all61' not in text
    assert 'native_case_v0487462262' in text


def test_runner_lowers_and_validates_current_case_before_replay():
    text = RUNNER.read_text()
    required = (
        "xstar_tools.xstar.native_fixed_program lower-atdb",
        "xstar_tools.xstar.type57_case_contract_v0487462201",
        "xstar_tools.xstar.type53_leveltemp_case_contract_v048746221",
        "xstar_tools.xstar.type49_leveltemp_case_contract_v048746222",
        "xstar_tools.xstar.type99_leveltemp_case_contract_v048746223",
        'mv "$CASE_TMP" "$CASE"',
    )
    for token in required:
        assert text.count(token) == 1, token


def test_same_verified_case_is_used_by_replay_and_controller():
    text = RUNNER.read_text()
    assert text.count('run_v048746226_native_fixed_replay.sh "$SOURCE_CAPTURE" "$CASE"') == 1
    assert text.count('XSTAR_V048746217_NATIVE_CASE_DIR="$CASE"') == 1
    assert text.count("v048746226_native_case_dir.txt") == 1


def test_readiness_fails_closed_on_stale_case_regression():
    text = READINESS.read_text()
    for key in (
        "runner_fresh_lower_atdb",
        "runner_type57_case_contract",
        "runner_stale_base13_case_removed",
        "runner_same_case_fixed_replay",
        "runner_same_case_controller",
    ):
        assert key in text
