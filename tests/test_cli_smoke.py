"""CLI smoke tests for xstar-atomic modules.

Skipped unless XSTAR_ATDB_FITS points to atdb.fits. These use ``python -m`` so they
work from the source tree without installing console scripts.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _atdb_path() -> Path | None:
    raw = os.environ.get("XSTAR_ATDB_FITS")
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.exists():
        return None
    return path


ATDB_PATH = _atdb_path()
needs_atdb = pytest.mark.skipif(
    ATDB_PATH is None,
    reason="set XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits to run CLI smoke tests",
)


def _run_json(module: str, *args: str):
    cmd = [sys.executable, "-m", module, str(ATDB_PATH), *args]
    proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return json.loads(proc.stdout)


@needs_atdb
def test_lines_cli_o8_lya():
    data = _run_json(
        "xstar_atomic.lines",
        "--element", "O",
        "--ion-stage", "8",
        "--line-search",
        "--wavelength-min", "18.8",
        "--wavelength-max", "19.1",
    )
    assert data["n_matches"] == 2


@needs_atdb
def test_recombination_cli_oxygen_summary():
    data = _run_json(
        "xstar_atomic.recombination",
        "--element", "O",
        "--temperatures", "1e6",
        "--summary",
    )
    assert data["n_recombination_like_records"] == 18
    assert data["n_evaluated_rows"] == 14
