#!/usr/bin/env python3
"""Check the current release-tree boundary without replaying closed milestones."""
from __future__ import annotations

import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_ROOT_MARKDOWN = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "AUTHORS.md", "PARITY_FREEZE.md"}


def reject(message: str) -> None:
    raise SystemExit(f"RELEASE_CANDIDATE_REJECT: {message}")


def run_checker(rel: str) -> None:
    proc = subprocess.run([sys.executable, str(ROOT / rel)], cwd=ROOT, text=True, capture_output=True)
    if proc.returncode:
        reject(f"{rel} failed:\n{proc.stdout}{proc.stderr}")


def main() -> int:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, flags=re.MULTILINE)
    if not match:
        reject("package version missing")
    version = match.group(1)
    unexpected = sorted(p.name for p in ROOT.glob("*.md") if p.name not in ALLOWED_ROOT_MARKDOWN)
    if unexpected:
        reject(f"historical Markdown leaked into repository root: {unexpected[:5]}")
    if list(ROOT.rglob("__pycache__")) or list(ROOT.rglob("*.pyc")):
        reject("generated Python cache files are present")
    if list((ROOT / "src/xstar_tools").rglob("atdb.fits")):
        reject("atdb.fits is bundled")
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    if "xstar_tools_conversation_" in manifest or "local_validation.md" in manifest:
        reject("historical report names remain in MANIFEST.in")
    makefile = (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text(encoding="utf-8")
    all_line = next((line for line in makefile.splitlines() if line.startswith("all:")), "")
    if "xstar-xspec-mpi" in all_line:
        reject("MPI executable leaked into normal make target")
    run_checker("tools/qualification/check_parity_freeze.py")
    run_checker("tools/qualification/check_source_concordance.py")
    run_checker("tools/qualification/check_documentation_coverage.py")
    run_checker("tools/qualification/check_documentation_build_outputs.py")
    print(f"RELEASE_CANDIDATE_VERSION={version}")
    print("RELEASE_CANDIDATE_ROOT_CLEAN=ACCEPT")
    print("RELEASE_CANDIDATE_PARITY_FREEZE=ACCEPT")
    print("RELEASE_CANDIDATE_RESULT=ACCEPT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
