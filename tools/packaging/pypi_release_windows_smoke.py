#!/usr/bin/env python3
"""Clean-install smoke for a repaired xstar-tools Windows wheels."""
from __future__ import annotations

import ctypes
from importlib import metadata as importlib_metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "qualification" / "parity_freeze.json").read_text(encoding="utf-8"))
EXPECTED_SCIENCE_REVISION = str(POLICY["science_revision"])
EXPECTED_C_API_ABI = int(POLICY["abis"]["c_api"])


VERSION = importlib_metadata.version("xstar-tools")
PREFIX = "PYPI_RELEASE_WINDOWS"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise SystemExit(
            f"command failed ({proc.returncode}): {' '.join(args)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
    raise SystemExit(f"unexpected Windows wheel test host: {platform.system()} {platform.machine()}")

run(sys.executable, "-m", "pip", "check")

version = run("xstar-cpp", "--version").stdout
if VERSION not in version or EXPECTED_SCIENCE_REVISION not in version:
    raise SystemExit(f"unexpected xstar-cpp --version output: {version!r}")
abi = run("xstar-cpp", "--abi").stdout
if str(EXPECTED_C_API_ABI) not in abi:
    raise SystemExit(f"unexpected xstar-cpp --abi output: {abi!r}")
run("xstar-xspec", "--version")

doctor = run("xstar-tools", "doctor", "--require", "zone-cpp", "--json")
doctor_data = json.loads(doctor.stdout)
if not doctor_data["doctor"]["ready"]:
    raise SystemExit(f"zone-cpp doctor did not report ready: {doctor.stdout}")

from xstar_tools.native_runtime import packaged_native_library_path, prepare_native_library_search

api_path = packaged_native_library_path("xstar_api")
prepare_native_library_search(api_path)
lib = ctypes.CDLL(str(api_path))
lib.xstar_api_abi_version.argtypes = []
lib.xstar_api_abi_version.restype = ctypes.c_uint32
if int(lib.xstar_api_abi_version()) != EXPECTED_C_API_ABI:
    raise SystemExit("installed libxstar_api ABI mismatch")

cpp_dir = api_path.parent
if (cpp_dir / "libxstar_backend_python.dll").exists():
    raise SystemExit("standalone Python embedding plugin leaked into Windows PyPI wheel")
if (cpp_dir / "xstar-xspec-mpi.exe").exists():
    raise SystemExit("MPI executable leaked into ordinary Windows PyPI wheel")

import xstar_tools

package_root = Path(xstar_tools.__file__).resolve().parent
site_dir = package_root.parent
vendor_dirs = sorted(p for p in site_dir.glob("xstar_tools*.libs") if p.is_dir())
if not vendor_dirs:
    raise SystemExit("delvewheel vendor directory is absent from installed wheel")
vendor_names = [p.name.lower() for d in vendor_dirs for p in d.iterdir() if p.is_file()]
for label, token in (
    ("CFITSIO", "cfitsio"),
    ("libstdc++", "libstdc++"),
    ("libgcc", "libgcc"),
    ("libwinpthread", "libwinpthread"),
):
    if not any(token in n for n in vendor_names):
        raise SystemExit(f"vendored Windows runtime is missing {label}")
if any(n.startswith("python3") and n.endswith(".dll") for n in vendor_names):
    raise SystemExit("Python runtime DLL was incorrectly vendored")

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
print(f"{PREFIX}_WINDOWS_AMD64=ACCEPT")
print(f"{PREFIX}_CFITSIO_WHEEL_LOCAL=ACCEPT")
print(f"{PREFIX}_MINGW_RUNTIME_WHEEL_LOCAL=ACCEPT")
print(f"{PREFIX}_NO_PYTHON_RUNTIME_DEPENDENCY=ACCEPT")
print(f"{PREFIX}_SCIENCE_SMOKE=ACCEPT")
print(f"{PREFIX}_ATDB_EXTERNAL=ACCEPT")
print(f"{PREFIX}_LICENSE_GPL_3_0=ACCEPT")
print(f"{PREFIX}_SMOKE_RESULT=ACCEPT")
