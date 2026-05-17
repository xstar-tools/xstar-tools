"""Source translations of XSTAR's Numerical Recipes linear algebra helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np


class XSTARLinearAlgebraError(RuntimeError):
    pass


@dataclass(frozen=True)
class LUDecomposition:
    lu: np.ndarray
    pivots: np.ndarray
    determinant_sign: float
    singular_rows: Tuple[int, ...] = ()


@dataclass(frozen=True)
class LinearSolveResult:
    solution: np.ndarray
    residual: np.ndarray
    max_scaled_residual: float
    method: str = "leqt2f_ludcmp_lubksb_mprove"


def ludcmp(a: np.ndarray, *, tiny: float = 1.0e-20) -> LUDecomposition:
    """Translate ``ludcmp.f90`` with zero-based NumPy storage."""
    lu = np.asarray(a, dtype=float).copy()
    if lu.ndim != 2 or lu.shape[0] != lu.shape[1]:
        raise ValueError("ludcmp requires a square matrix")
    n = lu.shape[0]
    vv = np.zeros(n, dtype=float)
    singular = []
    for i in range(n):
        aamax = float(np.max(np.abs(lu[i, :]))) if n else 0.0
        if aamax == 0.0:
            singular.append(i + 1)
            vv[i] = 1.0
        else:
            vv[i] = 1.0 / aamax
    pivots = np.zeros(n, dtype=np.int64)
    d = 1.0
    for j in range(n):
        for i in range(j):
            value = lu[i, j]
            if i > 0:
                value -= float(np.dot(lu[i, :i], lu[:i, j]))
            lu[i, j] = value
        aamax = 0.0
        imax = j
        for i in range(j, n):
            value = lu[i, j]
            if j > 0:
                value -= float(np.dot(lu[i, :j], lu[:j, j]))
            lu[i, j] = value
            dum = vv[i] * abs(value)
            if dum >= aamax:
                imax = i
                aamax = dum
        if j != imax:
            lu[[j, imax], :] = lu[[imax, j], :]
            d = -d
            vv[imax] = vv[j]
        pivots[j] = imax
        if j != n - 1:
            if lu[j, j] == 0.0:
                lu[j, j] = tiny
            lu[j + 1 :, j] /= lu[j, j]
    if n and lu[n - 1, n - 1] == 0.0:
        lu[n - 1, n - 1] = tiny
    return LUDecomposition(lu=lu, pivots=pivots, determinant_sign=d, singular_rows=tuple(singular))


def lubksb(decomposition: LUDecomposition, b: np.ndarray) -> np.ndarray:
    """Translate ``lubksb.f90`` forward/back substitution."""
    a = decomposition.lu
    pivots = decomposition.pivots
    x = np.asarray(b, dtype=float).copy()
    n = a.shape[0]
    if x.shape != (n,):
        raise ValueError("lubksb right-hand side has incompatible shape")
    ii = -1
    for i in range(n):
        ll = int(pivots[i])
        value = x[ll]
        x[ll] = x[i]
        if ii >= 0:
            value -= float(np.dot(a[i, ii:i], x[ii:i]))
        elif value != 0.0:
            ii = i
        x[i] = value
    for i in range(n - 1, -1, -1):
        value = x[i]
        if i < n - 1:
            value -= float(np.dot(a[i, i + 1 :], x[i + 1 :]))
        x[i] = value / a[i, i]
    return x


def mprove(a: np.ndarray, decomposition: LUDecomposition, b: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Translate one iterative-improvement pass from ``mprove.f90``."""
    original = np.asarray(a, dtype=float)
    rhs = np.asarray(b, dtype=float)
    improved = np.asarray(x, dtype=float).copy()
    residual = original @ improved - rhs
    correction = lubksb(decomposition, residual)
    improved -= correction
    return improved


def leqt2f(a: np.ndarray, b: np.ndarray, *, clamp_source_range: bool = True) -> LinearSolveResult:
    """Translate ``leqt2f.f90`` including LU solve and one improvement pass."""
    original = np.asarray(a, dtype=float)
    rhs = np.asarray(b, dtype=float)
    if original.ndim != 2 or original.shape[0] != original.shape[1]:
        raise ValueError("leqt2f requires a square matrix")
    if rhs.shape != (original.shape[0],):
        raise ValueError("leqt2f right-hand side has incompatible shape")
    decomposition = ludcmp(original)
    if decomposition.singular_rows:
        # The original routine prints and returns from ludcmp.  A Python caller
        # needs an explicit status so it cannot consume an uninitialized solve.
        raise XSTARLinearAlgebraError(
            "singular matrix rows in ludcmp: " + ",".join(map(str, decomposition.singular_rows))
        )
    x = lubksb(decomposition, rhs)
    x = mprove(original, decomposition, rhs, x)
    if clamp_source_range:
        x = np.where(x < 1.0e-36, 0.0, x)
        x = np.where(x > 1.0e36, 1.0e36, x)
    residual = original @ x - rhs
    scales = np.maximum(np.max(np.abs(original * x[np.newaxis, :]), axis=1), 1.0e-24)
    max_scaled = float(np.max(np.abs(residual) / scales)) if residual.size else 0.0
    return LinearSolveResult(solution=x, residual=residual, max_scaled_residual=max_scaled)
