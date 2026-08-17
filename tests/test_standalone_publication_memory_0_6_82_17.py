from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys


def test_standalone_publication_memory_gate():
    root = Path(__file__).resolve().parents[1]
    p = subprocess.run(
        [sys.executable, str(root / "tools/qualification/check_standalone_publication_memory_0_6_82_17.py")],
        cwd=root, text=True, capture_output=True,
    )
    assert p.returncode == 0, p.stdout + p.stderr
    assert "STANDALONE_PUBLICATION_MEMORY_068217_RESULT=ACCEPT" in p.stdout
    assert "STANDALONE_PUBLICATION_MEMORY_068217_NTOTIT=DIAGNOSTIC_ONLY" in p.stdout


def test_ntotit_is_diagnostic_only_for_step_acceptance(tmp_path):
    root = Path(__file__).resolve().parents[1]
    runner = root / "tools/qualification/run_c5_wide_rlogxi_host_smoke_0_6_82_17.py"
    spec = importlib.util.spec_from_file_location("wide068217", runner)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    reference = tmp_path / "fortran.log"
    candidate = tmp_path / "cpp.log"
    # Same material row, intentionally different ntotit.  The already-percent
    # h-c fields are within the <1 percentage-point acceptance gate.
    reference.write_text(
        "   17.50 -10.70  18.80  -3.00   0.17  12.00   3.94   1.88   8.79   1.41 -10.00 26\n"
    )
    candidate.write_text(
        "   17.50 -10.70  18.80  -3.00   0.17  12.00   3.94   1.78   8.79   1.41 -10.00 23\n"
    )
    result = mod.compare_step(candidate, reference)
    assert result["structure_accept"] is True
    assert result["science_accept"] is True
    assert result["ntotit"]["mismatch_count"] == 1
    assert result["ntotit"]["diagnostic_accept_exact"] is False
