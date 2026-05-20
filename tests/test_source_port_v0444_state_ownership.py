from __future__ import annotations

import json

import pytest

from xstar_atomic.benchmarks import complete_fixed_state_v0443_state_ownership_path


def test_v0444_physical_call73_state_ownership_target_closes_pre_continuum_gate():
    root = complete_fixed_state_v0443_state_ownership_path()
    target = json.loads((root / "correction_target.json").read_text())

    pre = target["pre_continuum"]["python"]
    xstar = target["pre_continuum"]["xstar"]
    final = target["final"]["python"]
    components = target["continuum_components"]
    rtol = target["rtol"]

    for name in ("httot", "cltot", "httot2", "cltot2"):
        assert pre[name] == pytest.approx(xstar[name], rel=rtol, abs=1.0e-12)

    heating = components["htcomp"] + components["htfreef"]
    cooling = components["clcomp"] + components["clbrems"]
    assert final["httot"] - pre["httot"] == pytest.approx(heating, rel=2.0e-14)
    assert final["cltot"] - pre["cltot"] == pytest.approx(cooling, rel=2.0e-14)
    assert final["httot2"] - pre["httot2"] == pytest.approx(heating, rel=2.0e-14)
    assert final["cltot2"] - pre["cltot2"] == pytest.approx(cooling, rel=2.0e-14)

    assert target["expected_acceptance"]["current_all_element_pre_continuum_parity"]
    assert target["expected_acceptance"]["v0444_complete_fixed_state_acceptance_ready"]
