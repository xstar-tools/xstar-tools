"""Audit source-faithful Magnesium Type-99 primary-cooling attribution/reduction."""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path
from typing import Any

RELEASE="0.6.48.7.46.21"
SCHEMA="xstar-tools-v0648746201-magnesium-type99-primary-cooling-audit-v1"
UCALC_OUT="v04874620_magnesium_type99_ucalc_comparison.csv"
LEDGER_OUT="v04874620_magnesium_type99_primary_ledger_comparison.csv"
FAMILY_OUT="v04874620_magnesium_type99_family_summary.csv"


def _read_csv(path: Path) -> list[dict[str,str]]:
    with path.open(newline="") as h: return list(csv.DictReader(h))

def _exact(a: Any,b: Any)->bool:
    try: return float(a).hex()==float(b).hex()
    except Exception: return str(a)==str(b)

def _write_csv(path: Path, rows: list[dict[str,Any]]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0]) if rows else ["empty"]
    with path.open("w",newline="") as h:
        w=csv.DictWriter(h,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)

def _native_record_rows(native_run: Path) -> list[dict[str,str]]:
    rows=[]
    q=native_run/"qualification_diagnostics"
    for sequence in range(1,62):
        path=q/f"evaluation_{sequence:04d}_records.csv"
        if not path.is_file():
            path=native_run/"evaluations"/f"evaluation_{sequence:04d}"/"native_records.csv"
        if not path.is_file(): raise FileNotFoundError(path)
        for row in _read_csv(path):
            if int(row.get("element_z","0"))==12 and int(row.get("data_type","0"))==99:
                row=dict(row); row["sequence"]=str(sequence); rows.append(row)
    return rows

def _native_ledger(native_run: Path) -> list[dict[str,str]]:
    rows=[]
    for sequence in range(1,62):
        candidates=(
            native_run/"evaluations"/f"evaluation_{sequence:04d}"/"native_thermal_diagonal_ledger.csv",
            native_run/"qualification_diagnostics"/f"evaluation_{sequence:04d}_thermal_diagonal_ledger.csv",
        )
        path=next((p for p in candidates if p.is_file()),None)
        if path is None: raise FileNotFoundError(candidates[0])
        for row in _read_csv(path):
            if int(row.get("element_z","0"))==12 and int(row.get("data_type","0"))==99:
                row=dict(row); row["sequence"]=str(sequence); rows.append(row)
    return rows

def _component_counts(path: Path, component: str) -> tuple[int,int,float]:
    rows=[r for r in _read_csv(path) if r.get("component")==component]
    exact=sum(int(r.get("computed_exact","0")) for r in rows)
    maximum=max((abs(float(r.get("computed_signed_delta","nan"))) for r in rows),default=float("nan"))
    return exact,len(rows),maximum

def audit(source_capture: Path,native_run: Path,baseline_v461931: Path,
          component_comparison: Path,type50_report: Path,output: Path)->dict[str,Any]:
    errors=[]; gates={}
    source_report=json.loads((source_capture/"all61_magnesium_type99_primary_cooling_capture_report.json").read_text())
    source_ucalc=_read_csv(source_capture/"v0472_all61_magnesium_type99_ucalc.csv")
    source_ledger=_read_csv(source_capture/"v0472_all61_magnesium_type99_primary_thermal_ledger.csv")
    source_family=_read_csv(source_capture/"v0472_all61_magnesium_type99_family_budget.csv")
    native_records=_native_record_rows(native_run)
    native_ledger=_native_ledger(native_run)
    baseline_ledger=_native_ledger(baseline_v461931/"native_all61")
    type50=json.loads(type50_report.read_text())

    gates["ALL_61_MAGNESIUM_TYPE99_SOURCE_STATES_CAPTURED"]="ACCEPT" if source_report.get("result")=="ACCEPT" and source_report.get("evaluations")==61 else "REJECT"
    gates["MAGNESIUM_TYPE99_UCALC_ROWS_EXACT_661"]="ACCEPT" if len(source_ucalc)==len(native_records)==661 else "REJECT"
    gates["MAGNESIUM_TYPE99_PRIMARY_THERMAL_ROWS_EXACT_1322"]="ACCEPT" if len(source_ledger)==len(native_ledger)==1322 else "REJECT"
    gates["MAGNESIUM_TYPE99_SOURCE_FAMILY_BUDGET_EXACT_61"]="ACCEPT" if len(source_family)==61 else "REJECT"

    src_u={(int(r["sequence"]),int(r["record"])):r for r in source_ucalc}
    nat_u={(int(r["sequence"]),int(r["record"])):r for r in native_records}
    ucmp=[]; answer_exact=0
    for key in sorted(set(src_u)|set(nat_u)):
        s=src_u.get(key); n=nat_u.get(key)
        row={"sequence":key[0],"record":key[1],"source_present":int(s is not None),"native_present":int(n is not None)}
        all_exact=s is not None and n is not None and n.get("type99_shadow_valid")=="1"
        for index in range(1,7):
            sv=s.get(f"ans{index}","") if s else ""; nv=n.get(f"type99_shadow_ans{index}","") if n else ""
            ex=_exact(sv,nv); answer_exact+=int(ex)
            row.update({f"source_ans{index}":sv,f"native_shadow_ans{index}":nv,f"ans{index}_exact":int(ex)})
            all_exact=all_exact and ex
        row["all_answers_exact"]=int(all_exact); ucmp.append(row)
    _write_csv(output/UCALC_OUT,ucmp)
    gates["MAGNESIUM_TYPE99_UCALC_ANSWERS_EXACT_3966"]="ACCEPT" if answer_exact==3966 and len(ucmp)==661 else "REJECT"

    def key(r): return (int(r["sequence"]),int(r["record"]),r["role"])
    src={key(r):r for r in source_ledger}; nat={key(r):r for r in native_ledger}; old={key(r):r for r in baseline_ledger}
    keys=sorted(set(src)|set(nat)|set(old))
    lcmp=[]; source_keys_exact=set(src)==set(nat) and len(src)==1322
    primary_rows=primary_exact=0; negative_preserved=0; secondary_preserved=0; weighted_exact=0; unexplained=0
    source_sums={i:0.0 for i in range(1,62)}; native_sums={i:0.0 for i in range(1,62)}
    for k in keys:
        s=src.get(k); n=nat.get(k); b=old.get(k)
        row={"sequence":k[0],"record":k[1],"role":k[2],"source_present":int(s is not None),"native_present":int(n is not None),"baseline_present":int(b is not None)}
        if not (s and n and b): unexplained+=1; lcmp.append(row); continue
        scj=float(s["cj"]); ncj=float(n["cj"]); bcj=float(b["cj"])
        source_positive=scj>0.0; applied=int(n.get("magnesium_type99_primary_cooling_reduction_applied","0"))
        row_exact=_exact(s["compact_row"],n["compact_row"]) and _exact(s["cj"],n["cj"])
        weighted=_exact(s["weighted_population"],n["weighted_population"])
        contribution=_exact(s["cooling_contribution"],n["cooling_contribution"])
        if source_positive:
            primary_rows+=1; primary_exact+=int(row_exact and weighted and contribution and applied==1)
            source_sums[k[0]]+=float(s["cooling_contribution"]); native_sums[k[0]]+=float(n["cooling_contribution"])
        else:
            negative_preserved+=int(_exact(n["compact_row"],b["compact_row"]) and _exact(n["cj"],b["cj"]) and applied==0)
        secondary_preserved+=int(_exact(n["cj2"],b["cj2"]) and _exact(n["heating2_contribution"],b["heating2_contribution"]) and _exact(n["cooling2_contribution"],b["cooling2_contribution"]))
        weighted_exact+=int(weighted)
        if source_positive and not (row_exact and weighted and contribution and applied==1): unexplained+=1
        row.update({
            "source_compact_row":s["compact_row"],"baseline_compact_row":b["compact_row"],"native_compact_row":n["compact_row"],
            "source_cj":s["cj"],"baseline_cj":b["cj"],"native_pre_reduction_cj":n.get("native_cj",""),"native_final_cj":n["cj"],
            "source_cj2":s["cj2"],"baseline_cj2":b["cj2"],"native_cj2":n["cj2"],
            "source_weighted_population":s["weighted_population"],"native_weighted_population":n["weighted_population"],
            "source_cooling_contribution":s["cooling_contribution"],"native_cooling_contribution":n["cooling_contribution"],
            "source_primary_cooling_row":int(source_positive),"reduction_applied":applied,
            "primary_row_exact":int(row_exact and weighted and contribution),"secondary_preserved":int(_exact(n["cj2"],b["cj2"]))})
        lcmp.append(row)
    _write_csv(output/LEDGER_OUT,lcmp)
    gates["MAGNESIUM_TYPE99_SOURCE_LEDGER_KEYS_EXACT_1322"]="ACCEPT" if source_keys_exact else "REJECT"
    gates["MAGNESIUM_TYPE99_PRIMARY_COOLING_ROWS_REDUCED_EXACT"]="ACCEPT" if primary_rows>0 and primary_exact==primary_rows else "REJECT"
    gates["MAGNESIUM_TYPE99_NONCOOLING_PRIMARY_ROWS_PRESERVED"]="ACCEPT" if negative_preserved==len(src)-primary_rows else "REJECT"
    gates["MAGNESIUM_TYPE99_SECONDARY_CHANNELS_PRESERVED_1322"]="ACCEPT" if secondary_preserved==1322 else "REJECT"
    gates["MAGNESIUM_TYPE99_COMPACT_POPULATIONS_EXACT_1322"]="ACCEPT" if weighted_exact==1322 else "REJECT"

    fam_by={int(r["sequence"]):r for r in source_family}; frows=[]; family_exact=0
    for seq in range(1,62):
        sf=fam_by.get(seq,{}); ss=source_sums[seq]; ns=native_sums[seq]
        exact=_exact(ss,ns) and _exact(sf.get("mg_type99_cooling","nan"),ss)
        family_exact+=int(exact)
        frows.append({"sequence":seq,"source_family_cooling":sf.get("mg_type99_cooling",""),"source_ledger_cooling":ss,"native_reduced_cooling":ns,"exact":int(exact)})
    _write_csv(output/FAMILY_OUT,frows)
    gates["MAGNESIUM_TYPE99_PRIMARY_COOLING_ALL61_EXACT"]="ACCEPT" if family_exact==61 else "REJECT"

    mg_exact,mg_total,mg_max=_component_counts(component_comparison,"mg_cooling")
    h_exact,h_total,_=_component_counts(component_comparison,"h_cooling")
    all_rows=_read_csv(component_comparison); native_exact=sum(int(r.get("computed_exact","0")) for r in all_rows)
    gates["MAGNESIUM_COOLING_ALL61_EXACT"]="ACCEPT" if mg_exact==mg_total==61 else "REJECT"
    gates["HYDROGEN_COOLING_ALL61_PRESERVED"]="ACCEPT" if h_exact==h_total==61 else "REJECT"
    gates["NATIVE_COMPUTED_THERMAL_VALUES_EXACT_1127"]="ACCEPT" if native_exact==1127 and len(all_rows)==2440 else "REJECT"
    t50g=type50.get("gates",{})
    gates["MAGNESIUM_TYPE50_CLOSURE_PRESERVED"]="ACCEPT" if type50.get("result")=="ACCEPT" and t50g.get("MAGNESIUM_TYPE50_COMMITTED_REVERSE_CJ_EXACT_146286")=="ACCEPT" and t50g.get("MAGNESIUM_TYPE50_COMMITTED_REVERSE_COOLING_EXACT_146286")=="ACCEPT" else "REJECT"
    gates["MAGNESIUM_TYPE99_UNEXPLAINED_DELTAS_ZERO"]="ACCEPT" if unexplained==0 else "REJECT"
    result="ACCEPT" if all(v=="ACCEPT" for v in gates.values()) else "REJECT"
    return {"schema":SCHEMA,"release":RELEASE,"result":result,"gates":gates,"errors":[k for k,v in gates.items() if v!="ACCEPT"],
            "source_ucalc_rows":len(source_ucalc),"native_ucalc_rows":len(native_records),"ucalc_answer_values_exact":answer_exact,
            "source_thermal_rows":len(source_ledger),"native_thermal_rows":len(native_ledger),"primary_cooling_rows":primary_rows,"primary_cooling_rows_exact":primary_exact,
            "source_family_values_exact":family_exact,"mg_cooling_exact":mg_exact,"mg_cooling_total":mg_total,"mg_cooling_max_abs_delta":mg_max,
            "native_computed_values_exact":native_exact,"native_computed_values_total":len(all_rows),"unexplained_deltas":unexplained,
            "qualification_only":True,"production_promotion_ready":False}

def main(argv=None)->int:
    p=argparse.ArgumentParser(); p.add_argument("--source-capture",type=Path,required=True); p.add_argument("--native-run",type=Path,required=True); p.add_argument("--baseline-v461931",type=Path,required=True); p.add_argument("--component-comparison",type=Path,required=True); p.add_argument("--type50-report",type=Path,required=True); p.add_argument("--output",type=Path,required=True); p.add_argument("--output-json",type=Path,required=True)
    a=p.parse_args(argv)
    try: r=audit(a.source_capture.resolve(),a.native_run.resolve(),a.baseline_v461931.resolve(),a.component_comparison.resolve(),a.type50_report.resolve(),a.output.resolve())
    except Exception as exc: r={"schema":SCHEMA,"release":RELEASE,"result":"REJECT","gates":{},"errors":[str(exc)],"qualification_only":True,"production_promotion_ready":False}
    a.output_json.parent.mkdir(parents=True,exist_ok=True); a.output_json.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n"); print(json.dumps(r,indent=2,sort_keys=True)); return 0 if r["result"]=="ACCEPT" else 2
if __name__=="__main__": raise SystemExit(main())
