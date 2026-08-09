from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_test_history_cleanup_gate_accepts() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/qualification/check_test_history_cleanup.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "TEST_HISTORY_CLEANUP_RESULT=ACCEPT" in proc.stdout
    assert "TEST_HISTORY_CLEANUP_ARCHIVED_XSTAR_ATOMIC_TESTS=155" in proc.stdout
    assert "TEST_HISTORY_CLEANUP_ARCHIVED_PARITY_ARTIFACT_TESTS=18" in proc.stdout
    assert "TEST_HISTORY_CLEANUP_ARCHIVED_SUPERSEDED_REGRESSION_TESTS=16" in proc.stdout
    assert "TEST_HISTORY_CLEANUP_ARCHIVED_UNUSED_FIXTURE_FILES=8" in proc.stdout
    assert "TEST_HISTORY_CLEANUP_ARCHIVED_TESTS_TOTAL=189" in proc.stdout


def test_active_tests_do_not_name_retired_namespace() -> None:
    offenders = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        if "xstar_atomic" in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(path.name)
    assert offenders == []
