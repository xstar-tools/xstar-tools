"""Public population-matrix workflow namespace."""
from __future__ import annotations

from typing import Any

from .workflow import build_matrix


def build_ion(ion, **kwargs: Any) -> dict:
    """Return matrix-related products from the current solver workflow."""
    return build_matrix(ion, **kwargs)


__all__ = ["build_ion", "build_matrix"]
