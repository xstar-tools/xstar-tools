from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_process_header_exists_and_is_in_makefile():
    assert (CPP / "xstar_process.hpp").is_file()
    text = (CPP / "Makefile").read_text()
    assert "xstar_process.hpp" in text


def test_posix_primitives_are_centralized():
    forbidden = ("::fork(", "::execv(", "::execvp(", "::waitpid(", "::kill(", "::getpid(", "::setenv(", "::unsetenv(")
    offenders = []
    for path in CPP.iterdir():
        if path.name == "xstar_process.hpp" or path.suffix not in {".cpp", ".hpp", ".h"}:
            continue
        text = path.read_text(errors="ignore")
        for token in forbidden:
            if token in text:
                offenders.append((path.name, token))
    assert not offenders, offenders


def test_posix_backend_preserves_native_calls():
    text = (CPP / "xstar_process.hpp").read_text()
    for token in ("return ::fork();", "::execvp(path, argv)", "::execv(path, argv)",
                  "return ::waitpid(pid, status, options);", "::kill(pid, SIGTERM)",
                  "::kill(pid, SIGKILL)", "::getpid()", "::setenv(name, value, overwrite)",
                  "::unsetenv(name)"):
        assert token in text


def test_windows_backend_is_explicitly_deferred():
    text = (CPP / "xstar_process.hpp").read_text()
    assert "defined(_WIN32)" in text
    assert "ENOSYS" in text
    assert "::_getpid()" in text
    assert "::_putenv_s" in text


def test_frontend_no_longer_has_posix_exec_compile_gate():
    text = (CPP / "xstar_cpp_frontend.cpp").read_text()
    assert "currently requires a POSIX execv environment" not in text
    assert "xstar_process::fork_process" in text
    assert "xstar_process::exec_program" in text
    assert "xstar_process::wait_process" in text


def test_parallel_scheduler_uses_process_layer():
    text = (CPP / "xstar_xspec_parallel.cpp").read_text()
    for token in ("xstar_process::fork_process", "xstar_process::exec_program",
                  "xstar_process::wait_process", "xstar_process::terminate_process"):
        assert token in text


def test_mpi_scheduler_uses_process_layer():
    text = (CPP / "xstar_xspec_mpi.cpp").read_text()
    for token in ("xstar_process::fork_process", "xstar_process::exec_program",
                  "xstar_process::wait_process", "xstar_process::terminate_process",
                  "xstar_process::force_kill_process"):
        assert token in text


def test_environment_mutation_uses_process_layer():
    for name in ("xstar_cpp_frontend.cpp", "xstar_standalone.cpp", "xstar_science_fits.cpp",
                 "local_zone_engine.cpp", "final_recompute_bridge.cpp"):
        text = (CPP / name).read_text()
        assert "xstar_process::set_environment" in text or "xstar_process::unset_environment" in text
        assert "::setenv(" not in text
        assert "::unsetenv(" not in text
