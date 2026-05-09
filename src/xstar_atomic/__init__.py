"""Python tools for reading and evaluating XSTAR's packed ``atdb.fits`` atomic database."""

__version__ = "0.3.119"

try:
    from .hierarchy import ATDB
    from .api import XSTARAtomic, parse_ion
    from .data import download_data, find_atdb_file, get_data_path, resolve_atdb_path, set_data_path
    from .xstar_element_solver import solve_element_reference
except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency guard
    if exc.name != "astropy":
        raise

    def _missing_astropy(*args, **kwargs):
        raise ImportError("This xstar_atomic feature requires astropy. Install package dependencies or `pip install astropy`.")

    ATDB = _missing_astropy  # type: ignore
    XSTARAtomic = _missing_astropy  # type: ignore
    parse_ion = _missing_astropy  # type: ignore
    download_data = _missing_astropy  # type: ignore
    find_atdb_file = _missing_astropy  # type: ignore
    get_data_path = _missing_astropy  # type: ignore
    resolve_atdb_path = _missing_astropy  # type: ignore
    set_data_path = _missing_astropy  # type: ignore
    solve_element_reference = _missing_astropy  # type: ignore

__all__ = [
    "ATDB",
    "XSTARAtomic",
    "parse_ion",
    "download_data",
    "find_atdb_file",
    "get_data_path",
    "resolve_atdb_path",
    "set_data_path",
    "solve_element_reference",
]
