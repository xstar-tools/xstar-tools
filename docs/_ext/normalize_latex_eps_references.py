#!/usr/bin/env python3
"""Normalize Sphinx EPS image references for classic LaTeX/DVI builds.

Sphinx may emit an EPS image as ``{name}.eps`` inside the argument to
``\\sphinxincludegraphics`` (for example ``{{backend_dispatch}.eps}``).
That spelling is legal in some TeX contexts but is awkward for classic
LaTeX/DVI workflows and defeats simple filename checks.  This helper rewrites
only that EPS-specific form to the conventional ``name.eps`` spelling while
leaving all other LaTeX untouched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

EPS_REFERENCE = re.compile(r"\{\{([^{}]+)\}\.eps\}")


def normalize_text(text: str) -> tuple[str, int]:
    """Return normalized LaTeX text and the number of rewritten references."""
    return EPS_REFERENCE.subn(r"{\1.eps}", text)


def normalize_file(path: Path) -> int:
    """Normalize one generated Sphinx LaTeX file in place."""
    original = path.read_text(encoding="utf-8")
    normalized, count = normalize_text(original)
    if normalized != original:
        path.write_text(normalized, encoding="utf-8")
    return count


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: normalize_latex_eps_references.py PATH_TO_TEX", file=sys.stderr)
        return 2
    path = Path(args[0])
    if not path.is_file():
        print(f"ERROR: LaTeX file does not exist: {path}", file=sys.stderr)
        return 2
    count = normalize_file(path)
    print(f"LATEX_EPS_REFERENCE_NORMALIZATION={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
