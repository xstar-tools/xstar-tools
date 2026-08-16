from __future__ import annotations

from pathlib import Path

from xstar_tools.xstar.compiled_case import compiled_case_status
from xstar_tools.xstar.native_fixed_program import validate_program_directory

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "src/xstar_tools/benchmarks"
FIXTURES = ROOT / "tests/fixtures/historical"


def test_active_benchmark_package_is_minimal() -> None:
    assert sorted(p.name for p in BENCH.iterdir() if p.is_dir()) == [
        "v06486_qualification_reference_v0472",
        "v0648724_call1_thermal_leaf_reference",
    ]
    assert sorted(
        p.name
        for p in (BENCH / "v06486_qualification_reference_v0472").iterdir()
        if p.is_file()
    ) == ["reference_radiation_v0472_full.csv", "trajectory.csv"]
    for obsolete in ("acceptance.py", "matrix.py", "smoke.py"):
        assert not (BENCH / obsolete).exists()


def test_relocated_fixed_program_fixture_is_valid() -> None:
    program = FIXTURES / "v06485_active_family_phase2_fixture"
    validation = validate_program_directory(program)
    assert validation.program_id == "v06485_active_family_phase2_fixture"
    assert validation.records == 27


def test_deprecated_compiled_case_is_not_bundled() -> None:
    assert not (BENCH / "v0648_compiled_case_helike_type69_mg11_ne1e8").exists()
    status = compiled_case_status()
    assert status["available"] is False


def test_package_data_excludes_retired_benchmark_archaeology() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package_data = pyproject.split('[tool.setuptools.package-data]', 1)[1]
    assert "v06486_qualification_reference_v0472/reference_radiation_v0472_full.csv" in package_data
    assert "v06486_qualification_reference_v0472/trajectory.csv" in package_data
    assert "v0648724_call1_thermal_leaf_reference/*" in package_data
    assert "v0648_compiled_case_helike_type69_mg11_ne1e8" not in package_data
    assert "oxygen_call73_v0434_acceptance" not in package_data
