"""Physical context objects for source-aligned XSTAR rate evaluation.

The XSTAR atomic database records are not sufficient by themselves to reproduce
many XSTAR rates.  Several branches in ``ucalc.f90`` also depend on the local
plasma state, the local radiation field, and escape/geometry quantities.  This
module provides lightweight, serializable context containers that can be passed
through public APIs, audits, and future population-matrix assembly code.

The classes in this module deliberately do not inject any new physics into the
solver.  They are provenance containers and helper utilities for audit-only
rate evaluators such as the v0.3.128 type-50 bound-bound line-pumping evaluator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


Number = int | float


def _finite_or_none(value: Any) -> float | None:
    """Return a finite float or ``None`` for missing/non-numeric values."""
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


@dataclass(frozen=True)
class LocalPlasmaState:
    """Local thermodynamic and ionization state for an XSTAR zone.

    Parameters
    ----------
    temperature_K:
        Electron temperature in Kelvin.
    electron_density_cm3:
        Electron density in cm^-3.
    ionization_parameter:
        Optional linear ionization parameter.  For XSTAR local-state products
        this is often more safely stored as ``log_xi`` because some output
        columns already contain log10(xi).
    log_xi:
        Optional local log10(xi) in erg cm s^-1.
    radius_cm, thickness_cm:
        Optional local radial information when constructing run-derived
        contexts.
    zone_index:
        Optional zone number/index from an XSTAR output table.
    ion_fraction:
        Optional ion fraction for the selected ion in the local zone.
    metadata:
        Free-form provenance fields, for example source FITS path or selection
        policy.
    """

    temperature_K: float | None = None
    electron_density_cm3: float | None = None
    ionization_parameter: float | None = None
    log_xi: float | None = None
    radius_cm: float | None = None
    thickness_cm: float | None = None
    zone_index: int | None = None
    ion_fraction: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "LocalPlasmaState":
        """Build a state from a dict/CSV row using common XSTAR column names."""
        return cls(
            temperature_K=_finite_or_none(
                data.get("temperature_K")
                or data.get("xstar_temperature_K")
                or data.get("temperature")
                or data.get("temperature_k")
            ),
            electron_density_cm3=_finite_or_none(
                data.get("electron_density_cm^-3")
                or data.get("xstar_electron_density_cm^-3")
                or data.get("electron_density_cm3")
                or data.get("density")
            ),
            ionization_parameter=_finite_or_none(
                data.get("ionization_parameter")
                or data.get("xi")
                or data.get("xstar_xi_erg_cm_s^-1")
            ),
            log_xi=_finite_or_none(data.get("log_xi") or data.get("xstar_log_xi_local")),
            radius_cm=_finite_or_none(data.get("radius_cm")),
            thickness_cm=_finite_or_none(data.get("thickness_cm")),
            zone_index=int(_finite_or_none(data.get("zone_index")) or 0) if data.get("zone_index") not in (None, "") else None,
            ion_fraction=_finite_or_none(data.get("ion_fraction") or data.get("xstar_helike_fraction")),
            metadata={k: v for k, v in data.items() if k not in {"temperature_K", "xstar_temperature_K"}},
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/CSV-friendly representation."""
        return {
            "temperature_K": self.temperature_K,
            "electron_density_cm3": self.electron_density_cm3,
            "ionization_parameter": self.ionization_parameter,
            "log_xi": self.log_xi,
            "radius_cm": self.radius_cm,
            "thickness_cm": self.thickness_cm,
            "zone_index": self.zone_index,
            "ion_fraction": self.ion_fraction,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RadiationField:
    """Local radiation field sampled on an XSTAR-like energy grid.

    The type-50 source-code branch uses ``bremsa(nb1)`` at the continuum bin
    containing the line energy.  This class stores the energy grid and the
    corresponding local radiation values without prescribing a final
    normalization convention.
    """

    energy_grid: Sequence[float] = field(default_factory=tuple)
    flux_density: Sequence[float] = field(default_factory=tuple)
    integrated_flux: float | None = None
    source: str | None = None
    normalization: str = "xstar-bremsa"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.energy_grid) != len(self.flux_density):
            raise ValueError("energy_grid and flux_density must have the same length")

    @classmethod
    def from_pairs(
        cls,
        pairs: Sequence[tuple[Number, Number]],
        *,
        source: str | Path | None = None,
        normalization: str = "xstar-bremsa",
        metadata: Mapping[str, Any] | None = None,
    ) -> "RadiationField":
        """Create a radiation field from ``(energy, value)`` pairs."""
        return cls(
            energy_grid=tuple(float(x[0]) for x in pairs),
            flux_density=tuple(float(x[1]) for x in pairs),
            source=str(source) if source is not None else None,
            normalization=normalization,
            metadata=dict(metadata or {}),
        )

    def bin_index(self, energy: Number) -> int | None:
        """Return the nearest energy-grid index for ``energy``.

        This helper is an audit convenience, not yet a guaranteed reproduction
        of XSTAR's internal ``nbinc`` routine.  Future versions should replace
        or supplement it with an exact source-code-matched bin mapper.
        """
        e = _finite_or_none(energy)
        if e is None or not self.energy_grid:
            return None
        return min(range(len(self.energy_grid)), key=lambda i: abs(float(self.energy_grid[i]) - e))

    def value_at(self, energy: Number) -> float | None:
        """Return the nearest-bin radiation value for ``energy``."""
        idx = self.bin_index(energy)
        if idx is None:
            return None
        return float(self.flux_density[idx])

    def to_dict(self) -> dict[str, Any]:
        """Return a compact JSON/CSV-friendly representation."""
        return {
            "n_energy_grid": len(self.energy_grid),
            "source": self.source,
            "normalization": self.normalization,
            "integrated_flux": self.integrated_flux,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class EscapeContext:
    """Line escape and covering/geometry context for XSTAR-like rates.

    Parameters
    ----------
    cfrac:
        XSTAR covering factor.  In the type-50 line-pumping branch the upward
        radiative-excitation term is multiplied by ``max(0, 1-cfrac)``.
    tau_in, tau_out:
        Optional inward/outward optical depths.
    ptmp1, ptmp2:
        Optional escape-probability factors used by XSTAR's type-50 branch.
    flinabs_ptmp1:
        Optional line absorption/profile factor entering the photoexcitation
        branch.  It is kept separate from ``ptmp1`` because XSTAR calls a
        distinct helper in the source code.
    """

    cfrac: float = 1.0
    tau_in: float | None = None
    tau_out: float | None = None
    ptmp1: float | None = None
    ptmp2: float | None = None
    flinabs_ptmp1: float | None = None
    escape_function: str = "pescl"
    continuum_escape_function: str = "pescv"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EscapeContext":
        """Build an escape context from common matrix/audit row names."""
        cfrac = _finite_or_none(data.get("cfrac"))
        return cls(
            cfrac=1.0 if cfrac is None else cfrac,
            tau_in=_finite_or_none(data.get("tau_in") or data.get("xstar_tau1_for_type50_escape")),
            tau_out=_finite_or_none(data.get("tau_out") or data.get("xstar_tau2_for_type50_escape")),
            ptmp1=_finite_or_none(data.get("ptmp1")),
            ptmp2=_finite_or_none(data.get("ptmp2")),
            flinabs_ptmp1=_finite_or_none(data.get("flinabs_ptmp1") or data.get("flinabs")),
            metadata=dict(data),
        )

    @property
    def covering_multiplier(self) -> float:
        """Return the XSTAR line-pumping multiplier ``max(0, 1-cfrac)``."""
        return max(0.0, 1.0 - float(self.cfrac))

    @property
    def ptmp_sum(self) -> float | None:
        """Return ``ptmp1 + ptmp2`` when both are available."""
        if self.ptmp1 is None or self.ptmp2 is None:
            return None
        return float(self.ptmp1) + float(self.ptmp2)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/CSV-friendly representation."""
        return {
            "cfrac": self.cfrac,
            "tau_in": self.tau_in,
            "tau_out": self.tau_out,
            "ptmp1": self.ptmp1,
            "ptmp2": self.ptmp2,
            "ptmp_sum": self.ptmp_sum,
            "flinabs_ptmp1": self.flinabs_ptmp1,
            "escape_function": self.escape_function,
            "continuum_escape_function": self.continuum_escape_function,
            "covering_multiplier": self.covering_multiplier,
            "metadata": dict(self.metadata),
        }


__all__ = ["LocalPlasmaState", "RadiationField", "EscapeContext"]
