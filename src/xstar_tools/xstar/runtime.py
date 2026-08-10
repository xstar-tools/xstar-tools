"""Small compatibility layer for source-faithful Fortran translation.

The first Python port deliberately preserves Fortran indexing and mutation
semantics.  Refactoring to idiomatic zero-based arrays should happen only after
the translated execution path is validated against the original program.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence, Tuple, Union

import numpy as np

Index = Union[int, slice, Tuple[Union[int, slice], ...]]


class FortranRuntimeError(RuntimeError):
    """Raised when translated source violates an explicit Fortran invariant."""


@dataclass
class FortranArray:
    """NumPy array with explicit 1-based integer indexing.

    The backing array contains a zero guard plane along every dimension.  Integer
    indices therefore map directly to the original Fortran subscripts.  Slices
    retain normal Python semantics and should be used only by translated helper
    code that documents the intended bounds.
    """

    data: np.ndarray

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the zeros operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Runtime state plumbing; no direct paper/manual equation.
    # XSTAR-FUNCTION-COMMENT-END
    @classmethod
    def zeros(cls, shape: Sequence[int], dtype: Any = float) -> "FortranArray":
        padded = tuple(int(n) + 1 for n in shape)
        return cls(np.zeros(padded, dtype=dtype))

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the full operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Runtime state plumbing; no direct paper/manual equation.
    # XSTAR-FUNCTION-COMMENT-END
    @classmethod
    def full(
        cls, shape: Sequence[int], fill_value: Any, dtype: Any = None
    ) -> "FortranArray":
        padded = tuple(int(n) + 1 for n in shape)
        return cls(np.full(padded, fill_value, dtype=dtype))

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the fortran shape operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Runtime state plumbing; no direct paper/manual equation.
    # XSTAR-FUNCTION-COMMENT-END
    @property
    def fortran_shape(self) -> Tuple[int, ...]:
        return tuple(int(n) - 1 for n in self.data.shape)

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the validate index operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Runtime state plumbing; no direct paper/manual equation.
    # XSTAR-FUNCTION-COMMENT-END
    def _validate_index(self, index: Index) -> None:
        indices = index if isinstance(index, tuple) else (index,)
        for item in indices:
            if isinstance(item, int) and item < 1:
                raise FortranRuntimeError(
                    f"Fortran integer index must be >=1, received {item}"
                )

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Return the requested logical item while preserving this object's indexing convention.
    # Reference context: Runtime state plumbing; no direct paper/manual equation.
    # XSTAR-FUNCTION-COMMENT-END
    def __getitem__(self, index: Index) -> Any:
        self._validate_index(index)
        return self.data[index]

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Update the requested logical item while preserving this object's indexing convention.
    # Reference context: Runtime state plumbing; no direct paper/manual equation.
    # XSTAR-FUNCTION-COMMENT-END
    def __setitem__(self, index: Index, value: Any) -> None:
        self._validate_index(index)
        self.data[index] = value

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the active view operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: Runtime state plumbing; no direct paper/manual equation.
    # XSTAR-FUNCTION-COMMENT-END
    def active_view(self) -> np.ndarray:
        """Return the zero-based view excluding all guard planes."""
        return self.data[tuple(slice(1, None) for _ in self.data.shape)]


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fortran nint operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Runtime state plumbing; no direct paper/manual equation.
# XSTAR-FUNCTION-COMMENT-END
def fortran_nint(value: Any) -> Any:
    """Fortran ``NINT``: nearest integer, ties away from zero."""
    arr = np.asarray(value)
    out = np.where(arr >= 0, np.floor(arr + 0.5), np.ceil(arr - 0.5)).astype(int)
    return int(out) if out.ndim == 0 else out


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fortran sign operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Runtime state plumbing; no direct paper/manual equation.
# XSTAR-FUNCTION-COMMENT-END
def fortran_sign(a: Any, b: Any) -> Any:
    """Fortran ``SIGN(a,b)``."""
    return np.copysign(np.abs(a), b)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fortran mod operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: Runtime state plumbing; no direct paper/manual equation.
# XSTAR-FUNCTION-COMMENT-END
def fortran_mod(a: Any, p: Any) -> Any:
    """Fortran ``MOD(a,p)`` with truncation toward zero."""
    a_arr = np.asarray(a)
    p_arr = np.asarray(p)
    result = a_arr - np.trunc(a_arr / p_arr) * p_arr
    return result.item() if result.ndim == 0 else result
