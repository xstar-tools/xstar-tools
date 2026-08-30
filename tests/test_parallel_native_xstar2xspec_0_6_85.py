from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_parallel_native_sources_present_and_versioned():
    text = (ROOT / "pyproject.toml").read_text()
    assert 'version = "0.6.86"' in text
    assert (CPP / "xstar_xspec_parallel.cpp").is_file()
    make = (CPP / "Makefile").read_text()
    assert "XSPEC_GRID_EXECUTABLE := $(XSPEC_SERIAL_EXECUTABLE)" in make
    assert "PACKAGE_VERSION ?= 0.6.86" in make
    assert "xstar_xspec_parallel.cpp" in make


def test_parallel_driver_preserves_deterministic_loopcontrol_placement():
    text = (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert '"--workers"' in text
    assert 'const fs::path work_dir = opt.output_dir / "xstar2xspec-work";' in text
    assert 'loopcontrol != job_index' in text
    assert 'completion_order' in text
    assert 'for (const auto &path : spectra) table.push_back(path.string());' in text
    assert 'concatenate_step_logs(steps' in text


def test_parallel_driver_is_bounded_local_process_pool_not_mpi_linkage():
    text = (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert '#include <mpi.h>' not in text
    assert 'spawn_job' in text
    assert 'active.size() < effective_workers' in text
    assert 'waitpid(-1' in text


def test_python_xstar2xspec_and_mpixstar_wrappers_expose_workers():
    pipeline = (ROOT / "src/xstar_tools/tables/pipeline.py").read_text()
    cli = (ROOT / "src/xstar_tools/cli/xstar2xspec.py").read_text()
    mpi = (ROOT / "src/xstar_tools/cli/mpixstar.py").read_text()
    assert "workers: int = 1" in pipeline
    assert '"--workers", str(workers)' in pipeline
    assert 'parser.add_argument("--workers", "-j"' in cli
    assert '"--workers", "--np", "-j"' in mpi
    assert "NotImplementedError" not in mpi


def test_084_serial_reference_source_is_retained():
    serial = CPP / "xstar_xspec_serial.cpp"
    assert serial.is_file()
    text = serial.read_text()
    assert 'constexpr const char *kPackageVersion = "0.6.84";' in text
    assert 'const fs::path work_dir = opt.output_dir / ".xstar2xspec-work";' in text
