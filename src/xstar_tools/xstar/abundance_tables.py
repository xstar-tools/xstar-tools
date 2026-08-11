"""Canonical XSTAR abundance bases used by ``abundtbl``.

The numerical values are transcribed from XSTAR 2.59g
``xstarlib/src/xstarsetup.f90``.  XSTAR first chooses one of these 30-element
cosmic abundance bases (H through Zn) and then multiplies it element-by-element
by the public ``habund`` ... ``znabund`` parameters.

The XSTAR manual documents ``lpgp`` and ``lpgs`` for the two Lodders, Palme &
Gail (2009) tables, while the 2.59g ``xstarsetup.f90`` source supplied for the
qualification campaign uses the spellings ``lgpp`` and ``lgps``.  xstar_tools
accepts both spellings and maps each pair to the same source array.
"""
from __future__ import annotations

from typing import Final
import warnings

import numpy as np


XDEF: Final = (
    1.00e0, 1.00e-1, 1.00e-10, 1.00e-10, 1.00e-10, 3.70e-4,
    1.10e-4, 6.80e-4, 3.98e-8, 2.80e-5, 1.78e-6, 3.50e-5,
    2.45e-6, 3.50e-5, 3.31e-7, 1.60e-5, 3.98e-7, 4.50e-6,
    8.91e-8, 2.10e-6, 1.66e-9, 1.35e-7, 2.51e-8, 7.08e-7,
    2.51e-7, 2.50e-5, 1.26e-7, 2.00e-6, 3.16e-8, 1.58e-8,
)
ANGR: Final = (
    1.00e0, 9.77e-2, 1.45e-11, 1.41e-11, 3.98e-10, 3.63e-4,
    1.12e-4, 8.51e-4, 3.63e-8, 1.23e-4, 2.14e-6, 3.80e-5,
    2.95e-6, 3.55e-5, 2.82e-7, 1.62e-5, 3.16e-7, 3.63e-6,
    1.32e-7, 2.29e-6, 1.26e-9, 9.77e-8, 1.00e-8, 4.68e-7,
    2.45e-7, 4.68e-5, 8.32e-8, 1.78e-6, 1.62e-8, 3.98e-8,
)
ASPL: Final = (
    1.00e0, 8.51e-2, 1.12e-11, 2.40e-11, 5.01e-10, 2.69e-4,
    6.76e-5, 4.90e-4, 3.63e-8, 8.51e-5, 1.74e-6, 3.98e-5,
    2.82e-6, 3.24e-5, 2.57e-7, 1.32e-5, 3.16e-7, 2.51e-6,
    1.07e-7, 2.19e-6, 1.41e-9, 8.91e-8, 8.51e-9, 4.37e-7,
    2.69e-7, 3.16e-5, 9.77e-8, 1.66e-6, 1.55e-8, 3.63e-8,
)
FELD: Final = (
    1.00e0, 9.77e-2, 1.26e-11, 2.51e-11, 3.55e-10, 3.98e-4,
    1.00e-4, 8.51e-4, 3.63e-8, 1.29e-4, 2.14e-6, 3.80e-5,
    2.95e-6, 3.55e-5, 2.82e-7, 1.62e-5, 3.16e-7, 4.47e-6,
    1.32e-7, 2.29e-6, 1.48e-9, 1.05e-7, 1.00e-8, 4.68e-7,
    2.45e-7, 3.24e-5, 8.32e-8, 1.78e-6, 1.62e-8, 3.98e-8,
)
ANEB: Final = (
    1.00e0, 8.01e-2, 2.19e-9, 2.87e-11, 8.82e-10, 4.45e-4,
    9.12e-5, 7.39e-4, 3.10e-8, 1.38e-4, 2.10e-6, 3.95e-5,
    3.12e-6, 3.68e-5, 3.82e-7, 1.89e-5, 1.93e-7, 3.82e-6,
    1.39e-7, 2.25e-6, 1.24e-9, 8.82e-8, 1.08e-8, 4.93e-7,
    3.50e-7, 3.31e-5, 8.27e-8, 1.81e-6, 1.89e-8, 4.63e-8,
)
GRSA: Final = (
    1.00e0, 8.51e-2, 1.26e-11, 2.51e-11, 3.55e-10, 3.31e-4,
    8.32e-5, 6.76e-4, 3.63e-8, 1.20e-4, 2.14e-6, 3.80e-5,
    2.95e-6, 3.55e-5, 2.82e-7, 2.14e-5, 3.16e-7, 2.51e-6,
    1.32e-7, 2.29e-6, 1.48e-9, 1.05e-7, 1.00e-8, 4.68e-7,
    2.45e-7, 3.16e-5, 8.32e-8, 1.78e-6, 1.62e-8, 3.98e-8,
)
WILM: Final = (
    1.00e0, 9.77e-2, 0.0, 0.0, 0.0, 2.40e-4,
    7.59e-5, 4.90e-4, 0.0, 8.71e-5, 1.45e-6, 2.51e-5,
    2.14e-6, 1.86e-5, 2.63e-7, 1.23e-5, 1.32e-7, 2.57e-6,
    0.0, 1.58e-6, 0.0, 6.46e-8, 0.0, 3.24e-7,
    2.19e-7, 2.69e-5, 8.32e-8, 1.12e-6, 0.0, 0.0,
)
LODD: Final = (
    1.00e0, 7.92e-2, 1.90e-9, 2.57e-11, 6.03e-10, 2.45e-4,
    6.76e-5, 4.90e-4, 2.88e-8, 7.41e-5, 1.99e-6, 3.55e-5,
    2.88e-6, 3.47e-5, 2.88e-7, 1.55e-5, 1.82e-7, 3.55e-6,
    1.29e-7, 2.19e-6, 1.17e-9, 8.32e-8, 1.00e-8, 4.47e-7,
    3.16e-7, 2.95e-5, 8.13e-8, 1.66e-6, 1.82e-8, 4.27e-8,
)
LPGP: Final = (
    1.00e0, 8.41e-2, 1.26e-11, 2.40e-11, 5.01e-10, 2.45e-4,
    7.24e-5, 5.37e-4, 3.63e-8, 1.12e-4, 2.00e-6, 3.47e-5,
    2.95e-6, 3.31e-5, 2.88e-7, 1.38e-5, 3.16e-7, 3.16e-6,
    1.32e-7, 2.14e-6, 1.26e-9, 7.94e-8, 1.00e-8, 4.37e-7,
    2.34e-7, 2.82e-5, 8.32e-8, 1.70e-6, 1.62e-8, 4.17e-8,
)
LPGS: Final = (
    1.00e0, 9.69e-2, 2.15e-9, 2.36e-11, 7.26e-10, 2.78e-4,
    8.19e-5, 6.06e-4, 3.10e-8, 1.27e-4, 2.23e-6, 3.98e-5,
    3.27e-6, 3.86e-5, 3.20e-7, 1.63e-5, 2.00e-7, 3.58e-6,
    1.45e-7, 2.33e-6, 1.33e-9, 9.54e-8, 1.11e-8, 5.06e-7,
    3.56e-7, 3.27e-5, 9.07e-8, 1.89e-6, 2.09e-8, 5.02e-8,
)

_TABLES: Final = {
    "xdef": XDEF,
    "angr": ANGR,
    "aspl": ASPL,
    "feld": FELD,
    "aneb": ANEB,
    "grsa": GRSA,
    "wilm": WILM,
    "lodd": LODD,
    "lpgp": LPGP,
    "lpgs": LPGS,
    # Exact spellings in the supplied XSTAR 2.59g xstarsetup.f90.
    "lgpp": LPGP,
    "lgps": LPGS,
}

DOCUMENTED_ABUNDANCE_TABLES: Final = (
    "xdef", "angr", "aspl", "feld", "aneb", "grsa", "wilm", "lodd", "lpgp", "lpgs"
)
SOURCE_COMPATIBILITY_ALIASES: Final = {"lgpp": "lpgp", "lgps": "lpgs"}


def resolve_abundance_table(name: object, *, warn_on_fallback: bool = True) -> tuple[str, np.ndarray]:
    """Resolve ``abundtbl`` and return ``(normalized_name, base_abundances)``.

    XSTAR 2.59g truncates the XPI string to four characters before
    ``xstarsetup`` selects a table.  Unknown names fall back to ``xdef``.
    xstar_tools additionally accepts the manual spellings ``lpgp/lpgs`` and
    the supplied source spellings ``lgpp/lgps`` as aliases for the same two
    Lodders et al. arrays.
    """

    raw = str(name).strip().lower()[:4]
    if raw in _TABLES:
        return raw, np.asarray(_TABLES[raw], dtype=float)
    if warn_on_fallback:
        warnings.warn(
            f"invalid XSTAR abundance table {name!r}; using abundtbl='xdef'",
            RuntimeWarning,
            stacklevel=2,
        )
    return "xdef", np.asarray(XDEF, dtype=float)


__all__ = [
    "DOCUMENTED_ABUNDANCE_TABLES",
    "SOURCE_COMPATIBILITY_ALIASES",
    "resolve_abundance_table",
]
