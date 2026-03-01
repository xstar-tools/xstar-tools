"""Python tools for reading and evaluating XSTAR's packed ``atdb.fits`` atomic database."""

from .hierarchy import ATDB
from .api import XSTARAtomic

__all__ = ["ATDB", "XSTARAtomic"]

__version__ = "0.2.3"
