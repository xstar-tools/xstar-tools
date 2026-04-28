from pathlib import Path


def test_solver_exposes_collision_record_direction_scale_option():
    text = (Path(__file__).resolve().parents[1] / "src" / "xstar_atomic" / "solver.py").read_text()
    assert "--collision-record-direction-scale" in text
    assert "parse_record_direction_scale_specs" in text
    assert "collision_excitation_direction_scale_applied" in text
    assert "collision_deexcitation_direction_scale_applied" in text


def test_solver_exposes_type69_ground_excitation_mode():
    text = (Path(__file__).resolve().parents[1] / "src" / "xstar_atomic" / "solver.py").read_text()
    assert "--collision-type69-ground-excitation-mode" in text
    assert "suppress-resonance" in text
    assert "is_type69_ground_resonance_excitation_row" in text


def test_type69_ground_resonance_row_helper_is_present_in_source():
    text = (Path(__file__).resolve().parents[1] / "src" / "xstar_atomic" / "solver.py").read_text()
    assert "lower != 1" in text
    assert "upper == 7" in text
    assert "data_type" in text and "!= 69" in text
