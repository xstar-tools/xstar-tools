from pathlib import Path
from xstar_tools.xstar import v0472_all61_fixed_state_capture as capture


def test_v06487463_generated_probe_all_factory_blocks_retain_summary():
    assert capture.RELEASE == "0.6.48.7.46.9.5"
    report = capture._v0487463_probe_retention_report()
    assert report["factory_blocks"] >= 2
    assert report["summary_blocks"] == report["factory_blocks"]
    assert report["profile_copy_blocks"] == report["factory_blocks"]
    assert report["element_retention_blocks"] == report["factory_blocks"]
    assert report["diagnostic_retention_blocks"] == report["factory_blocks"]
    compile(capture._PROBE, "<v0487463-probe>", "exec")


def test_v06487463_normalizer_repairs_partial_probe():
    probe = """def a(current_state):
    previous_factory = None
    payload = {} if previous_factory is None else dict(previous_factory(current_state))
    payload["retain_element_results"] = True
    payload["retain_diagnostic_arrays"] = True
    return payload

def b(current_state):
    previous_factory = None
    payload = {} if previous_factory is None else dict(previous_factory(current_state))
    profile = dict(payload.get("profile_control") or {})
    profile["diagnostics_mode"] = "summary"
    payload["profile_control"] = profile
    payload["retain_element_results"] = True
    payload["retain_diagnostic_arrays"] = True
    return payload
"""
    fixed = capture._v0487463_force_summary_retention(probe)
    report = capture._v0487463_probe_retention_report(fixed)
    assert report == {
        "factory_blocks": 2,
        "summary_blocks": 2,
        "profile_copy_blocks": 2,
        "element_retention_blocks": 2,
        "diagnostic_retention_blocks": 2,
    }


def test_v06487463_hotfix_artifacts_present():
    root=Path(__file__).resolve().parents[1]
    for rel in [
      "run_v0487463_all61_post_seed_system_decomposition.sh",
      "check_v0487463_all61_post_seed_system_decomposition.py",
      "check_v0487463_all61_post_seed_system_decomposition_readiness.py",
      "V06487463_GENERATED_PROBE_RETENTION_CONTRACT_HOTFIX.md",
    ]:
        assert (root/rel).is_file(), rel
