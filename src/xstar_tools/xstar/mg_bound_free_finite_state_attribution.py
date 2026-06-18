#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
from collections import Counter
RELEASE='0.6.48.7.46.9.4.2'
EXPECTED={49:49349,53:53436}

def f(row,key):
    try:return float(row.get(key,'nan'))
    except:return float('nan')
def i(row,key):
    try:return int(float(row.get(key,'0')))
    except:return 0

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--audit-output',type=Path,required=True); ap.add_argument('--output-json',type=Path,required=True); a=ap.parse_args()
    root=a.audit_output; diag=root/'native_all61'/'qualification_diagnostics'; errors=[]
    files=sorted(diag.glob('evaluation_*_records.csv'))
    if len(files)!=61: errors.append(f'diagnostic_files={len(files)} expected=61')
    outcsv=root/'all61_mg_type49_type53_finite_state.csv'
    fields=['sequence','record','data_type','ion_index','ion_stage','lower_row','upper_row','threshold_ev','bound_energy_ev','continuum_energy_ev','destination_energy_ev','bound_g','continuum_g','destination_g','rnist','exponent_energy_ev','exponent_dimensionless','electron_density_cm3','hydrogen_density_cm3','matrix_density_scale','legacy_max_abs','shadow_max_abs','committed_max_abs','legacy_nonfinite','legacy_implausible','shadow_valid','replacement_applied','committed_nonfinite','committed_implausible','phextrap_applied','runtime_state_abi_used','continuum_index_one_based','dsec_radiation_bin_count','continuum_tau_count']
    counts=Counter(); type_counts=Counter(); invalid=Counter(); max_legacy=0.0; max_committed=0.0
    with outcsv.open('w',newline='') as out:
      w=csv.DictWriter(out,fieldnames=fields); w.writeheader()
      for path in files:
        seq=int(path.name.split('_')[1])
        with path.open(newline='') as h:
          for row in csv.DictReader(h):
            if row.get('element_z')!='12' or row.get('data_type') not in {'49','53'}: continue
            dt=int(row['data_type']); type_counts[dt]+=1
            p='type49_' if dt==49 else 'mg_type53_'
            common='type49_' if dt==49 else 'type53_shadow_'
            d={
              'sequence':seq,'record':row['record'],'data_type':dt,'ion_index':row['ion_index'],'ion_stage':row['ion_stage'],'lower_row':row['lower_row'],'upper_row':row['upper_row'],
              'threshold_ev':f(row, common+'threshold_ev'), 'bound_energy_ev':f(row,common+'bound_energy_ev'), 'continuum_energy_ev':f(row,common+'continuum_energy_ev'), 'destination_energy_ev':f(row,common+'destination_energy_ev'),
              'bound_g':f(row,common+'bound_g'), 'continuum_g':f(row,common+'continuum_g'), 'destination_g':f(row,common+'destination_g'), 'rnist':f(row,common+'rnist'),
              'exponent_energy_ev':f(row,p+'exponent_energy_ev'), 'exponent_dimensionless':f(row,p+'exponent_dimensionless'), 'electron_density_cm3':f(row,p+'electron_density_cm3'), 'hydrogen_density_cm3':f(row,p+'hydrogen_density_cm3'), 'matrix_density_scale':f(row,p+'matrix_density_scale'),
              'legacy_max_abs':f(row,p+'legacy_max_abs'), 'shadow_max_abs':f(row,p+'shadow_max_abs'), 'committed_max_abs':f(row,p+'committed_max_abs'),
              'legacy_nonfinite':i(row,p+'legacy_nonfinite'),'legacy_implausible':i(row,p+'legacy_implausible'),'shadow_valid':i(row,'type49_shadow_valid' if dt==49 else 'type53_shadow_valid'),'replacement_applied':i(row,p+'replacement_applied'),'committed_nonfinite':i(row,p+'committed_nonfinite'),'committed_implausible':i(row,p+'committed_implausible'),
              'phextrap_applied':i(row,'type49_phextrap_applied') if dt==49 else 0,'runtime_state_abi_used':i(row,'type49_runtime_state_abi_used' if dt==49 else 'type53_runtime_state_abi_used'),'continuum_index_one_based':i(row,'type49_continuum_index_one_based' if dt==49 else 'type53_continuum_index_one_based'),'dsec_radiation_bin_count':i(row,'type49_dsec_radiation_bin_count' if dt==49 else 'type53_dsec_radiation_bin_count'),'continuum_tau_count':i(row,'type49_continuum_tau_count' if dt==49 else 'type53_continuum_tau_count')}
            w.writerow(d); counts['records']+=1
            for k in ('legacy_nonfinite','legacy_implausible','shadow_valid','replacement_applied','committed_nonfinite','committed_implausible','runtime_state_abi_used'): counts[k]+=int(d[k])
            if dt==49: counts['type49_phextrap_applied']+=d['phextrap_applied']
            max_legacy=max(max_legacy,d['legacy_max_abs'] if math.isfinite(d['legacy_max_abs']) else 0.0); max_committed=max(max_committed,d['committed_max_abs'] if math.isfinite(d['committed_max_abs']) else 0.0)
            for key in ('threshold_ev','bound_energy_ev','continuum_energy_ev','destination_energy_ev','bound_g','continuum_g','destination_g','rnist','exponent_energy_ev','exponent_dimensionless','electron_density_cm3','hydrogen_density_cm3','matrix_density_scale','shadow_max_abs','committed_max_abs'):
                v=d[key]
                if not math.isfinite(v): invalid[key]+=1
            if d['threshold_ev']<0 or d['exponent_energy_ev']<0 or d['exponent_dimensionless']<0: invalid['negative_energy_or_exponent']+=1
            if d['bound_g']<=0 or d['continuum_g']<=0 or d['destination_g']<=0: invalid['nonpositive_statistical_weight']+=1
    for dt,n in EXPECTED.items():
        if type_counts[dt]!=n: errors.append(f'Mg Type-{dt} records={type_counts[dt]} expected={n}')
    if counts['replacement_applied']!=sum(EXPECTED.values()): errors.append(f'replacements={counts["replacement_applied"]} expected={sum(EXPECTED.values())}')
    if counts['shadow_valid']!=sum(EXPECTED.values()): errors.append(f'shadows={counts["shadow_valid"]} expected={sum(EXPECTED.values())}')
    if counts['committed_nonfinite']!=0: errors.append(f'committed_nonfinite={counts["committed_nonfinite"]}')
    if counts['committed_implausible']!=0: errors.append(f'committed_implausible={counts["committed_implausible"]}')
    if counts['runtime_state_abi_used']!=sum(EXPECTED.values()): errors.append(f'runtime_state_abi_used={counts["runtime_state_abi_used"]}')
    if counts['type49_phextrap_applied']!=EXPECTED[49]: errors.append(f'type49_phextrap_applied={counts["type49_phextrap_applied"]}')
    if invalid: errors.append('invalid finite-state fields: '+json.dumps(dict(invalid),sort_keys=True))
    report={'schema':'xstar-tools-v064874693-mg-bound-free-finite-state-v1','release':RELEASE,'result':'ACCEPT' if not errors else 'REJECT','errors':errors,'record_counts':{str(k):v for k,v in sorted(type_counts.items())},'metrics':dict(counts),'invalid_fields':dict(invalid),'max_legacy_abs':max_legacy,'max_committed_abs':max_committed,'output_csv':outcsv.name,'gates':{'MG_TYPE49_FINITE_STATE_ATTRIBUTED':'ACCEPT' if not errors else 'REJECT','MG_TYPE53_FINITE_STATE_ATTRIBUTED':'ACCEPT' if not errors else 'REJECT','MG_BOUND_FREE_COMMITTED_NONFINITE_ZERO':'ACCEPT' if counts['committed_nonfinite']==0 else 'REJECT','MG_BOUND_FREE_COMMITTED_IMPLAUSIBLE_ZERO':'ACCEPT' if counts['committed_implausible']==0 else 'REJECT'}}
    a.output_json.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n'); print(json.dumps(report,indent=2,sort_keys=True)); return 0 if not errors else 2
if __name__=='__main__': raise SystemExit(main())
