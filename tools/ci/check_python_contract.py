#!/usr/bin/env python3
"""Tier-0 Python syntax/import and public API annotation contract."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
import sys
from typing import get_type_hints

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

PUBLIC_CALLABLES = {
    "XStarConfig.from_par_file": ("path", "return"),
    "XStarConfig.from_mapping": ("parameters", "return"),
    "XStarConfig.from_fortran_run_directory": ("directory", "return"),
    "XStarConfig.parameter_mapping": ("return",),
    "XStarData.from_directory": ("directory", "return"),
    "XStarData.validate": ("return",),
    "XStarData.identity": ("return",),
    "XStarProducts.as_dict": ("return",),
    "XStarResult.as_dict": ("return",),
}


def _compile_python() -> int:
    count = 0
    for path in sorted((ROOT / "src").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec", dont_inherit=True)
        ast.parse(source, filename=str(path))
        count += 1
    return count


def _resolve(root: object, dotted: str) -> object:
    obj = root
    for part in dotted.split("."):
        obj = getattr(obj, part)
    return obj


def main() -> int:
    syntax_files = _compile_python()
    import xstar_tools
    from xstar_tools import BackendMode, XStarConfig, XStarData, XStarProducts, XStarResult, run_xstar
    import xstar_tools.backends as backends

    namespace = {
        "XStarConfig": XStarConfig,
        "XStarData": XStarData,
        "XStarProducts": XStarProducts,
        "XStarResult": XStarResult,
    }
    missing: list[str] = []
    for dotted, required in PUBLIC_CALLABLES.items():
        head, tail = dotted.split(".", 1)
        obj = _resolve(namespace[head], tail)
        hints = get_type_hints(obj)
        for name in required:
            if name not in hints:
                missing.append(f"{dotted}:{name}")
    assert issubclass(BackendMode, str)
    assert callable(run_xstar)
    assert callable(backends.available) and callable(backends.describe)
    assert isinstance(xstar_tools.__science_revision__, str) and xstar_tools.__science_revision__
    if missing:
        print("CI_PUBLIC_API_TYPES_RESULT=REJECT")
        for item in missing:
            print(f"CI_PUBLIC_API_TYPES_MISSING={item}")
        return 1
    print("CI_PYTHON_SYNTAX_IMPORT_RESULT=ACCEPT")
    print(f"CI_PYTHON_SYNTAX_FILES={syntax_files}")
    print("CI_PUBLIC_API_TYPES_RESULT=ACCEPT")
    print(f"CI_PUBLIC_API_TYPED_CALLABLES={len(PUBLIC_CALLABLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
