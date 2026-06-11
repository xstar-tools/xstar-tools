from __future__ import annotations

import csv
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
FIXTURE = ROOT / "src/xstar_tools/benchmarks/v06485_active_family_phase2_fixture"


def _run(program: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CPP / "xstar_cpp"), "fixed-state-self-test", "--case-dir", str(program)],
        cwd=CPP,
        text=True,
        capture_output=True,
        check=False,
    )


def test_elements_loader_accepts_trailing_abundance(tmp_path: Path) -> None:
    if not (CPP / "xstar_cpp").exists():
        pytest.skip("native executable has not been built")
    target = tmp_path / "trailing_abundance"
    shutil.copytree(FIXTURE, target)
    rows = list(csv.DictReader((target / "elements.csv").open()))
    fieldnames = [name for name in rows[0] if name != "abundance"] + ["abundance"]
    with (target / "elements.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    completed = _run(target)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "program_record_count=27" in completed.stdout
    assert "RESULT=ACCEPT" in completed.stdout


def test_elements_loader_rejects_missing_named_field(tmp_path: Path) -> None:
    if not (CPP / "xstar_cpp").exists():
        pytest.skip("native executable has not been built")
    target = tmp_path / "missing_record_count"
    shutil.copytree(FIXTURE, target)
    rows = list(csv.DictReader((target / "elements.csv").open()))
    fieldnames = [name for name in rows[0] if name != "record_count"]
    with (target / "elements.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    completed = _run(target)
    assert completed.returncode != 0
    assert "missing elements.csv column: record_count" in completed.stderr
