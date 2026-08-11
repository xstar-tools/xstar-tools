from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/qualification/check_lte_rnisi_workspace_0_6_82_8.py"
CPP = ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp"


def test_lte_rnisi_workspace_checker_accepts() -> None:
    proc = subprocess.run([sys.executable, str(CHECKER)], cwd=ROOT, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "LTE_RNISI_WORKSPACE_06828_RESULT=ACCEPT" in proc.stdout
    assert "LTE_RNISI_WORKSPACE_06828_SOURCE_ND=20000" in proc.stdout
    assert "LTE_RNISI_WORKSPACE_06828_TRIGGER=Z6_ACTIVE_1_4_NLEV26_FINAL33" in proc.stdout


def test_rnisi_is_context_persistent_and_not_per_ion_resized() -> None:
    text = CPP.read_text(encoding="utf-8")
    assert "source_levwk_rnisi_workspace_v06828{};" in text
    start = text.index("std::vector<double> compute_element_lte_populations(")
    end = text.index("std::vector<double> compute_exact_lte_populations(", start)
    block = text[start:end]
    assert "rnisi.assign(" not in block
    assert "rnisi.clear(" not in block
    assert "rnisi[static_cast<std::size_t>(nlev)] = 1.0;" in block
    assert "rnisi.size() <= static_cast<std::size_t>(last_nlev)" not in block


def test_context_reset_restarts_fortran_static_workspace_state() -> None:
    text = CPP.read_text(encoding="utf-8")
    reset = text.index("int xstar_fixed_state_context_reset_v1(")
    end = text.index("int xstar_fixed_state_run_v1(", reset)
    block = text[reset:end]
    assert "source_levwk_rnisi_workspace_v06828.fill(0.0);" in block
