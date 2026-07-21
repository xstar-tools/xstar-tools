"""Capture v0.6.47.2 Mg source-record contributions at the literal msolvelucy commit.

Patch 5.19.3 is diagnostic-only.  It extends the existing all-61 solve-stage
capture and records the ordered per-term updates used to construct the final
outer-iteration Mg condensed matrix for call-1 DSEC sequences 1..21.
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

from . import v0472_all61_solve_stage_capture_v0487462131 as base

RELEASE = "0.6.48.7.46.25.5.17.25.82-patch5.19.3"
SCHEMA = "xstar-tools-v82-patch5193-v0472-source-record-contribution-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v82-patch5193-v0472-source-record-contribution-oracle-v1"
CONTRIBUTION_NAME = "v0472_all61_solve_stage_record_contributions.csv"
REPORT_NAME = "all61_source_record_contribution_capture_report.json"
VERIFY_NAME = "all61_source_record_contribution_capture_verification.json"
BUNDLE_MANIFEST_NAME = "all61_source_record_contribution_capture_manifest.json"

_PROBE = base._PROBE
_PROBE = _PROBE.replace(
    '"all61_solve_stage_manifest": [], "linear_solve_trace_current": [], "final_counter": 0}',
    '"all61_solve_stage_manifest": [], "all61_source_record_contributions": [], '
    '"linear_solve_trace_current": [], "final_counter": 0}',
    1,
)

_CAPTURE = r'''
V82_PATCH5193_SOURCE_RECORD_CONTRIBUTION_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","final_outer_iteration",
 "term_index","source_position","record","data_type","rate_type","ion_index","ion_stage","role",
 "row","column","row_superlevel","column_superlevel","lower_endpoint","upper_endpoint",
 "source_row_unclamped","source_column_unclamped","source_ipmat_clamped","idest1","idest2","ucalc_status",
 "record_ans1","record_ans2","record_ans3","record_ans4","record_ans5","record_ans6",
 "row_fraction_mm","row_fraction_nn","term_aj1","term_aj2",
 "offdiag_contribution","diagonal_contribution","offdiag_before","offdiag_after","diagonal_before","diagonal_after"
]


def _v82_patch5193_capture_source_record_contributions(kind, call_id, evaluation_index, sequence, result):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    if not (1 <= int(sequence) <= 21):
        return
    for item in tuple(getattr(result, "element_results", ()) or ()):
        request = getattr(item, "request", None)
        z = int(_field(request, "element_z") or 0)
        if z != 12:
            continue
        eq = getattr(item, "equilibrium", None)
        assembly = getattr(eq, "assembly", None)
        solve = getattr(eq, "solve", None)
        if assembly is None or solve is None or getattr(solve, "trace", None) is None:
            continue
        basis = assembly.basis
        n = int(basis.n_rows)
        nsp = int(basis.n_superlevels)
        final_outer = int(solve.outer_iterations)
        outer_rows = {
            int(row["compact_index"]): row for row in solve.trace.outer_level_rows
            if int(row["outer_iteration"]) == final_outer
        }
        if len(outer_rows) != n:
            raise RuntimeError(
                f"incomplete final-outer rr trace sequence={sequence} element={z} rows={len(outer_rows)}/{n}"
            )
        rr = {i: float(outer_rows[i]["rr"]) for i in range(1, n + 1)}
        nsup = {i: int(basis.nsup[i]) for i in range(1, n + 1)}

        record_result = {}
        for row in tuple(getattr(assembly, "record_results", ()) or ()):
            try:
                record_result[int(row.get("record", 0))] = row
            except Exception:
                pass

        running = np.zeros((nsp + 1, nsp + 1), dtype=float)
        role_offset = {
            "forward_offdiag": 0,
            "reverse_offdiag": 1,
            "forward_diag_loss": 2,
            "reverse_diag_loss": 3,
        }
        for term in assembly.terms:
            mm = min(n, int(term.row))
            nn = min(n, int(term.column))
            nspm = int(nsup[mm])
            nspn = int(nsup[nn])
            if not (nspn != nspm and nspn != 0 and nspm != 0 and
                    (abs(float(term.aj1)) > 1.0e-48 or abs(float(term.aj2)) > 1.0e-48)):
                continue
            off_before = float(running[nspm, nspn])
            diag_before = float(running[nspm, nspm])
            off = float(term.aj1) * float(rr[nn])
            diag = -float(term.aj2) * float(rr[mm])
            running[nspm, nspn] = off_before + off
            running[nspm, nspm] = diag_before + diag
            rec = record_result.get(int(term.record), {})
            role = str(getattr(term, "role", ""))
            offset = int(role_offset.get(role, 0))
            source_position = int(getattr(term, "term_index", 0)) - offset
            _STATE["all61_source_record_contributions"].append({
                "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
                "evaluation_index": int(evaluation_index), "element_z": z,
                "final_outer_iteration": final_outer,
                "term_index": int(term.term_index), "source_position": source_position,
                "record": int(term.record), "data_type": int(term.data_type), "rate_type": int(term.rate_type),
                "ion_index": int(term.ion_index), "ion_stage": int(term.ion_stage), "role": role,
                "row": mm, "column": nn, "row_superlevel": nspm, "column_superlevel": nspn,
                "lower_endpoint": int(term.lower_endpoint), "upper_endpoint": int(term.upper_endpoint),
                "source_row_unclamped": int(term.source_row_unclamped),
                "source_column_unclamped": int(term.source_column_unclamped),
                "source_ipmat_clamped": int(bool(term.source_ipmat_clamped)),
                "idest1": int(term.idest1), "idest2": int(term.idest2), "ucalc_status": str(term.ucalc_status),
                "record_ans1": float(rec.get("ans1", float("nan"))),
                "record_ans2": float(rec.get("ans2", float("nan"))),
                "record_ans3": float(rec.get("ans3", float("nan"))),
                "record_ans4": float(rec.get("ans4", float("nan"))),
                "record_ans5": float(rec.get("ans5", float("nan"))),
                "record_ans6": float(rec.get("ans6", float("nan"))),
                "row_fraction_mm": float(rr[mm]), "row_fraction_nn": float(rr[nn]),
                "term_aj1": float(term.aj1), "term_aj2": float(term.aj2),
                "offdiag_contribution": off, "diagonal_contribution": diag,
                "offdiag_before": off_before, "offdiag_after": float(running[nspm, nspn]),
                "diagonal_before": diag_before, "diagonal_after": float(running[nspm, nspm]),
            })
'''
_PROBE = _PROBE.replace("ALL61_SOLVE_STAGE_ROW_FIELDS = [", _CAPTURE + "\nALL61_SOLVE_STAGE_ROW_FIELDS = [", 1)
_PROBE = _PROBE.replace(
    '    _v048746213_capture_solve_stages(kind, call_id, evaluation_index, sequence, result)\n',
    '    _v048746213_capture_solve_stages(kind, call_id, evaluation_index, sequence, result)\n'
    '    _v82_patch5193_capture_source_record_contributions(kind, call_id, evaluation_index, sequence, result)\n',
    1,
)
_PROBE = _PROBE.replace(
    '      "v0472_all61_solve_stage_manifest.csv": lambda row: (int(row["sequence"]), int(row["element_z"])),\n',
    '      "v0472_all61_solve_stage_manifest.csv": lambda row: (int(row["sequence"]), int(row["element_z"])),\n'
    '      "v0472_all61_solve_stage_record_contributions.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["term_index"])),\n',
    1,
)
_PROBE = _PROBE.replace(
    '      ("v0472_all61_solve_stage_manifest.csv", ALL61_SOLVE_STAGE_MANIFEST_FIELDS, _STATE["all61_solve_stage_manifest"]),\n',
    '      ("v0472_all61_solve_stage_manifest.csv", ALL61_SOLVE_STAGE_MANIFEST_FIELDS, _STATE["all61_solve_stage_manifest"]),\n'
    '      ("v0472_all61_solve_stage_record_contributions.csv", V82_PATCH5193_SOURCE_RECORD_CONTRIBUTION_FIELDS, _STATE["all61_source_record_contributions"]),\n',
    1,
)
_PROBE = _PROBE.replace(
    f'"schema": "{base.SCHEMA}"',
    f'"schema": "{SCHEMA}"',
)
_DRIVER = base._DRIVER.replace(
    "import v048746213_solve_stage_probe_runtime as probe",
    "import v82_patch5193_source_record_probe_runtime as probe",
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def verify(bundle: Path) -> dict[str, Any]:
    bundle = bundle.resolve()
    errors: list[str] = []
    stage = base.verify(bundle)
    if stage.get("result") != "ACCEPT":
        errors.append("solve_stage_parent_verify_reject")
    contribution_path = bundle / CONTRIBUTION_NAME
    if not contribution_path.is_file():
        errors.append(f"missing:{CONTRIBUTION_NAME}")
        rows: list[dict[str, str]] = []
    else:
        rows = _read_csv(contribution_path)
    seqs = {int(r["sequence"]) for r in rows} if rows else set()
    elements = {int(r["element_z"]) for r in rows} if rows else set()
    if seqs != set(range(1, 22)):
        errors.append(f"call1_sequence_coverage={sorted(seqs)}")
    if elements and elements != {12}:
        errors.append(f"unexpected_elements={sorted(elements)}")
    if rows and any(int(r["final_outer_iteration"]) <= 0 for r in rows):
        errors.append("invalid_final_outer_iteration")
    if rows and any(int(r["row_superlevel"]) == int(r["column_superlevel"]) for r in rows):
        errors.append("same_superlevel_commit_captured")

    # Verify that replayed source commits recover every non-normalization Mg
    # condensed cell available in the parent solve-stage oracle for sequences 1..21.
    matrix_path = bundle / base.MATRIX_NAME
    matrix = _read_csv(matrix_path) if matrix_path.is_file() else []
    replay: dict[tuple[int, int, int], float] = {}
    for r in rows:
        key = (int(r["sequence"]), int(r["row_superlevel"]), int(r["column_superlevel"]))
        replay[key] = replay.get(key, 0.0) + float(r["offdiag_contribution"])
        dkey = (int(r["sequence"]), int(r["row_superlevel"]), int(r["row_superlevel"]))
        replay[dkey] = replay.get(dkey, 0.0) + float(r["diagonal_contribution"])
    matrix_checked = 0
    matrix_bad = 0
    for r in matrix:
        seq = int(r["sequence"]); z = int(r["element_z"])
        row = int(r["row_superlevel"]); col = int(r["column_superlevel"])
        if z != 12 or not (1 <= seq <= 21):
            continue
        # Source normalization row is overwritten after contribution assembly.
        manifest = None
        # For these Mg call-1 systems the normalization row is compact-row 552,
        # which belongs to the final superlevel.  Skip that superlevel row.
        nsp = max((int(x["row_superlevel"]) for x in matrix if int(x["sequence"]) == seq and int(x["element_z"]) == 12), default=0)
        if row == nsp:
            continue
        expected = float(r["normalized_matrix_value"])
        actual = replay.get((seq, row, col), 0.0)
        matrix_checked += 1
        if abs(expected - actual) > max(1.0e-12, abs(expected) * 1.0e-13):
            matrix_bad += 1
    if matrix_checked == 0:
        errors.append("no_matrix_cells_verified")
    if matrix_bad:
        errors.append(f"matrix_replay_bad_cells={matrix_bad}")

    return {
        "schema": VERIFY_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "actual_v0472_runtime_capture": bool(stage.get("actual_v0472_runtime_capture")),
        "call1_mg_sequences": len(seqs),
        "source_record_contribution_rows": len(rows),
        "matrix_replay_cells_checked": matrix_checked,
        "matrix_replay_bad_cells": matrix_bad,
        "source_record_level_terms_available": bool(rows) and matrix_bad == 0,
        "qualification_only": True,
        "production_promotion_ready": False,
    }


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if base.base.base.base._sha256(source_archive) != base.base.base.base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v82_patch5193_source_") as tmp:
        tmp_path = Path(tmp)
        base.base.base.base._safe_extract(source_archive, tmp_path / "source")
        root = base.base.base.base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"
        probe_dir.mkdir()
        (probe_dir / "v82_patch5193_source_record_probe_runtime.py").write_text(_PROBE)
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
        log = output_dir / "v0472_all61_source_record_contribution_capture_run.log"
        with log.open("w") as handle:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 source-record capture failed with exit {completed.returncode}; see {log}")
    historical = output_dir / "capture_report.json"
    if historical.is_file():
        import shutil
        shutil.copy2(historical, output_dir / base.REPORT_NAME)
        historical.replace(output_dir / REPORT_NAME)
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    files: dict[str, Any] = {}
    for path in sorted(output_dir.glob("v0472_all61_*.csv")):
        files[path.name] = {"sha256": base.base.base.base._sha256(path), "size_bytes": path.stat().st_size}
    for name in (REPORT_NAME, VERIFY_NAME):
        path = output_dir / name
        if path.is_file():
            files[name] = {"sha256": base.base.base.base._sha256(path), "size_bytes": path.stat().st_size}
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
