#!/usr/bin/env python3
"""Validate current package-version, science-revision, and ABI metadata."""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def match(path: Path, pattern: str, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    found = re.search(pattern, text, flags=re.MULTILINE)
    if not found:
        raise SystemExit(f"CI_PACKAGE_METADATA_REJECT: cannot resolve {label}")
    return found.group(1)


def main() -> int:
    policy = json.loads((ROOT / "qualification/parity_freeze.json").read_text(encoding="utf-8"))
    project_version = match(ROOT / "pyproject.toml", r'^version\s*=\s*"([^"]+)"', "project version")
    make_version = match(ROOT / "src/xstar_tools/xstar/cpp/Makefile", r'^PACKAGE_VERSION\s*\?=\s*([^\s]+)', "Makefile package version")
    parallel_version = match(ROOT / "src/xstar_tools/xstar/cpp/xstar_xspec_parallel.cpp", r'kPackageVersion\s*=\s*"([^"]+)"', "xstar-xspec package version")
    mpi_version = match(ROOT / "src/xstar_tools/xstar/cpp/xstar_xspec_mpi.cpp", r'kPackageVersion\s*=\s*"([^"]+)"', "xstar-xspec-mpi package version")
    science = match(ROOT / "src/xstar_tools/__init__.py", r'^__version__\s*=\s*"([^"]+)"', "science revision")
    errors=[]
    if len({project_version, make_version, parallel_version, mpi_version}) != 1:
        errors.append(f"package-version mismatch: project={project_version} make={make_version} xspec={parallel_version} mpi={mpi_version}")
    if science != policy["science_revision"]:
        errors.append(f"science revision mismatch: {science}")
    if policy["abis"] != {"c_api":60487,"production_zone":6048110,"fixed_state_program":60486,"fixed_state_engine":60488,"xspec_table":1}:
        errors.append("compact ABI policy changed")
    if errors:
        print("CI_PACKAGE_METADATA_RESULT=REJECT")
        for error in errors: print("CI_PACKAGE_METADATA_ERROR="+error)
        return 1
    print("CI_PACKAGE_METADATA_RESULT=ACCEPT")
    print(f"CI_PACKAGE_VERSION={project_version}")
    print(f"CI_SCIENCE_REVISION={science}")
    print("CI_C_API_ABI=60487")
    print("CI_PRODUCTION_ZONE_ABI=6048110")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
