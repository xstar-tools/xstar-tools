from __future__ import annotations

from pathlib import Path

from astropy.io import fits
import pytest

import xstar_atomic as xa
from xstar_atomic.source_port import (
    compare_physical_output_directories,
    default_port_ledger,
    run_direct_fortran_pprint_validation,
    run_output_writer_validation,
)


@pytest.fixture(scope="module")
def pprint_summary(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("pprint_output_v0470")
    return run_output_writer_validation(out_dir=root)


def test_v0470_direct_original_fortran_pprint_gate():
    summary = run_direct_fortran_pprint_validation()
    assert summary["pprint_option17_heading_direct_fortran_ready"] is True
    assert summary["pprint_option9_values_direct_fortran_ready"] is True
    assert summary["pprint_option11_column_direct_fortran_ready"] is True
    assert summary["pprint_direct_original_fortran_reference_ready"] is True


def test_v0470_default_pprint_source_order(pprint_summary):
    assert pprint_summary["legacy_pprint_default_path_translated"] is True
    assert pprint_summary["pprint_default_source_order_ready"] is True
    assert pprint_summary["pprint_source_state_handler_replaced_ready"] is True
    assert pprint_summary["verbose_pprint_untranslated_branches_fail_explicitly_ready"] is True
    order = pprint_summary["output_writer_source_order"]
    assert order.index("stpcut") < order.index("pprint(22)")
    assert order.index("pprint(22)") < order.index("pprint(11)")
    assert order.index("pprint(11)") < order.index("writespectra")


def test_v0470_legacy_products(pprint_summary):
    root = Path(pprint_summary["validation_root"]) / "generated_fits"
    assert pprint_summary["xout_step_log_ready"] is True
    assert pprint_summary["xout_abund1_extensions_ready"] is True
    assert pprint_summary["pprint_real4_persistence_ready"] is True
    assert (root / "xout_step.log").is_file()
    with fits.open(root / "xout_abund1.fits", checksum=True) as hdul:
        assert [h.name for h in hdul] == [
            "PRIMARY", "ABUNDANCES", "COLUMNS", "HEATING", "COOLING"
        ]
        assert len(hdul["ABUNDANCES"].data) == 3
        assert all(
            str(hdul["ABUNDANCES"].header[f"TFORM{i}"]).strip() == "E13.5"
            for i in range(1, len(hdul["ABUNDANCES"].columns) + 1)
        )


def test_v0470_physical_parity_harness_self_comparison(pprint_summary):
    root = Path(pprint_summary["validation_root"]) / "generated_fits"
    result = compare_physical_output_directories(root, root)
    assert result.inputs_available is True
    assert result.parity_run is True
    assert result.all_files_ready is True
    assert {item.filename for item in result.files} >= {
        "xout_step.log", "xout_abund1.fits", "xout_spect1.fits",
        "xout_lines1.fits", "xout_cont1.fits", "xout_rrc1.fits",
    }


def test_v0470_physical_parity_missing_inputs_not_claimed(tmp_path):
    result = compare_physical_output_directories(
        tmp_path / "missing_xstar", tmp_path / "missing_python"
    )
    assert result.inputs_available is False
    assert result.parity_run is False
    assert result.all_files_ready is False


def test_v0470_bounded_acceptance_and_physical_scope(pprint_summary):
    assert pprint_summary["physical_standard_benchmark_parity_harness_ready"] is True
    assert pprint_summary["physical_standard_benchmark_inputs_available"] is False
    assert pprint_summary["physical_standard_benchmark_parity_run"] is False
    assert pprint_summary["physical_standard_benchmark_all_files_match"] is False
    assert pprint_summary["detail_and_final_output_writer_source_acceptance_ready"] is True
    assert pprint_summary["next_source_target"] == "physical_all_atdb_standard_benchmark_output_parity"


def test_v0470_ledger_and_version():
    assert xa.__version__ == "0.4.80"
    routines = {entry.routine: entry for entry in default_port_ledger().entries}
    assert routines["pprint"].status.value == "validated"
    assert routines["physical_output_parity"].status.value == "partial"
