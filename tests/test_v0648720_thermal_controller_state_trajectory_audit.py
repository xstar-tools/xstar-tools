from __future__ import annotations
import csv, json
from pathlib import Path
from xstar_tools.xstar.thermal_controller_state_trajectory_audit import audit


def _write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as h:
        w=csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def test_audit_identifies_controller_causes(tmp_path: Path):
    root=tmp_path/'pkg'; ref=root/'src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/trajectory.csv'
    prior=tmp_path/'prior'; full=prior/'full_controller'
    native=[]; reference=[]; seq=0
    # Minimal but contract-complete trajectory matching the decisive real rows.
    ntemps=[100,100,100,100,83.33333002196431,69.44443892549619,57.87036347168518]
    nh=[-0.0015,-0.0014,-0.0013,-0.0013253644813441487,-0.000296,-0.000108,-6.615654365648586e-05]
    rtemps=[100,100,100,100,69.44443892549619,48.225300976769695,33.489789683449544]
    rh=[-1.1,-1.2,-1.3,-1.2379933611517373,-1.19,-1.13,-1.021]
    for i in range(21):
        seq+=1; reference.append({'sequence':seq,'kind':'dsec','call_index':1,'evaluation_index':i+1,'temperature_t4':rtemps[i] if i<7 else 6.5,'electron_fraction':1.2003632957721315 if i>=3 else [1,1.2,1.44][i], 'hmctot':rh[i] if i<7 else -0.1,'elcter':0,'lnerr':0})
    for call,count,first_h in ((2,1,-2.298067780339032e-05),(3,18,0.05995477125866798),(4,17,0.04245961130063218)):
        for i in range(count):
            seq+=1; reference.append({'sequence':seq,'kind':'dsec','call_index':call,'evaluation_index':i+1,'temperature_t4':6.499146221156158,'electron_fraction':1.2003632957721315,'hmctot':first_h,'elcter':0,'lnerr':0})
    # append immutable row 60 anchor and row 61
    while len(reference)<59: reference.append(dict(reference[-1], sequence=len(reference)+1, kind='final'))
    reference.append({'sequence':60,'kind':'final','call_index':3,'evaluation_index':19,'temperature_t4':6.499146221156158,'electron_fraction':1.2003632957721315,'hmctot':-0.000169238448,'elcter':0,'lnerr':-2})
    reference.append({'sequence':61,'kind':'final','call_index':4,'evaluation_index':18,'temperature_t4':6.499146221159782,'electron_fraction':1.2003632957721315,'hmctot':-0.00030199,'elcter':0,'lnerr':-2})
    for i,(t,h) in enumerate(zip(ntemps,nh),1):
        native.append({'sequence':i,'kind':'dsec','call_index':1,'evaluation_index':i,'temperature_t4':t,'electron_fraction_input':1.2003771234732117 if i>=4 else [1,1.2,1.44][i-1], 'hmctot':h})
    for call in (2,3,4): native.append({'sequence':len(native)+1,'kind':'dsec','call_index':call,'evaluation_index':1,'temperature_t4':57.87036347168518,'electron_fraction_input':1.2003771234732117,'hmctot':-6.615654365648586e-05})
    _write(ref, reference); _write(full/'native_dsec_trajectory.csv',native)
    (full/'native_dsec_summary.json').write_text(json.dumps({'total_evaluations':14,'dsec_evaluations':10,'final_evaluations':4,'reference_state_identity':False,'max_abs_temperature_t4_delta_to_reference':51.37,'max_abs_hmctot_delta_to_reference':1.335}))
    (prior/'controller_smoke').mkdir(parents=True)
    (prior/'controller_smoke/controller_smoke_summary.json').write_text(json.dumps({'initial_temperature_t4':6.499146221156158,'initial_electron_fraction':1.2003632957721315,'runtime_state_workspace_evaluations':1}))
    (prior/'audit_summary.json').write_text(json.dumps({'two_state_type53_promotion':True,'two_state_exactness':{'60':{'record_comparison':{'all_records_ieee_exact':True}},'61':{'record_comparison':{'all_records_ieee_exact':True}}},'hmctot_attribution':{'type53_is_not_remaining_cooling_source':True}}))
    result=audit(root,prior,tmp_path/'out')
    assert result['result']=='ACCEPT'
    assert result['first_temperature_branch_divergence']['identified'] is True
    assert result['early_termination']['identified'] is True
    assert result['between_call_state_refresh']['gap_identified'] is True
