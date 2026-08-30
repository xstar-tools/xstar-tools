from __future__ import annotations

import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
OLD_FIXTURE = ROOT / "tests/fixtures/historical/v06485_active_family_phase2_fixture"
NEW_FIXTURE = ROOT / "tests/fixtures/historical/v06486_active_family_phase2_fixture"
CALLERS = [
    CPP / "xstar_api.cpp",
    CPP / "xstar_backend_cpp.cpp",
    CPP / "xstar_standalone.cpp",
    CPP / "xstar_standalone_internal.hpp",
]
RAW_FIXTURE_PAYLOAD = ["rows.csv", "records.csv", "elements.csv", "ints.txt", "reals.txt"]


def make_config() -> dict[str, str]:
    cp = subprocess.run(
        ["make", "-s", "print-config", "PLATFORM=linux"],
        cwd=CPP, text=True, capture_output=True, check=True,
    )
    out: dict[str, str] = {}
    for line in cp.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
    return out


def test_version_and_closure_files_present() -> None:
    assert 'version = "0.6.88.2.1"' in (ROOT / "pyproject.toml").read_text()
    makefile = (CPP / "Makefile").read_text()
    assert "PACKAGE_VERSION ?= 0.6.88.2.1" in makefile
    assert "v06486_active_family_phase2_fixture" in makefile
    assert (ROOT / "portable_dynamic_library_layer_qualification_closure_0_6_88_2_1.md").is_file()
    assert NEW_FIXTURE.is_dir()


def test_dynamic_library_contract_remains_present() -> None:
    platform = (CPP / "xstar_platform.hpp").read_text()
    wrapper = (CPP / "xstar_dynamic_library.cpp").read_text()
    assert 'kSharedLibraryExtension = ".so"' in platform
    assert 'kSharedLibraryExtension = ".dylib"' in platform
    assert 'kSharedLibraryExtension = ".dll"' in platform
    assert "LoadLibraryW" in wrapper
    assert "GetProcAddress" in wrapper
    assert "FreeLibrary" in wrapper
    for path in CALLERS:
        text = path.read_text()
        for token in ("dlopen(", "dlsym(", "dlclose(", "dlerror(", "dladdr("):
            assert token not in text
        assert '.so"' not in text


def test_linux_loader_smoke_uses_platform_filesystem_libraries() -> None:
    cfg = make_config()
    filesystem_libs = shlex.split(cfg.get("FILESYSTEM_LIBS", ""))
    assert filesystem_libs == ["-lstdc++fs"], cfg

    with tempfile.TemporaryDirectory(prefix="xstar_dyn_08821_") as td:
        td_path = Path(td)
        plugin = td_path / "plugin.cpp"
        test = td_path / "test.cpp"
        library = td_path / "libxstar_test.so"
        exe = td_path / "test"
        plugin.write_text('extern "C" int xstar_test_symbol(void) { return 8821; }\n')
        test.write_text(
            '#include "xstar_platform.hpp"\n'
            '#include "xstar_dynamic_library.hpp"\n'
            'using fn = int (*)();\n'
            'int main(int argc, char** argv) {\n'
            '  if (argc != 2) return 2;\n'
            '  if (xstar_platform::shared_library_filename("xstar_test") != "libxstar_test.so") return 3;\n'
            "  if (xstar_platform::path_list_separator() != ':') return 4;\n"
            '  auto h = xstar_platform::dynamic_library_open(argv[1], xstar_platform::DynamicLibraryVisibility::local);\n'
            '  if (!h) return 5;\n'
            '  auto f = reinterpret_cast<fn>(xstar_platform::dynamic_library_symbol(h, "xstar_test_symbol"));\n'
            '  if (!f || f() != 8821) return 6;\n'
            '  if (xstar_platform::module_directory(reinterpret_cast<const void*>(&main)).empty()) return 7;\n'
            '  xstar_platform::dynamic_library_close(h);\n'
            '  return 0;\n'
            '}\n'
        )
        subprocess.run(
            ["g++", "-std=c++17", "-fPIC", "-shared", "-o", str(library), str(plugin)],
            check=True, text=True, capture_output=True,
        )
        subprocess.run(
            ["g++", "-std=c++17", f"-I{CPP}", "-o", str(exe), str(test),
             str(CPP / "xstar_dynamic_library.cpp"), "-ldl", *filesystem_libs],
            check=True, text=True, capture_output=True,
        )
        cp = subprocess.run([str(exe), str(library)], text=True, capture_output=True)
        assert cp.returncode == 0, cp.stderr


def test_60486_fixture_metadata_and_payload() -> None:
    manifest = (NEW_FIXTURE / "manifest.txt").read_text()
    assert "program_abi=60486" in manifest
    assert "program_id=v06486_active_family_phase2_fixture" in manifest
    coverage = (NEW_FIXTURE / "coverage.json").read_text()
    assert '"program_id": "v06486_active_family_phase2_fixture"' in coverage
    for name in RAW_FIXTURE_PAYLOAD:
        assert (OLD_FIXTURE / name).read_bytes() == (NEW_FIXTURE / name).read_bytes(), name


def test_make_test_uses_60486_fixture_only() -> None:
    text = (CPP / "Makefile").read_text()
    test_block = text[text.index("test: all"):text.index("\ninstall: all")]
    assert "v06486_active_family_phase2_fixture" in test_block
    assert "v06485_active_family_phase2_fixture" not in test_block
    assert ".v06486_native_output" in test_block
