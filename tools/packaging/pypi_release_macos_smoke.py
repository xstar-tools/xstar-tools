#!/usr/bin/env python3
"""Clean-install smoke for a repaired xstar-tools macOS release wheel."""
from __future__ import annotations

import ctypes
from importlib import metadata as importlib_metadata
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

PREFIX = "PYPI_RELEASE_MACOS"
VERSION = importlib_metadata.version("xstar-tools")
EXPECTED_ARCH = platform.machine()
if EXPECTED_ARCH not in {"arm64", "x86_64"}:
    raise SystemExit(f"unexpected macOS architecture: {EXPECTED_ARCH!r}")


def run(*args: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, text=True, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"command failed ({proc.returncode}): {' '.join(args)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


run(sys.executable, "-m", "pip", "check")

version = run("xstar-cpp", "--version").stdout
if VERSION not in version or "0.6.90.5.5" not in version:
    raise SystemExit(f"unexpected xstar-cpp --version output: {version!r}")
abi = run("xstar-cpp", "--abi").stdout
if "60487" not in abi:
    raise SystemExit(f"unexpected xstar-cpp --abi output: {abi!r}")
run("xstar-xspec", "--version")

doctor = run("xstar-tools", "doctor", "--require", "zone-cpp", "--json")
doctor_data = json.loads(doctor.stdout)
if not doctor_data["doctor"]["ready"]:
    raise SystemExit(f"zone-cpp doctor did not report ready: {doctor.stdout}")

from xstar_tools.native_runtime import packaged_native_library_path

api_path = packaged_native_library_path("xstar_api")
lib = ctypes.CDLL(str(api_path))
lib.xstar_api_abi_version.argtypes = []
lib.xstar_api_abi_version.restype = ctypes.c_uint32
if int(lib.xstar_api_abi_version()) != 60487:
    raise SystemExit("installed libxstar_api ABI mismatch")

cpp_dir = api_path.parent
native_paths = sorted(
    p
    for p in cpp_dir.iterdir()
    if p.is_file()
    and (
        p.suffix == ".dylib"
        or p.name
        in {
            "xstar_cpp",
            "xstar-cpp",
            "xstar-xspec-initable",
            "xstar-xspec-table",
            "xstar-xspec",
        }
    )
)
if not native_paths:
    raise SystemExit("installed macOS wheel contains no native runtime artifacts")

for path in native_paths:
    archs = run("lipo", "-archs", str(path)).stdout.split()
    if archs != [EXPECTED_ARCH]:
        raise SystemExit(f"{path.name} architectures {archs!r} != [{EXPECTED_ARCH!r}]")
    deps = run("otool", "-L", str(path)).stdout
    if "/tmp/xstar-cfitsio" in deps or "/opt/homebrew" in deps or "/usr/local/Cellar" in deps:
        raise SystemExit(f"unrepaired external dependency in {path.name}:\n{deps}")
    if "libpython" in deps or "Python.framework" in deps:
        raise SystemExit(f"Python runtime dependency leaked into {path.name}:\n{deps}")

package_root = cpp_dir.parent.parent
vendored_dirs = [p for p in package_root.rglob(".dylibs") if p.is_dir()]
vendored_cfitsio = [
    p for d in vendored_dirs for p in d.iterdir() if p.is_file() and "libcfitsio" in p.name
]
if not vendored_cfitsio:
    raise SystemExit("delocated wheel does not contain a vendored CFITSIO dylib")
for path in vendored_cfitsio:
    archs = run("lipo", "-archs", str(path)).stdout.split()
    if archs != [EXPECTED_ARCH]:
        raise SystemExit(f"vendored {path.name} architectures {archs!r} != [{EXPECTED_ARCH!r}]")

from xstar_tools.xstar.bremsstrahlung import bremem

result = bremem(
    [10.0, 100.0, 1000.0],
    [9.0, 8.0, 7.0],
    [1.0e-8, 2.0e-8, 3.0e-8],
    temperature_k=1.0e6,
    hydrogen_density_cm3=1.0e8,
    electron_fraction_xee=1.2,
)
expected = (185.2554089800474, 65.18940067478347, 0.001897745194931447)
for actual, target in zip(result.brcems_after, expected):
    if not math.isclose(float(actual), target, rel_tol=1.0e-14, abs_tol=0.0):
        raise SystemExit(f"bremsstrahlung smoke mismatch: {actual!r} != {target!r}")
if tuple(float(x) for x in result.opakc_after_cm_inv) != (1.0e-8, 2.0e-8, 3.0e-8):
    raise SystemExit("bremsstrahlung opacity-preservation smoke mismatch")

import xstar_tools

package_root = Path(xstar_tools.__file__).resolve().parent
if any(p.name == "atdb.fits" for p in package_root.rglob("atdb.fits")):
    raise SystemExit("atdb.fits unexpectedly bundled into xstar-tools wheel")

meta = importlib_metadata.metadata("xstar-tools")
if meta.get("License-Expression") != "GPL-3.0-only":
    raise SystemExit(f"unexpected License-Expression: {meta.get('License-Expression')!r}")

dist = importlib_metadata.distribution("xstar-tools")
license_files = [p for p in (dist.files or []) if p.name == "LICENSE" and "licenses" in p.parts]
if not license_files:
    raise SystemExit("installed wheel does not expose LICENSE under dist-info/licenses")
license_text = dist.locate_file(license_files[0]).read_text(encoding="utf-8")
if "GNU GENERAL PUBLIC LICENSE" not in license_text or "Version 3, 29 June 2007" not in license_text:
    raise SystemExit("installed LICENSE is not GNU GPL version 3 text")

print(f"{PREFIX}_CLEAN_INSTALL=ACCEPT")
print(f"{PREFIX}_PIP_CHECK=ACCEPT")
print(f"{PREFIX}_NATIVE_CLI=ACCEPT")
print(f"{PREFIX}_C_API_ABI=ACCEPT")
print(f"{PREFIX}_ZONE_CPP_LOAD=ACCEPT")
print(f"{PREFIX}_ARCHITECTURE={EXPECTED_ARCH}")
print(f"{PREFIX}_SINGLE_ARCH=ACCEPT")
print(f"{PREFIX}_CFITSIO_WHEEL_LOCAL=ACCEPT")
print(f"{PREFIX}_NO_PYTHON_RUNTIME_DEPENDENCY=ACCEPT")
print(f"{PREFIX}_SCIENCE_SMOKE=ACCEPT")
print(f"{PREFIX}_ATDB_EXTERNAL=ACCEPT")
print(f"{PREFIX}_LICENSE_GPL_3_0=ACCEPT")
print(f"{PREFIX}_SMOKE_RESULT=ACCEPT")
