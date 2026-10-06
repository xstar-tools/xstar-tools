#!/usr/bin/env python3
"""Copy a v1 conda recipe and point it at an exact local release sdist."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import shutil


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", type=Path, required=True)
    ap.add_argument("--sdist", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ns = ap.parse_args()

    recipe = ns.recipe.resolve()
    sdist = ns.sdist.resolve()
    out = ns.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(recipe, out)

    path = out / "recipe.yaml"
    text = path.read_text(encoding="utf-8")
    digest = sha256(sdist)
    text, n_url = re.subn(
        r"(?m)^  url: https://pypi\.org/packages/source/x/xstar-tools/xstar_tools-\$\{\{ version \}\}\.tar\.gz$",
        f"  url: {sdist.as_uri()}",
        text,
        count=1,
    )
    if n_url != 1:
        raise SystemExit("canonical PyPI source URL not found in v1 recipe")
    # The context sha256 is the authoritative checksum used by source.sha256.
    text, n_ctx = re.subn(
        r'(?m)^  sha256: "(?:[0-9a-f]{64}|__SOURCE_SHA256__)"$',
        f'  sha256: "{digest}"',
        text,
        count=1,
    )
    if n_ctx != 1:
        raise SystemExit("recipe context sha256 not found")
    path.write_text(text, encoding="utf-8")

    print(f"CONDA_LOCAL_RECIPE_V1={out}")
    print(f"CONDA_LOCAL_SOURCE={sdist}")
    print(f"CONDA_LOCAL_SOURCE_SHA256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
