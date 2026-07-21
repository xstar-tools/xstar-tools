"""Capture v0.6.47.2 lifetime of the three sequence-14 Type-88 owner records.

Patch 5.19.4.1 is diagnostic-only and is based on the accepted 5.19.3 engine.
It extends the authoritative 5.19.3 source-record contribution capture by
observing every SourceFaithfulUCalc evaluation of records 40294, 40379, 40380.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import v0472_all61_source_record_contribution_capture_v82_patch5193 as base

RELEASE = "0.6.48.7.46.25.5.17.25.82-patch5.19.4.1"
SCHEMA = "xstar-tools-v82-patch51941-v0472-type88-rate-lifetime-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v82-patch51941-v0472-type88-rate-lifetime-oracle-v1"
LIFETIME_NAME = "v0472_all61_type88_rate_lifetime.csv"
REPORT_NAME = "all61_type88_rate_lifetime_capture_report.json"
VERIFY_NAME = "all61_type88_rate_lifetime_capture_verification.json"
BUNDLE_MANIFEST_NAME = "all61_type88_rate_lifetime_capture_manifest.json"
TARGET_RECORDS = {40294, 40379, 40380}

_PROBE = base._PROBE
_PROBE = _PROBE.replace(
    '"all61_source_record_contributions": [], "linear_solve_trace_current": [], "final_counter": 0}',
    '"all61_source_record_contributions": [], "type88_rate_lifetime": [], '
    '"type88_rate_last": {}, "active_call_id": 0, "active_local_eval": 0, '
    '"linear_solve_trace_current": [], "final_counter": 0}',
    1,
)

_LIFETIME_CODE = r'''
V82_PATCH51941_TYPE88_TARGET_RECORDS = {40294, 40379, 40380}
V82_PATCH51941_TYPE88_RATE_LIFETIME_FIELDS = [
 "sequence","dsec_call_id","evaluation_index","record","data_type","rate_type","phase","caller_chain",
 "observation_index","temperature_k","temperature_t4","hydrogen_density_cm3","electron_fraction_xee",
 "electron_density_cm3","indonly","nlevp","ptmp1","ptmp2","covering_fraction",
 "full_epi_count","full_epi_sha256","full_bremsa_count","full_bremsa_sha256",
 "reduced_epi_count","reduced_epi_sha256","reduced_bremsa_count","reduced_bremsa_sha256",
 "previous_observed_phase","previous_observed_ans1","previous_observed_bit_equal",
 "ans1","ans2","ans3","ans4","ans5","ans6","idest1","idest2","status",
 "diag_threshold_ev","diag_nb1_one_based","diag_klmax_one_based","diag_integration_intervals",
 "lifecycle_classification"
]

def _v82_patch51941_hash_array(value):
    arr = _array(value)
    be = np.asarray(arr, dtype=">f8")
    return int(arr.size), hashlib.sha256(be.tobytes(order="C")).hexdigest()

def _v82_patch51941_type88_phase():
    import inspect
    names = [frame.function for frame in inspect.stack(context=0)[2:14]]
    if "calc_ion_rates" in names:
        phase = "preliminary_calc_ion_rates"
    elif "_assemble_element_matrix_impl" in names or "assemble_element_matrix" in names:
        phase = "calc_hmc_ion_second_pass"
    else:
        phase = "other"
    return phase, ">".join(names[:8])

def _v82_patch51941_install_type88_lifetime_wrapper():
    from xstar_tools.xstar import ucalc as ucalc_mod
    cls = ucalc_mod.SourceFaithfulUCalc
    if getattr(cls.evaluate, "_v82_patch51941_wrapped", False):
        return
    original_evaluate = cls.evaluate
    def wrapped_evaluate(self, record, context, *, strict=True):
        rec = int(getattr(record, "record", 0) or 0)
        if rec not in V82_PATCH51941_TYPE88_TARGET_RECORDS:
            return original_evaluate(self, record, context, strict=strict)
        phase, caller_chain = _v82_patch51941_type88_phase()
        radiation = getattr(context, "radiation", None)
        full_epi = getattr(radiation, "epi_eV", getattr(radiation, "epi", None))
        full_bremsa = getattr(radiation, "bremsa", None)
        reduced_epi = getattr(radiation, "epim_eV", getattr(radiation, "epim", None))
        reduced_bremsa = getattr(radiation, "bremsam", None)
        fne, fhe = _v82_patch51941_hash_array(full_epi)
        fnb, fhb = _v82_patch51941_hash_array(full_bremsa)
        rne, rhe = _v82_patch51941_hash_array(reduced_epi)
        rnb, rhb = _v82_patch51941_hash_array(reduced_bremsa)
        result = original_evaluate(self, record, context, strict=strict)
        sequence = int(_STATE.get("global_eval", 0) or 0)
        call_id = int(_STATE.get("active_call_id", 0) or 0)
        local_eval = int(_STATE.get("active_local_eval", 0) or 0)
        key = f"{sequence}:{rec}"
        prev = _STATE["type88_rate_last"].get(key)
        ans1 = float(getattr(result, "ans1", float("nan")))
        previous_ans1 = float(prev[1]) if prev is not None else float("nan")
        previous_phase = str(prev[0]) if prev is not None else "NONE"
        bit_equal = int(prev is not None and struct.pack(">d", previous_ans1) == struct.pack(">d", ans1))
        if prev is None:
            lifecycle = "first_observed_evaluation"
        elif phase == "calc_hmc_ion_second_pass" and previous_phase == "preliminary_calc_ion_rates":
            lifecycle = "second_pass_recomputed_same" if bit_equal else "second_pass_recomputed_different"
        else:
            lifecycle = "reevaluated_same" if bit_equal else "reevaluated_different"
        diagnostics = dict(getattr(result, "diagnostics", {}) or {})
        rows = _STATE["type88_rate_lifetime"]
        rows.append({
          "sequence": sequence, "dsec_call_id": call_id, "evaluation_index": local_eval,
          "record": rec, "data_type": int(getattr(record, "data_type", 0) or 0),
          "rate_type": int(getattr(record, "rate_type", 0) or 0), "phase": phase,
          "caller_chain": caller_chain,
          "observation_index": 1 + sum(1 for row in rows if int(row["sequence"]) == sequence and int(row["record"]) == rec),
          "temperature_k": float(getattr(context, "temperature_k", float("nan"))),
          "temperature_t4": float(getattr(context, "t", float("nan"))),
          "hydrogen_density_cm3": float(getattr(context, "hydrogen_density_cm3", float("nan"))),
          "electron_fraction_xee": float(getattr(context, "electron_fraction_xee", float("nan"))),
          "electron_density_cm3": float(getattr(context, "electron_density_cm3", float("nan"))),
          "indonly": int(bool(getattr(context, "indonly", False))), "nlevp": int(getattr(context, "nlevp", 0) or 0),
          "ptmp1": float(getattr(context, "ptmp1", float("nan"))), "ptmp2": float(getattr(context, "ptmp2", float("nan"))),
          "covering_fraction": float(getattr(context, "covering_fraction", float("nan"))),
          "full_epi_count": fne, "full_epi_sha256": fhe, "full_bremsa_count": fnb, "full_bremsa_sha256": fhb,
          "reduced_epi_count": rne, "reduced_epi_sha256": rhe, "reduced_bremsa_count": rnb, "reduced_bremsa_sha256": rhb,
          "previous_observed_phase": previous_phase, "previous_observed_ans1": previous_ans1,
          "previous_observed_bit_equal": bit_equal,
          "ans1": ans1, "ans2": float(getattr(result, "ans2", float("nan"))),
          "ans3": float(getattr(result, "ans3", float("nan"))), "ans4": float(getattr(result, "ans4", float("nan"))),
          "ans5": float(getattr(result, "ans5", float("nan"))), "ans6": float(getattr(result, "ans6", float("nan"))),
          "idest1": int(getattr(result, "idest1", 0) or 0), "idest2": int(getattr(result, "idest2", 0) or 0),
          "status": str(getattr(getattr(result, "status", None), "value", getattr(result, "status", ""))),
          "diag_threshold_ev": float(diagnostics.get("threshold_eV", float("nan"))),
          "diag_nb1_one_based": int(diagnostics.get("nb1_one_based", 0) or 0),
          "diag_klmax_one_based": int(diagnostics.get("klmax_one_based", 0) or 0),
          "diag_integration_intervals": int(diagnostics.get("integration_intervals", 0) or 0),
          "lifecycle_classification": lifecycle,
        })
        _STATE["type88_rate_last"][key] = (phase, ans1)
        return result
    wrapped_evaluate._v82_patch51941_wrapped = True
    cls.evaluate = wrapped_evaluate
'''
_PROBE = _PROBE.replace("V82_PATCH5193_SOURCE_RECORD_CONTRIBUTION_FIELDS = [", _LIFETIME_CODE + "\nV82_PATCH5193_SOURCE_RECORD_CONTRIBUTION_FIELDS = [", 1)
_PROBE = _PROBE.replace(
    '        self.capture_all_input_snapshots = False\n',
    '        _STATE["active_call_id"] = int(call_id)\n'
    '        _STATE["active_local_eval"] = int(local_eval)\n'
    '        self.capture_all_input_snapshots = False\n',
    1,
)
_PROBE = _PROBE.replace(
    '    dsec_mod.CalcHMCAllDsecEvaluator.__call__ = wrapped\n    _STATE["installed"] = True\n',
    '    dsec_mod.CalcHMCAllDsecEvaluator.__call__ = wrapped\n'
    '    _v82_patch51941_install_type88_lifetime_wrapper()\n'
    '    _STATE["installed"] = True\n',
    1,
)
_PROBE = _PROBE.replace(
    '      "v0472_all61_solve_stage_record_contributions.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["term_index"])),\n',
    '      "v0472_all61_solve_stage_record_contributions.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["term_index"])),\n'
    '      "v0472_all61_type88_rate_lifetime.csv": lambda row: (int(row["sequence"]), int(row["record"]), int(row["observation_index"])),\n',
    1,
)
_PROBE = _PROBE.replace(
    '      ("v0472_all61_solve_stage_record_contributions.csv", V82_PATCH5193_SOURCE_RECORD_CONTRIBUTION_FIELDS, _STATE["all61_source_record_contributions"]),\n',
    '      ("v0472_all61_solve_stage_record_contributions.csv", V82_PATCH5193_SOURCE_RECORD_CONTRIBUTION_FIELDS, _STATE["all61_source_record_contributions"]),\n'
    '      ("v0472_all61_type88_rate_lifetime.csv", V82_PATCH51941_TYPE88_RATE_LIFETIME_FIELDS, _STATE["type88_rate_lifetime"]),\n',
    1,
)
_PROBE = _PROBE.replace(f'"schema": "{base.SCHEMA}"', f'"schema": "{SCHEMA}"')
_DRIVER = base._DRIVER.replace("import v82_patch5193_source_record_probe_runtime as probe", "import v82_patch51941_type88_lifetime_probe_runtime as probe")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def verify(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    parent = base.verify(bundle)
    errors: list[str] = []
    if parent.get("result") != "ACCEPT":
        errors.append("parent_5193_source_record_capture_reject")
    path = bundle / LIFETIME_NAME
    rows = _read_csv(path) if path.is_file() else []
    if not rows:
        errors.append(f"missing_or_empty:{LIFETIME_NAME}")
    records = {int(r["record"]) for r in rows} if rows else set()
    if records != TARGET_RECORDS:
        errors.append(f"target_record_coverage={sorted(records)}")
    call1 = [r for r in rows if 1 <= int(r["sequence"]) <= 21]
    phases = {r["phase"] for r in call1}
    if "calc_hmc_ion_second_pass" not in phases:
        errors.append("missing_second_pass_observations")
    second_by_record = {rec: 0 for rec in TARGET_RECORDS}
    for r in call1:
        if r["phase"] == "calc_hmc_ion_second_pass":
            second_by_record[int(r["record"])] += 1
    missing_second = [rec for rec, count in sorted(second_by_record.items()) if count == 0]
    if missing_second:
        errors.append(f"missing_second_pass_records={missing_second}")
    report = {
        "schema": VERIFY_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "qualification_only": True,
        "production_promotion_ready": False,
        "production_rate_change_authorized": False,
        "actual_v0472_runtime_capture": True,
        "source_record_level_terms_available": bool(parent.get("source_record_level_terms_available", False)),
        "lifetime_rows": len(rows),
        "call1_lifetime_rows": len(call1),
        "target_records": sorted(records),
        "phases": sorted(phases),
        "second_pass_observations_by_record": {str(k): v for k, v in sorted(second_by_record.items())},
    }
    return report


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if base.base.base.base.base._sha256(source_archive) != base.base.base.base.base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v82_patch51941_source_") as tmp:
        tmp_path = Path(tmp)
        base.base.base.base.base._safe_extract(source_archive, tmp_path / "source")
        root = base.base.base.base.base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        (probe_dir / "v82_patch51941_type88_lifetime_probe_runtime.py").write_text(_PROBE)
        (probe_dir / "probe_config.json").write_text(json.dumps({"output_dir": str(output_dir)}, indent=2))
        (probe_dir / "driver.py").write_text(_DRIVER)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(probe_dir), str(root / "src")])
        env.update({"PYTHONFAULTHANDLER": "1", "PYTHONUNBUFFERED": "1", "OMP_NUM_THREADS": "1",
                    "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
        cmd = [sys.executable, str(probe_dir / "driver.py"), "--parameters-json", str(parameters_json.resolve()),
               "--atdb-path", str(atdb_path.resolve()), "--output-dir", str(output_dir / "physical_run")]
        if coheat_path is not None:
            cmd += ["--coheat-path", str(coheat_path.resolve())]
        log = output_dir / "v0472_all61_type88_rate_lifetime_capture_run.log"
        with log.open("w") as handle:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 Type-88 lifetime capture failed with exit {completed.returncode}; see {log}")
    historical = output_dir / "capture_report.json"
    if historical.is_file():
        import shutil
        shutil.copy2(historical, output_dir / base.REPORT_NAME)
        historical.replace(output_dir / REPORT_NAME)
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    files: dict[str, Any] = {}
    for path in sorted(output_dir.glob("v0472_all61_*.csv")):
        files[path.name] = {"sha256": base.base.base.base.base._sha256(path), "size_bytes": path.stat().st_size}
    for name in (REPORT_NAME, VERIFY_NAME):
        path = output_dir / name
        if path.is_file():
            files[name] = {"sha256": base.base.base.base.base._sha256(path), "size_bytes": path.stat().st_size}
    _write_json(output_dir / BUNDLE_MANIFEST_NAME, {**result, "immutable": result["result"] == "ACCEPT", "files": files})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("source_archive", type=Path)
    cap.add_argument("atdb_path", type=Path)
    cap.add_argument("output_dir", type=Path)
    cap.add_argument("parameters_json", type=Path)
    cap.add_argument("--coheat-path", type=Path)
    cap.add_argument("--output-json", type=Path)
    ver = sub.add_parser("verify")
    ver.add_argument("bundle", type=Path)
    ver.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = capture(args.source_archive, args.atdb_path, args.output_dir, args.parameters_json, args.coheat_path) if args.command == "capture" else verify(args.bundle)
    except Exception as exc:
        result = {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "qualification_only": True, "production_promotion_ready": False, "production_rate_change_authorized": False}
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
