"""Record-level XSTAR local matrix parity audits.

This module compares three views of the same local rate/matrix construction:

* preserved Python full-global matrix rows from ``xstar-atomic``;
* instrumented XSTAR ``ucalc`` rows containing ``ans1..ans6``;
* instrumented XSTAR ``calc_hmc_ion`` matrix rows containing the four
  ``ajisi/indbi`` insertions made from those rates.

The audit is intentionally diagnostic.  It does not alter solver physics.  Its
purpose is to identify where Python is already source-code equivalent and where
proxy/scaffold rows still differ from the Fortran local matrix.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
        if not math.isfinite(f):
            return default
        return int(round(f))
    except Exception:
        return default


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
        if not math.isfinite(f):
            return default
        return f
    except Exception:
        return default


def _write_csv(path: str | Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        ordered: List[str] = []
        for row in rows:
            for key in row.keys():
                if key not in ordered:
                    ordered.append(str(key))
        fields = ordered or ["status"]
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})


def _read_csv_rows(path: str | Path) -> List[Dict[str, str]]:
    with Path(path).open("r", newline="", encoding="utf-8") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _ion_token(ion: str) -> str:
    return ion.strip().lower().replace(" ", "_").replace("+", "p")


def _find_python_matrix_terms_csv(benchmark_dir: str | Path, ion: str) -> Path:
    root = Path(benchmark_dir)
    candidates: List[Path] = []
    ion_tok = _ion_token(ion)
    preferred_rel = root / "solver_products" / ion_tok / "xstar_like_element_solver_full_global_matrix_terms.csv"
    if preferred_rel.exists():
        return preferred_rel
    for p in root.rglob("xstar_like_element_solver_full_global_matrix_terms.csv"):
        candidates.append(p)
    if not candidates:
        raise FileNotFoundError(f"could not find xstar_like_element_solver_full_global_matrix_terms.csv under {root}")
    # Prefer a path containing the ion token, then the shortest path.
    candidates.sort(key=lambda p: (ion_tok not in str(p).lower(), len(str(p))))
    return candidates[0]


def _family_key_from_python(row: Mapping[str, Any]) -> str:
    dt = _as_int(row.get("data_type"), None)
    rt = _as_int(row.get("rate_type"), None)
    if dt is None:
        dt = _as_int(row.get("ltyp"), None)
    if rt is None:
        rt = _as_int(row.get("lrtyp"), None)
    src = str(row.get("rate_source") or row.get("source_method") or row.get("source_row_kind") or row.get("full_global_component") or "")
    if dt is not None and rt is not None:
        return f"type{dt}_rate{rt}:{src}"
    if dt is not None:
        return f"type{dt}:{src}"
    return f"unknown:{src}"


def _signed_python_value(row: Mapping[str, Any]) -> float:
    for key in ["full_global_signed_rate_s^-1", "signed_rate_s^-1", "rate_s^-1"]:
        val = _as_float(row.get(key), None)
        if val is not None:
            return float(val)
    return 0.0


def _python_row_is_proxy(row: Mapping[str, Any]) -> bool:
    text = " ".join(str(row.get(k, "")) for k in [
        "source_method", "rate_source", "provenance", "full_global_provenance",
        "source_proxy_basis", "type99_rate_source", "radiation_field_mode",
        "ucalc_context_status", "assembly_status", "full_global_assembly_status",
    ]).lower()
    return any(tok in text for tok in ["proxy", "scaffold", "placeholder", "flat", "xstar-powerlaw", "diagnostic"])


def _load_python_records(matrix_terms_csv: str | Path) -> Tuple[List[Dict[str, Any]], Dict[int, List[Dict[str, Any]]]]:
    rows: List[Dict[str, Any]] = []
    by_record: Dict[int, List[Dict[str, Any]]] = {}
    with Path(matrix_terms_csv).open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rec = _as_int(row.get("record"), None)
            if rec is None or rec <= 0:
                continue
            out = dict(row)
            out["record_int"] = rec
            out["python_signed_rate"] = _signed_python_value(row)
            out["python_abs_rate"] = abs(out["python_signed_rate"])
            out["family_key"] = _family_key_from_python(row)
            out["python_proxy_or_scaffold"] = _python_row_is_proxy(row)
            rows.append(out)
            by_record.setdefault(rec, []).append(out)
    return rows, by_record


def _load_ucalc_occurrences(
    ucalc_probe_csv: str | Path,
    wanted_records: Iterable[int],
) -> Tuple[Dict[int, List[Dict[str, str]]], Dict[int, int]]:
    """Load all ucalc captures for wanted records, preserving capture order.

    XSTAR calls ``ucalc`` many times during a run.  A preserved Python matrix
    corresponds to one local state, so choosing the latest capture for each
    record is not always physically meaningful.  Keeping all occurrences lets
    later audits select a common occurrence rank or scan ranks.
    """

    wanted = set(int(r) for r in wanted_records)
    by_record: Dict[int, List[Dict[str, str]]] = {r: [] for r in wanted}
    with Path(ucalc_probe_csv).open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rec = _as_int(row.get("ml_data"), None)
            if rec not in wanted:
                continue
            by_record.setdefault(rec, []).append(dict(row))
    for rows in by_record.values():
        rows.sort(key=lambda r: _as_int(r.get("capture_index"), -1) or -1)
    counts = {rec: len(rows) for rec, rows in by_record.items()}
    return by_record, counts


def _select_ucalc_rows(
    ucalc_by_record: Mapping[int, Sequence[Mapping[str, str]]],
    *,
    selection: str,
    occurrence_rank: int | None = None,
) -> Dict[int, Dict[str, str]]:
    selected: Dict[int, Dict[str, str]] = {}
    for rec, rows0 in ucalc_by_record.items():
        rows = list(rows0)
        if not rows:
            continue
        if selection == "latest-per-record":
            selected[rec] = dict(rows[-1])
        elif selection == "occurrence-rank":
            rank = occurrence_rank if occurrence_rank is not None else -1
            if rank == 0:
                raise ValueError("occurrence_rank is 1-based; use -1 for latest")
            idx = rank - 1 if rank > 0 else len(rows) + rank
            if 0 <= idx < len(rows):
                selected[rec] = dict(rows[idx])
        else:
            raise ValueError(f"unsupported selection={selection!r}")
    return selected


def _load_matrix_rows_for_selected(matrix_probe_csv: str | Path, selected_ucalc: Mapping[int, Mapping[str, str]]) -> Dict[int, List[Dict[str, str]]]:
    cap_to_rec: Dict[str, int] = {str(row.get("capture_index") or "").strip(): rec for rec, row in selected_ucalc.items()}
    out: Dict[int, List[Dict[str, str]]] = {rec: [] for rec in selected_ucalc}
    with Path(matrix_probe_csv).open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cap = str(row.get("capture_index") or "").strip()
            rec = cap_to_rec.get(cap)
            if rec is None:
                continue
            ml = _as_int(row.get("ml_data"), None)
            if ml != rec:
                continue
            out.setdefault(rec, []).append(dict(row))
    return out


def _load_matrix_rows_for_capture_set(
    matrix_probe_csv: str | Path,
    capture_to_rec: Mapping[str, int],
) -> Dict[str, List[Dict[str, str]]]:
    out: Dict[str, List[Dict[str, str]]] = {cap: [] for cap in capture_to_rec}
    with Path(matrix_probe_csv).open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cap = str(row.get("capture_index") or "").strip()
            rec = capture_to_rec.get(cap)
            if rec is None:
                continue
            ml = _as_int(row.get("ml_data"), None)
            if ml != rec:
                continue
            out.setdefault(cap, []).append(dict(row))
    return out


def _matrix_self_check(ucalc: Mapping[str, Any], matrix_rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    ans1 = _as_float(ucalc.get("ans1"), 0.0) or 0.0
    ans2 = _as_float(ucalc.get("ans2"), 0.0) or 0.0
    expected = {
        "forward_offdiag": ans1,
        "reverse_offdiag": ans2,
        "forward_diag_loss": -ans1,
        "reverse_diag_loss": -ans2,
    }
    n = 0
    n_match = 0
    max_abs_diff = 0.0
    for row in matrix_rows:
        kind = str(row.get("insertion_kind") or "")
        if kind not in expected:
            continue
        obs = _as_float(row.get("ajisi_1"), None)
        if obs is None:
            continue
        exp = expected[kind]
        diff = abs(obs - exp)
        max_abs_diff = max(max_abs_diff, diff)
        scale = max(1.0, abs(obs), abs(exp))
        if diff <= 1.0e-8 * scale:
            n_match += 1
        n += 1
    return {
        "fortran_matrix_self_check_rows": n,
        "fortran_matrix_self_check_matches": n_match,
        "fortran_matrix_self_check_max_abs_diff": max_abs_diff,
        "fortran_matrix_self_check_status": "pass" if n > 0 and n == n_match else "differs" if n > 0 else "no_rows",
    }


def _median(values: Sequence[float]) -> float | None:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    if not vals:
        return None
    return float(statistics.median(vals))


def _record_summary_row(
    rec: int,
    py_rows: Sequence[Mapping[str, Any]],
    ucalc: Mapping[str, str] | None,
    matrix_rows: Sequence[Mapping[str, str]],
    ucalc_count: int,
) -> Dict[str, Any]:
    py_signed = [float(r.get("python_signed_rate") or 0.0) for r in py_rows]
    py_abs_sum = sum(abs(v) for v in py_signed)
    py_signed_sum = sum(py_signed)
    f_signed = [_as_float(r.get("ajisi_1"), 0.0) or 0.0 for r in matrix_rows]
    f_abs_sum = sum(abs(v) for v in f_signed)
    f_signed_sum = sum(f_signed)
    ratio = py_abs_sum / f_abs_sum if f_abs_sum > 0 else None
    ans1 = _as_float(ucalc.get("ans1") if ucalc else None, None)
    ans2 = _as_float(ucalc.get("ans2") if ucalc else None, None)
    family = py_rows[0].get("family_key", "unknown") if py_rows else "unknown"
    proxy = any(bool(r.get("python_proxy_or_scaffold")) for r in py_rows)
    self_check = _matrix_self_check(ucalc or {}, matrix_rows)
    if ucalc is None:
        status = "no_fortran_ucalc_for_python_record"
    elif len(matrix_rows) == 0:
        status = "fortran_ucalc_without_selected_matrix_rows"
    elif ratio is None:
        status = "fortran_zero_abs_sum"
    elif 0.999 <= ratio <= 1.001:
        status = "python_fortran_abs_sum_match_0p1pct"
    elif 0.99 <= ratio <= 1.01:
        status = "python_fortran_abs_sum_match_1pct"
    elif 0.9 <= ratio <= 1.1:
        status = "python_fortran_abs_sum_match_10pct"
    else:
        status = "python_fortran_abs_sum_differs"
    return {
        "record": rec,
        "family_key": family,
        "python_proxy_or_scaffold": proxy,
        "python_n_terms": len(py_rows),
        "fortran_ucalc_seen_count": ucalc_count,
        "selected_capture_index": ucalc.get("capture_index", "") if ucalc else "",
        "ltyp": ucalc.get("ltyp", "") if ucalc else _as_int(py_rows[0].get("data_type"), "") if py_rows else "",
        "lrtyp": ucalc.get("lrtyp", "") if ucalc else _as_int(py_rows[0].get("rate_type"), "") if py_rows else "",
        "jkk_ion": ucalc.get("jkk_ion", "") if ucalc else "",
        "idest1": ucalc.get("idest1", "") if ucalc else "",
        "idest2": ucalc.get("idest2", "") if ucalc else "",
        "ans1": ans1 if ans1 is not None else "",
        "ans2": ans2 if ans2 is not None else "",
        "fortran_n_matrix_rows": len(matrix_rows),
        "python_signed_sum_s^-1": py_signed_sum,
        "fortran_ajisi1_signed_sum_s^-1": f_signed_sum,
        "python_abs_sum_s^-1": py_abs_sum,
        "fortran_ajisi1_abs_sum_s^-1": f_abs_sum,
        "python_over_fortran_abs_sum": ratio if ratio is not None else "",
        **self_check,
        "record_parity_status": status,
    }


def _family_summary(record_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Mapping[str, Any]]] = {}
    for r in record_rows:
        groups.setdefault(str(r.get("family_key") or "unknown"), []).append(r)
    out: List[Dict[str, Any]] = []
    for fam, rows in sorted(groups.items()):
        ratios = [_as_float(r.get("python_over_fortran_abs_sum"), None) for r in rows]
        ratios_f = [r for r in ratios if r is not None and math.isfinite(r)]
        statuses: Dict[str, int] = {}
        for r in rows:
            st = str(r.get("record_parity_status") or "")
            statuses[st] = statuses.get(st, 0) + 1
        out.append({
            "family_key": fam,
            "n_records": len(rows),
            "n_python_proxy_or_scaffold_records": sum(1 for r in rows if str(r.get("python_proxy_or_scaffold")).lower() == "true"),
            "n_records_with_fortran_ucalc": sum(1 for r in rows if str(r.get("selected_capture_index") or "")),
            "n_records_with_four_fortran_rows": sum(1 for r in rows if _as_int(r.get("fortran_n_matrix_rows"), 0) == 4),
            "median_python_over_fortran_abs_sum": _median(ratios_f),
            "min_python_over_fortran_abs_sum": min(ratios_f) if ratios_f else "",
            "max_python_over_fortran_abs_sum": max(ratios_f) if ratios_f else "",
            "n_abs_sum_differs": sum(1 for r in rows if r.get("record_parity_status") == "python_fortran_abs_sum_differs"),
            "status_counts": json.dumps(statuses, sort_keys=True),
        })
    return out


def _make_record_rows_for_selection(
    *,
    py_by_record: Mapping[int, Sequence[Mapping[str, Any]]],
    ucalc_by_record: Mapping[int, Sequence[Mapping[str, str]]],
    ucalc_counts: Mapping[int, int],
    matrix_probe_csv: str | Path,
    selection: str,
    occurrence_rank: int | None,
) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, str]]]:
    wanted = set(py_by_record.keys())
    selected_ucalc = _select_ucalc_rows(
        ucalc_by_record, selection=selection, occurrence_rank=occurrence_rank
    )
    selected_matrix = _load_matrix_rows_for_selected(matrix_probe_csv, selected_ucalc)
    record_rows = [
        _record_summary_row(
            rec,
            py_by_record.get(rec, []),
            selected_ucalc.get(rec),
            selected_matrix.get(rec, []),
            ucalc_counts.get(rec, 0),
        )
        for rec in sorted(wanted)
    ]
    return record_rows, selected_ucalc


def _selection_summary_stats(record_rows: Sequence[Mapping[str, Any]], wanted: set[int], selected_ucalc: Mapping[int, Mapping[str, str]]) -> Dict[str, Any]:
    ready_records = sum(1 for r in record_rows if _as_int(r.get("fortran_n_matrix_rows"), 0) == 4)
    n_self_pass = sum(1 for r in record_rows if r.get("fortran_matrix_self_check_status") == "pass")
    ratios = [_as_float(r.get("python_over_fortran_abs_sum"), None) for r in record_rows]
    ratios_f = [r for r in ratios if r is not None and math.isfinite(r)]
    log_abs = [abs(math.log10(r)) for r in ratios_f if r > 0]
    n_match_1pct = sum(1 for r in record_rows if r.get("record_parity_status") in (
        "python_fortran_abs_sum_match_0p1pct", "python_fortran_abs_sum_match_1pct"
    ))
    n_diff = sum(1 for r in record_rows if r.get("record_parity_status") == "python_fortran_abs_sum_differs")
    return {
        "n_python_records_with_fortran_ucalc": len(selected_ucalc),
        "n_python_records_without_fortran_ucalc": len(wanted - set(selected_ucalc.keys())),
        "n_python_records_with_selected_four_fortran_rows": ready_records,
        "n_python_records_without_selected_four_fortran_rows": len(wanted) - ready_records,
        "n_fortran_self_check_pass_records": n_self_pass,
        "n_fortran_self_check_nonpass_records": len(record_rows) - n_self_pass,
        "median_python_over_fortran_abs_sum": _median(ratios_f),
        "median_abs_log10_python_over_fortran_abs_sum": _median(log_abs),
        "n_match_1pct_or_better": n_match_1pct,
        "n_abs_sum_differs": n_diff,
    }


def scan_occurrence_rank_matrix_parity(
    *,
    benchmark_dir: str | Path,
    ion: str,
    ucalc_probe_csv: str | Path,
    matrix_probe_csv: str | Path,
    matrix_terms_csv: str | Path | None = None,
    max_occurrence_rank: int | None = None,
) -> List[Dict[str, Any]]:
    """Scan common ucalc occurrence ranks and rank local-state matches.

    This is meant for full XSTAR probes that contain many zones/passes.  It
    helps identify which Fortran epoch corresponds to the preserved Python
    local matrix before interpreting family-level rate differences.
    """

    matrix_terms_path = Path(matrix_terms_csv) if matrix_terms_csv else _find_python_matrix_terms_csv(benchmark_dir, ion)
    _py_rows, py_by_record = _load_python_records(matrix_terms_path)
    wanted = set(py_by_record.keys())
    ucalc_by_record, ucalc_counts = _load_ucalc_occurrences(ucalc_probe_csv, wanted)
    positive_counts = [c for c in ucalc_counts.values() if c > 0]
    if not positive_counts:
        return []
    max_rank = min(positive_counts)
    if max_occurrence_rank is not None and max_occurrence_rank > 0:
        max_rank = min(max_rank, int(max_occurrence_rank))
    rows: List[Dict[str, Any]] = []
    for rank in range(1, max_rank + 1):
        selected_ucalc = _select_ucalc_rows(ucalc_by_record, selection="occurrence-rank", occurrence_rank=rank)
        selected_matrix = _load_matrix_rows_for_selected(matrix_probe_csv, selected_ucalc)
        record_rows = [
            _record_summary_row(
                rec, py_by_record.get(rec, []), selected_ucalc.get(rec),
                selected_matrix.get(rec, []), ucalc_counts.get(rec, 0)
            )
            for rec in sorted(wanted)
        ]
        stats = _selection_summary_stats(record_rows, wanted, selected_ucalc)
        rows.append({
            "occurrence_rank": rank,
            **stats,
        })
    def _scan_sort_key(row: Mapping[str, Any]) -> Tuple[float, int]:
        metric = _as_float(row.get("median_abs_log10_python_over_fortran_abs_sum"), None)
        if metric is None:
            metric = float("inf")
        return (float(metric), -(_as_int(row.get("n_match_1pct_or_better"), 0) or 0))

    rows.sort(key=_scan_sort_key)
    for i, row in enumerate(rows, start=1):
        row["scan_rank_by_median_abs_log10_ratio"] = i
    rows.sort(key=lambda r: _as_int(r.get("occurrence_rank"), 0) or 0)
    return rows


def audit_record_level_matrix_parity(
    *,
    benchmark_dir: str | Path,
    ion: str,
    ucalc_probe_csv: str | Path,
    matrix_probe_csv: str | Path,
    matrix_terms_csv: str | Path | None = None,
    selection: str = "latest-per-record",
    occurrence_rank: int | None = None,
    scan_occurrence_ranks: bool = False,
    max_occurrence_rank: int | None = None,
) -> Dict[str, Any]:
    if selection not in {"latest-per-record", "occurrence-rank"}:
        raise ValueError("selection must be 'latest-per-record' or 'occurrence-rank'")
    matrix_terms_path = Path(matrix_terms_csv) if matrix_terms_csv else _find_python_matrix_terms_csv(benchmark_dir, ion)
    py_rows, py_by_record = _load_python_records(matrix_terms_path)
    wanted = set(py_by_record.keys())
    ucalc_by_record, ucalc_counts = _load_ucalc_occurrences(ucalc_probe_csv, wanted)
    record_rows, selected_ucalc = _make_record_rows_for_selection(
        py_by_record=py_by_record,
        ucalc_by_record=ucalc_by_record,
        ucalc_counts=ucalc_counts,
        matrix_probe_csv=matrix_probe_csv,
        selection=selection,
        occurrence_rank=occurrence_rank,
    )
    family_rows = _family_summary(record_rows)
    stats = _selection_summary_stats(record_rows, wanted, selected_ucalc)
    scan_rows: List[Dict[str, Any]] = []
    if scan_occurrence_ranks:
        scan_rows = scan_occurrence_rank_matrix_parity(
            benchmark_dir=benchmark_dir,
            ion=ion,
            ucalc_probe_csv=ucalc_probe_csv,
            matrix_probe_csv=matrix_probe_csv,
            matrix_terms_csv=matrix_terms_path,
            max_occurrence_rank=max_occurrence_rank,
        )
    best_scan = min(
        scan_rows,
        key=lambda r: _as_int(r.get("scan_rank_by_median_abs_log10_ratio"), 10**9) or 10**9,
        default={},
    )
    summary = {
        "audit_version": "v0.3.182",
        "ion": ion,
        "status": "record_level_matrix_parity_audit_completed",
        "selection": selection,
        "occurrence_rank": occurrence_rank if occurrence_rank is not None else "",
        "scan_occurrence_ranks": bool(scan_occurrence_ranks),
        "best_occurrence_rank_by_scan": best_scan.get("occurrence_rank", ""),
        "best_scan_median_abs_log10_ratio": best_scan.get("median_abs_log10_python_over_fortran_abs_sum", ""),
        "python_matrix_terms_csv": str(matrix_terms_path),
        "ucalc_probe_csv": str(ucalc_probe_csv),
        "matrix_probe_csv": str(matrix_probe_csv),
        "n_python_matrix_terms_with_record": len(py_rows),
        "n_python_records": len(wanted),
        **stats,
        "n_family_rows": len(family_rows),
        "n_python_proxy_or_scaffold_records": sum(1 for r in record_rows if str(r.get("python_proxy_or_scaffold")).lower() == "true"),
        "record_level_source_equivalent_ready": (
            len(wanted) > 0
            and stats["n_python_records_without_fortran_ucalc"] == 0
            and stats["n_python_records_with_selected_four_fortran_rows"] == len(wanted)
            and stats["n_fortran_self_check_pass_records"] == len(wanted)
            and all(str(r.get("record_parity_status", "")).startswith("python_fortran_abs_sum_match") for r in record_rows)
        ),
    }
    return {"summary": summary, "record_rows": record_rows, "family_rows": family_rows, "occurrence_scan_rows": scan_rows}


def write_record_level_matrix_parity_audit(
    *,
    out_dir: str | Path,
    audit: Mapping[str, Any],
) -> Dict[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "record_summary_csv": out / "xstar_record_level_matrix_parity_audit_records.csv",
        "family_summary_csv": out / "xstar_record_level_matrix_parity_audit_family_summary.csv",
        "occurrence_scan_csv": out / "xstar_record_level_matrix_parity_audit_occurrence_scan.csv",
        "json": out / "xstar_record_level_matrix_parity_audit.json",
        "markdown": out / "xstar_record_level_matrix_parity_audit.md",
    }
    record_rows = list(audit.get("record_rows", []))
    family_rows = list(audit.get("family_rows", []))
    occurrence_scan_rows = list(audit.get("occurrence_scan_rows", []))
    summary = dict(audit.get("summary", {}))
    _write_csv(paths["record_summary_csv"], record_rows)
    _write_csv(paths["family_summary_csv"], family_rows)
    _write_csv(paths["occurrence_scan_csv"], occurrence_scan_rows)
    payload = {"summary": summary, "record_rows": record_rows, "family_rows": family_rows, "occurrence_scan_rows": occurrence_scan_rows}
    paths["json"].write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# XSTAR record-level local matrix parity audit",
        "",
        f"- audit_version: `{summary.get('audit_version')}`",
        f"- ion: `{summary.get('ion')}`",
        f"- status: `{summary.get('status')}`",
        f"- selection: `{summary.get('selection')}`",
        f"- occurrence_rank: `{summary.get('occurrence_rank')}`",
        f"- scan_occurrence_ranks: `{summary.get('scan_occurrence_ranks')}`",
        f"- best_occurrence_rank_by_scan: `{summary.get('best_occurrence_rank_by_scan')}`",
        f"- best_scan_median_abs_log10_ratio: `{summary.get('best_scan_median_abs_log10_ratio')}`",
        f"- Python records: `{summary.get('n_python_records')}`",
        f"- records with selected Fortran ucalc: `{summary.get('n_python_records_with_fortran_ucalc')}`",
        f"- records with four selected Fortran matrix rows: `{summary.get('n_python_records_with_selected_four_fortran_rows')}`",
        f"- Fortran self-check pass records: `{summary.get('n_fortran_self_check_pass_records')}`",
        f"- median Python/Fortran abs-sum: `{summary.get('median_python_over_fortran_abs_sum')}`",
        f"- record-level source-equivalent ready: `{summary.get('record_level_source_equivalent_ready')}`",
        "",
        "This is a diagnostic audit.  The default selection keeps legacy `latest-per-record` behavior, but v0.3.182 can also select a common `occurrence-rank` and scan occurrence ranks across a full XSTAR run to locate the Fortran local-state epoch that best matches the preserved Python matrix before interpreting family-level mismatches.",
    ]
    paths["markdown"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {k: str(v) for k, v in paths.items()}
