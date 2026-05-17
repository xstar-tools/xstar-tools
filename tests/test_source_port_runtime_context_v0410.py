from __future__ import annotations

import csv
from pathlib import Path

import pytest

from xstar_atomic.source_port import load_xstar_runtime_context_reference
from xstar_atomic.source_port_element_cli import build_parser


def _write_probe(path: Path) -> None:
    fields = [
        "capture_index", "solve_call_id", "stage_capture_index", "stage",
        "ml_element", "element_z", "ipmat2", "nsp", "nionp", "nindbe",
        "nit", "nit2", "nit3", "level_index", "x_population", "nsup", "nion",
        "t_xstar_1e4K", "xee", "xpx", "cfrac",
    ]
    rows = []
    for capture, stage in ((437, "before_msolvelucy"), (438, "after_msolvelucy")):
        for index in (1, 2):
            rows.append({
                "capture_index": capture,
                "solve_call_id": 219,
                "stage_capture_index": capture,
                "stage": stage,
                "ml_element": 14550,
                "element_z": 8,
                "ipmat2": 2,
                "nsp": 2,
                "nionp": 8,
                "nindbe": 4,
                "nit": 0 if stage.startswith("before") else 2,
                "nit2": 0,
                "nit3": 0,
                "level_index": index,
                "x_population": 0.5,
                "nsup": index,
                "nion": 7,
                "t_xstar_1e4K": 7.6655185577588316,
                "xee": 1.2046560563936872,
                "xpx": 1.0e8,
                "cfrac": 1.0,
            })
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_runtime_context_selected_from_population_probe(tmp_path: Path):
    probe = tmp_path / "population.csv"
    _write_probe(probe)
    ref = load_xstar_runtime_context_reference(
        probe,
        element_z=8,
        solve_call_id="219",
    )
    assert ref.solve_call_id == "219"
    assert ref.n_rows == 2
    assert ref.temperature_k == pytest.approx(7.6655185577588316e4)
    assert ref.hydrogen_density_cm3 == pytest.approx(1.0e8)
    assert ref.electron_fraction_xee == pytest.approx(1.2046560563936872)
    assert ref.electron_density_cm3 == pytest.approx(1.2046560563936872e8)
    assert ref.covering_fraction == pytest.approx(1.0)


def test_cli_defaults_to_using_population_probe_runtime():
    parser = build_parser()
    args = parser.parse_args([
        "--atdb", "atdb.fits",
        "--temperature-k", "1e6",
        "--hydrogen-density-cm3", "1e8",
        "--electron-fraction-xee", "1",
        "--out-dir", "out",
    ])
    assert args.population_probe_runtime_policy == "use"
    assert args.population_probe_runtime_relative_tolerance == pytest.approx(5.0e-8)
