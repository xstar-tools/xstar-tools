from pathlib import Path
import csv, json
from xstar_tools.xstar.call1_thermal_leaf_parity_audit import audit_call1, prepare
ROOT=Path(__file__).resolve().parents[1]

def test_literal_comp2_and_scoped_oracle_present():
    engine=(ROOT/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    header=(ROOT/'src/xstar_tools/xstar/cpp/xstar_fixed_state_engine.h').read_text()
    assert 'source_cmpfnc' in engine and 'source_comp2' in engine
    assert 'coheat_table_v048724.h' in engine
    assert 'XSTAR_FIXED_RUNTIME_STATE_CALL1_THERMAL_ORACLE' in header
    assert 'hmctot_override' in header

def _write_exact(tmp_path, mismatch=False):
    source=ROOT/'src/xstar_tools/benchmarks/v0648724_call1_thermal_leaf_reference/v0472_call1_thermal_budget.csv'
    src=list(csv.DictReader(source.open()))[:21]
    pref=tmp_path/'prefix'; pref.mkdir()
    nf=['sequence','kind','call_index','evaluation_index','temperature_k','electron_fraction_input','h_heating','h_cooling','h_heating2','h_cooling2','he_heating','he_cooling','he_heating2','he_cooling2','mg_heating','mg_cooling','mg_heating2','mg_cooling2','computed_cmp1','computed_cmp2','computed_htcomp','computed_clcomp','cmp1','cmp2','htcomp','clcomp','htfreef','clbrems','hmctot']
    with (pref/'native_thermal_budget.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=nf); w.writeheader()
        for i,r in enumerate(src,1):
            row={k:r.get(k,'0') for k in nf}; row.update(sequence=i,kind='dsec',call_index=1,evaluation_index=i,temperature_k=r['temperature_k'],electron_fraction_input=r['electron_fraction_xee'],computed_cmp1='1',computed_cmp2='1',computed_htcomp='1',computed_clcomp='1')
            if mismatch and i==1: row['cmp1']=str(float(r['cmp1'])+1)
            w.writerow(row)
    sf=['sequence','kind','call_index','evaluation_index','temperature_t4','electron_fraction_input','computed_electron_fraction','charge_residual','hmctot']
    with (pref/'native_call1_state.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=sf); w.writeheader()
        for i,r in enumerate(src,1): w.writerow(dict(sequence=i,kind='dsec',call_index=1,evaluation_index=i,temperature_t4=r['temperature_t4'],electron_fraction_input=r['electron_fraction_xee'],computed_electron_fraction=0,charge_residual=r['elcter'],hmctot=r['hmctot']))
    return pref,source

def test_exact_21_state_gate_accepts(tmp_path):
    pref,source=_write_exact(tmp_path)
    result=audit_call1(pref,source,tmp_path/'out')
    assert result['result']=='ACCEPT'
    assert result['thermal_leaf_parity']['rows_exact']==21
    assert result['call1_controller_trajectory']['first_branch_restored']

def test_leaf_mismatch_rejects(tmp_path):
    pref,source=_write_exact(tmp_path,True)
    assert audit_call1(pref,source,tmp_path/'out')['result']=='REJECT'

def test_prior_executed_coverage_is_partial_not_run_required(tmp_path):
    prev=tmp_path/'prev'; (prev/'call_start_workspace_bin').mkdir(parents=True)
    for call in range(1,5):
        for name in ('radiation_energy','bremsa','continuum_tau_in','continuum_tau_out','global_xilevg','global_bilevg','global_rnisg'):
            (prev/'call_start_workspace_bin'/f'call_{call}_{name}.bin').write_bytes(b'')
    src=ROOT/'src/xstar_tools/benchmarks/v0648724_call1_thermal_leaf_reference/v0472_call1_thermal_budget.csv'; (prev/'v0472_call1_thermal_budget.csv').write_bytes(src.read_bytes())
    (prev/'mg_primary_workspace_transport_summary.json').write_text(json.dumps({'native_controller':{'dsec_evaluations':30}}))
    nd=prev/'native_full_controller'; nd.mkdir();
    with (nd/'native_runtime_state_transport.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['call_index']); w.writeheader(); [w.writerow({'call_index':i}) for i in range(1,5)]
    r=prepare(prev,tmp_path/'out')
    assert r['prior_v048723_four_call_runtime_coverage']=='PARTIAL'
