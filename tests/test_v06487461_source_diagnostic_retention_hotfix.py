from pathlib import Path
from xstar_tools.xstar import v0472_all61_fixed_state_capture as capture

def test_release_and_unconditional_retention_wrapper():
    assert capture.RELEASE == "0.6.48.7.46.9.2"
    assert capture._PROBE.count('payload = {} if previous_factory is None else dict(previous_factory(current_state))') >= 2
    assert 'if previous_factory is not None:\n                def retained_factory' not in capture._PROBE

def test_hotfix_artifacts_present():
    root=Path(__file__).resolve().parents[1]
    for rel in [
        "run_v0487461_all61_post_seed_system_decomposition.sh",
        "check_v0487461_all61_post_seed_system_decomposition.py",
        "check_v0487461_all61_post_seed_system_decomposition_readiness.py",
        "V06487461_SOURCE_DIAGNOSTIC_RETENTION_HOTFIX.md",
    ]:
        assert (root/rel).is_file(), rel
