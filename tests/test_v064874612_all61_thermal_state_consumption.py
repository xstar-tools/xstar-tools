from __future__ import annotations

import csv
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import xstar_tools
from xstar_tools.xstar import all61_thermal_state_consumption_audit as audit
from xstar_tools.xstar import thermal_component_parity_closure as closure
from xstar_tools.xstar import v0472_all61_thermal_state_capture as capture


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def dump(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def synthetic_ledgers(source: Path, native: Path, computed_delta: bool = True) -> None:
    source_rows: list[dict] = []
    native_rows: list[dict] = []
    state_fp_fields = [
        "input_dsec_radiation_fingerprint", "input_bremsa_fingerprint", "input_tau_in_fingerprint",
        "input_tau_out_fingerprint", "input_xilevg_fingerprint", "input_bilevg_fingerprint",
        "input_rnisg_fingerprint", "thermal_population_fingerprint",
    ]
    for seq in range(1, 62):
        kind = "dsec" if seq <= 57 else "final"
        call = ((seq - 1) % 4) + 1
        source_row = {
            "sequence": seq, "kind": kind, "call_index": call, "evaluation_index": seq,
            "temperature_k": 1.0e6 + seq, "temperature_t4": (1.0e6 + seq) / 1.0e4,
            "electron_fraction_input": 1.1, "electron_density_cm3": 1.1e8, "hydrogen_density_cm3": 1.0e8,
            "covering_fraction": 0.5, "turbulent_velocity_km_s": 100.0,
            "input_dsec_radiation_count": 9999, "input_bremsa_count": 9999,
            "input_tau_count": 301301, "input_global_level_count": 4000,
            "thermal_population_count": 688,
        }
        for index, field in enumerate(state_fp_fields):
            source_row[field] = f"{seq + index:016x}"
        for index, field in enumerate(audit.COMPONENT_FIELDS):
            source_row[field] = (seq * 100 + index + 1) * 1.0e-12
        source_rows.append(source_row)

        native_row = {
            "sequence": seq, "kind": kind, "call_index": call, "evaluation_index": seq,
            "temperature_k": source_row["temperature_k"], "electron_fraction_input": 1.1,
            "electron_density_cm3": 1.1e8, "hydrogen_density_cm3": 1.0e8,
            "covering_fraction": 0.5, "turbulent_velocity_km_s": 100.0,
            "input_dsec_radiation_count": 9999, "input_bremsa_count": 9999,
            "input_tau_count": 301301, "input_global_level_count": 4000,
            "thermal_population_count": 688,
            "thermal_component_closure_applied": 1, "thermal_consumed_fixed_state_closure": 1,
        }
        for field in state_fp_fields:
            native_row[field] = source_row[field]
        for field in audit.COMPONENT_FIELDS:
            committed_field = audit.COMMITTED_NATIVE_FIELD.get(field, field)
            computed_field = audit.COMPUTED_NATIVE_FIELD.get(field, f"computed_{field}")
            native_row[committed_field] = source_row[field]
            native_row[computed_field] = source_row[field]
        if computed_delta and seq == 1:
            native_row["computed_h_heating"] = float(source_row["h_heating"]) + 1.0e-20
        native_rows.append(native_row)

    write_csv(source / capture.BUDGET_NAME, list(source_rows[0]), source_rows)
    write_csv(native / "native_all61_thermal_budget.csv", list(native_rows[0]), native_rows)
    dump(native / "native_dsec_summary.json", {
        "release": capture.RELEASE, "result": "ACCEPT", "total_evaluations": 61,
        "thermal_ledger_rows": 61, "python_callbacks": 0,
    })


def test_generated_probe_installs_nonrecursive_input_hook(tmp_path: Path) -> None:
    helper_start = capture._PROBE.index("def _v04874612_capture_input(")
    helper_end = capture._PROBE.index("\ndef _v04874612_capture_result(", helper_start)
    base_start = capture._PROBE.index("def _v048742_capture_input(")
    base_end = capture._PROBE.index("\ndef _v048744_capture_solve_rows(", base_start)
    assert capture._PROBE[helper_start:helper_end].count("_v04874612_capture_input(") == 1
    assert capture._PROBE[base_start:base_end].count("_v04874612_capture_input(") == 1

    probe_dir = tmp_path / "probe"
    output_dir = tmp_path / "output"
    probe_dir.mkdir()
    (probe_dir / "probe_config.json").write_text(json.dumps({"output_dir": str(output_dir)}))
    runtime = probe_dir / "runtime.py"
    runtime.write_text(capture._PROBE)
    spec = importlib.util.spec_from_file_location("v04874612_test_probe_runtime", runtime)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    radiation = SimpleNamespace(epi_eV=np.array([1.0, 2.0]), bremsa=np.array([3.0, 4.0]))
    escape = SimpleNamespace(
        continuum_tau_in=np.array([5.0, 6.0, 7.0]),
        continuum_tau_out=np.array([8.0, 9.0, 10.0]),
    )
    request = SimpleNamespace(
        radiation=radiation,
        escape=escape,
        covering_fraction=0.5,
        turbulent_velocity_km_s=100.0,
    )
    state = SimpleNamespace(
        element_requests=(request,),
        global_xilevg_by_index=np.array([11.0, 12.0, 13.0]),
        global_bilevg_by_index=np.array([14.0, 15.0, 16.0]),
        global_rnisg_by_index=np.array([17.0, 18.0, 19.0]),
        temperature_k=1.0e6,
        temperature_t4=100.0,
        electron_fraction_xee=1.1,
    )
    module._v048742_capture_input("dsec", 1, 1, 1, state)
    assert 1 in module._STATE["all61_thermal_inputs"]
    assert module._STATE["all61_thermal_inputs"][1]["input_dsec_radiation_count"] == 2
    assert len(module._STATE["all61_inputs"]) == 1


def test_release_and_cpp_contract() -> None:
    assert xstar_tools.__version__ == "0.6.48.7.46.20.1"
    cpp = (root() / "src/xstar_tools/xstar/cpp/fixed_state_engine.cpp").read_text()
    assert "XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE" in cpp
    assert "XSTAR_QUALIFICATION_THERMAL_COMPONENT_PARITY_CLOSURE_DIR" in cpp
    assert "last_thermal_consumed_fixed_state_closure" in cpp
    assert "last_preclosure_electron_fraction" in cpp
    assert "closure.elcter != fixed_state_closure_data->charge_residual" in cpp
    assert "computed_charge_residual" in cpp
    assert len(capture.THERMAL_FIELDS) == 64
    compile(capture._PROBE, "<v46.12-probe>", "exec")


def test_prepare_and_audit_synthetic_all61(tmp_path: Path) -> None:
    source = tmp_path / "source"
    native = tmp_path / "native"
    synthetic_ledgers(source, native, computed_delta=True)
    prepared = tmp_path / "prepared"
    prep = closure.prepare(source, prepared)
    assert prep["result"] == "ACCEPT"
    assert prep["sequences_prepared"] == 61
    assert len(list(prepared.glob("sequence_*_thermal.csv"))) == 61

    output = tmp_path / "audit"
    result = audit.compare(source, native, output)
    assert result["result"] == "ACCEPT"
    assert result["thermal_component_values_exact"] == 2440
    assert result["thermal_component_values_total"] == 2440
    assert result["thermal_population_states_exact"] == 61
    assert result["gates"]["V06488_THERMAL_PARITY"] == "ACCEPT"
    assert result["independent_native_thermal_parity"] == "NOT_ACCEPTED"
    assert result["native_computed_values_exact"] == 2439

    closure_result = closure.audit(output, prepared / closure.REPORT_NAME)
    assert closure_result["result"] == "ACCEPT"

    baseline = tmp_path / "v46.11.1.json"
    dump(baseline, {
        "result": "ACCEPT", "dense_exact_systems": 183, "dense_mismatch_cells": 0,
        "gates": {"V06487_FIXED_STATE_PARITY": "ACCEPT"},
    })
    dump(output / "v048746121_canonical_scalar_oracle_alignment_report.json", {
        "result": "ACCEPT", "scalar_values_rebased": 1, "scalar_sequences_rebased": 1,
        "first_rebased_sequence": 9,
        "gates": {
            "ACCEPTED_V4611_LEVEL_POPULATIONS_PRESERVED_41968": "ACCEPT",
            "ACCEPTED_V4611_ION_POPULATIONS_PRESERVED_1098": "ACCEPT",
            "SOURCE_FIXED_THERMAL_CHARGE_BITS_EXACT_61": "ACCEPT",
        },
    })
    dump(output / "v048746121_native_replay_resume_manifest.json", {
        "result": "ACCEPT", "sequences_reusable": 61, "sequences_pending": 0,
    })
    checker = output / "checker.json"
    env = dict(os.environ, PYTHONPATH=str(root() / "src"))
    subprocess.run([
        sys.executable, str(root() / "check_v04874612_all61_thermal_state_consumption_audit.py"),
        "--audit-output", str(output), "--baseline-v048746111-report", str(baseline),
        "--output-json", str(checker),
    ], check=True, cwd=root(), env=env)
    checked = json.loads(checker.read_text())
    assert checked["result"] == "ACCEPT"
    assert checked["independent_native_thermal_parity"] == "NOT_ACCEPTED"
    assert checked["downstream"]["PRODUCTION_PROMOTION"] == "BLOCKED"


def test_population_fingerprint_mismatch_rejects(tmp_path: Path) -> None:
    source = tmp_path / "source"
    native = tmp_path / "native"
    synthetic_ledgers(source, native, computed_delta=False)
    rows = list(csv.DictReader((native / "native_all61_thermal_budget.csv").open()))
    rows[0]["thermal_population_fingerprint"] = "ffffffffffffffff"
    write_csv(native / "native_all61_thermal_budget.csv", list(rows[0]), rows)
    result = audit.compare(source, native, tmp_path / "audit")
    assert result["result"] == "REJECT"
    assert result["gates"]["ALL_61_THERMAL_POPULATION_STATE_EXACT"] == "REJECT"


def test_runtime_report_normalization_preserves_capture_and_materializes_canonical_names(tmp_path: Path) -> None:
    runtime_report = {
        "schema": "xstar-tools-v0648744-v0472-all61-fixed-state-capture-v1",
        "release": capture.RELEASE,
        "result": "ACCEPT",
        "actual_v0472_runtime_capture": True,
    }
    dump(tmp_path / capture.base.REPORT_NAME, {
        "schema": "stale-normalized-fixed-state-report",
        "release": "0.6.48.7.46.12",
        "result": "REJECT",
        "actual_v0472_runtime_capture": False,
    })
    dump(tmp_path / capture.RUNTIME_REPORT_NAME, runtime_report)
    write_csv(
        tmp_path / capture.BUDGET_NAME,
        capture.THERMAL_FIELDS,
        [{field: ("dsec" if field == "kind" else 1) for field in capture.THERMAL_FIELDS}],
    )
    normalized = capture._normalize_capture_reports(tmp_path)
    assert normalized["normalized"] is True
    assert normalized["source_report"] == capture.RUNTIME_REPORT_NAME
    assert (tmp_path / capture.RUNTIME_REPORT_NAME).is_file()
    fixed = json.loads((tmp_path / capture.base.REPORT_NAME).read_text())
    thermal = json.loads((tmp_path / capture.REPORT_NAME).read_text())
    assert fixed["actual_v0472_runtime_capture"] is True
    assert thermal["actual_v0472_runtime_capture"] is True
    assert thermal["schema"] == capture.SCHEMA
    assert thermal["all61_thermal_rows"] == 1


def test_workspace_directory_rebases_after_capture_bundle_move(tmp_path: Path) -> None:
    bundle = tmp_path / "moved_capture"
    local = bundle / "all61_input_workspaces" / "evaluation_0009"
    local.mkdir(parents=True)
    row = {
        "sequence": "9",
        "workspace_directory": "/obsolete/host/xstar_tools-0.6.48.7.46.12/"
        "v04874612_all61_thermal_state_consumption/v04874612_source_thermal_capture/"
        "all61_input_workspaces/evaluation_0009",
    }
    resolved, rebased = capture.base._resolve_workspace_directory(bundle, row)
    assert rebased is True
    assert resolved == local.resolve()


def test_runner_contains_source_capture_resume_and_preflight_contract() -> None:
    runner = (root() / "run_v04874612_all61_thermal_state_consumption_audit.sh").read_text()
    assert "V0487461212_RUNNER_REVISION=20260725-final-reference-decoupling-v1" in runner
    assert "THERMAL_AUDIT_RC=$?" in runner
    assert "THERMAL_CLOSURE_RC=$?" in runner
    assert "CHECKER_RC=$?" in runner
    assert 'exit "$CHECKER_RC"' in runner
    assert "V04874612_SOURCE_CAPTURE_REUSE=1" in runner
    assert "XSTAR_V04874612_FORCE_SOURCE_RECAPTURE" in runner
    assert "XSTAR_V04874612_SOURCE_CAPTURE_PREFLIGHT_ONLY" in runner
    assert "V04874612_SOURCE_CAPTURE_PREFLIGHT=ACCEPT" in runner
    assert "canonical_scalar_oracle_alignment" in runner
    assert "native_replay_resume" in runner
    assert "CANONICAL_FIXED_DIR" in runner
