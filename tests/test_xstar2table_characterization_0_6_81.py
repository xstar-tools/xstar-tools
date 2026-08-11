from __future__ import annotations

from pathlib import Path

from xstar_tools.tables import XSpecTableProducts

ROOT = Path(__file__).resolve().parents[1]
CPP = ROOT / "src/xstar_tools/xstar/cpp"


def test_native_xstar2table_sources_exist():
    for name in (
        "xstar_xspec_table.h",
        "xstar_xspec_table.cpp",
        "xstar_xspec_table_internal.hpp",
        "xstar_xspec_table_writer.cpp",
        "xstar_xspec_table_cli.cpp",
    ):
        assert (CPP / name).is_file()


def test_xstar2table_cli_is_implemented():
    text = (ROOT / "src/xstar_tools/cli/xstar2table.py").read_text(encoding="utf-8")
    assert "NotImplementedError" not in text
    assert "build_xspec_tables" in text


def test_canonical_transform_constants_are_pinned():
    text = (CPP / "xstar_xspec_table.cpp").read_text(encoding="utf-8")
    assert "8.356e-7;" in text
    assert "8.356e-7f" not in text
    assert "1.0e-32f" in text
    assert "TFLOAT" in text


def test_schema_writer_has_required_xspec_columns():
    text = (CPP / "xstar_xspec_table_writer.cpp").read_text(encoding="utf-8")
    for token in ("PARAMETERS", "ENERGIES", "SPECTRA", "PARAMVAL", "INTPSPEC", "ADDSP%03", "ADDMODEL", "REDSHIFT"):
        assert token in text


def test_product_paths_are_stable(tmp_path):
    products = XSpecTableProducts.from_directory(tmp_path)
    assert products.ain.name == "xout_ain.fits"
    assert products.aout.name == "xout_aout.fits"
    assert products.mtable.name == "xout_mtable.fits"
    assert products.etable.name == "xout_etable.fits"


def test_concordance_document_covers_legacy_limitations():
    text = (ROOT / "docs/developer/xstar2xspec_source_concordance.md").read_text(encoding="utf-8")
    assert "LASTSPEC" in text
    assert "energy-grid consistency" in text.lower()
    assert "loopcontrol=0" in text
    assert "0.6.82" in text and "0.6.83" in text


def test_native_wheel_stages_xspec_table_runtime():
    text = (ROOT / "build_support.py").read_text(encoding="utf-8")
    assert '"libxstar_xspec_table.so"' in text
    assert '"xstar-xspec-table"' in text
