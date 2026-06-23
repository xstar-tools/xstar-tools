from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "run_v048746226_native_fixed_replay.sh"
CONTROLLER = ROOT / "run_v048746217_canonical_thermal_controller_parity.sh"

PROMOTED_FLAGS = (
    "XSTAR_QUALIFICATION_TYPE57_SOURCE_ENERGY=1",
    "XSTAR_QUALIFICATION_TYPE68_SOURCE_CONSTANTS=1",
    "XSTAR_QUALIFICATION_MAGNESIUM_TYPE53_PERSISTENT_LEVELTEMP=1",
    "XSTAR_QUALIFICATION_MAGNESIUM_TYPE49_PERSISTENT_LEVELTEMP=1",
    "XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PERSISTENT_LEVELTEMP=1",
)

def test_hotfix_release_version():
    assert 'version = "0.6.48.7.46.21.16.2"' in (ROOT / "pyproject.toml").read_text()
    assert '__version__ = "0.6.48.7.46.21.16.2"' in (ROOT / "src/xstar_tools/__init__.py").read_text()

def test_fixed_replay_restores_all_promoted_runtime_flags_once():
    text = REPLAY.read_text()
    for flag in PROMOTED_FLAGS:
        assert text.count(flag) == 1, flag

def test_controller_and_fixed_replay_share_promoted_runtime_contract():
    replay = REPLAY.read_text()
    controller = CONTROLLER.read_text()
    for flag in PROMOTED_FLAGS:
        assert flag in replay, flag
        assert flag in controller, flag

def test_type57_guard_cannot_pass_readiness_without_replay_flag():
    checker = (ROOT / "check_v048746226_helium_type53_controller_residual_readiness.py").read_text()
    assert 'replay_type57_source_energy' in checker
    assert 'contract["replay_type57_source_energy"]==1' in checker
