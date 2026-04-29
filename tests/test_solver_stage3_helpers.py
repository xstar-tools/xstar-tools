import numpy as np
import pytest

pytest.importorskip("astropy")

from xstar_atomic.solver import (
    make_o7_triplet_diagnostics,
    prune_unconnected_levels,
    solve_steady_state,
    summarize_source_sink_vectors,
)


def test_solve_steady_state_reports_matrix_diagnostics():
    R = np.array([[0.0, 2.0], [1.0, 0.0]])
    pop, info = solve_steady_state(R, linear_solver="dense")
    assert abs(pop.sum() - 1.0) < 1e-12
    assert info["matrix_nnz"] > 0
    assert info["matrix_density"] > 0
    assert info["matrix_rank"] == 2
    assert info["linear_residual_linf"] is not None
    assert info["normalization_residual"] < 1e-12


def test_prune_unconnected_levels_preserves_ground_output_and_source_levels():
    levels = [1, 2, 3, 4, 5]
    edges = [(1, 2, "radiative"), (2, 3, "collision")]
    output_lines = [{"lower_level": 1, "upper_level": 4}]
    pruned, diag = prune_unconnected_levels(levels, edges, output_lines, ground_level=1, source_levels=[5])
    assert pruned == [1, 2, 3, 4, 5]
    assert diag["n_levels_removed"] == 0

    pruned2, diag2 = prune_unconnected_levels(levels, edges, [], ground_level=1, source_levels=[])
    assert pruned2 == [1, 2, 3]
    assert diag2["n_levels_removed"] == 2


def test_source_sink_summary_reports_nonzero_levels():
    levels = [1, 2, 3]
    source = np.array([0.0, 1.5, 0.0])
    sink = np.array([0.2, 0.0, 0.0])
    out = summarize_source_sink_vectors(levels, source, sink, ["note"])
    assert out["n_source_terms_nonzero"] == 1
    assert out["n_sink_terms_nonzero"] == 1
    assert out["source_sum_s^-1"] == 1.5
    assert len(out["nonzero_level_terms"]) == 2


def test_o7_triplet_diagnostics_compute_R_and_G():
    rows = [
        {"element": "O", "ion_stage": 7, "temperature_K": 1e6, "electron_density_cm^-3": 1.0, "upper_level": 2, "wavelength_A": 22.1012, "line_energy_emissivity_per_ion_erg_s^-1": 4.0},
        {"element": "O", "ion_stage": 7, "temperature_K": 1e6, "electron_density_cm^-3": 1.0, "upper_level": 3, "wavelength_A": 21.8070, "line_energy_emissivity_per_ion_erg_s^-1": 1.0},
        {"element": "O", "ion_stage": 7, "temperature_K": 1e6, "electron_density_cm^-3": 1.0, "upper_level": 5, "wavelength_A": 21.8044, "line_energy_emissivity_per_ion_erg_s^-1": 1.0},
        {"element": "O", "ion_stage": 7, "temperature_K": 1e6, "electron_density_cm^-3": 1.0, "upper_level": 7, "wavelength_A": 21.6020, "line_energy_emissivity_per_ion_erg_s^-1": 2.0},
    ]
    diag = make_o7_triplet_diagnostics(rows)
    assert len(diag) == 1
    assert diag[0]["R_f_over_i"] == 2.0
    assert diag[0]["G_f_plus_i_over_r"] == 3.0


def test_helike_triplet_diagnostics_compute_generic_c_v():
    from xstar_atomic.solver import make_helike_triplet_diagnostics
    rows = [
        {"element": "C", "ion_stage": 5, "temperature_K": 1e6, "electron_density_cm^-3": 1.0, "lower_label": "1s2.1S_0", "upper_label": "1s1.2s1.3S_1", "line_energy_emissivity_per_ion_erg_s^-1": 6.0},
        {"element": "C", "ion_stage": 5, "temperature_K": 1e6, "electron_density_cm^-3": 1.0, "lower_label": "1s2.1S_0", "upper_label": "1s1.2p1.1P_1", "line_energy_emissivity_per_ion_erg_s^-1": 2.0},
        {"element": "C", "ion_stage": 5, "temperature_K": 1e6, "electron_density_cm^-3": 1.0, "lower_label": "1s2.1S_0", "upper_label": "1s1.2p1.3P_2", "line_energy_emissivity_per_ion_erg_s^-1": 1.0},
        {"element": "C", "ion_stage": 5, "temperature_K": 1e6, "electron_density_cm^-3": 1.0, "lower_label": "1s2.1S_0", "upper_label": "1s1.2p1.3P_1", "line_energy_emissivity_per_ion_erg_s^-1": 1.0},
    ]
    diag = make_helike_triplet_diagnostics(rows)
    assert len(diag) == 1
    assert diag[0]["element"] == "C"
    assert diag[0]["ion_stage"] == 5
    assert diag[0]["R_f_over_i"] == 3.0
    assert diag[0]["G_f_plus_i_over_r"] == 4.0
