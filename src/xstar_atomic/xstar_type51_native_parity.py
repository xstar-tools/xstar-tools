"""Source-code parity audit for native XSTAR data-type 51 collision rates.

The v0.3.202 native-readiness audit identified type 51 as the dominant rate
family inside the six-row O VII compact subsystem.  This module evaluates the
existing Python Burgess--Tully decoder with the exact ``ucalc.f90`` type-51
formula and compares it record by record with the selected XSTAR ``ans1`` and
``ans2`` probe values and the mapped ``calc_hmc_ion`` compact matrix terms.

This remains an audit.  It does not enable type-51 terms in the production
expanded-basis solver.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .rates_type51 import evaluate_type51_ucalc_record


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return int(round(number)) if math.isfinite(number) else default
    except Exception:
        return default


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if str(key) not in fields:
                fields.append(str(key))
    if not fields:
        fields = ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _resolve_product(path: str | Path, default_name: str) -> Path:
    root = Path(path)
    if root.is_file() and root.name == default_name:
        return root
    if root.is_dir():
        direct = root / default_name
        if direct.exists():
            return direct
        hits = sorted(root.rglob(default_name))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"could not find {default_name} under {root}")


def _load_summary(root: str | Path) -> Dict[str, Any]:
    try:
        path = _resolve_product(root, "xstar_priority_matrix_closure_audit.json")
    except FileNotFoundError:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        summary = payload.get("summary", payload)
        if isinstance(summary, dict):
            return dict(summary)
    return {}


def _relative_difference(observed: float, expected: float) -> float:
    return abs(observed - expected) / max(abs(observed), abs(expected), 1.0e-300)


def _expected_matrix_coefficient(kind: str, ans1: float, ans2: float) -> float | None:
    return {
        "forward_offdiag": ans1,
        "reverse_offdiag": ans2,
        "forward_diag_loss": -ans1,
        "reverse_diag_loss": -ans2,
    }.get(kind)


def _decode_type51_records_from_atdb(
    *,
    atdb_fits: str | Path,
    wanted_records: Iterable[int],
    index_cache_path: str | Path | None = None,
    rebuild_index_cache: bool = False,
) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, List[Dict[str, Any]]], Dict[str, Any]]:
    wanted = {int(record) for record in wanted_records}
    decoded: Dict[int, Dict[str, Any]] = {}
    grids: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    metadata: Dict[str, Any] = {
        "atdb_fits": str(atdb_fits),
        "atdb_status": "not_loaded",
        "n_wanted_records": len(wanted),
    }
    if not wanted:
        metadata["atdb_status"] = "no_wanted_records"
        return decoded, dict(grids), metadata

    from .collisions import decode_collision_record
    from .hierarchy import ATDB, IndexedRecord
    from .lines import extract_levels, level_maps

    with ATDB(atdb_fits, prompt_for_data=False) as db:
        type51_records = db.select_records(
            data_type=51,
            rate_type=3,
            use_cache=True,
            cache_path=index_cache_path,
            rebuild_cache=rebuild_index_cache,
            cache_format="npz",
        )
        selected: Dict[int, IndexedRecord] = {
            int(record.recno): record for record in type51_records if int(record.recno) in wanted
        }
        groups: Dict[Tuple[int, int], List[int]] = defaultdict(list)
        for recno, record in selected.items():
            if record.element_z is None or record.ion_stage is None:
                continue
            groups[(int(record.element_z), int(record.ion_stage))].append(recno)

        for (element_z, ion_stage), recnos in sorted(groups.items()):
            ion_records = db.select_records(
                z=element_z,
                ion_stage=ion_stage,
                use_cache=True,
                cache_path=index_cache_path,
                rebuild_cache=False,
                cache_format="npz",
            )
            levels = extract_levels(db, ion_records, element_z, ion_stage)
            level_by_index, labels, energies, statistical_weights = level_maps(levels)
            for recno in recnos:
                record = selected[recno]
                summary, grid_rows = decode_collision_record(
                    db, record, labels, energies, statistical_weights, level_by_index
                )
                decoded[recno] = dict(summary)
                grids[recno] = [dict(row) for row in grid_rows]

        metadata.update({
            "atdb_status": "loaded",
            "atdb_date": db.date or "",
            "atdb_creator": db.creator or "",
            "index_cache_status": getattr(db, "_last_index_cache_status", ""),
            "n_type51_records_selected_from_atdb": len(selected),
            "n_type51_records_decoded": len(decoded),
            "n_type51_records_missing_from_atdb_selection": len(wanted - set(selected)),
        })
    return decoded, dict(grids), metadata


def build_type51_native_parity_audit(
    *,
    priority_matrix_closure_audit: str | Path,
    atdb_fits: str | Path | None = None,
    relative_rate_tolerance: float = 5.0e-5,
    index_cache_path: str | Path | None = None,
    rebuild_index_cache: bool = False,
    decoded_type51_rows: Sequence[Mapping[str, Any]] | None = None,
    decoded_type51_grid_rows: Sequence[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Compare native type-51 rates with selected XSTAR probe records.

    ``decoded_type51_rows`` and ``decoded_type51_grid_rows`` are primarily for
    tests and pre-decoded workflows.  Normal use should supply ``atdb_fits``.
    """
    if relative_rate_tolerance <= 0.0:
        raise ValueError("relative_rate_tolerance must be positive")

    ucalc_path = _resolve_product(
        priority_matrix_closure_audit,
        "xstar_priority_matrix_closure_audit_ucalc_records.csv",
    )
    matrix_path = _resolve_product(
        priority_matrix_closure_audit,
        "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv",
    )
    parent_summary = _load_summary(priority_matrix_closure_audit)
    ucalc_all = _read_csv(ucalc_path)
    matrix_all = _read_csv(matrix_path)
    ucalc_rows = [row for row in ucalc_all if _as_int(row.get("ltyp"), -1) == 51]
    matrix_rows = [row for row in matrix_all if _as_int(row.get("ltyp"), -1) == 51]
    wanted_records = sorted({int(_as_int(row.get("ml_data"), -1) or -1) for row in ucalc_rows if (_as_int(row.get("ml_data"), -1) or -1) > 0})

    decoded_by_record: Dict[int, Dict[str, Any]] = {}
    grid_by_record: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    if decoded_type51_rows is not None:
        for row in decoded_type51_rows:
            rec = _as_int(row.get("record"), None)
            if rec is not None:
                decoded_by_record[int(rec)] = dict(row)
        for row in decoded_type51_grid_rows or []:
            rec = _as_int(row.get("record"), None)
            if rec is not None:
                grid_by_record[int(rec)].append(dict(row))
        atdb_meta = {
            "atdb_fits": str(atdb_fits or ""),
            "atdb_status": "predecoded_rows_supplied",
            "n_wanted_records": len(wanted_records),
            "n_type51_records_decoded": len(decoded_by_record),
        }
    else:
        if atdb_fits is None:
            raise ValueError("atdb_fits is required unless decoded_type51_rows are supplied")
        decoded_by_record, grid_loaded, atdb_meta = _decode_type51_records_from_atdb(
            atdb_fits=atdb_fits,
            wanted_records=wanted_records,
            index_cache_path=index_cache_path,
            rebuild_index_cache=rebuild_index_cache,
        )
        grid_by_record.update(grid_loaded)

    native_by_record: Dict[int, Dict[str, Any]] = {}
    record_rows: List[Dict[str, Any]] = []
    for probe in ucalc_rows:
        rec = int(_as_int(probe.get("ml_data"), -1) or -1)
        decoded = decoded_by_record.get(rec)
        temperature_k = (_as_float(probe.get("t_xstar_1e4K"), 0.0) or 0.0) * 1.0e4
        hydrogen_density = _as_float(probe.get("xpx"), 0.0) or 0.0
        # The legacy v0.3.180 probe column is named xnx, but the insertion
        # passes calc_hmc_ion's xee.  Therefore ne = xpx*xee.
        electron_fraction = _as_float(probe.get("xnx"), 0.0) or 0.0
        electron_density = hydrogen_density * electron_fraction
        if decoded is None:
            native = {"status": "not_evaluated", "reason": "record_not_decoded"}
        else:
            native = evaluate_type51_ucalc_record(
                decoded,
                temperature_k,
                electron_density,
                grid_by_record.get(rec, []),
            )
        native_by_record[rec] = dict(native)
        xstar_ans1 = _as_float(probe.get("ans1"), 0.0) or 0.0
        xstar_ans2 = _as_float(probe.get("ans2"), 0.0) or 0.0
        native_ans1 = _as_float(native.get("ans1_excitation_s^-1"), 0.0) or 0.0
        native_ans2 = _as_float(native.get("ans2_deexcitation_s^-1"), 0.0) or 0.0
        rel1 = _relative_difference(native_ans1, xstar_ans1)
        rel2 = _relative_difference(native_ans2, xstar_ans2)
        evaluated = native.get("status") == "evaluated"
        ans1_pass = evaluated and rel1 <= relative_rate_tolerance
        ans2_pass = evaluated and rel2 <= relative_rate_tolerance
        endpoint_order_match = bool(decoded) and (
            _as_int(decoded.get("upper_level"), None) == _as_int(probe.get("idest1"), None)
            and _as_int(decoded.get("lower_level"), None) == _as_int(probe.get("idest2"), None)
        )
        record_rows.append({
            "record": rec,
            "capture_index": probe.get("capture_index", ""),
            "jkk_ion": probe.get("jkk_ion", ""),
            "element": decoded.get("element", "") if decoded else "",
            "ion_stage": decoded.get("ion_stage", "") if decoded else "",
            "ion_roman": decoded.get("ion_roman", "") if decoded else "",
            "lower_level": decoded.get("lower_level", "") if decoded else "",
            "upper_level": decoded.get("upper_level", "") if decoded else "",
            "lower_label": decoded.get("lower_label", "") if decoded else "",
            "upper_label": decoded.get("upper_label", "") if decoded else "",
            "xstar_idest1_upper": probe.get("idest1", ""),
            "xstar_idest2_lower": probe.get("idest2", ""),
            "endpoint_order_match": endpoint_order_match,
            "temperature_K": temperature_k,
            "probe_xpx_hydrogen_density_cm^-3": hydrogen_density,
            "probe_legacy_xnx_value_interpreted_as_xee": electron_fraction,
            "electron_density_xpx_times_xee_cm^-3": electron_density,
            "probe_xnx_semantics": "legacy_column_contains_xee_not_xnx; ne=xpx*xee",
            "native_status": native.get("status", ""),
            "native_reason": native.get("reason", ""),
            "native_spline_method": native.get("spline_method", ""),
            "native_n_bt_points": native.get("n_bt_points", ""),
            "native_bt_transition_type": native.get("bt_transition_type", ""),
            "native_bt_scaling_c": native.get("bt_scaling_c", ""),
            "native_eij_rdat_Ryd": native.get("eij_rdat_Ryd", ""),
            "native_eij_rdat_eV": native.get("eij_rdat_eV", ""),
            "native_wavelength_from_rdat_A": native.get("wavelength_from_rdat_A", ""),
            "native_bt_temperature_floor_K": native.get("bt_temperature_floor_K", ""),
            "native_bt_effective_temperature_K": native.get("bt_effective_temperature_K", ""),
            "native_bt_temperature_floor_applied": native.get("bt_temperature_floor_applied", ""),
            "native_upsilon": native.get("upsilon", ""),
            "native_q_excitation_cm3_s": native.get("q_excitation_cm3_s", ""),
            "native_q_deexcitation_cm3_s": native.get("q_deexcitation_cm3_s", ""),
            "xstar_ans1_s^-1": xstar_ans1,
            "native_ans1_s^-1": native_ans1,
            "ans1_native_over_xstar": native_ans1 / xstar_ans1 if xstar_ans1 != 0.0 else "",
            "ans1_relative_difference": rel1,
            "ans1_match": ans1_pass,
            "xstar_ans2_s^-1": xstar_ans2,
            "native_ans2_s^-1": native_ans2,
            "ans2_native_over_xstar": native_ans2 / xstar_ans2 if xstar_ans2 != 0.0 else "",
            "ans2_relative_difference": rel2,
            "ans2_match": ans2_pass,
            "record_native_type51_parity_status": "pass" if ans1_pass and ans2_pass and endpoint_order_match else "differs",
        })

    record_result = {int(row["record"]): row for row in record_rows}
    matrix_term_rows: List[Dict[str, Any]] = []
    for term in matrix_rows:
        rec = int(_as_int(term.get("ml_data"), -1) or -1)
        native = native_by_record.get(rec, {})
        ans1 = _as_float(native.get("ans1_excitation_s^-1"), 0.0) or 0.0
        ans2 = _as_float(native.get("ans2_deexcitation_s^-1"), 0.0) or 0.0
        kind = str(term.get("insertion_kind") or "")
        expected = _expected_matrix_coefficient(kind, ans1, ans2)
        observed = _as_float(term.get("ajisi_1"), 0.0) or 0.0
        rel = _relative_difference(expected or 0.0, observed) if expected is not None else math.inf
        match = expected is not None and native.get("status") == "evaluated" and rel <= relative_rate_tolerance
        matrix_term_rows.append({
            "record": rec,
            "capture_index": term.get("capture_index", ""),
            "insertion_kind": kind,
            "compact_row_ipmat2": term.get("compact_row_ipmat2", ""),
            "compact_col_ipmat2": term.get("compact_col_ipmat2", ""),
            "row_endpoint_selected": term.get("row_endpoint_selected", ""),
            "col_endpoint_selected": term.get("col_endpoint_selected", ""),
            "xstar_ajisi_1_s^-1": observed,
            "native_expected_ajisi_1_s^-1": expected if expected is not None else "",
            "native_over_xstar": (expected / observed) if expected is not None and observed != 0.0 else "",
            "relative_difference": rel if math.isfinite(rel) else "",
            "relative_rate_tolerance": relative_rate_tolerance,
            "matrix_term_match": match,
            "record_parity_status": record_result.get(rec, {}).get("record_native_type51_parity_status", ""),
        })

    internal_acc: MutableMapping[Tuple[int, int], Dict[str, Any]] = defaultdict(lambda: {
        "n_terms": 0,
        "xstar_coefficient_sum_s^-1": 0.0,
        "native_coefficient_sum_s^-1": 0.0,
    })
    for row in matrix_term_rows:
        if not (_as_bool(row.get("row_endpoint_selected")) and _as_bool(row.get("col_endpoint_selected"))):
            continue
        row_ip = int(_as_int(row.get("compact_row_ipmat2"), -1) or -1)
        col_ip = int(_as_int(row.get("compact_col_ipmat2"), -1) or -1)
        if row_ip <= 0 or col_ip <= 0:
            continue
        target = internal_acc[(row_ip, col_ip)]
        target["n_terms"] += 1
        target["xstar_coefficient_sum_s^-1"] += _as_float(row.get("xstar_ajisi_1_s^-1"), 0.0) or 0.0
        target["native_coefficient_sum_s^-1"] += _as_float(row.get("native_expected_ajisi_1_s^-1"), 0.0) or 0.0

    internal_rows: List[Dict[str, Any]] = []
    for (row_ip, col_ip), values in sorted(internal_acc.items()):
        xstar = float(values["xstar_coefficient_sum_s^-1"])
        native = float(values["native_coefficient_sum_s^-1"])
        rel = _relative_difference(native, xstar)
        internal_rows.append({
            "compact_row_ipmat2": row_ip,
            "compact_col_ipmat2": col_ip,
            "n_terms": values["n_terms"],
            "xstar_coefficient_sum_s^-1": xstar,
            "native_coefficient_sum_s^-1": native,
            "native_over_xstar": native / xstar if xstar != 0.0 else "",
            "relative_difference": rel,
            "internal_entry_match": rel <= relative_rate_tolerance,
        })

    selected_indices = sorted({
        int(_as_int(value, -1) or -1)
        for value in str(parent_summary.get("selected_xstar_ipmat2_indices") or "").split(";")
        if str(value).strip() and (int(_as_int(value, -1) or -1) > 0)
    })
    row_acc: MutableMapping[int, Dict[str, Any]] = defaultdict(lambda: {
        "n_internal_entries": 0,
        "xstar_abs_sum_s^-1": 0.0,
        "native_abs_sum_s^-1": 0.0,
        "max_relative_difference": 0.0,
    })
    for row in internal_rows:
        ip = int(row["compact_row_ipmat2"])
        target = row_acc[ip]
        target["n_internal_entries"] += 1
        target["xstar_abs_sum_s^-1"] += abs(float(row["xstar_coefficient_sum_s^-1"]))
        target["native_abs_sum_s^-1"] += abs(float(row["native_coefficient_sum_s^-1"]))
        target["max_relative_difference"] = max(target["max_relative_difference"], float(row["relative_difference"]))
    selected_row_rows: List[Dict[str, Any]] = []
    for ip in selected_indices:
        values = row_acc.get(ip, {})
        selected_row_rows.append({
            "xstar_ipmat2_index": ip,
            "n_internal_type51_entries": values.get("n_internal_entries", 0),
            "xstar_internal_type51_abs_sum_s^-1": values.get("xstar_abs_sum_s^-1", 0.0),
            "native_internal_type51_abs_sum_s^-1": values.get("native_abs_sum_s^-1", 0.0),
            "max_internal_entry_relative_difference": values.get("max_relative_difference", 0.0),
            "row_touched_by_native_type51": values.get("n_internal_entries", 0) > 0,
        })

    max_ans1 = max((float(row["ans1_relative_difference"]) for row in record_rows), default=math.inf)
    max_ans2 = max((float(row["ans2_relative_difference"]) for row in record_rows), default=math.inf)
    max_matrix = max((float(row["relative_difference"]) for row in matrix_term_rows if row.get("relative_difference") != ""), default=math.inf)
    max_internal = max((float(row["relative_difference"]) for row in internal_rows), default=math.inf)
    n_record_pass = sum(1 for row in record_rows if row["record_native_type51_parity_status"] == "pass")
    n_matrix_pass = sum(1 for row in matrix_term_rows if row["matrix_term_match"])
    n_internal_pass = sum(1 for row in internal_rows if row["internal_entry_match"])
    rows_touched = sum(1 for row in selected_row_rows if row["row_touched_by_native_type51"])

    record_ready = bool(record_rows) and n_record_pass == len(record_rows)
    matrix_ready = bool(matrix_term_rows) and n_matrix_pass == len(matrix_term_rows)
    internal_ready = bool(internal_rows) and n_internal_pass == len(internal_rows) and rows_touched == len(selected_indices)
    summary = {
        "audit_version": "v0.3.203",
        "status": "type51_native_parity_audit_completed",
        "ion": parent_summary.get("ion", ""),
        "selected_basis_solve_call_id": parent_summary.get("selected_basis_solve_call_id", ""),
        "selection": parent_summary.get("selection", ""),
        "occurrence_rank": parent_summary.get("occurrence_rank", ""),
        "selected_xstar_ipmat2_indices": ";".join(str(ip) for ip in selected_indices),
        "relative_rate_tolerance": relative_rate_tolerance,
        "probe_density_semantics": "legacy ucalc-probe xnx column contains xee; electron_density_cm^-3=xpx*xee",
        **atdb_meta,
        "n_selected_type51_ucalc_records": len(ucalc_rows),
        "n_type51_records_decoded": len(decoded_by_record),
        "n_type51_records_native_evaluated": sum(1 for row in record_rows if row["native_status"] == "evaluated"),
        "n_type51_records_endpoint_order_match": sum(1 for row in record_rows if row["endpoint_order_match"]),
        "n_type51_records_rate_parity_pass": n_record_pass,
        "n_type51_records_rate_parity_nonpass": len(record_rows) - n_record_pass,
        "max_ans1_relative_difference": max_ans1,
        "max_ans2_relative_difference": max_ans2,
        "n_type51_compact_matrix_terms": len(matrix_term_rows),
        "n_type51_compact_matrix_terms_match": n_matrix_pass,
        "n_type51_compact_matrix_terms_nonmatch": len(matrix_term_rows) - n_matrix_pass,
        "max_matrix_term_relative_difference": max_matrix,
        "n_type51_internal_compact_entries": len(internal_rows),
        "n_type51_internal_compact_entries_match": n_internal_pass,
        "n_type51_internal_compact_entries_nonmatch": len(internal_rows) - n_internal_pass,
        "max_internal_entry_relative_difference": max_internal,
        "n_selected_rows_touched_by_native_type51": rows_touched,
        "n_selected_rows_not_touched_by_native_type51": len(selected_indices) - rows_touched,
        "native_type51_record_rate_parity_ready": record_ready,
        "native_type51_compact_matrix_parity_ready": matrix_ready,
        "native_type51_internal_block_assembly_ready": internal_ready,
        "native_priority_subset_matrix_closure_ready": False,
        "dominant_next_target": (
            "integrate_native_type51_internal_block_then_native_type50_type71_external_rhs"
            if record_ready and matrix_ready and internal_ready
            else "resolve_native_type51_record_or_matrix_differences"
        ),
    }
    return {
        "summary": summary,
        "record_rows": record_rows,
        "matrix_term_rows": matrix_term_rows,
        "internal_entry_rows": internal_rows,
        "selected_row_rows": selected_row_rows,
    }


def write_type51_native_parity_audit(out_dir: str | Path, audit: Mapping[str, Any]) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "records_csv": out / "xstar_type51_native_parity_audit_records.csv",
        "matrix_terms_csv": out / "xstar_type51_native_parity_audit_matrix_terms.csv",
        "internal_entries_csv": out / "xstar_type51_native_parity_audit_internal_entries.csv",
        "selected_rows_csv": out / "xstar_type51_native_parity_audit_selected_rows.csv",
        "json": out / "xstar_type51_native_parity_audit.json",
        "markdown": out / "xstar_type51_native_parity_audit.md",
    }
    _write_csv(paths["records_csv"], audit.get("record_rows", []))
    _write_csv(paths["matrix_terms_csv"], audit.get("matrix_term_rows", []))
    _write_csv(paths["internal_entries_csv"], audit.get("internal_entry_rows", []))
    _write_csv(paths["selected_rows_csv"], audit.get("selected_row_rows", []))
    payload = dict(audit)
    paths["json"].write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    summary = dict(audit.get("summary", {}))
    lines = [
        "# XSTAR native type-51 selected-block parity audit",
        "",
        f"- Audit version: `{summary.get('audit_version', '')}`",
        f"- Ion: `{summary.get('ion', '')}`",
        f"- Selected compact rows: `{summary.get('selected_xstar_ipmat2_indices', '')}`",
        f"- Selected type-51 records: `{summary.get('n_selected_type51_ucalc_records', 0)}`",
        f"- Record-rate parity ready: `{summary.get('native_type51_record_rate_parity_ready', False)}`",
        f"- Compact matrix parity ready: `{summary.get('native_type51_compact_matrix_parity_ready', False)}`",
        f"- Internal block assembly ready: `{summary.get('native_type51_internal_block_assembly_ready', False)}`",
        "",
        "## Probe density interpretation",
        "",
        "The legacy full-parity probe column named `xnx` contains `xee`, the electron fraction relative to hydrogen, because the instrumentation call is made from `calc_hmc_ion.f90`.  This audit therefore evaluates the physical density as",
        "",
        "```text",
        "n_e = xpx * xee",
        "```",
        "",
        "where `xpx` is the hydrogen number density in cm^-3.",
        "",
        "## Acceptance",
        "",
        f"The source-code-aligned type-51 evaluator uses the ATDB transition energy, the XSTAR Burgess--Tully temperature floor, the physical Maxwellian temperature, and the probe-derived electron density.  The relative tolerance is `{summary.get('relative_rate_tolerance', '')}`.",
        "",
        "This is a diagnostic parity product.  It does not yet enable native type-51 terms in the production expanded compact-basis solver.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {key: str(value) for key, value in paths.items()}
