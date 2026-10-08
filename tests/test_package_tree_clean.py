from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT_MD = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "AUTHORS.md", "PARITY_FREEZE.md"}


def test_root_has_only_current_markdown_documents() -> None:
    assert {p.name for p in ROOT.glob("*.md")} == ALLOWED_ROOT_MD


def test_generated_python_caches_are_absent() -> None:
    """Reject tracked generated artifacts, not caches created by pytest itself.

    When the tests are invoked from an extracted source archive there is no VCS
    index. Source archive cleanliness is checked before packaging; runtime
    imports can legitimately create untracked __pycache__ directories.
    """
    if not (ROOT / ".git").exists():
        pytest.skip("VCS index unavailable; source archive cleanliness is a packaging gate")
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    offenders = [
        Path(item.decode("utf-8", errors="surrogateescape"))
        for item in tracked.split(b"\0") if item
    ]
    offenders = [
        path for path in offenders
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}
    ]
    assert not offenders, f"Tracked Python cache artifacts: {offenders}"


def test_historical_conversation_reports_are_not_shipped() -> None:
    names = [p.name for p in ROOT.iterdir()]
    assert not any(name.startswith("xstar_tools_conversation_") for name in names)
    assert not any(name.endswith("_local_validation.md") for name in names)


def test_atomic_database_remains_external() -> None:
    assert not list((ROOT / "src/xstar_tools").rglob("atdb.fits"))
