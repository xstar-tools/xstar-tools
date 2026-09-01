from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / 'src/xstar_tools/xstar/cpp'
RUNNER = ROOT / 'tools/qualification/run_windows_xspec_standard_header_closure_host_0_6_88_5_5.py'


def text(name):
    return (CPP / name).read_text()


def test_version_metadata():
    assert 'version = "0.6.88.5.5"' in (ROOT / 'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.88.5.5' in text('Makefile')
    assert 'kPackageVersion = "0.6.88.5.5"' in text('xstar_xspec_parallel.cpp')
    assert 'kPackageVersion = "0.6.88.5.5"' in text('xstar_xspec_mpi.cpp')


def test_portable_standard_headers_are_not_windows_excluded():
    src = text('xstar_xspec_parallel.cpp')
    guard = src.index('#if !defined(_WIN32)')
    for header in ['fstream', 'iostream', 'map', 'sstream', 'stdexcept', 'string', 'vector']:
        assert src.index(f'#include <{header}>') < guard


def test_only_posix_headers_remain_in_windows_guard():
    src = text('xstar_xspec_parallel.cpp')
    guard = src.index('#if !defined(_WIN32)')
    end = src.index('#endif', guard)
    block = src[guard:end]
    for header in ['fcntl.h', 'signal.h', 'sys/types.h', 'sys/wait.h', 'unistd.h']:
        assert f'#include <{header}>' in block
    for header in ['fstream', 'iostream', 'map', 'sstream', 'stdexcept', 'string', 'vector']:
        assert f'#include <{header}>' not in block


def test_usage_sites_responsible_for_5_4_failure_are_preserved():
    src = text('xstar_xspec_parallel.cpp')
    assert 'std::ofstream success(success_markers[job_index - 1], std::ios::out | std::ios::trunc);' in src
    assert 'std::cout << "XSTAR_XSPEC_06851_JOBS="' in src


def test_known_5_3_portability_fixes_are_preserved():
    local = text('local_zone_engine.cpp')
    assert 'far_coeff' in local
    assert '#if defined(__APPLE__) || defined(_WIN32)' in local
    backend = text('xstar_backend_python.cpp')
    assert 'PyUnicode_FromString(XSTAR_C_PATH(addition))' in backend


def test_5_4_host_rejection_is_recorded():
    record = (ROOT / 'xstar_tools-0.6.88.5.4_host_rejection.md').read_text()
    assert 'historical **Windows HOST REJECT**' in record
    assert 'xstar_xspec_parallel.cpp' in record
    assert '<fstream>' in record
    assert '<iostream>' in record
    assert 'return code `2`' in record


def test_diagnostic_runner_is_preserved_for_next_host_run():
    runner = RUNNER.read_text()
    for token in [
        'WINDOWS_BUILD_RETURN_CODE', 'WINDOWS_BUILD_FAILURE_CONTEXT_BEGIN',
        'WINDOWS_BUILD_DIAGNOSTIC_REPLAY_RETURN_CODE', 'WINDOWS_BUILD_DIAGNOSTIC_REPLAY_LOG_BEGIN',
        'SKIP_BUILD_FAILED', "run(['make', '-j1', 'all', 'PLATFORM=windows']",
    ]:
        assert token in runner


def test_process_evidence_stays_independent():
    runner = RUNNER.read_text()
    assert "gate('PROCESS_SMOKE_BUILD'" in runner
    assert "gate('PROCESS_SMOKE'" in runner
    assert "gate('XSPEC_FAKE_BUILD'" in runner
    assert 'WINDOWS_PROCESS_SMOKE_068855_RESULT=ACCEPT' in (ROOT / 'tests/windows_process_smoke_0_6_88_5_5.cpp').read_text()


def test_windows_workflow_uses_5_5_runner():
    wf = (ROOT / '.github/workflows/windows-build.yml').read_text()
    assert 'run_windows_xspec_standard_header_closure_host_0_6_88_5_5.py' in wf
    assert 'run_windows_xspec_standard_header_closure_068855_host' in wf
    assert 'UCRT64' in wf
    assert 'mingw-w64-ucrt-x86_64-cfitsio' in wf
