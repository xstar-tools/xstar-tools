from __future__ import annotations

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_multi_element_atdb_lowering_release_gate() -> None:
    proc = subprocess.run(
        ["python3", str(ROOT / "tools/qualification/check_multi_element_atdb_lowering_0_6_82_1.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "MULTI_ELEMENT_ATDB_LOWERING_06821_RESULT=ACCEPT" in proc.stdout


def test_realistic_xstar_example_is_packaged() -> None:
    text = (ROOT / "examples/xstar_example.par").read_text(encoding="utf-8")
    for name in ("cabund", "nabund", "oabund", "neabund", "mgabund", "alabund", "siabund",
                 "sabund", "arabund", "caabund", "crabund", "feabund", "niabund"):
        assert f"{name},r,h,1." in text
    assert 'abundtbl,s,a,"xdef"' in text
    assert "lwrite,i,h,0" in text
