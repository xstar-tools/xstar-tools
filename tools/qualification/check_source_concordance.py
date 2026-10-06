#!/usr/bin/env python3
"""Validate the current source-concordance map without replaying closed milestones."""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "qualification" / "source_concordance.json"
SCIENCE_HASHES = ROOT / "qualification" / "parity_freeze_current_source_hashes.json"


def reject(message: str) -> None:
    raise SystemExit(f"SOURCE_CONCORDANCE_REJECT: {message}")


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("science_revision") != "0.6.90.5.5":
        reject("science revision mismatch")
    canonical = str(data.get("canonical_fortran", ""))
    if "2.59g" not in canonical:
        reject("canonical FORTRAN XSTAR 2.59g authority is not recorded")

    source_hashes = json.loads(SCIENCE_HASHES.read_text(encoding="utf-8"))
    protected = set(source_hashes.get("files", {}))

    entries = data.get("entries", [])
    if not entries:
        reject("no concordance entries")
    seen_ids: set[str] = set()
    for entry in entries:
        ident = str(entry.get("id", ""))
        if not ident or ident in seen_ids:
            reject(f"invalid or duplicate entry id: {ident!r}")
        seen_ids.add(ident)
        if not entry.get("fortran"):
            reject(f"{ident}: missing canonical FORTRAN lineage")
        for group in ("python", "cpp"):
            paths = entry.get(group, [])
            if not paths:
                reject(f"{ident}: no {group} implementation paths")
            for rel in paths:
                path = ROOT / rel
                if not path.is_file():
                    reject(f"{ident}: missing active {group} source {rel}")
        tests = entry.get("characterization_tests", [])
        if not tests:
            reject(f"{ident}: no current characterization tests")
        for rel in tests:
            if not (ROOT / rel).is_file():
                reject(f"{ident}: missing characterization test {rel}")

    for key in ("documentation", "diagrams"):
        for rel in data.get(key, []):
            if not (ROOT / rel).is_file():
                reject(f"missing {key[:-1]} artifact: {rel}")

    active_comment_paths = set(data.get("source_comment_files", [])) | set(data.get("python_source_comment_files", [])) | set(data.get("cpp_source_comment_files", []))
    for rel in sorted(active_comment_paths):
        if not (ROOT / rel).is_file():
            reject(f"missing documented source-comment file: {rel}")

    # Every active science-critical implementation source represented by the
    # concordance must remain covered by the parity hash boundary when listed.
    mapped = {rel for entry in entries for group in ("python", "cpp") for rel in entry.get(group, [])}
    protected_mapped = mapped & protected
    if not protected_mapped:
        reject("concordance has no overlap with protected science-source hashes")

    print(f"SOURCE_CONCORDANCE_ENTRIES={len(entries)}")
    print(f"SOURCE_CONCORDANCE_PROTECTED_MAPPED_FILES={len(protected_mapped)}")
    print("SOURCE_CONCORDANCE_CURRENT_TESTS=ACCEPT")
    print("SOURCE_CONCORDANCE_RESULT=ACCEPT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
