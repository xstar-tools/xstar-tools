"""Thin setuptools hook; all project metadata/configuration lives in pyproject.toml."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from setuptools import setup

_support_path = Path(__file__).with_name("build_support.py")
_spec = importlib.util.spec_from_file_location("xstar_tools_build_support", _support_path)
if _spec is None or _spec.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load build support: {_support_path}")
_support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_support)

setup(cmdclass={"build_py": _support.XStarBuildPy}, distclass=_support.XStarDistribution)
