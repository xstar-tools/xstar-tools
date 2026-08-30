from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_0687_version_and_local_process_cli_contract():
    assert 'version = "0.6.87"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.87" in (CPP / "Makefile").read_text()
    text = (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert '"--processes"' in text
    assert '"--workers"' in text
    assert '"-j"' in text
    assert "std::size_t processes = 1;" in text
    assert "effective_processes" in text


def test_0687_mpi_keeps_np_semantics_separate():
    text = (CPP / "xstar_xspec_mpi.cpp").read_text()
    assert 'arg == "--processes"' in text
    assert "select MPI ranks with mpirun/mpiexec -np N" in text
    assert "MPI_Comm_size" in text


def test_0687_python_api_and_cli_use_processes_canonically():
    pipeline = (ROOT / "src/xstar_tools/tables/pipeline.py").read_text()
    cli = (ROOT / "src/xstar_tools/cli/xstar2xspec.py").read_text()
    assert "processes: int = 1" in pipeline
    assert "workers: int | None = None" in pipeline
    assert '[str(exe), "--output-dir", str(out), "--processes", str(processes)]' in pipeline
    assert 'parser.add_argument("--processes", "--workers", "-j"' in cli


def test_0687_readmes_contain_realistic_direct_examples_and_data_discovery():
    root_readme = (ROOT / "README.md").read_text()
    cpp_readme = (CPP / "README.md").read_text()
    for text in (root_readme, cpp_readme):
        assert "modelname='xstar_pg1211'" in text
        assert "columnnst=9" in text
        assert "rlogxinst=6" in text
        assert "--processes 2" in text
        assert "$HEADAS/refdata" in text
        assert "$XSTAR_DATA" in text
