from __future__ import annotations
import csv, json, os, subprocess, sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]

def write_csv(path: Path, fields, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)

def test_v4620_source_probe_contract():
    from xstar_tools.xstar import v0472_all61_magnesium_type99_primary_cooling_capture as m
    assert m.RELEASE=='0.6.48.7.46.20.1.1'
    assert m.EXPECTED_UCALC_ROWS==661
    assert m.EXPECTED_DIAGONAL_ROWS==1322
    assert m.EXPECTED_ACTIVE_RECORD_UNION==11
    compile(m._PROBE,'<probe>','exec')

def test_v4620_cpp_contract():
    text=(ROOT/'src/xstar_tools/xstar/cpp/fixed_state_engine.cpp').read_text()
    assert text.count('XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PRIMARY_COOLING_REDUCTION')==1
    assert text.count('XSTAR_QUALIFICATION_MAGNESIUM_TYPE99_PRIMARY_COOLING_LEDGER_CSV')==1
    assert 'source_row.cj > 0.0' in text
    assert 'magnesium Type-99 source primary-cooling ledger was not fully consumed' in text
    assert 'magnesium_type99_primary_cooling_reduction_applied' in text

def test_v4620_baseline_accepts_actual_host_result(tmp_path):
    from xstar_tools.xstar.v461931_baseline_gate_v04874620 import validate
    path=Path('/mnt/data/v461931_review/result/v0487461931_magnesium_type50_thermal_channel_preservation_hotfix/v0487461931_checker_report.json')
    if not path.exists(): pytest.skip('actual v46.19.3.1 host result not mounted')
    report=validate(path); assert report['result']=='ACCEPT'; assert report['native_computed_values_exact']==1066

def test_v4620_readiness(tmp_path):
    out=tmp_path/'readiness.json'
    cp=subprocess.run([sys.executable,str(ROOT/'check_v04874620_magnesium_type99_primary_cooling_readiness.py'),'--package-dir',str(ROOT),'--output-json',str(out)],cwd=ROOT)
    assert cp.returncode==0
    assert json.loads(out.read_text())['result']=='ACCEPT'

def test_v4620_synthetic_source_verifier(monkeypatch,tmp_path):
    from xstar_tools.xstar import v0472_all61_magnesium_type99_primary_cooling_capture as m
    monkeypatch.setattr(m.base,'verify',lambda bundle:{'result':'ACCEPT','errors':[]})
    u=[]; ledger=[]; family=[]
    all_records=list(range(100,111))
    active_union=list(range(100,111))
    for seq in range(1,62):
        count=9 if seq<=4 else 10 if seq<=6 else 11
        for rec in all_records[:count]:
            u.append({'sequence':seq,'kind':'dsec','call_index':1,'evaluation_index':seq,'record':rec,'data_type':99,'rate_type':7,'idest1':1,'idest2':2,'ans1':1.0,'ans2':2.0,'ans3':-3.0,'ans4':-4.0,'ans5':-5.0,'ans6':-6.0,'bound_energy_ev':10.0,'physical_destination_energy_ev':20.0,'leveltemp_destination_energy_ev':20.0,'threshold_ev':10.0,'swrat':1.0,'calt99_rec_cm3_s':1.0,'phint_scale':1.0,'pirt_unscaled_s':1.0,'rrrt_unscaled_s':2.0,'piht_unscaled_erg_s':4.0,'rrcl_unscaled_erg_s':3.0,'piht2_unscaled_erg_s':6.0,'rrcl2_unscaled_erg_s':5.0,'nb1_one_based':1,'nphint_one_based':1,'ndelt':1,'npass':1,'ucalc_status':'ok'})
        sums=[0.,0.,0.,0.]
        idx=0
        for rec in active_union[:count]:
            for role,row,cj in [('forward_diag_loss',1,2.0),('reverse_diag_loss',2,-1.0)]:
                idx+=1; pop=0.5; heating=-pop*cj if cj<0 else 0.; cooling=pop*cj if cj>0 else 0.; cj2=0.25
                ledger.append({'sequence':seq,'kind':'dsec','call_index':1,'evaluation_index':seq,'source_order_index':idx,'record':rec,'data_type':99,'rate_type':7,'ion_index':1,'ion_stage':1,'role':role,'compact_row':row,'compact_column':row,'idest1':1,'idest2':2,'cj':cj,'cj2':cj2,'abundance':1.0,'compact_population':pop,'weighted_population':pop,'heating_contribution':heating,'cooling_contribution':cooling,'heating2_contribution':0.0,'cooling2_contribution':pop*cj2})
                sums[0]+=heating; sums[1]+=cooling; sums[3]+=pop*cj2
        family.append({'sequence':seq,'kind':'dsec','call_index':1,'evaluation_index':seq,'mg_type99_heating':sums[0],'mg_type99_cooling':sums[1],'mg_type99_heating2':sums[2],'mg_type99_cooling2':sums[3],'active_type99_records':count,'diagonal_rows':2*count})
    write_csv(tmp_path/m.UCALC_NAME,m.UCALC_FIELDS,u); write_csv(tmp_path/m.LEDGER_NAME,m.LEDGER_FIELDS,ledger); write_csv(tmp_path/m.FAMILY_NAME,m.FAMILY_FIELDS,family)
    r=m.verify(tmp_path); assert r['result']=='ACCEPT'; assert r['magnesium_type99_primary_thermal_rows']==1322

def test_v4620_synthetic_audit_accepts(tmp_path):
    from xstar_tools.xstar.magnesium_type99_primary_cooling_v04874620 import audit
    source=tmp_path/'source'; native=tmp_path/'native'; baseline=tmp_path/'baseline'; out=tmp_path/'out'
    source.mkdir(); (native/'qualification_diagnostics').mkdir(parents=True); (native/'evaluations').mkdir(); (baseline/'native_all61/evaluations').mkdir(parents=True)
    (source/'all61_magnesium_type99_primary_cooling_capture_report.json').write_text(json.dumps({'result':'ACCEPT','evaluations':61}))
    ufields=['sequence','record','ans1','ans2','ans3','ans4','ans5','ans6']; urows=[]
    lfields=['sequence','record','role','compact_row','cj','cj2','weighted_population','heating_contribution','cooling_contribution','heating2_contribution','cooling2_contribution']; lrows=[]; frows=[]
    recfields=['element_z','data_type','record','type99_shadow_valid']+[f'type99_shadow_ans{i}' for i in range(1,7)]
    diagfields=['element_z','data_type','record','role','compact_row','cj','cj2','weighted_population','heating_contribution','cooling_contribution','heating2_contribution','cooling2_contribution','magnesium_type99_primary_cooling_reduction_applied','native_cj','source_cj']
    all_records=list(range(100,111)); active=list(range(100,111))
    for seq in range(1,62):
        rr=[]
        count=9 if seq<=4 else 10 if seq<=6 else 11
        for rec in all_records[:count]:
            vals=[1.,2.,-3.,-4.,-5.,-6.]
            urows.append({'sequence':seq,'record':rec,**{f'ans{i+1}':v for i,v in enumerate(vals)}})
            rr.append({'element_z':12,'data_type':99,'record':rec,'type99_shadow_valid':1,**{f'type99_shadow_ans{i+1}':v for i,v in enumerate(vals)}})
        write_csv(native/'qualification_diagnostics'/f'evaluation_{seq:04d}_records.csv',recfields,rr)
        nd=[]; bd=[]; total=0.0
        for rec in active[:count]:
            for role,row in [('forward_diag_loss',1),('reverse_diag_loss',2)]:
                cj=2.0; cj2=0.25; pop=0.5; cool=pop*cj; cool2=pop*cj2; total+=cool
                lrows.append({'sequence':seq,'record':rec,'role':role,'compact_row':row,'cj':cj,'cj2':cj2,'weighted_population':pop,'heating_contribution':0.0,'cooling_contribution':cool,'heating2_contribution':0.0,'cooling2_contribution':cool2})
                nd.append({'element_z':12,'data_type':99,'record':rec,'role':role,'compact_row':row,'cj':cj,'cj2':cj2,'weighted_population':pop,'heating_contribution':0.0,'cooling_contribution':cool,'heating2_contribution':0.0,'cooling2_contribution':cool2,'magnesium_type99_primary_cooling_reduction_applied':1,'native_cj':3.0,'source_cj':cj})
                bd.append({'element_z':12,'data_type':99,'record':rec,'role':role,'compact_row':row,'cj':3.0,'cj2':cj2,'weighted_population':pop,'heating_contribution':0.0,'cooling_contribution':1.5,'heating2_contribution':0.0,'cooling2_contribution':cool2,'magnesium_type99_primary_cooling_reduction_applied':0,'native_cj':3.0,'source_cj':3.0})
        frows.append({'sequence':seq,'mg_type99_cooling':total})
        ep=native/'evaluations'/f'evaluation_{seq:04d}'; ep.mkdir(); write_csv(ep/'native_thermal_diagonal_ledger.csv',diagfields,nd)
        bp=baseline/'native_all61/evaluations'/f'evaluation_{seq:04d}'; bp.mkdir(); write_csv(bp/'native_thermal_diagonal_ledger.csv',diagfields,bd)
    write_csv(source/'v0472_all61_magnesium_type99_ucalc.csv',ufields,urows)
    write_csv(source/'v0472_all61_magnesium_type99_primary_thermal_ledger.csv',lfields,lrows)
    write_csv(source/'v0472_all61_magnesium_type99_family_budget.csv',['sequence','mg_type99_cooling'],frows)
    comp=[]; remaining=1005
    for seq in range(1,62):
        for name in ['h_cooling','mg_cooling']+[f'x{i}' for i in range(38)]:
            exact=1 if name in ('h_cooling','mg_cooling') else int(remaining>0)
            if name not in ('h_cooling','mg_cooling') and remaining>0: remaining-=1
            comp.append({'sequence':seq,'component':name,'computed_exact':exact,'computed_signed_delta':0.0 if exact else 1.0})
    cpath=tmp_path/'components.csv'; write_csv(cpath,['sequence','component','computed_exact','computed_signed_delta'],comp)
    t50=tmp_path/'t50.json'; t50.write_text(json.dumps({'result':'ACCEPT','gates':{'MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286':'ACCEPT','MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286':'ACCEPT'}}))
    report=audit(source,native,baseline,cpath,t50,out)
    assert report['result']=='ACCEPT'
    assert report['native_computed_values_exact']==1127
    assert report['source_thermal_rows']==1322
