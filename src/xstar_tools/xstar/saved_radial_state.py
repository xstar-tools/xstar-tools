"""Source-faithful saved radial shell/pass state and ``unsavd.f90`` port.

The original XSTAR radial driver persists each shell through ``savd`` into four
FITS files and restores it on the following pass through ``unsavd``.  Output
writers remain outside the bounded Python port.  This module therefore models
the same caller-visible persistence contract in memory:

* values written by the ``fstepr*`` helpers are rounded through REAL(4);
* each shell snapshot is inserted after the one-based HDU requested by
  ``savd(jkp+1, ...)``, preserving CFITSIO insertion/shift semantics;
* ``unsavd`` restores scalar, population, line, RRC, opacity, and emissivity
  state, but only the direction-owned optical-depth row;
* the saved ``zrems`` table is deliberately read into a local temporary and is
  not copied back to the caller, exactly as in ``unsavd.f90``.

This is transfer state, not a detail-output implementation.  No FITS file is
created and no output writer is registered.
"""
# Source correspondence:
#   Fortran: savd.f90 / unsavd.f90 / rstepr* persistence semantics.
#   Role: shell-to-shell/pass state lifetime, including REAL(4) persisted values.
#   Concordance: STATE-001; qualification: accepted detail/terminal publication lineage.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import numpy as np

from .radiation import nbinc


class SavedRadialStatePortError(RuntimeError):
    """Raised when saved shell/pass state violates the source contract."""


def _real4_scalar(value: float) -> float:
    return float(np.float32(float(value)))


def _real4_array(values: Sequence[float]) -> np.ndarray:
    return np.asarray(values, dtype=np.float32).astype(float)


def _index_vector(
    values: Optional[Sequence[int]], *, size: int, name: str
) -> np.ndarray:
    if values is None:
        result = np.arange(1, int(size) + 1, dtype=int)
    else:
        result = np.asarray(values, dtype=int).reshape(-1)
    if result.size == 0 and size != 0:
        raise SavedRadialStatePortError(f"{name} cannot be empty")
    if np.any(result < 1) or np.any(result > int(size)):
        raise SavedRadialStatePortError(
            f"{name} contains an index outside 1:{int(size)}"
        )
    if np.unique(result).size != result.size:
        raise SavedRadialStatePortError(f"{name} contains duplicate indices")
    return result


@dataclass(frozen=True)
class SavedShellSnapshot:
    """One ``savd`` shell record after source REAL(4) persistence."""

    pass_index: int
    zone_index: int
    terminal_record: bool
    temperature: float
    pressure: float
    radius: float
    radial_depth: float
    step_size: float
    column: float
    electron_fraction: float
    hydrogen_density: float
    zeta: float
    level_indices_one_based: np.ndarray
    xilev: np.ndarray
    rnist: np.ndarray
    line_indices_one_based: np.ndarray
    rcem: np.ndarray
    oplin: np.ndarray
    tau0: np.ndarray
    rrc_indices_one_based: np.ndarray
    cemab: np.ndarray
    cabab: np.ndarray
    opakab: np.ndarray
    tauc: np.ndarray
    elumab: np.ndarray
    ncn2: int
    zrems_saved: np.ndarray
    dpthc: np.ndarray
    dpthcont: np.ndarray
    zremsz: np.ndarray
    opakc: np.ndarray
    rccemis: np.ndarray
    source_file: str = "xstar/xstarlib/src/savd.f90"
    storage_contract: str = "caller-owned in-memory fstepr-real4 equivalent"

    def validate(self) -> None:
        if self.pass_index < 1 or self.zone_index < 0:
            raise SavedRadialStatePortError("invalid pass/zone index in snapshot")
        n = int(self.ncn2)
        if n < 1:
            raise SavedRadialStatePortError("saved shell ncn2 must be positive")
        checks = {
            "xilev": self.xilev.shape == self.level_indices_one_based.shape,
            "rnist": self.rnist.shape == self.level_indices_one_based.shape,
            "rcem": self.rcem.shape == (2, self.line_indices_one_based.size),
            "oplin": self.oplin.shape == (self.line_indices_one_based.size,),
            "tau0": self.tau0.shape == (2, self.line_indices_one_based.size),
            "cemab": self.cemab.shape == (2, self.rrc_indices_one_based.size),
            "cabab": self.cabab.shape == (self.rrc_indices_one_based.size,),
            "opakab": self.opakab.shape == (self.rrc_indices_one_based.size,),
            "tauc": self.tauc.shape == (2, self.rrc_indices_one_based.size),
            "elumab": self.elumab.shape == (2, self.rrc_indices_one_based.size),
            "zrems_saved": self.zrems_saved.shape == (5, n),
            "dpthc": self.dpthc.shape == (2, n),
            "dpthcont": self.dpthcont.shape == (2, n),
            "zremsz": self.zremsz.shape == (n,),
            "opakc": self.opakc.shape == (n,),
            "rccemis": self.rccemis.shape == (2, n),
        }
        bad = [name for name, ok in checks.items() if not ok]
        if bad:
            raise SavedRadialStatePortError(
                "invalid saved shell array shapes: " + ", ".join(bad)
            )
        scalar_values = np.asarray(
            [
                self.temperature,
                self.pressure,
                self.radius,
                self.radial_depth,
                self.step_size,
                self.column,
                self.electron_fraction,
                self.hydrogen_density,
                self.zeta,
            ],
            dtype=float,
        )
        arrays = (
            self.xilev,
            self.rnist,
            self.rcem,
            self.oplin,
            self.tau0,
            self.cemab,
            self.cabab,
            self.opakab,
            self.tauc,
            self.elumab,
            self.zrems_saved,
            self.dpthc,
            self.opakc,
            self.rccemis,
        )
        if not np.all(np.isfinite(scalar_values)) or any(
            not np.all(np.isfinite(np.asarray(array, dtype=float))) for array in arrays
        ):
            raise SavedRadialStatePortError("saved shell contains non-finite values")


@dataclass
class SavedRadialPassState:
    """One pass's in-memory equivalent of the four XSTAR detail FITS files.

    Indices 1 and 2 are reserved for the primary/parameter HDUs.  ``savd``
    calls ``ftmahd(hdunum)`` followed by ``ftcrhd``; insertion after an earlier
    HDU shifts later shell records.  The list representation below preserves
    that behavior exactly.
    """

    pass_index: int
    hdu_snapshots: list[Optional[SavedShellSnapshot]] = field(
        default_factory=lambda: [None, None, None]
    )
    insertion_log: list[Mapping[str, int | bool]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if int(self.pass_index) < 1:
            raise SavedRadialStatePortError("pass_index must be positive")
        if len(self.hdu_snapshots) < 3:
            raise SavedRadialStatePortError(
                "saved pass must reserve one-based HDUs 1 and 2"
            )

    @property
    def hdu_count(self) -> int:
        return len(self.hdu_snapshots) - 1

    def insert_after_hdu(
        self, hdunum: int, snapshot: SavedShellSnapshot
    ) -> int:
        hdu = int(hdunum)
        if hdu < 1 or hdu > self.hdu_count:
            raise SavedRadialStatePortError(
                f"cannot insert after HDU {hdu}; current HDU count is {self.hdu_count}"
            )
        snapshot.validate()
        inserted = hdu + 1
        self.hdu_snapshots.insert(inserted, snapshot)
        self.insertion_log.append(
            {
                "after_hdu": hdu,
                "inserted_hdu": inserted,
                "zone_index": int(snapshot.zone_index),
                "terminal_record": bool(snapshot.terminal_record),
            }
        )
        return inserted

    def snapshot_at_hdu(self, hdunum: int) -> SavedShellSnapshot:
        hdu = int(hdunum)
        if hdu < 1 or hdu > self.hdu_count:
            raise SavedRadialStatePortError(
                f"saved pass {self.pass_index} has no HDU {hdu}"
            )
        snapshot = self.hdu_snapshots[hdu]
        if snapshot is None:
            raise SavedRadialStatePortError(
                f"saved pass {self.pass_index} HDU {hdu} is not a shell record"
            )
        return snapshot

    def populated_hdus(self) -> tuple[int, ...]:
        return tuple(
            index
            for index, snapshot in enumerate(self.hdu_snapshots)
            if index > 0 and snapshot is not None
        )


@dataclass
class SavedRadialStateStore:
    """Caller-owned saved state across alternating radial passes."""

    passes: dict[int, SavedRadialPassState] = field(default_factory=dict)

    def begin_pass(self, pass_index: int, *, replace: bool = False) -> SavedRadialPassState:
        index = int(pass_index)
        if index in self.passes and not replace:
            return self.passes[index]
        state = SavedRadialPassState(pass_index=index)
        self.passes[index] = state
        return state

    def require_pass(self, pass_index: int) -> SavedRadialPassState:
        index = int(pass_index)
        if index not in self.passes:
            raise SavedRadialStatePortError(f"saved radial pass {index} is unavailable")
        return self.passes[index]


@dataclass(frozen=True)
class UnsavdResult:
    """Caller-visible result of translated ``unsavd.f90``."""

    jkstep: int
    direction: int
    direction_row_one_based: int
    ncn2: int
    nry: int
    temperature: float
    pressure: float
    radius: float
    radial_depth: float
    step_size: float
    column: float
    electron_fraction: float
    hydrogen_density: float
    zeta: float
    xilev_after: np.ndarray
    rnist_after: np.ndarray
    rcem_after: np.ndarray
    oplin_after: np.ndarray
    tau0_after: np.ndarray
    cemab_after: np.ndarray
    cabab_after: np.ndarray
    opakab_after: np.ndarray
    tauc_after: np.ndarray
    zrems_after: np.ndarray
    dpthc_after: np.ndarray
    opakc_after: np.ndarray
    rccemis_after: np.ndarray
    zrems_saved_but_not_restored: bool
    source_file: str = "xstar/xstarlib/src/unsavd.f90"


def make_saved_shell_snapshot(
    *,
    pass_index: int,
    zone_index: int,
    terminal_record: bool,
    temperature: float,
    pressure: float,
    radius: float,
    radial_depth: float,
    step_size: float,
    column: float,
    electron_fraction: float,
    hydrogen_density: float,
    zeta: float,
    xilev: Sequence[float],
    rnist: Sequence[float],
    rcem: Sequence[Sequence[float]],
    oplin: Sequence[float],
    tau0: Sequence[Sequence[float]],
    cemab: Sequence[Sequence[float]],
    cabab: Sequence[float],
    opakab: Sequence[float],
    tauc: Sequence[Sequence[float]],
    elumab: Sequence[Sequence[float]],
    zrems: Sequence[Sequence[float]],
    dpthc: Sequence[Sequence[float]],
    dpthcont: Sequence[Sequence[float]],
    zremsz: Sequence[float],
    opakc: Sequence[float],
    rccemis: Sequence[Sequence[float]],
    ncn2: int,
    level_indices_one_based: Optional[Sequence[int]] = None,
    line_indices_one_based: Optional[Sequence[int]] = None,
    rrc_indices_one_based: Optional[Sequence[int]] = None,
) -> SavedShellSnapshot:
    """Capture the subset written by ``fstepr*`` with REAL(4) rounding."""
    n = int(ncn2)
    x = np.asarray(xilev, dtype=float).reshape(-1)
    rn = np.asarray(rnist, dtype=float).reshape(-1)
    if x.shape != rn.shape:
        raise SavedRadialStatePortError("xilev and rnist must have equal lengths")
    line = np.asarray(oplin, dtype=float).reshape(-1)
    rrc = np.asarray(opakab, dtype=float).reshape(-1)
    li = _index_vector(level_indices_one_based, size=x.size, name="level indices")
    lni = _index_vector(line_indices_one_based, size=line.size, name="line indices")
    ri = _index_vector(rrc_indices_one_based, size=rrc.size, name="RRC indices")

    rc = np.asarray(rcem, dtype=float)
    tau = np.asarray(tau0, dtype=float)
    ce = np.asarray(cemab, dtype=float)
    tc = np.asarray(tauc, dtype=float)
    elb = np.asarray(elumab, dtype=float)
    zr = np.asarray(zrems, dtype=float)
    dc = np.asarray(dpthc, dtype=float)
    dpc = np.asarray(dpthcont, dtype=float)
    zz = np.asarray(zremsz, dtype=float).reshape(-1)
    opc = np.asarray(opakc, dtype=float).reshape(-1)
    rce = np.asarray(rccemis, dtype=float)
    ca = np.asarray(cabab, dtype=float).reshape(-1)
    if rc.ndim != 2 or rc.shape[0] < 2 or rc.shape[1] < line.size:
        raise SavedRadialStatePortError("rcem shape is inconsistent with oplin")
    if tau.ndim != 2 or tau.shape[0] < 2 or tau.shape[1] < line.size:
        raise SavedRadialStatePortError("tau0 shape is inconsistent with oplin")
    if ce.ndim != 2 or ce.shape[0] < 2 or ce.shape[1] < rrc.size:
        raise SavedRadialStatePortError("cemab shape is inconsistent with opakab")
    if tc.ndim != 2 or tc.shape[0] < 2 or tc.shape[1] < rrc.size:
        raise SavedRadialStatePortError("tauc shape is inconsistent with opakab")
    if ca.size < rrc.size:
        raise SavedRadialStatePortError("cabab is shorter than opakab")
    if elb.ndim != 2 or elb.shape[0] < 2 or elb.shape[1] < rrc.size:
        raise SavedRadialStatePortError("elumab shape is inconsistent with opakab")
    if zr.ndim != 2 or zr.shape[0] < 5 or zr.shape[1] < n:
        raise SavedRadialStatePortError("zrems is shorter than the active continuum")
    if dc.ndim != 2 or dc.shape[0] < 2 or dc.shape[1] < n:
        raise SavedRadialStatePortError("dpthc is shorter than the active continuum")
    if dpc.ndim != 2 or dpc.shape[0] < 2 or dpc.shape[1] < n:
        raise SavedRadialStatePortError("dpthcont is shorter than the active continuum")
    if zz.size < n:
        raise SavedRadialStatePortError("zremsz is shorter than the active continuum")
    if opc.size < n or rce.ndim != 2 or rce.shape[0] < 2 or rce.shape[1] < n:
        raise SavedRadialStatePortError("continuum opacity/emissivity range is incomplete")

    snapshot = SavedShellSnapshot(
        pass_index=int(pass_index),
        zone_index=int(zone_index),
        terminal_record=bool(terminal_record),
        temperature=_real4_scalar(temperature),
        pressure=_real4_scalar(pressure),
        radius=_real4_scalar(radius),
        radial_depth=_real4_scalar(radial_depth),
        step_size=_real4_scalar(step_size),
        column=_real4_scalar(column),
        electron_fraction=_real4_scalar(electron_fraction),
        hydrogen_density=_real4_scalar(hydrogen_density),
        zeta=_real4_scalar(zeta),
        level_indices_one_based=li.copy(),
        xilev=_real4_array(x[li - 1]),
        rnist=_real4_array(rn[li - 1]),
        line_indices_one_based=lni.copy(),
        rcem=_real4_array(rc[:2, lni - 1]),
        oplin=_real4_array(line[lni - 1]),
        tau0=_real4_array(tau[:2, lni - 1]),
        rrc_indices_one_based=ri.copy(),
        cemab=_real4_array(ce[:2, ri - 1]),
        cabab=_real4_array(ca[ri - 1]),
        opakab=_real4_array(rrc[ri - 1]),
        tauc=_real4_array(tc[:2, ri - 1]),
        elumab=_real4_array(elb[:2, ri - 1]),
        ncn2=n,
        zrems_saved=_real4_array(zr[:5, :n]),
        dpthc=_real4_array(dc[:2, :n]),
        dpthcont=_real4_array(dpc[:2, :n]),
        zremsz=_real4_array(zz[:n]),
        opakc=_real4_array(opc[:n]),
        rccemis=_real4_array(rce[:2, :n]),
    )
    snapshot.validate()
    return snapshot


def unsavd(
    snapshot: SavedShellSnapshot,
    *,
    jkstep: int,
    direction: int,
    epi_eV: Sequence[float],
    ncn2: int,
    xilev_before: Sequence[float],
    rnist_before: Sequence[float],
    rcem_before: Sequence[Sequence[float]],
    oplin_before: Sequence[float],
    tau0_before: Sequence[Sequence[float]],
    cemab_before: Sequence[Sequence[float]],
    cabab_before: Sequence[float],
    opakab_before: Sequence[float],
    tauc_before: Sequence[Sequence[float]],
    zrems_before: Sequence[Sequence[float]],
    dpthc_before: Sequence[Sequence[float]],
    opakc_before: Sequence[float],
    rccemis_before: Sequence[Sequence[float]],
) -> UnsavdResult:
    """Translate the caller-visible assignments of ``unsavd.f90``."""
    snapshot.validate()
    ldir = int(direction)
    if ldir not in (-1, 1):
        raise SavedRadialStatePortError("unsavd direction must be -1 or 1")
    n = int(ncn2)
    if n != int(snapshot.ncn2):
        raise SavedRadialStatePortError(
            f"unsavd active continuum {n} differs from snapshot {snapshot.ncn2}"
        )
    epi = np.asarray(epi_eV, dtype=float).reshape(-1)
    if epi.size < n:
        raise SavedRadialStatePortError("epi is shorter than ncn2")

    x = np.asarray(xilev_before, dtype=float).reshape(-1).copy()
    rn = np.asarray(rnist_before, dtype=float).reshape(-1).copy()
    rc = np.asarray(rcem_before, dtype=float).copy()
    line = np.asarray(oplin_before, dtype=float).reshape(-1).copy()
    tau = np.asarray(tau0_before, dtype=float).copy()
    ce = np.asarray(cemab_before, dtype=float).copy()
    ca = np.asarray(cabab_before, dtype=float).reshape(-1).copy()
    opa = np.asarray(opakab_before, dtype=float).reshape(-1).copy()
    tc = np.asarray(tauc_before, dtype=float).copy()
    zr = np.asarray(zrems_before, dtype=float).copy()
    dc = np.asarray(dpthc_before, dtype=float).copy()
    opc = np.asarray(opakc_before, dtype=float).reshape(-1).copy()
    rce = np.asarray(rccemis_before, dtype=float).copy()

    li = snapshot.level_indices_one_based - 1
    lni = snapshot.line_indices_one_based - 1
    ri = snapshot.rrc_indices_one_based - 1
    if x.size <= np.max(li, initial=-1) or rn.size <= np.max(li, initial=-1):
        raise SavedRadialStatePortError("caller level arrays are too short")
    if (
        rc.ndim != 2
        or rc.shape[0] < 2
        or rc.shape[1] <= np.max(lni, initial=-1)
        or line.size <= np.max(lni, initial=-1)
        or tau.ndim != 2
        or tau.shape[0] < 2
        or tau.shape[1] <= np.max(lni, initial=-1)
    ):
        raise SavedRadialStatePortError("caller line arrays are too short")
    if (
        ce.ndim != 2
        or ce.shape[0] < 2
        or ce.shape[1] <= np.max(ri, initial=-1)
        or ca.size <= np.max(ri, initial=-1)
        or opa.size <= np.max(ri, initial=-1)
        or tc.ndim != 2
        or tc.shape[0] < 2
        or tc.shape[1] <= np.max(ri, initial=-1)
    ):
        raise SavedRadialStatePortError("caller RRC arrays are too short")
    if (
        zr.ndim != 2
        or zr.shape[0] < 5
        or zr.shape[1] < n
        or dc.ndim != 2
        or dc.shape[0] < 2
        or dc.shape[1] < n
        or opc.size < n
        or rce.ndim != 2
        or rce.shape[0] < 2
        or rce.shape[1] < n
    ):
        raise SavedRadialStatePortError("caller continuum arrays are too short")

    # rstepr/rstepr2/rstepr3/rstepr4 directly restore these arrays.
    x[li] = snapshot.xilev
    rn[li] = snapshot.rnist
    rc[:2, lni] = snapshot.rcem
    line[lni] = snapshot.oplin
    ce[:2, ri] = snapshot.cemab
    ca[ri] = snapshot.cabab
    opa[ri] = snapshot.opakab
    opc[:n] = snapshot.opakc
    rce[:2, :n] = snapshot.rccemis

    # unsavd copies only the direction-owned rows from local temporaries.
    row = 0 if ldir > 0 else 1
    tau[row, lni] = snapshot.tau0[row]
    tc[row, ri] = snapshot.tauc[row]
    dc[row, :n] = snapshot.dpthc[row]

    # rstepr4 reads zrems into zremsdum, which unsavd never copies back.
    zrems_unchanged = np.array_equal(zr, np.asarray(zrems_before, dtype=float))
    nry = int(nbinc(13.7, epi, n) + 1)
    return UnsavdResult(
        jkstep=int(jkstep),
        direction=ldir,
        direction_row_one_based=row + 1,
        ncn2=n,
        nry=nry,
        temperature=float(snapshot.temperature),
        pressure=float(snapshot.pressure),
        radius=float(snapshot.radius),
        radial_depth=float(snapshot.radial_depth),
        step_size=float(snapshot.step_size),
        column=float(snapshot.column),
        electron_fraction=float(snapshot.electron_fraction),
        hydrogen_density=float(snapshot.hydrogen_density),
        zeta=float(snapshot.zeta),
        xilev_after=x,
        rnist_after=rn,
        rcem_after=rc,
        oplin_after=line,
        tau0_after=tau,
        cemab_after=ce,
        cabab_after=ca,
        opakab_after=opa,
        tauc_after=tc,
        zrems_after=zr,
        dpthc_after=dc,
        opakc_after=opc,
        rccemis_after=rce,
        zrems_saved_but_not_restored=bool(zrems_unchanged),
    )


def direct_fortran_unsavd_reference_cases() -> Mapping[str, object]:
    """Frozen output from unmodified ``unsavd.f90`` with deterministic stubs."""
    scalars = [
        4.5678901234560000e5,
        5.6789012345669996e-3,
        1.2345678901230000e19,
        3.4567890123450000e12,
        2.3456789012340000e12,
        6.7890123456779995e21,
        7.8901234567890000e-1,
        8.9012345678900003e7,
        9.0123456789009992,
    ]
    common = {
        "scalars": scalars,
        "xilev": [10.1, 10.2, 10.3],
        "rnist": [20.1, 20.2, 20.3],
        "rcem": [[30.1, 30.2, 30.3, 30.4], [40.1, 40.2, 40.3, 40.4]],
        "oplin": [50.1, 50.2, 50.3, 50.4],
        "cemab": [[80.1, 80.2, 80.3], [90.1, 90.2, 90.3]],
        "cabab": [100.1, 100.2, 100.3],
        "opakab": [110.1, 110.2, 110.3],
        "opakc": [220.1, 220.2, 220.3, 220.4, -2205.0, -2206.0],
        "rccemis": [
            [230.1, 230.2, 230.3, 230.4, -2305.0, -2306.0],
            [240.1, 240.2, 240.3, 240.4, -2405.0, -2406.0],
        ],
    }
    return {
        "common": common,
        "direction_minus": {
            "tau0": [
                [-601.0, -602.0, -603.0, -604.0],
                [70.1, 70.2, 70.3, 70.4],
            ],
            "tauc": [
                [-1201.0, -1202.0, -1203.0],
                [130.1, 130.2, 130.3],
            ],
            "dpthc": [
                [-2001.0, -2002.0, -2003.0, -2004.0, -2005.0, -2006.0],
                [210.1, 210.2, 210.3, 210.4, -2105.0, -2106.0],
            ],
        },
        "direction_plus": {
            "tau0": [
                [60.1, 60.2, 60.3, 60.4],
                [-701.0, -702.0, -703.0, -704.0],
            ],
            "tauc": [
                [120.1, 120.2, 120.3],
                [-1301.0, -1302.0, -1303.0],
            ],
            "dpthc": [
                [200.1, 200.2, 200.3, 200.4, -2005.0, -2006.0],
                [-2101.0, -2102.0, -2103.0, -2104.0, -2105.0, -2106.0],
            ],
        },
        "zrems": [
            [-1411.0, -1412.0, -1413.0, -1414.0, -1415.0, -1416.0],
            [-1421.0, -1422.0, -1423.0, -1424.0, -1425.0, -1426.0],
            [-1431.0, -1432.0, -1433.0, -1434.0, -1435.0, -1436.0],
            [-1441.0, -1442.0, -1443.0, -1444.0, -1445.0, -1446.0],
            [-1451.0, -1452.0, -1453.0, -1454.0, -1455.0, -1456.0],
        ],
    }


def _direct_unsavd_python_result(direction: int) -> UnsavdResult:
    ncn = 6
    ncn2 = 4
    n_lines = 4
    n_rrc = 3
    snapshot = SavedShellSnapshot(
        pass_index=1,
        zone_index=2,
        terminal_record=False,
        temperature=4.567890123456e5,
        pressure=5.678901234567e-3,
        radius=1.234567890123e19,
        radial_depth=3.456789012345e12,
        step_size=2.345678901234e12,
        column=6.789012345678e21,
        electron_fraction=7.890123456789e-1,
        hydrogen_density=8.901234567890e7,
        zeta=9.012345678901,
        level_indices_one_based=np.arange(1, 4, dtype=int),
        xilev=np.asarray([10.1, 10.2, 10.3]),
        rnist=np.asarray([20.1, 20.2, 20.3]),
        line_indices_one_based=np.arange(1, 5, dtype=int),
        rcem=np.asarray([[30.1, 30.2, 30.3, 30.4], [40.1, 40.2, 40.3, 40.4]]),
        oplin=np.asarray([50.1, 50.2, 50.3, 50.4]),
        tau0=np.asarray([[60.1, 60.2, 60.3, 60.4], [70.1, 70.2, 70.3, 70.4]]),
        rrc_indices_one_based=np.arange(1, 4, dtype=int),
        cemab=np.asarray([[80.1, 80.2, 80.3], [90.1, 90.2, 90.3]]),
        cabab=np.asarray([100.1, 100.2, 100.3]),
        opakab=np.asarray([110.1, 110.2, 110.3]),
        tauc=np.asarray([[120.1, 120.2, 120.3], [130.1, 130.2, 130.3]]),
        ncn2=ncn2,
        zrems_saved=np.arange(5 * ncn2, dtype=float).reshape(5, ncn2),
        dpthc=np.asarray([[200.1, 200.2, 200.3, 200.4], [210.1, 210.2, 210.3, 210.4]]),
        dpthcont=np.asarray([[211.1, 211.2, 211.3, 211.4], [212.1, 212.2, 212.3, 212.4]]),
        zremsz=np.asarray([213.1, 213.2, 213.3, 213.4]),
        opakc=np.asarray([220.1, 220.2, 220.3, 220.4]),
        rccemis=np.asarray([[230.1, 230.2, 230.3, 230.4], [240.1, 240.2, 240.3, 240.4]]),
    )
    zrems_before = np.empty((5, ncn), dtype=float)
    for row in range(5):
        for col in range(ncn):
            zrems_before[row, col] = -1400.0 - 10.0 * (row + 1) - (col + 1)
    return unsavd(
        snapshot,
        jkstep=7,
        direction=direction,
        epi_eV=np.arange(1, ncn + 1, dtype=float),
        ncn2=ncn2,
        xilev_before=-100.0 - np.arange(1, 4, dtype=float),
        rnist_before=-200.0 - np.arange(1, 4, dtype=float),
        rcem_before=np.vstack(
            [-300.0 - np.arange(1, n_lines + 1), -400.0 - np.arange(1, n_lines + 1)]
        ),
        oplin_before=-500.0 - np.arange(1, n_lines + 1, dtype=float),
        tau0_before=np.vstack(
            [-600.0 - np.arange(1, n_lines + 1), -700.0 - np.arange(1, n_lines + 1)]
        ),
        cemab_before=np.vstack(
            [-800.0 - np.arange(1, n_rrc + 1), -900.0 - np.arange(1, n_rrc + 1)]
        ),
        cabab_before=-1000.0 - np.arange(1, n_rrc + 1, dtype=float),
        opakab_before=-1100.0 - np.arange(1, n_rrc + 1, dtype=float),
        tauc_before=np.vstack(
            [-1200.0 - np.arange(1, n_rrc + 1), -1300.0 - np.arange(1, n_rrc + 1)]
        ),
        zrems_before=zrems_before,
        dpthc_before=np.vstack(
            [-2000.0 - np.arange(1, ncn + 1), -2100.0 - np.arange(1, ncn + 1)]
        ),
        opakc_before=-2200.0 - np.arange(1, ncn + 1, dtype=float),
        rccemis_before=np.vstack(
            [-2300.0 - np.arange(1, ncn + 1), -2400.0 - np.arange(1, ncn + 1)]
        ),
    )


def run_direct_fortran_unsavd_validation(
    *, rtol: float = 2.0e-15, atol: float = 0.0
) -> Mapping[str, bool]:
    """Compare translated ``unsavd`` with frozen original-Fortran outputs."""
    refs = direct_fortran_unsavd_reference_cases()
    common = refs["common"]
    minus = _direct_unsavd_python_result(-1)
    plus = _direct_unsavd_python_result(1)

    def close(actual: object, expected: object) -> bool:
        return bool(
            np.allclose(
                np.asarray(actual, dtype=float),
                np.asarray(expected, dtype=float),
                rtol=rtol,
                atol=atol,
            )
        )

    scalar_minus = [
        minus.temperature,
        minus.pressure,
        minus.radius,
        minus.radial_depth,
        minus.step_size,
        minus.column,
        minus.electron_fraction,
        minus.hydrogen_density,
        minus.zeta,
    ]
    scalar_plus = [
        plus.temperature,
        plus.pressure,
        plus.radius,
        plus.radial_depth,
        plus.step_size,
        plus.column,
        plus.electron_fraction,
        plus.hydrogen_density,
        plus.zeta,
    ]
    summary = {
        "unsavd_translated": True,
        "unsavd_scalar_direct_fortran_ready": close(scalar_minus, common["scalars"])
        and close(scalar_plus, common["scalars"]),
        "unsavd_population_direct_fortran_ready": close(minus.xilev_after, common["xilev"])
        and close(minus.rnist_after, common["rnist"]),
        "unsavd_line_direct_fortran_ready": close(minus.rcem_after, common["rcem"])
        and close(minus.oplin_after, common["oplin"]),
        "unsavd_rrc_direct_fortran_ready": close(minus.cemab_after, common["cemab"])
        and close(minus.cabab_after, common["cabab"])
        and close(minus.opakab_after, common["opakab"]),
        "unsavd_continuum_direct_fortran_ready": close(minus.opakc_after, common["opakc"])
        and close(minus.rccemis_after, common["rccemis"]),
        "unsavd_direction_minus_optical_depth_ready": close(
            minus.tau0_after, refs["direction_minus"]["tau0"]
        )
        and close(minus.tauc_after, refs["direction_minus"]["tauc"])
        and close(minus.dpthc_after, refs["direction_minus"]["dpthc"]),
        "unsavd_direction_plus_optical_depth_ready": close(
            plus.tau0_after, refs["direction_plus"]["tau0"]
        )
        and close(plus.tauc_after, refs["direction_plus"]["tauc"])
        and close(plus.dpthc_after, refs["direction_plus"]["dpthc"]),
        "unsavd_zrems_local_temporary_semantics_ready": close(
            minus.zrems_after, refs["zrems"]
        )
        and close(plus.zrems_after, refs["zrems"])
        and minus.zrems_saved_but_not_restored
        and plus.zrems_saved_but_not_restored,
    }
    summary["unsavd_direct_original_fortran_reference_ready"] = bool(
        all(value for key, value in summary.items() if key.endswith("_ready"))
    )
    return summary


__all__ = [
    "SavedRadialStatePortError",
    "SavedShellSnapshot",
    "SavedRadialPassState",
    "SavedRadialStateStore",
    "UnsavdResult",
    "make_saved_shell_snapshot",
    "unsavd",
    "direct_fortran_unsavd_reference_cases",
    "run_direct_fortran_unsavd_validation",
]
