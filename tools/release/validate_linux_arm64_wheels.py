#!/usr/bin/env python3
"""Version-independent Linux ARM64 release-wheel qualification (not science acceptance).

Preflight works on any host. Wheel acceptance requires genuine native Linux
AArch64 plus auditwheel-repaired manylinux_2_28_aarch64 output and the existing
cibuildwheel clean-install test; it cannot qualify ARM32 or real-model science.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import zipfile

PREFIX = "LINUX_ARM64_RELEASE"


def release_policy(root: Path) -> dict[str, object]:
    """Read version and separately frozen science/ABI policy from the checkout.

    The existing parity-freeze and metadata checkers independently guard the
    source files.  Do not derive expected science values from the wheel being
    inspected, since that would allow a self-consistent but incorrect wheel.
    """
    import tomllib

    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    frozen = json.loads((root / "qualification/parity_freeze.json").read_text(encoding="utf-8"))
    abis = frozen["abis"]
    return {
        "package_version": project["project"]["version"],
        "science_revision": frozen["science_revision"],
        "abis": {
            "c_api_abi": abis["c_api"],
            "production_zone_abi": abis["production_zone"],
        },
    }
LIBRARY_STEMS = (
    "xstar_solver", "xstar_rates", "xstar_matrix", "xstar_emissivity",
    "xstar_opacity", "xstar_thermal", "xstar_engine", "xstar_local_zone",
    "xstar_final_recompute", "xstar_production_zone", "xstar_xspec_table",
    "xstar_api", "xstar_backend_cpp",
)
EXECUTABLES = (
    "xstar_cpp", "xstar-cpp", "xstar-xspec-initable",
    "xstar-xspec-table", "xstar-xspec",
)
ARTIFACTS = tuple(f"lib{stem}.so" for stem in LIBRARY_STEMS) + EXECUTABLES
ROOT_REL = "xstar_tools/xstar/cpp/"
MANDATORY_CHECKERS = (
    "tools/ci/check_package_metadata.py",
    "tools/qualification/check_parity_freeze.py",
    "tools/qualification/check_source_concordance.py",
    "tools/qualification/check_mn_type49_science_refreeze.py",
)


class GateError(RuntimeError):
    pass


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_elf_aarch64(data: bytes, name: str) -> None:
    if len(data) < 20 or data[:4] != b"\x7fELF":
        raise GateError(f"non-ELF native artifact: {name}")
    if data[4] != 2 or data[5] != 1 or struct.unpack_from("<H", data, 18)[0] != 183:
        raise GateError(f"native artifact is not little-endian ELF64 AArch64: {name}")


def validate_wheel(path: Path, *, policy: dict[str, object]) -> dict[str, object]:
    version = str(policy["package_version"])
    name = path.name
    match = re.fullmatch(
        r"xstar_tools-([^-]+)-(cp\d+)-(cp\d+)-(.+)\.whl", name
    )
    if not match or match.group(1) != version or match.group(2) != match.group(3):
        raise GateError(f"unexpected wheel version/CPython ABI: {name}")
    py_tag = match.group(2)
    platform_tags = match.group(4).split(".")
    if "manylinux_2_28_aarch64" not in platform_tags:
        raise GateError(f"wheel is not repaired for manylinux_2_28_aarch64: {name}")
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        if len(names) != len(set(names)):
            raise GateError(f"duplicate ZIP members: {name}")
        if any(part in {"..", ""} for member in names for part in member.split("/")[:-1]):
            raise GateError(f"unsafe ZIP member path: {name}")
        for artifact in ARTIFACTS:
            path_in_wheel = ROOT_REL + artifact
            if path_in_wheel not in names:
                raise GateError(f"wheel missing native artifact {artifact}: {name}")
            check_elf_aarch64(wheel.read(path_in_wheel), artifact)
        if any("xstar-xspec-mpi" in item for item in names):
            raise GateError(f"MPI executable unexpectedly included: {name}")
        if any("libxstar_backend_python" in item for item in names):
            raise GateError(f"Python-embedding plugin unexpectedly included: {name}")
        if any(item.endswith("/atdb.fits") or item == "atdb.fits" for item in names):
            raise GateError(f"external atomic database unexpectedly bundled: {name}")
        vendored = [item for item in names if Path(item).name.startswith("libcfitsio") and ".so" in item]
        if not vendored or not all(".libs/" in item for item in vendored):
            raise GateError(f"auditwheel wheel-local CFITSIO not found: {name}")
        for item in vendored:
            check_elf_aarch64(wheel.read(item), item)
        meta_name = ROOT_REL + "native_build.json"
        if meta_name not in names:
            raise GateError(f"native provenance manifest absent: {name}")
        meta = json.loads(wheel.read(meta_name))
        required = {
            "package_version": version,
            "science_revision": policy["science_revision"],
            "platform_system": "Linux",
            "platform_machine": "aarch64",
            "native_profile": "pypi-linux",
            "native_built": True,
            "mpi_included": False,
            "atomic_database_bundled": False,
            **policy["abis"],
        }
        for field, expected in required.items():
            if meta.get(field) != expected:
                raise GateError(f"wheel native_build.json {field}: expected {expected!r}, observed {meta.get(field)!r}")
        if set(meta.get("artifacts", [])) != set(ARTIFACTS) or len(meta["artifacts"]) != len(ARTIFACTS):
            raise GateError(f"wheel native artifact manifest mismatch: {name}")
        wheel_file = f"xstar_tools-{version}.dist-info/WHEEL"
        metadata_file = f"xstar_tools-{version}.dist-info/METADATA"
        if wheel_file not in names or metadata_file not in names:
            raise GateError(f"wheel metadata missing: {name}")
        wheel_text = wheel.read(wheel_file).decode("utf-8")
        metadata_text = wheel.read(metadata_file).decode("utf-8")
        if "Root-Is-Purelib: false" not in wheel_text:
            raise GateError(f"wheel falsely marked pure-Python: {name}")
        if not any(line.startswith(f"Tag: {py_tag}-{py_tag}-") and "manylinux_2_28_aarch64" in line
                   for line in wheel_text.splitlines()):
            raise GateError(f"repaired platform tag missing from WHEEL: {name}")
        if f"Version: {version}" not in metadata_text or "Name: xstar-tools" not in metadata_text:
            raise GateError(f"wheel dist-info project/version mismatch: {name}")
        return {"filename": name, "sha256": digest(path), "python_tag": py_tag,
                "native_artifacts": len(ARTIFACTS), "bundled_cfitsio": sorted(vendored),
                "science_revision": meta["science_revision"]}


def check_preflight(root: Path) -> dict[str, object]:
    import tomllib

    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    cibw = project["tool"]["cibuildwheel"]
    linux = cibw["linux"]
    if linux.get("manylinux-aarch64-image") != "manylinux_2_28":
        raise GateError("missing pinned ARM64 manylinux_2_28 image")
    if linux.get("manylinux-x86_64-image") != "manylinux_2_28":
        raise GateError("existing x86_64 manylinux image was changed")
    if "aarch64" in linux.get("archs", []):
        raise GateError("ARM64 builds must be selected explicitly by host workflow")
    env = linux.get("environment", {})
    for k, v in {
        "XSTAR_TOOLS_NATIVE": "required", "XSTAR_TOOLS_NATIVE_PROFILE": "pypi-linux",
        "XSTAR_TOOLS_CFITSIO_PREFIX": "/opt/xstar-cfitsio",
    }.items():
        if env.get(k) != v:
            raise GateError(f"wheel build profile contract altered: {k}")
    if "auditwheel repair" not in linux.get("repair-wheel-command", ""):
        raise GateError("auditwheel repair not enabled")
    if "pypi_release_linux_smoke.py" not in cibw.get("test-command", ""):
        raise GateError("isolated Linux wheel smoke not enabled")
    # The production release builds ARM64 wheels in its own job.  A historical
    # milestone workflow (such as linux-arm64-packaging.yml) is optional and
    # must never be a prerequisite for later PyPI releases.
    release_workflow = (root / ".github/workflows/pypi-release.yml").read_text(
        encoding="utf-8"
    )
    arm64_job_match = re.search(
        r"(?ms)^  linux-arm64:[ \t]*\n(?P<job>.*?)(?=^  [a-zA-Z][a-zA-Z0-9_-]*:[ \t]*(?:#.*)?$|\Z)",
        release_workflow,
    )
    if arm64_job_match is None:
        raise GateError("PyPI release workflow is missing the Linux ARM64 job")
    arm64_job = arm64_job_match.group("job")
    for contract in (
        "runs-on: ubuntu-24.04-arm",
        "CIBW_ARCHS_LINUX: aarch64",
        "pypa/cibuildwheel@",
        "tools/release/validate_linux_arm64_wheels.py",
        "--wheel-dir",
    ):
        if contract not in arm64_job:
            raise GateError(f"PyPI release ARM64 job is missing {contract!r}")
    if arm64_job.count("tools/release/validate_linux_arm64_wheels.py") < 2:
        raise GateError("PyPI release ARM64 job needs preflight and wheel validation")
    if "--preflight-only" not in arm64_job:
        raise GateError("PyPI release ARM64 job is missing source preflight")
    if re.search(r"\bcp\d+-manylinux_aarch64\b", arm64_job) is None:
        raise GateError("PyPI release ARM64 job selects no AArch64 CPython wheels")
    if not (root / "tools/packaging/build_manylinux_cfitsio.sh").is_file():
        raise GateError("pinned CFITSIO build script missing")
    for rel in MANDATORY_CHECKERS:
        result = subprocess.run([sys.executable, "-B", str(root / rel)], cwd=root,
                                text=True, capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        if result.returncode:
            raise GateError(f"source/freeze checker rejected {rel}:\n{result.stdout}{result.stderr}")
    return {"source_freeze": "ACCEPT", "packaging_contract": "ACCEPT",
            "source_version": release_policy(root)["package_version"],
            "science_revision": release_policy(root)["science_revision"],
            "architecture": platform.machine(), "system": platform.system()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=Path.cwd())
    parser.add_argument("--wheel-dir", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--require-builds", nargs="+", required=False, default=["cp311", "cp313"])
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    root = args.package.resolve()
    output = args.output_root.resolve() if args.output_root else None
    policy = release_policy(root)
    report: dict[str, object] = {"package_version": policy["package_version"],
                                 "science_revision": policy["science_revision"],
                                 "host_result": "NOT_RUN"}
    status = 0
    try:
        preflight = check_preflight(root)
        report.update(preflight)
        print(f"{PREFIX}_FREEZE=ACCEPT")
        print(f"{PREFIX}_SOURCE_CONTRACT=ACCEPT")
        if not args.preflight_only:
            if platform.system() != "Linux" or platform.machine().lower() not in {"aarch64", "arm64"}:
                raise GateError("native Linux ARM64 wheel qualification requires Linux/aarch64 host")
            if not args.wheel_dir or not args.wheel_dir.is_dir():
                raise GateError("repaired ARM64 wheel directory missing")
            if output is None or output == root or output.is_relative_to(root):
                raise GateError("evidence output must be outside the source checkout")
            found = sorted(args.wheel_dir.glob("*.whl"))
            wheels = [validate_wheel(path, policy=policy) for path in found]
            tags = {str(row["python_tag"]) for row in wheels}
            if tags != set(args.require_builds) or len(wheels) != len(args.require_builds):
                raise GateError(f"CPython wheel coverage mismatch: expected {args.require_builds}, observed {sorted(tags)}")
            report["wheels"] = wheels
            report["wheel_count"] = len(wheels)
            # The native installed-wheel smoke is performed separately by
            # cibuildwheel's isolated test-command, not by zip inspection.
            report["installed_wheel_smoke"] = "REQUIRED_BY_CIBUILDWHEEL"
            report["host_result"] = "ACCEPT"
            print(f"{PREFIX}_WHEEL_METADATA=ACCEPT")
            print(f"{PREFIX}_ELF_AARCH64=ACCEPT")
            print(f"{PREFIX}_CFITSIO_BUNDLED=ACCEPT")
            print(f"{PREFIX}_HOST_RESULT=ACCEPT")
        else:
            print(f"{PREFIX}_HOST_RESULT=NOT_RUN")
    except (GateError, OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        report["host_result"] = "REJECT"
        report["error"] = str(exc)
        print(f"{PREFIX}_HOST_RESULT=REJECT")
        print(f"{PREFIX}_ERROR={exc}", file=sys.stderr)
        status = 1
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        (output / "result.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
