"""Capture source v0.6.47.2 per-element and continuum thermal budgets for all 57 DSEC evaluations.

This is an observational qualification probe.  It executes the hash-verified
v0.6.47.2 Python physical workflow without changing rates, matrices, controller
logic, or products.  The only extension over the v0.6.48.7.21 probe is that the
thermal budget is retained for every DSEC call rather than call 1 only.
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

from . import v0472_thermal_budget_state_refresh_capture as base

RELEASE = "0.6.48.7.26"
SCHEMA = "xstar-tools-v0648726-v0472-full-dsec-thermal-budget-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v0648726-full-dsec-thermal-budget-oracle-v1"
BUDGET_NAME = "v0472_full_dsec_thermal_budget.csv"
STATE_NAME = base.STATE_NAME
TRACE_NAME = base.TRACE_NAME
REPORT_NAME = "full_dsec_capture_report.json"
VERIFY_NAME = "full_dsec_capture_verification.json"
MANIFEST_NAME = "full_dsec_capture_manifest.json"

_PROBE = base._PROBE
_PROBE = _PROBE.replace(
    '    if call_id != 1:\n        return\n',
    '    # v0.6.48.7.26: retain the budget for every DSEC call.\n',
)
_PROBE = _PROBE.replace('"v0472_call1_thermal_budget.csv"', f'"{BUDGET_NAME}"')
_PROBE = _PROBE.replace(
    '"result": "ACCEPT" if len(_STATE["budgets"]) >= 7 and len(_STATE["states"]) == 4 and len(_STATE["trace"]) >= 57 else "REJECT",',
    '"result": "ACCEPT" if len(_STATE["budgets"]) == 57 and len(_STATE["states"]) == 4 and len(_STATE["trace"]) == 57 else "REJECT",',
)
_PROBE = _PROBE.replace('"call1_budget_rows": len(_STATE["budgets"])', '"full_dsec_budget_rows": len(_STATE["budgets"])')
_PROBE = _PROBE.replace('"schema": "xstar-tools-v0648721-v0472-thermal-budget-state-refresh-probe-v1"', f'"schema": "{SCHEMA}"')
_PROBE = _PROBE.replace('"release": "0.6.48.7.21.4"', f'"release": "{RELEASE}"')
_DRIVER = base._DRIVER.replace('import v048721_probe_runtime as probe', 'import v048726_full_probe_runtime as probe')


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def verify(bundle: Path) -> dict[str, Any]:
    errors: list[str] = []
    for name in (BUDGET_NAME, STATE_NAME, TRACE_NAME, REPORT_NAME):
        if not (bundle / name).is_file():
            errors.append(f"missing:{name}")
    if errors:
        return {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": errors,
                "qualification_only": True, "production_promotion_ready": False}
    budgets = _read_csv(bundle / BUDGET_NAME)
    states = _read_csv(bundle / STATE_NAME)
    trace = _read_csv(bundle / TRACE_NAME)
    calls = [int(r["dsec_call_id"]) for r in budgets]
    inventory = {call: calls.count(call) for call in sorted(set(calls))}
    expected = {1: 21, 2: 1, 3: 18, 4: 17}
    if len(budgets) != 57: errors.append(f"budget_rows={len(budgets)}")
    if inventory != expected: errors.append(f"call_inventory={inventory}")
    if len(trace) != 57: errors.append(f"trace_rows={len(trace)}")
    if len(states) != 4 or [int(r["dsec_call_id"]) for r in states] != [1, 2, 3, 4]:
        errors.append("call_start_state_inventory")
    report = json.loads((bundle / REPORT_NAME).read_text())
    if not report.get("actual_v0472_runtime_capture"):
        errors.append("not_actual_v0472_runtime_capture")
    return {
        "schema": VERIFY_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "actual_v0472_runtime_capture": bool(report.get("actual_v0472_runtime_capture")),
        "full_dsec_budget_rows": len(budgets),
        "dsec_evaluations_observed": len(trace),
        "call_budget_inventory": {str(k): v for k, v in inventory.items()},
        "dsec_call_start_states": len(states),
        "budget_sha256": base._sha256(bundle / BUDGET_NAME),
        "trace_sha256": base._sha256(bundle / TRACE_NAME),
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if base._sha256(source_archive) != base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v048726_") as tmp:
        tmp_path = Path(tmp)
        base._safe_extract(source_archive, tmp_path / "source")
        root = base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        (probe_dir / "v048726_full_probe_runtime.py").write_text(_PROBE)
        (probe_dir / "probe_config.json").write_text(json.dumps({"output_dir": str(output_dir)}, indent=2))
        (probe_dir / "driver.py").write_text(_DRIVER)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(probe_dir), str(root / "src")])
        env.update({
            "PYTHONFAULTHANDLER": "1", "PYTHONUNBUFFERED": "1", "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
        })
        cmd = [sys.executable, str(probe_dir / "driver.py"), "--parameters-json", str(parameters_json.resolve()),
               "--atdb-path", str(atdb_path.resolve()), "--output-dir", str(output_dir / "physical_run")]
        if coheat_path is not None:
            cmd += ["--coheat-path", str(coheat_path.resolve())]
        log = output_dir / "v0472_full_capture_run.log"
        with log.open("w") as f:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=f, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 full thermal capture failed with exit {completed.returncode}; see {log}")
    # The generated probe retains the historical capture_report filename.
    historical = output_dir / base.REPORT_NAME
    if historical.is_file():
        historical.replace(output_dir / REPORT_NAME)
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    files = {}
    for name in (BUDGET_NAME, STATE_NAME, TRACE_NAME, REPORT_NAME, VERIFY_NAME):
        path = output_dir / name
        files[name] = {"sha256": base._sha256(path), "size_bytes": path.stat().st_size}
    _write_json(output_dir / MANIFEST_NAME, {**result, "immutable": result["result"] == "ACCEPT", "files": files})
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("source_archive", type=Path)
    c.add_argument("atdb_path", type=Path)
    c.add_argument("output_dir", type=Path)
    c.add_argument("parameters_json", type=Path)
    c.add_argument("--coheat-path", type=Path)
    c.add_argument("--output-json", type=Path)
    v = sub.add_parser("verify")
    v.add_argument("bundle", type=Path)
    v.add_argument("--output-json", type=Path)
    a = p.parse_args(argv)
    try:
        result = capture(a.source_archive, a.atdb_path, a.output_dir, a.parameters_json, a.coheat_path) if a.cmd == "capture" else verify(a.bundle)
    except Exception as exc:
        result = {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)],
                  "qualification_only": True, "production_promotion_ready": False}
    if a.output_json:
        _write_json(a.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
