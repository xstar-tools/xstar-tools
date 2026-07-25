from __future__ import annotations

from pathlib import Path
import warnings

from astropy.io import fits
from astropy.io.fits.verify import VerifyWarning

from xstar_tools import __version__
from xstar_tools.xstar.fits_provenance import python_fits_provenance
from xstar_tools.xstar.output_writers import (
    OutputTable,
    ShellOutputHeader,
    _primary_hdu,
    _table_hdu,
    _write_hdul_with_xstar_string_padding,
)


def _set_backend(monkeypatch, name: str) -> None:
    monkeypatch.setenv("XSTAR_ATOMIC_BACKEND", name)
    for key in (
        "XSTAR_ATOMIC_SOLVER_BACKEND", "XSTAR_ATOMIC_RATES_BACKEND",
        "XSTAR_ATOMIC_MATRIX_BACKEND", "XSTAR_ATOMIC_EMISSIVITY_BACKEND",
        "XSTAR_ATOMIC_OPACITY_BACKEND", "XSTAR_ATOMIC_THERMAL_BACKEND",
        "XSTAR_ATOMIC_ENGINE_BACKEND",
    ):
        monkeypatch.setenv(key, name)


def test_patch5201736_package_version_matches_cpp_release():
    assert __version__ == "0.6.48.7.46.25.5.17.25.82"


def test_patch5201736_backend_aware_primary_metadata(monkeypatch):
    _set_backend(monkeypatch, "python")
    pure = python_fits_provenance()
    assert pure.creator == f"xstar_tools pure-python {__version__}"
    assert pure.origin == "xstar_tools pure-Python"
    assert pure.datamode == "PYTHON_LIVE_STATE"

    _set_backend(monkeypatch, "cpp")
    cpp = python_fits_provenance()
    assert cpp.creator == f"xstar_tools python with cpp backend {__version__}"
    assert cpp.origin == "xstar_tools Python with C++ backend"
    assert cpp.datamode == "PYTHON_CPP_BACKEND_LIVE_STATE"


def test_patch5201736_primary_header_and_checksums(tmp_path: Path, monkeypatch):
    _set_backend(monkeypatch, "python")
    primary = _primary_hdu(model_name="model", atomic_data_date="2025-03-19T16:30:54")
    assert primary.header["CREATOR"] == f"xstar_tools pure-python {__version__}"
    assert primary.header.comments["CREATOR"] == ""
    assert primary.header.comments["RUNID"] == ""
    assert primary.header["MODEL"] == "model"
    assert primary.header.comments["MODEL"] == "source model name"
    assert primary.header["ORIGIN"] == "xstar_tools pure-Python"
    assert primary.header["DATAMODE"] == "PYTHON_LIVE_STATE"
    assert primary.header["TAUMODE"] == "NATIVE_OPACITY_TRAPEZOID"
    assert "DATE" in primary.header
    assert any("Flexible Image Transport System" in str(x) for x in primary.header["COMMENT"])

    table = OutputTable(
        extension_name="TEST",
        columns=("value",),
        units=("",),
        values={"value": [1.0]},
        formats=("1E",),
        binary=True,
        header_keywords={},
    )
    path = tmp_path / "header_test.fits"
    _write_hdul_with_xstar_string_padding(
        fits.HDUList([primary, _table_hdu(table)]), path, overwrite=True
    )
    with fits.open(path, checksum=True) as hdul:
        assert all("CHECKSUM" in h.header and "DATASUM" in h.header for h in hdul)



def test_patch5201736_cpp_backend_long_provenance_cards_do_not_warn(monkeypatch):
    _set_backend(monkeypatch, "cpp")
    with warnings.catch_warnings():
        warnings.simplefilter("error", VerifyWarning)
        primary = _primary_hdu(model_name="model", atomic_data_date="2025-03-19T16:30:54")
    assert primary.header["CREATOR"] == f"xstar_tools python with cpp backend {__version__}"
    assert primary.header.comments["CREATOR"] == ""
    assert primary.header["RUNID"] == f"python-cpp-backend-{__version__}"
    assert primary.header.comments["RUNID"] == ""

def test_patch5201736_radial_keyword_comments_and_state_source():
    header = ShellOutputHeader(
        1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0,
        state_source="live Python savd-equivalent radial state before geometry update",
    )
    cards = header.fits_keywords()
    assert cards["RINNER"][1] == "[cm] Inner shell radius"
    assert cards["ROUTER"][1] == "[cm] Outer shell radius"
    assert cards["RDEL"][1] == "[cm] distance from face"
    assert cards["LOGXI"][1] == "[erg cm/s] log(ionization parameter)"
    assert cards["STATESRC"] == "live Python savd-equivalent radial state before geometry update"
