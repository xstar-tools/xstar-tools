"""Build a source-code-derived matrix-closure manifest for priority basis rows.

This module joins the staged compact-basis activation produced by
``xstar_priority_basis_expansion`` to the raw XSTAR ``ucalc`` and
``calc_hmc_ion`` probes.  It selects one common local-state occurrence for
*all* probed ATDB records, applies the exact ``calc_hmc_element`` endpoint
translation

``element_ipmat2 = ion_ipmat2_offset + indbi``

and then retains every four-row Fortran matrix insertion that touches an
activated compact row.  This is essential for photoionization/recombination
records whose local ``indbi`` endpoint lies beyond the current ion's ``nlev``:
those indices intentionally enter an adjacent-ion or superlevel block and must
not be interpreted as missing local levels.

The audit also distinguishes ordinary four-row matrix records from ``ucalc``
metadata records for which XSTAR intentionally makes no matrix insertion (for
example records with ``idest2 <= 0``).  The result is a diagnostic
implementation manifest.  It does not alter default matrix assembly or solve
the expanded basis.
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return int(round(number)) if math.isfinite(number) else default
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
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
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


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


def _resolve_optional_csv(path: str | Path | None, preferred_name: str) -> Tuple[Path | None, str]:
    if path is None or not str(path).strip():
        return None, "csv_not_supplied"
    root = Path(path)
    if root.is_file():
        return (root, "csv_loaded") if root.exists() else (root, "csv_missing")
    if root.is_dir():
        direct = root / preferred_name
        if direct.exists():
            return direct, "csv_loaded"
        hits = sorted(root.rglob(preferred_name))
        if len(hits) == 1:
            return hits[0], "csv_loaded"
        return None, "csv_missing" if not hits else "directory_multiple_csv_candidates"
    return root, "csv_missing"


def _block_maps(
    compact_rows: Sequence[Mapping[str, Any]],
) -> Tuple[
    Dict[int, int],
    Dict[int, int],
    Dict[Tuple[int, int], int],
    Dict[int, int],
    Dict[int, Tuple[int, int]],
    int,
]:
    """Return physical-role maps and exact element-offset maps.

    ``calc_hmc_element.f90`` maps an ion-local ``indbi`` endpoint into the
    compact element matrix with ``indbe = indbi + ipmat2``.  Therefore each
    included ion block has a constant zero-based offset ``ipmat2 = compact -
    local``.  This offset mapping remains valid when ``indbi > nlev`` and the
    endpoint intentionally lands in a following compact ion block.
    """
    nionp_to_jkk: Dict[int, int] = {}
    jkk_to_nionp: Dict[int, int] = {}
    role_to_ip: Dict[Tuple[int, int], int] = {}
    offsets_by_nionp: Dict[int, set[int]] = defaultdict(set)
    block_bounds: Dict[int, List[int]] = defaultdict(list)
    max_basis = 0
    for row in compact_rows:
        ip = _as_int(row.get("xstar_ipmat2_index"), None)
        nionp = _as_int(row.get("primary_nionp_current"), None)
        jkk = _as_int(row.get("primary_jkk_ion"), None)
        local = _as_int(row.get("primary_local_level_index"), None)
        if ip is not None:
            max_basis = max(max_basis, ip)
        if nionp is not None and jkk is not None:
            nionp_to_jkk.setdefault(nionp, jkk)
            jkk_to_nionp.setdefault(jkk, nionp)
        if ip is not None and nionp is not None and local is not None and local > 0:
            role_to_ip.setdefault((nionp, local), ip)
            offsets_by_nionp[nionp].add(ip - local)
            block_bounds[nionp].append(ip)
        for prefix in ("population_role", "parent_role"):
            rn = _as_int(row.get(f"{prefix}_nionp"), None)
            rl = _as_int(row.get(f"{prefix}_local_level_index"), None)
            if ip is not None and rn is not None and rl is not None:
                role_to_ip.setdefault((rn, rl), ip)

    nionp_to_offset: Dict[int, int] = {}
    for nionp, offsets in offsets_by_nionp.items():
        if len(offsets) != 1:
            raise ValueError(
                f"inconsistent compact ipmat2 offsets for nionp={nionp}: {sorted(offsets)}"
            )
        nionp_to_offset[nionp] = next(iter(offsets))
    nionp_to_bounds = {
        nionp: (min(values), max(values)) for nionp, values in block_bounds.items()
    }
    return (
        nionp_to_jkk,
        jkk_to_nionp,
        role_to_ip,
        nionp_to_offset,
        nionp_to_bounds,
        max_basis,
    )


def _selected_role_rows(
    activation_rows: Sequence[Mapping[str, Any]],
    nionp_to_jkk: Mapping[int, int],
) -> List[Dict[str, Any]]:
    roles: List[Dict[str, Any]] = []
    for row in activation_rows:
        ip = _as_int(row.get("xstar_ipmat2_index"), None)
        if ip is None:
            continue
        role_specs = [
            (
                "population_role",
                _as_int(row.get("population_role_nionp"), _as_int(row.get("primary_nionp_current"), None)),
                _as_int(row.get("population_role_local_level_index"), _as_int(row.get("primary_local_level_index"), None)),
            )
        ]
        pn = _as_int(row.get("parent_role_nionp"), None)
        pl = _as_int(row.get("parent_role_local_level_index"), None)
        if pn is not None and pl is not None:
            role_specs.append(("parent_continuum_role", pn, pl))
        for kind, nionp, local in role_specs:
            if nionp is None or local is None:
                continue
            roles.append({
                "xstar_ipmat2_index": ip,
                "activation_order": row.get("activation_order", ""),
                "proposed_python_global_index": row.get("proposed_python_global_index", ""),
                "role_kind": kind,
                "nionp_current": nionp,
                "jkk_ion": nionp_to_jkk.get(nionp, ""),
                "local_level_index": local,
                "sharing_class": row.get("sharing_class", ""),
                "xstar_after_population": _as_float(row.get("xstar_after_population")),
            })
    roles.sort(key=lambda r: (_as_int(r.get("activation_order"), 10**9) or 10**9, str(r.get("role_kind"))))
    return roles


def _role_lookup(role_rows: Sequence[Mapping[str, Any]]) -> Dict[Tuple[int, int], List[int]]:
    lookup: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for row in role_rows:
        jkk = _as_int(row.get("jkk_ion"), None)
        local = _as_int(row.get("local_level_index"), None)
        ip = _as_int(row.get("xstar_ipmat2_index"), None)
        if jkk is not None and local is not None and ip is not None and ip not in lookup[(jkk, local)]:
            lookup[(jkk, local)].append(ip)
    return lookup


def _select_ucalc_occurrence_rows(
    ucalc_csv: Path,
    *,
    occurrence_rank: int,
) -> List[Dict[str, Any]]:
    """Select one common occurrence for every ATDB record in a streaming pass."""
    if occurrence_rank == 0:
        raise ValueError("occurrence_rank is 1-based; use -1 for latest")

    counts: Dict[int, int] = defaultdict(int)
    selected: Dict[int, Dict[str, Any]] = {}
    if occurrence_rank > 0:
        with ucalc_csv.open("r", newline="", encoding="utf-8") as handle:
            for raw in csv.DictReader(handle):
                rec = _as_int(raw.get("ml_data"), None)
                if rec is None:
                    continue
                counts[rec] += 1
                if counts[rec] == occurrence_rank:
                    selected[rec] = dict(raw)
    else:
        keep = abs(occurrence_rank)
        tails: Dict[int, deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=keep))
        with ucalc_csv.open("r", newline="", encoding="utf-8") as handle:
            for raw in csv.DictReader(handle):
                rec = _as_int(raw.get("ml_data"), None)
                if rec is None:
                    continue
                counts[rec] += 1
                tails[rec].append(dict(raw))
        for rec, rows in tails.items():
            if len(rows) >= keep:
                selected[rec] = list(rows)[0]

    rows: List[Dict[str, Any]] = []
    for rec, row in selected.items():
        out = dict(row)
        out["ucalc_occurrence_count"] = counts.get(rec, 0)
        out["selected_occurrence_rank"] = (
            occurrence_rank if occurrence_rank > 0 else counts.get(rec, 0) + occurrence_rank + 1
        )
        rows.append(out)
    rows.sort(key=lambda r: _as_int(r.get("ml_data"), 0) or 0)
    return rows


def _load_selected_matrix_rows(
    matrix_csv: Path,
    selected_ucalc: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    capture_to_ucalc = {
        str(row.get("capture_index") or "").strip(): row
        for row in selected_ucalc
    }
    rows: List[Dict[str, Any]] = []
    with matrix_csv.open("r", newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            cap = str(raw.get("capture_index") or "").strip()
            ucalc = capture_to_ucalc.get(cap)
            if ucalc is None:
                continue
            if _as_int(raw.get("ml_data"), None) != _as_int(ucalc.get("ml_data"), None):
                continue
            row = dict(raw)
            row["jkk_ion"] = ucalc.get("jkk_ion", "")
            row["ans1"] = ucalc.get("ans1", "")
            row["ans2"] = ucalc.get("ans2", "")
            rows.append(row)
    rows.sort(key=lambda r: (_as_int(r.get("capture_index"), 0) or 0, _as_int(r.get("insertion_index"), 0) or 0))
    return rows


def _map_endpoint(
    *,
    nionp: int | None,
    local_indbi: int | None,
    nionp_to_offset: Mapping[int, int],
    max_basis: int,
) -> Tuple[int | None, str]:
    if nionp is None or local_indbi is None:
        return None, "missing_nionp_or_indbi"
    offset = nionp_to_offset.get(nionp)
    if offset is None:
        return None, "missing_ion_block_offset"
    compact = offset + local_indbi
    if compact < 1 or compact > max_basis:
        return None, "outside_compact_element_basis"
    return compact, "mapped_by_calc_hmc_element_offset"


def _map_matrix_terms(
    matrix_rows: Sequence[Mapping[str, Any]],
    jkk_to_nionp: Mapping[int, int],
    nionp_to_offset: Mapping[int, int],
    selected_ips: Sequence[int],
    max_basis: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    selected_set = set(selected_ips)
    all_mapped: List[Dict[str, Any]] = []
    touching: List[Dict[str, Any]] = []
    unmapped: List[Dict[str, Any]] = []
    for raw in matrix_rows:
        jkk = _as_int(raw.get("jkk_ion"), None)
        nionp = jkk_to_nionp.get(jkk) if jkk is not None else None
        local_row = _as_int(raw.get("indbi_1"), None)
        local_col = _as_int(raw.get("indbi_2"), None)
        compact_row, row_status = _map_endpoint(
            nionp=nionp,
            local_indbi=local_row,
            nionp_to_offset=nionp_to_offset,
            max_basis=max_basis,
        )
        compact_col, col_status = _map_endpoint(
            nionp=nionp,
            local_indbi=local_col,
            nionp_to_offset=nionp_to_offset,
            max_basis=max_basis,
        )
        out = dict(raw)
        out.update({
            "nionp_current": nionp if nionp is not None else "",
            "ion_ipmat2_offset": nionp_to_offset.get(nionp, "") if nionp is not None else "",
            "compact_row_ipmat2": compact_row if compact_row is not None else "",
            "compact_col_ipmat2": compact_col if compact_col is not None else "",
            "row_endpoint_selected": compact_row in selected_set if compact_row is not None else False,
            "col_endpoint_selected": compact_col in selected_set if compact_col is not None else False,
            "term_touches_selected_compact_row": (compact_row in selected_set) or (compact_col in selected_set),
            "row_endpoint_mapping_status": row_status,
            "col_endpoint_mapping_status": col_status,
            "compact_endpoint_mapping_status": (
                "mapped_by_calc_hmc_element_offset"
                if compact_row is not None and compact_col is not None
                else "unmapped_endpoint"
            ),
        })
        all_mapped.append(out)
        if out["term_touches_selected_compact_row"]:
            touching.append(out)
        if compact_row is None or compact_col is None:
            unmapped.append({
                "capture_index": raw.get("capture_index", ""),
                "ml_data": raw.get("ml_data", ""),
                "ltyp": raw.get("ltyp", ""),
                "lrtyp": raw.get("lrtyp", ""),
                "jkk_ion": raw.get("jkk_ion", ""),
                "nionp_current": nionp if nionp is not None else "",
                "ion_ipmat2_offset": nionp_to_offset.get(nionp, "") if nionp is not None else "",
                "insertion_kind": raw.get("insertion_kind", ""),
                "indbi_1": raw.get("indbi_1", ""),
                "indbi_2": raw.get("indbi_2", ""),
                "compact_row_ipmat2": compact_row if compact_row is not None else "",
                "compact_col_ipmat2": compact_col if compact_col is not None else "",
                "row_endpoint_mapping_status": row_status,
                "col_endpoint_mapping_status": col_status,
                "unmapped_endpoint": "row" if compact_row is None else "col" if compact_col is None else "",
            })
    return all_mapped, touching, unmapped


def _family_key(row: Mapping[str, Any]) -> str:
    ltyp = _as_int(row.get("ltyp"), None)
    lrtyp = _as_int(row.get("lrtyp"), None)
    return f"type{ltyp if ltyp is not None else 'unknown'}_rate{lrtyp if lrtyp is not None else 'unknown'}"


def _direct_role_touches(
    row: Mapping[str, Any],
    role_lookup: Mapping[Tuple[int, int], Sequence[int]],
) -> List[int]:
    jkk = _as_int(row.get("jkk_ion"), None)
    if jkk is None:
        return []
    idest1 = _as_int(row.get("idest1"), None)
    idest2 = _as_int(row.get("idest2"), None)
    return sorted(set(role_lookup.get((jkk, idest1), ())) | set(role_lookup.get((jkk, idest2), ())))


def _matrix_insertion_expected(row: Mapping[str, Any]) -> bool:
    # calc_hmc_ion inserts the four rows only inside the positive-destination
    # branch.  The debug probe intentionally also contains metadata records
    # such as type-6/rate-13 rows with idest2=0.
    return (_as_int(row.get("idest1"), 0) or 0) > 0 and (_as_int(row.get("idest2"), 0) or 0) > 0


def build_priority_matrix_closure_audit(
    *,
    priority_basis_expansion: str | Path,
    ucalc_probe_csv: str | Path | None = None,
    matrix_probe_csv: str | Path | None = None,
    occurrence_rank: int = 73,
) -> Dict[str, Any]:
    """Build the Fortran-derived matrix-closure manifest for active priority rows."""
    root = Path(priority_basis_expansion)
    activation_path = _resolve_product(root, "xstar_priority_basis_expansion_activation_manifest.csv")
    compact_path = _resolve_product(root, "xstar_priority_basis_expansion_compact_basis.csv")
    closure_path = _resolve_product(root, "xstar_priority_basis_expansion_closure_requirements.csv")
    json_path = _resolve_product(root, "xstar_priority_basis_expansion.json")

    activation_rows = _read_csv(activation_path)
    compact_rows = _read_csv(compact_path)
    closure_rows = _read_csv(closure_path)
    metadata = json.loads(json_path.read_text(encoding="utf-8"))
    prior_summary = dict(metadata.get("summary", {}))

    (
        nionp_to_jkk,
        jkk_to_nionp,
        role_to_ip,
        nionp_to_offset,
        nionp_to_bounds,
        max_basis,
    ) = _block_maps(compact_rows)
    role_rows = _selected_role_rows(activation_rows, nionp_to_jkk)
    roles = _role_lookup(role_rows)
    selected_ips = sorted({_as_int(row.get("xstar_ipmat2_index"), 0) or 0 for row in activation_rows})

    block_rows = [
        {
            "nionp_current": nionp,
            "jkk_ion": nionp_to_jkk.get(nionp, ""),
            "ion_ipmat2_offset": offset,
            "compact_block_start": nionp_to_bounds.get(nionp, ("", ""))[0],
            "compact_block_end": nionp_to_bounds.get(nionp, ("", ""))[1],
        }
        for nionp, offset in sorted(nionp_to_offset.items())
    ]

    ucalc_path, ucalc_status = _resolve_optional_csv(ucalc_probe_csv, "xstar_ucalc_record_probe.csv")
    matrix_path, matrix_status = _resolve_optional_csv(matrix_probe_csv, "xstar_calc_hmc_ion_matrix_probe.csv")

    selected_all_ucalc: List[Dict[str, Any]] = []
    raw_matrix_rows: List[Dict[str, Any]] = []
    all_mapped_matrix_rows: List[Dict[str, Any]] = []
    compact_matrix_rows: List[Dict[str, Any]] = []
    unmapped_rows: List[Dict[str, Any]] = []
    if ucalc_status == "csv_loaded" and ucalc_path is not None:
        selected_all_ucalc = _select_ucalc_occurrence_rows(ucalc_path, occurrence_rank=occurrence_rank)
    if selected_all_ucalc and matrix_status == "csv_loaded" and matrix_path is not None:
        raw_matrix_rows = _load_selected_matrix_rows(matrix_path, selected_all_ucalc)
        all_mapped_matrix_rows, compact_matrix_rows, unmapped_rows = _map_matrix_terms(
            raw_matrix_rows,
            jkk_to_nionp,
            nionp_to_offset,
            selected_ips,
            max_basis,
        )

    rows_by_record: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    touching_terms_by_record: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for row in raw_matrix_rows:
        rec = _as_int(row.get("ml_data"), None)
        if rec is not None:
            rows_by_record[rec].append(row)
    for row in compact_matrix_rows:
        rec = _as_int(row.get("ml_data"), None)
        if rec is not None:
            touching_terms_by_record[rec].append(row)

    ucalc_by_record = {
        _as_int(row.get("ml_data"), 0) or 0: row for row in selected_all_ucalc
    }
    matrix_touching_records = set(touching_terms_by_record)
    direct_nonmatrix_records: set[int] = set()
    direct_touch_by_record: Dict[int, List[int]] = {}
    for rec, row in ucalc_by_record.items():
        direct = _direct_role_touches(row, roles)
        direct_touch_by_record[rec] = direct
        if direct and not _matrix_insertion_expected(row):
            direct_nonmatrix_records.add(rec)

    included_records = sorted(matrix_touching_records | direct_nonmatrix_records)
    ucalc_rows: List[Dict[str, Any]] = []
    nonmatrix_ucalc_rows: List[Dict[str, Any]] = []
    for rec in included_records:
        row = dict(ucalc_by_record[rec])
        matrix_count = len(rows_by_record.get(rec, []))
        expected = _matrix_insertion_expected(row)
        touched_from_terms = sorted({
            endpoint
            for term in touching_terms_by_record.get(rec, [])
            for endpoint in (
                _as_int(term.get("compact_row_ipmat2"), None),
                _as_int(term.get("compact_col_ipmat2"), None),
            )
            if endpoint in set(selected_ips)
        })
        direct = direct_touch_by_record.get(rec, [])
        touched = sorted(set(touched_from_terms) | set(direct))
        row.update({
            "touched_selected_xstar_ipmat2_indices": ";".join(str(v) for v in touched),
            "family_key": _family_key(row),
            "matrix_insertion_expected": expected,
            "expected_fortran_matrix_row_count": 4 if expected else 0,
            "fortran_matrix_row_count": matrix_count,
            "matrix_row_count_matches_expected": matrix_count == (4 if expected else 0),
            "four_matrix_rows_ready": expected and matrix_count == 4,
            "record_manifest_class": "matrix_record" if expected else "nonmatrix_ucalc_metadata",
        })
        ucalc_rows.append(row)
        if not expected:
            nonmatrix_ucalc_rows.append(row)

    selected_summary: List[Dict[str, Any]] = []
    for ip in selected_ips:
        records = [
            row for row in ucalc_rows
            if str(ip) in str(row.get("touched_selected_xstar_ipmat2_indices", "")).split(";")
        ]
        matrix_records = [row for row in records if _as_bool(row.get("matrix_insertion_expected"))]
        nonmatrix_records = [row for row in records if not _as_bool(row.get("matrix_insertion_expected"))]
        terms = [
            row for row in compact_matrix_rows
            if _as_int(row.get("compact_row_ipmat2"), None) == ip or _as_int(row.get("compact_col_ipmat2"), None) == ip
        ]
        role_subset = [row for row in role_rows if _as_int(row.get("xstar_ipmat2_index"), None) == ip]
        families = sorted({_family_key(row) for row in records})
        counterpart = sorted({
            endpoint
            for row in terms
            for endpoint in (_as_int(row.get("compact_row_ipmat2"), None), _as_int(row.get("compact_col_ipmat2"), None))
            if endpoint is not None and endpoint != ip
        })
        selected_summary.append({
            "xstar_ipmat2_index": ip,
            "activation_order": next((row.get("activation_order", "") for row in activation_rows if _as_int(row.get("xstar_ipmat2_index"), None) == ip), ""),
            "n_physical_roles": len(role_subset),
            "physical_roles": ";".join(f"{row.get('role_kind')}:{row.get('nionp_current')}:{row.get('local_level_index')}" for row in role_subset),
            "n_ucalc_records": len(records),
            "n_matrix_ucalc_records": len(matrix_records),
            "n_nonmatrix_ucalc_metadata_records": len(nonmatrix_records),
            "n_fortran_matrix_terms_touching_row": len(terms),
            "n_rate_families": len(families),
            "rate_families": ";".join(families),
            "counterpart_compact_rows": ";".join(str(v) for v in counterpart),
            "row_has_fortran_matrix_terms": len(terms) > 0,
            "fortran_record_manifest_ready": (
                len(terms) > 0
                and all(_as_bool(row.get("matrix_row_count_matches_expected")) for row in records)
            ),
            "native_matrix_terms_ready": False,
        })

    family_acc: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "records": set(), "matrix_records": set(), "nonmatrix_records": set(),
        "terms": 0, "selected_rows": set(), "abs_ajisi1_sum": 0.0,
    })
    for row in ucalc_rows:
        fam = str(row.get("family_key"))
        rec = _as_int(row.get("ml_data"), 0) or 0
        family_acc[fam]["records"].add(rec)
        if _as_bool(row.get("matrix_insertion_expected")):
            family_acc[fam]["matrix_records"].add(rec)
        else:
            family_acc[fam]["nonmatrix_records"].add(rec)
        for token in str(row.get("touched_selected_xstar_ipmat2_indices", "")).split(";"):
            value = _as_int(token, None)
            if value is not None:
                family_acc[fam]["selected_rows"].add(value)
    for row in compact_matrix_rows:
        fam = _family_key(row)
        family_acc[fam]["terms"] += 1
        family_acc[fam]["abs_ajisi1_sum"] += abs(_as_float(row.get("ajisi_1")))
    family_rows = [{
        "family_key": fam,
        "n_ucalc_records": len(data["records"]),
        "n_matrix_ucalc_records": len(data["matrix_records"]),
        "n_nonmatrix_ucalc_metadata_records": len(data["nonmatrix_records"]),
        "n_compact_matrix_terms": data["terms"],
        "n_selected_rows_touched": len(data["selected_rows"]),
        "selected_xstar_ipmat2_indices": ";".join(str(v) for v in sorted(data["selected_rows"])),
        "abs_ajisi1_sum": data["abs_ajisi1_sum"],
        "native_family_port_ready": False,
    } for fam, data in sorted(family_acc.items())]

    matrix_records = [row for row in ucalc_rows if _as_bool(row.get("matrix_insertion_expected"))]
    n_four = sum(_as_bool(row.get("four_matrix_rows_ready")) for row in matrix_records)
    n_expected_match = sum(_as_bool(row.get("matrix_row_count_matches_expected")) for row in ucalc_rows)
    n_selected_with_terms = sum(_as_bool(row.get("row_has_fortran_matrix_terms")) for row in selected_summary)
    probes_loaded = ucalc_status == "csv_loaded" and matrix_status == "csv_loaded"
    manifest_ready = (
        probes_loaded
        and len(selected_ips) > 0
        and n_selected_with_terms == len(selected_ips)
        and len(unmapped_rows) == 0
        and len(matrix_records) > 0
        and n_four == len(matrix_records)
        and n_expected_match == len(ucalc_rows)
    )
    status = "priority_matrix_closure_manifest_completed" if probes_loaded else "priority_matrix_closure_role_manifest_ready_probe_csvs_not_loaded"
    summary = {
        "audit_version": "v0.3.197",
        "status": status,
        "ion": prior_summary.get("ion", ""),
        "selected_basis_solve_call_id": prior_summary.get("selected_basis_solve_call_id", ""),
        "occurrence_rank": occurrence_rank,
        "selection": "latest-per-record" if occurrence_rank == -1 else "occurrence-rank",
        "ucalc_probe_status": ucalc_status,
        "matrix_probe_status": matrix_status,
        "ucalc_probe_csv": str(ucalc_path or ""),
        "matrix_probe_csv": str(matrix_path or ""),
        "n_selected_compact_rows": len(selected_ips),
        "selected_xstar_ipmat2_indices": ";".join(str(v) for v in selected_ips),
        "n_selected_physical_roles": len(role_rows),
        "n_selected_shared_alias_rows": sum(1 for row in activation_rows if "parent_continuum_shared" in str(row.get("sharing_class", ""))),
        "n_selected_ucalc_records": len(ucalc_rows),
        "n_selected_matrix_ucalc_records": len(matrix_records),
        "n_selected_nonmatrix_ucalc_metadata_records": len(nonmatrix_ucalc_rows),
        "n_selected_records_with_expected_matrix_row_count": n_expected_match,
        "n_selected_records_with_four_matrix_rows": n_four,
        "n_fortran_matrix_rows_loaded_at_occurrence": len(raw_matrix_rows),
        "n_fortran_matrix_rows_loaded": len(raw_matrix_rows),
        "n_compact_matrix_terms_touching_selected_rows": len(compact_matrix_rows),
        "n_unmapped_matrix_endpoints": len(unmapped_rows),
        "n_selected_rows_with_fortran_matrix_terms": n_selected_with_terms,
        "n_selected_rows_without_fortran_matrix_terms": len(selected_ips) - n_selected_with_terms,
        # Backward-compatible aliases, now defined in terms of actual matrix
        # terms rather than direct idest role matching.
        "n_selected_rows_with_fortran_records": n_selected_with_terms,
        "n_selected_rows_without_fortran_records": len(selected_ips) - n_selected_with_terms,
        "n_rate_families": len(family_rows),
        "compact_endpoint_mapping_mode": "calc_hmc_element_ipmat2_offset_plus_indbi",
        "n_compact_element_basis_rows": max_basis,
        "priority_role_manifest_ready": len(role_rows) > 0,
        "fortran_priority_subset_matrix_manifest_ready": manifest_ready,
        "native_priority_subset_matrix_closure_ready": False,
        "dominant_next_target": (
            "port_manifest_rate_families_and_assemble_compact_rhs_normalization_closure"
            if manifest_ready else
            "complete_priority_row_matrix_coverage_or_probe_endpoint_mapping"
        ),
    }
    return {
        "summary": summary,
        "block_rows": block_rows,
        "role_rows": role_rows,
        "ucalc_rows": ucalc_rows,
        "nonmatrix_ucalc_rows": nonmatrix_ucalc_rows,
        "compact_matrix_rows": compact_matrix_rows,
        "selected_row_summary": selected_summary,
        "family_rows": family_rows,
        "unmapped_rows": unmapped_rows,
        "closure_requirement_rows": closure_rows,
        "source_files": {
            "activation_manifest_csv": str(activation_path),
            "compact_basis_csv": str(compact_path),
            "closure_requirements_csv": str(closure_path),
            "priority_expansion_json": str(json_path),
        },
    }


def write_priority_matrix_closure_audit(out_dir: str | Path, audit: Mapping[str, Any]) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "block_map_csv": out / "xstar_priority_matrix_closure_audit_block_map.csv",
        "role_map_csv": out / "xstar_priority_matrix_closure_audit_role_map.csv",
        "ucalc_records_csv": out / "xstar_priority_matrix_closure_audit_ucalc_records.csv",
        "nonmatrix_ucalc_records_csv": out / "xstar_priority_matrix_closure_audit_nonmatrix_ucalc_records.csv",
        "compact_matrix_terms_csv": out / "xstar_priority_matrix_closure_audit_compact_matrix_terms.csv",
        "selected_row_summary_csv": out / "xstar_priority_matrix_closure_audit_selected_row_summary.csv",
        "family_summary_csv": out / "xstar_priority_matrix_closure_audit_family_summary.csv",
        "unmapped_endpoints_csv": out / "xstar_priority_matrix_closure_audit_unmapped_endpoints.csv",
        "closure_requirements_csv": out / "xstar_priority_matrix_closure_audit_closure_requirements.csv",
        "json": out / "xstar_priority_matrix_closure_audit.json",
        "markdown": out / "xstar_priority_matrix_closure_audit.md",
    }
    _write_csv(paths["block_map_csv"], list(audit.get("block_rows", [])))
    _write_csv(paths["role_map_csv"], list(audit.get("role_rows", [])))
    _write_csv(paths["ucalc_records_csv"], list(audit.get("ucalc_rows", [])))
    _write_csv(paths["nonmatrix_ucalc_records_csv"], list(audit.get("nonmatrix_ucalc_rows", [])))
    _write_csv(paths["compact_matrix_terms_csv"], list(audit.get("compact_matrix_rows", [])))
    _write_csv(paths["selected_row_summary_csv"], list(audit.get("selected_row_summary", [])))
    _write_csv(paths["family_summary_csv"], list(audit.get("family_rows", [])))
    _write_csv(paths["unmapped_endpoints_csv"], list(audit.get("unmapped_rows", [])))
    _write_csv(paths["closure_requirements_csv"], list(audit.get("closure_requirement_rows", [])))
    payload = dict(audit)
    paths["json"].write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    summary = dict(audit.get("summary", {}))
    lines = [
        "# XSTAR priority-subset matrix closure audit",
        "",
        f"- audit_version: `{summary.get('audit_version')}`",
        f"- status: `{summary.get('status')}`",
        f"- ion: `{summary.get('ion')}`",
        f"- occurrence_rank: `{summary.get('occurrence_rank')}`",
        f"- selected compact rows: `{summary.get('selected_xstar_ipmat2_indices')}`",
        f"- selected physical roles: `{summary.get('n_selected_physical_roles')}`",
        f"- selected matrix ucalc records: `{summary.get('n_selected_matrix_ucalc_records')}`",
        f"- selected non-matrix ucalc metadata records: `{summary.get('n_selected_nonmatrix_ucalc_metadata_records')}`",
        f"- compact matrix terms: `{summary.get('n_compact_matrix_terms_touching_selected_rows')}`",
        f"- endpoint mapping mode: `{summary.get('compact_endpoint_mapping_mode')}`",
        f"- unmapped matrix endpoints: `{summary.get('n_unmapped_matrix_endpoints')}`",
        f"- selected rows with matrix terms: `{summary.get('n_selected_rows_with_fortran_matrix_terms')}`",
        f"- Fortran manifest ready: `{summary.get('fortran_priority_subset_matrix_manifest_ready')}`",
        f"- native matrix closure ready: `{summary.get('native_priority_subset_matrix_closure_ready')}`",
        "",
        "Matrix endpoints are translated exactly as in `calc_hmc_element.f90`: `compact_ipmat2 = ion_ipmat2_offset + indbi`. Shared parent-continuum / next-ion-ground rows remain one compact unknown with multiple physical roles. Non-matrix `ucalc` metadata records are retained separately and do not falsely fail the four-row insertion check.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {key: str(path) for key, path in paths.items()}
