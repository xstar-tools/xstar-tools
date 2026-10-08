"""0.6.91.2 gate self-tests: no production-science data, no host ACCEPT."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/qualification/run_linux_arm64_science_host_0_6_91_2.py"
SPEC = importlib.util.spec_from_file_location("linux_arm64_science_06912", SCRIPT)
assert SPEC and SPEC.loader
sci = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sci)
ROOT = SCRIPT.parents[2]


def test_frozen_accepted_science_source_hashes_unchanged():
    hashes = sci.arm.source_hashes(ROOT)
    assert len(hashes) == 51
    assert sci.VERSION == "0.6.91.2"
    assert sci.arm.LIBRARIES and sci.arm.EXECUTABLES


def test_scaffold_golden_self_comparison():
    golden = ROOT / sci.REFERENCE_REL
    stats = sci.check_scaffold_log(golden / "xout_step.log", golden / "xout_step.log")
    assert stats["numeric_fields"] >= 8
    assert sci.check_scaffold_visits(golden / "visited_records.csv", golden / "visited_records.csv") == 23


def test_scaffold_tamper_discrete_rejects(tmp_path):
    golden = ROOT / sci.REFERENCE_REL / "xout_step.log"
    modified = tmp_path / "xout_step.log"
    modified.write_text(golden.read_text().replace("records_evaluated=23", "records_evaluated=24"))
    with pytest.raises(sci.GateError, match="discrete mismatch"):
        sci.check_scaffold_log(modified, golden)


def test_scaffold_floating_point_accepts_last_bit_and_rejects_material(tmp_path):
    golden = ROOT / sci.REFERENCE_REL / "xout_step.log"
    modified = tmp_path / "xout_step.log"
    modified.write_text(golden.read_text().replace("total_cooling=0.00012749202919629823", "total_cooling=0.00012749202919629824"))
    sci.check_scaffold_log(modified, golden)
    modified.write_text(golden.read_text().replace("total_cooling=0.00012749202919629823", "total_cooling=0.00013"))
    with pytest.raises(sci.GateError, match="float mismatch"):
        sci.check_scaffold_log(modified, golden)


def test_numeric_array_gate_does_not_ignore_corruption():
    accepted = sci.numeric_array_stats(np.array([1., 3., 5.]), np.array([1., 3., 5.]), rtol=.01, floor=1e-30)
    assert accepted["normalized_l1"] == 0
    with pytest.raises(sci.GateError, match="normalized L1"):
        sci.numeric_array_stats(np.array([1., 3., 7.]), np.array([1., 3., 5.]), rtol=.01, floor=1e-30)
    with pytest.raises(sci.GateError, match="nonfinite"):
        sci.numeric_array_stats(np.array([1., np.nan]), np.array([1., 2.]), rtol=.01, floor=1e-30)
    with pytest.raises(sci.GateError, match="zero-baseline"):
        sci.numeric_array_stats(np.array([1., 1e-10]), np.array([1., 0.]), rtol=.01, floor=1e-30)
    with pytest.raises(sci.GateError, match="non-numeric"):
        sci.numeric_array_stats(np.array(["a"]), np.array(["b"]), rtol=.01, floor=1e-30)


def _suite(tmp_path):
    suite = tmp_path / "suite"
    data = suite / "data"
    data.mkdir(parents=True)
    for f in ("atdb.fits", "coheat.dat"):
        (data / f).write_bytes(b"unit-test-placeholder-" + f.encode())
    doc = {"schema": "xstar-linux-arm64-science-reference-v1", "science_revision": "0.6.90.5.5",
           "atomic_data_sha256": sci.digest(data / "atdb.fits"),
           "coheat_sha256": sci.digest(data / "coheat.dat"), "cases": []}
    for cid, role in (("single", "single_element"), ("mn", "multi_element_mn")):
        case = suite / "cases" / cid
        ref = case / "reference"
        ref.mkdir(parents=True)
        inp = case / "xstar.par"
        inp.write_text("mnabund=1\n" if role == "multi_element_mn" else "mgabund=1\n")
        hashes = {}
        for f in (*sci.MODEL_PRODUCTS, "xout_step.log"):
            (ref / f).write_bytes(b"accepted-golden-" + cid.encode() + f.encode())
            hashes[f] = sci.digest(ref / f)
        doc["cases"].append({"id": cid, "role": role,
                             "reference_origin": "fortran-xstar-2.59g",
                             "input_sha256": sci.digest(inp), "reference_sha256": hashes})
    (suite / "manifest.json").write_text(json.dumps(doc))
    return suite, data


def test_reference_manifest_pinning_and_roles(tmp_path):
    suite, data = _suite(tmp_path)
    manifest, cases = sci.verify_pinned_inputs(suite, data, tmp_path)
    assert len(cases) == 2
    assert manifest["science_revision"] == "0.6.90.5.5"
    (suite / "cases/mn/reference/xout_spect1.fits").write_bytes(b"UNTRUSTED REBASELINED PRODUCT")
    with pytest.raises(sci.GateError, match="frozen science reference mismatch"):
        sci.verify_pinned_inputs(suite, data, tmp_path)


def test_reference_manifest_rejects_missing_mn_and_atomic_tamper(tmp_path):
    suite, data = _suite(tmp_path)
    doc_path = suite / "manifest.json"
    doc = json.loads(doc_path.read_text())
    doc["cases"][1]["role"] = "single_element"
    doc_path.write_text(json.dumps(doc))
    with pytest.raises(sci.GateError, match="both science regression case roles"):
        sci.verify_pinned_inputs(suite, data, tmp_path)
    doc["cases"][1]["role"] = "multi_element_mn"
    doc_path.write_text(json.dumps(doc))
    (data / "atdb.fits").write_bytes(b"tampered")
    with pytest.raises(sci.GateError, match="unpinned science atomic data"):
        sci.verify_pinned_inputs(suite, data, tmp_path)


def test_no_false_host_acceptance_without_real_science():
    source = SCRIPT.read_text()
    assert 'report["host_result"] = "NOT_RUN"' in source
    assert 'report["host_result"] = "ACCEPT"' in source
    assert '"host_result": "REJECT"' in source
    assert "run_full_science" in source
    assert "source_hashes(workroot)" in source
    assert "--science-cases" in source
