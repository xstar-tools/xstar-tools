"""Python tools for reading and evaluating XSTAR's packed ``atdb.fits`` atomic database.

This package is an early research/development package built from the validated
standalone ATDB scripts. It provides low-level packed-FITS decoding plus first
physics extractors for levels, lines, photoionization, collisions, recombination,
emissivity tables, and prototype level-population solving.
"""

from .hierarchy import ATDB, IndexedRecord, SYMBOL_TO_Z, Z_TO_SYMBOL, roman

__all__ = [
    "ATDB",
    "IndexedRecord",
    "SYMBOL_TO_Z",
    "Z_TO_SYMBOL",
    "roman",
]

__version__ = "0.1.0"
