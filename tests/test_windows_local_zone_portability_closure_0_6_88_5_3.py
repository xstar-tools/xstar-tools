import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"

def text(name):
    return (CPP / name).read_text()

def test_version_metadata():
    assert 'version = "0.6.88.5.3"' in (ROOT / "pyproject.toml").read_text()
    assert 'PACKAGE_VERSION ?= 0.6.88.5.3' in text("Makefile")
    assert 'kPackageVersion = "0.6.88.5.3"' in text("xstar_xspec_parallel.cpp")
    assert 'kPackageVersion = "0.6.88.5.3"' in text("xstar_xspec_mpi.cpp")

def test_type85_far_identifier_is_portable_without_arithmetic_change():
    s = text("local_zone_engine.cpp")
    assert 'source_pexs_sigma_mb_generic(int nmin,double zc,double eion,double far_coeff,double gam,double scal,double energy_ryd)' in s
    assert 'area[n]=8.06725*far_coeff*std::pow(static_cast<double>(nmin),3)/std::pow(static_cast<double>(n),3)' in s
    assert 'double zc=id3-114,eion=r[1],far_coeff=r[2],gam=r[3],scal=r[4]' in s
    assert 'source_pexs_sigma_mb_generic(nmin,zc,eion,far_coeff,gam,scal,epi[k]/13.605692)' in s
    assert 'double source_pexs_sigma_mb_generic(int nmin,double zc,double eion,double far,double gam' not in s
    assert 'double zc=id3-114,eion=r[1],far=r[2],gam=r[3]' not in s

def test_type77_exact_exp10_portability_branch_includes_windows():
    s = text("local_zone_engine.cpp")
    needle = '#if defined(__APPLE__) || defined(_WIN32)\n        downward=0x1.c2ccf22133138p-4;\n#else\n        downward=::exp10(rec);\n#endif'
    assert needle in s
    assert 'if (rec == -0.958375491843708)' in s
    assert 'downward=source_runtime_pow10(rec);' in s

def test_python_backend_path_uses_narrow_adapter():
    s = text("xstar_backend_python.cpp")
    assert '#include "xstar_path_compat.hpp"' in s
    assert 'PyObject* text = PyUnicode_FromString(XSTAR_C_PATH(addition));' in s
    assert 'PyUnicode_FromString(addition.c_str())' not in s

def test_path_audit_covers_standalone_and_python_backend():
    standalone = text("xstar_standalone.cpp")
    names = set(re.findall(r'(?:std::filesystem::path|fs::path)\s+([A-Za-z_][A-Za-z0-9_]*)', standalone))
    direct = [name for name in names if re.search(r'\b' + re.escape(name) + r'\.c_str\s*\(', standalone)]
    assert direct == []
    bad_join = [line for line in standalone.splitlines() if ' / ' in line and '.c_str()' in line and '.string().c_str()' not in line]
    assert bad_join == []
    py = text("xstar_backend_python.cpp")
    assert 'addition.c_str()' not in py
    assert 'XSTAR_C_PATH(addition)' in py

def test_process_and_path_compatibility_contracts_are_preserved():
    process = text("xstar_process.hpp")
    for token in ["CreateProcessW", "WaitForSingleObject", "TerminateProcess", "spawn_program", "_putenv_s"]:
        assert token in process
    helper = text("xstar_path_compat.hpp")
    assert '#define XSTAR_C_PATH(expr) ((expr).string().c_str())' in helper
    assert '#define XSTAR_C_PATH(expr) ((expr).c_str())' in helper
    mk = text("Makefile")
    assert "xstar-xspec-mpi is not supported on PLATFORM=windows" in mk

def test_predecessor_rejection_and_pool_diagnostics_recorded():
    ch = (ROOT / "CHANGELOG.md").read_text()
    assert "0.6.88.5.3 - WINDOWS_LOCAL_ZONE_PORTABILITY_CLOSURE" in ch
    assert (ROOT / "xstar_tools-0.6.88.5.2_host_rejection.md").is_file()
    runner = (ROOT / "tools/qualification/run_windows_local_zone_portability_closure_host_0_6_88_5_3.py").read_text()
    assert "XSPEC_POOL_PREDICATE_" in runner
    for token in ["'RETURN_CODE'", "'RESULT_MARKER'", "'MAX_ACTIVE'", "'JOBS_TOTAL'", "'SUCCESS_MARKERS'", "XSPEC_PROCESS_POOL_TREE_BEGIN", "XSPEC_JOB_LOG_BEGIN"]:
        assert token in runner

def test_windows_workflow_uses_5_3_runner():
    wf = (ROOT / ".github/workflows/windows-build.yml").read_text()
    assert "run_windows_local_zone_portability_closure_host_0_6_88_5_3.py" in wf
    assert "UCRT64" in wf
    assert "mingw-w64-ucrt-x86_64-cfitsio" in wf
