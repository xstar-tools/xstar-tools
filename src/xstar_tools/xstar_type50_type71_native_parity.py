"""Native selected-system parity audit for XSTAR data types 50 and 71.

The audit consumes the v0.3.198 priority matrix-closure manifest, decodes the
selected ATDB records, evaluates source-code-aligned ``ucalc`` branches, and
compares every compact insertion touching a selected endpoint.  Type-50
photoexcitation is accepted only with exact zero covering or an explicit
same-capture ``bremsa(nb1)`` context; no proxy radiation normalization is used.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .rates_type50 import evaluate_type50_ucalc_record
from .rates_type71 import evaluate_type71_ucalc_record


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
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "pass"}


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
        value = payload.get("summary", payload)
        if isinstance(value, dict):
            return dict(value)
    return {}


def _relative_difference(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1.0e-300)


def _expected_matrix_coefficient(kind: str, ans1: float, ans2: float) -> float | None:
    return {
        "forward_offdiag": ans1,
        "reverse_offdiag": ans2,
        "forward_diag_loss": -ans1,
        "reverse_diag_loss": -ans2,
    }.get(kind)


def _selected_indices(summary: Mapping[str, Any], matrix_rows: Sequence[Mapping[str, Any]]) -> list[int]:
    values = {
        int(ip)
        for token in str(summary.get("selected_xstar_ipmat2_indices") or "").split(";")
        if token.strip() and (ip := _as_int(token, None)) is not None and ip > 0
    }
    if not values:
        for row in matrix_rows:
            if _as_bool(row.get("row_endpoint_selected")):
                ip = _as_int(row.get("compact_row_ipmat2"), None)
                if ip is not None and ip > 0:
                    values.add(ip)
            if _as_bool(row.get("col_endpoint_selected")):
                ip = _as_int(row.get("compact_col_ipmat2"), None)
                if ip is not None and ip > 0:
                    values.add(ip)
    return sorted(values)


def _decode_records_from_atdb(
    *,
    atdb_fits: str | Path,
    type50_records: Iterable[int],
    type71_records: Iterable[int],
    index_cache_path: str | Path | None = None,
    rebuild_index_cache: bool = False,
) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[str, Any]]:
    wanted50 = {int(v) for v in type50_records}
    wanted71 = {int(v) for v in type71_records}
    decoded50: dict[int, dict[str, Any]] = {}
    decoded71: dict[int, dict[str, Any]] = {}
    from .hierarchy import ATDB, IndexedRecord
    from .lines import extract_lines

    with ATDB(atdb_fits, prompt_for_data=False) as db:
        rec50 = db.select_records(
            data_type=50, rate_type=4, use_cache=True,
            cache_path=index_cache_path, rebuild_cache=rebuild_index_cache,
            cache_format="npz",
        )
        selected50: dict[int, IndexedRecord] = {
            int(r.recno): r for r in rec50 if int(r.recno) in wanted50
        }
        groups: dict[tuple[int, int], list[int]] = defaultdict(list)
        for recno, rec in selected50.items():
            if rec.element_z is not None and rec.ion_stage is not None:
                groups[(int(rec.element_z), int(rec.ion_stage))].append(recno)
        for (z, stage), recnos in sorted(groups.items()):
            ion_records = db.select_records(
                z=z, ion_stage=stage, use_cache=True,
                cache_path=index_cache_path, rebuild_cache=False,
                cache_format="npz",
            )
            for row in extract_lines(db, ion_records, z, stage):
                recno = _as_int(row.get("record"), None)
                if recno in recnos:
                    decoded50[int(recno)] = dict(row)

        rec71 = db.select_records(
            data_type=71, rate_type=14, use_cache=True,
            cache_path=index_cache_path, rebuild_cache=False,
            cache_format="npz",
        )
        for rec in rec71:
            recno = int(rec.recno)
            if recno not in wanted71:
                continue
            header = db.header(recno)
            reals = [float(x) for x in db.real_slice(header)]
            ints = [int(x) for x in db.int_slice(header)]
            decoded71[recno] = {
                "record": recno,
                "element_z": rec.element_z,
                "element": rec.element_symbol,
                "ion_stage": rec.ion_stage,
                "ion": rec.ion_label,
                "lower_level": ints[2] if len(ints) >= 3 else None,
                "upper_level": ints[3] if len(ints) >= 4 else None,
                "nden": ints[0] if len(ints) >= 1 else None,
                "ntem": ints[1] if len(ints) >= 2 else None,
                "reals": reals,
                "ints": ints,
            }
        meta = {
            "atdb_fits": str(atdb_fits),
            "atdb_status": "loaded",
            "atdb_date": db.date or "",
            "atdb_creator": db.creator or "",
            "index_cache_status": getattr(db, "_last_index_cache_status", ""),
            "n_type50_records_decoded": len(decoded50),
            "n_type71_records_decoded": len(decoded71),
            "n_type50_records_missing_from_atdb": len(wanted50 - set(decoded50)),
            "n_type71_records_missing_from_atdb": len(wanted71 - set(decoded71)),
        }
    return decoded50, decoded71, meta


def _context_maps(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[tuple[int, int], dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    exact: dict[tuple[int, int], dict[str, Any]] = {}
    by_record: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for raw in rows:
        row = dict(raw)
        rec = _as_int(row.get("record") or row.get("ml_data"), None)
        cap = _as_int(row.get("capture_index"), None)
        if rec is None:
            continue
        by_record[int(rec)].append(row)
        if cap is not None:
            exact[(int(cap), int(rec))] = row
    return exact, by_record


def _lookup_context(
    *, capture: int | None, record: int, exact: Mapping[tuple[int, int], Mapping[str, Any]], by_record: Mapping[int, Sequence[Mapping[str, Any]]]
) -> tuple[dict[str, Any], str]:
    if capture is not None and (capture, record) in exact:
        return dict(exact[(capture, record)]), "exact_capture_record"
    candidates = list(by_record.get(record, []))
    if len(candidates) == 1:
        return dict(candidates[0]), "unique_record"
    return {}, "not_supplied" if not candidates else "ambiguous_record"


def build_type50_type71_native_parity_audit(
    *,
    priority_matrix_closure_audit: str | Path,
    atdb_fits: str | Path | None = None,
    type50_radiation_context_csv: str | Path | None = None,
    relative_rate_tolerance: float = 5.0e-5,
    index_cache_path: str | Path | None = None,
    rebuild_index_cache: bool = False,
    decoded_type50_rows: Sequence[Mapping[str, Any]] | None = None,
    decoded_type71_rows: Sequence[Mapping[str, Any]] | None = None,
    type50_context_rows: Sequence[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Build record and compact-matrix parity for selected type 50/71 terms."""
    if relative_rate_tolerance <= 0.0:
        raise ValueError("relative_rate_tolerance must be positive")
    ucalc_path = _resolve_product(priority_matrix_closure_audit, "xstar_priority_matrix_closure_audit_ucalc_records.csv")
    matrix_path = _resolve_product(priority_matrix_closure_audit, "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv")
    parent = _load_summary(priority_matrix_closure_audit)
    ucalc_all = _read_csv(ucalc_path)
    matrix_all = _read_csv(matrix_path)
    ucalc_rows = [r for r in ucalc_all if (_as_int(r.get("ltyp"), -1), _as_int(r.get("lrtyp"), -1)) in {(50, 4), (71, 14)}]
    matrix_rows = [r for r in matrix_all if (_as_int(r.get("ltyp"), -1), _as_int(r.get("lrtyp"), -1)) in {(50, 4), (71, 14)}]
    wanted50 = sorted({_as_int(r.get("ml_data"), -1) for r in ucalc_rows if _as_int(r.get("ltyp"), -1) == 50 and (_as_int(r.get("ml_data"), -1) or -1) > 0})
    wanted71 = sorted({_as_int(r.get("ml_data"), -1) for r in ucalc_rows if _as_int(r.get("ltyp"), -1) == 71 and (_as_int(r.get("ml_data"), -1) or -1) > 0})

    if decoded_type50_rows is not None or decoded_type71_rows is not None:
        d50 = {int(r["record"]): dict(r) for r in (decoded_type50_rows or []) if _as_int(r.get("record"), None) is not None}
        d71 = {int(r["record"]): dict(r) for r in (decoded_type71_rows or []) if _as_int(r.get("record"), None) is not None}
        atdb_meta = {
            "atdb_fits": str(atdb_fits or ""), "atdb_status": "predecoded_rows_supplied",
            "n_type50_records_decoded": len(d50), "n_type71_records_decoded": len(d71),
        }
    else:
        if atdb_fits is None:
            raise ValueError("atdb_fits is required unless predecoded rows are supplied")
        d50, d71, atdb_meta = _decode_records_from_atdb(
            atdb_fits=atdb_fits, type50_records=wanted50, type71_records=wanted71,
            index_cache_path=index_cache_path, rebuild_index_cache=rebuild_index_cache,
        )

    if type50_context_rows is not None:
        context_rows = [dict(r) for r in type50_context_rows]
        context_source = "preloaded_rows"
    elif type50_radiation_context_csv:
        context_rows = _read_csv(Path(type50_radiation_context_csv))
        context_source = str(type50_radiation_context_csv)
    else:
        context_rows = []
        context_source = "not_supplied"
    context_exact, context_by_record = _context_maps(context_rows)

    native_by_key: dict[tuple[int | None, int], dict[str, Any]] = {}
    record_rows: list[dict[str, Any]] = []
    for probe in ucalc_rows:
        family = "type50_rate4" if _as_int(probe.get("ltyp"), -1) == 50 else "type71_rate14"
        rec = int(_as_int(probe.get("ml_data"), -1) or -1)
        cap = _as_int(probe.get("capture_index"), None)
        p1 = _as_float(probe.get("ptmp1"), 0.0) or 0.0
        p2 = _as_float(probe.get("ptmp2"), 0.0) or 0.0
        temperature = (_as_float(probe.get("t_xstar_1e4K"), 0.0) or 0.0) * 1.0e4
        xpx = _as_float(probe.get("xpx"), 0.0) or 0.0
        xee = _as_float(probe.get("xnx"), 0.0) or 0.0
        ne = xpx * xee
        context, context_match = _lookup_context(capture=cap, record=rec, exact=context_exact, by_record=context_by_record)
        if family == "type50_rate4":
            decoded = d50.get(rec)
            if decoded is None:
                native = {"status": "not_evaluated", "reason": "record_not_decoded"}
            else:
                bremsa = _as_float(context.get("bremsa_nb1") or context.get("type50_bremsa_nb1"), None)
                flinabs = _as_float(context.get("flinabs_ptmp1"), 1.0)
                native = evaluate_type50_ucalc_record(
                    decoded, ptmp1=p1, ptmp2=p2,
                    cfrac=_as_float(probe.get("cfrac"), 1.0) or 0.0,
                    bremsa_nb1=bremsa, flinabs_ptmp1=flinabs,
                    hydrogen_density_cm3=xpx,
                )
            ans1_native = _as_float(native.get("ans1_photoexcitation_s^-1"), 0.0) or 0.0
            ans2_native = _as_float(native.get("ans2_escaped_decay_s^-1"), 0.0) or 0.0
            lower = _as_int((decoded or {}).get("lower_level"), None)
            upper = _as_int((decoded or {}).get("upper_level"), None)
        else:
            decoded = d71.get(rec)
            if decoded is None:
                native = {"status": "not_evaluated", "reason": "record_not_decoded"}
            else:
                native = evaluate_type71_ucalc_record(
                    decoded, temperature_k=temperature, electron_density_cm3=xpx,
                    ptmp1=p1, ptmp2=p2,
                )
            ans1_native = _as_float(native.get("ans1_upward_s^-1"), 0.0) or 0.0
            ans2_native = _as_float(native.get("ans2_downward_s^-1"), 0.0) or 0.0
            lower = _as_int((decoded or {}).get("lower_level"), None)
            upper = _as_int((decoded or {}).get("upper_level"), None)
        native_by_key[(cap, rec)] = dict(native)
        x1 = _as_float(probe.get("ans1"), 0.0) or 0.0
        x2 = _as_float(probe.get("ans2"), 0.0) or 0.0
        rel1, rel2 = _relative_difference(ans1_native, x1), _relative_difference(ans2_native, x2)
        xstar_idest1 = _as_int(probe.get("idest1"), None)
        xstar_idest2 = _as_int(probe.get("idest2"), None)
        if family == "type50_rate4":
            # ucalc.f90 type 50 energy-orders the endpoints before returning:
            # idest1 is the upper level and idest2 is the lower level.
            endpoint = lower == xstar_idest2 and upper == xstar_idest1
            idest1_role = "upper_level"
            idest2_role = "lower_level"
            endpoint_convention = "type50_post_energy_order: idest1=upper, idest2=lower"
        else:
            # ucalc.f90 type 71 returns the packed ATDB order unchanged:
            # idest1 is the lower spectroscopic destination and idest2 is the
            # upper superlevel source. calc_hmc_ion later derives llo/lup from
            # the level energies for the universal matrix insertion path.
            endpoint = lower == xstar_idest1 and upper == xstar_idest2
            idest1_role = "lower_spectroscopic_destination"
            idest2_role = "upper_superlevel_source"
            endpoint_convention = "type71_packed_order: idest1=lower_spectroscopic, idest2=upper_superlevel"
        evaluated = native.get("status") == "evaluated"
        if family == "type50_rate4":
            evaluated = evaluated and bool(native.get("source_equivalent_rate_context"))
        passed = evaluated and endpoint and rel1 <= relative_rate_tolerance and rel2 <= relative_rate_tolerance
        record_rows.append({
            "family_key": family, "record": rec, "capture_index": probe.get("capture_index", ""),
            "jkk_ion": probe.get("jkk_ion", ""), "lower_level": lower or "", "upper_level": upper or "",
            "xstar_idest1": probe.get("idest1", ""), "xstar_idest2": probe.get("idest2", ""),
            "xstar_idest1_role": idest1_role, "xstar_idest2_role": idest2_role,
            "endpoint_order_convention": endpoint_convention,
            # Compatibility columns retained only where their names are true.
            "xstar_idest1_upper": probe.get("idest1", "") if family == "type50_rate4" else "",
            "xstar_idest2_lower": probe.get("idest2", "") if family == "type50_rate4" else "",
            "endpoint_order_match": endpoint, "temperature_K": temperature,
            "probe_xpx_hydrogen_density_cm^-3": xpx,
            "probe_legacy_xnx_value_interpreted_as_xee": xee,
            "physical_electron_density_xpx_times_xee_cm^-3": ne,
            "type71_calt71_density_argument_xpx_cm^-3": xpx,
            "type71_density_semantics": "ucalc.f90 passes den=xpx, not xpx*xee",
            "ptmp1": p1, "ptmp2": p2, "ptmp_sum": p1 + p2,
            "cfrac": probe.get("cfrac", ""), "type50_context_match": context_match if family == "type50_rate4" else "not_applicable",
            "native_status": native.get("status", ""), "native_reason": native.get("reason", ""),
            "native_branch": native.get("branch", native.get("photoexcitation_status", "")),
            "native_aij_s^-1": native.get("aij_s^-1", ""),
            "native_wavelength_A": native.get("wavelength_A", ""),
            "native_bremsa_nb1": native.get("bremsa_nb1", ""),
            "native_radiation_context_required": native.get("radiation_context_required", ""),
            "native_source_equivalent_rate_context": native.get("source_equivalent_rate_context", ""),
            "native_density_floor_s^-1": native.get("density_floor_s^-1", ""),
            "native_density_floor_applied": native.get("density_floor_applied", ""),
            "native_special_ca_cap_applied": native.get("special_ca_i_ca_ii_cap_applied", ""),
            "xstar_ans1_s^-1": x1, "native_ans1_s^-1": ans1_native,
            "ans1_relative_difference": rel1, "ans1_match": evaluated and rel1 <= relative_rate_tolerance,
            "xstar_ans2_s^-1": x2, "native_ans2_s^-1": ans2_native,
            "ans2_relative_difference": rel2, "ans2_match": evaluated and rel2 <= relative_rate_tolerance,
            "record_parity_status": "pass" if passed else "differs",
        })

    record_result = {( _as_int(r.get("capture_index"), None), int(r["record"])): r for r in record_rows}
    matrix_term_rows: list[dict[str, Any]] = []
    for term in matrix_rows:
        rec = int(_as_int(term.get("ml_data"), -1) or -1)
        cap = _as_int(term.get("capture_index"), None)
        family = "type50_rate4" if _as_int(term.get("ltyp"), -1) == 50 else "type71_rate14"
        native = native_by_key.get((cap, rec), {})
        if family == "type50_rate4":
            ans1 = _as_float(native.get("ans1_photoexcitation_s^-1"), 0.0) or 0.0
            ans2 = _as_float(native.get("ans2_escaped_decay_s^-1"), 0.0) or 0.0
        else:
            ans1 = _as_float(native.get("ans1_upward_s^-1"), 0.0) or 0.0
            ans2 = _as_float(native.get("ans2_downward_s^-1"), 0.0) or 0.0
        kind = str(term.get("insertion_kind") or "")
        expected = _expected_matrix_coefficient(kind, ans1, ans2)
        observed = _as_float(term.get("ajisi_1"), 0.0) or 0.0
        rel = _relative_difference(expected or 0.0, observed) if expected is not None else math.inf
        record_status = record_result.get((cap, rec), {}).get("record_parity_status", "")
        match = expected is not None and native.get("status") == "evaluated" and record_status == "pass" and rel <= relative_rate_tolerance
        row_selected = _as_bool(term.get("row_endpoint_selected"))
        col_selected = _as_bool(term.get("col_endpoint_selected"))
        matrix_term_rows.append({
            "family_key": family, "record": rec, "capture_index": term.get("capture_index", ""),
            "insertion_kind": kind, "compact_row_ipmat2": term.get("compact_row_ipmat2", ""),
            "compact_col_ipmat2": term.get("compact_col_ipmat2", ""),
            "row_endpoint_selected": row_selected, "col_endpoint_selected": col_selected,
            "selected_system_partition": "selected_internal" if row_selected and col_selected else ("fixed_external" if row_selected else "external_row_out_of_scope"),
            "xstar_ajisi_1_s^-1": observed,
            "native_expected_ajisi_1_s^-1": expected if expected is not None else "",
            "relative_difference": rel if math.isfinite(rel) else "",
            "relative_rate_tolerance": relative_rate_tolerance,
            "matrix_term_match": match, "record_parity_status": record_status,
        })

    selected = _selected_indices(parent, matrix_rows)
    selected_set = set(selected)
    family_summary_rows: list[dict[str, Any]] = []
    selected_row_rows: list[dict[str, Any]] = []
    readiness: dict[str, bool] = {}
    for family in ("type50_rate4", "type71_rate14"):
        records = [r for r in record_rows if r["family_key"] == family]
        terms = [r for r in matrix_term_rows if r["family_key"] == family]
        selected_terms = [r for r in terms if _as_bool(r.get("row_endpoint_selected"))]
        external_terms = [r for r in selected_terms if not _as_bool(r.get("col_endpoint_selected"))]
        internal_terms = [r for r in selected_terms if _as_bool(r.get("col_endpoint_selected"))]
        touched = {int(_as_int(r.get("compact_row_ipmat2"), -1) or -1) for r in selected_terms if (_as_int(r.get("compact_row_ipmat2"), -1) or -1) > 0}
        expected_touched = touched.copy()
        record_ready = bool(records) and all(r["record_parity_status"] == "pass" for r in records)
        matrix_ready = bool(terms) and all(_as_bool(r["matrix_term_match"]) for r in terms)
        selected_ready = bool(selected_terms) and all(_as_bool(r["matrix_term_match"]) for r in selected_terms)
        external_ready = bool(external_terms) and all(_as_bool(r["matrix_term_match"]) for r in external_terms)
        readiness[family] = record_ready and matrix_ready and selected_ready
        family_summary_rows.append({
            "family_key": family, "n_records": len(records),
            "n_records_parity_pass": sum(r["record_parity_status"] == "pass" for r in records),
            "n_matrix_terms": len(terms), "n_matrix_terms_match": sum(_as_bool(r["matrix_term_match"]) for r in terms),
            "n_selected_row_terms": len(selected_terms), "n_selected_internal_terms": len(internal_terms),
            "n_fixed_external_terms": len(external_terms), "n_external_row_out_of_scope_terms": len(terms) - len(selected_terms),
            "n_selected_rows_touched": len(touched),
            "max_record_ans1_relative_difference": max((float(r["ans1_relative_difference"]) for r in records), default=math.inf),
            "max_record_ans2_relative_difference": max((float(r["ans2_relative_difference"]) for r in records), default=math.inf),
            "max_matrix_term_relative_difference": max((float(r["relative_difference"]) for r in terms if r.get("relative_difference") != ""), default=math.inf),
            "record_rate_parity_ready": record_ready, "compact_matrix_parity_ready": matrix_ready,
            "selected_system_parity_ready": selected_ready, "external_rhs_parity_ready": external_ready,
        })
        for ip in selected:
            rows = [r for r in selected_terms if _as_int(r.get("compact_row_ipmat2"), None) == ip]
            selected_row_rows.append({
                "family_key": family, "xstar_ipmat2_index": ip,
                "n_selected_row_terms": len(rows),
                "n_selected_internal_terms": sum(r["selected_system_partition"] == "selected_internal" for r in rows),
                "n_fixed_external_terms": sum(r["selected_system_partition"] == "fixed_external" for r in rows),
                "row_touched_by_native_family": bool(rows),
                "all_row_terms_match": bool(rows) and all(_as_bool(r["matrix_term_match"]) for r in rows),
            })

    type50_ready = readiness.get("type50_rate4", False)
    type71_ready = readiness.get("type71_rate14", False)
    summary = {
        "audit_version": "v0.3.207",
        "status": "type50_type71_native_parity_audit_completed",
        "ion": parent.get("ion", ""),
        "selected_basis_solve_call_id": parent.get("selected_basis_solve_call_id", ""),
        "selection": parent.get("selection", ""), "occurrence_rank": parent.get("occurrence_rank", ""),
        "selected_xstar_ipmat2_indices": ";".join(str(v) for v in selected),
        "relative_rate_tolerance": relative_rate_tolerance,
        "probe_density_semantics": "legacy probe xnx contains xee; physical ne=xpx*xee, but ucalc type71 passes den=xpx directly to calt71",
        "type71_calt71_density_semantics": "source-equivalent density argument is xpx",
        "type50_radiation_context_source": context_source,
        "type50_radiation_policy": "no proxy: explicit bremsa(nb1) required unless cfrac>=1 or the XSTAR wavelength sentinel makes pumping exactly zero",
        "type50_decay_floor_policy": "source max(A*(ptmp1+ptmp2),1e-20*xpx) reproduced from captured xpx",
        **atdb_meta,
        "n_selected_type50_ucalc_records": sum(r["family_key"] == "type50_rate4" for r in record_rows),
        "n_selected_type71_ucalc_records": sum(r["family_key"] == "type71_rate14" for r in record_rows),
        "n_type50_records_rate_parity_pass": sum(r["family_key"] == "type50_rate4" and r["record_parity_status"] == "pass" for r in record_rows),
        "n_type71_records_rate_parity_pass": sum(r["family_key"] == "type71_rate14" and r["record_parity_status"] == "pass" for r in record_rows),
        "n_type50_compact_matrix_terms": sum(r["family_key"] == "type50_rate4" for r in matrix_term_rows),
        "n_type71_compact_matrix_terms": sum(r["family_key"] == "type71_rate14" for r in matrix_term_rows),
        "n_type50_compact_matrix_terms_match": sum(r["family_key"] == "type50_rate4" and _as_bool(r["matrix_term_match"]) for r in matrix_term_rows),
        "n_type71_compact_matrix_terms_match": sum(r["family_key"] == "type71_rate14" and _as_bool(r["matrix_term_match"]) for r in matrix_term_rows),
        "native_type50_selected_system_parity_ready": type50_ready,
        "native_type71_selected_system_parity_ready": type71_ready,
        "native_type50_type71_selected_system_parity_ready": type50_ready and type71_ready,
        "native_priority_subset_matrix_closure_ready": False,
        "dominant_next_target": "integrate_native_type50_type71_into_native_type51_selected_system" if type50_ready and type71_ready else "resolve_type50_or_type71_record_matrix_parity",
    }
    return {
        "summary": summary, "record_rows": record_rows,
        "matrix_term_rows": matrix_term_rows,
        "family_summary_rows": family_summary_rows,
        "selected_row_rows": selected_row_rows,
    }


def write_type50_type71_native_parity_audit(out_dir: str | Path, audit: Mapping[str, Any]) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "records_csv": out / "xstar_type50_type71_native_parity_audit_records.csv",
        "matrix_terms_csv": out / "xstar_type50_type71_native_parity_audit_matrix_terms.csv",
        "family_summary_csv": out / "xstar_type50_type71_native_parity_audit_family_summary.csv",
        "selected_rows_csv": out / "xstar_type50_type71_native_parity_audit_selected_rows.csv",
        "json": out / "xstar_type50_type71_native_parity_audit.json",
        "markdown": out / "xstar_type50_type71_native_parity_audit.md",
    }
    _write_csv(paths["records_csv"], audit.get("record_rows", []))
    _write_csv(paths["matrix_terms_csv"], audit.get("matrix_term_rows", []))
    _write_csv(paths["family_summary_csv"], audit.get("family_summary_rows", []))
    _write_csv(paths["selected_rows_csv"], audit.get("selected_row_rows", []))
    paths["json"].write_text(json.dumps(dict(audit), indent=2, sort_keys=True), encoding="utf-8")
    s = dict(audit.get("summary", {}))
    lines = [
        "# XSTAR native type-50/type-71 selected-system parity audit", "",
        f"- Audit version: `{s.get('audit_version','')}`",
        f"- Ion: `{s.get('ion','')}`",
        f"- Selected rows: `{s.get('selected_xstar_ipmat2_indices','')}`",
        f"- Native type-50 parity ready: `{s.get('native_type50_selected_system_parity_ready',False)}`",
        f"- Native type-71 parity ready: `{s.get('native_type71_selected_system_parity_ready',False)}`", "",
        "Type-50 pumping is never reconstructed from a proxy continuum. An explicit same-capture `bremsa(nb1)` value is required unless full covering or the source high-wavelength sentinel makes the rate exactly zero.", "",
        "The legacy probe column `xnx` contains `xee`, but the XSTAR type-71 branch passes `den=xpx` directly to `calt71`; the audit follows that source behavior.", "",
        "This diagnostic does not change the production expanded compact-basis solver.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}


__all__ = ["build_type50_type71_native_parity_audit", "write_type50_type71_native_parity_audit"]
