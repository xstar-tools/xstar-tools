from pathlib import Path

import xstar_atomic as xa
from xstar_atomic.benchmark import (
    XSTARLocalTarget,
    compare_solver_to_xstar_target,
    default_helike_benchmark_cases,
    default_helike_wavelength_window,
    read_cases_csv,
    write_default_helike_cases_csv,
    write_xstar_benchmark_outputs,
)


def test_default_helike_windows_include_benchmark_ions():
    assert default_helike_wavelength_window("C V") == (40.0, 42.0)
    assert default_helike_wavelength_window("O VII") == (21.0, 23.0)
    assert default_helike_wavelength_window("Mg XI") == (9.0, 9.4)
    assert default_helike_wavelength_window("Ca XIX") == (3.0, 3.35)


def test_benchmark_target_and_comparison_rows(tmp_path):
    ctx = xa.context_from_values(
        ion="O VII",
        temperature_K=7.66552e4,
        electron_density_cm3=1.20466e8,
        log_xi=1.5,
        ion_fraction=0.255926,
    )
    triplet = xa.calc_triplet(
        "O VII",
        rows=[
            {"upper_level": "1s1.2s1.3S_1", "emit_outward": 8.0},
            {"upper_level": "1s1.2p1.3P_1", "emit_outward": 1.5},
            {"upper_level": "1s1.2p1.1P_1", "emit_outward": 2.5},
        ],
    )
    target = XSTARLocalTarget(
        ion="O VII",
        run_dir="run",
        context=ctx,
        triplet=triplet,
        line_rows=triplet.lines,
        xout_abund_path="run/xout_abund1.fits",
        xout_lines_path="run/xout_lines1.fits",
        wavelength_window_A=(21.0, 23.0),
    )
    assert target.local_state_row()["temperature_K"] == 7.66552e4
    assert target.triplet_row()["xstar_r_fraction"] == 2.5 / 12.0
    comparison = compare_solver_to_xstar_target(
        target,
        solver_triplet={"f_fraction": 0.70, "i_fraction": 0.10, "r_fraction": 0.20},
    )
    row = comparison.comparison_row()
    assert row["comparison_status"] == "solver_compared"
    assert row["delta_r_solver_minus_xstar"] == 0.20 - 2.5 / 12.0
    paths = write_xstar_benchmark_outputs(comparison, tmp_path)
    for path in paths.values():
        assert Path(path).is_file()


def test_public_benchmark_symbols_are_exported():
    assert callable(xa.reproduce_xstar_run)
    assert callable(xa.build_xstar_local_target)
    assert hasattr(xa, "XSTARBenchmarkComparison")


def test_default_helike_standard_suite_cases(tmp_path):
    cases = default_helike_benchmark_cases("xstar_runs")
    assert [c["ion"] for c in cases] == ["C V", "O VII", "Mg XI", "Ca XIX"]
    assert cases[0]["run_dir"] == "xstar_runs/helike_type69/c5_ne1e8"
    assert cases[-1]["run_dir"] == "xstar_runs/helike_type69/ca19_xi3_ne1e8"

    csv_path = write_default_helike_cases_csv(tmp_path / "helike_reproduction_cases.csv", xstar_runs_root="xstar_runs")
    rows = read_cases_csv(csv_path)
    assert rows == cases


def test_missing_cases_csv_error_has_standard_suite_hint(tmp_path):
    missing = tmp_path / "missing_cases.csv"
    try:
        read_cases_csv(missing)
    except FileNotFoundError as exc:
        text = str(exc)
        assert "--standard-helike-suite" in text
        assert "helike_reproduction_cases.csv" in text
    else:  # pragma: no cover
        raise AssertionError("read_cases_csv should fail for a missing file")
