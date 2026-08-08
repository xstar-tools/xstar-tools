from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def test_active_docs_have_no_version_specific_paths():
    docs = ROOT / "docs"
    pattern = re.compile(r"(?:^|/)(?:v\d|[^/]*(?:v\d{3,}|064\d|0\.6\.\d))", re.I)
    offenders = [
        p.relative_to(docs).as_posix()
        for p in docs.rglob("*")
        if pattern.search(p.relative_to(docs).as_posix())
    ]
    assert offenders == []
    assert not (docs / "v06481232_cpp_ucalc_102_label_coverage.csv").exists()


def test_root_is_free_of_parity_campaign_reports_and_handoffs():
    assert list(ROOT.glob("XSTAR_TOOLS_*.md")) == []
    conversations = {
        p
        for pattern in ("xstar_tools_conversation*.md", "*conversation_handoff*.md")
        for p in ROOT.glob(pattern)
    }
    assert conversations == set()


def test_documentation_cleanup_metadata_contract():
    freeze = json.loads((ROOT / "qualification" / "parity_freeze.json").read_text())
    cleanup = freeze["documentation_history_cleanup"]
    assert cleanup["distribution_version"] == "0.6.51"
    assert cleanup["active_docs_version_specific_paths"] == 0
    assert cleanup["version_specific_doc_source_files"] == 36
    assert cleanup["version_specific_doc_files_archived"] == 32
    assert cleanup["coverage_duplicate_files_removed"] == 4
    assert cleanup["coverage_canonical_files_retained"] == 2
    assert cleanup["malformed_coverage_directory_removed"] is True
    assert cleanup["root_qualification_reports_archived"] == 108
    assert cleanup["root_conversation_handoffs_archived"] == 26


def test_historical_coverage_is_canonical_when_full_history_is_present():
    historical = ROOT / "historical"
    if not historical.exists():
        return  # normal sdist/wheel intentionally prunes historical evidence
    csv = historical / "documentation" / "coverage" / "ucalc_102_label_coverage.csv"
    js = historical / "documentation" / "coverage" / "ucalc_coverage_summary.json"
    assert _sha256(csv) == "0d54172b7dc66c3576fd35ae988285ab5adb141e48b7e496ee5087ff6d6f8ea1"
    assert _sha256(js) == "7a4b977e9a109d2c1afbe7d809b2f20c23013a99dddfac4d504bb7ce065655e5"
    relocation = json.loads((historical / "relocation_manifest.json").read_text())
    assert relocation["counts"]["root_qualification_reports_archived"] == 108
    assert relocation["counts"]["root_conversation_handoffs_archived"] == 26
    assert relocation["counts"]["coverage_duplicate_files_removed"] == 4
