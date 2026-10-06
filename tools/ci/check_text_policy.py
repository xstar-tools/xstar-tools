#!/usr/bin/env python3
"""Dependency-free repository text-format policy for CI-controlled files.

The project intentionally does not mass-reformat source-faithful scientific code.
This gate enforces stable text hygiene (UTF-8, LF, final newline, no trailing
whitespace) on product/public/CI files while Ruff handles Python lint errors.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = (
    ROOT / ".github" / "workflows",
    ROOT / "tools" / "ci",
    ROOT / "src" / "xstar_tools" / "config.py",
    ROOT / "src" / "xstar_tools" / "data.py",
    ROOT / "src" / "xstar_tools" / "result.py",
    ROOT / "src" / "xstar_tools" / "backends.py",
    ROOT / "src" / "xstar_tools" / "execution.py",
)
TEXT_SUFFIXES = {".py", ".yml", ".yaml", ".md", ".toml", ".json"}


def paths() -> list[Path]:
    out: list[Path] = []
    for item in SCAN_ROOTS:
        if item.is_file():
            out.append(item)
        elif item.is_dir():
            out.extend(p for p in item.rglob("*") if p.is_file() and p.suffix in TEXT_SUFFIXES)
    return sorted(set(out))


def main() -> int:
    bad: list[str] = []
    for path in paths():
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            bad.append(f"{path.relative_to(ROOT)}: not UTF-8")
            continue
        if b"\r\n" in raw or b"\r" in raw:
            bad.append(f"{path.relative_to(ROOT)}: CRLF/CR found")
        if raw and not raw.endswith(b"\n"):
            bad.append(f"{path.relative_to(ROOT)}: missing final newline")
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.rstrip(" \t") != line:
                bad.append(f"{path.relative_to(ROOT)}:{lineno}: trailing whitespace")
    if bad:
        print("CI_TEXT_POLICY_RESULT=REJECT")
        for item in bad:
            print(item)
        return 1
    print("CI_TEXT_POLICY_RESULT=ACCEPT")
    print(f"CI_TEXT_POLICY_FILES={len(paths())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
