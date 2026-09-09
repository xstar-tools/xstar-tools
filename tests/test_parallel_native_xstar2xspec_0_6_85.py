from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"




def test_parallel_driver_preserves_deterministic_loopcontrol_placement():
    text = (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert '"--processes"' in text
    assert '"--workers"' in text  # compatibility alias
    assert 'const fs::path work_dir = opt.output_dir / "xstar2xspec-work";' in text
    assert 'loopcontrol != job_index' in text
    assert 'completion_order' in text
    assert 'for (const auto &path : spectra) table.push_back(path.string());' in text
    assert 'concatenate_step_logs(steps' in text




def test_python_xstar2xspec_and_mpixstar_wrappers_expose_processes_with_legacy_aliases():
    pipeline = (ROOT / "src/xstar_tools/tables/pipeline.py").read_text()
    cli = (ROOT / "src/xstar_tools/cli/xstar2xspec.py").read_text()
    mpi = (ROOT / "src/xstar_tools/cli/mpixstar.py").read_text()
    assert "processes: int = 1" in pipeline
    assert "workers: int | None = None" in pipeline
    assert '"--processes", str(processes)' in pipeline
    assert 'parser.add_argument("--processes", "--workers", "-j"' in cli
    assert '"--processes", "--workers", "--np", "-j"' in mpi
    assert "NotImplementedError" not in mpi


def test_084_serial_reference_source_is_retained():
    serial = CPP / "xstar_xspec_serial.cpp"
    assert serial.is_file()
    text = serial.read_text()
    assert 'constexpr const char *kPackageVersion = "0.6.84";' in text
    assert 'const fs::path work_dir = opt.output_dir / ".xstar2xspec-work";' in text
