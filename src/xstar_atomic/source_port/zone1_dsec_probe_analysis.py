"""Post-process and compare the v0.4.78 original-XSTAR zone-1 probe."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import struct
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

from .dsec import DsecPortError, load_xstar_dsec_trajectory
from .fortran_numbers import parse_fortran_float
from .zone1_dsec_diagnostic import (
    TARGET_CV_LOCAL_LEVELS,
    TARGET_TEMPERATURE_K,
    carbon_cooling_rows,
    compare_cooling_terms,
    enforce_cooling_gate,
)


def _read(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise DsecPortError(f"missing zone-1 probe product: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


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
    rows = _read(root / "xstar_dsec_calc_hmc_all_call_correlation.csv")
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


def _numeric_fingerprint_rows(
    root: Path, call_to_eval: Mapping[int, int]
) -> list[dict[str, Any]]:
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
        rows = _read(root / filename)
        grouped: Dict[tuple[int, str], list[tuple[int, float | int]]] = {}
        for position, row in enumerate(rows, start=1):
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
                grouped.setdefault((call, canonical_name), []).append(
                    (logical_index, value)
                )
        for (call, name), values in sorted(grouped.items()):
            output.append(
                _fingerprint(
                    call=call,
                    evaluation=call_to_eval[call],
                    name=name,
                    values=values,
                )
            )

    klev_rows = _read(root / "xstar_zone1_calc_hmc_all_input_klev_probe.csv")
    grouped_klev: Dict[int, list[tuple[int, str]]] = {}
    for row in klev_rows:
        call = int(row["calc_hmc_all_call_id"])
        if call in call_to_eval:
            grouped_klev.setdefault(call, []).append(
                (int(row["column_index"]), row["klev_hex"])
            )
    for call, values in sorted(grouped_klev.items()):
        output.append(
            _fingerprint(
                call=call,
                evaluation=call_to_eval[call],
                name="leveltemp_workspace.klev",
                values=values,
            )
        )

    summary_rows = _read(root / "xstar_calc_hmc_all_input_summary_probe.csv")
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
    for row in summary_rows:
        call = int(row["calc_hmc_all_call_id"])
        if call not in call_to_eval:
            continue
        values = [
            (
                index,
                int(row[field])
                if field in {"lcdd", "ncn2"}
                else parse_fortran_float(row[field]),
            )
            for index, field in enumerate(scalar_fields, start=1)
        ]
        output.append(
            _fingerprint(
                call=call,
                evaluation=call_to_eval[call],
                name="runtime_scalars",
                values=values,
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
    summaries = _read(root / "xstar_calc_hmc_all_input_summary_probe.csv")
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
    rows = _read(root / "xstar_zone1_calc_hmc_all_thermal_terms_probe.csv")
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


def analyze_xstar_zone1_probe(
    probe_dir: str | Path,
    *,
    out_dir: str | Path,
    target_temperature_k: float = TARGET_TEMPERATURE_K,
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

    fingerprints = _numeric_fingerprint_rows(root, call_to_eval)
    fingerprints_path = out / "xstar_zone1_calc_hmc_all_input_fingerprints.csv"
    _write(fingerprints_path, fingerprints)

    target_state = load_xstar_target_state(
        root, target_temperature_k=target_temperature_k
    )
    target_call = int(target_state["call_id"])
    target_eval = int(target_state["evaluation_index"])

    pre = [
        row
        for row in _read(root / "xstar_calc_hmc_element_pre_matrix_probe.csv")
        if int(row["calc_hmc_all_call_id"]) == target_call
        and int(row["element_z"]) == 6
    ]
    second = [
        row
        for row in _read(
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

    records = [
        row
        for row in _read(root / "xstar_zone1_calc_hmc_all_rate_records_probe.csv")
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
        for row in _read(root / "xstar_calc_hmc_all_matrix_terms_probe.csv")
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

    cooling = load_xstar_carbon_cooling_terms(root)
    cooling_path = out / "xstar_zone1_carbon_cooling_terms.csv"
    _write(cooling_path, cooling)

    summary = {
        "diagnostic_release": "0.4.78",
        "dsec_call_id": 1,
        "n_evaluations": len(sequence_rows),
        "n_input_fingerprints": len(fingerprints),
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
        "n_cv_matrix_audit_rows": len(matrix_rows),
        "n_carbon_cooling_terms": len(cooling),
        "production_rates_modified": False,
        "production_tolerances_modified": False,
        "empirical_corrections_added": False,
    }
    summary_path = out / "xstar_zone1_dsec_probe_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "sequence_csv": sequence_path,
        "fingerprints_csv": fingerprints_path,
        "rates_csv": rates_path,
        "matrix_csv": matrix_path,
        "cooling_csv": cooling_path,
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
        return tuple(str(row[field]) for field in keys)

    py = {key(row): row for row in python_rows}
    xs = {key(row): row for row in xstar_rows}
    output: list[dict[str, Any]] = []
    for item in sorted(set(py) | set(xs)):
        prow = py.get(item)
        xrow = xs.get(item)
        for field in fields:
            pv = 0.0 if prow is None else _float(prow, field)
            xv = 0.0 if xrow is None else _float(xrow, field)
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


def compare_zone1_probe_with_python(
    *,
    xstar_analysis_dir: str | Path,
    python_diagnostic_dir: str | Path,
    out_dir: str | Path,
    rtol: float = 5.0e-5,
    atol: float = 1.0e-30,
) -> Mapping[str, Path]:
    xs = Path(xstar_analysis_dir)
    py = Path(python_diagnostic_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    py_cooling = _read(py / "python_zone1_carbon_cooling_terms.csv")
    xs_cooling = _read(xs / "xstar_zone1_carbon_cooling_terms.csv")
    cooling_rows = compare_cooling_terms(
        py_cooling, xs_cooling, rtol=rtol, atol=atol
    )
    cooling_path = out / "zone1_carbon_cooling_term_comparison.csv"
    _write(cooling_path, [asdict(row) for row in cooling_rows])

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

    matrix_fields = (
        "escape_factor_in",
        "escape_factor_out",
        "density_scale",
        "ans1",
        "ans2",
        "ans3",
        "ans4",
        "ans5",
        "ans6",
        "aj1",
        "aj2",
        "cj",
        "cj2",
        "population",
        "cooling_contribution",
        "cooling2_contribution",
    )
    matrix_rows = _numeric_comparison(
        _read(py / "python_zone1_cv_matrix_levels_4_6_10_12_20.csv"),
        _read(xs / "xstar_zone1_cv_matrix_levels_4_6_10_12_20.csv"),
        keys=("local_level", "record", "role", "row", "column"),
        fields=matrix_fields,
        rtol=rtol,
        atol=atol,
    )
    matrix_path = out / "zone1_cv_matrix_comparison_T73198p4K.csv"
    _write(matrix_path, matrix_rows)

    py_fp = _read(py / "python_zone1_calc_hmc_all_input_fingerprints.csv")
    xs_fp = _read(xs / "xstar_zone1_calc_hmc_all_input_fingerprints.csv")
    py_fp_map = {
        (int(row["evaluation_index"]), row["name"]): row for row in py_fp
    }
    xs_fp_map = {
        (int(row["evaluation_index"]), row["name"]): row for row in xs_fp
    }
    fp_rows: list[dict[str, Any]] = []
    for key in sorted(set(py_fp_map) & set(xs_fp_map)):
        prow = py_fp_map[key]
        xrow = xs_fp_map[key]
        fp_rows.append(
            {
                "evaluation_index": key[0],
                "name": key[1],
                "python_count": int(prow["count"]),
                "xstar_count": int(xrow["count"]),
                "python_sha256": prow["sha256"],
                "xstar_sha256": xrow["sha256"],
                "exact_match": int(prow["count"]) == int(xrow["count"])
                and prow["sha256"] == xrow["sha256"],
            }
        )
    fingerprint_path = out / "zone1_input_fingerprint_comparison.csv"
    _write(fingerprint_path, fp_rows)

    replay = json.loads(
        (py / "python_zone1_same_entry_replay_summary.json").read_text(
            encoding="utf-8"
        )
    )
    rate_ready = bool(rate_rows) and all(
        str(row["within_tolerance"]).lower() == "true"
        if isinstance(row["within_tolerance"], str)
        else bool(row["within_tolerance"])
        for row in rate_rows
    )
    matrix_ready = bool(matrix_rows) and all(
        bool(row["within_tolerance"]) for row in matrix_rows
    )
    cooling_ready = bool(cooling_rows) and all(
        row.within_tolerance for row in cooling_rows
    )
    fingerprint_ready = bool(fp_rows) and all(
        bool(row["exact_match"]) for row in fp_rows
    )
    summary = {
        "diagnostic_release": "0.4.78",
        "same_entry_replay_ready": bool(replay.get("ready", False)),
        "input_fingerprint_common_count": len(fp_rows),
        "input_fingerprint_exact_ready": fingerprint_ready,
        "carbon_rate_parity_ready": rate_ready,
        "cv_matrix_parity_ready": matrix_ready,
        "carbon_cooling_term_parity_ready": cooling_ready,
        "thermal_root_may_continue": bool(
            replay.get("ready", False)
            and fingerprint_ready
            and rate_ready
            and matrix_ready
            and cooling_ready
        ),
        "production_rates_modified": False,
        "production_tolerances_modified": False,
        "empirical_corrections_added": False,
    }
    summary_path = out / "zone1_dsec_parity_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path = out / "zone1_dsec_parity_summary.md"
    markdown_path.write_text(
        "# Zone-1 DSEC parity gate\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {
        "fingerprint_comparison_csv": fingerprint_path,
        "rates_comparison_csv": rates_path,
        "matrix_comparison_csv": matrix_path,
        "cooling_comparison_csv": cooling_path,
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
