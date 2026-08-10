# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: leqt2f.f90 / ludcmp.f90 / lubksb.f90 / mprove.f90 / msolvelucy.f90
#   Role: Source-equivalent linear solve/refinement helpers for statistical equilibrium.
#   Relation: Mathematically/source-order equivalent numerical kernels; normalization and clamping behavior are qualified.
#   Concordance: LEVEL-001; MATRIX-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Source translations of XSTAR's Numerical Recipes linear algebra helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from .solver_backend import call_cpp_leqt2f, get_solver_backend, resolve_active_backend


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
    method: str = "leqt2f_ludcmp_lubksb_mprove_source_order"


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the source row product operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual s. 11.4.1, multilevel statistical-equilibrium matrix solution.
# XSTAR-FUNCTION-COMMENT-END
def _source_row_product(matrix: np.ndarray, row: int, vector: np.ndarray, n: int) -> float:
    """Fortran-order row dot product using explicit left-to-right accumulation."""
    total = 0.0
    for col in range(n):
        total = total + float(matrix[row, col]) * float(vector[col])
    return float(total)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Factor the dense kinetic matrix using the source-compatible LU decomposition and pivot scaling used by the translated solver.
# Reference context: XSTAR Manual s. 11.4.1, multilevel statistical-equilibrium matrix solution.
# XSTAR-FUNCTION-COMMENT-END
def ludcmp(a: np.ndarray, *, tiny: float = 1.0e-20) -> LUDecomposition:
    """Translate ``ludcmp.f90`` with explicit source-order loops."""
    lu = np.asarray(a, dtype=float).copy()
    if lu.ndim != 2 or lu.shape[0] != lu.shape[1]:
        raise ValueError("ludcmp requires a square matrix")
    n = lu.shape[0]
    vv = np.zeros(n, dtype=float)
    singular = []

    # Fortran lines 38-51: row scaling vector, left-to-right scan.
    for i in range(n):
        aamax = 0.0
        for j in range(n):
            value = abs(float(lu[i, j]))
            if value > aamax:
                aamax = value
        if aamax == 0.0:
            singular.append(i + 1)
            # The Fortran routine returns immediately.  Python returns a
            # status object so callers can fail explicitly instead of
            # consuming uninitialized pivots.
            return LUDecomposition(
                lu=lu,
                pivots=np.zeros(n, dtype=np.int64),
                determinant_sign=1.0,
                singular_rows=tuple(singular),
            )
        vv[i] = 1.0 / aamax

    pivots = np.zeros(n, dtype=np.int64)
    d = 1.0
    # Fortran lines 52-102: Numerical Recipes LU decomposition with >= pivot tie.
    for j in range(n):
        if j > 0:
            for i in range(j):
                total = float(lu[i, j])
                if i > 0:
                    for k in range(i):
                        total = total - float(lu[i, k]) * float(lu[k, j])
                    lu[i, j] = total
        aamax = 0.0
        imax = -1
        for i in range(j, n):
            total = float(lu[i, j])
            if j > 0:
                for k in range(j):
                    total = total - float(lu[i, k]) * float(lu[k, j])
                lu[i, j] = total
            dum = float(vv[i]) * abs(total)
            if dum >= aamax:
                imax = i
                aamax = dum
        if imax < 0:
            imax = 0
        if j != imax:
            for k in range(n):
                dum = float(lu[imax, k])
                lu[imax, k] = lu[j, k]
                lu[j, k] = dum
            d = -d
            vv[imax] = vv[j]
        pivots[j] = imax
        if j != n - 1:
            if lu[j, j] == 0.0:
                lu[j, j] = tiny
            dum = 1.0 / float(lu[j, j])
            for i in range(j + 1, n):
                lu[i, j] = float(lu[i, j]) * dum
    if n and lu[n - 1, n - 1] == 0.0:
        lu[n - 1, n - 1] = tiny
    return LUDecomposition(lu=lu, pivots=pivots, determinant_sign=d, singular_rows=tuple(singular))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Back-substitute through an LU factorization to recover one population/update vector.
# Reference context: XSTAR Manual s. 11.4.1, multilevel statistical-equilibrium matrix solution.
# XSTAR-FUNCTION-COMMENT-END
def lubksb(decomposition: LUDecomposition, b: np.ndarray) -> np.ndarray:
    """Translate ``lubksb.f90`` forward/back substitution in source order."""
    a = decomposition.lu
    pivots = decomposition.pivots
    x = np.asarray(b, dtype=float).copy()
    n = a.shape[0]
    if x.shape != (n,):
        raise ValueError("lubksb right-hand side has incompatible shape")
    ii = 0  # Fortran uses 0 as unset sentinel.
    for i in range(n):
        ll = int(pivots[i])
        total = float(x[ll])
        x[ll] = x[i]
        if ii != 0:
            for j in range(ii - 1, i):
                total = total - float(a[i, j]) * float(x[j])
        elif total != 0.0:
            ii = i + 1
        x[i] = total
    for i in range(n - 1, -1, -1):
        total = float(x[i])
        if i < n - 1:
            for j in range(i + 1, n):
                total = total - float(a[i, j]) * float(x[j])
        x[i] = total / float(a[i, i])
    return x


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the mprove operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual s. 11.4.1, multilevel statistical-equilibrium matrix solution.
# XSTAR-FUNCTION-COMMENT-END
def mprove(a: np.ndarray, decomposition: LUDecomposition, b: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Translate one iterative-improvement pass from ``mprove.f90``."""
    original = np.asarray(a, dtype=float)
    rhs = np.asarray(b, dtype=float)
    improved = np.asarray(x, dtype=float).copy()
    n = improved.shape[0]
    residual = np.zeros(n, dtype=float)
    # Fortran lines 32-38: sdp starts at -b(i) and accumulates j=1..n.
    for i in range(n):
        sdp = -float(rhs[i])
        for j in range(n):
            sdp = sdp + float(original[i, j]) * float(improved[j])
        residual[i] = sdp
    correction = lubksb(decomposition, residual)
    for i in range(n):
        improved[i] = float(improved[i]) - float(correction[i])
    return improved


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the leqt2f python operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual s. 11.4.1, multilevel statistical-equilibrium matrix solution.
# XSTAR-FUNCTION-COMMENT-END
def _leqt2f_python(a: np.ndarray, b: np.ndarray, *, clamp_source_range: bool = True) -> LinearSolveResult:
    """Pure-Python source-order LU/refinement implementation."""
    original = np.asarray(a, dtype=float)
    rhs = np.asarray(b, dtype=float)
    if original.ndim != 2 or original.shape[0] != original.shape[1]:
        raise ValueError("leqt2f requires a square matrix")
    if rhs.shape != (original.shape[0],):
        raise ValueError("leqt2f right-hand side has incompatible shape")
    n = original.shape[0]

    decomposition = ludcmp(original)
    if decomposition.singular_rows:
        raise XSTARLinearAlgebraError(
            "singular matrix rows in ludcmp: " + ",".join(map(str, decomposition.singular_rows))
        )
    x = lubksb(decomposition, rhs)
    x = mprove(original, decomposition, rhs, x)

    if clamp_source_range:
        for i in range(n):
            if x[i] < 1.0e-36:
                x[i] = 0.0
            if x[i] > 1.0e36:
                x[i] = 1.0e36

    residual = np.zeros(n, dtype=float)
    max_scaled = 0.0
    # Fortran leqt2f check uses max(0,btmp) and source-order accumulation.
    for row in range(n):
        total = 0.0
        tmpmx = 0.0
        for col in range(n):
            btmp = float(x[col])
            tmp = float(original[row, col]) * max(0.0, btmp)
            if abs(tmp) >= tmpmx:
                tmpmx = max(tmpmx, abs(tmp))
            total = total + tmp
        total = total - float(rhs[row])
        residual[row] = total
        err = total / max(1.0e-24, tmpmx)
        max_scaled = max(max_scaled, abs(err))
    return LinearSolveResult(solution=x, residual=residual, max_scaled_residual=float(max_scaled))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Solve the source-shaped linear system used by the level-population operator while preserving the qualified numerical path.
# Reference context: XSTAR Manual s. 11.4.1, multilevel statistical-equilibrium matrix solution.
# XSTAR-FUNCTION-COMMENT-END
def leqt2f(a: np.ndarray, b: np.ndarray, *, clamp_source_range: bool = True) -> LinearSolveResult:
    """Translate ``leqt2f.f90`` with optional C++ acceleration.

    Backend selection is process-wide via ``XSTAR_ATOMIC_SOLVER_BACKEND`` or
    ``set_solver_backend`` from :mod:`solver_backend`.  ``python`` remains the
    reference.  ``auto`` uses the C++ shared-object library when it is loadable
    and falls back to Python.  ``cpp`` requires the shared library and raises if
    it is missing.
    """
    backend = get_solver_backend()
    if backend in ("cpp", "auto"):
        try:
            solution, residual, max_scaled = call_cpp_leqt2f(
                a, b, clamp_source_range=clamp_source_range
            )
            return LinearSolveResult(
                solution=np.asarray(solution, dtype=float),
                residual=np.asarray(residual, dtype=float),
                max_scaled_residual=float(max_scaled),
                method="leqt2f_cpp_so_source_order",
            )
        except Exception:
            if backend == "cpp":
                raise
            # auto mode is explicitly opportunistic.  Keep the source-faithful
            # Python solve as the correctness fallback.
    return _leqt2f_python(a, b, clamp_source_range=clamp_source_range)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the solver backend status operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual s. 11.4.1, multilevel statistical-equilibrium matrix solution.
# XSTAR-FUNCTION-COMMENT-END
def solver_backend_status() -> dict[str, object]:
    status = resolve_active_backend()
    return {
        "requested": status.requested,
        "active": status.active,
        "cpp_available": status.cpp_available,
        "cpp_import_error": status.cpp_import_error,
        "cpp_library_path": status.cpp_library_path,
        "cpp_backend_name": status.cpp_backend_name,
        "cpp_abi_version": status.cpp_abi_version,
    }
