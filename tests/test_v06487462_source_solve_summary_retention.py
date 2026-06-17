from pathlib import Path
from xstar_tools.xstar import v0472_all61_fixed_state_capture as capture

def test_v06487462_generated_probe_forces_summary_on_copied_profile():
    assert capture.RELEASE == "0.6.48.7.46.9.4.1"
    assert capture._PROBE.count('payload = {} if previous_factory is None else dict(previous_factory(current_state))') >= 2
    assert capture._PROBE.count('profile["diagnostics_mode"] = "summary"') >= 2
    assert capture._PROBE.count('payload["profile_control"] = profile') >= 2
    compile(capture._PROBE, "<v0487462-probe>", "exec")

def test_v06487462_hotfix_artifacts_present():
    root=Path(__file__).resolve().parents[1]
    for rel in [
      "run_v0487462_all61_post_seed_system_decomposition.sh",
      "check_v0487462_all61_post_seed_system_decomposition.py",
      "check_v0487462_all61_post_seed_system_decomposition_readiness.py",
      "V06487462_SOURCE_SOLVE_SUMMARY_RETENTION_HOTFIX.md",
    ]:
        assert (root/rel).is_file(), rel
