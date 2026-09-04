from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_qualification_accepts():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_pypi_native_wheel_windows_0_6_89_4.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PYPI_NATIVE_WHEEL_WINDOWS_06894_RESULT=ACCEPT" in proc.stdout


def test_license_remains_gpl_3_0():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert 'license = "GPL-3.0"' in pyproject
    assert 'license-files = ["LICENSE"]' in pyproject
    assert "GNU GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3, 29 June 2007" in license_text


def test_pypi_windows_profile_removes_only_embedding_plugin():
    support = load_module(ROOT / "build_support.py", "xstar_tools_build_support_test_06894")
    full = set(support._native_artifacts("Windows", profile="full"))
    pypi = set(support._native_artifacts("Windows", profile="pypi-windows"))
    assert support._native_make_target("pypi-windows") == "pypi-windows"
    assert full - pypi == {"libxstar_backend_python.dll"}
    assert "libxstar_api.dll" in pypi
    assert "xstar-xspec.exe" in pypi


def test_windows_profile_skips_python_config_but_full_profile_retains_it():
    source = (ROOT / "build_support.py").read_text(encoding="utf-8")
    assert 'python_config = None if profile == "pypi-windows" else _python_config_tool()' in source
    assert 'env["PYTHON_CONFIG"] = tools["python_config"] or "true"' in source


def test_windows_workflow_is_amd64_cpython_only():
    workflow = (ROOT / ".github/workflows/pypi-native-wheel-windows.yml").read_text(encoding="utf-8")
    for cp in ("cp39", "cp310", "cp311", "cp312", "cp313", "cp314"):
        assert workflow.count(f"{cp}-win_amd64") == 1
    assert "-win32" not in workflow
    assert "win_arm64" not in workflow
    assert "msystem: UCRT64" in workflow
    assert "build_windows_cfitsio.sh" in workflow
    assert "core.autocrlf input" in workflow


def _pe_amd64() -> bytes:
    data = bytearray(0x90)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, 0x8664)
    return bytes(data)


def _write_synthetic_wheel(path: Path) -> None:
    dist = "xstar_tools-0.6.89.4.dist-info"
    cpp = "xstar_tools/xstar/cpp/"
    required = {
        "libxstar_solver.dll", "libxstar_rates.dll", "libxstar_matrix.dll",
        "libxstar_emissivity.dll", "libxstar_opacity.dll", "libxstar_thermal.dll",
        "libxstar_engine.dll", "libxstar_local_zone.dll", "libxstar_final_recompute.dll",
        "libxstar_production_zone.dll", "libxstar_xspec_table.dll", "libxstar_api.dll",
        "libxstar_backend_cpp.dll", "xstar_cpp.exe", "xstar-cpp.exe", "xstar-xspec-initable.exe",
        "xstar-xspec-table.exe", "xstar-xspec.exe",
    }
    native = {
        "native_built": True,
        "platform_system": "Windows",
        "platform_machine": "AMD64",
        "native_profile": "pypi-windows",
        "package_version": "0.6.89.4",
        "c_api_abi": 60487,
        "production_zone_abi": 6048110,
        "mpi_included": False,
        "atomic_database_bundled": False,
        "python_config": "",
        "artifacts": sorted(required),
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{dist}/WHEEL", "Wheel-Version: 1.0\nTag: cp313-cp313-win_amd64\n")
        zf.writestr(f"{dist}/METADATA", "Metadata-Version: 2.4\nName: xstar-tools\nVersion: 0.6.89.4\nLicense-Expression: GPL-3.0\n")
        zf.writestr(f"{dist}/licenses/LICENSE", "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n")
        zf.writestr(f"{dist}/entry_points.txt", "[console_scripts]\nxstar-cpp=x:a\nxstar-xspec-initable=x:b\nxstar-xspec-table=x:c\nxstar-xspec=x:d\n")
        zf.writestr(cpp + "native_build.json", json.dumps(native))
        pe = _pe_amd64()
        for name in required:
            zf.writestr(cpp + name, pe)
        for name in ("cfitsio-10-abc.dll", "libstdc++-6-abc.dll", "libgcc_s_seh-1-abc.dll", "libwinpthread-1-abc.dll"):
            zf.writestr("xstar_tools.libs/" + name, pe)


def test_artifact_checker_accepts_win_amd64_synthetic_wheel(tmp_path):
    checker = load_module(
        ROOT / "tools/qualification/check_pypi_native_wheel_windows_artifacts_0_6_89_4.py",
        "xstar_tools_windows_artifact_checker_06894",
    )
    wheel = tmp_path / "xstar_tools-0.6.89.4-cp313-cp313-win_amd64.whl"
    _write_synthetic_wheel(wheel)
    checker.inspect(wheel, "cp313-win_amd64")


def test_windows_cfitsio_is_pinned_and_shared():
    script = (ROOT / "tools/packaging/build_windows_cfitsio.sh").read_text(encoding="utf-8")
    assert "4.6.2" in script
    assert "66fd078cc0bea896b0d44b120d46d6805421a5361d3a5ad84d9f397b1b5de2cb" in script
    assert "CC=gcc CXX=g++" in script
    assert "*cfitsio*.dll" in script


def test_linux_and_macos_release_profiles_are_retained():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text(encoding="utf-8")
    assert 'manylinux-x86_64-image = "manylinux_2_28"' in pyproject
    assert 'XSTAR_TOOLS_NATIVE_PROFILE="pypi-linux"' in pyproject
    assert 'XSTAR_TOOLS_NATIVE_PROFILE="pypi-macos"' in pyproject
    assert "pypi-linux: $(PYPI_LINUX_TARGETS)" in makefile
    assert "pypi-macos: $(PYPI_MACOS_TARGETS)" in makefile
