# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: ucalc.f90 computed-GOTO data-type dispatch
#   Role: Compatibility registry over the single source-faithful UCalc implementation.
#   Relation: Dispatch abstraction only; the integer data type selects the evaluator exactly as the source branch label does.
#   Concordance: MATRIX-001; DB-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# Atomic-data note (XSTAR Manual Ch. 12; Mendoza et al. 2021, Appendix A):
#   Rule: data type selects the record formula/interpretation; rate type selects downstream use.
#   The dispatcher key is data type, not rate type. Rate type remains record metadata consumed after UCalc
#   returns standard rates/endpoints.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Backward-compatible registry facade for the complete ``ucalc`` subsystem.

New code should use :class:`xstar_tools.xstar.ucalc.SourceFaithfulUCalc`
directly.  The small registry class remains for callers introduced in v0.4.0,
but ``default_ucalc_dispatcher`` now exposes all source labels 1..102 and
delegates to the single authoritative implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Tuple


UCalcEvaluator = Callable[..., Any]


@dataclass(frozen=True)
class UCalcBranch:
    data_type: int
    source_routines: Tuple[str, ...]
    evaluator: UCalcEvaluator
    validation_status: str
    notes: str = ""


class UCalcDispatcher:
    """Explicit registry retained for compatibility with the v0.4.0 API."""

    def __init__(self) -> None:
        self._branches: Dict[int, UCalcBranch] = {}

    def register(self, branch: UCalcBranch) -> None:
        if branch.data_type in self._branches:
            raise ValueError(f"ucalc data type {branch.data_type} already registered")
        self._branches[branch.data_type] = branch

    @property
    def supported_data_types(self) -> Tuple[int, ...]:
        return tuple(sorted(self._branches))

    def branch(self, data_type: int) -> UCalcBranch:
        try:
            return self._branches[int(data_type)]
        except KeyError as exc:
            raise NotImplementedError(
                f"XSTAR ucalc data type {data_type} is outside the source range 1..102"
            ) from exc

    def evaluate(self, data_type: int, /, *args: Any, **kwargs: Any) -> Any:
        return self.branch(data_type).evaluator(*args, **kwargs)


def default_ucalc_dispatcher() -> UCalcDispatcher:
    """Return a legacy registry facade over all complete source branches.

    Each evaluator expects ``(UCalcRecord, UCalcContext, strict=True)`` and
    returns ``UCalcResult``.  This preserves the registry-shaped API while
    avoiding a second, incomplete implementation path.
    """

    from .ucalc import SourceFaithfulUCalc

    source = SourceFaithfulUCalc()
    dispatcher = UCalcDispatcher()
    for data_type in source.registered_data_types:
        spec = source.catalog[data_type]

        def evaluate(record: Any, context: Any, *, strict: bool = True, _source=source) -> Any:
            return _source.evaluate(record, context, strict=strict)

        dispatcher.register(
            UCalcBranch(
                data_type=data_type,
                source_routines=spec.source_routines,
                evaluator=evaluate,
                validation_status=spec.validation_status,
                notes=";".join(spec.notes),
            )
        )
    return dispatcher


__all__ = ["UCalcBranch", "UCalcDispatcher", "default_ucalc_dispatcher"]
