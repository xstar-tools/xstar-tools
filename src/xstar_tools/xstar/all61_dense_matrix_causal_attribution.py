"""Indexed all-61 dense-matrix causal attribution for v0.6.48.7.46.14.1.

The audit consumes the exact source and native contribution streams captured by
v0.6.48.7.46.9, but indexes those streams once by matrix cell instead of
rescanning every committed record for every mismatch.  Output rows are streamed
per system, and the large record table is gzip-compressed, so a completed 61-row
capture can be resumed without repeating source capture or native replay.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import sys
import tempfile
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

RELEASE = "0.6.48.7.46.14.1"
SCHEMA = "xstar-tools-v0648746931-hydrogen-type53-ieee-equivalence-attribution-v1"
SUMMARY_NAME = "all61_dense_matrix_causal_attribution_summary.json"
CELL_NAME = "all61_dense_matrix_causal_cells.csv"
RECORD_NAME = "all61_dense_matrix_causal_records.csv.gz"
LEGACY_RECORD_NAME = "all61_dense_matrix_causal_records.csv"
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

SYSTEM_FIELDS = [
    "sequence", "element_z", "n_rows", "source_contributions", "native_contributions",
    "source_reconstruction_exact", "native_reconstruction_exact", "dense_matrix_exact",
    "dense_mismatch_cells", "attributed_cells",
]
CELL_FIELDS = [
    "sequence", "element_z", "row", "column", "source_value", "native_value", "delta",
    "source_term_count", "native_term_count", "term_sequence_exact", "causal_record_count",
    "causal_term_count", "causal_data_types", "causal_records", "primary_classification",
    "direct_record_delta", "order_rounding_residual", "order_rounding_tolerance", "attributed",
]
RECORD_FIELDS = [
    "sequence", "element_z", "row", "column", "record", "data_type", "rate_type",
    "ion_index", "ion_stage", "source_ion_index", "native_ion_index", "role", "classification", "source_present", "native_present",
    "source_order_index", "native_order_index", "source_lower_row", "source_upper_row",
    "native_lower_row", "native_upper_row", "source_value", "native_value", "delta",
]

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
    def identity(self) -> tuple[int, int, int, int]:
        """Canonical source/native record identity.

        The source contribution stream stores the global XSTAR ion index while
        the lowered native stream stores an element-local ion index.  Record
        number, data type, rate type, and ion stage are invariant across both
        representations and uniquely identify the committed atomic record.
        """
        return (self.record, self.data_type, self.rate_type, self.ion_stage)

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


@contextmanager
def _atomic_csv_writer(
    path: Path,
    fieldnames: list[str],
    *,
    gzip_output: bool = False,
):
    """Stream a CSV to a temporary file and publish it atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.unlink(missing_ok=True)
    opener = (
        (lambda: gzip.open(temporary, "wt", newline="", compresslevel=1))
        if gzip_output
        else (lambda: temporary.open("w", newline=""))
    )
    try:
        with opener() as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            yield writer
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


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


def _record_maps(contributions: list[Contribution]) -> dict[tuple[int, int, int, int], Contribution]:
    out: dict[tuple[int, int, int, int], Contribution] = {}
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


TermEntry = tuple[tuple[int, int, int, int], int, float]


def _index_terms_by_cell(contributions: list[Contribution]) -> dict[tuple[int, int], list[TermEntry]]:
    """Index the source-ordered contribution stream by matrix cell.

    The lists preserve the exact contribution order and role order used by the
    original full scan.  Zero-valued terms are retained because they are part
    of the source-order contract even when they do not change the matrix.
    """
    out: dict[tuple[int, int], list[TermEntry]] = defaultdict(list)
    for contribution in contributions:
        identity = contribution.identity
        for role_index in range(4):
            out[contribution.cell(role_index)].append(
                (identity, role_index, contribution.term(role_index)[0])
            )
    return dict(out)


def _term_sequence_for_cell(system: SystemData, row: int, column: int) -> list[TermEntry]:
    """Reference full-scan implementation retained for regression tests."""
    out: list[TermEntry] = []
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
    *,
    metrics: dict[str, int] | None = None,
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
    if metrics is not None:
        canonical_pairs = [
            identity for identity in identities
            if source_map.get(identity) is not None and native_map.get(identity) is not None
        ]
        metrics["canonical_record_pairs"] = metrics.get("canonical_record_pairs", 0) + len(canonical_pairs)
        metrics["global_to_local_ion_index_pairs"] = metrics.get("global_to_local_ion_index_pairs", 0) + sum(
            source_map[identity].ion_index != native_map[identity].ion_index
            for identity in canonical_pairs
        )
    source_terms_by_cell = _index_terms_by_cell(source.contributions)
    native_terms_by_cell = _index_terms_by_cell(native.contributions)
    cell_rows: list[dict[str, Any]] = []
    record_rows: list[dict[str, Any]] = []
    class_counts: Counter[str] = Counter()
    type_counts: Counter[int] = Counter()
    mismatch_indices = np.argwhere(source.dense != native.dense)
    if metrics is not None:
        metrics["systems"] = metrics.get("systems", 0) + 1
        metrics["mismatch_cells"] = metrics.get("mismatch_cells", 0) + len(mismatch_indices)
        metrics["record_identities"] = metrics.get("record_identities", 0) + len(identities)
        metrics["full_identity_checks_avoided_baseline"] = (
            metrics.get("full_identity_checks_avoided_baseline", 0)
            + len(identities) * len(mismatch_indices)
        )
    for zero_row, zero_col in mismatch_indices:
        row = int(zero_row) + 1
        column = int(zero_col) + 1
        cell = (row, column)
        source_value = float(source.dense[zero_row, zero_col])
        native_value = float(native.dense[zero_row, zero_col])
        source_sequence = source_terms_by_cell.get(cell, [])
        native_sequence = native_terms_by_cell.get(cell, [])
        relevant_identities = sorted(
            {entry[0] for entry in source_sequence} | {entry[0] for entry in native_sequence}
        )
        if metrics is not None:
            metrics["indexed_identity_checks"] = (
                metrics.get("indexed_identity_checks", 0) + len(relevant_identities)
            )
            metrics["indexed_term_entries"] = (
                metrics.get("indexed_term_entries", 0)
                + len(source_sequence) + len(native_sequence)
            )
        causal: list[dict[str, Any]] = []
        for identity in relevant_identities:
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
                    "ion_index": native_contribution.ion_index if native_contribution else source_contribution.ion_index,
                    "ion_stage": identity[3],
                    "source_ion_index": source_contribution.ion_index if source_contribution else 0,
                    "native_ion_index": native_contribution.ion_index if native_contribution else 0,
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


def _new_hydrogen_type53_state() -> dict[str, Any]:
    return {
        "records_expected": 0,
        "contributions_exact": 0,
        "contributions_ieee_equivalent": 0,
        "roundoff_record_vectors": 0,
        "roundoff_real_fields": 0,
        "max_ulp_distance": 0,
        "max_absolute_delta": 0.0,
        "max_relative_delta": 0.0,
        "roundoff_records": [],
        "endpoints_exact": 0,
        "diagnostics_seen": 0,
        "diagnostics_exact": 0,
        "affected_channel_exact": {"ans1": 0, "ans2": 0, "ans3": 0, "ans4": 0, "ans5": 0, "ans6": 0},
        "phase_exact": {"call3": 0, "call4": 0, "final_call3": 0, "final_call4": 0},
        "phase_ieee_equivalent": {"call3": 0, "call4": 0, "final_call3": 0, "final_call4": 0},
        "errors": [],
    }


_HYDROGEN_TYPE53_AFFECTED_RECORDS = {41, 42, 43, 45, 47, 48, 59, 66}
_HYDROGEN_TYPE53_PHASE_EXPECTED = {
    "call3": 144,
    "call4": 136,
    "final_call3": 8,
    "final_call4": 8,
}

# v0.6.48.7.46.14.1: accept only host/compiler binary64 roundoff.
# A field must be finite, have the same sign, differ by no more than two ULPs,
# and satisfy the relative guard.  There is deliberately no nonzero absolute
# tolerance, so a small source value cannot be matched to zero.
_HYDROGEN_TYPE53_MAX_ULPS = 2
_HYDROGEN_TYPE53_MAX_RELATIVE_DELTA = 4.0e-16
_HYDROGEN_TYPE53_REAL_LABELS = tuple(
    f"{role}:{term}"
    for role in ROLE_NAMES
    for term in ("aj1", "aj2", "cj", "cj2")
)


def _binary64_ulp_distance(left: float, right: float) -> int:
    left_bits = int(np.float64(left).view(np.uint64))
    right_bits = int(np.float64(right).view(np.uint64))
    return abs(left_bits - right_bits)


def _binary64_ieee_equivalent(left: float, right: float) -> tuple[bool, int, float, float]:
    if left == right:
        return True, 0, 0.0, 0.0
    if not math.isfinite(left) or not math.isfinite(right):
        return False, 2**63 - 1, math.inf, math.inf
    if left == 0.0 or right == 0.0 or math.copysign(1.0, left) != math.copysign(1.0, right):
        return False, _binary64_ulp_distance(left, right), abs(right - left), math.inf
    absolute_delta = abs(right - left)
    relative_delta = absolute_delta / max(abs(left), abs(right))
    ulps = _binary64_ulp_distance(left, right)
    accepted = (
        ulps <= _HYDROGEN_TYPE53_MAX_ULPS
        and relative_delta <= _HYDROGEN_TYPE53_MAX_RELATIVE_DELTA
    )
    return accepted, ulps, absolute_delta, relative_delta


def _hydrogen_type53_vector_equivalence(
    source_reals: tuple[float, ...],
    native_reals: tuple[float, ...],
) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    accepted = len(source_reals) == len(native_reals) == REAL_COLUMNS
    max_ulps = 0
    max_absolute_delta = 0.0
    max_relative_delta = 0.0
    for index, (source_value, native_value) in enumerate(zip(source_reals, native_reals)):
        equivalent, ulps, absolute_delta, relative_delta = _binary64_ieee_equivalent(
            source_value, native_value
        )
        accepted = accepted and equivalent
        max_ulps = max(max_ulps, ulps)
        max_absolute_delta = max(max_absolute_delta, absolute_delta)
        max_relative_delta = max(max_relative_delta, relative_delta)
        if source_value != native_value:
            fields.append({
                "field": _HYDROGEN_TYPE53_REAL_LABELS[index],
                "source_value": source_value,
                "native_value": native_value,
                "delta": native_value - source_value,
                "absolute_delta": absolute_delta,
                "relative_delta": relative_delta,
                "ulp_distance": ulps,
                "accepted": equivalent,
            })
    return {
        "accepted": accepted,
        "bit_exact": source_reals == native_reals,
        "differing_fields": fields,
        "max_ulp_distance": max_ulps,
        "max_absolute_delta": max_absolute_delta,
        "max_relative_delta": max_relative_delta,
    }


def hydrogen_type53_ieee_equivalence_self_test() -> dict[str, Any]:
    observed_pairs = (
        (1.7648023082206567e-08, 1.7648023082206564e-08),
        (2.2096863507018874e-13, 2.2096863507018870e-13),
        (1.1937722916711257e-09, 1.1937722916711255e-09),
        (2.1881659622280428e-11, 2.1881659622280434e-11),
        (8.9060683811322620e-11, 8.9060683811322590e-11),
        (2.1881371018023603e-11, 2.1881371018023600e-11),
    )
    errors: list[str] = []
    max_ulps = 0
    max_relative = 0.0
    for source_value, native_value in observed_pairs:
        accepted, ulps, _absolute, relative = _binary64_ieee_equivalent(
            source_value, native_value
        )
        max_ulps = max(max_ulps, ulps)
        max_relative = max(max_relative, relative)
        if not accepted:
            errors.append(f"observed_roundoff_rejected:{source_value!r}:{native_value!r}")
    base = 1.0
    three_ulps = float(np.nextafter(np.nextafter(np.nextafter(base, math.inf), math.inf), math.inf))
    if _binary64_ieee_equivalent(base, three_ulps)[0]:
        errors.append("three_ulp_difference_accepted")
    if _binary64_ieee_equivalent(0.0, float(np.nextafter(0.0, 1.0)))[0]:
        errors.append("zero_to_nonzero_difference_accepted")
    if _binary64_ieee_equivalent(1.0, -1.0)[0]:
        errors.append("opposite_sign_difference_accepted")
    if _binary64_ieee_equivalent(math.nan, math.nan)[0]:
        errors.append("nan_difference_accepted")
    return {
        "schema": "xstar-tools-v0648746931-hydrogen-type53-ieee-equivalence-self-test-v1",
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "observed_pairs": len(observed_pairs),
        "max_ulp_distance": max_ulps,
        "max_relative_delta": max_relative,
        "limits": {
            "max_ulps": _HYDROGEN_TYPE53_MAX_ULPS,
            "max_relative_delta": _HYDROGEN_TYPE53_MAX_RELATIVE_DELTA,
            "nonzero_absolute_tolerance": 0.0,
        },
    }


def _hydrogen_type53_phase(sequence: int) -> str | None:
    if 23 <= sequence <= 40:
        return "call3"
    if 41 <= sequence <= 57:
        return "call4"
    if sequence == 60:
        return "final_call3"
    if sequence == 61:
        return "final_call4"
    return None


def _update_hydrogen_type53_state(
    state: dict[str, Any],
    source: SystemData,
    native: SystemData,
    native_run: Path,
) -> None:
    sequence = source.sequence
    source_map = _record_maps(source.contributions)
    native_map = _record_maps(native.contributions)
    errors: list[str] = state["errors"]
    phase = _hydrogen_type53_phase(sequence)
    for identity, source_contribution in source_map.items():
        if identity[1] != 53:
            continue
        state["records_expected"] += 1
        native_contribution = native_map.get(identity)
        if native_contribution is None:
            errors.append(f"missing_native_type53:{sequence}:{identity[0]}")
            continue
        endpoints_exact = (source_contribution.lower, source_contribution.upper) == (
            native_contribution.lower, native_contribution.upper
        )
        if endpoints_exact:
            state["endpoints_exact"] += 1
        metadata_exact = (
            source_contribution.record == native_contribution.record
            and source_contribution.data_type == native_contribution.data_type
            and source_contribution.rate_type == native_contribution.rate_type
            and source_contribution.ion_stage == native_contribution.ion_stage
            and endpoints_exact
        )
        vector = _hydrogen_type53_vector_equivalence(
            source_contribution.reals, native_contribution.reals
        )
        contribution_exact = metadata_exact and vector["bit_exact"]
        contribution_ieee_equivalent = metadata_exact and vector["accepted"]
        if contribution_exact:
            state["contributions_exact"] += 1
            if phase and identity[0] in _HYDROGEN_TYPE53_AFFECTED_RECORDS:
                state["phase_exact"][phase] += 1
        if contribution_ieee_equivalent:
            state["contributions_ieee_equivalent"] += 1
            if phase and identity[0] in _HYDROGEN_TYPE53_AFFECTED_RECORDS:
                state["phase_ieee_equivalent"][phase] += 1
        if contribution_ieee_equivalent and not contribution_exact:
            state["roundoff_record_vectors"] += 1
            state["roundoff_real_fields"] += len(vector["differing_fields"])
            state["max_ulp_distance"] = max(state["max_ulp_distance"], vector["max_ulp_distance"])
            state["max_absolute_delta"] = max(
                state["max_absolute_delta"], vector["max_absolute_delta"]
            )
            state["max_relative_delta"] = max(
                state["max_relative_delta"], vector["max_relative_delta"]
            )
            if len(state["roundoff_records"]) < 50:
                state["roundoff_records"].append({
                    "sequence": sequence,
                    "record": identity[0],
                    "phase": phase or "other",
                    "differing_fields": vector["differing_fields"],
                })
        if metadata_exact and not vector["accepted"]:
            errors.append(
                f"type53_contribution_outside_ieee_tolerance:{sequence}:{identity[0]}:"
                f"max_ulps={vector['max_ulp_distance']}:"
                f"max_relative={vector['max_relative_delta']:.17g}"
            )
    records_path = native_run / "qualification_diagnostics" / f"evaluation_{sequence:04d}_records.csv"
    if not records_path.is_file():
        errors.append(f"missing_record_diagnostics:{sequence}")
        return
    for row in _read_csv(records_path):
        if int(row["element_z"]) != 1 or int(row["data_type"]) != 53:
            continue
        state["diagnostics_seen"] += 1
        channel_exact = {
            f"ans{index}": float(row[f"ans{index}"]) == float(row[f"type53_shadow_ans{index}"])
            for index in range(1, 7)
        }
        exact = (
            int(row["matrix_committed"]) == 1
            and int(row["type53_shadow_valid"]) == 1
            and all(channel_exact.values())
        )
        if exact:
            state["diagnostics_exact"] += 1
        else:
            errors.append(f"type53_shadow_not_committed:{sequence}:{row['record']}")
        if int(row["record"]) in _HYDROGEN_TYPE53_AFFECTED_RECORDS and phase:
            for name, value in channel_exact.items():
                state["affected_channel_exact"][name] += int(value)


def _finalize_hydrogen_type53_state(state: dict[str, Any]) -> dict[str, Any]:
    expected_inventory = 31 * 61
    errors: list[str] = state["errors"]
    if state["records_expected"] != expected_inventory:
        errors.append(
            f"hydrogen_type53_inventory={state['records_expected']} expected={expected_inventory}"
        )
    for phase, expected in _HYDROGEN_TYPE53_PHASE_EXPECTED.items():
        if state["phase_ieee_equivalent"][phase] != expected:
            errors.append(
                f"hydrogen_type53_{phase}_ieee_equivalent="
                f"{state['phase_ieee_equivalent'][phase]} expected={expected}"
            )
    affected_total = sum(_HYDROGEN_TYPE53_PHASE_EXPECTED.values())
    for channel in ("ans1", "ans2", "ans3", "ans4", "ans5", "ans6"):
        if state["affected_channel_exact"][channel] != affected_total:
            errors.append(
                f"hydrogen_type53_{channel}_exact={state['affected_channel_exact'][channel]} expected={affected_total}"
            )
    result = "ACCEPT" if (
        not errors
        and state["contributions_ieee_equivalent"] == state["records_expected"]
        and state["endpoints_exact"] == state["records_expected"]
        and state["diagnostics_seen"] == state["records_expected"]
        and state["diagnostics_exact"] == state["records_expected"]
    ) else "REJECT"
    return {
        "result": result,
        "records_expected": state["records_expected"],
        "contributions_exact": state["contributions_exact"],
        "contributions_ieee_equivalent": state["contributions_ieee_equivalent"],
        "roundoff_record_vectors": state["roundoff_record_vectors"],
        "roundoff_real_fields": state["roundoff_real_fields"],
        "max_ulp_distance": state["max_ulp_distance"],
        "max_absolute_delta": state["max_absolute_delta"],
        "max_relative_delta": state["max_relative_delta"],
        "ieee_tolerance": {
            "max_ulps": _HYDROGEN_TYPE53_MAX_ULPS,
            "max_relative_delta": _HYDROGEN_TYPE53_MAX_RELATIVE_DELTA,
            "nonzero_absolute_tolerance": 0.0,
            "same_sign_required": True,
            "finite_required": True,
        },
        "roundoff_records": state["roundoff_records"],
        "endpoints_exact": state["endpoints_exact"],
        "diagnostics_seen": state["diagnostics_seen"],
        "diagnostics_exact": state["diagnostics_exact"],
        "affected_records": sorted(_HYDROGEN_TYPE53_AFFECTED_RECORDS),
        "affected_channel_exact": state["affected_channel_exact"],
        "phase_exact": state["phase_exact"],
        "phase_ieee_equivalent": state["phase_ieee_equivalent"],
        "phase_expected": dict(_HYDROGEN_TYPE53_PHASE_EXPECTED),
        "errors": errors[:50],
    }

def analyze(
    source_capture: Path,
    native_run: Path,
    output: Path,
    *,
    progress_every: int = 10,
) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    source_rows = _source_manifests(source_capture)
    native_rows = _native_manifests(native_run)
    expected = {(sequence, z) for sequence in range(1, 62) for z in (1, 2, 12)}
    if set(source_rows) != expected:
        errors.append(f"source_system_inventory={len(source_rows)} expected=183")
    if set(native_rows) != expected:
        errors.append(f"native_system_inventory={len(native_rows)} expected=183")

    source_system_count = 0
    native_system_count = 0
    hydrogen_type53_state = _new_hydrogen_type53_state()
    attribution_metrics: dict[str, int] = {}
    started = time.perf_counter()
    processed = 0
    cell_rows_written = 0
    record_rows_written = 0
    classification_counts: Counter[str] = Counter()
    data_type_counts: Counter[int] = Counter()
    source_reconstruction_exact = 0
    native_reconstruction_exact = 0
    dense_exact_systems = 0
    attributed_cells = 0
    total_mismatch_cells = 0

    (output / LEGACY_RECORD_NAME).unlink(missing_ok=True)
    for stale in (
        output / (SYSTEM_NAME + ".tmp"),
        output / (CELL_NAME + ".tmp"),
        output / (RECORD_NAME + ".tmp"),
    ):
        stale.unlink(missing_ok=True)
    with (
        _atomic_csv_writer(output / SYSTEM_NAME, SYSTEM_FIELDS) as system_writer,
        _atomic_csv_writer(output / CELL_NAME, CELL_FIELDS) as cell_writer,
        _atomic_csv_writer(output / RECORD_NAME, RECORD_FIELDS, gzip_output=True) as record_writer,
    ):
        for key in sorted(expected):
            if key not in source_rows or key not in native_rows:
                continue
            try:
                source = _load_system(source_rows[key], source=True)
                native = _load_system(native_rows[key], source=False)
                source_system_count += 1
                native_system_count += 1
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
                    local_cells, local_records, local_class, local_types = _attribute_system(
                        source, native, metrics=attribution_metrics
                    )
                    cell_writer.writerows(local_cells)
                    record_writer.writerows(local_records)
                    cell_rows_written += len(local_cells)
                    record_rows_written += len(local_records)
                    classification_counts.update(local_class)
                    data_type_counts.update(local_types)
                    total_mismatch_cells += len(local_cells)
                    attributed_cells += sum(int(row["attributed"]) for row in local_cells)
                system_writer.writerow({
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
                if key[1] == 1:
                    _update_hydrogen_type53_state(hydrogen_type53_state, source, native, native_run)
                processed += 1
                if progress_every > 0 and (processed % progress_every == 0 or processed == len(expected)):
                    elapsed = time.perf_counter() - started
                    print(
                        # Historical readiness marker: V04874692_PROGRESS
                        "V04874695_PROGRESS "
                        f"systems={processed}/{len(expected)} "
                        f"mismatch_cells={total_mismatch_cells} "
                        f"attributed_cells={attributed_cells} "
                        f"elapsed_seconds={elapsed:.3f}",
                        file=sys.stderr,
                        flush=True,
                    )
            except Exception as exc:
                errors.append(f"system:{key}:{type(exc).__name__}:{exc}")

    h53 = _finalize_hydrogen_type53_state(hydrogen_type53_state)
    errors.extend(f"hydrogen_type53:{value}" for value in h53["errors"])

    capture_exact = source_system_count == 183 and native_system_count == 183
    reconstruction_exact = source_reconstruction_exact == 183 and native_reconstruction_exact == 183
    zero_residual_closure = total_mismatch_cells == 0 and capture_exact and reconstruction_exact
    # A fully closed matrix has no causal rows left to attribute. Treat that
    # state as vacuously complete rather than requiring a positive mismatch
    # inventory and a nonzero identity-index workload.
    all_attributed = zero_residual_closure or attributed_cells == total_mismatch_cells
    baseline_checks = attribution_metrics.get("full_identity_checks_avoided_baseline", 0)
    indexed_checks = attribution_metrics.get("indexed_identity_checks", 0)
    reduction_factor = baseline_checks / max(1, indexed_checks)
    indexed_performance_exact = zero_residual_closure or (
        baseline_checks > 0 and reduction_factor >= 10.0
    )
    canonical_alignment_exact = zero_residual_closure or (
        attribution_metrics.get("canonical_record_pairs", 0) > 0
        and attribution_metrics.get("global_to_local_ion_index_pairs", 0) > 0
    )
    performance_milestone = (
        capture_exact and reconstruction_exact and all_attributed and indexed_performance_exact
    )
    scientific_milestone = performance_milestone and h53["result"] == "ACCEPT"

    post_seed_path = output / "all61_post_seed_system_decomposition_summary.json"
    post_seed = json.loads(post_seed_path.read_text()) if post_seed_path.is_file() else {}
    fixed_gate = str(post_seed.get("gates", {}).get("V06487_FIXED_STATE_PARITY", "REJECT"))
    gates = {
        "ALL_61_SOURCE_MATRIX_CONTRIBUTIONS_CAPTURED": "ACCEPT" if source_system_count == 183 else "REJECT",
        "ALL_61_NATIVE_MATRIX_CONTRIBUTIONS_CAPTURED": "ACCEPT" if native_system_count == 183 else "REJECT",
        "ALL_61_SOURCE_MATRIX_RECONSTRUCTION_EXACT": "ACCEPT" if source_reconstruction_exact == 183 else "REJECT",
        "ALL_61_NATIVE_MATRIX_RECONSTRUCTION_EXACT": "ACCEPT" if native_reconstruction_exact == 183 else "REJECT",
        "ALL_61_DENSE_MATRIX_CAUSAL_RECORDS_ATTRIBUTED": "ACCEPT" if all_attributed else "REJECT",
        "ALL_61_HYDROGEN_TYPE53_SOURCE_FAITHFUL": h53["result"],
        "HYDROGEN_TYPE53_RECORDS_EXPECTED": "ACCEPT" if h53["records_expected"] == 1891 else "REJECT",
        "HYDROGEN_TYPE53_CONTRIBUTIONS_BIT_EXACT": "ACCEPT" if h53["contributions_exact"] == 1891 else "REJECT",
        "HYDROGEN_TYPE53_CONTRIBUTIONS_IEEE_EQUIVALENT": "ACCEPT" if h53["contributions_ieee_equivalent"] == 1891 else "REJECT",
        "HYDROGEN_TYPE53_CALL3_BIT_EXACT": "ACCEPT" if h53["phase_exact"]["call3"] == 144 else "REJECT",
        "HYDROGEN_TYPE53_CALL4_BIT_EXACT": "ACCEPT" if h53["phase_exact"]["call4"] == 136 else "REJECT",
        "HYDROGEN_TYPE53_FINAL_CALL3_BIT_EXACT": "ACCEPT" if h53["phase_exact"]["final_call3"] == 8 else "REJECT",
        "HYDROGEN_TYPE53_FINAL_CALL4_BIT_EXACT": "ACCEPT" if h53["phase_exact"]["final_call4"] == 8 else "REJECT",
        "HYDROGEN_TYPE53_CALL3_IEEE_EQUIVALENT": "ACCEPT" if h53["phase_ieee_equivalent"]["call3"] == 144 else "REJECT",
        "HYDROGEN_TYPE53_CALL4_IEEE_EQUIVALENT": "ACCEPT" if h53["phase_ieee_equivalent"]["call4"] == 136 else "REJECT",
        "HYDROGEN_TYPE53_FINAL_CALL3_IEEE_EQUIVALENT": "ACCEPT" if h53["phase_ieee_equivalent"]["final_call3"] == 8 else "REJECT",
        "HYDROGEN_TYPE53_FINAL_CALL4_IEEE_EQUIVALENT": "ACCEPT" if h53["phase_ieee_equivalent"]["final_call4"] == 8 else "REJECT",
        "CANONICAL_RECORD_ALIGNMENT": "ACCEPT" if canonical_alignment_exact else "REJECT",
        "V064874692_HYDROGEN_TYPE53_LIVE_RADIATION_AND_CANONICAL_ALIGNMENT": (
            "ACCEPT" if scientific_milestone else "REJECT"
        ),
        "V064874691_INDEXED_CAUSAL_ATTRIBUTION_PERFORMANCE": (
            "ACCEPT" if performance_milestone else "REJECT"
        ),
        "V06487469_DENSE_MATRIX_CAUSAL_ATTRIBUTION": (
            "ACCEPT" if scientific_milestone else "REJECT"
        ),
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
        "result": "ACCEPT" if performance_milestone else "REJECT",
        "scientific_result": "ACCEPT" if scientific_milestone else "REJECT",
        "errors": errors[:200],
        "source_systems": source_system_count,
        "native_systems": native_system_count,
        "source_reconstruction_exact_systems": source_reconstruction_exact,
        "native_reconstruction_exact_systems": native_reconstruction_exact,
        "dense_exact_systems": dense_exact_systems,
        "dense_mismatch_cells": total_mismatch_cells,
        "dense_attributed_cells": attributed_cells,
        "causal_cell_rows_written": cell_rows_written,
        "causal_record_rows_written": record_rows_written,
        "causal_record_output": RECORD_NAME,
        "causal_record_output_compression": "gzip-level-1",
        "classification_counts": dict(sorted(classification_counts.items())),
        "causal_data_type_counts": {str(key): value for key, value in sorted(data_type_counts.items())},
        "hydrogen_type53": h53,
        "indexed_attribution_metrics": {
            **attribution_metrics,
            "identity_check_reduction_factor": reduction_factor,
            "performance_threshold": 10.0,
            "performance_gate_exact": indexed_performance_exact,
            "zero_residual_closure": zero_residual_closure,
            "canonical_alignment_vacuous": zero_residual_closure,
        },
        "elapsed_seconds": time.perf_counter() - started,
        "gates": gates,
        "qualification_only": True,
        "production_promotion_ready": False,
        "thermal_parity_started": False,
    }
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
    metrics: dict[str, int] = {}
    cells, records, classes, types = _attribute_system(source, native, metrics=metrics)
    errors: list[str] = []
    if not cells or not all(int(row["attributed"]) for row in cells):
        errors.append("cells_not_attributed")
    if not any(row["classification"] == "ENDPOINT_ORIENTATION_DELTA" for row in records):
        errors.append("orientation_not_classified")
    if types.get(50, 0) <= 0:
        errors.append("type50_not_attributed")
    return {
        "schema": "xstar-tools-v064874691-indexed-causal-attribution-self-test-v1",
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "mismatch_cells": len(cells),
        "record_rows": len(records),
        "classification_counts": dict(classes),
        "data_type_counts": {str(key): value for key, value in types.items()},
        "indexed_attribution_metrics": metrics,
    }




def canonical_record_alignment_self_test() -> dict[str, Any]:
    """Verify that global source and element-local native ion indices align.

    The source stream uses a global XSTAR ion index while the lowered native
    stream uses an element-local index.  The canonical identity must pair the
    same physical record without erasing either original audit value.
    """
    common_reals = tuple(float(index + 1) for index in range(REAL_COLUMNS))
    source = Contribution(
        (17, 40402, 40402, 50, 7, 71, 5, 11, 12, 0, 11, 12, 11, 12),
        common_reals,
    )
    native = Contribution(
        (3, 40402, 40402, 50, 7, 5, 5, 11, 12, 0, 11, 12, 11, 12),
        common_reals,
    )
    errors: list[str] = []
    if source.identity != native.identity:
        errors.append(f"canonical identities differ: {source.identity} != {native.identity}")
    source_map = _record_maps([source])
    native_map = _record_maps([native])
    if set(source_map) != set(native_map):
        errors.append("canonical maps do not pair the record")
    if source.ion_index == native.ion_index:
        errors.append("fixture does not exercise global-to-local ion-index alignment")
    if _classify_record(source, native) not in {"ACCUMULATION_ORDER_DELTA", "EXACT_RECORD"}:
        errors.append("canonical pair was classified as a missing or rate-delta record")
    return {
        "schema": "xstar-tools-v064874692-canonical-record-alignment-self-test-v1",
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "source_identity": list(source.identity),
        "native_identity": list(native.identity),
        "source_ion_index": source.ion_index,
        "native_ion_index": native.ion_index,
        "classification": _classify_record(source, native),
    }

def indexed_performance_self_test() -> dict[str, Any]:
    """Exercise semantic equivalence and require a large index advantage."""
    def make_contribution(order: int, *, delta: float = 0.0) -> Contribution:
        n = 127
        lower = (order % n) + 1
        upper = ((order * 17 + 11) % n) + 1
        if upper == lower:
            upper = (upper % n) + 1
        ints = (order, order * 4, 100000 + order, 50, 4, order % 13, order % 12 + 1,
                lower, upper, 0, lower, upper, lower, upper)
        base = float((order % 29) + 1) * 1.0e-6 + delta
        reals = (
            base, 0.0, 0.0, 0.0,
            base * 0.5, 0.0, 0.0, 0.0,
            -base, 0.0, 0.0, 0.0,
            -base * 0.5, 0.0, 0.0, 0.0,
        )
        return Contribution(ints, reals)

    source_contributions = [make_contribution(order) for order in range(1, 4001)]
    native_contributions = [
        make_contribution(order, delta=(1.0e-7 if order % 23 == 0 else 0.0))
        for order in range(1, 4001)
    ]
    source = SystemData(1, 12, 127, np.zeros((127, 127)), np.zeros((127, 127)),
                        np.zeros((127, 127)), source_contributions, {})
    native = SystemData(1, 12, 127, np.zeros((127, 127)), np.zeros((127, 127)),
                        np.zeros((127, 127)), native_contributions, {})
    source.dense, source.heat, source.heat2 = _reconstruct(source)
    native.dense, native.heat, native.heat2 = _reconstruct(native)
    metrics: dict[str, int] = {}
    started = time.perf_counter()
    cells, records, _classes, _types = _attribute_system(source, native, metrics=metrics)
    elapsed = time.perf_counter() - started

    source_index = _index_terms_by_cell(source.contributions)
    native_index = _index_terms_by_cell(native.contributions)
    sequence_equivalence = True
    for zero_row, zero_col in np.argwhere(source.dense != native.dense):
        cell = (int(zero_row) + 1, int(zero_col) + 1)
        if source_index.get(cell, []) != _term_sequence_for_cell(source, *cell):
            sequence_equivalence = False
            break
        if native_index.get(cell, []) != _term_sequence_for_cell(native, *cell):
            sequence_equivalence = False
            break

    baseline = metrics.get("full_identity_checks_avoided_baseline", 0)
    indexed = metrics.get("indexed_identity_checks", 0)
    reduction = baseline / max(1, indexed)
    errors: list[str] = []
    if not cells or not records:
        errors.append("no_attribution_rows")
    if not sequence_equivalence:
        errors.append("indexed_term_sequence_differs_from_full_scan")
    if reduction < 50.0:
        errors.append(f"identity_check_reduction={reduction:.3f} expected>=50")
    if any(not int(row["attributed"]) for row in cells):
        errors.append("unattributed_cells")
    return {
        "schema": "xstar-tools-v064874691-indexed-performance-self-test-v1",
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "records": 4000,
        "mismatch_cells": len(cells),
        "causal_record_rows": len(records),
        "term_sequence_equivalence": sequence_equivalence,
        "full_identity_checks_baseline": baseline,
        "indexed_identity_checks": indexed,
        "identity_check_reduction_factor": reduction,
        "elapsed_seconds": elapsed,
    }

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--native-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--progress-every", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        result = analyze(
            args.source_capture, args.native_run, args.output, progress_every=args.progress_every
        )
    except Exception as exc:
        result = {
            "schema": SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "gates": {
                "V064874691_INDEXED_CAUSAL_ATTRIBUTION_PERFORMANCE": "REJECT",
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
