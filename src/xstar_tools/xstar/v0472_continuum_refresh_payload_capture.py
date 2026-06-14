"""Capture full v0.6.47.2 between-call workspace payloads for v0.6.48.7.22.

The earlier v0.6.48.7.21.4 oracle identified the five workspaces that change
between DSEC calls.  This follow-up observational probe writes the complete
first-evaluation arrays for all four calls so transport can be implemented and
verified without reconstructing values from hashes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from . import v0472_thermal_budget_state_refresh_capture as base
from .continuum_refresh_payload_audit import PAYLOAD_ARRAYS, verify_payload_bundle

RELEASE = "0.6.48.7.22"
SCHEMA = "xstar-tools-v0648722-v0472-continuum-refresh-payload-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v0648722-continuum-refresh-payload-oracle-v1"
SOURCE_ARCHIVE_SHA256 = base.SOURCE_ARCHIVE_SHA256
BUDGET_NAME = base.BUDGET_NAME
STATE_NAME = base.STATE_NAME
TRACE_NAME = base.TRACE_NAME
REPORT_NAME = base.REPORT_NAME
VERIFY_NAME = "payload_capture_verification.json"
MANIFEST_NAME = "payload_capture_manifest.json"
PAYLOAD_DIR_NAME = "call_start_payloads"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n")


_payload_snippet = r'''
    payload_dir = _OUT / "call_start_payloads"
    payload_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        payload_dir / f"call_{int(call_id)}.npz",
        radiation_energy=_array(values["radiation_energy"]),
        bremsa=_array(values["bremsa"]),
        continuum_tau_in=_array(values["continuum_tau_in"]),
        continuum_tau_out=_array(values["continuum_tau_out"]),
        global_xilevg=_array(values["global_xilevg"]),
        global_bilevg=_array(values["global_bilevg"]),
        global_rnisg=_array(values["global_rnisg"]),
    )
    _STATE["payload_files"] = int(_STATE.get("payload_files", 0)) + 1
'''

_PROBE = base._PROBE.replace("0.6.48.7.21.4", RELEASE).replace("v0487214", "v048722")
_PROBE = _PROBE.replace(
    '"bypassed_retained_evaluators": 0}',
    '"bypassed_retained_evaluators": 0, "payload_files": 0}',
    1,
)
_PROBE = _PROBE.replace('    _STATE["states"].append(row)\n', '    _STATE["states"].append(row)\n' + _payload_snippet, 1)
_PROBE = _PROBE.replace(
    '"result": "ACCEPT" if len(_STATE["budgets"]) >= 7 and len(_STATE["states"]) == 4 and len(_STATE["trace"]) >= 57 else "REJECT",',
    '"result": "ACCEPT" if len(_STATE["budgets"]) >= 7 and len(_STATE["states"]) == 4 and len(_STATE["trace"]) >= 57 and int(_STATE.get("payload_files", 0)) == 4 else "REJECT",',
    1,
)
_PROBE = _PROBE.replace(
    '"dsec_evaluations_observed": len(_STATE["trace"]), "run_summary": run_summary or {},',
    '"dsec_evaluations_observed": len(_STATE["trace"]), "payload_files": int(_STATE.get("payload_files", 0)), "run_summary": run_summary or {},',
    1,
)
_DRIVER = base._DRIVER.replace("import v048721_probe_runtime as probe", "import v048722_probe_runtime as probe")


def capture(
    source_archive: Path,
    atdb_path: Path,
    output_dir: Path,
    parameters_json: Path,
    coheat_path: Path | None,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if base._sha256(source_archive) != SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v048722_") as tmp:
        tmp_path = Path(tmp)
        base._safe_extract(source_archive, tmp_path / "source")
        root = base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        (probe_dir / "v048722_probe_runtime.py").write_text(_PROBE)
        (probe_dir / "probe_config.json").write_text(json.dumps({"output_dir": str(output_dir)}, indent=2))
        (probe_dir / "driver.py").write_text(_DRIVER)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(probe_dir), str(root / "src")])
        env.update({
            "PYTHONFAULTHANDLER": "1",
            "PYTHONUNBUFFERED": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        })
        command = [
            sys.executable,
            str(probe_dir / "driver.py"),
            "--parameters-json", str(parameters_json.resolve()),
            "--atdb-path", str(atdb_path.resolve()),
            "--output-dir", str(output_dir / "physical_run"),
        ]
        if coheat_path is not None:
            command += ["--coheat-path", str(coheat_path.resolve())]
        log = output_dir / "v0472_payload_capture_run.log"
        with log.open("w") as stream:
            completed = subprocess.run(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 payload capture failed with exit {completed.returncode}; see {log}")
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    files: dict[str, Any] = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and "physical_run" not in path.parts:
            files[str(path.relative_to(output_dir))] = {
                "sha256": base._sha256(path),
                "size_bytes": path.stat().st_size,
            }
    _write_json(output_dir / MANIFEST_NAME, {**result, "immutable": result["result"] == "ACCEPT", "files": files})
    return result


def verify(bundle: Path) -> dict[str, Any]:
    base_result = base.verify(bundle)
    payload = verify_payload_bundle(bundle)
    errors = list(base_result.get("errors", [])) + list(payload.get("errors", []))
    accepted = base_result.get("result") == "ACCEPT" and payload.get("status") == "ACCEPT"
    return {
        "schema": VERIFY_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if accepted else "REJECT",
        "errors": errors,
        "actual_v0472_runtime_capture": bool(base_result.get("actual_v0472_runtime_capture")),
        "call1_budget_rows": int(base_result.get("call1_budget_rows", 0)),
        "dsec_call_start_states": int(base_result.get("dsec_call_start_states", 0)),
        "dsec_evaluations_observed": int(base_result.get("dsec_evaluations_observed", 0)),
        "payload_calls": int(payload.get("calls", 0)),
        "payload_arrays": list(PAYLOAD_ARRAYS),
        "between_call_changed_workspaces": list(base_result.get("between_call_changed_workspaces", [])),
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    capture_parser = sub.add_parser("capture")
    capture_parser.add_argument("source_archive", type=Path)
    capture_parser.add_argument("atdb_path", type=Path)
    capture_parser.add_argument("output_dir", type=Path)
    capture_parser.add_argument("parameters_json", type=Path)
    capture_parser.add_argument("--coheat-path", type=Path)
    capture_parser.add_argument("--output-json", type=Path)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("bundle", type=Path)
    verify_parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    try:
        result = (
            capture(args.source_archive, args.atdb_path, args.output_dir, args.parameters_json, args.coheat_path)
            if args.command == "capture"
            else verify(args.bundle)
        )
    except Exception as exc:
        result = {
            "schema": VERIFY_SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "qualification_only": True,
            "production_promotion_ready": False,
        }
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
