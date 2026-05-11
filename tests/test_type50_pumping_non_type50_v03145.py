import pytest
pytest.importorskip("astropy")

from xstar_atomic.xstar_element_solver import build_global_bound_bound_matrix_terms


def test_line_escape_and_pumping_handles_non_type50_bound_bound_rows_without_crash():
    transitions = [{
        "kind": "collisional_excitation",
        "data_type": 63,
        "record": 456,
        "element": "O",
        "element_z": 8,
        "ion_stage": 7,
        "from_level": 1,
        "to_level": 7,
        "rate_s^-1": 1.0e3,
        "source_method": "data_type_63_collision",
    }]
    global_index = [
        {"global_index": 0, "element": "O", "element_z": 8, "ion_stage": 7, "level_index": 1, "energy_eV": 0.0, "stat_weight": 1.0, "level_label": "1s2 1S0", "level_kind": "spectroscopic"},
        {"global_index": 6, "element": "O", "element_z": 8, "ion_stage": 7, "level_index": 7, "energy_eV": 574.0, "stat_weight": 3.0, "level_label": "1s2p 1P1", "level_kind": "spectroscopic"},
    ]
    rows = build_global_bound_bound_matrix_terms(
        transitions,
        global_index,
        type50_bound_bound_treatment="xstar-line-escape-and-pumping",
        radiation_field_mode="xstar-powerlaw",
        radiation_bremsa_scale=1.0e18,
        temperature_K=8.0e4,
    )
    assert rows
    assert rows[0]["type50_photoexcitation_status"] == "not_type50_radiative_transition"
    assert float(rows[0]["photoexcitation_rate_s^-1"]) == 0.0
