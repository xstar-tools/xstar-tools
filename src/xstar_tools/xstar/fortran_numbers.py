"""Parsing helpers for numeric text emitted by XSTAR Fortran probes.

Some Fortran exponential edit descriptors omit the ``E`` when the exponent
needs three digits, for example ``-3.1564610560130326-107``.  Python's
``float`` does not accept that representation, so probe readers normalize it
without changing the captured numeric value.
"""
from __future__ import annotations

import re
from typing import Any

_OMITTED_E_RE = re.compile(
    r"^([+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+)))([+-]\d{2,})$"
)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Parse fortran float for this module while preserving the surrounding source/runtime invariants.
# Reference context: Fortran numeric-format compatibility helper; no direct scientific formula.
# XSTAR-FUNCTION-COMMENT-END
def parse_fortran_float(value: Any) -> float:
    """Return a Python float from standard or width-compressed Fortran text.

    Accepted forms include ordinary decimal/scientific notation, ``D``
    exponents, and omitted-``E`` exponents such as ``1.23-107``.
    """

    text = str(value).strip()
    if not text:
        raise ValueError("empty Fortran numeric field")
    normalized = text.replace("D", "E").replace("d", "e")
    try:
        return float(normalized)
    except ValueError:
        match = _OMITTED_E_RE.fullmatch(normalized)
        if match is None:
            raise ValueError(f"invalid Fortran floating-point field: {text!r}") from None
        return float(f"{match.group(1)}E{match.group(2)}")
