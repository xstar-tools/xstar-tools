from __future__ import annotations

import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "build_support.py"


def _support():
    spec = importlib.util.spec_from_file_location("build_support_068911_test", SUPPORT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_metadata() -> None:
    assert 'version = "0.6.89.1.1"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.89.1.1" in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()


def test_extensionless_python_config_sibling(tmp_path: Path) -> None:
    support = _support()
    interpreter = tmp_path / "python.exe"
    interpreter.write_bytes(b"")
    config = tmp_path / "python3-config"
    config.write_text("#!/bin/sh\n")
    assert support._python_config_sibling(str(interpreter)) == config.as_posix()


def test_explicit_python_config_override_has_precedence(monkeypatch) -> None:
    support = _support()
    monkeypatch.setenv("PYTHON_CONFIG", "/chosen/python-config")
    assert support._python_config_tool() == "/chosen/python-config"


def test_normal_which_precedes_sibling(monkeypatch) -> None:
    support = _support()
    monkeypatch.delenv("PYTHON_CONFIG", raising=False)
    monkeypatch.setattr(support.shutil, "which", lambda name: "/path/python3-config" if name == "python3-config" else None)
    monkeypatch.setattr(support, "_python_config_sibling", lambda executable=None: "/sibling/python3-config")
    assert support._python_config_tool() == "/path/python3-config"


def test_mpi_and_atomic_database_policy_unchanged() -> None:
    support = SUPPORT.read_text()
    pyproject = (ROOT / "pyproject.toml").read_text()
    executable_block = support.split("_NATIVE_EXECUTABLE_STEMS", 1)[1].split(")", 1)[0]
    assert "xstar-xspec-mpi" not in executable_block
    assert "atdb.fits" not in pyproject
    assert not (ROOT / "src/xstar_tools/xstar/data/atdb.fits").exists()
