from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_apple_warning_helper_uses_position_safe_clang_attribute():
    text = (CPP / "xstar_compiler_warnings.hpp").read_text()
    assert "defined(__APPLE__) && defined(__clang__)" in text
    assert "#define XSTAR_APPLE_MAYBE_UNUSED __attribute__((unused))" in text
    assert "[[maybe_unused]]" not in text
    assert '-Wdeprecated-declarations' in text


def test_no_global_warning_suppression_added():
    makefile = (CPP / "Makefile").read_text()
    for token in ("-Wno-unused-function", "-Wno-unused-variable", "-Wno-unused-const-variable", "-Wno-deprecated-declarations"):
        assert token not in makefile


def test_warning_site_source_contract_remains_annotated():
    checks = {
        "level_population.cpp": ("XSTAR_APPLE_MAYBE_UNUSED inline const double& M(",),
        "opacity_kernels.cpp": (
            "XSTAR_APPLE_MAYBE_UNUSED static inline void voigte_small_a_farwing4(",
            "XSTAR_APPLE_MAYBE_UNUSED static inline void type50_consume_full(",
            "XSTAR_APPLE_MAYBE_UNUSED static std::pair<int,int> small_a_core_bounds_localized_v0682382(",
            "XSTAR_APPLE_MAYBE_UNUSED const bool production_inline_avx2_v064812328",
        ),
        "xstar_science_fits.cpp": ("kErgPerEv", "kFourPi", "kOraclePublicRrcSegments"),
        "xstar_standalone.cpp": ("source_brems_kev_per_t7_v068228", "kV82PublicLineInventory"),
        "xstar_atdb_runtime.cpp": ("kProgramAbi", "kType53LayoutMagic", "kType49LayoutMagic", "kType99LayoutMagic"),
    }
    for name, tokens in checks.items():
        text = (CPP / name).read_text()
        for token in tokens:
            assert token in text, (name, token)


def test_shared_ptr_deprecation_scope_preserved():
    text = (CPP / "local_zone_engine.cpp").read_text()
    assert "#if defined(__APPLE__) && defined(__clang__)" in text
    assert "XSTAR_APPLE_CLANG_IGNORE_DEPRECATED_DECLARATIONS" in text
    assert "} else if (!bound_free_payload_v06823087.unique()) {" in text


def test_attribute_spelling_accepts_existing_function_and_variable_positions():
    clang = shutil.which("clang++")
    if clang is None:
        return
    source = r'''
#include "xstar_compiler_warnings.hpp"
XSTAR_APPLE_MAYBE_UNUSED static inline void dormant_function() {}
XSTAR_APPLE_MAYBE_UNUSED static const bool dormant_flag = true;
int main() { return 0; }
'''
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "smoke.cpp"
        obj = Path(td) / "smoke.o"
        src.write_text(source)
        cp = subprocess.run(
            [clang, "-std=c++17", "-Wall", "-Wextra", "-Wpedantic", "-D__APPLE__", "-I", str(CPP), "-c", str(src), "-o", str(obj)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert cp.returncode == 0, cp.stdout
        assert "warning:" not in cp.stdout, cp.stdout


def test_version_metadata():
    assert 'version = "0.6.88.4.2"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.88.4.2" in (CPP / "Makefile").read_text()
    assert 'kPackageVersion = "0.6.88.4.2"' in (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert 'kPackageVersion = "0.6.88.4.2"' in (CPP / "xstar_xspec_mpi.cpp").read_text()


def test_historical_8841_host_rejection_recorded():
    text = (ROOT / "xstar_tools-0.6.88.4.1_host_rejection.md").read_text()
    assert "macos-15" in text and "ACCEPT" in text
    assert "macos-15-intel" in text and "rejected" in text
    assert "attribute list cannot appear here" in text
