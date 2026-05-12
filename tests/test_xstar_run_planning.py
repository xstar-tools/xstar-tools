from pathlib import Path

import xstar_atomic as xa
from xstar_atomic.xstar_run import parse_xstar_command

from xstar_atomic.xstar_state import (
    create_initial_xstar_run_state_from_input,
    required_live_state_fields,
    write_xstar_state_skeleton,
)


def test_required_live_state_fields_include_user_requested_arrays():
    names = {row["name"] for row in required_live_state_fields()}
    for name in [
        "epi(:)",
        "bremsa(:)",
        "bremsint(:)",
        "tau0(1:2,line)",
        "tauc/dpthc(1:2,continuum)",
        "cfrac",
        "vturbi",
        "temperature/electron density per zone",
        "ion fractions per zone",
        "level populations per zone",
    ]:
        assert name in names


def test_create_initial_xstar_run_state_seeds_zone_scalars(tmp_path: Path):
    params = parse_xstar_command("xstar nsteps=3 temperature=100 density=1 rlogxi=1.5 cfrac=1.0 vturbi=100")
    state = create_initial_xstar_run_state_from_input(params)
    assert len(state.zones) == 3
    assert state.zones[0].temperature == 100
    assert state.zones[0].electron_density == 1
    assert state.zones[0].cfrac == 1.0
    assert state.zones[0].vturbi == 100
    assert "continuum.epi" in state.zones[0].missing_core_fields()
    paths = write_xstar_state_skeleton(state, tmp_path)
    assert Path(paths["json"]).exists()
    assert "bremsint(:)" in Path(paths["markdown"]).read_text()


def test_xstar_recreation_plan_includes_live_state_schema():
    params = parse_xstar_command("xstar nsteps=1 density=1")
    plan = xa.xstar_recreation_plan(params)
    assert any(row["name"] == "level populations per zone" for row in plan["live_state_schema"])
