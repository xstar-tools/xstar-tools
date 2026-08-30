from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_0686_mpi_source_and_opt_in_make_target():
    make = (CPP / "Makefile").read_text()
    assert (CPP / "xstar_xspec_mpi.cpp").is_file()
    assert "MPICXX ?= mpic++" in make
    assert "mpi: $(XSPEC_MPI_EXECUTABLE)" in make
    assert "MPI_TARGETS := $(XSPEC_MPI_EXECUTABLE)" in make
    assert "TARGETS := $(PHYSICS_TARGETS) $(STANDALONE_TARGETS)" in make


def test_0686_true_mpi_uses_ranks_not_local_workers():
    text = (CPP / "xstar_xspec_mpi.cpp").read_text()
    assert "#include <mpi.h>" in text
    assert "MPI_Comm_rank" in text
    assert "MPI_Comm_size" in text
    assert "MPI_Fetch_and_op" in text
    assert "select MPI ranks with mpirun/mpiexec -np N" in text
    assert "xstar-xspec-table" in text


def test_0686_true_mpi_preserves_loopcontrol_and_failure_products():
    text = (CPP / "xstar_xspec_mpi.cpp").read_text()
    assert "loopcontrol != job_index" in text
    assert "for (const auto &path : spectra) table.push_back(path.string());" in text
    assert 'job_dir / "xstar-cpp.success"' in text
    assert "fs::remove(success_marker" in text
    assert "remove_all" in text  # only explicit --cleanup-work path
    assert "--cleanup-work" in text


def test_0686_docs_explain_process_vs_mpi_concurrency():
    root_readme = (ROOT / "README.md").read_text()
    cpp_readme = (CPP / "README.md").read_text()
    assert "two simultaneous `xstar-cpp` OS processes" in root_readme
    assert "make -C src/xstar_tools/xstar/cpp mpi" in root_readme
    assert "mpirun -np 4" in root_readme
    assert "Two simultaneous XSTAR processes" in cpp_readme and "process parallelism" in cpp_readme
