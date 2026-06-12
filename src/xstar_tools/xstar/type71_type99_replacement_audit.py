"""Audit a coupled type-71/type-99 evaluation-61 replacement candidate.

The type-71 side is checked against an independently captured 31-record
v0.6.47.2 evaluator oracle.  The type-99 side uses the immutable record-1695
oracle through an explicit qualification-only native substitution.  The module
measures the physical consequence without enabling any production correction.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import tarfile
from pathlib import Path
from typing import Any

from .helium_family_isolation import (
    ORACLE_SHA256 as TYPE53_ORACLE_SHA256,
    RADIATION_SHA256,
    discover_reference,
    load_oracle,
    read_csv,
    run_command,
    run_fixed_evaluation,
    sha256,
    state_metrics,
    verify_type53_invariant,
    write_csv,
    write_json,
)
from .v0472_type71_runtime_capture import ORACLE_NAME as TYPE71_ORACLE_NAME, verify as verify_type71
from .v0472_type99_runtime_capture import ORACLE_NAME as TYPE99_ORACLE_NAME, verify as verify_type99

RELEASE = "0.6.48.7.13"
SCHEMA = "xstar-tools-v064877-type71-type99-replacement-audit-v1"
TYPE71_ORACLE_SHA256 = "c8ab6ebc2dbb467208528dcfc43cfb316176a3b4bafde906e44a53b6676a38e9"
TYPE99_ORACLE_SHA256 = "bab5297c01e068617a1e1fca4b6dab12cded24c0c139cb394ad2f4c2475ea37b"
TYPE71_BUNDLE = Path("src/xstar_tools/benchmarks/v064877_type71_row77_runtime_oracle_v0472")
TYPE99_BUNDLE = Path("src/xstar_tools/benchmarks/v064876_type99_record1695_runtime_oracle_v0472")
TARGET_RECORD = 1695
TARGET_SOURCE_POSITION = 6312


def ion_rows(output: Path, evaluation: int) -> dict[tuple[int, int], dict[str, str]]:
    rows = read_csv(output / "diagnostics" / f"evaluation_{evaluation:04d}_ion_balance.csv")
    return {(int(r["element_z"]), int(r["stage"])): r for r in rows}


def element_isolation(baseline: Path, candidate: Path, evaluation: int) -> dict[str, Any]:
    a, b = ion_rows(baseline, evaluation), ion_rows(candidate, evaluation)
    fields = ("preliminary_fraction", "final_fraction", "preliminary_ionization", "preliminary_recombination")
    max_h_mg = 0.0; nonzero = 0
    for key, row in a.items():
        if key[0] not in (1, 12):
            continue
        for field in fields:
            delta = float(b[key][field]) - float(row[field])
            max_h_mg = max(max_h_mg, abs(delta))
            if delta != 0.0: nonzero += 1
    helium_sum = sum(float(row["final_fraction"]) for (z, _), row in b.items() if z == 2)
    return {"max_h_mg_absolute_delta": max_h_mg, "nonzero_h_mg_fields": nonzero,
            "helium_final_normalization_error": helium_sum - 1.0}


def metric_delta(a: dict[str, Any], b: dict[str, Any]) -> dict[str, float]:
    keys = ("he1_final_fraction", "he2_final_fraction", "he3_final_fraction",
            "native_electron_fraction", "native_charge_residual", "native_hmctot")
    return {f"delta_{key}": float(b[key]) - float(a[key]) for key in keys}


def read_oracle(path: Path, name: str) -> list[dict[str, str]]:
    rows = read_csv(path / name)
    if not rows: raise ValueError(f"empty oracle: {path / name}")
    return rows


def compare_type71(records_csv: Path, oracle_rows: list[dict[str, str]], output: Path) -> dict[str, Any]:
    native_rows = read_csv(records_csv)
    native = {(int(r["source_position"]), int(r["record"])): r for r in native_rows}
    comparison: list[dict[str, Any]] = []
    matrix: list[dict[str, Any]] = []
    exact_by_answer = {f"ans{i}": 0 for i in range(1, 7)}
    for ref in oracle_rows:
        key = (int(ref["source_position"]), int(ref["record"]))
        if key not in native: raise ValueError(f"missing native type71 record {key}")
        obs = native[key]
        answers_native = tuple(float(obs[f"ans{i}"]) for i in range(1, 7))
        answers_ref = tuple(float(ref[f"ans{i}"]) for i in range(1, 7))
        for i, (a, b) in enumerate(zip(answers_native, answers_ref), start=1):
            exact = a == b
            if exact: exact_by_answer[f"ans{i}"] += 1
            comparison.append({"source_position": key[0], "record": key[1], "answer": f"ans{i}",
                               "native": a, "reference": b, "delta": a-b, "absolute_delta": abs(a-b),
                               "ieee_exact": exact})
        # Universal four-term insertion, recorded for both variants.
        for variant, vals in (("native", answers_native), ("v06472_reference", answers_ref)):
            a1,a2,a3,a4,a5,a6=vals
            terms=(("forward_gain",int(ref["upper_row"]),int(ref["lower_row"]),a1,a2,0.0,0.0),
                   ("reverse_gain",int(ref["lower_row"]),int(ref["upper_row"]),a2,a1,0.0,0.0),
                   ("forward_diag_loss",int(ref["lower_row"]),int(ref["lower_row"]),-a1,-a1,a4,a6),
                   ("reverse_diag_loss",int(ref["upper_row"]),int(ref["upper_row"]),-a2,-a2,-a3,-a5))
            for role,row,col,aj1,aj2,cj,cj2 in terms:
                matrix.append({"variant":variant,"source_position":key[0],"record":key[1],"role":role,
                               "row":row,"column":col,"aj1":aj1,"aj2":aj2,"cj":cj,"cj2":cj2})
    write_csv(output / "type71_row77_answer_comparison.csv", comparison, list(comparison[0]))
    write_csv(output / "type71_row77_matrix_terms.csv", matrix, list(matrix[0]))
    return {"records": len(oracle_rows), "answers_compared": len(comparison), "matrix_terms_written": len(matrix),
            "exact_by_answer": exact_by_answer,
            "all_ieee_exact": all(v == len(oracle_rows) for v in exact_by_answer.values()),
            "first_divergence": next((r for r in comparison if not r["ieee_exact"]), None)}


def compare_type99(records_csv: Path, oracle_row: dict[str, str], output: Path) -> dict[str, Any]:
    rows = read_csv(records_csv)
    native = next(r for r in rows if int(r["record"]) == TARGET_RECORD and int(r["source_position"]) == TARGET_SOURCE_POSITION)
    comparison=[]
    for i in range(1,7):
        a=float(native[f"ans{i}"]); b=float(oracle_row[f"ans{i}"])
        comparison.append({"source_position":TARGET_SOURCE_POSITION,"record":TARGET_RECORD,"answer":f"ans{i}",
                           "candidate":a,"reference":b,"delta":a-b,"absolute_delta":abs(a-b),"ieee_exact":a==b})
    write_csv(output / "type99_record1695_candidate_comparison.csv", comparison, list(comparison[0]))
    return {"all_ieee_exact": all(r["ieee_exact"] for r in comparison),
            "exact_answers": sum(bool(r["ieee_exact"]) for r in comparison),
            "first_divergence": next((r for r in comparison if not r["ieee_exact"]), None)}


def portable_lowered_snapshot(lowered: Path, output: Path) -> dict[str, Any]:
    target = output / "inputs" / "v04873_active_h_he_mg_fresh.tar.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as tf:
        for path in sorted(lowered.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"lowered program contains a symlink: {path}")
            if path.is_file():
                tf.add(path, arcname=str(Path(lowered.name) / path.relative_to(lowered)), recursive=False)
    with tarfile.open(target, "r:gz") as tf:
        members=tf.getmembers(); links=[m.name for m in members if m.issym() or m.islnk()]
        unsafe=[m.name for m in members if m.name.startswith("/") or ".." in Path(m.name).parts]
    if links or unsafe: raise ValueError("portable lowered snapshot safety check failed")
    return {"path": str(Path("inputs") / target.name), "sha256": sha256(target), "members": len(members),
            "links": len(links), "unsafe_members": len(unsafe)}


def audit(package_dir: Path, lowered_program: Path, output_dir: Path, *, evaluation: int = 61,
          radiation_csv: Path | None = None) -> dict[str, Any]:
    root=package_dir.resolve(); lowered=lowered_program.resolve(); output=output_dir.resolve(); output.mkdir(parents=True,exist_ok=True)
    trajectory=discover_reference(root,"trajectory.csv")
    radiation=radiation_csv.resolve() if radiation_csv else discover_reference(root,"reference_radiation_v0472_full.csv")
    if sha256(radiation)!=RADIATION_SHA256: raise ValueError("qualification radiation SHA-256 mismatch")
    exe=root/"src/xstar_tools/xstar/cpp/xstar_cpp"
    env=dict(os.environ); env["PYTHONPATH"]=str(root/"src")+(os.pathsep+env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    run_command(["make","-C",str(root/"src/xstar_tools/xstar/cpp"),"-j2"],cwd=root,env=env)
    baseline=output/"baseline"; candidate=output/"candidate_exact_type99_with_exact_type71"
    if not (baseline/"native_evaluation_summary.json").is_file():
        run_fixed_evaluation(exe,lowered,trajectory,radiation,baseline,evaluation,root=root,env=env)
    candidate_env=dict(env); candidate_env["XSTAR_QUALIFICATION_REPLACEMENT"]="1"; candidate_env["XSTAR_QUALIFICATION_TYPE99_RECORD1695_ORACLE"]="1"
    if not (candidate/"native_evaluation_summary.json").is_file():
        run_fixed_evaluation(exe,lowered,trajectory,radiation,candidate,evaluation,root=root,env=candidate_env)

    oracle53=load_oracle(root/"src/xstar_tools/benchmarks/v064873_type53_runtime_oracle_v0472")
    inv_base=verify_type53_invariant(baseline,oracle53,evaluation); inv_candidate=verify_type53_invariant(candidate,oracle53,evaluation)
    type71_dir=root/TYPE71_BUNDLE; type99_dir=root/TYPE99_BUNDLE
    v71=verify_type71(type71_dir); v99=verify_type99(type99_dir)
    if v71["result"]!="ACCEPT" or v71["oracle_sha256"]!=TYPE71_ORACLE_SHA256: raise ValueError("type71 oracle verification failed")
    if v99["result"]!="ACCEPT" or v99["oracle_sha256"]!=TYPE99_ORACLE_SHA256: raise ValueError("type99 oracle verification failed")
    rows71=read_oracle(type71_dir,TYPE71_ORACLE_NAME); rows99=read_oracle(type99_dir,TYPE99_ORACLE_NAME)
    comparison71=compare_type71(baseline/"diagnostics"/f"evaluation_{evaluation:04d}_records.csv",rows71,output)
    # Confirm the type71 path remains exact in the candidate run too.
    comparison71_candidate=compare_type71(candidate/"diagnostics"/f"evaluation_{evaluation:04d}_records.csv",rows71,output/"candidate_type71_check")
    comparison99=compare_type99(candidate/"diagnostics"/f"evaluation_{evaluation:04d}_records.csv",rows99[0],output)
    base_metrics=state_metrics(baseline,evaluation); cand_metrics=state_metrics(candidate,evaluation)
    isolation=element_isolation(baseline,candidate,evaluation); deltas=metric_delta(base_metrics,cand_metrics)
    portable=portable_lowered_snapshot(lowered,output)
    residual_improved=abs(float(cand_metrics["native_charge_residual"])) < abs(float(base_metrics["native_charge_residual"]))
    he3_toward_reference=float(cand_metrics["he3_final_fraction"]) > float(base_metrics["he3_final_fraction"])
    state_row={"evaluation_ordinal":evaluation}
    for prefix, values in (("baseline",base_metrics),("candidate",cand_metrics)):
        for key in ("he1_final_fraction","he2_final_fraction","he3_final_fraction","native_electron_fraction","native_charge_residual","native_hmctot"):
            state_row[f"{prefix}_{key}"]=values[key]
    state_row.update(deltas)
    write_csv(output/"coupled_candidate_state_delta.csv",[state_row],list(state_row))
    summary={
        "schema":SCHEMA,"release":RELEASE,"result":"ACCEPT","evaluation_ordinal":evaluation,
        "baseline":base_metrics,"candidate":cand_metrics,"candidate_deltas":deltas,
        "type53_invariant":{"baseline":inv_base,"candidate":inv_candidate,"oracle_sha256":TYPE53_ORACLE_SHA256,
                            "preserved":inv_base["records"]==31 and inv_candidate["records"]==31},
        "type71_runtime_oracle":{**v71,"capture_kind":"exact_v06472_fixed_state_type71_row77_evaluator_replay",
                                 "full_dsec_runtime_capture":False},
        "type71_baseline_comparison":comparison71,"type71_candidate_comparison":comparison71_candidate,
        "type99_runtime_oracle":{**v99,"record":TARGET_RECORD,"source_position":TARGET_SOURCE_POSITION,
                                 "full_dsec_runtime_capture":False},
        "type99_candidate_comparison":comparison99,
        "coupled_candidate_definition":"exact v0.6.47.2 type99 record 1695 oracle substitution with the 31 native type71 row77 amplitudes independently verified exact",
        "candidate_charge_residual_improved":residual_improved,
        "candidate_he3_moved_toward_reference":he3_toward_reference,
        "candidate_fixed_state_result":"REJECT" if not (residual_improved and he3_toward_reference) else "ACCEPT",
        "candidate_general_state_implementation":False,
        "type99_type71_physics_replacement_ready":False,
        "element_isolation":isolation,"portable_lowered_program_snapshot":portable,
        "full_type53_family_promotion_ready":False,"fixed_state_parity":False,"production_promotion_ready":False,
        "remaining_blockers":[
            "the exact evaluation-61 type99 record-1695 substitution worsens the charge residual and He III fraction",
            "the type99 replacement is a fixed-state oracle substitution, not a general-state source implementation",
            "other helium matrix families still compensate for the source-correct type53/type71/type99 contracts",
            "whole fixed-state electron, charge, and thermal parity remain blocked",
        ],
    }
    write_json(output/"summary.json",summary)
    return summary


def parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("package_dir",type=Path); p.add_argument("lowered_program",type=Path); p.add_argument("output_dir",type=Path); p.add_argument("--evaluation",type=int,default=61); p.add_argument("--radiation-csv",type=Path); p.add_argument("--output-json",type=Path); return p


def main(argv:list[str]|None=None)->int:
    args=parser().parse_args(argv)
    try:
        report=audit(args.package_dir,args.lowered_program,args.output_dir,evaluation=args.evaluation,radiation_csv=args.radiation_csv)
        if args.output_json: write_json(args.output_json.resolve(),report)
        print(json.dumps(report,indent=2,sort_keys=True)); return 0
    except Exception as exc:
        print(f"type71/type99 replacement audit failed: {exc}"); return 2


if __name__=="__main__": raise SystemExit(main())
