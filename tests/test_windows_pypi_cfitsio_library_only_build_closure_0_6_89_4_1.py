from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_qualification_accepts():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_windows_pypi_cfitsio_library_only_build_closure_0_6_89_4_1.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WINDOWS_PYPI_CFITSIO_LIBRARY_ONLY_BUILD_CLOSURE_068941_RESULT=ACCEPT" in proc.stdout


def test_cfitsio_script_builds_only_library_and_leaf_installs():
    script = (ROOT / "tools/packaging/build_windows_cfitsio.sh").read_text(encoding="utf-8")
    active = {
        line.strip()
        for line in script.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert 'make -j"${jobs}" libcfitsio.la' in active
    assert 'make -j"${jobs}"' not in active
    assert "make install-libLTLIBRARIES install-includeHEADERS install-pkgconfigDATA" in active
    assert "make install" not in active
    assert not any(line.startswith("make ") and "smem" in line for line in active)


def test_predecessor_windows_runtime_implementation_is_retained():
    import hashlib
    assert hashlib.sha256((ROOT / "build_support.py").read_bytes()).hexdigest() == "3f6362d0f4007741b872448e532f19d125148e5924b2801096e29b8cadbd1b95"
    assert hashlib.sha256((ROOT / "src/xstar_tools/native_runtime.py").read_bytes()).hexdigest() == "2adf7e2059d9025413088d453d5f5623486cf37ff5f3fea885e2a199d58909c9"


def test_workflow_records_cfitsio_log_and_six_selectors():
    workflow = (ROOT / ".github/workflows/pypi-native-wheel-windows.yml").read_text(encoding="utf-8")
    for cp in ("cp39", "cp310", "cp311", "cp312", "cp313", "cp314"):
        assert workflow.count(f"{cp}-win_amd64") == 1
    assert "diffutils" in workflow
    assert "set -o pipefail" in workflow
    assert "cfitsio-build.log" in workflow
    assert "check_windows_pypi_cfitsio_library_only_build_closure_0_6_89_4_1.py" in workflow
    assert "check_windows_pypi_cfitsio_library_only_build_closure_artifacts_0_6_89_4_1.py" in workflow
    assert "WINDOWS_PYPI_CFITSIO_LIBRARY_ONLY_BUILD_CLOSURE_068941_GITHUB_JOB_RESULT=ACCEPT" in workflow


def _pe_amd64() -> bytes:
    data = bytearray(0x90)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", data, 0x84, 0x8664)
    return bytes(data)


def _write_synthetic_wheel(path: Path) -> None:
    dist = "xstar_tools-0.6.89.4.1.dist-info"
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
        "package_version": "0.6.89.4.1",
        "c_api_abi": 60487,
        "production_zone_abi": 6048110,
        "mpi_included": False,
        "atomic_database_bundled": False,
        "python_config": "",
        "artifacts": sorted(required),
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{dist}/WHEEL", "Wheel-Version: 1.0\nTag: cp313-cp313-win_amd64\n")
        zf.writestr(f"{dist}/METADATA", "Metadata-Version: 2.4\nName: xstar-tools\nVersion: 0.6.89.4.1\nLicense-Expression: GPL-3.0\n")
        zf.writestr(f"{dist}/licenses/LICENSE", "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n")
        zf.writestr(f"{dist}/entry_points.txt", "[console_scripts]\nxstar-cpp=x:a\nxstar-xspec-initable=x:b\nxstar-xspec-table=x:c\nxstar-xspec=x:d\n")
        zf.writestr(cpp + "native_build.json", json.dumps(native))
        pe = _pe_amd64()
        for name in required:
            zf.writestr(cpp + name, pe)
        for name in ("cfitsio-10-abc.dll", "libstdc++-6-abc.dll", "libgcc_s_seh-1-abc.dll", "libwinpthread-1-abc.dll"):
            zf.writestr("xstar_tools.libs/" + name, pe)


def test_artifact_checker_accepts_synthetic_repaired_wheel(tmp_path):
    checker = load_module(
        ROOT / "tools/qualification/check_windows_pypi_cfitsio_library_only_build_closure_artifacts_0_6_89_4_1.py",
        "xstar_tools_windows_artifact_checker_068941",
    )
    wheel = tmp_path / "xstar_tools-0.6.89.4.1-cp313-cp313-win_amd64.whl"
    _write_synthetic_wheel(wheel)
    checker.inspect(wheel, "cp313-win_amd64")


def test_license_science_and_public_abis_remain_frozen():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "GPL-3.0"' in pyproject
    assert '__version__ = "0.6.48.12.3.45.3.3.8"' in (ROOT / "src/xstar_tools/__init__.py").read_text(encoding="utf-8")
    q = json.loads((ROOT / "qualification/windows_pypi_cfitsio_library_only_build_closure_0_6_89_4_1.json").read_text())
    assert q["c_api_abi"] == 60487
    assert q["production_zone_abi"] == 6048110
    assert q["fixed_state_abi"] == 60486
    assert q["xspec_table_abi"] == 1


def test_linux_and_macos_release_profiles_remain_retained():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text(encoding="utf-8")
    assert 'manylinux-x86_64-image = "manylinux_2_28"' in pyproject
    assert 'XSTAR_TOOLS_NATIVE_PROFILE="pypi-linux"' in pyproject
    assert 'XSTAR_TOOLS_NATIVE_PROFILE="pypi-macos"' in pyproject
    assert "pypi-linux: $(PYPI_LINUX_TARGETS)" in makefile
    assert "pypi-macos: $(PYPI_MACOS_TARGETS)" in makefile


def test_no_atomic_database_is_bundled():
    assert not (ROOT / "src/xstar_tools/xstar/data/atdb.fits").exists()
    assert "atdb.fits" not in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
