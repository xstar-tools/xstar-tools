"""Capture exact v0.6.47.2 calc_emis/gsmooth/heatt continuum state for v82 patch 5.20.

This qualification-only probe extends the accepted 5.19.4.1 source runtime
capture.  It records the source ``calc_emis_all`` selected RRC identities and
the literal per-bin state consumed/produced by ``gsmooth`` and ``heatt``.
No captured values are used by production code.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import v0472_all61_type88_rate_lifetime_capture_v82_patch51941 as base

RELEASE = "0.6.48.7.46.25.5.17.25.82-patch5.20"
SCHEMA = "xstar-tools-v82-patch520-v0472-heatt-zrems-running-sum-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v82-patch520-v0472-heatt-zrems-running-sum-oracle-v1"
HEATT_NAME = "v0472_all61_heatt_zrems_running_sum.csv"
CALC_EMIS_NAME = "v0472_all61_calc_emis_selection_summary.csv"
REPORT_NAME = "all61_heatt_zrems_running_sum_capture_report.json"
VERIFY_NAME = "all61_heatt_zrems_running_sum_capture_verification.json"
BUNDLE_MANIFEST_NAME = "all61_heatt_zrems_running_sum_capture_manifest.json"

_PROBE = base._PROBE
_PROBE = _PROBE.replace(
    '"type88_rate_lifetime": [], "type88_rate_last": {}, "active_call_id": 0, "active_local_eval": 0, '
    '"linear_solve_trace_current": [], "final_counter": 0}',
    '"type88_rate_lifetime": [], "type88_rate_last": {}, "active_call_id": 0, "active_local_eval": 0, '
    '"patch520_heatt_rows": [], "patch520_calc_emis_summary": [], "patch520_last_gsmooth": None, '
    '"patch520_calc_emis_event": 0, "patch520_heatt_event": 0, '
    '"linear_solve_trace_current": [], "final_counter": 0}',
    1,
)

_PATCH520_CODE = r'''
V82_PATCH520_HEATT_FIELDS = [
 "sequence","dsec_call_id","evaluation_index","heatt_event","calc_emis_event","runtime_slot","energy_ev","radius_cm","zone_thickness_cm",
 "covering_fraction","fpr2","pre_bremsa","zremso1",
 "pre_gsmooth_opakc","pre_gsmooth_brcems","pre_gsmooth_rccemis1","pre_gsmooth_rccemis2",
 "post_gsmooth_opakc","post_gsmooth_brcems","post_gsmooth_rccemis1","post_gsmooth_rccemis2",
 "heatt_optp2","heatt_tau","heatt_fac","heatt_tmph","heatt_tmpc1","heatt_tmpc2",
 "heatt_tmpc_total","heatt_plane1_delta","heatt_plane1_replay","post_heatt_zrems1",
 "plane1_replay_bit_equal"
]
V82_PATCH520_CALC_EMIS_FIELDS = [
 "sequence","dsec_call_id","evaluation_index","calc_emis_event","hydrogen_density_cm3","electron_density_cm3","temperature_t4","covering_fraction",
 "rate7_rows","rate7_unique_slots","rate7_type49_rows","rate7_type53_rows","rate7_type99_rows",
 "rate42_rows","rate42_type88_rows","selected_slot_list","rate42_record_list",
 "rccemis1_nonzero","rccemis2_nonzero","rccemis1_sum","rccemis2_sum"
]

def _v82_patch520_install_continuum_wrappers():
    from xstar_tools.xstar import emergent_emissivity as ee
    from xstar_tools.xstar import radial_transfer as rt
    from xstar_tools.xstar import heatt as heatt_mod
    if getattr(ee.calc_emis_all, "_v82_patch520_wrapped", False):
        return

    original_calc_emis_all = ee.calc_emis_all
    def wrapped_calc_emis_all(context):
        result = original_calc_emis_all(context)
        _STATE["patch520_calc_emis_event"] = int(_STATE.get("patch520_calc_emis_event", 0)) + 1
        event = int(_STATE["patch520_calc_emis_event"])
        traces = list(getattr(result, "record_traces", ()) or ())
        rate7 = [r for r in traces if int(getattr(r, "rate_type", 0)) == 7]
        rate42 = [r for r in traces if int(getattr(r, "rate_type", 0)) == 42]
        slots = sorted({int(getattr(r, "retained_continuum_index", 0)) for r in rate7 if int(getattr(r, "retained_continuum_index", 0)) > 0})
        ws = getattr(context, "workspace", None)
        rcc = np.asarray(getattr(getattr(ws, "base", None), "rccemis", np.zeros((2,0))), dtype=float)
        row = {
          "sequence": int(_STATE.get("global_eval", 0) or 0),
          "dsec_call_id": int(_STATE.get("active_call_id", 0) or 0),
          "evaluation_index": int(_STATE.get("active_local_eval", 0) or 0),
          "calc_emis_event": event,
          "hydrogen_density_cm3": float(getattr(result, "hydrogen_density_cm3", float("nan"))),
          "electron_density_cm3": float(getattr(result, "electron_density_cm3", float("nan"))),
          "temperature_t4": float(getattr(context, "temperature_1e4K", float("nan"))),
          "covering_fraction": float(getattr(context, "covering_fraction", float("nan"))),
          "rate7_rows": len(rate7), "rate7_unique_slots": len(slots),
          "rate7_type49_rows": sum(int(getattr(r, "data_type", 0)) == 49 for r in rate7),
          "rate7_type53_rows": sum(int(getattr(r, "data_type", 0)) == 53 for r in rate7),
          "rate7_type99_rows": sum(int(getattr(r, "data_type", 0)) == 99 for r in rate7),
          "rate42_rows": len(rate42),
          "rate42_type88_rows": sum(int(getattr(r, "data_type", 0)) == 88 for r in rate42),
          "selected_slot_list": ";".join(str(x) for x in slots),
          "rate42_record_list": ";".join(str(int(getattr(r, "record", 0))) for r in rate42),
          "rccemis1_nonzero": int(np.count_nonzero(rcc[0])) if rcc.ndim == 2 and rcc.shape[0] >= 2 else 0,
          "rccemis2_nonzero": int(np.count_nonzero(rcc[1])) if rcc.ndim == 2 and rcc.shape[0] >= 2 else 0,
          "rccemis1_sum": float(np.sum(rcc[0])) if rcc.ndim == 2 and rcc.shape[0] >= 2 else 0.0,
          "rccemis2_sum": float(np.sum(rcc[1])) if rcc.ndim == 2 and rcc.shape[0] >= 2 else 0.0,
        }
        _STATE["patch520_calc_emis_summary"].append(row)
        return result
    wrapped_calc_emis_all._v82_patch520_wrapped = True
    ee.calc_emis_all = wrapped_calc_emis_all

    original_gsmooth = rt.apply_gsmooth_to_state
    def wrapped_gsmooth(state):
        ws = rt._workspace_from_state(state)
        n = int(state.control["ncn2"])
        pre = {
          "opakc": np.asarray(ws.opakc[:n], dtype=float).copy(),
          "brcems": np.asarray(ws.emissivity.base.brcems[:n], dtype=float).copy(),
          "rcc1": np.asarray(ws.rccemis[0,:n], dtype=float).copy(),
          "rcc2": np.asarray(ws.rccemis[1,:n], dtype=float).copy(),
        }
        result = original_gsmooth(state)
        _STATE["patch520_last_gsmooth"] = {
          "calc_emis_event": int(_STATE.get("patch520_calc_emis_event", 0)),
          "pre": pre,
          "post": {
            "opakc": np.asarray(ws.opakc[:n], dtype=float).copy(),
            "brcems": np.asarray(ws.emissivity.base.brcems[:n], dtype=float).copy(),
            "rcc1": np.asarray(ws.rccemis[0,:n], dtype=float).copy(),
            "rcc2": np.asarray(ws.rccemis[1,:n], dtype=float).copy(),
          },
        }
        return result
    wrapped_gsmooth._v82_patch520_wrapped = True
    rt.apply_gsmooth_to_state = wrapped_gsmooth

    original_heatt = rt.apply_heatt_to_state
    def wrapped_heatt(state):
        ws = rt._workspace_from_state(state)
        n = int(state.control["ncn2"])
        context = state.control.get("calc_emis_context")
        covering = float(getattr(context, "covering_fraction", state.control.get("cfrac", 1.0)))
        radius = float(state.transfer.radius)
        delrl = float(state.transfer.step_size)
        epi = np.asarray(state.radiation.epi[:n], dtype=float).copy()
        incident = np.asarray(state.radiation.bremsa[:n], dtype=float).copy()
        old = np.asarray(ws.zremso[0,:n], dtype=float).copy()
        opakc = np.asarray(ws.opakc[:n], dtype=float).copy()
        brc = np.asarray(ws.emissivity.base.brcems[:n], dtype=float).copy()
        rcc1 = np.asarray(ws.rccemis[0,:n], dtype=float).copy()
        rcc2 = np.asarray(ws.rccemis[1,:n], dtype=float).copy()
        last = _STATE.get("patch520_last_gsmooth") or {}
        pre = last.get("pre") or {"opakc":opakc,"brcems":brc,"rcc1":rcc1,"rcc2":rcc2}
        post = last.get("post") or {"opakc":opakc,"brcems":brc,"rcc1":rcc1,"rcc2":rcc2}
        _STATE["patch520_heatt_event"] = int(_STATE.get("patch520_heatt_event", 0)) + 1
        event = int(_STATE["patch520_heatt_event"])
        calc_event = int(last.get("calc_emis_event", _STATE.get("patch520_calc_emis_event", 0)))
        result = original_heatt(state)
        after = np.asarray(ws.zrems[0,:n], dtype=float)
        fpr2 = heatt_mod.XSTAR_HEATT_FOUR_PI * (radius * heatt_mod.XSTAR_HEATT_RADIUS_SCALE) ** 2
        for kl in range(n):
            optp2 = max(heatt_mod.XSTAR_HEATT_OPACITY_FLOOR, float(opakc[kl]))
            tau = optp2 * delrl
            fac = heatt_mod._source_fac(tau)
            tmph = float(incident[kl]) * optp2
            tmpc1 = float(rcc1[kl]) + float(brc[kl]) * (1.0 - covering) / 2.0
            tmpc2 = float(rcc2[kl]) + float(brc[kl]) * (1.0 + covering) / 2.0
            total = heatt_mod.XSTAR_HEATT_FOUR_PI * (tmpc1 + tmpc2)
            delta = (tmph - total) * fac * delrl * fpr2
            replay = max(0.0, float(old[kl]) - delta)
            actual = float(after[kl])
            bit_equal = int(struct.pack(">d", replay) == struct.pack(">d", actual))
            _STATE["patch520_heatt_rows"].append({
              "sequence":int(_STATE.get("global_eval", 0) or 0),
              "dsec_call_id":int(_STATE.get("active_call_id", 0) or 0),
              "evaluation_index":int(_STATE.get("active_local_eval", 0) or 0),
              "heatt_event":event,"calc_emis_event":calc_event,"runtime_slot":kl,
              "energy_ev":float(epi[kl]),"radius_cm":radius,"zone_thickness_cm":delrl,
              "covering_fraction":covering,"fpr2":fpr2,"pre_bremsa":float(incident[kl]),
              "zremso1":float(old[kl]),
              "pre_gsmooth_opakc":float(pre["opakc"][kl]),"pre_gsmooth_brcems":float(pre["brcems"][kl]),
              "pre_gsmooth_rccemis1":float(pre["rcc1"][kl]),"pre_gsmooth_rccemis2":float(pre["rcc2"][kl]),
              "post_gsmooth_opakc":float(post["opakc"][kl]),"post_gsmooth_brcems":float(post["brcems"][kl]),
              "post_gsmooth_rccemis1":float(post["rcc1"][kl]),"post_gsmooth_rccemis2":float(post["rcc2"][kl]),
              "heatt_optp2":optp2,"heatt_tau":tau,"heatt_fac":fac,"heatt_tmph":tmph,
              "heatt_tmpc1":tmpc1,"heatt_tmpc2":tmpc2,"heatt_tmpc_total":total,
              "heatt_plane1_delta":delta,"heatt_plane1_replay":replay,
              "post_heatt_zrems1":actual,"plane1_replay_bit_equal":bit_equal,
            })
        return result
    wrapped_heatt._v82_patch520_wrapped = True
    rt.apply_heatt_to_state = wrapped_heatt
'''

_PROBE = _PROBE.replace("V82_PATCH51941_TYPE88_TARGET_RECORDS = {40294, 40379, 40380}", _PATCH520_CODE + "\nV82_PATCH51941_TYPE88_TARGET_RECORDS = {40294, 40379, 40380}", 1)
_PROBE = _PROBE.replace(
    "    _v82_patch51941_install_type88_lifetime_wrapper()\n    _STATE[\"installed\"] = True\n",
    "    _v82_patch51941_install_type88_lifetime_wrapper()\n    _v82_patch520_install_continuum_wrappers()\n    _STATE[\"installed\"] = True\n",
    1,
)
_PROBE = _PROBE.replace(
    '      "v0472_all61_type88_rate_lifetime.csv": lambda row: (int(row["sequence"]), int(row["record"]), int(row["observation_index"])),\n',
    '      "v0472_all61_type88_rate_lifetime.csv": lambda row: (int(row["sequence"]), int(row["record"]), int(row["observation_index"])),\n'
    '      "v0472_all61_heatt_zrems_running_sum.csv": lambda row: (int(row["heatt_event"]), int(row["runtime_slot"])),\n'
    '      "v0472_all61_calc_emis_selection_summary.csv": lambda row: int(row["calc_emis_event"]),\n',
    1,
)
_PROBE = _PROBE.replace(
    '      ("v0472_all61_type88_rate_lifetime.csv", V82_PATCH51941_TYPE88_RATE_LIFETIME_FIELDS, _STATE["type88_rate_lifetime"]),\n',
    '      ("v0472_all61_type88_rate_lifetime.csv", V82_PATCH51941_TYPE88_RATE_LIFETIME_FIELDS, _STATE["type88_rate_lifetime"]),\n'
    '      ("v0472_all61_heatt_zrems_running_sum.csv", V82_PATCH520_HEATT_FIELDS, _STATE["patch520_heatt_rows"]),\n'
    '      ("v0472_all61_calc_emis_selection_summary.csv", V82_PATCH520_CALC_EMIS_FIELDS, _STATE["patch520_calc_emis_summary"]),\n',
    1,
)
_PROBE = _PROBE.replace(f'"schema": "{base.SCHEMA}"', f'"schema": "{SCHEMA}"')

_DRIVER = base._DRIVER.replace(
    "import v82_patch51941_type88_lifetime_probe_runtime as probe",
    "import v82_patch520_heatt_zrems_probe_runtime as probe",
)


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


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
        errors.append("parent_51941_source_capture_reject")
    heatt_path = bundle / HEATT_NAME
    calc_path = bundle / CALC_EMIS_NAME
    heatt = _read_csv(heatt_path) if heatt_path.is_file() else []
    calc = _read_csv(calc_path) if calc_path.is_file() else []
    if not heatt:
        errors.append(f"missing_or_empty:{HEATT_NAME}")
    if not calc:
        errors.append(f"missing_or_empty:{CALC_EMIS_NAME}")
    events = sorted({int(r["heatt_event"]) for r in heatt}) if heatt else []
    bad_replay = sum(int(r.get("plane1_replay_bit_equal", "0")) != 1 for r in heatt)
    if bad_replay:
        errors.append(f"heatt_plane1_replay_bit_mismatches={bad_replay}")
    rows_per_event: dict[int, int] = {}
    for r in heatt:
        e = int(r["heatt_event"]); rows_per_event[e] = rows_per_event.get(e, 0) + 1
    if any(v <= 0 for v in rows_per_event.values()):
        errors.append("empty_heatt_event")
    selected_rate7 = [int(r.get("rate7_rows", "0")) for r in calc]
    rate42 = [int(r.get("rate42_type88_rows", "0")) for r in calc]
    if not any(v > 0 for v in selected_rate7):
        errors.append("no_selected_rate7_rrc_rows")
    # Type-88 rate-42 is source-owned and must be observed, even though it is
    # not part of the public ncbin selection branch.
    if not any(v > 0 for v in rate42):
        errors.append("no_rate42_type88_rows")
    return {
        "schema": VERIFY_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "qualification_only": True,
        "production_promotion_ready": False,
        "actual_v0472_runtime_capture": True,
        "source_record_level_terms_available": bool(parent.get("source_record_level_terms_available", False)),
        "heatt_rows": len(heatt),
        "heatt_events": len(events),
        "heatt_rows_per_event": {str(k): v for k, v in sorted(rows_per_event.items())},
        "heatt_plane1_replay_bit_mismatches": bad_replay,
        "calc_emis_events": len(calc),
        "max_selected_rate7_rows": max(selected_rate7, default=0),
        "max_rate42_type88_rows": max(rate42, default=0),
    }


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_sha = base.base.base.base.base.base._sha256(source_archive)
    expected_sha = base.base.base.base.base.base.SOURCE_ARCHIVE_SHA256
    if source_sha != expected_sha:
        raise ValueError(f"v0.6.47.2 source archive hash mismatch: {source_sha}")
    with tempfile.TemporaryDirectory(prefix="v82_patch520_source_") as tmp:
        tmp_path = Path(tmp)
        helper = base.base.base.base.base.base
        helper._safe_extract(source_archive, tmp_path / "source")
        root = helper._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        (probe_dir / "v82_patch520_heatt_zrems_probe_runtime.py").write_text(_PROBE)
        (probe_dir / "probe_config.json").write_text(json.dumps({"output_dir": str(output_dir)}, indent=2))
        (probe_dir / "driver.py").write_text(_DRIVER)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(probe_dir), str(root / "src")])
        env.update({"PYTHONFAULTHANDLER":"1","PYTHONUNBUFFERED":"1","OMP_NUM_THREADS":"1",
                    "OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1","NUMEXPR_NUM_THREADS":"1"})
        cmd = [sys.executable, str(probe_dir / "driver.py"), "--parameters-json", str(parameters_json.resolve()),
               "--atdb-path", str(atdb_path.resolve()), "--output-dir", str(output_dir / "physical_run")]
        if coheat_path is not None:
            cmd += ["--coheat-path", str(coheat_path.resolve())]
        log = output_dir / "v0472_all61_heatt_zrems_running_sum_capture_run.log"
        with log.open("w") as handle:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 heatt/zrems capture failed with exit {completed.returncode}; see {log}")
    historical = output_dir / "capture_report.json"
    if historical.is_file():
        # Every nested verifier owns a differently named copy of the single
        # authoritative runtime report.  Preserve all of them before renaming.
        report_names = {
            base.base.base.REPORT_NAME,
            base.base.REPORT_NAME,
            base.REPORT_NAME,
            REPORT_NAME,
        }
        for name in report_names:
            shutil.copy2(historical, output_dir / name)
        historical.unlink()
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    files: dict[str, Any] = {}
    for path in sorted(output_dir.glob("v0472_all61_*.csv")):
        files[path.name] = {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
    for name in (REPORT_NAME, VERIFY_NAME):
        path = output_dir / name
        if path.is_file():
            files[name] = {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
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
        result = capture(args.source_archive, args.atdb_path, args.output_dir, args.parameters_json, args.coheat_path) \
            if args.command == "capture" else verify(args.bundle)
    except Exception as exc:
        result = {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "qualification_only": True, "production_promotion_ready": False}
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
