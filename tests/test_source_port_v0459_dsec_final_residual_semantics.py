from __future__ import annotations

import csv
import json
from pathlib import Path

from xstar_atomic.source_port_dsec_final_residual_semantics_cli import main


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_offline_final_residual_semantics_accepts_source_converged_state(
    tmp_path: Path,
) -> None:
    root = tmp_path / "v0458"
    summary = {
        "python_dsec_converged": True,
        "evaluation_count_ready": True,
        "source_control_flow_ready": True,
        "thermal_component_trajectory_ready": True,
        "thermal_residual_sign_ready": True,
        "evaluation2_internal_ready": True,
        "post_dsec_calc_hmc_all_executed": True,
        "natural_final_physics_ready": True,
        "exact_post_dsec_replay_executed": True,
        "exact_post_dsec_fixed_state_parity_ready": False,
        "frozen_v0444_complete_fixed_state_regression": True,
        "strict_trajectory_ready": False,
        "natural_final_fixed_state_parity_ready": False,
    }
    _write_json(root / "xstar_dsec_post_final_replay_summary.json", summary)
    exact = root / "unrestricted_source_zero_post_replay" / "post_dsec_exact_replay"
    exact_summary = {
        "fixed_state_calc_hmc_all_translated": True,
        "pre_matrix_ready": True,
        "element_loop_ready": True,
        "charge_scope_complete": True,
        "continuum_sequence_complete": True,
        "runtime_state_parity_ready": True,
        "continuum_component_parity_ready": True,
        "primary_heating_cooling_totals_parity_ready": True,
        "secondary_heating_cooling_totals_parity_ready": True,
        "electron_contribution_parity_ready": True,
        "charge_residual_parity_ready": True,
        "charge_identity_ready": True,
        "hmctot_parity_ready": False,
        "complete_fixed_state_ready": True,
    }
    _write_json(
        exact / "xstar_calc_hmc_all_complete_fixed_state_parity_summary.json",
        exact_summary,
    )
    py_h = 2.1780313628738658e-7
    py_c = 2.1779005273384123e-7
    xs_h = 2.1780603350353703e-7
    xs_c = 2.177880437491999e-7
    py_r = 2.0 * (py_h - py_c) / (1.0e-37 + py_h + py_c)
    xs_r = 2.0 * (xs_h - xs_c) / (1.0e-37 + xs_h + xs_c)
    rows = [
        ("temperature_t4", 7.6655, 7.6655, True),
        ("electron_fraction_xee", 1.204656, 1.204656, True),
        ("httot", py_h, xs_h, True),
        ("cltot", py_c, xs_c, True),
        ("httot2", 6.2541e-8, 6.2543e-8, True),
        ("cltot2", 6.21735e-8, 6.21736e-8, True),
        ("elcter", -4.1405e-5, -4.14068e-5, True),
        ("hmctot", py_r, xs_r, False),
    ]
    exact.mkdir(parents=True, exist_ok=True)
    with (exact / "xstar_calc_hmc_all_complete_fixed_state_parity.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("quantity", "python_value", "xstar_value", "within_tolerance"),
        )
        writer.writeheader()
        for quantity, py, xs, ready in rows:
            writer.writerow(
                {
                    "quantity": quantity,
                    "python_value": py,
                    "xstar_value": xs,
                    "within_tolerance": ready,
                }
            )

    out = tmp_path / "out"
    code = main(
        [
            "--v0458-results-dir",
            str(root),
            "--out-dir",
            str(out),
        ]
    )
    assert code == 0
    data = json.loads(
        (out / "xstar_dsec_final_residual_semantics_summary.json").read_text()
    )
    assert data["port_version"] == "v0.4.59"
    assert data["exact_post_dsec_fixed_state_parity_ready"] is False
    assert data["exact_post_dsec_fixed_state_semantic_ready"] is True
    assert data["unrestricted_source_semantic_acceptance_ready"] is True
    assert data["ready_to_advance_to_bremsmap"] is True
