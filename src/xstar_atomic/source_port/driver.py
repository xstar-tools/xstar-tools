"""Executable stage skeleton for the source-faithful Python XSTAR port."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Sequence

from .state import XSTARPythonState


class XSTARStage(str, Enum):
    SETUP = "setup"
    READ_ATOMIC_DATABASE = "read_atomic_database"
    BUILD_POINTERS = "build_pointers"
    INITIALIZE_RADIATION = "initialize_radiation"
    ZONE_TRANSFER = "zone_transfer"
    LOCAL_RATES = "local_rates"
    ELEMENT_POPULATIONS = "element_populations"
    IONIZATION_BALANCE = "ionization_balance"
    THERMAL_BALANCE = "thermal_balance"
    EMISSIVITY_OPACITY = "emissivity_opacity"
    CONVERGENCE = "convergence"
    OUTPUT = "output"


SOURCE_ORDER: Sequence[XSTARStage] = (
    XSTARStage.SETUP,
    XSTARStage.READ_ATOMIC_DATABASE,
    XSTARStage.BUILD_POINTERS,
    XSTARStage.INITIALIZE_RADIATION,
    XSTARStage.ZONE_TRANSFER,
    XSTARStage.LOCAL_RATES,
    XSTARStage.ELEMENT_POPULATIONS,
    XSTARStage.IONIZATION_BALANCE,
    XSTARStage.THERMAL_BALANCE,
    XSTARStage.EMISSIVITY_OPACITY,
    XSTARStage.CONVERGENCE,
    XSTARStage.OUTPUT,
)


class UnportedXSTARRoutine(NotImplementedError):
    """Raised at the first untranslated source stage."""

    def __init__(self, stage: XSTARStage, source_routines: Sequence[str]):
        self.stage = stage
        self.source_routines = tuple(source_routines)
        message = (
            f"XSTAR Python source port has not implemented stage {stage.value!r}; "
            f"source routines: {', '.join(self.source_routines) or 'not recorded'}"
        )
        super().__init__(message)


StageHandler = Callable[[XSTARPythonState], None]


_DEFAULT_SOURCE_ROUTINES: Dict[XSTARStage, Sequence[str]] = {
    XSTARStage.SETUP: ("xstarsetup", "init", "rread1"),
    XSTARStage.READ_ATOMIC_DATABASE: ("readtbl", "dbwk2"),
    XSTARStage.BUILD_POINTERS: ("setptrs",),
    XSTARStage.INITIALIZE_RADIATION: ("ener", "starf"),
    XSTARStage.ZONE_TRANSFER: ("trnfrc", "trnfrn", "bremsmap"),
    XSTARStage.LOCAL_RATES: ("ucalc",),
    XSTARStage.ELEMENT_POPULATIONS: (
        "levwkelement", "calc_hmc_ion", "calc_hmc_element", "msolvelucy"
    ),
    XSTARStage.IONIZATION_BALANCE: ("calc_hmc_all", "istruc", "ioneqm"),
    XSTARStage.THERMAL_BALANCE: ("heatt", "dsec"),
    XSTARStage.EMISSIVITY_OPACITY: ("calc_emis_all", "calc_emis_ion"),
    XSTARStage.CONVERGENCE: ("step", "stpcut"),
    XSTARStage.OUTPUT: ("savd", "writespectra", "writespectra2"),
}


@dataclass
class XSTARPythonDriver:
    """Run translated XSTAR stages in original source order.

    A stage must be explicitly registered before execution.  Missing stages
    raise immediately, which prevents an incomplete Python port from silently
    substituting audit data or empirical approximations.
    """

    handlers: Dict[XSTARStage, StageHandler] = field(default_factory=dict)
    source_routines: Dict[XSTARStage, Sequence[str]] = field(
        default_factory=lambda: dict(_DEFAULT_SOURCE_ROUTINES)
    )

    def register(
        self,
        stage: XSTARStage,
        handler: StageHandler,
        *,
        source_routines: Optional[Sequence[str]] = None,
    ) -> None:
        self.handlers[stage] = handler
        if source_routines is not None:
            self.source_routines[stage] = tuple(source_routines)

    def implemented_stages(self) -> List[XSTARStage]:
        return [stage for stage in SOURCE_ORDER if stage in self.handlers]

    def run(
        self,
        state: Optional[XSTARPythonState] = None,
        *,
        stop_after: Optional[XSTARStage] = None,
    ) -> XSTARPythonState:
        result = state or XSTARPythonState()
        for stage in SOURCE_ORDER:
            handler = self.handlers.get(stage)
            if handler is None:
                raise UnportedXSTARRoutine(
                    stage, self.source_routines.get(stage, ())
                )
            handler(result)
            result.provenance.setdefault("completed_stages", []).append(stage.value)
            if stop_after is stage:
                break
        return result
