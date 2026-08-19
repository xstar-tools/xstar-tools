from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "qualification/output_control_final_verbose_0_6_82_29_3_10/output_control_final_verbose_scope_0_6_82_29_3_10.json"
EVIDENCE = ROOT / "qualification/output_control_final_verbose_0_6_82_29_3_10/evidence"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_version_and_frozen_identifiers():
    assert 'version = "0.6.82.29.3.10"' in (ROOT / "pyproject.toml").read_text()
    assert "PACKAGE_VERSION ?= 0.6.82.29.3.10" in (ROOT / "src/xstar_tools/xstar/cpp/Makefile").read_text()
    data = json.loads(SCOPE.read_text())
    assert data["milestone"] == "0.6.82.29.3.10"
    assert data["science_revision"] == "0.6.48.12.3.45.3.3.8"
    assert (data["c_api_abi"], data["production_zone_abi"], data["fixed_state_abi"]) == (60487, 6048110, 60488)


def test_final_source_scope_is_numerically_frozen():
    data = json.loads(SCOPE.read_text())
    rows = data["production_hashes"]
    assert len(rows) == 137
    assert [r["path"] for r in rows if r["changed"]] == []
    for row in rows:
        assert row["sha256"] == row["baseline_sha256"]
        assert sha(ROOT / row["path"]) == row["sha256"]


def test_accepted_cpp_evidence_snapshot():
    d = json.loads((EVIDENCE / "cpp_0_6_82_29_3_8_comparison_summary.json").read_text())
    assert d["candidate_version"] == "0.6.82.29.3.8"
    assert d["accept"] is True
    assert d["science_invariance"]["accept"] is True
    assert d["science_invariance"]["worst"] == 0.0
    assert all(c["accept"] for c in d["cases"].values())


def test_python_science_and_final_publication_snapshots():
    full = json.loads((EVIDENCE / "python_full_0_6_82_29_3_9_comparison_summary.json").read_text())
    final = json.loads((EVIDENCE / "python_final_0_6_82_29_3_9_2_comparison_summary.json").read_text())
    assert full["candidate_version"] == "0.6.82.29.3.9"
    assert full["science_invariance"]["accept"] is True
    assert full["science_invariance"]["worst"] == 0.0
    assert final["candidate_version"] == "0.6.82.29.3.9.2"
    assert final["accept"] is True
    assert set(map(int, final["options"])) == {4, 6, 7, 10, 14, 18, 21, 29, 30}
    assert all(item["accept"] for item in final["options"].values())
    assert final["options"]["29"]["identities"] is True
    assert final["options"]["29"]["fortran_rows"] == final["options"]["29"]["cpp_rows"] == 1954


def test_final_checker_contract_and_marker():
    text = (ROOT / "tools/qualification/check_output_control_final_verbose_closure_0_6_82_29_3_10.py").read_text()
    for token in (
        'EXPECTED_VERSION = "0.6.82.29.3.10"',
        'science-invariance cpp=',
        'science-invariance python-full-matrix=',
        'science-invariance python-final-vs-full-lprint6=',
        'OUTPUT_CONTROL_068229310_FINAL_RESULT',
        'run_output_control_integrated_cpp_host_smoke_0_6_82_29_3_8.py',
    ):
        assert token in text


def test_final_closure_decision_waives_only_redundant_python_reruns():
    data = json.loads(SCOPE.read_text())
    waiver = data["python_full_rerun_waiver"]
    assert "lprint=6 superset" in waiver["decision"]
    assert len(waiver["basis"]) == 4
    assert data["accepted_evidence"]["cpp"]["science_invariance_worst"] == 0.0
    assert data["accepted_evidence"]["python_final_publication"]["options"] == [14, 21, 7, 10, 4, 6, 18, 29, 30]
