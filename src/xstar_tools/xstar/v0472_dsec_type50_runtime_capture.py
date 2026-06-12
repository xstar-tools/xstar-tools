"""Capture the live v0.6.47.2 DSEC escape-probability contract for He II type 50.

This module runs the untouched v0.6.47.2 physical Python backend in an isolated
subprocess and installs an observational monkeypatch before the physical runner
is imported.  The probe records the actual DSEC evaluation inputs and the
source-ordered matrix terms committed by the helium element solve.

The capture is qualification-only.  It never changes the v0.6.47.2 rates,
escape probabilities, matrices, populations, controller, or products.
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
from pathlib import Path
from typing import Any, Iterable, Mapping

RELEASE = "0.6.48.7.13"
SCHEMA = "xstar-tools-v0648713-v0472-dsec-type50-runtime-capture-v1"
BUNDLE_SCHEMA = "xstar-tools-v0648713-type50-dsec-runtime-oracle-v1"
SOURCE_ARCHIVE_SHA256 = "85ff0184bd95daf046fd28923837239c5192f8d309b0716556d1d804b0453060"
TARGET_EVALUATION = 61
TARGET_RECORDS = 79
TARGET_MATRIX_TERMS = TARGET_RECORDS * 4
FIXED_EVALUATOR_ORACLE_SHA256 = "548cbc4f489a19cfabb199ad2f063b581af0a1b5de21b3ae4a444841a0da4d6f"
RECORDS_NAME = "type50_heii_rows46_54_dsec_runtime_records.csv"
TERMS_NAME = "type50_heii_rows46_54_dsec_runtime_matrix_terms.csv"
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
    path = lowered_program / "records.csv"
    if not path.is_file():
        raise FileNotFoundError(f"missing lowered records: {path}")
    rows: list[dict[str, Any]] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if (
                int(row.get("element_index", -1)) == 1
                and int(row.get("ion_stage", -1)) == 2
                and int(row.get("data_type", -1)) == 50
                and (
                    46 <= int(row.get("lower_row", -1)) <= 54
                    or 46 <= int(row.get("upper_row", -1)) <= 54
                )
            ):
                rows.append(
                    {
                        "record": int(row["record"]),
                        "source_position": int(row["source_position"]),
                        "lower_row": int(row["lower_row"]),
                        "upper_row": int(row["upper_row"]),
                    }
                )
    rows.sort(key=lambda item: item["source_position"])
    if len(rows) != TARGET_RECORDS:
        raise ValueError(f"expected {TARGET_RECORDS} target records, found {len(rows)}")
    if len({row["record"] for row in rows}) != TARGET_RECORDS:
        raise ValueError("target record inventory is not unique")
    return rows


_PROBE_RUNTIME = r'''
from __future__ import annotations
import csv, json, math, pathlib, threading
from dataclasses import asdict

_CONFIG = json.loads(pathlib.Path(__file__).with_name("probe_config.json").read_text())
_OUT = pathlib.Path(_CONFIG["output_dir"])
_OUT.mkdir(parents=True, exist_ok=True)
_TARGET_EVAL = int(_CONFIG["target_evaluation"])
_TARGET = {int(row["record"]): dict(row) for row in _CONFIG["target_inventory"]}
_LOCK = threading.RLock()
_STATE = {
    "global_evaluation": 0,
    "dsec_call_counter": 0,
    "dsec_call_by_object": {},
    "current_dsec_call": 0,
    "records": {},
    "terms": [],
    "trace": [],
    "installed": False,
}

RECORD_FIELDS = [
    "global_evaluation_ordinal", "dsec_call_id", "dsec_local_evaluation_index",
    "source_position", "record", "element_z", "ion_stage", "data_type",
    "lower_row", "upper_row", "line_index", "tau_in", "tau_out",
    "allow_missing_as_zero", "ptmp1", "ptmp2", "ptmp_sum",
    "flinabs_ptmp1", "covering_fraction", "temperature_k",
    "hydrogen_density_cm3", "electron_fraction_xee", "ans1", "ans2",
    "ans3", "ans4", "ans5", "ans6", "idest1", "idest2",
    "ucalc_status", "matrix_term_count", "matrix_committed",
]
TERM_FIELDS = [
    "global_evaluation_ordinal", "dsec_call_id", "source_position", "record",
    "term_index", "role", "row", "column", "aj1", "aj2", "cj", "cj2",
    "idest1", "idest2", "lower_endpoint", "upper_endpoint",
    "source_row_unclamped", "source_column_unclamped", "source_ipmat_clamped",
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
    row.setdefault("ion_stage", 2)
    row.setdefault("data_type", 50)
    row.setdefault("lower_row", inv.get("lower_row"))
    row.setdefault("upper_row", inv.get("upper_row"))
    return row


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
            global_eval = int(_STATE["global_evaluation"])
            local_eval = len(getattr(self, "evaluations", ())) + 1
            _STATE["trace"].append({
                "global_evaluation_ordinal": global_eval,
                "dsec_call_id": int(_STATE["current_dsec_call"]),
                "dsec_local_evaluation_index": int(local_eval),
                "temperature_k": float(state.temperature_k),
                "hydrogen_density_cm3": float(state.hydrogen_density_cm3),
                "electron_fraction_xee": float(state.electron_fraction_xee),
            })
        return original_dsec_call(self, state)
    dsec_mod.CalcHMCAllDsecEvaluator.__call__ = dsec_call

    original_escape = eq._escape_factors
    def escape_factors(record, rate_type, derived, context):
        p1, p2, reason = original_escape(record, rate_type, derived, context)
        if int(rate_type) == 4 and int(record) in _TARGET and int(_STATE["global_evaluation"]) == _TARGET_EVAL:
            line_index = int(derived.nplini[record]) if record < len(derived.nplini) else 0
            tau_in, tau_out = context.escape.line_taus(line_index)
            with _LOCK:
                row = _ensure_record(record)
                row.update({
                    "line_index": line_index,
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
                    "escape_reason": reason,
                })
        return p1, p2, reason
    eq._escape_factors = escape_factors

    original_eval = SourceFaithfulUCalc.evaluate_record_number
    def evaluate_record_number(self, master, record, context, **kwargs):
        result = original_eval(self, master, record, context, **kwargs)
        extras = getattr(context, "extras", {}) or {}
        if (
            int(record) in _TARGET
            and int(getattr(result, "data_type", -1)) == 50
            and int(extras.get("element_z", -1)) == 2
            and int(extras.get("ion_stage", -1)) == 2
            and int(_STATE["global_evaluation"]) == _TARGET_EVAL
        ):
            with _LOCK:
                row = _ensure_record(record)
                row.update({
                    "dsec_local_evaluation_index": len(getattr(_CURRENT_EVALUATOR(), "evaluations", ())) + 1 if _CURRENT_EVALUATOR() is not None else "",
                    "ans1": float(result.ans1), "ans2": float(result.ans2),
                    "ans3": float(result.ans3), "ans4": float(result.ans4),
                    "ans5": float(result.ans5), "ans6": float(result.ans6),
                    "idest1": int(result.idest1), "idest2": int(result.idest2),
                    "ucalc_status": getattr(result.status, "value", str(result.status)),
                })
        return result
    SourceFaithfulUCalc.evaluate_record_number = evaluate_record_number

    # Keep a current evaluator pointer only for reporting the local index.
    _STATE["current_evaluator"] = None
    original_dsec_call_2 = dsec_mod.CalcHMCAllDsecEvaluator.__call__
    def dsec_call_with_pointer(self, state):
        _STATE["current_evaluator"] = self
        # calc_hmc_all binds its default element solver at function definition
        # time.  Supplying the wrapper explicitly ensures the probe observes
        # the matrix terms actually returned to the live DSEC call.
        self.element_solver = solve_element_statistical_equilibrium
        try:
            return original_dsec_call_2(self, state)
        finally:
            _STATE["current_evaluator"] = None
    dsec_mod.CalcHMCAllDsecEvaluator.__call__ = dsec_call_with_pointer

    original_solve = eq.solve_element_statistical_equilibrium
    def solve_element_statistical_equilibrium(master, derived, *, element_z, context, dispatcher=None):
        result = original_solve(master, derived, element_z=element_z, context=context, dispatcher=dispatcher)
        if int(element_z) == 2 and int(_STATE["global_evaluation"]) == _TARGET_EVAL:
            committed = [term for term in result.assembly.terms if int(term.record) in _TARGET and int(term.data_type) == 50]
            grouped = {}
            for term in committed:
                grouped.setdefault(int(term.record), []).append(term)
            with _LOCK:
                for record, terms in grouped.items():
                    row = _ensure_record(record)
                    row["matrix_term_count"] = len(terms)
                    row["matrix_committed"] = len(terms) == 4
                    for term in terms:
                        payload = {
                            "global_evaluation_ordinal": int(_STATE["global_evaluation"]),
                            "dsec_call_id": int(_STATE["current_dsec_call"]),
                            "source_position": _TARGET[record]["source_position"],
                            **asdict(term),
                        }
                        _STATE["terms"].append(payload)
        return result
    eq.solve_element_statistical_equilibrium = solve_element_statistical_equilibrium
    # local_zone imported the function directly; replace that binding too.
    from xstar_tools.xstar import local_zone
    local_zone.solve_element_statistical_equilibrium = solve_element_statistical_equilibrium
    _STATE["installed"] = True


def _CURRENT_EVALUATOR():
    return _STATE.get("current_evaluator")


def finalize(run_summary=None):
    rows = [row for (ev, _), row in sorted(_STATE["records"].items()) if int(ev) == _TARGET_EVAL]
    terms = [row for row in _STATE["terms"] if int(row["global_evaluation_ordinal"]) == _TARGET_EVAL]
    trace = list(_STATE["trace"])
    with (_OUT / "type50_heii_rows46_54_dsec_runtime_records.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RECORD_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    with (_OUT / "type50_heii_rows46_54_dsec_runtime_matrix_terms.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TERM_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(sorted(terms, key=lambda r:(int(r["source_position"]),int(r["term_index"]))))
    with (_OUT / "dsec_evaluation_trace.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACE_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(trace)
    report = {
        "schema": "xstar-tools-v0648713-v0472-dsec-type50-runtime-probe-v1",
        "release": "0.6.48.7.13",
        "result": "ACCEPT" if len(rows) == 79 and len(terms) == 316 else "REJECT",
        "capture_kind": "actual_v06472_dsec_type50_escape_probability_runtime_capture",
        "actual_dsec_runtime_capture": True,
        "target_evaluation_ordinal": _TARGET_EVAL,
        "dsec_evaluations_observed": len(trace),
        "records": len(rows),
        "matrix_terms": len(terms),
        "all_records_matrix_committed": all(bool(row.get("matrix_committed")) for row in rows) if rows else False,
        "source_package_version": "0.6.47.2",
        "flinabs_contract": "captured source value; v0.6.47.2 flinabs.f90 returns 1.0",
        "run_summary": run_summary or {},
        "production_promotion_ready": False,
    }
    (_OUT / "capture_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
'''

_DRIVER = r'''
from __future__ import annotations
import argparse, json, pathlib, os
p=argparse.ArgumentParser()
p.add_argument("--parameters-json", required=True)
p.add_argument("--atdb-path", required=True)
p.add_argument("--output-dir", required=True)
p.add_argument("--coheat-path")
a=p.parse_args()
import v048712_probe_runtime as probe
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
    for name in (RECORDS_NAME, TERMS_NAME, TRACE_NAME, REPORT_NAME):
        if not (bundle / name).is_file():
            errors.append(f"missing:{name}")
    if errors:
        return {
            "schema": BUNDLE_SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": errors,
            "production_promotion_ready": False,
        }
    records = _read_csv(bundle / RECORDS_NAME)
    terms = _read_csv(bundle / TERMS_NAME)
    trace = _read_csv(bundle / TRACE_NAME)
    report = json.loads((bundle / REPORT_NAME).read_text())
    if len(records) != TARGET_RECORDS:
        errors.append(f"records={len(records)}")
    if len(terms) != TARGET_MATRIX_TERMS:
        errors.append(f"matrix_terms={len(terms)}")
    if len({int(row["record"]) for row in records}) != TARGET_RECORDS:
        errors.append("record_identity_not_unique")
    if any(int(row["global_evaluation_ordinal"]) != TARGET_EVALUATION for row in records):
        errors.append("wrong_evaluation")
    required_record_fields = (
        "ptmp1", "ptmp2", "ptmp_sum", "flinabs_ptmp1", "covering_fraction",
        "tau_in", "tau_out", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
    )
    for row in records:
        for field in required_record_fields:
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
    for row in terms:
        by_record[int(row["record"])] = by_record.get(int(row["record"]), 0) + 1
    if set(by_record.values()) != {4} or len(by_record) != TARGET_RECORDS:
        errors.append("matrix_term_inventory")
    if not bool(report.get("actual_dsec_runtime_capture")):
        errors.append("not_actual_dsec_capture")
    if int(report.get("dsec_evaluations_observed", 0)) < TARGET_EVALUATION:
        errors.append("insufficient_dsec_evaluations")
    hashes = {name: sha256(bundle / name) for name in (RECORDS_NAME, TERMS_NAME, TRACE_NAME, REPORT_NAME)}
    result = {
        "schema": BUNDLE_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "capture_kind": report.get("capture_kind"),
        "actual_dsec_runtime_capture": bool(report.get("actual_dsec_runtime_capture")),
        "target_evaluation_ordinal": TARGET_EVALUATION,
        "records": len(records),
        "matrix_terms": len(terms),
        "dsec_evaluations_observed": len(trace),
        "record_oracle_sha256": hashes[RECORDS_NAME],
        "matrix_terms_sha256": hashes[TERMS_NAME],
        "trace_sha256": hashes[TRACE_NAME],
        "fixed_evaluator_oracle_sha256": FIXED_EVALUATOR_ORACLE_SHA256,
        "errors": errors,
        "production_promotion_ready": False,
    }
    return result


def freeze(bundle: Path) -> dict[str, Any]:
    result = verify(bundle)
    files = {}
    for name in (RECORDS_NAME, TERMS_NAME, TRACE_NAME, REPORT_NAME):
        path = bundle / name
        if path.is_file():
            files[name] = {"sha256": sha256(path), "size_bytes": path.stat().st_size}
    manifest = {
        **result,
        "immutable": result["result"] == "ACCEPT",
        "files": files,
    }
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
    inventory = _load_target_inventory(lowered_program)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="v048712_") as temp_name:
        temp = Path(temp_name)
        safe_extract(source_archive, temp / "source")
        root = source_root(temp / "source")
        probe_dir = temp / "probe"
        probe_dir.mkdir()
        (probe_dir / "v048712_probe_runtime.py").write_text(_PROBE_RUNTIME)
        write_json(
            probe_dir / "probe_config.json",
            {
                "output_dir": str(output_dir),
                "target_evaluation": int(target_evaluation),
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
        env["XSTAR_ATOMIC_BACKEND"] = "python"
        env["XSTAR_ATOMIC_SOLVER_BACKEND"] = "python"
        env["XSTAR_ATOMIC_RATES_BACKEND"] = "python"
        env["XSTAR_ATOMIC_MATRIX_BACKEND"] = "python"
        env["XSTAR_ATOMIC_EMISSIVITY_BACKEND"] = "python"
        env["XSTAR_ATOMIC_OPACITY_BACKEND"] = "python"
        env["XSTAR_ATOMIC_THERMAL_BACKEND"] = "python"
        env["XSTAR_ATOMIC_ENGINE_BACKEND"] = "python"
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
                f"v0.6.47.2 DSEC capture failed with exit {completed.returncode}; "
                f"see {output_dir / 'v0472_capture_run.log'}"
            )
    result = freeze(output_dir)
    write_json(output_dir / "verification.json", result)
    return result


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
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
        print(f"DSEC type-50 runtime capture failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
