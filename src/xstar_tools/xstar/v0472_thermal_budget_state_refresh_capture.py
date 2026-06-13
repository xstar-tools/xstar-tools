"""Capture original v0.6.47.2 call-1 thermal budgets and between-call state refresh.

This is an observational qualification probe. It executes the untouched,
hash-verified v0.6.47.2 Python physical workflow, records every call-1
``calc_hmc_all`` budget, and fingerprints the first-evaluation radiation,
opacity, escape, population, and source workspaces for all four DSEC calls.
No rates, matrices, controller decisions, or products are modified.
"""
from __future__ import annotations

import argparse
import csv
import sys
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any, Mapping

csv.field_size_limit(sys.maxsize)

RELEASE = "0.6.48.7.21.2"
SCHEMA = "xstar-tools-v0648721-v0472-thermal-budget-state-refresh-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v0648721-thermal-budget-state-refresh-oracle-v1"
SOURCE_ARCHIVE_SHA256 = "85ff0184bd95daf046fd28923837239c5192f8d309b0716556d1d804b0453060"
BUDGET_NAME = "v0472_call1_thermal_budget.csv"
STATE_NAME = "v0472_between_call_state_fingerprints.csv"
TRACE_NAME = "v0472_dsec_thermal_trace.csv"
REPORT_NAME = "capture_report.json"
VERIFY_NAME = "capture_verification.json"
MANIFEST_NAME = "capture_manifest.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _safe_extract(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            target = (root / member.name).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"unsafe member: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"archive contains link: {member.name}")
        tf.extractall(root, filter="fully_trusted")


def _source_root(destination: Path) -> Path:
    roots = [p.parent for p in destination.glob("*/pyproject.toml")]
    if len(roots) != 1:
        raise ValueError(f"expected one source root, found {len(roots)}")
    return roots[0]


_PROBE = r'''
from __future__ import annotations
import csv, hashlib, json, math, pathlib, struct, threading
import numpy as np

_CONFIG = json.loads(pathlib.Path(__file__).with_name("probe_config.json").read_text())
_OUT = pathlib.Path(_CONFIG["output_dir"])
_OUT.mkdir(parents=True, exist_ok=True)
_LOCK = threading.RLock()
_STATE = {"global_eval": 0, "call_counter": 0, "budgets": [], "states": [], "trace": [], "installed": False, "active_result": None}

BUDGET_FIELDS = [
 "global_evaluation_ordinal","dsec_call_id","dsec_local_evaluation_index","temperature_k","temperature_t4","electron_fraction_xee","hydrogen_density_cm3",
 "h_heating","h_cooling","h_heating2","h_cooling2","he_heating","he_cooling","he_heating2","he_cooling2","he_type53_heating","he_type53_cooling","he_type53_heating2","he_type53_cooling2","he_non_type53_heating","he_non_type53_cooling","he_non_type53_heating2","he_non_type53_cooling2","mg_heating","mg_cooling","mg_heating2","mg_cooling2",
 "element_heating","element_cooling","element_heating2","element_cooling2","httot_pre_continuum","cltot_pre_continuum","httot2_pre_continuum","cltot2_pre_continuum",
 "continuum_heating","continuum_cooling","continuum_heating2","continuum_cooling2","htfreef","htcomp","clcomp","clbrems","cmp1","cmp2",
 "httot","cltot","httot2","cltot2","hmctot","elcter","non_type53_scope_note"
]
STATE_FIELDS = [
 "dsec_call_id","global_evaluation_ordinal","temperature_k","temperature_t4","electron_fraction_xee","covering_fraction","turbulent_velocity_km_s",
 "radiation_energy_count","radiation_energy_sha256","bremsa_count","bremsa_sha256","continuum_tau_in_count","continuum_tau_in_sha256","continuum_tau_out_count","continuum_tau_out_sha256",
 "opakc_before_count","opakc_before_sha256","brcems_before_count","brcems_before_sha256","global_xilevg_count","global_xilevg_sha256","global_bilevg_count","global_bilevg_sha256","global_rnisg_count","global_rnisg_sha256",
 "radiation_energy_l1","bremsa_l1","continuum_tau_in_l1","continuum_tau_out_l1","opakc_before_l1","brcems_before_l1","global_xilevg_l1","global_bilevg_l1","global_rnisg_l1"
]
TRACE_FIELDS = ["global_evaluation_ordinal","dsec_call_id","dsec_local_evaluation_index","temperature_k","temperature_t4","electron_fraction_xee","hmctot","elcter"]

def _array(value):
    if value is None: return np.zeros(0, dtype=np.float64)
    try: return np.asarray(value, dtype=np.float64).reshape(-1)
    except Exception: return np.zeros(0, dtype=np.float64)

def _fp(value):
    arr = _array(value)
    be = np.asarray(arr, dtype=">f8")
    return len(arr), hashlib.sha256(be.tobytes(order="C")).hexdigest(), float(np.sum(np.abs(arr), dtype=np.float64))

def _field(obj, *names):
    for name in names:
        if hasattr(obj, name): return getattr(obj, name)
    return None

def _element(result, z):
    return (float(result.htt.get(z, 0.0)), float(result.cll.get(z, 0.0)), float(result.htt2.get(z, 0.0)), float(result.cll2.get(z, 0.0)))

def _family_budget(result, z, data_type):
    for item in result.element_results:
        if int(item.request.element_z) != int(z): continue
        abundance = float(item.request.abundance)
        populations = np.asarray(item.equilibrium.solve.populations, dtype=float)
        heating = cooling = heating2 = cooling2 = 0.0
        for term in item.equilibrium.assembly.terms:
            if int(term.data_type) != int(data_type) or int(term.row) != int(term.column): continue
            row = int(term.row)
            if row < 1 or row > populations.size: continue
            pop = float(populations[row-1]) * abundance
            if float(term.cj) > 0.0: cooling += pop * float(term.cj)
            else: heating -= pop * float(term.cj)
            if float(term.cj2) > 0.0: cooling2 += pop * float(term.cj2)
            else: heating2 -= pop * float(term.cj2)
        return heating, cooling, heating2, cooling2
    return 0.0, 0.0, 0.0, 0.0

def install():
    if _STATE["installed"]: return
    from xstar_tools.xstar import dsec as dsec_mod
    original = dsec_mod.CalcHMCAllDsecEvaluator.__call__
    original_calc_hmc_all = dsec_mod.calc_hmc_all

    def streaming_calc_hmc_all(*args, **kwargs):
        # Keep only the current full result long enough for the wrapper to
        # reduce it to scalar/hashed audit rows.  Never append the large
        # H/He/Mg result object to the DSEC evaluation history.
        result = original_calc_hmc_all(*args, **kwargs)
        _STATE["active_result"] = result
        return result

    dsec_mod.calc_hmc_all = streaming_calc_hmc_all

    def wrapped(self, state):
        with _LOCK:
            call_id = getattr(self, "_v0487212_call_id", None)
            if call_id is None:
                _STATE["call_counter"] += 1
                call_id = int(_STATE["call_counter"])
                setattr(self, "_v0487212_call_id", call_id)
            local_eval = len(getattr(self, "evaluations", ())) + 1
            _STATE["global_eval"] += 1
            global_eval = int(_STATE["global_eval"])
        # The source workflow normally discards full fixed-state results when
        # diagnostics_mode=none.  Preserve that memory discipline and stream
        # the current result through the calc_hmc_all shim above.
        self.retain_fixed_state_results = False
        # Only the first evaluation of each DSEC call is part of the
        # between-call state-refresh contract.  Capturing every snapshot
        # causes v0.6.47.2 diagnostics=none runs to inspect the intentionally
        # lightweight prior-result namespace, which does not own the full
        # global-level mapping.  First-snapshot-only capture is observational,
        # avoids retaining source arrays, and leaves the physical state path
        # unchanged.
        self.capture_all_input_snapshots = False
        self.capture_input_snapshot_indices = (1,)
        _STATE["active_result"] = None
        print(f"v0487212_capture_begin call={call_id} local={local_eval} global={global_eval}", flush=True)
        try:
            out = original(self, state)
        except BaseException:
            _STATE["active_result"] = None
            raise
        result = _STATE.get("active_result")
        snap = self.input_snapshots[-1] if (local_eval == 1 and self.input_snapshots) else None
        with _LOCK:
            _STATE["trace"].append({
              "global_evaluation_ordinal": global_eval, "dsec_call_id": call_id, "dsec_local_evaluation_index": local_eval,
              "temperature_k": float(state.temperature_k), "temperature_t4": float(state.temperature_t4), "electron_fraction_xee": float(state.electron_fraction_xee),
              "hmctot": float(out.hmctot), "elcter": float(out.elcter),
            })
            if call_id == 1 and result is not None:
                h = _element(result, 1); he = _element(result, 2); mg = _element(result, 12); he53 = _family_budget(result, 2, 53)
                continuum = result.continuum
                diag = dict(getattr(continuum, "diagnostics", {}) or {})
                element_heating = sum(float(v) for v in result.htt.values())
                element_cooling = sum(float(v) for v in result.cll.values())
                element_heating2 = sum(float(v) for v in result.htt2.values())
                element_cooling2 = sum(float(v) for v in result.cll2.values())
                _STATE["budgets"].append({
                  "global_evaluation_ordinal": global_eval, "dsec_call_id": call_id, "dsec_local_evaluation_index": local_eval,
                  "temperature_k": float(result.temperature_k), "temperature_t4": float(result.temperature_k)/1e4,
                  "electron_fraction_xee": float(result.electron_fraction_xee), "hydrogen_density_cm3": float(result.hydrogen_density_cm3),
                  "h_heating": h[0], "h_cooling": h[1], "h_heating2": h[2], "h_cooling2": h[3],
                  "he_heating": he[0], "he_cooling": he[1], "he_heating2": he[2], "he_cooling2": he[3],
                  "he_type53_heating": he53[0], "he_type53_cooling": he53[1], "he_type53_heating2": he53[2], "he_type53_cooling2": he53[3],
                  "he_non_type53_heating": he[0]-he53[0], "he_non_type53_cooling": he[1]-he53[1], "he_non_type53_heating2": he[2]-he53[2], "he_non_type53_cooling2": he[3]-he53[3],
                  "mg_heating": mg[0], "mg_cooling": mg[1], "mg_heating2": mg[2], "mg_cooling2": mg[3],
                  "element_heating": element_heating, "element_cooling": element_cooling, "element_heating2": element_heating2, "element_cooling2": element_cooling2,
                  "httot_pre_continuum": float(result.httot_pre_continuum), "cltot_pre_continuum": float(result.cltot_pre_continuum),
                  "httot2_pre_continuum": float(result.httot2_pre_continuum), "cltot2_pre_continuum": float(result.cltot2_pre_continuum),
                  "continuum_heating": float(continuum.heating), "continuum_cooling": float(continuum.cooling),
                  "continuum_heating2": float(continuum.heating2), "continuum_cooling2": float(continuum.cooling2),
                  "htfreef": float(continuum.htfreef), "htcomp": float(continuum.htcomp), "clcomp": float(continuum.clcomp), "clbrems": float(continuum.clbrems),
                  "cmp1": float(diag.get("cmp1", float("nan"))), "cmp2": float(diag.get("cmp2", float("nan"))),
                  "httot": float(result.httot), "cltot": float(result.cltot), "httot2": float(result.httot2), "cltot2": float(result.cltot2),
                  "hmctot": float(result.hmctot), "elcter": float(result.elcter),
                  "non_type53_scope_note": "helium type53 and non-type53 budgets are reconstructed from source-ordered diagonal thermal terms and solved populations",
                })
            if local_eval == 1 and snap is not None:
                radiation = snap.radiation
                escape = snap.escape
                free_context = (snap.calc_kwargs or {}).get("free_free_context")
                brem_context = (snap.calc_kwargs or {}).get("bremem_context")
                values = {
                  "radiation_energy": _field(radiation, "epi_eV", "epi"), "bremsa": _field(radiation, "bremsa"),
                  "continuum_tau_in": _field(escape, "continuum_tau_in"), "continuum_tau_out": _field(escape, "continuum_tau_out"),
                  "opakc_before": _field(free_context, "opakc_before_cm_inv"), "brcems_before": _field(brem_context, "brcems_before"),
                  "global_xilevg": snap.global_xilevg_by_index, "global_bilevg": snap.global_bilevg_by_index, "global_rnisg": snap.global_rnisg_by_index,
                }
                row = {
                  "dsec_call_id": call_id, "global_evaluation_ordinal": global_eval, "temperature_k": float(snap.temperature_k), "temperature_t4": float(snap.temperature_t4),
                  "electron_fraction_xee": float(snap.electron_fraction_xee), "covering_fraction": float(snap.covering_fraction), "turbulent_velocity_km_s": float(snap.turbulent_velocity_km_s),
                }
                for key, value in values.items():
                    count, digest, l1 = _fp(value)
                    row[key + "_count"] = count; row[key + "_sha256"] = digest; row[key + "_l1"] = l1
                _STATE["states"].append(row)
        _STATE["active_result"] = None
        print(f"v0487212_capture_end call={call_id} local={local_eval} global={global_eval} hmctot={float(out.hmctot):.17g}", flush=True)
        return out
    dsec_mod.CalcHMCAllDsecEvaluator.__call__ = wrapped
    _STATE["installed"] = True

def finalize(run_summary=None):
    for name, fields, rows in [
      ("v0472_call1_thermal_budget.csv", BUDGET_FIELDS, _STATE["budgets"]),
      ("v0472_between_call_state_fingerprints.csv", STATE_FIELDS, _STATE["states"]),
      ("v0472_dsec_thermal_trace.csv", TRACE_FIELDS, _STATE["trace"]),
    ]:
        with (_OUT/name).open("w", newline="") as f:
            w=csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    report = {
      "schema": "xstar-tools-v0648721-v0472-thermal-budget-state-refresh-probe-v1", "release": "0.6.48.7.21.2",
      "result": "ACCEPT" if len(_STATE["budgets"]) >= 7 and len(_STATE["states"]) == 4 and len(_STATE["trace"]) >= 57 else "REJECT",
      "actual_v0472_runtime_capture": True, "call1_budget_rows": len(_STATE["budgets"]), "dsec_call_start_states": len(_STATE["states"]),
      "dsec_evaluations_observed": len(_STATE["trace"]), "run_summary": run_summary or {}, "qualification_only": True, "production_promotion_ready": False,
    }
    (_OUT/"capture_report.json").write_text(json.dumps(report, indent=2, sort_keys=True)+"\n")
    return report
'''

_DRIVER = r'''
from __future__ import annotations
import argparse, faulthandler, json, pathlib
faulthandler.enable(all_threads=True)
p=argparse.ArgumentParser(); p.add_argument("--parameters-json", required=True); p.add_argument("--atdb-path", required=True); p.add_argument("--output-dir", required=True); p.add_argument("--coheat-path")
a=p.parse_args()
import v048721_probe_runtime as probe
probe.install()
from xstar_tools.xstar.physical_runner import run_xstar_from_parameters
params=json.loads(pathlib.Path(a.parameters_json).read_text())
result=run_xstar_from_parameters(params, atdb_path=a.atdb_path, output_dir=a.output_dir, coheat_path=a.coheat_path, overwrite=True,
 diagnostics_mode="none", active_subset=True, profile_components="none", profile_rss=False, profile_backend_calls=False,
 profile_terminal=True, progress_debug=False, backend="python", rates_backend="python", matrix_backend="python", emissivity_backend="python", output_final_recompute=False)
summary={"ready":bool(result.ready),"completed_passes":int(result.completed_passes),"completed_zones":int(result.completed_zones),"output_dir":str(result.output_dir)}
report=probe.finalize(summary); print(json.dumps(report, indent=2, sort_keys=True)); raise SystemExit(0 if report["result"]=="ACCEPT" else 2)
'''


def capture(source_archive: Path, atdb_path: Path, output_dir: Path, parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    if _sha256(source_archive) != SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v048721_") as tmp:
        tmp_path = Path(tmp)
        _safe_extract(source_archive, tmp_path / "source")
        root = _source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"; probe_dir.mkdir()
        (probe_dir / "v048721_probe_runtime.py").write_text(_PROBE)
        (probe_dir / "probe_config.json").write_text(json.dumps({"output_dir": str(output_dir)}, indent=2))
        (probe_dir / "driver.py").write_text(_DRIVER)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(probe_dir), str(root / "src")])
        env["PYTHONFAULTHANDLER"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["OMP_NUM_THREADS"] = "1"
        env["OPENBLAS_NUM_THREADS"] = "1"
        env["MKL_NUM_THREADS"] = "1"
        env["NUMEXPR_NUM_THREADS"] = "1"
        cmd = [sys.executable, str(probe_dir / "driver.py"), "--parameters-json", str(parameters_json.resolve()), "--atdb-path", str(atdb_path.resolve()), "--output-dir", str(output_dir / "physical_run")]
        if coheat_path is not None: cmd += ["--coheat-path", str(coheat_path.resolve())]
        log = output_dir / "v0472_capture_run.log"
        with log.open("w") as f:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=f, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 capture failed with exit {completed.returncode}; see {log}")
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    files = {name: {"sha256": _sha256(output_dir / name), "size_bytes": (output_dir / name).stat().st_size} for name in (BUDGET_NAME, STATE_NAME, TRACE_NAME, REPORT_NAME, VERIFY_NAME)}
    _write_json(output_dir / MANIFEST_NAME, {**result, "immutable": result["result"] == "ACCEPT", "files": files})
    return result


def verify(bundle: Path) -> dict[str, Any]:
    errors: list[str] = []
    for name in (BUDGET_NAME, STATE_NAME, TRACE_NAME, REPORT_NAME):
        if not (bundle / name).is_file(): errors.append(f"missing:{name}")
    if errors:
        return {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": errors, "qualification_only": True, "production_promotion_ready": False}
    budgets = _read_csv(bundle / BUDGET_NAME); states = _read_csv(bundle / STATE_NAME); trace = _read_csv(bundle / TRACE_NAME)
    if len(budgets) < 7: errors.append(f"call1_budget_rows={len(budgets)}")
    if len(states) != 4: errors.append(f"call_start_states={len(states)}")
    if len(trace) < 57: errors.append(f"dsec_trace_rows={len(trace)}")
    if any(int(r["dsec_call_id"]) != 1 for r in budgets): errors.append("budget_not_call1_only")
    if [int(r["dsec_call_id"]) for r in states] != [1,2,3,4]: errors.append("call_state_inventory")
    changed_fields = []
    if len(states) == 4:
        hash_fields = [k for k in states[0] if k.endswith("_sha256")]
        for key in hash_fields:
            if len({r[key] for r in states}) > 1: changed_fields.append(key.removesuffix("_sha256"))
    report = json.loads((bundle / REPORT_NAME).read_text())
    if not report.get("actual_v0472_runtime_capture"): errors.append("not_actual_capture")
    return {
      "schema": VERIFY_SCHEMA, "release": RELEASE, "result": "ACCEPT" if not errors else "REJECT", "errors": errors,
      "actual_v0472_runtime_capture": bool(report.get("actual_v0472_runtime_capture")), "call1_budget_rows": len(budgets), "dsec_call_start_states": len(states),
      "dsec_evaluations_observed": len(trace), "between_call_changed_workspaces": changed_fields,
      "budget_sha256": _sha256(bundle / BUDGET_NAME), "state_fingerprints_sha256": _sha256(bundle / STATE_NAME), "trace_sha256": _sha256(bundle / TRACE_NAME),
      "qualification_only": True, "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture"); c.add_argument("source_archive", type=Path); c.add_argument("atdb_path", type=Path); c.add_argument("output_dir", type=Path); c.add_argument("parameters_json", type=Path); c.add_argument("--coheat-path", type=Path); c.add_argument("--output-json", type=Path)
    v = sub.add_parser("verify"); v.add_argument("bundle", type=Path); v.add_argument("--output-json", type=Path)
    a = p.parse_args(argv)
    try:
        result = capture(a.source_archive, a.atdb_path, a.output_dir, a.parameters_json, a.coheat_path) if a.cmd == "capture" else verify(a.bundle)
    except Exception as exc:
        result = {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)], "qualification_only": True, "production_promotion_ready": False}
    if a.output_json: _write_json(a.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2

if __name__ == "__main__": raise SystemExit(main())
