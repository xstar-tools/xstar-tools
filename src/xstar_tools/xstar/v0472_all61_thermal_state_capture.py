"""Capture all 61 v0.6.47.2 Thermal budgets and consumed state fingerprints.

The probe extends the accepted all-61 fixed-state capture.  It observes the 57
controller evaluations and four retained final evaluations without changing
source physics, branch order, or products.  Every row records the complete
H/He/Mg and continuum Thermal budget together with fingerprints of the arrays
and compact solved populations consumed by that budget.
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

from . import v0472_all61_fixed_state_capture as base

RELEASE = "0.6.48.7.46.17.2"
SCHEMA = "xstar-tools-v064874612-v0472-all61-thermal-state-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v064874612-v0472-all61-thermal-state-oracle-v1"
BUDGET_NAME = "v0472_all61_thermal_budget.csv"
REPORT_NAME = "all61_thermal_state_capture_report.json"
VERIFY_NAME = "all61_thermal_state_capture_verification.json"
MANIFEST_NAME = "all61_thermal_state_capture_manifest.json"
RUNTIME_REPORT_NAME = "capture_report.json"

THERMAL_FIELDS = [
    "sequence", "kind", "call_index", "evaluation_index", "temperature_k", "temperature_t4",
    "electron_fraction_input", "electron_density_cm3", "hydrogen_density_cm3",
    "covering_fraction", "turbulent_velocity_km_s",
    "input_dsec_radiation_count", "input_dsec_radiation_fingerprint",
    "input_bremsa_count", "input_bremsa_fingerprint",
    "input_tau_count", "input_tau_in_fingerprint", "input_tau_out_fingerprint",
    "input_global_level_count", "input_xilevg_fingerprint", "input_bilevg_fingerprint", "input_rnisg_fingerprint",
    "thermal_population_count", "thermal_population_fingerprint",
    "h_heating", "h_cooling", "h_heating2", "h_cooling2",
    "he_heating", "he_cooling", "he_heating2", "he_cooling2",
    "he_type53_heating", "he_type53_cooling", "he_type53_heating2", "he_type53_cooling2",
    "he_non_type53_heating", "he_non_type53_cooling", "he_non_type53_heating2", "he_non_type53_cooling2",
    "mg_heating", "mg_cooling", "mg_heating2", "mg_cooling2",
    "element_heating", "element_cooling", "element_heating2", "element_cooling2",
    "continuum_heating", "continuum_cooling", "continuum_heating2", "continuum_cooling2",
    "cmp1", "cmp2", "htcomp", "clcomp", "htfreef", "clbrems",
    "httot", "cltot", "httot2", "cltot2", "hmctot", "elcter",
]

_EXTRA_CODE = r'''
V04874612_THERMAL_FIELDS = __THERMAL_FIELDS__

def _v04874612_fnv64(value):
    import struct
    values = _array(value)
    digest = 1469598103934665603
    prime = 1099511628211
    for scalar in values:
        for byte in struct.pack("<d", float(scalar)):
            digest ^= int(byte)
            digest = (digest * prime) & 0xffffffffffffffff
    return int(values.size), f"{digest:016x}"

def _v04874612_capture_input(kind, call_id, evaluation_index, sequence, state):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    requests = tuple(getattr(state, "element_requests", ()) or ())
    request = requests[0] if requests else None
    radiation = _field(request, "radiation")
    escape = _field(request, "escape")
    energy = _field(radiation, "epi_eV", "epi")
    bremsa = _field(radiation, "bremsa")
    tau_in = _field(escape, "continuum_tau_in")
    tau_out = _field(escape, "continuum_tau_out")
    gx = getattr(state, "global_xilevg_by_index", None)
    gb = getattr(state, "global_bilevg_by_index", None)
    gr = getattr(state, "global_rnisg_by_index", None)
    ec, ef = _v04874612_fnv64(energy)
    bc, bf = _v04874612_fnv64(bremsa)
    tic, tif = _v04874612_fnv64(tau_in)
    toc, tof = _v04874612_fnv64(tau_out)
    gxc, gxf = _v04874612_fnv64(gx)
    gbc, gbf = _v04874612_fnv64(gb)
    grc, grf = _v04874612_fnv64(gr)
    if tic != toc or gxc != gbc or gxc != grc:
        raise RuntimeError("v46.12 input state array inventory mismatch")
    _STATE.setdefault("all61_thermal_inputs", {})[int(sequence)] = {
      "input_dsec_radiation_count": ec, "input_dsec_radiation_fingerprint": ef,
      "input_bremsa_count": bc, "input_bremsa_fingerprint": bf,
      "input_tau_count": tic, "input_tau_in_fingerprint": tif, "input_tau_out_fingerprint": tof,
      "input_global_level_count": gxc, "input_xilevg_fingerprint": gxf,
      "input_bilevg_fingerprint": gbf, "input_rnisg_fingerprint": grf,
      "temperature_k": float(state.temperature_k),
      "electron_fraction_input": float(state.electron_fraction_xee),
      "covering_fraction": float(_field(request, "covering_fraction") or 0.0),
      "turbulent_velocity_km_s": float(_field(request, "turbulent_velocity_km_s") or 0.0),
    }

def _v04874612_capture_result(kind, call_id, evaluation_index, sequence, result):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    source_input = _STATE.setdefault("all61_thermal_inputs", {}).get(int(sequence))
    if source_input is None:
        raise RuntimeError(f"missing v46.12 Thermal input fingerprint for sequence {sequence}")
    h = _element(result, 1); he = _element(result, 2); mg = _element(result, 12)
    he53 = _family_budget(result, 2, 53)
    compact = []
    for item in tuple(getattr(result, "element_results", ()) or ()):
        request = getattr(item, "request", None)
        if int(_field(request, "element_z") or 0) not in (1,2,12):
            continue
        solve = getattr(getattr(item, "equilibrium", None), "solve", None)
        if solve is not None:
            compact.extend(float(v) for v in _array(getattr(solve, "populations", None)))
    pc, pf = _v04874612_fnv64(compact)
    continuum = result.continuum
    diag = dict(getattr(continuum, "diagnostics", {}) or {})
    element_heating = sum(float(v) for v in result.htt.values())
    element_cooling = sum(float(v) for v in result.cll.values())
    element_heating2 = sum(float(v) for v in result.htt2.values())
    element_cooling2 = sum(float(v) for v in result.cll2.values())
    row = {
      "sequence": int(sequence), "kind": str(kind), "call_index": int(call_id),
      "evaluation_index": int(evaluation_index), "temperature_k": float(source_input["temperature_k"]),
      "temperature_t4": float(source_input["temperature_k"])/1.0e4,
      "electron_fraction_input": float(source_input["electron_fraction_input"]),
      "electron_density_cm3": float(result.hydrogen_density_cm3) * float(source_input["electron_fraction_input"]),
      "hydrogen_density_cm3": float(result.hydrogen_density_cm3),
      "covering_fraction": float(source_input["covering_fraction"]),
      "turbulent_velocity_km_s": float(source_input["turbulent_velocity_km_s"]),
      "thermal_population_count": pc, "thermal_population_fingerprint": pf,
      "h_heating": h[0], "h_cooling": h[1], "h_heating2": h[2], "h_cooling2": h[3],
      "he_heating": he[0], "he_cooling": he[1], "he_heating2": he[2], "he_cooling2": he[3],
      "he_type53_heating": he53[0], "he_type53_cooling": he53[1],
      "he_type53_heating2": he53[2], "he_type53_cooling2": he53[3],
      "he_non_type53_heating": he[0]-he53[0], "he_non_type53_cooling": he[1]-he53[1],
      "he_non_type53_heating2": he[2]-he53[2], "he_non_type53_cooling2": he[3]-he53[3],
      "mg_heating": mg[0], "mg_cooling": mg[1], "mg_heating2": mg[2], "mg_cooling2": mg[3],
      "element_heating": element_heating, "element_cooling": element_cooling,
      "element_heating2": element_heating2, "element_cooling2": element_cooling2,
      "continuum_heating": float(continuum.heating), "continuum_cooling": float(continuum.cooling),
      "continuum_heating2": float(continuum.heating2), "continuum_cooling2": float(continuum.cooling2),
      "cmp1": float(diag.get("cmp1", float("nan"))), "cmp2": float(diag.get("cmp2", float("nan"))),
      "htcomp": float(continuum.htcomp), "clcomp": float(continuum.clcomp),
      "htfreef": float(continuum.htfreef), "clbrems": float(continuum.clbrems),
      "httot": float(result.httot), "cltot": float(result.cltot),
      "httot2": float(result.httot2), "cltot2": float(result.cltot2),
      # In the frozen Python result contract, elcter is the charge residual
      # (input electron fraction minus the computed charge sum).
      "hmctot": float(result.hmctot), "elcter": float(result.elcter),
    }
    row.update(source_input)
    _STATE.setdefault("all61_thermal", []).append(row)

def _v04874612_write_thermal():
    rows = sorted(_STATE.setdefault("all61_thermal", []), key=lambda row: int(row["sequence"]))
    with (_OUT / "__BUDGET_NAME__").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=V04874612_THERMAL_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
'''.replace("__THERMAL_FIELDS__", repr(THERMAL_FIELDS)).replace("__BUDGET_NAME__", BUDGET_NAME)

_PROBE = base._PROBE
anchor = "def _v048742_capture_input(kind, call_id, evaluation_index, sequence, state):"
if anchor not in _PROBE:
    raise RuntimeError("all-61 source capture input anchor missing")
_PROBE = _PROBE.replace(anchor, _EXTRA_CODE + "\n\n" + anchor, 1)
_V04874612_INPUT_HOOK = (
    "def _v048742_capture_input(kind, call_id, evaluation_index, sequence, state):\n"
    "    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)\n"
)
if _PROBE.count(_V04874612_INPUT_HOOK) != 1:
    raise RuntimeError("all-61 source capture input-hook target missing or ambiguous")
_PROBE = _PROBE.replace(
    _V04874612_INPUT_HOOK,
    _V04874612_INPUT_HOOK
    + "    _v04874612_capture_input(kind, call_id, evaluation_index, sequence, state)\n",
    1,
)
_PROBE = _PROBE.replace(
    "def _v048742_capture(kind, call_id, evaluation_index, sequence, state, result):\n    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)",
    "def _v048742_capture(kind, call_id, evaluation_index, sequence, state, result):\n    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)\n    _v04874612_capture_result(kind, call_id, evaluation_index, sequence, result)",
    1,
)


def _validate_generated_probe_input_hook(probe: str) -> None:
    helper_start = probe.find("def _v04874612_capture_input(")
    helper_end = probe.find("\ndef _v04874612_capture_result(", helper_start)
    base_start = probe.find("def _v048742_capture_input(")
    base_end = probe.find("\ndef _v048744_capture_solve_rows(", base_start)
    if min(helper_start, helper_end, base_start, base_end) < 0:
        raise RuntimeError("v46.12 generated probe input-hook functions missing")
    helper_body = probe[helper_start:helper_end]
    base_body = probe[base_start:base_end]
    # The helper definition itself is the only allowed occurrence in its body.
    if helper_body.count("_v04874612_capture_input(") != 1:
        raise RuntimeError("v46.12 generated probe contains a recursive Thermal input hook")
    if base_body.count("_v04874612_capture_input(") != 1:
        raise RuntimeError("v46.12 Thermal input hook is not installed in _v048742_capture_input")


_validate_generated_probe_input_hook(_PROBE)
_PROBE = _PROBE.replace(
    "def finalize(run_summary=None):\n    _v048742_write_all61()",
    "def finalize(run_summary=None):\n    _v048742_write_all61()\n    _v04874612_write_thermal()",
    1,
)
_PROBE = _PROBE.replace(
    '"all61_evaluations_observed": len(_STATE["all61_states"]),',
    '"all61_evaluations_observed": len(_STATE["all61_states"]), "all61_thermal_rows": len(_STATE.get("all61_thermal", [])),',
    1,
)
_PROBE = _PROBE.replace(f'"release": "{base.RELEASE}"', f'"release": "{RELEASE}"')
compile(_PROBE, "<v04874612-all61-thermal-probe>", "exec")

_DRIVER = base._DRIVER.replace("import v048744_all61_probe_runtime as probe", "import v04874612_all61_thermal_probe_runtime as probe")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _normalize_capture_reports(bundle: Path) -> dict[str, Any]:
    """Materialize canonical fixed-state and Thermal report names.

    The injected runtime writes ``capture_report.json``.  The parent fixed-state
    capture normally renames that file, but this derived Thermal capture runs
    the injected driver directly.  Normalize all three names without deleting
    the historical runtime report so an accepted capture can be resumed.
    """
    bundle = bundle.resolve()
    runtime_path = bundle / RUNTIME_REPORT_NAME
    fixed_path = bundle / base.REPORT_NAME
    thermal_path = bundle / REPORT_NAME
    source_path = next((path for path in (runtime_path, fixed_path, thermal_path) if path.is_file()), None)
    if source_path is None:
        return {
            "normalized": False,
            "source_report": None,
            "fixed_state_report": fixed_path.name,
            "thermal_report": thermal_path.name,
        }
    report = json.loads(source_path.read_text(encoding="utf-8"))
    if source_path == runtime_path or not fixed_path.is_file():
        _write_json(fixed_path, report)
    thermal_report = dict(report)
    thermal_report.update({
        "schema": SCHEMA,
        "release": RELEASE,
        "all61_thermal_rows": len(_read_csv(bundle / BUDGET_NAME)) if (bundle / BUDGET_NAME).is_file() else 0,
        "source_report_name": source_path.name,
        "fixed_state_report_name": fixed_path.name,
    })
    _write_json(thermal_path, thermal_report)
    return {
        "normalized": True,
        "source_report": source_path.name,
        "fixed_state_report": fixed_path.name,
        "thermal_report": thermal_path.name,
    }


def verify(bundle: Path) -> dict[str, Any]:
    errors: list[str] = []
    normalization = _normalize_capture_reports(bundle)
    base_result = base.verify(bundle)
    if base_result.get("result") != "ACCEPT":
        errors.extend(f"fixed_state:{item}" for item in base_result.get("errors", []))
    path = bundle / BUDGET_NAME
    if not path.is_file():
        errors.append(f"missing:{BUDGET_NAME}")
        rows: list[dict[str, str]] = []
    else:
        rows = _read_csv(path)
    if len(rows) != 61 or [int(row["sequence"]) for row in rows] != list(range(1, 62)):
        errors.append(f"thermal_inventory={len(rows)}")
    kinds = [row.get("kind", "") for row in rows]
    if kinds.count("dsec") != 57 or kinds.count("final") != 4:
        errors.append(f"thermal_kind_inventory=dsec:{kinds.count('dsec')},final:{kinds.count('final')}")
    finite_fields = [name for name in THERMAL_FIELDS if name not in {
        "kind", "input_dsec_radiation_fingerprint", "input_bremsa_fingerprint",
        "input_tau_in_fingerprint", "input_tau_out_fingerprint", "input_xilevg_fingerprint",
        "input_bilevg_fingerprint", "input_rnisg_fingerprint", "thermal_population_fingerprint",
    }]
    import math
    for row in rows:
        for name in finite_fields:
            try:
                if not math.isfinite(float(row[name])):
                    raise ValueError
            except Exception:
                errors.append(f"nonfinite:{row.get('sequence')}:{name}")
                break
    report = json.loads((bundle / base.REPORT_NAME).read_text()) if (bundle / base.REPORT_NAME).is_file() else {}
    return {
        "schema": VERIFY_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "actual_v0472_runtime_capture": bool(report.get("actual_v0472_runtime_capture")),
        "evaluations": len(rows),
        "dsec_evaluations": kinds.count("dsec"),
        "final_evaluations": kinds.count("final"),
        "thermal_fields": len(THERMAL_FIELDS),
        "fixed_state_capture_result": base_result.get("result", "REJECT"),
        "workspace_paths_rebased": int(base_result.get("workspace_paths_rebased", 0)),
        "workspace_paths_recorded_valid": int(base_result.get("workspace_paths_recorded_valid", 0)),
        "report_normalization": normalization,
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    if base.base.base._sha256(source_archive) != base.base.base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v04874612_") as tmp:
        tmp_path = Path(tmp)
        base.base.base._safe_extract(source_archive, tmp_path / "source")
        root = base.base.base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"; probe_dir.mkdir()
        (probe_dir / "v04874612_all61_thermal_probe_runtime.py").write_text(_PROBE)
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
        log = output_dir / "v0472_all61_thermal_capture_run.log"
        with log.open("w") as handle:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 all-61 Thermal capture failed with exit {completed.returncode}; see {log}")
    _normalize_capture_reports(output_dir)
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    files = {}
    for name in (BUDGET_NAME, REPORT_NAME, VERIFY_NAME):
        path = output_dir / name
        files[name] = {"sha256": base.base.base._sha256(path), "size_bytes": path.stat().st_size}
    _write_json(output_dir / MANIFEST_NAME, {**result, "immutable": result["result"] == "ACCEPT", "files": files})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("source_archive", type=Path); cap.add_argument("atdb_path", type=Path)
    cap.add_argument("output_dir", type=Path); cap.add_argument("parameters_json", type=Path)
    cap.add_argument("--coheat-path", type=Path); cap.add_argument("--output-json", type=Path)
    ver = sub.add_parser("verify"); ver.add_argument("bundle", type=Path); ver.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = capture(args.source_archive, args.atdb_path, args.output_dir, args.parameters_json, args.coheat_path) if args.cmd == "capture" else verify(args.bundle)
    except Exception as exc:
        result = {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "qualification_only": True, "production_promotion_ready": False}
    if args.cmd == "verify":
        _write_json(args.bundle / VERIFY_NAME, result)
        files: dict[str, dict[str, Any]] = {}
        for name in (BUDGET_NAME, base.REPORT_NAME, REPORT_NAME, VERIFY_NAME):
            path = args.bundle / name
            if path.is_file():
                files[name] = {"sha256": base.base.base._sha256(path), "size_bytes": path.stat().st_size}
        _write_json(args.bundle / MANIFEST_NAME, {**result, "immutable": result["result"] == "ACCEPT", "files": files})
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
