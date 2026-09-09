from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
CALLERS = [
    CPP / "xstar_api.cpp",
    CPP / "xstar_backend_cpp.cpp",
    CPP / "xstar_standalone.cpp",
    CPP / "xstar_standalone_internal.hpp",
]




def test_platform_filename_and_path_separator_contract() -> None:
    text = (CPP / "xstar_platform.hpp").read_text()
    assert 'kSharedLibraryExtension = ".so"' in text
    assert 'kSharedLibraryExtension = ".dylib"' in text
    assert 'kSharedLibraryExtension = ".dll"' in text
    assert "kPathListSeparator = ':'" in text
    assert "kPathListSeparator = ';'" in text
    assert "shared_library_filename" in text


def test_native_loader_calls_are_isolated_to_wrapper() -> None:
    forbidden = ("dlopen(", "dlsym(", "dlclose(", "dlerror(", "dladdr(")
    for path in CALLERS:
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{token} remains in {path.name}"
        assert "#include <dlfcn.h>" not in text
    wrapper = (CPP / "xstar_dynamic_library.cpp").read_text()
    for token in forbidden:
        assert token in wrapper
    assert "LoadLibraryW" in wrapper
    assert "GetProcAddress" in wrapper
    assert "FreeLibrary" in wrapper
    assert "GetModuleHandleExW" in wrapper
    assert "GetModuleFileNameW" in wrapper


def test_callers_do_not_hardcode_so_names() -> None:
    for path in CALLERS:
        text = path.read_text()
        assert '.so"' not in text
        assert "shared_library_filename" in text or path.name == "xstar_standalone_internal.hpp"


def test_plugin_path_uses_platform_separator() -> None:
    api = (CPP / "xstar_api.cpp").read_text()
    assert 'std::getenv("XSTAR_PLUGIN_PATH")' in api
    assert "xstar_platform::path_list_separator()" in api
    assert "std::getline(stream, item, ':')" not in api


def test_sibling_discovery_is_portable() -> None:
    internal = (CPP / "xstar_standalone_internal.hpp").read_text()
    wrapper = (CPP / "xstar_dynamic_library.cpp").read_text()
    assert "xstar_platform::module_directory(symbol_address)" in internal
    assert "dladdr(symbol_address" in wrapper
    assert "GetModuleHandleExW" in wrapper
    assert "std::filesystem::current_path()" in wrapper


def test_makefile_wires_internal_loader_and_windows_mpi_remains_unsupported() -> None:
    text = (CPP / "Makefile").read_text()
    assert "xstar_dynamic_library.o" in text
    assert "xstar_dynamic_library.cpp" in text
    assert "xstar_platform.hpp" in text
    cp = subprocess.run(
        ["make", "-s", "mpi", "PLATFORM=windows"], cwd=CPP,
        text=True, capture_output=True,
    )
    assert cp.returncode != 0
    assert "not supported on PLATFORM=windows" in cp.stderr


def test_linux_dynamic_library_smoke() -> None:
    with tempfile.TemporaryDirectory(prefix="xstar_dyn_0882_") as td:
        td_path = Path(td)
        plugin = td_path / "plugin.cpp"
        test = td_path / "test.cpp"
        library = td_path / "libxstar_test.so"
        exe = td_path / "test"
        plugin.write_text('extern "C" int xstar_test_symbol(void) { return 882; }\n')
        test.write_text(
            '#include "xstar_platform.hpp"\n'
            '#include "xstar_dynamic_library.hpp"\n'
            '#include <iostream>\n'
            'using fn = int (*)();\n'
            'int main(int argc, char** argv) {\n'
            '  if (argc != 2) return 2;\n'
            '  if (xstar_platform::shared_library_filename("xstar_test") != "libxstar_test.so") return 3;\n'
            "  if (xstar_platform::path_list_separator() != ':') return 4;\n"
            '  auto h = xstar_platform::dynamic_library_open(argv[1], xstar_platform::DynamicLibraryVisibility::local);\n'
            '  if (!h) return 5;\n'
            '  auto f = reinterpret_cast<fn>(xstar_platform::dynamic_library_symbol(h, "xstar_test_symbol"));\n'
            '  if (!f || f() != 882) return 6;\n'
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
             str(CPP / "xstar_dynamic_library.cpp"), "-ldl"],
            check=True, text=True, capture_output=True,
        )
        cp = subprocess.run([str(exe), str(library)], text=True, capture_output=True)
        assert cp.returncode == 0, cp.stderr
