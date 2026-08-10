from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def test_conda_packaging_gate_accepts():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_conda_packaging.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "CONDA_PACKAGING_RESULT=ACCEPT" in proc.stdout


def test_offline_science_smoke_executes_without_atdb():
    if not (ROOT / "conda/recipe/tests/offline_science_smoke.py").is_file():
        return
    proc = subprocess.run(
        [sys.executable, "conda/recipe/tests/offline_science_smoke.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONPATH": str(SRC), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "XSTAR_TOOLS_CONDA_OFFLINE_SCIENCE_SMOKE=ACCEPT" in proc.stdout


def test_recipe_is_single_package_and_platform_policy_is_explicit():
    recipe = ROOT / "conda/recipe/meta.yaml"
    if not recipe.is_file():
        manifest = json.loads((ROOT / "qualification/conda_packaging_0_6_72.json").read_text())
        assert manifest["package_outputs"] == ["xstar-tools"]
        assert manifest["atdb_bundled"] is False
        return
    text = recipe.read_text(encoding="utf-8")
    assert "outputs:" not in text
    assert "compiler('cxx')" in text
    assert "cfitsio" in text
    assert "# [linux]" in text
    assert "h5py >=3" in text and "scipy >=1.8" in text
    assert "atdb.fits" not in text


def test_legacy_xstar_python_port_is_historical_only():
    assert not (ROOT / "XSTAR_PYTHON_PORT.md").exists()
    manifest = json.loads((ROOT / "qualification/conda_packaging_0_6_72.json").read_text())
    archived = ROOT / manifest["legacy_root_document"]["historical_path"]
    if (ROOT / "historical").is_dir():
        assert archived.is_file()
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == manifest["legacy_root_document"]["sha256"]
    assert "include XSTAR_PYTHON_PORT.md" not in (ROOT / "MANIFEST.in").read_text()


def test_conda_is_not_in_pypi_sdist_manifest():
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "recursive-include conda" not in manifest
