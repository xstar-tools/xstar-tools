from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def read(name: str) -> str:
    return (CPP / name).read_text(encoding="utf-8")


def test_portable_dynamic_library_layer_has_posix_and_windows_backends() -> None:
    source = read("xstar_dynamic_library.cpp")
    assert "LoadLibraryW" in source
    assert "dlopen" in source


def test_portable_process_layer_has_posix_and_windows_backends() -> None:
    source = read("xstar_process.hpp")
    assert "CreateProcessW" in source
    assert "fork" in source
    assert "WaitForSingleObject" in source


def test_path_compatibility_boundary_exists_for_narrow_c_apis() -> None:
    source = read("xstar_path_compat.hpp")
    assert "XSTAR_C_PATH" in source
    assert "_WIN32" in source


def test_normal_build_remains_non_mpi_and_mpi_is_explicit() -> None:
    makefile = read("Makefile")
    all_line = next(line for line in makefile.splitlines() if line.startswith("all:"))
    assert "xstar-xspec-mpi" not in all_line
    assert "mpi:" in makefile
    assert "XSPEC_MPI_EXECUTABLE" in makefile
