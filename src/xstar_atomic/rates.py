"""Public rate-evaluator dispatch namespace.

This module is the stable import location for source-code-aligned rate helpers.
Only type 50 is implemented as a provenance-complete evaluator in v0.3.132.
Additional data types should be added here only after their source-code context
requirements are explicit.
"""
from __future__ import annotations

from typing import Any

from .rates_type50 import RateEvaluation, evaluate_type50_bound_bound, type50_formula_summary


def type50_bound_bound(**kwargs: Any) -> RateEvaluation:
    """Evaluate the audit-only XSTAR type-50 bound-bound radiative branch."""
    return evaluate_type50_bound_bound(**kwargs)


def type50(**kwargs: Any) -> RateEvaluation:
    """Alias for :func:`type50_bound_bound`."""
    return type50_bound_bound(**kwargs)


def calc_rate(kind: str, /, **kwargs: Any) -> RateEvaluation:
    """Dispatch to a named public rate evaluator."""
    key = str(kind).strip().lower().replace("-", "_")
    if key in {"type50", "type50_bound_bound", "bound_bound_type50"}:
        return type50_bound_bound(**kwargs)
    raise NotImplementedError(f"No public rate evaluator is registered for kind={kind!r}")


__all__ = ["RateEvaluation", "evaluate_type50_bound_bound", "type50_bound_bound", "type50", "calc_rate", "type50_formula_summary"]
