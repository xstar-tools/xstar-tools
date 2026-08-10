from __future__ import annotations

import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def test_packaging_gate_accepts():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_packaging_milestone.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PACKAGING_MILESTONE_RESULT=ACCEPT" in proc.stdout


def test_build_metadata_is_authoritative_and_setup_is_thin():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    setup = (ROOT / "setup.py").read_text(encoding="utf-8")
    assert 'build-backend = "setuptools.build_meta"' in pyproject
    match = re.search(r'^version = "([0-9.]+)"$', pyproject, re.MULTILINE)
    assert match is not None
    assert tuple(map(int, match.group(1).split('.'))) >= (0, 6, 71)
    assert "include-package-data = false" in pyproject
    setup_cfg = ROOT / "setup.cfg"
    if setup_cfg.exists():
        # setuptools writes this exact non-authoritative file into generated sdists.
        assert setup_cfg.read_text(encoding="utf-8").strip() == "[egg_info]\ntag_build = \ntag_date = 0"
    assert "version=" not in setup
    assert "install_requires" not in setup


def test_wheel_static_package_data_is_whitelisted():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_data = pyproject.split("[tool.setuptools.package-data]", 1)[1]
    assert '"cpp/*"' not in package_data
    assert '"native/*"' not in package_data
    assert '"cpp/constants.def"' in package_data
    assert '"cpp/xstar_api.h"' in package_data
    assert '"cpp/xstar_production_zone_bridge.h"' in package_data
    assert "atdb.fits" not in package_data


def test_python_only_build_hook_writes_explicit_metadata(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT))
    try:
        import build_support
        from setuptools import Distribution
        monkeypatch.setenv("XSTAR_TOOLS_NATIVE", "off")
        dist = Distribution({"name": "xstar-tools", "version": "0.6.72", "packages": []})
        cmd = build_support.XStarBuildPy(dist)
        cmd.build_lib = str(tmp_path / "build")
        # Call only the native stage; ordinary build_py file copying is covered by wheel verification.
        cmd._build_native_runtime()
        meta = json.loads((tmp_path / "build/xstar_tools/xstar/cpp/native_build.json").read_text())
        assert meta["native_built"] is False
        assert meta["policy"] == "off"
        assert meta["science_revision"] == "0.6.48.12.3.45.3.3.8"
        assert meta["production_zone_abi"] == 6048110
    finally:
        sys.path.remove(str(ROOT))


def test_xstar_cpp_console_launcher_has_explicit_python_only_failure(monkeypatch, capsys):
    sys.path.insert(0, str(SRC))
    try:
        import xstar_tools.execution as execution
        import xstar_tools.cli.xstar_cpp as launcher
        monkeypatch.setattr(execution, "native_executable_path", lambda: None)
        assert launcher.main() == 69
        assert "native runtime is not installed" in capsys.readouterr().err
    finally:
        sys.path.remove(str(SRC))


def test_installed_data_policy_is_user_owned_not_site_packages():
    text = (SRC / "xstar_tools/data.py").read_text(encoding="utf-8")
    assert "XDG_CONFIG_HOME" in text
    assert "XDG_DATA_HOME" in text
    assert 'DATAPATH_FILE = _user_config_home() / "xstar-tools" / "datapath"' in text
    assert 'DEFAULT_DATA_DIR = _user_data_home() / "xstar-tools"' in text
    assert 'DATAPATH_FILE = (PACKAGE_DIR / "datapath")' not in text


def test_native_platform_policy_is_explicit():
    sys.path.insert(0, str(ROOT))
    try:
        import build_support
        assert build_support._SUPPORTED_NATIVE_SYSTEMS == {"Linux"}
    finally:
        sys.path.remove(str(ROOT))
