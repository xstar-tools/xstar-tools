#!/usr/bin/env python3
"""Validate the compact xstar-tools scientific parity-freeze boundary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "qualification" / "parity_freeze.json"


def fail(message: str) -> None:
    raise SystemExit(f"PARITY_FREEZE_REJECT: {message}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_regex(path: Path, pattern: str, expected: int | str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        fail(f"{label} not found in {path.relative_to(ROOT)}")
    observed = match.group(1)
    if isinstance(expected, int):
        try:
            observed = int(observed)
        except ValueError:
            fail(f"{label} is not an integer: {observed!r}")
    if observed != expected:
        fail(f"{label} mismatch: expected {expected!r}, observed {observed!r}")


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if policy.get("schema") != "xstar-tools-parity-freeze-v2":
        fail("unsupported parity-freeze schema")
    if policy.get("science_revision") != "0.6.90.5.5":
        fail("science revision changed")
    if policy.get("canonical_authority") != "FORTRAN XSTAR 2.59g":
        fail("canonical authority changed")

    refs = policy["references"]
    for label, record in refs.items():
        path = ROOT / record["path"]
        if not path.is_file():
            fail(f"missing {label}: {record['path']}")
        observed = sha256(path)
        if observed != record["sha256"]:
            fail(f"{label} hash mismatch: {observed}")

    source_manifest = json.loads((ROOT / refs["current_source_hashes"]["path"]).read_text(encoding="utf-8"))
    if source_manifest.get("science_revision") != policy["science_revision"]:
        fail("current source-hash manifest science revision mismatch")
    for rel, record in sorted(source_manifest.get("files", {}).items()):
        path = ROOT / rel
        if not path.is_file():
            fail(f"science-critical source missing: {rel}")
        observed = sha256(path)
        if observed != record["sha256"]:
            fail(f"science-critical source changed: {rel}")
    for rel in source_manifest.get("retired_frozen_paths", {}):
        if (ROOT / rel).exists():
            fail(f"retired frozen source unexpectedly active: {rel}")

    require_regex(ROOT / "src/xstar_tools/__init__.py", r'^__version__\s*=\s*"([^"]+)"', policy["science_revision"], "Python science revision")
    abis = policy["abis"]
    require_regex(ROOT / "src/xstar_tools/xstar/cpp/xstar_api.h", r"#define\s+XSTAR_API_ABI_VERSION\s+(\d+)u", abis["c_api"], "C API ABI")
    require_regex(ROOT / "src/xstar_tools/xstar/cpp/xstar_xspec_table.h", r"#define\s+XSTAR_XSPEC_TABLE_ABI_VERSION\s+(\d+)u", abis["xspec_table"], "XSPEC-table ABI")
    require_regex(ROOT / "src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h", r"#define\s+XSTAR_FIXED_STATE_PROGRAM_ABI_VERSION\s+(\d+)u", abis["fixed_state_program"], "fixed-state program ABI")
    require_regex(ROOT / "src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h", r"#define\s+XSTAR_FIXED_STATE_ENGINE_ABI_VERSION\s+(\d+)u", abis["fixed_state_engine"], "fixed-state engine ABI")
    require_regex(ROOT / "src/xstar_tools/xstar/cpp_backend_production_zone.py", r"^ABI_VERSION\s*=\s*(\d+)", abis["production_zone"], "production-zone ABI")

    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text(encoding="utf-8")
    active_lines = [line.split("#", 1)[0] for line in makefile.splitlines()]
    for flag in policy["compiler_policy"]["forbid"]:
        assignment = re.compile(rf"^\s*[A-Z0-9_]*FLAGS\s*(?:\+?=|:=|\?=).*{re.escape(flag)}")
        if any(assignment.search(line) for line in active_lines):
            fail(f"forbidden floating-point compiler flag assigned in Makefile: {flag}")
        if f"findstring {flag}" not in makefile:
            fail(f"Makefile no longer rejects forbidden floating-point flag: {flag}")
    for flag in policy["compiler_policy"]["require"]:
        if flag not in makefile:
            fail(f"required floating-point compiler flag absent from Makefile: {flag}")

    package_root = ROOT / "src/xstar_tools"
    bundled_atdb = list(package_root.rglob("atdb.fits"))
    if bundled_atdb:
        fail(f"atdb.fits is bundled: {bundled_atdb[0].relative_to(ROOT)}")

    c5 = policy["accepted_c5"]
    if c5.get("routine_rerun") is not False or c5.get("detail3_identities") != [709, 762]:
        fail("accepted C5 freeze record changed")
    models = {item.get("model") for item in policy["accepted_structural_exceptions"]}
    if models != {"helike_type69/ca19_xi2_ne1", "helike_type69/o7_ne1e10"}:
        fail("accepted structural-exception set changed")

    selftest = ROOT / refs["option23_selftest"]["path"]
    proc = subprocess.run([sys.executable, "-B", str(selftest)], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode != 0:
        fail(f"frozen Option-23 selftest failed:\n{proc.stdout}{proc.stderr}")

    print(f"PARITY_FREEZE_SCIENCE_REVISION={policy['science_revision']}")
    print(f"PARITY_FREEZE_SCIENCE_SOURCE_FILES={len(source_manifest['files'])}")
    print("PARITY_FREEZE_REFERENCE_HASHES=ACCEPT")
    print("PARITY_FREEZE_ABIS=ACCEPT")
    print("PARITY_FREEZE_COMPILER_POLICY=ACCEPT")
    print("PARITY_FREEZE_ATDB_EXTERNAL=ACCEPT")
    print("PARITY_FREEZE_RESULT=ACCEPT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
