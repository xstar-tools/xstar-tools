from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.6.89.4.4"
PREFIX = "WINDOWS_PYPI_PKG_CONFIG_QUALIFICATION_LAUNCHER_CLOSURE_068944"


def load_build_support():
    spec = importlib.util.spec_from_file_location("xstar_tools_build_support_test_068944", ROOT / "build_support.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_qualification_accepts():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_windows_pypi_pkg_config_qualification_launcher_closure_0_6_89_4_4.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{PREFIX}_RESULT=ACCEPT" in proc.stdout


def test_pkg_config_metadata_qualification_uses_mocked_process_boundary():
    support = load_build_support()
    calls: list[list[str]] = []
    outputs = {
        "--cflags": r"-IC:\xstar\cfitsio\include",
        "--variable=libdir": r"C:\xstar\cfitsio\lib",
        "--libs": r"-LC:\xstar\cfitsio\lib -lcfitsio -lz",
    }

    def fake_run(args, **kwargs):
        argv = [str(x) for x in args]
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=outputs[argv[1]] + "\n", stderr="")

    with patch.object(support.subprocess, "run", side_effect=fake_run):
        values = support._pkg_config_cfitsio_make_variables(r"C:\qualification\pkg-config.exe")

    assert values == (
        "-IC:/xstar/cfitsio/include",
        "C:/xstar/cfitsio/lib",
        "-LC:/xstar/cfitsio/lib -lcfitsio -lz",
    )
    assert calls == [
        [r"C:\qualification\pkg-config.exe", "--cflags", "cfitsio"],
        [r"C:\qualification\pkg-config.exe", "--variable=libdir", "cfitsio"],
        [r"C:\qualification\pkg-config.exe", "--libs", "cfitsio"],
    ]


def test_checker_does_not_create_or_execute_fake_posix_tool():
    source = (ROOT / "tools/qualification/check_windows_pypi_pkg_config_qualification_launcher_closure_0_6_89_4_4.py").read_text(encoding="utf-8")
    assert "import tempfile" not in source
    assert "def fake_pkg_config(" not in source
    assert 'patch.object(support.subprocess, "run"' in source


def test_production_build_support_is_predecessor_implementation():
    import hashlib
    data = (ROOT / "build_support.py").read_bytes()
    assert hashlib.sha256(data).hexdigest() == "ac67b25cf55da936ffc6d50424d27f738dd5d4e504ef89d7d4b2f9bc6dade814"


def test_windows_profile_still_passes_explicit_cfitsio_make_variables():
    source = (ROOT / "build_support.py").read_text(encoding="utf-8")
    assert 'if profile == "pypi-windows":' in source
    assert 'f"CFITSIO_CFLAGS={cflags}"' in source
    assert 'f"CFITSIO_LIBDIR={libdir}"' in source
    assert 'f"CFITSIO_LIBS={libs}"' in source
    assert "*cfitsio_make_args" in source


def test_make_command_line_values_bypass_pkg_config_shell_rediscovery():
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
    assert "check_windows_pypi_pkg_config_qualification_launcher_closure_0_6_89_4_4.py" in workflow
    assert "check_windows_pypi_pkg_config_qualification_launcher_closure_artifacts_0_6_89_4_4.py" in workflow
    assert f"{PREFIX}_GITHUB_JOB_RESULT=ACCEPT" in workflow


def test_manifest_preserves_science_abis_mpi_and_atdb_policy():
    q = json.loads((ROOT / "qualification/windows_pypi_pkg_config_qualification_launcher_closure_0_6_89_4_4.json").read_text())
    assert q["predecessor"] == "0.6.89.4.3"
    assert q["predecessor_failure_stage"] == "source_qualification_fake_pkg_config_launcher"
    assert q["qualification_only_change"] is True
    assert q["production_build_support_changed"] is False
    assert q["science_change"] is False
    assert q["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert q["c_api_abi"] == 60487
    assert q["production_zone_abi"] == 6048110
    assert q["fixed_state_abi"] == 60486
    assert q["xspec_table_abi"] == 1
    assert q["ordinary_wheel_includes_mpi"] is False
    assert q["bundles_atdb_fits"] is False
