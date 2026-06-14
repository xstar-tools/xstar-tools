from pathlib import Path
import csv, json, math
from xstar_tools.xstar.call1_secant_temperature_ieee_audit import audit_call1, prepare, ulp_distance

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src/xstar_tools/benchmarks/v0648724_call1_thermal_leaf_reference/v0472_call1_thermal_budget.csv'


def test_source_temperature_commit_and_secant_order_present():
    thermal=(ROOT/'src/xstar_tools/xstar/cpp/thermal_kernels.cpp').read_text()
    assert 'source_temperature_commit_t4' in thermal
    assert 'temperature_k = temperature_t4 * 1.0e4' in thermal
    assert 'committed_t4 = temperature_k / 1.0e4' in thermal
    assert 'state->temperature_t4 = source_temperature_commit_t4(result.temperature_t4);' in thermal
    assert 'source_temperature_secant' in thermal
    standalone=(ROOT/'src/xstar_tools/xstar/cpp/xstar_standalone.cpp').read_text()
    makefile=(ROOT/'src/xstar_tools/xstar/cpp/Makefile').read_text()
    assert 'secant-ieee-self-test' in standalone and 'secant-ieee-self-test' in makefile
    for token in ('low_product = tl * hmctth','high_product = th * hmcttl','numerator = low_product - high_product','denominator = hmctth - hmcttl'):
        assert token in thermal


def _fixture(tmp_path: Path, temperature_mismatch: bool=False):
    src=list(csv.DictReader(SOURCE.open()))[:21]
    pref=tmp_path/'prefix'; pref.mkdir()
    nf=['sequence','kind','call_index','evaluation_index','temperature_k','electron_fraction_input','h_heating','h_cooling','h_heating2','h_cooling2','he_heating','he_cooling','he_heating2','he_cooling2','mg_heating','mg_cooling','mg_heating2','mg_cooling2','computed_cmp1','computed_cmp2','computed_htcomp','computed_clcomp','cmp1','cmp2','htcomp','clcomp','htfreef','clbrems','hmctot']
    with (pref/'native_thermal_budget.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=nf); w.writeheader()
        for i,r in enumerate(src,1):
            row={k:r.get(k,'0') for k in nf}; row.update(sequence=i,kind='dsec',call_index=1,evaluation_index=i,temperature_k=r['temperature_k'],electron_fraction_input=r['electron_fraction_xee'],computed_cmp1='1',computed_cmp2='1',computed_htcomp='1',computed_clcomp='1')
            w.writerow(row)
    sf=['sequence','kind','call_index','evaluation_index','temperature_t4','electron_fraction_input','computed_electron_fraction','charge_residual','hmctot']
    with (pref/'native_call1_state.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=sf); w.writeheader()
        for i,r in enumerate(src,1):
            t=float(r['temperature_t4'])
            if temperature_mismatch and i==14: t=math.nextafter(t,0.0)
            w.writerow(dict(sequence=i,kind='dsec',call_index=1,evaluation_index=i,temperature_t4=repr(t),electron_fraction_input=r['electron_fraction_xee'],computed_electron_fraction=0,charge_residual=r['elcter'],hmctot=r['hmctot']))
    return pref


def test_exact_21_state_temperature_gate_accepts(tmp_path):
    result=audit_call1(_fixture(tmp_path),SOURCE,tmp_path/'out')
    assert result['result']=='ACCEPT'
    assert result['call1_controller_trajectory']['temperature_rows_ieee_exact']==21
    assert result['gates']['CALL1_SECANT_TEMPERATURE_IEEE']=='ACCEPT'


def test_one_ulp_temperature_mismatch_rejects(tmp_path):
    result=audit_call1(_fixture(tmp_path,True),SOURCE,tmp_path/'out')
    assert result['result']=='REJECT'
    assert result['call1_controller_trajectory']['temperature_rows_ieee_exact']==20
    rows=list(csv.DictReader((tmp_path/'out/call1_thermal_leaf_and_state_comparison.csv').open()))
    assert int(rows[13]['temperature_ulp_distance'])==1


def test_ulp_distance_adjacent():
    x=7.788652249358545
    assert ulp_distance(x,math.nextafter(x,0.0))==1


def test_prepare_preserves_prior_partial_coverage(tmp_path):
    prev=tmp_path/'prev'; (prev/'call_start_workspace_bin').mkdir(parents=True)
    for call in range(1,5):
        for name in ('radiation_energy','bremsa','continuum_tau_in','continuum_tau_out','global_xilevg','global_bilevg','global_rnisg'):
            (prev/'call_start_workspace_bin'/f'call_{call}_{name}.bin').write_bytes(b'')
    (prev/'v0472_call1_thermal_budget.csv').write_bytes(SOURCE.read_bytes())
    (prev/'preparation_summary.json').write_text(json.dumps({'prior_v048723_dsec_evaluations':30,'prior_v048723_observed_calls':[1,2,3,4]}))
    result=prepare(prev,tmp_path/'out')
    assert result['prior_v048723_four_call_runtime_coverage']=='PARTIAL'
