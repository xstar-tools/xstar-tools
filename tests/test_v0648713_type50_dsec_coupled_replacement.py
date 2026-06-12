from pathlib import Path
import csv, hashlib, struct
from xstar_tools.xstar.type50_dsec_coupled_replacement_audit import RECORD_SHA, TERM_SHA, TRACE_SHA, BUNDLE

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def test_actual_dsec_oracle_inventory_and_hashes():
    root=Path(__file__).resolve().parents[1]
    d=root/BUNDLE
    assert sha(d/'type50_heii_rows46_54_dsec_runtime_records.csv')==RECORD_SHA
    assert sha(d/'type50_heii_rows46_54_dsec_runtime_matrix_terms.csv')==TERM_SHA
    assert sha(d/'dsec_evaluation_trace.csv')==TRACE_SHA
    assert len(list(csv.DictReader((d/'type50_heii_rows46_54_dsec_runtime_records.csv').open())))==79
    assert len(list(csv.DictReader((d/'type50_heii_rows46_54_dsec_runtime_matrix_terms.csv').open())))==316

def test_live_terms_follow_captured_density_contract():
    root=Path(__file__).resolve().parents[1]; d=root/BUNDLE
    rec={(r['source_position'],r['record']):r for r in csv.DictReader((d/'type50_heii_rows46_54_dsec_runtime_records.csv').open())}
    for t in csv.DictReader((d/'type50_heii_rows46_54_dsec_runtime_matrix_terms.csv').open()):
        r=rec[(t['source_position'],t['record'])]
        if t['role']=='reverse_diag_loss':
            expect=-float(r['ans3'])*float(r['hydrogen_density_cm3'])
            assert struct.pack('>d',expect)==struct.pack('>d',float(t['cj']))
