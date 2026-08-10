from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "references" / "current"


def test_milestone11_checker_accepts_current_tree():
    proc = subprocess.run(
        [sys.executable, "tools/qualification/check_reference_normalization_0_6_79.py"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    assert proc.returncode == 0, proc.stdout
    assert "REFERENCE_NORMALIZATION_0679_RESULT=ACCEPT" in proc.stdout


def test_current_registry_is_exact_62_and_matches_frozen_cpp44_order():
    with (CURRENT / "model_registry.csv").open(newline="", encoding="utf-8") as handle:
        current = list(csv.DictReader(handle))
    with (ROOT / "qualification/zone_cpp_0667_vs_cpp44_0_6_74.csv").open(newline="", encoding="utf-8") as handle:
        frozen = list(csv.DictReader(handle))
    assert len(current) == 62
    assert [r["model"] for r in current] == [r["model"] for r in frozen]
    assert all(r["frozen_cpp44_exact"] == "true" for r in current)


def test_current_smoke_policy_excludes_c5_and_slow_ca():
    rows = list(csv.DictReader((CURRENT / "model_registry.csv").open(newline="", encoding="utf-8")))
    defaults = {r["model"] for r in rows if r["tier1_default"] == "true"}
    assert defaults == {
        "helike_type69/o7_ne1e10",
        "helike_type69/mg11_ne1e8",
        "helike_type69/ca19_xi2_ne1",
    }
    assert all(r["routine_smoke_allowed"] == "false" for r in rows if "/c5_" in r["model"])
    assert next(r for r in rows if r["model"] == "helike_type69/ca19_ne1e8")["routine_smoke_allowed"] == "false"


def test_structural_exceptions_are_first_class_metadata():
    doc = json.loads((CURRENT / "structural_exceptions.json").read_text())
    assert {x["model"] for x in doc["python_publication_inventory_exceptions"]} == {
        "helike_type69/ca19_xi2_ne1", "helike_type69/o7_ne1e10"
    }
    assert doc["c5"]["routine_rerun"] is False
    assert doc["fortran_option24"]["candidate_only_allowed_ion"] == "he_ii"


def test_external_assets_fail_closed_on_known_vs_unknown_hashes():
    doc = json.loads((CURRENT / "external_assets.json").read_text())
    assets = {x["id"]: x for x in doc["assets"]}
    assert assets["frozen-cpp44-products"]["sha256"] == "f46a15bc7db7a8adc9655f3e15b5243386cd7bfc2567dfc75eadc1030da555d2"
    assert assets["canonical-suite-inputs"]["sha256"] is None
    assert assets["canonical-fortran-products"]["sha256"] is None


def test_release_candidate_tag_contract():
    from tools.release.check_release_candidate_boundary import tag_matches

    assert tag_matches("0.6.79", "v0.6.79rc1")
    assert tag_matches("0.6.79", "v0.6.79rc12")
    assert not tag_matches("0.6.79", "v0.6.78rc1")
    assert not tag_matches("0.6.79", "v0.6.79")
