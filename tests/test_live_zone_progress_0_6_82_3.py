from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
FRONTEND = CPP / "xstar_cpp_frontend.cpp"


def _compiler() -> str:
    cxx = shutil.which("g++")
    if not cxx:
        pytest.skip("g++ is required for native frontend regression")
    return cxx


def _build_frontend(tmp_path: Path) -> Path:
    cxx = _compiler()
    (tmp_path / "api_stub.cpp").write_text(
        '#include <cstdint>\n'
        'extern "C" std::uint32_t xstar_api_abi_version(void){return 60487u;}\n'
        'extern "C" const char* xstar_api_version_string(void){return "0.6.48.12.3.45.3.3.8";}\n',
        encoding="utf-8",
    )
    (tmp_path / "zone_stub.cpp").write_text(
        '#include <cstdint>\n'
        'extern "C" std::int32_t xstar_production_zone_abi_version_v0648110(void){return 6048110;}\n',
        encoding="utf-8",
    )
    subprocess.run([cxx, "-shared", "-fPIC", "-o", str(tmp_path / "libxstar_api.so"), str(tmp_path / "api_stub.cpp")], check=True)
    subprocess.run([cxx, "-shared", "-fPIC", "-o", str(tmp_path / "libxstar_production_zone.so"), str(tmp_path / "zone_stub.cpp")], check=True)
    exe = tmp_path / "xstar-cpp"
    proc = subprocess.run(
        [
            cxx, "-std=c++17", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-O0",
            '-DXSTAR_TOOLS_PACKAGE_VERSION="0.6.82.3"',
            "-o", str(exe), str(FRONTEND), "-L", str(tmp_path), "-lxstar_api", "-lxstar_production_zone",
            "-lstdc++fs", "-Wl,-rpath,$ORIGIN",
        ],
        text=True,
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return exe


def test_frontend_propagates_text_progress_to_native_process(tmp_path: Path) -> None:
    exe = _build_frontend(tmp_path)
    sibling = tmp_path / "xstar_cpp"
    sibling.write_text(
        "#!/bin/sh\n"
        "if [ \"${XSTAR_CPP_PROGRESS_MODE:-}\" != text ]; then\n"
        "  echo progress-mode-missing >&2\n"
        "  exit 93\n"
        "fi\n"
        "echo PROGRESS_ENV=${XSTAR_CPP_PROGRESS_MODE}\n"
        "out=.\n"
        "while [ $# -gt 0 ]; do\n"
        "  case \"$1\" in --output-dir) out=$2; shift 2;; *) shift;; esac\n"
        "done\n"
        "mkdir -p \"$out\"\n"
        "printf fake > \"$out/xout_abund1.fits\"\n"
        "printf 'print option: 1\\n' > \"$out/xout_step.log\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    sibling.chmod(0o755)
    data = tmp_path / "data"
    data.mkdir()
    (data / "atdb.fits").write_bytes(b"atdb")
    (data / "coheat.dat").write_bytes(b"coheat")
    par = tmp_path / "xstar.par"
    par.write_text("spectrum,s,h,pow,,,spectrum\ncolumn,r,h,1.e20,0,,column\n", encoding="utf-8")
    out = tmp_path / "run"
    proc = subprocess.run(
        [str(exe), "--input", str(par), "--data-dir", str(data), "--output", str(out), "--progress", "text"],
        text=True,
        capture_output=True,
        env=dict(os.environ),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PROGRESS_ENV=text" in proc.stdout


def test_standalone_streams_each_accepted_zone_before_controller_returns() -> None:
    text = (CPP / "xstar_standalone.cpp").read_text(encoding="utf-8")
    assert 'std::getenv("XSTAR_CPP_PROGRESS_MODE")' in text
    assert 'print_xstar_style_live_header();' in text
    assert 'print_xstar_style_live_zone(' in text
    mark = text.index("production_zone_mark_complete(", text.index("for (std::size_t call = 1; ; ++call)"))
    live = text.index("print_xstar_style_live_zone(", mark)
    controller_line = text.index('V048746255172582_CONTROLLER_CALL=', mark)
    assert mark < live < controller_line
    assert "std::cerr" in text[text.index("void print_xstar_style_live_zone"):live]
    assert "std::flush" in text[text.index("void print_xstar_style_live_zone"):live]
    assert "if (!live_text_progress)" in text


def test_06823_host_runner_streams_combined_output_live() -> None:
    text = (ROOT / "tools/qualification/run_multi_element_host_smoke_0_6_82_3.py").read_text(encoding="utf-8")
    assert 'EXPECTED_VERSION = "0.6.82.3"' in text
    assert "subprocess.Popen(" in text
    assert "stderr=subprocess.STDOUT" in text
    assert "bufsize=1" in text
    assert 'print(line, end="", flush=True)' in text
