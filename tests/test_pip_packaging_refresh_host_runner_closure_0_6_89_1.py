from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/qualification/run_pip_packaging_refresh_host_runner_closure_host_0_6_89_1.py"


def _runner():
    spec = importlib.util.spec_from_file_location("pip_runner_06891_test", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_metadata() -> None:
    assert 'version = "0.6.89.1"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.89.1" in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()


def test_wheel_member_prefix_does_not_require_leading_slash() -> None:
    runner = _runner()
    names = {
        "xstar_tools/xstar/cpp/libxstar_api.so",
        "xstar_tools/xstar/cpp/libxstar_production_zone.so",
        "xstar_tools/xstar/cpp/xstar-cpp",
        "xstar_tools/xstar/cpp/xstar-xspec-initable",
        "xstar_tools/xstar/cpp/xstar-xspec-table",
        "xstar_tools/xstar/cpp/xstar-xspec",
    }
    basenames = runner.packaged_cpp_basenames(names)
    assert basenames == {
        "libxstar_api.so",
        "libxstar_production_zone.so",
        "xstar-cpp",
        "xstar-xspec-initable",
        "xstar-xspec-table",
        "xstar-xspec",
    }


def test_unrelated_or_similar_paths_are_not_counted() -> None:
    runner = _runner()
    names = {
        "prefix/xstar_tools/xstar/cpp/libxstar_api.so",
        "xstar_tools/xstar/cppish/xstar-xspec",
        "xstar_tools/xstar/cpp/xstar-xspec",
    }
    assert runner.packaged_cpp_basenames(names) == {"xstar-xspec"}


def test_historical_bug_pattern_is_not_reintroduced() -> None:
    text = RUNNER.read_text()
    assert '"/xstar_tools/xstar/cpp/" in' not in text
    assert "PurePosixPath" in text
