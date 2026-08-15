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
    supported=('0.6.82.27.1','0.6.82.27.2','0.6.82.27.3','0.6.82.27.4','0.6.82.27.5','0.6.82.27.6','0.6.82.27.7','0.6.82.27.8','0.6.82.27.9','0.6.82.27.10','0.6.82.27.12','0.6.82.27.13','0.6.82.27.14','0.6.82.27.15','0.6.82.27.16','0.6.82.29','0.6.82.29.1','0.6.82.29.2')
    assert any(f'version = "{v}"' in pyproject for v in supported)
    assert any(f'PACKAGE_VERSION ?= {v}' in make for v in supported)
    obj=json.loads(MAN.read_text())
    assert obj['predecessor']=='0.6.82.27'
    assert obj['predecessor_status']=='REJECT_NPASS_GT1_HOST_SCIENCE'
    assert obj['accepted_predecessor_milestone']=='0.6.82.26.3'
    assert obj['science_revision']=='0.6.48.12.3.45.3.3.8'
    assert (obj['c_api_abi'],obj['production_zone_abi'],obj['fixed_state_abi'])==(60487,6048110,60488)
    assert obj['numerical_source_count_predecessor']==137
    assert set(obj['intentional_numerical_source_changes'])=={
        'src/xstar_tools/xstar/cpp/xstar_standalone.cpp',
        'src/xstar_tools/xstar/radial_transfer.py',
        'src/xstar_tools/xstar/saved_radial_state.py',
    }
    current=next(v for v in supported if f'version = "{v}"' in pyproject)
    current_suffix=current.rsplit('.',1)[-1]
    max_hotfix=16 if current in ('0.6.82.29','0.6.82.29.1','0.6.82.29.2') else (int(current_suffix) if current != '0.6.82.27' else 0)
    successors=[]
    for n in range(2,max_hotfix+1):
        q=ROOT/f'qualification/npass_0_6_82_27_{n}/npass_hotfix_source_scope_0_6_82_27_{n}.json'
        if q.is_file(): successors.append(json.loads(q.read_text()))
    for rel,old in obj['predecessor_sha256'].items():
        expected=obj['candidate_changed_sha256'].get(rel,old)
        for successor in successors:
            assert successor['predecessor_sha256'][rel]==expected, f"{successor['milestone']}:{rel}"
            expected=successor['candidate_changed_sha256'].get(rel,expected)
        now=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
        active_version=next((line.split('=',1)[1].strip().strip('\"') for line in pyproject.splitlines() if line.startswith('version = ')), '')
        if active_version in ('0.6.82.27.16.5', '0.6.82.28','0.6.82.28.1','0.6.82.29','0.6.82.29.1','0.6.82.29.2'):
            later=json.loads((ROOT/'qualification/npass_0_6_82_27_16_5/type50_nbinc_source_correction_scope_0_6_82_27_16_5.json').read_text())
            row=next((r for r in later['production_hashes'] if r['path']==rel), None)
            if row is not None and row['baseline_sha256'] != row['sha256']:
                expected=row['sha256']
        if active_version in ('0.6.82.28', '0.6.82.28.1','0.6.82.29','0.6.82.29.1','0.6.82.29.2'):
            spectrum=json.loads((ROOT/'qualification/spectrum_0_6_82_28/spectrum_source_scope_0_6_82_28.json').read_text())
            row=next((r for r in spectrum['production_hashes'] if r['path']==rel), None)
            if row is not None and row['baseline_sha256'] != row['sha256']:
                expected=row['sha256']
        if active_version in ('0.6.82.28.1','0.6.82.29','0.6.82.29.1','0.6.82.29.2'):
            hotfix=json.loads((ROOT/'qualification/spectrum_0_6_82_28_1/spectrum_file_input_artifact_hotfix_scope_0_6_82_28_1.json').read_text())
            row=next((r for r in hotfix['production_hashes'] if r['path']==rel), None)
            if row is not None and row['baseline_sha256'] != row['sha256']:
                expected=row['sha256']
        if active_version in ('0.6.82.29','0.6.82.29.1','0.6.82.29.2'):
            output=json.loads((ROOT/'qualification/output_control_0_6_82_29/output_control_scope_0_6_82_29.json').read_text())
            row=next((r for r in output['production_hashes'] if r['path']==rel), None)
            if row is not None and row['baseline_sha256'] != row['sha256']:
                expected=row['sha256']
        if active_version in ('0.6.82.29.1','0.6.82.29.2'):
            verbose=json.loads((ROOT/'qualification/output_control_verbose_0_6_82_29_1/output_control_verbose_scope_0_6_82_29_1.json').read_text())
            row=next((r for r in verbose['production_hashes'] if r['path']==rel), None)
            if row is not None and row['baseline_sha256'] != row['sha256']:
                expected=row['sha256']
        if active_version == '0.6.82.29.2':
            verbose2=json.loads((ROOT/'qualification/output_control_verbose_0_6_82_29_2/output_control_verbose_scope_0_6_82_29_2.json').read_text())
            row=next((r for r in verbose2['production_hashes'] if r['path']==rel), None)
            if row is not None and row.get('changed'):
                expected=row['sha256']
        assert now==expected, rel


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
