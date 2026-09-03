from __future__ import annotations

import importlib.util
import json
from pathlib import Path
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
        [sys.executable, "tools/qualification/check_pypi_native_wheel_macos_0_6_89_3.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PYPI_NATIVE_WHEEL_MACOS_06893_RESULT=ACCEPT" in proc.stdout


def test_license_is_gpl_3_0_and_gplv3_text():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert 'license = "GPL-3.0"' in pyproject
    assert 'license-files = ["LICENSE"]' in pyproject
    assert "GNU GENERAL PUBLIC LICENSE" in license_text
    assert "Version 3, 29 June 2007" in license_text
    assert "MIT License" not in license_text


def test_pypi_macos_profile_removes_only_embedding_plugin():
    support = load_module(ROOT / "build_support.py", "xstar_tools_build_support_test_06893")
    full = set(support._native_artifacts("Darwin", profile="full"))
    pypi = set(support._native_artifacts("Darwin", profile="pypi-macos"))
    assert support._native_make_target("pypi-macos") == "pypi-macos"
    assert full - pypi == {"libxstar_backend_python.dylib"}
    assert "libxstar_api.dylib" in pypi
    assert "xstar-xspec" in pypi


def test_macos_workflow_is_native_arch_only():
    workflow = (ROOT / ".github/workflows/pypi-native-wheel-macos.yml").read_text(encoding="utf-8")
    assert workflow.count("cp39-macosx_arm64") == 1
    assert workflow.count("cp314-macosx_arm64") == 1
    assert workflow.count("cp39-macosx_x86_64") == 1
    assert workflow.count("cp314-macosx_x86_64") == 1
    assert "universal2" not in workflow
    assert "macos-15-intel" in workflow
    assert "CIBW_ARCHS_MACOS" in workflow


def _write_synthetic_wheel(path: Path, arch: str = "arm64") -> None:
    dist = "xstar_tools-0.6.89.3.dist-info"
    cpp = "xstar_tools/xstar/cpp/"
    required = {
        "libxstar_solver.dylib", "libxstar_rates.dylib", "libxstar_matrix.dylib",
        "libxstar_emissivity.dylib", "libxstar_opacity.dylib", "libxstar_thermal.dylib",
        "libxstar_engine.dylib", "libxstar_local_zone.dylib", "libxstar_final_recompute.dylib",
        "libxstar_production_zone.dylib", "libxstar_xspec_table.dylib", "libxstar_api.dylib",
        "libxstar_backend_cpp.dylib", "xstar_cpp", "xstar-cpp", "xstar-xspec-initable",
        "xstar-xspec-table", "xstar-xspec",
    }
    native = {
        "native_built": True,
        "platform_system": "Darwin",
        "platform_machine": arch,
        "native_profile": "pypi-macos",
        "package_version": "0.6.89.3",
        "c_api_abi": 60487,
        "production_zone_abi": 6048110,
        "mpi_included": False,
        "atomic_database_bundled": False,
        "artifacts": sorted(required),
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{dist}/WHEEL", f"Wheel-Version: 1.0\nTag: cp313-cp313-macosx_11_0_{arch}\n")
        zf.writestr(f"{dist}/METADATA", "Metadata-Version: 2.4\nName: xstar-tools\nVersion: 0.6.89.3\nLicense-Expression: GPL-3.0\n")
        zf.writestr(f"{dist}/licenses/LICENSE", "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n")
        zf.writestr(f"{dist}/entry_points.txt", "[console_scripts]\nxstar-cpp=x:a\nxstar-xspec-initable=x:b\nxstar-xspec-table=x:c\nxstar-xspec=x:d\n")
        zf.writestr(cpp + "native_build.json", json.dumps(native))
        for name in required:
            zf.writestr(cpp + name, b"")
        zf.writestr("xstar_tools/.dylibs/libcfitsio.10.dylib", b"")


@pytest.mark.parametrize("arch", ["arm64", "x86_64"])
def test_artifact_checker_accepts_arch_specific_synthetic_wheel(tmp_path, arch):
    checker = load_module(
        ROOT / "tools/qualification/check_pypi_native_wheel_macos_artifacts_0_6_89_3.py",
        "xstar_tools_macos_artifact_checker_06893",
    )
    wheel = tmp_path / f"xstar_tools-0.6.89.3-cp313-cp313-macosx_11_0_{arch}.whl"
    _write_synthetic_wheel(wheel, arch)
    checker.inspect(wheel, f"cp313-macosx_{arch}")


def test_macos_cfitsio_is_pinned_and_targeted():
    script = (ROOT / "tools/packaging/build_macos_cfitsio.sh").read_text(encoding="utf-8")
    assert "4.6.2" in script
    assert "66fd078cc0bea896b0d44b120d46d6805421a5361d3a5ad84d9f397b1b5de2cb" in script
    assert 'MACOSX_DEPLOYMENT_TARGET:-11.0' in script


def test_linux_release_profile_is_retained():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text(encoding="utf-8")
    assert 'manylinux-x86_64-image = "manylinux_2_28"' in pyproject
    assert 'XSTAR_TOOLS_NATIVE_PROFILE="pypi-linux"' in pyproject
    assert "pypi-linux: $(PYPI_LINUX_TARGETS)" in makefile
