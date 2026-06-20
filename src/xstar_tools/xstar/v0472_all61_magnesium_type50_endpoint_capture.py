"""Capture all-61 Mg Type-50 escape and source-local endpoint-energy state.

The capture is observational and qualification-only.  It extends the accepted
all-61 Thermal source probe with the caller-owned line optical-depth arrays and
the record-to-line-index mapping consumed by ``calc_hmc_ion``/``ucalc``.  It
never replaces rates, populations, controller state, or products.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import v0472_all61_thermal_state_capture as base

RELEASE = "0.6.48.7.46.20.2"
SCHEMA = "xstar-tools-v0648746193-v0472-all61-magnesium-type50-endpoint-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v0648746193-v0472-all61-magnesium-type50-endpoint-state-v1"
ESCAPE_NAME = "v0472_all61_magnesium_type50_endpoint_escape.csv"
MAP_NAME = "v0472_magnesium_type50_line_index_map.csv"
ENDPOINT_MAP_NAME = "v0472_magnesium_type50_endpoint_energy_map.csv"
REPORT_NAME = "all61_magnesium_type50_endpoint_capture_report.json"
VERIFY_NAME = "all61_magnesium_type50_endpoint_capture_verification.json"
MANIFEST_NAME = "all61_magnesium_type50_endpoint_capture_manifest.json"
EXPECTED_EVALUATIONS = 61
EXPECTED_UNIQUE_RECORDS = 2420
EXPECTED_SEQUENCE_COUNTS = {
    **{sequence: 2196 for sequence in range(1, 5)},
    **{sequence: 2201 for sequence in range(5, 7)},
    **{sequence: 2420 for sequence in range(7, EXPECTED_EVALUATIONS + 1)},
}
EXPECTED_ROWS = sum(EXPECTED_SEQUENCE_COUNTS.values())
EXPECTED_COUNT_SET = frozenset(EXPECTED_SEQUENCE_COUNTS.values())

ESCAPE_FIELDS = [
    "sequence", "kind", "call_index", "evaluation_index", "record",
    "line_index", "tau_in", "tau_out", "ptmp1", "ptmp2", "ptmp_sum",
    "covering_fraction", "ans1", "ans2", "ans3", "ans4", "ans5", "ans6",
    "idest1", "idest2", "source_endpoint1_energy_ev",
    "source_endpoint2_energy_ev", "source_endpoint_energy_ev",
    "source_endpoint_energy_hex", "ucalc_status",
]
MAP_FIELDS = ["record", "line_index"]
ENDPOINT_MAP_FIELDS = [
    "record", "idest1", "idest2", "source_endpoint1_energy_ev",
    "source_endpoint2_energy_ev", "source_endpoint_energy_ev",
    "source_endpoint_energy_hex",
]

_EXTRA_CODE = r'''
V04874619_ESCAPE_FIELDS = __ESCAPE_FIELDS__
V04874619_MAP_FIELDS = __MAP_FIELDS__
V048746193_ENDPOINT_MAP_FIELDS = __ENDPOINT_MAP_FIELDS__

def _v04874619_capture_line_state(kind, call_id, evaluation_index, sequence, state):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    _STATE["v04874619_current_identity"] = {
      "sequence": int(sequence), "kind": str(kind), "call_index": int(call_id),
      "evaluation_index": int(evaluation_index),
    }
    requests = tuple(getattr(state, "element_requests", ()) or ())
    request = requests[0] if requests else None
    escape = _field(request, "escape")
    directory = _OUT / "all61_input_workspaces" / f"evaluation_{int(sequence):04d}"
    directory.mkdir(parents=True, exist_ok=True)
    prefix = f"call_{int(call_id)}_"
    np.asarray(_array(_field(escape, "line_tau_in")), dtype=np.float64).tofile(
        directory / (prefix + "line_tau_in.bin"))
    np.asarray(_array(_field(escape, "line_tau_out")), dtype=np.float64).tofile(
        directory / (prefix + "line_tau_out.bin"))

def _v04874619_install_hooks():
    from xstar_tools.xstar import element_equilibrium as eq
    from xstar_tools.xstar.ucalc import SourceFaithfulUCalc
    original_escape = eq._escape_factors
    original_evaluate = SourceFaithfulUCalc.evaluate_record_number

    def escape_factors(record, rate_type, derived, context):
        p1, p2, reason = original_escape(record, rate_type, derived, context)
        # ElementEquilibriumContext intentionally has no UCalc ``extras``.
        # Capture every rate-type-4 escape event here; the result hook below
        # performs the authoritative Magnesium/data-type-50 filter once the
        # UCalcContext and evaluated result are available.
        if int(rate_type) == 4:
            ident = dict(_STATE.get("v04874619_current_identity") or {})
            if ident:
                line_index = int(derived.nplini[record]) if int(record) < len(derived.nplini) else 0
                tau_in, tau_out = context.escape.line_taus(line_index)
                key = (int(ident["sequence"]), int(record))
                _STATE.setdefault("v04874619_pending_escape", {})[key] = {
                  **ident, "record": int(record), "line_index": line_index,
                  "tau_in": float(tau_in) if tau_in is not None else float("nan"),
                  "tau_out": float(tau_out) if tau_out is not None else float("nan"),
                  "ptmp1": float(p1), "ptmp2": float(p2),
                  "ptmp_sum": float(p1) + float(p2),
                  "covering_fraction": float(context.covering_fraction),
                  "escape_reason": reason or "",
                }
        return p1, p2, reason

    def evaluate_record_number(self, master, record, context, **kwargs):
        result = original_evaluate(self, master, record, context, **kwargs)
        extras = dict(getattr(context, "extras", {}) or {})
        if int(getattr(result, "data_type", -1)) == 50 and int(extras.get("element_z", 0) or 0) == 12:
            ident = dict(_STATE.get("v04874619_current_identity") or {})
            key = (int(ident.get("sequence", 0)), int(record))
            row = dict(_STATE.setdefault("v04874619_pending_escape", {}).get(key) or {})
            if not row:
                raise RuntimeError(f"missing magnesium Type-50 escape state sequence={key[0]} record={record}")
            row.update({
              "ans1": float(result.ans1), "ans2": float(result.ans2),
              "ans3": float(result.ans3), "ans4": float(result.ans4),
              "ans5": float(result.ans5), "ans6": float(result.ans6),
              "idest1": int(result.idest1), "idest2": int(result.idest2),
              "ucalc_status": getattr(result.status, "value", str(result.status)),
            })
            endpoint1 = float(context.levels.energy(int(result.idest1)))
            endpoint2 = float(context.levels.energy(int(result.idest2)))
            endpoint_energy = abs(endpoint1 - endpoint2)
            diagnostics = dict(getattr(result, "diagnostics", {}) or {})
            diagnostic_endpoint = diagnostics.get("endpoint_energy_eV")
            if diagnostic_endpoint is not None and float(diagnostic_endpoint).hex() != endpoint_energy.hex():
                raise RuntimeError(
                    f"magnesium Type-50 endpoint diagnostic mismatch sequence={key[0]} record={record}")
            row.update({
              "source_endpoint1_energy_ev": endpoint1,
              "source_endpoint2_energy_ev": endpoint2,
              "source_endpoint_energy_ev": endpoint_energy,
              "source_endpoint_energy_hex": endpoint_energy.hex(),
            })
            prior = _STATE.setdefault("v04874619_escape_rows", {}).get(key)
            if prior is not None and prior != row:
                raise RuntimeError(f"inconsistent magnesium Type-50 escape capture sequence={key[0]} record={record}")
            _STATE["v04874619_escape_rows"][key] = row
        return result

    eq._escape_factors = escape_factors
    SourceFaithfulUCalc.evaluate_record_number = evaluate_record_number

def _v04874619_write_escape():
    rows = [row for _, row in sorted(_STATE.setdefault("v04874619_escape_rows", {}).items())]
    with (_OUT / "__ESCAPE_NAME__").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=V04874619_ESCAPE_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
    mapping = {}
    for row in rows:
        record = int(row["record"]); line_index = int(row["line_index"])
        prior = mapping.setdefault(record, line_index)
        if prior != line_index:
            raise RuntimeError(f"magnesium Type-50 line-index mapping changed for record {record}")
    with (_OUT / "__MAP_NAME__").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=V04874619_MAP_FIELDS)
        writer.writeheader(); writer.writerows(
            {"record": record, "line_index": mapping[record]} for record in sorted(mapping))
    endpoint_mapping = {}
    for row in rows:
        record = int(row["record"])
        value = {
          "record": record,
          "idest1": int(row["idest1"]),
          "idest2": int(row["idest2"]),
          "source_endpoint1_energy_ev": float(row["source_endpoint1_energy_ev"]),
          "source_endpoint2_energy_ev": float(row["source_endpoint2_energy_ev"]),
          "source_endpoint_energy_ev": float(row["source_endpoint_energy_ev"]),
          "source_endpoint_energy_hex": str(row["source_endpoint_energy_hex"]),
        }
        prior = endpoint_mapping.setdefault(record, value)
        if prior != value:
            raise RuntimeError(
                f"magnesium Type-50 source endpoint state changed for record {record}")
    with (_OUT / "__ENDPOINT_MAP_NAME__").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=V048746193_ENDPOINT_MAP_FIELDS)
        writer.writeheader(); writer.writerows(
            endpoint_mapping[record] for record in sorted(endpoint_mapping))
'''.replace("__ESCAPE_FIELDS__", repr(ESCAPE_FIELDS)).replace("__MAP_FIELDS__", repr(MAP_FIELDS)).replace("__ENDPOINT_MAP_FIELDS__", repr(ENDPOINT_MAP_FIELDS)).replace("__ESCAPE_NAME__", ESCAPE_NAME).replace("__MAP_NAME__", MAP_NAME).replace("__ENDPOINT_MAP_NAME__", ENDPOINT_MAP_NAME)

_PROBE = base._PROBE
anchor = "def _v04874612_capture_input(kind, call_id, evaluation_index, sequence, state):"
if _PROBE.count(anchor) != 1:
    raise RuntimeError("v46.19.3 source-probe input anchor missing or ambiguous")
_PROBE = _PROBE.replace(anchor, _EXTRA_CODE + "\n\n" + anchor, 1)
input_hook = (
    "def _v04874612_capture_input(kind, call_id, evaluation_index, sequence, state):\n"
    "    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)\n"
)
if _PROBE.count(input_hook) != 1:
    raise RuntimeError("v46.19.3 source-probe input hook missing or ambiguous")
_PROBE = _PROBE.replace(input_hook, input_hook + "    _v04874619_capture_line_state(kind, call_id, evaluation_index, sequence, state)\n", 1)
install_anchor = '    _STATE["installed"] = True'
if _PROBE.count(install_anchor) != 1:
    raise RuntimeError("v46.19.3 source-probe install anchor missing or ambiguous")
_PROBE = _PROBE.replace(install_anchor, "    _v04874619_install_hooks()\n" + install_anchor, 1)
final_anchor = "def finalize(run_summary=None):\n    _v048742_write_all61()"
if _PROBE.count(final_anchor) != 1:
    raise RuntimeError("v46.19.3 source-probe finalize anchor missing or ambiguous")
_PROBE = _PROBE.replace(final_anchor, final_anchor + "\n    _v04874619_write_escape()", 1)
_PROBE = _PROBE.replace(
    '"all61_thermal_rows": len(_STATE.get("all61_thermal", [])),',
    '"all61_thermal_rows": len(_STATE.get("all61_thermal", [])), "magnesium_type50_escape_rows": len(_STATE.get("v04874619_escape_rows", {})),',
    1,
)
compile(_PROBE, "<v048746193-all61-magnesium-type50-endpoint-probe>", "exec")
_DRIVER = base._DRIVER.replace(
    "import v04874612_all61_thermal_probe_runtime as probe",
    "import v048746193_all61_magnesium_type50_endpoint_probe_runtime as probe",
)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _same_float(a: float, b: float) -> bool:
    return float(a).hex() == float(b).hex()


def _pescl(tau: float) -> float:
    tau = float(tau)
    if tau < 1.0:
        if tau < 1.0e-5:
            value = 1.0
        else:
            aa = 2.0 * tau
            value = (1.0 - math.exp(-aa)) / aa
    else:
        bb = 0.5 * math.sqrt(max(math.log(tau), 0.0)) / (1.0 + tau / 1.0e5)
        value = 1.0 / (tau * math.sqrt(math.pi) * (1.2 + bb))
    return value / 2.0


def verify(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    errors: list[str] = []
    base_result = base.verify(bundle)
    if base_result.get("result") != "ACCEPT":
        errors.extend(f"thermal:{item}" for item in base_result.get("errors", []))
    escape_path = bundle / ESCAPE_NAME
    map_path = bundle / MAP_NAME
    endpoint_map_path = bundle / ENDPOINT_MAP_NAME
    if not escape_path.is_file():
        errors.append(f"missing:{ESCAPE_NAME}")
        rows: list[dict[str, str]] = []
    else:
        rows = _read_csv(escape_path)
    if not map_path.is_file():
        errors.append(f"missing:{MAP_NAME}")
        mapping_rows: list[dict[str, str]] = []
    else:
        mapping_rows = _read_csv(map_path)
    if not endpoint_map_path.is_file():
        errors.append(f"missing:{ENDPOINT_MAP_NAME}")
        endpoint_rows: list[dict[str, str]] = []
    else:
        endpoint_rows = _read_csv(endpoint_map_path)
    if len(rows) != EXPECTED_ROWS:
        errors.append(f"escape_rows={len(rows)} expected={EXPECTED_ROWS}")
    sequences = sorted({int(row["sequence"]) for row in rows}) if rows else []
    if sequences != list(range(1, EXPECTED_EVALUATIONS + 1)):
        errors.append(f"escape_sequences={len(sequences)}")
    counts: dict[int, int] = {}
    for row in rows:
        sequence = int(row["sequence"]); counts[sequence] = counts.get(sequence, 0) + 1
        try:
            tau_in = float(row["tau_in"]); tau_out = float(row["tau_out"])
            p1 = _pescl(tau_in) * (1.0 - float(row["covering_fraction"]))
            p2 = _pescl(tau_out) * (1.0 - float(row["covering_fraction"])) + 2.0 * _pescl(tau_in + tau_out) * float(row["covering_fraction"])
            if not (_same_float(p1, float(row["ptmp1"])) and _same_float(p2, float(row["ptmp2"]))):
                errors.append(f"ptmp_mismatch:{sequence}:{row['record']}")
                break
            for name in ("ans1", "ans2", "ans3", "ans4", "ans5", "ans6"):
                if not math.isfinite(float(row[name])):
                    raise ValueError(name)
            endpoint1 = float(row["source_endpoint1_energy_ev"])
            endpoint2 = float(row["source_endpoint2_energy_ev"])
            endpoint = float(row["source_endpoint_energy_ev"])
            if endpoint.hex() != str(row["source_endpoint_energy_hex"]):
                raise ValueError("source_endpoint_energy_hex")
            if abs(endpoint1 - endpoint2).hex() != endpoint.hex():
                raise ValueError("source_endpoint_energy_difference")
            if (-float(row["ans2"]) * endpoint * 1.602176634e-12).hex() != float(row["ans3"]).hex():
                raise ValueError("source_ans3_endpoint_identity")
            if (-float(row["ans1"]) * endpoint * 1.602176634e-12).hex() != float(row["ans4"]).hex():
                raise ValueError("source_ans4_endpoint_identity")
        except Exception as exc:
            errors.append(f"invalid_escape_row:{sequence}:{row.get('record')}:{exc}")
            break
    if counts != EXPECTED_SEQUENCE_COUNTS:
        observed = {sequence: counts.get(sequence, 0) for sequence in range(1, EXPECTED_EVALUATIONS + 1)}
        errors.append(f"records_by_sequence={observed}")
    mapping = {(int(row["record"]), int(row["line_index"])) for row in mapping_rows}
    source_records = {int(row["record"]) for row in rows}
    mapping_records = {record for record, _ in mapping}
    if len(mapping) != EXPECTED_UNIQUE_RECORDS or len(mapping_rows) != EXPECTED_UNIQUE_RECORDS:
        errors.append(f"line_map_rows={len(mapping_rows)} unique={len(mapping)}")
    if source_records != mapping_records:
        errors.append(
            f"line_map_record_domain_mismatch=source:{len(source_records)},map:{len(mapping_records)}"
        )
    endpoint_mapping: dict[int, dict[str, str]] = {}
    for row in endpoint_rows:
        record = int(row["record"])
        if record in endpoint_mapping:
            errors.append(f"duplicate_endpoint_record:{record}")
            break
        endpoint_mapping[record] = row
        try:
            endpoint = float(row["source_endpoint_energy_ev"])
            if not math.isfinite(endpoint) or endpoint <= 0.0:
                raise ValueError("nonpositive_endpoint")
            if endpoint.hex() != row["source_endpoint_energy_hex"]:
                raise ValueError("endpoint_hex")
            if abs(float(row["source_endpoint1_energy_ev"]) - float(row["source_endpoint2_energy_ev"])).hex() != endpoint.hex():
                raise ValueError("endpoint_difference")
        except Exception as exc:
            errors.append(f"invalid_endpoint_map:{record}:{exc}")
            break
    endpoint_records = set(endpoint_mapping)
    if len(endpoint_rows) != EXPECTED_UNIQUE_RECORDS or len(endpoint_mapping) != EXPECTED_UNIQUE_RECORDS:
        errors.append(f"endpoint_map_rows={len(endpoint_rows)} unique={len(endpoint_mapping)}")
    if source_records != endpoint_records:
        errors.append(
            f"endpoint_map_record_domain_mismatch=source:{len(source_records)},map:{len(endpoint_records)}"
        )
    for row in rows:
        record = int(row["record"])
        endpoint_row = endpoint_mapping.get(record)
        if endpoint_row is None:
            continue
        for name in ("idest1", "idest2", "source_endpoint1_energy_ev",
                     "source_endpoint2_energy_ev", "source_endpoint_energy_ev",
                     "source_endpoint_energy_hex"):
            if str(row[name]) != str(endpoint_row[name]):
                errors.append(f"endpoint_map_row_mismatch:{row['sequence']}:{record}:{name}")
                break
        if errors and errors[-1].startswith("endpoint_map_row_mismatch"):
            break
    input_rows = _read_csv(bundle / base.base.INPUT_NAME) if (bundle / base.base.INPUT_NAME).is_file() else []
    line_workspace_files = 0
    for row in input_rows:
        sequence = int(row["sequence"]); call_id = int(row["dsec_call_id"])
        directory, _ = base.base._resolve_workspace_directory(bundle, row)
        for suffix in ("line_tau_in.bin", "line_tau_out.bin"):
            path = directory / f"call_{call_id}_{suffix}"
            if not path.is_file():
                errors.append(f"missing_line_workspace:{sequence}:{path.name}")
            else:
                line_workspace_files += 1
    result = {
        "schema": VERIFY_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "evaluations": len(sequences),
        "magnesium_type50_static_lowered_records": 2454,
        "magnesium_type50_unique_runtime_records": len(source_records),
        "magnesium_type50_expected_unique_runtime_records": EXPECTED_UNIQUE_RECORDS,
        "magnesium_type50_runtime_record_count_set": sorted(set(counts.values())),
        "magnesium_type50_expected_runtime_record_count_set": sorted(EXPECTED_COUNT_SET),
        "magnesium_type50_records_by_sequence": {str(key): value for key, value in sorted(counts.items())},
        "magnesium_type50_escape_rows": len(rows),
        "line_index_map_rows": len(mapping_rows),
        "endpoint_energy_map_rows": len(endpoint_rows),
        "endpoint_energy_rows": len(rows),
        "source_ans3_endpoint_identity_rows": sum(
            1 for row in rows
            if (-float(row["ans2"]) * float(row["source_endpoint_energy_ev"]) * 1.602176634e-12).hex()
            == float(row["ans3"]).hex()
        ),
        "source_ans4_endpoint_identity_rows": sum(
            1 for row in rows
            if (-float(row["ans1"]) * float(row["source_endpoint_energy_ev"]) * 1.602176634e-12).hex()
            == float(row["ans4"]).hex()
        ),
        "line_workspace_files": line_workspace_files,
        "thermal_capture_result": base_result.get("result", "REJECT"),
        "qualification_only": True,
        "production_promotion_ready": False,
    }
    return result


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    if base.base.base.base._sha256(source_archive) != base.base.base.base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v048746193_") as tmp:
        tmp_path = Path(tmp)
        base.base.base.base._safe_extract(source_archive, tmp_path / "source")
        root = base.base.base.base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"; probe_dir.mkdir()
        (probe_dir / "v048746193_all61_magnesium_type50_endpoint_probe_runtime.py").write_text(_PROBE)
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
        log = output_dir / "v0472_all61_magnesium_type50_escape_capture_run.log"
        with log.open("w") as handle:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 magnesium Type-50 escape capture failed with exit {completed.returncode}; see {log}")
    base._normalize_capture_reports(output_dir)
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    _write_json(output_dir / REPORT_NAME, result)
    files: dict[str, dict[str, Any]] = {}
    for name in (ESCAPE_NAME, MAP_NAME, ENDPOINT_MAP_NAME, REPORT_NAME, VERIFY_NAME):
        path = output_dir / name
        if path.is_file():
            files[name] = {"sha256": base.base.base.base._sha256(path), "size_bytes": path.stat().st_size}
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
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
