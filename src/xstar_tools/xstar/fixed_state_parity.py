"""Fixed-state parity qualification for XSTAR v0.6.48.7.11.

The module freezes the exact information that is actually available from the
v0.6.47.2 reference run and compares it with native source-order diagnostics.
It deliberately refuses to claim all-61 ion/level parity when the reference
bundle does not contain those per-evaluation vectors.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "xstar-tools-v06487-fixed-state-parity-v1"
ORACLE_SCHEMA = "xstar-tools-v06487-fixed-state-oracle-v1"

ION_LABELS: dict[int, list[str]] = {
    1: ["H I", "H II"],
    2: ["He I", "He II", "He III"],
    12: [
        "Mg I", "Mg II", "Mg III", "Mg IV", "Mg V", "Mg VI", "Mg VII",
        "Mg VIII", "Mg IX", "Mg X", "Mg XI", "Mg XII", "Mg XIII",
    ],
}
ROMAN_STAGE = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
    "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11,
    "xii": 12, "xiii": 13,
}
ELEMENT_INDEX_TO_Z = {0: 1, 1: 2, 2: 12}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})
    os.replace(tmp, path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _float(value: Any) -> float:
    if value is None or value == "":
        return math.nan
    return float(value)


def _same_ieee(a: float, b: float) -> bool:
    import struct
    return struct.pack(">d", float(a)) == struct.pack(">d", float(b))


def _ion_column_name(z: int, stage: int) -> str | None:
    prefix = {1: "h", 2: "he", 12: "mg"}[z]
    roman = next((name for name, number in ROMAN_STAGE.items() if number == stage), None)
    return None if roman is None else f"{prefix}_{roman}"


def build_oracle(reference_dir: Path, program_rows_csv: Path, output_dir: Path) -> dict[str, Any]:
    """Build the frozen v0.6.47.2 fixed-state oracle.

    The trajectory supplies all 61 exact electron-fraction and charge-residual
    values.  The historical FITS files supply four accepted ion states and the
    final detailed level vector.  The latter is mapped to the native source-order
    row basis by (element Z, ion charge, excitation energy, stable source order).
    """
    reference_dir = reference_dir.resolve()
    program_rows_csv = program_rows_csv.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    from astropy.io import fits

    trajectory = _read_csv(reference_dir / "trajectory.csv")
    state_rows: list[dict[str, Any]] = []
    for row in trajectory:
        trial = float(row["electron_fraction"])
        residual = float(row["elcter"])
        state_rows.append({
            "evaluation_ordinal": int(row["sequence"]),
            "kind": row["kind"],
            "call_index": int(row["call_index"]),
            "evaluation_index": int(row["evaluation_index"]),
            "temperature_t4": float(row["temperature_t4"]),
            "electron_fraction_input": trial,
            "reference_charge_residual": residual,
            "reference_computed_electron_fraction": trial - residual,
            "reference_hmctot": float(row["hmctot"]),
            "reference_lnerr": int(row["lnerr"]),
        })
    state_fields = list(state_rows[0])
    _write_csv(output_dir / "trajectory_state_oracle.csv", state_rows, state_fields)

    with fits.open(reference_dir / "xout_abund1.fits", memmap=False) as hdul:
        abund = hdul[1].data
        accepted_indices = [i for i in range(len(abund)) if float(abund["temperature"][i]) > 0.0]
        accepted_evaluations = [int(row["sequence"]) for row in trajectory if row["kind"] == "final"]
        if len(accepted_indices) != len(accepted_evaluations):
            raise ValueError("accepted FITS rows do not match final trajectory evaluations")
        ion_rows: list[dict[str, Any]] = []
        for state_ordinal, (row_index, evaluation_ordinal) in enumerate(zip(accepted_indices, accepted_evaluations), 1):
            for z in (1, 2, 12):
                values: list[float] = []
                for stage in range(1, z + 1):
                    column = _ion_column_name(z, stage)
                    values.append(float(abund[column][row_index]) if column in abund.dtype.names else 0.0)
                values.append(max(0.0, 1.0 - sum(values)))
                for stage, value in enumerate(values, 1):
                    ion_rows.append({
                        "accepted_state_ordinal": state_ordinal,
                        "reference_evaluation_ordinal": evaluation_ordinal,
                        "reference_fits_row": row_index,
                        "temperature_t4": float(abund["temperature"][row_index]),
                        "reference_electron_fraction": float(abund["x_e"][row_index]),
                        "element_z": z,
                        "stage": stage,
                        "ion_charge": stage - 1,
                        "ion_label": ION_LABELS[z][stage - 1],
                        "reference_fraction": value,
                    })
    ion_fields = list(ion_rows[0])
    _write_csv(output_dir / "accepted_ion_populations.csv", ion_rows, ion_fields)

    native_rows_raw = _read_csv(program_rows_csv)
    native_rows: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for global_index, row in enumerate(native_rows_raw, 1):
        z = ELEMENT_INDEX_TO_Z[int(row["element_index"])]
        key = (z, int(row["ion_charge"]))
        native_rows.setdefault(key, []).append({
            "global_population_row": global_index,
            "element_z": z,
            "ion_charge": int(row["ion_charge"]),
            "element_row": int(row["row"]),
            "energy_ev": float(row["energy_ev"]),
        })

    level_rows: list[dict[str, Any]] = []
    with fits.open(reference_dir / "xo01_detail.fits", memmap=False) as hdul:
        # HDU 5 corresponds to the fourth/final accepted state. HDU 6 repeats it.
        detail_hdu = 5 if len(hdul) > 5 else len(hdul) - 1
        detail = hdul[detail_hdu].data
        used: set[int] = set()
        for ref_index in range(len(detail)):
            z = int(detail["atomic_number"][ref_index])
            label = str(detail["ion"][ref_index]).strip().lower()
            roman = label.split("_")[-1]
            charge = ROMAN_STAGE[roman] - 1
            energy = float(detail["e_excitation"][ref_index])
            candidates = [r for r in native_rows.get((z, charge), []) if r["global_population_row"] not in used]
            if candidates:
                selected = min(candidates, key=lambda r: (abs(r["energy_ev"] - energy), r["global_population_row"]))
                used.add(selected["global_population_row"])
                global_row: int | str = selected["global_population_row"]
                element_row: int | str = selected["element_row"]
                native_energy: float | str = selected["energy_ev"]
                energy_delta: float | str = selected["energy_ev"] - energy
                status = "mapped"
            else:
                global_row = ""
                element_row = ""
                native_energy = ""
                energy_delta = ""
                status = "unmapped_reference_continuum_or_missing_row"
            level_rows.append({
                "accepted_state_ordinal": 4,
                "reference_evaluation_ordinal": accepted_evaluations[-1],
                "reference_detail_hdu": detail_hdu,
                "reference_detail_index": int(detail["index"][ref_index]),
                "global_population_row": global_row,
                "element_z": z,
                "ion_charge": charge,
                "ion_label": str(detail["ion"][ref_index]).strip(),
                "ion_level": str(detail["ion_level"][ref_index]).strip(),
                "reference_energy_ev": energy,
                "native_energy_ev": native_energy,
                "energy_delta_ev": energy_delta,
                "reference_population": float(detail["population"][ref_index]),
                "reference_lte_population": float(detail["lte"][ref_index]),
                "mapping_status": status,
            })
    level_fields = list(level_rows[0])
    _write_csv(output_dir / "final_level_populations.csv", level_rows, level_fields)

    mapped = sum(row["mapping_status"] == "mapped" for row in level_rows)
    files = []
    for name in ("trajectory_state_oracle.csv", "accepted_ion_populations.csv", "final_level_populations.csv"):
        path = output_dir / name
        files.append({"path": name, "size_bytes": path.stat().st_size, "sha256": _sha256(path)})
    manifest = {
        "schema": ORACLE_SCHEMA,
        "immutable": True,
        "source_release": "0.6.47.2",
        "reference_bundle": reference_dir.name,
        "reference_manifest_sha256": _sha256(reference_dir / "reference_manifest.json"),
        "program_rows_sha256": _sha256(program_rows_csv),
        "trajectory_state_count": len(state_rows),
        "accepted_ion_state_count": len(accepted_indices),
        "final_level_reference_rows": len(level_rows),
        "final_level_mapped_rows": mapped,
        "final_level_unmapped_rows": len(level_rows) - mapped,
        "all_61_electron_fraction_oracle": len(state_rows) == 61,
        "all_61_ion_population_oracle": False,
        "all_61_level_population_oracle": False,
        "files": files,
        "production_promotion_ready": False,
    }
    _write_json(output_dir / "oracle_manifest.json", manifest)
    return manifest


def verify_oracle(oracle_dir: Path) -> dict[str, Any]:
    oracle_dir = oracle_dir.resolve()
    manifest = json.loads((oracle_dir / "oracle_manifest.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("schema") != ORACLE_SCHEMA:
        errors.append("unexpected oracle schema")
    if manifest.get("immutable") is not True:
        errors.append("oracle is not immutable")
    verified = 0
    for item in manifest.get("files", []):
        path = oracle_dir / item["path"]
        if not path.is_file():
            errors.append(f"missing {item['path']}")
            continue
        if path.stat().st_size != item["size_bytes"]:
            errors.append(f"size mismatch {item['path']}")
        elif _sha256(path) != item["sha256"]:
            errors.append(f"hash mismatch {item['path']}")
        else:
            verified += 1
    return {
        "schema": ORACLE_SCHEMA,
        "oracle_directory": str(oracle_dir),
        "files_expected": len(manifest.get("files", [])),
        "files_verified": verified,
        "errors": errors,
        "result": "ACCEPT" if not errors else "REJECT",
        "production_promotion_ready": False,
    }


def compare_fixed_state(
    oracle_dir: Path,
    qualification_output: Path,
    output_dir: Path,
    *,
    final_evaluation: int = 61,
    max_reported: int = 200,
) -> dict[str, Any]:
    oracle_dir = oracle_dir.resolve()
    qualification_output = qualification_output.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    diagnostics = qualification_output / "qualification_diagnostics"
    reference_input = qualification_output / "reference_input"
    trajectory_path = reference_input / "native_trajectory.csv"
    summary_path = reference_input / "native_trajectory_summary.json"
    if not diagnostics.is_dir() or not trajectory_path.is_file():
        raise FileNotFoundError(
            "qualification output must contain qualification_diagnostics "
            "and reference_input/native_trajectory.csv"
        )

    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    python_callbacks = int(summary.get("python_callbacks", -1))

    reference_states = {
        int(row["evaluation_ordinal"]): row
        for row in _read_csv(oracle_dir / "trajectory_state_oracle.csv")
    }
    native_states = {int(row["sequence"]): row for row in _read_csv(trajectory_path)}
    state_diffs: list[dict[str, Any]] = []
    electron_exact = True
    charge_exact = True
    max_xe_delta = 0.0
    max_charge_delta = 0.0
    for ordinal in sorted(reference_states):
        reference = reference_states[ordinal]
        native = native_states.get(ordinal)
        if native is None:
            electron_exact = False
            charge_exact = False
            state_diffs.append({
                "evaluation_ordinal": ordinal,
                "quantity": "missing_native_state",
                "reference": "present",
                "native": "missing",
                "absolute_delta": "",
                "ieee_exact": False,
            })
            continue
        pairs = [
            (
                "computed_electron_fraction",
                float(reference["reference_computed_electron_fraction"]),
                float(native["native_electron_fraction"]),
            ),
            (
                "charge_residual",
                float(reference["reference_charge_residual"]),
                float(native["native_charge_residual"]),
            ),
        ]
        for quantity, ref_value, native_value in pairs:
            delta = native_value - ref_value
            exact = _same_ieee(ref_value, native_value)
            if quantity == "computed_electron_fraction":
                electron_exact = electron_exact and exact
                max_xe_delta = max(max_xe_delta, abs(delta))
            else:
                charge_exact = charge_exact and exact
                max_charge_delta = max(max_charge_delta, abs(delta))
            if not exact:
                state_diffs.append({
                    "evaluation_ordinal": ordinal,
                    "quantity": quantity,
                    "reference": format(ref_value, ".17g"),
                    "native": format(native_value, ".17g"),
                    "absolute_delta": format(abs(delta), ".17g"),
                    "ieee_exact": False,
                })
    _write_csv(
        output_dir / "state_differences.csv",
        state_diffs,
        ["evaluation_ordinal", "quantity", "reference", "native", "absolute_delta", "ieee_exact"],
    )

    reference_ions = _read_csv(oracle_dir / "accepted_ion_populations.csv")
    ion_diffs: list[dict[str, Any]] = []
    accepted_ion_exact = True
    final_ion_exact = True
    max_ion_delta = 0.0
    max_final_ion_delta = 0.0
    accepted_evaluations = sorted({int(row["reference_evaluation_ordinal"]) for row in reference_ions})
    for evaluation_ordinal in accepted_evaluations:
        path = diagnostics / f"evaluation_{evaluation_ordinal:04d}_ion_balance.csv"
        native_ions = {
            (int(row["element_z"]), int(row["stage"])): row
            for row in _read_csv(path)
        } if path.is_file() else {}
        for reference in reference_ions:
            if int(reference["reference_evaluation_ordinal"]) != evaluation_ordinal:
                continue
            key = (int(reference["element_z"]), int(reference["stage"]))
            native = native_ions.get(key)
            ref_value = float(reference["reference_fraction"])
            native_value = math.nan if native is None else float(native["final_fraction"])
            delta = native_value - ref_value
            exact = native is not None and _same_ieee(ref_value, native_value)
            accepted_ion_exact = accepted_ion_exact and exact
            if evaluation_ordinal == final_evaluation:
                final_ion_exact = final_ion_exact and exact
            magnitude = abs(delta) if math.isfinite(delta) else math.inf
            max_ion_delta = max(max_ion_delta, magnitude)
            if evaluation_ordinal == final_evaluation:
                max_final_ion_delta = max(max_final_ion_delta, magnitude)
            if not exact:
                ion_diffs.append({
                    "accepted_state_ordinal": int(reference["accepted_state_ordinal"]),
                    "evaluation_ordinal": evaluation_ordinal,
                    "element_z": key[0],
                    "stage": key[1],
                    "ion_label": reference["ion_label"],
                    "reference_fraction": format(ref_value, ".17g"),
                    "native_fraction": "" if native is None else format(native_value, ".17g"),
                    "absolute_delta": "" if not math.isfinite(delta) else format(abs(delta), ".17g"),
                    "ieee_exact": exact,
                })
    ion_diffs.sort(key=lambda row: float(row["absolute_delta"] or "inf"), reverse=True)
    _write_csv(
        output_dir / "accepted_ion_differences.csv",
        ion_diffs,
        [
            "accepted_state_ordinal", "evaluation_ordinal", "element_z", "stage", "ion_label",
            "reference_fraction", "native_fraction", "absolute_delta", "ieee_exact",
        ],
    )
    # Compatibility filename retained for downstream scripts; contains final-state rows only.
    final_ion_diffs = [row for row in ion_diffs if int(row["evaluation_ordinal"]) == final_evaluation]
    _write_csv(
        output_dir / "final_ion_differences.csv",
        final_ion_diffs,
        [
            "accepted_state_ordinal", "evaluation_ordinal", "element_z", "stage", "ion_label",
            "reference_fraction", "native_fraction", "absolute_delta", "ieee_exact",
        ],
    )

    reference_levels = [
        row for row in _read_csv(oracle_dir / "final_level_populations.csv")
        if row["mapping_status"] == "mapped"
    ]
    final_level_evaluation = int(reference_levels[0].get("reference_evaluation_ordinal", final_evaluation))
    level_path = diagnostics / f"evaluation_{final_level_evaluation:04d}_populations.csv"
    native_levels = {
        int(row["global_population_row"]): row
        for row in _read_csv(level_path)
    } if level_path.is_file() else {}
    level_diffs: list[dict[str, Any]] = []
    level_exact = True
    max_level_delta = 0.0
    for reference in reference_levels:
        global_row = int(reference["global_population_row"])
        native = native_levels.get(global_row)
        ref_value = float(reference["reference_population"])
        native_value = math.nan if native is None else float(native["final_population"])
        delta = native_value - ref_value
        exact = native is not None and _same_ieee(ref_value, native_value)
        level_exact = level_exact and exact
        max_level_delta = max(max_level_delta, abs(delta) if math.isfinite(delta) else math.inf)
        if not exact:
            level_diffs.append({
                "evaluation_ordinal": final_level_evaluation,
                "global_population_row": global_row,
                "element_z": int(reference["element_z"]),
                "ion_charge": int(reference["ion_charge"]),
                "ion_label": reference["ion_label"],
                "ion_level": reference["ion_level"],
                "reference_population": format(ref_value, ".17g"),
                "native_population": "" if native is None else format(native_value, ".17g"),
                "absolute_delta": "" if not math.isfinite(delta) else format(abs(delta), ".17g"),
                "ieee_exact": exact,
            })
    level_diffs.sort(key=lambda row: float(row["absolute_delta"] or "inf"), reverse=True)
    _write_csv(
        output_dir / "final_level_differences.csv",
        level_diffs,
        [
            "evaluation_ordinal", "global_population_row", "element_z", "ion_charge", "ion_label",
            "ion_level", "reference_population", "native_population", "absolute_delta", "ieee_exact",
        ],
    )

    all_61_electron_exact = (
        electron_exact and len(reference_states) == 61 and len(native_states) == 61
    )
    all_61_charge_exact = charge_exact and len(reference_states) == 61 and len(native_states) == 61
    all_61_ion_oracle = False
    all_61_level_oracle = False
    exact_ions_all_61 = False
    exact_levels_all_61 = False
    fixed_state_parity = (
        python_callbacks == 0
        and all_61_electron_exact
        and all_61_charge_exact
        and all_61_ion_oracle
        and all_61_level_oracle
        and exact_ions_all_61
        and exact_levels_all_61
    )

    blockers: list[str] = []
    if python_callbacks != 0:
        blockers.append("native trajectory summary does not report zero Python callbacks")
    if not all_61_ion_oracle:
        blockers.append("all 61 reference ion-population vectors are not present in the frozen v0.6.47.2 artifacts")
    if not all_61_level_oracle:
        blockers.append("all 61 reference level-population vectors are not present in the frozen v0.6.47.2 artifacts")
    if not all_61_electron_exact:
        blockers.append("native computed electron fraction does not match all 61 reference-input states")
    if not all_61_charge_exact:
        blockers.append("native charge residual does not match all 61 reference-input states")
    if not accepted_ion_exact:
        blockers.append("native H/He/Mg ion populations do not match all four accepted reference states")
    if not level_exact:
        blockers.append("native final mapped level populations do not match the accepted reference state")

    report = {
        "schema": SCHEMA,
        "oracle_directory": str(oracle_dir),
        "qualification_output": str(qualification_output),
        "output_directory": str(output_dir),
        "reference_evaluations": len(reference_states),
        "native_evaluations": len(native_states),
        "python_callbacks": python_callbacks,
        "all_61_electron_fraction_exact": all_61_electron_exact,
        "all_61_charge_residual_exact": all_61_charge_exact,
        "max_abs_electron_fraction_delta": max_xe_delta,
        "max_abs_charge_residual_delta": max_charge_delta,
        "accepted_ion_states_compared": len(accepted_evaluations),
        "accepted_ion_evaluations": accepted_evaluations,
        "accepted_ion_population_exact": accepted_ion_exact,
        "max_abs_accepted_ion_population_delta": max_ion_delta,
        "final_ion_population_exact": final_ion_exact,
        "max_abs_final_ion_population_delta": max_final_ion_delta,
        "final_level_evaluation": final_level_evaluation,
        "final_level_population_exact": level_exact,
        "mapped_final_level_rows_compared": len(reference_levels),
        "max_abs_final_level_population_delta": max_level_delta,
        "all_61_ion_population_oracle_available": all_61_ion_oracle,
        "all_61_level_population_oracle_available": all_61_level_oracle,
        "exact_h_he_mg_ion_populations_all_61": exact_ions_all_61,
        "exact_level_populations_all_61": exact_levels_all_61,
        "fixed_state_parity": fixed_state_parity,
        "result": "ACCEPT" if fixed_state_parity else "REJECT",
        "production_promotion_ready": False,
        "blockers": blockers,
        "differences_reported": {
            "state": min(len(state_diffs), max_reported),
            "accepted_ion": min(len(ion_diffs), max_reported),
            "final_ion": min(len(final_ion_diffs), max_reported),
            "level": min(len(level_diffs), max_reported),
        },
    }
    _write_json(output_dir / "fixed_state_parity_report.json", report)
    return report

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-oracle")
    build.add_argument("reference_dir", type=Path)
    build.add_argument("program_rows_csv", type=Path)
    build.add_argument("output_dir", type=Path)
    build.add_argument("--output-json", type=Path)
    verify = sub.add_parser("verify-oracle")
    verify.add_argument("oracle_dir", type=Path)
    verify.add_argument("--output-json", type=Path)
    compare = sub.add_parser("compare")
    compare.add_argument("oracle_dir", type=Path)
    compare.add_argument("qualification_output", type=Path)
    compare.add_argument("output_dir", type=Path)
    compare.add_argument("--final-evaluation", type=int, default=61)
    compare.add_argument("--output-json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build-oracle":
        result = build_oracle(args.reference_dir, args.program_rows_csv, args.output_dir)
        exit_status = 0
    elif args.command == "verify-oracle":
        result = verify_oracle(args.oracle_dir)
        exit_status = 0 if result.get("result") == "ACCEPT" else 1
    else:
        result = compare_fixed_state(
            args.oracle_dir, args.qualification_output, args.output_dir,
            final_evaluation=args.final_evaluation,
        )
        exit_status = 0 if result.get("result") == "ACCEPT" else 1
    if getattr(args, "output_json", None):
        target = args.output_json.resolve()
        _write_json(target, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
