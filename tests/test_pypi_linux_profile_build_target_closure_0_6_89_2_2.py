from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def load_support():
    spec = importlib.util.spec_from_file_location("build_support_068922_test", ROOT / "build_support.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dry(target: str) -> str:
    proc = subprocess.run(
        ["make", "-n", "-C", str(CPP), "PLATFORM=linux", "PYTHON_CONFIG=true", "PKG_CONFIG=true", target],
        text=True, capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout + proc.stderr


def test_profile_make_target_mapping():
    m = load_support()
    assert m._native_make_target("full") == "all"
    assert m._native_make_target("pypi-linux") == "pypi-linux"


def test_pypi_target_omits_python_embedding_plugin():
    out = dry("pypi-linux")
    assert "libxstar_backend_python" not in out
    assert "-lpython" not in out


def test_pypi_target_omits_mpi():
    assert "xstar-xspec-mpi" not in dry("pypi-linux")


def test_pypi_target_retains_public_runtime():
    out = dry("pypi-linux")
    for token in (
        "libxstar_api.so", "libxstar_backend_cpp.so", "libxstar_production_zone.so",
        "xstar-cpp", "xstar-xspec-initable", "xstar-xspec-table", "xstar-xspec",
    ):
        assert token in out


def test_full_target_still_builds_python_embedding_plugin():
    assert "libxstar_backend_python.so" in dry("all")


def test_pypi_artifact_contract_matches_build_target():
    m = load_support()
    artifacts = set(m._native_artifacts("Linux", profile="pypi-linux"))
    assert "libxstar_backend_python.so" not in artifacts
    assert {"libxstar_api.so", "libxstar_backend_cpp.so", "xstar-cpp", "xstar-xspec"} <= artifacts
