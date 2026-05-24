from __future__ import annotations

from pathlib import Path

import pytest
from astropy.io import fits

import xstar_atomic as xa
from xstar_atomic.source_port import (
    default_port_ledger,
    run_direct_fortran_output_writer_validation,
    run_output_writer_validation,
)


@pytest.fixture(scope="module")
def output_summary(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("output_writer_v0469")
    return run_output_writer_validation(out_dir=root)


def test_v0469_direct_original_fortran_writer_gate():
    summary = run_direct_fortran_output_writer_validation()
    assert summary["voigte_direct_fortran_ready"] is True
    assert summary["binemis_strong_line_direct_fortran_ready"] is True
    assert summary["fstepr_direct_fortran_ready"] is True
    assert summary["fstepr2_direct_fortran_ready"] is True
    assert summary["fstepr3_direct_fortran_ready"] is True
    assert summary["fstepr4_direct_fortran_ready"] is True
    assert summary["writespectra_direct_fortran_ready"] is True
    assert summary["writespectra2_direct_fortran_ready"] is True
    assert summary["writespectra3_direct_fortran_ready"] is True
    assert summary["writespectra4_direct_fortran_ready"] is True
    assert summary["output_writers_direct_original_fortran_reference_ready"] is True


def test_v0469_detail_writer_sequence_and_real4_contract(output_summary):
    assert output_summary["detail_caller_owned_pass_store_ready"] is True
    assert output_summary["savd_fstepr_call_order_ready"] is True
    assert output_summary["detail_hdu_insertion_shift_order_ready"] is True
    assert output_summary["detail_shell_header_real4_ready"] is True
    assert output_summary["detail_table_schemas_ready"] is True
    assert output_summary["detail_record_count"] == 3


def test_v0469_final_source_order_and_lwri_contract(output_summary):
    assert output_summary["final_local_recompute_source_order_ready"] is True
    assert output_summary["final_nlimd_zero_dsec_skip_ready"] is True
    assert output_summary["final_writer_source_order_ready"] is True
    assert output_summary["writespectra_lwri_gates_ready"] is True
    order = output_summary["output_writer_source_order"]
    assert order.index("heatt") < order.index("stpcut")
    assert order.index("stpcut") < order.index("pprint(22)")
    assert order[-4:] == [
        "writespectra", "writespectra2", "writespectra3", "writespectra4"
    ]


def test_v0469_fits_products_have_source_layout_and_checksums(output_summary):
    assert output_summary["detail_pass_filename_fnappend_ready"] is True
    assert output_summary["fits_primary_parameters_data_hdu_ready"] is True
    assert output_summary["fits_checksums_ready"] is True
    root = Path(output_summary["validation_root"]) / "generated_fits"
    expected = {
        "xo01_detail.fits", "xo01_detal2.fits", "xo01_detal3.fits", "xo01_detal4.fits",
        "xout_spect1.fits", "xout_lines1.fits", "xout_cont1.fits", "xout_rrc1.fits",
        "xout_abund1.fits",
    }
    assert {path.name for path in root.glob("*.fits")} == expected
    with fits.open(root / "xout_spect1.fits", checksum=True) as hdul:
        assert [hdu.name for hdu in hdul] == ["PRIMARY", "PARAMETERS", "XSTAR_SPECTRA"]
        assert hdul[0].header["CREATOR"] == "XSTAR version 2.59g"


def test_v0469_caller_owned_state_and_explicit_pprint_boundary(output_summary):
    assert output_summary["caller_owned_output_state_ready"] is True
    assert output_summary["pprint_source_state_handler_explicit_ready"] is True
    assert output_summary["legacy_pprint_ascii_products_not_approximated_ready"] is True
    assert output_summary["physical_standard_benchmark_not_claimed_ready"] is True


def test_v0469_output_writer_acceptance(output_summary):
    assert output_summary["detail_and_final_output_writer_source_acceptance_ready"] is True
    assert output_summary["next_source_target"] == (
        "physical_all_atdb_standard_benchmark_output_parity"
    )


def test_v0469_ledger_exports_and_version():
    assert xa.__version__ == "0.4.87"
    ledger = default_port_ledger()
    routines = {entry.routine: entry for entry in ledger.entries}
    for routine in (
        "fheader", "fparmlist", "savd", "fstepr", "fstepr2", "fstepr3", "fstepr4",
        "binemis", "voigte", "writespectra", "writespectra2", "writespectra3", "writespectra4",
    ):
        assert routines[routine].status.value == "validated"
    assert routines["pprint"].status.value == "validated"
