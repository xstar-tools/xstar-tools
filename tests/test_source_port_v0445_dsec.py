from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

from xstar_atomic.source_port.dsec import (
    DSEC_CHARGE_TOLERANCE,
    DSEC_ELECTRON_FACTOR,
    DSEC_TEMPERATURE_FACTOR,
    DSEC_TEMPERATURE_STAGNATION_TOLERANCE,
    DSEC_THERMAL_TOLERANCE,
    CalcHMCAllDsecEvaluator,
    DsecEvaluation,
    DsecMutableRuntimeState,
    compare_dsec_trajectory,
    dsec,
    load_python_dsec_trajectory,
    load_xstar_dsec_trajectory,
    validate_v0444_complete_fixed_state_regression,
    write_dsec_trajectory_products,
)
from xstar_atomic.source_port.local_zone import FixedStateElementRequest


class LinearBalanceEvaluator:
    def __init__(self, *, target_t4: float = 2.0, target_xee: float = 1.0):
        self.target_t4 = target_t4
        self.target_xee = target_xee
        self.calls: list[tuple[float, float]] = []

    def __call__(self, state: DsecMutableRuntimeState) -> DsecEvaluation:
        self.calls.append((state.temperature_t4, state.electron_fraction_xee))
        # Source sign convention: positive hmctot means heating exceeds cooling,
        # so dsec raises the temperature.
        return DsecEvaluation(
            hmctot=(self.target_t4 - state.temperature_t4) / self.target_t4,
            elcter=state.electron_fraction_xee - self.target_xee,
        )



def test_calc_hmc_all_evaluator_owns_one_reusable_dispatcher() -> None:
    evaluator = CalcHMCAllDsecEvaluator(master=object(), derived=object())
    assert evaluator.dispatcher is not None
    first = evaluator.dispatcher
    evaluator.__post_init__()
    assert evaluator.dispatcher is first

def test_default_real_constants_are_promoted_after_float32_rounding() -> None:
    assert DSEC_CHARGE_TOLERANCE == float(np.float32(1.0e-4))
    assert DSEC_THERMAL_TOLERANCE == float(np.float32(1.0e-4))
    assert DSEC_TEMPERATURE_STAGNATION_TOLERANCE == float(np.float32(2.0e-9))
    assert DSEC_TEMPERATURE_FACTOR == float(np.float32(1.2))
    assert DSEC_ELECTRON_FACTOR == float(np.float32(1.2))


def test_negative_nlim_runs_charge_only_and_keeps_temperature() -> None:
    state = DsecMutableRuntimeState(1.5, 1.44, 1.0e8)
    evaluator = LinearBalanceEvaluator(target_t4=2.0, target_xee=1.0)
    result = dsec(state, evaluator=evaluator, nlim=-20, tinf_t4=0.01)

    assert result.requested_thermal_iteration is False
    assert result.charge_converged is True
    assert result.state.temperature_t4 == 1.5
    assert math.isclose(result.state.electron_fraction_xee, 1.0, rel_tol=2.0e-7)
    assert "temperature_multiply" not in [row.event for row in result.trajectory]
    assert "temperature_divide" not in [row.event for row in result.trajectory]


def test_positive_nlim_reproduces_nested_charge_and_thermal_branches() -> None:
    state = DsecMutableRuntimeState(1.0, 1.44, 1.0e8)
    evaluator = LinearBalanceEvaluator(target_t4=2.0, target_xee=1.0)
    result = dsec(state, evaluator=evaluator, nlim=20, tinf_t4=0.01)

    events = [row.event for row in result.trajectory]
    assert result.converged is True
    assert result.lnerr == 0
    assert result.ntotit == len(evaluator.calls)
    assert math.isclose(result.state.temperature_t4, 2.0, rel_tol=1.0e-12)
    assert math.isclose(result.state.electron_fraction_xee, 1.0, rel_tol=2.0e-7)
    assert "charge_divide_xee" in events
    assert "temperature_multiply" in events
    assert "temperature_secant" in events
    assert events[0] == "begin"
    assert events[-1] == "finish"


def test_tinf_proximity_disables_both_iterations_after_one_evaluation() -> None:
    state = DsecMutableRuntimeState(1.0, 1.0, 1.0e8)

    def balanced(current: DsecMutableRuntimeState) -> DsecEvaluation:
        return DsecEvaluation(hmctot=0.0, elcter=0.0)

    result = dsec(state, evaluator=balanced, nlim=99, tinf_t4=1.0)
    assert result.ntotit == 1
    assert [row.event for row in result.trajectory] == [
        "begin", "after_calc_hmc_all", "charge_loop_exit", "finish"
    ]
    after = result.trajectory[1]
    assert after.nlimx == 0
    assert after.nlimxx == 0
    assert after.nlimt == 0
    assert after.nlimtt == 0


def test_mutable_population_seed_is_replayed_on_next_trial() -> None:
    request = FixedStateElementRequest(
        element_z=8,
        min_ion_stage=3,
        max_ion_stage=8,
        initial_populations=np.array([0.2, 0.8]),
        initial_population_source="original",
    )
    state = DsecMutableRuntimeState(
        1.0, 1.0, 1.0e8, element_requests=(request,),
        element_populations={8: np.array([0.3, 0.7])},
    )
    replay = state.requests_for_next_call()[0]
    assert np.array_equal(replay.initial_populations, np.array([0.3, 0.7]))
    assert replay.initial_population_source == "dsec_previous_calc_hmc_all_final_population"
    replay.initial_populations[0] = 99.0
    assert state.element_populations[8][0] == 0.3


def _write_probe_from_result(path: Path, result, *, perturb_hmctot: bool = False) -> None:
    fields = ["dsec_call_id"] + list(result.trajectory[0].__dataclass_fields__)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for event in result.trajectory:
            row = {name: getattr(event, name) for name in event.__dataclass_fields__}
            row["dsec_call_id"] = 1
            if perturb_hmctot and event.event == "after_calc_hmc_all" and row["hmctot"] is not None:
                row["hmctot"] = -float(row["hmctot"])
            writer.writerow(row)


def test_trajectory_loader_and_strengthened_residual_parity(tmp_path: Path) -> None:
    result = dsec(
        DsecMutableRuntimeState(1.0, 1.44, 1.0e8),
        evaluator=LinearBalanceEvaluator(),
        nlim=20,
        tinf_t4=0.01,
    )
    probe = tmp_path / "xstar_dsec_trajectory_probe.csv"
    _write_probe_from_result(probe, result)
    parity = compare_dsec_trajectory(result, load_xstar_dsec_trajectory(probe))
    assert parity.ready is True
    assert parity.thermal_residual_sign_ready is True
    assert parity.charge_residual_sign_ready is True

    _write_probe_from_result(probe, result, perturb_hmctot=True)
    mismatch = compare_dsec_trajectory(result, load_xstar_dsec_trajectory(probe))
    assert mismatch.thermal_residual_sign_ready is False
    assert mismatch.ready is False


def test_trajectory_products_and_frozen_v0444_gate(tmp_path: Path) -> None:
    result = dsec(
        DsecMutableRuntimeState(1.0, 1.44, 1.0e8),
        evaluator=LinearBalanceEvaluator(),
        nlim=20,
        tinf_t4=0.01,
    )
    products = write_dsec_trajectory_products(result, tmp_path)
    assert products["csv"].is_file()
    assert products["json"].is_file()
    loaded = load_python_dsec_trajectory(tmp_path)
    assert [row.event for row in loaded.trajectory] == [
        row.event for row in result.trajectory
    ]
    assert loaded.ntotit == result.ntotit
    assert validate_v0444_complete_fixed_state_regression().ready is True
