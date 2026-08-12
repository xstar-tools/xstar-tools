from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_cpp_preserves_literal_niter_and_zero_skips_controller() -> None:
    runtime = (ROOT / "src/xstar_tools/xstar/cpp/xstar_atdb_runtime.cpp").read_text(encoding="utf-8")
    standalone = (ROOT / "src/xstar_tools/xstar/cpp/xstar_standalone.cpp").read_text(encoding="utf-8")
    assert "p.niter=p.requested_niter;" in runtime
    assert "p.niter=std::max(1,p.requested_niter)" not in runtime
    assert "if (params.niter == 0)" in standalone
    assert "Canonical xstarcalc.f90: nlimdt==0 skips dsec entirely" in standalone
    assert "config.nlim = params.niter;" in standalone


def test_cpp_dsec_negative_contract_is_charge_only() -> None:
    text = (ROOT / "src/xstar_tools/xstar/cpp/thermal_kernels.cpp").read_text(encoding="utf-8")
    assert "int nlimt = std::max(nlim, 0), nlimx = std::abs(nlim);" in text
    assert "int nlimtt = std::max(nlimt, 1), nlimxx = std::max(nlimx, 1);" in text
    assert "nlimt = std::max(nlim, 0); nlimx = std::abs(nlim); nlimxx = nlimx;" in text


def test_python_xstarcalc_and_dsec_have_all_three_source_branches() -> None:
    driver = (ROOT / "src/xstar_tools/xstar/driver.py").read_text(encoding="utf-8")
    dsec = (ROOT / "src/xstar_tools/xstar/dsec.py").read_text(encoding="utf-8")
    physical = (ROOT / "src/xstar_tools/xstar/physical_runner.py").read_text(encoding="utf-8")
    assert "if not fixed_state and nlimdt != 0:" in driver
    assert "skipped_source_routines" in driver
    assert "Negative ``nlim``" in dsec
    assert "nlimt = max(nlim, 0)" in dsec
    assert "nlimx = abs(nlim)" in dsec
    assert '"nlimd": int(parameters.get("niter"))' in physical
    assert '"nlimdt": int(parameters.get("niter"))' in physical
    assert "state.plasma.xee = 1.0" in physical


def test_source_gate_accepts() -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/qualification/check_niter_semantics_0_6_82_24.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "NITER_SEMANTICS_068224_RESULT=ACCEPT" in proc.stdout
