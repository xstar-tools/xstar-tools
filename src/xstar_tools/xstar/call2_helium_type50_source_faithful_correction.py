"""v0.6.48.7.37 Type-50 records 781/917 source-faithful correction audit."""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path
from typing import Any

RELEASE = "0.6.48.7.37"
SCHEMA = "xstar-tools-v0648737-type50-source-faithful-correction-v1"
SUMMARY = "call2_helium_solve_state_rate_matrix_decomposition_summary.json"
TARGET_RECORDS = (781, 917)
ANS_FIELDS = tuple(f"ans{i}" for i in range(1, 7))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def f(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, "nan"))
    except (TypeError, ValueError):
        return math.nan


def exact(a: float, b: float) -> bool:
    return math.isfinite(a) and math.isfinite(b) and a == b


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-replay", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    summary_path = args.output / SUMMARY
    base = json.loads(summary_path.read_text())
    gates = dict(base.get("gates", {}))
    source_rows = read_csv(args.source_capture / "v0472_call2_eval1_he_bound_free_records.csv")
    native_rows = read_csv(args.native_replay / "diagnostics/evaluation_0022_records.csv")
    term_rows = read_csv(args.output / "call2_he_source_order_term_comparison.csv")

    source = {int(float(r["record"])): r for r in source_rows if int(float(r.get("data_type", 0))) == 50}
    native = {int(float(r["record"])): r for r in native_rows if int(float(r.get("data_type", 0))) == 50}

    comparisons: list[dict[str, Any]] = []
    all_answers = True
    all_context = True
    exact_record_count = 0
    for record in sorted(source):
        sr = source[record]
        nr = native.get(record, {})
        row: dict[str, Any] = {"record": record, "source_present": True, "native_present": bool(nr)}
        record_answers = bool(nr)
        for name in ANS_FIELDS:
            sv = f(sr, name)
            nv = f(nr, name)
            ok = exact(sv, nv)
            row[f"source_{name}"] = sv
            row[f"native_{name}"] = nv
            row[f"{name}_exact"] = ok
            record_answers &= ok
        source_cfrac = f(sr, "diag_cfrac")
        native_cfrac = f(nr, "type50_covering_fraction")
        source_ptmp1 = f(sr, "diag_ptmp1")
        native_ptmp1 = f(nr, "type50_ptmp1")
        source_ptmp2 = f(sr, "diag_ptmp2")
        native_ptmp2 = f(nr, "type50_ptmp2")
        source_wave = f(sr, "diag_wavelength_A")
        native_wave = f(nr, "type50_stored_wavelength_a")
        context_exact = all((
            exact(source_cfrac, native_cfrac),
            exact(source_ptmp1, native_ptmp1),
            exact(source_ptmp2, native_ptmp2),
            exact(source_wave, native_wave),
        ))
        row.update({
            "source_covering_fraction": source_cfrac,
            "native_covering_fraction": native_cfrac,
            "covering_fraction_exact": exact(source_cfrac, native_cfrac),
            "source_ptmp1": source_ptmp1,
            "native_ptmp1": native_ptmp1,
            "ptmp1_exact": exact(source_ptmp1, native_ptmp1),
            "source_ptmp2": source_ptmp2,
            "native_ptmp2": native_ptmp2,
            "ptmp2_exact": exact(source_ptmp2, native_ptmp2),
            "source_stored_wavelength_a": source_wave,
            "native_stored_wavelength_a": native_wave,
            "stored_wavelength_exact": exact(source_wave, native_wave),
            "photoexcitation_zero_covering": nr.get("type50_photoexcitation_zero_covering") == "1",
            "used_dsec_covering": nr.get("type50_used_dsec_covering") == "1",
            "answers_exact": record_answers,
            "context_exact": context_exact,
        })
        if record_answers and context_exact:
            exact_record_count += 1
        all_answers &= record_answers
        all_context &= context_exact
        comparisons.append(row)
    write_csv(args.output / "call2_he_type50_record_comparison.csv", comparisons)

    terms = {(int(float(r["record"])), r["role"]): r for r in term_rows if int(float(r.get("data_type", 0))) == 50}
    r781_gain = terms.get((781, "forward_gain"), {})
    r781_diag = terms.get((781, "forward_diag_loss"), {})
    r917_gain = terms.get((917, "forward_gain"), {})
    r917_diag = terms.get((917, "forward_diag_loss"), {})
    record781_zero = (
        f(source.get(781, {}), "ans1") == 0.0
        and f(native.get(781, {}), "ans1") == 0.0
        and native.get(781, {}).get("type50_photoexcitation_zero_covering") == "1"
        and r781_gain.get("aj1_exact") == "True"
        and r781_diag.get("aj1_exact") == "True"
    )
    record917_forward_loss = (
        f(source.get(917, {}), "ans1") == 0.0
        and f(native.get(917, {}), "ans1") == 0.0
        and r917_gain.get("aj1_exact") == "True"
        and r917_diag.get("aj1_exact") == "True"
        and f(r917_diag, "source_aj1") == 0.0
        and f(r917_diag, "native_aj1") == 0.0
    )
    target_answers = all(
        next((row["answers_exact"] and row["context_exact"] for row in comparisons if row["record"] == rec), False)
        for rec in TARGET_RECORDS
    )

    matrix_exact = int(base.get("dense_matrix_exact_cells", 0))
    matrix_cells = int(base.get("matrix_cells", 6084))
    remaining = matrix_cells - matrix_exact
    type50_gate = gates.get("CALL2_HE_TYPE50_RATE_MATRIX")
    all_301 = len(source) == 301 and len(native) >= 301 and exact_record_count == 301
    gates.update({
        "CALL2_HE_TYPE50_TARGET_RECORD_CAPTURE": "ACCEPT" if all(r in source and r in native for r in TARGET_RECORDS) else "REJECT",
        "CALL2_HE_TYPE50_DSEC_COVERING_SEMANTICS": "ACCEPT" if all_context else "REJECT",
        "CALL2_HE_TYPE50_RECORD781_SOURCE_ZERO_RETURN": "ACCEPT" if record781_zero else "REJECT",
        "CALL2_HE_TYPE50_RECORD917_FORWARD_DIAGONAL_LOSS": "ACCEPT" if record917_forward_loss else "REJECT",
        "CALL2_HE_TYPE50_TARGET_ANS1_TO_ANS6_EXACT": "ACCEPT" if target_answers else "REJECT",
        "CALL2_HE_TYPE50_ALL_301_RECORD_ANSWERS_EXACT": "ACCEPT" if all_301 else "REJECT",
        "CALL2_HE_TYPE50_ROOT_CAUSE": "ACCEPT" if all_301 and record781_zero and record917_forward_loss else "REJECT",
        "CALL2_HE_TYPE50_RATE_MATRIX": "ACCEPT" if type50_gate == "ACCEPT" and all_301 else "REJECT",
        "CALL2_HE_FIXED_STATE_PARITY": f"BLOCKED_BY_{remaining}_MATRIX_CELLS" if remaining else "RUN_ALLOWED",
    })
    accepted = all((
        all_301,
        record781_zero,
        record917_forward_loss,
        target_answers,
        gates["CALL2_HE_TYPE50_RATE_MATRIX"] == "ACCEPT",
        matrix_exact == 5784,
        base.get("metadata_keyed_matched_terms") == 5232,
        base.get("unmatched_source_terms") == 0,
        base.get("unmatched_native_terms") == 0,
    ))
    report = {
        **base,
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if accepted else "REJECT",
        "physics_changed": True,
        "physics_change_scope": "Type-50 source DSEC covering/zero-photoexcitation semantics, post-swap ans1-ans6 signs, and records 781/917 forward matrix construction",
        "type50_target_records": list(TARGET_RECORDS),
        "type50_source_record_count": len(source),
        "type50_native_record_count": len(native),
        "type50_exact_record_count": exact_record_count,
        "type50_record781_zero_return_exact": record781_zero,
        "type50_record917_forward_diagonal_loss_exact": record917_forward_loss,
        "dense_matrix_exact_cells": matrix_exact,
        "remaining_incorrect_matrix_cells": remaining,
        "gates": gates,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if accepted else 2


if __name__ == "__main__":
    raise SystemExit(main())
