"""Capture the complete source-order Magnesium primary-cooling stream.

The qualification-only probe extends the accepted v46.20 Type-99 capture and
records every positive primary diagonal term consumed by Magnesium cooling in
the exact source assembly order.  It transports ordering metadata only; native
coefficients, populations, and cooling products remain independently computed.
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

from . import v0472_all61_magnesium_type99_primary_cooling_capture as base

RELEASE = "0.6.48.7.46.21"
SCHEMA = "xstar-tools-v0648746202-v0472-all61-magnesium-primary-cooling-source-order-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v0648746202-v0472-all61-magnesium-primary-cooling-source-order-state-v1"
LEDGER_NAME = "v0472_all61_magnesium_primary_cooling_source_order_ledger.csv"
FAMILY_NAME = "v0472_all61_magnesium_primary_cooling_source_order_family.csv"
REPORT_NAME = "all61_magnesium_primary_cooling_source_order_capture_report.json"
VERIFY_NAME = "all61_magnesium_primary_cooling_source_order_capture_verification.json"
MANIFEST_NAME = "all61_magnesium_primary_cooling_source_order_capture_manifest.json"
EXPECTED_EVALUATIONS = 61

LEDGER_FIELDS = [
    "sequence", "kind", "call_index", "evaluation_index",
    "source_order_index", "record", "data_type", "rate_type",
    "ion_index", "ion_stage", "role", "compact_row", "compact_column",
    "idest1", "idest2", "cj", "abundance", "compact_population",
    "weighted_population", "cooling_contribution",
]
FAMILY_FIELDS = [
    "sequence", "kind", "call_index", "evaluation_index",
    "positive_primary_rows", "source_order_reduced_mg_cooling",
    "source_mg_cooling", "reduction_exact",
]

_EXTRA_CODE = r'''
V048746202_MG_PRIMARY_LEDGER_FIELDS = __LEDGER_FIELDS__
V048746202_MG_PRIMARY_FAMILY_FIELDS = __FAMILY_FIELDS__

def _v048746202_capture_magnesium_primary_source_order(kind, call_id, evaluation_index, sequence, result):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    rows = []
    for item in tuple(getattr(result, "element_results", ()) or ()):
        request = getattr(item, "request", None)
        if int(_field(request, "element_z") or 0) != 12:
            continue
        abundance = float(_field(request, "abundance") or 0.0)
        populations = np.asarray(item.equilibrium.solve.populations, dtype=float)
        for term in tuple(item.equilibrium.assembly.terms or ()):
            if int(term.row) != int(term.column) or not (float(term.cj) > 0.0):
                continue
            compact_row = int(term.row)
            if compact_row < 1 or compact_row > populations.size:
                raise RuntimeError(f"Magnesium primary-cooling row outside population vector: {compact_row}")
            compact_population = float(populations[compact_row-1])
            weighted_population = compact_population * abundance
            cooling = weighted_population * float(term.cj)
            rows.append({
              "sequence": int(sequence), "kind": str(kind), "call_index": int(call_id),
              "evaluation_index": int(evaluation_index),
              "source_order_index": int(term.term_index), "record": int(term.record),
              "data_type": int(term.data_type), "rate_type": int(term.rate_type),
              "ion_index": int(term.ion_index), "ion_stage": int(term.ion_stage),
              "role": str(term.role), "compact_row": compact_row,
              "compact_column": int(term.column), "idest1": int(term.idest1),
              "idest2": int(term.idest2), "cj": float(term.cj),
              "abundance": abundance, "compact_population": compact_population,
              "weighted_population": weighted_population,
              "cooling_contribution": cooling,
            })
    rows.sort(key=lambda row: int(row["source_order_index"]))
    reduced = 0.0
    for row in rows:
        reduced += float(row["cooling_contribution"])
    source_mg_cooling = float(getattr(result, "cll", {}).get(12, 0.0))
    _STATE.setdefault("v048746202_mg_primary_ledger", []).extend(rows)
    _STATE.setdefault("v048746202_mg_primary_family", []).append({
      "sequence": int(sequence), "kind": str(kind), "call_index": int(call_id),
      "evaluation_index": int(evaluation_index),
      "positive_primary_rows": len(rows),
      "source_order_reduced_mg_cooling": reduced,
      "source_mg_cooling": source_mg_cooling,
      "reduction_exact": int(float(reduced).hex() == float(source_mg_cooling).hex()),
    })

def _v048746202_write_magnesium_primary_source_order():
    ledger_rows = sorted(
        _STATE.setdefault("v048746202_mg_primary_ledger", []),
        key=lambda row: (int(row["sequence"]), int(row["source_order_index"])))
    with (_OUT / "__LEDGER_NAME__").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=V048746202_MG_PRIMARY_LEDGER_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(ledger_rows)
    family_rows = sorted(
        _STATE.setdefault("v048746202_mg_primary_family", []),
        key=lambda row: int(row["sequence"]))
    with (_OUT / "__FAMILY_NAME__").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=V048746202_MG_PRIMARY_FAMILY_FIELDS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(family_rows)
'''.replace("__LEDGER_FIELDS__", repr(LEDGER_FIELDS)).replace("__FAMILY_FIELDS__", repr(FAMILY_FIELDS)).replace("__LEDGER_NAME__", LEDGER_NAME).replace("__FAMILY_NAME__", FAMILY_NAME)

_PROBE = base._PROBE
anchor = "def _v04874612_capture_input(kind, call_id, evaluation_index, sequence, state):"
if _PROBE.count(anchor) != 1:
    raise RuntimeError("v46.20.2 source-probe input anchor missing or ambiguous")
_PROBE = _PROBE.replace(anchor, _EXTRA_CODE + "\n\n" + anchor, 1)
result_hook = "    _v04874620_capture_type99_thermal(kind, call_id, evaluation_index, sequence, result)"
if _PROBE.count(result_hook) != 1:
    raise RuntimeError("v46.20.2 source-probe result hook missing or ambiguous")
_PROBE = _PROBE.replace(
    result_hook,
    result_hook + "\n    _v048746202_capture_magnesium_primary_source_order(kind, call_id, evaluation_index, sequence, result)",
    1,
)
final_hook = "    _v04874620_write_type99()"
if _PROBE.count(final_hook) != 1:
    raise RuntimeError("v46.20.2 source-probe finalize hook missing or ambiguous")
_PROBE = _PROBE.replace(final_hook, final_hook + "\n    _v048746202_write_magnesium_primary_source_order()", 1)
_PROBE = _PROBE.replace(
    '"magnesium_type99_thermal_rows": len(_STATE.get("v04874620_type99_ledger", [])),',
    '"magnesium_type99_thermal_rows": len(_STATE.get("v04874620_type99_ledger", [])), "magnesium_primary_cooling_source_order_rows": len(_STATE.get("v048746202_mg_primary_ledger", [])),',
    1,
)
compile(_PROBE, "<v048746202-all61-magnesium-primary-cooling-source-order-probe>", "exec")
_DRIVER = base._DRIVER.replace(
    "import v04874620_all61_magnesium_type99_primary_cooling_probe_runtime as probe",
    "import v048746202_all61_magnesium_primary_cooling_source_order_probe_runtime as probe",
)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _exact(a: str | float, b: str | float) -> bool:
    try:
        return float(a).hex() == float(b).hex()
    except Exception:
        return False


def verify(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    errors: list[str] = []
    base_result = base.verify(bundle)
    if base_result.get("result") != "ACCEPT":
        errors.extend(f"base:{item}" for item in base_result.get("errors", []))
    ledger_path = bundle / LEDGER_NAME
    family_path = bundle / FAMILY_NAME
    for path in (ledger_path, family_path):
        if not path.is_file():
            errors.append(f"missing:{path.name}")
    ledger = _read_csv(ledger_path) if ledger_path.is_file() else []
    family = _read_csv(family_path) if family_path.is_file() else []

    rows_by_sequence: dict[int, list[dict[str, str]]] = {}
    all_keys: set[tuple[int, int, str]] = set()
    for row in ledger:
        try:
            sequence = int(row["sequence"])
            record = int(row["record"])
            role = row["role"]
            order = int(row["source_order_index"])
            cj = float(row["cj"])
            pop = float(row["weighted_population"])
            cooling = float(row["cooling_contribution"])
            if sequence < 1 or sequence > 61 or record <= 0 or order <= 0 or not role:
                raise ValueError("identity")
            if not (cj > 0.0) or not all(math.isfinite(v) for v in (cj, pop, cooling)):
                raise ValueError("finite-positive")
            if not _exact(cooling, pop * cj):
                raise ValueError("cooling_identity")
            key = (sequence, record, role)
            if key in all_keys:
                raise ValueError("duplicate_key")
            all_keys.add(key)
            rows_by_sequence.setdefault(sequence, []).append(row)
        except Exception as exc:
            errors.append(f"invalid_ledger_row:{exc}")
            break

    if set(rows_by_sequence) != set(range(1, EXPECTED_EVALUATIONS + 1)):
        errors.append(f"ledger_sequence_inventory={len(rows_by_sequence)}")
    source_order_exact = 0
    row_counts: dict[int, int] = {}
    reduced_by_sequence: dict[int, float] = {}
    for sequence, rows in sorted(rows_by_sequence.items()):
        rows.sort(key=lambda row: int(row["source_order_index"]))
        orders = [int(row["source_order_index"]) for row in rows]
        if len(orders) != len(set(orders)) or any(left >= right for left, right in zip(orders, orders[1:])):
            errors.append(f"source_order_not_strict:{sequence}")
            break
        total = 0.0
        for row in rows:
            total += float(row["cooling_contribution"])
        reduced_by_sequence[sequence] = total
        row_counts[sequence] = len(rows)

    family_by_sequence = {int(row["sequence"]): row for row in family}
    if len(family) != EXPECTED_EVALUATIONS or set(family_by_sequence) != set(range(1, 62)):
        errors.append(f"family_sequence_inventory={len(family_by_sequence)}")
    for sequence in range(1, 62):
        row = family_by_sequence.get(sequence)
        if row is None or sequence not in reduced_by_sequence:
            continue
        if int(row["positive_primary_rows"]) != row_counts[sequence]:
            errors.append(f"family_row_count_mismatch:{sequence}")
            break
        if not _exact(row["source_order_reduced_mg_cooling"], reduced_by_sequence[sequence]):
            errors.append(f"family_csv_reduction_mismatch:{sequence}")
            break
        if not _exact(row["source_order_reduced_mg_cooling"], row["source_mg_cooling"]):
            errors.append(f"source_order_reduction_mismatch:{sequence}")
            break
        if int(row["reduction_exact"]) != 1:
            errors.append(f"source_order_reduction_flag:{sequence}")
            break
        source_order_exact += 1

    return {
        "schema": VERIFY_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "evaluations": len(family_by_sequence),
        "magnesium_primary_cooling_rows": len(ledger),
        "magnesium_primary_cooling_rows_by_sequence": {str(k): v for k, v in sorted(row_counts.items())},
        "magnesium_primary_cooling_source_order_exact": source_order_exact,
        "type99_capture_result": base_result.get("result", "REJECT"),
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if base.base.base.base.base.base._sha256(source_archive) != base.base.base.base.base.base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v048746202_") as tmp:
        tmp_path = Path(tmp)
        base.base.base.base.base.base._safe_extract(source_archive, tmp_path / "source")
        root = base.base.base.base.base.base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        (probe_dir / "v048746202_all61_magnesium_primary_cooling_source_order_probe_runtime.py").write_text(_PROBE)
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
        log = output_dir / "v0472_all61_magnesium_primary_cooling_source_order_capture_run.log"
        with log.open("w") as handle:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(
                f"v0.6.47.2 magnesium primary-cooling source-order capture failed with exit {completed.returncode}; see {log}")
    base.base.base._normalize_capture_reports(output_dir)
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    _write_json(output_dir / REPORT_NAME, result)
    files: dict[str, dict[str, Any]] = {}
    for name in (LEDGER_NAME, FAMILY_NAME, REPORT_NAME, VERIFY_NAME):
        path = output_dir / name
        if path.is_file():
            files[name] = {
                "sha256": base.base.base.base.base.base._sha256(path),
                "size_bytes": path.stat().st_size,
            }
    _write_json(output_dir / MANIFEST_NAME, {
        **result, "immutable": result["result"] == "ACCEPT", "files": files,
    })
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
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
        result = (
            capture(args.source_archive, args.atdb_path, args.output_dir, args.parameters_json, args.coheat_path)
            if args.cmd == "capture" else verify(args.bundle)
        )
    except Exception as exc:
        result = {
            "schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT",
            "errors": [str(exc)], "qualification_only": True,
            "production_promotion_ready": False,
        }
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
