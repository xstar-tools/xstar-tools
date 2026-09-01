from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def text(name):
    return (CPP / name).read_text()


def test_version_metadata():
    assert 'version = "0.6.88.5.1"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.88.5.1' in text("Makefile")
    assert 'kPackageVersion = "0.6.88.5.1"' in text("xstar_xspec_parallel.cpp")
    assert 'kPackageVersion = "0.6.88.5.1"' in text("xstar_xspec_mpi.cpp")


def test_path_adapter_is_windows_only():
    h = text("xstar_path_compat.hpp")
    assert "#if defined(_WIN32)" in h
    assert "#define XSTAR_C_PATH(expr) ((expr).string().c_str())" in h
    assert "#define XSTAR_C_PATH(expr) ((expr).c_str())" in h


def test_reported_failing_boundaries_use_adapter():
    standalone = text("xstar_standalone.cpp")
    science = text("xstar_science_fits.cpp")
    step = text("xstar_step_log.cpp")
    assert 'XSTAR_C_PATH(output_root / "native_thermal_budget.csv")' in standalone
    assert "XSTAR_C_PATH(diagnostics_root)" in standalone
    assert 'XSTAR_C_PATH(std::filesystem::path(options.output_dir) / "visited_records.csv")' in standalone
    assert "XSTAR_C_PATH(item.second)" in standalone
    assert "fits_open_file(&fptr, XSTAR_C_PATH(atdb)" in science
    for token in ["XSTAR_C_PATH(atdb)", "XSTAR_C_PATH(abundance_path)", "XSTAR_C_PATH(detail_path)",
                  "XSTAR_C_PATH(final_line_detail_path_v0682279)", "XSTAR_C_PATH(output_dir/\"xout_abund1.fits\")",
                  "XSTAR_C_PATH(detail_path_v0682277)"]:
        assert token in step


def test_win32_process_backend_preserved():
    h = text("xstar_process.hpp")
    for token in ["CreateProcessW", "WaitForSingleObject", "TerminateProcess", "spawn_program", "_putenv_s"]:
        assert token in h
    assert "fork_process()" in h and "ENOSYS" in h


def test_windows_link_contract():
    mk = text("Makefile")
    assert "--out-implib,$@.a" in mk
    assert "WINDOWS_PRODUCTION_ZONE_DEFINE := -DXSTAR_PRODUCTION_ZONE_BUILD" in mk
    assert "WINDOWS_BACKEND_DEFINE := -DXSTAR_BACKEND_BUILD" in mk
    assert "WINDOWS_PYTHON_BACKEND_DEFINE := -DXSTAR_PYTHON_BACKEND_BUILD" in mk
    assert "ifeq ($(PLATFORM),windows)\n  PYTHON_RPATHS :=\nendif" in mk


def test_windows_mpi_remains_out_of_scope():
    mk = text("Makefile")
    assert "xstar-xspec-mpi is not supported on PLATFORM=windows" in mk


def test_host_rejection_recorded():
    ch = (ROOT / "CHANGELOG.md").read_text()
    assert "0.6.88.5.1 - WINDOWS_PATH_ENCODING_CLOSURE" in ch
    assert (ROOT / "xstar_tools-0.6.88.5_host_rejection.md").is_file()


def test_windows_workflow_uses_closure_runner():
    wf = (ROOT / ".github/workflows/windows-build.yml").read_text()
    assert "run_windows_path_encoding_closure_host_0_6_88_5_1.py" in wf
    assert "UCRT64" in wf
    assert "mingw-w64-ucrt-x86_64-cfitsio" in wf
