from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess

from xstar_tools.xstar.native_fixed_program import (
    ACTIVE_LOWERER_DATA_TYPES,
    PROGRAM_ABI,
    _coverage_from_counts,
    validate_program_directory,
)

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
PROGRAM = ROOT / "src/xstar_tools/benchmarks/v06485_active_family_phase2_fixture"
TRAJECTORY = ROOT / "src/xstar_tools/benchmarks/v0648_compiled_case_helike_type69_mg11_ne1e8/trajectory.csv"
PHASE2_TYPES = {1, 2, 9, 30, 38, 39, 60, 62, 68, 72, 73, 76, 95}
ALL_ACTIVE_TYPES = {49, 50, 51, 53, 54, 56, 57, 63, 69, 71, 74, 77, 86, 88, 99} | PHASE2_TYPES


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CPP / "xstar_cpp"), *args],
        cwd=CPP,
        text=True,
        capture_output=True,
        check=False,
    )


def test_host_inventory_is_strictly_complete_but_not_production_promoted() -> None:
    counts = {
        (13, 6): 700,
        (3, 1): 1, (3, 2): 6, (3, 9): 3, (3, 30): 3,
        (3, 38): 10, (3, 39): 10, (3, 49): 809, (4, 50): 2888,
        (3, 51): 1191, (3, 53): 1039, (3, 54): 121, (3, 56): 646,
        (3, 57): 473, (3, 60): 19, (3, 62): 4, (3, 63): 740,
        (3, 68): 12, (3, 69): 12, (4, 71): 195, (3, 72): 6,
        (3, 73): 39, (3, 74): 90, (3, 76): 9, (3, 77): 185,
        (1, 86): 140, (3, 88): 24, (3, 95): 30, (1, 99): 17,
    }
    result = _coverage_from_counts(counts, (1, 2, 12))
    assert result["records_scanned"] == 9422
    assert result["category_counts"] == {"native_executable": 8722, "topology_metadata": 700}
    assert result["recognized_but_not_active_lowered_counts"] == {}
    assert result["unsupported_physics_counts"] == {}
    assert result["active_record_completion_ready"] is True
    assert result["production_promotion_ready"] is False
    assert ALL_ACTIVE_TYPES <= ACTIVE_LOWERER_DATA_TYPES


def test_phase2_fixture_uses_current_abi_and_every_remaining_family() -> None:
    validation = validate_program_directory(PROGRAM)
    assert PROGRAM_ABI == 60485
    assert validation.program_id == "v06485_active_family_phase2_fixture"
    assert validation.records == 27
    assert PHASE2_TYPES <= set(validation.opcodes)


def test_phase2_native_single_and_batch_are_callback_free() -> None:
    single = run("fixed-state-self-test", "--case-dir", str(PROGRAM))
    assert single.returncode == 0, single.stdout + single.stderr
    assert "program_record_count=27" in single.stdout
    assert "records_evaluated=54" in single.stdout
    assert "visited_data_types=27" in single.stdout
    assert "python_callbacks=0" in single.stdout
    batch = run("fixed-state-batch-self-test", "--case-dir", str(PROGRAM), "--batch", "64")
    assert batch.returncode == 0, batch.stdout + batch.stderr
    assert "records_evaluated=1728" in batch.stdout
    assert "python_callbacks=0" in batch.stdout


def test_reference_input_trajectory_uses_charge_residual_semantics(tmp_path: Path) -> None:
    completed = run(
        "run-fixed-trajectory", "--case-dir", str(PROGRAM),
        "--trajectory-csv", str(TRAJECTORY), "--output-dir", str(tmp_path),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "trajectory_evaluations=61" in completed.stdout
    rows = list(csv.DictReader((tmp_path / "native_trajectory.csv").open()))
    assert len(rows) == 61
    first = rows[0]
    calculated = float(first["electron_fraction_input"]) - float(first["native_electron_fraction"])
    assert abs(calculated - float(first["native_charge_residual"])) < 1.0e-15
    summary = json.loads((tmp_path / "native_trajectory_summary.json").read_text())
    assert summary["evaluations"] == 61
    assert summary["python_callbacks"] == 0
    assert "max_abs_charge_residual_delta_to_reference" in summary


def test_native_dsec_controller_runs_57_plus_four_evaluations(tmp_path: Path) -> None:
    completed = run(
        "run-fixed-dsec", "--case-dir", str(PROGRAM),
        "--trajectory-csv", str(TRAJECTORY), "--output-dir", str(tmp_path),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "dsec_evaluations=57" in completed.stdout
    assert "final_evaluations=4" in completed.stdout
    assert "total_evaluations=61" in completed.stdout
    assert "python_callbacks=0" in completed.stdout
    assert "reference_state_identity=false" in completed.stdout
    summary = json.loads((tmp_path / "native_dsec_summary.json").read_text())
    assert summary["trajectory_mode"] == "native_dsec_controller"
    assert summary["dsec_evaluations"] == 57
    assert summary["total_evaluations"] == 61
    assert summary["production_promotion_ready"] is False
    assert summary["historical_fits_generated"] == 9
    assert summary["historical_fits_schema_complete"] is True
    assert summary["historical_fits_computed_from_native_state"] is True
    assert summary["continuum_and_spectrum_paths_separate"] is True
    assert summary["historical_fits_physical_equivalence_qualified"] is False
    assert (tmp_path / "xout_cont1.fits").read_bytes() != (tmp_path / "xout_spect1.fits").read_bytes()
    rows = list(csv.DictReader((tmp_path / "native_dsec_trajectory.csv").open()))
    assert len(rows) == 61
    assert sum(row["kind"] == "dsec" for row in rows) == 57
    assert sum(row["kind"] == "final" for row in rows) == 4

    import pytest
    fits = pytest.importorskip("astropy.io.fits")
    reference_dir = TRAJECTORY.parent / "science"
    names = sorted(path.name for path in reference_dir.glob("*.fits"))
    assert len(names) == 9
    for name in names:
        with fits.open(reference_dir / name) as reference, fits.open(tmp_path / name) as generated:
            assert [hdu.name for hdu in generated] == [hdu.name for hdu in reference]
            for expected_hdu, actual_hdu in zip(reference, generated):
                expected_rows = None if expected_hdu.data is None else len(expected_hdu.data)
                actual_rows = None if actual_hdu.data is None else len(actual_hdu.data)
                assert actual_rows == expected_rows
                expected_columns = [] if not hasattr(expected_hdu, "columns") else list(zip(expected_hdu.columns.names, expected_hdu.columns.formats))
                actual_columns = [] if not hasattr(actual_hdu, "columns") else list(zip(actual_hdu.columns.names, actual_hdu.columns.formats))
                assert actual_columns == expected_columns
            assert generated[0].header["COMPUTED"] is True
            assert generated[0].header["REPLAY"] is False
            assert generated[0].header["QUALSTAT"] == "DEVELOPMENT"
            if name == "xout_cont1.fits":
                assert generated[0].header["PRODUCT"] == "CONTINUUM"
                assert generated[0].header["SPECMODE"] == "FREE_FREE_NATIVE"
            if name == "xout_spect1.fits":
                assert generated[0].header["PRODUCT"] == "FULL_SPECTRUM"
                assert generated[0].header["SPECMODE"] == "CONTINUUM_PLUS_PROFILE"


def test_python_bridge_reports_current_version() -> None:
    completed = subprocess.run(
        [str(CPP / "xstar_cpp"), "python-bridge-test", "--plugin-dir", ".", "--python-path", "../../.."],
        cwd=CPP,
        text=True,
        capture_output=True,
        check=False,
        env={**__import__("os").environ, "PYTHONPATH": "../../.."},
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert '"version": "0.6.48.5.1"' in completed.stdout
