"""Capture source-order Thermal state for independent all-61 parity.

This v46.21 probe extends the v46.20.2 capture with a complete H/He/Mg
record-level ans3--ans6 ledger.  Magnesium primary cooling is verified with the
Fortran/Python grouping: unweighted population-rate products are accumulated in
source order and abundance is applied once after the completed element sum.
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

from . import v0472_all61_magnesium_primary_cooling_source_order_capture as legacy

RELEASE = "0.6.48.7.46.21.5"
SCHEMA = "xstar-tools-v064874621-v0472-all61-independent-thermal-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v064874621-v0472-all61-independent-thermal-state-v1"
ANSWER_LEDGER_NAME = "v0472_all61_thermal_answer_channels.csv"
REPORT_NAME = "all61_independent_thermal_capture_report.json"
VERIFY_NAME = "all61_independent_thermal_capture_verification.json"
MANIFEST_NAME = "all61_independent_thermal_capture_manifest.json"
EXPECTED_EVALUATIONS = 61
ANSWER_FIELDS = [
    "sequence", "kind", "call_index", "evaluation_index", "element_z",
    "source_position", "record", "data_type", "rate_type", "ion_index",
    "ion_stage", "density_scale", "idest1", "idest2", "ans3", "ans4",
    "ans5", "ans6",
]

_EXTRA_CODE = r'''
V04874621_ANSWER_FIELDS = __ANSWER_FIELDS__

def _v04874621_install_answer_hook():
    """Capture final committed UCalc ans3--ans6 for every active H/He/Mg record."""
    from xstar_tools.xstar.ucalc import SourceFaithfulUCalc
    original_evaluate = SourceFaithfulUCalc.evaluate_record_number

    def evaluate_record_number(self, master, record, context, **kwargs):
        result = original_evaluate(self, master, record, context, **kwargs)
        extras = dict(getattr(context, "extras", {}) or {})
        element_z = int(extras.get("element_z", 0) or 0)
        status_obj = getattr(result, "status", None)
        status = getattr(status_obj, "value", str(status_obj or ""))
        if element_z in (1, 2, 12) and status == "evaluated":
            ident = dict(_STATE.get("v04874619_current_identity") or {})
            sequence = int(ident.get("sequence", 0) or 0)
            if sequence <= 0:
                raise RuntimeError(f"missing sequence for Thermal answer record {record}")
            row = {
                **ident,
                "sequence": sequence,
                "element_z": element_z,
                "source_position": 0,
                "record": int(record),
                "data_type": int(getattr(result, "data_type", 0) or 0),
                "rate_type": int(getattr(result, "rate_type", 0) or 0),
                "ion_index": int(extras.get("ion_index", extras.get("jkion", 0)) or 0),
                "ion_stage": int(extras.get("ion_stage", 0) or 0),
                "density_scale": float(getattr(context, "hydrogen_density_cm3", 0.0) or 0.0),
                "idest1": int(getattr(result, "idest1", 0) or 0),
                "idest2": int(getattr(result, "idest2", 0) or 0),
                "ans3": float(getattr(result, "ans3", 0.0)),
                "ans4": float(getattr(result, "ans4", 0.0)),
                "ans5": float(getattr(result, "ans5", 0.0)),
                "ans6": float(getattr(result, "ans6", 0.0)),
            }
            key = (sequence, element_z, int(record))
            sink = _STATE.setdefault("v04874621_answer_channels", {})
            prior = sink.get(key)
            if prior is not None:
                for name in ("data_type", "rate_type", "idest1", "idest2",
                             "ans3", "ans4", "ans5", "ans6"):
                    left = prior[name]; right = row[name]
                    if isinstance(left, float) or isinstance(right, float):
                        same = float(left).hex() == float(right).hex()
                    else:
                        same = left == right
                    if not same:
                        raise RuntimeError(
                            f"non-unique Thermal answer context sequence={sequence} "
                            f"element={element_z} record={record} field={name}"
                        )
            else:
                sink[key] = row
        return result

    SourceFaithfulUCalc.evaluate_record_number = evaluate_record_number

def _v04874621_write_answer_channels():
    rows = sorted(
        _STATE.setdefault("v04874621_answer_channels", {}).values(),
        key=lambda row: (int(row["sequence"]), int(row["element_z"]),
                         int(row["source_position"]), int(row["record"])))
    with (_OUT / "__ANSWER_LEDGER_NAME__").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=V04874621_ANSWER_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)
'''.replace("__ANSWER_FIELDS__", repr(ANSWER_FIELDS)).replace("__ANSWER_LEDGER_NAME__", ANSWER_LEDGER_NAME)

_PROBE = legacy._PROBE
anchor = "def _v04874612_capture_input(kind, call_id, evaluation_index, sequence, state):"
if _PROBE.count(anchor) != 1:
    raise RuntimeError("v46.21 source-probe input anchor missing or ambiguous")
_PROBE = _PROBE.replace(anchor, _EXTRA_CODE + "\n\n" + anchor, 1)
install_hook = "    _v04874620_install_type99_hook()"
if _PROBE.count(install_hook) != 1:
    raise RuntimeError("v46.21 source-probe UCalc install hook missing or ambiguous")
_PROBE = _PROBE.replace(
    install_hook,
    install_hook + "\n    _v04874621_install_answer_hook()",
    1,
)
final_hook = "    _v048746202_write_magnesium_primary_source_order()"
if _PROBE.count(final_hook) != 1:
    raise RuntimeError("v46.21 source-probe final hook missing or ambiguous")
_PROBE = _PROBE.replace(final_hook, final_hook + "\n    _v04874621_write_answer_channels()", 1)
compile(_PROBE, "<v04874621-all61-independent-thermal-probe>", "exec")
_DRIVER = legacy._DRIVER.replace(
    "import v048746202_all61_magnesium_primary_cooling_source_order_probe_runtime as probe",
    "import v04874621_all61_independent_thermal_probe_runtime as probe",
)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _exact(left: Any, right: Any) -> bool:
    try:
        return float(left).hex() == float(right).hex()
    except Exception:
        return False


def verify(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    errors: list[str] = []
    # Type-99 capture is the scientifically accepted parent.  Do not call the
    # v46.20.2 verifier because it intentionally encodes the rejected
    # per-record abundance grouping.
    type99_result = legacy.base.verify(bundle)
    if type99_result.get("result") != "ACCEPT":
        errors.extend(f"type99:{item}" for item in type99_result.get("errors", []))

    ledger_path = bundle / legacy.LEDGER_NAME
    family_path = bundle / legacy.FAMILY_NAME
    answer_path = bundle / ANSWER_LEDGER_NAME
    for path in (ledger_path, family_path, answer_path):
        if not path.is_file():
            errors.append(f"missing:{path.name}")
    ledger = _read_csv(ledger_path) if ledger_path.is_file() else []
    family = _read_csv(family_path) if family_path.is_file() else []
    answers = _read_csv(answer_path) if answer_path.is_file() else []

    rows_by_sequence: dict[int, list[dict[str, str]]] = {}
    seen_keys: set[tuple[int, int, str]] = set()
    for row in ledger:
        try:
            sequence = int(row["sequence"]); record = int(row["record"])
            role = row["role"]; order = int(row["source_order_index"])
            abundance = float(row["abundance"])
            population = float(row["compact_population"]); coefficient = float(row["cj"])
            weighted_population = float(row["weighted_population"])
            weighted_contribution = float(row["cooling_contribution"])
            if not (1 <= sequence <= 61 and record > 0 and order > 0 and role and coefficient > 0.0):
                raise ValueError("identity")
            if not all(math.isfinite(value) for value in (
                abundance, population, coefficient, weighted_population, weighted_contribution
            )):
                raise ValueError("nonfinite")
            if not _exact(weighted_population, population * abundance):
                raise ValueError("weighted_population_identity")
            # The historical v46.20.2 row diagnostic remains per-row weighted;
            # it is never used to construct the v46.21 scientific total.
            if not _exact(weighted_contribution, weighted_population * coefficient):
                raise ValueError("weighted_contribution_identity")
            key = (sequence, record, role)
            if key in seen_keys:
                raise ValueError("duplicate_key")
            seen_keys.add(key); rows_by_sequence.setdefault(sequence, []).append(row)
        except Exception as exc:
            errors.append(f"invalid_magnesium_row:{exc}")
            break

    family_by_sequence = {int(row["sequence"]): row for row in family}
    abundance_after_sum_exact = 0
    row_counts: dict[int, int] = {}
    for sequence in range(1, 62):
        rows = sorted(rows_by_sequence.get(sequence, []), key=lambda row: int(row["source_order_index"]))
        row_counts[sequence] = len(rows)
        if not rows:
            continue
        orders = [int(row["source_order_index"]) for row in rows]
        if len(orders) != len(set(orders)) or any(a >= b for a, b in zip(orders, orders[1:])):
            errors.append(f"source_order_not_strict:{sequence}"); continue
        abundances = {float(row["abundance"]).hex() for row in rows}
        if len(abundances) != 1:
            errors.append(f"abundance_not_invariant:{sequence}"); continue
        unweighted = 0.0
        for row in rows:
            unweighted += float(row["compact_population"]) * float(row["cj"])
        reduced = unweighted * float(rows[0]["abundance"])
        source_value = family_by_sequence.get(sequence, {}).get("source_mg_cooling", "nan")
        if _exact(reduced, source_value):
            abundance_after_sum_exact += 1
        else:
            errors.append(f"abundance_after_sum_mismatch:{sequence}")

    answer_sequences: set[int] = set()
    answer_keys: set[tuple[int, int, int]] = set()
    answer_field_values = 0
    answer_counts_by_element = {1: 0, 2: 0, 12: 0}
    for row in answers:
        try:
            sequence = int(row["sequence"]); element_z = int(row["element_z"]); record = int(row["record"])
            key = (sequence, element_z, record)
            if not (1 <= sequence <= 61 and element_z in answer_counts_by_element and record > 0):
                raise ValueError("identity")
            if key in answer_keys:
                raise ValueError("duplicate_key")
            values = [float(row[name]) for name in ("ans3", "ans4", "ans5", "ans6")]
            if not all(math.isfinite(value) for value in values):
                raise ValueError("nonfinite")
            answer_keys.add(key); answer_sequences.add(sequence)
            answer_counts_by_element[element_z] += 1; answer_field_values += 4
        except Exception as exc:
            errors.append(f"invalid_answer_row:{exc}")
            break
    if answer_sequences != set(range(1, 62)):
        errors.append(f"answer_sequence_inventory={len(answer_sequences)}")
    if any(answer_counts_by_element[z] == 0 for z in answer_counts_by_element):
        errors.append("answer_element_inventory")

    result = "ACCEPT" if not errors and abundance_after_sum_exact == 61 else "REJECT"
    return {
        "schema": VERIFY_SCHEMA, "release": RELEASE, "result": result,
        "errors": errors, "evaluations": len(answer_sequences),
        "magnesium_primary_cooling_rows": len(ledger),
        "magnesium_primary_cooling_rows_by_sequence": {str(k): v for k, v in row_counts.items()},
        "magnesium_abundance_after_source_order_exact": abundance_after_sum_exact,
        "thermal_answer_channel_rows": len(answers),
        "thermal_answer_values": answer_field_values,
        "thermal_answer_rows_by_element": {str(k): v for k, v in answer_counts_by_element.items()},
        "type99_capture_result": type99_result.get("result", "REJECT"),
        "qualification_only": True, "production_promotion_ready": False,
    }


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    root_base = legacy.base.base.base.base.base.base
    if root_base._sha256(source_archive) != root_base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v04874621_") as tmp:
        tmp_path = Path(tmp)
        root_base._safe_extract(source_archive, tmp_path / "source")
        root = root_base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"; probe_dir.mkdir()
        (probe_dir / "v04874621_all61_independent_thermal_probe_runtime.py").write_text(_PROBE)
        (probe_dir / "probe_config.json").write_text(json.dumps({"output_dir": str(output_dir)}, indent=2))
        (probe_dir / "driver.py").write_text(_DRIVER)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(probe_dir), str(root / "src")])
        env.update({
            "PYTHONFAULTHANDLER": "1", "PYTHONUNBUFFERED": "1", "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
        })
        cmd = [
            sys.executable, str(probe_dir / "driver.py"),
            "--parameters-json", str(parameters_json.resolve()),
            "--atdb-path", str(atdb_path.resolve()),
            "--output-dir", str(output_dir / "physical_run"),
        ]
        if coheat_path is not None:
            cmd += ["--coheat-path", str(coheat_path.resolve())]
        log = output_dir / "v0472_all61_independent_thermal_capture_run.log"
        with log.open("w") as handle:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 independent Thermal capture failed with exit {completed.returncode}; see {log}")
    legacy.base.base.base._normalize_capture_reports(output_dir)
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result); _write_json(output_dir / REPORT_NAME, result)
    files: dict[str, dict[str, Any]] = {}
    for name in (legacy.LEDGER_NAME, legacy.FAMILY_NAME, ANSWER_LEDGER_NAME, REPORT_NAME, VERIFY_NAME):
        path = output_dir / name
        if path.is_file():
            files[name] = {"sha256": root_base._sha256(path), "size_bytes": path.stat().st_size}
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
        result = {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": [str(exc)], "qualification_only": True, "production_promotion_ready": False}
    if args.output_json: _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
