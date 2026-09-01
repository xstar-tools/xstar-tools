from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_version_metadata():
    assert 'version = "0.6.88.5"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.88.5' in (CPP / "Makefile").read_text()
    assert 'kPackageVersion = "0.6.88.5"' in (CPP / "xstar_xspec_parallel.cpp").read_text()


def test_windows_process_backend_is_native_spawn_not_fork_emulation():
    text = (CPP / "xstar_process.hpp").read_text()
    for token in ("CreateProcessW", "WaitForSingleObject", "TerminateProcess", "_getpid", "_putenv_s", "spawn_program"):
        assert token in text
    assert "errno = ENOSYS" in text


def test_windows_pe_import_library_contract():
    text = (CPP / "Makefile").read_text()
    assert "--out-implib,$@.a" in text
    assert "--export-all-symbols" in text
    assert "SHLIB_INSTALL_NAME_MODE ?= pe-import-library" in text
    assert "V0682401_PRODUCTION_COMPILER ?= MINGW64" in text


def test_windows_executable_suffix_is_centralized():
    platform = (CPP / "xstar_platform.hpp").read_text()
    xspec = (CPP / "xstar_xspec_parallel.cpp").read_text()
    frontend = (CPP / "xstar_cpp_frontend.cpp").read_text()
    assert 'kExecutableExtension = ".exe"' in platform
    assert "executable_filename(name)" in xspec
    assert 'executable_filename("xstar_cpp")' in frontend


def test_windows_xspec_uses_spawn_program():
    text = (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert "#if defined(_WIN32)" in text
    assert text.count("xstar_process::spawn_program") >= 2
    assert "xstar_process::wait_process(-1" in text


def test_windows_mpi_stays_out_of_scope():
    text = (CPP / "Makefile").read_text()
    assert 'xstar-xspec-mpi is not supported on PLATFORM=windows' in text


def test_windows_backend_exports_do_not_reuse_api_dllimport():
    backend = (CPP / "xstar_backend_plugin.h").read_text()
    bridge = (CPP / "xstar_python_bridge.h").read_text()
    assert "XSTAR_BACKEND_EXPORT" in backend
    assert "XSTAR_PYTHON_BRIDGE_EXPORT" in bridge
    assert "XSTAR_API_EXPORT const xstar_backend_descriptor" not in backend


def test_no_windows_rpath_generation():
    text = (CPP / "Makefile").read_text()
    assert "ifneq ($(PLATFORM),windows)" in text
    assert "PYTHON_RPATHS :=" in text
