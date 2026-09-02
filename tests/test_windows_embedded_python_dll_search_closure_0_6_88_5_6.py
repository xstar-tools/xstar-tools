from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / 'src/xstar_tools/xstar/cpp'
RUNNER = ROOT / 'tools/qualification/run_windows_embedded_python_dll_search_closure_host_0_6_88_5_6.py'


def text(name):
    return (CPP / name).read_text()


def test_version_metadata():
    assert 'version = "0.6.88.5.6"' in (ROOT / 'pyproject.toml').read_text()
    assert 'PACKAGE_VERSION ?= 0.6.88.5.6' in text('Makefile')
    assert 'kPackageVersion = "0.6.88.5.6"' in text('xstar_xspec_parallel.cpp')
    assert 'kPackageVersion = "0.6.88.5.6"' in text('xstar_xspec_mpi.cpp')


def test_windows_dll_search_is_embedder_owned_and_windows_only():
    src = text('xstar_backend_python.cpp')
    helper = src.index('bool ensure_windows_python_dll_search(std::string& error)')
    guard = src.rfind('#if defined(_WIN32)', 0, helper)
    end = src.index('#endif', helper)
    assert guard >= 0 < helper < end
    block = src[guard:end]
    for token in [
        'Py_GetPrefix()', 'L"bin"', 'PyImport_ImportModule("os")',
        'PyObject_GetAttrString(os, "add_dll_directory")',
        'PyObject_SetAttrString(sys, kHandleAttribute, handle)',
        '_xstar_windows_dll_directory_handle',
    ]:
        assert token in block


def test_windows_dll_search_has_prefix_fallback():
    src = text('xstar_backend_python.cpp')
    assert 'if (!std::filesystem::is_directory(dll_directory, ec))' in src
    assert 'dll_directory = prefix;' in src


def test_windows_dll_search_runs_before_python_package_imports():
    src = text('xstar_backend_python.cpp')
    ensure_call = src.index('if (!ensure_windows_python_dll_search(error))')
    sys_path = src.index('PyObject* path = PySys_GetObject("path");')
    package_import = src.index('PyImport_ImportModule("xstar_tools.xstar.standalone_backend")')
    assert ensure_call < sys_path < package_import


def test_windows_dll_search_handle_is_retained_for_interpreter_lifetime():
    src = text('xstar_backend_python.cpp')
    assert 'PyObject_SetAttrString(sys, kHandleAttribute, handle)' in src
    assert 'Py_XDECREF(handle);' in src
    assert 'PyObject_HasAttrString(sys, kHandleAttribute)' in src


def test_5_5_header_fix_and_5_3_portability_fixes_are_preserved():
    parallel = text('xstar_xspec_parallel.cpp')
    guard = parallel.index('#if !defined(_WIN32)')
    for header in ['fstream', 'iostream', 'map', 'sstream', 'stdexcept', 'string', 'vector']:
        assert parallel.index(f'#include <{header}>') < guard
    local = text('local_zone_engine.cpp')
    assert 'far_coeff' in local
    assert '#if defined(__APPLE__) || defined(_WIN32)' in local
    backend = text('xstar_backend_python.cpp')
    assert 'PyUnicode_FromString(XSTAR_C_PATH(addition))' in backend


def test_5_5_host_rejection_is_recorded_as_python_runtime_only_failure():
    record = (ROOT / 'xstar_tools-0.6.88.5.5_host_rejection.md').read_text()
    assert 'historical **Windows HOST REJECT**' in record
    assert 'HOST_WINDOWS_BUILD=ACCEPT' in record
    assert 'HOST_XSPEC_PROCESS_POOL=ACCEPT' in record
    assert 'DLL load failed while importing `_ctypes`' in record
    assert 'fixed-state' in record.lower()


def test_runner_splits_fixed_state_and_python_runtime_gates():
    runner = RUNNER.read_text()
    for token in [
        "gate('PYTHON_RUNTIME_CTYPES_IMPORT'", "gate('FIXED_STATE_SELF_TEST'",
        "gate('FIXED_STATE_BATCH_SELF_TEST'", "gate('FIXED_STATE_OUTPUT'",
        "gate('PYTHON_BACKEND_SELF_TEST'", "gate('PYTHON_BRIDGE_TEST'",
        "gate('WINDOWS_REGRESSION'",
    ]:
        assert token in runner


def test_build_diagnostics_and_process_evidence_remain_preserved():
    runner = RUNNER.read_text()
    for token in [
        'WINDOWS_BUILD_RETURN_CODE', 'WINDOWS_BUILD_FAILURE_CONTEXT_BEGIN',
        'WINDOWS_BUILD_DIAGNOSTIC_REPLAY_RETURN_CODE', 'WINDOWS_BUILD_DIAGNOSTIC_REPLAY_LOG_BEGIN',
        'SKIP_BUILD_FAILED', "gate('PROCESS_SMOKE_BUILD'", "gate('PROCESS_SMOKE'",
        "gate('XSPEC_FAKE_BUILD'", "gate('XSPEC_PROCESS_POOL'",
    ]:
        assert token in runner
    assert 'WINDOWS_PROCESS_SMOKE_068856_RESULT=ACCEPT' in (ROOT / 'tests/windows_process_smoke_0_6_88_5_6.cpp').read_text()


def test_windows_workflow_uses_5_6_runner_without_dependency_workaround():
    wf = (ROOT / '.github/workflows/windows-build.yml').read_text()
    assert 'run_windows_embedded_python_dll_search_closure_host_0_6_88_5_6.py' in wf
    assert 'run_windows_embedded_python_dll_search_closure_068856_host' in wf
    assert 'UCRT64' in wf
    assert 'mingw-w64-ucrt-x86_64-python' in wf
    assert 'mingw-w64-ucrt-x86_64-libffi' not in wf
