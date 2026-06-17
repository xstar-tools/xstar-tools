"""Capture all 61 immutable v0.6.47.2 post-seed element solve systems.

This qualification-only capture extends the accepted all-61 fixed-state capture
with eight raw float64 arrays for each H/He/Mg element solve: dense matrix,
primary and secondary heating matrices, RHS, transformed solver input, final
outer-start vector, final compact population, and active-ion reconstruction.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import v0472_all61_fixed_state_capture as fixed

RELEASE = "0.6.48.7.46.6"
SCHEMA = "xstar-tools-v06487466-v0472-all61-post-seed-system-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v06487466-v0472-all61-post-seed-system-oracle-v1"
SYSTEM_MANIFEST_NAME = "v0472_all61_solve_system_manifest.csv"
REPORT_NAME = "all61_post_seed_system_capture_report.json"
VERIFY_NAME = "all61_post_seed_system_capture_verification.json"
MANIFEST_NAME = "all61_post_seed_system_capture_manifest.json"
SYSTEM_DIR_NAME = "v0472_all61_solve_systems"
ARRAY_NAMES = (
    "dense_matrix",
    "heating_matrix",
    "heating_matrix2",
    "rhs",
    "solver_input",
    "outer",
    "final",
    "ion_reconstruction",
)

_SYSTEM_CAPTURE_CODE = r'''
import hashlib as _v048746_hashlib

V048746_SYSTEM_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","abundance",
 "active_min_stage","active_max_stage","n_rows","n_ions","normalization_row",
 "solver_method","converged","outer_iterations","fixed_point_iterations",
 "normalization","normalization_error",
 "dense_matrix_path","dense_matrix_count","dense_matrix_sha256",
 "heating_matrix_path","heating_matrix_count","heating_matrix_sha256",
 "heating_matrix2_path","heating_matrix2_count","heating_matrix2_sha256",
 "rhs_path","rhs_count","rhs_sha256",
 "solver_input_path","solver_input_count","solver_input_sha256",
 "outer_path","outer_count","outer_sha256",
 "final_path","final_count","final_sha256",
 "ion_reconstruction_path","ion_reconstruction_count","ion_reconstruction_sha256",
]
_STATE.setdefault("all61_solve_systems", [])

def _v048746_sha256(path):
    digest = _v048746_hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _v048746_write_array(directory, name, value):
    array = np.ascontiguousarray(np.asarray(value, dtype=np.float64).reshape(-1))
    path = directory / (name + ".bin")
    array.tofile(path)
    return path, int(array.size), _v048746_sha256(path)

def _v048746_capture_solve_system(kind, call_id, evaluation_index, sequence, z, abundance, assembly, solve):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    n = int(assembly.basis.n_rows)
    stages = np.asarray(assembly.basis.ion_stage, dtype=np.int32)
    active_values = [int(stages[i]) for i in range(1, min(n + 1, stages.size))]
    active_min = min(active_values) if active_values else 0
    active_max = max(active_values) if active_values else 0
    n_ions = int(assembly.basis.n_ions)
    arrays = {
      "dense_matrix": np.asarray(assembly.dense_matrix, dtype=np.float64),
      "heating_matrix": np.asarray(assembly.heating_matrix, dtype=np.float64),
      "heating_matrix2": np.asarray(assembly.heating_matrix2, dtype=np.float64),
      "rhs": np.asarray(assembly.rhs, dtype=np.float64),
      "solver_input": np.asarray(assembly.initial_populations[1:n+1], dtype=np.float64),
      "outer": np.asarray(solve.final_outer_start_populations, dtype=np.float64),
      "final": np.asarray(solve.populations, dtype=np.float64),
      "ion_reconstruction": np.asarray(solve.ion_population_totals_final_vector, dtype=np.float64),
    }
    expected = {
      "dense_matrix": n * n,
      "heating_matrix": n * n,
      "heating_matrix2": n * n,
      "rhs": n,
      "solver_input": n,
      "outer": n,
      "final": n,
      "ion_reconstruction": n_ions,
    }
    for name, array in arrays.items():
        if int(array.size) != int(expected[name]):
            raise RuntimeError(
                f"invalid source solve-system {name} size z={z} n={n} "
                f"n_ions={n_ions} size={array.size} expected={expected[name]}"
            )
    relative = Path("v0472_all61_solve_systems") / f"evaluation_{int(sequence):04d}" / f"element_{int(z):02d}"
    directory = _OUT / relative
    directory.mkdir(parents=True, exist_ok=True)
    row = {
      "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
      "evaluation_index": int(evaluation_index), "element_z": int(z), "abundance": float(abundance),
      "active_min_stage": int(active_min), "active_max_stage": int(active_max),
      "n_rows": int(n), "n_ions": int(n_ions),
      "normalization_row": int(assembly.basis.normalization_row),
      "solver_method": str(solve.solver_method), "converged": int(bool(solve.converged)),
      "outer_iterations": int(solve.outer_iterations),
      "fixed_point_iterations": int(solve.fixed_point_iterations),
      "normalization": float(solve.normalization),
      "normalization_error": float(solve.normalization_error),
    }
    for name, array in arrays.items():
        path, count, digest = _v048746_write_array(directory, name, array)
        row[name + "_path"] = str(path.relative_to(_OUT))
        row[name + "_count"] = int(count)
        row[name + "_sha256"] = str(digest)
    _STATE["all61_solve_systems"].append(row)

def _v048746_write_solve_system_manifest():
    rows = sorted(
        _STATE.get("all61_solve_systems", []),
        key=lambda row: (int(row["sequence"]), int(row["element_z"])),
    )
    path = _OUT / "v0472_all61_solve_system_manifest.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=V048746_SYSTEM_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
'''

_PROBE = fixed._PROBE
_PROBE = _PROBE.replace(
    "def _v048744_capture_solve_rows(kind, call_id, evaluation_index, sequence, result):",
    _SYSTEM_CAPTURE_CODE
    + "\n\ndef _v048744_capture_solve_rows(kind, call_id, evaluation_index, sequence, result):",
    1,
)
_PROBE = _PROBE.replace(
    "        if assembly is None or solve is None:\n            continue\n        basis = assembly.basis",
    "        if assembly is None or solve is None:\n            continue\n"
    "        _v048746_capture_solve_system(kind, call_id, evaluation_index, sequence, z, "
    "float(_field(request, 'abundance') or 0.0), assembly, solve)\n"
    "        basis = assembly.basis",
    1,
)
_PROBE = _PROBE.replace(
    "def finalize(run_summary=None):\n    _v048742_write_all61()",
    "def finalize(run_summary=None):\n    _v048746_write_solve_system_manifest()\n    _v048742_write_all61()",
    1,
)
_DRIVER = fixed._DRIVER.replace(
    "import v048744_all61_probe_runtime as probe",
    "import v0487466_all61_post_seed_probe_runtime as probe",
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(bundle: Path) -> dict[str, Any]:
    base_result = fixed.verify(bundle)
    errors = list(base_result.get("errors", []))
    manifest_path = bundle / SYSTEM_MANIFEST_NAME
    rows: list[dict[str, str]] = []
    arrays = 0
    bytes_total = 0
    if not manifest_path.is_file():
        errors.append(f"missing:{SYSTEM_MANIFEST_NAME}")
    else:
        rows = _read_csv(manifest_path)
        identities = {(int(row["sequence"]), int(row["element_z"])) for row in rows}
        expected_identities = {(sequence, z) for sequence in range(1, 62) for z in (1, 2, 12)}
        if identities != expected_identities or len(rows) != 183:
            errors.append(f"solve_system_inventory={len(rows)} identities={len(identities)}")
        for row in rows:
            n = int(row["n_rows"])
            n_ions = int(row["n_ions"])
            expected_counts = {
                "dense_matrix": n * n,
                "heating_matrix": n * n,
                "heating_matrix2": n * n,
                "rhs": n,
                "solver_input": n,
                "outer": n,
                "final": n,
                "ion_reconstruction": n_ions,
            }
            for name in ARRAY_NAMES:
                path = bundle / row[f"{name}_path"]
                count = int(row[f"{name}_count"])
                if count != expected_counts[name]:
                    errors.append(
                        f"count_mismatch:{row['sequence']}:{row['element_z']}:{name}:{count}!={expected_counts[name]}"
                    )
                    continue
                if not path.is_file():
                    errors.append(f"missing_array:{path}")
                    continue
                expected_bytes = count * 8
                actual_bytes = path.stat().st_size
                if actual_bytes != expected_bytes:
                    errors.append(f"size_mismatch:{path}:{actual_bytes}!={expected_bytes}")
                    continue
                if _sha256(path) != row[f"{name}_sha256"]:
                    errors.append(f"sha256_mismatch:{path}")
                    continue
                arrays += 1
                bytes_total += actual_bytes
    result = {
        "schema": VERIFY_SCHEMA,
        "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT",
        "errors": errors,
        "actual_v0472_runtime_capture": bool(base_result.get("actual_v0472_runtime_capture")),
        "evaluations": int(base_result.get("evaluations", 0)),
        "solve_systems": len(rows),
        "binary_arrays": arrays,
        "binary_bytes": bytes_total,
        "basis_solve_rows": int(base_result.get("solve_rows", 0)),
        "workspace_sequence_contract_exact": bool(base_result.get("workspace_sequence_contract_exact")),
        "qualification_only": True,
        "production_promotion_ready": False,
        "thermal_parity_started": False,
    }
    return result


def capture(
    source_archive: Path,
    atdb_path: Path,
    output_dir: Path,
    parameters_json: Path,
    coheat_path: Path | None,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if fixed.base.base._sha256(source_archive) != fixed.base.base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v0487466_") as raw:
        temp = Path(raw)
        fixed.base.base._safe_extract(source_archive, temp / "source")
        root = fixed.base.base._source_root(temp / "source")
        probe_dir = temp / "probe"
        probe_dir.mkdir()
        (probe_dir / "v0487466_all61_post_seed_probe_runtime.py").write_text(_PROBE)
        (probe_dir / "probe_config.json").write_text(
            json.dumps({"output_dir": str(output_dir)}, indent=2)
        )
        (probe_dir / "driver.py").write_text(_DRIVER)
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(probe_dir), str(root / "src")])
        env.update(
            {
                "PYTHONFAULTHANDLER": "1",
                "PYTHONUNBUFFERED": "1",
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            }
        )
        command = [
            sys.executable,
            str(probe_dir / "driver.py"),
            "--parameters-json",
            str(parameters_json.resolve()),
            "--atdb-path",
            str(atdb_path.resolve()),
            "--output-dir",
            str(output_dir / "physical_run"),
        ]
        if coheat_path is not None:
            command += ["--coheat-path", str(coheat_path.resolve())]
        log = output_dir / "v0472_all61_post_seed_system_capture.log"
        with log.open("w") as handle:
            completed = subprocess.run(
                command,
                cwd=root,
                env=env,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
        if completed.returncode != 0:
            raise RuntimeError(
                f"v0.6.47.2 post-seed system capture failed with exit {completed.returncode}; see {log}"
            )
    historical = output_dir / "capture_report.json"
    if historical.is_file():
        historical.replace(output_dir / fixed.REPORT_NAME)
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    _write_json(output_dir / REPORT_NAME, result)
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != MANIFEST_NAME:
            files[str(path.relative_to(output_dir))] = {
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
    _write_json(
        output_dir / MANIFEST_NAME,
        {
            **result,
            "immutable": result["result"] == "ACCEPT",
            "files": files,
        },
    )
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
        if args.command == "capture":
            result = capture(
                args.source_archive,
                args.atdb_path,
                args.output_dir,
                args.parameters_json,
                args.coheat_path,
            )
        else:
            result = verify(args.bundle)
    except Exception as exc:
        result = {
            "schema": VERIFY_SCHEMA,
            "release": RELEASE,
            "result": "REJECT",
            "errors": [str(exc)],
            "qualification_only": True,
            "production_promotion_ready": False,
            "thermal_parity_started": False,
        }
    if args.output_json:
        _write_json(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("result") == "ACCEPT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
