from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_example_history_cleanup_gate() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/qualification/check_example_history_cleanup.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "EXAMPLE_HISTORY_CLEANUP_RESULT=ACCEPT" in proc.stdout
