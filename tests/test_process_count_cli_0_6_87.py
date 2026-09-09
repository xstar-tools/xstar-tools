from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"




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


