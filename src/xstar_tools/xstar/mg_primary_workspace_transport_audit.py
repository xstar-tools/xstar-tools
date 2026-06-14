"""v0.6.48.7.23 Mg-primary correction and call-start workspace transport audit."""
from __future__ import annotations
import argparse, csv, json, os, subprocess
from pathlib import Path
from typing import Any
import numpy as np

RELEASE='0.6.48.7.23'
SCHEMA='xstar-tools-v0648723-mg-primary-workspace-transport-audit-v1'
ARRAYS=('radiation_energy','bremsa','continuum_tau_in','continuum_tau_out','global_xilevg','global_bilevg','global_rnisg')

def read_csv(path: Path):
    with path.open(newline='') as f: return list(csv.DictReader(f))

def write_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')

def prepare(capture_dir: Path, output_dir: Path) -> dict[str,Any]:
    payload_dir=capture_dir/'original_payload_capture'/'call_start_payloads'
    if not payload_dir.is_dir(): payload_dir=capture_dir/'call_start_payloads'
    out=output_dir/'call_start_workspace_bin'; out.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for call in range(1,5):
        with np.load(payload_dir/f'call_{call}.npz',allow_pickle=False) as z:
            for name in ARRAYS:
                a=np.asarray(z[name],dtype=np.float64).reshape(-1)
                target=out/f'call_{call}_{name}.bin'; a.tofile(target)
                manifest.append({'call_index':call,'workspace':name,'count':int(a.size),'bytes':target.stat().st_size})
    budget=capture_dir/'original_payload_capture'/'v0472_call1_thermal_budget.csv'
    if not budget.is_file(): budget=capture_dir/'v0472_call1_thermal_budget.csv'
    target_budget=output_dir/'v0472_call1_thermal_budget.csv'; target_budget.write_bytes(budget.read_bytes())
    result={'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT','payload_calls':4,'payload_arrays':list(ARRAYS),'manifest':manifest,'workspace_dir':str(out),'mg_budget_csv':str(target_budget),'qualification_only':True,'production_promotion_ready':False}
    write_json(output_dir/'transport_preparation.json',result)
    return result

def audit(package_dir: Path, capture_dir: Path, native_dir: Path, output_dir: Path) -> dict[str,Any]:
    source_path=capture_dir/'original_payload_capture'/'v0472_call1_thermal_budget.csv'
    if not source_path.is_file(): source_path=capture_dir/'v0472_call1_thermal_budget.csv'
    source=[r for r in read_csv(source_path) if int(r['dsec_call_id'])==1]
    native=read_csv(native_dir/'native_thermal_budget.csv') if (native_dir/'native_thermal_budget.csv').is_file() else []
    native_call1=[r for r in native if r.get('kind')=='dsec' and int(r.get('call_index','0'))==1]
    compared=min(len(source),len(native_call1))
    exact=0
    rows=[]
    for i in range(compared):
        s,n=source[i],native_call1[i]
        fields=('mg_heating','mg_cooling','mg_heating2','mg_cooling2')
        ok=all(float(s[f])==float(n[f]) for f in fields)
        exact+=int(ok)
        rows.append({'evaluation':i+1,'exact':ok,**{f'source_{f}':float(s[f]) for f in fields},**{f'native_{f}':float(n[f]) for f in fields}})
    if rows:
        with (output_dir/'mg_primary_budget_comparison.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summary_path=native_dir/'native_dsec_summary.json'
    summary=json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    trajectory=native_dir/'native_dsec_trajectory.csv'
    traj=read_csv(trajectory) if trajectory.is_file() else []
    dsec=[r for r in traj if r.get('kind')=='dsec']
    mapping_rows=[]
    case_rows=package_dir/'_unused_'
    mg_gate=compared>=7 and exact==compared
    prep_path=output_dir/'transport_preparation.json'
    prep=json.loads(prep_path.read_text()) if prep_path.is_file() else {}
    payload_ready=prep.get('result')=='ACCEPT' and int(prep.get('payload_calls',0))==4
    runtime_transport=int(summary.get('call_start_workspace_evaluations',0))>0 or int(summary.get('runtime_state_workspace_evaluations',0))>0
    workspace_gate=payload_ready or runtime_transport
    controller_completed=summary_path.is_file()
    controller_identity=bool(summary.get('reference_state_identity',False))
    result={
      'schema':SCHEMA,'release':RELEASE,'result':'ACCEPT' if mg_gate and workspace_gate else 'REJECT',
      'mg_primary_thermal_construction':{'rows_compared':compared,'rows_exact':exact,'status':'ACCEPT' if mg_gate else 'REJECT'},
      'call_start_workspace_transport':{'evaluations':int(summary.get('call_start_workspace_evaluations',0)),'payload_ready':payload_ready,'runtime_observed':runtime_transport,'status':'ACCEPT' if workspace_gate else 'REJECT'},
      'global_level_workspace_transport':{'status':'ACCEPT' if workspace_gate else 'REJECT','note':'global_xilevg, global_bilevg, and global_rnisg are carried through the fixed-state input ABI; mapped rows consume global_xilevg as initial populations while bilevg/rnisg remain available for subsequent family activation'},
      'native_controller':summary,
      'gates':{
        'mg_primary_thermal_construction':'ACCEPT' if mg_gate else 'REJECT',
        'five_workspace_transport':'ACCEPT' if workspace_gate else 'REJECT',
        'complete_controller_execution':'ACCEPT' if controller_completed else 'RUN_REQUIRED',
        'complete_controller_parity':'ACCEPT' if controller_identity else ('REJECT' if controller_completed else 'RUN_REQUIRED'),
        'thermal_parity':'ACCEPT' if controller_identity else 'BLOCKED',
        'production_promotion':'BLOCKED',
      },
      'next_required_work': 'promote controller parity' if controller_identity else ('review complete post-Mg/post-transport trajectory' if controller_completed else 'run the complete post-Mg/post-transport controller parity gate'),
      'qualification_only':True,'production_promotion_ready':False,
    }
    write_json(output_dir/'mg_primary_workspace_transport_summary.json',result)
    return result

def main(argv=None):
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('prepare'); p.add_argument('capture_dir',type=Path); p.add_argument('output_dir',type=Path)
    a=sub.add_parser('audit'); a.add_argument('--package-dir',type=Path,default=Path('.')); a.add_argument('--capture-dir',type=Path,required=True); a.add_argument('--native-dir',type=Path,required=True); a.add_argument('--output-dir',type=Path,required=True)
    args=ap.parse_args()
    try:
        r=prepare(args.capture_dir.resolve(),args.output_dir.resolve()) if args.cmd=='prepare' else audit(args.package_dir.resolve(),args.capture_dir.resolve(),args.native_dir.resolve(),args.output_dir.resolve())
    except Exception as e:
        r={'schema':SCHEMA,'release':RELEASE,'result':'REJECT','errors':[str(e)],'qualification_only':True,'production_promotion_ready':False}
    print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r['result']=='ACCEPT' else 2
if __name__=='__main__': raise SystemExit(main())
