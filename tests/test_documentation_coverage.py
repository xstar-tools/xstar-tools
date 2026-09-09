from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_documentation_coverage_gate() -> None:
    proc = subprocess.run(
        [sys.executable, "-B", str(ROOT / "tools/qualification/check_documentation_coverage.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DOCUMENTATION_COVERAGE_RESULT=ACCEPT" in proc.stdout
