from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_cpp_tree_consolidation_checker_accepts():
    p=subprocess.run([sys.executable,str(ROOT/'tools/qualification/check_cpp_tree_consolidation_0_6_74.py')],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'CPP_TREE_CONSOLIDATION_RESULT=ACCEPT' in p.stdout
    assert 'CPP_TREE_CONSOLIDATION_CPP44_FITS_PAYLOAD_PAIRS=558/558' in p.stdout

def test_all_cpp_sources_and_headers_are_in_cpp():
    xroot=ROOT/'src/xstar_tools/xstar'; cpp=xroot/'cpp'
    outside=[p for p in xroot.rglob('*') if p.is_file() and p.suffix in {'.cpp','.h','.hpp'} and cpp not in p.parents]
    assert outside==[]
    assert (cpp/'xstar_cpp_frontend.cpp').is_file()
    assert not (xroot/'native').exists()

def test_zone_cpp_matches_frozen_cpp44_reference_exactly():
    d=json.loads((ROOT/'qualification/zone_cpp_0667_vs_cpp44_0_6_74.json').read_text())
    assert d['result']=='ACCEPT_CPP44_EXACT_PARITY'
    assert d['model_count']==62
    assert d['fits_payload_bitexact_pairs']==558
    assert d['fits_payload_pairs']==558
    assert d['step_normalized_exact_models']==62
    assert d['exact_gate_models']==62
