"""Bounded radial-shell translation from ``xstar.f90``.

This module translates the four radial kernels that have no unresolved atomic
physics dependency in the first bounded Milestone-5 release::

    step -> trnfrc -> [accepted local xstarcalc] -> heatt -> stpcut -> trnfrn

``heatt`` remains an explicit caller-supplied state handler.  The optional
``gsmooth`` branch and reverse-pass ``unsavd`` restoration are deliberately not
approximated: the driver raises at those source routines until they are ported.
Output writers are outside this bounded shell contract.

The low-level kernels preserve the source's active-range mutation and caller-
owned tail semantics.  Default-real constants that participate in mixed
real(4)/real(8) expressions are rounded through binary32 before use.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import numpy as np

from .driver import (
    XSTARPythonDriver,
    XSTARSourceRoutine,
    UnportedXSTARSourceRoutine,
)
from .emergent_emissivity import CalcEmisWorkspace
from .radiation import nbinc
from .state import XSTARPythonState
from .xstarcalc import register_complete_local_xstarcalc_source_routines


XSTAR_STEP_RADIUS_SCALE = float(np.float32(1.0e-19))
XSTAR_STEP_GEOMETRY_FACTOR = float(np.float32(12.56))
XSTAR_STEP_ZREMS_GATE = float(np.float32(1.0e-12))
XSTAR_STEP_OPACITY_FLOOR = 1.0e-49

XSTAR_TRNFRC_RADIUS_SCALE = float(np.float32(1.0e19))
XSTAR_TRNFRC_GEOMETRY_FACTOR = float(np.float32(12.56))
XSTAR_TRNFRC_ERG_PER_EV = float(np.float32(1.602197e-12))


class RadialTransferPortError(RuntimeError):
    """Raised when a translated radial source contract is invalid."""


RadialStateHandler = Callable[[XSTARPythonState], Any]


@dataclass(frozen=True)
class StepResult:
    """Result of the literal ``step.f90`` zone-size calculation."""

    delr_cm: float
    selected_bin_one_based: int
    initial_delr_cm: float
    remaining_column_delr_cm: float
    radius_column_limit_cm: float
    source_file: str = "xstar/xstarlib/src/step.f90"


@dataclass(frozen=True)
class TrnfrcResult:
    """Result of ``trnfrc.f90`` on caller-owned continuum arrays."""

    direction: int
    ncn2: int
    nry: int
    fpr2: float
    bremsa_before: np.ndarray
    bremsa_after: np.ndarray
    bremsint_before: np.ndarray
    bremsint_after: np.ndarray
    source_file: str = "xstar/xstarlib/src/trnfrc.f90"


@dataclass(frozen=True)
class StpcutResult:
    """Result of ``stpcut.f90`` optical-depth accumulation."""

    direction: int
    direction_row_one_based: int
    ncn2: int
    n_lines: int
    n_continua: int
    dpthc_before: np.ndarray
    dpthc_after: np.ndarray
    dpthcont_before: np.ndarray
    dpthcont_after: np.ndarray
    tau0_before: np.ndarray
    tau0_after: np.ndarray
    tauc_before: np.ndarray
    tauc_after: np.ndarray
    max_zone_continuum_depth: float
    source_file: str = "xstar/xstarlib/src/stpcut.f90"


@dataclass(frozen=True)
class TrnfrnResult:
    """Result of ``trnfrn.f90`` transfer-state commit."""

    ncn2: int
    n_lines: int
    n_continua: int
    zremso_before: np.ndarray
    zremso_after: np.ndarray
    elumo_before: np.ndarray
    elumo_after: np.ndarray
    elumabo_before: np.ndarray
    elumabo_after: np.ndarray
    source_file: str = "xstar/xstarlib/src/trnfrn.f90"


@dataclass
class RadialTransferWorkspace:
    """Caller-owned arrays shared by the bounded radial-shell sequence.

    ``emissivity`` is the same :class:`CalcEmisWorkspace` passed through the
    accepted ``calc_emisab_all``/``calc_emis_all`` sequence.  Its line and RRC
    arrays have Python one-based guard rows; the transfer kernels receive only
    their physical ``1:nlsvn`` / ``1:ncsvn`` slices.
    """

    emissivity: CalcEmisWorkspace
    zremsz: np.ndarray
    dpthc: np.ndarray
    dpthcont: np.ndarray
    tau0: np.ndarray
    tauc: np.ndarray
    zrems: np.ndarray
    zremso: np.ndarray
    elumab: np.ndarray
    elumabo: np.ndarray
    elum: np.ndarray
    elumo: np.ndarray

    def validate(self, *, ncn2: int, n_lines: int, n_continua: int) -> None:
        n = int(ncn2)
        nl = int(n_lines)
        nc = int(n_continua)
        if n < 2:
            raise RadialTransferPortError("radial transfer requires ncn2 >= 2")
        if nl < 0 or nc < 0:
            raise RadialTransferPortError("line and continuum counts must be nonnegative")

        checks = {
            "zremsz": np.asarray(self.zremsz).ndim == 1 and np.asarray(self.zremsz).size >= n,
            "dpthc": np.asarray(self.dpthc).ndim == 2 and np.asarray(self.dpthc).shape[0] == 2 and np.asarray(self.dpthc).shape[1] >= n,
            "dpthcont": np.asarray(self.dpthcont).ndim == 2 and np.asarray(self.dpthcont).shape[0] == 2 and np.asarray(self.dpthcont).shape[1] >= n,
            "tau0": np.asarray(self.tau0).ndim == 2 and np.asarray(self.tau0).shape[0] == 2 and np.asarray(self.tau0).shape[1] >= nl,
            "tauc": np.asarray(self.tauc).ndim == 2 and np.asarray(self.tauc).shape[0] == 2 and np.asarray(self.tauc).shape[1] >= nc,
            "zrems": np.asarray(self.zrems).ndim == 2 and np.asarray(self.zrems).shape[0] >= 5 and np.asarray(self.zrems).shape[1] >= n,
            "zremso": np.asarray(self.zremso).ndim == 2 and np.asarray(self.zremso).shape[0] >= 5 and np.asarray(self.zremso).shape[1] >= n,
            "elumab": np.asarray(self.elumab).ndim == 2 and np.asarray(self.elumab).shape[0] >= 2 and np.asarray(self.elumab).shape[1] >= nc,
            "elumabo": np.asarray(self.elumabo).ndim == 2 and np.asarray(self.elumabo).shape[0] >= 2 and np.asarray(self.elumabo).shape[1] >= nc,
            "elum": np.asarray(self.elum).ndim == 2 and np.asarray(self.elum).shape[0] >= 2 and np.asarray(self.elum).shape[1] >= nl,
            "elumo": np.asarray(self.elumo).ndim == 2 and np.asarray(self.elumo).shape[0] >= 2 and np.asarray(self.elumo).shape[1] >= nl,
        }
        bad = [name for name, ok in checks.items() if not ok]
        if bad:
            raise RadialTransferPortError(
                "invalid radial workspace shapes: " + ", ".join(bad)
            )

        self.emissivity.validate(
            n_lines=nl,
            n_continua=nc,
            n_energy=n,
        )
        for name in checks:
            arr = np.asarray(getattr(self, name), dtype=float)
            if not np.all(np.isfinite(arr)):
                raise RadialTransferPortError(f"{name} contains non-finite values")

    @property
    def opakc(self) -> np.ndarray:
        return self.emissivity.base.opakc

    @property
    def opakcont(self) -> np.ndarray:
        return self.emissivity.base.opakcont

    @property
    def rccemis(self) -> np.ndarray:
        return self.emissivity.base.rccemis

    @property
    def oplin_physical(self) -> np.ndarray:
        return self.emissivity.base.oplin[1:]

    @property
    def opakab_physical(self) -> np.ndarray:
        return self.emissivity.base.opakab[1:]

    @property
    def fline_physical(self) -> np.ndarray:
        return self.emissivity.fline[:, 1:]


@dataclass(frozen=True)
class BoundedRadialShellResult:
    """Summary of one accepted bounded first-pass radial shell."""

    state: XSTARPythonState
    zone_index: int
    pass_index: int
    direction: int
    source_order: tuple[str, ...]
    skipped_source_routines: tuple[str, ...]
    step_executed: bool
    output_writers_executed: bool
    source_file: str = "xstar/src/xstar/xstar.f90"


def _vector(values: Sequence[float], *, name: str, minimum: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    if arr.size < int(minimum):
        raise RadialTransferPortError(f"{name} is shorter than the active range")
    if not np.all(np.isfinite(arr)):
        raise RadialTransferPortError(f"{name} contains non-finite values")
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
        raise RadialTransferPortError(
            f"{name} must have at least shape ({rows}, {columns})"
        )
    if not np.all(np.isfinite(arr)):
        raise RadialTransferPortError(f"{name} contains non-finite values")
    return arr


def step(
    ectt_eV: float,
    emult: float,
    epi_eV: Sequence[float],
    opakc: Sequence[float],
    rccemis: Sequence[Sequence[float]],
    fline: Sequence[Sequence[float]],
    zrems: Sequence[Sequence[float]],
    dpthc: Sequence[Sequence[float]],
    *,
    ncn2: int,
    radius_cm: float,
    column_limit_cm2: float,
    column_cm2: float,
    hydrogen_density_cm3: float,
    taumax: float,
    numrec0: int,
) -> StepResult:
    """Translate ``step.f90`` in literal assignment and branch order."""
    n = int(ncn2)
    epi = _vector(epi_eV, name="epi", minimum=n)
    opacity = _vector(opakc, name="opakc", minimum=n)
    rrc = _matrix(rccemis, name="rccemis", rows=2, columns=n)
    # ``fline`` participates only in source diagnostics guarded by ``lpri``;
    # the numerical step calculation never reads it.  Preserve only its
    # two-direction rank contract here so bounded synthetic line counts need
    # not equal the continuum-grid length.
    fline_arr = np.asarray(fline, dtype=float)
    if fline_arr.ndim != 2 or fline_arr.shape[0] < 2:
        raise RadialTransferPortError("fline must have two direction rows")
    if not np.all(np.isfinite(fline_arr)):
        raise RadialTransferPortError("fline contains non-finite values")
    master = _matrix(zrems, name="zrems", rows=1, columns=n)
    depths = _matrix(dpthc, name="dpthc", rows=1, columns=n)

    xpx = float(hydrogen_density_cm3)
    r = float(radius_cm)
    nrec = int(numrec0)
    if xpx == 0.0:
        raise RadialTransferPortError("step source division requires nonzero xpx")
    if nrec == 0:
        raise RadialTransferPortError("step source division requires nonzero numrec0")

    rmax = float(column_limit_cm2) / xpx
    delr = min(rmax, r / nrec)
    initial_delr = delr
    r19 = r * XSTAR_STEP_RADIUS_SCALE
    fpr2 = XSTAR_STEP_GEOMETRY_FACTOR * r19 * r19
    klmn = 1

    for kl in range(1, n + 1):
        idx = kl - 1
        optp2 = max(float(opacity[idx]), XSTAR_STEP_OPACITY_FLOOR)
        dell = max(
            optp2 * float(master[0, idx]),
            (float(rrc[0, idx]) + float(rrc[1, idx])) * fpr2,
        )
        # Preserve the source's immediately overwritten first estimate.
        tst = float(emult) * float(master[0, idx]) / (
            abs(dell) + XSTAR_STEP_OPACITY_FLOOR
        )
        del tst
        tst = float(emult) / optp2
        if (
            float(epi[idx]) > float(ectt_eV)
            and float(depths[0, idx]) <= float(taumax)
            and float(master[0, idx]) > XSTAR_STEP_ZREMS_GATE
        ):
            if tst < delr:
                klmn = kl
            delr = min(delr, tst)

    delrmn = (float(column_limit_cm2) - float(column_cm2)) / xpx
    delr = min(delr, delrmn)
    return StepResult(
        delr_cm=float(delr),
        selected_bin_one_based=int(klmn),
        initial_delr_cm=float(initial_delr),
        remaining_column_delr_cm=float(delrmn),
        radius_column_limit_cm=float(rmax),
    )


def trnfrc(
    *,
    direction: int,
    radius_cm: float,
    column_limit_cm2: float,
    hydrogen_density_cm3: float,
    epi_eV: Sequence[float],
    zremsz: Sequence[float],
    dpthc: Sequence[Sequence[float]],
    opakc: Sequence[float],
    zrems: Sequence[Sequence[float]],
    bremsa_before: Sequence[float],
    bremsint_before: Sequence[float],
    ncn2: int,
) -> TrnfrcResult:
    """Translate ``trnfrc.f90`` with active-range/tail ownership intact."""
    n = int(ncn2)
    if n < 2:
        raise RadialTransferPortError("trnfrc requires ncn2 >= 2")
    epi = _vector(epi_eV, name="epi", minimum=n)
    source = _vector(zremsz, name="zremsz", minimum=n)
    depths = _matrix(dpthc, name="dpthc", rows=1, columns=n)
    _vector(opakc, name="opakc", minimum=n)
    master = _matrix(zrems, name="zrems", rows=1, columns=n)
    brem_before = _vector(bremsa_before, name="bremsa", minimum=n)
    bint_before = _vector(bremsint_before, name="bremsint", minimum=n)

    xpx = float(hydrogen_density_cm3)
    if xpx == 0.0:
        raise RadialTransferPortError("trnfrc source division requires nonzero xpx")
    del column_limit_cm2  # Source uses rmax only for diagnostics.

    r19 = float(radius_cm) / XSTAR_TRNFRC_RADIUS_SCALE
    fpr2 = XSTAR_TRNFRC_GEOMETRY_FACTOR * r19 * r19
    if fpr2 == 0.0:
        raise RadialTransferPortError("trnfrc source division requires nonzero radius")
    ncnm = n - 1
    brem_after = brem_before.copy()
    bint_after = bint_before.copy()
    # Fortran rows ncn2 and ncn2-1 are cleared before the descending loop.
    brem_after[n - 1] = 0.0
    brem_after[ncnm - 1] = 0.0
    bint_after[n - 1] = 0.0
    bint_after[ncnm - 1] = 0.0
    nry = int(nbinc(13.6, epi, n) + 2)

    for jkp in range(1, ncnm + 1):
        jk = ncnm + 1 - jkp  # one-based
        idx = jk - 1
        if int(direction) < 0:
            brem_after[idx] = float(master[0, idx]) / fpr2
        else:
            brem_after[idx] = (
                float(source[idx]) * math.exp(-float(depths[0, idx])) / fpr2
            )
        sumtmp = (
            (float(brem_after[idx]) + float(brem_after[idx + 1]))
            * (float(epi[idx + 1]) - float(epi[idx]))
            / 2.0
        )
        bint_after[idx] = (
            float(bint_after[idx + 1]) + sumtmp * XSTAR_TRNFRC_ERG_PER_EV
        )

    return TrnfrcResult(
        direction=int(direction),
        ncn2=n,
        nry=nry,
        fpr2=float(fpr2),
        bremsa_before=brem_before.copy(),
        bremsa_after=brem_after,
        bremsint_before=bint_before.copy(),
        bremsint_after=bint_after,
    )


def stpcut(
    *,
    direction: int,
    epi_eV: Sequence[float],
    opakc: Sequence[float],
    opakcont: Sequence[float],
    oplin: Sequence[float],
    opakab: Sequence[float],
    delr_cm: float,
    dpthc_before: Sequence[Sequence[float]],
    dpthcont_before: Sequence[Sequence[float]],
    tau0_before: Sequence[Sequence[float]],
    tauc_before: Sequence[Sequence[float]],
    ncn2: int,
    n_lines: int,
    n_continua: int,
) -> StpcutResult:
    """Translate ``stpcut.f90`` and mutate only the selected direction row."""
    n = int(ncn2)
    nl = int(n_lines)
    nc = int(n_continua)
    _vector(epi_eV, name="epi", minimum=n)
    opacity = _vector(opakc, name="opakc", minimum=n)
    opacity_cont = _vector(opakcont, name="opakcont", minimum=n)
    line_opacity = _vector(oplin, name="oplin", minimum=nl)
    rrc_opacity = _vector(opakab, name="opakab", minimum=nc)
    dpth_before = _matrix(dpthc_before, name="dpthc", rows=2, columns=n)
    dpthcont_before_arr = _matrix(
        dpthcont_before, name="dpthcont", rows=2, columns=n
    )
    line_before = _matrix(tau0_before, name="tau0", rows=2, columns=nl)
    rrc_before = _matrix(tauc_before, name="tauc", rows=2, columns=nc)

    dpth_after = dpth_before.copy()
    dpthcont_after = dpthcont_before_arr.copy()
    line_after = line_before.copy()
    rrc_after = rrc_before.copy()
    lind = 1 if int(direction) > 0 else 0  # Python row; source lind=2/1.
    delr = float(delr_cm)
    dpthmx = 0.0

    # ``optmp`` is explicitly zeroed by the source and never filled in the
    # active routine, so ``optpp`` remains zero for every bin.
    for i in range(n):
        optpp = min(0.0, float(np.float32(1.0e3)) / (float(np.float32(1.0e-24)) + delr))
        dpthtmp = (float(opacity[i]) + optpp) * delr
        dpthtmpcont = float(opacity_cont[i]) * delr
        dpth_after[lind, i] = float(dpth_after[lind, i]) + dpthtmp
        dpthcont_after[lind, i] = (
            float(dpthcont_after[lind, i]) + dpthtmpcont
        )
        if dpthtmp > dpthmx:
            dpthmx = dpthtmp

    for i in range(nl):
        line_after[lind, i] = float(line_after[lind, i]) + float(line_opacity[i]) * delr
    for i in range(nc):
        rrc_after[lind, i] = float(rrc_after[lind, i]) + float(rrc_opacity[i]) * delr

    return StpcutResult(
        direction=int(direction),
        direction_row_one_based=lind + 1,
        ncn2=n,
        n_lines=nl,
        n_continua=nc,
        dpthc_before=dpth_before.copy(),
        dpthc_after=dpth_after,
        dpthcont_before=dpthcont_before_arr.copy(),
        dpthcont_after=dpthcont_after,
        tau0_before=line_before.copy(),
        tau0_after=line_after,
        tauc_before=rrc_before.copy(),
        tauc_after=rrc_after,
        max_zone_continuum_depth=float(dpthmx),
    )


def trnfrn(
    *,
    zrems: Sequence[Sequence[float]],
    zremso_before: Sequence[Sequence[float]],
    elumab: Sequence[Sequence[float]],
    elumabo_before: Sequence[Sequence[float]],
    elum: Sequence[Sequence[float]],
    elumo_before: Sequence[Sequence[float]],
    ncn2: int,
    n_lines: int,
    n_continua: int,
) -> TrnfrnResult:
    """Translate ``trnfrn.f90`` active-range state commits."""
    n = int(ncn2)
    nl = int(n_lines)
    nc = int(n_continua)
    current_cont = _matrix(zrems, name="zrems", rows=5, columns=n)
    old_cont = _matrix(zremso_before, name="zremso", rows=5, columns=n)
    current_rrc = _matrix(elumab, name="elumab", rows=2, columns=nc)
    old_rrc = _matrix(elumabo_before, name="elumabo", rows=2, columns=nc)
    current_lines = _matrix(elum, name="elum", rows=2, columns=nl)
    old_lines = _matrix(elumo_before, name="elumo", rows=2, columns=nl)

    cont_after = old_cont.copy()
    lines_after = old_lines.copy()
    rrc_after = old_rrc.copy()
    cont_after[:5, :n] = current_cont[:5, :n]
    lines_after[:2, :nl] = current_lines[:2, :nl]
    rrc_after[:2, :nc] = current_rrc[:2, :nc]
    return TrnfrnResult(
        ncn2=n,
        n_lines=nl,
        n_continua=nc,
        zremso_before=old_cont.copy(),
        zremso_after=cont_after,
        elumo_before=old_lines.copy(),
        elumo_after=lines_after,
        elumabo_before=old_rrc.copy(),
        elumabo_after=rrc_after,
    )


def _workspace_from_state(state: XSTARPythonState) -> RadialTransferWorkspace:
    workspace = state.control.get("radial_transfer_workspace")
    if not isinstance(workspace, RadialTransferWorkspace):
        raise RadialTransferPortError(
            "state.control['radial_transfer_workspace'] must be a "
            "RadialTransferWorkspace"
        )
    ncn2 = int(state.control.get("ncn2", 0))
    n_lines = int(state.control.get("nlsvn", workspace.elum.shape[1]))
    n_continua = int(state.control.get("ncsvn", workspace.elumab.shape[1]))
    workspace.validate(ncn2=ncn2, n_lines=n_lines, n_continua=n_continua)

    # Bind the explicit radial workspace to the top-level caller-owned state.
    # Once bound, a second nonidentical array is an ownership error rather than
    # an invitation to copy silently.
    if state.radiation.zrems is None:
        state.radiation.zrems = workspace.zrems
    elif state.radiation.zrems is not workspace.zrems:
        raise RadialTransferPortError(
            "radiation.zrems must be the same caller-owned array as the radial workspace"
        )
    if state.radiation.zremso is None:
        state.radiation.zremso = workspace.zremso
    elif state.radiation.zremso is not workspace.zremso:
        raise RadialTransferPortError(
            "radiation.zremso must be the same caller-owned array as the radial workspace"
        )
    if state.transfer.tau_in is None:
        state.transfer.tau_in = workspace.dpthc[0]
    if state.transfer.tau_out is None:
        state.transfer.tau_out = workspace.dpthc[1]
    return workspace


def apply_step_to_state(state: XSTARPythonState) -> StepResult:
    workspace = _workspace_from_state(state)
    ncn2 = int(state.control["ncn2"])
    result = step(
        float(state.control.get("ectt", 1.0)),
        float(state.control.get("emult", 1.0)),
        state.radiation.epi,
        workspace.opakc,
        workspace.rccemis,
        workspace.fline_physical,
        workspace.zrems,
        workspace.dpthc,
        ncn2=ncn2,
        radius_cm=float(state.transfer.radius),
        column_limit_cm2=float(state.control["xpxcol"]),
        column_cm2=float(state.transfer.column),
        hydrogen_density_cm3=float(state.plasma.xpx),
        taumax=float(state.control.get("taumax", 1.0e30)),
        numrec0=int(state.control["numrec"]),
    )
    state.transfer.step_size = result.delr_cm
    state.control["delr"] = result.delr_cm
    state.transfer.source_arrays["step"] = result
    state.transfer.provenance["step"] = {
        "source_file": result.source_file,
        "selected_bin_one_based": result.selected_bin_one_based,
        "active_ncn2": ncn2,
    }
    return result


def apply_trnfrc_to_state(state: XSTARPythonState) -> TrnfrcResult:
    workspace = _workspace_from_state(state)
    if state.radiation.epi is None or state.radiation.bremsa is None or state.radiation.bremsint is None:
        raise RadialTransferPortError(
            "radiation state must provide epi, bremsa, and bremsint"
        )
    ncn2 = int(state.control["ncn2"])
    result = trnfrc(
        direction=int(state.transfer.direction),
        radius_cm=float(state.transfer.radius),
        column_limit_cm2=float(state.control["xpxcol"]),
        hydrogen_density_cm3=float(state.plasma.xpx),
        epi_eV=state.radiation.epi,
        zremsz=workspace.zremsz,
        dpthc=workspace.dpthc,
        opakc=workspace.opakc,
        zrems=workspace.zrems,
        bremsa_before=state.radiation.bremsa,
        bremsint_before=state.radiation.bremsint,
        ncn2=ncn2,
    )
    np.asarray(state.radiation.bremsa)[:] = result.bremsa_after
    np.asarray(state.radiation.bremsint)[:] = result.bremsint_after
    state.control["nry"] = result.nry
    state.transfer.source_arrays["trnfrc"] = result
    state.transfer.provenance["trnfrc"] = {
        "source_file": result.source_file,
        "direction": result.direction,
        "active_ncn2": result.ncn2,
        "nry": result.nry,
    }
    return result


def apply_heatt_to_state(state: XSTARPythonState) -> Any:
    """Invoke the explicit translated-state placeholder for ``heatt.f90``."""
    handler = state.control.get("heatt_source_handler")
    if not callable(handler):
        raise RadialTransferPortError(
            "state.control['heatt_source_handler'] must be a callable; heatt "
            "is intentionally not approximated in this release"
        )
    result = handler(state)
    state.transfer.source_arrays["heatt"] = result
    state.transfer.provenance["heatt"] = {
        "source_file": "xstar/xstarlib/src/heatt.f90",
        "handler": "state.control['heatt_source_handler']",
        "translated_physics": False,
    }
    return result


def apply_stpcut_to_state(state: XSTARPythonState) -> StpcutResult:
    workspace = _workspace_from_state(state)
    ncn2 = int(state.control["ncn2"])
    n_lines = int(state.control.get("nlsvn", workspace.elum.shape[1]))
    n_continua = int(state.control.get("ncsvn", workspace.elumab.shape[1]))
    result = stpcut(
        direction=int(state.transfer.direction),
        epi_eV=state.radiation.epi,
        opakc=workspace.opakc,
        opakcont=workspace.opakcont,
        oplin=workspace.oplin_physical,
        opakab=workspace.opakab_physical,
        delr_cm=float(state.transfer.step_size),
        dpthc_before=workspace.dpthc,
        dpthcont_before=workspace.dpthcont,
        tau0_before=workspace.tau0,
        tauc_before=workspace.tauc,
        ncn2=ncn2,
        n_lines=n_lines,
        n_continua=n_continua,
    )
    workspace.dpthc[:, :] = result.dpthc_after
    workspace.dpthcont[:, :] = result.dpthcont_after
    workspace.tau0[:, :] = result.tau0_after
    workspace.tauc[:, :] = result.tauc_after
    state.transfer.source_arrays["stpcut"] = result
    state.transfer.provenance["stpcut"] = {
        "source_file": result.source_file,
        "direction_row_one_based": result.direction_row_one_based,
        "active_ncn2": result.ncn2,
        "n_lines": result.n_lines,
        "n_continua": result.n_continua,
    }
    return result


def apply_trnfrn_to_state(state: XSTARPythonState) -> TrnfrnResult:
    workspace = _workspace_from_state(state)
    ncn2 = int(state.control["ncn2"])
    n_lines = int(state.control.get("nlsvn", workspace.elum.shape[1]))
    n_continua = int(state.control.get("ncsvn", workspace.elumab.shape[1]))
    result = trnfrn(
        zrems=workspace.zrems,
        zremso_before=workspace.zremso,
        elumab=workspace.elumab,
        elumabo_before=workspace.elumabo,
        elum=workspace.elum,
        elumo_before=workspace.elumo,
        ncn2=ncn2,
        n_lines=n_lines,
        n_continua=n_continua,
    )
    workspace.zremso[:, :] = result.zremso_after
    workspace.elumo[:, :] = result.elumo_after
    workspace.elumabo[:, :] = result.elumabo_after
    state.transfer.source_arrays["trnfrn"] = result
    state.transfer.provenance["trnfrn"] = {
        "source_file": result.source_file,
        "active_ncn2": result.ncn2,
        "n_lines": result.n_lines,
        "n_continua": result.n_continua,
    }
    return result


def register_bounded_radial_source_routines(driver: XSTARPythonDriver) -> None:
    """Register translated first-pass kernels plus accepted local ``xstarcalc``."""
    register_complete_local_xstarcalc_source_routines(driver)
    driver.register_source_routine(XSTARSourceRoutine.STEP, apply_step_to_state)
    driver.register_source_routine(XSTARSourceRoutine.TRNFRC, apply_trnfrc_to_state)
    driver.register_source_routine(XSTARSourceRoutine.HEATT, apply_heatt_to_state)
    driver.register_source_routine(XSTARSourceRoutine.STPCUT, apply_stpcut_to_state)
    driver.register_source_routine(XSTARSourceRoutine.TRNFRN, apply_trnfrn_to_state)
    # ``GSSMOOTH`` and ``UNSAVD`` are intentionally not registered.


def run_bounded_radial_shell(
    state: XSTARPythonState,
    *,
    zone_index: int,
    pass_index: int = 1,
    direction: int = 1,
    driver: Optional[XSTARPythonDriver] = None,
    fixed_state: bool = False,
) -> BoundedRadialShellResult:
    """Execute one bounded radial shell around the accepted local driver."""
    runner = driver or XSTARPythonDriver()
    if driver is None:
        register_bounded_radial_source_routines(runner)
    completed_before = len(state.provenance.get("completed_source_routines", []))
    skipped_before = len(state.provenance.get("skipped_source_routines", []))
    runner.run_radial_shell(
        state,
        zone_index=int(zone_index),
        pass_index=int(pass_index),
        direction=int(direction),
        fixed_state=bool(fixed_state),
    )
    source_order = tuple(
        state.provenance.get("completed_source_routines", [])[completed_before:]
    )
    skipped = tuple(
        state.provenance.get("skipped_source_routines", [])[skipped_before:]
    )
    return BoundedRadialShellResult(
        state=state,
        zone_index=int(zone_index),
        pass_index=int(pass_index),
        direction=int(direction),
        source_order=source_order,
        skipped_source_routines=skipped,
        step_executed=XSTARSourceRoutine.STEP.value in source_order,
        output_writers_executed=False,
    )


def direct_fortran_radial_reference_cases() -> Mapping[str, Any]:
    """Frozen outputs from unmodified XSTAR kernels compiled with stubs."""
    return {
        "step_delr": 2.5e13,
        "trnfrc_out_bremsa": [
            1.8010298253952486e-1,
            3.2592783540327841e-1,
            4.4236755157852753e-1,
            5.3369428425760534e-1,
            6.0363319773525137e-1,
            0.0,
            777.0,
            888.0,
        ],
        "trnfrc_out_bremsint": [
            5.2482420098858120e-9,
            5.2480393196213083e-9,
            5.2424999970854445e-9,
            5.1721270465867615e-9,
            4.3521268411437128e-9,
            0.0,
            999.0,
            1111.0,
        ],
        "trnfrc_in_bremsa": [
            5.9713373568410714e-2,
            1.1942674713682143e-1,
            1.7914012070523216e-1,
            2.3885349427364286e-1,
            2.9856686784205361e-1,
            0.0,
            777.0,
            888.0,
        ],
        "trnfrc_in_bremsint": [
            2.5724684627775849e-9,
            2.5723967083366270e-9,
            2.5702440751078934e-9,
            2.5401072099056233e-9,
            2.1526332287335790e-9,
            0.0,
            999.0,
            1111.0,
        ],
        "stpcut_dpthc": [
            [101.0, 103.0, 105.0, 107.0, 109.0, 111.0, 113.0, 115.0],
            [102.00000002500001, 104.00000025, 106.05, 108.0125, 110.00025, 112.000025, 114.0, 116.0],
        ],
        "stpcut_dpthcont": [
            [201.0, 203.0, 205.0, 207.0, 209.0, 211.0, 213.0, 215.0],
            [202.0125, 204.025, 206.0375, 208.05, 210.0625, 212.075, 214.0, 216.0],
        ],
        "stpcut_tau0": [
            [301.0, 303.0, 305.0, 307.0, 309.0, 311.0, 313.0, 315.0],
            [302.25, 304.5, 306.75, 309.0, 310.0, 312.0, 314.0, 316.0],
        ],
        "stpcut_tauc": [
            [401.0, 403.0, 405.0, 407.0, 409.0, 411.0],
            [402.125, 404.15, 406.175, 408.0, 410.0, 412.0],
        ],
    }


def _direct_reference_inputs() -> Mapping[str, Any]:
    epi = np.asarray([0.5, 1.0, 10.0, 100.0, 1000.0, 10000.0, 20000.0, 40000.0])
    opakc = np.asarray([1e-20, 1e-19, 2e-14, 5e-15, 1e-16, 1e-17, 9.0, 10.0])
    rcc = np.zeros((2, 8))
    zrems = np.zeros((5, 8))
    for i in range(8):
        zrems[0, i] = 1e-3 * (i + 1)
        rcc[0, i] = 1e-7 * (i + 1)
        rcc[1, i] = 2e-7 * (i + 1)
    dpth = np.zeros((2, 8))
    dpth[0, 3] = 20.0
    return {
        "epi": epi,
        "opakc": opakc,
        "rcc": rcc,
        "zrems": zrems,
        "dpth": dpth,
    }


def run_direct_fortran_radial_validation(
    *, rtol: float = 2.0e-15, atol: float = 0.0
) -> Mapping[str, Any]:
    """Compare all four Python kernels with frozen direct-Fortran cases."""
    refs = direct_fortran_radial_reference_cases()
    inp = _direct_reference_inputs()
    step_result = step(
        1.0,
        0.5,
        inp["epi"],
        inp["opakc"],
        inp["rcc"],
        np.zeros((2, 8)),
        inp["zrems"],
        inp["dpth"],
        ncn2=6,
        radius_cm=2e19,
        column_limit_cm2=5e22,
        column_cm2=1e22,
        hydrogen_density_cm3=1e8,
        taumax=10.0,
        numrec0=10,
    )

    zremsz = np.asarray([10., 20., 30., 40., 50., 60., 70., 80.])
    dpth = np.zeros((2, 8))
    dpth[0, :6] = np.asarray([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    zrems = np.zeros((5, 8))
    zrems[0, :6] = np.asarray([3., 6., 9., 12., 15., 18.])
    brem0 = np.asarray([101., 102., 103., 104., 105., 106., 777., 888.])
    bint0 = np.asarray([201., 202., 203., 204., 205., 206., 999., 1111.])
    out_result = trnfrc(
        direction=1,
        radius_cm=2e19,
        column_limit_cm2=5e22,
        hydrogen_density_cm3=1e8,
        epi_eV=inp["epi"],
        zremsz=zremsz,
        dpthc=dpth,
        opakc=inp["opakc"],
        zrems=zrems,
        bremsa_before=brem0,
        bremsint_before=bint0,
        ncn2=6,
    )
    in_result = trnfrc(
        direction=-1,
        radius_cm=2e19,
        column_limit_cm2=5e22,
        hydrogen_density_cm3=1e8,
        epi_eV=inp["epi"],
        zremsz=zremsz,
        dpthc=dpth,
        opakc=inp["opakc"],
        zrems=zrems,
        bremsa_before=brem0,
        bremsint_before=bint0,
        ncn2=6,
    )

    dpthc0 = np.arange(101.0, 117.0).reshape((2, 8), order="F")
    dpthcont0 = np.arange(201.0, 217.0).reshape((2, 8), order="F")
    tau00 = np.arange(301.0, 317.0).reshape((2, 8), order="F")
    tauc0 = np.arange(401.0, 413.0).reshape((2, 6), order="F")
    stp_result = stpcut(
        direction=1,
        epi_eV=inp["epi"],
        opakc=inp["opakc"],
        opakcont=np.asarray([0.5e-14, 1e-14, 1.5e-14, 2e-14, 2.5e-14, 3e-14, 7., 8.]),
        oplin=np.asarray([1e-13, 2e-13, 3e-13, 4e-13, 5., 6., 7., 8.]),
        opakab=np.asarray([5e-14, 6e-14, 7e-14, 8., 9., 10.]),
        delr_cm=2.5e12,
        dpthc_before=dpthc0,
        dpthcont_before=dpthcont0,
        tau0_before=tau00,
        tauc_before=tauc0,
        ncn2=6,
        n_lines=4,
        n_continua=3,
    )

    current_z = np.empty((5, 8))
    for j in range(5):
        for i in range(8):
            current_z[j, i] = 1000.0 * (j + 1) + (i + 1)
    current_l = np.empty((2, 8))
    for j in range(2):
        for i in range(8):
            current_l[j, i] = 2000.0 * (j + 1) + (i + 1)
    current_r = np.empty((2, 6))
    for j in range(2):
        for i in range(6):
            current_r[j, i] = 3000.0 * (j + 1) + (i + 1)
    commit_result = trnfrn(
        zrems=current_z,
        zremso_before=np.full((5, 8), -1.0),
        elumab=current_r,
        elumabo_before=np.full((2, 6), -3.0),
        elum=current_l,
        elumo_before=np.full((2, 8), -2.0),
        ncn2=6,
        n_lines=4,
        n_continua=3,
    )
    trnfrn_cont_ready = bool(
        np.array_equal(commit_result.zremso_after[:, :6], current_z[:, :6])
        and np.all(commit_result.zremso_after[:, 6:] == -1.0)
    )
    trnfrn_line_ready = bool(
        np.array_equal(commit_result.elumo_after[:, :4], current_l[:, :4])
        and np.all(commit_result.elumo_after[:, 4:] == -2.0)
    )
    trnfrn_rrc_ready = bool(
        np.array_equal(commit_result.elumabo_after[:, :3], current_r[:, :3])
        and np.all(commit_result.elumabo_after[:, 3:] == -3.0)
    )

    summary = {
        "port_version": "v0.4.64",
        "step_translated": True,
        "trnfrc_translated": True,
        "stpcut_translated": True,
        "trnfrn_translated": True,
        "step_direct_fortran_ready": bool(
            np.isclose(step_result.delr_cm, refs["step_delr"], rtol=rtol, atol=atol)
        ),
        "trnfrc_out_bremsa_ready": bool(np.allclose(out_result.bremsa_after, refs["trnfrc_out_bremsa"], rtol=rtol, atol=atol)),
        "trnfrc_out_bremsint_ready": bool(np.allclose(out_result.bremsint_after, refs["trnfrc_out_bremsint"], rtol=rtol, atol=atol)),
        "trnfrc_in_bremsa_ready": bool(np.allclose(in_result.bremsa_after, refs["trnfrc_in_bremsa"], rtol=rtol, atol=atol)),
        "trnfrc_in_bremsint_ready": bool(np.allclose(in_result.bremsint_after, refs["trnfrc_in_bremsint"], rtol=rtol, atol=atol)),
        "stpcut_dpthc_ready": bool(np.allclose(stp_result.dpthc_after, refs["stpcut_dpthc"], rtol=rtol, atol=atol)),
        "stpcut_dpthcont_ready": bool(np.allclose(stp_result.dpthcont_after, refs["stpcut_dpthcont"], rtol=rtol, atol=atol)),
        "stpcut_tau0_ready": bool(np.allclose(stp_result.tau0_after, refs["stpcut_tau0"], rtol=rtol, atol=atol)),
        "stpcut_tauc_ready": bool(np.allclose(stp_result.tauc_after, refs["stpcut_tauc"], rtol=rtol, atol=atol)),
        "trnfrn_continuum_active_range_ready": trnfrn_cont_ready,
        "trnfrn_line_active_range_ready": trnfrn_line_ready,
        "trnfrn_rrc_active_range_ready": trnfrn_rrc_ready,
    }
    summary["direct_original_fortran_reference_ready"] = bool(
        all(value for key, value in summary.items() if key.endswith("_ready"))
    )
    return summary


def _build_radial_validation_state(*, zone_index: int) -> XSTARPythonState:
    # Reuse the accepted complete-local fixture, while binding its emissivity
    # arrays to the outer radial caller before any source routine executes.
    from .xstarcalc import _build_validation_state

    state, _ = _build_validation_state(nlimdt=5)
    shared = CalcEmisWorkspace.allocate(
        n_lines=3,
        n_continua=3,
        n_energy=5,
        continuum_fill=0.0,
        fline_fill=0.0,
        flinel_fill=0.0,
    )
    # Inputs seen by step/trnfrc before xstarcalc overwrites emissivity arrays.
    shared.base.opakc[:] = np.asarray([1e-18, 2e-18, 4e-18, 8e-18, 16e-18])
    shared.base.rccemis[:, :] = 0.0
    state.control["preallocated_emissivity_workspace"] = shared

    zrems = np.zeros((5, 5))
    zrems[0, :] = np.asarray([5.0, 4.0, 3.0, 2.0, 1.0])
    workspace = RadialTransferWorkspace(
        emissivity=shared,
        zremsz=np.asarray([20.0, 18.0, 16.0, 14.0, 12.0]),
        dpthc=np.zeros((2, 5)),
        dpthcont=np.zeros((2, 5)),
        tau0=np.zeros((2, 3)),
        tauc=np.zeros((2, 3)),
        zrems=zrems,
        zremso=np.full((5, 5), -7.0),
        elumab=np.zeros((2, 3)),
        elumabo=np.full((2, 3), -8.0),
        elum=np.zeros((2, 3)),
        elumo=np.full((2, 3), -9.0),
    )
    state.control.update({
        "radial_transfer_workspace": workspace,
        "ncn2": 5,
        "ncn2m": 4,
        "nlsvn": 3,
        "ncsvn": 3,
        "nlimd": 5,
        "emult": 0.5,
        "xpxcol": 1.0e21,
        "taumax": 10.0,
        "numrec": 20,
        "xlum": 1.0e38,
        "tinf": 100.0,
        "vturbi": 0.0,
        "radexp": 0.0,
        "lcdd": 1,
        "lpri": 0,
    })
    state.transfer.radius = 1.0e19
    state.transfer.radial_depth = 0.0
    state.transfer.column = 0.0
    state.plasma.xpx = 5.0
    state.plasma.temperature = 1.0e6

    # Make the accepted local validation handler use the exact caller-owned
    # workspace instead of allocating a new object.
    original_hmc = state.control["calc_hmc_all_source_handler"]

    def hmc_with_caller_workspace(runtime: XSTARPythonState) -> Any:
        result = original_hmc(runtime)
        generated = runtime.control["shared_emissivity_workspace"]
        caller = runtime.control["preallocated_emissivity_workspace"]
        # Copy the synthetic context bindings onto the caller object and replace
        # both contexts before calc_emisab_all/calc_emis_all execute.
        caller.base.rcem[:, :] = generated.base.rcem
        caller.base.oplin[:] = generated.base.oplin
        caller.base.brcems[:] = generated.base.brcems
        caller.base.rccemis[:, :] = generated.base.rccemis
        caller.base.opakc[:] = generated.base.opakc
        caller.base.opakcont[:] = generated.base.opakcont
        caller.base.cemab[:, :] = generated.base.cemab
        caller.base.cabab[:] = generated.base.cabab
        caller.base.opakab[:] = generated.base.opakab
        caller.fline[:, :] = generated.fline
        caller.flinel[:] = generated.flinel
        runtime.control["calc_emisab_context"].workspace = caller.base
        runtime.control["calc_emis_context"].workspace = caller
        runtime.control["shared_emissivity_workspace"] = caller
        return result

    state.control["calc_hmc_all_source_handler"] = hmc_with_caller_workspace

    call_trace: list[str] = []

    def heatt_handler(runtime: XSTARPythonState) -> Mapping[str, Any]:
        call_trace.append("heatt")
        ws = runtime.control["radial_transfer_workspace"]
        ws.zrems[:, :] += 100.0
        ws.elum[:, :] = np.asarray([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        ws.elumab[:, :] = np.asarray([[7.0, 8.0, 9.0], [10.0, 11.0, 12.0]])
        runtime.control["heatt_saw_local_emissivity"] = bool(runtime.local_zone.emissivity_ready)
        return {"source_state_only": True, "zone_index": int(zone_index)}

    state.control["heatt_source_handler"] = heatt_handler
    state.control["radial_call_trace"] = call_trace
    return state


def run_bounded_radial_shell_validation(
    *, rtol: float = 2.0e-14, atol: float = 1.0e-30
) -> Mapping[str, Any]:
    """Validate direct kernels, first-pass order, ownership, and boundaries."""
    direct = dict(run_direct_fortran_radial_validation(rtol=rtol, atol=atol))

    zone1_state = _build_radial_validation_state(zone_index=1)
    zone1 = run_bounded_radial_shell(zone1_state, zone_index=1, pass_index=1, direction=1)
    expected_zone1 = (
        "trnfrc",
        "bremsmap",
        "dsec",
        "calc_hmc_all",
        "calc_emisab_all",
        "calc_emis_all",
        "heatt",
        "stpcut",
        "trnfrn",
    )
    zone1_order_ready = zone1.source_order == expected_zone1
    zone1_skip_ready = bool(
        not zone1.step_executed
        and XSTARSourceRoutine.STEP.value in zone1.skipped_source_routines
        and zone1_state.transfer.step_size == 0.0
    )

    zone2_state = _build_radial_validation_state(zone_index=2)
    zone2 = run_bounded_radial_shell(zone2_state, zone_index=2, pass_index=1, direction=1)
    expected_zone2 = (
        "step",
        "trnfrc",
        "bremsmap",
        "dsec",
        "calc_hmc_all",
        "calc_emisab_all",
        "calc_emis_all",
        "heatt",
        "stpcut",
        "trnfrn",
    )
    zone2_order_ready = zone2.source_order == expected_zone2
    zone2_step_ready = bool(
        zone2.step_executed
        and zone2_state.transfer.step_size > 0.0
        and "step" in zone2_state.transfer.source_arrays
    )
    ws2 = zone2_state.control["radial_transfer_workspace"]
    ownership_ready = bool(
        ws2.emissivity is zone2_state.control["shared_emissivity_workspace"]
        and np.array_equal(ws2.zremso, ws2.zrems)
        and np.array_equal(ws2.elumo, ws2.elum)
        and np.array_equal(ws2.elumabo, ws2.elumab)
        and np.any(ws2.dpthc[1, :] != 0.0)
        and np.any(ws2.dpthcont[1, :] != 0.0)
    )
    heatt_boundary_ready = bool(
        zone2_state.control.get("heatt_saw_local_emissivity")
        and zone2_state.control["radial_call_trace"] == ["heatt"]
        and zone2.source_order.index("calc_emis_all") < zone2.source_order.index("heatt")
        < zone2.source_order.index("stpcut")
    )

    reverse_state = _build_radial_validation_state(zone_index=1)
    reverse_failure_ready = False
    reverse_completed: tuple[str, ...] = ()
    try:
        run_bounded_radial_shell(reverse_state, zone_index=1, pass_index=2, direction=-1)
    except UnportedXSTARSourceRoutine as exc:
        reverse_failure_ready = exc.routine is XSTARSourceRoutine.UNSAVD
        reverse_completed = tuple(
            reverse_state.provenance.get("completed_source_routines", [])
        )

    turbulent_state = _build_radial_validation_state(zone_index=1)
    turbulent_state.control["vturbi"] = 1.0
    turbulent_failure_ready = False
    turbulent_completed: tuple[str, ...] = ()
    try:
        run_bounded_radial_shell(turbulent_state, zone_index=1, pass_index=1, direction=1)
    except UnportedXSTARSourceRoutine as exc:
        turbulent_failure_ready = exc.routine is XSTARSourceRoutine.GSSMOOTH
        turbulent_completed = tuple(
            turbulent_state.provenance.get("completed_source_routines", [])
        )
    turbulent_boundary_order_ready = bool(
        turbulent_completed
        == (
            "trnfrc",
            "bremsmap",
            "dsec",
            "calc_hmc_all",
            "calc_emisab_all",
            "calc_emis_all",
        )
        and "heatt" not in turbulent_completed
    )

    summary: dict[str, Any] = {
        **direct,
        "port_version": "v0.4.64",
        "bounded_radial_shell_translated": True,
        "zone1_step_skip_ready": zone1_skip_ready,
        "zone1_first_pass_call_order_ready": zone1_order_ready,
        "zone1_source_order": list(zone1.source_order),
        "later_first_pass_step_ready": zone2_step_ready,
        "later_first_pass_call_order_ready": zone2_order_ready,
        "later_zone_source_order": list(zone2.source_order),
        "shared_radial_array_ownership_ready": ownership_ready,
        "heatt_explicit_source_state_handler_ready": heatt_boundary_ready,
        "reverse_pass_unsavd_explicit_failure_ready": reverse_failure_ready,
        "reverse_pass_completed_before_failure": list(reverse_completed),
        "turbulent_gsmooth_explicit_failure_ready": turbulent_failure_ready,
        "turbulent_failure_source_boundary_ready": turbulent_boundary_order_ready,
        "turbulent_completed_before_failure": list(turbulent_completed),
        "output_writers_excluded_ready": bool(
            not zone1.output_writers_executed
            and not zone2.output_writers_executed
            and not zone2_state.transfer.provenance["radial_shell"]["output_writers_executed"]
        ),
    }
    summary["bounded_radial_shell_source_acceptance_ready"] = bool(
        all(value for key, value in summary.items() if key.endswith("_ready"))
    )
    summary["next_source_target"] = "heatt"
    return summary


def write_bounded_radial_shell_validation_products(
    summary: Mapping[str, Any], out_dir: str | Path
) -> Mapping[str, str]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "xstar_bounded_radial_shell_source_validation_summary.json"
    md_path = out / "xstar_bounded_radial_shell_source_validation_summary.md"
    json_path.write_text(
        json.dumps(dict(summary), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        "# XSTAR bounded radial-shell source validation\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "XSTAR_STEP_RADIUS_SCALE",
    "XSTAR_STEP_GEOMETRY_FACTOR",
    "XSTAR_STEP_ZREMS_GATE",
    "XSTAR_STEP_OPACITY_FLOOR",
    "XSTAR_TRNFRC_RADIUS_SCALE",
    "XSTAR_TRNFRC_GEOMETRY_FACTOR",
    "XSTAR_TRNFRC_ERG_PER_EV",
    "RadialTransferPortError",
    "StepResult",
    "TrnfrcResult",
    "StpcutResult",
    "TrnfrnResult",
    "RadialTransferWorkspace",
    "BoundedRadialShellResult",
    "step",
    "trnfrc",
    "stpcut",
    "trnfrn",
    "apply_step_to_state",
    "apply_trnfrc_to_state",
    "apply_heatt_to_state",
    "apply_stpcut_to_state",
    "apply_trnfrn_to_state",
    "register_bounded_radial_source_routines",
    "run_bounded_radial_shell",
    "direct_fortran_radial_reference_cases",
    "run_direct_fortran_radial_validation",
    "run_bounded_radial_shell_validation",
    "write_bounded_radial_shell_validation_products",
]
