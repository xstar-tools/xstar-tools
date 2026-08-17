from __future__ import annotations

import tarfile
import warnings
from pathlib import Path

import numpy as np
import pytest

from xstar_tools.xstar.abundance_tables import (
    DOCUMENTED_ABUNDANCE_TABLES,
    SOURCE_COMPATIBILITY_ALIASES,
    resolve_abundance_table,
)

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"
FIXTURE = ROOT / "tools/qualification/reference/xstar2table_mpi_grid_0_6_81_1.tar.gz"


def test_documented_abundance_table_inventory_and_source_aliases():
    assert DOCUMENTED_ABUNDANCE_TABLES == (
        "xdef", "angr", "aspl", "feld", "aneb", "grsa", "wilm", "lodd", "lpgp", "lpgs"
    )
    assert SOURCE_COMPATIBILITY_ALIASES == {"lgpp": "lpgp", "lgps": "lpgs"}


def test_abundance_tables_have_source_values_for_representative_elements():
    # Indices: H=0, He=1, C=5, O=7, Mg=11, Fe=25, Zn=29.
    expected = {
        "xdef": (1.00, 1.00e-1, 3.70e-4, 6.80e-4, 3.50e-5, 2.50e-5, 1.58e-8),
        "angr": (1.00, 9.77e-2, 3.63e-4, 8.51e-4, 3.80e-5, 4.68e-5, 3.98e-8),
        "aspl": (1.00, 8.51e-2, 2.69e-4, 4.90e-4, 3.98e-5, 3.16e-5, 3.63e-8),
        "feld": (1.00, 9.77e-2, 3.98e-4, 8.51e-4, 3.80e-5, 3.24e-5, 3.98e-8),
        "aneb": (1.00, 8.01e-2, 4.45e-4, 7.39e-4, 3.95e-5, 3.31e-5, 4.63e-8),
        "grsa": (1.00, 8.51e-2, 3.31e-4, 6.76e-4, 3.80e-5, 3.16e-5, 3.98e-8),
        "wilm": (1.00, 9.77e-2, 2.40e-4, 4.90e-4, 2.51e-5, 2.69e-5, 0.0),
        "lodd": (1.00, 7.92e-2, 2.45e-4, 4.90e-4, 3.55e-5, 2.95e-5, 4.27e-8),
        "lpgp": (1.00, 8.41e-2, 2.45e-4, 5.37e-4, 3.47e-5, 2.82e-5, 4.17e-8),
        "lpgs": (1.00, 9.69e-2, 2.78e-4, 6.06e-4, 3.98e-5, 3.27e-5, 5.02e-8),
    }
    indices = [0, 1, 5, 7, 11, 25, 29]
    for name, wanted in expected.items():
        normalized, base = resolve_abundance_table(name)
        assert normalized == name
        assert base.shape == (30,)
        np.testing.assert_array_equal(base[indices], np.asarray(wanted, dtype=float))


def test_abundance_source_spellings_alias_documented_lodders_tables():
    name_p, p = resolve_abundance_table("lpgp")
    alias_p, pp = resolve_abundance_table("lgpp")
    name_s, s = resolve_abundance_table("lpgs")
    alias_s, ss = resolve_abundance_table("lgps")
    assert (name_p, alias_p, name_s, alias_s) == ("lpgp", "lgpp", "lpgs", "lgps")
    np.testing.assert_array_equal(p, pp)
    np.testing.assert_array_equal(s, ss)


def test_unknown_abundance_table_falls_back_to_xdef_with_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        normalized, unknown = resolve_abundance_table("xxxx")
    _, xdef = resolve_abundance_table("xdef", warn_on_fallback=False)
    assert normalized == "xdef"
    np.testing.assert_array_equal(unknown, xdef)
    assert caught and "using abundtbl='xdef'" in str(caught[0].message)


def test_native_abundance_reader_contains_all_source_selectors():
    text = (CPP / "xstar_atdb_runtime.cpp").read_text(encoding="utf-8")
    for name in DOCUMENTED_ABUNDANCE_TABLES:
        assert f'"{name}"' in text
    for alias in SOURCE_COMPATIBILITY_ALIASES:
        assert f'"{alias}"' in text
    assert "multiplier*base" in text.replace(" ", "")


def test_lwrite_native_publication_uses_literal_source_condition():
    text = (CPP / "xstar_science_fits.cpp").read_text(encoding="utf-8")
    assert 'parameter_value(state, "lwrite", 0.0)' in text
    assert 'parameter_value(state, "npass", 1.0)' in text
    assert "const bool write_detail_products = (lwrite > 0) || (npass > 1);" in text
    assert "if (write_detail_products)" in text
    assert "result.files_written = write_detail_products ? 8u : 4u;" in text


def test_native_standalone_acceptance_uses_control_required_product_count():
    text = (CPP / "xstar_standalone.cpp").read_text(encoding="utf-8")
    assert "required_native_fits_products" in text
    assert 'retained_public_parameter_number(product, "lwrite", 0.0)' in text
    assert 'retained_public_parameter_number(product, "npass", 1.0)' in text
    assert "const bool detail = (lwrite > 0) || (npass > 1);" in text
    assert "const std::size_t public_non_abundance = detail ? 8u : 4u;" in text
    assert "fits_count != required_fits_count" in text
    assert 'FITS_PRODUCTS_REQUIRED=' in text


def test_python_public_contract_validates_lwrite_lprint_loopcontrol_ranges():
    text = (ROOT / "src/xstar_tools/xstar/physical_runner.py").read_text(encoding="utf-8")
    contract = (ROOT / "src/xstar_tools/xstar/parameter_contract.py").read_text(encoding="utf-8")
    # Since 0.6.82.23, public range validation is centralized in the
    # machine-readable Table-1 contract rather than duplicated as runner-local
    # error strings.  Keep this historical gate aligned with that ownership.
    assert "coerce_and_validate_parameter(_name, values[_name])" in text
    assert "('lwrite', 'integer', 0, 0, 1" in contract
    assert "('lprint', 'integer', 0, -1, 6" in contract
    assert "('loopcontrol', 'integer', 0, 0, 30000" in contract
    assert "detail_products_required" in text
    assert "lprint_contract" in text


def test_loopcontrol_real_mpi_grid_is_one_based_and_sequential():
    assert FIXTURE.is_file()
    with tarfile.open(FIXTURE, "r:gz") as archive:
        member = next(m for m in archive.getmembers() if m.name.endswith("xstinitable.lis"))
        content = archive.extractfile(member).read().decode("utf-8", errors="replace")
    lines = [line.strip() for line in content.splitlines() if line.strip().startswith("xstar ")]
    assert len(lines) == 6
    for index, line in enumerate(lines, start=1):
        assert f"loopcontrol={index}" in line
    assert "column=1e+20 rlogxi=1 loopcontrol=1" in content
    assert "column=1e+21 rlogxi=3 loopcontrol=6" in content


def test_xspec_sources_document_chapter6_and_canonical_source_provenance():
    for filename in ("xstar_xspec_table.cpp", "xstar_xspec_table_writer.cpp"):
        text = (CPP / filename).read_text(encoding="utf-8")
        assert "Chapter 6" in text
        assert "xstar2table.c" in text
        assert "xstartablelib.c" in text
        assert "not a new XSTAR scientific" in text or "does not alter\n// XSTAR physics" in text


def test_xspec_each_top_level_function_has_explanatory_comment():
    # This is deliberately lightweight: every function name that defines the
    # 0.6.81 table layer must be preceded by an explanatory // comment block.
    expected = {
        "xstar_xspec_table.cpp": [
            "set_message", "fits_error", "require_view", "read_float_column",
            "xstar_xspec_spectrum_open_v1", "xstar_xspec_spectrum_close_v1",
            "xstar_xspec_slice_energy_v1", "xstar_xspec_transform_v1",
            "xstar_xspec_read_parameter_v1",
        ],
        "xstar_xspec_table_writer.cpp": [
            "trim", "split", "as_float", "as_int", "fits_error", "fits_check",
            "ordered_parameters", "nint", "nadd", "ncombos",
            "write_primary_and_parameters", "write_energies_and_spectra_headers",
            "append_headers", "write_spectrum_row", "read_param", "parse_config",
            "build_tables",
        ],
    }
    for filename, names in expected.items():
        lines = (CPP / filename).read_text(encoding="utf-8").splitlines()
        for name in names:
            idx = next(i for i, line in enumerate(lines) if f"{name}(" in line)
            preceding = "\n".join(lines[max(0, idx - 5):idx])
            assert "//" in preceding, f"{filename}:{name} lacks explanatory comment"
