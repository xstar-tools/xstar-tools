from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_source_root_history_cleanup_gate() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/qualification/check_source_root_history_cleanup.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SOURCE_ROOT_HISTORY_CLEANUP_RESULT=ACCEPT" in proc.stdout


def test_generated_o7_density_grid_directory_is_absent() -> None:
    assert not (ROOT / "o7_solver_source_fit_density_xstar_grid").exists()
