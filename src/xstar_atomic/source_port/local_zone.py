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
from .ion_balance import (
    CalcIonRatesContext,
    CalcIonRatesResult,
    IstrucResult,
    IonStageLimitResult,
    calc_element_pre_matrix_balance,
)


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
    critf: float = 1.0e-7
    use_source_ion_limits: bool = True
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
        if not np.isfinite(self.critf) or self.critf < 0.0:
            raise CalcHMCAllError("critf must be finite and nonnegative")


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
    calc_ion_rates: Dict[int, CalcIonRatesResult]
    preliminary_pirt: Dict[int, float]
    preliminary_rrrt: Dict[int, float]
    second_pass_pirt: Dict[int, float]
    second_pass_rrrt: Dict[int, float]
    preliminary_istruc: IstrucResult
    source_limits: IonStageLimitResult
    selected_min_ion_stage: int
    selected_max_ion_stage: int
    ion_fractions: Dict[int, float]
    preliminary_ion_fractions: Dict[int, float]
    fully_stripped_fraction: float
    heating: float
    cooling: float
    heating2: float
    cooling2: float
    heating_per_abundance: float
    cooling_per_abundance: float
    heating2_per_abundance: float
    cooling2_per_abundance: float
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
    preliminary_ion_fractions: Dict[Tuple[int, int], float]
    preliminary_rrrt: Dict[Tuple[int, int], float]
    preliminary_pirt: Dict[Tuple[int, int], float]
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
    pre_matrix_ready: bool
    element_loop_ready: bool
    charge_closure_scope_complete: bool
    complete_fixed_state_ready: bool
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    global_element_index_by_z: Dict[int, int] = field(default_factory=dict)
    global_ion_index_by_key: Dict[Tuple[int, int], int] = field(default_factory=dict)
    global_level_index_by_key: Dict[Tuple[int, int, int], int] = field(default_factory=dict)


ContinuumKernel = Callable[..., FixedStateContinuumResult]
ElementSolver = Callable[..., ElementEquilibriumResult]
PreMatrixSolver = Callable[..., Tuple[Dict[int, CalcIonRatesResult], IstrucResult, IonStageLimitResult]]


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
    pre_matrix_solver: PreMatrixSolver = calc_element_pre_matrix_balance,
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
    preliminary_ion_fractions: Dict[Tuple[int, int], float] = {}
    preliminary_rrrt: Dict[Tuple[int, int], float] = {}
    preliminary_pirt: Dict[Tuple[int, int], float] = {}
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
    all_pre_matrix_ready = True
    ion_element_z = getattr(derived, "ion_element_z", ())
    available_element_z = {
        int(z) for z in np.asarray(ion_element_z).reshape(-1) if int(z) > 0
    }
    requested_element_z = {int(item.element_z) for item in elements if float(item.abundance) > 1.0e-24}
    charge_scope_complete = bool(available_element_z) and requested_element_z == available_element_z

    # Preserve the native XSTAR global array indices so bounded probe products
    # can be compared without guessing from element/stage/local-level labels.
    global_ion_index_by_key: Dict[Tuple[int, int], int] = {}
    ion_record_to_index: Dict[int, int] = {}
    n_ions = int(getattr(derived, "n_ions", 0))
    ion_records = np.asarray(getattr(derived, "ion_records", ()), dtype=int).reshape(-1)
    ion_stages = np.asarray(getattr(derived, "ion_stage", ()), dtype=int).reshape(-1)
    ion_elements = np.asarray(getattr(derived, "ion_element_z", ()), dtype=int).reshape(-1)
    for ion_index in range(1, min(n_ions + 1, ion_records.size, ion_stages.size, ion_elements.size)):
        ion_record_to_index[int(ion_records[ion_index])] = ion_index
        key = (int(ion_elements[ion_index]), int(ion_stages[ion_index]))
        if key[0] in requested_element_z and key[0] > 0 and key[1] > 0:
            global_ion_index_by_key[key] = ion_index

    # Element arrays such as htt/cll are indexed by source element ordinal
    # ``jk``, not by atomic number.  Decode the exact ordinal from the packed
    # rate-type-11 element headers.
    global_element_index_by_z: Dict[int, int] = {}
    global_element_index_source = "packed_type11_element_ordinal"
    element_records = np.asarray(getattr(derived, "element_records", ()), dtype=int).reshape(-1)
    for element_index in range(1, element_records.size):
        element_record = int(element_records[element_index])
        if element_record <= 0 or not hasattr(master, "record_integers"):
            continue
        integers = np.asarray(master.record_integers(element_record), dtype=int).reshape(-1)
        if integers.size and int(integers[0]) > 0:
            global_element_index_by_z[int(integers[0])] = element_index
    # Synthetic/minimal tests may omit packed element headers.  Preserve a
    # deterministic fallback without using it in production provenance.
    if not global_element_index_by_z:
        global_element_index_source = "synthetic_sorted_element_fallback"
        for element_index, z in enumerate(sorted(available_element_z), start=1):
            global_element_index_by_z[int(z)] = element_index

    # Global level arrays use the source ordinal ``mm`` in
    # derivedpointers%npilev(mm,jkk).  Packed local level labels are metadata
    # and are not valid substitutes for this ordinal.
    global_level_index_by_key: Dict[Tuple[int, int, int], int] = {}
    npilev = np.asarray(getattr(derived, "npilev", ()), dtype=int)
    nlevs = np.asarray(getattr(derived, "nlevs", ()), dtype=int).reshape(-1)
    if npilev.ndim == 2:
        for ion_index in range(1, min(n_ions + 1, ion_stages.size, ion_elements.size, nlevs.size)):
            z = int(ion_elements[ion_index])
            stage = int(ion_stages[ion_index])
            if z not in requested_element_z or stage <= 0:
                continue
            nlev = int(nlevs[ion_index])
            for local_ordinal in range(1, min(nlev + 1, npilev.shape[0])):
                if ion_index >= npilev.shape[1]:
                    break
                global_level_index = int(npilev[local_ordinal, ion_index])
                if global_level_index > 0:
                    global_level_index_by_key[(z, stage, local_ordinal)] = global_level_index

    for request in elements:
        request.validate()
        z = int(request.element_z)
        abundance = float(request.abundance)

        ion_rate_context = CalcIonRatesContext(
            temperature_k=float(temperature_k),
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=float(electron_fraction_xee),
            radiation=request.radiation,
            covering_fraction=float(request.covering_fraction),
            turbulent_velocity_km_s=float(request.turbulent_velocity_km_s),
            neutral_h_density_cm3=float(request.neutral_h_density_cm3),
            ionized_h_density_cm3=float(request.ionized_h_density_cm3),
            lfast=int(request.lfast),
            strict_context=bool(request.strict_context),
        )
        calc_rates_by_stage, preliminary, source_limits = pre_matrix_solver(
            master,
            derived,
            element_z=z,
            context=ion_rate_context,
            critf=float(request.critf),
            dispatcher=dispatcher,
        )
        pre_matrix_ok = all(item.ready for item in calc_rates_by_stage.values())
        all_pre_matrix_ready &= pre_matrix_ok
        if request.use_source_ion_limits:
            selected_min = int(source_limits.mml)
            selected_max = int(source_limits.mmu)
        else:
            selected_min = int(request.min_ion_stage)
            selected_max = int(request.max_ion_stage)
        mml[z] = selected_min
        mmu[z] = selected_max

        for stage, item in calc_rates_by_stage.items():
            key = (z, int(stage))
            preliminary_pirt[key] = float(item.pirti)
            preliminary_rrrt[key] = float(item.rrrti)
            # calc_hmc_element starts its returned arrays with these
            # preliminary values; active ions are overwritten by the second
            # calc_hmc_ion pass below.
            pirt[key] = float(item.pirti)
            rrrt[key] = float(item.rrrti)
        for stage in range(1, preliminary.n_rates + 2):
            preliminary_ion_fractions[(z, stage)] = float(preliminary.fractions[stage])

        context = ElementEquilibriumContext(
            temperature_k=float(temperature_k),
            hydrogen_density_cm3=xpx,
            electron_fraction_xee=float(electron_fraction_xee),
            min_ion_stage=selected_min,
            max_ion_stage=selected_max,
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

        second_pass_pirt: Dict[int, float] = {}
        second_pass_rrrt: Dict[int, float] = {}
        for ion_summary in getattr(equilibrium.assembly, "ion_summaries", ()):
            stage = int(ion_summary.ion_stage)
            second_pass_pirt[stage] = float(ion_summary.second_pass_pirt)
            second_pass_rrrt[stage] = float(ion_summary.second_pass_rrrt)
            pirt[(z, stage)] = float(ion_summary.second_pass_pirt)
            rrrt[(z, stage)] = float(ion_summary.second_pass_rrrt)

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
        lte_has_guard = lte.size == populations.size + 1
        nlev_by_stage = {
            int(block.ion_stage): int(block.nlev)
            for block in equilibrium.assembly.basis.blocks
        }
        for row in equilibrium.assembly.basis.rows:
            idx = row.compact_index - 1
            for role in row.roles:
                key = _role_key(z, role)
                if key is None:
                    continue
                pop = float(populations[idx])
                lte_index = row.compact_index if lte_has_guard else idx
                rn = float(lte[lte_index]) if lte_index < lte.size else 0.0
                local_level = int(key[2])
                ion_nlev = int(nlev_by_stage.get(int(key[1]), 0))
                is_final_continuum = bool(ion_nlev > 0 and local_level == ion_nlev)

                xilevg[key] = pop
                rnisg[key] = rn
                # calc_hmc_element writes bileve for spectroscopic rows using
                # 1e-37. calc_hmc_all recomputes only the final continuum row
                # with 1e-48. Preserve the literal two-floor source rule.
                bilevg[key] = pop / (rn + (1.0e-48 if is_final_continuum else 1.0e-37))
                gammag[key] = float(solve.gamma[idx])
                alphag[key] = float(solve.alpha[idx])
                fgammag[key] = np.asarray(solve.fgamma[:, idx], dtype=float).copy()
                falphag[key] = np.asarray(solve.falpha[:, idx], dtype=float).copy()
                # calc_hmc_all copies the dominant-record indices only for
                # mm=1..nlev-1. The final continuum row retains its zeroed
                # global-array value even though gamma/alpha are copied.
                igammamaxg[key] = 0 if is_final_continuum else int(solve.igammamax_record[idx])
                ialphamaxg[key] = 0 if is_final_continuum else int(solve.ialphamax_record[idx])

        element_results.append(
            FixedStateElementResult(
                request=request,
                equilibrium=equilibrium,
                calc_ion_rates=calc_rates_by_stage,
                preliminary_pirt={stage: float(item.pirti) for stage, item in calc_rates_by_stage.items()},
                preliminary_rrrt={stage: float(item.rrrti) for stage, item in calc_rates_by_stage.items()},
                second_pass_pirt=second_pass_pirt,
                second_pass_rrrt=second_pass_rrrt,
                preliminary_istruc=preliminary,
                source_limits=source_limits,
                selected_min_ion_stage=selected_min,
                selected_max_ion_stage=selected_max,
                ion_fractions=stage_fractions,
                preliminary_ion_fractions={
                    stage: float(preliminary.fractions[stage])
                    for stage in range(1, preliminary.n_rates + 2)
                },
                fully_stripped_fraction=fully_stripped,
                heating=element_ht,
                cooling=element_cl,
                heating2=element_ht2,
                cooling2=element_cl2,
                heating_per_abundance=float(solve.heating),
                cooling_per_abundance=float(solve.cooling),
                heating2_per_abundance=float(solve.heating2),
                cooling2_per_abundance=float(solve.cooling2),
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
    complete = bool(all_pre_matrix_ready and all_ready and charge_scope_complete and continuum.complete)

    return FixedStateCalcHMCAllResult(
        temperature_k=float(temperature_k),
        hydrogen_density_cm3=xpx,
        electron_fraction_xee=float(electron_fraction_xee),
        electron_density_cm3=xpx * float(electron_fraction_xee),
        pressure=float(pressure),
        lcdd=int(lcdd),
        element_results=element_results,
        ion_fractions=ion_fractions,
        preliminary_ion_fractions=preliminary_ion_fractions,
        preliminary_rrrt=preliminary_rrrt,
        preliminary_pirt=preliminary_pirt,
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
        pre_matrix_ready=all_pre_matrix_ready,
        element_loop_ready=all_ready,
        charge_closure_scope_complete=charge_scope_complete,
        complete_fixed_state_ready=complete,
        global_element_index_by_z=global_element_index_by_z,
        global_ion_index_by_key=global_ion_index_by_key,
        global_level_index_by_key=global_level_index_by_key,
        diagnostics={
            "source_file": "xstar/xstarlib/src/calc_hmc_all.f90",
            "source_mode": "fixed_temperature_fixed_electron_fraction",
            "n_elements": len(element_results),
            "pre_matrix_ready": bool(all_pre_matrix_ready),
            "calc_ion_rates_translated": True,
            "istruc_ioneqm_translated": True,
            "second_pass_calc_hmc_ion_rates_translated": True,
            "global_level_mapping_source": "derivedpointers.npilev(local_ordinal,ion_index)",
            "global_element_index_source": global_element_index_source,
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
            "xitp_preliminary": result.preliminary_ion_fractions,
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


def _type77_floor_impact_rows(result: FixedStateCalcHMCAllResult) -> List[Dict[str, Any]]:
    """Build a fixed-population source-vs-legacy type-77 floor audit.

    The legacy branch reproduces the pre-v0.4.27 record-wavelength temperature
    floor. It is diagnostic only and never modifies the production matrix.
    """

    rows: List[Dict[str, Any]] = []

    def as_float(value: Any) -> Optional[float]:
        try:
            out = float(value)
        except (TypeError, ValueError):
            return None
        return out if np.isfinite(out) else None

    for element in result.element_results:
        equilibrium = element.equilibrium
        solve = getattr(equilibrium, "solve", None)
        if solve is None:
            continue
        populations = np.asarray(solve.populations, dtype=float)
        block_by_ion = {
            int(block.ion_index): block for block in equilibrium.assembly.basis.blocks
        }
        for record in getattr(equilibrium.assembly, "record_results", ()):
            if int(record.get("data_type", 0) or 0) != 77:
                continue
            if str(record.get("status", "")) != "evaluated":
                continue
            ion_index = int(record.get("ion_index", 0) or 0)
            block = block_by_ion.get(ion_index)
            if block is None:
                continue
            idest1 = int(record.get("idest1", 0) or 0)
            idest2 = int(record.get("idest2", 0) or 0)
            if idest1 <= 0 or idest2 <= 0:
                continue
            row1 = min(len(populations), int(block.compact_index(idest1)))
            row2 = min(len(populations), int(block.compact_index(idest2)))
            pop1 = float(populations[row1 - 1])
            pop2 = float(populations[row2 - 1])
            source_clu = as_float(record.get("ans1_after_calc_hmc_ion_filter", record.get("ans1")))
            source_cul = as_float(record.get("ans2_after_calc_hmc_ion_filter", record.get("ans2")))
            legacy_clu = as_float(record.get("diag_type77_legacy_record_floor_clu_s^-1"))
            legacy_cul = as_float(record.get("diag_type77_legacy_record_floor_cul_s^-1"))
            if None in {source_clu, source_cul, legacy_clu, legacy_cul}:
                continue
            source_net = float(source_clu) * pop1 - float(source_cul) * pop2
            legacy_net = float(legacy_clu) * pop1 - float(legacy_cul) * pop2
            delta_clu = float(source_clu) - float(legacy_clu)
            delta_cul = float(source_cul) - float(legacy_cul)
            rows.append({
                "element_z": int(element.request.element_z),
                "ion_stage": int(record.get("ion_stage", block.ion_stage) or block.ion_stage),
                "ion_index": ion_index,
                "record": int(record.get("record", 0) or 0),
                "idest1": idest1,
                "idest2": idest2,
                "compact_row_idest1": row1,
                "compact_row_idest2": row2,
                "population_idest1": pop1,
                "population_idest2": pop2,
                "endpoint_energy_difference_eV": record.get("diag_type77_endpoint_energy_difference_eV"),
                "source_floor_wavelength_A": record.get("diag_type77_source_floor_wavelength_A"),
                "record_wavelength_A": record.get("diag_type77_calt77_wavelength_A"),
                "source_log10_temperature_used": record.get("diag_type77_calt77_log10_temperature_used"),
                "legacy_log10_temperature_used": record.get("diag_type77_legacy_record_floor_log10_temperature_used"),
                "source_clu_s_inv": source_clu,
                "source_cul_s_inv": source_cul,
                "legacy_clu_s_inv": legacy_clu,
                "legacy_cul_s_inv": legacy_cul,
                "source_minus_legacy_clu_s_inv": delta_clu,
                "source_minus_legacy_cul_s_inv": delta_cul,
                "source_net_population_flux_s_inv": source_net,
                "legacy_net_population_flux_s_inv": legacy_net,
                "source_minus_legacy_net_population_flux_s_inv": source_net - legacy_net,
                "fixed_population_l1_impact_s_inv": abs(delta_clu * pop1) + abs(delta_cul * pop2),
                "production_operator_uses": "source_endpoint_floor",
                "legacy_branch_role": "diagnostic_only",
            })
    return rows


def write_fixed_state_calc_hmc_all_products(
    result: FixedStateCalcHMCAllResult,
    out_dir: str,
    *,
    port_version: str = "v0.4.29",
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
            fieldnames=(
                "element_z", "ion_stage",
                "preliminary_istruc_fraction", "final_ion_fraction",
                "preliminary_pirt_s_inv", "preliminary_rrrt_s_inv",
                "pirt_s_inv", "rrrt_s_inv",
                "stot_flow_s_inv", "atot_flow_s_inv", "xtot",
            ),
        )
        writer.writeheader()
        ion_keys = sorted(
            set(result.preliminary_ion_fractions)
            | set(result.ion_fractions)
            | set(result.preliminary_pirt)
            | set(result.preliminary_rrrt)
            | set(result.pirt)
            | set(result.rrrt)
            | set(result.stotg)
            | set(result.atotg)
        )
        for z, stage in ion_keys:
            writer.writerow({
                "element_z": z,
                "ion_stage": stage,
                "preliminary_istruc_fraction": result.preliminary_ion_fractions.get((z, stage), 0.0),
                "final_ion_fraction": result.ion_fractions.get((z, stage), 0.0),
                "preliminary_pirt_s_inv": result.preliminary_pirt.get((z, stage), 0.0),
                "preliminary_rrrt_s_inv": result.preliminary_rrrt.get((z, stage), 0.0),
                "pirt_s_inv": result.pirt.get((z, stage), 0.0),
                "rrrt_s_inv": result.rrrt.get((z, stage), 0.0),
                "stot_flow_s_inv": result.stotg.get((z, stage), 0.0),
                "atot_flow_s_inv": result.atotg.get((z, stage), 0.0),
                "xtot": result.xtotg.get((z, stage), 0.0),
            })

    element_csv = out / "xstar_calc_hmc_all_fixed_state_elements.csv"
    with element_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "element_z", "global_element_index",
                "requested_abundance", "effective_abundance", "abundance_source",
                "abundance", "requested_min_ion_stage", "requested_max_ion_stage",
                "selected_min_ion_stage", "selected_max_ion_stage", "critf",
                "ion_stage_selection", "pre_matrix_ready",
                "heating_per_abundance", "cooling_per_abundance",
                "heating2_per_abundance", "cooling2_per_abundance",
                "heating", "cooling", "heating2", "cooling2",
                "electron_contribution", "fully_stripped_fraction",
                "element_solver_ready",
            ),
        )
        writer.writeheader()
        for item in result.element_results:
            writer.writerow({
                "element_z": item.request.element_z,
                "global_element_index": result.global_element_index_by_z.get(item.request.element_z, 0),
                "requested_abundance": result.diagnostics.get("requested_abundance"),
                "effective_abundance": item.request.abundance,
                "abundance_source": result.diagnostics.get("abundance_source", "fixed_state_request"),
                "abundance": item.request.abundance,
                "requested_min_ion_stage": item.request.min_ion_stage,
                "requested_max_ion_stage": item.request.max_ion_stage,
                "selected_min_ion_stage": item.selected_min_ion_stage,
                "selected_max_ion_stage": item.selected_max_ion_stage,
                "critf": item.request.critf,
                "ion_stage_selection": "source_istruc" if item.request.use_source_ion_limits else "explicit_override",
                "pre_matrix_ready": all(rate.ready for rate in item.calc_ion_rates.values()),
                "heating_per_abundance": item.heating_per_abundance,
                "cooling_per_abundance": item.cooling_per_abundance,
                "heating2_per_abundance": item.heating2_per_abundance,
                "cooling2_per_abundance": item.cooling2_per_abundance,
                "heating": item.heating,
                "cooling": item.cooling,
                "heating2": item.heating2,
                "cooling2": item.cooling2,
                "electron_contribution": item.electron_contribution,
                "fully_stripped_fraction": item.fully_stripped_fraction,
                "element_solver_ready": item.equilibrium.full_element_direct_solve_ready,
            })

    contribution_csv = out / "xstar_calc_hmc_all_calc_ion_rates_records.csv"
    with contribution_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "element_z", "ion_stage", "ion_index", "record",
                "data_type", "rate_type", "status",
                "idest1_packed", "idest1", "idest2",
                "ans1", "ans2", "added_to_pirti", "added_to_rrrti", "reason",
            ),
        )
        writer.writeheader()
        for item in result.element_results:
            for stage, rate_result in sorted(item.calc_ion_rates.items()):
                for row in rate_result.contributions:
                    writer.writerow({
                        "element_z": item.request.element_z,
                        "ion_stage": stage,
                        "ion_index": rate_result.ion_index,
                        "record": row.record,
                        "data_type": row.data_type,
                        "rate_type": row.rate_type,
                        "status": row.status,
                        "idest1_packed": row.idest1_packed,
                        "idest1": row.idest1,
                        "idest2": row.idest2,
                        "ans1": row.ans1,
                        "ans2": row.ans2,
                        "added_to_pirti": row.added_to_pirti,
                        "added_to_rrrti": row.added_to_rrrti,
                        "reason": row.reason,
                    })

    level_csv = out / "xstar_calc_hmc_all_fixed_state_levels.csv"
    with level_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "element_z", "ion_stage", "local_level", "global_level_index", "population", "lte_population",
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
                "global_level_index": result.global_level_index_by_key.get(key, 0),
                "population": result.xilevg[key],
                "lte_population": result.rnisg.get(key, 0.0),
                "departure_coefficient": result.bilevg.get(key, 0.0),
                "gamma": result.gammag.get(key, 0.0),
                "alpha": result.alphag.get(key, 0.0),
                "igammamax_record": result.igammamaxg.get(key, 0),
                "ialphamax_record": result.ialphamaxg.get(key, 0),
            })

    type77_rows = _type77_floor_impact_rows(result)
    type77_csv = out / "xstar_calc_hmc_all_type77_floor_impact.csv"
    type77_fields = (
        "element_z", "ion_stage", "ion_index", "record", "idest1", "idest2",
        "compact_row_idest1", "compact_row_idest2", "population_idest1",
        "population_idest2", "endpoint_energy_difference_eV",
        "source_floor_wavelength_A", "record_wavelength_A",
        "source_log10_temperature_used", "legacy_log10_temperature_used",
        "source_clu_s_inv", "source_cul_s_inv", "legacy_clu_s_inv",
        "legacy_cul_s_inv", "source_minus_legacy_clu_s_inv",
        "source_minus_legacy_cul_s_inv", "source_net_population_flux_s_inv",
        "legacy_net_population_flux_s_inv",
        "source_minus_legacy_net_population_flux_s_inv",
        "fixed_population_l1_impact_s_inv", "production_operator_uses",
        "legacy_branch_role",
    )
    with type77_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=type77_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(type77_rows)
    type77_summary = {
        "mode": "diagnostic_fixed_population_source_endpoint_floor_vs_legacy_record_floor",
        "production_operator_uses": "source_endpoint_floor",
        "legacy_values_enter_operator": False,
        "n_records": len(type77_rows),
        "n_records_with_rate_change": sum(
            abs(float(row["source_minus_legacy_clu_s_inv"])) > 0.0
            or abs(float(row["source_minus_legacy_cul_s_inv"])) > 0.0
            for row in type77_rows
        ),
        "max_absolute_rate_change_s_inv": max((
            max(abs(float(row["source_minus_legacy_clu_s_inv"])),
                abs(float(row["source_minus_legacy_cul_s_inv"])))
            for row in type77_rows
        ), default=0.0),
        "sum_fixed_population_l1_impact_s_inv": sum(
            float(row["fixed_population_l1_impact_s_inv"]) for row in type77_rows
        ),
        "max_fixed_population_l1_impact_s_inv": max((
            float(row["fixed_population_l1_impact_s_inv"]) for row in type77_rows
        ), default=0.0),
        "max_absolute_net_flux_change_s_inv": max((
            abs(float(row["source_minus_legacy_net_population_flux_s_inv"]))
            for row in type77_rows
        ), default=0.0),
    }
    type77_json = out / "xstar_calc_hmc_all_type77_floor_impact_summary.json"
    type77_json.write_text(json.dumps(type77_summary, indent=2) + "\n")

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
        "n_preliminary_ion_entries": len(result.preliminary_ion_fractions),
        "n_preliminary_rate_entries": len(result.preliminary_pirt),
        "n_second_pass_rate_entries": len(result.pirt),
        "n_level_entries": len(result.xilevg),
        "n_global_element_mappings": len(result.global_element_index_by_z),
        "n_global_ion_mappings": len(result.global_ion_index_by_key),
        "n_global_level_mappings": len(result.global_level_index_by_key),
        "pre_matrix_ready": result.pre_matrix_ready,
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
        "type77_floor_impact": type77_summary,
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
        f"- Pre-matrix calc_ion_rates/istruc ready: `{result.pre_matrix_ready}`\n"
        f"- Second-pass calc_hmc_ion rate entries: `{len(result.pirt)}`\n"
        f"- Source global-level mappings: `{len(result.global_level_index_by_key)}`\n"
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
        "calc_ion_rates_records_csv": str(contribution_csv),
        "levels_csv": str(level_csv),
        "type77_floor_impact_csv": str(type77_csv),
        "type77_floor_impact_json": str(type77_json),
        "json": str(json_path),
        "markdown": str(md_path),
    }
