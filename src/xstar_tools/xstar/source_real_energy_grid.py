"""Literal arithmetic-kind translation of the XSTAR ``ener.f90`` grid."""
from __future__ import annotations
import numpy as np


def source_default_real(value: float) -> float:
    """Evaluate a source default-REAL literal then promote it to Python float."""
    return float(np.float32(value))


def source_default_real_reciprocal(denominator: int) -> float:
    """Translate ``1./float(denominator)`` as a default-REAL expression."""
    if int(denominator) == 0:
        raise ZeroDivisionError("ener default-real reciprocal denominator is zero")
    return float(np.float32(np.float32(1.0) / np.float32(int(denominator))))


def source_ener_grid(ncn2: int) -> np.ndarray:
    """Return the source-faithful REAL(8) EPI grid from ``ener.f90``.

    The bounds and EPI/DELE variables are REAL(8), but ``0.1``, ``4.e+5``,
    ``1.``, ``1.e+6`` and ``FLOAT(...)`` are default REAL.  Those expressions
    are therefore rounded in binary32 before assignment/promotion.
    """
    n = int(ncn2)
    if n < 4:
        raise ValueError("ener requires at least four bins")
    n2 = max(2, n // 50)
    n3 = n - n2
    if n3 < 2:
        raise ValueError("ener first segment is too small")
    out = np.zeros(n, dtype=float)

    ebnd1 = source_default_real(0.1)
    ebnd2 = source_default_real(4.0e5)
    ebnd2o = ebnd2
    out[0] = ebnd1
    dele = (ebnd2 / ebnd1) ** source_default_real_reciprocal(n3 - 1)
    for i in range(1, n3):
        out[i] = out[i - 1] * dele

    ebnd2 = source_default_real(1.0e6)
    ebnd1 = ebnd2o
    dele = (ebnd2 / ebnd1) ** source_default_real_reciprocal(n2 - 1)
    for i in range(n3, n):
        out[i] = out[i - 1] * dele
    return out
