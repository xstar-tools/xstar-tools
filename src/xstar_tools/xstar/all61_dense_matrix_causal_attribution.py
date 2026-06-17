"""All-61 dense-matrix causal record attribution for v0.6.48.7.46.9.

The audit consumes exact source and native matrix-contribution streams.  Each
stream stores one compact row per committed atomic record and all four matrix
terms produced by that record.  The module first requires each stream to
reconstruct its captured dense/heating matrices bit-for-bit; only then does it
attribute every differing dense-matrix cell to rate-value, endpoint/orientation,
presence, or accumulation-order causes.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

RELEASE = "0.6.48.7.46.9"
SCHEMA = "xstar-tools-v06487469-all61-dense-matrix-causal-attribution-v1"
SUMMARY_NAME = "all61_dense_matrix_causal_attribution_summary.json"
CELL_NAME = "all61_dense_matrix_causal_cells.csv"
RECORD_NAME = "all61_dense_matrix_causal_records.csv"
SYSTEM_NAME = "all61_matrix_contribution_systems.csv"
SOURCE_MANIFEST = "v0472_all61_solve_system_manifest.csv"
INT_COLUMNS = 14
REAL_COLUMNS = 16
ROLE_NAMES = (
    "forward_offdiag",
    "reverse_offdiag",
    "forward_diag_loss",
    "reverse_diag_loss",
)
INT_FIELDS = (
    "source_order_index",
    "source_position",
    "record",
    "data_type",
    "rate_type",
    "ion_index",
    "ion_stage",
    "lower_row",
    "upper_row",
    "source_ipmat_clamped",
    "idest1",
    "idest2",
    "lower_endpoint",
    "upper_endpoint",
)


@dataclass(frozen=True)
class Contribution:
    ints: tuple[int, ...]
    reals: tuple[float, ...]

    @property
    def order(self) -> int:
        return self.ints[0]

    @property
    def source_position(self) -> int:
        return self.ints[1]

    @property
    def record(self) -> int:
        return self.ints[2]

    @property
    def data_type(self) -> int:
        return self.ints[3]

    @property
    def rate_type(self) -> int:
        return self.ints[4]

    @property
    def ion_index(self) -> int:
        return self.ints[5]

    @property
    def ion_stage(self) -> int:
        return self.ints[6]

    @property
    def lower(self) -> int:
        return self.ints[7]

    @property
    def upper(self) -> int:
        return self.ints[8]

    @property
    def identity(self) -> tuple[int, int, int, int, int]:
        return (self.record, self.data_type, self.rate_type, self.ion_index, self.ion_stage)

    def cell(self, role_index: int) -> tuple[int, int]:
        if role_index == 0:
            return self.upper, self.lower
        if role_index == 1:
            return self.lower, self.upper
        if role_index == 2:
            return self.lower, self.lower
        if role_index == 3:
            return self.upper, self.upper
        raise IndexError(role_index)

    def term(self, role_index: int) -> tuple[float, float, float, float]:
        start = role_index * 4
        return self.reals[start : start + 4]  # type: ignore[return-value]


@dataclass
class SystemData:
    sequence: int
    element_z: int
    n_rows: int
    dense: np.ndarray
    heat: np.ndarray
    heat2: np.ndarray
    contributions: list[Contribution]
    manifest: dict[str, str]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _native_manifests(native_run: Path) -> dict[tuple[int, int], dict[str, str]]:
    root = native_run / "qualification_diagnostics"
    out: dict[tuple[int, int], dict[str, str]] = {}
    for path in sorted(root.glob("evaluation_*_all_element_solve_system_manifest.csv")):
        rows = _read_csv(path)
        for row in rows:
            key = (int(row["evaluation_ordinal"]), int(row["element_z"]))
            if key in out:
                raise ValueError(f"duplicate native contribution system {key}")
            row = dict(row)
            row["_manifest_root"] = str(root)
            out[key] = row
    return out


def _source_manifests(source_capture: Path) -> dict[tuple[int, int], dict[str, str]]:
    rows = _read_csv(source_capture / SOURCE_MANIFEST)
    out: dict[tuple[int, int], dict[str, str]] = {}
    for row in rows:
        key = (int(row["sequence"]), int(row["element_z"]))
        if key in out:
            raise ValueError(f"duplicate source contribution system {key}")
        row = dict(row)
        row["_manifest_root"] = str(source_capture)
        out[key] = row
    return out


def _resolve(row: Mapping[str, str], field: str) -> Path:
    return Path(row["_manifest_root"]) / row[field]


def _load_system(row: dict[str, str], *, source: bool) -> SystemData:
    sequence = int(row["sequence"] if source else row["evaluation_ordinal"])
    element_z = int(row["element_z"])
    n = int(row["n_rows"])
    dense = np.fromfile(_resolve(row, "dense_matrix_path"), dtype=np.float64)
    heat = np.fromfile(_resolve(row, "heating_matrix_path"), dtype=np.float64)
    heat2 = np.fromfile(_resolve(row, "heating_matrix2_path"), dtype=np.float64)
    if dense.size != n * n or heat.size != n * n or heat2.size != n * n:
        raise ValueError(f"matrix size mismatch sequence={sequence} z={element_z}")
    int_rows = int(row["matrix_contribution_int_rows"])
    int_columns = int(row["matrix_contribution_int_columns"])
    real_rows = int(row["matrix_contribution_real_rows"])
    real_columns = int(row["matrix_contribution_real_columns"])
    if int_rows != real_rows or int_columns != INT_COLUMNS or real_columns != REAL_COLUMNS:
        raise ValueError(
            f"contribution shape mismatch sequence={sequence} z={element_z}: "
            f"ints={int_rows}x{int_columns} reals={real_rows}x{real_columns}"
        )
    ints = np.fromfile(_resolve(row, "matrix_contribution_ints_path"), dtype=np.int64)
    reals = np.fromfile(_resolve(row, "matrix_contribution_reals_path"), dtype=np.float64)
    if ints.size != int_rows * int_columns or reals.size != real_rows * real_columns:
        raise ValueError(f"contribution binary size mismatch sequence={sequence} z={element_z}")
    ints = ints.reshape(int_rows, int_columns)
    reals = reals.reshape(real_rows, real_columns)
    contributions = [
        Contribution(tuple(int(v) for v in ints[index]), tuple(float(v) for v in reals[index]))
        for index in range(int_rows)
    ]
    expected_order = list(range(1, int_rows + 1))
    actual_order = [c.order for c in contributions]
    if actual_order != expected_order:
        raise ValueError(f"noncanonical contribution order sequence={sequence} z={element_z}")
    return SystemData(
        sequence=sequence,
        element_z=element_z,
        n_rows=n,
        dense=dense.reshape(n, n),
        heat=heat.reshape(n, n),
        heat2=heat2.reshape(n, n),
        contributions=contributions,
        manifest=row,
    )


def _reconstruct(system: SystemData) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dense = np.zeros((system.n_rows, system.n_rows), dtype=np.float64)
    heat = np.zeros_like(dense)
    heat2 = np.zeros_like(dense)
    for contribution in system.contributions:
        for role_index in range(4):
            row, column = contribution.cell(role_index)
            if row < 1 or row > system.n_rows or column < 1 or column > system.n_rows:
                raise ValueError(
                    f"contribution cell outside basis sequence={system.sequence} z={system.element_z} "
                    f"record={contribution.record} role={ROLE_NAMES[role_index]} cell={row},{column}"
                )
            aj1, _aj2, cj, cj2 = contribution.term(role_index)
            dense[row - 1, column - 1] += aj1
            heat[row - 1, column - 1] += cj
            heat2[row - 1, column - 1] += cj2
    return dense, heat, heat2


def _record_maps(contributions: list[Contribution]) -> dict[tuple[int, int, int, int, int], Contribution]:
    out: dict[tuple[int, int, int, int, int], Contribution] = {}
    for contribution in contributions:
        if contribution.identity in out:
            raise ValueError(f"duplicate record identity {contribution.identity}")
        out[contribution.identity] = contribution
    return out


def _value_for_cell(contribution: Contribution | None, role_index: int, row: int, column: int) -> float:
    if contribution is None or contribution.cell(role_index) != (row, column):
        return 0.0
    return contribution.term(role_index)[0]


def _classify_record(source: Contribution | None, native: Contribution | None) -> str:
    if source is None:
        return "NATIVE_ONLY_RECORD"
    if native is None:
        return "SOURCE_ONLY_RECORD"
    if (source.lower, source.upper) != (native.lower, native.upper):
        return "ENDPOINT_ORIENTATION_DELTA"
    if source.reals != native.reals:
        return "RATE_VALUE_DELTA"
    if source.order != native.order:
        return "ACCUMULATION_ORDER_DELTA"
    return "EXACT_RECORD"


def _term_sequence_for_cell(system: SystemData, row: int, column: int) -> list[tuple[tuple[int, int, int, int, int], int, float]]:
    out: list[tuple[tuple[int, int, int, int, int], int, float]] = []
    for contribution in system.contributions:
        for role_index in range(4):
            if contribution.cell(role_index) == (row, column):
                out.append((contribution.identity, role_index, contribution.term(role_index)[0]))
    return out


def _ulp_tolerance(a: float, b: float, terms: int) -> float:
    scale = max(abs(a), abs(b), 1.0)
    return float(np.spacing(np.float64(scale))) * max(4, terms * 2)


def _attribute_system(
    source: SystemData,
    native: SystemData,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter[str], Counter[int]]:
    if source.n_rows != native.n_rows:
        raise ValueError(f"dimension mismatch sequence={source.sequence} z={source.element_z}")
    source_map = _record_maps(source.contributions)
    native_map = _record_maps(native.contributions)
    identities = sorted(set(source_map) | set(native_map))
    classifications = {
        identity: _classify_record(source_map.get(identity), native_map.get(identity))
        for identity in identities
    }
    cell_rows: list[dict[str, Any]] = []
    record_rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    type_counts: Counter[int] = Counter()
    mismatch_indices = np.argwhere(source.dense != native.dense)
    for zero_row, zero_col in mismatch_indices:
        row = int(zero_row) + 1
        column = int(zero_col) + 1
        source_value = float(source.dense[zero_row, zero_col])
        native_value = float(native.dense[zero_row, zero_col])
        causal: list[dict[str, Any]] = []
        for identity in identities:
            source_contribution = source_map.get(identity)
            native_contribution = native_map.get(identity)
            for role_index, role in enumerate(ROLE_NAMES):
                source_term = _value_for_cell(source_contribution, role_index, row, column)
                native_term = _value_for_cell(native_contribution, role_index, row, column)
                if source_term == native_term:
                    continue
                classification = classifications[identity]
                causal_row = {
                    "sequence": source.sequence,
                    "element_z": source.element_z,
                    "row": row,
                    "column": column,
                    "record": identity[0],
                    "data_type": identity[1],
                    "rate_type": identity[2],
                    "ion_index": identity[3],
                    "ion_stage": identity[4],
                    "role": role,
                    "classification": classification,
                    "source_present": int(source_contribution is not None),
                    "native_present": int(native_contribution is not None),
                    "source_order_index": source_contribution.order if source_contribution else 0,
                    "native_order_index": native_contribution.order if native_contribution else 0,
                    "source_lower_row": source_contribution.lower if source_contribution else 0,
                    "source_upper_row": source_contribution.upper if source_contribution else 0,
                    "native_lower_row": native_contribution.lower if native_contribution else 0,
                    "native_upper_row": native_contribution.upper if native_contribution else 0,
                    "source_value": source_term,
                    "native_value": native_term,
                    "delta": native_term - source_term,
                }
                causal.append(causal_row)
                record_rows.append(causal_row)
                class_counts[classification] += 1
                type_counts[identity[1]] += 1
        source_sequence = _term_sequence_for_cell(source, row, column)
        native_sequence = _term_sequence_for_cell(native, row, column)
        sequence_exact = source_sequence == native_sequence
        if causal:
            primary = sorted(
                {item["classification"] for item in causal},
                key=lambda value: (
                    0 if value == "ENDPOINT_ORIENTATION_DELTA" else
                    1 if value == "RATE_VALUE_DELTA" else
                    2 if value.endswith("ONLY_RECORD") else 3,
                    value,
                ),
            )[0]
            attributed = True
        elif not sequence_exact:
            primary = "ACCUMULATION_ORDER_ONLY"
            attributed = True
            class_counts[primary] += 1
        else:
            primary = "UNRESOLVED"
            attributed = False
            class_counts[primary] += 1
        direct_delta = math.fsum(float(item["delta"]) for item in causal)
        residual = (native_value - source_value) - direct_delta
        order_tolerance = _ulp_tolerance(source_value, native_value, len(source_sequence) + len(native_sequence))
        cell_rows.append({
            "sequence": source.sequence,
            "element_z": source.element_z,
            "row": row,
            "column": column,
            "source_value": source_value,
            "native_value": native_value,
            "delta": native_value - source_value,
            "source_term_count": len(source_sequence),
            "native_term_count": len(native_sequence),
            "term_sequence_exact": int(sequence_exact),
            "causal_record_count": len({(item["record"], item["data_type"], item["rate_type"]) for item in causal}),
            "causal_term_count": len(causal),
            "causal_data_types": ";".join(str(value) for value in sorted({item["data_type"] for item in causal})),
            "causal_records": ";".join(str(value) for value in sorted({item["record"] for item in causal})),
            "primary_classification": primary,
            "direct_record_delta": direct_delta,
            "order_rounding_residual": residual,
            "order_rounding_tolerance": order_tolerance,
            "attributed": int(attributed),
        })
    return cell_rows, record_rows, class_counts, type_counts


def _hydrogen_type53_gate(
    source_systems: dict[tuple[int, int], SystemData],
    native_systems: dict[tuple[int, int], SystemData],
    native_run: Path,
) -> dict[str, Any]:
    expected = 0
    contribution_exact = 0
    endpoint_exact = 0
    diagnostics_seen = 0
    diagnostics_exact = 0
    errors: list[str] = []
    for sequence in range(1, 62):
        source_map = _record_maps(source_systems[(sequence, 1)].contributions)
        native_map = _record_maps(native_systems[(sequence, 1)].contributions)
        for identity, source_contribution in source_map.items():
            if identity[1] != 53:
                continue
            expected += 1
            native_contribution = native_map.get(identity)
            if native_contribution is None:
                errors.append(f"missing_native_type53:{sequence}:{identity[0]}")
                continue
            if (source_contribution.lower, source_contribution.upper) == (
                native_contribution.lower, native_contribution.upper
            ):
                endpoint_exact += 1
            if source_contribution.ints[2:9] == native_contribution.ints[2:9] and source_contribution.reals == native_contribution.reals:
                contribution_exact += 1
        records_path = native_run / "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
        if not records_path.is_file():
            errors.append(f"missing_record_diagnostics:{sequence}")
            continue
        for row in _read_csv(records_path):
            if int(row["element_z"]) != 1 or int(row["data_type"]) != 53:
                continue
            diagnostics_seen += 1
            exact = (
                int(row["matrix_committed"]) == 1
                and int(row["type53_shadow_valid"]) == 1
                and all(
                    float(row[f"ans{index}"]) == float(row[f"type53_shadow_ans{index}"])
                    for index in range(1, 7)
                )
            )
            if exact:
                diagnostics_exact += 1
            else:
                errors.append(f"type53_shadow_not_committed:{sequence}:{row['record']}")
    if expected != 31 * 61:
        errors.append(f"hydrogen_type53_inventory={expected} expected={31*61}")
    result = "ACCEPT" if (
        not errors and contribution_exact == expected and endpoint_exact == expected
        and diagnostics_seen == expected and diagnostics_exact == expected
    ) else "REJECT"
    return {
        "result": result,
        "records_expected": expected,
        "contributions_exact": contribution_exact,
        "endpoints_exact": endpoint_exact,
        "diagnostics_seen": diagnostics_seen,
        "diagnostics_exact": diagnostics_exact,
        "errors": errors[:50],
    }


def analyze(source_capture: Path, native_run: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    source_rows = _source_manifests(source_capture)
    native_rows = _native_manifests(native_run)
    expected = {(sequence, z) for sequence in range(1, 62) for z in (1, 2, 12)}
    if set(source_rows) != expected:
        errors.append(f"source_system_inventory={len(source_rows)} expected=183")
    if set(native_rows) != expected:
        errors.append(f"native_system_inventory={len(native_rows)} expected=183")

    source_systems: dict[tuple[int, int], SystemData] = {}
    native_systems: dict[tuple[int, int], SystemData] = {}
    system_rows: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []
    record_rows: list[dict[str, Any]] = []
    classification_counts: Counter[str] = Counter()
    data_type_counts: Counter[int] = Counter()
    source_reconstruction_exact = 0
    native_reconstruction_exact = 0
    dense_exact_systems = 0
    attributed_cells = 0
    total_mismatch_cells = 0

    for key in sorted(expected):
        if key not in source_rows or key not in native_rows:
            continue
        try:
            source = _load_system(source_rows[key], source=True)
            native = _load_system(native_rows[key], source=False)
            source_systems[key] = source
            native_systems[key] = native
            source_reconstructed = _reconstruct(source)
            native_reconstructed = _reconstruct(native)
            source_exact = all(
                np.array_equal(actual, expected_matrix)
                for actual, expected_matrix in zip(source_reconstructed, (source.dense, source.heat, source.heat2))
            )
            native_exact = all(
                np.array_equal(actual, expected_matrix)
                for actual, expected_matrix in zip(native_reconstructed, (native.dense, native.heat, native.heat2))
            )
            source_reconstruction_exact += int(source_exact)
            native_reconstruction_exact += int(native_exact)
            if not source_exact:
                errors.append(f"source_reconstruction:{key}")
            if not native_exact:
                errors.append(f"native_reconstruction:{key}")
            dense_exact = np.array_equal(source.dense, native.dense)
            dense_exact_systems += int(dense_exact)
            local_cells: list[dict[str, Any]] = []
            local_records: list[dict[str, Any]] = []
            local_class = Counter()
            local_types = Counter()
            if source_exact and native_exact and not dense_exact:
                local_cells, local_records, local_class, local_types = _attribute_system(source, native)
                cell_rows.extend(local_cells)
                record_rows.extend(local_records)
                classification_counts.update(local_class)
                data_type_counts.update(local_types)
                total_mismatch_cells += len(local_cells)
                attributed_cells += sum(int(row["attributed"]) for row in local_cells)
            system_rows.append({
                "sequence": key[0],
                "element_z": key[1],
                "n_rows": source.n_rows,
                "source_contributions": len(source.contributions),
                "native_contributions": len(native.contributions),
                "source_reconstruction_exact": int(source_exact),
                "native_reconstruction_exact": int(native_exact),
                "dense_matrix_exact": int(dense_exact),
                "dense_mismatch_cells": len(local_cells),
                "attributed_cells": sum(int(row["attributed"]) for row in local_cells),
            })
        except Exception as exc:
            errors.append(f"system:{key}:{type(exc).__name__}:{exc}")

    h53 = {
        "result": "REJECT",
        "records_expected": 0,
        "contributions_exact": 0,
        "endpoints_exact": 0,
        "diagnostics_seen": 0,
        "diagnostics_exact": 0,
        "errors": ["incomplete systems"],
    }
    if len(source_systems) == 183 and len(native_systems) == 183:
        h53 = _hydrogen_type53_gate(source_systems, native_systems, native_run)
        errors.extend(f"hydrogen_type53:{value}" for value in h53["errors"])

    all_attributed = total_mismatch_cells > 0 and attributed_cells == total_mismatch_cells
    capture_exact = len(source_systems) == 183 and len(native_systems) == 183
    reconstruction_exact = source_reconstruction_exact == 183 and native_reconstruction_exact == 183
    milestone = capture_exact and reconstruction_exact and all_attributed and h53["result"] == "ACCEPT"

    post_seed_path = output / "all61_post_seed_system_decomposition_summary.json"
    post_seed = json.loads(post_seed_path.read_text()) if post_seed_path.is_file() else {}
    fixed_gate = str(post_seed.get("gates", {}).get("V06487_FIXED_STATE_PARITY", "REJECT"))
    gates = {
        "ALL_61_SOURCE_MATRIX_CONTRIBUTIONS_CAPTURED": "ACCEPT" if len(source_systems) == 183 else "REJECT",
        "ALL_61_NATIVE_MATRIX_CONTRIBUTIONS_CAPTURED": "ACCEPT" if len(native_systems) == 183 else "REJECT",
        "ALL_61_SOURCE_MATRIX_RECONSTRUCTION_EXACT": "ACCEPT" if source_reconstruction_exact == 183 else "REJECT",
        "ALL_61_NATIVE_MATRIX_RECONSTRUCTION_EXACT": "ACCEPT" if native_reconstruction_exact == 183 else "REJECT",
        "ALL_61_DENSE_MATRIX_CAUSAL_RECORDS_ATTRIBUTED": "ACCEPT" if all_attributed else "REJECT",
        "ALL_61_HYDROGEN_TYPE53_SOURCE_FAITHFUL": h53["result"],
        "V06487469_DENSE_MATRIX_CAUSAL_ATTRIBUTION": "ACCEPT" if milestone else "REJECT",
        "V06487_FIXED_STATE_PARITY": fixed_gate,
        "V06488_THERMAL_PARITY_READY": "ACCEPT" if fixed_gate == "ACCEPT" else "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
        "THERMAL_PARITY": "NOT_RUN" if fixed_gate == "ACCEPT" else "BLOCKED",
        "CONTROLLER_PARITY": "NOT_RUN_V06489",
        "PRODUCT_PARITY": "BLOCKED",
        "PRODUCTION_PROMOTION": "BLOCKED",
    }
    result = {
        "schema": SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if milestone else "REJECT",
        "errors": errors[:200],
        "source_systems": len(source_systems),
        "native_systems": len(native_systems),
        "source_reconstruction_exact_systems": source_reconstruction_exact,
        "native_reconstruction_exact_systems": native_reconstruction_exact,
        "dense_exact_systems": dense_exact_systems,
        "dense_mismatch_cells": total_mismatch_cells,
        "dense_attributed_cells": attributed_cells,
        "classification_counts": dict(sorted(classification_counts.items())),
        "causal_data_type_counts": {str(key): value for key, value in sorted(data_type_counts.items())},
        "hydrogen_type53": h53,
        "gates": gates,
        "qualification_only": True,
        "production_promotion_ready": False,
        "thermal_parity_started": False,
    }
    _write_csv(
        output / SYSTEM_NAME,
        [
            "sequence", "element_z", "n_rows", "source_contributions", "native_contributions",
            "source_reconstruction_exact", "native_reconstruction_exact", "dense_matrix_exact",
            "dense_mismatch_cells", "attributed_cells",
        ],
        system_rows,
    )
    _write_csv(
        output / CELL_NAME,
        [
            "sequence", "element_z", "row", "column", "source_value", "native_value", "delta",
            "source_term_count", "native_term_count", "term_sequence_exact", "causal_record_count",
            "causal_term_count", "causal_data_types", "causal_records", "primary_classification",
            "direct_record_delta", "order_rounding_residual", "order_rounding_tolerance", "attributed",
        ],
        cell_rows,
    )
    _write_csv(
        output / RECORD_NAME,
        [
            "sequence", "element_z", "row", "column", "record", "data_type", "rate_type",
            "ion_index", "ion_stage", "role", "classification", "source_present", "native_present",
            "source_order_index", "native_order_index", "source_lower_row", "source_upper_row",
            "native_lower_row", "native_upper_row", "source_value", "native_value", "delta",
        ],
        record_rows,
    )
    _write_json(output / SUMMARY_NAME, result)
    return result


def causal_attribution_self_test() -> dict[str, Any]:
    def contribution(order: int, record: int, data_type: int, lower: int, upper: int, base: float) -> Contribution:
        ints = (order, 4 * order, record, data_type, 7, 1, 1, lower, upper, 0, 0, 0, 0, 0)
        reals = (
            base, base + 1, 0.0, 0.0,
            base + 1, base, 0.0, 0.0,
            -base, -base, base + 2, base + 3,
            -(base + 1), -(base + 1), -(base + 4), -(base + 5),
        )
        return Contribution(ints, reals)

    source = SystemData(1, 12, 3, np.zeros((3, 3)), np.zeros((3, 3)), np.zeros((3, 3)), [
        contribution(1, 100, 50, 2, 1, 5.0),
    ], {})
    native = SystemData(1, 12, 3, np.zeros((3, 3)), np.zeros((3, 3)), np.zeros((3, 3)), [
        contribution(1, 100, 50, 1, 2, 5.0),
    ], {})
    source.dense, source.heat, source.heat2 = _reconstruct(source)
    native.dense, native.heat, native.heat2 = _reconstruct(native)
    cells, records, classes, types = _attribute_system(source, native)
    errors: list[str] = []
    if not cells or not all(int(row["attributed"]) for row in cells):
        errors.append("cells_not_attributed")
    if not any(row["classification"] == "ENDPOINT_ORIENTATION_DELTA" for row in records):
        errors.append("orientation_not_classified")
    if types.get(50, 0) <= 0:
        errors.append("type50_not_attributed")
    return {
        "schema": "xstar-tools-v06487469-causal-attribution-self-test-v1",
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "mismatch_cells": len(cells),
        "record_rows": len(records),
        "classification_counts": dict(classes),
        "data_type_counts": {str(key): value for key, value in types.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = analyze(args.source_capture, args.native_run, args.output)
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "gates": {
                "V06487469_DENSE_MATRIX_CAUSAL_ATTRIBUTION": "REJECT",
                "V06487_FIXED_STATE_PARITY": "REJECT",
                "V06488_THERMAL_PARITY_READY": "NO_FIXED_STATE_GATE_NOT_ACCEPTED",
                "THERMAL_PARITY": "BLOCKED",
                "CONTROLLER_PARITY": "NOT_RUN_V06489",
                "PRODUCT_PARITY": "BLOCKED",
                "PRODUCTION_PROMOTION": "BLOCKED",
            },
            "qualification_only": True,
            "production_promotion_ready": False,
            "thermal_parity_started": False,
        }
        _write_json(args.output / SUMMARY_NAME, result)
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
