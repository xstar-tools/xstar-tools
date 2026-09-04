from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.6.89.4.3"
PREFIX = "WINDOWS_PYPI_CFITSIO_METADATA_PROPAGATION_CLOSURE_068943"


def load_build_support():
    spec = importlib.util.spec_from_file_location("xstar_tools_build_support_test_068943", ROOT / "build_support.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_source_qualification_accepts():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_windows_pypi_cfitsio_metadata_propagation_closure_0_6_89_4_3.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{PREFIX}_RESULT=ACCEPT" in proc.stdout


def test_pkg_config_metadata_is_normalized_and_returned(tmp_path):
    fake = tmp_path / "pkg-config"
    fake.write_text(
        "\n".join([
            "#!/bin/sh",
            'case "$1" in',
            r"  --cflags) printf '%s\n' '-IC:\xstar\cfitsio\include' ;;",
            r"  --variable=libdir) printf '%s\n' 'C:\xstar\cfitsio\lib' ;;",
            r"  --libs) printf '%s\n' '-LC:\xstar\cfitsio\lib -lcfitsio -lz' ;;",
            "  *) exit 3 ;;",
            "esac",
            "",
        ]),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    support = load_build_support()
    assert support._pkg_config_cfitsio_make_variables(str(fake)) == (
        "-IC:/xstar/cfitsio/include",
        "C:/xstar/cfitsio/lib",
        "-LC:/xstar/cfitsio/lib -lcfitsio -lz",
    )


def test_windows_profile_passes_explicit_cfitsio_make_variables():
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


def test_cfitsio_prebuild_contract_is_unchanged():
    script = (ROOT / "tools/packaging/build_windows_cfitsio.sh").read_text(encoding="utf-8")
    assert "--enable-shared" in script
    assert "--disable-static" in script
    assert '-version-info 10 -no-undefined' in script
    assert "make install-libLTLIBRARIES install-includeHEADERS install-pkgconfigDATA" in script
    assert "*cfitsio*.dll" in script


def test_workflow_keeps_six_windows_selectors_and_new_checkers():
    workflow = (ROOT / ".github/workflows/pypi-native-wheel-windows.yml").read_text(encoding="utf-8")
    for cp in ("cp39", "cp310", "cp311", "cp312", "cp313", "cp314"):
        assert workflow.count(f"{cp}-win_amd64") == 1
    assert "check_windows_pypi_cfitsio_metadata_propagation_closure_0_6_89_4_3.py" in workflow
    assert "check_windows_pypi_cfitsio_metadata_propagation_closure_artifacts_0_6_89_4_3.py" in workflow
    assert f"{PREFIX}_GITHUB_JOB_RESULT=ACCEPT" in workflow


def test_manifest_preserves_science_abis_mpi_and_atdb_policy():
    q = json.loads((ROOT / "qualification/windows_pypi_cfitsio_metadata_propagation_closure_0_6_89_4_3.json").read_text())
    assert q["science_change"] is False
    assert q["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert q["c_api_abi"] == 60487
    assert q["production_zone_abi"] == 6048110
    assert q["fixed_state_abi"] == 60486
    assert q["xspec_table_abi"] == 1
    assert q["ordinary_wheel_includes_mpi"] is False
    assert q["bundles_atdb_fits"] is False


def test_smoke_targets_current_version_and_prefix():
    smoke = (ROOT / "tools/packaging/pypi_windows_wheel_smoke.py").read_text(encoding="utf-8")
    assert f'VERSION = "{VERSION}"' in smoke
    assert f'PREFIX = "{PREFIX}_SMOKE"' in smoke
