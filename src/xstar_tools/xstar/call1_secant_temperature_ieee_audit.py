"""v0.6.48.7.25 call-1 secant temperature IEEE restoration audit."""
from __future__ import annotations
import argparse, csv, json, shutil, math, struct
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.25"
SCHEMA = "xstar-tools-v0648725-call1-secant-temperature-ieee-v1"
LEAVES = ("cmp1","cmp2","htcomp","clcomp","clbrems","htfreef")
HHE = ("h_heating","h_cooling","h_heating2","h_cooling2","he_heating","he_cooling","he_heating2","he_cooling2")
MG = ("mg_heating","mg_cooling","mg_heating2","mg_cooling2")

def ordered_bits(value: float) -> int:
    bits=struct.unpack(">Q",struct.pack(">d",float(value)))[0]
    return (~bits & 0xffffffffffffffff) if (bits >> 63) else (bits | 0x8000000000000000)

def ulp_distance(a: float,b: float) -> int:
    if math.isnan(a) or math.isnan(b): return 2**63-1
    return abs(ordered_bits(a)-ordered_bits(b))

def rows(path: Path) -> list[dict[str,str]]:
    with path.open(newline="") as f: return list(csv.DictReader(f))

def dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True)+"\n")

def locate(root: Path, names: tuple[str,...]) -> Path:
    for name in names:
        p=root/name
        if p.is_file(): return p
    for name in names:
        hits=list(root.rglob(name))
        if hits: return hits[0]
    raise FileNotFoundError(f"none of {names} found below {root}")

def prepare(previous_audit: Path, output: Path) -> dict[str,Any]:
    output.mkdir(parents=True, exist_ok=True)
    budget=locate(previous_audit,("v0472_call1_thermal_budget.csv",))
    shutil.copy2(budget, output/"v0472_call1_thermal_budget.csv")
    ws=previous_audit/"call_start_workspace_bin"
    if not ws.is_dir():
        hits=list(previous_audit.rglob("call_start_workspace_bin")); ws=hits[0] if hits else ws
    if not ws.is_dir(): raise FileNotFoundError("call_start_workspace_bin not found")
    shutil.copytree(ws, output/"call_start_workspace_bin", dirs_exist_ok=True)
    previous_summary=None
    for name in ("preparation_summary.json","mg_primary_workspace_transport_summary.json","v048723_checker_report.json"):
        hits=list(previous_audit.rglob(name))
        if hits:
            try: previous_summary=json.loads(hits[0].read_text())
            except Exception: pass
            break
    prior_dsec=0; prior_calls=[]
    if previous_summary:
        if "prior_v048723_dsec_evaluations" in previous_summary:
            prior_dsec=int(previous_summary.get("prior_v048723_dsec_evaluations",0) or 0)
            prior_calls=[int(v) for v in previous_summary.get("prior_v048723_observed_calls",[]) or []]
        else:
            native=previous_summary.get("native_controller",previous_summary)
            prior_dsec=int(native.get("dsec_evaluations",0) or 0)
    transport=previous_audit/"native_full_controller"/"native_runtime_state_transport.csv"
    if transport.is_file():
        prior_calls=sorted({int(r["call_index"]) for r in rows(transport) if int(r.get("call_index",0))>0})
    coverage="ACCEPT" if prior_dsec==57 else ("PARTIAL" if prior_dsec>0 and prior_calls==[1,2,3,4] else "REJECT")
    out={"schema":SCHEMA,"release":RELEASE,"result":"ACCEPT","source_budget_rows":len(rows(budget)),"workspace_payload_prepared":True,
         "prior_v048723_four_call_runtime_coverage":coverage,"prior_v048723_dsec_evaluations":prior_dsec,"prior_v048723_observed_calls":prior_calls,
         "qualification_only":True,"production_promotion_ready":False}
    dump(output/"preparation_summary.json",out); return out

def audit_call1(prefix: Path, source_budget: Path, output: Path) -> dict[str,Any]:
    output.mkdir(parents=True, exist_ok=True)
    src=[r for r in rows(source_budget) if int(r["dsec_call_id"])==1]
    nat=[r for r in rows(prefix/"native_thermal_budget.csv") if r.get("kind")=="dsec" and int(r.get("call_index",0))==1]
    state_path=prefix/"native_call1_state.csv"
    state=[r for r in rows(state_path) if r.get("kind")=="dsec"] if state_path.is_file() else []
    n=min(len(src),len(nat),len(state))
    comparison=[]; leaf_exact=hhe_exact=mg_exact=state_exact=temperature_exact=0
    for i in range(n):
        s,nr,st=src[i],nat[i],state[i]
        leaf_ok=all(float(s[f])==float(nr[f]) for f in LEAVES)
        hhe_ok=all(float(s[f])==float(nr[f]) for f in HHE)
        mg_ok=all(float(s[f])==float(nr[f]) for f in MG)
        state_ok=(float(s["temperature_t4"])==float(st["temperature_t4"]) and
                  float(s["electron_fraction_xee"])==float(st["electron_fraction_input"]) and
                  float(s["elcter"])==float(st["charge_residual"]) and
                  float(s["hmctot"])==float(st["hmctot"]))
        leaf_exact+=leaf_ok; hhe_exact+=hhe_ok; mg_exact+=mg_ok; state_exact+=state_ok; temperature_exact += float(s["temperature_t4"])==float(st["temperature_t4"])
        comparison.append({"evaluation":i+1,"thermal_leaves_exact":leaf_ok,"h_he_primary_exact":hhe_ok,"mg_oracle_exact":mg_ok,"controller_state_exact":state_ok,
            **{f"source_{f}":float(s[f]) for f in LEAVES},**{f"native_{f}":float(nr[f]) for f in LEAVES},
            "source_temperature_t4":float(s["temperature_t4"]),"native_temperature_t4":float(st["temperature_t4"]),"temperature_ulp_distance":ulp_distance(float(s["temperature_t4"]),float(st["temperature_t4"])),
            "source_electron_fraction":float(s["electron_fraction_xee"]),"native_electron_fraction":float(st["electron_fraction_input"]),
            "source_charge_residual":float(s["elcter"]),"native_charge_residual":float(st["charge_residual"]),
            "source_hmctot":float(s["hmctot"]),"native_hmctot":float(st["hmctot"])})
    if comparison:
        with (output/"call1_thermal_leaf_and_state_comparison.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(comparison[0])); w.writeheader(); w.writerows(comparison)
    all21=n==21 and leaf_exact==21 and hhe_exact==21 and mg_exact==21 and state_exact==21
    computed_present=bool(nat and all(k in nat[0] for k in ("computed_cmp1","computed_cmp2","computed_htcomp","computed_clcomp")))
    out={"schema":SCHEMA,"release":RELEASE,"result":"ACCEPT" if all21 else "REJECT",
         "call1_rows":{"source":len(src),"native":len(nat),"state":len(state),"compared":n},
         "thermal_leaf_parity":{"fields":list(LEAVES),"rows_exact":leaf_exact,"status":"ACCEPT" if n==21 and leaf_exact==21 else "REJECT"},
         "hydrogen_helium_primary_construction":{"mode":"captured_call1_qualification_oracle","rows_exact":hhe_exact,"general_all_state_formula_qualified":False,"status":"ACCEPT" if n==21 and hhe_exact==21 else "REJECT"},
         "magnesium_primary_construction":{"mode":"abundance_weighting_plus_captured_call1_source_budget_oracle","rows_exact":mg_exact,"general_all_state_formula_qualified":False,"status":"ACCEPT" if n==21 and mg_exact==21 else "REJECT"},
         "native_comp2_cmpfnc_heatf":{"literal_native_path_present":computed_present,"effective_call1_leaves_oracle_scoped":True,"status":"ACCEPT" if computed_present else "REJECT"},
         "call1_controller_trajectory":{"temperature_rows_ieee_exact":temperature_exact,"temperature_electron_fraction_charge_hmctot_rows_exact":state_exact,"secant_temperature_ieee_restored":temperature_exact==21,"first_branch_restored":all21,"status":"ACCEPT" if all21 else "REJECT"},
         "gates":{"CALL1_THERMAL_LEAF_PARITY":"ACCEPT" if n==21 and leaf_exact==21 else "REJECT","CALL1_H_HE_PRIMARY_THERMAL":"ACCEPT" if n==21 and hhe_exact==21 else "REJECT","CALL1_CONTROLLER_TRAJECTORY":"ACCEPT" if all21 else "REJECT","CALL1_SECANT_TEMPERATURE_IEEE":"ACCEPT" if temperature_exact==21 else "REJECT","FIRST_BRANCH_RESTORATION":"ACCEPT" if all21 else "REJECT","CALLS_2_TO_4":"RUN_ALLOWED" if all21 else "BLOCKED_BY_CALL1"},
         "qualification_only":True,"production_promotion_ready":False}
    dump(output/"call1_parity_summary.json",out); return out

def audit_full(full: Path, call1_summary: Path, output: Path) -> dict[str,Any]:
    output.mkdir(parents=True, exist_ok=True)
    c1=json.loads(call1_summary.read_text())
    summary_path=full/"native_dsec_summary.json"
    summary=json.loads(summary_path.read_text()) if summary_path.is_file() else {}
    executed=bool(summary)
    dsec=int(summary.get("dsec_evaluations",0) or 0); calls=int(summary.get("dsec_calls",0) or 0)
    coverage="ACCEPT" if executed and dsec==57 and calls==4 else ("PARTIAL" if executed and calls==4 and dsec>0 else "REJECT")
    parity=bool(summary.get("reference_state_identity",False))
    call1_ok=c1.get("result")=="ACCEPT"
    result={"schema":SCHEMA,"release":RELEASE,"result":"ACCEPT" if call1_ok else "REJECT","call1":c1,"native_controller":summary,
      "gates":{"CALL1_THERMAL_LEAF_PARITY":"ACCEPT" if call1_ok else "REJECT","CALL1_CONTROLLER_TRAJECTORY":"ACCEPT" if call1_ok else "REJECT","CALL1_SECANT_TEMPERATURE_IEEE":"ACCEPT" if call1_ok else "REJECT",
        "FOUR_CALL_WORKSPACE_RUNTIME_COVERAGE":coverage,"COMPLETE_CONTROLLER_EXECUTION":"ACCEPT" if executed else "NOT_RUN_CALL1_GATE",
        "COMPLETE_CONTROLLER_PARITY":"ACCEPT" if parity else ("REJECT" if executed else "NOT_RUN_CALL1_GATE"),
        "GLOBAL_BILEVG_RNISG_CONSUMER_CORRECTION":"DEFERRED_UNTIL_CALL1_EXACT" if not call1_ok else "DEFERRED_POST_CALL1",
        "THERMAL_PARITY":"BLOCKED","PRODUCT_PARITY":"BLOCKED","PRODUCTION_PROMOTION":"BLOCKED"},
      "next_required_work":"diagnose first post-call1 divergence and only then activate global_bilevg/global_rnisg consumers" if call1_ok else "complete exact call1 leaf and controller-state parity",
      "qualification_only":True,"production_promotion_ready":False}
    dump(output/"call1_secant_temperature_ieee_summary.json",result); return result

def main(argv=None):
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("prepare"); p.add_argument("previous_audit",type=Path); p.add_argument("output",type=Path)
    p=sub.add_parser("audit-call1"); p.add_argument("--prefix",type=Path,required=True); p.add_argument("--source-budget",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    p=sub.add_parser("audit-full"); p.add_argument("--full",type=Path,required=True); p.add_argument("--call1-summary",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    try:
        if a.cmd=="prepare": result=prepare(a.previous_audit.resolve(),a.output.resolve())
        elif a.cmd=="audit-call1": result=audit_call1(a.prefix.resolve(),a.source_budget.resolve(),a.output.resolve())
        else: result=audit_full(a.full.resolve(),a.call1_summary.resolve(),a.output.resolve())
    except Exception as exc:
        result={"schema":SCHEMA,"release":RELEASE,"result":"REJECT","errors":[str(exc)],"qualification_only":True,"production_promotion_ready":False}
    print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["result"]=="ACCEPT" else 2
if __name__=="__main__": raise SystemExit(main())
