"""Source-faithful translation of XSTAR's relativistic Compton subsystem.

This module translates the coherent source path

``calc_hmc_all.f90 -> comp2.f90 -> cmpfnc.f90 -> hunt3.f90``

and the global ``coheat.dat`` table state initialized by ``xstarsetup.f90``.
The original XSTAR constants, table orientation, boundary interpolation, and
trapezoidal continuum integration are preserved deliberately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import csv
import hashlib
import json
import math
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .fortran_numbers import parse_fortran_float


XSTAR_COMPTON_NCOMP = 101
XSTAR_COMPTON_EMC2_EV = 5.11e5
XSTAR_COMPTON_KT_EV_PER_T4 = float(np.float32(0.861707))
XSTAR_THOMSON_CROSS_SECTION_CM2 = float(np.float32(6.6524587321e-25))
XSTAR_ERG_PER_EV = float(np.float32(1.602176634e-12))


class ComptonPortError(RuntimeError):
    """Raised when the translated Compton subsystem cannot execute."""


@dataclass(frozen=True)
class ComptonTableState:
    """Global ``coheat.dat`` arrays from ``globaldata.f90``.

    ``decomp`` uses the exact source orientation ``decomp(sx_index,
    energy_index)``.  Arrays are stored zero-based in Python, but all
    interpolation indices reported in diagnostics retain the one-based XSTAR
    convention.
    """

    ecomp: np.ndarray
    sxcomp: np.ndarray
    decomp: np.ndarray
    ncomp: int
    source_path: str
    source_sha256: str
    loaded: bool = True
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        n = int(self.ncomp)
        e = np.asarray(self.ecomp, dtype=float)
        sx = np.asarray(self.sxcomp, dtype=float)
        de = np.asarray(self.decomp, dtype=float)
        if n != XSTAR_COMPTON_NCOMP:
            raise ComptonPortError(
                f"coheat table must contain ncomp={XSTAR_COMPTON_NCOMP}, got {n}"
            )
        if e.shape != (n,) or sx.shape != (n,) or de.shape != (n, n):
            raise ComptonPortError(
                f"invalid coheat shapes: ecomp={e.shape}, sxcomp={sx.shape}, "
                f"decomp={de.shape}, ncomp={n}"
            )
        if not np.all(np.isfinite(e)) or not np.all(np.isfinite(sx)) or not np.all(np.isfinite(de)):
            raise ComptonPortError("coheat table contains non-finite values")
        if np.any(np.diff(e) <= 0.0) or np.any(np.diff(sx) <= 0.0):
            raise ComptonPortError("coheat ecomp/sxcomp grids must be strictly increasing")


@dataclass(frozen=True)
class CmpFncResult:
    """One translated ``cmpfnc`` evaluation with source indices."""

    value: float
    ee: float
    sxx: float
    used_table: bool
    energy_index_one_based: int
    temperature_index_one_based: int
    energy_lower_one_based: int
    temperature_lower_one_based: int
    ddede: float
    ddedsx: float
    dele: float
    delsx: float


@dataclass(frozen=True)
class Comp2Result:
    """Complete result of XSTAR ``comp2.f90``."""

    cmp1: float
    cmp2: float
    temperature_t4: float
    ekt_ev: float
    electron_rest_energy_ev: float
    sxx: float
    sum1: float
    sum2: float
    sum3: float
    cfake: float
    hfake: float
    cohc: float
    ncn2: int
    cmpfnc_table_loaded: bool
    n_cmpfnc_table_evaluations: int
    n_cmpfnc_low_energy_evaluations: int
    table_source_path: str
    table_source_sha256: str
    source_file: str = "xstar/xstarlib/src/comp2.f90"

    def heating_rate(self, *, hydrogen_density_cm3: float, electron_fraction_xee: float) -> float:
        """Return ``heatf``'s Compton heating rate in erg cm^-3 s^-1."""
        xnx = float(hydrogen_density_cm3) * float(electron_fraction_xee)
        return float(self.cmp1) * xnx * XSTAR_ERG_PER_EV

    def cooling_rate(self, *, hydrogen_density_cm3: float, electron_fraction_xee: float) -> float:
        """Return ``heatf``'s Compton cooling rate in erg cm^-3 s^-1."""
        xnx = float(hydrogen_density_cm3) * float(electron_fraction_xee)
        return float(self.ekt_ev) * float(self.cmp2) * xnx * XSTAR_ERG_PER_EV


@dataclass(frozen=True)
class Comp2Context:
    """Inputs needed to execute ``comp2`` inside translated ``calc_hmc_all``."""

    epi_eV: np.ndarray
    bremsa: np.ndarray
    table: ComptonTableState
    ncn2: Optional[int] = None
    source: str = "xstar_comp2_same_call_probe"

    def validate(self) -> None:
        epi = np.asarray(self.epi_eV, dtype=float).reshape(-1)
        brem = np.asarray(self.bremsa, dtype=float).reshape(-1)
        n = epi.size if self.ncn2 is None else int(self.ncn2)
        if n < 2:
            raise ComptonPortError("comp2 requires at least two continuum bins")
        if epi.size < n or brem.size < n:
            raise ComptonPortError(
                f"comp2 arrays shorter than ncn2={n}: epi={epi.size}, bremsa={brem.size}"
            )
        if not np.all(np.isfinite(epi[:n])) or not np.all(np.isfinite(brem[:n])):
            raise ComptonPortError("comp2 continuum contains non-finite values")
        if np.any(np.diff(epi[:n]) <= 0.0):
            raise ComptonPortError("comp2 photon-energy grid must be strictly increasing")
        self.table.validate()


@dataclass(frozen=True)
class Comp2ProbeReference:
    """Exact same-call XSTAR inputs and outputs captured after ``comp2``."""

    call_id: int
    ncn2: int
    temperature_t4: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    ekt_ev: float
    cmp1: float
    cmp2: float
    htcomp: float
    clcomp: float
    epi_eV: np.ndarray
    bremsa: np.ndarray
    summary_path: str
    grid_path: str


@dataclass(frozen=True)
class Comp2ParityResult:
    """Bounded v0.4.39 XSTAR/Python Compton comparison."""

    call_id: int
    python: Comp2Result
    reference: Comp2ProbeReference
    cmp1_absolute_difference: float
    cmp1_relative_difference: float
    cmp2_absolute_difference: float
    cmp2_relative_difference: float
    htcomp_absolute_difference: float
    htcomp_relative_difference: float
    clcomp_absolute_difference: float
    clcomp_relative_difference: float
    cmp1_parity_ready: bool
    cmp2_parity_ready: bool
    compton_heating_parity_ready: bool
    compton_cooling_parity_ready: bool
    comp2_translated: bool
    cmpfnc_table_loaded: bool
    continuum_grid_parity_ready: bool
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(
            self.comp2_translated
            and self.cmpfnc_table_loaded
            and self.continuum_grid_parity_ready
            and self.cmp1_parity_ready
            and self.cmp2_parity_ready
            and self.compton_heating_parity_ready
            and self.compton_cooling_parity_ready
        )


def packaged_coheat_path() -> Path:
    """Return the packaged source copy of XSTAR ``coheat.dat``."""
    target = resources.files("xstar_tools.xstar").joinpath("data/coheat.dat")
    return Path(str(target))


def resolve_coheat_path(path: str | Path | None = None, *, atdb_path: str | Path | None = None) -> Path:
    """Resolve ``coheat.dat`` with explicit, XSTAR-data, then packaged precedence."""
    candidates: List[Path] = []
    if path is not None:
        candidates.append(Path(path))
    if atdb_path is not None:
        candidates.append(Path(atdb_path).resolve().parent / "coheat.dat")
    candidates.append(packaged_coheat_path())
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "coheat.dat was not found; supply --coheat-data or place it beside atdb.fits"
    )


def load_compton_table(path: str | Path | None = None, *, atdb_path: str | Path | None = None) -> ComptonTableState:
    """Translate the ``xstarsetup.f90`` global Compton-table initialization."""
    target = resolve_coheat_path(path, atdb_path=atdb_path)
    raw = target.read_bytes()
    ecomp = np.zeros(XSTAR_COMPTON_NCOMP, dtype=float)
    sxcomp = np.zeros(XSTAR_COMPTON_NCOMP, dtype=float)
    decomp = np.zeros((XSTAR_COMPTON_NCOMP, XSTAR_COMPTON_NCOMP), dtype=float)
    seen = np.zeros_like(decomp, dtype=bool)
    n_rows = 0
    for lineno, line in enumerate(raw.decode("ascii").splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) < 6:
            raise ComptonPortError(f"invalid coheat.dat line {lineno}: {line!r}")
        try:
            sx_index = int(fields[0])
            energy_index = int(fields[1])
            # ``xstarsetup.f90`` format 902 reads the third field, skips
            # the fourth (the reciprocal temperature coordinate), then
            # reads the fifth and sixth fields into ecomp/decomp.
            sx = parse_fortran_float(fields[2])
            energy = parse_fortran_float(fields[4])
            value = parse_fortran_float(fields[5])
        except Exception as exc:
            raise ComptonPortError(f"cannot parse coheat.dat line {lineno}: {line!r}") from exc
        if not (1 <= sx_index <= XSTAR_COMPTON_NCOMP and 1 <= energy_index <= XSTAR_COMPTON_NCOMP):
            raise ComptonPortError(
                f"coheat.dat index out of range at line {lineno}: {sx_index},{energy_index}"
            )
        i = sx_index - 1
        j = energy_index - 1
        sxcomp[i] = float(sx)
        ecomp[j] = float(energy)
        decomp[i, j] = float(value)
        seen[i, j] = True
        n_rows += 1
    if n_rows != XSTAR_COMPTON_NCOMP * XSTAR_COMPTON_NCOMP or not bool(np.all(seen)):
        raise ComptonPortError(
            f"coheat.dat must contain {XSTAR_COMPTON_NCOMP**2} complete rows, got {n_rows}"
        )
    state = ComptonTableState(
        ecomp=ecomp,
        sxcomp=sxcomp,
        decomp=decomp,
        ncomp=XSTAR_COMPTON_NCOMP,
        source_path=str(target),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        loaded=True,
        diagnostics={
            "source_file": "xstar/data/coheat.dat",
            "loader_source_file": "xstar/xstarlib/src/xstarsetup.f90",
            "array_orientation": "decomp(sx_index,energy_index)",
            "n_rows": n_rows,
        },
    )
    state.validate()
    return state


def hunt3_one_based(grid: Sequence[float], x: float) -> int:
    """Return XSTAR ``hunt3``'s one-based bracket index for monotonic grids."""
    arr = np.asarray(grid, dtype=float).reshape(-1)
    if arr.size < 1:
        raise ComptonPortError("hunt3 requires a non-empty grid")
    if np.any(np.diff(arr) <= 0.0):
        raise ComptonPortError("translated hunt3 currently requires an ascending grid")
    # ``hunt3`` begins at jlo=1 and treats equality as an upward hunt.  This is
    # equivalent to side='right', then source-clamping to [1,n].
    index = int(np.searchsorted(arr, float(x), side="right"))
    return max(1, min(int(arr.size), index))


def cmpfnc(ee: float, sxx: float, table: ComptonTableState) -> CmpFncResult:
    """Translate ``cmpfnc.f90`` exactly for one photon/temperature pair."""
    ee = float(ee)
    sxx = float(sxx)
    if not math.isfinite(ee) or not math.isfinite(sxx):
        raise ComptonPortError("cmpfnc inputs must be finite")
    if ee <= 1.0e-4:
        return CmpFncResult(
            value=4.0 * sxx - ee,
            ee=ee,
            sxx=sxx,
            used_table=False,
            energy_index_one_based=0,
            temperature_index_one_based=0,
            energy_lower_one_based=0,
            temperature_lower_one_based=0,
            ddede=0.0,
            ddedsx=0.0,
            dele=0.0,
            delsx=0.0,
        )

    table.validate()
    n = int(table.ncomp)
    mm = max(2, min(n, hunt3_one_based(table.ecomp, ee)))
    ll = max(2, min(n, hunt3_one_based(table.sxcomp, sxx)))
    m = mm - 1
    l = ll - 1
    m0 = m - 1
    l0 = l - 1
    de = np.asarray(table.decomp, dtype=float)
    egrid = np.asarray(table.ecomp, dtype=float)
    sxgrid = np.asarray(table.sxcomp, dtype=float)
    ddedsx = (
        de[l, m] - de[l0, m] + de[l, m0] - de[l0, m0]
    ) / (2.0 * (sxgrid[l] - sxgrid[l0]))
    ddede = (
        de[l, m] - de[l, m0] + de[l0, m] - de[l0, m0]
    ) / (2.0 * (egrid[m] - egrid[m0]))
    dele = ee - egrid[m0]
    delsx = sxx - sxgrid[l0]
    value = ddedsx * delsx + ddede * dele + de[l0, m0]
    return CmpFncResult(
        value=float(value),
        ee=ee,
        sxx=sxx,
        used_table=True,
        energy_index_one_based=mm,
        temperature_index_one_based=ll,
        energy_lower_one_based=mm - 1,
        temperature_lower_one_based=ll - 1,
        ddede=float(ddede),
        ddedsx=float(ddedsx),
        dele=float(dele),
        delsx=float(delsx),
    )


def comp2(
    epi_eV: Sequence[float],
    bremsa: Sequence[float],
    *,
    temperature_k: float,
    table: ComptonTableState,
    ncn2: Optional[int] = None,
) -> Comp2Result:
    """Translate XSTAR ``comp2.f90`` including source-order trapezoids."""
    epi = np.asarray(epi_eV, dtype=float).reshape(-1)
    brem = np.asarray(bremsa, dtype=float).reshape(-1)
    n = int(epi.size if ncn2 is None else ncn2)
    context = Comp2Context(epi_eV=epi, bremsa=brem, table=table, ncn2=n)
    context.validate()
    if not math.isfinite(float(temperature_k)) or float(temperature_k) <= 0.0:
        raise ComptonPortError("temperature_k must be finite and positive")

    t4 = float(temperature_k) / 1.0e4
    ekt = t4 * XSTAR_COMPTON_KT_EV_PER_T4
    xx = XSTAR_COMPTON_EMC2_EV / (ekt + 1.0e-10)
    sxx = 1.0 / xx

    eee = float(epi[0])
    ee = eee / XSTAR_COMPTON_EMC2_EV
    first = cmpfnc(ee, sxx, table)
    tmp1 = float(brem[0]) * first.value
    sum1 = 0.0
    sum2 = 0.0
    sum3 = 0.0
    n_table = int(first.used_table)
    n_low = int(not first.used_table)
    for kl in range(1, n):
        tmp1o = tmp1
        eeeo = eee
        eeo = ee
        eee = float(epi[kl])
        ee = eee / XSTAR_COMPTON_EMC2_EV
        evaluated = cmpfnc(ee, sxx, table)
        n_table += int(evaluated.used_table)
        n_low += int(not evaluated.used_table)
        tmp1 = float(brem[kl]) * evaluated.value
        width = eee - eeeo
        sum1 += (tmp1 + tmp1o) * width / 2.0
        sum2 += (float(brem[kl]) + float(brem[kl - 1])) * width / 2.0
        sum3 += (
            float(brem[kl]) * ee + float(brem[kl - 1]) * eeo
        ) * width / 2.0

    cfake = sum2 * XSTAR_THOMSON_CROSS_SECTION_CM2
    hfake = sum3 * XSTAR_THOMSON_CROSS_SECTION_CM2
    cohc = -sum1 * XSTAR_THOMSON_CROSS_SECTION_CM2
    cmp1_value = hfake
    cmp2_value = (-cohc + hfake) / ekt
    return Comp2Result(
        cmp1=float(cmp1_value),
        cmp2=float(cmp2_value),
        temperature_t4=float(t4),
        ekt_ev=float(ekt),
        electron_rest_energy_ev=XSTAR_COMPTON_EMC2_EV,
        sxx=float(sxx),
        sum1=float(sum1),
        sum2=float(sum2),
        sum3=float(sum3),
        cfake=float(cfake),
        hfake=float(hfake),
        cohc=float(cohc),
        ncn2=n,
        cmpfnc_table_loaded=bool(table.loaded),
        n_cmpfnc_table_evaluations=n_table,
        n_cmpfnc_low_energy_evaluations=n_low,
        table_source_path=table.source_path,
        table_source_sha256=table.source_sha256,
    )


def comp2_continuum_result(
    context: Comp2Context,
    *,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
) -> Tuple[Comp2Result, Dict[str, Any]]:
    """Execute ``comp2`` and derive the two rates later applied by ``heatf``."""
    context.validate()
    result = comp2(
        context.epi_eV,
        context.bremsa,
        temperature_k=temperature_k,
        table=context.table,
        ncn2=context.ncn2,
    )
    htcomp = result.heating_rate(
        hydrogen_density_cm3=hydrogen_density_cm3,
        electron_fraction_xee=electron_fraction_xee,
    )
    clcomp = result.cooling_rate(
        hydrogen_density_cm3=hydrogen_density_cm3,
        electron_fraction_xee=electron_fraction_xee,
    )
    return result, {
        "status": "comp2_complete_freef_bremem_heatf_deferred",
        "comp2_translated": True,
        "cmpfnc_translated": True,
        "hunt3_translated": True,
        "cmpfnc_table_loaded": bool(result.cmpfnc_table_loaded),
        "cmp1": result.cmp1,
        "cmp2": result.cmp2,
        "ekt_ev": result.ekt_ev,
        "htcomp": htcomp,
        "clcomp": clcomp,
        "ncn2": result.ncn2,
        "compton_context_source": context.source,
        "coheat_source_path": result.table_source_path,
        "coheat_source_sha256": result.table_source_sha256,
        "missing_source_sequence": "freef -> bremem -> heatf",
        "heatf_rates_derived_for_parity_only": True,
        "heatf_rates_accumulated_into_totals": False,
    }


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _select_call_id(rows: Iterable[Mapping[str, str]], requested: Optional[int]) -> int:
    ids = sorted({int(row["calc_hmc_all_call_id"]) for row in rows})
    if not ids:
        raise ComptonPortError("Compton probe contains no calc_hmc_all call ids")
    selected = ids[-1] if requested is None else int(requested)
    if selected not in ids:
        raise ComptonPortError(f"Compton probe call {selected} not present; available={ids}")
    return selected


def load_comp2_probe_reference(
    probe_dir: str | Path,
    *,
    call_id: Optional[int] = None,
) -> Comp2ProbeReference:
    """Load exact same-call ``epi/bremsa/cmp1/cmp2`` XSTAR probe products."""
    root = Path(probe_dir)
    summary_path = root / "xstar_calc_hmc_all_comp2_summary_probe.csv"
    grid_path = root / "xstar_calc_hmc_all_comp2_grid_probe.csv"
    summaries = _read_csv(summary_path)
    grids = _read_csv(grid_path)
    if not summaries:
        raise ComptonPortError(f"missing or empty Comp2 summary probe: {summary_path}")
    if not grids:
        raise ComptonPortError(f"missing or empty Comp2 grid probe: {grid_path}")
    selected = _select_call_id(summaries, call_id)
    selected_summary = [
        row for row in summaries if int(row["calc_hmc_all_call_id"]) == selected
    ]
    if len(selected_summary) != 1:
        raise ComptonPortError(
            f"expected one Comp2 summary row for call {selected}, got {len(selected_summary)}"
        )
    row = selected_summary[0]
    selected_grid = [
        item for item in grids if int(item["calc_hmc_all_call_id"]) == selected
    ]
    selected_grid.sort(key=lambda item: int(item["grid_index"]))
    ncn2 = int(row["ncn2"])
    if len(selected_grid) != ncn2:
        raise ComptonPortError(
            f"Comp2 grid row count mismatch for call {selected}: {len(selected_grid)} != {ncn2}"
        )
    indices = [int(item["grid_index"]) for item in selected_grid]
    if indices != list(range(1, ncn2 + 1)):
        raise ComptonPortError("Comp2 probe grid indices are not complete and consecutive")
    epi = np.asarray([parse_fortran_float(item["epi_eV"]) for item in selected_grid], dtype=float)
    bremsa = np.asarray([parse_fortran_float(item["bremsa"]) for item in selected_grid], dtype=float)
    if np.any(np.diff(epi) <= 0.0):
        raise ComptonPortError("Comp2 probe energy grid is not strictly increasing")
    return Comp2ProbeReference(
        call_id=selected,
        ncn2=ncn2,
        temperature_t4=parse_fortran_float(row["temperature_t4"]),
        electron_fraction_xee=parse_fortran_float(row["electron_fraction_xee"]),
        hydrogen_density_cm3=parse_fortran_float(row["hydrogen_density_cm3"]),
        ekt_ev=parse_fortran_float(row["ekt_ev"]),
        cmp1=parse_fortran_float(row["cmp1"]),
        cmp2=parse_fortran_float(row["cmp2"]),
        htcomp=parse_fortran_float(row["htcomp"]),
        clcomp=parse_fortran_float(row["clcomp"]),
        epi_eV=epi,
        bremsa=bremsa,
        summary_path=str(summary_path),
        grid_path=str(grid_path),
    )


def _difference(got: float, expected: float) -> Tuple[float, float]:
    absolute = abs(float(got) - float(expected))
    relative = absolute / max(abs(float(expected)), 1.0e-300)
    return absolute, relative


def _within(got: float, expected: float, *, rtol: float, atol: float) -> bool:
    return abs(float(got) - float(expected)) <= float(atol) + float(rtol) * abs(float(expected))


def compare_comp2_probe(
    reference: Comp2ProbeReference,
    *,
    table: ComptonTableState,
    rtol: float = 5.0e-12,
    atol: float = 1.0e-30,
) -> Comp2ParityResult:
    """Recompute the exact XSTAR call and compare coefficients and rates."""
    python = comp2(
        reference.epi_eV,
        reference.bremsa,
        temperature_k=reference.temperature_t4 * 1.0e4,
        table=table,
        ncn2=reference.ncn2,
    )
    htcomp = python.heating_rate(
        hydrogen_density_cm3=reference.hydrogen_density_cm3,
        electron_fraction_xee=reference.electron_fraction_xee,
    )
    clcomp = python.cooling_rate(
        hydrogen_density_cm3=reference.hydrogen_density_cm3,
        electron_fraction_xee=reference.electron_fraction_xee,
    )
    cmp1_abs, cmp1_rel = _difference(python.cmp1, reference.cmp1)
    cmp2_abs, cmp2_rel = _difference(python.cmp2, reference.cmp2)
    ht_abs, ht_rel = _difference(htcomp, reference.htcomp)
    cl_abs, cl_rel = _difference(clcomp, reference.clcomp)
    grid_ready = bool(
        reference.epi_eV.size == reference.ncn2
        and reference.bremsa.size == reference.ncn2
        and np.all(np.isfinite(reference.epi_eV))
        and np.all(np.isfinite(reference.bremsa))
        and np.all(np.diff(reference.epi_eV) > 0.0)
    )
    return Comp2ParityResult(
        call_id=reference.call_id,
        python=python,
        reference=reference,
        cmp1_absolute_difference=cmp1_abs,
        cmp1_relative_difference=cmp1_rel,
        cmp2_absolute_difference=cmp2_abs,
        cmp2_relative_difference=cmp2_rel,
        htcomp_absolute_difference=ht_abs,
        htcomp_relative_difference=ht_rel,
        clcomp_absolute_difference=cl_abs,
        clcomp_relative_difference=cl_rel,
        cmp1_parity_ready=_within(python.cmp1, reference.cmp1, rtol=rtol, atol=atol),
        cmp2_parity_ready=_within(python.cmp2, reference.cmp2, rtol=rtol, atol=atol),
        compton_heating_parity_ready=_within(htcomp, reference.htcomp, rtol=rtol, atol=atol),
        compton_cooling_parity_ready=_within(clcomp, reference.clcomp, rtol=rtol, atol=atol),
        comp2_translated=True,
        cmpfnc_table_loaded=bool(table.loaded),
        continuum_grid_parity_ready=grid_ready,
        diagnostics={
            "rtol": float(rtol),
            "atol": float(atol),
            "reference_summary_path": reference.summary_path,
            "reference_grid_path": reference.grid_path,
            "coheat_source_path": table.source_path,
            "coheat_source_sha256": table.source_sha256,
            "python_htcomp": htcomp,
            "python_clcomp": clcomp,
        },
    )


def write_comp2_parity_products(
    parity: Comp2ParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.39",
) -> Dict[str, Path]:
    """Write bounded Compton parity JSON, Markdown, and continuum CSV."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "port_version": port_version,
        "calc_hmc_all_call_id": parity.call_id,
        "comp2_translated": parity.comp2_translated,
        "cmpfnc_table_loaded": parity.cmpfnc_table_loaded,
        "continuum_grid_parity_ready": parity.continuum_grid_parity_ready,
        "cmp1_parity_ready": parity.cmp1_parity_ready,
        "cmp2_parity_ready": parity.cmp2_parity_ready,
        "compton_heating_coefficient_parity_ready": parity.compton_heating_parity_ready,
        "compton_cooling_coefficient_parity_ready": parity.compton_cooling_parity_ready,
        "comp2_parity_ready": parity.ready,
        "python_cmp1": parity.python.cmp1,
        "xstar_cmp1": parity.reference.cmp1,
        "cmp1_absolute_difference": parity.cmp1_absolute_difference,
        "cmp1_relative_difference": parity.cmp1_relative_difference,
        "python_cmp2": parity.python.cmp2,
        "xstar_cmp2": parity.reference.cmp2,
        "cmp2_absolute_difference": parity.cmp2_absolute_difference,
        "cmp2_relative_difference": parity.cmp2_relative_difference,
        "python_htcomp": parity.diagnostics["python_htcomp"],
        "xstar_htcomp": parity.reference.htcomp,
        "htcomp_absolute_difference": parity.htcomp_absolute_difference,
        "htcomp_relative_difference": parity.htcomp_relative_difference,
        "python_clcomp": parity.diagnostics["python_clcomp"],
        "xstar_clcomp": parity.reference.clcomp,
        "clcomp_absolute_difference": parity.clcomp_absolute_difference,
        "clcomp_relative_difference": parity.clcomp_relative_difference,
        "temperature_t4": parity.reference.temperature_t4,
        "ekt_ev": parity.python.ekt_ev,
        "ncn2": parity.reference.ncn2,
        "coheat_source_path": parity.python.table_source_path,
        "coheat_source_sha256": parity.python.table_source_sha256,
        "diagnostics": dict(parity.diagnostics),
    }
    json_path = out / "xstar_calc_hmc_all_comp2_parity_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "xstar_calc_hmc_all_comp2_parity_summary.md"
    md_path.write_text(
        "# XSTAR `comp2` parity\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items() if key != "diagnostics")
        + "\n",
        encoding="utf-8",
    )
    csv_path = out / "xstar_calc_hmc_all_comp2_continuum.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["grid_index", "epi_eV", "bremsa"])
        for index, (energy, flux) in enumerate(
            zip(parity.reference.epi_eV, parity.reference.bremsa), start=1
        ):
            writer.writerow([index, f"{energy:.17e}", f"{flux:.17e}"])
    return {"json": json_path, "markdown": md_path, "continuum_csv": csv_path}


__all__ = [
    "XSTAR_COMPTON_NCOMP",
    "XSTAR_COMPTON_EMC2_EV",
    "XSTAR_COMPTON_KT_EV_PER_T4",
    "XSTAR_THOMSON_CROSS_SECTION_CM2",
    "XSTAR_ERG_PER_EV",
    "ComptonPortError",
    "ComptonTableState",
    "CmpFncResult",
    "Comp2Result",
    "Comp2Context",
    "Comp2ProbeReference",
    "Comp2ParityResult",
    "packaged_coheat_path",
    "resolve_coheat_path",
    "load_compton_table",
    "hunt3_one_based",
    "cmpfnc",
    "comp2",
    "comp2_continuum_result",
    "load_comp2_probe_reference",
    "compare_comp2_probe",
    "write_comp2_parity_products",
]
