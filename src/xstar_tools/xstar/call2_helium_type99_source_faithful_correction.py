"""v0.6.48.7.36 Type-99 records 779/780/1695 source-faithful correction audit."""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.36"
SCHEMA = "xstar-tools-v0648736-type99-source-faithful-correction-v1"
SUMMARY = "call2_helium_solve_state_rate_matrix_decomposition_summary.json"
TARGET_RECORDS = (779, 780, 1695)
ANS_FIELDS = tuple(f"ans{i}" for i in range(1, 7))
INTERMEDIATE_FIELDS = (
    ("threshold_ev", "diag_type99_threshold_eV_derived", "type99_threshold_ev"),
    ("destination_energy_ev", "diag_type99_leveltemp_destination_energy_eV", "type99_destination_energy_ev"),
    ("swrat", "diag_type99_swrat", "type99_swrat"),
    ("rec_cm3_s", "diag_type99_calt99_rec_cm3_s", "type99_rec_cm3_s"),
    ("milne_alpha_cm3_s", "diag_type99_calt99_alpha_milne_cm3_s", "type99_milne_alpha_cm3_s"),
    ("cross_section_scale", "diag_type99_calt99_scale_rec_over_alpha", "type99_cross_section_scale"),
    ("pirt_unscaled_s", "diag_pirt", "type99_pirt_unscaled_s"),
    ("rrrt_unscaled_s", "diag_rrrt", "type99_rrrt_unscaled_s"),
    ("piht_unscaled_erg_s", "diag_piht", "type99_piht_unscaled_erg_s"),
    ("rrcl_unscaled_erg_s", "diag_rrcl", "type99_rrcl_unscaled_erg_s"),
    ("piht2_unscaled_erg_s", "diag_piht2", "type99_piht2_unscaled_erg_s"),
    ("rrcl2_unscaled_erg_s", "diag_rrcl2", "type99_rrcl2_unscaled_erg_s"),
    ("phint_scale", "diag_type99_scale", "type99_phint_scale"),
    ("nbinc_threshold_one_based", "diag_nbinc_threshold_fortran", "type99_nbinc_threshold_one_based"),
    ("nb1_one_based", "diag_nb1_fortran", "type99_nb1_one_based"),
    ("nphint_one_based", "diag_nphint_fortran", "type99_nphint_one_based"),
    ("ndelt", "diag_ndelt_fortran", "type99_ndelt"),
    ("npass", "diag_npass", "type99_npass"),
    ("cached_atmp22_stale_reuses", "diag_n_cached_atmp22_stale_reuses", "type99_cached_atmp22_stale_reuses"),
)

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))

def f(row: dict[str, str], key: str) -> float:
    try: return float(row.get(key, "nan"))
    except (TypeError, ValueError): return math.nan

def exact(a: float, b: float) -> bool:
    return math.isfinite(a) and math.isfinite(b) and a == b

def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields: fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    summary_path=args.output/SUMMARY
    base=json.loads(summary_path.read_text())
    gates=dict(base.get("gates", {}))
    source_rows=read_csv(args.source_capture/"v0472_call2_eval1_he_bound_free_records.csv")
    native_rows=read_csv(args.native_replay/"diagnostics/evaluation_0022_records.csv")
    source={int(float(r["record"])):r for r in source_rows if int(float(r.get("data_type",0)))==99}
    native={int(float(r["record"])):r for r in native_rows if int(float(r.get("data_type",0)))==99}
    rows=[]
    all_answers=True; all_intermediates=True
    for record in TARGET_RECORDS:
        sr=source.get(record,{}); nr=native.get(record,{})
        row:dict[str,Any]={"record":record,"source_present":bool(sr),"native_present":bool(nr)}
        record_answer_exact=bool(sr and nr)
        for name in ANS_FIELDS:
            sv=f(sr,name); nv=f(nr,name); ok=exact(sv,nv)
            row[f"source_{name}"]=sv; row[f"native_{name}"]=nv; row[f"{name}_exact"]=ok
            record_answer_exact &= ok
        record_intermediate_exact=bool(sr and nr)
        for label, source_key, native_key in INTERMEDIATE_FIELDS:
            sv=f(sr,source_key); nv=f(nr,native_key); ok=exact(sv,nv)
            row[f"source_{label}"]=sv; row[f"native_{label}"]=nv; row[f"{label}_exact"]=ok
            record_intermediate_exact &= ok
        row["answers_exact"]=record_answer_exact
        row["intermediates_exact"]=record_intermediate_exact
        all_answers &= record_answer_exact; all_intermediates &= record_intermediate_exact
        rows.append(row)
    write_csv(args.output/"call2_he_type99_record_comparison.csv", rows)

    type99_gate=gates.get("CALL2_HE_TYPE99_RATE_MATRIX")
    matrix_exact=int(base.get("dense_matrix_exact_cells",0))
    matrix_cells=int(base.get("matrix_cells",6084))
    remaining=matrix_cells-matrix_exact
    target_capture=all(bool(source.get(r)) and bool(native.get(r)) for r in TARGET_RECORDS)
    gates.update({
        "CALL2_HE_TYPE99_TARGET_RECORD_CAPTURE":"ACCEPT" if target_capture else "REJECT",
        "CALL2_HE_TYPE99_DESTINATION_WORKSPACE":"ACCEPT" if all(row["destination_energy_ev_exact"] for row in rows) else "REJECT",
        "CALL2_HE_TYPE99_THRESHOLD":"ACCEPT" if all(row["threshold_ev_exact"] for row in rows) else "REJECT",
        "CALL2_HE_TYPE99_CALT99_DENSITY_SEMANTICS":"ACCEPT" if all(row["rec_cm3_s_exact"] for row in rows) else "REJECT",
        "CALL2_HE_TYPE99_MILNE_INTIN_IEEE":"ACCEPT" if all(row["milne_alpha_cm3_s_exact"] and row["cross_section_scale_exact"] for row in rows) else "REJECT",
        "CALL2_HE_TYPE99_PHINT53HUNT_REDUCED_GRID":"ACCEPT" if all(row["nbinc_threshold_one_based_exact"] and row["nb1_one_based_exact"] and row["nphint_one_based_exact"] and row["ndelt_exact"] for row in rows) else "REJECT",
        "CALL2_HE_TYPE99_PHINT53HUNT_NORMALIZATION":"ACCEPT" if all(row["pirt_unscaled_s_exact"] and row["rrrt_unscaled_s_exact"] and row["phint_scale_exact"] for row in rows) else "REJECT",
        "CALL2_HE_TYPE99_FINAL_SIGN_SCALE_SEQUENCE":"ACCEPT" if all_answers else "REJECT",
        "CALL2_HE_TYPE99_ANS1_TO_ANS6_EXACT":"ACCEPT" if all_answers else "REJECT",
        "CALL2_HE_TYPE99_ROOT_CAUSE":"ACCEPT" if all_answers and all_intermediates else "REJECT",
        "CALL2_HE_TYPE99_RATE_MATRIX":"ACCEPT" if type99_gate=="ACCEPT" and all_answers else "REJECT",
        "CALL2_HE_FIXED_STATE_PARITY": f"BLOCKED_BY_{remaining}_MATRIX_CELLS" if remaining else "RUN_ALLOWED",
    })
    accepted=target_capture and all_answers and all_intermediates and gates["CALL2_HE_TYPE99_RATE_MATRIX"]=="ACCEPT"
    report={**base,
        "schema":SCHEMA,"release":RELEASE,"result":"ACCEPT" if accepted else "REJECT",
        "physics_changed":True,
        "physics_change_scope":"Type-99 records 779/780/1695 source-faithful destination workspace, calt99, milne/intin, reduced bremsmap phint53hunt, and final ans1-ans6 sequence",
        "type99_target_records":list(TARGET_RECORDS),
        "type99_exact_records":sum(1 for row in rows if row["answers_exact"] and row["intermediates_exact"]),
        "type99_answers_exact":all_answers,"type99_intermediates_exact":all_intermediates,
        "dense_matrix_exact_cells":matrix_exact,"remaining_incorrect_matrix_cells":remaining,
        "gates":gates,"qualification_only":True,"production_promotion_ready":False,
    }
    summary_path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True)); return 0 if accepted else 2

if __name__=="__main__": raise SystemExit(main())
