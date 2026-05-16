"""Exact live-radiation native parity gate for XSTAR data type 53.

The gate consumes the selected v0.3.198 compact manifest, an explicitly chosen
instrumented XSTAR ``epim/bremsam/bremsint`` capture, and ``atdb.fits``.  It
replays the complete ``ucalc.f90`` type-53 rate branch through the source-
aligned :mod:`xstar_atomic.rates_type53` kernel and compares ``ans1..ans6`` and
all compact matrix insertions.  No analytic continuum or empirical scale is
accepted.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .rates_type53 import Type53LiveRadiationState, evaluate_type53_ucalc_record
from .xstar_live_rate_grid_probe import read_live_rate_grid_probe_csv


def _as_int(v: Any, default: int | None = None) -> int | None:
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return default
        x = float(v)
        return int(round(x)) if math.isfinite(x) else default
    except Exception:
        return default


def _as_float(v: Any, default: float | None = None) -> float | None:
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return default
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _as_bool(v: Any) -> bool:
    return isinstance(v, bool) and v or str(v).strip().lower() in {"1", "true", "yes", "y", "pass"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if str(key) not in fields:
                fields.append(str(key))
    if not fields:
        fields = ["status"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fields})


def _resolve_product(root: str | Path, name: str) -> Path:
    p = Path(root)
    if p.is_file() and p.name == name:
        return p
    if p.is_dir():
        q = p / name
        if q.exists():
            return q
        hits = sorted(p.rglob(name))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"could not find {name} under {p}")


def _load_summary(root: str | Path) -> dict[str, Any]:
    try:
        p = _resolve_product(root, "xstar_priority_matrix_closure_audit.json")
    except FileNotFoundError:
        return {}
    obj = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(obj, dict):
        value = obj.get("summary", obj)
        return dict(value) if isinstance(value, dict) else {}
    return {}


def _rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1.0e-300)


def _expected(kind: str, ans1: float, ans2: float) -> float | None:
    return {
        "forward_offdiag": ans1,
        "reverse_offdiag": ans2,
        "forward_diag_loss": -ans1,
        "reverse_diag_loss": -ans2,
    }.get(kind)


def _select_state(states: Sequence[Any], selector: str | int) -> tuple[Any | None, str]:
    if not states:
        return None, "no_live_states"
    token = str(selector).strip().lower()
    if token == "last":
        return states[-1], "selected_last_capture"
    if token == "first":
        return states[0], "selected_first_capture"
    try:
        wanted = int(token)
    except Exception:
        return None, "invalid_capture_selector"
    for state in states:
        if _as_int(state.metadata.get("capture_index"), None) == wanted:
            return state, "selected_capture_index"
    # Also permit zero-based Python sequence selection when explicitly 0.
    if wanted == 0:
        return states[0], "selected_zero_based_first_state"
    return None, "capture_index_not_found"


def _selected_indices(summary: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list[int]:
    out = {
        int(v) for t in str(summary.get("selected_xstar_ipmat2_indices") or "").split(";")
        if t.strip() and (v := _as_int(t, None)) is not None and v > 0
    }
    if not out:
        for r in rows:
            for side in ("row", "col"):
                if _as_bool(r.get(f"{side}_endpoint_selected")):
                    v = _as_int(r.get(f"compact_{side}_ipmat2"), None)
                    if v and v > 0:
                        out.add(v)
    return sorted(out)


def _decode_type53_records(
    *, atdb_fits: str | Path, wanted_records: Sequence[int],
    index_cache_path: str | Path | None = None, rebuild_index_cache: bool = False,
) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    """Decode packed type-53 records plus current/parent level context."""
    from .hierarchy import ATDB
    from .lines import extract_levels

    wanted = {int(v) for v in wanted_records}
    decoded: dict[int, dict[str, Any]] = {}
    with ATDB(atdb_fits, prompt_for_data=False) as db:
        records = db.select_records(
            data_type=53, rate_type=7, use_cache=True, cache_path=index_cache_path,
            rebuild_cache=rebuild_index_cache, cache_format="npz",
        )
        selected = [r for r in records if int(r.recno) in wanted]
        groups: dict[tuple[int, int], list[Any]] = defaultdict(list)
        for r in selected:
            if r.element_z is not None and r.ion_stage is not None:
                groups[(int(r.element_z), int(r.ion_stage))].append(r)

        level_cache: dict[tuple[int, int], dict[int, dict[str, Any]]] = {}
        def levels(z: int, stage: int) -> dict[int, dict[str, Any]]:
            key = (z, stage)
            if key not in level_cache:
                rs = db.select_records(
                    z=z, ion_stage=stage, use_cache=True, cache_path=index_cache_path,
                    rebuild_cache=False, cache_format="npz",
                )
                level_cache[key] = {
                    int(row["level_index"]): dict(row)
                    for row in extract_levels(db, rs, z, stage)
                    if _as_int(row.get("level_index"), None) is not None
                }
            return level_cache[key]

        for (z, stage), recs in groups.items():
            cur = levels(z, stage)
            parent = levels(z, stage + 1)
            if not cur:
                continue
            nlev = max(cur)
            continuum = cur.get(nlev, {})
            continuum_energy = _as_float(continuum.get("energy_eV"), 0.0) or 0.0
            continuum_g = _as_float(continuum.get("statistical_weight_g"), 0.0) or 0.0
            for r in recs:
                h = db.header(int(r.recno))
                reals = [float(v) for v in db.real_slice(h)]
                ints = [int(v) for v in db.int_slice(h)]
                bound = ints[-2] if len(ints) >= 2 else None
                offset = ints[-3] if len(ints) >= 3 else 1
                idest2 = nlev + int(offset) - 1
                bound_row = cur.get(int(bound or -1), {})
                base_threshold = _as_float(bound_row.get("binding_from_continuum_eV"), 0.0) or 0.0
                parent_local = idest2 - nlev + 1
                parent_row = parent.get(parent_local, {}) if idest2 > nlev else {}
                parent_excitation = (_as_float(parent_row.get("energy_eV"), 0.0) or 0.0) if idest2 > nlev else 0.0
                destination_g = (_as_float(parent_row.get("statistical_weight_g"), continuum_g) or continuum_g) if idest2 > nlev else continuum_g
                ntmp = max(1, len(reals) // 2)
                e_ryd = [reals[2 * i] for i in range(ntmp) if 2 * i + 1 < len(reals)]
                sigma = [max(0.0, reals[2 * i + 1]) * 1.0e-18 for i in range(ntmp) if 2 * i + 1 < len(reals)]
                decoded[int(r.recno)] = {
                    "record": int(r.recno), "element_z": z, "element": r.element_symbol,
                    "ion_stage": stage, "ion": r.ion_label, "nlev": nlev,
                    "bound_level": bound, "destination_level": idest2,
                    "parent_local_level": parent_local if idest2 > nlev else 1,
                    "threshold_eV": base_threshold + parent_excitation,
                    "base_threshold_eV": base_threshold,
                    "parent_excitation_eV": parent_excitation,
                    "bound_energy_eV": _as_float(bound_row.get("energy_eV"), 0.0) or 0.0,
                    "continuum_energy_eV": continuum_energy,
                    "destination_energy_eV": continuum_energy + parent_excitation,
                    "bound_statistical_weight": _as_float(bound_row.get("statistical_weight_g"), 0.0) or 0.0,
                    "continuum_statistical_weight": continuum_g,
                    "destination_statistical_weight": destination_g,
                    "energy_above_threshold_ryd": e_ryd,
                    "cross_section_cm2": sigma,
                    "raw_ints": ints, "raw_reals": reals,
                }
        meta = {
            "atdb_fits": str(atdb_fits), "atdb_status": "loaded",
            "atdb_date": db.date or "", "atdb_creator": db.creator or "",
            "index_cache_status": getattr(db, "_last_index_cache_status", ""),
            "n_type53_records_decoded": len(decoded),
            "n_type53_records_missing_from_atdb": len(wanted - set(decoded)),
        }
    return decoded, meta


def _context_check(
    *, state: Type53LiveRadiationState, probe_rows: Sequence[Mapping[str, Any]],
    density_field_semantics: str, relative_tolerance: float,
) -> tuple[dict[str, Any], bool]:
    """Check live-state metadata against the selected ucalc occurrence."""
    first = probe_rows[0] if probe_rows else {}
    expected_t = (_as_float(first.get("t_xstar_1e4K"), 0.0) or 0.0) * 1.0e4
    expected_xpx = _as_float(first.get("xpx"), 0.0) or 0.0
    expected_xee = _as_float(first.get("xnx"), 0.0) or 0.0
    expected_cfrac = _as_float(first.get("cfrac"), 0.0) or 0.0
    md = dict(state.metadata)
    observed_t = _as_float(md.get("temperature_K"), None)
    observed_xpx = _as_float(md.get("xpx"), None)
    observed_cfrac = _as_float(md.get("cfrac"), None)
    raw_density = _as_float(md.get("electron_density_cm^-3"), None)
    semantics = str(density_field_semantics).strip().lower()
    if semantics == "xee":
        observed_xee = raw_density
        observed_ne = (observed_xpx * observed_xee) if observed_xpx is not None and observed_xee is not None else None
    elif semantics == "electron_density":
        observed_ne = raw_density
        observed_xee = observed_ne / observed_xpx if observed_ne is not None and observed_xpx not in (None, 0.0) else None
    else:
        observed_xee = None
        observed_ne = None

    def match(obs: float | None, exp: float) -> bool:
        return obs is not None and _rel(float(obs), float(exp)) <= relative_tolerance
    checks = {
        "temperature_metadata_present": observed_t is not None,
        "temperature_match": match(observed_t, expected_t),
        "xpx_metadata_present": observed_xpx is not None,
        "xpx_match": match(observed_xpx, expected_xpx),
        "cfrac_metadata_present": observed_cfrac is not None,
        "cfrac_match": match(observed_cfrac, expected_cfrac),
        "density_metadata_present": raw_density is not None,
        "xee_match": True if semantics == "ignore" else match(observed_xee, expected_xee),
    }
    ready = all(checks.values())
    row = {
        "live_capture_index": state.metadata.get("capture_index", ""),
        "live_zone_index": state.metadata.get("zone_index", ""),
        "live_pass_index": state.metadata.get("pass_index", ""),
        "live_ldir": state.metadata.get("ldir", ""),
        "density_field_semantics": semantics,
        "expected_temperature_K": expected_t, "observed_temperature_K": observed_t,
        "expected_xpx_cm^-3": expected_xpx, "observed_xpx_cm^-3": observed_xpx,
        "expected_xee": expected_xee, "observed_xee": observed_xee,
        "expected_electron_density_cm^-3": expected_xpx * expected_xee,
        "observed_electron_density_cm^-3": observed_ne,
        "expected_cfrac": expected_cfrac, "observed_cfrac": observed_cfrac,
        **checks, "live_state_context_ready": ready,
    }
    return row, ready


def build_type53_live_native_parity_audit(
    *, priority_matrix_closure_audit: str | Path,
    live_rate_grid_probe_csv: str | Path | None = None,
    live_rate_grid_state: str | int = "last",
    live_density_field_semantics: str = "electron_density",
    atdb_fits: str | Path | None = None,
    relative_rate_tolerance: float = 5.0e-5,
    live_context_relative_tolerance: float = 5.0e-5,
    lfast: int = 2,
    index_cache_path: str | Path | None = None,
    rebuild_index_cache: bool = False,
    decoded_type53_rows: Sequence[Mapping[str, Any]] | None = None,
    live_state: Type53LiveRadiationState | None = None,
) -> dict[str, Any]:
    if relative_rate_tolerance <= 0 or live_context_relative_tolerance <= 0:
        raise ValueError("tolerances must be positive")
    ucalc_path = _resolve_product(priority_matrix_closure_audit, "xstar_priority_matrix_closure_audit_ucalc_records.csv")
    matrix_path = _resolve_product(priority_matrix_closure_audit, "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv")
    parent = _load_summary(priority_matrix_closure_audit)
    ucalc = [r for r in _read_csv(ucalc_path) if (_as_int(r.get("ltyp"), -1), _as_int(r.get("lrtyp"), -1)) == (53, 7)]
    matrix = [r for r in _read_csv(matrix_path) if (_as_int(r.get("ltyp"), -1), _as_int(r.get("lrtyp"), -1)) == (53, 7)]
    wanted = sorted({int(_as_int(r.get("ml_data"), -1) or -1) for r in ucalc if (_as_int(r.get("ml_data"), -1) or -1) > 0})

    if decoded_type53_rows is not None:
        decoded = {int(r["record"]): dict(r) for r in decoded_type53_rows if _as_int(r.get("record"), None) is not None}
        atdb_meta = {"atdb_fits": str(atdb_fits or ""), "atdb_status": "predecoded_rows_supplied", "n_type53_records_decoded": len(decoded)}
    else:
        if atdb_fits is None:
            raise ValueError("atdb_fits is required unless decoded_type53_rows are supplied")
        decoded, atdb_meta = _decode_type53_records(
            atdb_fits=atdb_fits, wanted_records=wanted,
            index_cache_path=index_cache_path, rebuild_index_cache=rebuild_index_cache,
        )

    state_selection_status = "preloaded_live_state"
    if live_state is None:
        if live_rate_grid_probe_csv is None:
            raise ValueError("live_rate_grid_probe_csv is required unless live_state is supplied")
        states = read_live_rate_grid_probe_csv(live_rate_grid_probe_csv)
        chosen, state_selection_status = _select_state(states, live_rate_grid_state)
        if chosen is None:
            raise ValueError(f"could not select live rate-grid state: {state_selection_status}")
        md = dict(chosen.metadata)
        md.update({"zone_index": chosen.zone_index, "pass_index": chosen.pass_index, "ldir": chosen.ldir, "ncn2m": chosen.ncn2m})
        live_state = Type53LiveRadiationState.from_sequences(chosen.epim_eV, chosen.bremsam, chosen.bremsint, metadata=md)
    validation = live_state.validate()
    context_row, context_ready = _context_check(
        state=live_state, probe_rows=ucalc, density_field_semantics=live_density_field_semantics,
        relative_tolerance=live_context_relative_tolerance,
    )
    context_row.update({"state_selection_status": state_selection_status, **validation})

    native_by_key: dict[tuple[int | None, int], dict[str, Any]] = {}
    record_rows: list[dict[str, Any]] = []
    for probe in ucalc:
        rec = int(_as_int(probe.get("ml_data"), -1) or -1)
        cap = _as_int(probe.get("capture_index"), None)
        d = decoded.get(rec)
        if d is None:
            native = {"status": "not_evaluated_record_not_decoded"}
        else:
            native = evaluate_type53_ucalc_record(
                d, live_state,
                temperature_k=(_as_float(probe.get("t_xstar_1e4K"), 0.0) or 0.0) * 1.0e4,
                xpx_cm3=_as_float(probe.get("xpx"), 0.0) or 0.0,
                electron_fraction_xee=_as_float(probe.get("xnx"), 0.0) or 0.0,
                ptmp1=_as_float(probe.get("ptmp1"), 0.0) or 0.0,
                ptmp2=_as_float(probe.get("ptmp2"), 0.0) or 0.0,
                lfast=lfast,
            )
        native_by_key[(cap, rec)] = native
        native_ans = [
            _as_float(native.get("ans1_photoionization_s^-1"), 0.0) or 0.0,
            _as_float(native.get("ans2_milne_recombination_s^-1"), 0.0) or 0.0,
            _as_float(native.get("ans3_cooling_signed_erg_s^-1"), 0.0) or 0.0,
            _as_float(native.get("ans4_heating_signed_erg_s^-1"), 0.0) or 0.0,
            _as_float(native.get("ans5_electron_pov_cooling_signed_erg_s^-1"), 0.0) or 0.0,
            _as_float(native.get("ans6_electron_pov_heating_signed_erg_s^-1"), 0.0) or 0.0,
        ]
        xstar_ans = [_as_float(probe.get(f"ans{i}"), 0.0) or 0.0 for i in range(1, 7)]
        rels = [_rel(a, b) for a, b in zip(native_ans, xstar_ans)]
        endpoint = d is not None and _as_int(probe.get("idest1"), None) == _as_int(d.get("bound_level"), None) and _as_int(probe.get("idest2"), None) == _as_int(d.get("destination_level"), None)
        evaluated = native.get("status") == "evaluated"
        rate_pass = evaluated and context_ready and endpoint and rels[0] <= relative_rate_tolerance and rels[1] <= relative_rate_tolerance
        heat_pass = rate_pass and all(v <= relative_rate_tolerance for v in rels[2:])
        row = {
            "family_key": "type53_rate7", "record": rec, "capture_index": probe.get("capture_index", ""),
            "jkk_ion": probe.get("jkk_ion", ""),
            "xstar_idest1": probe.get("idest1", ""), "native_idest1_bound": (d or {}).get("bound_level", ""),
            "xstar_idest2": probe.get("idest2", ""), "native_idest2_destination": (d or {}).get("destination_level", ""),
            "endpoint_order_convention": "type53_packed_order: idest1=bound, idest2=continuum_or_parent",
            "endpoint_order_match": endpoint,
            "temperature_K": (_as_float(probe.get("t_xstar_1e4K"), 0.0) or 0.0) * 1.0e4,
            "xpx_cm^-3": _as_float(probe.get("xpx"), 0.0) or 0.0,
            "probe_legacy_xnx_value_interpreted_as_xee": _as_float(probe.get("xnx"), 0.0) or 0.0,
            "physical_electron_density_xpx_times_xee_cm^-3": (_as_float(probe.get("xpx"), 0.0) or 0.0) * (_as_float(probe.get("xnx"), 0.0) or 0.0),
            "ptmp1": probe.get("ptmp1", ""), "ptmp2": probe.get("ptmp2", ""), "cfrac": probe.get("cfrac", ""),
            "native_status": native.get("status", ""), "native_source_branch": native.get("source_branch", ""),
            "live_state_context_ready": context_ready,
            "threshold_eV": (d or {}).get("threshold_eV", ""),
            "base_threshold_eV": (d or {}).get("base_threshold_eV", ""),
            "parent_excitation_eV": (d or {}).get("parent_excitation_eV", ""),
            "continuum_statistical_weight": (d or {}).get("continuum_statistical_weight", ""),
            "destination_statistical_weight": (d or {}).get("destination_statistical_weight", ""),
            "rnist": native.get("rnist", ""), "n_cross_section_pairs": len((d or {}).get("energy_above_threshold_ryd", [])),
        }
        for i in range(6):
            row[f"xstar_ans{i+1}"] = xstar_ans[i]
            row[f"native_ans{i+1}"] = native_ans[i]
            row[f"ans{i+1}_relative_difference"] = rels[i]
            row[f"ans{i+1}_match"] = evaluated and context_ready and rels[i] <= relative_rate_tolerance
        row["record_rate_parity_status"] = "pass" if rate_pass else "differs"
        row["record_heating_cooling_parity_status"] = "pass" if heat_pass else "differs"
        record_rows.append(row)

    record_result = {(_as_int(r.get("capture_index"), None), int(r["record"])): r for r in record_rows}
    matrix_rows: list[dict[str, Any]] = []
    for term in matrix:
        rec = int(_as_int(term.get("ml_data"), -1) or -1)
        cap = _as_int(term.get("capture_index"), None)
        native = native_by_key.get((cap, rec), {})
        kind = str(term.get("insertion_kind") or term.get("matrix_insertion_kind") or "")
        ans1 = _as_float(native.get("ans1_photoionization_s^-1"), 0.0) or 0.0
        ans2 = _as_float(native.get("ans2_milne_recombination_s^-1"), 0.0) or 0.0
        exp = _expected(kind, ans1, ans2)
        obs = _as_float(term.get("ajisi_1"), 0.0) or 0.0
        rd = _rel(exp or 0.0, obs) if exp is not None else math.inf
        status = record_result.get((cap, rec), {}).get("record_rate_parity_status", "")
        match = exp is not None and status == "pass" and rd <= relative_rate_tolerance
        rs, cs = _as_bool(term.get("row_endpoint_selected")), _as_bool(term.get("col_endpoint_selected"))
        matrix_rows.append({
            "family_key": "type53_rate7", "record": rec, "capture_index": term.get("capture_index", ""),
            "insertion_kind": kind, "compact_row_ipmat2": term.get("compact_row_ipmat2", ""),
            "compact_col_ipmat2": term.get("compact_col_ipmat2", ""),
            "row_endpoint_selected": rs, "col_endpoint_selected": cs,
            "selected_system_partition": "selected_internal" if rs and cs else ("fixed_external" if rs else "external_row_out_of_scope"),
            "xstar_ajisi_1_s^-1": obs, "native_expected_ajisi_1_s^-1": exp if exp is not None else "",
            "relative_difference": rd if math.isfinite(rd) else "", "relative_rate_tolerance": relative_rate_tolerance,
            "matrix_term_match": match, "record_rate_parity_status": status,
        })

    selected = _selected_indices(parent, matrix)
    selected_terms = [r for r in matrix_rows if _as_bool(r.get("row_endpoint_selected"))]
    external_terms = [r for r in selected_terms if not _as_bool(r.get("col_endpoint_selected"))]
    internal_terms = [r for r in selected_terms if _as_bool(r.get("col_endpoint_selected"))]
    rate_ready = bool(record_rows) and all(r["record_rate_parity_status"] == "pass" for r in record_rows)
    heat_ready = bool(record_rows) and all(r["record_heating_cooling_parity_status"] == "pass" for r in record_rows)
    matrix_ready = bool(matrix_rows) and all(_as_bool(r["matrix_term_match"]) for r in matrix_rows)
    selected_ready = bool(selected_terms) and all(_as_bool(r["matrix_term_match"]) for r in selected_terms)
    external_ready = bool(external_terms) and all(_as_bool(r["matrix_term_match"]) for r in external_terms)
    touched = {int(_as_int(r.get("compact_row_ipmat2"), -1) or -1) for r in selected_terms}
    selected_rows = [{
        "xstar_ipmat2_index": ip,
        "n_selected_row_terms": sum(_as_int(r.get("compact_row_ipmat2"), None) == ip for r in selected_terms),
        "n_selected_internal_terms": sum(_as_int(r.get("compact_row_ipmat2"), None) == ip and r["selected_system_partition"] == "selected_internal" for r in selected_terms),
        "n_fixed_external_terms": sum(_as_int(r.get("compact_row_ipmat2"), None) == ip and r["selected_system_partition"] == "fixed_external" for r in selected_terms),
        "row_touched_by_native_type53": ip in touched,
        "all_row_terms_match": all(_as_bool(r["matrix_term_match"]) for r in selected_terms if _as_int(r.get("compact_row_ipmat2"), None) == ip),
    } for ip in selected]
    family_summary = [{
        "family_key": "type53_rate7", "n_records": len(record_rows),
        "n_records_rate_parity_pass": sum(r["record_rate_parity_status"] == "pass" for r in record_rows),
        "n_records_heating_cooling_parity_pass": sum(r["record_heating_cooling_parity_status"] == "pass" for r in record_rows),
        "n_matrix_terms": len(matrix_rows), "n_matrix_terms_match": sum(_as_bool(r["matrix_term_match"]) for r in matrix_rows),
        "n_selected_row_terms": len(selected_terms), "n_selected_internal_terms": len(internal_terms),
        "n_fixed_external_terms": len(external_terms), "n_external_row_out_of_scope_terms": len(matrix_rows) - len(selected_terms),
        "max_ans1_relative_difference": max((float(r["ans1_relative_difference"]) for r in record_rows), default=math.inf),
        "max_ans2_relative_difference": max((float(r["ans2_relative_difference"]) for r in record_rows), default=math.inf),
        "max_heating_cooling_relative_difference": max((float(r[f"ans{i}_relative_difference"]) for r in record_rows for i in range(3, 7)), default=math.inf),
        "max_matrix_term_relative_difference": max((float(r["relative_difference"]) for r in matrix_rows if r.get("relative_difference") != ""), default=math.inf),
        "live_rate_parity_ready": rate_ready, "heating_cooling_parity_ready": heat_ready,
        "compact_matrix_parity_ready": matrix_ready, "selected_system_parity_ready": selected_ready,
        "external_rhs_parity_ready": external_ready,
    }]
    summary = {
        "audit_version": "v0.3.208", "status": "type53_exact_live_native_parity_audit_completed",
        "ion": parent.get("ion", ""), "selected_basis_solve_call_id": parent.get("selected_basis_solve_call_id", ""),
        "selection": parent.get("selection", ""), "occurrence_rank": parent.get("occurrence_rank", ""),
        "selected_xstar_ipmat2_indices": ";".join(str(v) for v in selected),
        "relative_rate_tolerance": relative_rate_tolerance, "live_context_relative_tolerance": live_context_relative_tolerance,
        "live_rate_grid_probe_csv": str(live_rate_grid_probe_csv or "preloaded"),
        "live_rate_grid_state_selector": str(live_rate_grid_state), "live_rate_grid_state_selection_status": state_selection_status,
        "live_density_field_semantics": live_density_field_semantics, "lfast": int(lfast),
        "live_state_context_ready": context_ready, **atdb_meta,
        "n_selected_type53_ucalc_records": len(record_rows),
        "n_type53_records_rate_parity_pass": sum(r["record_rate_parity_status"] == "pass" for r in record_rows),
        "n_type53_records_heating_cooling_parity_pass": sum(r["record_heating_cooling_parity_status"] == "pass" for r in record_rows),
        "n_type53_compact_matrix_terms": len(matrix_rows), "n_type53_compact_matrix_terms_match": sum(_as_bool(r["matrix_term_match"]) for r in matrix_rows),
        "n_type53_selected_row_terms": len(selected_terms), "n_type53_selected_internal_terms": len(internal_terms),
        "n_type53_fixed_external_terms": len(external_terms), "n_type53_external_row_out_of_scope_terms": len(matrix_rows) - len(selected_terms),
        "native_type53_exact_live_rate_parity_ready": rate_ready,
        "native_type53_heating_cooling_parity_ready": heat_ready,
        "native_type53_opacity_rrc_parity_ready": False,
        "native_type53_compact_matrix_parity_ready": matrix_ready,
        "native_type53_external_rhs_parity_ready": external_ready,
        "native_type53_selected_system_parity_ready": rate_ready and matrix_ready and selected_ready,
        "type53_scale44_resolved_by_exact_live_state": rate_ready and matrix_ready,
        "empirical_type53_scale_applied": False,
        "native_priority_subset_matrix_closure_ready": False,
        "dominant_next_target": "integrate_exact_live_type53_into_native_type51_type50_type71_selected_system" if rate_ready and matrix_ready else "resolve_exact_live_type53_context_rate_or_matrix_parity",
    }
    return {"summary": summary, "record_rows": record_rows, "matrix_term_rows": matrix_rows, "family_summary_rows": family_summary, "selected_row_rows": selected_rows, "live_state_context_rows": [context_row]}


def write_type53_live_native_parity_audit(out_dir: str | Path, audit: Mapping[str, Any]) -> dict[str, str]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    paths = {
        "records_csv": out / "xstar_type53_live_native_parity_audit_records.csv",
        "matrix_terms_csv": out / "xstar_type53_live_native_parity_audit_matrix_terms.csv",
        "family_summary_csv": out / "xstar_type53_live_native_parity_audit_family_summary.csv",
        "selected_rows_csv": out / "xstar_type53_live_native_parity_audit_selected_rows.csv",
        "live_state_context_csv": out / "xstar_type53_live_native_parity_audit_live_state_context.csv",
        "json": out / "xstar_type53_live_native_parity_audit.json",
        "markdown": out / "xstar_type53_live_native_parity_audit.md",
    }
    for key, data in (("records_csv", "record_rows"), ("matrix_terms_csv", "matrix_term_rows"), ("family_summary_csv", "family_summary_rows"), ("selected_rows_csv", "selected_row_rows"), ("live_state_context_csv", "live_state_context_rows")):
        _write_csv(paths[key], audit.get(data, []))
    paths["json"].write_text(json.dumps(dict(audit), indent=2, sort_keys=True), encoding="utf-8")
    s = dict(audit.get("summary", {}))
    paths["markdown"].write_text("\n".join([
        "# XSTAR exact live-radiation type-53 parity audit", "",
        f"- Audit version: `{s.get('audit_version','')}`",
        f"- Ion: `{s.get('ion','')}`",
        f"- Live state context ready: `{s.get('live_state_context_ready',False)}`",
        f"- Native type-53 live-rate parity ready: `{s.get('native_type53_exact_live_rate_parity_ready',False)}`",
        f"- Heating/cooling parity ready: `{s.get('native_type53_heating_cooling_parity_ready',False)}`",
        f"- Compact matrix parity ready: `{s.get('native_type53_compact_matrix_parity_ready',False)}`",
        f"- Type-53 scale-44 resolved: `{s.get('type53_scale44_resolved_by_exact_live_state',False)}`", "",
        "The gate consumes an explicitly selected live `epim`, `bremsam`, and `bremsint` state. No proxy continuum or empirical scale is accepted.", "",
        "Opacity/RRC-emissivity readiness remains separate because the selected matrix manifest does not carry the complete bound/parent population context required to compare those arrays.", "",
    ]) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}


__all__ = ["build_type53_live_native_parity_audit", "write_type53_live_native_parity_audit"]
