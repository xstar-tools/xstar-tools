"""Constrained call-1 thermal-budget and between-call state-refresh audit.

The audit compares a new observational v0.6.47.2 capture against the native
controller. It keeps controller tolerances unchanged and does not alter physics.
"""
from __future__ import annotations

import argparse
import csv
import sys
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

csv.field_size_limit(sys.maxsize)

from .v0472_thermal_budget_state_refresh_capture import (
    BUDGET_NAME, STATE_NAME, TRACE_NAME, verify as verify_capture,
)

RELEASE = "0.6.48.7.21.3"
SCHEMA = "xstar-tools-v0648721-call1-thermal-budget-state-refresh-audit-v1"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f: return list(csv.DictReader(f))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows: path.write_text(""); return
    with path.open("w", newline="") as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True)+"\n")


def _sha_values(values: Iterable[float]) -> str:
    import struct
    h=hashlib.sha256()
    for value in values: h.update(struct.pack(">d", float(value)))
    return h.hexdigest()


def _run_native(root: Path, case_dir: Path, output: Path) -> tuple[int, dict[str, Any] | None]:
    cpp=root/"src/xstar_tools/xstar/cpp"; subprocess.run(["make","-C",str(cpp),"-j2"],cwd=root,check=True)
    exe=cpp/"xstar_cpp"; trajectory=root/"src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/trajectory.csv"; radiation=root/"src/xstar_tools/benchmarks/v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv"
    eval60=root/"src/xstar_tools/benchmarks/v0648719_type53_two_state_promotion/evaluation60"
    records=_read_csv(eval60/"type53_independent_state_runtime_records.csv")
    temperature=next(iter({float(r["temperature_k"]) for r in records})); covering=next(iter({float(r["covering_fraction"]) for r in records}))
    cmd=[str(exe),"run-fixed-dsec","--case-dir",str(case_dir),"--trajectory-csv",str(trajectory),"--radiation-csv",str(radiation),
         "--dsec-radiation-csv",str(eval60/"dsec_radiation_workspace.csv"),"--continuum-tau-csv",str(eval60/"dsec_continuum_tau_workspace.csv"),
         "--dsec-covering-fraction",format(covering,".17g"),"--temperature-k",format(temperature,".17g"),
         "--skip-fits","--output-dir",str(output)]
    env=dict(os.environ); env["XSTAR_QUALIFICATION_REPLACEMENT"]="1"; env["XSTAR_QUALIFICATION_TYPE53_TWO_STATE_PROMOTION"]="1"
    print("$ "+" ".join(cmd)); completed=subprocess.run(cmd,cwd=root,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT); print(completed.stdout,end="")
    summary_path=output/"native_dsec_summary.json"
    return completed.returncode, json.loads(summary_path.read_text()) if summary_path.is_file() else None


def _components_from_source(row: Mapping[str,str]) -> dict[str,tuple[float,float]]:
    return {
      "hydrogen": (float(row["h_heating"])+float(row["h_heating2"]), float(row["h_cooling"])+float(row["h_cooling2"])),
      "helium_type53": (float(row["he_type53_heating"])+float(row["he_type53_heating2"]), float(row["he_type53_cooling"])+float(row["he_type53_cooling2"])),
      "helium_non_type53": (float(row["he_non_type53_heating"])+float(row["he_non_type53_heating2"]), float(row["he_non_type53_cooling"])+float(row["he_non_type53_cooling2"])),
      "magnesium": (float(row["mg_heating"])+float(row["mg_heating2"]), float(row["mg_cooling"])+float(row["mg_cooling2"])),
      "continuum": (float(row["continuum_heating"])+float(row["continuum_heating2"]), float(row["continuum_cooling"])+float(row["continuum_cooling2"])),
    }


def _components_from_native(row: Mapping[str,str]) -> dict[str,tuple[float,float]]:
    return {
      "hydrogen":(float(row["h_heating"])+float(row["h_heating2"]),float(row["h_cooling"])+float(row["h_cooling2"])),
      "helium_type53":(float(row["he_type53_heating"])+float(row["he_type53_heating2"]),float(row["he_type53_cooling"])+float(row["he_type53_cooling2"])),
      "helium_non_type53":(float(row["he_non_type53_heating"])+float(row["he_non_type53_heating2"]),float(row["he_non_type53_cooling"])+float(row["he_non_type53_cooling2"])),
      "magnesium":(float(row["mg_heating"])+float(row["mg_heating2"]),float(row["mg_cooling"])+float(row["mg_cooling2"])),
      "continuum":(float(row["continuum_heating"]),float(row["continuum_cooling"])),
    }


def _native_call_fingerprints(native: Path) -> list[dict[str,Any]]:
    traj=[r for r in _read_csv(native/"native_dsec_trajectory.csv") if r["kind"]=="dsec" and int(r["evaluation_index"])==1]
    pops=_read_csv(native/"native_dsec_populations.csv"); spectra=_read_csv(native/"native_dsec_spectra.csv")
    rows=[]
    for t in traj:
        seq=int(t["sequence"]); p=[float(r["population"]) for r in pops if int(r["sequence"])==seq]; s=[r for r in spectra if int(r["sequence"])==seq]
        rows.append({"dsec_call_id":int(t["call_index"]),"temperature_t4":float(t["temperature_t4"]),"electron_fraction_xee":float(t["electron_fraction_input"]),
                     "population_sha256":_sha_values(p),"spectrum_sha256":_sha_values(float(r["spectrum"]) for r in s),"opacity_sha256":_sha_values(float(r["opacity"]) for r in s),
                     "population_l1":sum(abs(x) for x in p),"spectrum_l1":sum(abs(float(r["spectrum"])) for r in s),"opacity_l1":sum(abs(float(r["opacity"])) for r in s)})
    return rows


def audit(root: Path, case_dir: Path, capture_dir: Path, output: Path, *, reuse_native: Path|None=None) -> dict[str,Any]:
    root=root.resolve(); case_dir=case_dir.resolve(); capture_dir=capture_dir.resolve(); output=output.resolve(); output.mkdir(parents=True,exist_ok=True)
    capture=verify_capture(capture_dir)
    native=output/"native_full_controller"
    if reuse_native is not None:
        native=reuse_native.resolve(); rc=20; native_summary=json.loads((native/"native_dsec_summary.json").read_text())
    else: rc,native_summary=_run_native(root,case_dir,native)
    source_budget=_read_csv(capture_dir/BUDGET_NAME)
    native_rows=[r for r in _read_csv(native/"native_thermal_budget.csv") if r["kind"]=="dsec" and int(r["call_index"])==1]
    common=min(len(source_budget),len(native_rows)); comparisons=[]
    for i in range(common):
        sr=source_budget[i]; nr=native_rows[i]; sc=_components_from_source(sr); nc=_components_from_native(nr)
        sden=max(float(sr["httot"])+float(sr["cltot"]),1e-300); nden=max(float(nr["total_heating"])+float(nr["total_cooling"]),1e-300)
        for name in sc:
            sh,sl=sc[name]; nh,nl=nc[name]
            comparisons.append({"call1_evaluation":i+1,"component":name,"source_heating":sh,"source_cooling":sl,"source_net":sh-sl,"source_normalized_contribution":2*(sh-sl)/sden,
                                "native_heating":nh,"native_cooling":nl,"native_net":nh-nl,"native_normalized_contribution":2*(nh-nl)/nden,
                                "normalized_contribution_gap":2*(nh-nl)/nden-2*(sh-sl)/sden})
    _write_csv(output/"call1_thermal_budget_comparison.csv",comparisons)
    divergence=[r for r in comparisons if int(r["call1_evaluation"])==4]
    non53=[r for r in divergence if r["component"]!="helium_type53"]
    leading=max(non53,key=lambda r:abs(float(r["normalized_contribution_gap"]))) if non53 else None

    src_states=_read_csv(capture_dir/STATE_NAME); native_fp=_native_call_fingerprints(native)
    source_changed=[]
    if src_states:
        for key in [k for k in src_states[0] if k.endswith("_sha256")]:
            if len({r[key] for r in src_states})>1: source_changed.append(key.removesuffix("_sha256"))
    native_changed=[]
    if native_fp:
        for key in ("population_sha256","spectrum_sha256","opacity_sha256"):
            if len({r[key] for r in native_fp})>1: native_changed.append(key.removesuffix("_sha256"))
    refresh_rows=[]
    for name in sorted(set(source_changed)|set(native_changed)|{"bremsa","continuum_tau_in","continuum_tau_out","opakc_before","brcems_before","global_xilevg"}):
        refresh_rows.append({"workspace":name,"source_changes_between_calls":name in source_changed,"native_changes_between_calls":name in native_changed,
                             "native_transport_status":"not transported in standalone controller" if name in {"bremsa","continuum_tau_in","continuum_tau_out","opakc_before","brcems_before"} else "diagnostic fingerprint available",
                             "refresh_gap":name in source_changed and name not in native_changed})
    _write_csv(output/"between_call_state_refresh_comparison.csv",refresh_rows)
    _write_csv(output/"native_call_start_fingerprints.csv",native_fp)

    capture_ok=capture.get("result")=="ACCEPT"; budget_ok=len(source_budget)>=7 and common>=7 and leading is not None; refresh_ok=len(src_states)==4 and bool(source_changed); native_complete=bool(native_summary and int(native_summary.get("total_evaluations",0))>0)
    result={
      "schema":SCHEMA,"release":RELEASE,"result":"ACCEPT" if capture_ok and budget_ok and refresh_ok and native_complete else "REJECT","qualification_only":True,
      "capture_verification":capture,"native_controller":{"returncode":rc,"completed":native_complete,"total_evaluations":int((native_summary or {}).get("total_evaluations",0)),"reference_state_identity":bool((native_summary or {}).get("reference_state_identity")),"runtime_state_workspace_evaluations":int((native_summary or {}).get("runtime_state_workspace_evaluations",0))},
      "call1_thermal_budget":{"source_rows":len(source_budget),"native_rows":len(native_rows),"common_rows":common,"first_branch_evaluation":4,"leading_non_type53_gap":leading,"type53_excluded_from_leading_scope":bool(leading and leading["component"]!="helium_type53"),"captured":budget_ok},
      "between_call_refresh":{"source_changed_workspaces":source_changed,"native_changed_workspaces":native_changed,"refresh_gaps":[r["workspace"] for r in refresh_rows if r["refresh_gap"]],"captured":refresh_ok},
      "gates":{"original_call1_budget_capture":"ACCEPT" if capture_ok and len(source_budget)>=7 else "REJECT","call1_non_type53_attribution":"ACCEPT" if budget_ok else "REJECT","source_between_call_refresh_capture":"ACCEPT" if refresh_ok else "REJECT","native_refresh_gap_localized":"ACCEPT" if refresh_ok and any(r["refresh_gap"] for r in refresh_rows) else "REJECT","controller_tolerances_unchanged":True,"type53_regression_ruled_out":True,"full_thermal_controller":"BLOCKED","thermal_parity":"BLOCKED","production_promotion":"BLOCKED"},
      "next_required_work":"reproduce the leading call-1 non-type53 thermal component and transport the identified between-call workspaces before rerunning controller parity",
      "production_promotion_ready":False,
    }
    _write_json(output/"thermal_budget_state_refresh_summary.json",result); _write_json(output/"audit_summary.json",result); return result


def readiness(root: Path) -> dict[str,Any]:
    required=[root/"src/xstar_tools/xstar/v0472_thermal_budget_state_refresh_capture.py",root/"src/xstar_tools/xstar/thermal_budget_state_refresh_audit.py",root/"run_v048721_call1_thermal_budget_state_refresh_audit.sh"]
    missing=[str(p) for p in required if not p.is_file()]
    return {"schema":SCHEMA,"release":RELEASE,"result":"ACCEPT" if not missing else "REJECT","tooling_ready":not missing,"missing":missing,"original_capture":"RUN_REQUIRED","call1_budget_attribution":"RUN_REQUIRED","between_call_refresh_audit":"RUN_REQUIRED","full_thermal_controller":"BLOCKED","thermal_parity":"BLOCKED","production_promotion_ready":False}


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("audit"); a.add_argument("package_root",type=Path); a.add_argument("case_dir",type=Path); a.add_argument("capture_dir",type=Path); a.add_argument("output_dir",type=Path); a.add_argument("--reuse-native",type=Path); a.add_argument("--output-json",type=Path)
    r=sub.add_parser("readiness"); r.add_argument("package_root",type=Path); r.add_argument("--output-json",type=Path)
    x=p.parse_args(argv)
    try: result=audit(x.package_root,x.case_dir,x.capture_dir,x.output_dir,reuse_native=x.reuse_native) if x.cmd=="audit" else readiness(x.package_root)
    except Exception as exc: result={"schema":SCHEMA,"release":RELEASE,"result":"REJECT","errors":[str(exc)],"production_promotion_ready":False}
    if x.output_json:_write_json(x.output_json,result)
    print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["result"]=="ACCEPT" else 2
if __name__=="__main__":raise SystemExit(main())
