"""Source-faithful translation of XSTAR ``heatt.f90``.

``heatt`` performs the shell-local continuum, line, and recombination-continuum
transfer after the accepted local ``xstarcalc`` calculation.  The translation
preserves several source-visible ownership details that are easy to lose in a
formula-only rewrite:

* only ``1:ncn2`` continuum columns are replaced; higher caller-owned columns
  remain untouched;
* the line loop inherits the final continuum-only ``optp2`` value for the first
  inward line term, then explicitly sets ``optp2=0`` for all remaining line
  work;
* line and RRC luminosity arrays are formed from the corresponding ``old``
  arrays rather than accumulated from their current values;
* the shared ``leveltemp`` workspace is overwritten only through ``1:nlev`` for
  each visited ion, retaining higher columns from earlier ions; and
* RRC records are traversed in element/ion/type-7 source order using the packed
  pointer hierarchy and ``npconi2`` mapping.

The original routine declares local ``cmp1`` and ``cmp2`` variables but neither
receives nor initializes them.  They affect only local diagnostic heating totals
and no caller-visible output.  This port therefore validates and returns all
well-defined caller-visible arrays while explicitly marking the final Compton
summary as source-uninitialized instead of inventing values.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .element_equilibrium import build_level_table
from .ucalc import UCalcLevel, UCalcLevelTable


XSTAR_HEATT_FOUR_PI = float(np.float32(12.56))
XSTAR_HEATT_RADIUS_SCALE = 1.0e-19
XSTAR_HEATT_FAC_THRESHOLD = float(np.float32(0.01))
XSTAR_HEATT_OPACITY_FLOOR = 1.0e-49
XSTAR_HEATT_RRC_FLOOR = 1.0e-49
XSTAR_HEATT_ABUNDANCE_FLOOR = float(np.float32(1.0e-10))
XSTAR_HEATT_ERG_PER_EV = 1.602176634e-12
XSTAR_HEATT_WAVELENGTH_EV_ANGSTROM = float(np.float32(12398.4016))


class HeattPortError(RuntimeError):
    """Raised when the translated ``heatt`` source contract is invalid."""


@dataclass(frozen=True)
class HeattLineTrace:
    line_index_one_based: int
    record: int
    rate_type: int
    wavelength_angstrom: float
    evaluated: bool
    inherited_optp2: float
    inward_absorption_term: float
    inward_emissivity: float
    outward_emissivity: float


@dataclass(frozen=True)
class HeattRRCTrace:
    element_z: int
    ion_index: int
    record: int
    continuum_index_one_based: int
    destination_level: int
    evaluated: bool
    emissivity_sum: float


@dataclass(frozen=True)
class HeattResult:
    """Caller-visible result of one literal ``heatt.f90`` execution."""

    ncn2: int
    n_lines: int
    n_continua: int
    fpr2: float
    zrems_before: np.ndarray
    zrems_after: np.ndarray
    elum_before: np.ndarray
    elum_after: np.ndarray
    elumab_before: np.ndarray
    elumab_after: np.ndarray
    leveltemp_workspace: UCalcLevelTable
    continuum_net_integral: float
    continuum_positive_integral: float
    pre_compton_heating: float
    pre_compton_cooling: float
    bremsstrahlung_integral: float
    compton_coefficients_source_initialized: bool
    line_traces: tuple[HeattLineTrace, ...]
    rrc_traces: tuple[HeattRRCTrace, ...]
    native_metrics: Mapping[str, Any] = field(default_factory=dict)
    source_file: str = "xstar/xstarlib/src/heatt.f90"


def _vector(values: Sequence[float], *, name: str, minimum: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size < int(minimum):
        raise HeattPortError(f"{name} is shorter than the active source range")
    if not np.all(np.isfinite(arr)):
        raise HeattPortError(f"{name} contains non-finite values")
    return arr


def _matrix(
    values: Sequence[Sequence[float]],
    *,
    name: str,
    rows: int,
    columns: int,
) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < int(rows) or arr.shape[1] < int(columns):
        raise HeattPortError(
            f"{name} must have at least shape ({int(rows)}, {int(columns)})"
        )
    if not np.all(np.isfinite(arr)):
        raise HeattPortError(f"{name} contains non-finite values")
    return arr


def _copy_leveltemp(initial: Optional[UCalcLevelTable]) -> UCalcLevelTable:
    if initial is None:
        return UCalcLevelTable(levels={}, nlev=0)
    return UCalcLevelTable(levels=dict(initial.levels), nlev=int(initial.nlev))


def _overwrite_leveltemp(
    workspace: UCalcLevelTable, current: UCalcLevelTable
) -> UCalcLevelTable:
    for local in range(1, int(current.nlev) + 1):
        workspace.levels[local] = current.require(local)
    workspace.nlev = int(current.nlev)
    return workspace


def _abundance(abundances_by_z: Mapping[int, float] | Sequence[float], z: int) -> float:
    if isinstance(abundances_by_z, Mapping):
        return float(abundances_by_z.get(int(z), 0.0))
    arr = np.asarray(abundances_by_z, dtype=float).reshape(-1)
    zi = int(z)
    # Prefer a one-based guard when present.  A physical zero-based list remains
    # accepted for small bounded fixtures.
    if arr.size > zi:
        return float(arr[zi])
    if 1 <= zi <= arr.size:
        return float(arr[zi - 1])
    return 0.0


def _source_fac(tau: float) -> float:
    value = float(tau)
    if value > XSTAR_HEATT_FAC_THRESHOLD:
        return (1.0 - math.exp(-value)) / value
    return 1.0



def _native_heatt_requested() -> bool:
    enabled = os.environ.get("XSTAR_ATOMIC_THERMAL_ENGINE_CPP", "").strip().lower()
    product = os.environ.get("XSTAR_ATOMIC_THERMAL_ENGINE_CPP_PRODUCT", "").strip().lower()
    return enabled not in {"", "0", "false", "no", "off"} and product not in {"", "0", "false", "no", "off"}


def _heatt_native(
    *, temperature_1e4K: float, radius_cm: float, covering_fraction: float,
    zone_thickness_cm: float, electron_fraction_xee: float,
    hydrogen_density_cm3: float, abundances_by_z: Mapping[int, float] | Sequence[float],
    epi_eV: Sequence[float], bremsa: Sequence[float],
    leveltemp_workspace: Optional[UCalcLevelTable], zrems_before: Sequence[Sequence[float]],
    zremso: Sequence[Sequence[float]], elumab_before: Sequence[Sequence[float]],
    elumabo: Sequence[Sequence[float]], elum_before: Sequence[Sequence[float]],
    elumo: Sequence[Sequence[float]], rcem: Sequence[Sequence[float]],
    rccemis: Sequence[Sequence[float]], opakc: Sequence[float],
    opakcont: Sequence[float], cemab: Sequence[Sequence[float]],
    flinel: Sequence[float], brcems: Sequence[float], master: Any, derived: Any,
    ncn2: int, n_lines: int, n_continua: int,
) -> HeattResult:
    from .cpp_backend_thermal import apply_heatt_cpp

    n, nl, nc = int(ncn2), int(n_lines), int(n_continua)
    epi = _vector(epi_eV, name="epi", minimum=n)
    incident = _vector(bremsa, name="bremsa", minimum=n)
    opacity = _vector(opakc, name="opakc", minimum=n)
    opacity_cont = _vector(opakcont, name="opakcont", minimum=n)
    line_bins = _vector(flinel, name="flinel", minimum=n)
    brems = _vector(brcems, name="brcems", minimum=n)
    old_cont = _matrix(zremso, name="zremso", rows=5, columns=n)
    current_cont = _matrix(zrems_before, name="zrems", rows=5, columns=n)
    old_lines = _matrix(elumo, name="elumo", rows=2, columns=nl)
    current_lines = _matrix(elum_before, name="elum", rows=2, columns=nl)
    old_rrc = _matrix(elumabo, name="elumabo", rows=2, columns=nc)
    current_rrc = _matrix(elumab_before, name="elumab", rows=2, columns=nc)
    line_emis = _matrix(rcem, name="rcem", rows=2, columns=nl)
    continuum_emis = _matrix(rccemis, name="rccemis", rows=2, columns=n)
    rrc_emis = _matrix(cemab, name="cemab", rows=2, columns=nc)
    if master is None or derived is None:
        if nl or nc:
            raise HeattPortError("native heatt line/RRC traversal requires master and derived pointers")

    line_rows: list[dict[str, Any]] = []
    line_traces: list[HeattLineTrace] = []
    inherited = max(XSTAR_HEATT_OPACITY_FLOOR, float(opacity_cont[n - 1]))
    for jk in range(1, nl + 1):
        record = int(derived.nplin[jk]) if jk < len(derived.nplin) else 0
        rate_type = 0
        wavelength = 0.0
        evaluated = False
        if record:
            header = master.header(record)
            rate_type = int(header.rate_type)
            reals = master.record_reals(record)
            wavelength = abs(float(reals[0])) if len(reals) else 0.0
            evaluated = bool(1.0 < wavelength < 1.0e8 and rate_type == 4)
        line_rows.append({"record": record, "rate_type": rate_type, "wavelength_angstrom": wavelength})
        inward_absorption = float(old_lines[0, jk - 1]) * inherited / (XSTAR_HEATT_FOUR_PI * (float(radius_cm) * XSTAR_HEATT_RADIUS_SCALE) ** 2) if evaluated and radius_cm else 0.0
        line_traces.append(HeattLineTrace(
            line_index_one_based=jk, record=record, rate_type=rate_type,
            wavelength_angstrom=wavelength, evaluated=evaluated,
            inherited_optp2=inherited, inward_absorption_term=inward_absorption,
            inward_emissivity=float(line_emis[0, jk - 1]) if evaluated else 0.0,
            outward_emissivity=float(line_emis[1, jk - 1]) if evaluated else 0.0,
        ))
        if evaluated:
            inherited = 0.0

    leveltemp = _copy_leveltemp(leveltemp_workspace)
    rrc_rows: list[dict[str, Any]] = []
    rrc_traces: list[HeattRRCTrace] = []
    element_record = int(derived.npfirst[11]) if len(derived.npfirst) > 11 else 0
    while element_record:
        element_ints = master.record_integers(element_record)
        if len(element_ints) > 0:
            element_z = int(element_ints[-1]); nnz = int(element_ints[0])
            if _abundance(abundances_by_z, element_z) >= XSTAR_HEATT_ABUNDANCE_FLOOR:
                ion_record = int(derived.npfirst[12]) if len(derived.npfirst) > 12 else 0
                ion_index = 0; matched_stages = 0
                while ion_record and matched_stages < nnz:
                    ion_index += 1
                    ion_ints = master.record_integers(ion_record)
                    ion_element_z = int(ion_ints[-2]) if len(ion_ints) >= 2 else 0
                    if ion_element_z == element_z:
                        matched_stages += 1
                        _overwrite_leveltemp(leveltemp, build_level_table(master, derived, ion_index))
                        rec = int(derived.npfi[7, ion_index])
                        parent = int(derived.npar[rec]) if rec else 0
                        while rec and int(derived.npar[rec]) == parent:
                            header = master.header(rec)
                            if int(header.rate_type) != 7:
                                break
                            ci = int(derived.npconi2[rec])
                            ints = master.record_integers(rec)
                            idest1 = int(ints[-2]) if len(ints) >= 2 else 0
                            in_range = 1 <= ci <= nc
                            active = bool(in_range and (float(rrc_emis[0, ci - 1]) > XSTAR_HEATT_RRC_FLOOR or float(rrc_emis[1, ci - 1]) > XSTAR_HEATT_RRC_FLOOR))
                            if active and (idest1 <= 0 or leveltemp.get(idest1) is None):
                                raise HeattPortError(f"RRC record {rec} references missing level {idest1}")
                            emissivity_sum = float(rrc_emis[0, ci - 1] + rrc_emis[1, ci - 1]) if active else 0.0
                            rrc_rows.append({"record": rec, "continuum_index_one_based": ci, "destination_level": idest1, "active": active})
                            rrc_traces.append(HeattRRCTrace(element_z=element_z, ion_index=ion_index, record=rec,
                                continuum_index_one_based=ci, destination_level=idest1, evaluated=active,
                                emissivity_sum=emissivity_sum))
                            rec = int(derived.npnxt[rec])
                    ion_record = int(derived.npnxt[ion_record])
        element_record = int(derived.npnxt[element_record])

    z_after = current_cont.copy(); line_after = current_lines.copy(); rrc_after = current_rrc.copy()
    metrics = apply_heatt_cpp(
        lines=line_rows, rrcs=rrc_rows, temperature_1e4K=temperature_1e4K,
        radius_cm=radius_cm, covering_fraction=covering_fraction,
        zone_thickness_cm=zone_thickness_cm, electron_fraction_xee=electron_fraction_xee,
        hydrogen_density_cm3=hydrogen_density_cm3, epi_eV=epi, bremsa=incident,
        opakc=opacity, opakcont=opacity_cont, flinel=line_bins, brcems=brems,
        zrems=z_after, zremso=old_cont, elum=line_after, elumo=old_lines,
        rcem=line_emis, elumab=rrc_after, elumabo=old_rrc, cemab=rrc_emis,
        rccemis=continuum_emis, ncn2=n, n_lines=nl, n_continua=nc,
    )
    return HeattResult(
        ncn2=n, n_lines=nl, n_continua=nc, fpr2=float(metrics["fpr2"]),
        zrems_before=current_cont.copy(), zrems_after=z_after,
        elum_before=current_lines.copy(), elum_after=line_after,
        elumab_before=current_rrc.copy(), elumab_after=rrc_after,
        leveltemp_workspace=leveltemp,
        continuum_net_integral=float(metrics["continuum_net_integral"]),
        continuum_positive_integral=float(metrics["continuum_positive_integral"]),
        pre_compton_heating=float(metrics["pre_compton_heating"]),
        pre_compton_cooling=float(metrics["pre_compton_cooling"]),
        bremsstrahlung_integral=float(metrics["bremsstrahlung_integral"]),
        compton_coefficients_source_initialized=False,
        line_traces=tuple(line_traces), rrc_traces=tuple(rrc_traces),
        native_metrics=dict(metrics),
        source_file="xstar/xstarlib/src/heatt.f90 (native v0.6.48.3)",
    )


def heatt(
    *,
    temperature_1e4K: float,
    radius_cm: float,
    covering_fraction: float,
    zone_thickness_cm: float,
    electron_fraction_xee: float,
    hydrogen_density_cm3: float,
    abundances_by_z: Mapping[int, float] | Sequence[float],
    epi_eV: Sequence[float],
    bremsa: Sequence[float],
    leveltemp_workspace: Optional[UCalcLevelTable],
    zrems_before: Sequence[Sequence[float]],
    zremso: Sequence[Sequence[float]],
    elumab_before: Sequence[Sequence[float]],
    elumabo: Sequence[Sequence[float]],
    elum_before: Sequence[Sequence[float]],
    elumo: Sequence[Sequence[float]],
    rcem: Sequence[Sequence[float]],
    rccemis: Sequence[Sequence[float]],
    opakc: Sequence[float],
    opakcont: Sequence[float],
    cemab: Sequence[Sequence[float]],
    flinel: Sequence[float],
    brcems: Sequence[float],
    master: Any,
    derived: Any,
    ncn2: int,
    n_lines: int,
    n_continua: int,
) -> HeattResult:
    """Translate ``heatt.f90`` in literal loop and mutation order."""
    if _native_heatt_requested():
        return _heatt_native(
            temperature_1e4K=temperature_1e4K, radius_cm=radius_cm,
            covering_fraction=covering_fraction, zone_thickness_cm=zone_thickness_cm,
            electron_fraction_xee=electron_fraction_xee, hydrogen_density_cm3=hydrogen_density_cm3,
            abundances_by_z=abundances_by_z, epi_eV=epi_eV, bremsa=bremsa,
            leveltemp_workspace=leveltemp_workspace, zrems_before=zrems_before, zremso=zremso,
            elumab_before=elumab_before, elumabo=elumabo, elum_before=elum_before, elumo=elumo,
            rcem=rcem, rccemis=rccemis, opakc=opakc, opakcont=opakcont, cemab=cemab,
            flinel=flinel, brcems=brcems, master=master, derived=derived, ncn2=ncn2,
            n_lines=n_lines, n_continua=n_continua,
        )
    n = int(ncn2)
    nl = int(n_lines)
    nc = int(n_continua)
    if n < 1 or nl < 0 or nc < 0:
        raise HeattPortError("invalid heatt active dimensions")

    epi = _vector(epi_eV, name="epi", minimum=n)
    incident = _vector(bremsa, name="bremsa", minimum=n)
    opacity = _vector(opakc, name="opakc", minimum=n)
    opacity_cont = _vector(opakcont, name="opakcont", minimum=n)
    line_bins = _vector(flinel, name="flinel", minimum=n)
    brems = _vector(brcems, name="brcems", minimum=n)
    old_cont = _matrix(zremso, name="zremso", rows=5, columns=n)
    current_cont = _matrix(zrems_before, name="zrems", rows=5, columns=n)
    old_lines = _matrix(elumo, name="elumo", rows=2, columns=nl)
    current_lines = _matrix(elum_before, name="elum", rows=2, columns=nl)
    old_rrc = _matrix(elumabo, name="elumabo", rows=2, columns=nc)
    current_rrc = _matrix(elumab_before, name="elumab", rows=2, columns=nc)
    line_emis = _matrix(rcem, name="rcem", rows=2, columns=nl)
    continuum_emis = _matrix(rccemis, name="rccemis", rows=2, columns=n)
    rrc_emis = _matrix(cemab, name="cemab", rows=2, columns=nc)

    if master is None or derived is None:
        if nl or nc:
            raise HeattPortError("heatt line/RRC traversal requires master and derived pointers")

    z_after = current_cont.copy()
    line_after = current_lines.copy()
    rrc_after = current_rrc.copy()
    leveltemp = _copy_leveltemp(leveltemp_workspace)

    r19 = float(radius_cm) * XSTAR_HEATT_RADIUS_SCALE
    fpr2 = XSTAR_HEATT_FOUR_PI * r19 * r19
    if fpr2 == 0.0 and nl:
        raise HeattPortError("heatt line transfer requires nonzero radius")
    delrl = float(zone_thickness_cm)

    # Source computes this diagnostic before the transfer loops.
    clbrems = 0.0
    tmp2 = 0.0
    for kl in range(n):
        tmp2o = tmp2
        tmp2 = float(brems[kl])
        if kl >= 1:
            clbrems += (
                (tmp2 + tmp2o)
                * (float(epi[kl]) - float(epi[kl - 1]))
                * XSTAR_HEATT_ERG_PER_EV
                / 2.0
            )

    hmctot = 0.0
    hpctot = 0.0
    epii = float(epi[0])
    hmctmp = 0.0
    hpctmp = 0.0
    tmpc = 0.0
    tmph = 0.0
    # ``optp2`` intentionally survives the continuum loop and is consumed by
    # the first line before the source resets it to zero.
    optp2 = XSTAR_HEATT_OPACITY_FLOOR
    for kl in range(n):
        optp2 = max(XSTAR_HEATT_OPACITY_FLOOR, float(opacity[kl]))
        epiio = epii
        epii = float(epi[kl])
        tautmp = optp2 * delrl
        fac = _source_fac(tautmp)
        tmph = float(incident[kl]) * optp2
        tmpc1 = float(continuum_emis[0, kl]) + float(brems[kl]) * (
            1.0 - float(covering_fraction)
        ) / 2.0
        tmpc2 = float(continuum_emis[1, kl]) + float(brems[kl]) * (
            1.0 + float(covering_fraction)
        ) / 2.0
        tmpc = (tmpc1 + tmpc2) * XSTAR_HEATT_FOUR_PI
        hmctmpo = hmctmp
        hpctmpo = hpctmp
        hmctmp = (tmph - tmpc) * fac
        hpctmp = (tmph + tmpc) * fac

        z_after[0, kl] = max(
            0.0,
            float(old_cont[0, kl])
            - (
                tmph
                - XSTAR_HEATT_FOUR_PI * (tmpc1 + tmpc2)
            )
            * fac
            * delrl
            * fpr2,
        )
        z_after[1, kl] = (
            float(old_cont[1, kl])
            + XSTAR_HEATT_FOUR_PI * tmpc1 * fac * delrl * fpr2
        )
        z_after[2, kl] = (
            float(old_cont[2, kl])
            + XSTAR_HEATT_FOUR_PI * tmpc2 * fac * delrl * fpr2
        )
        if kl >= 1:
            de = float(epii - epiio)
            hmctot += (hmctmp + hmctmpo) * de * XSTAR_HEATT_ERG_PER_EV / 2.0
            hpctot += (hpctmp + hpctmpo) * de * XSTAR_HEATT_ERG_PER_EV / 2.0

        # Continuum-only afterthought.  Its final ``optp2`` is source-owned
        # state entering the line loop.
        optp2 = max(XSTAR_HEATT_OPACITY_FLOOR, float(opacity_cont[kl]))
        fac = _source_fac(optp2 * delrl)
        z_after[3, kl] = (
            float(old_cont[3, kl])
            + XSTAR_HEATT_FOUR_PI * tmpc1 * fac * delrl * fpr2
        )
        z_after[4, kl] = (
            float(old_cont[4, kl])
            + XSTAR_HEATT_FOUR_PI * tmpc2 * fac * delrl * fpr2
        )

    httot = (hmctot + hpctot) / 2.0
    cltot = (-hmctot + hpctot) / 2.0
    clcont = cltot

    line_traces: list[HeattLineTrace] = []
    for jk in range(1, nl + 1):
        record = int(derived.nplin[jk]) if jk < len(derived.nplin) else 0
        rate_type = 0
        wavelength = 0.0
        evaluated = False
        inherited = float(optp2)
        inward_absorption = 0.0
        tmpc1 = 0.0
        tmpc2 = 0.0
        if record != 0:
            header = master.header(record)
            rate_type = int(header.rate_type)
            reals = master.record_reals(record)
            wavelength = abs(float(reals[0])) if len(reals) else 0.0
            if 1.0 < wavelength < 1.0e8 and rate_type == 4:
                # Preserve the stale last-bin continuum-only opacity in this
                # one expression before ``optp2=0``.
                inward_absorption = float(old_lines[0, jk - 1]) * optp2 / fpr2
                tmpc1 = float(line_emis[0, jk - 1])
                tmpc2 = float(line_emis[1, jk - 1])
                tmpc = tmpc1 + tmpc2
                # ``ener`` and ``etst`` are diagnostic-only, but evaluate the
                # source expression to keep exceptional behavior aligned.
                _ener = (
                    XSTAR_HEATT_ERG_PER_EV
                    * XSTAR_HEATT_WAVELENGTH_EV_ANGSTROM
                    / max(wavelength, XSTAR_HEATT_OPACITY_FLOOR)
                )
                del _ener
                optp2 = 0.0
                fac = 1.0
                hmctot -= tmpc * fac
                hpctot += tmpc * fac
                cltot += tmpc
                line_after[0, jk - 1] = max(
                    0.0,
                    float(old_lines[0, jk - 1])
                    + (-inward_absorption + tmpc1) * fac * delrl * fpr2,
                )
                tmph = float(old_lines[1, jk - 1]) * optp2 / fpr2
                line_after[1, jk - 1] = max(
                    0.0,
                    float(old_lines[1, jk - 1])
                    + (-tmph + tmpc2) * fac * delrl * fpr2,
                )
                evaluated = True
        line_traces.append(
            HeattLineTrace(
                line_index_one_based=jk,
                record=record,
                rate_type=rate_type,
                wavelength_angstrom=wavelength,
                evaluated=evaluated,
                inherited_optp2=inherited,
                inward_absorption_term=inward_absorption,
                inward_emissivity=tmpc1,
                outward_emissivity=tmpc2,
            )
        )

    rrc_traces: list[HeattRRCTrace] = []
    element_record = int(derived.npfirst[11]) if len(derived.npfirst) > 11 else 0
    while element_record:
        element_ints = master.record_integers(element_record)
        if len(element_ints) > 0:
            element_z = int(element_ints[-1])
            nnz = int(element_ints[0])
            abundant = _abundance(abundances_by_z, element_z) >= XSTAR_HEATT_ABUNDANCE_FLOOR
            if abundant:
                ion_record = int(derived.npfirst[12]) if len(derived.npfirst) > 12 else 0
                ion_index = 0
                matched_stages = 0
                while ion_record and matched_stages < nnz:
                    ion_index += 1
                    ion_ints = master.record_integers(ion_record)
                    ion_element_z = int(ion_ints[-2]) if len(ion_ints) >= 2 else 0
                    if ion_element_z == element_z:
                        matched_stages += 1
                        current_levels = build_level_table(master, derived, ion_index)
                        _overwrite_leveltemp(leveltemp, current_levels)
                        rec = int(derived.npfi[7, ion_index])
                        parent = int(derived.npar[rec]) if rec else 0
                        while rec and int(derived.npar[rec]) == parent:
                            header = master.header(rec)
                            if int(header.rate_type) != 7:
                                break
                            continuum_index = int(derived.npconi2[rec])
                            ints = master.record_integers(rec)
                            idest1 = int(ints[-2]) if len(ints) >= 2 else 0
                            in_range = 1 <= continuum_index <= nc
                            active = bool(
                                in_range
                                and (
                                    float(rrc_emis[0, continuum_index - 1]) > XSTAR_HEATT_RRC_FLOOR
                                    or float(rrc_emis[1, continuum_index - 1]) > XSTAR_HEATT_RRC_FLOOR
                                )
                            )
                            emissivity_sum = 0.0
                            if active:
                                # The threshold is diagnostic-only but source
                                # indexing must still be valid.
                                if idest1 <= 0 or leveltemp.get(idest1) is None:
                                    raise HeattPortError(
                                        f"RRC record {rec} references missing level {idest1}"
                                    )
                                _eth = (
                                    float(leveltemp.require(idest1).ionization_potential_ev)
                                    - float(leveltemp.require(idest1).energy_ev)
                                )
                                del _eth
                                emissivity_sum = (
                                    float(rrc_emis[0, continuum_index - 1])
                                    + float(rrc_emis[1, continuum_index - 1])
                                )
                                fac = delrl
                                increment = emissivity_sum * fac * fpr2 / 2.0
                                rrc_after[0, continuum_index - 1] = max(
                                    0.0,
                                    float(old_rrc[0, continuum_index - 1]) + increment,
                                )
                                rrc_after[1, continuum_index - 1] = max(
                                    0.0,
                                    float(old_rrc[1, continuum_index - 1]) + increment,
                                )
                            rrc_traces.append(
                                HeattRRCTrace(
                                    element_z=element_z,
                                    ion_index=ion_index,
                                    record=rec,
                                    continuum_index_one_based=continuum_index,
                                    destination_level=idest1,
                                    evaluated=active,
                                    emissivity_sum=emissivity_sum,
                                )
                            )
                            rec = int(derived.npnxt[rec])
                    ion_record = int(derived.npnxt[ion_record])
        element_record = int(derived.npnxt[element_record])

    # Lines have already updated ``cltot``.  The final source statements use
    # uninitialized local cmp1/cmp2; no caller-visible array depends on them.
    del temperature_1e4K, electron_fraction_xee, hydrogen_density_cm3, clcont

    return HeattResult(
        ncn2=n,
        n_lines=nl,
        n_continua=nc,
        fpr2=float(fpr2),
        zrems_before=current_cont.copy(),
        zrems_after=z_after,
        elum_before=current_lines.copy(),
        elum_after=line_after,
        elumab_before=current_rrc.copy(),
        elumab_after=rrc_after,
        leveltemp_workspace=leveltemp,
        continuum_net_integral=float(hmctot),
        continuum_positive_integral=float(hpctot),
        pre_compton_heating=float(httot),
        pre_compton_cooling=float(cltot),
        bremsstrahlung_integral=float(clbrems),
        compton_coefficients_source_initialized=False,
        line_traces=tuple(line_traces),
        rrc_traces=tuple(rrc_traces),
    )


__all__ = [
    "XSTAR_HEATT_FOUR_PI",
    "XSTAR_HEATT_RADIUS_SCALE",
    "XSTAR_HEATT_FAC_THRESHOLD",
    "XSTAR_HEATT_OPACITY_FLOOR",
    "XSTAR_HEATT_RRC_FLOOR",
    "XSTAR_HEATT_ABUNDANCE_FLOOR",
    "XSTAR_HEATT_ERG_PER_EV",
    "XSTAR_HEATT_WAVELENGTH_EV_ANGSTROM",
    "HeattPortError",
    "HeattLineTrace",
    "HeattRRCTrace",
    "HeattResult",
    "heatt",
]

# ---------------------------------------------------------------------------
# Frozen direct-original-Fortran acceptance fixture
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _DirectHeader:
    data_type: int
    rate_type: int


class _DirectHeattMaster:
    def __init__(self) -> None:
        self._headers = {
            1: _DirectHeader(13, 11),
            2: _DirectHeader(14, 12),
            3: _DirectHeader(6, 13),
            4: _DirectHeader(50, 4),
            5: _DirectHeader(50, 50),
            6: _DirectHeader(53, 7),
            7: _DirectHeader(53, 7),
        }
        self._integers = {
            1: np.asarray([1, 0, 2], dtype=int),
            2: np.asarray([1, 2, 1], dtype=int),
            3: np.asarray([1, 0, 0, 1, 0], dtype=int),
            4: np.asarray([1, 2], dtype=int),
            5: np.asarray([1, 2], dtype=int),
            6: np.asarray([0, 1, 1, 0], dtype=int),
            7: np.asarray([0, 1, 1, 0], dtype=int),
        }
        self._reals = {
            1: np.asarray([0.5]),
            2: np.asarray([], dtype=float),
            3: np.asarray([2.0, 3.0, 0.0, 12.0]),
            4: np.asarray([10.0]),
            5: np.asarray([20.0]),
            6: np.asarray([1.0]),
            7: np.asarray([2.0]),
        }

    def header(self, record: int) -> _DirectHeader:
        return self._headers[int(record)]

    def record_integers(self, record: int) -> np.ndarray:
        return self._integers[int(record)]

    def record_reals(self, record: int) -> np.ndarray:
        return self._reals[int(record)]

    def record_chars(self, record: int) -> bytes:
        return b""


class _DirectHeattDerived:
    def __init__(self) -> None:
        self.npfirst = np.zeros(20, dtype=int)
        self.npfirst[11] = 1
        self.npfirst[12] = 2
        self.npar = np.zeros(8, dtype=int)
        self.npar[2] = 1
        self.npar[3:8] = 2
        self.npnxt = np.zeros(8, dtype=int)
        self.npnxt[6] = 7
        self.npfi = np.zeros((20, 3), dtype=int)
        self.npfi[13, 1] = 3
        self.npfi[7, 1] = 6
        self.nplin = np.zeros(5, dtype=int)
        self.nplin[1] = 4
        self.nplin[2] = 5
        self.npconi2 = np.zeros(8, dtype=int)
        self.npconi2[6] = 1
        self.npconi2[7] = 2
        self.nlevs = np.asarray([0, 1, 0], dtype=int)
        self.ion_records = np.asarray([0, 2, 0], dtype=int)


def direct_fortran_heatt_reference_case() -> Mapping[str, Any]:
    """Frozen output from unmodified ``heatt.f90`` compiled with stubs."""
    return {
        "zrems": [
            [109.17404856295778, 107.00339898608938, 66.50385820812258, 110.60463113327397, -1005.0, -1006.0],
            [202.85360492385408, 205.44313626153624, 207.5293677704822, 210.71820750863256, -2005.0, -2006.0],
            [307.82284365588839, 307.28155290796735, 306.42668655671304, 306.38590547035551, -3005.0, -3006.0],
            [402.85360492385405, 405.40063059293834, 407.63968123502218, 410.42523910229369, -4005.0, -4006.0],
            [507.82284365588839, 507.21635190500496, 506.51014404683497, 506.28186061576787, -5005.0, -5006.0],
        ],
        "elum": [
            [5.7560000419616699, -900.0, -900.0, -900.0],
            [8.5120000839233398, -900.0, -900.0, -900.0],
        ],
        "elumab": [
            [9.5024000167846676, -600.0, -600.0],
            [10.502400016784668, -600.0, -600.0],
        ],
        "leveltemp_energy": [2.0, 222.0, 0.0],
        "leveltemp_ionpot": [12.0, 444.0, 0.0],
    }


def _direct_heatt_python_result() -> HeattResult:
    master = _DirectHeattMaster()
    derived = _DirectHeattDerived()
    epi = np.asarray([1.0, 10.0, 100.0, 1000.0, 2000.0, 3000.0])
    bremsa = np.asarray([2.0, 3.0, 4.0, 5.0, 77.0, 88.0])
    opakc = np.asarray([0.02, 0.1, 1.0, 0.04, 7.0, 8.0])
    opakcont = np.asarray([0.01, 0.2, 0.8, 0.4, 9.0, 10.0])
    brcems = np.asarray([0.005, 0.006, 0.007, 0.008, 66.0, 67.0])
    flinel = np.asarray([1.0, 2.0, 3.0, 4.0, 55.0, 56.0])
    rccemis = np.zeros((2, 6), dtype=float)
    rccemis[0, :4] = [0.01, 0.02, 0.03, 0.04]
    rccemis[1, :4] = [0.04, 0.03, 0.02, 0.01]
    rccemis[:, 4:] = np.asarray([[91.0, 93.0], [92.0, 94.0]])
    zrems = np.empty((5, 6), dtype=float)
    zremso = np.empty((5, 6), dtype=float)
    for row in range(5):
        for col in range(6):
            zrems[row, col] = -1000.0 * (row + 1) - (col + 1)
            zremso[row, col] = 100.0 * (row + 1) + (col + 1)
    elum = np.full((2, 4), -900.0)
    elumo = np.full((2, 4), -800.0)
    elumo[:, 0] = [5.0, 6.0]
    elumo[:, 1] = [7.0, 8.0]
    elumab = np.full((2, 3), -600.0)
    elumabo = np.full((2, 3), -700.0)
    elumabo[:, 0] = [9.0, 10.0]
    elumabo[:, 1] = [11.0, 12.0]
    elumabo[:, 2] = [13.0, 14.0]
    rcem = np.zeros((2, 4), dtype=float)
    rcem[:, 0] = [0.1, 0.2]
    rcem[:, 1] = [0.3, 0.4]
    cemab = np.zeros((2, 3), dtype=float)
    cemab[:, 0] = [0.03, 0.05]
    leveltemp = UCalcLevelTable(
        levels={
            1: UCalcLevel(index=1),
            2: UCalcLevel(
                index=2, energy_ev=222.0, ionization_potential_ev=444.0
            ),
            3: UCalcLevel(index=3),
        },
        nlev=0,
    )
    return heatt(
        temperature_1e4K=2.0,
        radius_cm=2.0e19,
        covering_fraction=0.3,
        zone_thickness_cm=0.25,
        electron_fraction_xee=1.2,
        hydrogen_density_cm3=5.0,
        abundances_by_z={1: 1.0, 2: 0.5},
        epi_eV=epi,
        bremsa=bremsa,
        leveltemp_workspace=leveltemp,
        zrems_before=zrems,
        zremso=zremso,
        elumab_before=elumab,
        elumabo=elumabo,
        elum_before=elum,
        elumo=elumo,
        rcem=rcem,
        rccemis=rccemis,
        opakc=opakc,
        opakcont=opakcont,
        cemab=cemab,
        flinel=flinel,
        brcems=brcems,
        master=master,
        derived=derived,
        ncn2=4,
        n_lines=2,
        n_continua=2,
    )


def run_direct_fortran_heatt_validation(
    *, rtol: float = 2.0e-15, atol: float = 0.0
) -> Mapping[str, Any]:
    refs = direct_fortran_heatt_reference_case()
    result = _direct_heatt_python_result()
    energy = [result.leveltemp_workspace.energy(i) for i in range(1, 4)]
    ionpot = [
        float(result.leveltemp_workspace.require(i).ionization_potential_ev)
        for i in range(1, 4)
    ]
    summary = {
        "heatt_translated": True,
        "heatt_continuum_direct_fortran_ready": bool(
            np.allclose(result.zrems_after, refs["zrems"], rtol=rtol, atol=atol)
        ),
        "heatt_line_direct_fortran_ready": bool(
            np.allclose(result.elum_after, refs["elum"], rtol=rtol, atol=atol)
        ),
        "heatt_rrc_direct_fortran_ready": bool(
            np.allclose(result.elumab_after, refs["elumab"], rtol=rtol, atol=atol)
        ),
        "heatt_leveltemp_direct_fortran_ready": bool(
            np.allclose(energy, refs["leveltemp_energy"], rtol=rtol, atol=atol)
            and np.allclose(ionpot, refs["leveltemp_ionpot"], rtol=rtol, atol=atol)
        ),
        "heatt_caller_tail_ownership_ready": bool(
            np.array_equal(result.zrems_after[:, 4:], result.zrems_before[:, 4:])
            and np.all(result.elum_after[:, 2:] == -900.0)
            and np.all(result.elumab_after[:, 1:] == -600.0)
        ),
        "heatt_stale_optp2_line_semantics_ready": bool(
            result.line_traces[0].evaluated
            and math.isclose(result.line_traces[0].inherited_optp2, 0.4)
            and result.line_traces[1].evaluated is False
        ),
        "heatt_uninitialized_compton_diagnostic_explicit_ready": bool(
            result.compton_coefficients_source_initialized is False
        ),
    }
    summary["heatt_direct_original_fortran_reference_ready"] = bool(
        all(value for key, value in summary.items() if key.endswith("_ready"))
    )
    return summary

__all__ += ["direct_fortran_heatt_reference_case", "run_direct_fortran_heatt_validation"]
