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


@dataclass(frozen=True)
class XSTARContext:
    """Bundle local plasma, radiation, escape, and run provenance.

    This is the public context object used by the workflow API.  It is small on
    purpose: v0.3.132 uses it to pass local XSTAR state into audit and solver
    wrappers without pretending that a full radiation-transfer state has already
    been reconstructed.
    """

    plasma: LocalPlasmaState = field(default_factory=LocalPlasmaState)
    radiation: RadiationField | None = None
    escape: EscapeContext | None = None
    ion: str | None = None
    run_dir: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/CSV-friendly representation."""
        return {
            "ion": self.ion,
            "run_dir": self.run_dir,
            "plasma": self.plasma.to_dict(),
            "radiation": self.radiation.to_dict() if self.radiation is not None else None,
            "escape": self.escape.to_dict() if self.escape is not None else None,
            "metadata": dict(self.metadata),
        }


def _normalize_key(text: Any) -> str:
    return str(text or "").strip().lower().replace(" ", "_").replace("-", "_")


def _ion_column_candidates(ion: str | None) -> tuple[str, ...]:
    if not ion:
        return ()
    import re
    from .api import parse_ion

    try:
        _z, stage, symbol = parse_ion(ion)
    except Exception:
        return (_normalize_key(ion),)
    if symbol is None or stage is None:
        return (_normalize_key(ion),)
    roman_map = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    n = int(stage)
    roman = []
    for value, glyph in roman_map:
        while n >= value:
            roman.append(glyph)
            n -= value
    roman_text = "".join(roman).lower()
    sym = symbol.lower()
    return (
        f"{sym}_{roman_text}",
        f"{sym}{roman_text}",
        f"{sym}_{stage}",
        f"{sym}{stage}",
        _normalize_key(ion),
        re.sub(r"[^a-z0-9]+", "_", str(ion).lower()).strip("_"),
    )


def _find_ion_fraction_column(row: Mapping[str, Any], ion: str | None) -> str | None:
    norm_to_key = {_normalize_key(k): k for k in row.keys()}
    for cand in _ion_column_candidates(ion):
        if cand in norm_to_key:
            return norm_to_key[cand]
    # XSTAR abundance tables often use labels like c_v or o_vii.  Fallback to a
    # contains match only when the requested ion has a known normalized label.
    candidates = [c for c in _ion_column_candidates(ion) if c]
    for nk, original in norm_to_key.items():
        if nk in candidates or any(nk == c for c in candidates):
            return original
    return None


def context_from_values(
    *,
    temperature_K: float | None = None,
    electron_density_cm3: float | None = None,
    ion: str | None = None,
    log_xi: float | None = None,
    ionization_parameter: float | None = None,
    radius_cm: float | None = None,
    thickness_cm: float | None = None,
    ion_fraction: float | None = None,
    radiation: RadiationField | None = None,
    escape: EscapeContext | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> XSTARContext:
    """Create an :class:`XSTARContext` from explicit local physical values."""
    plasma = LocalPlasmaState(
        temperature_K=temperature_K,
        electron_density_cm3=electron_density_cm3,
        ionization_parameter=ionization_parameter,
        log_xi=log_xi,
        radius_cm=radius_cm,
        thickness_cm=thickness_cm,
        ion_fraction=ion_fraction,
        metadata=dict(metadata or {}),
    )
    return XSTARContext(plasma=plasma, radiation=radiation, escape=escape, ion=ion, metadata=dict(metadata or {}))


def context_from_xstar_run(
    run_dir: str | Path,
    *,
    ion: str | None = None,
    zone_index: int | None = None,
    selection: str = "max_fraction",
    xout_abund_filename: str = "xout_abund1.fits",
) -> XSTARContext:
    """Build a lightweight local context from an XSTAR run directory.

    The current implementation reads ``xout_abund1.fits`` and selects either a
    requested ``zone_index`` or the zone with the largest fraction for ``ion``.
    It records run provenance and local ``T``, ``ne``, ``log_xi``, radius, and
    thickness.  Radiation and detailed escape contexts are intentionally left
    empty until the v0.3.13x radiation/escape API is source-matched.
    """
    run_path = Path(run_dir)
    abund_path = run_path / xout_abund_filename
    if not abund_path.exists():
        raise FileNotFoundError(f"Could not find {xout_abund_filename!r} in {run_path}")
    from .xstar_outputs import read_xout_abundances

    tables = read_xout_abundances(abund_path)
    rows = list(tables.get("abundances", []))
    if not rows:
        raise ValueError(f"No ABUNDANCES rows found in {abund_path}")
    ion_col = _find_ion_fraction_column(rows[0], ion)

    enriched: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        xe = _finite_or_none(row.get("x_e"))
        np_ = _finite_or_none(row.get("n_p"))
        temp_1e4 = _finite_or_none(row.get("temperature"))
        logxi = _finite_or_none(row.get("ion_parameter"))
        frac = _finite_or_none(row.get(ion_col)) if ion_col is not None else None
        enriched.append({
            "zone_index": idx,
            "temperature_K": 1.0e4 * temp_1e4 if temp_1e4 is not None else None,
            "electron_density_cm3": xe * np_ if xe is not None and np_ is not None else None,
            "log_xi": logxi,
            "ionization_parameter": 10.0 ** logxi if logxi is not None else None,
            "radius_cm": _finite_or_none(row.get("radius")),
            "thickness_cm": _finite_or_none(row.get("delta_r")),
            "ion_fraction": frac,
            "raw_row": dict(row),
        })
    if zone_index is not None:
        matches = [r for r in enriched if int(r["zone_index"]) == int(zone_index)]
        if not matches:
            raise ValueError(f"zone_index={zone_index} not found in {abund_path}")
        chosen = matches[0]
        selection_policy = "zone_index"
    elif selection == "max_fraction" and ion_col is not None:
        chosen = max(enriched, key=lambda r: -1.0 if r.get("ion_fraction") is None else float(r["ion_fraction"]))
        selection_policy = "max_fraction"
    else:
        chosen = enriched[0]
        selection_policy = "first_zone"
    plasma = LocalPlasmaState(
        temperature_K=chosen.get("temperature_K"),
        electron_density_cm3=chosen.get("electron_density_cm3"),
        ionization_parameter=chosen.get("ionization_parameter"),
        log_xi=chosen.get("log_xi"),
        radius_cm=chosen.get("radius_cm"),
        thickness_cm=chosen.get("thickness_cm"),
        zone_index=chosen.get("zone_index"),
        ion_fraction=chosen.get("ion_fraction"),
        metadata={
            "xstar_abund_path": str(abund_path),
            "xstar_case_directory": run_path.name,
            "selection": selection_policy,
            "ion_fraction_column": ion_col,
        },
    )
    return XSTARContext(
        plasma=plasma,
        ion=ion,
        run_dir=str(run_path),
        metadata={
            "xstar_abund_path": str(abund_path),
            "selection": selection_policy,
            "n_zones": len(rows),
            "ion_fraction_column": ion_col,
        },
    )


__all__ = ["LocalPlasmaState", "RadiationField", "EscapeContext", "XSTARContext", "context_from_values", "context_from_xstar_run"]
