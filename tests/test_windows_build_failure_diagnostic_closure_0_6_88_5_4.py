from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
RUNNER = ROOT / "tools/qualification/run_windows_build_failure_diagnostic_closure_host_0_6_88_5_4.py"


def text(name):
    return (CPP / name).read_text()


def test_version_metadata():
    assert 'version = "0.6.88.5.4"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.88.5.4' in text("Makefile")
    assert 'kPackageVersion = "0.6.88.5.4"' in text("xstar_xspec_parallel.cpp")
    assert 'kPackageVersion = "0.6.88.5.4"' in text("xstar_xspec_mpi.cpp")


def test_known_5_3_portability_fixes_are_preserved():
    local = text("local_zone_engine.cpp")
    assert 'double source_pexs_sigma_mb_generic(int nmin,double zc,double eion,double far_coeff,double gam,double scal,double energy_ryd)' in local
    assert '#if defined(__APPLE__) || defined(_WIN32)' in local
    backend = text("xstar_backend_python.cpp")
    assert 'PyUnicode_FromString(XSTAR_C_PATH(addition))' in backend
    assert 'PyUnicode_FromString(addition.c_str())' not in backend


def test_native_build_diagnostics_are_explicit():
    runner = RUNNER.read_text()
    for token in [
        'WINDOWS_BUILD_RETURN_CODE',
        'WINDOWS_BUILD_LOG_PATH',
        'WINDOWS_BUILD_OUTPUT_CHARS',
        'WINDOWS_BUILD_FAILURE_CONTEXT_BEGIN',
        'WINDOWS_BUILD_FAILURE_CONTEXT_END',
        'WINDOWS_BUILD_LOG_TAIL_BEGIN',
        'WINDOWS_BUILD_LOG_TAIL_END',
        'WINDOWS_BUILD_DIAGNOSTIC_REPLAY_RETURN_CODE',
        'WINDOWS_BUILD_DIAGNOSTIC_REPLAY_LOG_BEGIN',
        'WINDOWS_BUILD_DIAGNOSTIC_REPLAY_LOG_END',
    ]:
        assert token in runner
    assert 'BUILD_DIAGNOSTIC_TAIL_CHARS = 60000' in runner
    assert "run(['make', '-j1', 'all', 'PLATFORM=windows']" in runner
    assert "WINDOWS_BUILD_DIAGNOSTIC_REPLAY=RAN" in runner


def test_build_failure_context_patterns_are_actionable():
    runner = RUNNER.read_text()
    for token in ['error:', 'fatal error', 'undefined reference', 'collect2:', 'make: ***', 'ld.exe', 'cannot find']:
        assert token in runner


def test_build_dependent_gates_skip_instead_of_cascade_reject():
    runner = RUNNER.read_text()
    assert 'SKIP_BUILD_FAILED' in runner
    for gate in [
        'WARNING_FREE_BUILD', 'WINDOWS_TARGETS', 'IMPORT_LIBRARIES', 'PE_FORMAT', 'API_EXPORTS',
        'XSTAR_CPP_VERSION', 'XSTAR_XSPEC_VERSION', 'SIBLING_DISCOVERY', 'PLUGIN_PATH',
        'XSPEC_PROCESS_POOL', 'WINDOWS_REGRESSION'
    ]:
        assert f"skip('{gate}', 'BUILD_FAILED')" in runner


def test_independent_process_evidence_is_preserved():
    runner = RUNNER.read_text()
    assert "gate('PROCESS_SMOKE_BUILD'" in runner
    assert "gate('PROCESS_SMOKE'" in runner
    assert "gate('XSPEC_FAKE_BUILD'" in runner
    assert 'WINDOWS_PROCESS_SMOKE_068854_RESULT=ACCEPT' in (ROOT / 'tests/windows_process_smoke_0_6_88_5_4.cpp').read_text()


def test_predecessor_rejection_and_design_are_recorded():
    ch = (ROOT / 'CHANGELOG.md').read_text()
    assert '0.6.88.5.4 - WINDOWS_BUILD_FAILURE_DIAGNOSTIC_CLOSURE' in ch
    assert (ROOT / 'xstar_tools-0.6.88.5.3_host_rejection.md').is_file()
    assert (ROOT / 'windows_build_failure_diagnostic_closure_0_6_88_5_4.md').is_file()
    assert (ROOT / 'docs/developer/windows_build_failure_diagnostic_closure_0_6_88_5_4.md').is_file()


def test_windows_workflow_uses_5_4_runner():
    wf = (ROOT / '.github/workflows/windows-build.yml').read_text()
    assert 'run_windows_build_failure_diagnostic_closure_host_0_6_88_5_4.py' in wf
    assert 'run_windows_build_failure_diagnostic_closure_068854_host' in wf
    assert 'UCRT64' in wf
    assert 'mingw-w64-ucrt-x86_64-cfitsio' in wf
