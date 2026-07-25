"""Backend-aware FITS provenance metadata shared by Python product writers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .. import __version__
from .backend_config import resolve_backend_selection

FITS_STANDARD_COMMENTS = (
    "FITS (Flexible Image Transport System) format is defined in 'Astronomy",
    "and Astrophysics', volume 376, page 359; bibcode: 2001A&A...376..359H",
)


@dataclass(frozen=True)
class PythonFitsProvenance:
    creator: str
    origin: str
    datamode: str
    run_id: str
    backend_kind: str


def python_fits_provenance() -> PythonFitsProvenance:
    """Return truthful product provenance for the active Python driver mode."""
    selection = resolve_backend_selection()
    kernels = (
        selection.solver_backend,
        selection.rates_backend,
        selection.matrix_backend,
        selection.emissivity_backend,
        selection.opacity_backend,
        selection.thermal_backend,
        selection.engine_backend,
    )
    if all(name == "python" for name in kernels):
        return PythonFitsProvenance(
            creator=f"xstar_tools pure-python {__version__}",
            origin="xstar_tools pure-Python",
            datamode="PYTHON_LIVE_STATE",
            run_id=f"python-pure-{__version__}",
            backend_kind="pure-python",
        )
    if all(name == "cpp" for name in kernels):
        return PythonFitsProvenance(
            creator=f"xstar_tools python with cpp backend {__version__}",
            origin="xstar_tools Python with C++ backend",
            datamode="PYTHON_CPP_BACKEND_LIVE_STATE",
            run_id=f"python-cpp-backend-{__version__}",
            backend_kind="python-with-cpp-backend",
        )
    return PythonFitsProvenance(
        creator=f"xstar_tools Python mixed backend {__version__}",
        origin="xstar_tools Python mixed backend",
        datamode="PYTHON_MIXED_BACKEND_LIVE_STATE",
        run_id=f"python-mixed-backend-{__version__}",
        backend_kind="python-mixed-backend",
    )


def apply_python_primary_fits_header(
    header: Any,
    *,
    model_name: str,
    atomic_data_date: str,
) -> PythonFitsProvenance:
    """Apply the C++-style provenance block to a Python primary HDU header."""
    provenance = python_fits_provenance()
    for text in FITS_STANDARD_COMMENTS:
        header.add_comment(text)
    header["CREATOR"] = provenance.creator
    header["MODEL"] = (str(model_name)[:30].rstrip(), "source model name")
    header["ORIGIN"] = provenance.origin
    header["ATDATA"] = (str(atomic_data_date)[:63], "supplied atomic database metadata")
    header["DATAMODE"] = (provenance.datamode, "no benchmark payloads")
    header["TAUMODE"] = (
        "NATIVE_OPACITY_TRAPEZOID",
        "output-grid depths from native opacity",
    )
    header["RUNID"] = provenance.run_id
    header["DATE"] = (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "file creation date (YYYY-MM-DDThh:mm:ss UT)",
    )
    return provenance


__all__ = [
    "FITS_STANDARD_COMMENTS",
    "PythonFitsProvenance",
    "apply_python_primary_fits_header",
    "python_fits_provenance",
]
