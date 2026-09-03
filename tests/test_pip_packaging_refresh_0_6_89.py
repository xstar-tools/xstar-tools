from __future__ import annotations

import importlib.util
from pathlib import Path

import xstar_tools.native_runtime as runtime

ROOT = Path(__file__).resolve().parents[1]


def _build_support():
    path = ROOT / "build_support.py"
    spec = importlib.util.spec_from_file_location("xstar_tools_build_support_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_and_console_scripts() -> None:
    text = (ROOT / "pyproject.toml").read_text()
    assert 'version = "0.6.89"' in text
    assert 'xstar-cpp = "xstar_tools.cli.xstar_cpp:main"' in text
    assert 'xstar-xspec-initable = "xstar_tools.cli.native_exec:main_xstar_xspec_initable"' in text
    assert 'xstar-xspec-table = "xstar_tools.cli.native_exec:main_xstar_xspec_table"' in text
    assert 'xstar-xspec = "xstar_tools.cli.native_exec:main_xstar_xspec"' in text


def test_platform_neutral_artifact_sets_exclude_mpi() -> None:
    support = _build_support()
    assert support._SUPPORTED_NATIVE_SYSTEMS == {"Linux", "Darwin", "Windows"}
    expected = {
        "Linux": (".so", ""),
        "Darwin": (".dylib", ""),
        "Windows": (".dll", ".exe"),
    }
    for system, (lib_suffix, exe_suffix) in expected.items():
        artifacts = set(support._native_artifacts(system))
        assert f"libxstar_api{lib_suffix}" in artifacts
        assert f"libxstar_production_zone{lib_suffix}" in artifacts
        assert f"xstar-cpp{exe_suffix}" in artifacts
        assert f"xstar-xspec-initable{exe_suffix}" in artifacts
        assert f"xstar-xspec-table{exe_suffix}" in artifacts
        assert f"xstar-xspec{exe_suffix}" in artifacts
        assert f"xstar-xspec-mpi{exe_suffix}" not in artifacts


def test_runtime_name_contract() -> None:
    assert runtime.native_library_filename("xstar_api", system="Linux") == "libxstar_api.so"
    assert runtime.native_library_filename("xstar_api", system="Darwin") == "libxstar_api.dylib"
    assert runtime.native_library_filename("xstar_api", system="Windows") == "libxstar_api.dll"
    assert runtime.native_executable_filename("xstar-xspec", system="Linux") == "xstar-xspec"
    assert runtime.native_executable_filename("xstar-xspec", system="Windows") == "xstar-xspec.exe"


def test_atdb_remains_external_and_mpi_remains_opt_in() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text()
    support = (ROOT / "build_support.py").read_text()
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    assert "atdb.fits" not in pyproject
    assert not (ROOT / "src/xstar_tools/xstar/data/atdb.fits").exists()
    assert '"atomic_database_bundled": False' in support
    assert '"xstar-xspec-mpi"' not in support.split("_NATIVE_EXECUTABLE_STEMS", 1)[1].split(")", 1)[0]
    assert "all: $(TARGETS)" in makefile
    assert "MPI_TARGETS := $(XSPEC_MPI_EXECUTABLE)" in makefile


def test_python_native_loaders_use_central_runtime_resolver() -> None:
    files = [
        "src/xstar_tools/execution.py",
        "src/xstar_tools/xstar/compiled_case.py",
        "src/xstar_tools/xstar/cpp_backend_element.py",
        "src/xstar_tools/xstar/cpp_backend_emissivity.py",
        "src/xstar_tools/xstar/cpp_backend_extra.py",
        "src/xstar_tools/xstar/cpp_backend_final_recompute.py",
        "src/xstar_tools/xstar/cpp_backend_matrix.py",
        "src/xstar_tools/xstar/cpp_backend_production_zone.py",
        "src/xstar_tools/xstar/cpp_backend_rates.py",
        "src/xstar_tools/xstar/cpp_backend_spectral.py",
        "src/xstar_tools/xstar/cpp_backend_thermal.py",
        "src/xstar_tools/xstar/solver_backend.py",
    ]
    for name in files:
        text = (ROOT / name).read_text()
        assert "native_runtime" in text, name
        assert '/ "libxstar_' not in text, name
    helper = (ROOT / "src/xstar_tools/native_runtime.py").read_text()
    assert "os.add_dll_directory" in helper
    assert "Package-local candidates precede" in helper
