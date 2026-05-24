from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import xstar_atomic as xa
import xstar_atomic.source_port.ucalc as ucalc_module
from xstar_atomic.source_port.ucalc import (
    SourceFaithfulUCalc,
    UCalcContext,
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcStatus,
)
from xstar_atomic.source_port import ucalc_leaves
from xstar_atomic.source_port.zone1_dsec_probe_analysis import (
    compare_zone1_probe_with_python,
)
from xstar_atomic.xstar_zone1_dsec_probe import (
    zone1_extra_helper,
    zone1_insertion_snippets,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_v0479_type15_uses_literal_final_shell_threshold_and_d(monkeypatch):
    captured: dict[str, float] = {}

    def fake_bkhsgo(epi, threshold, d, b, coeff):
        captured["threshold"] = float(threshold)
        captured["d"] = float(d)
        return np.ones_like(np.asarray(epi, dtype=float)) * 1.0e-20

    def fake_phintfo_exact(*, sigma_cm2, threshold_ev, context, swrat):
        captured["phintfo_threshold"] = float(threshold_ev)
        return {
            "ans1": 1.0, "ans2": 2.0, "ans3": 3.0, "ans4": 4.0,
            "ans5": 5.0, "ans6": 6.0, "opakab": 0.0,
        }

    monkeypatch.setattr(ucalc_leaves, "bkhsgo", fake_bkhsgo)
    monkeypatch.setattr(ucalc_module, "_phintfo_exact", fake_phintfo_exact)
    levels = UCalcLevelTable(
        levels={
            1: UCalcLevel(1, energy_ev=0.0, statistical_weight=2.0),
            2: UCalcLevel(2, energy_ev=10.0, statistical_weight=4.0),
        },
        nlev=2,
    )
    radiation = SimpleNamespace(
        epim_eV=np.linspace(10.0, 1000.0, 200),
        bremsam=np.ones(200),
        bremsint=np.ones(200),
    )
    shell1 = [25.0, 1.5, 0.1] + [0.0] * 11 + [0.0]
    shell2 = [40.0, 2.5, 0.2] + [0.0] * 11 + [0.0]
    record = UCalcRecord(
        record=77,
        data_type=15,
        rate_type=1,
        continuation=0,
        reals=tuple(shell1 + shell2),
        integers=(2, 0, 3, 1, 1),
        parent_record=55,
    )
    context = UCalcContext(
        temperature_k=73198.4,
        hydrogen_density_cm3=1.0e8,
        electron_fraction_xee=1.2,
        nlev=2,
        levels=levels,
        radiation=radiation,
        extras={"type15_threshold_ev": 100.0},
    )
    result = SourceFaithfulUCalc().evaluate(record, context)
    assert result.status is UCalcStatus.EVALUATED
    assert captured == {
        "threshold": pytest.approx(40.0),
        "d": pytest.approx(2.5),
        "phintfo_threshold": pytest.approx(40.0),
    }
    assert result.diagnostics["type15_parent_threshold_ev"] == pytest.approx(100.0)
    assert result.diagnostics["type15_shell_thresholds_ev"] == pytest.approx((25.0, 40.0))
    assert result.diagnostics["type15_shell_d_values"] == pytest.approx((1.5, 2.5))
    assert result.diagnostics["type15_effective_threshold_ev"] == pytest.approx(40.0)
    assert result.diagnostics["type15_effective_d"] == pytest.approx(2.5)
    assert result.diagnostics["type15_bkhsgo_threshold_ev"] == pytest.approx(40.0)
    assert result.diagnostics["type15_phintfo_threshold_ev"] == pytest.approx(40.0)
    assert result.diagnostics["threshold_source"] == "final_type15_shell_record"


def test_v0479_probe_correlates_type15_shells_only_with_preliminary_civ_record():
    helper = zone1_extra_helper()
    snippets = zone1_insertion_snippets()
    assert "module xap_zone1_preliminary_rate_state" in helper
    assert "xap_zone1_begin_calc_ion_rate_record" in helper
    assert "xap_zone1_preliminary_element_z.ne.6" in helper
    assert "record.ne.xap_zone1_preliminary_record" in helper
    assert "call xap_zone1_clear_preliminary_rate()" in helper
    assert "pirti_before=pirti" in snippets["calc_ion_rates_record"]
    assert "rrrti_before=rrrti" in snippets["calc_ion_rates_record"]
    assert "xap_zone1_type15_shell" in snippets["ucalc_type15_shell"]
    assert "subroutine xap_zone1_type15_effective" in helper
    assert "xap_zone1_type15_effective(ml,nilin,1,ett,ddd)" in snippets["ucalc_type15_shell"]
    assert "xap_zone1_type15_effective(ml,nilin,2,ett,ddd)" in snippets["ucalc_type15_shell"]
    assert "xap_zone1_normalization_row" in snippets["msolvelucy_normalization_row"]
    assert "xap_zone1_level_population" in snippets["calc_hmc_element_level_population"]


def test_v0479_ten_gate_comparator_requires_and_accepts_complete_exact_contract(tmp_path: Path):
    py = tmp_path / "python"
    xs = tmp_path / "xstar"
    out = tmp_path / "comparison"

    rates = []
    for stage, fraction, photo, recomb in (
        (4, 4.5e-5, 9.0e-10, 2.4e-12),
        (5, 0.02, 8.3e-11, 3.0e-12),
        (6, 0.98, 2.2e-11, 4.0e-12),
    ):
        rates.append({
            "ion_stage": stage,
            "preliminary_ion_fraction": fraction,
            "preliminary_photoionization_rate": photo,
            "preliminary_recombination_rate": recomb,
            "second_pass_photoionization_rate": photo,
            "second_pass_recombination_rate": recomb,
        })
    record = {
        "record": 123,
        "data_type": 15,
        "rate_type": 1,
        "parent_record": 100,
        "parent_threshold_ev": 100.0,
        "shell_thresholds_ev": "25;40",
        "shell_d_values": "1.5;2.5",
        "final_effective_threshold_ev": 40.0,
        "final_effective_d": 2.5,
        "bkhsgo_threshold_ev": 40.0,
        "bkhsgo_effective_d": 2.5,
        "phintfo_threshold_ev": 40.0,
        "phintfo_effective_d": 2.5,
        "ans1": 9.0e-10,
        "ans2": 1.0,
        "ans3": 2.0,
        "ans4": 3.0,
        "ans5": 4.0,
        "ans6": 5.0,
        "pirti_before": 0.0,
        "pirti_contribution": 9.0e-10,
        "pirti_after": 9.0e-10,
        "rrrti_before": 0.0,
        "rrrti_contribution": 0.0,
        "rrrti_after": 0.0,
        "idest1": 1,
        "idest2": 2,
    }
    topology = [{
        "critf": 1.0e-7,
        "civ_preliminary_fraction": 4.5e-5,
        "selected_min_ion_stage": 4,
        "selected_max_ion_stage": 6,
        "civ_retained": True,
        "compact_dimension": 100,
        "normalization_row": 100,
    }]
    matrix = []
    for index in range(932):
        matrix.append({
            "local_level": 4 + index % 7,
            "record": 1000 + index,
            "role": "forward_diag_loss",
            "row": 30 + index,
            "column": 30 + index,
            "escape_factor_in": 1.0,
            "escape_factor_out": 1.0,
            "density_scale": 1.0e8,
            "ans1": 1.0,
            "ans2": 2.0,
            "ans3": 3.0,
            "ans4": 4.0,
            "ans5": 5.0,
            "ans6": 6.0,
            "aj1": 1.0,
            "aj2": 2.0,
            "cj": 3.0,
            "cj2": 4.0,
        })
    initial = [
        {"compact_index": index, "population": 1.0 / 100.0}
        for index in range(1, 101)
    ]
    normalization = [
        {"outer_iteration": 1, "column": index, "matrix_value": 1.0, "rhs_value": 1.0}
        for index in range(1, 101)
    ]
    levels = [
        {"ion_stage": 5, "local_level": level, "population": 1.0e-4 * level}
        for level in (4, 5, 6, 10, 11, 12, 20)
    ]
    cooling = [{
        "ion_stage": 5,
        "record": 777,
        "data_type": 50,
        "rate_type": 4,
        "role": "forward_diag_loss",
        "idest1": 20,
        "idest2": 20,
        "lower_endpoint": 20,
        "upper_endpoint": 20,
        "population": 2.0e-3,
        "cj": 3.0e-20,
        "cj2": 4.0e-20,
        "cooling_contribution": 6.0e-23,
        "cooling2_contribution": 8.0e-23,
    }]
    fingerprint = [{"evaluation_index": 1, "name": "runtime", "count": 1, "sha256": "abc"}]

    for root, prefix in ((py, "python"), (xs, "xstar")):
        _write_csv(root / f"{prefix}_zone1_carbon_rates_T73198p4K.csv", rates)
        _write_csv(root / f"{prefix}_zone1_civ_calc_ion_rates_records_T73198p4K.csv", [record])
        _write_csv(root / f"{prefix}_zone1_carbon_topology_T73198p4K.csv", topology)
        _write_csv(root / f"{prefix}_zone1_cv_matrix_levels_4_6_10_12_20.csv", matrix)
        _write_csv(root / f"{prefix}_zone1_carbon_initial_population_T73198p4K.csv", initial)
        _write_csv(root / f"{prefix}_zone1_carbon_normalization_row_T73198p4K.csv", normalization)
        _write_csv(root / f"{prefix}_zone1_cv_level_populations_T73198p4K.csv", levels)
        cooling_rows = [dict(row) for row in cooling]
        if prefix == "xstar":
            cooling_rows[0]["idest1"], cooling_rows[0]["idest2"] = 99, 42
        _write_csv(root / f"{prefix}_zone1_carbon_cooling_logical_T73198p4K.csv", cooling_rows)
        _write_csv(root / f"{prefix}_zone1_calc_hmc_all_input_fingerprints.csv", fingerprint)
    (py / "python_zone1_same_entry_replay_summary.json").write_text(
        json.dumps({"ready": True}), encoding="utf-8"
    )

    products = compare_zone1_probe_with_python(
        xstar_analysis_dir=xs,
        python_diagnostic_dir=py,
        out_dir=out,
    )
    summary = json.loads(products["summary_json"].read_text(encoding="utf-8"))
    assert summary["type15_record_level_proof_ready"] is True
    assert summary["civ_record_level_parity_ready"] is True
    assert summary["python_civ_dominant_record"] == 123
    assert summary["python_civ_dominant_data_type"] == 15
    assert summary["python_civ_type15_is_dominant"] is True
    assert summary["civ_preliminary_photoionization_parity_ready"] is True
    assert summary["civ_preliminary_fraction_parity_ready"] is True
    assert summary["civ_retained_by_critf_ready"] is True
    assert summary["cv_compact_topology_ready"] is True
    assert summary["cv_logical_row_count_python"] == 932
    assert summary["cv_logical_coefficient_parity_ready"] is True
    assert summary["cv_initial_population_vector_ready"] is True
    assert summary["cv_normalization_row_ready"] is True
    assert summary["cv_level20_population_parity_ready"] is True
    assert summary["carbon_cooling_logical_parity_ready"] is True
    assert summary["thermal_root_may_continue"] is True

    # A benchmark with no selected data-type-15 record must report the proof
    # as non-applicable rather than fail merely because lazily-created shell
    # probe files do not exist.  Record-level C IV parity still remains a gate.
    non_type15_record = dict(record)
    non_type15_record["data_type"] = 59
    non_type15_record["rate_type"] = 1
    for root, prefix in ((py, "python"), (xs, "xstar")):
        _write_csv(
            root / f"{prefix}_zone1_civ_calc_ion_rates_records_T73198p4K.csv",
            [non_type15_record],
        )
    not_applicable = compare_zone1_probe_with_python(
        xstar_analysis_dir=xs,
        python_diagnostic_dir=py,
        out_dir=tmp_path / "comparison_not_applicable",
    )
    not_applicable_summary = json.loads(
        not_applicable["summary_json"].read_text(encoding="utf-8")
    )
    assert not_applicable_summary["type15_record_level_proof_applicable"] is False
    assert not_applicable_summary["type15_record_level_proof_ready"] is False
    assert not_applicable_summary["type15_record_gate_passed"] is True
    assert not_applicable_summary["civ_record_level_parity_ready"] is True
    assert not_applicable_summary["thermal_root_may_continue"] is True

    # Coverage is strict: one missing logical C V row blocks both gate 5 and DSEC.
    _write_csv(
        xs / "xstar_zone1_cv_matrix_levels_4_6_10_12_20.csv",
        matrix[:-1],
    )
    incomplete = compare_zone1_probe_with_python(
        xstar_analysis_dir=xs,
        python_diagnostic_dir=py,
        out_dir=tmp_path / "comparison_incomplete",
    )
    incomplete_summary = json.loads(
        incomplete["summary_json"].read_text(encoding="utf-8")
    )
    assert incomplete_summary["cv_logical_row_count_xstar"] == 931
    assert incomplete_summary["cv_logical_coefficient_parity_ready"] is False
    assert incomplete_summary["thermal_root_may_continue"] is False
    assert xa.__version__ == "0.4.85"
