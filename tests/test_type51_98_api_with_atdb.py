"""API-level real-ATDB tests for collision data types 51 and 98.

These tests use representative targets discovered by the validation inventory in
``tests/data/collision_type51_98_targets.csv``. They are skipped unless
``XSTAR_ATDB_FITS`` points to a local XSTAR ``atdb.fits`` file.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest


def _atdb_path() -> Path:
    path = os.environ.get("XSTAR_ATDB_FITS")
    if not path:
        pytest.skip("Set XSTAR_ATDB_FITS=/path/to/atdb.fits to run real-ATDB API tests")
    p = Path(path)
    if not p.exists():
        pytest.skip(f"XSTAR_ATDB_FITS does not exist: {p}")
    return p


def _target_rows() -> list[dict]:
    csv_path = Path(__file__).parent / "data" / "collision_type51_98_targets.csv"
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        for key in (
            "ion_stage",
            "data_type",
            "n_records",
            "n_evaluated_rows",
            "n_positive_rate_rows",
            "first_record",
            "first_lower_level",
            "first_upper_level",
        ):
            row[key] = int(row[key])
        for key in (
            "first_wavelength_A",
            "first_temperature_K",
            "first_q_excitation_cm3_s",
            "first_q_deexcitation_cm3_s",
        ):
            row[key] = float(row[key])
    return rows


def _representative_target(data_type: int) -> dict:
    rows = [r for r in _target_rows() if r["data_type"] == data_type]
    if not rows:
        pytest.skip(f"No data_type={data_type} target row stored")
    # Prefer a target with many positive rates for type 51 and the discovered
    # Ne IX target for type 98. Sorting makes the choice deterministic.
    rows.sort(key=lambda r: (r["n_positive_rate_rows"], r["n_records"]), reverse=True)
    return rows[0]


@pytest.mark.parametrize("data_type,expected_method", [
    (51, "BT_5pt_upsil_type51"),
    (98, "BT_general_upsiln_type98"),
])
def test_high_level_api_collisions_type51_type98_targets(data_type, expected_method):
    fitsfile = _atdb_path()
    from xstar_atomic import XSTARAtomic

    target = _representative_target(data_type)
    db = XSTARAtomic(fitsfile)
    result = db.collisions(
        target["ion"],
        data_type=data_type,
        lower_level=target["first_lower_level"],
        upper_level=target["first_upper_level"],
        temperatures=[target["first_temperature_K"], 3.0e6, 1.0e7],
    )

    matches = result["matches"]
    evaluated = result["evaluated_rates"]
    assert matches, f"No API collision summary rows for target {target}"
    assert evaluated, f"No API collision evaluation rows for target {target}"

    first_match = matches[0]
    assert int(first_match["data_type"]) == data_type
    assert int(first_match["lower_level"]) == target["first_lower_level"]
    assert int(first_match["upper_level"]) == target["first_upper_level"]
    assert abs(float(first_match["wavelength_from_levels_A"]) - target["first_wavelength_A"]) < 1.0e-6

    first_eval = next(
        row for row in evaluated
        if abs(float(row["temperature_K"]) - target["first_temperature_K"]) / target["first_temperature_K"] < 1.0e-12
    )
    assert first_eval["eval_method"] == expected_method
    assert float(first_eval["q_excitation_cm3_s"]) > 0.0
    assert float(first_eval["q_deexcitation_cm3_s"]) > 0.0

    # Regression against the validation inventory that selected this target.
    # These are deliberately loose, but catch accidental changes in BT decoding.
    assert float(first_eval["q_excitation_cm3_s"]) == pytest.approx(
        target["first_q_excitation_cm3_s"], rel=1.0e-10
    )
    assert float(first_eval["q_deexcitation_cm3_s"]) == pytest.approx(
        target["first_q_deexcitation_cm3_s"], rel=1.0e-10
    )


def test_high_level_api_type98_accepts_ion_alias():
    """Ensure the type-98 Ne IX target is accessible through flexible ion names."""
    fitsfile = _atdb_path()
    from xstar_atomic import XSTARAtomic

    target = _representative_target(98)
    db = XSTARAtomic(fitsfile)
    result = db.collisions(
        "ne_ix",
        data_type=98,
        lower_level=target["first_lower_level"],
        upper_level=target["first_upper_level"],
        temperatures=[1.0e6],
    )
    assert result["matches"]
    assert result["evaluated_rates"]
    assert result["evaluated_rates"][0]["eval_method"] == "BT_general_upsiln_type98"
