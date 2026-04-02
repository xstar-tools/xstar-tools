import pytest

pytest.importorskip("astropy")

from xstar_atomic.recombination import allocation_levels, build_radiative_branching, parse_level_weight_map


def test_parse_level_weight_map():
    assert parse_level_weight_map("2,3:0.5;7") == {2: 1.0, 3: 0.5, 7: 1.0}


def test_selected_cascade_yield_prefers_levels_feeding_targets():
    levels = [
        {"level_index": 2, "statistical_weight_g": 3.0},
        {"level_index": 3, "statistical_weight_g": 1.0},
        {"level_index": 4, "statistical_weight_g": 5.0},
    ]
    lines = [
        {"upper_level": 4, "lower_level": 2, "A_s^-1": 9.0, "record": 1, "wavelength_A": 20.0},
        {"upper_level": 4, "lower_level": 3, "A_s^-1": 1.0, "record": 2, "wavelength_A": 21.0},
    ]
    branches, _ = build_radiative_branching(lines)
    alloc = allocation_levels(
        "selected-cascade-yield",
        [2, 3, 4],
        levels,
        {},
        branches_by_upper=branches,
        cascade_target_weights={2: 1.0},
        cascade_weight_floor=0.0,
    )
    weights = {lev: weight for lev, weight, _note in alloc}
    # Level 4 has a strong radiative path into target level 2; level 2 is itself
    # also a target.  Level 3 has no target yield and receives no source with a
    # zero floor.
    assert 2 in weights
    assert 4 in weights
    assert 3 not in weights
    assert weights[4] > weights[2]
