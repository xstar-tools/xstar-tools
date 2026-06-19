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

RELEASE = "0.6.48.7.46.17.2"
SCHEMA = "xstar-tools-v06487467-v0472-all61-post-seed-system-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v06487467-v0472-all61-post-seed-system-oracle-v1"
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
CONTRIBUTION_INT_COLUMNS = 14
CONTRIBUTION_REAL_COLUMNS = 16

_SYSTEM_CAPTURE_CODE = r'''
import csv as _v048746_csv
import hashlib as _v048746_hashlib
from pathlib import Path as _v048746_Path
import numpy as _v048746_np

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
 "matrix_contribution_ints_path","matrix_contribution_int_rows","matrix_contribution_int_columns","matrix_contribution_ints_sha256",
 "matrix_contribution_reals_path","matrix_contribution_real_rows","matrix_contribution_real_columns","matrix_contribution_reals_sha256",
]
_STATE.setdefault("all61_solve_systems", [])

def _v048746_sha256(path):
    digest = _v048746_hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _v048746_write_array(directory, name, value):
    array = _v048746_np.ascontiguousarray(_v048746_np.asarray(value, dtype=_v048746_np.float64).reshape(-1))
    path = directory / (name + ".bin")
    array.tofile(path)
    return path, int(array.size), _v048746_sha256(path)

def _v048746_write_int64_array(directory, name, value):
    array = _v048746_np.ascontiguousarray(_v048746_np.asarray(value, dtype=_v048746_np.int64).reshape(-1))
    path = directory / (name + ".bin")
    array.tofile(path)
    return path, int(array.size), _v048746_sha256(path)

def _v048746_pack_matrix_contributions(assembly):
    terms = list(assembly.terms)
    if len(terms) % 4 != 0:
        raise RuntimeError(f"source matrix term stream is not four-term grouped: terms={len(terms)}")
    ints = []
    reals = []
    expected_roles = ("forward_offdiag", "reverse_offdiag", "forward_diag_loss", "reverse_diag_loss")
    for group_start in range(0, len(terms), 4):
        group = terms[group_start:group_start + 4]
        roles = tuple(str(term.role) for term in group)
        if roles != expected_roles:
            raise RuntimeError(
                f"source matrix contribution role sequence mismatch at term {group_start + 1}: {roles}"
            )
        identity = tuple(
            (int(term.record), int(term.data_type), int(term.rate_type),
             int(term.ion_index), int(term.ion_stage))
            for term in group
        )
        if len(set(identity)) != 1:
            raise RuntimeError(f"source matrix contribution identity mismatch at term {group_start + 1}")
        forward, reverse, lower_diag, upper_diag = group
        lower_row = int(forward.column)
        upper_row = int(forward.row)
        expected_cells = (
            (upper_row, lower_row), (lower_row, upper_row),
            (lower_row, lower_row), (upper_row, upper_row),
        )
        actual_cells = tuple((int(term.row), int(term.column)) for term in group)
        if actual_cells != expected_cells:
            raise RuntimeError(
                f"source matrix contribution cell sequence mismatch at term {group_start + 1}: "
                f"actual={actual_cells} expected={expected_cells}"
            )
        record, data_type, rate_type, ion_index, ion_stage = identity[0]
        ints.append([
            group_start // 4 + 1, int(forward.term_index), record, data_type, rate_type,
            ion_index, ion_stage, lower_row, upper_row,
            int(any(bool(getattr(term, "source_ipmat_clamped", False)) for term in group)),
            int(getattr(forward, "idest1", 0)), int(getattr(forward, "idest2", 0)),
            int(getattr(forward, "lower_endpoint", 0)), int(getattr(forward, "upper_endpoint", 0)),
        ])
        reals.append([
            float(forward.aj1), float(forward.aj2), float(forward.cj), float(forward.cj2),
            float(reverse.aj1), float(reverse.aj2), float(reverse.cj), float(reverse.cj2),
            float(lower_diag.aj1), float(lower_diag.aj2), float(lower_diag.cj), float(lower_diag.cj2),
            float(upper_diag.aj1), float(upper_diag.aj2), float(upper_diag.cj), float(upper_diag.cj2),
        ])
    return (
        _v048746_np.asarray(ints, dtype=_v048746_np.int64).reshape((-1, 14)),
        _v048746_np.asarray(reals, dtype=_v048746_np.float64).reshape((-1, 16)),
    )

def _v048746_capture_solve_system(kind, call_id, evaluation_index, sequence, z, abundance, assembly, solve):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    n = int(assembly.basis.n_rows)
    stages = _v048746_np.asarray(assembly.basis.ion_stage, dtype=_v048746_np.int32)
    active_values = [int(stages[i]) for i in range(1, min(n + 1, stages.size))]
    active_min = min(active_values) if active_values else 0
    active_max = max(active_values) if active_values else 0
    n_ions = int(assembly.basis.n_ions)
    contribution_ints, contribution_reals = _v048746_pack_matrix_contributions(assembly)
    arrays = {
      "dense_matrix": _v048746_np.asarray(assembly.dense_matrix, dtype=_v048746_np.float64),
      "heating_matrix": _v048746_np.asarray(assembly.heating_matrix, dtype=_v048746_np.float64),
      "heating_matrix2": _v048746_np.asarray(assembly.heating_matrix2, dtype=_v048746_np.float64),
      "rhs": _v048746_np.asarray(assembly.rhs, dtype=_v048746_np.float64),
      "solver_input": _v048746_np.asarray(assembly.initial_populations[1:n+1], dtype=_v048746_np.float64),
      "outer": _v048746_np.asarray(solve.final_outer_start_populations, dtype=_v048746_np.float64),
      "final": _v048746_np.asarray(solve.populations, dtype=_v048746_np.float64),
      "ion_reconstruction": _v048746_np.asarray(solve.ion_population_totals_final_vector, dtype=_v048746_np.float64),
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
    relative = _v048746_Path("v0472_all61_solve_systems") / f"evaluation_{int(sequence):04d}" / f"element_{int(z):02d}"
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
    ints_path, ints_count, ints_digest = _v048746_write_int64_array(
        directory, "matrix_contribution_ints", contribution_ints
    )
    reals_path, reals_count, reals_digest = _v048746_write_array(
        directory, "matrix_contribution_reals", contribution_reals
    )
    row["matrix_contribution_ints_path"] = str(ints_path.relative_to(_OUT))
    row["matrix_contribution_int_rows"] = int(contribution_ints.shape[0])
    row["matrix_contribution_int_columns"] = int(contribution_ints.shape[1])
    row["matrix_contribution_ints_sha256"] = str(ints_digest)
    row["matrix_contribution_reals_path"] = str(reals_path.relative_to(_OUT))
    row["matrix_contribution_real_rows"] = int(contribution_reals.shape[0])
    row["matrix_contribution_real_columns"] = int(contribution_reals.shape[1])
    row["matrix_contribution_reals_sha256"] = str(reals_digest)
    if ints_count != contribution_ints.size or reals_count != contribution_reals.size:
        raise RuntimeError("matrix contribution binary count mismatch")
    _STATE["all61_solve_systems"].append(row)

def _v048746_write_solve_system_manifest():
    rows = sorted(
        _STATE.get("all61_solve_systems", []),
        key=lambda row: (int(row["sequence"]), int(row["element_z"])),
    )
    path = _OUT / "v0472_all61_solve_system_manifest.csv"
    with path.open("w", newline="") as handle:
        writer = _v048746_csv.DictWriter(handle, fieldnames=V048746_SYSTEM_FIELDS, extrasaction="ignore")
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
    "import v0487467_all61_post_seed_probe_runtime as probe",
)


def probe_capture_behavioral_self_test(output_dir: Path | None = None) -> dict[str, Any]:
    """Execute the injected system-capture block with three synthetic elements.

    This catches runtime-only probe defects such as missing imports that ordinary
    ``compile(_PROBE, ...)`` validation cannot detect.
    """
    import tempfile
    from types import SimpleNamespace

    import numpy as np

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if output_dir is None:
        temporary = tempfile.TemporaryDirectory(prefix="v0487467_probe_self_test_")
        root = Path(temporary.name)
    else:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)

    namespace: dict[str, Any] = {
        "_STATE": {},
        "_OUT": root,
        "_v048743_canonical_sequence": lambda kind, call_id, evaluation_index: int(evaluation_index),
    }
    try:
        exec(_SYSTEM_CAPTURE_CODE, namespace)
        capture_fn = namespace["_v048746_capture_solve_system"]
        write_manifest = namespace["_v048746_write_solve_system_manifest"]
        expected_files: list[Path] = []
        for sequence, z, n, n_ions in ((1, 1, 3, 2), (2, 2, 4, 3), (3, 12, 5, 4)):
            basis = SimpleNamespace(
                n_rows=n,
                n_ions=n_ions,
                normalization_row=n,
                ion_stage=np.asarray([0] + list(range(1, n + 1)), dtype=np.int32),
            )
            dense = np.arange(n * n, dtype=np.float64).reshape(n, n) + float(z)
            terms = []
            term_index = 1
            for contribution_index in range(2):
                lower = 1 + contribution_index
                upper = min(n, lower + 1)
                ans1 = float(z + contribution_index + 0.125)
                ans2 = float(z + contribution_index + 0.25)
                ans3 = float(z + contribution_index + 0.375)
                ans4 = float(z + contribution_index + 0.5)
                ans5 = float(z + contribution_index + 0.625)
                ans6 = float(z + contribution_index + 0.75)
                xpx = 10.0
                specs = (
                    ("forward_offdiag", upper, lower, ans1, ans2, 0.0, 0.0),
                    ("reverse_offdiag", lower, upper, ans2, ans1, 0.0, 0.0),
                    ("forward_diag_loss", lower, lower, -ans1, -ans1, ans4*xpx, ans6*xpx),
                    ("reverse_diag_loss", upper, upper, -ans2, -ans2, -ans3*xpx, -ans5*xpx),
                )
                for role, row_index, column_index, aj1, aj2, cj, cj2 in specs:
                    terms.append(SimpleNamespace(
                        term_index=term_index, record=1000+contribution_index, data_type=53,
                        rate_type=7, ion_index=1, ion_stage=1, role=role,
                        row=row_index, column=column_index, aj1=aj1, aj2=aj2, cj=cj, cj2=cj2,
                        idest1=1, idest2=2, lower_endpoint=1, upper_endpoint=2,
                        source_ipmat_clamped=False,
                    ))
                    term_index += 1
            assembly = SimpleNamespace(
                basis=basis,
                terms=terms,
                dense_matrix=dense,
                heating_matrix=dense + 0.25,
                heating_matrix2=dense + 0.5,
                rhs=np.arange(n, dtype=np.float64) + 0.75,
                initial_populations=np.arange(n + 1, dtype=np.float64) + 1.0,
            )
            solve = SimpleNamespace(
                final_outer_start_populations=np.arange(n, dtype=np.float64) + 2.0,
                populations=np.arange(n, dtype=np.float64) + 3.0,
                ion_population_totals_final_vector=np.arange(n_ions, dtype=np.float64) + 4.0,
                solver_method="synthetic",
                converged=True,
                outer_iterations=2,
                fixed_point_iterations=3,
                normalization=1.0,
                normalization_error=0.0,
            )
            capture_fn("dsec", sequence, sequence, sequence, z, 1.0, assembly, solve)
            directory = root / SYSTEM_DIR_NAME / f"evaluation_{sequence:04d}" / f"element_{z:02d}"
            expected_files.extend(directory / f"{name}.bin" for name in ARRAY_NAMES)
            expected_files.extend([
                directory / "matrix_contribution_ints.bin",
                directory / "matrix_contribution_reals.bin",
            ])
        write_manifest()

        manifest = root / SYSTEM_MANIFEST_NAME
        rows = _read_csv(manifest) if manifest.is_file() else []
        missing = [str(path.relative_to(root)) for path in expected_files if not path.is_file()]
        wrong_sizes = [
            str(path.relative_to(root))
            for path in expected_files
            if path.is_file() and path.stat().st_size <= 0
        ]
        errors: list[str] = []
        if len(rows) != 3:
            errors.append(f"manifest_rows={len(rows)} expected=3")
        if len(expected_files) != 30:
            errors.append(f"expected_files={len(expected_files)} expected=30")
        contribution_shapes = {
            (int(row.get("matrix_contribution_int_rows", 0)),
             int(row.get("matrix_contribution_int_columns", 0)),
             int(row.get("matrix_contribution_real_rows", 0)),
             int(row.get("matrix_contribution_real_columns", 0)))
            for row in rows
        }
        if contribution_shapes != {(2, 14, 2, 16)}:
            errors.append(f"contribution_shapes={sorted(contribution_shapes)} expected=[(2,14,2,16)]")
        if missing:
            errors.append(f"missing_files={missing}")
        if wrong_sizes:
            errors.append(f"empty_files={wrong_sizes}")
        return {
            "schema": "xstar-tools-v06487467-probe-behavioral-self-test-v1",
            "release": RELEASE,
            "result": "ACCEPT" if not errors else "REJECT",
            "errors": errors,
            "systems": len(rows),
            "binary_arrays": len(expected_files) - len(missing),
            "manifest": str(manifest),
        }
    except Exception as exc:
        return {
            "schema": "xstar-tools-v06487467-probe-behavioral-self-test-v1",
            "release": RELEASE,
            "result": "REJECT",
            "errors": [f"{type(exc).__name__}: {exc}"],
            "systems": 0,
            "binary_arrays": 0,
        }
    finally:
        if temporary is not None:
            temporary.cleanup()


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
            contribution_rows = int(row.get("matrix_contribution_int_rows", 0))
            int_columns = int(row.get("matrix_contribution_int_columns", 0))
            real_rows = int(row.get("matrix_contribution_real_rows", 0))
            real_columns = int(row.get("matrix_contribution_real_columns", 0))
            if contribution_rows <= 0 or contribution_rows != real_rows:
                errors.append(
                    f"contribution_rows:{row['sequence']}:{row['element_z']}:"
                    f"ints={contribution_rows}:reals={real_rows}"
                )
            if int_columns != CONTRIBUTION_INT_COLUMNS or real_columns != CONTRIBUTION_REAL_COLUMNS:
                errors.append(
                    f"contribution_columns:{row['sequence']}:{row['element_z']}:"
                    f"ints={int_columns}:reals={real_columns}"
                )
            for kind_name, item_rows, item_columns, dtype_size in (
                ("matrix_contribution_ints", contribution_rows, int_columns, 8),
                ("matrix_contribution_reals", real_rows, real_columns, 8),
            ):
                path = bundle / row[f"{kind_name}_path"]
                expected_bytes = item_rows * item_columns * dtype_size
                if not path.is_file():
                    errors.append(f"missing_array:{path}")
                    continue
                if path.stat().st_size != expected_bytes:
                    errors.append(
                        f"size_mismatch:{path}:{path.stat().st_size}!={expected_bytes}"
                    )
                    continue
                if _sha256(path) != row[f"{kind_name}_sha256"]:
                    errors.append(f"sha256_mismatch:{path}")
                    continue
                arrays += 1
                bytes_total += expected_bytes
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
    with tempfile.TemporaryDirectory(prefix="v0487467_") as raw:
        temp = Path(raw)
        fixed.base.base._safe_extract(source_archive, temp / "source")
        root = fixed.base.base._source_root(temp / "source")
        probe_dir = temp / "probe"
        probe_dir.mkdir()
        (probe_dir / "v0487467_all61_post_seed_probe_runtime.py").write_text(_PROBE)
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
