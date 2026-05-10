"""Public population-solver workflow namespace."""
from __future__ import annotations

from typing import Any

from .workflow import solve_populations


def ion(ion, **kwargs: Any) -> dict:
    """Solve level populations for one ion using the current source-level wrapper."""
    return solve_populations(ion, **kwargs)


__all__ = ["ion", "solve_populations"]
