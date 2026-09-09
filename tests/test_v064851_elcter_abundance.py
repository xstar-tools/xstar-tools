from __future__ import annotations

import csv
from pathlib import Path
import shutil
import subprocess

import pytest

from xstar_tools.xstar.native_fixed_program import (
    QUALIFIED_XDEF_ABUNDANCES_BY_Z,
    _parse_abundance_spec,
    validate_program_directory,
)

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
FIXTURE = ROOT / "tests/fixtures/historical/v06485_active_family_phase2_fixture"


def _run_first_xee(program: Path) -> float:
    completed = subprocess.run(
        [str(CPP / "xstar_cpp"), "fixed-state-self-test", "--case-dir", str(program)],
        cwd=CPP,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    values = dict(
        line.split("=", 1)
        for line in completed.stdout.splitlines()
        if "=" in line
    )
    return float(values["first_computed_electron_fraction"])


def _copy_with_abundance_and_final_charge(
    tmp_path: Path, name: str, abundance: float, final_charge: int
) -> Path:
    target = tmp_path / name
    shutil.copytree(FIXTURE, target)
    elements = list(csv.DictReader((target / "elements.csv").open()))
    elements[0]["abundance"] = f"{abundance:.17g}"
    with (target / "elements.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(elements[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(elements)
    rows = list(csv.DictReader((target / "rows.csv").open()))
    rows[-1]["ion_charge"] = str(final_charge)
    with (target / "rows.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    validate_program_directory(target)
    return target




def test_elcter_scales_with_abundance_and_ignores_final_row_charge(tmp_path: Path) -> None:
    if not (CPP / "xstar_cpp").exists():
        pytest.skip("native executable has not been built")
    quarter_charge0 = _copy_with_abundance_and_final_charge(tmp_path, "quarter0", 0.25, 0)
    quarter_charge7 = _copy_with_abundance_and_final_charge(tmp_path, "quarter7", 0.25, 7)
    half_charge7 = _copy_with_abundance_and_final_charge(tmp_path, "half7", 0.5, 7)

    xee_quarter0 = _run_first_xee(quarter_charge0)
    xee_quarter7 = _run_first_xee(quarter_charge7)
    xee_half7 = _run_first_xee(half_charge7)

    # The normalization row represents the fully stripped stage, so its
    # serialized row charge must not affect electron accounting.
    assert xee_quarter0 == pytest.approx(xee_quarter7, rel=0.0, abs=1.0e-14)
    # Explicit elemental abundance must scale the full represented+bare charge.
    assert xee_half7 == pytest.approx(2.0 * xee_quarter7, rel=1.0e-13, abs=1.0e-14)
