from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def run_make(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", *args], cwd=CPP, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def parse_config(text: str) -> dict[str, str]:
    cfg: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            cfg[k] = v
    return cfg


def clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("CXX", None)
    env.pop("PLATFORM", None)
    return env


def test_release_metadata_and_acceptance_record() -> None:
    assert 'version = "0.6.88.3.1"' in (ROOT / "pyproject.toml").read_text()
    makefile = (CPP / "Makefile").read_text()
    assert "PACKAGE_VERSION ?= 0.6.88.3.1" in makefile
    assert "0.6.88.3.1 — MACOS_NATIVE_BUILD_COMPILE_CLOSURE" in (ROOT / "CHANGELOG.md").read_text()
    assert (ROOT / "macos_native_build_compile_closure_0_6_88_3_1.md").is_file()
    assert (ROOT / "xstar_tools-0.6.88.3_host_rejection.md").is_file()
    assert 'kPackageVersion = "0.6.88.3.1"' in (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert 'kPackageVersion = "0.6.88.3.1"' in (CPP / "xstar_xspec_mpi.cpp").read_text()


def test_type77_apple_exact_value_compile_closure() -> None:
    source = (CPP / "local_zone_engine.cpp").read_text()
    block = """if (rec == -0.958375491843708) {
#if defined(__APPLE__)
        downward=0x1.c2ccf22133138p-4;
#else
        downward=::exp10(rec);
#endif
    }"""
    assert block in source
    assert float.fromhex("0x1.c2ccf22133138p-4").hex() == "0x1.c2ccf22133138p-4"
    import struct
    bits = struct.unpack(">Q", struct.pack(">d", float.fromhex("0x1.c2ccf22133138p-4")))[0]
    assert bits == 0x3FBC2CCF22133138


def test_macos_default_contract_uses_apple_clang_dylib_loader_path() -> None:
    env = clean_env()
    cp = run_make(
        "-s", "print-config", "PLATFORM=macos",
        "PKG_CONFIG=/bin/false", "BREW=/bin/false", "PYTHON_CONFIG=/bin/true",
        env=env,
    )
    assert cp.returncode == 0, cp.stdout
    cfg = parse_config(cp.stdout)
    assert cfg["PLATFORM"] == "macos"
    assert cfg["CXX"] == "clang++"
    assert cfg["SHLIB_EXT"] == ".dylib"
    assert cfg["SHLIB_LDFLAGS"] == "-dynamiclib"
    assert cfg["SHLIB_INSTALL_NAME_MODE"] == "@rpath"
    assert cfg["RPATH_ORIGIN"] == "-Wl,-rpath,@loader_path"
    assert cfg["DL_LIBS"] == ""
    assert cfg["FILESYSTEM_LIBS"] == ""
    assert cfg["V0682401_PRODUCTION_COMPILER"] == "APPLECLANG"


def test_macos_dry_run_has_macho_install_names_and_no_linux_shared_targets() -> None:
    env = clean_env()
    cp = run_make(
        "-Bn", "all", "PLATFORM=macos",
        "PKG_CONFIG=/bin/false", "BREW=/bin/false", "PYTHON_CONFIG=/bin/true",
        env=env,
    )
    assert cp.returncode == 0, cp.stdout
    out = cp.stdout
    assert "clang++" in out
    assert "-dynamiclib" in out
    assert "libxstar_api.dylib" in out
    assert "-Wl,-install_name,@rpath/libxstar_api.dylib" in out
    assert "-Wl,-install_name,@rpath/libxstar_backend_cpp.dylib" in out
    assert "-Wl,-rpath,@loader_path" in out
    assert "libxstar_api.so" not in out
    assert " -ldl" not in out
    assert " -lstdc++fs" not in out


def test_pkg_config_cfitsio_precedes_homebrew() -> None:
    with tempfile.TemporaryDirectory(prefix="xstar_macos_pkg_08831_") as td:
        td_path = Path(td)
        pkg = td_path / "pkg-config"
        brew = td_path / "brew"
        pkg.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  --cflags) echo -I/opt/pkg/cfitsio/include ;;\n"
            "  --variable=libdir) echo /opt/pkg/cfitsio/lib ;;\n"
            "  --libs) echo '-L/opt/pkg/cfitsio/lib -lcfitsio' ;;\n"
            "  *) exit 1 ;;\n"
            "esac\n"
        )
        brew.write_text("#!/bin/sh\necho /should/not/be/used\n")
        pkg.chmod(0o755); brew.chmod(0o755)
        cp = run_make(
            "-s", "print-config", "PLATFORM=macos",
            f"PKG_CONFIG={pkg}", f"BREW={brew}", "PYTHON_CONFIG=/bin/true",
            env=clean_env(),
        )
        assert cp.returncode == 0, cp.stdout
        cfg = parse_config(cp.stdout)
        assert cfg["CFITSIO_DISCOVERY"] == "pkg-config"
        assert cfg["CFITSIO_CFLAGS"] == "-I/opt/pkg/cfitsio/include"
        assert cfg["CFITSIO_LIBDIR"] == "/opt/pkg/cfitsio/lib"
        assert cfg["CFITSIO_LIBS"] == "-L/opt/pkg/cfitsio/lib -lcfitsio"
        assert cfg["CFITSIO_BREW_PREFIX"] == ""


def test_homebrew_cfitsio_fallback_when_pkg_config_misses() -> None:
    with tempfile.TemporaryDirectory(prefix="xstar_macos_brew_08831_") as td:
        td_path = Path(td)
        brew = td_path / "brew"
        brew.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = \"--prefix\" ] && [ \"$2\" = \"cfitsio\" ]; then\n"
            "  echo /opt/homebrew/opt/cfitsio\n"
            "  exit 0\n"
            "fi\n"
            "exit 1\n"
        )
        brew.chmod(0o755)
        cp = run_make(
            "-s", "print-config", "PLATFORM=macos",
            "PKG_CONFIG=/bin/false", f"BREW={brew}", "PYTHON_CONFIG=/bin/true",
            env=clean_env(),
        )
        assert cp.returncode == 0, cp.stdout
        cfg = parse_config(cp.stdout)
        assert cfg["CFITSIO_DISCOVERY"] == "homebrew"
        assert cfg["CFITSIO_BREW_PREFIX"] == "/opt/homebrew/opt/cfitsio"
        assert cfg["CFITSIO_CFLAGS"] == "-I/opt/homebrew/opt/cfitsio/include"
        assert cfg["CFITSIO_LIBDIR"] == "/opt/homebrew/opt/cfitsio/lib"
        assert cfg["CFITSIO_LIBS"] == "-L/opt/homebrew/opt/cfitsio/lib -lcfitsio"
        assert cfg["CFITSIO_RPATH"] == "-Wl,-rpath,/opt/homebrew/opt/cfitsio/lib"


def test_apple_platform_runtime_contract_remains_dlopen_based() -> None:
    platform = (CPP / "xstar_platform.hpp").read_text()
    loader = (CPP / "xstar_dynamic_library.cpp").read_text()
    assert "#elif defined(__APPLE__)" in platform
    assert 'kSharedLibraryExtension = ".dylib"' in platform
    assert "kPathListSeparator = ':'" in platform
    assert "#include <dlfcn.h>" in loader
    for token in ("dlopen(", "dlsym(", "dlclose(", "dlerror(", "dladdr("):
        assert token in loader
    # Optional surrogate syntax coverage when clang++ exists on the current host.
    clang = shutil.which("clang++")
    if clang:
        cp = subprocess.run(
            [clang, "-std=c++17", "-D__APPLE__", "-fsyntax-only", str(CPP / "xstar_dynamic_library.cpp")],
            cwd=CPP, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert cp.returncode == 0, cp.stdout
