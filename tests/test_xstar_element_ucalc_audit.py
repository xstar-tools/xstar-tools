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

from xstar_atomic.xstar_element_solver import _audit_type59_recombination_record


def test_ucalc_level_guesses_for_type59_records():
    g59 = _guess_ucalc_levels(59, 7, [10, 2, 27, 4], nlevp=81)
    assert g59["idest1_guess"] == 27
    assert g59["idest2_guess"] == 81 + 10 - 1
    assert g59["idest3_guess"] == 4
    assert g59["idest4_guess"] == 2


def test_type59_excited_destination_is_suppressed_by_ucalc_gate():
    row = _audit_type59_recombination_record(
        [21.0, 1.0, 1.0],
        [10, 2, 27, 4],
        rate_type=7,
        record_ion_stage=5,
        target_ion_stage=5,
        parent_ion_stage=6,
        nlevp=81,
        level_rows=[{"level_index": 27, "level_label": "1s1.2s1.3S_1"}],
        level_indices=[1, 27],
    )
    assert row["type59_would_recombine_to_excited_level"] is True
    assert row["recomb_would_feed_helike_triplet_upper_candidate"] is True
    assert row["type59_ucalc_recombination_outputs_suppressed"] is True
    assert row["type59_can_feed_helike_triplet_upper_after_visible_gate"] is False
    assert row["python_eval_status"] == "type59_audited_recombination_outputs_suppressed_by_ucalc_gate"
