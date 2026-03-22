"""Python tools for reading and evaluating XSTAR's packed ``atdb.fits`` atomic database."""

from .hierarchy import ATDB
from .api import XSTARAtomic, parse_ion

__all__ = ["ATDB", "XSTARAtomic", "parse_ion"]

__version__ = "0.2.24"
