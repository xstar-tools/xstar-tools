from __future__ import annotations
import hashlib, importlib.util, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MAN=ROOT/'qualification/npass_0_6_82_27_1/npass_hotfix_source_scope_0_6_82_27_1.json'
CPP=ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp'
PY_STATE=ROOT/'src/xstar_tools/xstar/saved_radial_state.py'
PY_TRANSFER=ROOT/'src/xstar_tools/xstar/radial_transfer.py'
RUNNER=ROOT/'tools/qualification/run_c5_npass_multipass_host_smoke_0_6_82_27_1.py'

def _runner():
    spec=importlib.util.spec_from_file_location('npass0271_runner', RUNNER)
    assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
    return mod

def test_0682271_version_and_scope_chain():
    pyproject=(ROOT/'pyproject.toml').read_text(); make=(ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text()
    current_0271='version = "0.6.82.27.1"' in pyproject
    current_0272='version = "0.6.82.27.3"' in pyproject or 'version = "0.6.82.27.4"' in pyproject or 'version = "0.6.82.27.5"' in pyproject or ('version = "0.6.82.27.6"' in pyproject or ('version = "0.6.82.27.7"' in pyproject or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject or 'version = "0.6.82.27.10"' in pyproject)) or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject or 'version = "0.6.82.27.10"' in pyproject))
    assert current_0271 or current_0272
    assert ('PACKAGE_VERSION ?= 0.6.82.27.1' in make) or ('PACKAGE_VERSION ?= 0.6.82.27.3' in make) or ('PACKAGE_VERSION ?= 0.6.82.27.4' in make) or ('PACKAGE_VERSION ?= 0.6.82.27.5' in make) or ('PACKAGE_VERSION ?= 0.6.82.27.6' in make) or (('PACKAGE_VERSION ?= 0.6.82.27.7' in make or 'PACKAGE_VERSION ?= 0.6.82.27.8' in make or 'PACKAGE_VERSION ?= 0.6.82.27.9' in make or 'PACKAGE_VERSION ?= 0.6.82.27.10' in make))
    obj=json.loads(MAN.read_text())
    assert obj['predecessor']=='0.6.82.27'
    assert obj['predecessor_status']=='REJECT_NPASS_GT1_HOST_SCIENCE'
    assert obj['accepted_predecessor_milestone']=='0.6.82.26.3'
    assert obj['science_revision']=='0.6.48.12.3.45.3.3.8'
    assert (obj['c_api_abi'],obj['production_zone_abi'],obj['fixed_state_abi'])==(60487,6048110,60488)
    assert obj['numerical_source_count_predecessor']==137
    changed=set(obj['intentional_numerical_source_changes'])
    assert changed=={
        'src/xstar_tools/xstar/cpp/xstar_standalone.cpp',
        'src/xstar_tools/xstar/radial_transfer.py',
        'src/xstar_tools/xstar/saved_radial_state.py',
    }
    successor2=json.loads((ROOT/'qualification/npass_0_6_82_27_2/npass_hotfix_source_scope_0_6_82_27_2.json').read_text()) if current_0272 else None
    successor3=json.loads((ROOT/'qualification/npass_0_6_82_27_3/npass_hotfix_source_scope_0_6_82_27_3.json').read_text()) if ('version = "0.6.82.27.4"' in pyproject or 'version = "0.6.82.27.5"' in pyproject or ('version = "0.6.82.27.6"' in pyproject or ('version = "0.6.82.27.7"' in pyproject or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject or 'version = "0.6.82.27.10"' in pyproject)) or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject or 'version = "0.6.82.27.10"' in pyproject))) else None
    successor4=json.loads((ROOT/'qualification/npass_0_6_82_27_4/npass_hotfix_source_scope_0_6_82_27_4.json').read_text()) if successor3 is not None else None
    successor5=json.loads((ROOT/'qualification/npass_0_6_82_27_5/npass_hotfix_source_scope_0_6_82_27_5.json').read_text()) if ('version = "0.6.82.27.5"' in pyproject or ('version = "0.6.82.27.6"' in pyproject or ('version = "0.6.82.27.7"' in pyproject or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject or 'version = "0.6.82.27.10"' in pyproject)) or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject or 'version = "0.6.82.27.10"' in pyproject))) else None
    successor6=json.loads((ROOT/'qualification/npass_0_6_82_27_6/npass_hotfix_source_scope_0_6_82_27_6.json').read_text()) if ('version = "0.6.82.27.6"' in pyproject or ('version = "0.6.82.27.7"' in pyproject or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject or 'version = "0.6.82.27.10"' in pyproject)) or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject or 'version = "0.6.82.27.10"' in pyproject)) else None
    successor7=json.loads((ROOT/'qualification/npass_0_6_82_27_7/npass_hotfix_source_scope_0_6_82_27_7.json').read_text()) if ('version = "0.6.82.27.7"' in pyproject or ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject or 'version = "0.6.82.27.10"' in pyproject)) else None
    successor8=json.loads((ROOT/'qualification/npass_0_6_82_27_8/npass_hotfix_source_scope_0_6_82_27_8.json').read_text()) if ('version = "0.6.82.27.8"' in pyproject or 'version = "0.6.82.27.9"' in pyproject or 'version = "0.6.82.27.10"' in pyproject) else None
    successor9=json.loads((ROOT/'qualification/npass_0_6_82_27_9/npass_hotfix_source_scope_0_6_82_27_9.json').read_text()) if 'version = "0.6.82.27.9"' in pyproject else None
    for rel,old in obj['predecessor_sha256'].items():
        expected_0271=obj['candidate_changed_sha256'].get(rel,old)
        if successor2 is None:
            now=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(); assert now==expected_0271, rel; continue
        assert successor2['predecessor_sha256'][rel]==expected_0271, rel
        expected_0272=successor2['candidate_changed_sha256'].get(rel, expected_0271)
        if successor3 is None: continue
        assert successor3['predecessor_sha256'][rel]==expected_0272, rel
        expected_0273=successor3['candidate_changed_sha256'].get(rel, expected_0272)
        assert successor4['predecessor_sha256'][rel]==expected_0273, rel
        expected_0274=successor4['candidate_changed_sha256'].get(rel, expected_0273)
        if successor5 is None:
            now=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(); assert now==expected_0274, rel; continue
        assert successor5['predecessor_sha256'][rel]==expected_0274, rel
        expected_0275=successor5['candidate_changed_sha256'].get(rel, expected_0274)
        if successor6 is None:
            now=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(); assert now==expected_0275, rel; continue
        assert successor6['predecessor_sha256'][rel]==expected_0275, rel
        expected_0276=successor6['candidate_changed_sha256'].get(rel, expected_0275)
        if successor7 is None:
            now=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(); assert now==expected_0276, rel
            continue
        assert successor7['predecessor_sha256'][rel]==expected_0276, rel
        expected_0277=successor7['candidate_changed_sha256'].get(rel, expected_0276)
        if successor8 is None:
            now=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(); assert now==expected_0277, rel
            continue
        assert successor8['predecessor_sha256'][rel]==expected_0277, rel
        expected_0278=successor8['candidate_changed_sha256'].get(rel, expected_0277)
        if successor9 is None:
            now=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(); assert now==expected_0278, rel
            continue
        assert successor9['predecessor_sha256'][rel]==expected_0278, rel
        expected_0279=successor9['candidate_changed_sha256'].get(rel, expected_0278)
        now=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest(); assert now==expected_0279, rel

def test_0682271_cpp_savd_appends_tail_and_live_rows_share_step_state():
    text=CPP.read_text()
    assert 'hdus.push_back(std::move(shell));' in text
    assert 'hdus.insert(hdus.begin()' not in text
    assert 'pass-1 records are HDU 3=zone1, 4=zone2, 5=terminal' in text
    assert 'print_xstar_style_live_multipass_heading' in text
    assert 'print_xstar_style_live_pprint_row_v0682271' in text
    assert 'whole.legacy_pprint.radial_rows.back()' in text
    # Multipass must not also use the older reconstructed live row path.
    assert text.count('effective_npass_v068227 == 1u && live_text_zone_progress_enabled()') >= 2

def test_0682271_python_savd_appends_tail_and_validation_encodes_replay():
    saved=PY_STATE.read_text(); transfer=PY_TRANSFER.read_text()
    assert 'self.hdu_snapshots.append(snapshot)' in saved
    assert 'self.hdu_snapshots.insert(inserted, snapshot)' not in saved
    assert 'inserted = self.hdu_count' in saved
    assert 'pass1.terminal_saved_hdu == 5' in transfer
    assert 'snapshot_at_hdu(4).zone_index == 2' in transfer
    assert 'snapshot_at_hdu(5).terminal_record' in transfer
    assert 'pass2.terminal_saved_hdu == 6' in transfer

def test_0682271_dependency_free_source_replay_is_hdu5_4_3():
    hdus=[None,None,None]
    def savd(after,label):
        assert 1 <= after < len(hdus)
        hdus.append(label)
    savd(2,'zone1'); savd(3,'zone2'); savd(3,'terminal')
    assert hdus[3:]==['zone1','zone2','terminal']
    numrec=3
    assert [hdus[(numrec+1-jkp)+2] for jkp in range(1,numrec+1)]==['terminal','zone2','zone1']

def test_0682271_live_terminal_gate_rejects_the_actual_027_pattern(tmp_path):
    r=_runner()
    # Mimic the rejected .27 symptom: all rows remain under pass 1 while STEP
    # contains the requested pass headings.  The new gate must reject it.
    cand=tmp_path/'cpp.log'; ref=tmp_path/'fortran.log'; step=tmp_path/'xout_step.log'
    cand.write_text(' pass number=           1          -1\n   11.50 -36.00 -10.00 1.00 1.20 8.00 4.67 -0.01 0.00 -10.00 -10.00 29\n   11.62 -0.62 19.00 0.76 1.20 8.00 4.67 -5.36 0.00 -10.00 -10.00 8\n final print: 1\n')
    ref.write_text(' pass number=           1          -1\n   11.50 -36.00 -10.00 1.00 1.20 8.00 4.67 -0.01 0.00 -10.00 -10.00 29\n pass number=           2           1\n   11.62 -0.62 19.00 0.76 1.20 8.00 4.67 -5.36 0.00 -10.00 -10.00 8\n final print: 1\n')
    step.write_text(' pass number= 1 -1\n print option:17\n 11.50 -36.00 -10.00 1.00 1.20 8.00 4.67 -0.01 0.00 -10.00 -10.00 29\n print option:18\n pass number= 2 1\n print option:17\n 11.62 -0.62 19.00 0.76 1.20 8.00 4.67 -5.36 0.00 -10.00 -10.00 8\n print option:18\n')
    got=r.compare_live_option17(cand,ref,step,2)
    assert got['accept'] is False
    assert got['live_step_exact'] is False

def test_0682271_host_runner_is_cpp_first_and_can_reuse_fortran_tree():
    text=RUNNER.read_text()
    assert 'EXPECTED_VERSION = "0.6.82.27.1"' in text
    assert '--fortran-reference-root' in text
    assert 'elif args.action in {"run-cpp", "fortran-cpp"}' in text
    assert 'backends = ("cpp",)' in text
    assert 'compare_live_option17' in text
