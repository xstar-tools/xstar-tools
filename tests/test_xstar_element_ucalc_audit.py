import pytest
pytest.importorskip("astropy")

from xstar_atomic.xstar_element_solver import _evaluate_type95_bryans_ci, _guess_ucalc_levels


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
