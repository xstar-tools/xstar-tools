from __future__ import annotations

from pathlib import Path
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_type51_broad_element_release_gate() -> None:
    proc = subprocess.run(
        ["python3", str(ROOT / "tools/qualification/check_type51_broad_element_closure_0_6_82_2.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "TYPE51_BROAD_ELEMENT_CLOSURE_06822_RESULT=ACCEPT" in proc.stdout


def _write_version_stub(path: Path, version: str) -> None:
    path.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"--version\" ]; then\n"
        f"  echo 'xstar-cpp package version {version}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 99\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_06822_host_runner_rejects_stale_binary(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "atdb.fits").write_bytes(b"stub")
    (data / "coheat.dat").write_text("stub\n", encoding="utf-8")
    binary = tmp_path / "xstar-cpp"
    _write_version_stub(binary, "0.6.82.1")
    proc = subprocess.run(
        ["python3", str(ROOT / "tools/qualification/run_multi_element_host_smoke_0_6_82_2.py"),
         "--data-dir", str(data), "--xstar-cpp", str(binary), "--output", str(tmp_path / "out")],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 2
    assert "MULTI_ELEMENT_HOST_SMOKE_06822_RESULT=REJECT_STALE_BINARY" in proc.stdout
    assert "MULTI_ELEMENT_HOST_SMOKE_06822_BINARY_VERSION=0.6.82.1" in proc.stdout


def test_type54_57_59_cases_remain_present() -> None:
    text = (ROOT / "src/xstar_tools/xstar/cpp/local_zone_engine.cpp").read_text(encoding="utf-8")
    for opcode in (
        "XSTAR_FIXED_OPCODE_TYPE54_ANGULAR_REDIS",
        "XSTAR_FIXED_OPCODE_TYPE57_COLLISIONAL_IONIZATION",
        "XSTAR_FIXED_OPCODE_TYPE59_VERNER_BOUND_FREE",
    ):
        assert f"case {opcode}:" in text
