from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from astropy.io import fits
import numpy as np

from xstar_tools.xstar.qualification import compare_directories


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests/fixtures/historical/v06486_qualification_reference_v0472"


def mutate_first_float_cell(path: Path) -> tuple[int, str, tuple[int, ...]]:
    patch: tuple[int, str, int, bytes] | None = None
    with fits.open(path, memmap=False) as hdul:
        for hdu_index, hdu in enumerate(hdul):
            data = hdu.data
            if data is None or not getattr(data.dtype, "names", None):
                continue
            for name in data.dtype.names or ():
                values = np.asarray(data[name])
                if values.size and values.dtype.kind == "f":
                    original = values.flat[0]
                    toward = np.asarray(np.inf, dtype=values.dtype)
                    replacement = np.nextafter(original, toward)
                    if float(replacement) == float(original):
                        replacement = values.dtype.type(
                            float(original) + max(abs(float(original)), 1.0) * 1.0e-6
                        )
                    field_offset = data.dtype.fields[name][1]
                    byte_offset = int(hdu._data_offset) + int(field_offset)
                    replacement_bytes = np.asarray(replacement, dtype=values.dtype).tobytes()
                    patch = (hdu_index, name, byte_offset, replacement_bytes)
                    break
            if patch is not None:
                break
    if patch is None:
        raise AssertionError("no floating FITS cell found")
    with path.open("r+b") as handle:
        handle.seek(patch[2])
        handle.write(patch[3])
    return patch[0], patch[1], (0,)


def test_ieee_fits_comparison_handles_noncontiguous_fields_and_finds_one_cell(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    shutil.copytree(REFERENCE, candidate)
    hdu_index, field, index = mutate_first_float_cell(candidate / "xout_cont1.fits")

    result = compare_directories(REFERENCE, candidate, mode="ieee", profile="science-products")

    assert result["result"] == "REJECT"
    assert Path(result["reference_directory"]).is_absolute()
    assert Path(result["candidate_directory"]).is_absolute()
    assert any(
        difference["category"] == "fits_value"
        and f"HDU {hdu_index}, field {field}, index {index}" in difference["location"]
        for difference in result["differences"]
    )


def test_cli_removes_stale_json_when_comparison_raises(tmp_path: Path) -> None:
    stale = tmp_path / "stale.json"
    stale.write_text('{"result":"STALE"}\n', encoding="utf-8")
    missing = tmp_path / "missing-candidate"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "xstar_tools.xstar.qualification",
            "compare",
            str(REFERENCE),
            str(missing),
            "--mode",
            "ieee",
            "--output-json",
            str(stale),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    assert completed.returncode != 0
    assert not stale.exists()


def test_cli_resolves_report_and_directory_paths_to_absolute(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    shutil.copytree(REFERENCE, candidate)
    report = tmp_path / "nested" / "report.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "xstar_tools.xstar.qualification",
            "compare",
            os.path.relpath(REFERENCE, ROOT),
            os.path.relpath(candidate, ROOT),
            "--mode",
            "ieee",
            "--profile",
            "science-products",
            "--output-json",
            os.path.relpath(report, ROOT),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert Path(payload["reference_directory"]).is_absolute()
    assert Path(payload["candidate_directory"]).is_absolute()
    assert report.resolve().is_file()
    assert payload["output_json"] == str(report.resolve())
    assert payload["result"] == "ACCEPT"
