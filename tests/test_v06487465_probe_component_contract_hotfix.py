from xstar_tools import __version__
from xstar_tools.xstar import v0472_all61_fixed_state_capture as capture


def test_v0487465_component_release_and_probe_contract():
    assert __version__ == "0.6.48.7.46.9.4.1"
    assert capture.RELEASE == "0.6.48.7.46.9.4.1"
    report = capture._v0487465_probe_retention_report()
    assert report["factory_blocks"] >= 2
    for key in (
        "profile_copy_blocks", "summary_blocks",
        "element_retention_blocks", "diagnostic_retention_blocks",
    ):
        assert report[key] == report["factory_blocks"]
    compile(capture._PROBE, "<v0487465-test-probe>", "exec")
