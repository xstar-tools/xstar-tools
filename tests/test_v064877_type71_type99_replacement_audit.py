from __future__ import annotations
import csv
import tarfile
from pathlib import Path

import xstar_tools
from xstar_tools.xstar.type71_type99_replacement_audit import (
    RELEASE, TYPE71_ORACLE_SHA256, TYPE99_ORACLE_SHA256, portable_lowered_snapshot,
)
from xstar_tools.xstar.v0472_type71_runtime_capture import ORACLE_NAME, verify
from xstar_tools.xstar.v0472_type99_runtime_capture import verify as verify99

ROOT=Path(__file__).resolve().parents[1]

def test_release_is_pinned():
    assert xstar_tools.__version__ == "0.6.48.7.46.19.3.1"
    assert RELEASE == "0.6.48.7.13"

def test_type71_oracle_is_complete_and_exactly_pinned():
    bundle=ROOT/"src/xstar_tools/benchmarks/v064877_type71_row77_runtime_oracle_v0472"
    report=verify(bundle)
    assert report["result"]=="ACCEPT"
    assert report["oracle_sha256"]==TYPE71_ORACLE_SHA256
    rows=list(csv.DictReader((bundle/ORACLE_NAME).open()))
    assert len(rows)==31
    assert all(int(r["upper_row"])==77 and int(r["data_type"])==71 for r in rows)
    assert all(float(r["ptmp_sum"])==1.0 for r in rows)
    assert all(float(r["ans1"])==0.0 and float(r["ans4"])==0.0 for r in rows)

def test_type99_oracle_remains_pinned():
    bundle=ROOT/"src/xstar_tools/benchmarks/v064876_type99_record1695_runtime_oracle_v0472"
    report=verify99(bundle)
    assert report["result"]=="ACCEPT"
    assert report["oracle_sha256"]==TYPE99_ORACLE_SHA256

def test_portable_snapshot_has_no_links(tmp_path):
    lowered=tmp_path/"program"; lowered.mkdir()
    (lowered/"manifest.txt").write_text("program_id=test\n")
    (lowered/"records.csv").write_text("source_position,record\n4,1\n")
    out=tmp_path/"out"; out.mkdir()
    report=portable_lowered_snapshot(lowered,out)
    assert report["links"]==0 and report["unsafe_members"]==0
    archive=out/report["path"]
    with tarfile.open(archive,"r:gz") as tf:
        assert not any(m.issym() or m.islnk() for m in tf.getmembers())

def test_qualification_gate_and_release_scripts_exist():
    cpp=(ROOT/"src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    # v0.6.48.7.36 supersedes the record-1695 qualification oracle with the
    # genuine source-faithful Type-99 evaluator while retaining the general
    # qualification replacement switch for older promoted families.
    assert "evaluate_type99_source_faithful" in cpp
    assert "build_type99_reduced_radiation" in cpp
    assert "XSTAR_QUALIFICATION_REPLACEMENT" in cpp
    assert (ROOT/"run_v04877_type71_type99_replacement_audit.sh").is_file()
    assert (ROOT/"check_v04877_type71_type99_replacement_audit.py").is_file()
