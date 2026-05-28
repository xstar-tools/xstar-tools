"""Bounded radial-shell translation from ``xstar.f90``.

This module translates the bounded first-pass Milestone-5 sequence::

    step -> trnfrc -> [accepted local xstarcalc] -> heatt -> stpcut -> trnfrn

``gsmooth`` and ``heatt`` are translated source routines operating on the same
caller-owned continuum, line, RRC, and mutable state left by ``xstarcalc``.
The smoothing branch executes only for nonzero turbulent velocity and remains
at its literal source position before ``heatt``.  Reverse-pass ``unsavd`` restoration uses a caller-owned in-memory equivalent
of the source FITS shell records, including REAL(4) persistence and HDU insertion
order.  The inline ``density.dat`` branch and fixed requested-pass convergence
contract are also translated.  Output writers remain outside this bounded shell
contract.

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
from .heatt import (
    HeattResult,
    heatt,
    run_direct_fortran_heatt_validation,
)
from .gsmooth import (
    GSmoothResult,
    gsmooth,
    run_direct_fortran_gsmooth_validation,
)
from .radiation import nbinc
from .radial_control import (
    RadialPassConvergenceContract,
    TabulatedRadialDensityState,
    TabulatedRadialRadiusError,
    advance_tabulated_radial_density,
    build_radial_pass_convergence_contract,
    first_pass_shell_condition,
    initialize_tabulated_radial_density,
    repeated_pass_shell_condition,
    run_direct_fortran_tabulated_density_validation,
)
from .saved_radial_state import (
    SavedRadialPassState,
    SavedRadialStatePortError,
    SavedRadialStateStore,
    SavedShellSnapshot,
    UnsavdResult,
    make_saved_shell_snapshot,
    run_direct_fortran_unsavd_validation,
    unsavd,
)
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


def _emit_progress(state: XSTARPythonState, event: str, **details: Any) -> None:
    callback = state.control.get("progress_callback")
    if callable(callback):
        callback(str(event), details)


@dataclass(frozen=True)
class StepResult:
    """Result of the literal ``step.f90`` zone-size calculation.

    The trace fields are source-order observables for the physical radial
    runner.  They do not change the step calculation; they preserve the exact
    selected opacity bin and limiting values needed to compare Python with the
    original ``step.f90`` call at the missing intermediate-zone boundary.
    """

    delr_cm: float
    selected_bin_one_based: int
    initial_delr_cm: float
    remaining_column_delr_cm: float
    radius_column_limit_cm: float
    emult: float = 0.0
    ectt_eV: float = 0.0
    taumax: float = 0.0
    selected_epi_eV: float = 0.0
    selected_opakc_cm_inv: float = 0.0
    selected_dpthc: float = 0.0
    selected_zrems: float = 0.0
    selected_tst_cm: float = 0.0
    min_tst_bin_one_based: int = 0
    min_tst_cm: float = 0.0
    min_tst_epi_eV: float = 0.0
    min_tst_opakc_cm_inv: float = 0.0
    min_tst_dpthc: float = 0.0
    min_tst_zrems: float = 0.0
    opacity_limited_delr_cm: float = 0.0
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

    @property
    def rcem_physical(self) -> np.ndarray:
        return self.emissivity.base.rcem[:, 1:]

    @property
    def cemab_physical(self) -> np.ndarray:
        return self.emissivity.base.cemab[:, 1:]


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


@dataclass(frozen=True)
class BoundedRadialPassResult:
    """One bounded pass with source HDU save/restore bookkeeping."""

    state: XSTARPythonState
    pass_index: int
    direction: int
    shell_results: tuple[BoundedRadialShellResult, ...]
    restored_hdus: tuple[int, ...]
    saved_hdus: tuple[int, ...]
    terminal_saved_hdu: int
    numrec: int
    termination_reason: str
    density_iostat: int
    source_loop_predicate: str
    source_file: str = "xstar/src/xstar/xstar.f90"


@dataclass(frozen=True)
class BoundedRadialMultipassResult:
    """Bounded repeated-pass result without output writers."""

    state: XSTARPythonState
    pass_results: tuple[BoundedRadialPassResult, ...]
    saved_state: SavedRadialStateStore
    pass_convergence_contract: RadialPassConvergenceContract
    output_writers_executed: bool = False
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
    min_tst = float("inf")
    min_tst_bin = 0
    min_tst_epi = 0.0
    min_tst_opakc = 0.0
    min_tst_dpthc = 0.0
    min_tst_zrems = 0.0
    selected_tst = 0.0
    selected_epi = float(epi[0]) if n else 0.0
    selected_opakc = max(float(opacity[0]), XSTAR_STEP_OPACITY_FLOOR) if n else 0.0
    selected_dpthc = float(depths[0, 0]) if n else 0.0
    selected_zrems = float(master[0, 0]) if n else 0.0

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
        active = (
            float(epi[idx]) > float(ectt_eV)
            and float(depths[0, idx]) <= float(taumax)
            and float(master[0, idx]) > XSTAR_STEP_ZREMS_GATE
        )
        if active and tst < min_tst:
            min_tst = float(tst)
            min_tst_bin = kl
            min_tst_epi = float(epi[idx])
            min_tst_opakc = float(optp2)
            min_tst_dpthc = float(depths[0, idx])
            min_tst_zrems = float(master[0, idx])
        if active:
            if tst < delr:
                klmn = kl
                selected_tst = float(tst)
                selected_epi = float(epi[idx])
                selected_opakc = float(optp2)
                selected_dpthc = float(depths[0, idx])
                selected_zrems = float(master[0, idx])
            delr = min(delr, tst)

    opacity_limited_delr = float(delr)
    delrmn = (float(column_limit_cm2) - float(column_cm2)) / xpx
    delr = min(delr, delrmn)
    if not math.isfinite(min_tst):
        min_tst = 0.0
    if selected_tst == 0.0 and klmn >= 1 and klmn <= n:
        idx = klmn - 1
        selected_opakc = max(float(opacity[idx]), XSTAR_STEP_OPACITY_FLOOR)
        selected_tst = float(emult) / selected_opakc
        selected_epi = float(epi[idx])
        selected_dpthc = float(depths[0, idx])
        selected_zrems = float(master[0, idx])
    return StepResult(
        delr_cm=float(delr),
        selected_bin_one_based=int(klmn),
        initial_delr_cm=float(initial_delr),
        remaining_column_delr_cm=float(delrmn),
        radius_column_limit_cm=float(rmax),
        emult=float(emult),
        ectt_eV=float(ectt_eV),
        taumax=float(taumax),
        selected_epi_eV=float(selected_epi),
        selected_opakc_cm_inv=float(selected_opakc),
        selected_dpthc=float(selected_dpthc),
        selected_zrems=float(selected_zrems),
        selected_tst_cm=float(selected_tst),
        min_tst_bin_one_based=int(min_tst_bin),
        min_tst_cm=float(min_tst),
        min_tst_epi_eV=float(min_tst_epi),
        min_tst_opakc_cm_inv=float(min_tst_opakc),
        min_tst_dpthc=float(min_tst_dpthc),
        min_tst_zrems=float(min_tst_zrems),
        opacity_limited_delr_cm=float(opacity_limited_delr),
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


def apply_gsmooth_to_state(state: XSTARPythonState) -> GSmoothResult:
    """Apply translated ``gsmooth.f90`` to the post-``xstarcalc`` arrays."""
    workspace = _workspace_from_state(state)
    context = state.control.get("calc_emis_context")
    if context is None:
        raise RadialTransferPortError(
            "translated gsmooth requires state.control['calc_emis_context']"
        )
    ncn2 = int(state.control["ncn2"])
    result = gsmooth(
        temperature_1e4K=float(getattr(context, "temperature_1e4K")),
        turbulent_velocity_km_s=float(state.control.get("vturbi", 0.0)),
        epi_eV=state.radiation.epi,
        opakc_before=workspace.opakc,
        rccemis_before=workspace.rccemis,
        brcems_before=workspace.emissivity.base.brcems,
        ncn2=ncn2,
    )
    workspace.opakc[:] = result.opakc_after
    workspace.rccemis[:, :] = result.rccemis_after
    workspace.emissivity.base.brcems[:] = result.brcems_after
    state.transfer.source_arrays["gsmooth"] = result
    state.transfer.provenance["gsmooth"] = {
        "source_file": result.source_file,
        "helper_source_file": "xstar/xstarlib/src/gsmooth2.f90",
        "active_ncn2": result.ncn2,
        "temperature_1e4K": result.temperature_1e4K,
        "turbulent_velocity_km_s": result.turbulent_velocity_km_s,
        "vtherm_cm_s": result.vtherm_cm_s,
    }
    from .continuum_diagnostics import append_phase_snapshot

    append_phase_snapshot(state, "gsmooth")
    return result


def apply_heatt_to_state(state: XSTARPythonState) -> HeattResult:
    """Apply translated ``heatt.f90`` to the radial caller-owned state."""
    workspace = _workspace_from_state(state)
    context = state.control.get("calc_emis_context")
    if context is None:
        raise RadialTransferPortError(
            "translated heatt requires state.control['calc_emis_context']"
        )
    master = getattr(context, "master", None)
    derived = getattr(context, "derived", None)
    ncn2 = int(state.control["ncn2"])
    n_lines = int(state.control.get("nlsvn", workspace.elum.shape[1]))
    n_continua = int(state.control.get("ncsvn", workspace.elumab.shape[1]))
    calc_emis_result = state.local_zone.source_arrays.get("calc_emis_all")
    leveltemp = getattr(calc_emis_result, "leveltemp_workspace", None)
    if leveltemp is None:
        calc_emisab_result = state.local_zone.source_arrays.get("calc_emisab_all")
        leveltemp = getattr(calc_emisab_result, "leveltemp_workspace", None)

    result = heatt(
        temperature_1e4K=float(getattr(context, "temperature_1e4K")),
        radius_cm=float(state.transfer.radius),
        covering_fraction=float(getattr(context, "covering_fraction", state.control.get("cfrac", 1.0))),
        zone_thickness_cm=float(state.transfer.step_size),
        electron_fraction_xee=float(state.plasma.xee),
        hydrogen_density_cm3=float(state.plasma.xpx),
        abundances_by_z=getattr(context, "abundances_by_z"),
        epi_eV=state.radiation.epi,
        bremsa=state.radiation.bremsa,
        leveltemp_workspace=leveltemp,
        zrems_before=workspace.zrems,
        zremso=workspace.zremso,
        elumab_before=workspace.elumab,
        elumabo=workspace.elumabo,
        elum_before=workspace.elum,
        elumo=workspace.elumo,
        rcem=workspace.rcem_physical[:, :n_lines],
        rccemis=workspace.rccemis,
        opakc=workspace.opakc,
        opakcont=workspace.opakcont,
        cemab=workspace.cemab_physical[:, :n_continua],
        flinel=workspace.emissivity.flinel,
        brcems=workspace.emissivity.base.brcems,
        master=master,
        derived=derived,
        ncn2=ncn2,
        n_lines=n_lines,
        n_continua=n_continua,
    )
    workspace.zrems[:, :] = result.zrems_after
    workspace.elum[:, :] = result.elum_after
    workspace.elumab[:, :] = result.elumab_after
    if leveltemp is not None:
        leveltemp.levels.clear()
        leveltemp.levels.update(result.leveltemp_workspace.levels)
        leveltemp.nlev = int(result.leveltemp_workspace.nlev)
    state.transfer.source_arrays["heatt"] = result
    state.transfer.provenance["heatt"] = {
        "source_file": result.source_file,
        "translated_physics": True,
        "active_ncn2": result.ncn2,
        "n_lines": result.n_lines,
        "n_continua": result.n_continua,
        "compton_coefficients_source_initialized": result.compton_coefficients_source_initialized,
    }
    from .continuum_diagnostics import append_phase_snapshot

    phase = "final heatt" if state.control.get("continuum_phase_context") == "final" else "heatt"
    append_phase_snapshot(state, phase)
    return result



def _saved_store_from_state(
    state: XSTARPythonState, *, create: bool = False
) -> SavedRadialStateStore:
    store = state.transfer.saved_pass_state
    if store is None and create:
        store = SavedRadialStateStore()
        state.transfer.saved_pass_state = store
    if not isinstance(store, SavedRadialStateStore):
        raise RadialTransferPortError(
            "transfer.saved_pass_state must be a SavedRadialStateStore"
        )
    return store


def _level_arrays_from_state(state: XSTARPythonState) -> tuple[np.ndarray, np.ndarray]:
    xilev = state.local_zone.source_arrays.get("xilevg")
    if xilev is None:
        xilev = state.plasma.populations
    rnist = state.local_zone.source_arrays.get("rnisg")
    if xilev is None or rnist is None:
        raise RadialTransferPortError(
            "saved radial state requires current xilevg and rnisg arrays"
        )
    x = np.asarray(xilev, dtype=float).reshape(-1)
    rn = np.asarray(rnist, dtype=float).reshape(-1)
    if x.shape != rn.shape:
        raise RadialTransferPortError("xilevg and rnisg lengths differ")
    return x, rn


def capture_saved_shell_snapshot_from_state(
    state: XSTARPythonState, *, terminal_record: bool = False
) -> SavedShellSnapshot:
    """Capture the exact caller-owned state passed to ``savd``.

    The resulting in-memory record deliberately applies the REAL(4) rounding
    performed by the source ``fstepr*`` FITS writers.  It is transfer state,
    not an output product.
    """
    workspace = _workspace_from_state(state)
    xilev, rnist = _level_arrays_from_state(state)
    ncn2 = int(state.control["ncn2"])
    n_lines = int(state.control.get("nlsvn", workspace.elum.shape[1]))
    n_continua = int(state.control.get("ncsvn", workspace.elumab.shape[1]))
    level_indices = state.control.get("saved_level_indices_one_based")
    line_indices = state.control.get("saved_line_indices_one_based")
    rrc_indices = state.control.get("saved_rrc_indices_one_based")
    return make_saved_shell_snapshot(
        pass_index=int(state.transfer.pass_index),
        zone_index=int(state.transfer.zone_index),
        terminal_record=bool(terminal_record),
        temperature=float(state.plasma.temperature),
        pressure=float(state.control.get("p", 0.0)),
        radius=float(state.transfer.radius),
        radial_depth=float(state.transfer.radial_depth),
        step_size=float(state.transfer.step_size),
        column=float(state.transfer.column),
        electron_fraction=float(state.plasma.xee),
        hydrogen_density=float(state.plasma.xpx),
        zeta=float(state.control.get("zeta", 0.0)),
        xilev=xilev,
        rnist=rnist,
        rcem=workspace.rcem_physical[:, :n_lines],
        oplin=workspace.oplin_physical[:n_lines],
        tau0=workspace.tau0[:, :n_lines],
        cemab=workspace.cemab_physical[:, :n_continua],
        cabab=workspace.emissivity.base.cabab[1 : n_continua + 1],
        opakab=workspace.opakab_physical[:n_continua],
        tauc=workspace.tauc[:, :n_continua],
        zrems=workspace.zrems,
        dpthc=workspace.dpthc,
        opakc=workspace.opakc,
        rccemis=workspace.rccemis,
        ncn2=ncn2,
        level_indices_one_based=level_indices,
        line_indices_one_based=line_indices,
        rrc_indices_one_based=rrc_indices,
    )


def save_radial_shell_state(
    state: XSTARPythonState,
    *,
    hdunum: int,
    terminal_record: bool = False,
) -> int:
    """Insert one shell record after the source-requested one-based HDU."""
    store = _saved_store_from_state(state, create=True)
    pass_state = store.begin_pass(int(state.transfer.pass_index))
    snapshot = capture_saved_shell_snapshot_from_state(
        state, terminal_record=terminal_record
    )
    inserted_hdu = pass_state.insert_after_hdu(int(hdunum), snapshot)
    output_record_written = False
    if bool(state.control.get("output_writers_enabled", False)):
        lwri = int(state.control.get("lwri", 0))
        npass = int(state.control.get("npass", 1))
        # v0.5.11: the source terminal savd call follows the same
        # detail-output condition as ordinary shell savd calls.  In the
        # Python runner, however, late writer-state normalization can leave
        # the condition flags less informative than the existing caller-owned
        # detail store.  If this pass already has detail records, append the
        # terminal caller-owned state as well; do not synthesize a zero shell.
        stores = state.outputs.get("detail_output_stores", {})
        pass_has_detail_records = False
        if isinstance(stores, dict):
            store = stores.get(int(state.transfer.pass_index))
            pass_has_detail_records = bool(getattr(store, "records", ()))
        if lwri > 0 or npass > 1 or (bool(terminal_record) and pass_has_detail_records):
            from .output_writers import append_detail_output_from_state

            append_detail_output_from_state(state, hdunum=int(hdunum), terminal_record=bool(terminal_record))
            output_record_written = True
    state.transfer.provenance.setdefault("saved_shell_records", []).append(
        {
            "source_file": "xstar/xstarlib/src/savd.f90",
            "pass_index": int(state.transfer.pass_index),
            "zone_index": int(state.transfer.zone_index),
            "after_hdu": int(hdunum),
            "inserted_hdu": int(inserted_hdu),
            "terminal_record": bool(terminal_record),
            "storage": "caller-owned in-memory REAL(4) shell state",
            "output_writer_executed": bool(output_record_written),
        }
    )
    from .continuum_diagnostics import append_phase_snapshot

    append_phase_snapshot(
        state,
        "savd/detail snapshot",
        note=f"after_hdu={int(hdunum)} inserted_hdu={int(inserted_hdu)} terminal={bool(terminal_record)}",
    )
    return inserted_hdu


def apply_unsavd_to_state(state: XSTARPythonState) -> UnsavdResult:
    """Restore the previous pass's shell record through ``unsavd.f90``."""
    workspace = _workspace_from_state(state)
    store = _saved_store_from_state(state)
    pass_index = int(state.transfer.pass_index)
    if pass_index <= 1:
        raise RadialTransferPortError("unsavd is valid only after the first pass")
    previous = store.require_pass(pass_index - 1)
    jkstep = int(state.control["unsavd_jkstep"])
    snapshot = previous.snapshot_at_hdu(jkstep)
    xilev, rnist = _level_arrays_from_state(state)
    ncn2 = int(state.control["ncn2"])
    n_lines = int(state.control.get("nlsvn", workspace.elum.shape[1]))
    n_continua = int(state.control.get("ncsvn", workspace.elumab.shape[1]))
    result = unsavd(
        snapshot,
        jkstep=jkstep,
        direction=int(state.transfer.direction),
        epi_eV=state.radiation.epi,
        ncn2=ncn2,
        xilev_before=xilev,
        rnist_before=rnist,
        rcem_before=workspace.rcem_physical[:, :n_lines],
        oplin_before=workspace.oplin_physical[:n_lines],
        tau0_before=workspace.tau0[:, :n_lines],
        cemab_before=workspace.cemab_physical[:, :n_continua],
        cabab_before=workspace.emissivity.base.cabab[1 : n_continua + 1],
        opakab_before=workspace.opakab_physical[:n_continua],
        tauc_before=workspace.tauc[:, :n_continua],
        zrems_before=workspace.zrems,
        dpthc_before=workspace.dpthc,
        opakc_before=workspace.opakc,
        rccemis_before=workspace.rccemis,
    )

    state.plasma.temperature = result.temperature
    state.plasma.xee = result.electron_fraction
    state.plasma.xpx = result.hydrogen_density
    state.transfer.radius = result.radius
    state.transfer.radial_depth = result.radial_depth
    state.transfer.step_size = result.step_size
    state.transfer.column = result.column
    state.control.update(
        {
            "t": result.temperature,
            "p": result.pressure,
            "r": result.radius,
            "rdel": result.radial_depth,
            "delr": result.step_size,
            "xcol": result.column,
            "xee": result.electron_fraction,
            "xpx": result.hydrogen_density,
            "zeta": result.zeta,
            "nry_unsavd": result.nry,
        }
    )
    state.plasma.populations = result.xilev_after
    state.local_zone.source_arrays["xilevg"] = result.xilev_after
    state.local_zone.source_arrays["rnisg"] = result.rnist_after
    for key in ("calc_emisab_context", "calc_emis_context"):
        context = state.control.get(key)
        if context is not None:
            context.xilevg = result.xilev_after
            context.rnisg = result.rnist_after
            context.temperature_1e4K = result.temperature / 1.0e4
            context.electron_fraction_xee = result.electron_fraction
            context.hydrogen_density_cm3 = result.hydrogen_density
            context.pressure_dyn_cm2 = result.pressure

    workspace.rcem_physical[:, :n_lines] = result.rcem_after
    workspace.oplin_physical[:n_lines] = result.oplin_after
    workspace.tau0[:, :n_lines] = result.tau0_after
    workspace.cemab_physical[:, :n_continua] = result.cemab_after
    workspace.emissivity.base.cabab[1 : n_continua + 1] = result.cabab_after
    workspace.opakab_physical[:n_continua] = result.opakab_after
    workspace.tauc[:, :n_continua] = result.tauc_after
    workspace.zrems[:, :] = result.zrems_after
    workspace.dpthc[:, :] = result.dpthc_after
    workspace.opakc[:] = result.opakc_after
    workspace.rccemis[:, :] = result.rccemis_after

    state.transfer.source_arrays["unsavd"] = result
    state.transfer.provenance["unsavd"] = {
        "source_file": result.source_file,
        "previous_pass": pass_index - 1,
        "jkstep": jkstep,
        "direction": result.direction,
        "direction_row_one_based": result.direction_row_one_based,
        "zrems_saved_but_not_restored": result.zrems_saved_but_not_restored,
    }
    state.control.setdefault("restored_hdus", []).append(jkstep)
    return result


def initialize_bounded_radial_pass_state(state: XSTARPythonState) -> None:
    """Apply the radial subset of ``init`` and source-spectrum seeding.

    This helper is intentionally bounded to caller-owned arrays needed by the
    saved-pass contract.  It does not claim the full ``init.f90`` routine.
    """
    workspace = _workspace_from_state(state)
    ncn2 = int(state.control["ncn2"])
    workspace.rccemis[:, :] = 0.0
    workspace.emissivity.base.brcems[:] = 0.0
    workspace.emissivity.flinel[:] = 0.0
    workspace.zrems[:4, :] = 0.0  # source init does not clear zrems(5,:)
    workspace.zremso[:, :] = 0.0
    workspace.dpthc[:, :] = 0.0
    workspace.dpthcont[:, :] = 0.0
    workspace.opakc[:] = 0.0
    workspace.opakcont[:] = 0.0
    workspace.emissivity.base.rcem[:, :] = 0.0
    workspace.emissivity.base.oplin[:] = 0.0
    workspace.emissivity.fline[:, :] = 0.0
    workspace.elum[:, :] = 0.0
    workspace.elumo[:, :] = 0.0
    workspace.tau0[:, :] = 0.0
    workspace.emissivity.base.cemab[:, :] = 0.0
    workspace.emissivity.base.cabab[:] = 0.0
    workspace.emissivity.base.opakab[:] = 0.0
    workspace.elumab[:, :] = 0.0
    workspace.elumabo[:, :] = 0.0
    workspace.tauc[:, :] = 0.0
    if state.radiation.bremsa is not None:
        np.asarray(state.radiation.bremsa)[:] = 0.0
    if state.radiation.bremsam is not None:
        np.asarray(state.radiation.bremsam)[:] = 0.0
    if state.radiation.bremsint is not None:
        np.asarray(state.radiation.bremsint)[:] = 0.0
    workspace.zrems[0, :ncn2] = workspace.zremsz[:ncn2]
    workspace.zremso[0, :ncn2] = workspace.zremsz[:ncn2]
    xilev = state.local_zone.source_arrays.get("xilevg")
    if xilev is not None:
        zero = np.zeros_like(np.asarray(xilev, dtype=float))
        state.local_zone.source_arrays["xilevg"] = zero
        state.plasma.populations = zero
    state.transfer.provenance.setdefault("pass_initialization", []).append(
        {
            "pass_index": int(state.transfer.pass_index),
            "source_file": "xstar/xstarlib/src/init.f90 + xstar.f90",
            "bounded_radial_subset": True,
            "zrems_row5_retained": True,
        }
    )


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
    from .continuum_diagnostics import append_phase_snapshot

    phase = "final stpcut" if state.control.get("continuum_phase_context") == "final" else "stpcut"
    append_phase_snapshot(state, phase)
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
    from .continuum_diagnostics import append_phase_snapshot

    append_phase_snapshot(state, "trnfrn")
    return result


def register_bounded_radial_source_routines(driver: XSTARPythonDriver) -> None:
    """Register translated radial kernels, ``unsavd``, and local ``xstarcalc``."""
    register_complete_local_xstarcalc_source_routines(driver)
    driver.register_source_routine(XSTARSourceRoutine.STEP, apply_step_to_state)
    driver.register_source_routine(XSTARSourceRoutine.TRNFRC, apply_trnfrc_to_state)
    driver.register_source_routine(XSTARSourceRoutine.GSSMOOTH, apply_gsmooth_to_state)
    driver.register_source_routine(XSTARSourceRoutine.HEATT, apply_heatt_to_state)
    driver.register_source_routine(XSTARSourceRoutine.STPCUT, apply_stpcut_to_state)
    driver.register_source_routine(XSTARSourceRoutine.TRNFRN, apply_trnfrn_to_state)
    driver.register_source_routine(XSTARSourceRoutine.UNSAVD, apply_unsavd_to_state)


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
    _emit_progress(
        state,
        "radial_shell_start",
        pass_index=int(pass_index),
        zone_index=int(zone_index),
        direction=int(direction),
        temperature_K=float(state.plasma.temperature),
        column_cm2=float(state.transfer.column),
    )
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
    if bool(state.control.get("radial_spectrum_parity_diagnostic_enabled", False)):
        from .radial_spectrum_parity import append_python_radial_shell_diagnostic

        append_python_radial_shell_diagnostic(
            state,
            zone_index=int(zone_index),
            pass_index=int(pass_index),
            direction=int(direction),
        )
    source_order = tuple(
        state.provenance.get("completed_source_routines", [])[completed_before:]
    )
    skipped = tuple(
        state.provenance.get("skipped_source_routines", [])[skipped_before:]
    )
    result = BoundedRadialShellResult(
        state=state,
        zone_index=int(zone_index),
        pass_index=int(pass_index),
        direction=int(direction),
        source_order=source_order,
        skipped_source_routines=skipped,
        step_executed=XSTARSourceRoutine.STEP.value in source_order,
        output_writers_executed=False,
    )
    _emit_progress(
        state,
        "radial_shell_done",
        pass_index=result.pass_index,
        zone_index=result.zone_index,
        direction=result.direction,
        temperature_K=float(state.plasma.temperature),
        electron_fraction=float(state.plasma.xee),
        column_cm2=float(state.transfer.column),
    )
    return result



def _first_pass_stop_reason(state: XSTARPythonState) -> str:
    if int(state.control.get("density_iostat", 0)) != 0:
        return "density_iostat_nonzero"
    if float(state.transfer.column) >= float(state.control.get("xpxcol", np.inf)):
        return "column_limit"
    if float(state.plasma.xee) <= float(state.control.get("xeemin", -np.inf)):
        return "electron_fraction_limit"
    if (
        float(state.plasma.temperature) / 1.0e4
        <= float(state.control.get("tinf", 0.0)) * 0.99
    ):
        return "temperature_floor"
    if int(state.control.get("numrec", 0)) <= 0:
        return "numrec_nonpositive"
    return "source_first_pass_condition_false"


def run_bounded_radial_pass(
    state: XSTARPythonState,
    *,
    pass_index: int,
    first_pass_shell_count: Optional[int] = None,
    total_passes: Optional[int] = None,
    direction: Optional[int] = None,
    driver: Optional[XSTARPythonDriver] = None,
    fixed_state: bool = False,
) -> BoundedRadialPassResult:
    """Execute one bounded pass with source-order save/restore state.

    The production analytic and tabulated first passes both use the literal
    source predicate ``xcol<xpxcol and xee>xeemin and t>tinf*0.99 and
    numrec>0 and ierr==0``.  ``first_pass_shell_count`` is retained only for
    the bounded synthetic validation fixture; it is not a production shell
    cap and does not reinterpret the XSTAR ``nsteps`` parameter.  Later passes
    honor ``jkp<numrec`` and ``ierr==0``.
    """
    kk = int(pass_index)
    if kk < 1:
        raise RadialTransferPortError("pass_index must be positive")
    if total_passes is not None:
        state.control["npass"] = int(total_passes)
    npass = int(state.control.get("npass", max(kk, 1)))
    if npass < kk:
        raise RadialTransferPortError("total pass count is smaller than pass_index")
    ldir = int((-1) ** kk if direction is None else direction)
    if ldir not in (-1, 1):
        raise RadialTransferPortError("radial pass direction must be -1 or 1")

    _emit_progress(
        state,
        "radial_pass_start",
        pass_index=kk,
        direction=ldir,
        total_passes=npass,
    )
    radexp = float(state.control.get("radexp", 0.0))
    tabulated = radexp < -99.0
    if tabulated:
        table = state.control.get("tabulated_density_state")
        if not isinstance(table, TabulatedRadialDensityState):
            raise RadialTransferPortError(
                "radexp < -99 requires state.control['tabulated_density_state']"
            )
        if kk == 1 and not table.initialized:
            initialize_tabulated_radial_density(state, table)

    store = _saved_store_from_state(state, create=True)
    pass_state = store.begin_pass(kk, replace=True)
    state.transfer.pass_index = kk
    state.transfer.direction = ldir
    state.control["kk"] = kk
    state.control["ldir"] = ldir
    state.control["restored_hdus"] = []
    state.control["save_radial_shell_state_handler"] = save_radial_shell_state
    # xstar.f90 resets ierr=0 at the start of every pass; the sequential
    # density unit itself remains at its current file position.
    state.control["density_iostat"] = 0
    initialize_bounded_radial_pass_state(state)
    if bool(state.control.get("pprint_legacy_enabled", False)):
        from .pprint_legacy import legacy_pprint_begin_pass

        legacy_pprint_begin_pass(state)

    runner = driver or XSTARPythonDriver()
    if driver is None:
        register_bounded_radial_source_routines(runner)
    shells: list[BoundedRadialShellResult] = []

    if kk == 1 and not tabulated:
        if int(state.control.get("numrec", 0)) <= 0:
            # The source first-pass predicate contains numrec>0, so no shell is
            # entered after numrec<=0 has forced npass=1.
            termination_reason = "numrec_nonpositive"
            source_predicate = (
                "xcol<xpxcol and xee>xeemin and t>tinf*0.99 and "
                "numrec>0 and ierr==0"
            )
        elif bool(state.control.get("bounded_radial_validation_mode", False)):
            # Historical synthetic fixtures deliberately execute a tiny fixed
            # number of shells.  Keep that bounded test contract isolated from
            # the production source predicate.
            if first_pass_shell_count is None or int(first_pass_shell_count) < 1:
                raise RadialTransferPortError(
                    "first_pass_shell_count must be positive in bounded validation mode"
                )
            for jkp in range(1, int(first_pass_shell_count) + 1):
                shells.append(
                    run_bounded_radial_shell(
                        state,
                        zone_index=jkp,
                        pass_index=kk,
                        direction=ldir,
                        driver=runner,
                        fixed_state=fixed_state,
                    )
                )
            termination_reason = "bounded_validation_shell_count"
            source_predicate = "bounded synthetic validation fixture"
        else:
            jkp = 0
            while first_pass_shell_condition(state):
                jkp += 1
                if jkp > 3999:
                    raise RadialTransferPortError("too many steps: buffer filled")
                shells.append(
                    run_bounded_radial_shell(
                        state,
                        zone_index=jkp,
                        pass_index=kk,
                        direction=ldir,
                        driver=runner,
                        fixed_state=fixed_state,
                    )
                )
            termination_reason = _first_pass_stop_reason(state)
            source_predicate = (
                "xcol<xpxcol and xee>xeemin and t>tinf*0.99 and "
                "numrec>0 and ierr==0"
            )
    elif kk == 1:
        jkp = 0
        while first_pass_shell_condition(state):
            jkp += 1
            if jkp > 3999:
                raise RadialTransferPortError("too many steps: buffer filled")
            shells.append(
                run_bounded_radial_shell(
                    state,
                    zone_index=jkp,
                    pass_index=kk,
                    direction=ldir,
                    driver=runner,
                    fixed_state=fixed_state,
                )
            )
        termination_reason = _first_pass_stop_reason(state)
        source_predicate = (
            "xcol<xpxcol and xee>xeemin and t>tinf*0.99 and numrec>0 and ierr==0"
        )
    elif not tabulated:
        shell_count = int(state.control["numrec"])
        if shell_count < 1:
            raise RadialTransferPortError("numrec must be positive on later passes")
        for jkp in range(1, shell_count + 1):
            shells.append(
                run_bounded_radial_shell(
                    state,
                    zone_index=jkp,
                    pass_index=kk,
                    direction=ldir,
                    driver=runner,
                    fixed_state=fixed_state,
                )
            )
        termination_reason = "numrec_completed"
        source_predicate = "jkp<numrec and ierr==0"
    else:
        jkp = 0
        while repeated_pass_shell_condition(state, completed_shells=jkp):
            jkp += 1
            shells.append(
                run_bounded_radial_shell(
                    state,
                    zone_index=jkp,
                    pass_index=kk,
                    direction=ldir,
                    driver=runner,
                    fixed_state=fixed_state,
                )
            )
        termination_reason = (
            "density_iostat_nonzero"
            if int(state.control.get("density_iostat", 0)) != 0
            else "numrec_completed"
        )
        source_predicate = "jkp<numrec and ierr==0"

    shell_count = len(shells)
    if kk == 1:
        # Source sets numrec=jkp+1 after the first radial traversal.
        state.control["numrec"] = shell_count + 1
    if bool(state.control.get("pprint_legacy_enabled", False)):
        from .pprint_legacy import legacy_pprint_after_heatt

        # The source terminal report reuses the final shell state and jkp, and
        # final-pass pprint(12) writes the numrec row.
        legacy_pprint_after_heatt(state, terminal_record=True)
    terminal_hdu = save_radial_shell_state(
        state, hdunum=shell_count + 1, terminal_record=True
    )
    restored_hdus = tuple(int(value) for value in state.control["restored_hdus"])
    result = BoundedRadialPassResult(
        state=state,
        pass_index=kk,
        direction=ldir,
        shell_results=tuple(shells),
        restored_hdus=restored_hdus,
        saved_hdus=pass_state.populated_hdus(),
        terminal_saved_hdu=int(terminal_hdu),
        numrec=int(state.control["numrec"]),
        termination_reason=termination_reason,
        density_iostat=int(state.control.get("density_iostat", 0)),
        source_loop_predicate=source_predicate,
    )
    state.transfer.provenance.setdefault("radial_passes", []).append(
        {
            "source_file": result.source_file,
            "pass_index": kk,
            "direction": ldir,
            "shell_count": shell_count,
            "numrec": result.numrec,
            "restored_hdus": list(result.restored_hdus),
            "saved_hdus": list(result.saved_hdus),
            "terminal_saved_hdu": result.terminal_saved_hdu,
            "termination_reason": result.termination_reason,
            "density_iostat": result.density_iostat,
            "source_loop_predicate": result.source_loop_predicate,
            "output_writers_executed": False,
        }
    )
    _emit_progress(
        state,
        "radial_pass_done",
        pass_index=result.pass_index,
        direction=result.direction,
        shell_count=len(result.shell_results),
        termination_reason=result.termination_reason,
        numrec=result.numrec,
    )
    return result


def run_bounded_radial_multipass(
    state: XSTARPythonState,
    *,
    first_pass_shell_count: Optional[int],
    pass_count: int = 3,
    driver: Optional[XSTARPythonDriver] = None,
    fixed_state: bool = False,
) -> BoundedRadialMultipassResult:
    """Execute the literal fixed requested-pass schedule.

    This is an explicit source convergence contract: no adaptive comparison of
    successive passes is introduced.  ``numrec <= 0`` forces one effective
    pass exactly as in ``xstar.f90``.
    """
    requested = int(pass_count)
    initial_numrec = int(state.control.get("numrec", 0))
    contract = build_radial_pass_convergence_contract(
        numrec=initial_numrec, npass=requested
    )
    count = int(contract.effective_passes)
    if count < 1:
        raise RadialTransferPortError("effective pass count must be positive")
    _emit_progress(
        state,
        "radial_multipass_start",
        requested_passes=requested,
        effective_passes=count,
        first_pass_shell_count=first_pass_shell_count,
    )
    runner = driver or XSTARPythonDriver()
    if driver is None:
        register_bounded_radial_source_routines(runner)
    state.control["npass"] = count
    state.transfer.provenance["pass_convergence_contract"] = {
        "source_file": contract.source_file,
        "requested_passes": contract.requested_passes,
        "effective_passes": contract.effective_passes,
        "initial_numrec": contract.initial_numrec,
        "directions": list(contract.directions),
        "adaptive_convergence_used": contract.adaptive_convergence_used,
        "convergence_kind": contract.convergence_kind,
        "first_pass_predicate": contract.first_pass_predicate,
        "repeated_pass_predicate": contract.repeated_pass_predicate,
    }
    results: list[BoundedRadialPassResult] = []
    for kk in range(1, count + 1):
        results.append(
            run_bounded_radial_pass(
                state,
                pass_index=kk,
                first_pass_shell_count=(first_pass_shell_count if kk == 1 else None),
                total_passes=count,
                driver=runner,
                fixed_state=fixed_state,
            )
        )
    state.transfer.converged = len(results) == count
    result = BoundedRadialMultipassResult(
        state=state,
        pass_results=tuple(results),
        saved_state=_saved_store_from_state(state),
        pass_convergence_contract=contract,
        output_writers_executed=False,
    )
    _emit_progress(
        state,
        "radial_multipass_done",
        completed_passes=len(result.pass_results),
        completed_zones=sum(len(item.shell_results) for item in result.pass_results),
    )
    return result


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
    """Compare radial kernels and ``heatt`` with frozen direct-Fortran cases."""
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

    heatt_direct = dict(run_direct_fortran_heatt_validation(rtol=rtol, atol=atol))
    gsmooth_direct = dict(run_direct_fortran_gsmooth_validation(rtol=rtol, atol=atol))
    summary = {
        "port_version": "v0.4.67",
        **gsmooth_direct,
        **heatt_direct,
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
        "tinf": 0.01,
        "vturbi": 0.0,
        "radexp": 0.0,
        "lcdd": 1,
        "lpri": 0,
        "bounded_radial_validation_mode": True,
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
        # The reusable emissivity fixture predates heatt and omitted the direct
        # line pointer array.  Production setptrs always supplies it.
        for key in ("calc_emisab_context", "calc_emis_context"):
            ctx = runtime.control[key]
            derived = ctx.derived
            if not hasattr(derived, "nplin"):
                derived.nplin = np.zeros(int(runtime.control["nlsvn"]) + 1, dtype=int)
            derived.nplin[1] = 10
            if int(runtime.control["nlsvn"]) >= 2:
                derived.nplin[2] = 11
            if hasattr(ctx.master, "_reals"):
                ctx.master._reals[10] = np.asarray([10.0])
        return result

    state.control["calc_hmc_all_source_handler"] = hmc_with_caller_workspace

    from .output_writers import (
        LevelOutputMetadata,
        LineOutputMetadata,
        RRCOutputMetadata,
        SourceOutputMetadata,
    )

    state.control["output_atomic_metadata"] = SourceOutputMetadata(
        levels=tuple(
            LevelOutputMetadata(
                global_index=index,
                ion_index=1,
                excitation_eV=float((index - 1) * 10.0),
                ion_label="o_vii",
                atomic_number=8,
                level_label=("ground" if index == 1 else f"level_{index}"),
                upper_index=index,
            )
            for index in range(1, 7)
        ),
        lines=(
            LineOutputMetadata(1, 21.60, "o_vii", "ground", "resonance", rate_type=50, data_type=50, atomic_mass=16.0, natural_rate_s=3.0e8),
            LineOutputMetadata(2, 21.80, "o_vii", "ground", "intercombination", rate_type=50, data_type=50, atomic_mass=16.0, natural_rate_s=2.0e8),
            LineOutputMetadata(3, 22.10, "o_vii", "ground", "forbidden", rate_type=50, data_type=50, atomic_mass=16.0, natural_rate_s=1.0e3),
        ),
        rrcs=(
            RRCOutputMetadata(1, 1, 739.3, "o_vii", "ground"),
            RRCOutputMetadata(2, 2, 700.0, "o_vii", "level_2"),
            RRCOutputMetadata(3, 3, 650.0, "o_vii", "level_3"),
        ),
        provenance={"fixture": "bounded-radial-output-v0.4.69"},
    )
    state.control["cfrac"] = 0.25
    return state


def run_bounded_radial_shell_validation(
    *, rtol: float = 2.0e-14, atol: float = 1.0e-30
) -> Mapping[str, Any]:
    """Validate radial kernels, saved passes, density tables, and pass control."""
    direct = dict(run_direct_fortran_radial_validation(rtol=rtol, atol=atol))
    direct.update(run_direct_fortran_unsavd_validation(rtol=rtol, atol=atol))
    direct.update(
        run_direct_fortran_tabulated_density_validation(
            rtol=min(rtol, 2.0e-15), atol=0.0
        )
    )

    zone1_state = _build_radial_validation_state(zone_index=1)
    zone1 = run_bounded_radial_shell(zone1_state, zone_index=1, pass_index=1, direction=1)
    expected_zone1 = (
        "trnfrc", "bremsmap", "dsec", "calc_hmc_all", "calc_emisab_all",
        "calc_emis_all", "heatt", "stpcut", "trnfrn",
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
        "step", "trnfrc", "bremsmap", "dsec", "calc_hmc_all",
        "calc_emisab_all", "calc_emis_all", "heatt", "stpcut", "trnfrn",
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
    heatt_result = zone2_state.transfer.source_arrays.get("heatt")
    heatt_boundary_ready = bool(
        isinstance(heatt_result, HeattResult)
        and zone2.source_order.index("calc_emis_all") < zone2.source_order.index("heatt")
        < zone2.source_order.index("stpcut")
        and zone2_state.transfer.provenance["heatt"]["translated_physics"] is True
        and heatt_result.compton_coefficients_source_initialized is False
    )

    turbulent_state = _build_radial_validation_state(zone_index=1)
    np.asarray(turbulent_state.radiation.epi)[-1] = 2.1e4
    turbulent_state.control["vturbi"] = 1.2e4
    turbulent = run_bounded_radial_shell(
        turbulent_state, zone_index=1, pass_index=1, direction=1
    )
    expected_turbulent = (
        "trnfrc", "bremsmap", "dsec", "calc_hmc_all", "calc_emisab_all",
        "calc_emis_all", "gsmooth", "heatt", "stpcut", "trnfrn",
    )
    turbulent_order_ready = turbulent.source_order == expected_turbulent
    gsmooth_result = turbulent_state.transfer.source_arrays.get("gsmooth")
    turbulent_gsmooth_ready = bool(
        isinstance(gsmooth_result, GSmoothResult)
        and turbulent.source_order.index("calc_emis_all")
        < turbulent.source_order.index("gsmooth")
        < turbulent.source_order.index("heatt")
        and turbulent_state.transfer.provenance["gsmooth"]["source_file"]
        == "xstar/xstarlib/src/gsmooth.f90"
    )
    turbulent_ws = turbulent_state.control["radial_transfer_workspace"]
    turbulent_ownership_ready = bool(
        isinstance(gsmooth_result, GSmoothResult)
        and np.array_equal(turbulent_ws.opakc, gsmooth_result.opakc_after)
        and np.array_equal(turbulent_ws.rccemis, gsmooth_result.rccemis_after)
        and np.array_equal(
            turbulent_ws.emissivity.base.brcems, gsmooth_result.brcems_after
        )
    )

    multipass_state = _build_radial_validation_state(zone_index=1)
    multipass = run_bounded_radial_multipass(
        multipass_state, first_pass_shell_count=2, pass_count=3
    )
    pass1, pass2, pass3 = multipass.pass_results
    expected_restore_hdus = (5, 4, 3)
    direction_ready = tuple(p.direction for p in multipass.pass_results) == (-1, 1, -1)
    restore_order_ready = bool(
        pass2.restored_hdus == expected_restore_hdus
        and pass3.restored_hdus == expected_restore_hdus
    )
    unsavd_before_transfer_ready = bool(
        all(
            shell.source_order[0] == "unsavd"
            and shell.source_order.index("unsavd") < shell.source_order.index("trnfrc")
            for radial_pass in (pass2, pass3)
            for shell in radial_pass.shell_results
        )
    )
    hdu_insertion_ready = bool(
        pass1.saved_hdus == (3, 4, 5)
        and pass1.terminal_saved_hdu == 4
        and multipass.saved_state.require_pass(1).snapshot_at_hdu(3).zone_index == 1
        and multipass.saved_state.require_pass(1).snapshot_at_hdu(4).terminal_record
        and multipass.saved_state.require_pass(1).snapshot_at_hdu(5).zone_index == 2
        and pass2.saved_hdus == (3, 4, 5, 6)
        and pass2.terminal_saved_hdu == 5
    )
    first_snapshot = multipass.saved_state.require_pass(1).snapshot_at_hdu(3)
    real4_ready = bool(
        first_snapshot.radius == float(np.float32(first_snapshot.radius))
        and first_snapshot.temperature == float(np.float32(first_snapshot.temperature))
        and np.array_equal(
            first_snapshot.opakc,
            np.asarray(first_snapshot.opakc, dtype=np.float32).astype(float),
        )
    )
    pass2_dsec_skip_ready = bool(
        all("dsec" not in shell.source_order for shell in pass2.shell_results)
    )
    pass3_dsec_execute_ready = bool(
        all("dsec" in shell.source_order for shell in pass3.shell_results)
    )
    repeated_state_ready = bool(
        pass1.numrec == 3
        and len(pass2.shell_results) == 3
        and len(pass3.shell_results) == 3
        and pass2.saved_hdus == (3, 4, 5, 6)
        and pass3.saved_hdus == (3, 4, 5, 6)
    )
    zrems_local_ready = bool(
        all(
            shell.state.transfer.source_arrays["unsavd"].zrems_saved_but_not_restored
            for radial_pass in (pass2, pass3)
            for shell in radial_pass.shell_results
        )
    )

    # Source tabulated-density path: first row is consumed before pass 1;
    # each shell consumes one further row, and EOF retains the last values.
    table_state = _build_radial_validation_state(zone_index=1)
    table_state.control.update(
        {
            "radexp": -100.0,
            "xpxcol": 1.0e40,
            "xeemin": -1.0,
            "numrec": 20,
            "tabulated_density_state": TabulatedRadialDensityState.from_rows(
                [(1.0e18, 1.25e8), (1.4e18, 2.5e8), (2.1e18, 4.0e8)]
            ),
        }
    )
    table_run = run_bounded_radial_multipass(
        table_state, first_pass_shell_count=None, pass_count=1
    )
    table_pass = table_run.pass_results[0]
    density_reads = table_state.transfer.provenance.get("tabulated_density_reads", [])
    table_initial_ready = bool(
        table_state.transfer.provenance["tabulated_density_initialization"]["row_one_based"] == 1
        and len(table_pass.shell_results) == 3
    )
    table_update_ready = bool(
        [row["row_one_based"] for row in density_reads] == [2, 3, None]
        and np.allclose(
            [row["delr_cm"] for row in density_reads],
            [4.0e17, 7.0e17, 0.0],
            rtol=2.0e-15,
            atol=0.0,
        )
        and np.isclose(table_state.transfer.radius, 2.1e18, rtol=2.0e-15)
        and np.isclose(table_state.plasma.xpx, 4.0e8, rtol=2.0e-15)
        and np.isclose(table_state.transfer.radial_depth, 1.1e18, rtol=2.0e-15)
        and np.isclose(table_state.transfer.column, 3.8000000000000002e26, rtol=2.0e-15)
    )
    table_eof_ready = bool(
        table_pass.termination_reason == "density_iostat_nonzero"
        and table_pass.density_iostat == -1
        and density_reads[-1]["retained_previous_values"] is True
        and table_pass.numrec == 4
    )
    table_call_order_ready = bool(
        table_pass.shell_results[0].source_order == expected_zone1
        and table_pass.shell_results[1].source_order == expected_zone2
        and table_pass.shell_results[2].source_order == expected_zone2
    )
    table_stream = table_state.control["tabulated_density_state"]
    table_stream_ready = bool(
        isinstance(table_stream, TabulatedRadialDensityState)
        and table_stream.next_index_zero_based == 3
        and table_stream.iostat == -1
        and table_stream.initialized
    )
    descending_state = _build_radial_validation_state(zone_index=1)
    descending_table = TabulatedRadialDensityState.from_rows(
        [(2.0e18, 1.0e8), (1.5e18, 2.0e8)]
    )
    initialize_tabulated_radial_density(descending_state, descending_table)
    try:
        advance_tabulated_radial_density(descending_state)
    except TabulatedRadialRadiusError:
        radius_error_ready = True
    else:
        radius_error_ready = False

    contract = multipass.pass_convergence_contract
    forced_one = build_radial_pass_convergence_contract(numrec=0, npass=5)
    forced_state = _build_radial_validation_state(zone_index=1)
    forced_state.control["numrec"] = 0
    forced_state.local_zone.source_arrays["xilevg"] = np.zeros(2, dtype=float)
    forced_state.local_zone.source_arrays["rnisg"] = np.zeros(2, dtype=float)
    forced_run = run_bounded_radial_multipass(
        forced_state, first_pass_shell_count=1, pass_count=5
    )
    pass_contract_ready = bool(
        contract.requested_passes == 3
        and contract.effective_passes == 3
        and contract.directions == (-1, 1, -1)
        and contract.adaptive_convergence_used is False
        and contract.convergence_kind == "fixed_requested_pass_count"
        and multipass_state.transfer.converged is True
    )
    numrec_force_ready = bool(
        forced_one.effective_passes == 1
        and forced_one.directions == (-1,)
        and forced_one.adaptive_convergence_used is False
        and len(forced_run.pass_results) == 1
        and forced_run.pass_results[0].direction == -1
        and len(forced_run.pass_results[0].shell_results) == 0
        and forced_run.pass_results[0].termination_reason == "numrec_nonpositive"
        and forced_run.pass_results[0].numrec == 1
    )
    pass_loop_predicates_ready = bool(
        pass1.source_loop_predicate == "bounded synthetic validation fixture"
        and pass2.source_loop_predicate == "jkp<numrec and ierr==0"
        and table_pass.source_loop_predicate
        == "xcol<xpxcol and xee>xeemin and t>tinf*0.99 and numrec>0 and ierr==0"
    )

    summary: dict[str, Any] = {
        **direct,
        "port_version": "v0.4.68",
        "bounded_radial_shell_translated": True,
        "zone1_step_skip_ready": zone1_skip_ready,
        "zone1_first_pass_call_order_ready": zone1_order_ready,
        "zone1_source_order": list(zone1.source_order),
        "later_first_pass_step_ready": zone2_step_ready,
        "later_first_pass_call_order_ready": zone2_order_ready,
        "later_zone_source_order": list(zone2.source_order),
        "shared_radial_array_ownership_ready": ownership_ready,
        "heatt_translated_in_radial_sequence_ready": heatt_boundary_ready,
        "turbulent_gsmooth_executed_ready": turbulent_gsmooth_ready,
        "turbulent_gsmooth_before_heatt_ready": turbulent_order_ready,
        "turbulent_shared_array_ownership_ready": turbulent_ownership_ready,
        "turbulent_source_order": list(turbulent.source_order),
        "caller_owned_saved_shell_state_ready": isinstance(
            multipass_state.transfer.saved_pass_state, SavedRadialStateStore
        ),
        "saved_state_real4_rounding_ready": real4_ready,
        "saved_hdu_insertion_shift_order_ready": hdu_insertion_ready,
        "multipass_direction_alternation_ready": direction_ready,
        "reverse_pass_unsavd_executed_ready": unsavd_before_transfer_ready,
        "reverse_pass_restore_hdu_order_ready": restore_order_ready,
        "reverse_pass_restored_hdus": [list(pass2.restored_hdus), list(pass3.restored_hdus)],
        "positive_pass_nlimdt_zero_dsec_skip_ready": pass2_dsec_skip_ready,
        "negative_repeated_pass_nlimdt_restore_dsec_ready": pass3_dsec_execute_ready,
        "unsavd_zrems_local_temporary_in_multipass_ready": zrems_local_ready,
        "repeated_radial_pass_state_ready": repeated_state_ready,
        "multipass_source_orders": [
            [list(shell.source_order) for shell in radial_pass.shell_results]
            for radial_pass in multipass.pass_results
        ],
        "tabulated_density_initial_source_read_ready": table_initial_ready,
        "tabulated_density_post_shell_update_ready": table_update_ready,
        "tabulated_density_eof_loop_termination_ready": table_eof_ready,
        "tabulated_density_call_order_ready": table_call_order_ready,
        "tabulated_density_sequential_stream_ownership_ready": table_stream_ready,
        "tabulated_density_negative_radius_failure_ready": radius_error_ready,
        "tabulated_density_shell_count": len(table_pass.shell_results),
        "tabulated_density_read_rows": [row["row_one_based"] for row in density_reads],
        "fixed_pass_count_convergence_contract_ready": pass_contract_ready,
        "numrec_nonpositive_forces_one_pass_ready": numrec_force_ready,
        "source_pass_loop_predicates_ready": pass_loop_predicates_ready,
        "adaptive_pass_convergence_not_invented_ready": bool(
            not contract.adaptive_convergence_used
            and not forced_one.adaptive_convergence_used
        ),
        "pass_convergence_kind": contract.convergence_kind,
        "output_writers_excluded_ready": bool(
            not zone1.output_writers_executed
            and not zone2.output_writers_executed
            and not turbulent.output_writers_executed
            and not multipass.output_writers_executed
            and not table_run.output_writers_executed
            and all(
                not shell.output_writers_executed
                for run in (multipass, table_run)
                for radial_pass in run.pass_results
                for shell in radial_pass.shell_results
            )
        ),
    }
    summary["bounded_radial_shell_source_acceptance_ready"] = bool(
        all(value for key, value in summary.items() if key.endswith("_ready"))
    )
    summary["next_source_target"] = "detail_and_final_output_writers"
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
    "GSmoothResult",
    "gsmooth",
    "run_direct_fortran_gsmooth_validation",
    "HeattResult",
    "heatt",
    "run_direct_fortran_heatt_validation",
    "StepResult",
    "TrnfrcResult",
    "StpcutResult",
    "TrnfrnResult",
    "RadialTransferWorkspace",
    "BoundedRadialShellResult",
    "BoundedRadialPassResult",
    "BoundedRadialMultipassResult",
    "SavedRadialStatePortError",
    "SavedShellSnapshot",
    "SavedRadialPassState",
    "SavedRadialStateStore",
    "UnsavdResult",
    "make_saved_shell_snapshot",
    "unsavd",
    "run_direct_fortran_unsavd_validation",
    "step",
    "trnfrc",
    "stpcut",
    "trnfrn",
    "apply_step_to_state",
    "apply_trnfrc_to_state",
    "apply_gsmooth_to_state",
    "apply_heatt_to_state",
    "capture_saved_shell_snapshot_from_state",
    "save_radial_shell_state",
    "apply_unsavd_to_state",
    "initialize_bounded_radial_pass_state",
    "apply_stpcut_to_state",
    "apply_trnfrn_to_state",
    "register_bounded_radial_source_routines",
    "run_bounded_radial_shell",
    "run_bounded_radial_pass",
    "run_bounded_radial_multipass",
    "direct_fortran_radial_reference_cases",
    "run_direct_fortran_radial_validation",
    "run_bounded_radial_shell_validation",
    "write_bounded_radial_shell_validation_products",
]
