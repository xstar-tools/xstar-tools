from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import xstar_atomic as xa
import importlib
dsec_module = importlib.import_module("xstar_atomic.source_port.dsec")
from xstar_atomic.source_port.dsec import (
    CalcHMCAllDsecEvaluator,
    DsecCalcHMCAllInputSnapshot,
    DsecMutableRuntimeState,
    DsecPortError,
)
from xstar_atomic.source_port.local_zone import FixedStateElementRequest
from xstar_atomic.source_port import zone1_dsec_diagnostic as diagnostic
from xstar_atomic.source_port.zone1_dsec_diagnostic import (
    TARGET_CARBON_STAGES,
    TARGET_CV_LOCAL_LEVELS,
    TARGET_TEMPERATURE_K,
    compare_cooling_terms,
    enforce_cooling_gate,
    numeric_fingerprint,
    replay_same_entry_state,
    snapshot_fingerprints,
)
from xstar_atomic.source_port.zone1_dsec_probe_analysis import load_xstar_target_state
from xstar_atomic.source_port_zone1_dsec_cli import build_parser
from xstar_atomic.xstar_zone1_dsec_probe import (
    write_zone1_probe_products,
    zone1_extra_helper,
    zone1_insertion_snippets,
)


def _snapshot() -> DsecCalcHMCAllInputSnapshot:
    radiation = SimpleNamespace(
        epim=np.asarray([1.0, 2.0, 3.0]),
        bremsam=np.asarray([4.0, 5.0, 6.0]),
        bremsint=np.asarray([7.0, 8.0, 9.0]),
    )
    escape = SimpleNamespace(
        line_tau_in=np.asarray([0.1, 0.2]),
        line_tau_out=np.asarray([0.3, 0.4]),
        continuum_tau_in=np.asarray([0.5, 0.6]),
        continuum_tau_out=np.asarray([0.7, 0.8]),
    )
    request = FixedStateElementRequest(
        element_z=6,
        min_ion_stage=4,
        max_ion_stage=6,
        abundance=3.0e-4,
        radiation=radiation,
        escape=escape,
    )
    return DsecCalcHMCAllInputSnapshot(
        evaluation_index=7,
        temperature_t4=7.31984,
        temperature_k=TARGET_TEMPERATURE_K,
        electron_fraction_xee=1.202,
        hydrogen_density_cm3=1.0e8,
        pressure=3.0,
        lcdd=1,
        covering_fraction=1.0,
        turbulent_velocity_km_s=1.0,
        critf=1.0e-7,
        global_level_populations={(6, 5, 1): 0.9},
        global_bilev_values={(6, 5, 1): 1.0e-37},
        global_rnist_values={(6, 5, 1): 2.0},
        global_level_index_by_key={(6, 5, 1): 1},
        leveltemp_workspace=SimpleNamespace(
            rlev=np.asarray([[1.0, 2.0], [3.0, 4.0]]),
            ilev=np.asarray([[1, 2], [3, 4]]),
        ),
        leveltemp_owner_by_column={1: {"element_z": 6, "ion_stage": 5}},
        radiation=radiation,
        escape=escape,
        calc_kwargs={"continuum_context": SimpleNamespace(opakc=np.asarray([1.0, 2.0]))},
        global_xilevg_by_index=np.asarray([0.0, 0.9]),
        global_bilevg_by_index=np.asarray([0.0, 1.0e-37]),
        global_rnisg_by_index=np.asarray([0.0, 2.0]),
        element_requests=(request,),
        required_element_z=(1, 2, 6),
        source_global_alias_writeback=True,
        dispatcher_state=SimpleNamespace(work=np.asarray([11.0, 12.0])),
        element_solver_state=SimpleNamespace(buffer=np.asarray([13.0])),
        pre_matrix_solver_state=SimpleNamespace(buffer=np.asarray([14.0])),
    )


def _dummy_result() -> SimpleNamespace:
    return SimpleNamespace(
        temperature_k=TARGET_TEMPERATURE_K,
        electron_fraction_xee=1.202,
        hydrogen_density_cm3=1.0e8,
        hmctot=1.0e-8,
        elcter=-2.0e-9,
        httot=1.0,
        cltot=1.0,
        httot2=2.0,
        cltot2=2.0,
        global_xilevg_by_index=np.asarray([0.0, 0.5, 0.5]),
        global_bilevg_by_index=np.asarray([0.0, 1.0, 2.0]),
        global_rnisg_by_index=np.asarray([0.0, 3.0, 4.0]),
        ion_fractions={(6, 4): 0.1, (6, 5): 0.2, (6, 6): 0.7},
        element_results=[],
    )


def test_v0478_numeric_fingerprint_is_exact_and_mutation_sensitive():
    first = numeric_fingerprint(
        np.asarray([1.0, 2.0, 3.0]), name="array", evaluation_index=1
    )
    second = numeric_fingerprint(
        np.asarray([1.0, 2.0, 3.0]), name="array", evaluation_index=1
    )
    changed = numeric_fingerprint(
        np.asarray([1.0, 2.0, 3.000000000000001]),
        name="array",
        evaluation_index=1,
    )
    assert first == second
    assert first.sha256 != changed.sha256


def test_v0478_snapshot_fingerprints_cover_all_mutable_namespaces():
    rows = snapshot_fingerprints(_snapshot())
    names = {row.name for row in rows}
    assert "runtime_scalars" in names
    assert "global_xilevg_by_index" in names
    assert "radiation.epim" in names
    assert "radiation.bremsam" in names
    assert "escape.line_tau_in" in names
    assert "calc_kwargs.continuum_context.opakc" in names
    assert "leveltemp_workspace.rlev" in names
    assert "dispatcher.work" in names
    assert "element_solver.buffer" in names
    assert "pre_matrix_solver.buffer" in names
    assert "element_requests.structure" in names
    assert "element_requests.abundance" in names
    assert "element_requests.min_ion_stage" in names
    assert "element_requests.max_ion_stage" in names


def test_v0478_evaluator_gate_runs_after_calc_before_state_commit(monkeypatch):
    request = FixedStateElementRequest(6, 4, 6)
    state = DsecMutableRuntimeState(
        temperature_t4=7.31984,
        electron_fraction_xee=1.202,
        hydrogen_density_cm3=1.0e8,
        element_requests=(request,),
        global_level_populations={},
    )
    sentinel = RuntimeError("stop-before-commit")
    result = _dummy_result()
    monkeypatch.setattr(dsec_module, "calc_hmc_all", lambda *args, **kwargs: result)

    observed = {}

    def gate(index, snapshot, returned):
        observed["index"] = index
        observed["snapshot"] = snapshot
        observed["result"] = returned
        raise sentinel

    evaluator = CalcHMCAllDsecEvaluator(
        master=object(),
        derived=object(),
        dispatcher=SimpleNamespace(work=np.asarray([1.0])),
        capture_all_input_snapshots=True,
        evaluation_gate_callback=gate,
    )
    with pytest.raises(RuntimeError, match="stop-before-commit"):
        evaluator(state)
    assert observed["index"] == 1
    assert observed["result"] is result
    assert len(evaluator.input_snapshots) == 1
    assert state.calc_hmc_all_call_count == 0
    assert state.last_calc_hmc_all is None


def test_v0478_same_entry_replay_requires_bitwise_identical_outputs(monkeypatch):
    monkeypatch.setattr(diagnostic, "calc_hmc_all", lambda *args, **kwargs: _dummy_result())
    replay = replay_same_entry_state(object(), object(), _snapshot())
    assert replay.ready is True
    assert replay.rows
    assert all(row.exact_match for row in replay.rows)


def test_v0478_same_entry_replay_detects_mutating_or_nondeterministic_output(monkeypatch):
    counter = {"n": 0}

    def varying(*args, **kwargs):
        counter["n"] += 1
        result = _dummy_result()
        result.hmctot = float(counter["n"])
        return result

    monkeypatch.setattr(diagnostic, "calc_hmc_all", varying)
    replay = replay_same_entry_state(object(), object(), _snapshot())
    assert replay.ready is False
    assert any(row.quantity == "hmctot" and not row.exact_match for row in replay.rows)


def test_v0478_carbon_cooling_gate_is_term_by_term_and_fail_fast():
    python_rows = [
        {"evaluation_index": 1, "record": 10, "term_index": 2, "row": 4, "cooling_contribution": 1.0},
        {"evaluation_index": 1, "record": 11, "term_index": 3, "row": 5, "cooling_contribution": 2.0},
    ]
    xstar_rows = [
        {"evaluation_index": 1, "record": 10, "term_index": 2, "row": 4, "cooling_contribution": 1.0},
        {"evaluation_index": 1, "record": 11, "term_index": 3, "row": 5, "cooling_contribution": 2.1},
    ]
    compared = compare_cooling_terms(python_rows, xstar_rows, rtol=1.0e-12, atol=0.0)
    assert [row.within_tolerance for row in compared] == [True, False]
    with pytest.raises(DsecPortError, match="before the thermal root finder"):
        enforce_cooling_gate(compared)


def test_v0478_original_probe_bundle_captures_complete_sequence_and_required_audits(tmp_path: Path):
    products = write_zone1_probe_products(tmp_path)
    assert products["zone1_helper"].is_file()
    assert products["zone1_snippets"].is_file()
    assert products["zone1_manifest"].is_file()
    helper = zone1_extra_helper()
    assert "xap_zone1_entry_arrays" in helper
    assert "xap_zone1_rate_record" in helper
    assert "xap_zone1_second_pass_rate" in helper
    assert "xap_zone1_thermal_term" in helper
    assert "xap_zone1_begin_calc_ion_rate_record" in helper
    assert "xap_zone1_type15_shell" in helper
    assert "xap_zone1_calc_ion_rate_record" in helper
    assert "xap_zone1_normalization_row" in helper
    assert "xap_zone1_level_population" in helper
    snippets = zone1_insertion_snippets()
    assert set(snippets) == {
        "calc_hmc_all_entry_arrays",
        "calc_hmc_ion_record",
        "calc_hmc_element_second_pass_rate",
        "msolvelucy_thermal_term",
        "calc_ion_rates_record",
        "ucalc_type15_shell",
        "msolvelucy_normalization_row",
        "calc_hmc_element_level_population",
    }
    manifest = products["zone1_manifest"].read_text(encoding="utf-8")
    assert "XSTAR_ATOMIC_HMC_TARGET_DSEC_EVALUATION=0" in manifest
    assert "every internal calc_hmc_all evaluation" in manifest


def test_v0478_target_state_uses_nearest_original_73198p4K_evaluation(tmp_path: Path):
    with (tmp_path / "xstar_dsec_calc_hmc_all_call_correlation.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["dsec_call_id", "phase", "calc_hmc_all_call_id", "dsec_evaluation_index"],
        )
        writer.writeheader()
        writer.writerow({"dsec_call_id": 1, "phase": "dsec_internal", "calc_hmc_all_call_id": 10, "dsec_evaluation_index": 1})
        writer.writerow({"dsec_call_id": 1, "phase": "dsec_internal", "calc_hmc_all_call_id": 11, "dsec_evaluation_index": 2})
    with (tmp_path / "xstar_calc_hmc_all_input_summary_probe.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["calc_hmc_all_call_id", "temperature_k", "electron_fraction_xee", "hydrogen_density_cm3"],
        )
        writer.writeheader()
        writer.writerow({"calc_hmc_all_call_id": 10, "temperature_k": "7.0E4", "electron_fraction_xee": "1.1", "hydrogen_density_cm3": "1.0E8"})
        writer.writerow({"calc_hmc_all_call_id": 11, "temperature_k": "7.31984E4", "electron_fraction_xee": "1.202", "hydrogen_density_cm3": "1.0E8"})
    selected = load_xstar_target_state(tmp_path)
    assert selected["call_id"] == 11
    assert selected["evaluation_index"] == 2
    assert selected["temperature_K"] == pytest.approx(TARGET_TEMPERATURE_K)


def test_v0478_cli_exposes_probe_gate_and_unchanged_physical_tolerances():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--run-script", "run_xstar.sh",
            "--output-dir", "zone1",
            "--xstar-probe-dir", "probe",
            "--enforce-cooling-gate",
        ]
    )
    assert args.xstar_probe_dir == "probe"
    assert args.enforce_cooling_gate is True
    assert args.cooling_rtol == pytest.approx(5.0e-5)
    assert args.cooling_atol == pytest.approx(1.0e-30)


def test_v0478_scope_constants_are_exact_and_no_empirical_correction_exists():
    assert TARGET_TEMPERATURE_K == pytest.approx(73198.4)
    assert TARGET_CARBON_STAGES == (4, 5, 6)
    assert TARGET_CV_LOCAL_LEVELS == (4, 5, 6, 10, 11, 12, 20)
    source = Path(diagnostic.__file__).read_text(encoding="utf-8")
    assert "empirical correction" not in source.lower()
    assert xa.__version__ == "0.4.82"
