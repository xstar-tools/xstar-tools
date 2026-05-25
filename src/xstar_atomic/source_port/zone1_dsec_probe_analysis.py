"""Memory-safe post-processing for the v0.4.79 zone-1/type-15 probe."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import struct
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Iterator, Mapping, Sequence

from .dsec import DsecPortError, load_xstar_dsec_trajectory
from .fortran_numbers import parse_fortran_float
from .zone1_dsec_diagnostic import (
    TARGET_CV_LOCAL_LEVELS,
    TARGET_TEMPERATURE_K,
    carbon_cooling_rows,
    compare_cooling_terms,
    enforce_cooling_gate,
)


def _iter_rows(path: Path) -> Iterator[dict[str, str]]:
    """Yield CSV rows without materializing the complete probe file.

    Several original-XSTAR probe products contain full-capacity arrays for
    every DSEC evaluation and can contain tens of millions of rows.  Keeping
    ``list(csv.DictReader(...))`` copies of those products is unnecessary and
    can cause the Linux OOM killer to terminate the analyzer.
    """
    if not path.is_file():
        raise DsecPortError(f"missing zone-1 probe product: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def _read(path: Path) -> list[dict[str, str]]:
    """Read a bounded analysis product into memory.

    Raw original-XSTAR probe products must be consumed with ``_iter_rows``.
    This helper remains appropriate for the compact derived CSV products used
    by the final comparator.
    """
    return list(_iter_rows(path))


def _read_optional(path: Path) -> list[dict[str, str]]:
    """Read a bounded optional diagnostic product, returning an empty list."""
    if not path.is_file():
        return []
    return list(_iter_rows(path))


_STATE_PHASE_NAMES = {
    10: "calc_hmc_all_entry_hydrogen",
    20: "calc_hmc_all_map_global_to_element_entry",
    21: "calc_hmc_all_map_global_to_hydrogen_entry",
    25: "calc_hmc_all_preliminary_hydrogen_rates",
    30: "calc_hmc_element_pre_msolvelucy",
    40: "msolvelucy_outer_start",
    41: "msolvelucy_outer_start_xtot",
    50: "msolvelucy_post_condensed",
    60: "msolvelucy_fixed_point_after_normalization",
    70: "msolvelucy_post_fixed_point_outer",
    80: "msolvelucy_final_vector",
    90: "msolvelucy_final_outer_start_xtot",
    100: "calc_hmc_element_final_vector_xii",
    110: "calc_hmc_element_workspace_writeback",
    120: "calc_hmc_all_global_writeback",
    130: "calc_hmc_all_alias_boundary",
    140: "calc_hmc_all_element_electron_contribution",
}



def _write(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _call_map(root: Path) -> dict[int, int]:
    rows = _iter_rows(root / "xstar_dsec_calc_hmc_all_call_correlation.csv")
    return {
        int(row["calc_hmc_all_call_id"]): int(row["dsec_evaluation_index"])
        for row in rows
        if int(row["dsec_call_id"]) == 1
        and str(row["phase"]).strip() == "dsec_internal"
    }


def _sha_rows(rows: Iterable[tuple[int, float | int | str]]) -> str:
    sha = hashlib.sha256()
    for index, value in rows:
        sha.update(struct.pack("<q", int(index)))
        if isinstance(value, str):
            encoded = value.encode("utf-8")
            sha.update(struct.pack("<q", len(encoded)))
            sha.update(encoded)
        elif isinstance(value, int):
            sha.update(struct.pack("<q", value))
        else:
            sha.update(struct.pack("<d", float(value)))
    return sha.hexdigest()


def _fingerprint(
    *,
    call: int,
    evaluation: int,
    name: str,
    values: Sequence[tuple[int, float | int | str]],
) -> dict[str, Any]:
    numeric = [float(value) for _, value in values if not isinstance(value, str)]
    return {
        "evaluation_index": int(evaluation),
        "call_id": int(call),
        "name": name,
        "count": len(values),
        "nonzero_count": sum(value != 0.0 for value in numeric),
        "finite_count": sum(math.isfinite(value) for value in numeric),
        "minimum": min(numeric) if numeric else math.nan,
        "maximum": max(numeric) if numeric else math.nan,
        "total": sum(numeric) if numeric else math.nan,
        "total_abs": sum(abs(value) for value in numeric) if numeric else math.nan,
        "total_square": sum(value * value for value in numeric) if numeric else math.nan,
        "weighted_total": (
            sum(index * float(value) for index, value in values if not isinstance(value, str))
            if numeric
            else math.nan
        ),
        "first": values[0][1] if values else math.nan,
        "last": values[-1][1] if values else math.nan,
        "sha256": _sha_rows(values),
    }


class _FingerprintAccumulator:
    """Incremental equivalent of ``_fingerprint`` for one logical array."""

    __slots__ = (
        "count",
        "nonzero_count",
        "finite_count",
        "minimum",
        "maximum",
        "total",
        "total_abs",
        "total_square",
        "weighted_total",
        "first",
        "last",
        "sha",
        "has_numeric",
    )

    def __init__(self) -> None:
        self.count = 0
        self.nonzero_count = 0
        self.finite_count = 0
        self.minimum = math.nan
        self.maximum = math.nan
        self.total = 0.0
        self.total_abs = 0.0
        self.total_square = 0.0
        self.weighted_total = 0.0
        self.first: float | int | str = math.nan
        self.last: float | int | str = math.nan
        self.sha = hashlib.sha256()
        self.has_numeric = False

    def add(self, index: int, value: float | int | str) -> None:
        if self.count == 0:
            self.first = value
        self.last = value
        self.count += 1
        self.sha.update(struct.pack("<q", int(index)))
        if isinstance(value, str):
            encoded = value.encode("utf-8")
            self.sha.update(struct.pack("<q", len(encoded)))
            self.sha.update(encoded)
            return
        if isinstance(value, int):
            self.sha.update(struct.pack("<q", value))
        else:
            self.sha.update(struct.pack("<d", float(value)))
        numeric = float(value)
        if not self.has_numeric:
            self.minimum = numeric
            self.maximum = numeric
            self.has_numeric = True
        else:
            # Preserve the ordered Python min/max behavior used by the old
            # list implementation, including any leading NaN semantics.
            self.minimum = min(self.minimum, numeric)
            self.maximum = max(self.maximum, numeric)
        self.nonzero_count += int(numeric != 0.0)
        self.finite_count += int(math.isfinite(numeric))
        self.total += numeric
        self.total_abs += abs(numeric)
        self.total_square += numeric * numeric
        self.weighted_total += int(index) * numeric

    def finish(self, *, call: int, evaluation: int, name: str) -> dict[str, Any]:
        return {
            "evaluation_index": int(evaluation),
            "call_id": int(call),
            "name": name,
            "count": self.count,
            "nonzero_count": self.nonzero_count,
            "finite_count": self.finite_count,
            "minimum": self.minimum if self.has_numeric else math.nan,
            "maximum": self.maximum if self.has_numeric else math.nan,
            "total": self.total if self.has_numeric else math.nan,
            "total_abs": self.total_abs if self.has_numeric else math.nan,
            "total_square": self.total_square if self.has_numeric else math.nan,
            "weighted_total": self.weighted_total if self.has_numeric else math.nan,
            "first": self.first,
            "last": self.last,
            "sha256": self.sha.hexdigest(),
        }


def _numeric_fingerprint_rows(
    root: Path,
    call_to_eval: Mapping[int, int],
    *,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Fingerprint raw probe arrays in one pass with bounded memory.

    v0.4.79 materialized each complete full-capacity CSV and then retained a
    second grouped list of every value.  The continuum/escape probe products
    can therefore require several gigabytes.  This implementation retains only
    one small accumulator for each ``(call, canonical_name)`` pair.
    """
    specs = [
        (
            "xstar_calc_hmc_all_input_continuum_probe.csv",
            "grid_index",
            {
                "epi_eV": "radiation.epim",
                "bremsa": "radiation.bremsam",
                "bremsint": "radiation.bremsint",
            },
        ),
        (
            "xstar_calc_hmc_all_input_tau0_probe.csv",
            "line_index",
            {"tau_in": "escape.line_tau_in", "tau_out": "escape.line_tau_out"},
        ),
        (
            "xstar_calc_hmc_all_input_tauc_probe.csv",
            "continuum_index",
            {
                "tau_in": "escape.continuum_tau_in",
                "tau_out": "escape.continuum_tau_out",
            },
        ),
        (
            "xstar_calc_hmc_all_input_global_levels_probe.csv",
            "global_level_index",
            {
                "xilevg": "global_xilevg_by_index",
                "bilevg": "global_bilevg_by_index",
                "rnisg": "global_rnisg_by_index",
            },
        ),
        (
            "xstar_calc_hmc_all_input_leveltemp_probe.csv",
            "row_index",
            {"rlev": "leveltemp_workspace.rlev", "ilev": "leveltemp_workspace.ilev"},
        ),
        (
            "xstar_zone1_calc_hmc_all_input_elements_probe.csv",
            "element_index",
            {
                "abundance": "element_requests.abundance",
                "mml": "element_requests.min_ion_stage",
                "mmu": "element_requests.max_ion_stage",
            },
        ),
    ]
    output: list[dict[str, Any]] = []
    for filename, index_name, fields in specs:
        probe_path = root / filename
        if progress is not None:
            progress(
                f"fingerprint_file_start file={filename} "
                f"size_bytes={probe_path.stat().st_size if probe_path.is_file() else -1}"
            )
        grouped: Dict[tuple[int, str], _FingerprintAccumulator] = {}
        n_rows = 0
        for position, row in enumerate(_iter_rows(probe_path), start=1):
            n_rows = position
            call = int(row["calc_hmc_all_call_id"])
            if call not in call_to_eval:
                continue
            logical_index = (
                (int(row["column_index"]) - 1) * 10 + int(row["slot"])
                if filename.endswith("leveltemp_probe.csv")
                else int(row.get(index_name, position))
            )
            for field, canonical_name in fields.items():
                value: float | int
                if field in {"ilev", "mml", "mmu"}:
                    value = int(row[field])
                else:
                    value = parse_fortran_float(row[field])
                group_key = (call, canonical_name)
                accumulator = grouped.get(group_key)
                if accumulator is None:
                    accumulator = _FingerprintAccumulator()
                    grouped[group_key] = accumulator
                accumulator.add(logical_index, value)
        for (call, name), accumulator in sorted(grouped.items()):
            output.append(
                accumulator.finish(
                    call=call,
                    evaluation=call_to_eval[call],
                    name=name,
                )
            )
        if progress is not None:
            progress(
                f"fingerprint_file_done file={filename} rows={n_rows} "
                f"groups={len(grouped)}"
            )

    klev_path = root / "xstar_zone1_calc_hmc_all_input_klev_probe.csv"
    if progress is not None:
        progress(
            "fingerprint_file_start "
            f"file={klev_path.name} "
            f"size_bytes={klev_path.stat().st_size if klev_path.is_file() else -1}"
        )
    grouped_klev: Dict[int, _FingerprintAccumulator] = {}
    n_klev_rows = 0
    for row in _iter_rows(klev_path):
        n_klev_rows += 1
        call = int(row["calc_hmc_all_call_id"])
        if call in call_to_eval:
            accumulator = grouped_klev.get(call)
            if accumulator is None:
                accumulator = _FingerprintAccumulator()
                grouped_klev[call] = accumulator
            accumulator.add(int(row["column_index"]), row["klev_hex"])
    for call, accumulator in sorted(grouped_klev.items()):
        output.append(
            accumulator.finish(
                call=call,
                evaluation=call_to_eval[call],
                name="leveltemp_workspace.klev",
            )
        )
    if progress is not None:
        progress(
            f"fingerprint_file_done file={klev_path.name} rows={n_klev_rows} "
            f"groups={len(grouped_klev)}"
        )

    scalar_fields = (
        "temperature_t4",
        "temperature_k",
        "trad",
        "radius_cm",
        "zone_thickness_cm",
        "electron_fraction_xee",
        "hydrogen_density_cm3",
        "covering_fraction",
        "pressure",
        "lcdd",
        "zeta",
        "turbulent_velocity_km_s",
        "critf",
        "ncn2",
    )
    for row in _iter_rows(root / "xstar_calc_hmc_all_input_summary_probe.csv"):
        call = int(row["calc_hmc_all_call_id"])
        if call not in call_to_eval:
            continue
        accumulator = _FingerprintAccumulator()
        for index, field in enumerate(scalar_fields, start=1):
            value: float | int
            if field in {"lcdd", "ncn2"}:
                value = int(row[field])
            else:
                value = parse_fortran_float(row[field])
            accumulator.add(index, value)
        output.append(
            accumulator.finish(
                call=call,
                evaluation=call_to_eval[call],
                name="runtime_scalars",
            )
        )
    return sorted(output, key=lambda row: (row["evaluation_index"], row["name"]))

def load_xstar_target_state(
    probe_dir: str | Path,
    *,
    target_temperature_k: float = TARGET_TEMPERATURE_K,
) -> dict[str, Any]:
    root = Path(probe_dir)
    call_to_eval = _call_map(root)
    summaries = _iter_rows(root / "xstar_calc_hmc_all_input_summary_probe.csv")
    candidates = [
        row
        for row in summaries
        if int(row["calc_hmc_all_call_id"]) in call_to_eval
    ]
    if not candidates:
        raise DsecPortError("zone-1 original probe has no correlated DSEC inputs")
    selected = min(
        candidates,
        key=lambda row: abs(
            parse_fortran_float(row["temperature_k"]) - target_temperature_k
        ),
    )
    call = int(selected["calc_hmc_all_call_id"])
    return {
        "call_id": call,
        "evaluation_index": int(call_to_eval[call]),
        "temperature_K": parse_fortran_float(selected["temperature_k"]),
        "electron_fraction_xee": parse_fortran_float(
            selected["electron_fraction_xee"]
        ),
        "hydrogen_density_cm3": parse_fortran_float(
            selected["hydrogen_density_cm3"]
        ),
    }


def load_xstar_carbon_cooling_terms(
    probe_dir: str | Path,
) -> list[dict[str, Any]]:
    root = Path(probe_dir)
    call_to_eval = _call_map(root)
    rows = _iter_rows(root / "xstar_zone1_calc_hmc_all_thermal_terms_probe.csv")
    output: list[dict[str, Any]] = []
    for row in rows:
        call = int(row["calc_hmc_all_call_id"])
        if call not in call_to_eval or int(row["element_z"]) != 6:
            continue
        output.append(
            {
                "evaluation_index": call_to_eval[call],
                "call_id": call,
                "record": int(row["record"]),
                "term_index": int(row["term_index"]),
                "row": int(row["row"]),
                "column": int(row["column"]),
                "data_type": int(row["data_type"]),
                "rate_type": int(row["rate_type"]),
                "population": parse_fortran_float(row["population"]),
                "cj": parse_fortran_float(row["cj"]),
                "cj2": parse_fortran_float(row["cj2"]),
                "cooling_contribution": parse_fortran_float(
                    row["cooling_contribution"]
                ),
                "cooling2_contribution": parse_fortran_float(
                    row["cooling2_contribution"]
                ),
            }
        )
    return output


def make_carbon_cooling_gate(
    probe_dir: str | Path,
    *,
    rtol: float = 5.0e-5,
    atol: float = 1.0e-30,
):
    """Return a fail-fast gate called before DSEC commits each trial state."""
    reference = load_xstar_carbon_cooling_terms(probe_dir)
    by_evaluation: Dict[int, list[dict[str, Any]]] = {}
    for row in reference:
        by_evaluation.setdefault(int(row["evaluation_index"]), []).append(row)

    def gate(evaluation_index: int, snapshot: Any, result: Any) -> None:
        xstar_rows = by_evaluation.get(int(evaluation_index), [])
        if not xstar_rows:
            raise DsecPortError(
                "zone-1 carbon cooling gate lacks original evaluation "
                f"{evaluation_index}"
            )
        python_rows = carbon_cooling_rows(
            result, evaluation_index=int(evaluation_index)
        )
        comparison = compare_cooling_terms(
            python_rows, xstar_rows, rtol=rtol, atol=atol
        )
        enforce_cooling_gate(comparison)

    return gate


def _format_float_sequence(values: Sequence[float]) -> str:
    return ";".join(f"{float(value):.17e}" for value in values)


def _parse_float_sequence(value: str | None) -> tuple[float, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    return tuple(parse_fortran_float(item) for item in text.split(";") if item.strip())


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}




def _load_type15_probe_rows(
    root: Path,
    *,
    target_call: int,
    civ_raw: Sequence[Mapping[str, str]],
    progress: Callable[[str], None] | None = None,
) -> tuple[dict[int, list[dict[str, str]]], dict[tuple[int, int], dict[str, str]]]:
    """Load data-type-15 shell/call-site probes only when applicable.

    The original-XSTAR helper creates these CSV files lazily.  A selected
    C IV record with ``rate_type == 15`` is not necessarily data type 15
    (the current case contains data type 95/rate type 15).  Therefore the
    absence of the two data-type-15 files is valid when no selected C IV
    record has ``data_type == 15``.  When such a record is present, both
    files remain mandatory and a missing file is a real probe-contract
    failure.
    """
    selected_records = {
        int(row["record"])
        for row in civ_raw
        if int(row["data_type"]) == 15
    }
    if not selected_records:
        if progress is not None:
            progress(
                "type15_probe_not_applicable "
                "selected_civ_data_type15_records=0"
            )
        return {}, {}

    if progress is not None:
        progress(
            "type15_probe_required "
            f"selected_civ_data_type15_records={len(selected_records)}"
        )
    shell_rows = [
        row
        for row in _iter_rows(root / "xstar_zone1_type15_shell_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["record"]) in selected_records
    ]
    shells_by_record: Dict[int, list[dict[str, str]]] = {}
    for row in shell_rows:
        shells_by_record.setdefault(int(row["record"]), []).append(row)
    for values in shells_by_record.values():
        values.sort(key=lambda row: int(row["shell_index"]))

    effective_rows = [
        row
        for row in _iter_rows(root / "xstar_zone1_type15_effective_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["record"]) in selected_records
    ]
    effective_by_record_phase = {
        (int(row["record"]), int(row["phase"])): row
        for row in effective_rows
    }
    return shells_by_record, effective_by_record_phase

def analyze_xstar_zone1_probe(
    probe_dir: str | Path,
    *,
    out_dir: str | Path,
    target_temperature_k: float = TARGET_TEMPERATURE_K,
    include_input_fingerprints: bool = True,
    progress: Callable[[str], None] | None = None,
) -> Mapping[str, Path]:
    root = Path(probe_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    call_to_eval = _call_map(root)

    trajectory = load_xstar_dsec_trajectory(root, call_id=1)
    sequence_rows = [
        {
            "evaluation_index": event.evaluation_index,
            "temperature_K": event.temperature_k,
            "electron_fraction_xee": event.electron_fraction_xee,
            "hmctot": event.hmctot,
            "elcter": event.elcter,
            "ntotit": event.ntotit,
            "nnt": event.nnt,
            "nntt": event.nntt,
            "event": event.event,
        }
        for event in trajectory.events
        if event.event == "after_calc_hmc_all"
    ]
    sequence_path = out / "xstar_zone1_dsec_evaluation_sequence.csv"
    _write(sequence_path, sequence_rows)

    if include_input_fingerprints:
        if progress is not None:
            progress("input_fingerprint_stage_start")
        fingerprints = _numeric_fingerprint_rows(
            root, call_to_eval, progress=progress
        )
        if progress is not None:
            progress(
                f"input_fingerprint_stage_done fingerprints={len(fingerprints)}"
            )
    else:
        fingerprints = []
        if progress is not None:
            progress("input_fingerprint_stage_skipped")
    fingerprints_path = out / "xstar_zone1_calc_hmc_all_input_fingerprints.csv"
    _write(fingerprints_path, fingerprints)

    if progress is not None:
        progress("target_state_analysis_start")
    target_state = load_xstar_target_state(
        root, target_temperature_k=target_temperature_k
    )
    target_call = int(target_state["call_id"])
    target_eval = int(target_state["evaluation_index"])

    pre = [
        row
        for row in _iter_rows(root / "xstar_calc_hmc_element_pre_matrix_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["element_z"]) == 6
    ]
    second = [
        row
        for row in _iter_rows(
            root / "xstar_zone1_calc_hmc_all_second_pass_rates_probe.csv"
        )
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["element_z"]) == 6
    ]
    second_by_stage = {int(row["ion_stage"]): row for row in second}
    rate_rows: list[dict[str, Any]] = []
    for row in pre:
        stage = int(row["ion_stage"])
        if stage not in {4, 5, 6}:
            continue
        srow = second_by_stage.get(stage)
        rate_rows.append(
            {
                "source": "xstar",
                "evaluation_index": target_eval,
                "call_id": target_call,
                "temperature_K": target_state["temperature_K"],
                "electron_fraction_xee": target_state["electron_fraction_xee"],
                "hydrogen_density_cm3": target_state["hydrogen_density_cm3"],
                "ion_stage": stage,
                "preliminary_ion_fraction": parse_fortran_float(row["xitp"]),
                "preliminary_photoionization_rate": parse_fortran_float(
                    row["pirt"]
                ),
                "preliminary_recombination_rate": parse_fortran_float(
                    row["rrrt"]
                ),
                "second_pass_photoionization_rate": 0.0
                if srow is None
                else parse_fortran_float(srow["pirt"]),
                "second_pass_recombination_rate": 0.0
                if srow is None
                else parse_fortran_float(srow["rrrt"]),
            }
        )
    rates_path = out / "xstar_zone1_carbon_rates_T73198p4K.csv"
    _write(rates_path, rate_rows)

    civ_raw = [
        row for row in _iter_rows(root / "xstar_zone1_civ_calc_ion_rates_records_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
    ]
    shells_by_record, effective_by_record_phase = _load_type15_probe_rows(
        root, target_call=target_call, civ_raw=civ_raw, progress=progress
    )
    civ_records: list[dict[str, Any]] = []
    for row in civ_raw:
        record = int(row["record"])
        shells = shells_by_record.get(record, [])
        final_shell = next(
            (item for item in reversed(shells) if int(item["is_final"]) == 1),
            shells[-1] if shells else None,
        )
        bkhsgo_row = effective_by_record_phase.get((record, 1))
        phintfo_row = effective_by_record_phase.get((record, 2))
        civ_records.append(
            {
                "source": "xstar",
                "evaluation_index": target_eval,
                "call_id": target_call,
                "element_z": int(row["element_z"]),
                "ion_stage": int(row["ion_stage"]),
                "ion_index": int(row["ion_index"]),
                "record": record,
                "data_type": int(row["data_type"]),
                "rate_type": int(row["rate_type"]),
                "status": "evaluated",
                "parent_record": int(row["parent_record"]),
                "parent_threshold_ev": parse_fortran_float(row["parent_threshold_ev"]),
                "shell_thresholds_ev": _format_float_sequence(
                    parse_fortran_float(item["shell_threshold_ev"]) for item in shells
                ),
                "shell_d_values": _format_float_sequence(
                    parse_fortran_float(item["shell_d"]) for item in shells
                ),
                "final_effective_threshold_ev": math.nan if final_shell is None else parse_fortran_float(final_shell["shell_threshold_ev"]),
                "final_effective_d": math.nan if final_shell is None else parse_fortran_float(final_shell["shell_d"]),
                "bkhsgo_threshold_ev": math.nan if bkhsgo_row is None else parse_fortran_float(bkhsgo_row["effective_threshold_ev"]),
                "bkhsgo_effective_d": math.nan if bkhsgo_row is None else parse_fortran_float(bkhsgo_row["effective_d"]),
                "phintfo_threshold_ev": math.nan if phintfo_row is None else parse_fortran_float(phintfo_row["effective_threshold_ev"]),
                "phintfo_effective_d": math.nan if phintfo_row is None else parse_fortran_float(phintfo_row["effective_d"]),
                "ans1": parse_fortran_float(row["ans1"]),
                "ans2": parse_fortran_float(row["ans2"]),
                "ans3": parse_fortran_float(row["ans3"]),
                "ans4": parse_fortran_float(row["ans4"]),
                "ans5": parse_fortran_float(row["ans5"]),
                "ans6": parse_fortran_float(row["ans6"]),
                "pirti_before": parse_fortran_float(row["pirti_before"]),
                "pirti_contribution": parse_fortran_float(row["pirti_contribution"]),
                "pirti_after": parse_fortran_float(row["pirti_after"]),
                "rrrti_before": parse_fortran_float(row["rrrti_before"]),
                "rrrti_contribution": parse_fortran_float(row["rrrti_contribution"]),
                "rrrti_after": parse_fortran_float(row["rrrti_after"]),
                "idest1": int(row["idest1"]),
                "idest2": int(row["idest2"]),
            }
        )
    civ_records_path = out / "xstar_zone1_civ_calc_ion_rates_records_T73198p4K.csv"
    _write(civ_records_path, civ_records)

    stage4 = next((row for row in pre if int(row["ion_stage"]) == 4), None)
    initial_raw = [
        row for row in _iter_rows(root / "xstar_calc_hmc_all_msolvelucy_initial_population_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["element_z"]) == 6
    ]
    initial_population_rows = [
        {
            "source": "xstar",
            "evaluation_index": target_eval,
            "compact_dimension": int(row["compact_dimension"]),
            "compact_index": int(row["compact_index"]),
            "population": parse_fortran_float(row["population"]),
        }
        for row in initial_raw
    ]
    initial_population_path = out / "xstar_zone1_carbon_initial_population_T73198p4K.csv"
    _write(initial_population_path, initial_population_rows)
    compact_dimension = (
        int(initial_raw[0]["compact_dimension"]) if initial_raw else 0
    )
    topology_rows = []
    if stage4 is not None:
        mml = int(stage4["mml"])
        mmu = int(stage4["mmu"])
        topology_rows.append(
            {
                "source": "xstar",
                "evaluation_index": target_eval,
                "element_z": 6,
                "critf": parse_fortran_float(stage4["critf"]),
                "civ_preliminary_fraction": parse_fortran_float(stage4["xitp"]),
                "selected_min_ion_stage": mml,
                "selected_max_ion_stage": mmu,
                "civ_retained": bool(mml <= 4 <= mmu),
                "compact_dimension": compact_dimension,
                "normalization_row": compact_dimension,
            }
        )
    topology_path = out / "xstar_zone1_carbon_topology_T73198p4K.csv"
    _write(topology_path, topology_rows)

    normalization_raw = [
        row for row in _iter_rows(root / "xstar_zone1_msolvelucy_normalization_row_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["element_z"]) == 6
    ]
    first_outer = min((int(row["outer_iteration"]) for row in normalization_raw), default=0)
    normalization_rows = [
        {
            "source": "xstar",
            "evaluation_index": target_eval,
            "outer_iteration": int(row["outer_iteration"]),
            "condensed_dimension": int(row["condensed_dimension"]),
            "normalization_row": int(row["normalization_row"]),
            "column": int(row["column"]),
            "matrix_value": parse_fortran_float(row["matrix_value"]),
            "rhs_value": parse_fortran_float(row["rhs_value"]),
        }
        for row in normalization_raw
        if int(row["outer_iteration"]) == first_outer
    ]
    normalization_path = out / "xstar_zone1_carbon_normalization_row_T73198p4K.csv"
    _write(normalization_path, normalization_rows)

    level_population_rows = [
        {
            "source": "xstar",
            "evaluation_index": target_eval,
            "element_z": int(row["element_z"]),
            "ion_stage": int(row["ion_stage"]),
            "ion_index": int(row["ion_index"]),
            "local_level": int(row["local_level"]),
            "compact_index": int(row["compact_index"]),
            "population": parse_fortran_float(row["population"]),
        }
        for row in _iter_rows(root / "xstar_zone1_carbon_level_population_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["ion_stage"]) == 5
        and int(row["local_level"]) in set(TARGET_CV_LOCAL_LEVELS)
    ]
    level_population_path = out / "xstar_zone1_cv_level_populations_T73198p4K.csv"
    _write(level_population_path, level_population_rows)

    records = [
        row
        for row in _iter_rows(root / "xstar_zone1_calc_hmc_all_rate_records_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["element_z"]) == 6
        and int(row["ion_stage"]) == 5
    ]
    target_levels = set(TARGET_CV_LOCAL_LEVELS)
    records = [
        row
        for row in records
        if target_levels.intersection(
            {int(row["idest1"]), int(row["idest2"])}
        )
    ]
    record_map = {int(row["record"]): row for row in records}
    matrix = [
        row
        for row in _iter_rows(root / "xstar_calc_hmc_all_matrix_terms_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["element_z"]) == 6
        and int(row["source_record"]) in record_map
    ]
    role_by_order = {
        1: "forward_offdiag",
        2: "reverse_offdiag",
        3: "forward_diag_loss",
        4: "reverse_diag_loss",
    }
    order_by_record: Dict[int, int] = {}
    matrix_rows: list[dict[str, Any]] = []
    for row in matrix:
        record = int(row["source_record"])
        order_by_record[record] = order_by_record.get(record, 0) + 1
        role_order = order_by_record[record]
        rr = record_map[record]
        touched = sorted(
            target_levels.intersection(
                {int(rr["idest1"]), int(rr["idest2"])}
            )
        )
        for local_level in touched:
            matrix_rows.append(
                {
                    "source": "xstar",
                    "evaluation_index": target_eval,
                    "call_id": target_call,
                    "element_z": 6,
                    "ion_stage": 5,
                    "local_level": local_level,
                    "record": record,
                    "data_type": int(rr["data_type"]),
                    "rate_type": int(rr["rate_type"]),
                    "role": role_by_order.get(role_order, f"term_{role_order}"),
                    "term_index": int(row["term_index"]),
                    "row": int(row["row_compact"]),
                    "column": int(row["column_compact"]),
                    "idest1": int(rr["idest1"]),
                    "idest2": int(rr["idest2"]),
                    "lower_endpoint": int(rr["lower_endpoint"]),
                    "upper_endpoint": int(rr["upper_endpoint"]),
                    "escape_factor_in": parse_fortran_float(
                        rr["escape_factor_in"]
                    ),
                    "escape_factor_out": parse_fortran_float(
                        rr["escape_factor_out"]
                    ),
                    "density_scale": parse_fortran_float(rr["density_scale"]),
                    "ans1": parse_fortran_float(rr["ans1"]),
                    "ans2": parse_fortran_float(rr["ans2"]),
                    "ans3": parse_fortran_float(rr["ans3"]),
                    "ans4": parse_fortran_float(rr["ans4"]),
                    "ans5": parse_fortran_float(rr["ans5"]),
                    "ans6": parse_fortran_float(rr["ans6"]),
                    "aj1": parse_fortran_float(row["aj1"]),
                    "aj2": parse_fortran_float(row["aj2"]),
                    "cj": parse_fortran_float(row["cj"]),
                    "cj2": parse_fortran_float(row["cj2"]),
                    "population": parse_fortran_float(row["row_population"]),
                    "cooling_contribution": parse_fortran_float(
                        row["row_population"]
                    )
                    * parse_fortran_float(row["cj"]),
                    "cooling2_contribution": parse_fortran_float(
                        row["row_population"]
                    )
                    * parse_fortran_float(row["cj2"]),
                }
            )
    matrix_path = out / "xstar_zone1_cv_matrix_levels_4_6_10_12_20.csv"
    _write(matrix_path, matrix_rows)

    all_rate_records = [
        row for row in _iter_rows(root / "xstar_zone1_calc_hmc_all_rate_records_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["element_z"]) == 6
    ]
    all_record_map = {int(row["record"]): row for row in all_rate_records}
    all_matrix = [
        row for row in _iter_rows(root / "xstar_calc_hmc_all_matrix_terms_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["element_z"]) == 6
    ]
    matrix_by_term = {int(row["term_index"]): row for row in all_matrix}
    role_order: Dict[int, int] = {}
    role_by_term: Dict[int, str] = {}
    for row in all_matrix:
        record = int(row["source_record"])
        role_order[record] = role_order.get(record, 0) + 1
        role_by_term[int(row["term_index"])] = role_by_order.get(
            role_order[record], f"term_{role_order[record]}"
        )
    thermal_raw = [
        row for row in _iter_rows(root / "xstar_zone1_calc_hmc_all_thermal_terms_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["element_z"]) == 6
    ]
    logical_cooling_rows: list[dict[str, Any]] = []
    for row in thermal_raw:
        term_index = int(row["term_index"])
        mrow = matrix_by_term.get(term_index)
        rr = all_record_map.get(int(row["record"]))
        if mrow is None or rr is None:
            continue
        logical_cooling_rows.append(
            {
                "source": "xstar",
                "evaluation_index": target_eval,
                "element_z": 6,
                "ion_stage": int(rr["ion_stage"]),
                "record": int(row["record"]),
                "data_type": int(row["data_type"]),
                "rate_type": int(row["rate_type"]),
                "role": role_by_term.get(term_index, ""),
                "idest1": int(rr["idest1"]),
                "idest2": int(rr["idest2"]),
                "lower_endpoint": int(rr["lower_endpoint"]),
                "upper_endpoint": int(rr["upper_endpoint"]),
                "population": parse_fortran_float(row["population"]),
                "cj": parse_fortran_float(row["cj"]),
                "cj2": parse_fortran_float(row["cj2"]),
                "cooling_contribution": parse_fortran_float(row["cooling_contribution"]),
                "cooling2_contribution": parse_fortran_float(row["cooling2_contribution"]),
            }
        )
    logical_cooling_path = out / "xstar_zone1_carbon_cooling_logical_T73198p4K.csv"
    _write(logical_cooling_path, logical_cooling_rows)

    cooling = load_xstar_carbon_cooling_terms(root)
    cooling_path = out / "xstar_zone1_carbon_cooling_terms.csv"
    _write(cooling_path, cooling)

    # v0.4.88 diagnostic-only source-order state path.  The full carbon
    # path remains target-evaluation scoped because it is intentionally heavy.
    # Hydrogen, electron-fraction, and lightweight carbon-correlation rows are
    # retained across all DSEC evaluations so the next comparison can find the
    # first differing evaluation rather than only the final target call.
    def _int_field(row: Mapping[str, str], field: str, default: int = 0) -> int:
        value = row.get(field, "")
        return default if value in ("", None) else int(float(str(value)))

    def _float_field(row: Mapping[str, str], field: str, default: float = 0.0) -> float:
        value = row.get(field, "")
        return default if value in ("", None) else parse_fortran_float(str(value))

    hydrogen_state_rows: list[dict[str, Any]] = []
    for row in _read_optional(root / "xstar_zone1_hydrogen_state_path_probe.csv"):
        call_id = _int_field(row, "calc_hmc_all_call_id")
        evaluation = call_to_eval.get(call_id)
        if evaluation is None:
            continue
        # v0.4.86/v0.4.87 emitted a compact legacy header containing only
        # xilevg1/abel1/xpx/xh0/xh1 for the selected call.  v0.4.88 emits a
        # general row schema for all phases.  Accept both for back-compat.
        if "xilevg1" in row:
            hydrogen_state_rows.append(
                {
                    "source": "xstar",
                    "evaluation_index": evaluation,
                    "phase_code": 10,
                    "phase": _STATE_PHASE_NAMES[10],
                    "outer_iteration": 0,
                    "fixed_iteration": 0,
                    "compact_index": 0,
                    "superlevel": 0,
                    "ion_counter": 0,
                    "ion_stage": 1,
                    "ion_index": 0,
                    "local_level": 0,
                    "global_index": 1,
                    "full_element_index": 1,
                    "hydrogen_ground_fraction": parse_fortran_float(row["xilevg1"]),
                    "hydrogen_abundance": parse_fortran_float(row["abel1"]),
                    "hydrogen_density_cm3": parse_fortran_float(row["xpx"]),
                    "neutral_h_density_cm3": parse_fortran_float(row["xh0"]),
                    "ionized_h_density_cm3": parse_fortran_float(row["xh1"]),
                    "population": parse_fortran_float(row["xilevg1"]),
                }
            )
            continue
        phase_code = _int_field(row, "phase_code")
        item: dict[str, Any] = {
            "source": "xstar",
            "evaluation_index": evaluation,
            "phase_code": phase_code,
            "phase": _STATE_PHASE_NAMES.get(phase_code, f"phase_{phase_code}"),
            "outer_iteration": _int_field(row, "outer_iteration"),
            "fixed_iteration": _int_field(row, "fixed_iteration"),
            "compact_index": _int_field(row, "compact_index"),
            "superlevel": _int_field(row, "superlevel"),
            "ion_counter": _int_field(row, "ion_counter"),
            "ion_stage": _int_field(row, "ion_stage"),
            "ion_index": _int_field(row, "ion_index"),
            "local_level": _int_field(row, "local_level"),
            "global_index": _int_field(row, "global_index"),
            "full_element_index": _int_field(row, "full_element_index"),
        }
        for field in (
            "hydrogen_ground_fraction", "hydrogen_abundance",
            "hydrogen_density_cm3", "neutral_h_density_cm3",
            "ionized_h_density_cm3", "photoionization_rate",
            "recombination_rate", "preliminary_ion_fraction",
            "population", "population_total",
        ):
            if field in row and str(row.get(field, "")) != "":
                item[field] = _float_field(row, field)
        hydrogen_state_rows.append(item)
    hydrogen_state_path = out / "xstar_zone1_hydrogen_state_path.csv"
    _write(hydrogen_state_path, hydrogen_state_rows)

    electron_fraction_rows: list[dict[str, Any]] = []
    for row in _read_optional(root / "xstar_zone1_electron_fraction_path_probe.csv"):
        call_id = _int_field(row, "calc_hmc_all_call_id")
        evaluation = call_to_eval.get(call_id)
        if evaluation is None:
            continue
        phase_code = _int_field(row, "phase_code", 140)
        electron_fraction_rows.append(
            {
                "source": "xstar",
                "evaluation_index": evaluation,
                "phase_code": phase_code,
                "phase": _STATE_PHASE_NAMES.get(phase_code, f"phase_{phase_code}"),
                "element_z": _int_field(row, "element_z"),
                "element_abundance": _float_field(row, "element_abundance"),
                "selected_min_ion_stage": _int_field(row, "selected_min_ion_stage"),
                "selected_max_ion_stage": _int_field(row, "selected_max_ion_stage"),
                "xisum": _float_field(row, "xisum"),
                "fully_stripped_fraction": _float_field(row, "fully_stripped_fraction"),
                "electron_contribution_increment": _float_field(row, "electron_contribution_increment"),
                "electron_contribution_after_element": _float_field(row, "electron_contribution_after_element"),
            }
        )
    electron_fraction_path = out / "xstar_zone1_electron_fraction_path.csv"
    _write(electron_fraction_path, electron_fraction_rows)

    carbon_state_rows: list[dict[str, Any]] = []
    carbon_solve_eval09_11_rows: list[dict[str, Any]] = []
    carbon_correlation_buckets: dict[tuple[int, int, int, int], list[tuple[int, float]]] = {}
    for row in _read_optional(root / "xstar_zone1_carbon_state_path_probe.csv"):
        call_id = _int_field(row, "calc_hmc_all_call_id")
        evaluation = call_to_eval.get(call_id)
        if evaluation is None:
            continue
        phase_code = _int_field(row, "phase_code")
        item = {
            "source": "xstar",
            "evaluation_index": evaluation,
            "phase_code": phase_code,
            "phase": _STATE_PHASE_NAMES.get(phase_code, f"phase_{phase_code}"),
            "outer_iteration": _int_field(row, "outer_iteration"),
            "fixed_iteration": _int_field(row, "fixed_iteration"),
            "compact_index": _int_field(row, "compact_index"),
            "superlevel": _int_field(row, "superlevel"),
            "ion_counter": _int_field(row, "ion_counter"),
            "ion_stage": _int_field(row, "ion_stage"),
            "ion_index": _int_field(row, "ion_index"),
            "local_level": _int_field(row, "local_level"),
            "global_index": _int_field(row, "global_index"),
            "full_element_index": _int_field(row, "full_element_index"),
            "population": _float_field(row, "population"),
        }
        if call_id == target_call:
            carbon_state_rows.append(item)
        if 9 <= evaluation <= 11 and phase_code in (30, 40, 50, 60, 70, 80, 120):
            carbon_solve_eval09_11_rows.append(dict(item))
        if phase_code in (20, 120):
            key = (
                evaluation,
                phase_code,
                int(item["ion_stage"]),
                int(item["ion_index"]),
            )
            carbon_correlation_buckets.setdefault(key, []).append(
                (int(item["local_level"]), float(item["population"]))
            )
    carbon_state_path = out / "xstar_zone1_carbon_state_path_T73198p4K.csv"
    _write(carbon_state_path, carbon_state_rows)
    carbon_solve_eval09_11_path = out / "xstar_zone1_carbon_solve_path_eval09_11_T73198p4K.csv"
    _write(carbon_solve_eval09_11_path, carbon_solve_eval09_11_rows)

    carbon_inner_eval11_rows: list[dict[str, Any]] = []
    for row in _read_optional(root / "xstar_zone1_carbon_msolvelucy_inner_probe.csv"):
        call_id = _int_field(row, "calc_hmc_all_call_id")
        evaluation = call_to_eval.get(call_id)
        if evaluation != 11:
            continue
        if _int_field(row, "outer_iteration") != 1:
            continue
        item = {
            "source": "xstar",
            "evaluation_index": evaluation,
            "element_z": _int_field(row, "element_z"),
            "outer_iteration": _int_field(row, "outer_iteration"),
            "row_kind": row.get("row_kind", ""),
            "physical_identity": row.get("physical_identity", ""),
            "shared_compact_index": _int_field(row, "shared_compact_index"),
            "shared_superlevel": _int_field(row, "shared_superlevel"),
            "compact_index": _int_field(row, "compact_index"),
            "superlevel": _int_field(row, "superlevel"),
            "ion_counter": _int_field(row, "ion_counter"),
            "ion_stage": _int_field(row, "ion_stage"),
            "row_superlevel": _int_field(row, "row_superlevel"),
            "column_superlevel": _int_field(row, "column_superlevel"),
            "term_index": _int_field(row, "term_index"),
            "source_row": _int_field(row, "source_row"),
            "source_column": _int_field(row, "source_column"),
            "source_record": _int_field(row, "source_record"),
            "rate_type": _int_field(row, "rate_type"),
            "data_type": _int_field(row, "data_type"),
            "roles": row.get("roles", ""),
            "population": _float_field(row, "population"),
            "population_before_condensed_solve": _float_field(row, "population_before_condensed_solve"),
            "population_after_condensed_solve": _float_field(row, "population_after_condensed_solve"),
            "raw_matrix_value": _float_field(row, "raw_matrix_value"),
            "normalized_matrix_value": _float_field(row, "normalized_matrix_value"),
            "rr": _float_field(row, "rr"),
            "population_outer_start": _float_field(row, "population_outer_start"),
            "population_after_condensed": _float_field(row, "population_after_condensed"),
            "population_after_fixed_point": _float_field(row, "population_after_fixed_point"),
            "xm_before_normalization": _float_field(row, "xm_before_normalization"),
            "normalization_denominator": _float_field(row, "normalization_denominator"),
            "population_before": _float_field(row, "population_before"),
            "riu": _float_field(row, "riu"),
            "rui": _float_field(row, "rui"),
            "ril": _float_field(row, "ril"),
            "rli": _float_field(row, "rli"),
            "population_unnormalized": _float_field(row, "population_unnormalized"),
            "population_after": _float_field(row, "population_after"),
            "aj1": _float_field(row, "aj1"),
            "aj2": _float_field(row, "aj2"),
            "rr_mm": _float_field(row, "rr_mm"),
            "rr_nn": _float_field(row, "rr_nn"),
            "offdiag_contribution": _float_field(row, "offdiag_contribution"),
            "diag_contribution": _float_field(row, "diag_contribution"),
            "importance": _float_field(row, "importance"),
        }
        carbon_inner_eval11_rows.append(item)
    carbon_inner_eval11_path = out / "xstar_zone1_carbon_msolvelucy_inner_eval11_outer1_T73198p4K.csv"
    _write(carbon_inner_eval11_path, carbon_inner_eval11_rows)

    carbon_correlation_rows: list[dict[str, Any]] = []
    direct_carbon_correlation = _read_optional(root / "xstar_zone1_carbon_stage_correlation_probe.csv")
    if direct_carbon_correlation:
        for row in direct_carbon_correlation:
            call_id = _int_field(row, "calc_hmc_all_call_id")
            evaluation = call_to_eval.get(call_id)
            if evaluation is None:
                continue
            phase_code = _int_field(row, "phase_code")
            carbon_correlation_rows.append(
                {
                    "source": "xstar",
                    "evaluation_index": evaluation,
                    "phase_code": phase_code,
                    "phase": _STATE_PHASE_NAMES.get(phase_code, f"phase_{phase_code}"),
                    "ion_stage": _int_field(row, "ion_stage"),
                    "ion_index": _int_field(row, "ion_index"),
                    "nlev": _int_field(row, "nlev"),
                    "ground_local_level": _int_field(row, "ground_local_level"),
                    "ground_global_index": _int_field(row, "ground_global_index"),
                    "continuum_local_level": _int_field(row, "continuum_local_level"),
                    "continuum_global_index": _int_field(row, "continuum_global_index"),
                    "next_ion_stage": _int_field(row, "next_ion_stage"),
                    "next_ground_local_level": _int_field(row, "next_ground_local_level"),
                    "next_ground_global_index": _int_field(row, "next_ground_global_index"),
                    "population_total": _float_field(row, "population_total"),
                    "ground_population": _float_field(row, "ground_population"),
                    "continuum_population": _float_field(row, "continuum_population"),
                    "next_ground_population": _float_field(row, "next_ground_population"),
                    "continuum_next_ground_difference": _float_field(row, "continuum_next_ground_difference"),
                }
            )
    else:
        for (evaluation, phase_code, ion_stage, ion_index), values in sorted(carbon_correlation_buckets.items()):
            if not values:
                continue
            max_level = max(level for level, _value in values)
            total = sum(value for level, value in values if level < max_level)
            continuum = sum(value for level, value in values if level == max_level)
            carbon_correlation_rows.append(
                {
                    "source": "xstar",
                    "evaluation_index": evaluation,
                    "phase_code": phase_code,
                    "phase": _STATE_PHASE_NAMES.get(phase_code, f"phase_{phase_code}"),
                    "ion_stage": ion_stage,
                    "ion_index": ion_index,
                    "nlev": 0,
                    "ground_local_level": 1,
                    "ground_global_index": 0,
                    "continuum_local_level": 0,
                    "continuum_global_index": 0,
                    "next_ion_stage": ion_stage + 1,
                    "next_ground_local_level": 1,
                    "next_ground_global_index": 0,
                    "population_total": float(total),
                    "ground_population": 0.0,
                    "continuum_population": float(continuum),
                    "next_ground_population": 0.0,
                    "continuum_next_ground_difference": 0.0,
                }
            )
    carbon_correlation_path = out / "xstar_zone1_carbon_stage_correlation.csv"
    _write(carbon_correlation_path, carbon_correlation_rows)

    carbon_stage_total_rows: list[dict[str, Any]] = []
    carbon_solve_stage_eval09_11_rows: list[dict[str, Any]] = []
    for row in _read_optional(root / "xstar_zone1_carbon_stage_totals_probe.csv"):
        call_id = _int_field(row, "calc_hmc_all_call_id")
        evaluation = call_to_eval.get(call_id)
        if evaluation is None:
            continue
        phase_code = _int_field(row, "phase_code")
        item = {
            "source": "xstar",
            "evaluation_index": evaluation,
            "phase_code": phase_code,
            "phase": _STATE_PHASE_NAMES.get(phase_code, f"phase_{phase_code}"),
            "outer_iteration": _int_field(row, "outer_iteration"),
            "ion_counter": _int_field(row, "ion_counter"),
            "ion_stage": _int_field(row, "ion_stage"),
            "population_total": _float_field(row, "population_total"),
        }
        if call_id == target_call:
            carbon_stage_total_rows.append(dict(item))
        if 9 <= evaluation <= 11 and phase_code in (41, 90, 100):
            carbon_solve_stage_eval09_11_rows.append(dict(item))
    carbon_stage_totals_path = out / "xstar_zone1_carbon_stage_totals_T73198p4K.csv"
    _write(carbon_stage_totals_path, carbon_stage_total_rows)
    carbon_solve_stage_eval09_11_path = out / "xstar_zone1_carbon_solve_stage_totals_eval09_11_T73198p4K.csv"
    _write(carbon_solve_stage_eval09_11_path, carbon_solve_stage_eval09_11_rows)

    carbon_alias_rows: list[dict[str, Any]] = []
    for row in _read_optional(root / "xstar_zone1_carbon_alias_boundaries_probe.csv"):
        if _int_field(row, "calc_hmc_all_call_id") != target_call:
            continue
        lower_population = _float_field(row, "lower_population")
        upper_population = _float_field(row, "upper_population")
        carbon_alias_rows.append(
            {
                "source": "xstar",
                "evaluation_index": target_eval,
                "phase_code": 130,
                "phase": _STATE_PHASE_NAMES[130],
                "lower_ion_index": _int_field(row, "lower_ion_index"),
                "lower_ion_stage": _int_field(row, "lower_ion_stage"),
                "lower_local_level": _int_field(row, "lower_local_level"),
                "lower_global_index": _int_field(row, "lower_global_index"),
                "lower_population": lower_population,
                "upper_ion_index": _int_field(row, "upper_ion_index"),
                "upper_ion_stage": _int_field(row, "upper_ion_stage"),
                "upper_local_level": _int_field(row, "upper_local_level"),
                "upper_global_index": _int_field(row, "upper_global_index"),
                "upper_population": upper_population,
                "absolute_difference": abs(lower_population - upper_population),
            }
        )
    carbon_alias_path = out / "xstar_zone1_carbon_alias_boundaries_T73198p4K.csv"
    _write(carbon_alias_path, carbon_alias_rows)

    summary = {
        "diagnostic_release": "0.4.92",
        "probe_contract_version": "0.4.92",
        "dsec_call_id": 1,
        "n_evaluations": len(sequence_rows),
        "n_input_fingerprints": len(fingerprints),
        "input_fingerprints_skipped": not include_input_fingerprints,
        "input_fingerprint_algorithm": "streaming_constant_memory",
        "target_temperature_K": target_temperature_k,
        "selected_call_id": target_call,
        "selected_evaluation_index": target_eval,
        "selected_temperature_K": target_state["temperature_K"],
        "selected_electron_fraction_xee": target_state[
            "electron_fraction_xee"
        ],
        "selected_hydrogen_density_cm3": target_state[
            "hydrogen_density_cm3"
        ],
        "n_carbon_rate_rows": len(rate_rows),
        "n_civ_preliminary_record_rows": len(civ_records),
        "n_cv_matrix_audit_rows": len(matrix_rows),
        "n_carbon_initial_population_rows": len(initial_population_rows),
        "n_carbon_normalization_row_entries": len(normalization_rows),
        "n_cv_selected_level_population_rows": len(level_population_rows),
        "n_carbon_logical_cooling_terms": len(logical_cooling_rows),
        "n_carbon_cooling_terms": len(cooling),
        "n_hydrogen_state_path_rows": len(hydrogen_state_rows),
        "n_electron_fraction_path_rows": len(electron_fraction_rows),
        "n_carbon_state_path_rows": len(carbon_state_rows),
        "n_carbon_solve_path_eval09_11_rows": len(carbon_solve_eval09_11_rows),
        "n_carbon_msolvelucy_inner_eval11_outer1_rows": len(carbon_inner_eval11_rows),
        "n_carbon_stage_total_rows": len(carbon_stage_total_rows),
        "n_carbon_solve_stage_total_eval09_11_rows": len(carbon_solve_stage_eval09_11_rows),
        "n_carbon_stage_correlation_rows": len(carbon_correlation_rows),
        "n_carbon_alias_rows": len(carbon_alias_rows),
        "source_order_state_path_probe_available": bool(
            hydrogen_state_rows and carbon_state_rows and carbon_stage_total_rows
        ),
        "hydrogen_all_evaluations_probe_available": bool(hydrogen_state_rows),
        "electron_fraction_path_probe_available": bool(electron_fraction_rows),
        "carbon_stage_correlation_probe_available": bool(carbon_correlation_rows),
        "production_rates_modified": False,
        "probe_is_observation_only": True,
        "production_solver_modified": False,
        "live_hydrogen_charge_exchange_state": False,
        "production_tolerances_modified": False,
        "empirical_corrections_added": False,
    }
    summary_path = out / "xstar_zone1_dsec_probe_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if progress is not None:
        progress(
            "target_state_analysis_done "
            f"target_call={target_call} target_evaluation={target_eval}"
        )
    return {
        "sequence_csv": sequence_path,
        "fingerprints_csv": fingerprints_path,
        "rates_csv": rates_path,
        "civ_records_csv": civ_records_path,
        "topology_csv": topology_path,
        "initial_population_csv": initial_population_path,
        "normalization_row_csv": normalization_path,
        "cv_level_populations_csv": level_population_path,
        "logical_cooling_csv": logical_cooling_path,
        "matrix_csv": matrix_path,
        "cooling_csv": cooling_path,
        "hydrogen_state_path_csv": hydrogen_state_path,
        "electron_fraction_path_csv": electron_fraction_path,
        "carbon_state_path_csv": carbon_state_path,
        "carbon_solve_path_eval09_11_csv": carbon_solve_eval09_11_path,
        "carbon_msolvelucy_inner_eval11_outer1_csv": carbon_inner_eval11_path,
        "carbon_stage_totals_csv": carbon_stage_totals_path,
        "carbon_solve_stage_totals_eval09_11_csv": carbon_solve_stage_eval09_11_path,
        "carbon_stage_correlation_csv": carbon_correlation_path,
        "carbon_alias_boundaries_csv": carbon_alias_path,
        "summary_json": summary_path,
    }


def _float(row: Mapping[str, str], field: str) -> float:
    return parse_fortran_float(row[field])


def _numeric_comparison(
    python_rows: Sequence[Mapping[str, str]],
    xstar_rows: Sequence[Mapping[str, str]],
    *,
    keys: Sequence[str],
    fields: Sequence[str],
    rtol: float,
    atol: float,
) -> list[dict[str, Any]]:
    def key(row: Mapping[str, str]) -> tuple[str, ...]:
        return tuple(str(row.get(field, "")) for field in keys)

    def number(row: Mapping[str, str] | None, field: str) -> float:
        if row is None:
            return 0.0
        value = row.get(field, "")
        if value in (None, ""):
            return 0.0
        return parse_fortran_float(str(value))

    py = {key(row): row for row in python_rows}
    xs = {key(row): row for row in xstar_rows}
    output: list[dict[str, Any]] = []
    for item in sorted(set(py) | set(xs)):
        prow = py.get(item)
        xrow = xs.get(item)
        for field in fields:
            pv = number(prow, field)
            xv = number(xrow, field)
            diff = abs(pv - xv)
            output.append(
                {
                    **{name: value for name, value in zip(keys, item)},
                    "field": field,
                    "python_value": pv,
                    "xstar_value": xv,
                    "absolute_difference": diff,
                    "relative_difference": diff
                    / max(abs(pv), abs(xv), atol),
                    "within_tolerance": diff <= atol + rtol * abs(xv),
                }
            )
    return output


def _numeric_comparison_with_presence(
    python_rows: Sequence[Mapping[str, str]],
    xstar_rows: Sequence[Mapping[str, str]],
    *,
    keys: Sequence[str],
    fields: Sequence[str],
    rtol: float,
    atol: float,
) -> list[dict[str, Any]]:
    """Compare numeric rows while separating coverage from numeric parity.

    v0.4.88 used the union of keys and substituted zero for a missing side.
    That was useful for spotting missing rows, but it made unmatched hydrogen
    vector rows look like physical 0-vs-1 population disagreements.  v0.4.89
    records key coverage explicitly and only evaluates tolerance for matched
    rows.
    """

    def key(row: Mapping[str, str]) -> tuple[str, ...]:
        return tuple(str(row.get(field, "")) for field in keys)

    def number(row: Mapping[str, str], field: str) -> float:
        value = row.get(field, "")
        if value in (None, ""):
            return 0.0
        return parse_fortran_float(str(value))

    py = {key(row): row for row in python_rows}
    xs = {key(row): row for row in xstar_rows}
    output: list[dict[str, Any]] = []
    for item in sorted(set(py) | set(xs)):
        prow = py.get(item)
        xrow = xs.get(item)
        matched = prow is not None and xrow is not None
        for field in fields:
            base = {name: value for name, value in zip(keys, item)}
            if not matched:
                output.append(
                    {
                        **base,
                        "field": field,
                        "python_present": prow is not None,
                        "xstar_present": xrow is not None,
                        "comparison_status": "matched" if matched else "unmatched_key",
                        "python_value": "" if prow is None else prow.get(field, ""),
                        "xstar_value": "" if xrow is None else xrow.get(field, ""),
                        "absolute_difference": "",
                        "relative_difference": "",
                        "within_tolerance": False,
                    }
                )
                continue
            pv = number(prow, field)
            xv = number(xrow, field)
            diff = abs(pv - xv)
            output.append(
                {
                    **base,
                    "field": field,
                    "python_present": True,
                    "xstar_present": True,
                    "comparison_status": "matched",
                    "python_value": pv,
                    "xstar_value": xv,
                    "absolute_difference": diff,
                    "relative_difference": diff / max(abs(pv), abs(xv), atol),
                    "within_tolerance": diff <= atol + rtol * abs(xv),
                }
            )
    return output


def _canonical_hydrogen_phase(row: Mapping[str, str]) -> dict[str, str]:
    """Return a row copy with the H mapping phase canonicalized.

    The Python v0.4.88 product names the hydrogen global-to-element mapping as
    phase 21, while the original-XSTAR side emits the same physical rows under
    the generic element-mapping phase 20.  For comparison these are the same
    physical locus, so both are keyed as phase 21.
    """
    out = dict(row)
    if str(out.get("phase_code", "")) == "20":
        phase = str(out.get("phase", "")).lower()
        if (
            not phase
            or "hydrogen" in phase
            or str(out.get("ion_stage", "")) in ("1", "")
        ):
            out["phase_code"] = "21"
            out["phase"] = _STATE_PHASE_NAMES[21]
    return out


def _first_row(
    rows: Sequence[Mapping[str, Any]],
    *,
    predicate: Callable[[Mapping[str, Any]], bool],
) -> Mapping[str, Any] | None:
    selected = [row for row in rows if predicate(row)]
    if not selected:
        return None

    def as_int(row: Mapping[str, Any], key: str) -> int:
        value = row.get(key, 0)
        if value in (None, ""):
            return 0
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    return min(
        selected,
        key=lambda row: (
            as_int(row, "evaluation_index"),
            as_int(row, "phase_code"),
            as_int(row, "outer_iteration"),
            as_int(row, "fixed_iteration"),
            as_int(row, "compact_index"),
            as_int(row, "ion_counter"),
            as_int(row, "ion_stage"),
            as_int(row, "ion_index"),
            as_int(row, "local_level"),
            str(row.get("field", "")),
        ),
    )


def _row_summary(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    keys = (
        "evaluation_index", "phase_code", "phase", "outer_iteration",
        "fixed_iteration", "compact_index", "ion_counter", "ion_stage",
        "ion_index", "local_level", "full_element_index", "element_z",
        "field", "python_present", "xstar_present", "comparison_status",
        "python_value", "xstar_value", "absolute_difference",
        "relative_difference", "within_tolerance",
    )
    return {key: row.get(key) for key in keys if key in row}


def _rows_with_fields(
    rows: Sequence[Mapping[str, str]],
    *,
    keys: Sequence[str],
    fields: Sequence[str],
) -> list[Mapping[str, str]]:
    """Keep rows that can be safely passed to ``_numeric_comparison``."""
    return [
        row
        for row in rows
        if all(key in row and str(row.get(key, "")) != "" for key in keys)
        and all(field in row and str(row.get(field, "")) != "" for field in fields)
    ]


def _compare_optional_numeric_groups(
    groups: Sequence[tuple[Sequence[Mapping[str, str]], Sequence[Mapping[str, str]], Sequence[str], Sequence[str]]],
    *,
    rtol: float,
    atol: float,
    include_presence: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for py_rows, xs_rows, keys, fields in groups:
        left = _rows_with_fields(py_rows, keys=keys, fields=fields)
        right = _rows_with_fields(xs_rows, keys=keys, fields=fields)
        if left or right:
            compare = _numeric_comparison_with_presence if include_presence else _numeric_comparison
            rows.extend(
                compare(
                    left, right, keys=keys, fields=fields, rtol=rtol, atol=atol
                )
            )
    return rows

def compare_zone1_probe_with_python(
    *,
    xstar_analysis_dir: str | Path,
    python_diagnostic_dir: str | Path,
    out_dir: str | Path,
    rtol: float = 5.0e-5,
    atol: float = 1.0e-30,
) -> Mapping[str, Path]:
    """Evaluate the source-port physical and diagnostic parity contracts."""
    xs = Path(xstar_analysis_dir)
    py = Path(python_diagnostic_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 1-2. Aggregate C IV preliminary rate and fraction parity.
    rate_fields = (
        "preliminary_ion_fraction",
        "preliminary_photoionization_rate",
        "preliminary_recombination_rate",
        "second_pass_photoionization_rate",
        "second_pass_recombination_rate",
    )
    rate_rows = _numeric_comparison(
        _read(py / "python_zone1_carbon_rates_T73198p4K.csv"),
        _read(xs / "xstar_zone1_carbon_rates_T73198p4K.csv"),
        keys=("ion_stage",),
        fields=rate_fields,
        rtol=rtol,
        atol=atol,
    )
    rates_path = out / "zone1_carbon_rate_comparison_T73198p4K.csv"
    _write(rates_path, rate_rows)
    civ_rate_ready = all(
        bool(row["within_tolerance"])
        for row in rate_rows
        if str(row["ion_stage"]) == "4"
        and row["field"] == "preliminary_photoionization_rate"
    ) and any(
        str(row["ion_stage"]) == "4"
        and row["field"] == "preliminary_photoionization_rate"
        for row in rate_rows
    )
    civ_fraction_ready = all(
        bool(row["within_tolerance"])
        for row in rate_rows
        if str(row["ion_stage"]) == "4"
        and row["field"] == "preliminary_ion_fraction"
    ) and any(
        str(row["ion_stage"]) == "4"
        and row["field"] == "preliminary_ion_fraction"
        for row in rate_rows
    )

    # Record-level proof of the source type-15 threshold order.
    py_records = _read(py / "python_zone1_civ_calc_ion_rates_records_T73198p4K.csv")
    xs_records = _read(xs / "xstar_zone1_civ_calc_ion_rates_records_T73198p4K.csv")
    py_record_map = {int(row["record"]): row for row in py_records}
    xs_record_map = {int(row["record"]): row for row in xs_records}
    dominant_python_civ_record = (
        max(
            py_records,
            key=lambda row: abs(_float(row, "pirti_contribution")),
        )
        if py_records
        else None
    )
    common_record_fields = (
        "parent_threshold_ev",
        "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
        "pirti_before", "pirti_contribution", "pirti_after",
        "rrrti_before", "rrrti_contribution", "rrrti_after",
    )
    type15_record_fields = (
        "final_effective_threshold_ev", "final_effective_d",
        "bkhsgo_threshold_ev", "bkhsgo_effective_d",
        "phintfo_threshold_ev", "phintfo_effective_d",
    )
    record_comparison: list[dict[str, Any]] = []
    common_records = sorted(set(py_record_map) | set(xs_record_map))
    for record in common_records:
        prow = py_record_map.get(record)
        xrow = xs_record_map.get(record)
        base = {
            "record": record,
            "python_present": prow is not None,
            "xstar_present": xrow is not None,
            "data_type": 0 if prow is None else int(prow["data_type"]),
            "rate_type": 0 if prow is None else int(prow["rate_type"]),
        }
        applicable_numeric_fields = list(common_record_fields)
        row_data_type = None
        if prow is not None:
            row_data_type = int(prow["data_type"])
        elif xrow is not None:
            row_data_type = int(xrow["data_type"])
        if row_data_type == 15:
            applicable_numeric_fields.extend(type15_record_fields)
        for field in applicable_numeric_fields:
            pv = 0.0 if prow is None else _float(prow, field)
            xv = 0.0 if xrow is None else _float(xrow, field)
            diff = abs(pv - xv)
            record_comparison.append(
                {
                    **base,
                    "field": field,
                    "python_value": pv,
                    "xstar_value": xv,
                    "absolute_difference": diff,
                    "relative_difference": diff / max(abs(pv), abs(xv), atol),
                    "within_tolerance": bool(
                        prow is not None
                        and xrow is not None
                        and math.isfinite(pv)
                        and math.isfinite(xv)
                        and diff <= atol + rtol * abs(xv)
                    ),
                }
            )
        for field in ("parent_record", "idest1", "idest2", "data_type", "rate_type"):
            pv = None if prow is None else int(prow[field])
            xv = None if xrow is None else int(xrow[field])
            record_comparison.append(
                {
                    **base,
                    "field": field,
                    "python_value": pv,
                    "xstar_value": xv,
                    "absolute_difference": 0 if pv == xv else 1,
                    "relative_difference": 0.0 if pv == xv else 1.0,
                    "within_tolerance": bool(pv is not None and pv == xv),
                }
            )
        if row_data_type == 15:
            for field in ("shell_thresholds_ev", "shell_d_values"):
                pseq = () if prow is None else _parse_float_sequence(prow.get(field))
                xseq = () if xrow is None else _parse_float_sequence(xrow.get(field))
                same_length = bool(pseq) and len(pseq) == len(xseq)
                within = same_length and all(
                    abs(pv - xv) <= atol + rtol * abs(xv)
                    for pv, xv in zip(pseq, xseq)
                )
                record_comparison.append(
                    {
                        **base,
                        "field": field,
                        "python_value": _format_float_sequence(pseq),
                        "xstar_value": _format_float_sequence(xseq),
                        "absolute_difference": 0 if within else 1,
                        "relative_difference": 0.0 if within else 1.0,
                        "within_tolerance": bool(within),
                    }
                )
    record_path = out / "zone1_civ_calc_ion_rates_record_comparison_T73198p4K.csv"
    _write(record_path, record_comparison)
    record_coverage_ready = bool(py_records) and bool(xs_records) and len(py_record_map) == len(py_records) and len(xs_record_map) == len(xs_records) and set(py_record_map) == set(xs_record_map)
    record_numeric_ready = bool(record_comparison) and all(
        bool(row["within_tolerance"]) for row in record_comparison
    )
    type15_common = [
        record for record in set(py_record_map) & set(xs_record_map)
        if int(py_record_map[record]["data_type"]) == 15
    ]
    type15_record_level_proof_applicable = bool(type15_common)
    type15_last_shell_ready = bool(type15_common)
    type15_parent_diff_observed = False
    for record in type15_common:
        for row in (py_record_map[record], xs_record_map[record]):
            shells = _parse_float_sequence(row.get("shell_thresholds_ev"))
            shell_ds = _parse_float_sequence(row.get("shell_d_values"))
            effective = _float(row, "final_effective_threshold_ev")
            effective_d = _float(row, "final_effective_d")
            bkhsgo_threshold = _float(row, "bkhsgo_threshold_ev")
            bkhsgo_d = _float(row, "bkhsgo_effective_d")
            phintfo_threshold = _float(row, "phintfo_threshold_ev")
            phintfo_d = _float(row, "phintfo_effective_d")
            parent = _float(row, "parent_threshold_ev")
            if not shells or not shell_ds:
                type15_last_shell_ready = False
            else:
                last_threshold = shells[-1]
                last_d = shell_ds[-1]
                for observed in (effective, bkhsgo_threshold, phintfo_threshold):
                    if abs(observed - last_threshold) > atol + rtol * abs(last_threshold):
                        type15_last_shell_ready = False
                for observed in (effective_d, bkhsgo_d, phintfo_d):
                    if abs(observed - last_d) > atol + rtol * abs(last_d):
                        type15_last_shell_ready = False
            if abs(parent - effective) > atol + rtol * abs(effective):
                type15_parent_diff_observed = True
    type15_record_proof_ready = bool(
        type15_record_level_proof_applicable
        and record_coverage_ready
        and record_numeric_ready
        and type15_last_shell_ready
        and type15_parent_diff_observed
    )
    type15_record_gate_passed = bool(
        not type15_record_level_proof_applicable
        or type15_record_proof_ready
    )

    # v0.4.82 proof for the actual dominant C IV record family.  Unlike the
    # optional data-type-15 shell proof, type 59 needs no additional original
    # probe file: the existing calc_ion_rates record rows contain the complete
    # returned rate/heating contract and endpoint mapping.
    type59_common = [
        record for record in set(py_record_map) & set(xs_record_map)
        if int(py_record_map[record]["data_type"]) == 59
        and int(xs_record_map[record]["data_type"]) == 59
    ]
    type59_record_level_proof_applicable = bool(type59_common)
    type59_rows = [
        row for row in record_comparison
        if int(row["data_type"]) == 59
    ]
    type59_endpoint_rows = [
        row for row in type59_rows
        if row["field"] in {"parent_record", "idest1", "idest2", "data_type", "rate_type"}
    ]
    type59_rate_rows = [
        row for row in type59_rows
        if row["field"] in {
            "parent_threshold_ev", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
            "pirti_contribution",
        }
    ]
    type59_record_coverage_ready = bool(type59_common) and all(
        record in py_record_map and record in xs_record_map
        for record in type59_common
    )
    type59_endpoint_mapping_ready = bool(type59_endpoint_rows) and all(
        bool(row["within_tolerance"]) for row in type59_endpoint_rows
    )
    type59_rate_heating_parity_ready = bool(type59_rate_rows) and all(
        bool(row["within_tolerance"]) for row in type59_rate_rows
    )
    type59_record_level_proof_ready = bool(
        type59_record_level_proof_applicable
        and type59_record_coverage_ready
        and type59_endpoint_mapping_ready
        and type59_rate_heating_parity_ready
    )
    type59_record_gate_passed = bool(
        not type59_record_level_proof_applicable
        or type59_record_level_proof_ready
    )

    # 3. C IV retained by the same critf-selected topology.
    py_topology = _read(py / "python_zone1_carbon_topology_T73198p4K.csv")
    xs_topology = _read(xs / "xstar_zone1_carbon_topology_T73198p4K.csv")
    topology_rows: list[dict[str, Any]] = []
    ptop = py_topology[0] if py_topology else None
    xtop = xs_topology[0] if xs_topology else None
    topology_fields = (
        "critf", "civ_preliminary_fraction", "selected_min_ion_stage",
        "selected_max_ion_stage", "compact_dimension", "normalization_row",
    )
    for field in topology_fields:
        if field in {"selected_min_ion_stage", "selected_max_ion_stage", "compact_dimension", "normalization_row"}:
            pv = None if ptop is None else int(ptop[field])
            xv = None if xtop is None else int(xtop[field])
            within = pv is not None and pv == xv
            diff = 0 if within else 1
        else:
            pv = 0.0 if ptop is None else _float(ptop, field)
            xv = 0.0 if xtop is None else _float(xtop, field)
            diff = abs(pv - xv)
            within = ptop is not None and xtop is not None and diff <= atol + rtol * abs(xv)
        topology_rows.append(
            {
                "field": field,
                "python_value": pv,
                "xstar_value": xv,
                "absolute_difference": diff,
                "within_tolerance": bool(within),
            }
        )
    p_retained = bool(ptop and _bool_value(ptop.get("civ_retained")))
    x_retained = bool(xtop and _bool_value(xtop.get("civ_retained")))
    civ_retained_ready = bool(
        p_retained and x_retained
        and ptop is not None and xtop is not None
        and int(ptop["selected_min_ion_stage"]) == int(xtop["selected_min_ion_stage"])
        and int(ptop["selected_max_ion_stage"]) == int(xtop["selected_max_ion_stage"])
    )
    topology_summary_path = out / "zone1_carbon_topology_comparison_T73198p4K.csv"
    _write(topology_summary_path, topology_rows)

    # 4-5. Separate compact topology from logical C V coefficient parity.
    matrix_fields = (
        "escape_factor_in", "escape_factor_out", "density_scale",
        "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
        "aj1", "aj2", "cj", "cj2",
    )
    py_matrix_rows = _read(py / "python_zone1_cv_matrix_levels_4_6_10_12_20.csv")
    xs_matrix_rows = _read(xs / "xstar_zone1_cv_matrix_levels_4_6_10_12_20.csv")
    matrix_rows = _numeric_comparison(
        py_matrix_rows,
        xs_matrix_rows,
        keys=("local_level", "record", "role"),
        fields=matrix_fields,
        rtol=rtol,
        atol=atol,
    )
    matrix_path = out / "zone1_cv_logical_coefficient_comparison_T73198p4K.csv"
    _write(matrix_path, matrix_rows)
    logical_keys = ("local_level", "record", "role")
    py_matrix_map = {
        tuple(row[key] for key in logical_keys): row for row in py_matrix_rows
    }
    xs_matrix_map = {
        tuple(row[key] for key in logical_keys): row for row in xs_matrix_rows
    }
    offset_rows: list[dict[str, Any]] = []
    for key in sorted(set(py_matrix_map) & set(xs_matrix_map)):
        prow = py_matrix_map[key]
        xrow = xs_matrix_map[key]
        offset_rows.append(
            {
                **{field: value for field, value in zip(logical_keys, key)},
                "python_row": int(prow["row"]),
                "xstar_row": int(xrow["row"]),
                "row_offset_xstar_minus_python": int(xrow["row"]) - int(prow["row"]),
                "python_column": int(prow["column"]),
                "xstar_column": int(xrow["column"]),
                "column_offset_xstar_minus_python": int(xrow["column"]) - int(prow["column"]),
            }
        )
    offset_path = out / "zone1_cv_compact_topology_offsets_T73198p4K.csv"
    _write(offset_path, offset_rows)
    cv_topology_ready = bool(offset_rows) and all(
        row["row_offset_xstar_minus_python"] == 0
        and row["column_offset_xstar_minus_python"] == 0
        for row in offset_rows
    ) and bool(ptop and xtop and int(ptop["compact_dimension"]) == int(xtop["compact_dimension"]))
    cv_coefficients_ready = bool(matrix_rows) and len(py_matrix_rows) == 932 and len(xs_matrix_rows) == 932 and len(py_matrix_map) == 932 and len(xs_matrix_map) == 932 and set(py_matrix_map) == set(xs_matrix_map) and all(
        bool(row["within_tolerance"]) for row in matrix_rows
    )

    # 6. Complete incoming compact population vector.
    py_initial = _read(py / "python_zone1_carbon_initial_population_T73198p4K.csv")
    xs_initial = _read(xs / "xstar_zone1_carbon_initial_population_T73198p4K.csv")
    initial_rows = _numeric_comparison(
        py_initial, xs_initial, keys=("compact_index",), fields=("population",),
        rtol=rtol, atol=atol,
    )
    initial_path = out / "zone1_carbon_initial_population_comparison_T73198p4K.csv"
    _write(initial_path, initial_rows)
    py_initial_keys = {str(row["compact_index"]) for row in py_initial}
    xs_initial_keys = {str(row["compact_index"]) for row in xs_initial}
    initial_ready = bool(initial_rows) and len(py_initial_keys) == len(py_initial) and len(xs_initial_keys) == len(xs_initial) and py_initial_keys == xs_initial_keys and len(py_initial) == len(xs_initial) and all(
        bool(row["within_tolerance"]) for row in initial_rows
    )

    # 7. Literal condensed number-conservation row.
    py_normalization = _read(py / "python_zone1_carbon_normalization_row_T73198p4K.csv")
    xs_normalization = _read(xs / "xstar_zone1_carbon_normalization_row_T73198p4K.csv")
    normalization_rows = _numeric_comparison(
        py_normalization, xs_normalization, keys=("outer_iteration", "column"),
        fields=("matrix_value", "rhs_value"), rtol=rtol, atol=atol,
    )
    normalization_path = out / "zone1_carbon_normalization_row_comparison_T73198p4K.csv"
    _write(normalization_path, normalization_rows)
    py_normalization_keys = {(str(row["outer_iteration"]), str(row["column"])) for row in py_normalization}
    xs_normalization_keys = {(str(row["outer_iteration"]), str(row["column"])) for row in xs_normalization}
    normalization_ready = bool(normalization_rows) and len(py_normalization_keys) == len(py_normalization) and len(xs_normalization_keys) == len(xs_normalization) and py_normalization_keys == xs_normalization_keys and len(py_normalization) == len(xs_normalization) and all(
        bool(row["within_tolerance"]) for row in normalization_rows
    )

    # 8. Reassess the previously catastrophic C V local level 20 population.
    py_levels = _read(py / "python_zone1_cv_level_populations_T73198p4K.csv")
    xs_levels = _read(xs / "xstar_zone1_cv_level_populations_T73198p4K.csv")
    level_rows = _numeric_comparison(
        py_levels, xs_levels, keys=("ion_stage", "local_level"), fields=("population",),
        rtol=rtol, atol=atol,
    )
    level_path = out / "zone1_cv_level_population_comparison_T73198p4K.csv"
    _write(level_path, level_rows)
    level20_rows = [
        row for row in level_rows
        if str(row["ion_stage"]) == "5" and str(row["local_level"]) == "20"
    ]
    py_level_keys = {(str(row["ion_stage"]), str(row["local_level"])) for row in py_levels}
    xs_level_keys = {(str(row["ion_stage"]), str(row["local_level"])) for row in xs_levels}
    level20_key = ("5", "20")
    level20_ready = bool(level20_rows) and len(py_level_keys) == len(py_levels) and len(xs_level_keys) == len(xs_levels) and level20_key in py_level_keys and level20_key in xs_level_keys and py_level_keys == xs_level_keys and all(
        bool(row["within_tolerance"]) for row in level20_rows
    )

    # 9. Fixed-state carbon cooling under stable physical keys.
    cooling_fields = (
        "population", "cj", "cj2", "cooling_contribution",
        "cooling2_contribution",
    )
    py_cooling = _read(py / "python_zone1_carbon_cooling_logical_T73198p4K.csv")
    xs_cooling = _read(xs / "xstar_zone1_carbon_cooling_logical_T73198p4K.csv")
    # Raw idest1/idest2 orientation is a matrix-write implementation detail
    # and can be reversed while naming the same physical endpoint pair.  Gate
    # cooling on the stable record/type/role/physical-endpoint identity.
    cooling_keys = (
        "ion_stage", "record", "data_type", "rate_type", "role",
        "lower_endpoint", "upper_endpoint",
    )
    cooling_rows = _numeric_comparison(
        py_cooling, xs_cooling, keys=cooling_keys,
        fields=cooling_fields, rtol=rtol, atol=atol,
    )
    cooling_path = out / "zone1_carbon_cooling_logical_comparison_T73198p4K.csv"
    _write(cooling_path, cooling_rows)
    py_cooling_keys = {tuple(str(row[key]) for key in cooling_keys) for row in py_cooling}
    xs_cooling_keys = {tuple(str(row[key]) for key in cooling_keys) for row in xs_cooling}
    cooling_ready = bool(cooling_rows) and len(py_cooling_keys) == len(py_cooling) and len(xs_cooling_keys) == len(xs_cooling) and py_cooling_keys == xs_cooling_keys and len(py_cooling) == len(xs_cooling) and all(
        bool(row["within_tolerance"]) for row in cooling_rows
    )

    # v0.4.88 source-order state-path comparison.  This is diagnostic-only
    # until the newly instrumented original XSTAR has generated the products.
    py_state = _read_optional(py / "python_zone1_carbon_state_path_T73198p4K.csv")
    xs_state = _read_optional(xs / "xstar_zone1_carbon_state_path_T73198p4K.csv")
    state_keys = (
        "phase_code", "outer_iteration", "fixed_iteration",
        "compact_index", "superlevel", "ion_counter", "ion_stage",
        "ion_index", "local_level", "full_element_index",
    )
    state_rows = _numeric_comparison(
        py_state, xs_state, keys=state_keys, fields=("population",),
        rtol=rtol, atol=atol,
    ) if py_state or xs_state else []
    state_path = out / "zone1_carbon_state_path_comparison_T73198p4K.csv"
    _write(state_path, state_rows)
    py_state_keys = {tuple(str(row.get(key, "")) for key in state_keys) for row in py_state}
    xs_state_keys = {tuple(str(row.get(key, "")) for key in state_keys) for row in xs_state}
    state_path_ready = bool(state_rows) and len(py_state_keys) == len(py_state) and len(xs_state_keys) == len(xs_state) and py_state_keys == xs_state_keys and all(bool(row["within_tolerance"]) for row in state_rows)

    py_stage = _read_optional(py / "python_zone1_carbon_stage_totals_T73198p4K.csv")
    xs_stage = _read_optional(xs / "xstar_zone1_carbon_stage_totals_T73198p4K.csv")
    stage_keys = ("phase_code", "outer_iteration", "ion_counter", "ion_stage")
    stage_rows = _numeric_comparison(
        py_stage, xs_stage, keys=stage_keys, fields=("population_total",),
        rtol=rtol, atol=atol,
    ) if py_stage or xs_stage else []
    stage_path = out / "zone1_carbon_stage_total_comparison_T73198p4K.csv"
    _write(stage_path, stage_rows)
    py_stage_keys = {tuple(str(row.get(key, "")) for key in stage_keys) for row in py_stage}
    xs_stage_keys = {tuple(str(row.get(key, "")) for key in stage_keys) for row in xs_stage}
    stage_totals_ready = bool(stage_rows) and len(py_stage_keys) == len(py_stage) and len(xs_stage_keys) == len(xs_stage) and py_stage_keys == xs_stage_keys and all(bool(row["within_tolerance"]) for row in stage_rows)

    py_h_raw = _read_optional(py / "python_zone1_hydrogen_state_path.csv")
    xs_h_raw = _read_optional(xs / "xstar_zone1_hydrogen_state_path.csv")
    py_h = [_canonical_hydrogen_phase(row) for row in py_h_raw]
    xs_h = [_canonical_hydrogen_phase(row) for row in xs_h_raw]
    def _phase_rows(rows: Sequence[Mapping[str, str]], phases: set[int]) -> list[Mapping[str, str]]:
        return [
            row for row in rows
            if row.get("phase_code") not in (None, "")
            and int(row.get("phase_code", 0)) in phases
        ]

    hydrogen_rows = _compare_optional_numeric_groups(
        (
            (
                _phase_rows(py_h, {10}), _phase_rows(xs_h, {10}),
                ("evaluation_index", "phase_code"),
                (
                    "hydrogen_ground_fraction", "hydrogen_abundance",
                    "hydrogen_density_cm3", "neutral_h_density_cm3",
                    "ionized_h_density_cm3", "population",
                ),
            ),
            (
                _phase_rows(py_h, {21, 30, 40, 50, 60, 70, 80, 110, 120}),
                _phase_rows(xs_h, {21, 30, 40, 50, 60, 70, 80, 110, 120}),
                (
                    "evaluation_index", "phase_code", "outer_iteration",
                    "fixed_iteration", "compact_index", "superlevel",
                    "ion_counter", "ion_stage", "ion_index", "local_level",
                    "full_element_index",
                ),
                ("population",),
            ),
            (
                _phase_rows(py_h, {41, 90, 100}),
                _phase_rows(xs_h, {41, 90, 100}),
                ("evaluation_index", "phase_code", "outer_iteration", "ion_counter", "ion_stage"),
                ("population_total",),
            ),
            (
                _phase_rows(py_h, {25}), _phase_rows(xs_h, {25}),
                ("evaluation_index", "phase_code", "ion_stage", "ion_index"),
                ("photoionization_rate", "recombination_rate", "preliminary_ion_fraction"),
            ),
        ),
        rtol=rtol,
        atol=atol,
        include_presence=True,
    ) if py_h or xs_h else []
    for row in hydrogen_rows:
        if "phase_code" in row:
            try:
                row["phase"] = _STATE_PHASE_NAMES.get(int(row["phase_code"]), f"phase_{row['phase_code']}")
            except (TypeError, ValueError):
                row["phase"] = f"phase_{row.get('phase_code', '')}"
    hydrogen_path = out / "zone1_hydrogen_state_path_comparison_T73198p4K.csv"
    _write(hydrogen_path, hydrogen_rows)
    hydrogen_matched_rows = [
        row for row in hydrogen_rows
        if row.get("comparison_status", "matched") == "matched"
    ]
    hydrogen_unmatched_rows = [
        row for row in hydrogen_rows
        if row.get("comparison_status") == "unmatched_key"
    ]
    hydrogen_state_ready = (
        bool(hydrogen_matched_rows)
        and not hydrogen_unmatched_rows
        and all(bool(row["within_tolerance"]) for row in hydrogen_matched_rows)
    )
    hydrogen_first_raw_numeric_difference = _first_row(
        hydrogen_matched_rows,
        predicate=lambda row: float(row.get("absolute_difference") or 0.0) > 0.0,
    )
    hydrogen_first_tolerance_failure = _first_row(
        hydrogen_matched_rows,
        predicate=lambda row: not bool(row.get("within_tolerance", False)),
    )
    hydrogen_first_unmatched_key_failure = _first_row(
        hydrogen_unmatched_rows, predicate=lambda row: True
    )
    hydrogen_first_differing_evaluation = (
        None
        if hydrogen_first_tolerance_failure is None
        else int(hydrogen_first_tolerance_failure.get("evaluation_index", 0))
    )

    hydrogen_recombination_audit_rows = [
        row for row in hydrogen_matched_rows
        if 18 <= int(row.get("evaluation_index", 0)) <= 24
        and int(row.get("phase_code", 0)) == 25
        and row.get("field") in ("recombination_rate", "preliminary_ion_fraction")
    ]
    hydrogen_recombination_audit_path = out / "zone1_hydrogen_recombination_audit_eval18_24_T73198p4K.csv"
    _write(hydrogen_recombination_audit_path, hydrogen_recombination_audit_rows)
    hydrogen_recombination_first_tolerance_failure = _first_row(
        hydrogen_recombination_audit_rows,
        predicate=lambda row: not bool(row.get("within_tolerance", False)),
    )

    py_electron = _read_optional(py / "python_zone1_electron_fraction_path.csv")
    xs_electron = _read_optional(xs / "xstar_zone1_electron_fraction_path.csv")
    electron_keys = ("evaluation_index", "phase_code", "element_z")
    electron_rows = _numeric_comparison(
        py_electron, xs_electron, keys=electron_keys,
        fields=(
            "xisum", "fully_stripped_fraction",
            "electron_contribution_increment",
            "electron_contribution_after_element",
        ),
        rtol=rtol,
        atol=atol,
    ) if py_electron or xs_electron else []
    electron_path = out / "zone1_electron_fraction_path_comparison_T73198p4K.csv"
    _write(electron_path, electron_rows)
    electron_keys_py = {tuple(str(row.get(key, "")) for key in electron_keys) for row in py_electron}
    electron_keys_xs = {tuple(str(row.get(key, "")) for key in electron_keys) for row in xs_electron}
    electron_ready = bool(electron_rows) and electron_keys_py == electron_keys_xs and all(bool(row["within_tolerance"]) for row in electron_rows)

    py_carbon_corr = _read_optional(py / "python_zone1_carbon_stage_correlation.csv")
    xs_carbon_corr = _read_optional(xs / "xstar_zone1_carbon_stage_correlation.csv")
    carbon_corr_keys = ("evaluation_index", "phase_code", "ion_stage", "ion_index")
    carbon_corr_rows = _numeric_comparison(
        py_carbon_corr, xs_carbon_corr, keys=carbon_corr_keys,
        fields=(
            "population_total", "ground_population", "continuum_population",
            "next_ground_population", "continuum_next_ground_difference",
        ),
        rtol=rtol,
        atol=atol,
    ) if py_carbon_corr or xs_carbon_corr else []
    carbon_corr_path = out / "zone1_carbon_stage_correlation_comparison_T73198p4K.csv"
    _write(carbon_corr_path, carbon_corr_rows)
    carbon_corr_keys_py = {tuple(str(row.get(key, "")) for key in carbon_corr_keys) for row in py_carbon_corr}
    carbon_corr_keys_xs = {tuple(str(row.get(key, "")) for key in carbon_corr_keys) for row in xs_carbon_corr}
    carbon_corr_ready = bool(carbon_corr_rows) and carbon_corr_keys_py == carbon_corr_keys_xs and all(bool(row["within_tolerance"]) for row in carbon_corr_rows)

    def _row_keyed(rows, *, evaluation, phase_code, ion_stage):
        for row in rows:
            if (
                int(row.get("evaluation_index", 0)) == int(evaluation)
                and int(row.get("phase_code", 0)) == int(phase_code)
                and int(row.get("ion_stage", 0)) == int(ion_stage)
            ):
                return row
        return None

    def _num(row, field):
        if row is None:
            return 0.0
        value = row.get(field, "")
        if value in (None, ""):
            return 0.0
        return parse_fortran_float(str(value))

    carbon_eval09_12_rows = [
        row for row in carbon_corr_rows
        if str(row.get("comparison_status", "matched")) == "matched"
        and 9 <= int(row.get("evaluation_index", 0)) <= 12
        and int(row.get("phase_code", 0)) in (20, 120)
    ]
    carbon_eval09_12_path = out / "zone1_carbon_stage_carryforward_eval09_12_T73198p4K.csv"
    _write(carbon_eval09_12_path, carbon_eval09_12_rows)

    carbon_cii_ciii_identity_rows: list[dict[str, Any]] = []
    for evaluation in range(9, 13):
        for phase_code in (20, 120):
            py_cii = _row_keyed(py_carbon_corr, evaluation=evaluation, phase_code=phase_code, ion_stage=2)
            py_ciii = _row_keyed(py_carbon_corr, evaluation=evaluation, phase_code=phase_code, ion_stage=3)
            xs_cii = _row_keyed(xs_carbon_corr, evaluation=evaluation, phase_code=phase_code, ion_stage=2)
            xs_ciii = _row_keyed(xs_carbon_corr, evaluation=evaluation, phase_code=phase_code, ion_stage=3)
            py_lower = _num(py_cii, "continuum_population")
            py_upper = _num(py_ciii, "ground_population")
            xs_lower = _num(xs_cii, "continuum_population")
            xs_upper = _num(xs_ciii, "ground_population")
            carbon_cii_ciii_identity_rows.append({
                "evaluation_index": evaluation,
                "phase_code": phase_code,
                "phase": _STATE_PHASE_NAMES.get(phase_code, f"phase_{phase_code}"),
                "lower_role": "C_II_continuum",
                "lower_ion_stage": 2,
                "lower_ion_index_python": "" if py_cii is None else py_cii.get("ion_index", ""),
                "lower_ion_index_xstar": "" if xs_cii is None else xs_cii.get("ion_index", ""),
                "lower_local_level_python": "" if py_cii is None else py_cii.get("continuum_local_level", ""),
                "lower_local_level_xstar": "" if xs_cii is None else xs_cii.get("continuum_local_level", ""),
                "lower_global_index_python": "" if py_cii is None else py_cii.get("continuum_global_index", ""),
                "lower_global_index_xstar": "" if xs_cii is None else xs_cii.get("continuum_global_index", ""),
                "upper_role": "C_III_ground",
                "upper_ion_stage": 3,
                "upper_ion_index_python": "" if py_ciii is None else py_ciii.get("ion_index", ""),
                "upper_ion_index_xstar": "" if xs_ciii is None else xs_ciii.get("ion_index", ""),
                "upper_local_level_python": "" if py_ciii is None else py_ciii.get("ground_local_level", ""),
                "upper_local_level_xstar": "" if xs_ciii is None else xs_ciii.get("ground_local_level", ""),
                "upper_global_index_python": "" if py_ciii is None else py_ciii.get("ground_global_index", ""),
                "upper_global_index_xstar": "" if xs_ciii is None else xs_ciii.get("ground_global_index", ""),
                "python_lower_population": py_lower,
                "python_upper_population": py_upper,
                "python_alias_absolute_difference": abs(py_lower - py_upper),
                "xstar_lower_population": xs_lower,
                "xstar_upper_population": xs_upper,
                "xstar_alias_absolute_difference": abs(xs_lower - xs_upper),
                "lower_python_xstar_relative_difference": abs(py_lower - xs_lower) / max(abs(py_lower), abs(xs_lower), atol),
                "upper_python_xstar_relative_difference": abs(py_upper - xs_upper) / max(abs(py_upper), abs(xs_upper), atol),
            })
    carbon_cii_ciii_identity_path = out / "zone1_carbon_cii_ciii_alias_identity_eval09_12_T73198p4K.csv"
    _write(carbon_cii_ciii_identity_path, carbon_cii_ciii_identity_rows)

    carbon_carryforward_rows: list[dict[str, Any]] = []
    for evaluation in range(9, 12):
        for ion_stage in range(1, 8):
            for field in ("population_total", "ground_population", "continuum_population", "next_ground_population"):
                py_write = _row_keyed(py_carbon_corr, evaluation=evaluation, phase_code=120, ion_stage=ion_stage)
                py_next = _row_keyed(py_carbon_corr, evaluation=evaluation + 1, phase_code=20, ion_stage=ion_stage)
                xs_write = _row_keyed(xs_carbon_corr, evaluation=evaluation, phase_code=120, ion_stage=ion_stage)
                xs_next = _row_keyed(xs_carbon_corr, evaluation=evaluation + 1, phase_code=20, ion_stage=ion_stage)
                py_w = _num(py_write, field)
                py_n = _num(py_next, field)
                xs_w = _num(xs_write, field)
                xs_n = _num(xs_next, field)
                carbon_carryforward_rows.append({
                    "writeback_evaluation": evaluation,
                    "next_entry_evaluation": evaluation + 1,
                    "ion_stage": ion_stage,
                    "field": field,
                    "python_phase120_value": py_w,
                    "python_next_phase20_value": py_n,
                    "python_carryforward_absolute_difference": abs(py_w - py_n),
                    "xstar_phase120_value": xs_w,
                    "xstar_next_phase20_value": xs_n,
                    "xstar_carryforward_absolute_difference": abs(xs_w - xs_n),
                    "phase120_python_xstar_relative_difference": abs(py_w - xs_w) / max(abs(py_w), abs(xs_w), atol),
                    "next_phase20_python_xstar_relative_difference": abs(py_n - xs_n) / max(abs(py_n), abs(xs_n), atol),
                })
    carbon_carryforward_path = out / "zone1_carbon_writeback_to_next_entry_eval09_12_T73198p4K.csv"
    _write(carbon_carryforward_path, carbon_carryforward_rows)

    carbon_eval09_12_first_tolerance_failure = _first_row(
        carbon_eval09_12_rows,
        predicate=lambda row: not bool(row.get("within_tolerance", False)),
    )

    # v0.4.92 diagnostic-only: compare the carbon solve path for evaluations
    # 9--11 and isolate the physical C II-continuum / C III-ground shared row.
    # This deliberately avoids the generic next-ground stage-correlation field
    # that v0.4.90 identified as timing-sensitive on the XSTAR side.
    py_carbon_solve_eval09_11 = _read_optional(py / "python_zone1_carbon_solve_path_eval09_11_T73198p4K.csv")
    xs_carbon_solve_eval09_11 = _read_optional(xs / "xstar_zone1_carbon_solve_path_eval09_11_T73198p4K.csv")
    carbon_solve_keys = (
        "evaluation_index", "phase_code", "outer_iteration", "fixed_iteration",
        "compact_index", "superlevel", "ion_counter", "ion_stage",
    )
    carbon_solve_eval09_11_rows = _numeric_comparison_with_presence(
        py_carbon_solve_eval09_11, xs_carbon_solve_eval09_11,
        keys=carbon_solve_keys, fields=("population",), rtol=rtol, atol=atol,
    ) if py_carbon_solve_eval09_11 or xs_carbon_solve_eval09_11 else []
    carbon_solve_eval09_11_path = out / "zone1_carbon_solve_path_eval09_11_comparison_T73198p4K.csv"
    _write(carbon_solve_eval09_11_path, carbon_solve_eval09_11_rows)

    py_carbon_solve_stage_eval09_11 = _read_optional(py / "python_zone1_carbon_solve_stage_totals_eval09_11_T73198p4K.csv")
    xs_carbon_solve_stage_eval09_11 = _read_optional(xs / "xstar_zone1_carbon_solve_stage_totals_eval09_11_T73198p4K.csv")
    carbon_solve_stage_keys = (
        "evaluation_index", "phase_code", "outer_iteration",
        "ion_counter", "ion_stage",
    )
    carbon_solve_stage_eval09_11_rows = _numeric_comparison_with_presence(
        py_carbon_solve_stage_eval09_11, xs_carbon_solve_stage_eval09_11,
        keys=carbon_solve_stage_keys, fields=("population_total",),
        rtol=rtol, atol=atol,
    ) if py_carbon_solve_stage_eval09_11 or xs_carbon_solve_stage_eval09_11 else []
    carbon_solve_stage_eval09_11_path = out / "zone1_carbon_solve_stage_totals_eval09_11_comparison_T73198p4K.csv"
    _write(carbon_solve_stage_eval09_11_path, carbon_solve_stage_eval09_11_rows)

    carbon_cii_ciii_solve_rows: list[dict[str, Any]] = []

    def _append_boundary_row(row: Mapping[str, Any], *, locus: str, identity: str) -> None:
        carbon_cii_ciii_solve_rows.append({
            "evaluation_index": row.get("evaluation_index", ""),
            "phase_code": row.get("phase_code", ""),
            "phase": _STATE_PHASE_NAMES.get(int(row.get("phase_code", 0) or 0), f"phase_{row.get('phase_code', '')}"),
            "outer_iteration": row.get("outer_iteration", 0),
            "fixed_iteration": row.get("fixed_iteration", 0),
            "compact_index": row.get("compact_index", ""),
            "ion_counter": row.get("ion_counter", ""),
            "ion_stage": row.get("ion_stage", ""),
            "field": row.get("field", ""),
            "locus": locus,
            "physical_identity": identity,
            "python_present": row.get("python_present", True),
            "xstar_present": row.get("xstar_present", True),
            "comparison_status": row.get("comparison_status", "matched"),
            "python_value": row.get("python_value", ""),
            "xstar_value": row.get("xstar_value", ""),
            "absolute_difference": row.get("absolute_difference", ""),
            "relative_difference": row.get("relative_difference", ""),
            "within_tolerance": row.get("within_tolerance", False),
        })

    for row in carbon_solve_eval09_11_rows:
        if (
            str(row.get("comparison_status", "matched")) == "matched"
            and int(row.get("compact_index", 0) or 0) == 1
            and int(row.get("phase_code", 0) or 0) in (30, 40, 50, 60, 70, 80)
        ):
            _append_boundary_row(
                row, locus="shared_compact_row",
                identity="C_II_continuum_equals_C_III_ground",
            )
    for row in carbon_solve_stage_eval09_11_rows:
        if (
            str(row.get("comparison_status", "matched")) == "matched"
            and int(row.get("ion_stage", 0) or 0) == 3
            and int(row.get("phase_code", 0) or 0) in (41, 90, 100)
        ):
            _append_boundary_row(
                row, locus="C_III_stage_total",
                identity="C_III_total_from_solve_vector",
            )
    for row in carbon_corr_rows:
        if (
            str(row.get("comparison_status", "matched")) == "matched"
            and 9 <= int(row.get("evaluation_index", 0) or 0) <= 11
            and int(row.get("phase_code", 0) or 0) == 120
            and int(row.get("ion_stage", 0) or 0) == 2
            and str(row.get("field", "")) == "continuum_population"
        ):
            _append_boundary_row(
                row, locus="phase120_writeback_alias",
                identity="C_II_continuum_equals_C_III_ground",
            )
    carbon_cii_ciii_solve_rows.sort(key=lambda row: (
        int(row.get("evaluation_index", 0) or 0),
        int(row.get("phase_code", 0) or 0),
        int(row.get("outer_iteration", 0) or 0),
        int(row.get("fixed_iteration", 0) or 0),
        int(row.get("compact_index", 0) or 0),
        str(row.get("locus", "")),
    ))
    carbon_cii_ciii_solve_path = out / "zone1_carbon_cii_ciii_solve_path_eval09_11_T73198p4K.csv"
    _write(carbon_cii_ciii_solve_path, carbon_cii_ciii_solve_rows)
    carbon_cii_ciii_first_tolerance_failure = _first_row(
        carbon_cii_ciii_solve_rows,
        predicate=lambda row: str(row.get("comparison_status", "matched")) == "matched"
        and not bool(row.get("within_tolerance", False)),
    )

    # v0.4.92 diagnostic-only: inner msolvelucy audit for evaluation 11,
    # outer iteration 1.  These rows compare the condensed matrix row,
    # RHS/source vector, solved superlevel population, expansion/scatter,
    # fixed-point normalization denominator, and ordered dominant
    # contributions for the C II-continuum / C III-ground shared row.
    py_inner_eval11 = _read_optional(py / "python_zone1_carbon_msolvelucy_inner_eval11_outer1_T73198p4K.csv")
    xs_inner_eval11 = _read_optional(xs / "xstar_zone1_carbon_msolvelucy_inner_eval11_outer1_T73198p4K.csv")
    inner_keys = (
        "evaluation_index", "outer_iteration", "row_kind",
        "compact_index", "superlevel", "ion_counter", "ion_stage",
        "row_superlevel", "column_superlevel", "term_index",
        "source_row", "source_column", "source_record", "rate_type", "data_type",
    )
    inner_fields = (
        "population", "population_before_condensed_solve",
        "population_after_condensed_solve", "raw_matrix_value",
        "normalized_matrix_value", "rr", "population_outer_start",
        "population_after_condensed", "population_after_fixed_point",
        "xm_before_normalization", "normalization_denominator",
        "population_before", "riu", "rui", "ril", "rli",
        "population_unnormalized", "population_after", "aj1", "aj2",
        "rr_mm", "rr_nn", "offdiag_contribution", "diag_contribution",
        "importance",
    )
    carbon_inner_eval11_rows = _numeric_comparison_with_presence(
        py_inner_eval11, xs_inner_eval11, keys=inner_keys, fields=inner_fields,
        rtol=rtol, atol=atol,
    ) if py_inner_eval11 or xs_inner_eval11 else []
    carbon_inner_eval11_path = out / "zone1_carbon_msolvelucy_inner_eval11_outer1_comparison_T73198p4K.csv"
    _write(carbon_inner_eval11_path, carbon_inner_eval11_rows)
    carbon_inner_eval11_first_tolerance_failure = _first_row(
        carbon_inner_eval11_rows,
        predicate=lambda row: str(row.get("comparison_status", "matched")) == "matched"
        and not bool(row.get("within_tolerance", False)),
    )

    py_alias = _read_optional(py / "python_zone1_carbon_alias_boundaries_T73198p4K.csv")
    xs_alias = _read_optional(xs / "xstar_zone1_carbon_alias_boundaries_T73198p4K.csv")
    alias_keys = (
        "lower_ion_index", "lower_ion_stage", "lower_local_level",
        "lower_global_index", "upper_ion_index", "upper_ion_stage",
        "upper_local_level", "upper_global_index",
    )
    alias_rows = _numeric_comparison(
        py_alias, xs_alias, keys=alias_keys,
        fields=("lower_population", "upper_population", "absolute_difference"),
        rtol=rtol, atol=atol,
    ) if py_alias or xs_alias else []
    alias_path = out / "zone1_carbon_alias_boundary_comparison_T73198p4K.csv"
    _write(alias_path, alias_rows)
    alias_ready = bool(alias_rows) and all(bool(row["within_tolerance"]) for row in alias_rows)

    source_order_state_path_probe_available = bool(
        py_h and xs_h and py_electron and xs_electron
    )

    def _failure_candidate(rows, phase_code: int | None = None):
        failed = [
            row for row in rows
            if row.get("comparison_status", "matched") == "matched"
            and not bool(row.get("within_tolerance", False))
        ]
        if not failed:
            return None
        def _order(row):
            evaluation = row.get("evaluation_index", "")
            evaluation_order = 999999 if evaluation in (None, "") else int(evaluation)
            return (
                evaluation_order,
                int(row.get("phase_code", phase_code or 0)),
                int(row.get("outer_iteration", 0)),
                int(row.get("fixed_iteration", 0)),
                int(row.get("compact_index", 0)),
                int(row.get("ion_counter", 0)),
                int(row.get("ion_stage", 0)),
                int(row.get("global_index", 0)),
                int(row.get("element_z", 0)),
                str(row.get("field", "")),
            )
        return min(failed, key=_order)

    candidates = []
    for rows, forced_phase, family in (
        (hydrogen_matched_rows, None, "hydrogen"),
        (state_rows, None, "level_state"),
        (stage_rows, None, "stage_total"),
        (electron_rows, 140, "electron_fraction"),
        (carbon_corr_rows, None, "carbon_stage_correlation"),
        (alias_rows, 130, "alias_boundary"),
    ):
        row = _failure_candidate(rows, forced_phase)
        if row is not None:
            phase_code = int(row.get("phase_code", forced_phase or 0))
            raw_evaluation = row.get("evaluation_index", "")
            evaluation_index = 999999 if raw_evaluation in (None, "") else int(raw_evaluation)
            candidates.append((evaluation_index, phase_code, family, row))
    first_state_path_divergence = None
    if candidates:
        evaluation_index, phase_code, family, row = min(
            candidates,
            key=lambda item: (
                item[0],
                item[1],
                int(item[3].get("outer_iteration", 0)),
                int(item[3].get("fixed_iteration", 0)),
                int(item[3].get("compact_index", 0)),
                int(item[3].get("ion_stage", 0)),
            ),
        )
        if phase_code <= 21:
            locus = "incoming_global_state_or_live_hydrogen"
        elif phase_code == 25:
            locus = "hydrogen_preliminary_rate_totals"
        elif phase_code == 30:
            locus = "global_to_compact_mapping"
        elif phase_code < 100:
            locus = "msolvelucy_iteration_path"
        elif phase_code == 100:
            locus = "final_vector_xii_accumulation"
        elif phase_code == 110:
            locus = "element_workspace_writeback"
        elif phase_code == 120:
            locus = "global_xilevg_writeback"
        elif phase_code == 140:
            locus = "element_electron_fraction_accumulation"
        else:
            locus = "continuum_ground_alias_writeback"
        first_state_path_divergence = {
            "family": family,
            "evaluation_index": None if evaluation_index == 999999 else evaluation_index,
            "phase_code": phase_code,
            "phase": _STATE_PHASE_NAMES.get(phase_code, f"phase_{phase_code}"),
            "locus": locus,
            **{key: row.get(key) for key in (
                "outer_iteration", "fixed_iteration", "compact_index",
                "ion_counter", "ion_stage", "ion_index", "local_level",
                "global_index", "full_element_index", "element_z", "field",
                "python_value", "xstar_value", "absolute_difference",
                "relative_difference",
            ) if key in row},
        }

    # Keep the old raw-fingerprint comparison as an observation, not a gate.
    py_fp = _read(py / "python_zone1_calc_hmc_all_input_fingerprints.csv")
    xs_fp = _read(xs / "xstar_zone1_calc_hmc_all_input_fingerprints.csv")
    py_fp_map = {(int(row["evaluation_index"]), row["name"]): row for row in py_fp}
    xs_fp_map = {(int(row["evaluation_index"]), row["name"]): row for row in xs_fp}
    fp_rows: list[dict[str, Any]] = []
    for key in sorted(set(py_fp_map) & set(xs_fp_map)):
        prow = py_fp_map[key]
        xrow = xs_fp_map[key]
        fp_rows.append(
            {
                "evaluation_index": key[0], "name": key[1],
                "python_count": int(prow["count"]), "xstar_count": int(xrow["count"]),
                "python_sha256": prow["sha256"], "xstar_sha256": xrow["sha256"],
                "exact_match": int(prow["count"]) == int(xrow["count"])
                and prow["sha256"] == xrow["sha256"],
            }
        )
    fingerprint_path = out / "zone1_input_fingerprint_comparison.csv"
    _write(fingerprint_path, fp_rows)

    replay = json.loads(
        (py / "python_zone1_same_entry_replay_summary.json").read_text(encoding="utf-8")
    )
    same_entry_ready = bool(replay.get("ready", False))

    # 10. DSEC is allowed to continue only after all requested physical gates.
    thermal_root_ready = bool(
        same_entry_ready
        and type15_record_gate_passed
        and type59_record_gate_passed
        and civ_rate_ready
        and civ_fraction_ready
        and civ_retained_ready
        and cv_topology_ready
        and cv_coefficients_ready
        and initial_ready
        and normalization_ready
        and level20_ready
        and cooling_ready
    )
    summary = {
        "diagnostic_release": "0.4.92",
        "probe_contract_version": "0.4.92",
        "same_entry_replay_ready": same_entry_ready,
        "type15_record_level_proof_applicable": type15_record_level_proof_applicable,
        "type15_record_gate_passed": type15_record_gate_passed,
        "type15_record_coverage_ready": record_coverage_ready,
        "type15_record_numeric_parity_ready": record_numeric_ready,
        "type15_final_shell_threshold_ready": type15_last_shell_ready,
        "type15_parent_vs_effective_difference_observed": type15_parent_diff_observed,
        "type15_record_level_proof_ready": type15_record_proof_ready,
        "type59_record_level_proof_applicable": type59_record_level_proof_applicable,
        "type59_record_gate_passed": type59_record_gate_passed,
        "type59_record_coverage_ready": type59_record_coverage_ready,
        "type59_endpoint_mapping_ready": type59_endpoint_mapping_ready,
        "type59_rate_heating_parity_ready": type59_rate_heating_parity_ready,
        "type59_record_level_proof_ready": type59_record_level_proof_ready,
        "civ_record_level_parity_ready": bool(
            record_coverage_ready and record_numeric_ready
        ),
        "python_civ_dominant_record": (
            None
            if dominant_python_civ_record is None
            else int(dominant_python_civ_record["record"])
        ),
        "python_civ_dominant_data_type": (
            None
            if dominant_python_civ_record is None
            else int(dominant_python_civ_record["data_type"])
        ),
        "python_civ_dominant_rate_type": (
            None
            if dominant_python_civ_record is None
            else int(dominant_python_civ_record["rate_type"])
        ),
        "python_civ_dominant_pirti_contribution": (
            None
            if dominant_python_civ_record is None
            else _float(dominant_python_civ_record, "pirti_contribution")
        ),
        "python_civ_type15_is_dominant": bool(
            dominant_python_civ_record is not None
            and int(dominant_python_civ_record["data_type"]) == 15
        ),
        "civ_preliminary_photoionization_parity_ready": civ_rate_ready,
        "civ_preliminary_fraction_parity_ready": civ_fraction_ready,
        "civ_retained_by_critf_ready": civ_retained_ready,
        "cv_compact_topology_ready": cv_topology_ready,
        "cv_logical_row_count_python": len(py_matrix_rows),
        "cv_logical_row_count_xstar": len(xs_matrix_rows),
        "cv_logical_coefficient_parity_ready": cv_coefficients_ready,
        "cv_initial_population_vector_ready": initial_ready,
        "cv_normalization_row_ready": normalization_ready,
        "cv_level20_population_parity_ready": level20_ready,
        "carbon_cooling_logical_parity_ready": cooling_ready,
        "source_order_state_path_probe_available": source_order_state_path_probe_available,
        "hydrogen_state_path_parity_ready": hydrogen_state_ready,
        "hydrogen_phase20_21_canonicalized": True,
        "hydrogen_matched_comparison_rows": len(hydrogen_matched_rows),
        "hydrogen_unmatched_key_rows": len(hydrogen_unmatched_rows),
        "hydrogen_first_differing_evaluation": hydrogen_first_differing_evaluation,
        "hydrogen_first_raw_numeric_difference": _row_summary(hydrogen_first_raw_numeric_difference),
        "hydrogen_first_tolerance_failure": _row_summary(hydrogen_first_tolerance_failure),
        "hydrogen_first_unmatched_key_failure": _row_summary(hydrogen_first_unmatched_key_failure),
        "hydrogen_recombination_audit_eval18_24_ready": bool(hydrogen_recombination_audit_rows),
        "hydrogen_recombination_audit_eval18_24_first_tolerance_failure": _row_summary(hydrogen_recombination_first_tolerance_failure),
        "electron_fraction_path_parity_ready": electron_ready,
        "carbon_stage_correlation_parity_ready": carbon_corr_ready,
        "carbon_carryforward_eval09_12_ready": bool(carbon_eval09_12_rows),
        "carbon_carryforward_eval09_12_first_tolerance_failure": _row_summary(carbon_eval09_12_first_tolerance_failure),
        "carbon_cii_ciii_alias_identity_eval09_12_ready": bool(carbon_cii_ciii_identity_rows),
        "carbon_writeback_to_next_entry_eval09_12_ready": bool(carbon_carryforward_rows),
        "carbon_solve_path_eval09_11_ready": bool(carbon_solve_eval09_11_rows),
        "carbon_solve_stage_totals_eval09_11_ready": bool(carbon_solve_stage_eval09_11_rows),
        "carbon_cii_ciii_solve_path_eval09_11_ready": bool(carbon_cii_ciii_solve_rows),
        "carbon_cii_ciii_solve_path_eval09_11_first_tolerance_failure": _row_summary(carbon_cii_ciii_first_tolerance_failure),
        "carbon_msolvelucy_inner_eval11_outer1_ready": bool(carbon_inner_eval11_rows),
        "carbon_msolvelucy_inner_eval11_outer1_first_tolerance_failure": _row_summary(carbon_inner_eval11_first_tolerance_failure),
        "carbon_state_path_parity_ready": state_path_ready,
        "carbon_stage_totals_parity_ready": stage_totals_ready,
        "carbon_alias_boundary_parity_ready": alias_ready,
        "phase110_physical_identity_key_ready": True,
        "state_path_probe_is_diagnostic_only": True,
        "source_order_first_divergence": first_state_path_divergence,
        "production_physics_modified_in_this_release": False,
        "thermal_root_may_continue": thermal_root_ready,
        "input_fingerprint_common_count": len(fp_rows),
        "input_fingerprint_exact_observation": bool(fp_rows) and all(
            bool(row["exact_match"]) for row in fp_rows
        ),
        "production_rates_modified": True,
        "production_rate_change_scope": (
            "ucalc_data_type_15_final_shell_threshold_plus_"
            "data_type_59_compact_fields_continuum_offset_pre_swap_zeroing_"
            "literal_nbinc_enxt_excited_parent_weight_plus_calc_ion_rates_lfpi1_"
            "plus_calc_hmc_all_live_xh0_xh1_and_strict_msolvelucy"
        ),
        "production_solver_modified": True,
        "production_solver_change_scope": (
            "msolvelucy_no_lstsq_no_dense_rescue_literal_1dminus24_"
            "normalization_ordered_diff_diff2_and_rate_type5_falpha"
        ),
        "live_hydrogen_charge_exchange_state": True,
        "production_tolerances_modified": False,
        "empirical_corrections_added": False,
    }
    summary_path = out / "zone1_dsec_parity_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = out / "zone1_dsec_parity_summary.md"
    markdown_path.write_text(
        "# Zone-1 DSEC C IV record/topology parity gate\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n", encoding="utf-8",
    )
    return {
        "fingerprint_comparison_csv": fingerprint_path,
        "rates_comparison_csv": rates_path,
        "civ_record_comparison_csv": record_path,
        "topology_comparison_csv": topology_summary_path,
        "cv_topology_offsets_csv": offset_path,
        "matrix_comparison_csv": matrix_path,
        "initial_population_comparison_csv": initial_path,
        "normalization_row_comparison_csv": normalization_path,
        "cv_level_population_comparison_csv": level_path,
        "cooling_comparison_csv": cooling_path,
        "carbon_state_path_comparison_csv": state_path,
        "carbon_stage_total_comparison_csv": stage_path,
        "hydrogen_state_path_comparison_csv": hydrogen_path,
        "hydrogen_recombination_audit_eval18_24_csv": hydrogen_recombination_audit_path,
        "electron_fraction_path_comparison_csv": electron_path,
        "carbon_stage_correlation_comparison_csv": carbon_corr_path,
        "carbon_stage_carryforward_eval09_12_csv": carbon_eval09_12_path,
        "carbon_cii_ciii_alias_identity_eval09_12_csv": carbon_cii_ciii_identity_path,
        "carbon_writeback_to_next_entry_eval09_12_csv": carbon_carryforward_path,
        "carbon_solve_path_eval09_11_comparison_csv": carbon_solve_eval09_11_path,
        "carbon_solve_stage_totals_eval09_11_comparison_csv": carbon_solve_stage_eval09_11_path,
        "carbon_msolvelucy_inner_eval11_outer1_comparison_csv": carbon_inner_eval11_path,
        "carbon_cii_ciii_solve_path_eval09_11_csv": carbon_cii_ciii_solve_path,
        "carbon_alias_boundary_comparison_csv": alias_path,
        "summary_json": summary_path,
        "summary_markdown": markdown_path,
    }


__all__ = [
    "load_xstar_target_state",
    "load_xstar_carbon_cooling_terms",
    "analyze_xstar_zone1_probe",
    "compare_zone1_probe_with_python",
    "make_carbon_cooling_gate",
    "enforce_cooling_gate",
]
