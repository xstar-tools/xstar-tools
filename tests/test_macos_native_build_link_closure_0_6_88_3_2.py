from __future__ import annotations

import os
import shutil
import subprocess
import sys
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


def local_zone_link_line(text: str) -> str:
    for line in text.splitlines():
        if "-o libxstar_local_zone" in line and "local_zone_engine.cpp" in line:
            return line
    return ""


def test_release_metadata_and_host_rejection_record() -> None:
    assert 'version = "0.6.88.3.2"' in (ROOT / "pyproject.toml").read_text()
    makefile = (CPP / "Makefile").read_text()
    assert "PACKAGE_VERSION ?= 0.6.88.3.2" in makefile
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert "0.6.88.3.2 — MACOS_NATIVE_BUILD_LINK_CLOSURE" in changelog
    assert "0.6.88.3.1 — MACOS_NATIVE_BUILD_COMPILE_CLOSURE (HOST REJECT — historical)" in changelog
    rejection = (ROOT / "xstar_tools-0.6.88.3.1_host_rejection.md").read_text()
    assert "HOST REJECT" in rejection
    assert "xstar_opacity_apply_line_profile_v1" in rejection
    assert "Python 3.14" in rejection
    assert 'kPackageVersion = "0.6.88.3.2"' in (CPP / "xstar_xspec_parallel.cpp").read_text()
    assert 'kPackageVersion = "0.6.88.3.2"' in (CPP / "xstar_xspec_mpi.cpp").read_text()


def test_type77_compile_closure_is_carried_forward_unchanged() -> None:
    source = (CPP / "local_zone_engine.cpp").read_text()
    block = """if (rec == -0.958375491843708) {
#if defined(__APPLE__)
        downward=0x1.c2ccf22133138p-4;
#else
        downward=::exp10(rec);
#endif
    }"""
    assert block in source


def test_macos_local_zone_directly_links_opacity() -> None:
    cp = run_make(
        "-Bn", "all", "PLATFORM=macos",
        "PKG_CONFIG=/bin/false", "BREW=/bin/false", "PYTHON_CONFIG=/bin/true",
        env=clean_env(),
    )
    assert cp.returncode == 0, cp.stdout
    line = local_zone_link_line(cp.stdout)
    assert line, cp.stdout
    assert "-lxstar_engine" in line
    assert "-lxstar_emissivity" in line
    assert "-lxstar_opacity" in line
    assert "-Wl,-rpath,@loader_path" in line


def test_linux_local_zone_link_command_does_not_gain_opacity() -> None:
    cp = run_make("-Bn", "all", "PLATFORM=linux", env=clean_env())
    assert cp.returncode == 0, cp.stdout
    line = local_zone_link_line(cp.stdout)
    assert line, cp.stdout
    assert "-lxstar_engine" in line
    assert "-lxstar_emissivity" in line
    assert "-lxstar_opacity" not in line


def test_macos_default_contract_uses_apple_clang_dylib_loader_path() -> None:
    cp = run_make(
        "-s", "print-config", "PLATFORM=macos",
        "PKG_CONFIG=/bin/false", "BREW=/bin/false", "PYTHON_CONFIG=/bin/true",
        env=clean_env(),
    )
    assert cp.returncode == 0, cp.stdout
    cfg = parse_config(cp.stdout)
    assert cfg["PLATFORM"] == "macos"
    assert cfg["CXX"] == "clang++"
    assert cfg["SHLIB_EXT"] == ".dylib"
    assert cfg["SHLIB_LDFLAGS"] == "-dynamiclib"
    assert cfg["SHLIB_INSTALL_NAME_MODE"] == "@rpath"
    assert cfg["RPATH_ORIGIN"] == "-Wl,-rpath,@loader_path"
    assert cfg["V0682401_PRODUCTION_COMPILER"] == "APPLECLANG"


def test_pkg_config_and_homebrew_cfitsio_contract_is_preserved() -> None:
    with tempfile.TemporaryDirectory(prefix="xstar_macos_brew_08832_") as td:
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
        assert cfg["CFITSIO_LIBS"] == "-L/opt/homebrew/opt/cfitsio/lib -lcfitsio"


def test_runner_and_checker_propagate_active_interpreter() -> None:
    runner = (ROOT / "tools/qualification/run_macos_native_build_link_closure_host_0_6_88_3_2.py").read_text()
    checker = (ROOT / "tools/qualification/check_macos_native_build_link_closure_0_6_88_3_2.py").read_text()
    assert "import sys" in runner
    assert "sys.executable" in runner
    assert "import sys" in checker
    assert "sys.executable" in checker
    assert '["python3", "-m", "pytest"' not in checker


def test_github_actions_uses_setup_python_interpreter_consistently() -> None:
    workflow = (ROOT / ".github/workflows/macos-build.yml").read_text()
    assert "actions/setup-python@v5" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "python -m pip install pytest" in workflow
    assert "python tools/qualification/run_macos_native_build_link_closure_host_0_6_88_3_2.py" in workflow
    assert "python3 -m pip install pytest" not in workflow


def test_apple_platform_runtime_contract_remains_dlopen_based() -> None:
    platform = (CPP / "xstar_platform.hpp").read_text()
    loader = (CPP / "xstar_dynamic_library.cpp").read_text()
    assert "#elif defined(__APPLE__)" in platform
    assert 'kSharedLibraryExtension = ".dylib"' in platform
    assert "#include <dlfcn.h>" in loader
    for token in ("dlopen(", "dlsym(", "dlclose(", "dlerror(", "dladdr("):
        assert token in loader
    clang = shutil.which("clang++")
    if clang:
        cp = subprocess.run(
            [clang, "-std=c++17", "-D__APPLE__", "-fsyntax-only", str(CPP / "xstar_dynamic_library.cpp")],
            cwd=CPP, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        assert cp.returncode == 0, cp.stdout
