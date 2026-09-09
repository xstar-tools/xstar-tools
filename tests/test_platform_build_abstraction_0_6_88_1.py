from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def _config(platform: str | None = None, env: dict[str, str] | None = None) -> dict[str, str]:
    cmd = ["make", "-s", "print-config"]
    if platform is not None:
        cmd.append(f"PLATFORM={platform}")
    cp = subprocess.run(cmd, cwd=CPP, env=env, text=True, capture_output=True, check=True)
    out: dict[str, str] = {}
    for line in cp.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
    return out




def test_linux_contract() -> None:
    cfg = _config("linux")
    assert cfg["PLATFORM"] == "linux"
    assert cfg["SHLIB_EXT"] == ".so"
    assert cfg["EXEEXT"] == ""
    assert cfg["SHLIB_LDFLAGS"] == "-shared"
    assert cfg["PIC_FLAGS"] == "-fPIC"
    assert cfg["DL_LIBS"] == "-ldl"
    assert cfg["THREAD_LIBS"] == "-pthread"
    assert cfg["RPATH_ORIGIN"] == "-Wl,-rpath,$ORIGIN"
    assert cfg["FILESYSTEM_LIBS"] == "-lstdc++fs"


def test_macos_contract() -> None:
    cfg = _config("macos")
    assert cfg["SHLIB_EXT"] == ".dylib"
    assert cfg["EXEEXT"] == ""
    assert cfg["SHLIB_LDFLAGS"] == "-dynamiclib"
    assert cfg["PIC_FLAGS"] == "-fPIC"
    assert cfg["DL_LIBS"] == ""
    assert cfg["THREAD_LIBS"] == "-pthread"
    assert cfg["RPATH_ORIGIN"] == "-Wl,-rpath,@loader_path"
    assert cfg["FILESYSTEM_LIBS"] == ""


def test_windows_contract_and_no_mpi() -> None:
    cfg = _config("windows")
    assert cfg["SHLIB_EXT"] == ".dll"
    assert cfg["EXEEXT"] == ".exe"
    assert cfg["SHLIB_LDFLAGS"] == "-shared"
    assert cfg["PIC_FLAGS"] == ""
    assert cfg["DL_LIBS"] == ""
    assert cfg["THREAD_LIBS"] == "-pthread"
    assert cfg["RPATH_ORIGIN"] == ""
    assert cfg["FILESYSTEM_LIBS"] == ""
    cp = subprocess.run(
        ["make", "-s", "mpi", "PLATFORM=windows"], cwd=CPP,
        text=True, capture_output=True,
    )
    assert cp.returncode != 0
    assert "not supported on PLATFORM=windows" in cp.stderr


def test_environment_platform_does_not_override_host_detection() -> None:
    env = os.environ.copy()
    env["PLATFORM"] = "linux/amd64"
    cfg = _config(env=env)
    assert cfg["PLATFORM"] in {"linux", "macos", "windows"}
    assert cfg["PLATFORM"] != "linux/amd64"


def test_linux_target_names_are_unchanged() -> None:
    cp = subprocess.run(
        ["make", "-pn", "PLATFORM=linux"], cwd=CPP,
        text=True, capture_output=True, check=True,
    )
    text = cp.stdout
    assert "SOLVER_TARGET := libxstar_solver.so" in text
    assert "API_TARGET := libxstar_api.so" in text
    assert "PUBLIC_EXECUTABLE_TARGET := xstar-cpp" in text
    assert "XSPEC_GRID_EXECUTABLE := xstar-xspec" in text
