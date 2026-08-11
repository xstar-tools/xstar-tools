from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/qualification/check_type63_source_cutoff_0_6_82_7.py"


def test_type63_source_cutoff_checker_accepts():
    proc = subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "TYPE63_SOURCE_CUTOFF_06827_RESULT=ACCEPT" in proc.stdout
    assert "TYPE63_SOURCE_CUTOFF_06827_FORTRAN_ZERO_RECORDS_XI1P2=16" in proc.stdout
    assert "TYPE63_SOURCE_CUTOFF_06827_TERMINAL_STEP=FROZEN_06826" in proc.stdout
