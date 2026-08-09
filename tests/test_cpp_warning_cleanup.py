from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_cpp_warning_cleanup_gate_accepts() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/qualification/check_cpp_warning_cleanup.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CPP_WARNING_CLEANUP_RESULT=ACCEPT" in proc.stdout
    assert "CPP_WARNING_CLEANUP_WARNING_COUNT=0" in proc.stdout


def test_cpp_warning_cleanup_manifest_is_behavior_neutral() -> None:
    data = json.loads((ROOT / "qualification/cpp_warning_cleanup_0_6_58.json").read_text())
    assert data["productization_version"] == "0.6.58"
    assert data["production_zone_abi"] == 6048110
    assert len(data["files"]) == 6
    assert all(item["behavior_change"] is False for item in data["files"].values())
    assert data["build_verification"]["warning_count"] == 0
