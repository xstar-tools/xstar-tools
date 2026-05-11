import pytest
pytest.importorskip("astropy")

from xstar_atomic.xstar_element_solver import build_global_bound_bound_matrix_terms


def test_type50_line_escape_and_pumping_injects_reverse_matrix_terms():
    transitions = [{
        "kind": "radiative_decay",
        "data_type": 50,
        "record": 123,
        "element": "O",
        "element_z": 8,
        "ion_stage": 7,
        "from_level": 7,
        "to_level": 1,
        "rate_s^-1": 3.0e12,
        "source_method": "data_type_50_rate_type_4",
        "depth_inward": 0.0,
        "depth_outward": 0.0,
    }]
    global_index = [
        {"global_index": 0, "element": "O", "element_z": 8, "ion_stage": 7, "level_index": 1, "energy_eV": 0.0, "stat_weight": 1.0, "level_label": "1s2 1S0", "level_kind": "spectroscopic"},
        {"global_index": 6, "element": "O", "element_z": 8, "ion_stage": 7, "level_index": 7, "energy_eV": 574.0, "stat_weight": 3.0, "level_label": "1s2p 1P1", "level_kind": "spectroscopic"},
    ]
    rows = build_global_bound_bound_matrix_terms(
        transitions,
        global_index,
        type50_bound_bound_treatment="xstar-line-escape-and-pumping",
        type50_escape_factor=0.35,
        type50_escape_source="xstar-reference-lines",
        type50_cfrac=0.0,
        radiation_field_mode="xstar-powerlaw",
        radiation_bremsa_scale=1.0e18,
        radiation_n_energy_grid=128,
        radiation_powerlaw_index=1.0,
        temperature_K=8.0e4,
    )
    pump = [r for r in rows if r.get("matrix_role") == "type50_photoexcitation_gain_to_upper_proxy"]
    assert pump, rows
    assert float(pump[0]["signed_rate_s^-1"]) > 0.0
    assert pump[0]["type50_photoexcitation_matrix_status"] == "source_code_matched_ucalc_type50_lower_to_upper_injected"
    assert pump[0]["matrix_safe_to_solve_physically"] is True
    assert pump[0]["type50_photoexcitation_status"] == "evaluated_xstar_ucalc_type50_with_explicit_epi_bremsa_grid"


def test_type50_line_escape_and_pumping_respects_cfrac_one_zero_pumping():
    transitions = [{
        "kind": "radiative_decay", "data_type": 50, "record": 123,
        "element": "O", "element_z": 8, "ion_stage": 7,
        "from_level": 7, "to_level": 1, "rate_s^-1": 3.0e12,
        "source_method": "data_type_50_rate_type_4", "depth_inward": 0.0, "depth_outward": 0.0,
    }]
    global_index = [
        {"global_index": 0, "element": "O", "element_z": 8, "ion_stage": 7, "level_index": 1, "energy_eV": 0.0, "stat_weight": 1.0, "level_label": "1s2 1S0", "level_kind": "spectroscopic"},
        {"global_index": 6, "element": "O", "element_z": 8, "ion_stage": 7, "level_index": 7, "energy_eV": 574.0, "stat_weight": 3.0, "level_label": "1s2p 1P1", "level_kind": "spectroscopic"},
    ]
    rows = build_global_bound_bound_matrix_terms(
        transitions, global_index,
        type50_bound_bound_treatment="xstar-line-escape-and-pumping",
        type50_cfrac=1.0,
        radiation_field_mode="xstar-powerlaw",
        radiation_bremsa_scale=1.0e18,
        temperature_K=8.0e4,
    )
    pump = [r for r in rows if r.get("matrix_role") == "type50_photoexcitation_gain_to_upper_proxy"]
    assert pump == []
    bb = [r for r in rows if r.get("matrix_role") == "bound_bound_gain_to_destination"][0]
    assert bb["type50_photoexcitation_covering_multiplier"] == 0.0
