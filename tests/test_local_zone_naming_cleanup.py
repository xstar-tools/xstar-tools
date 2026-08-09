from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_local_zone_naming_gate_accepts():
    p=subprocess.run([sys.executable,str(ROOT/'tools/qualification/check_local_zone_naming_cleanup.py')],cwd=ROOT,text=True,capture_output=True)
    assert p.returncode==0,p.stdout+p.stderr
    assert 'LOCAL_ZONE_NAMING_RESULT=ACCEPT' in p.stdout

def test_active_local_zone_paths_and_legacy_abi():
    expected=[
      'src/xstar_tools/xstar/local_zone.py',
      'src/xstar_tools/xstar/all_element_local_zone.py',
      'src/xstar_tools/xstar/complete_local_zone.py',
      'src/xstar_tools/source_port_complete_local_zone_cli.py',
      'src/xstar_tools/xstar/cpp/local_zone_engine.cpp',
      'src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h',
    ]
    for rel in expected: assert (ROOT/rel).is_file(),rel
    for p in (ROOT/'src').rglob('*'):
        if p.is_file(): assert 'fixed_state' not in p.name
    header=(ROOT/'src/xstar_tools/xstar/cpp/xstar_local_zone_engine.h').read_text()
    assert 'xstar_fixed_state_' in header
    assert 'xstar_local_zone_' not in header

def test_naming_manifest_is_behavior_neutral():
    d=json.loads((ROOT/'qualification/local_zone_naming_cleanup_0_6_59.json').read_text())
    assert d['policy']['science_behavior_changed'] is False
    assert all(v['normalizes_to_base'] for k,v in d['renamed_paths'].items() if not k.endswith('.svg'))
    assert all(v['normalizes_to_base'] for v in d['approved_shared_source_edits'].values())
