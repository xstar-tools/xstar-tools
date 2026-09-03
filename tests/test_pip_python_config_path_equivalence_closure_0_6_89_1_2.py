from __future__ import annotations

import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "build_support.py"


def load_support():
    spec = importlib.util.spec_from_file_location("build_support_068912_test", SUPPORT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sibling_discovery_accepts_canonical_path_equivalence(tmp_path: Path) -> None:
    support = load_support()
    real = tmp_path / "real-bin"
    real.mkdir()
    config = real / "python3-config"
    config.write_text("#!/bin/sh\n", encoding="utf-8")
    interpreter = real / "python.exe"
    interpreter.write_bytes(b"")

    alias = tmp_path / "alias-bin"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks unavailable on this host")

    discovered = support._python_config_sibling(str(alias / "python.exe"))
    assert discovered is not None
    assert Path(discovered).resolve() == config.resolve()
    assert Path(discovered).is_file()
    assert "\\" not in discovered


def test_build_support_and_runtime_frozen_hashes() -> None:
    import hashlib
    assert hashlib.sha256(SUPPORT.read_bytes()).hexdigest() == "93fbfcb4987def93853daa1a22c67077f0cc8b6a13b28f2f8d50baf4b546b3f8"
    runtime = ROOT / "src/xstar_tools/native_runtime.py"
    assert hashlib.sha256(runtime.read_bytes()).hexdigest() == "c764699e128f7c0c457124001d26ddafa587859a7e737c417d2b117998ea3bd1"
