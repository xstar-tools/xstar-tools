"""Capture all 61 immutable v0.6.47.2 H/He/Mg fixed-state evaluations.

The probe observes the 57 DSEC evaluations and the four retained final
fixed-state evaluations. It does not change rates, matrices, controller
branches, or products.
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

from . import v0472_full_dsec_thermal_budget_capture as base

RELEASE = "0.6.48.7.46.5"
SCHEMA = "xstar-tools-v0648744-v0472-all61-fixed-state-capture-v1"
VERIFY_SCHEMA = "xstar-tools-v0648744-v0472-all61-fixed-state-oracle-v1"
STATE_NAME = "v0472_all61_fixed_state_rows.csv"
INPUT_NAME = "v0472_all61_input_states.csv"
ION_NAME = "v0472_all61_ion_populations.csv"
LEVEL_NAME = "v0472_all61_level_populations.csv"
SOLVE_NAME = "v0472_all61_element_solve_rows.csv"
REPORT_NAME = "all61_fixed_state_capture_report.json"
VERIFY_NAME = "all61_fixed_state_capture_verification.json"
MANIFEST_NAME = "all61_fixed_state_capture_manifest.json"


def canonical_sequence(kind: str, call_id: int, evaluation_index: int) -> int:
    """Map a source fixed-state identity to the canonical 61-row trajectory."""
    call_id = int(call_id)
    evaluation_index = int(evaluation_index)
    if str(kind) == "final":
        if call_id not in (1, 2, 3, 4):
            raise ValueError(f"invalid final call_id={call_id}")
        return 57 + call_id
    offsets = {1: 0, 2: 21, 3: 22, 4: 40}
    limits = {1: 21, 2: 1, 3: 18, 4: 17}
    if call_id not in offsets or not (1 <= evaluation_index <= limits[call_id]):
        raise ValueError(f"invalid DSEC identity call={call_id} evaluation={evaluation_index}")
    return offsets[call_id] + evaluation_index


_PROBE = base._PROBE
_PROBE = _PROBE.replace(
    '"bypassed_retained_evaluators": 0}',
    '"bypassed_retained_evaluators": 0, "all61_states": [], "all61_ions": [], "all61_levels": [], "all61_inputs": [], "all61_solve_rows": [], "final_counter": 0}',
)

_CAPTURE_CODE = r'''
ALL61_STATE_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","temperature_k","temperature_t4",
 "electron_fraction_input","computed_electron_fraction","charge_residual","hmctot"
]
ALL61_ION_FIELDS = ["sequence","kind","dsec_call_id","evaluation_index","element_z","stage","ion_charge","population"]
ALL61_LEVEL_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","stage","local_level_ordinal",
 "global_level_index","population","bilevg","rnisg"
]
ALL61_SOLVE_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","element_z","abundance",
 "active_min_stage","active_max_stage","compact_row","ion","ion_stage","ion_charge",
 "superlevel","is_normalization_row","transformed_initial_population",
 "final_outer_start_population","final_population","rhs","row_residual","row_scale",
 "relative_row_residual","solver_method","converged"
]
ALL61_INPUT_FIELDS = [
 "sequence","kind","dsec_call_id","evaluation_index","temperature_k","temperature_t4",
 "electron_fraction_input","covering_fraction","turbulent_velocity_km_s","workspace_directory",
 "radiation_bins","continuum_tau_count","global_level_count"
]

def _v048743_canonical_sequence(kind, call_id, evaluation_index):
    call_id = int(call_id)
    evaluation_index = int(evaluation_index)
    if str(kind) == "final":
        if call_id not in (1, 2, 3, 4):
            raise ValueError(f"invalid final call_id={call_id}")
        return 57 + call_id
    offsets = {1: 0, 2: 21, 3: 22, 4: 40}
    limits = {1: 21, 2: 1, 3: 18, 4: 17}
    if call_id not in offsets or not (1 <= evaluation_index <= limits[call_id]):
        raise ValueError(f"invalid DSEC identity call={call_id} evaluation={evaluation_index}")
    return offsets[call_id] + evaluation_index

def _v048742_value(array, one_based_index):
    values = _array(array)
    index = int(one_based_index) - 1
    return float(values[index]) if 0 <= index < values.size else 0.0

def _v048742_capture_input(kind, call_id, evaluation_index, sequence, state):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    requests = tuple(getattr(state, "element_requests", ()) or ())
    request = requests[0] if requests else None
    radiation = _field(request, "radiation")
    escape = _field(request, "escape")
    directory = _OUT / "all61_input_workspaces" / f"evaluation_{int(sequence):04d}"
    directory.mkdir(parents=True, exist_ok=True)
    prefix = f"call_{int(call_id)}_"
    arrays = {
      "radiation_energy": _field(radiation, "epi_eV", "epi"),
      "bremsa": _field(radiation, "bremsa"),
      "continuum_tau_in": _field(escape, "continuum_tau_in"),
      "continuum_tau_out": _field(escape, "continuum_tau_out"),
      "global_xilevg": getattr(state, "global_xilevg_by_index", None),
      "global_bilevg": getattr(state, "global_bilevg_by_index", None),
      "global_rnisg": getattr(state, "global_rnisg_by_index", None),
    }
    for name, value in arrays.items():
        np.asarray(_array(value), dtype=np.float64).tofile(directory / (prefix + name + ".bin"))
    radiation_bins = int(_array(arrays["radiation_energy"]).size)
    tau_count = int(_array(arrays["continuum_tau_in"]).size)
    global_count = int(_array(arrays["global_xilevg"]).size)
    _STATE["all61_inputs"].append({
      "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
      "evaluation_index": int(evaluation_index), "temperature_k": float(state.temperature_k),
      "temperature_t4": float(state.temperature_t4), "electron_fraction_input": float(state.electron_fraction_xee),
      "covering_fraction": float(_field(request, "covering_fraction") or 0.0),
      "turbulent_velocity_km_s": float(_field(request, "turbulent_velocity_km_s") or 0.0),
      "workspace_directory": str(directory), "radiation_bins": radiation_bins,
      "continuum_tau_count": tau_count, "global_level_count": global_count,
    })

def _v048744_capture_solve_rows(kind, call_id, evaluation_index, sequence, result):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    for item in tuple(getattr(result, "element_results", ()) or ()):
        request = getattr(item, "request", None)
        z = int(_field(request, "element_z") or 0)
        if z not in (1, 2, 12):
            continue
        eq = getattr(item, "equilibrium", None)
        assembly = getattr(eq, "assembly", None)
        solve = getattr(eq, "solve", None)
        if assembly is None or solve is None:
            continue
        basis = assembly.basis
        n = int(basis.n_rows)
        rows = tuple(basis.rows)
        ion_stages = np.asarray(basis.ion_stage, dtype=np.int32)
        initial = np.asarray(assembly.initial_populations[1:n+1], dtype=float)
        final = np.asarray(solve.populations, dtype=float)
        outer = np.asarray(solve.final_outer_start_populations, dtype=float)
        rhs = np.asarray(assembly.rhs, dtype=float)
        residual = np.asarray(solve.row_residual, dtype=float)
        scale = np.asarray(solve.row_scale, dtype=float)
        stages = [int(ion_stages[i]) for i in range(1, min(n + 1, ion_stages.size))]
        active_min = min(stages) if stages else 0
        active_max = max(stages) if stages else 0
        abundance = float(_field(request, "abundance") or 0.0)
        for i in range(n):
            meta = rows[i]
            stage = int(ion_stages[i + 1]) if i + 1 < ion_stages.size else 0
            row_residual = float(residual[i]) if residual.size == n else float("nan")
            row_scale = float(scale[i]) if scale.size == n else float("nan")
            relative = abs(row_residual) / max(abs(row_scale), 1.0e-300)
            _STATE["all61_solve_rows"].append({
              "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
              "evaluation_index": int(evaluation_index), "element_z": z, "abundance": abundance,
              "active_min_stage": active_min, "active_max_stage": active_max,
              "compact_row": i + 1, "ion": int(meta.ion_counter), "ion_stage": stage,
              "ion_charge": max(0, stage - 1), "superlevel": int(meta.superlevel),
              "is_normalization_row": 1 if i + 1 == int(basis.normalization_row) else 0,
              "transformed_initial_population": float(initial[i]) if initial.size == n else float("nan"),
              "final_outer_start_population": float(outer[i]) if outer.size == n else float("nan"),
              "final_population": float(final[i]) if final.size == n else float("nan"),
              "rhs": float(rhs[i]) if rhs.size == n else float("nan"),
              "row_residual": row_residual, "row_scale": row_scale,
              "relative_row_residual": relative, "solver_method": str(solve.solver_method),
              "converged": int(bool(solve.converged)),
            })

def _v048742_capture(kind, call_id, evaluation_index, sequence, state, result):
    sequence = _v048743_canonical_sequence(kind, call_id, evaluation_index)
    _v048744_capture_solve_rows(kind, call_id, evaluation_index, sequence, result)
    input_xee = float(result.electron_fraction_xee)
    charge_residual = float(result.elcter)
    computed_xee = input_xee - charge_residual
    _STATE["all61_states"].append({
      "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
      "evaluation_index": int(evaluation_index), "temperature_k": float(result.temperature_k),
      "temperature_t4": float(result.temperature_k) / 1.0e4,
      "electron_fraction_input": input_xee,
      "computed_electron_fraction": computed_xee,
      "charge_residual": charge_residual, "hmctot": float(result.hmctot),
    })
    for z in (1, 2, 12):
        for stage in range(1, z + 2):
            _STATE["all61_ions"].append({
              "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
              "evaluation_index": int(evaluation_index), "element_z": z, "stage": stage,
              "ion_charge": stage - 1,
              "population": float(result.ion_fractions.get((z, stage), 0.0)),
            })
    mapping = dict(getattr(result, "global_level_index_by_key", {}) or {})
    gx = getattr(result, "global_xilevg_by_index", None)
    gb = getattr(result, "global_bilevg_by_index", None)
    gr = getattr(result, "global_rnisg_by_index", None)
    for key, global_index in sorted(mapping.items(), key=lambda item: int(item[1])):
        if len(key) != 3:
            continue
        z, stage, local_ordinal = (int(key[0]), int(key[1]), int(key[2]))
        if z not in (1, 2, 12):
            continue
        _STATE["all61_levels"].append({
          "sequence": int(sequence), "kind": str(kind), "dsec_call_id": int(call_id),
          "evaluation_index": int(evaluation_index), "element_z": z, "stage": stage,
          "local_level_ordinal": local_ordinal, "global_level_index": int(global_index),
          "population": _v048742_value(gx, global_index),
          "bilevg": _v048742_value(gb, global_index),
          "rnisg": _v048742_value(gr, global_index),
        })

def _v048742_write_all61():
    sort_keys = {
      "v0472_all61_fixed_state_rows.csv": lambda row: (int(row["sequence"]),),
      "v0472_all61_ion_populations.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["stage"])),
      "v0472_all61_level_populations.csv": lambda row: (int(row["sequence"]), int(row["global_level_index"])),
      "v0472_all61_input_states.csv": lambda row: (int(row["sequence"]),),
      "v0472_all61_element_solve_rows.csv": lambda row: (int(row["sequence"]), int(row["element_z"]), int(row["compact_row"])),
    }
    for name, fields, rows in [
      ("v0472_all61_fixed_state_rows.csv", ALL61_STATE_FIELDS, _STATE["all61_states"]),
      ("v0472_all61_ion_populations.csv", ALL61_ION_FIELDS, _STATE["all61_ions"]),
      ("v0472_all61_level_populations.csv", ALL61_LEVEL_FIELDS, _STATE["all61_levels"]),
      ("v0472_all61_input_states.csv", ALL61_INPUT_FIELDS, _STATE["all61_inputs"]),
      ("v0472_all61_element_solve_rows.csv", ALL61_SOLVE_FIELDS, _STATE["all61_solve_rows"]),
    ]:
        ordered = sorted(rows, key=sort_keys[name])
        with (_OUT / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader(); writer.writerows(ordered)
'''
_PROBE = _PROBE.replace("def _capture_result(call_id, local_eval, global_eval, state, result):", _CAPTURE_CODE + "\n\ndef _capture_result(call_id, local_eval, global_eval, state, result):\n    _v048742_capture(\"dsec\", call_id, local_eval, global_eval, state, result)")

_OLD_RETAINED = '''        if bool(getattr(self, "retain_fixed_state_results", True)):
            with _LOCK:
                _STATE["bypassed_retained_evaluators"] += 1
            print("v0487214_capture_bypass retained_fixed_state_result=1", flush=True)
            return original(self, state)
'''
_NEW_RETAINED = '''        if bool(getattr(self, "retain_fixed_state_results", True)):
            with _LOCK:
                _STATE["final_counter"] += 1
                call_id = int(_STATE["final_counter"])
                final_indices = (22, 2, 19, 18)
                final_evaluation_index = final_indices[call_id - 1] if 1 <= call_id <= 4 else 0
                _STATE["global_eval"] += 1
                global_eval = int(_STATE["global_eval"])
                _STATE["bypassed_retained_evaluators"] += 1
            with _LOCK:
                _v048742_capture_input("final", call_id, final_evaluation_index, global_eval, state)
            previous_factory = self.calc_kwargs_factory
            def retained_factory(current_state):
                payload = {} if previous_factory is None else dict(previous_factory(current_state))
                try:
                    profile = dict(payload.get("profile_control") or {})
                except Exception:
                    profile = {}
                profile["diagnostics_mode"] = "summary"
                payload["profile_control"] = profile
                payload["retain_element_results"] = True
                payload["retain_diagnostic_arrays"] = True
                return payload
            self.calc_kwargs_factory = retained_factory
            try:
                out = original(self, state)
            finally:
                self.calc_kwargs_factory = previous_factory
            fixed = getattr(out, "fixed_state_result", None)
            if fixed is not None:
                with _LOCK:
                    _v048742_capture("final", call_id, final_evaluation_index, global_eval, state, fixed)
            print(f"v048742_capture_final call={call_id} global={global_eval}", flush=True)
            return out
'''
if _OLD_RETAINED not in _PROBE:
    raise RuntimeError("retained-evaluator probe anchor not found")
_PROBE = _PROBE.replace(_OLD_RETAINED, _NEW_RETAINED)
_PROBE = _PROBE.replace(
    '        def capture_pre(evaluation_index, current_state):\n            if previous_pre is not None:\n                previous_pre(evaluation_index, current_state)\n            if int(evaluation_index) == 1:\n                with _LOCK:\n                    _capture_start_state(self, current_state, call_id, global_eval)\n',
    '        def capture_pre(evaluation_index, current_state):\n            if previous_pre is not None:\n                previous_pre(evaluation_index, current_state)\n            with _LOCK:\n                _v048742_capture_input("dsec", call_id, local_eval, global_eval, current_state)\n                if int(evaluation_index) == 1:\n                    _capture_start_state(self, current_state, call_id, global_eval)\n',
)
_PROBE = _PROBE.replace(
    "def finalize(run_summary=None):\n    for name, fields, rows in [",
    "def finalize(run_summary=None):\n    _v048742_write_all61()\n    for name, fields, rows in [",
)
_PROBE = _PROBE.replace(
    '"result": "ACCEPT" if len(_STATE["budgets"]) == 57 and len(_STATE["states"]) == 4 and len(_STATE["trace"]) == 57 else "REJECT",',
    '"result": "ACCEPT" if len(_STATE["budgets"]) == 57 and len(_STATE["states"]) == 4 and len(_STATE["trace"]) == 57 and len(_STATE["all61_states"]) == 61 else "REJECT",',
)
_PROBE = _PROBE.replace(
    '"dsec_evaluations_observed": len(_STATE["trace"]),',
    '"dsec_evaluations_observed": len(_STATE["trace"]), "all61_evaluations_observed": len(_STATE["all61_states"]), "all61_ion_rows": len(_STATE["all61_ions"]), "all61_level_rows": len(_STATE["all61_levels"]),',
)
_PROBE = _PROBE.replace(
'''        try:\n            out = original(self, state)\n        finally:\n            self.pre_evaluation_callback = previous_pre\n            self.progress_callback = previous_progress\n''',
'''        previous_factory = self.calc_kwargs_factory
        def retained_factory(current_state):
            payload = {} if previous_factory is None else dict(previous_factory(current_state))
            try:
                profile = dict(payload.get("profile_control") or {})
            except Exception:
                profile = {}
            profile["diagnostics_mode"] = "summary"
            payload["profile_control"] = profile
            payload["retain_element_results"] = True
            payload["retain_diagnostic_arrays"] = True
            return payload
        self.calc_kwargs_factory = retained_factory
        try:
            out = original(self, state)
        finally:
            self.calc_kwargs_factory = previous_factory
            self.pre_evaluation_callback = previous_pre
            self.progress_callback = previous_progress
''')

_PROBE = _PROBE.replace(f'"schema": "{base.SCHEMA}"', f'"schema": "{SCHEMA}"')
_PROBE = _PROBE.replace(f'"release": "{base.RELEASE}"', f'"release": "{RELEASE}"')


def _v0487463_probe_retention_report(probe: str | None = None) -> dict[str, int]:
    text = _PROBE if probe is None else str(probe)
    lines = text.splitlines()
    header = "payload = {} if previous_factory is None else dict(previous_factory(current_state))"
    reports = []
    for index, line in enumerate(lines):
        if line.strip() != header:
            continue
        end = index + 1
        while end < len(lines) and end <= index + 32 and lines[end].strip() != "return payload":
            end += 1
        if end >= len(lines) or lines[end].strip() != "return payload":
            reports.append((False, False, False, False))
            continue
        block = "\n".join(lines[index:end + 1])
        reports.append((
            'profile["diagnostics_mode"] = "summary"' in block,
            'payload["profile_control"] = profile' in block,
            'payload["retain_element_results"] = True' in block,
            'payload["retain_diagnostic_arrays"] = True' in block,
        ))
    return {
        "factory_blocks": len(reports),
        "summary_blocks": sum(int(row[0]) for row in reports),
        "profile_copy_blocks": sum(int(row[1]) for row in reports),
        "element_retention_blocks": sum(int(row[2]) for row in reports),
        "diagnostic_retention_blocks": sum(int(row[3]) for row in reports),
    }


def _v0487463_force_summary_retention(probe: str) -> str:
    text = str(probe)
    trailing_newline = text.endswith("\n")
    lines = text.splitlines()
    header = "payload = {} if previous_factory is None else dict(previous_factory(current_state))"
    indices = [index for index, line in enumerate(lines) if line.strip() == header]
    if len(indices) < 2:
        raise RuntimeError(
            f"expected at least two qualification factory blocks in generated probe; found {len(indices)}"
        )
    offset = 0
    for original_index in indices:
        index = original_index + offset
        end = index + 1
        while end < len(lines) and end <= index + 32 and lines[end].strip() != "return payload":
            end += 1
        if end >= len(lines) or lines[end].strip() != "return payload":
            raise RuntimeError(f"qualification factory block at line {index + 1} has no return payload")
        block = "\n".join(lines[index:end + 1])
        complete = (
            'profile["diagnostics_mode"] = "summary"' in block
            and 'payload["profile_control"] = profile' in block
            and 'payload["retain_element_results"] = True' in block
            and 'payload["retain_diagnostic_arrays"] = True' in block
        )
        if complete:
            continue
        indent = lines[index][: len(lines[index]) - len(lines[index].lstrip())]
        insertion = [
            indent + "try:",
            indent + '    profile = dict(payload.get("profile_control") or {})',
            indent + "except Exception:",
            indent + "    profile = {}",
            indent + 'profile["diagnostics_mode"] = "summary"',
            indent + 'payload["profile_control"] = profile',
        ]
        lines[index + 1:index + 1] = insertion
        offset += len(insertion)
    updated = "\n".join(lines) + ("\n" if trailing_newline else "")
    report = _v0487463_probe_retention_report(updated)
    required = report["factory_blocks"]
    if required < 2 or any(report[key] != required for key in (
        "summary_blocks", "profile_copy_blocks", "element_retention_blocks", "diagnostic_retention_blocks"
    )):
        raise RuntimeError(f"generated probe retention normalization incomplete: {report}")
    return updated


_PROBE = _v0487463_force_summary_retention(_PROBE)



# BEGIN V06487465 PROBE COMPONENT CONTRACT
def _v0487465_probe_retention_report(probe: str | None = None) -> dict[str, int]:
    text = _PROBE if probe is None else str(probe)
    lines = text.splitlines()
    reports: list[tuple[bool, bool, bool, bool]] = []
    for index, line in enumerate(lines):
        if line.strip() != "def retained_factory(current_state):":
            continue
        indent = len(line) - len(line.lstrip())
        end = index + 1
        while end < len(lines):
            stripped = lines[end].strip()
            current_indent = len(lines[end]) - len(lines[end].lstrip()) if stripped else indent + 4
            if stripped and current_indent <= indent and end > index + 1:
                break
            if stripped == "return payload":
                end += 1
                break
            end += 1
        block = "\n".join(lines[index:end])
        reports.append((
            'profile = dict(payload.get("profile_control") or {})' in block,
            'profile["diagnostics_mode"] = "summary"' in block and 'payload["profile_control"] = profile' in block,
            'payload["retain_element_results"] = True' in block,
            'payload["retain_diagnostic_arrays"] = True' in block,
        ))
    return {
        "factory_blocks": len(reports),
        "profile_copy_blocks": sum(int(row[0]) for row in reports),
        "summary_blocks": sum(int(row[1]) for row in reports),
        "element_retention_blocks": sum(int(row[2]) for row in reports),
        "diagnostic_retention_blocks": sum(int(row[3]) for row in reports),
    }


def _v0487465_force_summary_retention(probe: str) -> str:
    text = str(probe)
    trailing_newline = text.endswith("\n")
    lines = text.splitlines()
    indices = [
        index for index, line in enumerate(lines)
        if line.strip() == "def retained_factory(current_state):"
    ]
    if len(indices) < 2:
        raise RuntimeError(
            f"expected at least two retained_factory blocks in generated probe; found {len(indices)}"
        )
    offset = 0
    for original_index in indices:
        index = original_index + offset
        def_line = lines[index]
        indent = def_line[: len(def_line) - len(def_line.lstrip())]
        body_indent = indent + "    "
        end = index + 1
        while end < len(lines):
            stripped = lines[end].strip()
            current_indent = len(lines[end]) - len(lines[end].lstrip()) if stripped else len(body_indent)
            if stripped and current_indent <= len(indent) and end > index + 1:
                break
            if stripped == "return payload":
                end += 1
                break
            end += 1
        canonical = [
            body_indent + "payload = {} if previous_factory is None else dict(previous_factory(current_state))",
            body_indent + "try:",
            body_indent + '    profile = dict(payload.get("profile_control") or {})',
            body_indent + "except Exception:",
            body_indent + "    profile = {}",
            body_indent + 'profile["diagnostics_mode"] = "summary"',
            body_indent + 'payload["profile_control"] = profile',
            body_indent + 'payload["retain_element_results"] = True',
            body_indent + 'payload["retain_diagnostic_arrays"] = True',
            body_indent + "return payload",
        ]
        old_count = end - (index + 1)
        lines[index + 1:end] = canonical
        offset += len(canonical) - old_count
    updated = "\n".join(lines) + ("\n" if trailing_newline else "")
    report = _v0487465_probe_retention_report(updated)
    total = report["factory_blocks"]
    required = (
        "profile_copy_blocks", "summary_blocks",
        "element_retention_blocks", "diagnostic_retention_blocks",
    )
    if total < 2 or any(report[key] != total for key in required):
        raise RuntimeError(f"generated probe retention repair incomplete: {report}")
    compile(updated, "<v0487465-probe>", "exec")
    return updated


_PROBE = _v0487465_force_summary_retention(_PROBE)
# END V06487465 PROBE COMPONENT CONTRACT


_DRIVER = base._DRIVER.replace("import v048726_full_probe_runtime as probe", "import v048744_all61_probe_runtime as probe")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def verify(bundle: Path) -> dict[str, Any]:
    errors: list[str] = []
    for name in (STATE_NAME, INPUT_NAME, ION_NAME, LEVEL_NAME, SOLVE_NAME, REPORT_NAME):
        if not (bundle / name).is_file():
            errors.append(f"missing:{name}")
    if errors:
        return {"schema": VERIFY_SCHEMA, "release": RELEASE, "result": "REJECT", "errors": errors,
                "qualification_only": True, "production_promotion_ready": False}
    states = _read_csv(bundle / STATE_NAME)
    inputs = _read_csv(bundle / INPUT_NAME)
    ions = _read_csv(bundle / ION_NAME)
    levels = _read_csv(bundle / LEVEL_NAME)
    solve_rows = _read_csv(bundle / SOLVE_NAME)
    sequences = [int(row["sequence"]) for row in states]
    kinds = [row["kind"] for row in states]
    workspace_contract_exact = True
    for row in inputs:
        try:
            expected_sequence = canonical_sequence(row["kind"], int(row["dsec_call_id"]), int(row["evaluation_index"]))
        except Exception as exc:
            errors.append(f"invalid_identity:{exc}")
            workspace_contract_exact = False
            continue
        actual_sequence = int(row["sequence"])
        if actual_sequence != expected_sequence:
            errors.append(f"sequence_identity_mismatch:{actual_sequence}!={expected_sequence}")
            workspace_contract_exact = False
        directory = Path(row["workspace_directory"])
        prefix = f"call_{int(row['dsec_call_id'])}_"
        for name in ("radiation_energy", "bremsa", "continuum_tau_in", "continuum_tau_out", "global_xilevg", "global_bilevg", "global_rnisg"):
            if not (directory / f"{prefix}{name}.bin").is_file():
                errors.append(f"missing_workspace:{actual_sequence}:{prefix}{name}.bin")
                workspace_contract_exact = False
    if len(inputs) != 61 or [int(row["sequence"]) for row in inputs] != list(range(1, 62)):
        errors.append(f"input_inventory={len(inputs)}")
    if len(states) != 61 or sequences != list(range(1, 62)):
        errors.append(f"state_inventory={len(states)}")
    if kinds.count("dsec") != 57 or kinds.count("final") != 4:
        errors.append(f"kind_inventory=dsec:{kinds.count('dsec')},final:{kinds.count('final')}")
    expected_ions = 61 * ((1 + 1) + (2 + 1) + (12 + 1))
    if len(ions) != expected_ions:
        errors.append(f"ion_rows={len(ions)} expected={expected_ions}")
    if not levels or {int(row["sequence"]) for row in levels} != set(range(1, 62)):
        errors.append("level_sequence_inventory")
    solve_sequences = {int(row["sequence"]) for row in solve_rows}
    solve_elements = {(int(row["sequence"]), int(row["element_z"])) for row in solve_rows}
    if not solve_rows or solve_sequences != set(range(1, 62)):
        errors.append("solve_row_sequence_inventory")
    if len(solve_elements) != 61 * 3:
        errors.append(f"solve_element_inventory={len(solve_elements)}")
    report = json.loads((bundle / REPORT_NAME).read_text())
    if not report.get("actual_v0472_runtime_capture"):
        errors.append("not_actual_v0472_runtime_capture")
    return {
        "schema": VERIFY_SCHEMA, "release": RELEASE,
        "result": "ACCEPT" if not errors else "REJECT", "errors": errors,
        "actual_v0472_runtime_capture": bool(report.get("actual_v0472_runtime_capture")),
        "evaluations": len(states), "input_states": len(inputs), "dsec_evaluations": kinds.count("dsec"),
        "final_evaluations": kinds.count("final"), "ion_rows": len(ions), "level_rows": len(levels),
        "solve_rows": len(solve_rows), "solve_elements": len(solve_elements),
        "workspace_sequence_contract_exact": workspace_contract_exact,
        "qualification_only": True, "production_promotion_ready": False,
    }


def capture(source_archive: Path, atdb_path: Path, output_dir: Path,
            parameters_json: Path, coheat_path: Path | None) -> dict[str, Any]:
    output_dir = output_dir.resolve(); output_dir.mkdir(parents=True, exist_ok=True)
    if base.base._sha256(source_archive) != base.base.SOURCE_ARCHIVE_SHA256:
        raise ValueError("v0.6.47.2 source archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="v048744_") as tmp:
        tmp_path = Path(tmp)
        base.base._safe_extract(source_archive, tmp_path / "source")
        root = base.base._source_root(tmp_path / "source")
        probe_dir = tmp_path / "probe"; probe_dir.mkdir()
        (probe_dir / "v048744_all61_probe_runtime.py").write_text(_PROBE)
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
        log = output_dir / "v0472_all61_capture_run.log"
        with log.open("w") as handle:
            completed = subprocess.run(cmd, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
        if completed.returncode != 0:
            raise RuntimeError(f"v0.6.47.2 all-61 capture failed with exit {completed.returncode}; see {log}")
    historical = output_dir / "capture_report.json"
    if historical.is_file():
        historical.replace(output_dir / REPORT_NAME)
    result = verify(output_dir)
    _write_json(output_dir / VERIFY_NAME, result)
    files = {}
    for name in (STATE_NAME, INPUT_NAME, ION_NAME, LEVEL_NAME, SOLVE_NAME, REPORT_NAME, VERIFY_NAME):
        path = output_dir / name
        files[name] = {"sha256": base.base._sha256(path), "size_bytes": path.stat().st_size}
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
