"""Audit the v46.17 source-faithful continuum workspace and Thermal correction."""
from __future__ import annotations
import argparse,csv,json,math,struct
from pathlib import Path
from typing import Any
import numpy as np
from .all61_native_replay_aggregate import CONTINUUM_WORKSPACE_LEDGER_NAME, THERMAL_LEDGER_NAME
from .all61_thermal_state_consumption_audit import COMPONENT_DIFF_NAME

RELEASE="0.6.48.7.46.20.2"
SCHEMA="xstar-tools-v064874617-continuum-workspace-correction-v1"
COMPONENTS=("cmp1","cmp2","htcomp","clcomp","htfreef","clbrems","continuum_heating","continuum_cooling","continuum_heating2","continuum_cooling2")

def read_csv(p:Path)->list[dict[str,str]]:
    with p.open(newline="") as h:return list(csv.DictReader(h))
def write_csv(p:Path,fields:list[str],rows:list[dict[str,Any]])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open("w",newline="") as h:w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
def bits(x:float)->bytes:return struct.pack(">d",float(x))
def exact(a:float,b:float)->bool:return math.isfinite(a) and math.isfinite(b) and bits(a)==bits(b)
def ordered_int(x:float)->int:
    i=struct.unpack(">q",bits(x))[0]
    return 0x8000000000000000-i if i<0 else i

def ulp(a:float,b:float)->int:
    if not math.isfinite(a) or not math.isfinite(b):return 2**63-1
    return abs(ordered_int(a)-ordered_int(b))
def source_scale(a:float,b:float)->bool:
    if not math.isfinite(a) or not math.isfinite(b):return False
    return abs(a-b)<=max(1e-30,1e-9*max(abs(a),abs(b)))

def source_epim()->np.ndarray:
    n=999;n2=max(2,n//50);n3=n-n2
    e=np.zeros(n,dtype=np.float64)
    eb1=np.float64(np.float32(0.1));eb2=np.float64(np.float32(4e5))
    dele=(eb2/eb1)**np.float64(np.float32(1.0)/np.float32(n3-1))
    e[0]=eb1
    for i in range(1,n3):e[i]=e[i-1]*dele
    eb1=eb2;eb2=np.float64(np.float32(1e6))
    dele=(eb2/eb1)**np.float64(np.float32(1.0)/np.float32(n2-1))
    for i in range(n3,n):e[i]=e[i-1]*dele
    return e

def huntf(grid:np.ndarray,x:float)->int:
    n=len(grid);tiny=float(np.float32(1e-34));xtmp=max(x,float(grid[1]));j=1
    if x<tiny or grid[0]<=tiny or grid[-1]<=tiny:return j
    j=int((n-1)*math.log(xtmp/grid[0])/math.log(grid[-1]/grid[0]))+1
    if j<n:
        t=abs(math.log(x/(tiny+grid[j-1])));t2=abs(math.log(x/(tiny+grid[j])))
        if t2<t:j+=1
    return max(1,min(n,j))

def reconstruct(full_epi:np.ndarray,full_bremsa:np.ndarray)->tuple[np.ndarray,np.ndarray,np.ndarray]:
    epim=source_epim();n3=len(full_epi)-max(2,len(full_epi)//50);domain=full_epi[:n3]
    idx=np.asarray([huntf(domain,float(x)) for x in epim],dtype=np.int64)
    return epim,idx,full_bremsa[idx-1]

def compare(source_capture:Path,native_run:Path,component_comparison:Path,output:Path)->dict[str,Any]:
    inputs=read_csv(source_capture/"v0472_all61_input_states.csv")
    native=read_csv(native_run/CONTINUUM_WORKSPACE_LEDGER_NAME)
    thermal=read_csv(native_run/THERMAL_LEDGER_NAME)
    comps=read_csv(component_comparison)
    by_seq:dict[int,list[dict[str,str]]]={}
    for r in native:by_seq.setdefault(int(r["sequence"]),[]).append(r)
    workspace_rows=[];epim_exact=map_exact=brems_exact=0;total=0;errors=[]
    canonical=source_epim();canonical_exact=0
    for i,x in enumerate(canonical,1):
        if by_seq.get(1) and exact(float(by_seq[1][i-1]["epim_ev"]),float(x)):canonical_exact+=1
    for src in inputs:
        seq=int(src["sequence"]);call=int(src["dsec_call_id"]);root=source_capture/"all61_input_workspaces"/f"evaluation_{seq:04d}"
        epi=np.fromfile(root/f"call_{call}_radiation_energy.bin",dtype=np.float64)
        bremsa=np.fromfile(root/f"call_{call}_bremsa.bin",dtype=np.float64)
        epim,idx,bremsam=reconstruct(epi,bremsa);rows=sorted(by_seq.get(seq,[]),key=lambda r:int(r["reduced_bin_one_based"]))
        if len(rows)!=999:errors.append(f"sequence_{seq:04d}:rows={len(rows)}");continue
        se=sm=sb=0
        for k,r in enumerate(rows):
            se+=exact(float(r["epim_ev"]),float(epim[k]));sm+=int(int(r["full_bin_one_based"])==int(idx[k]));sb+=exact(float(r["bremsam"]),float(bremsam[k]))
        epim_exact+=se;map_exact+=sm;brems_exact+=sb;total+=999
        workspace_rows.append({"sequence":seq,"rows":999,"epim_exact":se,"bremsmap_exact":sm,"bremsam_exact":sb,"first_index":int(idx[0]),"last_index":int(idx[-1])})
    comp_rows=[];summary={}
    for name in COMPONENTS:
        rows=[r for r in comps if r["component"]==name];ex=scale=0;max_abs=max_rel=0.0;max_ulp=0
        for r in rows:
            a=float(r["source_value"]);b=float(r["computed_native_value"]);d=abs(b-a);rel=d/max(abs(a),1e-300)
            ex+=exact(a,b);scale+=source_scale(a,b);max_abs=max(max_abs,d);max_rel=max(max_rel,rel);max_ulp=max(max_ulp,ulp(a,b))
        summary[name]={"rows":len(rows),"bit_exact":ex,"source_scale":scale,"max_abs_residual":max_abs,"max_rel_residual":max_rel,"max_ulp_distance":max_ulp}
        comp_rows.append({"component":name,**summary[name]})
    flags=sum(r.get("continuum_workspace_source_faithful")=="1" for r in thermal)
    counts=sum(r.get("continuum_epim_count")=="999" and r.get("continuum_bremsam_count")=="999" and r.get("continuum_bremsmap_count")=="999" for r in thermal)
    gates={
      "ALL_61_CONTINUUM_WORKSPACES_RECONSTRUCTED":"ACCEPT" if len(workspace_rows)==61 and total==60939 else "REJECT",
      "CONTINUUM_EPIM_CANONICAL_VALUES_EXACT_999":"ACCEPT" if canonical_exact==999 else "REJECT",
      "CONTINUUM_EPIM_VALUES_EXACT_60939":"ACCEPT" if epim_exact==60939 else "REJECT",
      "CONTINUUM_BREMSMAP_INDICES_EXACT_60939":"ACCEPT" if map_exact==60939 else "REJECT",
      "CONTINUUM_BREMSAM_VALUES_EXACT_60939":"ACCEPT" if brems_exact==60939 else "REJECT",
      "CONTINUUM_WORKSPACE_SOURCE_FAITHFUL_61":"ACCEPT" if flags==61 and counts==61 else "REJECT",
      "COMPTON_COMPONENTS_SOURCE_SCALE_61":"ACCEPT" if all(summary[x]["source_scale"]==61 for x in ("cmp1","cmp2","htcomp","clcomp")) else "REJECT",
      "FREE_FREE_COMPONENTS_SOURCE_SCALE_61":"ACCEPT" if all(summary[x]["source_scale"]==61 for x in ("htfreef","clbrems")) else "REJECT",
    }
    result="ACCEPT" if not errors and all(v=="ACCEPT" for v in gates.values()) else "REJECT"
    report={"schema":SCHEMA,"release":RELEASE,"result":result,"errors":errors,"workspace_rows":total,"epim_exact":epim_exact,"bremsmap_exact":map_exact,"bremsam_exact":brems_exact,"component_summary":summary,"gates":gates,"qualification_only":True,"production_promotion_ready":False}
    output.mkdir(parents=True,exist_ok=True)
    write_csv(output/"v04874617_continuum_workspace_summary.csv",list(workspace_rows[0]) if workspace_rows else ["sequence"],workspace_rows)
    write_csv(output/"v04874617_continuum_component_summary.csv",list(comp_rows[0]) if comp_rows else ["component"],comp_rows)
    (output/"v04874617_continuum_workspace_report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return report

def main(argv=None)->int:
    p=argparse.ArgumentParser();p.add_argument("--source-capture",type=Path,required=True);p.add_argument("--native-run",type=Path,required=True);p.add_argument("--component-comparison",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--output-json",type=Path);a=p.parse_args()
    try:r=compare(a.source_capture,a.native_run,a.component_comparison,a.output)
    except Exception as e:r={"schema":SCHEMA,"release":RELEASE,"result":"REJECT","errors":[str(e)],"qualification_only":True,"production_promotion_ready":False}
    if a.output_json:a.output_json.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n")
    print(json.dumps(r,indent=2,sort_keys=True));return 0 if r["result"]=="ACCEPT" else 2
if __name__=="__main__":raise SystemExit(main())
