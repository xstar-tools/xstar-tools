from __future__ import annotations

import json
from pathlib import Path

from xstar_atomic.source_port_dsec_causality_cli import (
    _clean_passthrough,
    _write_products,
)


def test_causality_passthrough_strips_owned_options() -> None:
    args = [
        "--atdb", "atdb.fits",
        "--out-dir", "old",
        "--maximum-evaluations", "9",
        "--global-writeback-mode=dense-source",
        "--leveltemp-lifecycle", "carry",
        "--print-summary",
        "--progress",
    ]
    cleaned = _clean_passthrough(args)
    assert cleaned == ["--atdb", "atdb.fits", "--progress"]


def test_causality_products_identify_production_mode(tmp_path: Path) -> None:
    base = {
        "label": "mode",
        "global_writeback_mode": "legacy-selected",
        "leveltemp_lifecycle": "carry",
        "exit_code": 2,
        "trajectory_parity_ready": False,
        "thermal_parity_ready": False,
        "transition_state_ready": False,
        "python_httot_pre_continuum": 1.0,
        "xstar_httot_pre_continuum": 1.0,
        "httot_pre_continuum_absolute_difference": 0.0,
        "httot_pre_continuum_relative_difference": 0.0,
        "python_cltot_pre_continuum": 2.0,
        "xstar_cltot_pre_continuum": 2.0,
        "cltot_pre_continuum_absolute_difference": 0.0,
        "cltot_pre_continuum_relative_difference": 0.0,
        "python_httot2_pre_continuum": 3.0,
        "xstar_httot2_pre_continuum": 3.0,
        "httot2_pre_continuum_absolute_difference": 0.0,
        "httot2_pre_continuum_relative_difference": 0.0,
        "python_cltot2_pre_continuum": 4.0,
        "xstar_cltot2_pre_continuum": 4.0,
        "cltot2_pre_continuum_absolute_difference": 0.0,
        "cltot2_pre_continuum_relative_difference": 0.0,
        "python_hmctot": -0.5,
        "xstar_hmctot": -0.5,
        "hmctot_absolute_difference": 0.0,
        "hmctot_relative_difference": 0.0,
        "python_elcter": 0.0,
        "xstar_elcter": 0.0,
        "elcter_absolute_difference": 0.0,
        "elcter_relative_difference": 0.0,
    }
    a = {"mode_id": "A_current_v0451", **base}
    d = {
        "mode_id": "D_production_both",
        **base,
        "global_writeback_mode": "dense-source",
        "leveltemp_lifecycle": "reset-per-call",
        "thermal_parity_ready": True,
        "transition_state_ready": True,
        "exit_code": 0,
    }
    products = _write_products(tmp_path, [a, d])
    summary = json.loads(products["json"].read_text(encoding="utf-8"))
    assert summary["port_version"] == "v0.4.52"
    assert summary["production_mode_completed"]
    assert summary["production_transition_state_ready"]
    assert summary["production_thermal_parity_ready"]


def test_physical_parser_defaults_to_both_production_corrections() -> None:
    from xstar_atomic.source_port_dsec_physical_cli import build_parser

    args = build_parser().parse_args(
        [
            "--atdb", "atdb.fits",
            "--xstar-dsec-trajectory", "trajectory.csv",
            "--oxygen-call73-regression-dir", "frozen",
            "--out-dir", "out",
        ]
    )
    assert args.global_writeback_mode == "dense-source"
    assert args.leveltemp_lifecycle == "reset-per-call"
