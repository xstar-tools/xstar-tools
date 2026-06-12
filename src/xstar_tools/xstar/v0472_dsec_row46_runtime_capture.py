"""Capture the complete v0.6.47.2 DSEC source-order contract incident on He II row 46.

The capture runs the untouched, hash-verified v0.6.47.2 Python backend in an
isolated subprocess.  An observational monkeypatch records every evaluated
record whose committed helium matrix terms touch full row 46, together with
escape-probability inputs, population-dependent state, source insertion order,
and the pre/post-normalization linear-system rows.

The probe is qualification-only and does not modify rates, matrices,
populations, controller decisions, or products.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

RELEASE = "0.6.48.7.14"
SCHEMA = "xstar-tools-v0648714-v0472-dsec-row46-runtime-capture-v1"
BUNDLE_SCHEMA = "xstar-tools-v0648714-row46-dsec-runtime-oracle-v1"
SOURCE_ARCHIVE_SHA256 = "85ff0184bd95daf046fd28923837239c5192f8d309b0716556d1d804b0453060"
TARGET_EVALUATION = 61
TARGET_FULL_ROW = 46
TARGET_RECORDS = 155
TARGET_MATRIX_TERMS = TARGET_RECORDS * 4
TARGET_TYPE_COUNTS = {50: 9, 53: 44, 56: 8, 57: 44, 71: 1, 74: 42, 76: 1, 77: 1, 95: 3, 99: 2}

RECORDS_NAME = "heii_row46_dsec_runtime_records.csv"
TERMS_NAME = "heii_row46_dsec_runtime_matrix_terms.csv"
SOLVE_ROWS_NAME = "heii_row46_dsec_solve_rows.csv"
ROW46_MATRIX_NAME = "heii_row46_dsec_matrix_row.csv"
NORMALIZATION_NAME = "heii_row46_dsec_normalization_row.csv"
TRACE_NAME = "dsec_evaluation_trace.csv"
REPORT_NAME = "capture_report.json"
MANIFEST_NAME = "reference_manifest.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            target = (root / member.name).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"unsafe source member: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"source archive contains link: {member.name}")
        tar.extractall(root, filter="fully_trusted")


def source_root(destination: Path) -> Path:
    roots = [p.parent for p in destination.glob("*/pyproject.toml")]
    if len(roots) != 1:
        raise ValueError(f"expected one extracted source root, found {len(roots)}")
    return roots[0]


def _load_target_inventory(lowered_program: Path) -> list[dict[str, Any]]:
    """Load every helium record so the runtime term stream can define row 46.

    The complete contributor set cannot be inferred from records whose lowered
    endpoints literally equal 46 because compact-basis aliasing maps many He I
    continuum records onto the first He II row.  The observational probe
    therefore watches all helium records and freezes only records whose actual
    committed terms touch compact row 46.
    """
    path = lowered_program / "records.csv"
    if not path.is_file():
        raise FileNotFoundError(f"missing lowered records: {path}")
    rows: list[dict[str, Any]] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                element_index = int(row.get("element_index", -1))
            except (TypeError, ValueError):
                continue
            if element_index != 1:
                continue
            rows.append(
                {
                    "record": int(row["record"]),
                    "source_position": int(row["source_position"]),
                    "data_type": int(row["data_type"]),
                    "rate_type": int(row["rate_type"]),
                    "ion_stage": int(row["ion_stage"]),
                    "lower_row": int(row["lower_row"]),
                    "upper_row": int(row["upper_row"]),
                }
            )
    rows.sort(key=lambda item: item["source_position"])
    if not rows:
        raise ValueError("helium target inventory is empty")
    if len({row["record"] for row in rows}) != len(rows):
        raise ValueError("helium target inventory is not unique")
    return rows


_PROBE_RUNTIME = r'''
from __future__ import annotations
import csv, json, math, pathlib, threading
from dataclasses import asdict

_CONFIG = json.loads(pathlib.Path(__file__).with_name("probe_config.json").read_text())
_OUT = pathlib.Path(_CONFIG["output_dir"])
_OUT.mkdir(parents=True, exist_ok=True)
_TARGET_EVAL = int(_CONFIG["target_evaluation"])
_TARGET_FULL_ROW = int(_CONFIG["target_full_row"])
_TARGET = {int(row["record"]): dict(row) for row in _CONFIG["target_inventory"]}
_LOCK = threading.RLock()
_STATE = {
    "global_evaluation": 0,
    "dsec_call_counter": 0,
    "dsec_call_by_object": {},
    "current_dsec_call": 0,
    "current_evaluator": None,
    "records": {},
    "terms": [],
    "trace": [],
    "solve_rows": [],
    "row46_matrix": [],
    "normalization": [],
    "actual_records_touching_row46": set(),
    "installed": False,
}

RECORD_FIELDS = [
    "global_evaluation_ordinal", "dsec_call_id", "dsec_local_evaluation_index",
    "source_position", "record", "element_z", "ion_stage", "data_type", "rate_type",
    "lower_row", "upper_row", "escape_kind", "escape_index", "tau_in", "tau_out",
    "allow_missing_as_zero", "ptmp1", "ptmp2", "ptmp_sum", "flinabs_ptmp1",
    "covering_fraction", "temperature_k", "hydrogen_density_cm3", "electron_fraction_xee",
    "ans1", "ans2", "ans3", "ans4", "ans5", "ans6", "idest1", "idest2",
    "ucalc_status", "reason", "provenance_branch", "provenance_implementation",
    "diagnostics_json", "compact_lower_row", "compact_upper_row",
    "initial_lower_population", "initial_upper_population", "lte_lower_population",
    "lte_upper_population", "final_outer_lower_population", "final_outer_upper_population",
    "final_lower_population", "final_upper_population", "population_dependency_json",
    "matrix_term_count", "matrix_committed",
]
TERM_FIELDS = [
    "global_evaluation_ordinal", "dsec_call_id", "source_order_index", "source_position",
    "record", "data_type", "rate_type", "term_index", "role", "row", "column",
    "aj1", "aj2", "cj", "cj2", "idest1", "idest2", "lower_endpoint", "upper_endpoint",
    "source_row_unclamped", "source_column_unclamped", "source_ipmat_clamped",
    "touches_row46",
]
SOLVE_FIELDS = [
    "global_evaluation_ordinal", "compact_row", "full_row", "is_normalization_row",
    "ion_counter", "superlevel", "initial_population", "lte_population",
    "final_outer_start_population", "final_population", "rhs", "row_residual",
    "row_scale", "relative_row_residual",
]
MATRIX_FIELDS = [
    "global_evaluation_ordinal", "matrix_row_kind", "compact_row", "full_row",
    "compact_column", "dense_before_normalization", "normalized_after_commit",
    "heating_value", "heating2_value", "rhs",
]
TRACE_FIELDS = [
    "global_evaluation_ordinal", "dsec_call_id", "dsec_local_evaluation_index",
    "temperature_k", "hydrogen_density_cm3", "electron_fraction_xee",
]


def _finite(value):
    try:
        x = float(value)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _safe_index(values, index):
    try:
        if values is None or index < 0 or index >= len(values):
            return None
        return _finite(values[index])
    except Exception:
        return None


def _record_key(record):
    return (int(_STATE["global_evaluation"]), int(record))


def _ensure_record(record):
    key = _record_key(record)
    row = _STATE["records"].setdefault(key, {})
    inv = _TARGET.get(int(record), {})
    row.setdefault("global_evaluation_ordinal", int(_STATE["global_evaluation"]))
    row.setdefault("dsec_call_id", int(_STATE["current_dsec_call"]))
    row.setdefault("source_position", inv.get("source_position"))
    row.setdefault("record", int(record))
    row.setdefault("element_z", 2)
    row.setdefault("ion_stage", inv.get("ion_stage"))
    row.setdefault("data_type", inv.get("data_type"))
    row.setdefault("rate_type", inv.get("rate_type"))
    row.setdefault("lower_row", inv.get("lower_row"))
    row.setdefault("upper_row", inv.get("upper_row"))
    return row


def _roles_json(role):
    try:
        return json.dumps(role, sort_keys=True, default=str)
    except Exception:
        return "{}"


def install():
    if _STATE["installed"]:
        return
    from xstar_tools.xstar import dsec as dsec_mod
    from xstar_tools.xstar import element_equilibrium as eq
    from xstar_tools.xstar.ucalc import SourceFaithfulUCalc

    original_dsec_call = dsec_mod.CalcHMCAllDsecEvaluator.__call__
    def dsec_call(self, state):
        with _LOCK:
            ident = id(self)
            if ident not in _STATE["dsec_call_by_object"]:
                _STATE["dsec_call_counter"] += 1
                _STATE["dsec_call_by_object"][ident] = int(_STATE["dsec_call_counter"])
            _STATE["current_dsec_call"] = int(_STATE["dsec_call_by_object"][ident])
            _STATE["global_evaluation"] += 1
            local_eval = len(getattr(self, "evaluations", ())) + 1
            _STATE["trace"].append({
                "global_evaluation_ordinal": int(_STATE["global_evaluation"]),
                "dsec_call_id": int(_STATE["current_dsec_call"]),
                "dsec_local_evaluation_index": int(local_eval),
                "temperature_k": float(state.temperature_k),
                "hydrogen_density_cm3": float(state.hydrogen_density_cm3),
                "electron_fraction_xee": float(state.electron_fraction_xee),
            })
            _STATE["current_evaluator"] = self
        try:
            self.element_solver = solve_element_statistical_equilibrium
            return original_dsec_call(self, state)
        finally:
            _STATE["current_evaluator"] = None
    dsec_mod.CalcHMCAllDsecEvaluator.__call__ = dsec_call

    original_escape = eq._escape_factors
    def escape_factors(record, rate_type, derived, context):
        p1, p2, reason = original_escape(record, rate_type, derived, context)
        if int(record) in _TARGET and int(_STATE["global_evaluation"]) == _TARGET_EVAL:
            escape_kind = "none"
            escape_index = 0
            tau_in = tau_out = 0.0
            if int(rate_type) == 4:
                escape_kind = "line"
                escape_index = int(derived.nplini[record]) if record < len(derived.nplini) else 0
                tau_in, tau_out = context.escape.line_taus(escape_index)
            elif int(rate_type) == 7:
                escape_kind = "continuum"
                escape_index = int(derived.npconi2[record]) if record < len(derived.npconi2) else 0
                tau_in, tau_out = context.escape.continuum_taus(escape_index)
            if tau_in is None and context.escape.allow_missing_as_zero:
                tau_in = 0.0
            if tau_out is None and context.escape.allow_missing_as_zero:
                tau_out = 0.0
            with _LOCK:
                row = _ensure_record(record)
                row.update({
                    "escape_kind": escape_kind,
                    "escape_index": escape_index,
                    "tau_in": _finite(tau_in),
                    "tau_out": _finite(tau_out),
                    "allow_missing_as_zero": bool(context.escape.allow_missing_as_zero),
                    "ptmp1": float(p1),
                    "ptmp2": float(p2),
                    "ptmp_sum": float(p1) + float(p2),
                    "flinabs_ptmp1": 1.0,
                    "covering_fraction": float(context.covering_fraction),
                    "temperature_k": float(context.temperature_k),
                    "hydrogen_density_cm3": float(context.hydrogen_density_cm3),
                    "electron_fraction_xee": float(context.electron_fraction_xee),
                    "escape_reason": reason or "",
                })
        return p1, p2, reason
    eq._escape_factors = escape_factors

    original_eval = SourceFaithfulUCalc.evaluate_record_number
    def evaluate_record_number(self, master, record, context, **kwargs):
        result = original_eval(self, master, record, context, **kwargs)
        extras = getattr(context, "extras", {}) or {}
        if (
            int(record) in _TARGET
            and int(extras.get("element_z", -1)) == 2
            and int(_STATE["global_evaluation"]) == _TARGET_EVAL
        ):
            rnise = extras.get("rnise")
            population_payload = {
                "rnise_idest1": _safe_index(rnise, int(result.idest1)),
                "rnise_idest2": _safe_index(rnise, int(result.idest2)),
                "compact_start": extras.get("compact_start"),
                "leveltemp_workspace_persistent": extras.get("leveltemp_workspace_persistent"),
                "leveltemp_owner_idest1": (extras.get("leveltemp_owner_by_column") or {}).get(int(result.idest1)),
                "leveltemp_owner_idest2": (extras.get("leveltemp_owner_by_column") or {}).get(int(result.idest2)),
            }
            with _LOCK:
                row = _ensure_record(record)
                row.update({
                    "dsec_local_evaluation_index": len(getattr(_STATE.get("current_evaluator"), "evaluations", ())) + 1 if _STATE.get("current_evaluator") is not None else "",
                    "data_type": int(result.data_type),
                    "rate_type": int(result.rate_type),
                    "ans1": float(result.ans1), "ans2": float(result.ans2),
                    "ans3": float(result.ans3), "ans4": float(result.ans4),
                    "ans5": float(result.ans5), "ans6": float(result.ans6),
                    "idest1": int(result.idest1), "idest2": int(result.idest2),
                    "ucalc_status": getattr(result.status, "value", str(result.status)),
                    "reason": str(getattr(result, "reason", "")),
                    "provenance_branch": str(getattr(result.provenance, "branch_name", "")),
                    "provenance_implementation": str(getattr(result.provenance, "implementation", "")),
                    "diagnostics_json": json.dumps(dict(getattr(result, "diagnostics", {}) or {}), sort_keys=True, default=str),
                    "population_dependency_json": json.dumps(population_payload, sort_keys=True, default=str),
                })
        return result
    SourceFaithfulUCalc.evaluate_record_number = evaluate_record_number

    original_solve = eq.solve_element_statistical_equilibrium
    def solve_element_statistical_equilibrium(master, derived, *, element_z, context, dispatcher=None):
        result = original_solve(master, derived, element_z=element_z, context=context, dispatcher=dispatcher)
        if int(element_z) == 2 and int(_STATE["global_evaluation"]) == _TARGET_EVAL:
            assembly = result.assembly
            solve = result.solve
            terms_all = list(assembly.terms)
            touched = [term for term in terms_all if int(term.row) == _TARGET_FULL_ROW or int(term.column) == _TARGET_FULL_ROW]
            actual_records = {int(term.record) for term in touched}
            _STATE["actual_records_touching_row46"] = actual_records
            grouped = {}
            for source_order_index, term in enumerate(terms_all, start=1):
                if int(term.record) not in actual_records:
                    continue
                grouped.setdefault(int(term.record), []).append(term)
                payload = {
                    "global_evaluation_ordinal": int(_STATE["global_evaluation"]),
                    "dsec_call_id": int(_STATE["current_dsec_call"]),
                    "source_order_index": int(source_order_index),
                    "source_position": int(_TARGET[int(term.record)]["source_position"]),
                    **asdict(term),
                    "touches_row46": bool(int(term.row) == _TARGET_FULL_ROW or int(term.column) == _TARGET_FULL_ROW),
                }
                _STATE["terms"].append(payload)
            initial = assembly.initial_populations
            lte = assembly.lte_populations
            final_outer = solve.final_outer_start_populations if solve is not None else None
            final = solve.populations if solve is not None else None
            for record, record_terms in grouped.items():
                forward = next((term for term in record_terms if str(term.role) == "forward_offdiag"), record_terms[0])
                compact_lower = int(forward.column)
                compact_upper = int(forward.row)
                row = _ensure_record(record)
                row.update({
                    "compact_lower_row": compact_lower,
                    "compact_upper_row": compact_upper,
                    "initial_lower_population": _safe_index(initial, compact_lower),
                    "initial_upper_population": _safe_index(initial, compact_upper),
                    "lte_lower_population": _safe_index(lte, compact_lower),
                    "lte_upper_population": _safe_index(lte, compact_upper),
                    "final_outer_lower_population": _safe_index(final_outer, compact_lower),
                    "final_outer_upper_population": _safe_index(final_outer, compact_upper),
                    "final_lower_population": _safe_index(final, compact_lower),
                    "final_upper_population": _safe_index(final, compact_upper),
                    "matrix_term_count": len(record_terms),
                    "matrix_committed": len(record_terms) == 4,
                })
            n = int(assembly.basis.n_rows)
            norm = int(assembly.basis.normalization_row)
            row46 = _TARGET_FULL_ROW
            for compact in range(1, n + 1):
                basis_row = assembly.basis.row(compact)
                full_row = compact
                roles = list(getattr(basis_row, "roles", ()) or ())
                _STATE["solve_rows"].append({
                    "global_evaluation_ordinal": int(_STATE["global_evaluation"]),
                    "compact_row": compact,
                    "full_row": full_row,
                    "is_normalization_row": int(compact == norm),
                    "ion_counter": int(getattr(basis_row, "ion_counter", 0)),
                    "superlevel": int(getattr(basis_row, "superlevel", 0)),
                    "initial_population": _safe_index(initial, compact),
                    "lte_population": _safe_index(lte, compact),
                    "final_outer_start_population": _safe_index(final_outer, compact),
                    "final_population": _safe_index(final, compact),
                    "rhs": _safe_index(assembly.rhs, compact - 1),
                    "row_residual": _safe_index(getattr(solve, "row_residual", None), compact - 1),
                    "row_scale": _safe_index(getattr(solve, "row_scale", None), compact - 1),
                    "relative_row_residual": _safe_index(getattr(solve, "relative_row_residual", None), compact - 1),
                    "roles_json": _roles_json(roles),
                })
            for kind, compact_row in (("physical_row46", row46), ("normalization", norm)):
                for col in range(1, n + 1):
                    payload = {
                        "global_evaluation_ordinal": int(_STATE["global_evaluation"]),
                        "matrix_row_kind": kind,
                        "compact_row": compact_row,
                        "full_row": compact_row,
                        "compact_column": col,
                        "dense_before_normalization": float(assembly.dense_matrix[compact_row - 1, col - 1]),
                        "normalized_after_commit": float(assembly.normalized_matrix[compact_row - 1, col - 1]),
                        "heating_value": float(assembly.heating_matrix[compact_row - 1, col - 1]),
                        "heating2_value": float(assembly.heating_matrix2[compact_row - 1, col - 1]),
                        "rhs": float(assembly.rhs[compact_row - 1]),
                    }
                    if kind == "physical_row46":
                        _STATE["row46_matrix"].append(payload)
                    else:
                        _STATE["normalization"].append(payload)
        return result
    eq.solve_element_statistical_equilibrium = solve_element_statistical_equilibrium
    from xstar_tools.xstar import local_zone
    local_zone.solve_element_statistical_equilibrium = solve_element_statistical_equilibrium
    _STATE["installed"] = True


def finalize(run_summary=None):
    actual_records = set(_STATE["actual_records_touching_row46"])
    rows = [row for (ev, record), row in sorted(_STATE["records"].items()) if int(ev) == _TARGET_EVAL and int(record) in actual_records]
    terms = [row for row in _STATE["terms"] if int(row["global_evaluation_ordinal"]) == _TARGET_EVAL and int(row["record"]) in actual_records]
    trace = list(_STATE["trace"])
    solve_rows = list(_STATE["solve_rows"])
    row46_matrix = list(_STATE["row46_matrix"])
    normalization = list(_STATE["normalization"])
    with (_OUT / "heii_row46_dsec_runtime_records.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RECORD_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(sorted(rows, key=lambda r: int(r["source_position"])))
    with (_OUT / "heii_row46_dsec_runtime_matrix_terms.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TERM_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(sorted(terms, key=lambda r: int(r["source_order_index"])))
    solve_fields = SOLVE_FIELDS + ["roles_json"]
    with (_OUT / "heii_row46_dsec_solve_rows.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=solve_fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(solve_rows)
    with (_OUT / "heii_row46_dsec_matrix_row.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATRIX_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(row46_matrix)
    with (_OUT / "heii_row46_dsec_normalization_row.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MATRIX_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(normalization)
    with (_OUT / "dsec_evaluation_trace.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACE_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(trace)
    captured_records = {int(row["record"]) for row in rows}
    report = {
        "schema": "xstar-tools-v0648714-v0472-dsec-row46-runtime-probe-v1",
        "release": "0.6.48.7.14",
        "result": "ACCEPT" if len(rows) == 155 and len(terms) == 620 and captured_records == actual_records else "REJECT",
        "capture_kind": "actual_v06472_dsec_heii_row46_complete_source_order_runtime_capture",
        "actual_dsec_runtime_capture": True,
        "target_evaluation_ordinal": _TARGET_EVAL,
        "target_full_row": _TARGET_FULL_ROW,
        "dsec_evaluations_observed": len(trace),
        "records": len(rows),
        "matrix_terms": len(terms),
        "solve_rows": len(solve_rows),
        "row46_matrix_columns": len(row46_matrix),
        "normalization_columns": len(normalization),
        "target_records_match_actual_terms": captured_records == actual_records,
        "missing_captured_records": sorted(actual_records - captured_records),
        "unexpected_captured_records": sorted(captured_records - actual_records),
        "all_records_matrix_committed": all(bool(row.get("matrix_committed")) for row in rows) if rows else False,
        "source_package_version": "0.6.47.2",
        "flinabs_contract": "captured source value; v0.6.47.2 flinabs.f90 returns 1.0",
        "run_summary": run_summary or {},
        "single_record_correction_ready": False,
        "production_promotion_ready": False,
    }
    (_OUT / "capture_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
'''

_DRIVER = r'''
from __future__ import annotations
import argparse, json, pathlib
p=argparse.ArgumentParser()
p.add_argument("--parameters-json", required=True)
p.add_argument("--atdb-path", required=True)
p.add_argument("--output-dir", required=True)
p.add_argument("--coheat-path")
a=p.parse_args()
import v048714_probe_runtime as probe
probe.install()
from xstar_tools.xstar.physical_runner import run_xstar_from_parameters
params=json.loads(pathlib.Path(a.parameters_json).read_text())
result=run_xstar_from_parameters(
    params,
    atdb_path=a.atdb_path,
    output_dir=a.output_dir,
    coheat_path=a.coheat_path,
    overwrite=True,
    diagnostics_mode="none",
    active_subset=True,
    profile_components="none",
    profile_rss=False,
    profile_backend_calls=False,
    profile_terminal=True,
    progress_debug=False,
    backend="python",
    rates_backend="python",
    matrix_backend="python",
    emissivity_backend="python",
    output_final_recompute=False,
)
summary={
    "ready": bool(result.ready),
    "completed_passes": int(result.completed_passes),
    "completed_zones": int(result.completed_zones),
    "output_dir": str(result.output_dir),
}
report=probe.finalize(summary)
print(json.dumps(report, indent=2, sort_keys=True))
raise SystemExit(0 if report["result"] == "ACCEPT" else 2)
'''


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def verify(bundle: Path) -> dict[str, Any]:
    errors: list[str] = []
    required = (
        RECORDS_NAME,
        TERMS_NAME,
        SOLVE_ROWS_NAME,
        ROW46_MATRIX_NAME,
        NORMALIZATION_NAME,
        TRACE_NAME,
        REPORT_NAME,
    )
    for name in required:
        if not (bundle / name).is_file():
            errors.append(f"missing:{name}")
    if errors:
        return {
            "schema": BUNDLE_SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": errors,
            "single_record_correction_ready": False,
            "production_promotion_ready": False,
        }
    records = _read_csv(bundle / RECORDS_NAME)
    terms = _read_csv(bundle / TERMS_NAME)
    solve_rows = _read_csv(bundle / SOLVE_ROWS_NAME)
    row46_matrix = _read_csv(bundle / ROW46_MATRIX_NAME)
    normalization = _read_csv(bundle / NORMALIZATION_NAME)
    trace = _read_csv(bundle / TRACE_NAME)
    report = json.loads((bundle / REPORT_NAME).read_text())
    if len(records) != TARGET_RECORDS:
        errors.append(f"records={len(records)}")
    if len(terms) != TARGET_MATRIX_TERMS:
        errors.append(f"matrix_terms={len(terms)}")
    if len({int(row["record"]) for row in records}) != TARGET_RECORDS:
        errors.append("record_identity_not_unique")
    counts = Counter(int(row["data_type"]) for row in records)
    if dict(sorted(counts.items())) != TARGET_TYPE_COUNTS:
        errors.append(f"type_inventory={dict(sorted(counts.items()))}")
    if any(int(row["global_evaluation_ordinal"]) != TARGET_EVALUATION for row in records):
        errors.append("wrong_evaluation")
    for row in records:
        for field in (
            "ptmp1", "ptmp2", "ptmp_sum", "flinabs_ptmp1", "covering_fraction",
            "temperature_k", "hydrogen_density_cm3", "electron_fraction_xee",
            "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
        ):
            try:
                value = float(row[field])
            except Exception:
                errors.append(f"non_numeric:{row.get('record')}:{field}")
                break
            if not (value == value and abs(value) != float("inf")):
                errors.append(f"non_finite:{row.get('record')}:{field}")
                break
        if str(row.get("matrix_committed", "")).lower() not in {"true", "1"}:
            errors.append(f"not_committed:{row.get('record')}")
    by_record: dict[int, int] = {}
    source_order = []
    for row in terms:
        by_record[int(row["record"])] = by_record.get(int(row["record"]), 0) + 1
        source_order.append(int(row["source_order_index"]))
    if set(by_record.values()) != {4} or len(by_record) != TARGET_RECORDS:
        errors.append("matrix_term_inventory")
    if source_order != sorted(source_order) or len(source_order) != len(set(source_order)):
        errors.append("source_order_not_strict")
    if len(solve_rows) == 0:
        errors.append("missing_solve_rows")
    normalization_rows = [r for r in solve_rows if int(r.get("is_normalization_row", 0)) == 1]
    if len(normalization_rows) != 1:
        errors.append(f"normalization_row_count={len(normalization_rows)}")
    dimension = len(solve_rows)
    if len(row46_matrix) != dimension:
        errors.append(f"row46_matrix_columns={len(row46_matrix)}:{dimension}")
    if len(normalization) != dimension:
        errors.append(f"normalization_columns={len(normalization)}:{dimension}")
    if normalization:
        if any(float(row["normalized_after_commit"]) != 1.0 for row in normalization):
            errors.append("normalization_row_not_all_ones")
        if any(float(row["rhs"]) != 1.0 for row in normalization):
            errors.append("normalization_rhs_not_one")
    if not bool(report.get("actual_dsec_runtime_capture")):
        errors.append("not_actual_dsec_capture")
    if not bool(report.get("target_records_match_actual_terms")):
        errors.append("target_records_do_not_match_actual_terms")
    if int(report.get("dsec_evaluations_observed", 0)) < TARGET_EVALUATION:
        errors.append("insufficient_dsec_evaluations")
    hashes = {name: sha256(bundle / name) for name in required}
    result = {
        "schema": BUNDLE_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "capture_kind": report.get("capture_kind"),
        "actual_dsec_runtime_capture": bool(report.get("actual_dsec_runtime_capture")),
        "target_evaluation_ordinal": TARGET_EVALUATION,
        "target_full_row": TARGET_FULL_ROW,
        "records": len(records),
        "matrix_terms": len(terms),
        "solve_rows": len(solve_rows),
        "normalization_row": int(normalization_rows[0]["full_row"]) if len(normalization_rows) == 1 else None,
        "dsec_evaluations_observed": len(trace),
        "data_type_counts": {str(k): v for k, v in sorted(counts.items())},
        "record_oracle_sha256": hashes[RECORDS_NAME],
        "matrix_terms_sha256": hashes[TERMS_NAME],
        "solve_rows_sha256": hashes[SOLVE_ROWS_NAME],
        "row46_matrix_sha256": hashes[ROW46_MATRIX_NAME],
        "normalization_sha256": hashes[NORMALIZATION_NAME],
        "trace_sha256": hashes[TRACE_NAME],
        "errors": errors,
        "single_record_correction_ready": False,
        "production_promotion_ready": False,
    }
    return result


def freeze(bundle: Path) -> dict[str, Any]:
    result = verify(bundle)
    files: dict[str, Any] = {}
    for name in (
        RECORDS_NAME,
        TERMS_NAME,
        SOLVE_ROWS_NAME,
        ROW46_MATRIX_NAME,
        NORMALIZATION_NAME,
        TRACE_NAME,
        REPORT_NAME,
    ):
        path = bundle / name
        if path.is_file():
            files[name] = {"sha256": sha256(path), "size_bytes": path.stat().st_size}
    manifest = {**result, "immutable": result["result"] == "ACCEPT", "files": files}
    write_json(bundle / MANIFEST_NAME, manifest)
    return result


def run_capture(
    source_archive: Path,
    lowered_program: Path,
    atdb_path: Path,
    output_dir: Path,
    *,
    parameters_json: Path,
    coheat_path: Path | None = None,
    target_evaluation: int = TARGET_EVALUATION,
) -> dict[str, Any]:
    if sha256(source_archive) != SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive SHA-256 mismatch")
    if not atdb_path.is_file():
        raise FileNotFoundError(f"ATDB not found: {atdb_path}")
    if not parameters_json.is_file():
        raise FileNotFoundError(f"parameters JSON not found: {parameters_json}")
    inventory = _load_target_inventory(lowered_program)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="v048714_") as temp_name:
        temp = Path(temp_name)
        safe_extract(source_archive, temp / "source")
        root = source_root(temp / "source")
        probe_dir = temp / "probe"
        probe_dir.mkdir()
        (probe_dir / "v048714_probe_runtime.py").write_text(_PROBE_RUNTIME)
        write_json(
            probe_dir / "probe_config.json",
            {
                "output_dir": str(output_dir),
                "target_evaluation": int(target_evaluation),
                "target_full_row": TARGET_FULL_ROW,
                "target_inventory": inventory,
            },
        )
        driver = probe_dir / "run_capture.py"
        driver.write_text(_DRIVER)
        run_output = output_dir / "v0472_reference_run"
        command = [
            sys.executable,
            str(driver),
            "--parameters-json",
            str(parameters_json.resolve()),
            "--atdb-path",
            str(atdb_path.resolve()),
            "--output-dir",
            str(run_output),
        ]
        if coheat_path is not None:
            command.extend(["--coheat-path", str(coheat_path.resolve())])
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(probe_dir), str(root / "src")])
        for name in (
            "BACKEND", "SOLVER_BACKEND", "RATES_BACKEND", "MATRIX_BACKEND",
            "EMISSIVITY_BACKEND", "OPACITY_BACKEND", "THERMAL_BACKEND", "ENGINE_BACKEND",
        ):
            env[f"XSTAR_ATOMIC_{name}"] = "python"
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        (output_dir / "v0472_capture_run.log").write_text(completed.stdout)
        if completed.returncode != 0:
            raise RuntimeError(
                f"v0.6.47.2 row-46 DSEC capture failed with exit {completed.returncode}; "
                f"see {output_dir / 'v0472_capture_run.log'}"
            )
    result = freeze(output_dir)
    write_json(output_dir / "verification.json", result)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("source_archive", type=Path)
    run.add_argument("lowered_program", type=Path)
    run.add_argument("atdb_path", type=Path)
    run.add_argument("output_dir", type=Path)
    run.add_argument(
        "--parameters-json",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "benchmarks"
        / "v06486_qualification_reference_v0472"
        / "parameters.json",
    )
    run.add_argument("--coheat-path", type=Path)
    run.add_argument("--target-evaluation", type=int, default=TARGET_EVALUATION)
    run.add_argument("--output-json", type=Path)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("bundle_dir", type=Path)
    verify_parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "run":
            result = run_capture(
                args.source_archive,
                args.lowered_program,
                args.atdb_path,
                args.output_dir,
                parameters_json=args.parameters_json,
                coheat_path=args.coheat_path,
                target_evaluation=args.target_evaluation,
            )
        else:
            result = verify(args.bundle_dir)
        if args.output_json:
            write_json(args.output_json, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["result"] == "ACCEPT" else 2
    except Exception as exc:
        print(f"DSEC row-46 runtime capture failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
