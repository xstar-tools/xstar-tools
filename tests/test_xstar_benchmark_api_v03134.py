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


def test_solver_result_summary_he_like_triplet_is_extracted(tmp_path, monkeypatch):
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

    import xstar_atomic.benchmark as benchmark

    def fake_solve_populations(*args, **kwargs):
        return {
            "summary": {
                "he_like_triplet": {
                    "f_fraction": 0.70,
                    "i_fraction": 0.10,
                    "r_fraction": 0.20,
                    "R": 7.0,
                    "G": 4.0,
                }
            }
        }

    monkeypatch.setattr(benchmark, "solve_populations", fake_solve_populations)
    comparison = compare_solver_to_xstar_target(target, run_solver=True)
    row = comparison.comparison_row()
    assert row["comparison_status"] == "solver_compared"
    assert "quick_summary_not_full_xstar_validation_path" in row["comparison_warnings"]
    assert row["solver_f_fraction"] == 0.70
    assert row["solver_i_fraction"] == 0.10
    assert row["solver_r_fraction"] == 0.20


def test_solver_result_without_triplet_is_not_marked_compared(monkeypatch):
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

    import xstar_atomic.benchmark as benchmark

    def fake_solve_populations(*args, **kwargs):
        return {"summary": {"some_other_summary": {"ok": True}}}

    monkeypatch.setattr(benchmark, "solve_populations", fake_solve_populations)
    comparison = compare_solver_to_xstar_target(target, run_solver=True)
    row = comparison.comparison_row()
    assert row["comparison_status"] == "solver_no_triplet_values"
    assert "solver_returned_no_finite_triplet_fractions" in row["comparison_warnings"]
    assert row["solver_f_fraction"] is None


def test_run_solver_resolves_blank_fitsfile_from_environment(monkeypatch, tmp_path):
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

    import xstar_atomic.benchmark as benchmark

    fake_atdb = tmp_path / "atdb.fits"
    fake_atdb.write_bytes(b"SIMPLE  =                    T" + b" " * 2850)
    monkeypatch.setenv("XSTAR_ATDB", str(fake_atdb))

    seen = {}

    def fake_solve_populations(*args, **kwargs):
        seen["fitsfile"] = kwargs.get("fitsfile")
        return {"summary": {"he_like_triplet": {"f_fraction": 0.70, "i_fraction": 0.10, "r_fraction": 0.20}}}

    monkeypatch.setattr(benchmark, "solve_populations", fake_solve_populations)
    comparison = compare_solver_to_xstar_target(target, run_solver=True, fitsfile="")
    assert comparison.status == "solver_compared"
    assert seen["fitsfile"] is None


def test_benchmark_comparison_includes_R_G_L2_metrics():
    ctx = xa.context_from_values(ion="O VII", temperature_K=1.0e5, electron_density_cm3=1.0e8)
    triplet = xa.calc_triplet(
        "O VII",
        rows=[
            {"upper_level": "1s1.2s1.3S_1", "emit_outward": 8.0},
            {"upper_level": "1s1.2p1.3P_1", "emit_outward": 1.0},
            {"upper_level": "1s1.2p1.1P_1", "emit_outward": 1.0},
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
    comparison = compare_solver_to_xstar_target(
        target,
        solver_triplet={"f_fraction": 0.7, "i_fraction": 0.2, "r_fraction": 0.1},
    )
    row = comparison.comparison_row()
    assert row["xstar_R_f_over_i"] == 8.0
    assert row["xstar_G_f_plus_i_over_r"] == 9.0
    assert row["xstar_L2_to_xstar"] == 0.0
    assert abs(row["solver_R_f_over_i"] - 3.5) < 1e-12
    assert abs(row["solver_G_f_plus_i_over_r"] - 9.0) < 1e-12
    assert row["solver_L2_to_xstar"] is not None
    assert row["delta_R_solver_minus_xstar"] == -4.5


def test_full_global_triplet_is_preferred_over_quick_summary(monkeypatch):
    ctx = xa.context_from_values(ion="O VII", temperature_K=7.66552e4, electron_density_cm3=1.20466e8)
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

    import xstar_atomic.benchmark as benchmark

    def fake_solve_populations(*args, **kwargs):
        return {
            "summary": {"he_like_triplet": {"f_fraction": 0.01, "i_fraction": 0.01, "r_fraction": 0.98}},
            "full_global_normalized_solve_comparison": [
                {
                    "row_kind": "summary",
                    "comparison_case": "full_global_xstar_tau0_calc_emis_ion",
                    "f_fraction": 0.70,
                    "i_fraction": 0.10,
                    "r_fraction": 0.20,
                    "R": 7.0,
                    "G": 4.0,
                    "l2_distance_to_target": 0.123,
                }
            ],
        }

    monkeypatch.setattr(benchmark, "solve_populations", fake_solve_populations)
    comparison = compare_solver_to_xstar_target(target, run_solver=True)
    row = comparison.comparison_row()
    assert row["solver_f_fraction"] == 0.70
    assert row["solver_triplet_source"] == "full_global:full_global_xstar_tau0_calc_emis_ion"
    assert row["solver_l2_distance_to_target_reported"] == 0.123


def test_tau0_triplet_source_is_preferred_over_reference_depth(monkeypatch):
    ctx = xa.context_from_values(ion="O VII", temperature_K=7.66552e4, electron_density_cm3=1.20466e8)
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

    import xstar_atomic.benchmark as benchmark

    def fake_solve_populations(*args, **kwargs):
        return {
            "summary": {"he_like_triplet": {"f_fraction": 0.01, "i_fraction": 0.01, "r_fraction": 0.98}},
            "full_global_normalized_solve_comparison": [
                {
                    "row_kind": "summary",
                    "comparison_case": "full_global_xstar_reference_depth_emit_outward_calc_emis_ion",
                    "f_fraction": 0.90,
                    "i_fraction": 0.05,
                    "r_fraction": 0.05,
                    "R": 18.0,
                    "G": 19.0,
                },
                {
                    "row_kind": "summary",
                    "comparison_case": "full_global_xstar_tau0_calc_emis_ion",
                    "f_fraction": 0.70,
                    "i_fraction": 0.10,
                    "r_fraction": 0.20,
                    "R": 7.0,
                    "G": 4.0,
                },
            ],
        }

    monkeypatch.setattr(benchmark, "solve_populations", fake_solve_populations)
    comparison = compare_solver_to_xstar_target(target, run_solver=True, solver_preset="xstar-local-state")
    row = comparison.comparison_row()
    assert row["solver_f_fraction"] == 0.70
    assert row["solver_r_fraction"] == 0.20
    assert row["solver_triplet_source"] == "full_global:full_global_xstar_tau0_calc_emis_ion"


def test_solver_preset_local_state_passes_validation_kwargs(monkeypatch):
    ctx = xa.context_from_values(ion="O VII", temperature_K=7.66552e4, electron_density_cm3=1.20466e8)
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

    import xstar_atomic.benchmark as benchmark

    seen = {}

    def fake_solve_populations(*args, **kwargs):
        seen.update(kwargs)
        ref = kwargs.get("xstar_reference_lines_csv")
        if ref:
            ref_path = Path(ref)
            seen["reference_suffix"] = ref_path.suffix
            seen["reference_text"] = ref_path.read_text(encoding="utf-8")
        return {"summary": {"he_like_triplet": {"f_fraction": 0.70, "i_fraction": 0.10, "r_fraction": 0.20}}}

    monkeypatch.setattr(benchmark, "solve_populations", fake_solve_populations)
    compare_solver_to_xstar_target(target, run_solver=True, solver_preset="xstar-local-state")
    assert seen["full_global_linear_solver"] == "xstar-lucy"
    assert seen["full_global_topology"] == "xstar-continuum-alias-superlevels"
    assert seen["type50_bound_bound_treatment"] == "xstar-line-escape"
    assert seen["type50_escape_factor"] == 0.35
    assert seen["reference_suffix"] == ".csv"
    assert "emit_outward" in seen["reference_text"]
    assert not str(seen["xstar_reference_lines_csv"]).endswith(".fits")


def test_xstar_local_state_preset_does_not_use_output_depths_as_matrix_tau0():
    from xstar_atomic.benchmark import xstar_local_state_solver_kwargs

    kwargs = xstar_local_state_solver_kwargs(None)
    assert kwargs["type50_bound_bound_treatment"] == "xstar-line-escape"
    assert kwargs["type50_escape_source"] == "matrix-row"


def test_experimental_pumping_preset_is_explicitly_unsafe():
    from xstar_atomic.benchmark import solver_kwargs_from_preset

    kwargs = solver_kwargs_from_preset("xstar-local-state-experimental-pumping", None)
    assert kwargs["type50_bound_bound_treatment"] == "xstar-line-escape-and-pumping"
    assert kwargs["type50_escape_source"] == "unsafe-xout-lines-depths"


def test_type50_reference_depth_annotation_matches_reversed_levels():
    import pytest
    pytest.importorskip("astropy")
    from xstar_atomic.xstar_element_solver import _annotate_type50_transition_depths_from_reference

    transitions = [
        {
            "kind": "radiative_decay",
            "data_type": 50,
            "ion_stage": 7,
            "from_level": 7,
            "to_level": 1,
            "wavelength_A": 21.602,
            "rate_s^-1": 1.0,
        }
    ]
    refs = [
        {
            "ion_stage": 7,
            "lower_level": 1,
            "upper_level": 7,
            "wavelength_A": 21.602,
            "depth_inward": 6.89,
            "depth_outward": 0.0,
            "record": 123,
        }
    ]
    out = _annotate_type50_transition_depths_from_reference(transitions, refs)
    assert out[0]["depth_inward"] == 6.89
    assert out[0]["xstar_reference_depth_source"] == "same_run_xout_lines1"
    assert out[0]["xstar_reference_depth_match_mode"] == "reversed_level_indices"


def test_xstar_local_state_solver_kwargs_uses_target_cfrac():
    import xstar_atomic.benchmark as benchmark

    ctx = xa.context_from_values(ion="O VII", temperature_K=1.0e5, electron_density_cm3=1.0e8)
    triplet = xa.calc_triplet(
        "O VII",
        rows=[
            {"upper_level": "1s1.2s1.3S_1", "emit_outward": 8.0},
            {"upper_level": "1s1.2p1.3P_1", "emit_outward": 1.0},
            {"upper_level": "1s1.2p1.1P_1", "emit_outward": 1.0},
        ],
    )
    target = XSTARLocalTarget(
        ion="O VII",
        run_dir="run",
        context=ctx,
        triplet=triplet,
        line_rows=triplet.lines,
        xstar_cfrac=0.75,
        xstar_cfrac_source="xstar_parameters:xout_abund1.fits",
    )
    kw = benchmark.xstar_local_state_solver_kwargs(target)
    assert kw["type50_bound_bound_treatment"] == "xstar-line-escape"
    assert kw["type50_cfrac"] == 0.75
    assert "type50_cfrac_source" not in kw  # diagnostic only; not a solver kwarg


def test_xstar_local_state_solver_kwargs_falls_back_to_cfrac_one():
    import xstar_atomic.benchmark as benchmark

    kw = benchmark.xstar_local_state_solver_kwargs(None)
    assert kw["type50_cfrac"] == 1.0
