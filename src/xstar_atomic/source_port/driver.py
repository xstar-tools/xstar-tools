"""Executable stage skeleton for the source-faithful Python XSTAR port."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Sequence

import numpy as np

from .state import XSTARPythonState


class XSTARSourceRoutine(str, Enum):
    """Source-level calls used by the zone and ``xstarcalc`` drivers.

    These are deliberately separate from the older coarse :class:`XSTARStage`
    groups.  Milestone 4 needs the original nested call order because
    ``dsec`` repeatedly invokes ``calc_hmc_all`` before the final fixed-state
    call and the emissivity routines.
    """

    STEP = "step"
    TRNFRC = "trnfrc"
    BREMSMAP = "bremsmap"
    DSEC = "dsec"
    CALC_HMC_ALL = "calc_hmc_all"
    CALC_EMISAB_ALL = "calc_emisab_all"
    CALC_EMIS_ALL = "calc_emis_all"
    HEATT = "heatt"
    STPCUT = "stpcut"
    TRNFRN = "trnfrn"
    GSSMOOTH = "gsmooth"
    UNSAVD = "unsavd"


XSTARCALC_SOURCE_ORDER: Sequence[XSTARSourceRoutine] = (
    XSTARSourceRoutine.BREMSMAP,
    XSTARSourceRoutine.DSEC,
    XSTARSourceRoutine.CALC_HMC_ALL,
    XSTARSourceRoutine.CALC_EMISAB_ALL,
    XSTARSourceRoutine.CALC_EMIS_ALL,
)

XSTARCALC_FIXED_STATE_ORDER: Sequence[XSTARSourceRoutine] = (
    XSTARSourceRoutine.BREMSMAP,
    XSTARSourceRoutine.CALC_HMC_ALL,
    XSTARSourceRoutine.CALC_EMISAB_ALL,
    XSTARSourceRoutine.CALC_EMIS_ALL,
)

ZONE_SOURCE_ORDER: Sequence[XSTARSourceRoutine] = (
    XSTARSourceRoutine.STEP,
    XSTARSourceRoutine.TRNFRC,
    *XSTARCALC_SOURCE_ORDER,
    XSTARSourceRoutine.HEATT,
    XSTARSourceRoutine.STPCUT,
    XSTARSourceRoutine.TRNFRN,
)


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


class UnportedXSTARSourceRoutine(NotImplementedError):
    """Raised when a source-level routine is absent from a requested plan."""

    def __init__(self, routine: XSTARSourceRoutine, *, state: XSTARPythonState | None = None):
        self.routine = routine
        self.state = state
        super().__init__(
            f"XSTAR Python source port has not implemented routine {routine.value!r}"
        )


class UnportedXSTARRoutine(NotImplementedError):
    """Raised at the first untranslated source stage."""

    def __init__(
        self,
        stage: XSTARStage,
        source_routines: Sequence[str],
        *,
        state: XSTARPythonState | None = None,
    ):
        self.stage = stage
        self.source_routines = tuple(source_routines)
        self.state = state
        message = (
            f"XSTAR Python source port has not implemented stage {stage.value!r}; "
            f"source routines: {', '.join(self.source_routines) or 'not recorded'}"
        )
        super().__init__(message)


StageHandler = Callable[[XSTARPythonState], None]
RoutineHandler = Callable[[XSTARPythonState], None]


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
    routine_handlers: Dict[XSTARSourceRoutine, RoutineHandler] = field(default_factory=dict)
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

    def register_source_routine(
        self,
        routine: XSTARSourceRoutine | str,
        handler: RoutineHandler,
    ) -> None:
        """Register one translated source routine for nested driver plans."""
        key = routine if isinstance(routine, XSTARSourceRoutine) else XSTARSourceRoutine(str(routine))
        self.routine_handlers[key] = handler

    def implemented_source_routines(self) -> List[XSTARSourceRoutine]:
        return [routine for routine in XSTARSourceRoutine if routine in self.routine_handlers]

    def run_source_routines(
        self,
        routines: Sequence[XSTARSourceRoutine],
        state: Optional[XSTARPythonState] = None,
    ) -> XSTARPythonState:
        """Execute an explicit source-level call plan in the supplied order."""
        result = state or XSTARPythonState()
        for routine in routines:
            handler = self.routine_handlers.get(routine)
            if handler is None:
                raise UnportedXSTARSourceRoutine(routine, state=result)
            handler(result)
            result.provenance.setdefault("completed_source_routines", []).append(routine.value)
        return result

    def run_xstarcalc(
        self,
        state: Optional[XSTARPythonState] = None,
        *,
        fixed_state: bool = False,
    ) -> XSTARPythonState:
        """Run ``xstarcalc.f90`` in literal local-zone source order.

        The translated driver preserves the control semantics surrounding the
        nested calls, not only the call list itself:

        * ``bremsmap`` executes before thermal iteration;
        * ``lpri`` is saved and forced to zero for the local calculation;
        * ``dsec`` is skipped when ``nlimdt == 0`` or ``fixed_state`` is true;
        * the final ``calc_hmc_all`` call always executes after ``dsec``;
        * ``calc_emisab_all`` precedes ``calc_emis_all``;
        * ``nry = nbinc(13.6, epi, ncn2) + 2`` is evaluated after emissivity;
        * the caller's ``lpri`` value is restored on exit.

        Individual routine implementations remain explicitly registered.
        Missing translated routines therefore still fail immediately.
        """
        result = state or XSTARPythonState()

        def execute(routine: XSTARSourceRoutine) -> None:
            handler = self.routine_handlers.get(routine)
            if handler is None:
                raise UnportedXSTARSourceRoutine(routine, state=result)
            handler(result)
            result.provenance.setdefault("completed_source_routines", []).append(
                routine.value
            )

        execute(XSTARSourceRoutine.BREMSMAP)

        lpri_saved = int(result.control.get("lpri", 0))
        result.control["lprisv"] = lpri_saved
        result.control["lpri"] = 0
        dsec_executed = False
        try:
            nlimdt = int(result.control.get("nlimdt", 1))
            if not fixed_state and nlimdt != 0:
                execute(XSTARSourceRoutine.DSEC)
                dsec_executed = True
            else:
                result.provenance.setdefault("skipped_source_routines", []).append(
                    XSTARSourceRoutine.DSEC.value
                )

            execute(XSTARSourceRoutine.CALC_HMC_ALL)
            execute(XSTARSourceRoutine.CALC_EMISAB_ALL)
            execute(XSTARSourceRoutine.CALC_EMIS_ALL)

            if result.radiation.epi is not None:
                from .radiation import nbinc

                ncn2 = int(
                    result.control.get(
                        "ncn2", len(np.asarray(result.radiation.epi).reshape(-1))
                    )
                )
                result.control["nry"] = int(
                    nbinc(13.6, result.radiation.epi, ncn2) + 2
                )
        finally:
            result.control["lpri"] = lpri_saved

        result.local_zone.provenance["xstarcalc"] = {
            "source_file": "xstar/xstarlib/src/xstarcalc.f90",
            "fixed_state_mode": bool(fixed_state),
            "dsec_executed": bool(dsec_executed),
            "nlimdt": int(result.control.get("nlimdt", 1)),
            "lpri_saved": lpri_saved,
            "lpri_restored": int(result.control.get("lpri", 0)),
            "nry": (int(result.control["nry"]) if "nry" in result.control else None),
            "completed_source_routines": list(
                result.provenance.get("completed_source_routines", [])
            ),
        }
        return result


    def run_radial_shell(
        self,
        state: Optional[XSTARPythonState] = None,
        *,
        zone_index: int,
        pass_index: int = 1,
        direction: int = 1,
        fixed_state: bool = False,
    ) -> XSTARPythonState:
        """Run one bounded radial-shell caller sequence from ``xstar.f90``.

        ``zone_index`` and ``pass_index`` are the one-based ``jkp`` and ``kk``
        values *after* the source loop increments ``jkp``.  The method
        preserves the source-level control boundaries used by the first radial
        milestone:

        * reverse/multipass shells first require ``unsavd``;
        * first-pass zone 1 skips ``step`` and sets ``delr=0``;
        * later first-pass zones execute ``step``;
        * ``trnfrc`` precedes the complete accepted local ``xstarcalc``;
        * nonzero turbulent velocity requires ``gsmooth`` before ``heatt``;
        * translated ``heatt`` updates continuum, line, and RRC transfer state;
        * the inline radius/column update precedes ``stpcut`` and ``trnfrn``.

        Output calls (``pprint``, ``savd``, and spectrum writers) are
        intentionally outside this bounded routine.
        """
        result = state or XSTARPythonState()
        jkp = int(zone_index)
        kk = int(pass_index)
        ldir = int(direction)
        if jkp < 1:
            raise ValueError("zone_index must be one-based and positive")
        if kk < 1:
            raise ValueError("pass_index must be one-based and positive")
        if ldir not in (-1, 1):
            raise ValueError("direction must be -1 or 1")

        result.transfer.zone_index = jkp
        result.transfer.pass_index = kk
        result.transfer.direction = ldir
        result.control["jkp"] = jkp
        result.control["kk"] = kk
        result.control["ldir"] = ldir

        def execute(routine: XSTARSourceRoutine) -> None:
            handler = self.routine_handlers.get(routine)
            if handler is None:
                raise UnportedXSTARSourceRoutine(routine, state=result)
            handler(result)
            result.provenance.setdefault("completed_source_routines", []).append(
                routine.value
            )

        completed_before = len(
            result.provenance.get("completed_source_routines", [])
        )
        skipped_before = len(result.provenance.get("skipped_source_routines", []))

        # xstar.f90 calls unsavd before any local work on passes after the first.
        if kk > 1:
            execute(XSTARSourceRoutine.UNSAVD)
            nlimd = int(result.control.get("nlimd", result.control.get("nlimdt", 1)))
            result.control["nlimdt"] = 0 if ldir > 0 else nlimd
        else:
            # Save the initial density/radius for the analytic density law.
            lcdd = int(result.control.get("lcdd", 1))
            if lcdd == 1 and jkp == 1:
                result.control["xpx0"] = float(result.plasma.xpx)
                result.control["r0"] = float(result.transfer.radius)

            result.control["nlimdt"] = int(
                result.control.get("nlimd", result.control.get("nlimdt", 1))
            )
            result.transfer.step_size = 0.0
            result.control["delr"] = 0.0
            result.control["ectt"] = 1.0
            if jkp > 1:
                execute(XSTARSourceRoutine.STEP)
            else:
                result.provenance.setdefault("skipped_source_routines", []).append(
                    XSTARSourceRoutine.STEP.value
                )

        radius = float(result.transfer.radius)
        xpx = float(result.plasma.xpx)
        xlum = float(result.control.get("xlum", 0.0))
        if radius <= 0.0 or xpx <= 0.0:
            raise ValueError("radial shell requires positive radius and hydrogen density")
        r19 = radius * float(np.float32(1.0e-19))
        xi = xlum / r19 / r19 / xpx
        result.control["xi"] = xi
        result.control["zeta"] = float(np.log10(xi)) if xi > 0.0 else float("-inf")

        execute(XSTARSourceRoutine.TRNFRC)

        tinf = float(result.control.get("tinf", 0.0))
        if result.plasma.temperature < tinf * 1.02:
            result.plasma.temperature = tinf * 1.01

        self.run_xstarcalc(result, fixed_state=fixed_state)

        vturbi = float(result.control.get("vturbi", 0.0))
        if vturbi > float(np.float32(1.0e-34)):
            execute(XSTARSourceRoutine.GSSMOOTH)

        execute(XSTARSourceRoutine.HEATT)

        # Inline xstar.f90 position, density, radial-depth, and column updates.
        delr = float(result.transfer.step_size)
        radexp = float(result.control.get("radexp", 0.0))
        if radexp < -99.0:
            raise NotImplementedError(
                "tabulated radial density update (radexp < -99) is not part of "
                "the bounded radial-shell milestone"
            )
        result.transfer.radius = float(result.transfer.radius) + delr
        lcdd = int(result.control.get("lcdd", 1))
        if lcdd == 1:
            xpx0 = float(result.control.get("xpx0", result.plasma.xpx))
            r0 = float(result.control.get("r0", result.transfer.radius))
            if r0 <= 0.0:
                raise ValueError("r0 must be positive for the analytic density law")
            result.plasma.xpx = xpx0 * (result.transfer.radius / r0) ** radexp
        result.transfer.radial_depth = float(result.transfer.radial_depth) + delr
        result.transfer.column = float(result.transfer.column) + float(result.plasma.xpx) * delr
        result.control["r"] = float(result.transfer.radius)
        result.control["rdel"] = float(result.transfer.radial_depth)
        result.control["xcol"] = float(result.transfer.column)
        result.control["delr"] = delr

        execute(XSTARSourceRoutine.STPCUT)
        execute(XSTARSourceRoutine.TRNFRN)

        completed = tuple(
            result.provenance.get("completed_source_routines", [])[completed_before:]
        )
        skipped = tuple(
            result.provenance.get("skipped_source_routines", [])[skipped_before:]
        )
        result.transfer.provenance["radial_shell"] = {
            "source_file": "xstar/src/xstar/xstar.f90",
            "zone_index": jkp,
            "pass_index": kk,
            "direction": ldir,
            "completed_source_routines": list(completed),
            "skipped_source_routines": list(skipped),
            "output_writers_executed": False,
            "fixed_state_mode": bool(fixed_state),
        }
        return result

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
                    stage,
                    self.source_routines.get(stage, ()),
                    state=result,
                )
            handler(result)
            result.provenance.setdefault("completed_stages", []).append(stage.value)
            if stop_after is stage:
                break
        return result
