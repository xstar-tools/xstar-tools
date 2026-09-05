from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.6.89.4.5"
PREFIX = "WINDOWS_PYPI_DELVEWHEEL_EXISTING_DLL_RESOLUTION_CLOSURE_068945"
REPAIR_COMMAND = (
    "delvewheel repair --ignore-existing --analyze-existing --analyze-existing-exes "
    "--add-path %XSTAR_TOOLS_WINDOWS_DLL_PATH% -w {dest_dir} -v {wheel}"
)


def test_source_qualification_accepts():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_windows_pypi_delvewheel_existing_dll_resolution_closure_0_6_89_4_5.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{PREFIX}_RESULT=ACCEPT" in proc.stdout


def test_repair_command_combines_ignore_and_analysis_modes():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert REPAIR_COMMAND in pyproject
    assert "--ignore-existing" in REPAIR_COMMAND
    assert "--analyze-existing" in REPAIR_COMMAND
    assert "--analyze-existing-exes" in REPAIR_COMMAND
    assert "--with-mangle" not in REPAIR_COMMAND


def test_external_windows_dll_search_path_is_retained():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "--add-path %XSTAR_TOOLS_WINDOWS_DLL_PATH%" in pyproject
    workflow = (ROOT / ".github/workflows/pypi-native-wheel-windows.yml").read_text(encoding="utf-8")
    assert '"XSTAR_TOOLS_WINDOWS_DLL_PATH=$cfitsioBin;$ucrtBin"' in workflow


def test_native_production_implementation_is_predecessor_identical():
    expected = {
        "build_support.py": "ac67b25cf55da936ffc6d50424d27f738dd5d4e504ef89d7d4b2f9bc6dade814",
        "src/xstar_tools/native_runtime.py": "2adf7e2059d9025413088d453d5f5623486cf37ff5f3fea885e2a199d58909c9",
        "tools/packaging/build_windows_cfitsio.sh": "d79a8b3441f0b294d6721cbb2bceb0d60e3129b35cc4b5c7acc7c71314970e0a",
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest


def test_make_command_line_values_still_bypass_pkg_config_rediscovery():
    cpp = ROOT / "src/xstar_tools/xstar/cpp"
    proc = subprocess.run(
        [
            "make", "-n", "-C", str(cpp), "PLATFORM=windows",
            "PYTHON_CONFIG=true", "PKG_CONFIG=false",
            "CFITSIO_CFLAGS=-IC:/xstar/cfitsio/include",
            "CFITSIO_LIBDIR=C:/xstar/cfitsio/lib",
            "CFITSIO_LIBS=-LC:/xstar/cfitsio/lib -lcfitsio -lz",
            f"PACKAGE_VERSION={VERSION}", "pypi-windows",
        ],
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    output = proc.stdout + proc.stderr
    assert "-IC:/xstar/cfitsio/include" in output
    assert "-LC:/xstar/cfitsio/lib" in output
    assert "-lcfitsio" in output
    assert "-lz" in output
    assert "xstar-xspec-mpi" not in output


def test_workflow_keeps_six_windows_selectors_and_new_checkers():
    workflow = (ROOT / ".github/workflows/pypi-native-wheel-windows.yml").read_text(encoding="utf-8")
    for cp in ("cp39", "cp310", "cp311", "cp312", "cp313", "cp314"):
        assert workflow.count(f"{cp}-win_amd64") == 1
    assert "check_windows_pypi_delvewheel_existing_dll_resolution_closure_0_6_89_4_5.py" in workflow
    assert "check_windows_pypi_delvewheel_existing_dll_resolution_closure_artifacts_0_6_89_4_5.py" in workflow
    assert f"{PREFIX}_GITHUB_JOB_RESULT=ACCEPT" in workflow


def test_manifest_preserves_science_abis_mpi_and_atdb_policy():
    q = json.loads((ROOT / "qualification/windows_pypi_delvewheel_existing_dll_resolution_closure_0_6_89_4_5.json").read_text())
    assert q["predecessor"] == "0.6.89.4.4"
    assert q["predecessor_failure_stage"] == "delvewheel_existing_dll_dependency_resolution"
    assert q["packaging_repair_command_only_change"] is True
    assert q["delvewheel_ignore_existing"] is True
    assert q["delvewheel_analyze_existing"] is True
    assert q["delvewheel_analyze_existing_exes"] is True
    assert q["science_change"] is False
    assert q["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert q["c_api_abi"] == 60487
    assert q["production_zone_abi"] == 6048110
    assert q["fixed_state_abi"] == 60486
    assert q["xspec_table_abi"] == 1
    assert q["ordinary_wheel_includes_mpi"] is False
    assert q["bundles_atdb_fits"] is False


def test_license_remains_gpl_3_0():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'license = "GPL-3.0"' in pyproject
