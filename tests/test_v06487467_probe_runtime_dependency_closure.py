from __future__ import annotations

from xstar_tools.xstar import v0472_all61_post_seed_system_capture as capture


def test_injected_capture_block_is_runtime_self_contained() -> None:
    assert capture.RELEASE == "0.6.48.7.46.9.4.1"
    assert "from pathlib import Path as _v048746_Path" in capture._SYSTEM_CAPTURE_CODE
    assert "import numpy as _v048746_np" in capture._SYSTEM_CAPTURE_CODE
    assert "import csv as _v048746_csv" in capture._SYSTEM_CAPTURE_CODE
    assert 'relative = _v048746_Path("v0472_all61_solve_systems")' in capture._SYSTEM_CAPTURE_CODE
    compile(capture._PROBE, "<v0487467-probe>", "exec")


def test_injected_capture_block_executes_and_writes_all_arrays() -> None:
    report = capture.probe_capture_behavioral_self_test()
    assert report["result"] == "ACCEPT", report
    assert report["systems"] == 3
    assert report["binary_arrays"] == 30
