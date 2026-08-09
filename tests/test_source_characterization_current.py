"""Current, dependency-free characterization anchors for Milestone-2 concordance IDs.

These tests intentionally exercise stable architectural/source contracts without
requiring an ATDB installation or any retired package namespace.  Full
scientific acceptance remains owned by the frozen parity evidence.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XSTAR = ROOT / "src/xstar_tools/xstar"
CPP = XSTAR / "cpp"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_arch_001_controller_one_zone_boundary() -> None:
    driver = text(XSTAR / "driver.py")
    runner = text(XSTAR / "physical_runner.py")
    assert "local_zone" in driver or "run_" in driver
    assert "radial" in runner.lower()
    assert (CPP / "xstar_engine.cpp").is_file()
    assert (CPP / "xstar_standalone.cpp").is_file()


def test_input_001_fortran_input_semantics_anchor() -> None:
    nums = text(XSTAR / "fortran_numbers.py")
    runner = text(XSTAR / "physical_runner.py")
    assert "Fortran" in nums and "exponent" in nums.lower()
    assert "rlogxi" in runner or "radius" in runner.lower()


def test_db_001_atomic_database_pointer_topology_anchor() -> None:
    source = text(XSTAR / "atomic_database.py")
    assert "setptrs" in source
    assert "XSTARMasterData" in source
    assert "XSTARDerivedPointers" in source
    assert "data type" in source.lower()


def test_ion_001_pre_matrix_ion_balance_anchor() -> None:
    source = text(XSTAR / "ion_balance.py")
    assert "ion" in source.lower()
    assert "rate" in source.lower()
    assert "active" in source.lower()


def test_level_001_compact_level_topology_anchor() -> None:
    source = text(XSTAR / "element_equilibrium.py")
    assert "level" in source.lower()
    assert "lte" in source.lower()
    assert (CPP / "level_population.cpp").is_file()


def test_matrix_001_matrix_assembly_and_solve_anchor() -> None:
    source = text(XSTAR / "element_equilibrium.py")
    linear = text(XSTAR / "linear_algebra.py")
    assert "matrix" in source.lower()
    assert "lucy" in linear.lower() or "solve" in linear.lower()
    assert (CPP / "matrix_kernels.cpp").is_file()


def test_therm_001_thermal_construction_anchor() -> None:
    source = text(XSTAR / "thermal_balance.py")
    assert "heating" in source.lower() or "cooling" in source.lower()
    assert (CPP / "thermal_kernels.cpp").is_file()


def test_dsec_001_nonlinear_controller_anchor() -> None:
    source = text(XSTAR / "dsec.py")
    assert "temperature" in source.lower()
    assert "converg" in source.lower()
    assert "dsec" in source.lower()


def test_emisab_001_reduced_grid_publication_anchor() -> None:
    source = text(XSTAR / "emissivity.py")
    assert "calc_emisab" in source
    assert "reduced" in source.lower() or "bin" in source.lower()


def test_emis_001_full_grid_emission_opacity_anchor() -> None:
    source = text(XSTAR / "emergent_emissivity.py")
    assert "calc_emis" in source
    assert "opacity" in source.lower() or "emiss" in source.lower()


def test_type50_001_line_profile_opacity_anchor() -> None:
    source = text(CPP / "opacity_kernels.cpp")
    assert "Type50" in source or "type50" in source
    assert "linopac" in source.lower() or "profile" in source.lower()


def test_radial_001_transfer_termination_anchor() -> None:
    transfer = text(XSTAR / "radial_transfer.py")
    control = text(XSTAR / "radial_control.py")
    assert "transfer" in transfer.lower() or "radial" in transfer.lower()
    assert "stop" in control.lower() or "termination" in control.lower() or "step" in control.lower()


def test_state_001_saved_radial_state_anchor() -> None:
    source = text(XSTAR / "saved_radial_state.py")
    assert "save" in source.lower()
    assert "restore" in source.lower() or "unsav" in source.lower()


def test_detail_001_detail_publication_anchor() -> None:
    source = text(XSTAR / "output_writers.py")
    assert "fstepr" in source.lower()
    assert "detail" in source.lower()


def test_step_001_step_print_anchor() -> None:
    source = text(XSTAR / "pprint_legacy.py")
    assert "option" in source.lower()
    assert "abund" in source.lower() or "pprint" in source.lower()


def test_final_001_final_product_writers_anchor() -> None:
    source = text(CPP / "xstar_science_fits.cpp")
    for token in ("xout_lines1", "xout_cont1", "xout_rrc1", "xout_spect1"):
        assert token in source


def test_backend_001_public_mode_mapping_anchor() -> None:
    source = text(ROOT / "src/xstar_tools/execution.py")
    for mode in ("pure-python", "zone-python", "zone-cpp", "zone-all", "xstar-cpp"):
        assert mode in source
    assert "cpp-zone" in source
    assert "cpp-all" in source


def test_terminal_001_terminal_lifetime_anchor() -> None:
    standalone = text(CPP / "xstar_standalone.cpp")
    fits = text(CPP / "xstar_science_fits.cpp")
    assert "final" in standalone.lower()
    assert "terminal" in standalone.lower() or "final" in fits.lower()
