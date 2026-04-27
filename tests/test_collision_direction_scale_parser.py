from pathlib import Path


def test_solver_exposes_collision_record_direction_scale_option():
    text = (Path(__file__).resolve().parents[1] / "src" / "xstar_atomic" / "solver.py").read_text()
    assert "--collision-record-direction-scale" in text
    assert "parse_record_direction_scale_specs" in text
    assert "collision_excitation_direction_scale_applied" in text
    assert "collision_deexcitation_direction_scale_applied" in text
