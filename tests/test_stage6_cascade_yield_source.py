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


def test_cascade_target_preset_resolution():
    from xstar_atomic.recombination import parse_level_weight_map, resolve_cascade_target_levels

    text = resolve_cascade_target_levels("", "o7-triplet-fdown-rkeep")
    assert text == "2:0.5,3:1.0,4:1.0,5:1.0,7:1.0"
    weights = parse_level_weight_map(text)
    assert weights[2] == 0.5
    assert weights[3] == 1.0
    assert weights[7] == 1.0
    assert resolve_cascade_target_levels("2:1.0", "o7-triplet-fdown-rkeep") == "2:1.0"


    text090 = resolve_cascade_target_levels("", "o7-triplet-fdown090-rkeep")
    text085 = resolve_cascade_target_levels("", "o7-triplet-fdown085-rkeep")
    text075 = resolve_cascade_target_levels("", "o7-triplet-fdown075-rkeep")
    assert parse_level_weight_map(text090)[2] == 0.90
    assert parse_level_weight_map(text085)[2] == 0.85
    assert parse_level_weight_map(text075)[2] == 0.75
    assert parse_level_weight_map(text090)[7] == 1.0
    assert parse_level_weight_map(text085)[7] == 1.0
    assert parse_level_weight_map(text075)[7] == 1.0

    equal_text = resolve_cascade_target_levels("", "o7-triplet-equal")
    assert equal_text == "2:1.0,3:1.0,4:1.0,5:1.0,7:1.0"

    # New Stage-6 shift presets preserve the resonance target and approximately
    # preserve total target weight by moving source weight from forbidden to
    # intercombination levels.
    f2i010 = parse_level_weight_map(resolve_cascade_target_levels("", "o7-triplet-f2i010-rkeep"))
    f2i025 = parse_level_weight_map(resolve_cascade_target_levels("", "o7-triplet-f2i025-rkeep"))
    assert f2i010[2] == 0.90
    assert abs(f2i010[3] - 1.0333333333) < 1e-10
    assert f2i010[7] == 1.0
    assert abs(sum(f2i010.values()) - 5.0) < 1e-8
    assert f2i025[2] == 0.75
    assert abs(f2i025[3] - 1.0833333333) < 1e-10
    assert f2i025[7] == 1.0
    assert abs(sum(f2i025.values()) - 5.0) < 1e-8

    # Backward-compatible alias now points to the preferred forbidden-to-
    # intercombination shift experiment, not the old resonance-downweighted map.
    assert resolve_cascade_target_levels("", "o7-triplet-xstar-tuned") == resolve_cascade_target_levels("", "o7-triplet-f2i025-rkeep")
