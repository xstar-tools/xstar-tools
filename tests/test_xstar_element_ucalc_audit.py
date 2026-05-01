import pytest
pytest.importorskip("astropy")

from xstar_atomic.xstar_element_solver import _evaluate_type57_calt57_record, _evaluate_type95_bryans_ci, _guess_ucalc_levels


def test_type95_bryans_ci_diagnostic_evaluates_positive_rate():
    # Minimal synthetic Bryans-like spline: E, Tmin, x grid, rho grid.
    row = _evaluate_type95_bryans_ci(
        [100.0, 1.0, 0.0, 0.5, 1.0, 0.2, 0.3, 0.4],
        [1, 1],
        temperature=1.0e6,
        electron_density=1.0e8,
    )
    assert row["python_eval_status"] == "evaluated_type95_bryans_ci_diagnostic"
    assert row["python_rate_forward_s^-1"] >= 0.0
    assert row["type95_nspline"] == 3


def test_ucalc_level_guesses_for_bound_free_records():
    g53 = _guess_ucalc_levels(53, 7, [1, 2, 3, 4], nlevp=81)
    assert g53["idest1_guess"] == 3
    assert g53["idest2_guess"] == 81 + 2 - 1
    g57 = _guess_ucalc_levels(57, 5, [2, 99, 4], nlevp=81)
    assert g57["idest1_guess"] == 99
    assert g57["idest2_guess"] == 81



def test_type57_calt57_diagnostic_evaluates_without_assembly():
    # Synthetic level row similar to an excited C V destination.  The evaluator
    # ports calt57/irc/szirc and reports ucalc ans1/ans2 rates for audit only.
    row = _evaluate_type57_calt57_record(
        [5.1],
        [3, 3, 6, 10, 20],
        temperature=1.0e6,
        electron_density=1.0e8,
        nlevp=57,
        level_rows=[{
            "level_index": 10,
            "energy_eV": 5.0,
            "binding_from_continuum_eV": 500.0,
            "statistical_weight_g": 3.0,
        }],
    )
    assert row["python_eval_status"] in {
        "evaluated_type57_calt57_diagnostic",
        "type57_rate_below_xstar_cutoff",
    }
    assert row["type57_n_principal"] == 3
    assert row["type57_destination_level"] == 10
    assert "type57_cion_cm3_s" in row


def test_type57_ground_destination_is_not_evaluated_by_ucalc_gate():
    row = _evaluate_type57_calt57_record(
        [1.0],
        [1, 1],
        temperature=1.0e6,
        electron_density=1.0e8,
        nlevp=57,
        level_rows=[{
            "level_index": 1,
            "energy_eV": 0.0,
            "binding_from_continuum_eV": 500.0,
            "statistical_weight_g": 1.0,
        }],
    )
    # ucalc gates out idest1 <= 1 before calling calt57; a later ground-zeroing
    # safeguard is preserved in the evaluator for completeness.
    assert row["python_eval_status"] == "type57_idest1_outside_ucalc_range"
