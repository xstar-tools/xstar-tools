#!/usr/bin/env python3
"""Clean-install smoke for a repaired xstar-tools Linux release wheel."""
from __future__ import annotations

import ctypes
from importlib import metadata as importlib_metadata
import json
import math
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "qualification" / "parity_freeze.json").read_text(encoding="utf-8"))
EXPECTED_SCIENCE_REVISION = str(POLICY["science_revision"])
EXPECTED_C_API_ABI = int(POLICY["abis"]["c_api"])


def run(*args: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, text=True, capture_output=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"command failed ({proc.returncode}): {' '.join(args)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


# Package dependency integrity in the isolated cibuildwheel test environment.
run(sys.executable, "-m", "pip", "check")

# Public native CLI/version/ABI surface.
version = run("xstar-cpp", "--version").stdout
if importlib_metadata.version("xstar-tools") not in version or EXPECTED_SCIENCE_REVISION not in version:
    raise SystemExit(f"unexpected xstar-cpp --version output: {version!r}")
abi = run("xstar-cpp", "--abi").stdout
if str(EXPECTED_C_API_ABI) not in abi:
    raise SystemExit(f"unexpected xstar-cpp --abi output: {abi!r}")
run("xstar-xspec", "--version")

# Python-to-native loader boundary and production-zone readiness.  No atdb.fits
# is needed merely to prove that the repaired libraries load.
doctor = run("xstar-tools", "doctor", "--require", "zone-cpp", "--json")
doctor_data = json.loads(doctor.stdout)
if not doctor_data["doctor"]["ready"]:
    raise SystemExit(f"zone-cpp doctor did not report ready: {doctor.stdout}")

from xstar_tools.native_runtime import packaged_native_library_path

api_path = packaged_native_library_path("xstar_api")
lib = ctypes.CDLL(str(api_path))
lib.xstar_api_abi_version.argtypes = []
lib.xstar_api_abi_version.restype = ctypes.c_uint32
if int(lib.xstar_api_abi_version()) != EXPECTED_C_API_ABI:
    raise SystemExit("installed libxstar_api ABI mismatch")

# auditwheel must leave a self-contained dependency closure.  Check every
# installed XSTAR ELF library/executable for missing dependencies and require
# CFITSIO to resolve from the installed wheel rather than /usr/lib or /lib.
cpp_dir = api_path.parent
native_paths = sorted(
    p for p in cpp_dir.iterdir()
    if p.is_file() and (p.suffix == ".so" or p.name in {
        "xstar_cpp", "xstar-cpp", "xstar-xspec-initable", "xstar-xspec-table", "xstar-xspec"
    })
)
cfitsio_seen = False
for path in native_paths:
    dep = run("ldd", str(path)).stdout
    if "not found" in dep:
        raise SystemExit(f"unresolved dependency in {path.name}:\n{dep}")
    for line in dep.splitlines():
        if "libcfitsio" in line:
            cfitsio_seen = True
            if "site-packages" not in line:
                raise SystemExit(
                    f"CFITSIO for {path.name} did not resolve from installed wheel: {line}"
                )
if not cfitsio_seen:
    raise SystemExit("no installed native artifact reported a CFITSIO dependency")

# Small pinned, offline XSTAR science leaf.  This exercises installed package
# numerics without weakening the external atdb.fits policy.
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

# External atomic-data policy remains explicit.
import xstar_tools
package_root = Path(xstar_tools.__file__).resolve().parent
if any(p.name == "atdb.fits" for p in package_root.rglob("atdb.fits")):
    raise SystemExit("atdb.fits unexpectedly bundled into xstar-tools wheel")

print("PYPI_RELEASE_LINUX_CLEAN_INSTALL=ACCEPT")
print("PYPI_RELEASE_LINUX_PIP_CHECK=ACCEPT")
print("PYPI_RELEASE_LINUX_NATIVE_CLI=ACCEPT")
print("PYPI_RELEASE_LINUX_C_API_ABI=ACCEPT")
print("PYPI_RELEASE_LINUX_ZONE_CPP_LOAD=ACCEPT")
print("PYPI_RELEASE_LINUX_CFITSIO_WHEEL_LOCAL=ACCEPT")
print("PYPI_RELEASE_LINUX_SCIENCE_SMOKE=ACCEPT")
print("PYPI_RELEASE_LINUX_ATDB_EXTERNAL=ACCEPT")
print("PYPI_RELEASE_LINUX_SMOKE_RESULT=ACCEPT")
