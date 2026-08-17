from pathlib import Path
import subprocess, sys
ROOT=Path(__file__).resolve().parents[1]

def test_source_gate():
 p=subprocess.run([sys.executable,str(ROOT/'tools/qualification/check_low_xi_memory_performance_0_6_82_22.py')],cwd=ROOT,capture_output=True,text=True)
 assert p.returncode==0,p.stdout+p.stderr
 assert 'LOW_XI_MEMORY_PERFORMANCE_068222_RESULT=ACCEPT' in p.stdout

def test_emult_runner_prepare_defaults(tmp_path):
 runner=ROOT/'tools/qualification/run_c5_emult_sweep_0_6_82_22.py'
 p=subprocess.run([sys.executable,str(runner),'prepare','--package',str(ROOT),'--data-dir',str(ROOT),'--output-root',str(tmp_path/'out')],cwd=ROOT,capture_output=True,text=True)
 assert p.returncode==0,p.stdout+p.stderr
 assert 'C5_EMULT_VALUES=0.1,0.25,0.5,1' in p.stdout

def test_runner_uses_stable_csv_schema():
 src=(ROOT/'tools/qualification/run_c5_emult_sweep_0_6_82_22.py').read_text()
 assert 'fieldnames=SUMMARY_FIELDS' in src
 assert 'fieldnames=list(rows[0].keys())' not in src

def test_production_snapshot_compaction_is_nonterminal_and_diagnostic_safe():
 src=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
 assert 'finals[finals.size() - 2u]' in src
 assert '!data.reference_trajectory_mode && !data.reference_diagnostics_enabled' in src
 assert 'compact_completed_snapshot_rrc_v068222' in src

def test_diagnostic_scratch_is_lazy():
 src=(ROOT/'src/xstar_tools/xstar/cpp/local_zone_engine.cpp').read_text()
 assert 'if (opacity_producer_audit_v82_patch511 || exact_absorption_audit_v82_patch5203)' in src
 assert 'producer_temp_opacity.assign(input.radiation_bin_count, 0.0);' in src
