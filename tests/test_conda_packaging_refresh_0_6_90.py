from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_conda_packaging_refresh_source_gate_accepts() -> None:
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_conda_packaging_refresh_0_6_90.py", "--allow-unsealed-source"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CONDA_PACKAGING_REFRESH_0690_RESULT=ACCEPT" in proc.stdout


def test_conda_offline_science_smoke() -> None:
    proc = subprocess.run(
        [sys.executable, "conda/recipe/tests/offline_science_smoke.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "XSTAR_TOOLS_CONDA_OFFLINE_SCIENCE_SMOKE=ACCEPT" in proc.stdout
