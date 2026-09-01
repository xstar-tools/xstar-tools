import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"

def text(name):
    return (CPP / name).read_text()

def test_version_metadata():
    assert 'version = "0.6.88.5.2"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.88.5.2' in text("Makefile")
    assert 'kPackageVersion = "0.6.88.5.2"' in text("xstar_xspec_parallel.cpp")
    assert 'kPackageVersion = "0.6.88.5.2"' in text("xstar_xspec_mpi.cpp")

def test_two_host_reported_path_boundaries_are_closed():
    s = text("xstar_standalone.cpp")
    assert 'context, XSTAR_C_PATH(output), &stats, message.data(), message.size());' in s
    assert 'context, XSTAR_C_PATH(outdir / "visited_records.csv"), message.data(), message.size());' in s
    assert 'context, output.c_str(), &stats, message.data(), message.size());' not in s
    assert '(outdir / "visited_records.csv").c_str()' not in s

def test_filesystem_path_direct_cstr_audit():
    s = text("xstar_standalone.cpp")
    names = set(re.findall(r'(?:std::filesystem::path|fs::path)\s+([A-Za-z_][A-Za-z0-9_]*)', s))
    direct = [name for name in names if re.search(r'\b' + re.escape(name) + r'\.c_str\s*\(', s)]
    assert direct == []
    bad_join = [line for line in s.splitlines() if ' / ' in line and '.c_str()' in line and '.string().c_str()' not in line]
    assert bad_join == []

def test_mingw_misleading_indentation_sites_closed():
    h = text("xstar_process.hpp")
    assert 'if (wr==WAIT_TIMEOUT) return 0; if (wr!=WAIT_OBJECT_0)' not in h
    assert 'if(!overwrite && std::getenv(name)!=nullptr) return 0; return ::_putenv_s' not in h
    assert 'if (wr == WAIT_TIMEOUT) return 0;\n            if (wr != WAIT_OBJECT_0)' in h
    assert 'if (!overwrite && std::getenv(name) != nullptr) return 0;\n    return ::_putenv_s(name,value);' in h

def test_win32_process_backend_preserved():
    h = text("xstar_process.hpp")
    for token in ["CreateProcessW", "WaitForSingleObject", "TerminateProcess", "spawn_program", "_putenv_s"]:
        assert token in h
    assert "fork_process()" in h and "ENOSYS" in h

def test_path_adapter_and_windows_link_contract_preserved():
    h = text("xstar_path_compat.hpp")
    assert '#define XSTAR_C_PATH(expr) ((expr).string().c_str())' in h
    assert '#define XSTAR_C_PATH(expr) ((expr).c_str())' in h
    mk = text("Makefile")
    assert "--out-implib,$@.a" in mk
    assert "ifeq ($(PLATFORM),windows)\n  PYTHON_RPATHS :=\nendif" in mk
    assert "xstar-xspec-mpi is not supported on PLATFORM=windows" in mk

def test_host_rejection_and_scheduler_path_recorded():
    ch = (ROOT / "CHANGELOG.md").read_text()
    assert "0.6.88.5.2 - WINDOWS_PATH_BOUNDARY_COMPLETION" in ch
    assert (ROOT / "xstar_tools-0.6.88.5.1_host_rejection.md").is_file()
    runner = (ROOT / "tools/qualification/run_windows_path_boundary_completion_host_0_6_88_5_2.py").read_text()
    assert "xstar2xspec_scheduler.log" in runner
    assert "xstar2xspec-work/scheduler.log" not in runner

def test_windows_workflow_uses_5_2_runner():
    wf = (ROOT / ".github/workflows/windows-build.yml").read_text()
    assert "run_windows_path_boundary_completion_host_0_6_88_5_2.py" in wf
    assert "UCRT64" in wf
    assert "mingw-w64-ucrt-x86_64-cfitsio" in wf
