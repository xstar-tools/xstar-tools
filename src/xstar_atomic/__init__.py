"""Python tools for reading and evaluating XSTAR's packed ``atdb.fits`` atomic database."""

from .hierarchy import ATDB
from .api import XSTARAtomic, parse_ion
from .data import download_data, find_atdb_file, get_data_path, resolve_atdb_path, set_data_path
from .xstar_element_solver import solve_element_reference

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

__version__ = "0.3.23"
