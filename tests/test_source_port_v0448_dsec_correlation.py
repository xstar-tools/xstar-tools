from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from xstar_atomic.source_port import (
    DsecMutableRuntimeState,
    DsecEvaluation,
    compare_dsec_thermal_decomposition,
    compare_dsec_trajectory,
    dsec,
    load_dsec_matching_input_state,
    load_xstar_dsec_thermal_decomposition,
    load_xstar_dsec_trajectory,
    resolve_dsec_calc_hmc_all_calls,
)


def _write(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def test_call_correlation_resolves_input_and_post(tmp_path: Path) -> None:
    path = tmp_path / "xstar_dsec_calc_hmc_all_call_correlation.csv"
    _write(
        path,
        [
            "calc_hmc_all_call_id",
            "dsec_call_id",
            "dsec_evaluation_index",
            "phase",
            "temperature_t4",
            "electron_fraction_xee",
            "hydrogen_density_cm3",
        ],
        [
            [11, 1, 1, "dsec_internal", 100.0, 1.0, 1.0e8],
            [12, 1, 2, "dsec_internal", 100.0, 1.2, 1.0e8],
            [44, 1, 0, "post_dsec", 7.66, 1.2046, 1.0e8],
        ],
    )
    result = resolve_dsec_calc_hmc_all_calls(path, dsec_call_id=1)
    assert result.input_calc_hmc_all_call_id == 11
    assert result.post_dsec_calc_hmc_all_call_id == 44


def test_matching_input_loader_restores_runtime_and_workspaces(tmp_path: Path) -> None:
    _write(
        tmp_path / "xstar_calc_hmc_all_input_summary_probe.csv",
        [
            "calc_hmc_all_call_id", "dsec_call_id", "dsec_evaluation_index",
            "phase", "temperature_t4", "temperature_k", "trad", "radius_cm",
            "zone_thickness_cm", "electron_fraction_xee", "hydrogen_density_cm3",
            "covering_fraction", "pressure", "lcdd", "zeta",
            "turbulent_velocity_km_s", "critf", "ncn2",
        ],
        [[11, 1, 1, "dsec_internal", 100.0, 1.0e6, 0.0, 1.0e16, 1.0e12,
          1.0, 1.0e8, 1.0, 0.0, 1, 0.0, 0.0, 1.0e-6, 2]],
    )
    _write(
        tmp_path / "xstar_calc_hmc_all_input_continuum_probe.csv",
        ["calc_hmc_all_call_id", "grid_index", "ncn2", "epi_eV", "bremsa", "bremsint"],
        [[11, 1, 2, 10.0, 2.0, 3.0], [11, 2, 2, 20.0, 1.0, 1.5]],
    )
    _write(
        tmp_path / "xstar_calc_hmc_all_input_tau0_probe.csv",
        ["calc_hmc_all_call_id", "line_index", "tau_in", "tau_out"],
        [[11, 1, 0.1, 0.2], [11, 2, 0.3, 0.4]],
    )
    _write(
        tmp_path / "xstar_calc_hmc_all_input_tauc_probe.csv",
        ["calc_hmc_all_call_id", "continuum_index", "tau_in", "tau_out"],
        [[11, 1, 0.5, 0.6]],
    )
    _write(
        tmp_path / "xstar_calc_hmc_all_input_global_levels_probe.csv",
        ["calc_hmc_all_call_id", "global_level_index", "xilevg", "bilevg", "rnisg"],
        [[11, 1, 0.0, 1.0, 2.0], [11, 2, 0.0, 3.0, 4.0]],
    )
    _write(
        tmp_path / "xstar_calc_hmc_all_input_leveltemp_probe.csv",
        ["calc_hmc_all_call_id", "column_index", "slot", "rlev", "ilev", "nlpt", "iltp"],
        [[11, 1, 1, 12.0, 2, 1, 9], [11, 1, 2, 3.0, 1, 1, 9]],
    )
    state = load_dsec_matching_input_state(tmp_path, call_id=11)
    assert state.dsec_call_id == 1
    assert state.phase == "dsec_internal"
    assert state.global_xilevg_is_zero
    assert state.radiation.epim_eV == (10.0, 20.0)
    assert np.array_equal(state.escape.line_tau_in, np.array([0.1, 0.3]))
    assert state.leveltemp_workspace is not None
    assert state.leveltemp_workspace.energy(1) == 12.0


class _Linear:
    def __call__(self, state: DsecMutableRuntimeState) -> DsecEvaluation:
        return DsecEvaluation(
            hmctot=(2.0 - state.temperature_t4) / 2.0,
            elcter=state.electron_fraction_xee - 1.0,
        )


def _write_trajectory(path: Path, result) -> None:
    fields = ["dsec_call_id", *result.trajectory[0].__dataclass_fields__]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for event in result.trajectory:
            writer.writerow({"dsec_call_id": 1, **{k: getattr(event, k) for k in event.__dataclass_fields__}})


def test_fast_prefix_mode_is_a_valid_xstar_trajectory_prefix(tmp_path: Path) -> None:
    full = dsec(DsecMutableRuntimeState(1.0, 1.44, 1.0e8), evaluator=_Linear(), nlim=20, tinf_t4=0.01)
    path = tmp_path / "xstar_dsec_trajectory_probe.csv"
    _write_trajectory(path, full)
    prefix = dsec(
        DsecMutableRuntimeState(1.0, 1.44, 1.0e8),
        evaluator=_Linear(),
        nlim=20,
        tinf_t4=0.01,
        maximum_evaluations=1,
    )
    assert prefix.prefix_terminated
    assert [row.event for row in prefix.trajectory] == ["begin", "after_calc_hmc_all"]
    parity = compare_dsec_trajectory(
        prefix,
        load_xstar_dsec_trajectory(path),
        prefix_mode=True,
    )
    assert parity.ready


def _fixed(value: float):
    continuum = SimpleNamespace(htcomp=value, clcomp=value, htfreef=value, clbrems=value)
    return SimpleNamespace(
        temperature_k=1.0e6,
        electron_fraction_xee=1.0,
        hydrogen_density_cm3=1.0e8,
        httot_pre_continuum=value,
        cltot_pre_continuum=value,
        httot2_pre_continuum=value,
        cltot2_pre_continuum=value,
        httot=value,
        cltot=value,
        httot2=value,
        cltot2=value,
        hmctot=value,
        elcter=value,
        continuum=continuum,
    )


def test_thermal_decomposition_prefix_parity(tmp_path: Path) -> None:
    fields = [
        "dsec_call_id", "evaluation_index", "calc_hmc_all_call_id", "phase",
        "temperature_t4", "temperature_k", "electron_fraction_xee",
        "hydrogen_density_cm3", "httot_pre_continuum", "cltot_pre_continuum",
        "httot2_pre_continuum", "cltot2_pre_continuum", "htcomp", "clcomp",
        "htfreef", "clbrems", "httot", "cltot", "httot2", "cltot2",
        "cllines", "clcont", "hmctot", "elcter",
    ]
    values = [1, 1, 11, "dsec_internal", 100.0, 1.0e6, 1.0, 1.0e8] + [2.0] * 16
    path = tmp_path / "xstar_dsec_thermal_decomposition_probe.csv"
    _write(path, fields, [values])
    rows = load_xstar_dsec_thermal_decomposition(path, dsec_call_id=1)
    evaluation = DsecEvaluation(hmctot=2.0, elcter=2.0, fixed_state_result=_fixed(2.0))
    parity = compare_dsec_thermal_decomposition([evaluation], rows, prefix_mode=True)
    assert parity.ready
