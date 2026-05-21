from __future__ import annotations

import json
from pathlib import Path

from xstar_atomic.source_port_dsec_transition_replay_cli import (
    _clean_passthrough,
    _element_comparison,
    _write_products,
)


def test_exact_replay_passthrough_strips_owned_options() -> None:
    args = [
        "--atdb", "atdb.fits",
        "--out-dir", "old",
        "--maximum-evaluations", "9",
        "--global-writeback-mode=dense-source",
        "--leveltemp-lifecycle", "carry",
        "--transition-input-mode", "compare-only",
        "--print-summary",
        "--progress",
    ]
    assert _clean_passthrough(args) == ["--atdb", "atdb.fits", "--progress"]


def test_element_comparison_orders_largest_cooling_change_first() -> None:
    base = {
        "abundance": "1",
        "selected_min_ion_stage": "1",
        "selected_max_ion_stage": "2",
        "basis_size": "3",
        "n_superlevels": "2",
        "solver_converged": "True",
        "solver_method": "leqt2f",
        "outer_iterations": "1",
        "fixed_point_iterations": "2",
        "used_dense_fallback": "False",
        "heating_per_abundance": "1",
        "cooling_per_abundance": "2",
        "heating2_per_abundance": "3",
        "cooling2_per_abundance": "4",
        "heating": "1",
        "cooling": "2",
        "heating2": "3",
        "cooling2": "4",
        "electron_contribution": "5",
    }
    current = {1: dict(base), 8: dict(base, cooling="10")}
    replay = {1: dict(base, cooling="2.5"), 8: dict(base, cooling="7")}
    rows = _element_comparison(current, replay)
    assert [row["element_z"] for row in rows] == [8, 1]
    assert rows[0]["cooling_absolute_change"] == 3.0


def test_replay_products_classify_exact_seed_result(tmp_path: Path) -> None:
    common = {
        "label": "mode",
        "transition_input_mode": "compare-only",
        "exit_code": 2,
        "trajectory_parity_ready": False,
        "thermal_parity_ready": False,
        "transition_state_ready": False,
    }
    for name, value in (
        ("httot_pre_continuum", 1.0),
        ("cltot_pre_continuum", 2.0),
        ("httot2_pre_continuum", 3.0),
        ("cltot2_pre_continuum", 4.0),
        ("hmctot", -0.5),
        ("elcter", 0.0),
    ):
        common[f"python_{name}"] = value
        common[f"xstar_{name}"] = value
        common[f"{name}_absolute_difference"] = 0.0
        common[f"{name}_relative_difference"] = 0.0
        common[f"{name}_within_tolerance"] = True
    p = {"mode_id": "P_python_transition", **common}
    x = {
        "mode_id": "X_xstar_seeded_transition",
        **common,
        "transition_input_mode": "replay-exact",
        "transition_state_ready": True,
        "thermal_parity_ready": True,
        "exit_code": 0,
    }
    products = _write_products(tmp_path, [p, x], [])
    summary = json.loads(products["json"].read_text(encoding="utf-8"))
    assert summary["port_version"] == "v0.4.53"
    assert summary["exact_seed_primary_thermal_ready"]
    assert summary["diagnostic_conclusion"] == "evaluation_1_population_solution_or_writeback"
