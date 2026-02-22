"""Python tools for reading and evaluating XSTAR's packed ``atdb.fits`` atomic database.

This package is an early research/development package built from the validated
standalone ATDB scripts. It provides low-level packed-FITS decoding plus first
physics extractors for levels, lines, photoionization, collisions, recombination,
emissivity tables, and prototype level-population solving.
"""

from .hierarchy import ATDB, IndexedRecord, SYMBOL_TO_Z, Z_TO_SYMBOL, roman
from .api import XSTARAtomic, parse_ion, roman_to_int

__all__ = [
    "ATDB",
    "XSTARAtomic",
    "IndexedRecord",
    "SYMBOL_TO_Z",
    "Z_TO_SYMBOL",
    "roman",
    "parse_ion",
    "roman_to_int",
]

__version__ = "0.1.5"
