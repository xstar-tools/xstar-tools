"""Source-faithful translation of XSTAR's ``heatf.f90`` subsystem.

The bounded source path is::

    calc_hmc_all.f90 -> heatf.f90

``heatf`` is the first local-zone continuum routine that mutates the primary
and secondary heating/cooling totals.  It integrates the already translated
``bremem`` emissivity, converts the ``comp2`` coefficients to volumetric
Compton rates, adds ``freef`` heating, and evaluates XSTAR's normalized thermal
residual ``hmctot``.  The implementation preserves source expression order and
Fortran default-real literal rounding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np

from .fortran_numbers import parse_fortran_float


# These literals are default REAL in heatf.f90 and constants.f90 and therefore
# round to binary32 before promotion to REAL(8).
XSTAR_HEATF_KT_EV_PER_T4 = float(np.float32(0.861707))
XSTAR_HEATF_ERG_PER_EV = float(np.float32(1.602176634e-12))
XSTAR_HEATF_RESIDUAL_FLOOR = float(np.float32(1.0e-37))
XSTAR_HEATF_RESIDUAL_FACTOR = float(np.float32(2.0))


class HeatFPortError(RuntimeError):
    """Raised when the translated ``heatf`` subsystem cannot execute."""


@dataclass(frozen=True)
class HeatFContext:
    """Exact caller state entering XSTAR ``heatf``."""

    epi_eV: np.ndarray
    brcems: np.ndarray
    htfreef_erg_cm3_s: float
    cmp1: float
    cmp2: float
    httot_before: float
    cltot_before: float
    httot2_before: float
    cltot2_before: float
    radius_cm: float = 0.0
    zone_thickness_cm: float = 0.0
    ncn2: Optional[int] = None
    source: str = "xstar_heatf_same_call_probe"

    def validate(self) -> None:
        epi = np.asarray(self.epi_eV, dtype=float).reshape(-1)
        brc = np.asarray(self.brcems, dtype=float).reshape(-1)
        n = epi.size if self.ncn2 is None else int(self.ncn2)
        if n < 1:
            raise HeatFPortError("heatf requires at least one continuum bin")
        if epi.size < n or brc.size < n:
            raise HeatFPortError(
                f"heatf arrays shorter than ncn2={n}: epi={epi.size}, brcems={brc.size}"
            )
        if not np.all(np.isfinite(epi[:n])) or not np.all(np.isfinite(brc[:n])):
            raise HeatFPortError("heatf continuum arrays contain non-finite values")
        if n > 1 and np.any(np.diff(epi[:n]) <= 0.0):
            raise HeatFPortError("heatf photon-energy grid must be strictly increasing")
        scalars = (
            self.htfreef_erg_cm3_s,
            self.cmp1,
            self.cmp2,
            self.httot_before,
            self.cltot_before,
            self.httot2_before,
            self.cltot2_before,
            self.radius_cm,
            self.zone_thickness_cm,
        )
        if not all(math.isfinite(float(value)) for value in scalars):
            raise HeatFPortError("heatf scalar state contains non-finite values")


@dataclass(frozen=True)
class HeatFResult:
    """Complete source-order output of XSTAR ``heatf.f90``."""

    temperature_t4: float
    radius_cm: float
    zone_thickness_cm: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    electron_density_cm3: float
    ekt_ev: float
    ncn2: int
    epi_eV: np.ndarray
    brcems: np.ndarray
    previous_brcems: np.ndarray
    cumulative_clbrems_erg_cm3_s: np.ndarray
    htfreef_erg_cm3_s: float
    cmp1: float
    cmp2: float
    htcomp_erg_cm3_s: float
    clcomp_erg_cm3_s: float
    clbrems_erg_cm3_s: float
    httot_before: float
    cltot_before: float
    httot2_before: float
    cltot2_before: float
    httot_after: float
    cltot_after: float
    httot2_after: float
    cltot2_after: float
    hmctot: float
    source_file: str = "xstar/xstarlib/src/heatf.f90"


@dataclass(frozen=True)
class HeatFProbeReference:
    """Exact same-call XSTAR state captured immediately around ``heatf``."""

    call_id: int
    ncn2: int
    temperature_t4: float
    radius_cm: float
    zone_thickness_cm: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    electron_density_cm3: float
    ekt_ev: float
    htfreef_erg_cm3_s: float
    cmp1: float
    cmp2: float
    httot_before: float
    cltot_before: float
    httot2_before: float
    cltot2_before: float
    htcomp_erg_cm3_s: float
    clcomp_erg_cm3_s: float
    clbrems_erg_cm3_s: float
    httot_after: float
    cltot_after: float
    httot2_after: float
    cltot2_after: float
    hmctot: float
    epi_eV: np.ndarray
    brcems: np.ndarray
    previous_brcems: np.ndarray
    cumulative_clbrems_erg_cm3_s: np.ndarray
    summary_path: str
    grid_path: str


@dataclass(frozen=True)
class HeatFParityResult:
    """Bounded v0.4.42 XSTAR/Python ``heatf`` comparison."""

    call_id: int
    python: HeatFResult
    reference: HeatFProbeReference
    continuum_grid_parity_ready: bool
    bremsstrahlung_cooling_integral_parity_ready: bool
    compton_heating_accumulation_parity_ready: bool
    compton_cooling_accumulation_parity_ready: bool
    free_free_heating_accumulation_parity_ready: bool
    bremsstrahlung_cooling_accumulation_parity_ready: bool
    primary_heating_cooling_totals_parity_ready: bool
    secondary_heating_cooling_totals_parity_ready: bool
    hmctot_parity_ready: bool
    heatf_translated: bool
    max_cumulative_clbrems_absolute_difference: float
    max_cumulative_clbrems_relative_difference: float
    max_scalar_absolute_difference: float
    max_scalar_relative_difference: float
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(
            self.heatf_translated
            and self.continuum_grid_parity_ready
            and self.bremsstrahlung_cooling_integral_parity_ready
            and self.compton_heating_accumulation_parity_ready
            and self.compton_cooling_accumulation_parity_ready
            and self.free_free_heating_accumulation_parity_ready
            and self.bremsstrahlung_cooling_accumulation_parity_ready
            and self.primary_heating_cooling_totals_parity_ready
            and self.secondary_heating_cooling_totals_parity_ready
            and self.hmctot_parity_ready
        )


def _relative_difference(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray:
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    return np.abs(aa - bb) / np.maximum(
        np.maximum(np.abs(aa), np.abs(bb)), 1.0e-300
    )


def heatf(
    epi_eV: Sequence[float],
    brcems: Sequence[float],
    *,
    temperature_k: float,
    radius_cm: float,
    zone_thickness_cm: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    htfreef_erg_cm3_s: float,
    cmp1: float,
    cmp2: float,
    httot_before: float,
    cltot_before: float,
    httot2_before: float,
    cltot2_before: float,
    ncn2: Optional[int] = None,
) -> HeatFResult:
    """Translate XSTAR ``heatf.f90`` in literal source order."""
    context = HeatFContext(
        epi_eV=np.asarray(epi_eV, dtype=float),
        brcems=np.asarray(brcems, dtype=float),
        htfreef_erg_cm3_s=float(htfreef_erg_cm3_s),
        cmp1=float(cmp1),
        cmp2=float(cmp2),
        httot_before=float(httot_before),
        cltot_before=float(cltot_before),
        httot2_before=float(httot2_before),
        cltot2_before=float(cltot2_before),
        radius_cm=float(radius_cm),
        zone_thickness_cm=float(zone_thickness_cm),
        ncn2=ncn2,
    )
    context.validate()
    if not math.isfinite(float(temperature_k)) or float(temperature_k) <= 0.0:
        raise HeatFPortError("temperature_k must be finite and positive")
    if (
        not math.isfinite(float(hydrogen_density_cm3))
        or float(hydrogen_density_cm3) < 0.0
    ):
        raise HeatFPortError("hydrogen_density_cm3 must be finite and nonnegative")
    if (
        not math.isfinite(float(electron_fraction_xee))
        or float(electron_fraction_xee) < 0.0
    ):
        raise HeatFPortError("electron_fraction_xee must be finite and nonnegative")

    epi_all = np.asarray(context.epi_eV, dtype=float).reshape(-1)
    brc_all = np.asarray(context.brcems, dtype=float).reshape(-1)
    n = epi_all.size if context.ncn2 is None else int(context.ncn2)
    epi = epi_all[:n].copy()
    brc = brc_all[:n].copy()

    # Source loop: clbrems=0.; tmp2=0.; then source-order trapezoids.
    clbrems = 0.0
    tmp2 = 0.0
    previous = np.empty(n, dtype=float)
    cumulative = np.empty(n, dtype=float)
    for kl in range(n):
        tmp2o = tmp2
        tmp2 = float(brc[kl])
        previous[kl] = tmp2o
        if kl >= 1:
            clbrems = (
                clbrems
                + (tmp2 + tmp2o)
                * (float(epi[kl]) - float(epi[kl - 1]))
                * XSTAR_HEATF_ERG_PER_EV
                / float(np.float32(2.0))
            )
        cumulative[kl] = clbrems

    t4 = float(temperature_k) / 1.0e4
    xnx = float(hydrogen_density_cm3) * float(electron_fraction_xee)
    ekt = t4 * XSTAR_HEATF_KT_EV_PER_T4
    htcomp = float(cmp1) * xnx * XSTAR_HEATF_ERG_PER_EV
    clcomp = ekt * float(cmp2) * xnx * XSTAR_HEATF_ERG_PER_EV

    # Preserve the exact left-to-right source accumulation sequence.
    httot = (float(httot_before) + htcomp) + float(htfreef_erg_cm3_s)
    cltot = (float(cltot_before) + clcomp) + clbrems
    httot2 = (float(httot2_before) + htcomp) + float(htfreef_erg_cm3_s)
    cltot2 = (float(cltot2_before) + clcomp) + clbrems
    hmctot = (
        XSTAR_HEATF_RESIDUAL_FACTOR
        * (httot - cltot)
        / ((XSTAR_HEATF_RESIDUAL_FLOOR + httot) + cltot)
    )

    return HeatFResult(
        temperature_t4=t4,
        radius_cm=float(radius_cm),
        zone_thickness_cm=float(zone_thickness_cm),
        electron_fraction_xee=float(electron_fraction_xee),
        hydrogen_density_cm3=float(hydrogen_density_cm3),
        electron_density_cm3=xnx,
        ekt_ev=ekt,
        ncn2=n,
        epi_eV=epi,
        brcems=brc,
        previous_brcems=previous,
        cumulative_clbrems_erg_cm3_s=cumulative,
        htfreef_erg_cm3_s=float(htfreef_erg_cm3_s),
        cmp1=float(cmp1),
        cmp2=float(cmp2),
        htcomp_erg_cm3_s=htcomp,
        clcomp_erg_cm3_s=clcomp,
        clbrems_erg_cm3_s=clbrems,
        httot_before=float(httot_before),
        cltot_before=float(cltot_before),
        httot2_before=float(httot2_before),
        cltot2_before=float(cltot2_before),
        httot_after=httot,
        cltot_after=cltot,
        httot2_after=httot2,
        cltot2_after=cltot2,
        hmctot=hmctot,
    )


def heatf_continuum_result(
    context: HeatFContext,
    *,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
) -> tuple[HeatFResult, Dict[str, Any]]:
    """Execute ``heatf`` in the translated ``calc_hmc_all`` source slot."""
    result = heatf(
        context.epi_eV,
        context.brcems,
        temperature_k=temperature_k,
        radius_cm=context.radius_cm,
        zone_thickness_cm=context.zone_thickness_cm,
        hydrogen_density_cm3=hydrogen_density_cm3,
        electron_fraction_xee=electron_fraction_xee,
        htfreef_erg_cm3_s=context.htfreef_erg_cm3_s,
        cmp1=context.cmp1,
        cmp2=context.cmp2,
        httot_before=context.httot_before,
        cltot_before=context.cltot_before,
        httot2_before=context.httot2_before,
        cltot2_before=context.cltot2_before,
        ncn2=context.ncn2,
    )
    return result, {
        "heatf_translated": True,
        "heatf_source_file": result.source_file,
        "heatf_context_source": context.source,
        "heatf_source_order_accumulation": True,
        "heatf_primary_totals_complete": True,
        "heatf_secondary_totals_complete": True,
        "heatf_hmctot_complete": True,
        "heatf_remaining_source_sequence": "",
    }


def load_heatf_probe_reference(
    probe_dir: str | Path,
    *,
    call_id: int = 73,
) -> HeatFProbeReference:
    """Read the v0.4.42 pre/bin/post-``heatf`` same-call probe products."""
    root = Path(probe_dir)
    summary_path = root / "xstar_calc_hmc_all_heatf_summary_probe.csv"
    grid_path = root / "xstar_calc_hmc_all_heatf_grid_probe.csv"
    if not summary_path.is_file() or not grid_path.is_file():
        raise FileNotFoundError(
            f"missing heatf probe products in {root}: expected "
            f"{summary_path.name} and {grid_path.name}"
        )

    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if int(row["calc_hmc_all_call_id"]) == int(call_id)
        ]
    if len(rows) != 1:
        raise HeatFPortError(
            f"expected one heatf summary row for call {call_id}, found {len(rows)}"
        )
    row = rows[0]
    n = int(row["ncn2"])

    with grid_path.open(newline="", encoding="utf-8") as handle:
        grows = [
            item
            for item in csv.DictReader(handle)
            if int(item["calc_hmc_all_call_id"]) == int(call_id)
        ]
    grows.sort(key=lambda item: int(item["grid_index"]))
    if len(grows) != n or [int(item["grid_index"]) for item in grows] != list(
        range(1, n + 1)
    ):
        raise HeatFPortError(
            f"incomplete heatf grid for call {call_id}: expected {n} rows, "
            f"found {len(grows)}"
        )

    def scalar(key: str) -> float:
        return parse_fortran_float(row[key])

    def array(key: str) -> np.ndarray:
        return np.asarray(
            [parse_fortran_float(item[key]) for item in grows], dtype=float
        )

    return HeatFProbeReference(
        call_id=int(call_id),
        ncn2=n,
        temperature_t4=scalar("temperature_t4"),
        radius_cm=scalar("radius_cm"),
        zone_thickness_cm=scalar("zone_thickness_cm"),
        electron_fraction_xee=scalar("electron_fraction_xee"),
        hydrogen_density_cm3=scalar("hydrogen_density_cm3"),
        electron_density_cm3=scalar("electron_density_cm3"),
        ekt_ev=scalar("ekt_ev"),
        htfreef_erg_cm3_s=scalar("htfreef"),
        cmp1=scalar("cmp1"),
        cmp2=scalar("cmp2"),
        httot_before=scalar("httot_before"),
        cltot_before=scalar("cltot_before"),
        httot2_before=scalar("httot2_before"),
        cltot2_before=scalar("cltot2_before"),
        htcomp_erg_cm3_s=scalar("htcomp"),
        clcomp_erg_cm3_s=scalar("clcomp"),
        clbrems_erg_cm3_s=scalar("clbrems"),
        httot_after=scalar("httot_after"),
        cltot_after=scalar("cltot_after"),
        httot2_after=scalar("httot2_after"),
        cltot2_after=scalar("cltot2_after"),
        hmctot=scalar("hmctot"),
        epi_eV=array("epi_eV"),
        brcems=array("brcems"),
        previous_brcems=array("previous_brcems"),
        cumulative_clbrems_erg_cm3_s=array("cumulative_clbrems"),
        summary_path=str(summary_path),
        grid_path=str(grid_path),
    )


def compare_heatf_probe(
    reference: HeatFProbeReference,
    *,
    rtol: float = 5.0e-12,
    atol: float = 1.0e-40,
) -> HeatFParityResult:
    """Compare translated ``heatf`` with the exact same-call XSTAR probe."""
    result = heatf(
        reference.epi_eV,
        reference.brcems,
        temperature_k=reference.temperature_t4 * 1.0e4,
        radius_cm=reference.radius_cm,
        zone_thickness_cm=reference.zone_thickness_cm,
        hydrogen_density_cm3=reference.hydrogen_density_cm3,
        electron_fraction_xee=reference.electron_fraction_xee,
        htfreef_erg_cm3_s=reference.htfreef_erg_cm3_s,
        cmp1=reference.cmp1,
        cmp2=reference.cmp2,
        httot_before=reference.httot_before,
        cltot_before=reference.cltot_before,
        httot2_before=reference.httot2_before,
        cltot2_before=reference.cltot2_before,
        ncn2=reference.ncn2,
    )
    grid_ready = bool(
        result.ncn2 == reference.ncn2
        and np.array_equal(result.epi_eV, reference.epi_eV)
        and np.array_equal(result.brcems, reference.brcems)
    )
    cum_abs = np.abs(
        result.cumulative_clbrems_erg_cm3_s
        - reference.cumulative_clbrems_erg_cm3_s
    )
    cum_rel = _relative_difference(
        result.cumulative_clbrems_erg_cm3_s,
        reference.cumulative_clbrems_erg_cm3_s,
    )
    integral_ready = bool(
        np.allclose(
            result.cumulative_clbrems_erg_cm3_s,
            reference.cumulative_clbrems_erg_cm3_s,
            rtol=rtol,
            atol=atol,
        )
        and math.isclose(
            result.clbrems_erg_cm3_s,
            reference.clbrems_erg_cm3_s,
            rel_tol=rtol,
            abs_tol=atol,
        )
    )

    def close(a: float, b: float) -> bool:
        return math.isclose(float(a), float(b), rel_tol=rtol, abs_tol=atol)

    htcomp_ready = close(result.htcomp_erg_cm3_s, reference.htcomp_erg_cm3_s)
    clcomp_ready = close(result.clcomp_erg_cm3_s, reference.clcomp_erg_cm3_s)
    primary_ready = close(result.httot_after, reference.httot_after) and close(
        result.cltot_after, reference.cltot_after
    )
    secondary_ready = close(result.httot2_after, reference.httot2_after) and close(
        result.cltot2_after, reference.cltot2_after
    )
    # Verify the specific translated source additions, not merely the final sums.
    # Tiny free-free heating can be far below the ulp of the pre-existing
    # total, so validate the literal source-order expression rather than
    # recovering the term by subtracting nearly equal totals.
    freef_ready = close(
        result.httot_after,
        (reference.httot_before + reference.htcomp_erg_cm3_s)
        + reference.htfreef_erg_cm3_s,
    ) and close(
        result.httot2_after,
        (reference.httot2_before + reference.htcomp_erg_cm3_s)
        + reference.htfreef_erg_cm3_s,
    )
    brems_accum_ready = close(
        result.cltot_after,
        (reference.cltot_before + reference.clcomp_erg_cm3_s)
        + reference.clbrems_erg_cm3_s,
    ) and close(
        result.cltot2_after,
        (reference.cltot2_before + reference.clcomp_erg_cm3_s)
        + reference.clbrems_erg_cm3_s,
    )
    hmctot_ready = close(result.hmctot, reference.hmctot)

    scalar_pairs = (
        (result.htcomp_erg_cm3_s, reference.htcomp_erg_cm3_s),
        (result.clcomp_erg_cm3_s, reference.clcomp_erg_cm3_s),
        (result.clbrems_erg_cm3_s, reference.clbrems_erg_cm3_s),
        (result.httot_after, reference.httot_after),
        (result.cltot_after, reference.cltot_after),
        (result.httot2_after, reference.httot2_after),
        (result.cltot2_after, reference.cltot2_after),
        (result.hmctot, reference.hmctot),
    )
    scalar_abs = np.asarray([abs(a - b) for a, b in scalar_pairs], dtype=float)
    scalar_rel = np.asarray(
        [float(_relative_difference(a, b)) for a, b in scalar_pairs], dtype=float
    )
    return HeatFParityResult(
        call_id=reference.call_id,
        python=result,
        reference=reference,
        continuum_grid_parity_ready=grid_ready,
        bremsstrahlung_cooling_integral_parity_ready=integral_ready,
        compton_heating_accumulation_parity_ready=htcomp_ready,
        compton_cooling_accumulation_parity_ready=clcomp_ready,
        free_free_heating_accumulation_parity_ready=freef_ready,
        bremsstrahlung_cooling_accumulation_parity_ready=brems_accum_ready,
        primary_heating_cooling_totals_parity_ready=primary_ready,
        secondary_heating_cooling_totals_parity_ready=secondary_ready,
        hmctot_parity_ready=hmctot_ready,
        heatf_translated=True,
        max_cumulative_clbrems_absolute_difference=(
            float(np.max(cum_abs)) if cum_abs.size else 0.0
        ),
        max_cumulative_clbrems_relative_difference=(
            float(np.max(cum_rel)) if cum_rel.size else 0.0
        ),
        max_scalar_absolute_difference=(
            float(np.max(scalar_abs)) if scalar_abs.size else 0.0
        ),
        max_scalar_relative_difference=(
            float(np.max(scalar_rel)) if scalar_rel.size else 0.0
        ),
        diagnostics={
            "rtol": float(rtol),
            "atol": float(atol),
            "reference_summary_path": reference.summary_path,
            "reference_grid_path": reference.grid_path,
            "source_ergsev": XSTAR_HEATF_ERG_PER_EV,
            "source_residual_floor": XSTAR_HEATF_RESIDUAL_FLOOR,
            "source_order": "clbrems -> htcomp/clcomp -> totals -> hmctot",
        },
    )


def write_heatf_parity_products(
    parity: HeatFParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.42",
) -> Dict[str, Path]:
    """Write scalar and per-bin ``heatf`` parity products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    py = parity.python
    ref = parity.reference
    csv_path = out / "xstar_calc_hmc_all_heatf_continuum.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "grid_index",
            "epi_eV",
            "brcems",
            "previous_brcems",
            "python_cumulative_clbrems",
            "xstar_cumulative_clbrems",
            "absolute_difference",
            "relative_difference",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for idx in range(py.ncn2):
            writer.writerow(
                {
                    "grid_index": idx + 1,
                    "epi_eV": py.epi_eV[idx],
                    "brcems": py.brcems[idx],
                    "previous_brcems": py.previous_brcems[idx],
                    "python_cumulative_clbrems": py.cumulative_clbrems_erg_cm3_s[idx],
                    "xstar_cumulative_clbrems": ref.cumulative_clbrems_erg_cm3_s[idx],
                    "absolute_difference": abs(
                        py.cumulative_clbrems_erg_cm3_s[idx]
                        - ref.cumulative_clbrems_erg_cm3_s[idx]
                    ),
                    "relative_difference": float(
                        _relative_difference(
                            py.cumulative_clbrems_erg_cm3_s[idx],
                            ref.cumulative_clbrems_erg_cm3_s[idx],
                        )
                    ),
                }
            )

    summary = {
        "port_version": port_version,
        "calc_hmc_all_call_id": parity.call_id,
        "heatf_translated": parity.heatf_translated,
        "continuum_grid_parity_ready": parity.continuum_grid_parity_ready,
        "bremsstrahlung_cooling_integral_parity_ready": parity.bremsstrahlung_cooling_integral_parity_ready,
        "compton_heating_accumulation_parity_ready": parity.compton_heating_accumulation_parity_ready,
        "compton_cooling_accumulation_parity_ready": parity.compton_cooling_accumulation_parity_ready,
        "free_free_heating_accumulation_parity_ready": parity.free_free_heating_accumulation_parity_ready,
        "bremsstrahlung_cooling_accumulation_parity_ready": parity.bremsstrahlung_cooling_accumulation_parity_ready,
        "primary_heating_cooling_totals_parity_ready": parity.primary_heating_cooling_totals_parity_ready,
        "secondary_heating_cooling_totals_parity_ready": parity.secondary_heating_cooling_totals_parity_ready,
        "hmctot_parity_ready": parity.hmctot_parity_ready,
        "heatf_parity_ready": parity.ready,
        "ncn2": py.ncn2,
        "temperature_t4": py.temperature_t4,
        "htcomp": py.htcomp_erg_cm3_s,
        "clcomp": py.clcomp_erg_cm3_s,
        "htfreef": py.htfreef_erg_cm3_s,
        "clbrems": py.clbrems_erg_cm3_s,
        "httot_before": py.httot_before,
        "cltot_before": py.cltot_before,
        "httot_after": py.httot_after,
        "cltot_after": py.cltot_after,
        "httot2_after": py.httot2_after,
        "cltot2_after": py.cltot2_after,
        "hmctot": py.hmctot,
        "max_cumulative_clbrems_absolute_difference": parity.max_cumulative_clbrems_absolute_difference,
        "max_cumulative_clbrems_relative_difference": parity.max_cumulative_clbrems_relative_difference,
        "max_scalar_absolute_difference": parity.max_scalar_absolute_difference,
        "max_scalar_relative_difference": parity.max_scalar_relative_difference,
        "diagnostics": dict(parity.diagnostics),
    }
    json_path = out / "xstar_calc_hmc_all_heatf_parity_summary.json"
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_path = out / "xstar_calc_hmc_all_heatf_parity_summary.md"
    md_path.write_text(
        "# xstar-atomic v0.4.42 heatf parity\n\n"
        + "\n".join(
            f"- {key}: `{value}`"
            for key, value in summary.items()
            if key != "diagnostics"
        )
        + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": md_path, "continuum_csv": csv_path}


__all__ = [
    "XSTAR_HEATF_KT_EV_PER_T4",
    "XSTAR_HEATF_ERG_PER_EV",
    "XSTAR_HEATF_RESIDUAL_FLOOR",
    "XSTAR_HEATF_RESIDUAL_FACTOR",
    "HeatFPortError",
    "HeatFContext",
    "HeatFResult",
    "HeatFProbeReference",
    "HeatFParityResult",
    "heatf",
    "heatf_continuum_result",
    "load_heatf_probe_reference",
    "compare_heatf_probe",
    "write_heatf_parity_products",
]
