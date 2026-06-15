"""Source-faithful translation of XSTAR's ``freef.f90`` subsystem.

The bounded source path is::

    calc_hmc_all.f90 -> freef.f90

``freef`` computes a unity-Gaunt-factor free--free opacity increment, adds it
in place to the incoming continuum opacity array, and integrates the absorbed
continuum into ``htfreef`` using the original source-order trapezoid rule.
The incoming opacity is explicit state: the translation never assumes that it
is zero because the Fortran routine mutates its caller-owned workspace.
"""
from __future__ import annotations

from .constants import LEGACY_BOLTZMANN_EV_PER_T4

from dataclasses import dataclass, field
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

import numpy as np

from .fortran_numbers import parse_fortran_float


# Default-real literals in freef.f90 are rounded to binary32 before assignment
# to REAL(8).  Preserve that source behavior deliberately.
XSTAR_FREEF_CC = float(np.float32(2.614e-37))
XSTAR_FREEF_KT_EV_PER_T4 = float(np.float32(LEGACY_BOLTZMANN_EV_PER_T4))
XSTAR_FREEF_ION_Z2_FACTOR = float(np.float32(1.4))
XSTAR_FREEF_GAMMA_FACTOR = float(np.float32(0.158))
XSTAR_FREEF_GAUNT_FACTOR = 1.0
XSTAR_ERG_PER_EV = float(np.float32(1.602176634e-12))


class FreeFreePortError(RuntimeError):
    """Raised when the translated ``freef`` subsystem cannot execute."""


@dataclass(frozen=True)
class FreeFreeContext:
    """Caller-owned continuum arrays entering XSTAR ``freef``."""

    epi_eV: np.ndarray
    bremsa: np.ndarray
    opakc_before_cm_inv: np.ndarray
    ncn2: Optional[int] = None
    source: str = "xstar_freef_same_call_probe"

    def validate(self) -> None:
        epi = np.asarray(self.epi_eV, dtype=float).reshape(-1)
        brem = np.asarray(self.bremsa, dtype=float).reshape(-1)
        opac = np.asarray(self.opakc_before_cm_inv, dtype=float).reshape(-1)
        n = epi.size if self.ncn2 is None else int(self.ncn2)
        if n < 1:
            raise FreeFreePortError("freef requires at least one continuum bin")
        if epi.size < n or brem.size < n or opac.size < n:
            raise FreeFreePortError(
                f"freef arrays shorter than ncn2={n}: epi={epi.size}, "
                f"bremsa={brem.size}, opakc={opac.size}"
            )
        if not np.all(np.isfinite(epi[:n])):
            raise FreeFreePortError("freef energy grid contains non-finite values")
        if not np.all(np.isfinite(brem[:n])) or not np.all(np.isfinite(opac[:n])):
            raise FreeFreePortError("freef continuum state contains non-finite values")
        if np.any(epi[:n] <= 0.0):
            raise FreeFreePortError("freef photon energies must be positive")
        if n > 1 and np.any(np.diff(epi[:n]) <= 0.0):
            raise FreeFreePortError("freef photon-energy grid must be strictly increasing")


@dataclass(frozen=True)
class FreeFreeResult:
    """Complete result of XSTAR ``freef.f90``."""

    temperature_t4: float
    ekt_ev: float
    t6: float
    hydrogen_density_cm3: float
    electron_fraction_xee: float
    electron_density_cm3: float
    enz2_cm3: float
    cc: float
    ncn2: int
    epi_eV: np.ndarray
    bremsa: np.ndarray
    dimensionless_energy: np.ndarray
    gamma: np.ndarray
    gaunt_factor: np.ndarray
    stimulated_factor: np.ndarray
    opacity_increment_cm_inv: np.ndarray
    opakc_before_cm_inv: np.ndarray
    opakc_after_cm_inv: np.ndarray
    cumulative_htfreef_erg_cm3_s: np.ndarray
    htfreef_erg_cm3_s: float
    source_file: str = "xstar/xstarlib/src/freef.f90"


@dataclass(frozen=True)
class FreeFreeProbeReference:
    """Exact same-call XSTAR state captured immediately around ``freef``."""

    call_id: int
    ncn2: int
    temperature_t4: float
    electron_fraction_xee: float
    hydrogen_density_cm3: float
    ekt_ev: float
    t6: float
    electron_density_cm3: float
    enz2_cm3: float
    cc: float
    htfreef_erg_cm3_s: float
    epi_eV: np.ndarray
    bremsa: np.ndarray
    opakc_before_cm_inv: np.ndarray
    opacity_increment_cm_inv: np.ndarray
    opakc_after_cm_inv: np.ndarray
    cumulative_htfreef_erg_cm3_s: np.ndarray
    summary_path: str
    grid_path: str


@dataclass(frozen=True)
class FreeFreeParityResult:
    """Bounded v0.4.40 XSTAR/Python ``freef`` comparison."""

    call_id: int
    python: FreeFreeResult
    reference: FreeFreeProbeReference
    continuum_grid_parity_ready: bool
    free_free_opacity_increment_parity_ready: bool
    free_free_opacity_mutation_parity_ready: bool
    htfreef_parity_ready: bool
    freef_translated: bool
    gaunt_factor_mode_unity: bool
    max_opacity_increment_absolute_difference: float
    max_opacity_increment_relative_difference: float
    max_opacity_after_absolute_difference: float
    max_opacity_after_relative_difference: float
    htfreef_absolute_difference: float
    htfreef_relative_difference: float
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return bool(
            self.freef_translated
            and self.gaunt_factor_mode_unity
            and self.continuum_grid_parity_ready
            and self.free_free_opacity_increment_parity_ready
            and self.free_free_opacity_mutation_parity_ready
            and self.htfreef_parity_ready
        )


def _relative_difference(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray:
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    return np.abs(aa - bb) / np.maximum(np.maximum(np.abs(aa), np.abs(bb)), 1.0e-300)


def freef(
    epi_eV: Sequence[float],
    bremsa: Sequence[float],
    opakc_before_cm_inv: Sequence[float],
    *,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    ncn2: Optional[int] = None,
) -> FreeFreeResult:
    """Translate XSTAR ``freef.f90`` with exact source-order accumulation."""
    context = FreeFreeContext(
        epi_eV=np.asarray(epi_eV, dtype=float),
        bremsa=np.asarray(bremsa, dtype=float),
        opakc_before_cm_inv=np.asarray(opakc_before_cm_inv, dtype=float),
        ncn2=ncn2,
    )
    context.validate()
    if not math.isfinite(float(temperature_k)) or float(temperature_k) <= 0.0:
        raise FreeFreePortError("temperature_k must be finite and positive")
    if not math.isfinite(float(hydrogen_density_cm3)) or float(hydrogen_density_cm3) < 0.0:
        raise FreeFreePortError("hydrogen_density_cm3 must be finite and nonnegative")
    if not math.isfinite(float(electron_fraction_xee)) or float(electron_fraction_xee) < 0.0:
        raise FreeFreePortError("electron_fraction_xee must be finite and nonnegative")

    epi_all = np.asarray(context.epi_eV, dtype=float).reshape(-1)
    brem_all = np.asarray(context.bremsa, dtype=float).reshape(-1)
    before_all = np.asarray(context.opakc_before_cm_inv, dtype=float).reshape(-1)
    n = epi_all.size if context.ncn2 is None else int(context.ncn2)
    epi = epi_all[:n].copy()
    brem = brem_all[:n].copy()
    before = before_all[:n].copy()

    t4 = float(temperature_k) / 1.0e4
    ekt = t4 * XSTAR_FREEF_KT_EV_PER_T4
    t6 = t4 / 100.0
    xnx = float(hydrogen_density_cm3) * float(electron_fraction_xee)
    enz2 = XSTAR_FREEF_ION_Z2_FACTOR * xnx
    sqrt_t4 = math.sqrt(t4)

    temp = np.empty(n, dtype=float)
    gam = np.empty(n, dtype=float)
    gau = np.ones(n, dtype=float)
    stimulated = np.empty(n, dtype=float)
    increment = np.empty(n, dtype=float)
    after = before.copy()
    cumulative = np.zeros(n, dtype=float)

    htfreef = 0.0
    opaff_previous = 0.0
    for kk in range(n):
        temp_kk = float(epi[kk]) / ekt
        gam_kk = XSTAR_FREEF_GAMMA_FACTOR / t6
        stimulated_kk = 1.0 - math.exp(-temp_kk)
        opaff = (
            XSTAR_FREEF_CC
            * xnx
            * enz2
            * 1.0
            / sqrt_t4
            / float(epi[kk]) ** 3.0
            * stimulated_kk
        )
        if kk > 0:
            htfreef += (
                float(brem[kk]) * opaff
                + float(brem[kk - 1]) * opaff_previous
            ) * XSTAR_ERG_PER_EV * (float(epi[kk]) - float(epi[kk - 1])) / 2.0
        temp[kk] = temp_kk
        gam[kk] = gam_kk
        stimulated[kk] = stimulated_kk
        increment[kk] = opaff
        after[kk] = before[kk] + opaff
        cumulative[kk] = htfreef
        opaff_previous = opaff

    return FreeFreeResult(
        temperature_t4=t4,
        ekt_ev=ekt,
        t6=t6,
        hydrogen_density_cm3=float(hydrogen_density_cm3),
        electron_fraction_xee=float(electron_fraction_xee),
        electron_density_cm3=xnx,
        enz2_cm3=enz2,
        cc=XSTAR_FREEF_CC,
        ncn2=n,
        epi_eV=epi,
        bremsa=brem,
        dimensionless_energy=temp,
        gamma=gam,
        gaunt_factor=gau,
        stimulated_factor=stimulated,
        opacity_increment_cm_inv=increment,
        opakc_before_cm_inv=before,
        opakc_after_cm_inv=after,
        cumulative_htfreef_erg_cm3_s=cumulative,
        htfreef_erg_cm3_s=float(htfreef),
    )


def freef_continuum_result(
    context: FreeFreeContext,
    *,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
) -> tuple[FreeFreeResult, Dict[str, Any]]:
    """Execute ``freef`` in the translated ``calc_hmc_all`` source slot."""
    result = freef(
        context.epi_eV,
        context.bremsa,
        context.opakc_before_cm_inv,
        temperature_k=temperature_k,
        hydrogen_density_cm3=hydrogen_density_cm3,
        electron_fraction_xee=electron_fraction_xee,
        ncn2=context.ncn2,
    )
    return result, {
        "freef_translated": True,
        "freef_source_file": result.source_file,
        "freef_context_source": context.source,
        "gaunt_factor_mode": "source_unity",
        "gaunt_factor_mode_unity": True,
        "free_free_opacity_added_in_place": True,
        "htfreef": result.htfreef_erg_cm3_s,
        "bremem_deferred": True,
        "heatf_accumulation_deferred": True,
    }


def load_freef_probe_reference(
    probe_dir: str | Path,
    *,
    call_id: int = 73,
) -> FreeFreeProbeReference:
    """Read the v0.4.40 pre/post-``freef`` same-call probe products."""
    root = Path(probe_dir)
    summary_path = root / "xstar_calc_hmc_all_freef_summary_probe.csv"
    grid_path = root / "xstar_calc_hmc_all_freef_grid_probe.csv"
    if not summary_path.is_file() or not grid_path.is_file():
        raise FileNotFoundError(
            f"missing freef probe products in {root}: expected {summary_path.name} and {grid_path.name}"
        )

    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if int(row["calc_hmc_all_call_id"]) == int(call_id)]
    if len(rows) != 1:
        raise FreeFreePortError(
            f"expected one freef summary row for call {call_id}, found {len(rows)}"
        )
    row = rows[0]
    n = int(row["ncn2"])

    with grid_path.open(newline="", encoding="utf-8") as handle:
        grows = [r for r in csv.DictReader(handle) if int(r["calc_hmc_all_call_id"]) == int(call_id)]
    grows.sort(key=lambda item: int(item["grid_index"]))
    if len(grows) != n or [int(r["grid_index"]) for r in grows] != list(range(1, n + 1)):
        raise FreeFreePortError(
            f"incomplete freef grid for call {call_id}: expected {n} rows, found {len(grows)}"
        )

    array = lambda key: np.asarray([parse_fortran_float(r[key]) for r in grows], dtype=float)
    return FreeFreeProbeReference(
        call_id=int(call_id),
        ncn2=n,
        temperature_t4=parse_fortran_float(row["temperature_t4"]),
        electron_fraction_xee=parse_fortran_float(row["electron_fraction_xee"]),
        hydrogen_density_cm3=parse_fortran_float(row["hydrogen_density_cm3"]),
        ekt_ev=parse_fortran_float(row["ekt_ev"]),
        t6=parse_fortran_float(row["t6"]),
        electron_density_cm3=parse_fortran_float(row["electron_density_cm3"]),
        enz2_cm3=parse_fortran_float(row["enz2_cm3"]),
        cc=parse_fortran_float(row["cc"]),
        htfreef_erg_cm3_s=parse_fortran_float(row["htfreef"]),
        epi_eV=array("epi_eV"),
        bremsa=array("bremsa"),
        opakc_before_cm_inv=array("opakc_before"),
        opacity_increment_cm_inv=array("opaff"),
        opakc_after_cm_inv=array("opakc_after"),
        cumulative_htfreef_erg_cm3_s=array("cumulative_htfreef"),
        summary_path=str(summary_path),
        grid_path=str(grid_path),
    )


def compare_freef_probe(
    reference: FreeFreeProbeReference,
    *,
    rtol: float = 5.0e-12,
    atol: float = 1.0e-40,
) -> FreeFreeParityResult:
    """Compare translated ``freef`` with the exact same-call XSTAR probe."""
    result = freef(
        reference.epi_eV,
        reference.bremsa,
        reference.opakc_before_cm_inv,
        temperature_k=reference.temperature_t4 * 1.0e4,
        hydrogen_density_cm3=reference.hydrogen_density_cm3,
        electron_fraction_xee=reference.electron_fraction_xee,
        ncn2=reference.ncn2,
    )
    grid_ready = bool(
        result.ncn2 == reference.ncn2
        and np.array_equal(result.epi_eV, reference.epi_eV)
        and np.array_equal(result.bremsa, reference.bremsa)
        and np.array_equal(result.opakc_before_cm_inv, reference.opakc_before_cm_inv)
    )
    inc_abs = np.abs(result.opacity_increment_cm_inv - reference.opacity_increment_cm_inv)
    inc_rel = _relative_difference(result.opacity_increment_cm_inv, reference.opacity_increment_cm_inv)
    after_abs = np.abs(result.opakc_after_cm_inv - reference.opakc_after_cm_inv)
    after_rel = _relative_difference(result.opakc_after_cm_inv, reference.opakc_after_cm_inv)
    ht_abs = abs(result.htfreef_erg_cm3_s - reference.htfreef_erg_cm3_s)
    ht_rel = float(_relative_difference(result.htfreef_erg_cm3_s, reference.htfreef_erg_cm3_s))
    increment_ready = bool(np.allclose(
        result.opacity_increment_cm_inv,
        reference.opacity_increment_cm_inv,
        rtol=rtol,
        atol=atol,
    ))
    mutation_ready = bool(np.allclose(
        result.opakc_after_cm_inv,
        reference.opakc_after_cm_inv,
        rtol=rtol,
        atol=atol,
    ))
    ht_ready = bool(math.isclose(
        result.htfreef_erg_cm3_s,
        reference.htfreef_erg_cm3_s,
        rel_tol=rtol,
        abs_tol=atol,
    ))
    return FreeFreeParityResult(
        call_id=reference.call_id,
        python=result,
        reference=reference,
        continuum_grid_parity_ready=grid_ready,
        free_free_opacity_increment_parity_ready=increment_ready,
        free_free_opacity_mutation_parity_ready=mutation_ready,
        htfreef_parity_ready=ht_ready,
        freef_translated=True,
        gaunt_factor_mode_unity=bool(np.all(result.gaunt_factor == 1.0)),
        max_opacity_increment_absolute_difference=float(np.max(inc_abs)) if inc_abs.size else 0.0,
        max_opacity_increment_relative_difference=float(np.max(inc_rel)) if inc_rel.size else 0.0,
        max_opacity_after_absolute_difference=float(np.max(after_abs)) if after_abs.size else 0.0,
        max_opacity_after_relative_difference=float(np.max(after_rel)) if after_rel.size else 0.0,
        htfreef_absolute_difference=float(ht_abs),
        htfreef_relative_difference=float(ht_rel),
        diagnostics={
            "rtol": float(rtol),
            "atol": float(atol),
            "reference_summary_path": reference.summary_path,
            "reference_grid_path": reference.grid_path,
            "source_constant_cc": XSTAR_FREEF_CC,
            "source_constant_ergsev": XSTAR_ERG_PER_EV,
            "bremem_deferred": True,
            "heatf_deferred": True,
        },
    )


def write_freef_parity_products(
    parity: FreeFreeParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.40",
) -> Dict[str, Path]:
    """Write scalar and per-bin ``freef`` parity products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    py = parity.python
    ref = parity.reference
    csv_path = out / "xstar_calc_hmc_all_freef_continuum.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "grid_index", "epi_eV", "bremsa", "opakc_before",
            "python_opaff", "xstar_opaff", "opaff_absolute_difference",
            "opaff_relative_difference", "python_opakc_after", "xstar_opakc_after",
            "opakc_after_absolute_difference", "opakc_after_relative_difference",
            "dimensionless_energy", "gamma", "gaunt_factor", "stimulated_factor",
            "python_cumulative_htfreef", "xstar_cumulative_htfreef",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for idx in range(py.ncn2):
            writer.writerow({
                "grid_index": idx + 1,
                "epi_eV": py.epi_eV[idx],
                "bremsa": py.bremsa[idx],
                "opakc_before": py.opakc_before_cm_inv[idx],
                "python_opaff": py.opacity_increment_cm_inv[idx],
                "xstar_opaff": ref.opacity_increment_cm_inv[idx],
                "opaff_absolute_difference": abs(py.opacity_increment_cm_inv[idx] - ref.opacity_increment_cm_inv[idx]),
                "opaff_relative_difference": float(_relative_difference(py.opacity_increment_cm_inv[idx], ref.opacity_increment_cm_inv[idx])),
                "python_opakc_after": py.opakc_after_cm_inv[idx],
                "xstar_opakc_after": ref.opakc_after_cm_inv[idx],
                "opakc_after_absolute_difference": abs(py.opakc_after_cm_inv[idx] - ref.opakc_after_cm_inv[idx]),
                "opakc_after_relative_difference": float(_relative_difference(py.opakc_after_cm_inv[idx], ref.opakc_after_cm_inv[idx])),
                "dimensionless_energy": py.dimensionless_energy[idx],
                "gamma": py.gamma[idx],
                "gaunt_factor": py.gaunt_factor[idx],
                "stimulated_factor": py.stimulated_factor[idx],
                "python_cumulative_htfreef": py.cumulative_htfreef_erg_cm3_s[idx],
                "xstar_cumulative_htfreef": ref.cumulative_htfreef_erg_cm3_s[idx],
            })

    summary = {
        "port_version": port_version,
        "calc_hmc_all_call_id": parity.call_id,
        "freef_translated": parity.freef_translated,
        "gaunt_factor_mode_unity": parity.gaunt_factor_mode_unity,
        "continuum_grid_parity_ready": parity.continuum_grid_parity_ready,
        "free_free_opacity_increment_parity_ready": parity.free_free_opacity_increment_parity_ready,
        "free_free_opacity_mutation_parity_ready": parity.free_free_opacity_mutation_parity_ready,
        "htfreef_parity_ready": parity.htfreef_parity_ready,
        "freef_parity_ready": parity.ready,
        "ncn2": py.ncn2,
        "temperature_t4": py.temperature_t4,
        "python_htfreef": py.htfreef_erg_cm3_s,
        "xstar_htfreef": ref.htfreef_erg_cm3_s,
        "htfreef_absolute_difference": parity.htfreef_absolute_difference,
        "htfreef_relative_difference": parity.htfreef_relative_difference,
        "max_opacity_increment_absolute_difference": parity.max_opacity_increment_absolute_difference,
        "max_opacity_increment_relative_difference": parity.max_opacity_increment_relative_difference,
        "max_opacity_after_absolute_difference": parity.max_opacity_after_absolute_difference,
        "max_opacity_after_relative_difference": parity.max_opacity_after_relative_difference,
        "diagnostics": dict(parity.diagnostics),
    }
    json_path = out / "xstar_calc_hmc_all_freef_parity_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path = out / "xstar_calc_hmc_all_freef_parity_summary.md"
    md_path.write_text(
        "# xstar-atomic v0.4.40 freef parity\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items() if key != "diagnostics")
        + "\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": md_path, "continuum_csv": csv_path}


__all__ = [
    "XSTAR_FREEF_CC", "XSTAR_FREEF_KT_EV_PER_T4", "XSTAR_FREEF_ION_Z2_FACTOR",
    "XSTAR_FREEF_GAMMA_FACTOR", "XSTAR_FREEF_GAUNT_FACTOR", "FreeFreePortError",
    "FreeFreeContext", "FreeFreeResult", "FreeFreeProbeReference", "FreeFreeParityResult",
    "freef", "freef_continuum_result", "load_freef_probe_reference", "compare_freef_probe",
    "write_freef_parity_products",
]
