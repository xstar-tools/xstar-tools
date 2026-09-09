from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT_MD = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "AUTHORS.md", "PARITY_FREEZE.md"}


def test_root_has_only_current_markdown_documents() -> None:
    assert {p.name for p in ROOT.glob("*.md")} == ALLOWED_ROOT_MD


def test_generated_python_caches_are_absent() -> None:
    assert not list(ROOT.rglob("__pycache__"))
    assert not list(ROOT.rglob("*.pyc"))


def test_historical_conversation_reports_are_not_shipped() -> None:
    names = [p.name for p in ROOT.iterdir()]
    assert not any(name.startswith("xstar_tools_conversation_") for name in names)
    assert not any(name.endswith("_local_validation.md") for name in names)


def test_atomic_database_remains_external() -> None:
    assert not list((ROOT / "src/xstar_tools").rglob("atdb.fits"))
