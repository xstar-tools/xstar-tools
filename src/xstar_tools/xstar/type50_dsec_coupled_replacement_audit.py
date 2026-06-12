"""Qualification-only actual-DSEC type-50 coupled replacement audit."""
from __future__ import annotations

import argparse, csv, json, os, struct
from pathlib import Path
from typing import Any, Iterable
import numpy as np

from .helium_family_isolation import RADIATION_SHA256, discover_reference, load_oracle, read_csv, run_command, sha256, state_metrics, verify_type53_invariant, write_csv, write_json
from .helium_matrix_residual_decomposition import verify_type71_invariant, verify_type99_invariant
from .helium_solve_response_decomposition import (_diagnostic_path, _matrix, _solve_rows, _effective_system, _reference_populations, _residual_rows, _verify_source_order_assembly, _preliminary_comparison, _matrix_delta_rows, _population_delta_rows)
from .type50_manifold_replacement_audit import REFERENCE_DIR, reference_metrics, metric_improvements, metric_delta
from .type71_type99_replacement_audit import TYPE71_BUNDLE, TYPE71_ORACLE_SHA256, TYPE99_BUNDLE, TYPE99_ORACLE_SHA256, element_isolation
from .v0472_type71_runtime_capture import ORACLE_NAME as TYPE71_ORACLE_NAME, verify as verify_type71
from .v0472_type99_runtime_capture import ORACLE_NAME as TYPE99_ORACLE_NAME, verify as verify_type99

RELEASE="0.6.48.7.13"
SCHEMA="xstar-tools-v0648713-type50-dsec-coupled-replacement-audit-v1"
BUNDLE=Path("src/xstar_tools/benchmarks/v0648712_type50_dsec_runtime_oracle_v0472")
RECORDS="type50_heii_rows46_54_dsec_runtime_records.csv"
TERMS="type50_heii_rows46_54_dsec_runtime_matrix_terms.csv"
RECORD_SHA="d860a17a644a952dd6fe47a47cf166e2bd309ec29832d66020ec0b610baa5399"
TERM_SHA="7e48fbc5f159efa9e6c409be7823f283ab80f179629efcbae9abdd348b116443"
TRACE_SHA="46ad8a73302ea68381829f4568c6907b3c618e0a4449e3337f692a5dd6121257"


def _bits(value: str|float) -> bytes:
    return struct.pack(">d", float(value))


def _run(root:Path, exe:Path, lowered:Path, trajectory:Path, radiation:Path, out:Path, evaluation:int, dsec:bool)->None:
    if (out/"native_evaluation_summary.json").is_file() and _diagnostic_path(out,evaluation,"helium_solve_state.json").is_file(): return
    env=dict(os.environ); env["PYTHONPATH"]=str(root/"src")+(os.pathsep+env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["XSTAR_QUALIFICATION_REPLACEMENT"]="1"; env["XSTAR_QUALIFICATION_TYPE99_RECORD1695_ORACLE"]="1"; env["XSTAR_QUALIFICATION_SOLVE_RESPONSE"]="1"
    env.pop("XSTAR_QUALIFICATION_TYPE50_MANIFOLD_ORACLE",None)
    if dsec: env["XSTAR_QUALIFICATION_TYPE50_DSEC_RUNTIME_ORACLE"]="1"
    else: env.pop("XSTAR_QUALIFICATION_TYPE50_DSEC_RUNTIME_ORACLE",None)
    run_command([str(exe),"run-fixed-evaluation","--case-dir",str(lowered),"--trajectory-csv",str(trajectory),"--evaluation",str(evaluation),"--radiation-csv",str(radiation),"--diagnostics-dir",str(out/"diagnostics"),"--output-dir",str(out)],cwd=root,env=env)


def _oracle(root:Path):
    d=root/BUNDLE
    if sha256(d/RECORDS)!=RECORD_SHA or sha256(d/TERMS)!=TERM_SHA or sha256(d/"dsec_evaluation_trace.csv")!=TRACE_SHA: raise ValueError("actual-DSEC oracle hash mismatch")
    r=read_csv(d/RECORDS); t=read_csv(d/TERMS)
    if len(r)!=79 or len(t)!=316: raise ValueError("actual-DSEC oracle inventory mismatch")
    return r,t


def _compare_answers(run:Path, oracle:list[dict[str,str]], output:Path, evaluation:int)->dict[str,Any]:
    rows=read_csv(_diagnostic_path(run,evaluation,"records.csv"))
    by={(int(r["source_position"]),int(r["record"])):r for r in rows if int(r["data_type"])==50 and int(r["element_z"])==2}
    out=[]; exact={f"ans{i}":0 for i in range(1,7)}
    for o in oracle:
        k=(int(o["source_position"]),int(o["record"])); a=by.get(k)
        if a is None: raise ValueError(f"missing applied type-50 record {k}")
        row={"source_position":k[0],"record":k[1],"lower_row":int(o["lower_row"]),"upper_row":int(o["upper_row"]),"tau_in":float(o["tau_in"]),"tau_out":float(o["tau_out"]),"ptmp1":float(o["ptmp1"]),"ptmp2":float(o["ptmp2"]),"flinabs_ptmp1":float(o["flinabs_ptmp1"]),"covering_fraction":float(o["covering_fraction"])}
        for i in range(1,7):
            ok=_bits(a[f"ans{i}"])==_bits(o[f"ans{i}"]); exact[f"ans{i}"]+=int(ok); row[f"oracle_ans{i}"]=float(o[f"ans{i}"]); row[f"applied_ans{i}"]=float(a[f"ans{i}"]); row[f"ans{i}_ieee_exact"]=ok
        out.append(row)
    write_csv(output/"type50_dsec_candidate_answer_comparison.csv",out,list(out[0]))
    return {"records":79,"answers":474,"exact_by_answer":exact,"all_ieee_exact":all(v==79 for v in exact.values()),"record_oracle_sha256":RECORD_SHA}


def _compare_terms(run:Path, oracle:list[dict[str,str]], output:Path, evaluation:int)->dict[str,Any]:
    rows=read_csv(_diagnostic_path(run,evaluation,"helium_source_order_terms.csv"))
    selected=[r for r in rows if int(r["data_type"])==50 and 46<=min(int(r["full_row"]),int(r["full_column"]))<=54 or False]
    # Exact key selection is safer than row filtering.
    keys={(int(o["source_position"]),int(o["record"])) for o in oracle}
    selected=[r for r in rows if (int(r["contribution_source_position"]),int(r["record"])) in keys]
    role={"forward_gain":"forward_offdiag","reverse_gain":"reverse_offdiag","forward_diag_loss":"forward_diag_loss","reverse_diag_loss":"reverse_diag_loss"}
    actual={(int(r["contribution_source_position"]),int(r["record"]),role[r["role"]]):r for r in selected}
    out=[]; exact=0
    for o in oracle:
        k=(int(o["source_position"]),int(o["record"]),o["role"]); a=actual.get(k)
        if a is None: raise ValueError(f"missing committed term {k}")
        row={"source_position":k[0],"record":k[1],"role":k[2],"row":int(o["row"]),"column":int(o["column"])}; ok=True
        for field in ("aj1","aj2","cj","cj2"):
            same=_bits(a[field])==_bits(o[field]); ok &= same; row[f"oracle_{field}"]=float(o[field]); row[f"applied_{field}"]=float(a[field]); row[f"{field}_ieee_exact"]=same
        exact+=int(ok); row["term_ieee_exact"]=ok; out.append(row)
    write_csv(output/"type50_dsec_candidate_matrix_terms.csv",out,list(out[0]))
    return {"terms":316,"exact_terms":exact,"all_ieee_exact":exact==316,"matrix_terms_sha256":TERM_SHA}


def _constraints(root:Path, run:Path, evaluation:int)->dict[str,Any]:
    o53=load_oracle(root/"src/xstar_tools/benchmarks/v064873_type53_runtime_oracle_v0472")
    d71=root/TYPE71_BUNDLE; d99=root/TYPE99_BUNDLE
    if verify_type71(d71)["oracle_sha256"]!=TYPE71_ORACLE_SHA256 or verify_type99(d99)["oracle_sha256"]!=TYPE99_ORACLE_SHA256: raise ValueError("immutable oracle verification failed")
    o71=read_csv(d71/TYPE71_ORACLE_NAME); o99=read_csv(d99/TYPE99_ORACLE_NAME)[0]
    return {"type53":verify_type53_invariant(run,o53,evaluation),"type71":verify_type71_invariant(run,o71,evaluation),"type99":verify_type99_invariant(run,o99,evaluation)}


def audit(package_dir:Path, lowered_program:Path, output_dir:Path, *, evaluation:int=61, radiation_csv:Path|None=None)->dict[str,Any]:
    if evaluation!=61: raise ValueError("actual-DSEC coupled replacement is restricted to evaluation 61")
    root=package_dir.resolve(); lowered=lowered_program.resolve(); out=output_dir.resolve(); out.mkdir(parents=True,exist_ok=True)
    oracle_records,oracle_terms=_oracle(root)
    traj=discover_reference(root,"trajectory.csv"); rad=radiation_csv.resolve() if radiation_csv else discover_reference(root,"reference_radiation_v0472_full.csv")
    if sha256(rad)!=RADIATION_SHA256: raise ValueError("qualification radiation hash mismatch")
    exe=root/"src/xstar_tools/xstar/cpp/xstar_cpp"; env=dict(os.environ); env["PYTHONPATH"]=str(root/"src")
    run_command(["make","-C",str(root/"src/xstar_tools/xstar/cpp"),"-j2"],cwd=root,env=env)
    baseline=out/"baseline_exact_53_71_99"; candidate=out/"candidate_actual_dsec_type50"
    _run(root,exe,lowered,traj,rad,baseline,evaluation,False); _run(root,exe,lowered,traj,rad,candidate,evaluation,True)
    answers=_compare_answers(candidate,oracle_records,out,evaluation); terms=_compare_terms(candidate,oracle_terms,out,evaluation)
    constraints={"baseline":_constraints(root,baseline,evaluation),"candidate":_constraints(root,candidate,evaluation)}
    isolation=element_isolation(baseline,candidate,evaluation); preliminary=_preliminary_comparison(baseline,candidate,evaluation)
    brows=_solve_rows(baseline,evaluation); crows=_solve_rows(candidate,evaluation); norm=next(i for i,r in enumerate(brows) if int(r["is_normalization_row"])==1)
    ref=_reference_populations(root,evaluation,brows); bmat,bh,bh2,brhs=_matrix(baseline,evaluation); cmat,ch,ch2,crhs=_matrix(candidate,evaluation)
    bres=np.asarray([r["effective_solver_residual"] for r in _residual_rows("baseline",brows,bmat,ref,norm,"reference")],dtype=float)
    cres_rows=_residual_rows("candidate",crows,cmat,ref,norm,"reference"); cres=np.asarray([r["effective_solver_residual"] for r in cres_rows],dtype=float)
    write_csv(out/"helium_reference_residual_rows.csv",cres_rows,list(cres_rows[0]))
    bnative=np.asarray([float(r["final_population"]) for r in brows]); cnative=np.asarray([float(r["final_population"]) for r in crows])
    delta_rows=_matrix_delta_rows(bmat,cmat,bh,ch,bh2,ch2,brows); write_csv(out/"helium_actual_dsec_matrix_delta.csv",delta_rows,list(delta_rows[0]))
    pop_rows=_population_delta_rows(brows,crows,ref); write_csv(out/"helium_actual_dsec_solution_response.csv",pop_rows,list(pop_rows[0]))
    beff,br=_effective_system(bmat,norm); ceff,cr=_effective_system(cmat,norm)
    bcond=float(np.linalg.cond(beff)); ccond=float(np.linalg.cond(ceff)); brank=int(np.linalg.matrix_rank(beff)); crank=int(np.linalg.matrix_rank(ceff))
    reduction=float(np.sum(np.abs(bres))-np.sum(np.abs(cres))); frac=reduction/max(float(np.sum(np.abs(bres))),1e-300)
    base_metrics=state_metrics(baseline,evaluation); cand_metrics=state_metrics(candidate,evaluation); reference=reference_metrics(root,evaluation); improvements,all_improved=metric_improvements(base_metrics,cand_metrics,reference)
    write_csv(out/"type50_dsec_fixed_state_metrics.csv",improvements,list(improvements[0]))
    baseline_terms=read_csv(_diagnostic_path(baseline,evaluation,"helium_source_order_terms.csv")); candidate_terms=read_csv(_diagnostic_path(candidate,evaluation,"helium_source_order_terms.csv"))
    bledger=[{**r,"source_order_index":int(r["source_order_index"]),"compact_row":int(r["compact_row"]),"compact_column":int(r["compact_column"]),"aj1":float(r["aj1"])} for r in baseline_terms]
    cledger=[{**r,"source_order_index":int(r["source_order_index"]),"compact_row":int(r["compact_row"]),"compact_column":int(r["compact_column"]),"aj1":float(r["aj1"])} for r in candidate_terms]
    assembly={"baseline":_verify_source_order_assembly(bledger,bmat),"candidate":_verify_source_order_assembly(cledger,cmat)}
    immutable=all([constraints["candidate"]["type53"]["applied_exact"],constraints["candidate"]["type71"]["all_ieee_exact"],constraints["candidate"]["type99"]["all_ieee_exact"]])
    ok=answers["all_ieee_exact"] and terms["all_ieee_exact"] and immutable and isolation["max_h_mg_absolute_delta"]==0.0 and preliminary["baseline_candidate_ieee_exact"] and frac>=0.90 and crank==78 and ccond<bcond and assembly["candidate"]["matrix_ieee_exact"]
    summary={"schema":SCHEMA,"release":RELEASE,"result":"ACCEPT" if ok else "REJECT","evaluation_ordinal":61,"qualification_only":True,"actual_dsec_oracle":{"record_oracle_sha256":RECORD_SHA,"matrix_terms_sha256":TERM_SHA,"trace_sha256":TRACE_SHA,"records":79,"matrix_terms":316},"answer_exactness":answers,"matrix_term_exactness":terms,"immutable_constraints":constraints,"element_isolation":isolation,"preliminary_and_active_stage_comparison":preliminary,"source_order_assembly":assembly,"linear_system":{"baseline":{"reference_residual_l1":float(np.sum(np.abs(bres))),"condition_number_2":bcond,"matrix_rank":brank},"candidate":{"reference_residual_l1":float(np.sum(np.abs(cres))),"reference_residual_linf":float(np.max(np.abs(cres))),"condition_number_2":ccond,"matrix_rank":crank},"delta":{"reference_residual_l1_reduction":reduction,"reference_residual_fraction_reduced":frac,"dense_matrix_nonzero_entries":len(delta_rows),"dense_matrix_delta_l1":float(np.sum(np.abs(cmat-bmat))),"dense_matrix_delta_linf":float(np.max(np.abs(cmat-bmat))),"native_solution_delta_l1":float(np.sum(np.abs(cnative-bnative))),"native_solution_delta_linf":float(np.max(np.abs(cnative-bnative))),"rhs_ieee_exact":bool(np.array_equal(brhs,crhs))}},"baseline_state":base_metrics,"candidate_state":cand_metrics,"reference_state":reference,"whole_fixed_state_metric_improvements":improvements,"all_whole_fixed_state_metrics_improved":all_improved,"candidate_general_state_implementation":False,"fixed_state_parity":False,"type50_general_state_promotion_ready":False,"production_promotion_ready":False,"remaining_blockers":["the substitution is bound to the captured evaluation-61 DSEC state","the full type-50 escape-probability law is not yet implemented for arbitrary states","whole fixed-state parity remains incomplete","thermal, controller, and product parity remain blocked"]}
    write_json(out/"summary.json",summary); write_json(out/"helium_actual_dsec_linear_system_summary.json",summary["linear_system"]); print(json.dumps(summary,indent=2,sort_keys=True)); return summary


def main(argv:Iterable[str]|None=None)->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("package_dir",type=Path); p.add_argument("lowered_program",type=Path); p.add_argument("output_dir",type=Path); p.add_argument("--evaluation",type=int,default=61); p.add_argument("--radiation-csv",type=Path); p.add_argument("--output-json",type=Path); a=p.parse_args(argv)
    try: r=audit(a.package_dir,a.lowered_program,a.output_dir,evaluation=a.evaluation,radiation_csv=a.radiation_csv)
    except Exception as e: print(f"actual-DSEC type-50 audit failed: {e}"); return 2
    if a.output_json: write_json(a.output_json,r)
    return 0 if r["result"]=="ACCEPT" else 2

if __name__=="__main__": raise SystemExit(main())
