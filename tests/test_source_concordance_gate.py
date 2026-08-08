from __future__ import annotations

import fnmatch
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _concordance():
    return json.loads((ROOT / "qualification" / "source_concordance.json").read_text())


def test_source_concordance_metadata_and_docs_exist():
    data = _concordance()
    assert data["schema"] == "xstar-tools-source-concordance-v1"
    assert data["productization_version"] == "0.6.54"
    assert data["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert data["canonical_fortran"]["version"] == "2.59g"
    for rel in data["documentation"] + data["diagrams"]:
        assert (ROOT / rel).is_file()


def test_source_concordance_entries_have_real_characterization_tests():
    data = _concordance()
    ids = [entry["id"] for entry in data["entries"]]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 16
    text = (ROOT / "docs" / "developer" / "python_cpp_fortran_concordance.md").read_text()
    for entry in data["entries"]:
        assert entry["id"] in text
        assert entry["characterization_tests"]
        for rel in entry["characterization_tests"]:
            assert (ROOT / rel).is_file()


def test_source_comments_obey_freeze_policy():
    data = _concordance()
    frozen = json.loads((ROOT / "qualification" / "parity_freeze_science_hashes.json").read_text())
    for rel in data["source_comment_files"]:
        assert rel not in frozen
        text = (ROOT / rel).read_text(errors="replace")
        assert "Source correspondence:" in text
        assert "Concordance:" in text
    assert data["pinned_source_policy"]["non_science_cpp_refactor_manifest"] == "qualification/cpp_non_science_refactor_0_6_54.json"
    assert len(data["cpp_source_comment_files"]) == 47
    for rel in data["cpp_source_comment_files"]:
        text = (ROOT / rel).read_text(errors="replace")
        assert text.startswith("// XSTAR-SOURCE-CORRESPONDENCE-BEGIN\n")
        assert "// Fortran:" in text[:2500]
        assert "// Concordance:" in text[:2500]


def test_every_parity_pinned_scientific_source_has_a_refactor_rule():
    data = _concordance()
    frozen = json.loads((ROOT / "qualification" / "parity_freeze_science_hashes.json").read_text())
    rules = data["refactor_gate"]["path_rules"]
    valid_ids = {entry["id"] for entry in data["entries"]}
    for rule in rules:
        assert set(rule["concordance_ids"]) <= valid_ids
    uncovered = [
        rel for rel in frozen
        if not any(fnmatch.fnmatch(rel, rule["glob"]) for rule in rules)
    ]
    assert uncovered == []


def test_required_architecture_diagrams_are_registered():
    data = _concordance()
    assert {Path(rel).name for rel in data["diagrams"]} == {
        "controller_radial_flow.svg",
        "fixed_state_solve.svg",
        "publication_ownership.svg",
        "backend_dispatch.svg",
    }

def test_refactor_policy_requires_current_runnable_characterization():
    data = _concordance()
    policy = data["characterization_policy"]
    assert policy["historical_lineage_may_not_substitute_for_current_test"] is True
    assert "current runnable characterization test" in policy["refactor_requirement"]

