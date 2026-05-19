"""Fixed-state core of XSTAR ``calc_hmc_all.f90``.

This module is the first Milestone-4 source port.  It preserves the outer
``calc_hmc_all`` element loop and source-shaped accounting while reusing the
validated Milestone-3 ``calc_hmc_element`` kernel.  Temperature and electron
fraction are fixed inputs here; ``dsec`` remains the subsequent nonlinear
translation target.

The continuum leaves ``comp2 -> freef -> bremem -> heatf`` are represented by
an explicit callback.  Omitting that callback is allowed for element-loop and
charge-accounting development, but the result then advertises that complete
fixed-state local-zone parity is not yet ready.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .element_equilibrium import (
    ElementEquilibriumContext,
    ElementEquilibriumResult,
    EscapeProbabilityContext,
    solve_element_statistical_equilibrium,
)
from .ucalc import SourceFaithfulUCalc


class CalcHMCAllError(RuntimeError):
    """Raised when the fixed-state local-zone source sequence cannot run."""


@dataclass(frozen=True)
class FixedStateElementRequest:
    """One element passed through the translated ``calc_hmc_all`` loop."""

    element_z: int
    min_ion_stage: int
    max_ion_stage: int
    abundance: float = 1.0
    radiation: Any = None
    escape: EscapeProbabilityContext = field(default_factory=EscapeProbabilityContext)
    covering_fraction: float = 1.0
    turbulent_velocity_km_s: float = 0.0
    neutral_h_density_cm3: float = 0.0
    ionized_h_density_cm3: float = 0.0
    lfast: int = 2
    initial_populations: Optional[np.ndarray] = None
    strict_context: bool = True
    capture_lucy_trace: bool = False

    def validate(self) -> None:
        if self.element_z <= 0:
            raise CalcHMCAllError("element_z must be positive")
        if self.min_ion_stage <= 0 or self.max_ion_stage < self.min_ion_stage:
            raise CalcHMCAllError("invalid ion-stage range")
        if not np.isfinite(self.abundance) or self.abundance < 0.0:
            raise CalcHMCAllError("element abundance must be finite and nonnegative")


@dataclass(frozen=True)
class FixedStateContinuumResult:
    """Source-shaped continuum contribution returned by a leaf callback."""

    heating: float = 0.0
    cooling: float = 0.0
    heating2: float = 0.0
    cooling2: float = 0.0
    htcomp: float = 0.0
    clcomp: float = 0.0
    clbrems: float = 0.0
    htfreef: float = 0.0
    brcems: Optional[np.ndarray] = None
    opakc: Optional[np.ndarray] = None
    complete: bool = False
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class FixedStateElementResult:
    """One completed element-loop iteration."""

    request: FixedStateElementRequest
    equilibrium: ElementEquilibriumResult
    ion_fractions: Dict[int, float]
    fully_stripped_fraction: float
    heating: float
    cooling: float
    heating2: float
    cooling2: float
    electron_contribution: float


@dataclass
class FixedStateCalcHMCAllResult:
    """Result of the fixed-temperature/electron-fraction ``calc_hmc_all`` core."""

    temperature_k: float
    hydrogen_density_cm3: float
    electron_fraction_xee: float
    electron_density_cm3: float
    pressure: float
    lcdd: int
    element_results: List[FixedStateElementResult]
    ion_fractions: Dict[Tuple[int, int], float]
    rrrt: Dict[Tuple[int, int], float]
    pirt: Dict[Tuple[int, int], float]
    htt: Dict[int, float]
    cll: Dict[int, float]
    htt2: Dict[int, float]
    cll2: Dict[int, float]
    xilevg: Dict[Tuple[int, int, int], float]
    rnisg: Dict[Tuple[int, int, int], float]
    bilevg: Dict[Tuple[int, int, int], float]
    gammag: Dict[Tuple[int, int, int], float]
    alphag: Dict[Tuple[int, int, int], float]
    fgammag: Dict[Tuple[int, int, int], np.ndarray]
    falphag: Dict[Tuple[int, int, int], np.ndarray]
    igammamaxg: Dict[Tuple[int, int, int], int]
    ialphamaxg: Dict[Tuple[int, int, int], int]
    stotg: Dict[Tuple[int, int], float]
    atotg: Dict[Tuple[int, int], float]
    fstotg: Dict[Tuple[int, int], np.ndarray]
    fatotg: Dict[Tuple[int, int], np.ndarray]
    xtotg: Dict[Tuple[int, int], float]
    mml: Dict[int, int]
    mmu: Dict[int, int]
    httot: float
    cltot: float
    httot2: float
    cltot2: float
    hmctot: float
    elcter: float
    electron_contribution: float
    continuum: FixedStateContinuumResult
    element_loop_ready: bool
    charge_closure_scope_complete: bool
    complete_fixed_state_ready: bool
    diagnostics: Dict[str, Any] = field(default_factory=dict)


ContinuumKernel = Callable[..., FixedStateContinuumResult]
ElementSolver = Callable[..., ElementEquilibriumResult]


def resolve_calc_hmc_all_density(
    *,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    pressure: float,
    lcdd: int,
) -> float:
    """Reproduce the source ``xpx`` mutation at entry to ``calc_hmc_all``.

    XSTAR stores temperature in units of ``1e4 K``.  The historical ``lcdd``
    branch names are preserved literally rather than reinterpreted.
    """
    t4 = float(temperature_k) / 1.0e4
    xpx = float(hydrogen_density_cm3)
    if int(lcdd) == 0:
        xpx = float(pressure) / (1.38e-12 * max(t4, 1.0e-24))
    if int(lcdd) == 2:
        xpx = float(pressure) / (float(electron_fraction_xee) + 1.0e-34)
    return xpx


def _role_key(element_z: int, role: Mapping[str, Any]) -> Optional[Tuple[int, int, int]]:
    stage = int(role.get("ion_stage", 0))
    level = int(role.get("local_level", role.get("level", 0)))
    if stage <= 0 or level <= 0:
        return None
    return int(element_z), stage, level


def calc_hmc_all(
    master: Any,
    derived: Any,
    *,
    elements: Sequence[FixedStateElementRequest],
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    pressure: float = 0.0,
    lcdd: int = 1,
    continuum_kernel: Optional[ContinuumKernel] = None,
    dispatcher: Optional[SourceFaithfulUCalc] = None,
    element_solver: ElementSolver = solve_element_statistical_equilibrium,
) -> FixedStateCalcHMCAllResult:
    """Run the fixed-state element/charge/heating core of ``calc_hmc_all``.

    The function does not iterate temperature or electron fraction.  It calls
    the validated complete element solver once per supplied element, stores
    source-shaped ion/level diagnostics, accumulates abundance-weighted
    heating/cooling, and evaluates the source charge residual
    ``elcter = xee - enelec``.
    """
    if temperature_k <= 0.0 or not np.isfinite(temperature_k):
        raise CalcHMCAllError("temperature_k must be finite and positive")
    if electron_fraction_xee < 0.0 or not np.isfinite(electron_fraction_xee):
        raise CalcHMCAllError("electron_fraction_xee must be finite and nonnegative")
    if not elements:
        raise CalcHMCAllError("at least one element request is required")

    xpx = resolve_calc_hmc_all_density(
        temperature_k=temperature_k,
        hydrogen_density_cm3=hydrogen_density_cm3,
        electron_fraction_xee=electron_fraction_xee,
        pressure=pressure,
        lcdd=lcdd,
    )
    if xpx < 0.0 or not np.isfinite(xpx):
        raise CalcHMCAllError("resolved hydrogen density is invalid")

    ion_fractions: Dict[Tuple[int, int], float] = {}
    rrrt: Dict[Tuple[int, int], float] = {}
    pirt: Dict[Tuple[int, int], float] = {}
    htt: Dict[int, float] = {}
    cll: Dict[int, float] = {}
    htt2: Dict[int, float] = {}
    cll2: Dict[int, float] = {}
    xilevg: Dict[Tuple[int, int, int], float] = {}
    rnisg: Dict[Tuple[int, int, int], float] = {}
    bilevg: Dict[Tuple[int, int, int], float] = {}
    gammag: Dict[Tuple[int, int, int], float] = {}
    alphag: Dict[Tuple[int, int, int], float] = {}
    fgammag: Dict[Tuple[int, int, int], np.ndarray] = {}
    falphag: Dict[Tuple[int, int, int], np.ndarray] = {}
    igammamaxg: Dict[Tuple[int, int, int], int] = {}
    ialphamaxg: Dict[Tuple[int, int, int], int] = {}
    stotg: Dict[Tuple[int, int], float] = {}
    atotg: Dict[Tuple[int, int], float] = {}
    fstotg: Dict[Tuple[int, int], np.ndarray] = {}
    fatotg: Dict[Tuple[int, int], np.ndarray] = {}
    xtotg: Dict[Tuple[int, int], float] = {}
    mml: Dict[int, int] = {}
    mmu: Dict[int, int] = {}

    element_results: List[FixedStateElementResult] = []
    httot = cltot = httot2 = cltot2 = 0.0
    enelec = 0.0
    all_ready = True
    charge_scope_complete = True

    for request in elements:
        request.validate()
        z = int(request.element_z)
        abundance = float(request.abundance)
        mml[z] = int(request.min_ion_stage)
        mmu[z] = int(request.max_ion_stage)
        charge_scope_complete &= request.min_ion_stage == 1 and request.max_ion_stage >= z

        context = ElementEquilibriumContext(
            temperature_k=float(temperature_k),
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=float(electron_fraction_xee),
            min_ion_stage=int(request.min_ion_stage),
            max_ion_stage=int(request.max_ion_stage),
            radiation=request.radiation,
            escape=request.escape,
            covering_fraction=float(request.covering_fraction),
            turbulent_velocity_km_s=float(request.turbulent_velocity_km_s),
            neutral_h_density_cm3=float(request.neutral_h_density_cm3),
            ionized_h_density_cm3=float(request.ionized_h_density_cm3),
            abundance=abundance,
            lfast=int(request.lfast),
            initial_populations=request.initial_populations,
            strict_context=bool(request.strict_context),
            capture_lucy_trace=bool(request.capture_lucy_trace),
        )
        equilibrium = element_solver(
            master,
            derived,
            element_z=z,
            context=context,
            dispatcher=dispatcher,
        )
        solve = equilibrium.solve
        ready = bool(equilibrium.full_element_direct_solve_ready and solve is not None)
        all_ready &= ready
        if solve is None:
            raise CalcHMCAllError(f"element Z={z} did not produce a population solution")

        element_ht = float(solve.heating) * abundance
        element_cl = float(solve.cooling) * abundance
        element_ht2 = float(solve.heating2) * abundance
        element_cl2 = float(solve.cooling2) * abundance
        htt[z], cll[z], htt2[z], cll2[z] = element_ht, element_cl, element_ht2, element_cl2
        httot += element_ht
        cltot += element_cl
        httot2 += element_ht2
        cltot2 += element_cl2

        stage_fractions: Dict[int, float] = {}
        for ion_slot, block in enumerate(equilibrium.assembly.basis.blocks):
            fraction = float(solve.ion_population_totals[ion_slot])
            stage = int(block.ion_stage)
            stage_fractions[stage] = fraction
            ion_fractions[(z, stage)] = fraction
            rrrt[(z, stage)] = float(solve.recombination_totals[ion_slot])
            pirt[(z, stage)] = float(solve.ionization_totals[ion_slot])
            stotg[(z, stage)] = float(solve.ionization_totals[ion_slot])
            atotg[(z, stage)] = float(solve.recombination_totals[ion_slot])
            fstotg[(z, stage)] = np.asarray(solve.ionization_components[:, ion_slot], dtype=float).copy()
            fatotg[(z, stage)] = np.asarray(solve.recombination_components[:, ion_slot], dtype=float).copy()
            xtotg[(z, stage)] = fraction
            enelec += fraction * float(stage - 1) * abundance

        xisum = float(sum(stage_fractions.values()))
        fully_stripped = max(0.0, 1.0 - xisum)
        if fully_stripped > 0.0:
            ion_fractions[(z, z + 1)] = fully_stripped
        enelec += fully_stripped * float(z) * abundance

        populations = np.asarray(solve.populations, dtype=float)
        lte = np.asarray(equilibrium.assembly.initial_populations, dtype=float)
        for row in equilibrium.assembly.basis.rows:
            idx = row.compact_index - 1
            for role in row.roles:
                key = _role_key(z, role)
                if key is None:
                    continue
                pop = float(populations[idx])
                rn = float(lte[idx]) if idx < lte.size else 0.0
                xilevg[key] = pop
                rnisg[key] = rn
                bilevg[key] = pop / (rn + 1.0e-48)
                gammag[key] = float(solve.gamma[idx])
                alphag[key] = float(solve.alpha[idx])
                fgammag[key] = np.asarray(solve.fgamma[:, idx], dtype=float).copy()
                falphag[key] = np.asarray(solve.falpha[:, idx], dtype=float).copy()
                igammamaxg[key] = int(solve.igammamax_record[idx])
                ialphamaxg[key] = int(solve.ialphamax_record[idx])

        element_results.append(
            FixedStateElementResult(
                request=request,
                equilibrium=equilibrium,
                ion_fractions=stage_fractions,
                fully_stripped_fraction=fully_stripped,
                heating=element_ht,
                cooling=element_cl,
                heating2=element_ht2,
                cooling2=element_cl2,
                electron_contribution=sum(
                    value * float(stage - 1) * abundance
                    for stage, value in stage_fractions.items()
                ) + fully_stripped * float(z) * abundance,
            )
        )

    if continuum_kernel is None:
        continuum = FixedStateContinuumResult(
            complete=False,
            diagnostics={
                "status": "deferred",
                "missing_source_sequence": "comp2 -> freef -> bremem -> heatf",
            },
        )
    else:
        continuum = continuum_kernel(
            temperature_k=float(temperature_k),
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=float(electron_fraction_xee),
            pressure=float(pressure),
            lcdd=int(lcdd),
            element_results=tuple(element_results),
        )
        if not isinstance(continuum, FixedStateContinuumResult):
            raise CalcHMCAllError("continuum_kernel must return FixedStateContinuumResult")

    httot += float(continuum.heating)
    cltot += float(continuum.cooling)
    httot2 += float(continuum.heating2)
    cltot2 += float(continuum.cooling2)
    hmctot = 2.0 * (httot - cltot) / (1.0e-37 + httot + cltot)
    elcter = float(electron_fraction_xee) - enelec
    complete = bool(all_ready and charge_scope_complete and continuum.complete)

    return FixedStateCalcHMCAllResult(
        temperature_k=float(temperature_k),
        hydrogen_density_cm3=xpx,
        electron_fraction_xee=float(electron_fraction_xee),
        electron_density_cm3=xpx * float(electron_fraction_xee),
        pressure=float(pressure),
        lcdd=int(lcdd),
        element_results=element_results,
        ion_fractions=ion_fractions,
        rrrt=rrrt,
        pirt=pirt,
        htt=htt,
        cll=cll,
        htt2=htt2,
        cll2=cll2,
        xilevg=xilevg,
        rnisg=rnisg,
        bilevg=bilevg,
        gammag=gammag,
        alphag=alphag,
        fgammag=fgammag,
        falphag=falphag,
        igammamaxg=igammamaxg,
        ialphamaxg=ialphamaxg,
        stotg=stotg,
        atotg=atotg,
        fstotg=fstotg,
        fatotg=fatotg,
        xtotg=xtotg,
        mml=mml,
        mmu=mmu,
        httot=httot,
        cltot=cltot,
        httot2=httot2,
        cltot2=cltot2,
        hmctot=hmctot,
        elcter=elcter,
        electron_contribution=enelec,
        continuum=continuum,
        element_loop_ready=all_ready,
        charge_closure_scope_complete=charge_scope_complete,
        complete_fixed_state_ready=complete,
        diagnostics={
            "source_file": "xstar/xstarlib/src/calc_hmc_all.f90",
            "source_mode": "fixed_temperature_fixed_electron_fraction",
            "n_elements": len(element_results),
            "continuum_complete": bool(continuum.complete),
            "dsec_deferred": True,
        },
    )


def register_fixed_state_calc_hmc_all(
    driver: Any,
    *,
    elements: Sequence[FixedStateElementRequest],
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    pressure: float = 0.0,
    lcdd: int = 1,
    continuum_kernel: Optional[ContinuumKernel] = None,
    dispatcher: Optional[SourceFaithfulUCalc] = None,
) -> None:
    """Register fixed-state ``calc_hmc_all`` on the source-routine driver."""
    from .driver import XSTARSourceRoutine

    def _handler(state: Any) -> None:
        if state.atomic.master is None or state.atomic.derived is None:
            raise CalcHMCAllError("atomic database state must be initialized first")
        result = calc_hmc_all(
            state.atomic.master,
            state.atomic.derived,
            elements=elements,
            temperature_k=temperature_k,
            hydrogen_density_cm3=hydrogen_density_cm3,
            electron_fraction_xee=electron_fraction_xee,
            pressure=pressure,
            lcdd=lcdd,
            continuum_kernel=continuum_kernel,
            dispatcher=dispatcher,
        )
        state.plasma.temperature = result.temperature_k
        state.plasma.xpx = result.hydrogen_density_cm3
        state.plasma.xee = result.electron_fraction_xee
        state.plasma.electron_density = result.electron_density_cm3
        state.plasma.ion_fractions = result.ion_fractions
        state.thermal.heating = result.httot
        state.thermal.cooling = result.cltot
        state.thermal.electron_fraction = result.electron_fraction_xee
        state.thermal.residual = result.hmctot
        state.local_zone.calc_hmc_all = result
        state.local_zone.fixed_state_ready = result.complete_fixed_state_ready
        state.local_zone.source_arrays = {
            "xiin": result.ion_fractions,
            "rrrt": result.rrrt,
            "pirt": result.pirt,
            "htt": result.htt,
            "cll": result.cll,
            "htt2": result.htt2,
            "cll2": result.cll2,
            "xilevg": result.xilevg,
            "rnisg": result.rnisg,
            "bilevg": result.bilevg,
            "gammag": result.gammag,
            "alphag": result.alphag,
            "fgammag": result.fgammag,
            "falphag": result.falphag,
            "igammamaxg": result.igammamaxg,
            "ialphamaxg": result.ialphamaxg,
            "stotg": result.stotg,
            "atotg": result.atotg,
            "fstotg": result.fstotg,
            "fatotg": result.fatotg,
            "xtotg": result.xtotg,
            "mml": result.mml,
            "mmu": result.mmu,
        }
        state.outputs["calc_hmc_all_fixed_state"] = result
        state.provenance["calc_hmc_all_fixed_state_ready"] = result.complete_fixed_state_ready

    driver.register_source_routine(XSTARSourceRoutine.CALC_HMC_ALL, _handler)


def write_fixed_state_calc_hmc_all_products(
    result: FixedStateCalcHMCAllResult,
    out_dir: str,
    *,
    port_version: str = "v0.4.23",
) -> Dict[str, str]:
    """Write compact fixed-state ``calc_hmc_all`` diagnostics."""
    import csv
    import json
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    ion_csv = out / "xstar_calc_hmc_all_fixed_state_ions.csv"
    with ion_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("element_z", "ion_stage", "ion_fraction", "pirt_s_inv", "rrrt_s_inv"),
        )
        writer.writeheader()
        for (z, stage), fraction in sorted(result.ion_fractions.items()):
            writer.writerow({
                "element_z": z,
                "ion_stage": stage,
                "ion_fraction": fraction,
                "pirt_s_inv": result.pirt.get((z, stage), 0.0),
                "rrrt_s_inv": result.rrrt.get((z, stage), 0.0),
            })

    element_csv = out / "xstar_calc_hmc_all_fixed_state_elements.csv"
    with element_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "element_z", "abundance", "min_ion_stage", "max_ion_stage",
                "heating", "cooling", "heating2", "cooling2",
                "electron_contribution", "fully_stripped_fraction",
                "element_solver_ready",
            ),
        )
        writer.writeheader()
        for item in result.element_results:
            writer.writerow({
                "element_z": item.request.element_z,
                "abundance": item.request.abundance,
                "min_ion_stage": item.request.min_ion_stage,
                "max_ion_stage": item.request.max_ion_stage,
                "heating": item.heating,
                "cooling": item.cooling,
                "heating2": item.heating2,
                "cooling2": item.cooling2,
                "electron_contribution": item.electron_contribution,
                "fully_stripped_fraction": item.fully_stripped_fraction,
                "element_solver_ready": item.equilibrium.full_element_direct_solve_ready,
            })

    level_csv = out / "xstar_calc_hmc_all_fixed_state_levels.csv"
    with level_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "element_z", "ion_stage", "local_level", "population", "lte_population",
                "departure_coefficient", "gamma", "alpha",
                "igammamax_record", "ialphamax_record",
            ),
        )
        writer.writeheader()
        for key in sorted(result.xilevg):
            z, stage, level = key
            writer.writerow({
                "element_z": z,
                "ion_stage": stage,
                "local_level": level,
                "population": result.xilevg[key],
                "lte_population": result.rnisg.get(key, 0.0),
                "departure_coefficient": result.bilevg.get(key, 0.0),
                "gamma": result.gammag.get(key, 0.0),
                "alpha": result.alphag.get(key, 0.0),
                "igammamax_record": result.igammamaxg.get(key, 0),
                "ialphamax_record": result.ialphamaxg.get(key, 0),
            })

    summary = {
        "port_version": port_version,
        "source_routine": "calc_hmc_all",
        "mode": "fixed_temperature_fixed_electron_fraction",
        "temperature_k": result.temperature_k,
        "hydrogen_density_cm3": result.hydrogen_density_cm3,
        "electron_fraction_xee": result.electron_fraction_xee,
        "electron_density_cm3": result.electron_density_cm3,
        "pressure": result.pressure,
        "lcdd": result.lcdd,
        "n_elements": len(result.element_results),
        "n_ion_entries": len(result.ion_fractions),
        "n_level_entries": len(result.xilevg),
        "httot": result.httot,
        "cltot": result.cltot,
        "httot2": result.httot2,
        "cltot2": result.cltot2,
        "hmctot": result.hmctot,
        "electron_contribution": result.electron_contribution,
        "elcter": result.elcter,
        "element_loop_ready": result.element_loop_ready,
        "charge_closure_scope_complete": result.charge_closure_scope_complete,
        "continuum_complete": result.continuum.complete,
        "complete_fixed_state_ready": result.complete_fixed_state_ready,
        "diagnostics": dict(result.diagnostics),
        "continuum_diagnostics": dict(result.continuum.diagnostics),
    }
    json_path = out / "xstar_calc_hmc_all_fixed_state_summary.json"
    json_path.write_text(json.dumps(summary, indent=2) + "\n")

    md_path = out / "xstar_calc_hmc_all_fixed_state_summary.md"
    md_path.write_text(
        "# Fixed-state calc_hmc_all summary\n\n"
        f"- Port version: `{port_version}`\n"
        f"- Temperature: `{result.temperature_k:.16g} K`\n"
        f"- Hydrogen density: `{result.hydrogen_density_cm3:.16g} cm^-3`\n"
        f"- Electron fraction: `{result.electron_fraction_xee:.16g}`\n"
        f"- Elements: `{len(result.element_results)}`\n"
        f"- Element loop ready: `{result.element_loop_ready}`\n"
        f"- Charge-closure scope complete: `{result.charge_closure_scope_complete}`\n"
        f"- Continuum leaves complete: `{result.continuum.complete}`\n"
        f"- Complete fixed-state ready: `{result.complete_fixed_state_ready}`\n"
        f"- Heating/cooling residual: `{result.hmctot:.16g}`\n"
        f"- Charge residual: `{result.elcter:.16g}`\n"
    )
    return {
        "ions_csv": str(ion_csv),
        "elements_csv": str(element_csv),
        "levels_csv": str(level_csv),
        "json": str(json_path),
        "markdown": str(md_path),
    }
