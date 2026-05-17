"""Registry-based dispatcher mirroring the top-level structure of ``ucalc.f90``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional, Sequence, Tuple


UCalcEvaluator = Callable[..., Any]


@dataclass(frozen=True)
class UCalcBranch:
    data_type: int
    source_routines: Tuple[str, ...]
    evaluator: UCalcEvaluator
    validation_status: str
    notes: str = ""


class UCalcDispatcher:
    """Explicit registry for translated ``ucalc`` data-type branches."""

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
                f"XSTAR ucalc data type {data_type} has not yet been translated"
            ) from exc

    def evaluate(self, data_type: int, /, *args: Any, **kwargs: Any) -> Any:
        return self.branch(data_type).evaluator(*args, **kwargs)


def default_ucalc_dispatcher() -> UCalcDispatcher:
    """Create the source-port dispatcher from currently validated branches."""
    from xstar_atomic.rates_type50 import evaluate_type50_ucalc_record
    from xstar_atomic.rates_type51 import evaluate_type51_ucalc_record
    from xstar_atomic.rates_type53 import evaluate_type53_ucalc_record
    from xstar_atomic.rates_type71 import evaluate_type71_ucalc_record

    dispatcher = UCalcDispatcher()
    dispatcher.register(
        UCalcBranch(
            50,
            ("ucalc.f90", "pescv.f90", "pescl.f90"),
            evaluate_type50_ucalc_record,
            "validated_selected_system",
            "Exact decay; pumping requires explicit live radiation unless identically zero.",
        )
    )
    dispatcher.register(
        UCalcBranch(
            51,
            ("ucalc.f90", "upsil.f90", "upsiln.f90"),
            evaluate_type51_ucalc_record,
            "validated_selected_system",
            "Five-point records directly validated; nine-point branch needs broader coverage.",
        )
    )
    dispatcher.register(
        UCalcBranch(
            53,
            ("ucalc.f90", "phint53.f90", "rnist.f90"),
            evaluate_type53_ucalc_record,
            "translated_pending_real_context_parity",
            "Exact live-rate kernel; current real O VII context association remains unresolved.",
        )
    )
    dispatcher.register(
        UCalcBranch(
            71,
            ("ucalc.f90", "calt71.f90"),
            evaluate_type71_ucalc_record,
            "validated_selected_system",
        )
    )
    return dispatcher
