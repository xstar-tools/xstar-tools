#!/usr/bin/env python3
"""Fail when generated build/cache artifacts are committed in the active tree."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_DIR_NAMES = {"__pycache__", ".pytest_cache", "build", "dist"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".o", ".so", ".dylib", ".dll"}
FORBIDDEN_BASENAMES = {"xstar_cpp", "xstar-cpp"}


def _active(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if not parts:
        return True
    if parts[0] == "historical":
        return False
    if ".git" in parts:
        return False
    return True


def _tracked_paths() -> list[Path] | None:
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, check=True,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [ROOT / item.decode("utf-8") for item in proc.stdout.split(b"\0") if item]


def _is_forbidden(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if not _active(path):
        return False
    if any(part in FORBIDDEN_DIR_NAMES or part.endswith(".egg-info") for part in rel.parts[:-1]):
        return True
    if path.name in FORBIDDEN_BASENAMES:
        return True
    if path.suffix in FORBIDDEN_SUFFIXES:
        return True
    return False


def main() -> int:
    tracked = _tracked_paths()
    if tracked is not None:
        bad = sorted(str(p.relative_to(ROOT)) for p in tracked if _is_forbidden(p))
    else:
        bad = []
        for base, dirs, files in os.walk(ROOT):
            base_path = Path(base)
            dirs[:] = [d for d in dirs if d != "historical" and d != ".git"]
            for d in dirs:
                p = base_path / d
                if _is_forbidden(p / "placeholder"):
                    bad.append(str(p.relative_to(ROOT)) + "/")
            for name in files:
                p = base_path / name
                if _is_forbidden(p):
                    bad.append(str(p.relative_to(ROOT)))
    if bad:
        print("CI_TREE_CLEAN_RESULT=REJECT")
        for item in bad:
            print(f"CI_TREE_CLEAN_FORBIDDEN={item}")
        return 1
    print("CI_TREE_CLEAN_RESULT=ACCEPT")
    print("CI_TREE_CLEAN_GENERATED_ARTIFACTS=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
