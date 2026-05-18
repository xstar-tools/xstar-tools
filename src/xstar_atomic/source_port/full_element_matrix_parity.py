"""Record-level parity for the complete source-ported element matrix.

This diagnostic joins the existing instrumented XSTAR ``ucalc`` and
``calc_hmc_ion`` probe products to the native Python ``ElementMatrixAssembly``.
It never substitutes probed rates into the production solve.  Its purpose is to
identify the first remaining rate family or packed-record translation that
prevents condensed-matrix and population parity.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import csv
import json
import math

from .element_equilibrium import ElementMatrixAssembly, MatrixTerm


class FullElementMatrixParityError(RuntimeError):
    """Raised when the record-level XSTAR probe products are inconsistent."""


@dataclass(frozen=True)
class MatrixFamilyParityMetrics:
    data_type: int
    rate_type: int
    n_python_terms: int
    n_xstar_terms: int
    n_matched_terms: int
    n_python_only_terms: int
    n_xstar_only_terms: int
    n_terms_outside_tolerance: int
    max_abs_aj1_difference: float
    max_abs_aj2_difference: float
    l1_aj1_difference: float
    l1_aj2_difference: float
    max_active_relative_difference: float
    ready: bool


@dataclass
class FullElementMatrixParityResult:
    source_ucalc_csv: str
    source_matrix_csv: str
    selection: str
    n_selected_ucalc_records: int
    n_selected_xstar_terms: int
    n_python_terms: int
    n_matched_terms: int
    n_python_only_terms: int
    n_xstar_only_terms: int
    n_terms_outside_tolerance: int
    family_metrics: List[MatrixFamilyParityMetrics]
    detail_rows: List[Dict[str, Any]]
    full_element_matrix_parity_ready: bool
    first_failing_data_type: int
    first_failing_rate_type: int
    diagnosis: str
    absolute_tolerance: float
    relative_tolerance: float
    relative_floor: float


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or str(value).strip() == "":
            return default
        number = float(value)
        return int(round(number)) if math.isfinite(number) else default
    except Exception:
        return default


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _read_csv(path: str | Path) -> List[Dict[str, str]]:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(str(target))
    with target.open("r", newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _capture_number(row: Mapping[str, Any]) -> int:
    return _as_int(row.get("capture_index"), -1) or -1


def _term_key(record: int, role: str, row: int, column: int) -> Tuple[int, str, int, int]:
    return int(record), str(role).strip(), int(row), int(column)


def _select_latest_ucalc_rows(
    assembly: ElementMatrixAssembly,
    ucalc_probe_csv: str | Path,
) -> Dict[Tuple[int, int], Dict[str, str]]:
    """Stream the ucalc probe and retain only active-ion latest captures."""
    blocks = {int(block.ion_index): block for block in assembly.basis.blocks}
    selected: Dict[Tuple[int, int], Dict[str, str]] = {}
    target = Path(ucalc_probe_csv)
    if not target.is_file():
        raise FileNotFoundError(str(target))
    n_rows = 0
    with target.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            n_rows += 1
            ion = _as_int(row.get("jkk_ion"), None)
            record = _as_int(row.get("ml_data"), None)
            if ion not in blocks or record is None:
                continue
            key = int(ion), int(record)
            prior = selected.get(key)
            if prior is None or _capture_number(row) > _capture_number(prior):
                selected[key] = dict(row)
    if n_rows == 0:
        raise FullElementMatrixParityError("ucalc probe CSV contains no rows")
    if not selected:
        raise FullElementMatrixParityError(
            "ucalc probe contains no rows for the active element ion blocks"
        )
    return selected


def _probe_term_rows(
    assembly: ElementMatrixAssembly,
    selected_ucalc: Mapping[Tuple[int, int], Mapping[str, str]],
    matrix_probe_csv: str | Path,
) -> List[Dict[str, Any]]:
    """Stream selected XSTAR matrix rows and map local endpoints to compact rows."""
    blocks = {int(block.ion_index): block for block in assembly.basis.blocks}
    selected_by_capture: Dict[Tuple[int, int], Tuple[int, Mapping[str, str]]] = {}
    for (ion, record), row in selected_ucalc.items():
        selected_by_capture[(_capture_number(row), int(record))] = (int(ion), row)

    target = Path(matrix_probe_csv)
    if not target.is_file():
        raise FileNotFoundError(str(target))
    out: List[Dict[str, Any]] = []
    n_rows = 0
    with target.open("r", newline="", encoding="utf-8") as handle:
        for mrow in csv.DictReader(handle):
            n_rows += 1
            capture = _as_int(mrow.get("capture_index"), None)
            record = _as_int(mrow.get("ml_data"), None)
            if capture is None or record is None:
                continue
            selected = selected_by_capture.get((int(capture), int(record)))
            if selected is None:
                continue
            ion, urow = selected
            block = blocks[ion]
            local_row = _as_int(mrow.get("indbi_1"), None)
            local_col = _as_int(mrow.get("indbi_2"), None)
            if local_row is None or local_col is None:
                raise FullElementMatrixParityError(
                    f"matrix probe row for record {record} lacks indbi_1/indbi_2"
                )
            raw_row = block.compact_start + int(local_row) - 1
            raw_col = block.compact_start + int(local_col) - 1
            compact_row = min(assembly.basis.n_rows, raw_row)
            compact_col = min(assembly.basis.n_rows, raw_col)
            out.append(
                {
                    "record": int(record),
                    "capture_index": int(capture),
                    "ion_index": ion,
                    "ion_stage": block.ion_stage,
                    "data_type": _as_int(mrow.get("ltyp"), _as_int(urow.get("ltyp"), 0)) or 0,
                    "rate_type": _as_int(mrow.get("lrtyp"), _as_int(urow.get("lrtyp"), 0)) or 0,
                    "role": str(mrow.get("insertion_kind") or "").strip(),
                    "row": compact_row,
                    "column": compact_col,
                    "source_row_unclamped": raw_row,
                    "source_column_unclamped": raw_col,
                    "source_ipmat_clamped": raw_row != compact_row or raw_col != compact_col,
                    "aj1": _as_float(mrow.get("ajisi_1"), 0.0) or 0.0,
                    "aj2": _as_float(mrow.get("ajisi_2"), 0.0) or 0.0,
                    "cj": _as_float(mrow.get("cjisi"), 0.0) or 0.0,
                    "cj2": _as_float(mrow.get("cjisi2"), 0.0) or 0.0,
                    "idest1": _as_int(mrow.get("idest1"), _as_int(urow.get("idest1"), 0)) or 0,
                    "idest2": _as_int(mrow.get("idest2"), _as_int(urow.get("idest2"), 0)) or 0,
                }
            )
    if n_rows == 0:
        raise FullElementMatrixParityError("matrix probe CSV contains no rows")
    return out

def _python_term_row(term: MatrixTerm) -> Dict[str, Any]:
    return {
        "record": int(term.record),
        "ion_index": int(term.ion_index),
        "ion_stage": int(term.ion_stage),
        "data_type": int(term.data_type),
        "rate_type": int(term.rate_type),
        "role": str(term.role),
        "row": int(term.row),
        "column": int(term.column),
        "source_row_unclamped": int(term.source_row_unclamped),
        "source_column_unclamped": int(term.source_column_unclamped),
        "source_ipmat_clamped": bool(term.source_ipmat_clamped),
        "aj1": float(term.aj1),
        "aj2": float(term.aj2),
        "cj": float(term.cj),
        "cj2": float(term.cj2),
        "idest1": int(term.idest1),
        "idest2": int(term.idest2),
    }


def compare_full_element_matrix_probe(
    assembly: ElementMatrixAssembly,
    ucalc_probe_csv: str | Path,
    matrix_probe_csv: str | Path,
    *,
    absolute_tolerance: float = 1.0e-10,
    relative_tolerance: float = 5.0e-5,
    relative_floor: float = 1.0e-30,
) -> FullElementMatrixParityResult:
    """Compare the complete native matrix term manifest with XSTAR probes."""
    selected_ucalc = _select_latest_ucalc_rows(assembly, ucalc_probe_csv)
    xstar_terms = _probe_term_rows(assembly, selected_ucalc, matrix_probe_csv)
    n_selected_records = len(selected_ucalc)
    python_terms = [_python_term_row(term) for term in assembly.terms]

    x_by_key: Dict[Tuple[int, str, int, int], List[Dict[str, Any]]] = {}
    p_by_key: Dict[Tuple[int, str, int, int], List[Dict[str, Any]]] = {}
    for row in xstar_terms:
        x_by_key.setdefault(_term_key(row["record"], row["role"], row["row"], row["column"]), []).append(row)
    for row in python_terms:
        p_by_key.setdefault(_term_key(row["record"], row["role"], row["row"], row["column"]), []).append(row)

    details: List[Dict[str, Any]] = []
    all_keys = sorted(set(x_by_key) | set(p_by_key))
    for key in all_keys:
        xrows = x_by_key.get(key, [])
        prows = p_by_key.get(key, [])
        count = max(len(xrows), len(prows))
        for occurrence in range(count):
            xrow = xrows[occurrence] if occurrence < len(xrows) else None
            prow = prows[occurrence] if occurrence < len(prows) else None
            source = xrow or prow or {}
            status = "matched" if xrow is not None and prow is not None else ("xstar_only" if xrow is not None else "python_only")
            xaj1 = None if xrow is None else float(xrow["aj1"])
            xaj2 = None if xrow is None else float(xrow["aj2"])
            paj1 = None if prow is None else float(prow["aj1"])
            paj2 = None if prow is None else float(prow["aj2"])
            if status == "matched":
                d1 = abs(paj1 - xaj1)
                d2 = abs(paj2 - xaj2)
                active1 = abs(xaj1) > relative_floor
                active2 = abs(xaj2) > relative_floor
                r1 = d1 / abs(xaj1) if active1 else 0.0
                r2 = d2 / abs(xaj2) if active2 else 0.0
                t1 = absolute_tolerance + relative_tolerance * abs(xaj1)
                t2 = absolute_tolerance + relative_tolerance * abs(xaj2)
                within = d1 <= t1 and d2 <= t2
            else:
                d1 = abs((paj1 or 0.0) - (xaj1 or 0.0))
                d2 = abs((paj2 or 0.0) - (xaj2 or 0.0))
                r1 = r2 = math.inf
                within = False
            details.append(
                {
                    "record": key[0],
                    "role": key[1],
                    "row": key[2],
                    "column": key[3],
                    "occurrence": occurrence + 1,
                    "status": status,
                    "data_type": int(source.get("data_type", 0)),
                    "rate_type": int(source.get("rate_type", 0)),
                    "ion_index": int(source.get("ion_index", 0)),
                    "ion_stage": int(source.get("ion_stage", 0)),
                    "xstar_aj1": xaj1,
                    "python_aj1": paj1,
                    "aj1_absolute_difference": d1,
                    "aj1_relative_difference": r1,
                    "xstar_aj2": xaj2,
                    "python_aj2": paj2,
                    "aj2_absolute_difference": d2,
                    "aj2_relative_difference": r2,
                    "within_tolerance": within,
                    "xstar_idest1": None if xrow is None else xrow.get("idest1"),
                    "xstar_idest2": None if xrow is None else xrow.get("idest2"),
                    "python_idest1": None if prow is None else prow.get("idest1"),
                    "python_idest2": None if prow is None else prow.get("idest2"),
                    "xstar_source_row_unclamped": None if xrow is None else xrow.get("source_row_unclamped"),
                    "xstar_source_column_unclamped": None if xrow is None else xrow.get("source_column_unclamped"),
                    "python_source_row_unclamped": None if prow is None else prow.get("source_row_unclamped"),
                    "python_source_column_unclamped": None if prow is None else prow.get("source_column_unclamped"),
                }
            )

    families: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for row in details:
        families.setdefault((int(row["data_type"]), int(row["rate_type"])), []).append(row)
    family_metrics: List[MatrixFamilyParityMetrics] = []
    for (data_type, rate_type), rows in sorted(families.items()):
        matched = [row for row in rows if row["status"] == "matched"]
        active_rel: List[float] = []
        for row in matched:
            for key in ("aj1_relative_difference", "aj2_relative_difference"):
                value = float(row[key])
                if math.isfinite(value):
                    active_rel.append(value)
        n_py = sum(row["status"] in {"matched", "python_only"} for row in rows)
        n_x = sum(row["status"] in {"matched", "xstar_only"} for row in rows)
        n_bad = sum(not bool(row["within_tolerance"]) for row in rows)
        family_metrics.append(
            MatrixFamilyParityMetrics(
                data_type=data_type,
                rate_type=rate_type,
                n_python_terms=n_py,
                n_xstar_terms=n_x,
                n_matched_terms=len(matched),
                n_python_only_terms=sum(row["status"] == "python_only" for row in rows),
                n_xstar_only_terms=sum(row["status"] == "xstar_only" for row in rows),
                n_terms_outside_tolerance=n_bad,
                max_abs_aj1_difference=max((float(row["aj1_absolute_difference"]) for row in rows), default=0.0),
                max_abs_aj2_difference=max((float(row["aj2_absolute_difference"]) for row in rows), default=0.0),
                l1_aj1_difference=sum(float(row["aj1_absolute_difference"]) for row in rows),
                l1_aj2_difference=sum(float(row["aj2_absolute_difference"]) for row in rows),
                max_active_relative_difference=max(active_rel) if active_rel else 0.0,
                ready=n_bad == 0,
            )
        )

    failing = [metric for metric in family_metrics if not metric.ready]
    # Rank the first target by total absolute rate disagreement rather than by
    # numerical data-type order.
    failing.sort(
        key=lambda metric: (
            -(metric.l1_aj1_difference + metric.l1_aj2_difference),
            metric.data_type,
            metric.rate_type,
        )
    )
    first = failing[0] if failing else None
    n_py_only = sum(row["status"] == "python_only" for row in details)
    n_x_only = sum(row["status"] == "xstar_only" for row in details)
    n_bad = sum(not bool(row["within_tolerance"]) for row in details)
    ready = n_bad == 0
    diagnosis = (
        "full_element_record_matrix_parity_reproduced"
        if ready
        else f"resolve_native_type{first.data_type}_rate{first.rate_type}_matrix_parity"
    )
    return FullElementMatrixParityResult(
        source_ucalc_csv=str(Path(ucalc_probe_csv)),
        source_matrix_csv=str(Path(matrix_probe_csv)),
        selection="latest-per-record-within-selected-element-ion-blocks",
        n_selected_ucalc_records=n_selected_records,
        n_selected_xstar_terms=len(xstar_terms),
        n_python_terms=len(python_terms),
        n_matched_terms=sum(row["status"] == "matched" for row in details),
        n_python_only_terms=n_py_only,
        n_xstar_only_terms=n_x_only,
        n_terms_outside_tolerance=n_bad,
        family_metrics=family_metrics,
        detail_rows=details,
        full_element_matrix_parity_ready=ready,
        first_failing_data_type=0 if first is None else first.data_type,
        first_failing_rate_type=0 if first is None else first.rate_type,
        diagnosis=diagnosis,
        absolute_tolerance=float(absolute_tolerance),
        relative_tolerance=float(relative_tolerance),
        relative_floor=float(relative_floor),
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(str(key))
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or ["status"], extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_full_element_matrix_parity_products(
    result: FullElementMatrixParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.13",
) -> Dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    details_csv = out / "xstar_full_element_matrix_parity_details.csv"
    families_csv = out / "xstar_full_element_matrix_parity_families.csv"
    _write_csv(details_csv, result.detail_rows)
    _write_csv(families_csv, [metric.__dict__ for metric in result.family_metrics])
    summary = {
        "port_version": port_version,
        "status": "full_element_record_matrix_parity_completed",
        "source_ucalc_csv": result.source_ucalc_csv,
        "source_matrix_csv": result.source_matrix_csv,
        "selection": result.selection,
        "n_selected_ucalc_records": result.n_selected_ucalc_records,
        "n_selected_xstar_terms": result.n_selected_xstar_terms,
        "n_python_terms": result.n_python_terms,
        "n_matched_terms": result.n_matched_terms,
        "n_python_only_terms": result.n_python_only_terms,
        "n_xstar_only_terms": result.n_xstar_only_terms,
        "n_terms_outside_tolerance": result.n_terms_outside_tolerance,
        "full_element_matrix_parity_ready": result.full_element_matrix_parity_ready,
        "first_failing_data_type": result.first_failing_data_type,
        "first_failing_rate_type": result.first_failing_rate_type,
        "diagnosis": result.diagnosis,
        "absolute_tolerance": result.absolute_tolerance,
        "relative_tolerance": result.relative_tolerance,
        "relative_floor": result.relative_floor,
        "family_metrics": [metric.__dict__ for metric in result.family_metrics],
    }
    json_path = out / "xstar_full_element_matrix_parity_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path = out / "xstar_full_element_matrix_parity_summary.md"
    markdown_path.write_text(
        "\n".join(
            [
                "# XSTAR/Python full-element record matrix parity",
                "",
                f"- Port version: `{port_version}`",
                f"- Selection: `{result.selection}`",
                f"- XSTAR terms: `{result.n_selected_xstar_terms}`",
                f"- Python terms: `{result.n_python_terms}`",
                f"- Matched terms: `{result.n_matched_terms}`",
                f"- Python-only terms: `{result.n_python_only_terms}`",
                f"- XSTAR-only terms: `{result.n_xstar_only_terms}`",
                f"- Terms outside tolerance: `{result.n_terms_outside_tolerance}`",
                f"- Matrix parity ready: `{result.full_element_matrix_parity_ready}`",
                f"- First failing family: `type {result.first_failing_data_type}, rate {result.first_failing_rate_type}`",
                f"- Diagnosis: `{result.diagnosis}`",
                "",
                "The probe coefficients are comparison-only and are never inserted into the production solve.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "full_element_matrix_parity_details_csv": details_csv,
        "full_element_matrix_parity_families_csv": families_csv,
        "full_element_matrix_parity_json": json_path,
        "full_element_matrix_parity_markdown": markdown_path,
    }
