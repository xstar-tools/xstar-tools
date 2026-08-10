# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: bremem.f90
#   Role: Bremsstrahlung cooling/emission leaf used by calc_hmc_all.
#   Relation: Source-faithful thermal leaf; numerical constants/order remain source-derived.
#   Concordance: THERM-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Source-faithful translation of XSTAR's ``bremem.f90`` subsystem.

The bounded source path is::

    calc_hmc_all.f90 -> bremem.f90

``bremem`` clears the caller-owned bremsstrahlung emissivity workspace and
repopulates it on the current continuum grid.  The present XSTAR source uses a
unity Gaunt factor and leaves ``opakc`` unchanged because the Kirchhoff-opacity
branch remains commented out.  Both behaviors are preserved deliberately.
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


# Default-real literals in bremem.f90 are rounded to binary32 before assignment
# to REAL(8).  Preserve that source behavior deliberately.
XSTAR_BREMEM_CC = float(np.float32(1.032e-13))
XSTAR_BREMEM_KT_EV_PER_T4 = float(np.float32(LEGACY_BOLTZMANN_EV_PER_T4))
XSTAR_BREMEM_ION_Z2_FACTOR = float(np.float32(1.4))
XSTAR_BREMEM_GAMMA_FACTOR = float(np.float32(0.158))
XSTAR_BREMEM_ION_CHARGE = 1.0
XSTAR_BREMEM_GAUNT_FACTOR = 1.0


class BremsstrahlungPortError(RuntimeError):
    """Raised when the translated ``bremem`` subsystem cannot execute."""


@dataclass(frozen=True)
class BremsstrahlungContext:
    """Caller-owned continuum arrays entering XSTAR ``bremem``."""

    epi_eV: np.ndarray
    brcems_before: np.ndarray
    opakc_before_cm_inv: np.ndarray
    ncn2: Optional[int] = None
    source: str = "xstar_bremem_same_call_probe"

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Validate BremsstrahlungContext invariants before the value is consumed downstream.
    # Reference context: XSTAR Manual ss. 11.4.4 and 11.6; Kallman & Bautista (2001), thermal bremsstrahlung.
    # XSTAR-FUNCTION-COMMENT-END
    def validate(self) -> None:
        epi = np.asarray(self.epi_eV, dtype=float).reshape(-1)
        brc = np.asarray(self.brcems_before, dtype=float).reshape(-1)
        opac = np.asarray(self.opakc_before_cm_inv, dtype=float).reshape(-1)
        n = epi.size if self.ncn2 is None else int(self.ncn2)
        if n < 1:
            raise BremsstrahlungPortError("bremem requires at least one continuum bin")
        if epi.size < n or brc.size < n or opac.size < n:
            raise BremsstrahlungPortError(
                f"bremem arrays shorter than ncn2={n}: epi={epi.size}, "
                f"brcems={brc.size}, opakc={opac.size}"
            )
        if not np.all(np.isfinite(epi[:n])):
            raise BremsstrahlungPortError("bremem energy grid contains non-finite values")
        if not np.all(np.isfinite(brc[:n])) or not np.all(np.isfinite(opac[:n])):
            raise BremsstrahlungPortError("bremem continuum state contains non-finite values")
        if np.any(epi[:n] <= 0.0):
            raise BremsstrahlungPortError("bremem photon energies must be positive")
        if n > 1 and np.any(np.diff(epi[:n]) <= 0.0):
            raise BremsstrahlungPortError(
                "bremem photon-energy grid must be strictly increasing"
            )


@dataclass(frozen=True)
class BremsstrahlungResult:
    """Complete result of XSTAR ``bremem.f90``."""

    temperature_t4: float
    ekt_ev: float
    t6: float
    hydrogen_density_cm3: float
    electron_fraction_xee: float
    electron_density_cm3: float
    enz2_cm3: float
    cc: float
    ion_charge: float
    ncn2: int
    epi_eV: np.ndarray
    dimensionless_energy: np.ndarray
    gamma: np.ndarray
    gaunt_factor: np.ndarray
    brtmp: np.ndarray
    bbee: np.ndarray
    brcems_before: np.ndarray
    brcems_after: np.ndarray
    opakc_before_cm_inv: np.ndarray
    opakc_after_cm_inv: np.ndarray
    source_file: str = "xstar/xstarlib/src/bremem.f90"


@dataclass(frozen=True)
class BremsstrahlungProbeReference:
    """Exact same-call XSTAR state captured immediately around ``bremem``."""

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
    ion_charge: float
    epi_eV: np.ndarray
    dimensionless_energy: np.ndarray
    gamma: np.ndarray
    gaunt_factor: np.ndarray
    brcems_before: np.ndarray
    brtmp: np.ndarray
    brcems_after: np.ndarray
    bbee: np.ndarray
    opakc_before_cm_inv: np.ndarray
    opakc_after_cm_inv: np.ndarray
    summary_path: str
    grid_path: str


@dataclass(frozen=True)
class BremsstrahlungParityResult:
    """Bounded v0.4.41 XSTAR/Python ``bremem`` comparison."""

    call_id: int
    python: BremsstrahlungResult
    reference: BremsstrahlungProbeReference
    continuum_grid_parity_ready: bool
    bremsstrahlung_emissivity_parity_ready: bool
    brcems_reset_semantics_ready: bool
    continuum_opacity_preserved_parity_ready: bool
    bremem_translated: bool
    gaunt_factor_mode_unity: bool
    max_brcems_absolute_difference: float
    max_brcems_relative_difference: float
    max_opacity_absolute_difference: float
    max_opacity_relative_difference: float
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Report whether all prerequisites/results required by this stage are present and internally consistent.
    # Reference context: XSTAR Manual ss. 11.4.4 and 11.6; Kallman & Bautista (2001), thermal bremsstrahlung.
    # XSTAR-FUNCTION-COMMENT-END
    @property
    def ready(self) -> bool:
        return bool(
            self.bremem_translated
            and self.gaunt_factor_mode_unity
            and self.continuum_grid_parity_ready
            and self.bremsstrahlung_emissivity_parity_ready
            and self.brcems_reset_semantics_ready
            and self.continuum_opacity_preserved_parity_ready
        )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the relative difference operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual ss. 11.4.4 and 11.6; Kallman & Bautista (2001), thermal bremsstrahlung.
# XSTAR-FUNCTION-COMMENT-END
def _relative_difference(a: np.ndarray | float, b: np.ndarray | float) -> np.ndarray:
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    return np.abs(aa - bb) / np.maximum(
        np.maximum(np.abs(aa), np.abs(bb)), 1.0e-300
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build thermal bremsstrahlung continuum emissivity on the working energy grid while retaining the source Gaunt-factor/grid conventions.
# Reference context: XSTAR Manual ss. 11.4.4 and 11.6; Kallman & Bautista (2001), thermal bremsstrahlung.
# XSTAR-FUNCTION-COMMENT-END
def bremem(
    epi_eV: Sequence[float],
    brcems_before: Sequence[float],
    opakc_before_cm_inv: Sequence[float],
    *,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
    ncn2: Optional[int] = None,
) -> BremsstrahlungResult:
    """Translate XSTAR ``bremem.f90`` in exact source order."""
    context = BremsstrahlungContext(
        epi_eV=np.asarray(epi_eV, dtype=float),
        brcems_before=np.asarray(brcems_before, dtype=float),
        opakc_before_cm_inv=np.asarray(opakc_before_cm_inv, dtype=float),
        ncn2=ncn2,
    )
    context.validate()
    if not math.isfinite(float(temperature_k)) or float(temperature_k) <= 0.0:
        raise BremsstrahlungPortError("temperature_k must be finite and positive")
    if (
        not math.isfinite(float(hydrogen_density_cm3))
        or float(hydrogen_density_cm3) < 0.0
    ):
        raise BremsstrahlungPortError(
            "hydrogen_density_cm3 must be finite and nonnegative"
        )
    if (
        not math.isfinite(float(electron_fraction_xee))
        or float(electron_fraction_xee) < 0.0
    ):
        raise BremsstrahlungPortError(
            "electron_fraction_xee must be finite and nonnegative"
        )

    epi_all = np.asarray(context.epi_eV, dtype=float).reshape(-1)
    brc_before_all = np.asarray(context.brcems_before, dtype=float).reshape(-1)
    opac_before_all = np.asarray(context.opakc_before_cm_inv, dtype=float).reshape(-1)
    n = epi_all.size if context.ncn2 is None else int(context.ncn2)
    epi = epi_all[:n].copy()
    brc_before = brc_before_all[:n].copy()
    opac_before = opac_before_all[:n].copy()

    t4 = float(temperature_k) / 1.0e4
    ekt = t4 * XSTAR_BREMEM_KT_EV_PER_T4
    t6 = t4 / 100.0
    xnx = float(hydrogen_density_cm3) * float(electron_fraction_xee)
    enz2 = XSTAR_BREMEM_ION_Z2_FACTOR * xnx
    zz = XSTAR_BREMEM_ION_CHARGE
    sqrt_t4 = math.sqrt(t4)

    # Source loop 1: bremem explicitly clears the caller-owned workspace.
    brc_after = np.zeros(n, dtype=float)

    temp = np.empty(n, dtype=float)
    gam = np.empty(n, dtype=float)
    gau = np.ones(n, dtype=float)
    brtmp = np.empty(n, dtype=float)
    bbee = np.zeros(n, dtype=float)
    opac_after = opac_before.copy()

    # Source loop 2: compute each emissivity bin.  The opacity branch is
    # commented out in the original source and must remain a no-op.
    for kk in range(n):
        temp_kk = float(epi[kk]) / ekt
        gam_kk = zz * zz * XSTAR_BREMEM_GAMMA_FACTOR / t6
        brtmp_kk = (
            XSTAR_BREMEM_CC
            * xnx
            * enz2
            * XSTAR_BREMEM_GAUNT_FACTOR
            * math.exp(-temp_kk)
            / sqrt_t4
        )
        temp[kk] = temp_kk
        gam[kk] = gam_kk
        brtmp[kk] = brtmp_kk
        brc_after[kk] = brc_after[kk] + brtmp_kk

    return BremsstrahlungResult(
        temperature_t4=t4,
        ekt_ev=ekt,
        t6=t6,
        hydrogen_density_cm3=float(hydrogen_density_cm3),
        electron_fraction_xee=float(electron_fraction_xee),
        electron_density_cm3=xnx,
        enz2_cm3=enz2,
        cc=XSTAR_BREMEM_CC,
        ion_charge=zz,
        ncn2=n,
        epi_eV=epi,
        dimensionless_energy=temp,
        gamma=gam,
        gaunt_factor=gau,
        brtmp=brtmp,
        bbee=bbee,
        brcems_before=brc_before,
        brcems_after=brc_after,
        opakc_before_cm_inv=opac_before,
        opakc_after_cm_inv=opac_after,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the bremem continuum result operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual ss. 11.4.4 and 11.6; Kallman & Bautista (2001), thermal bremsstrahlung.
# XSTAR-FUNCTION-COMMENT-END
def bremem_continuum_result(
    context: BremsstrahlungContext,
    *,
    temperature_k: float,
    hydrogen_density_cm3: float,
    electron_fraction_xee: float,
) -> tuple[BremsstrahlungResult, Dict[str, Any]]:
    """Execute ``bremem`` in the translated ``calc_hmc_all`` source slot."""
    result = bremem(
        context.epi_eV,
        context.brcems_before,
        context.opakc_before_cm_inv,
        temperature_k=temperature_k,
        hydrogen_density_cm3=hydrogen_density_cm3,
        electron_fraction_xee=electron_fraction_xee,
        ncn2=context.ncn2,
    )
    return result, {
        "bremem_translated": True,
        "bremem_source_file": result.source_file,
        "bremem_context_source": context.source,
        "bremem_gaunt_factor_mode": "source_unity",
        "bremem_gaunt_factor_mode_unity": True,
        "brcems_workspace_cleared_before_population": True,
        "bremem_opacity_branch_active": False,
        "continuum_opacity_preserved": bool(
            np.array_equal(result.opakc_before_cm_inv, result.opakc_after_cm_inv)
        ),
        "heatf_accumulation_deferred": True,
    }


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Load bremem probe reference for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.4.4 and 11.6; Kallman & Bautista (2001), thermal bremsstrahlung.
# XSTAR-FUNCTION-COMMENT-END
def load_bremem_probe_reference(
    probe_dir: str | Path,
    *,
    call_id: int = 73,
) -> BremsstrahlungProbeReference:
    """Read the v0.4.41 pre/post-``bremem`` same-call probe products."""
    root = Path(probe_dir)
    summary_path = root / "xstar_calc_hmc_all_bremem_summary_probe.csv"
    grid_path = root / "xstar_calc_hmc_all_bremem_grid_probe.csv"
    if not summary_path.is_file() or not grid_path.is_file():
        raise FileNotFoundError(
            f"missing bremem probe products in {root}: expected "
            f"{summary_path.name} and {grid_path.name}"
        )

    with summary_path.open(newline="", encoding="utf-8") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if int(row["calc_hmc_all_call_id"]) == int(call_id)
        ]
    if len(rows) != 1:
        raise BremsstrahlungPortError(
            f"expected one bremem summary row for call {call_id}, found {len(rows)}"
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
        raise BremsstrahlungPortError(
            f"incomplete bremem grid for call {call_id}: expected {n} rows, "
            f"found {len(grows)}"
        )

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the array operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual ss. 11.4.4 and 11.6; Kallman & Bautista (2001), thermal bremsstrahlung.
    # XSTAR-FUNCTION-COMMENT-END
    def array(key: str) -> np.ndarray:
        return np.asarray(
            [parse_fortran_float(item[key]) for item in grows], dtype=float
        )

    return BremsstrahlungProbeReference(
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
        ion_charge=parse_fortran_float(row["ion_charge"]),
        epi_eV=array("epi_eV"),
        dimensionless_energy=array("temp"),
        gamma=array("gam"),
        gaunt_factor=array("gau"),
        brcems_before=array("brcems_before"),
        brtmp=array("brtmp"),
        brcems_after=array("brcems_after"),
        bbee=array("bbee"),
        opakc_before_cm_inv=array("opakc_before"),
        opakc_after_cm_inv=array("opakc_after"),
        summary_path=str(summary_path),
        grid_path=str(grid_path),
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Compare bremem probe for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.4.4 and 11.6; Kallman & Bautista (2001), thermal bremsstrahlung.
# XSTAR-FUNCTION-COMMENT-END
def compare_bremem_probe(
    reference: BremsstrahlungProbeReference,
    *,
    rtol: float = 5.0e-12,
    atol: float = 1.0e-40,
) -> BremsstrahlungParityResult:
    """Compare translated ``bremem`` with the exact same-call XSTAR probe."""
    result = bremem(
        reference.epi_eV,
        reference.brcems_before,
        reference.opakc_before_cm_inv,
        temperature_k=reference.temperature_t4 * 1.0e4,
        hydrogen_density_cm3=reference.hydrogen_density_cm3,
        electron_fraction_xee=reference.electron_fraction_xee,
        ncn2=reference.ncn2,
    )
    grid_ready = bool(
        result.ncn2 == reference.ncn2
        and np.array_equal(result.epi_eV, reference.epi_eV)
        and np.array_equal(result.brcems_before, reference.brcems_before)
        and np.array_equal(
            result.opakc_before_cm_inv, reference.opakc_before_cm_inv
        )
    )
    br_abs = np.abs(result.brcems_after - reference.brcems_after)
    br_rel = _relative_difference(result.brcems_after, reference.brcems_after)
    op_abs = np.abs(result.opakc_after_cm_inv - reference.opakc_after_cm_inv)
    op_rel = _relative_difference(
        result.opakc_after_cm_inv, reference.opakc_after_cm_inv
    )
    emissivity_ready = bool(
        np.allclose(
            result.brcems_after,
            reference.brcems_after,
            rtol=rtol,
            atol=atol,
        )
        and np.allclose(result.brtmp, reference.brtmp, rtol=rtol, atol=atol)
    )
    reset_ready = bool(
        np.allclose(result.brcems_after, result.brtmp, rtol=rtol, atol=atol)
        and np.allclose(
            reference.brcems_after, reference.brtmp, rtol=rtol, atol=atol
        )
    )
    opacity_ready = bool(
        np.allclose(
            result.opakc_after_cm_inv,
            reference.opakc_after_cm_inv,
            rtol=rtol,
            atol=atol,
        )
        and np.array_equal(
            result.opakc_after_cm_inv, result.opakc_before_cm_inv
        )
        and np.array_equal(
            reference.opakc_after_cm_inv, reference.opakc_before_cm_inv
        )
    )
    return BremsstrahlungParityResult(
        call_id=reference.call_id,
        python=result,
        reference=reference,
        continuum_grid_parity_ready=grid_ready,
        bremsstrahlung_emissivity_parity_ready=emissivity_ready,
        brcems_reset_semantics_ready=reset_ready,
        continuum_opacity_preserved_parity_ready=opacity_ready,
        bremem_translated=True,
        gaunt_factor_mode_unity=bool(np.all(result.gaunt_factor == 1.0)),
        max_brcems_absolute_difference=float(np.max(br_abs)) if br_abs.size else 0.0,
        max_brcems_relative_difference=float(np.max(br_rel)) if br_rel.size else 0.0,
        max_opacity_absolute_difference=float(np.max(op_abs)) if op_abs.size else 0.0,
        max_opacity_relative_difference=float(np.max(op_rel)) if op_rel.size else 0.0,
        diagnostics={
            "rtol": float(rtol),
            "atol": float(atol),
            "reference_summary_path": reference.summary_path,
            "reference_grid_path": reference.grid_path,
            "source_constant_cc": XSTAR_BREMEM_CC,
            "source_opacity_branch": "commented_out",
            "heatf_deferred": True,
        },
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write bremem parity products for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual ss. 11.4.4 and 11.6; Kallman & Bautista (2001), thermal bremsstrahlung.
# XSTAR-FUNCTION-COMMENT-END
def write_bremem_parity_products(
    parity: BremsstrahlungParityResult,
    out_dir: str | Path,
    *,
    port_version: str = "v0.4.41",
) -> Dict[str, Path]:
    """Write scalar and per-bin ``bremem`` parity products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    py = parity.python
    ref = parity.reference
    csv_path = out / "xstar_calc_hmc_all_bremem_continuum.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "grid_index",
            "epi_eV",
            "brcems_before",
            "python_brtmp",
            "xstar_brtmp",
            "python_brcems_after",
            "xstar_brcems_after",
            "brcems_absolute_difference",
            "brcems_relative_difference",
            "dimensionless_energy",
            "gamma",
            "gaunt_factor",
            "bbee",
            "opakc_before",
            "python_opakc_after",
            "xstar_opakc_after",
            "opakc_absolute_difference",
            "opakc_relative_difference",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for idx in range(py.ncn2):
            writer.writerow(
                {
                    "grid_index": idx + 1,
                    "epi_eV": py.epi_eV[idx],
                    "brcems_before": py.brcems_before[idx],
                    "python_brtmp": py.brtmp[idx],
                    "xstar_brtmp": ref.brtmp[idx],
                    "python_brcems_after": py.brcems_after[idx],
                    "xstar_brcems_after": ref.brcems_after[idx],
                    "brcems_absolute_difference": abs(
                        py.brcems_after[idx] - ref.brcems_after[idx]
                    ),
                    "brcems_relative_difference": float(
                        _relative_difference(
                            py.brcems_after[idx], ref.brcems_after[idx]
                        )
                    ),
                    "dimensionless_energy": py.dimensionless_energy[idx],
                    "gamma": py.gamma[idx],
                    "gaunt_factor": py.gaunt_factor[idx],
                    "bbee": py.bbee[idx],
                    "opakc_before": py.opakc_before_cm_inv[idx],
                    "python_opakc_after": py.opakc_after_cm_inv[idx],
                    "xstar_opakc_after": ref.opakc_after_cm_inv[idx],
                    "opakc_absolute_difference": abs(
                        py.opakc_after_cm_inv[idx]
                        - ref.opakc_after_cm_inv[idx]
                    ),
                    "opakc_relative_difference": float(
                        _relative_difference(
                            py.opakc_after_cm_inv[idx],
                            ref.opakc_after_cm_inv[idx],
                        )
                    ),
                }
            )

    summary = {
        "port_version": port_version,
        "calc_hmc_all_call_id": parity.call_id,
        "bremem_translated": parity.bremem_translated,
        "gaunt_factor_mode_unity": parity.gaunt_factor_mode_unity,
        "continuum_grid_parity_ready": parity.continuum_grid_parity_ready,
        "bremsstrahlung_emissivity_parity_ready": parity.bremsstrahlung_emissivity_parity_ready,
        "brcems_reset_semantics_ready": parity.brcems_reset_semantics_ready,
        "continuum_opacity_preserved_parity_ready": parity.continuum_opacity_preserved_parity_ready,
        "bremem_parity_ready": parity.ready,
        "ncn2": py.ncn2,
        "temperature_t4": py.temperature_t4,
        "max_brcems_absolute_difference": parity.max_brcems_absolute_difference,
        "max_brcems_relative_difference": parity.max_brcems_relative_difference,
        "max_opacity_absolute_difference": parity.max_opacity_absolute_difference,
        "max_opacity_relative_difference": parity.max_opacity_relative_difference,
        "diagnostics": dict(parity.diagnostics),
    }
    json_path = out / "xstar_calc_hmc_all_bremem_parity_summary.json"
    json_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    md_path = out / "xstar_calc_hmc_all_bremem_parity_summary.md"
    md_path.write_text(
        "# xstar-atomic v0.4.41 bremem parity\n\n"
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
    "XSTAR_BREMEM_CC",
    "XSTAR_BREMEM_KT_EV_PER_T4",
    "XSTAR_BREMEM_ION_Z2_FACTOR",
    "XSTAR_BREMEM_GAMMA_FACTOR",
    "XSTAR_BREMEM_ION_CHARGE",
    "XSTAR_BREMEM_GAUNT_FACTOR",
    "BremsstrahlungPortError",
    "BremsstrahlungContext",
    "BremsstrahlungResult",
    "BremsstrahlungProbeReference",
    "BremsstrahlungParityResult",
    "bremem",
    "bremem_continuum_result",
    "load_bremem_probe_reference",
    "compare_bremem_probe",
    "write_bremem_parity_products",
]
