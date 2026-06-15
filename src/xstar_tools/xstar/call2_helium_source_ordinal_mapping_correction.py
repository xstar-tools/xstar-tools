"""v0.6.48.7.30.4 complete He II source-ordinal mapping correction audit."""
from __future__ import annotations

import argparse
import csv
import json
import math
import struct
from pathlib import Path

RELEASE = "0.6.48.7.30.4"
SCHEMA = "xstar-tools-v06487304-complete-heii-source-ordinal-mapping-correction-v1"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str, default: float = math.nan) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def integer(row: dict[str, str], key: str, default: int = 0) -> int:
    try:
        return int(float(row.get(key, default)))
    except (TypeError, ValueError):
        return default


def read_f64_vector(path: Path) -> list[float]:
    payload = path.read_bytes()
    if len(payload) % 8:
        raise ValueError(f"invalid float64 payload size: {path}")
    return list(struct.unpack(f"={len(payload) // 8}d", payload))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-replay", type=Path, required=True)
    parser.add_argument("--call-start-workspace-dir", type=Path, required=True)
    parser.add_argument("--prior-summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    source_rows = read_csv(args.source_capture / "v0472_call2_eval1_he_populations.csv")
    population_rows = read_csv(args.native_replay / "diagnostics/evaluation_0022_populations.csv")
    solve_rows = read_csv(args.native_replay / "diagnostics/evaluation_0022_helium_solve_rows.csv")
    call_start = read_f64_vector(args.call_start_workspace_dir / "call_2_global_xilevg.bin")

    native_he = [row for row in population_rows if integer(row, "element_z") == 2]
    source_by_row = {integer(row, "element_row"): row for row in source_rows}
    native_by_row = {integer(row, "element_row"): row for row in native_he}
    solve_by_row = {integer(row, "full_row"): row for row in solve_rows}

    ledger: list[dict[str, object]] = []
    for element_row in sorted(source_by_row):
        source = source_by_row[element_row]
        native = native_by_row.get(element_row, {})
        solve = solve_by_row.get(element_row, {})
        expected_global = 33 + element_row
        population_global = integer(native, "global_population_row")
        loaded_global = integer(solve, "loaded_global_level_index")
        source_seed = call_start[expected_global - 1] if 0 < expected_global <= len(call_start) else math.nan
        loaded_seed = number(solve, "loaded_call_start_xilevg")
        source_post = number(source, "population_after_solve")
        native_post = number(solve, "final_population", number(native, "final_population"))
        ledger.append({
            "element_row": element_row,
            "ion": integer(native, "ion"),
            "compact_row": integer(solve, "compact_row"),
            "expected_source_global_level_index": expected_global,
            "native_population_global_row": population_global,
            "native_loaded_global_level_index": loaded_global,
            "population_ledger_ordinal_exact": population_global == expected_global,
            "mapping_exact": loaded_global == expected_global,
            "source_call_start_xilevg": source_seed,
            "native_loaded_call_start_xilevg": loaded_seed,
            "seed_transport_exact": math.isfinite(source_seed) and loaded_seed == source_seed,
            "source_post_solve_population": source_post,
            "native_post_solve_population": native_post,
            "post_solve_exact": math.isfinite(source_post) and native_post == source_post,
            "normalization_row": integer(solve, "is_normalization_row"),
        })

    ledger_path = args.output / "call2_he_source_ordinal_mapping_ledger.csv"
    write_csv(ledger_path, ledger)

    prior = json.loads(args.prior_summary.read_text())
    prior_gates = prior.get("gates", {})
    baseline = (
        prior.get("result") == "ACCEPT"
        and prior_gates.get("CALL2_HE_CALL_START_SEED_PHASE") == "ACCEPT"
        and prior_gates.get("CALL2_HE_SEED_TRANSPORT_LEDGER") == "ACCEPT"
    )
    row_ledger = len(ledger) == 78
    population_ordinals = row_ledger and all(bool(row["population_ledger_ordinal_exact"]) for row in ledger)
    mapping = row_ledger and all(bool(row["mapping_exact"]) for row in ledger)
    seed = row_ledger and all(bool(row["seed_transport_exact"]) for row in ledger)
    he_i = row_ledger and all(
        row["native_loaded_global_level_index"] == 33 + row["element_row"]
        for row in ledger if int(row["element_row"]) <= 45
    )
    he_ii = row_ledger and all(
        row["native_loaded_global_level_index"] == 33 + row["element_row"]
        for row in ledger if int(row["element_row"]) >= 46
    )
    boundary = row_ledger and ledger[45]["native_loaded_global_level_index"] == 79
    normalization = (
        row_ledger
        and ledger[-1]["expected_source_global_level_index"] == 111
        and ledger[-1]["native_loaded_global_level_index"] == 111
        and int(ledger[-1]["normalization_row"]) == 1
    )
    post_solve = row_ledger and all(bool(row["post_solve_exact"]) for row in ledger)
    initialization = mapping and seed

    gates = {
        "CALL1_ACCEPTED_BASELINE": "ACCEPT" if baseline else "REJECT",
        "CALL2_HE_78_ROW_LEDGER": "ACCEPT" if row_ledger else "REJECT",
        "CALL2_HE_78_ROW_MAPPING_EXACT": "ACCEPT" if mapping else "REJECT",
        "CALL2_HE_78_ROW_MAPPING": "ACCEPT" if mapping else "REJECT",
        "CALL2_HE_POPULATION_LEDGER_ORDINALS": "ACCEPT" if population_ordinals else "REJECT",
        "CALL2_HE_I_GLOBAL_LEVEL_MAPPING": "ACCEPT" if he_i else "REJECT",
        "CALL2_HE_II_GLOBAL_LEVEL_MAPPING": "ACCEPT" if he_ii else "REJECT",
        "CALL2_HE_BOUNDARY_ROW_GLOBAL_LEVEL_79": "ACCEPT" if boundary else "REJECT",
        "CALL2_HE_NORMALIZATION_ROW_GLOBAL_LEVEL_111": "ACCEPT" if normalization else "REJECT",
        "CALL2_HE_GLOBAL_XILEVG_MAPPING": "ACCEPT" if mapping else "REJECT",
        "CALL2_HE_SEED_TRANSPORT_EXACT": "ACCEPT" if seed else "REJECT",
        "CALL2_HE_GENUINE_NATIVE_INITIALIZATION_CORRECTION": "ACCEPT" if initialization else "REJECT",
        "CALL2_HE_POST_SOLVE_POPULATION_EXACT": "ACCEPT" if post_solve else "REJECT",
        "CALL2_HE_RATE_EVALUATION": "RUN_ALLOWED" if initialization else "BLOCKED_BY_SEED_TRANSPORT",
        "CALL2_HE_MATRIX_THERMAL_ACCUMULATION": "RUN_ALLOWED" if initialization else "BLOCKED_BY_SEED_TRANSPORT",
        "CALL2_GENERAL_HE_THERMAL": "RUN_ALLOWED" if initialization else "BLOCKED_BY_SEED_TRANSPORT",
        "CALLS_3_TO_4": "BLOCKED_BY_CALL2_HELIUM",
        "THERMAL_PARITY": "BLOCKED",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    }
    core = baseline and row_ledger and population_ordinals and mapping and seed and he_i and he_ii and boundary and normalization
    report = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if core else "REJECT",
        "rows": len(ledger),
        "mapping_exact_rows": sum(bool(row["mapping_exact"]) for row in ledger),
        "seed_transport_exact_rows": sum(bool(row["seed_transport_exact"]) for row in ledger),
        "post_solve_exact_rows": sum(bool(row["post_solve_exact"]) for row in ledger),
        "gates": gates,
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    summary_path = args.output / "call2_helium_source_ordinal_mapping_correction_summary.json"
    summary_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if core else 2


if __name__ == "__main__":
    raise SystemExit(main())
