"""Audit-only XSTAR type-50 bound-bound radiative rate evaluator.

XSTAR data type 50 stores bound-bound radiative transitions.  In ``ucalc.f90``
the type-50 branch constructs a downward escaped decay and an upward
photoexcitation / line-pumping term.  XSTAR then swaps the local ``ans1`` and
``ans2`` branches so the returned ``ans1`` is the lower-to-upper
photoexcitation rate and the returned ``ans2`` is the upper-to-lower escaped
radiative decay.

This module implements that source-code relation as an explicit, typed,
provenance-rich evaluator.  It is intentionally audit-only in v0.3.128: nothing
here modifies the population solver unless a future matrix assembly mode opts in
and validates the term against same-run XSTAR outputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping

from .context import EscapeContext, LocalPlasmaState, RadiationField

C_LIGHT_CM_S = 2.99792458e10
TYPE50_SOURCE_FORMULA = (
    "ucalc.f90:type50 pre-swap ans1=A*(ptmp1+ptmp2); "
    "sigma=0.02655*flin*lambda_cm/vtherm; "
    "ans2=sigma*bremsa(nb1)*vtherm/c*flinabs(ptmp1)*(1-cfrac); "
    "post-swap ans1=photoexcitation and ans2=escaped decay"
)


def _finite_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


@dataclass(frozen=True)
class RateEvaluation:
    """Provenance-rich rate evaluation result.

    The generic fields allow the same class to be reused for future XSTAR data
    types.  Type-50-specific terms are stored in ``terms`` and exposed through
    convenience keys by :func:`evaluate_type50_bound_bound`.
    """

    process: str
    data_type: int
    status: str
    value_s_inv: float | None = None
    lower_to_upper_photoexcitation_s_inv: float | None = None
    upper_to_lower_escaped_decay_s_inv: float | None = None
    source_formula: str = ""
    record_id: int | str | None = None
    ion: str | None = None
    lower_level: int | str | None = None
    upper_level: int | str | None = None
    terms: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/CSV-friendly representation."""
        out = {
            "process": self.process,
            "data_type": self.data_type,
            "status": self.status,
            "value_s^-1": self.value_s_inv,
            "lower_to_upper_photoexcitation_s^-1": self.lower_to_upper_photoexcitation_s_inv,
            "upper_to_lower_escaped_decay_s^-1": self.upper_to_lower_escaped_decay_s_inv,
            "source_formula": self.source_formula,
            "record_id": self.record_id,
            "ion": self.ion,
            "lower_level": self.lower_level,
            "upper_level": self.upper_level,
            "warnings": "; ".join(self.warnings),
        }
        out.update({f"term_{k}": v for k, v in dict(self.terms).items()})
        out.update({f"meta_{k}": v for k, v in dict(self.metadata).items()})
        return out


def evaluate_type50_bound_bound(
    *,
    aij_s_inv: float | None = None,
    oscillator_strength: float | None = None,
    wavelength_A: float | None = None,
    wavelength_cm: float | None = None,
    vtherm_cm_s: float | None = None,
    bremsa_nb1: float | None = None,
    ptmp1: float | None = None,
    ptmp2: float | None = None,
    flinabs_ptmp1: float | None = None,
    cfrac: float = 1.0,
    ion: str | None = None,
    lower_level: int | str | None = None,
    upper_level: int | str | None = None,
    record_id: int | str | None = None,
    plasma_state: LocalPlasmaState | None = None,
    radiation_field: RadiationField | None = None,
    escape_context: EscapeContext | None = None,
    line_energy: float | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> RateEvaluation:
    """Evaluate the XSTAR type-50 radiative branch in audit mode.

    Parameters are named after the XSTAR source-code ingredients wherever
    possible.  If ``radiation_field`` and ``line_energy`` are provided but
    ``bremsa_nb1`` is omitted, the nearest-bin radiation value is used as an
    audit approximation.  Future versions should add an exact XSTAR ``nbinc``
    mapper before this term is injected into a solver.
    """
    warnings: list[str] = []
    if escape_context is not None:
        if ptmp1 is None:
            ptmp1 = escape_context.ptmp1
        if ptmp2 is None:
            ptmp2 = escape_context.ptmp2
        if flinabs_ptmp1 is None:
            flinabs_ptmp1 = escape_context.flinabs_ptmp1
        cfrac = escape_context.cfrac
    if bremsa_nb1 is None and radiation_field is not None and line_energy is not None:
        bremsa_nb1 = radiation_field.value_at(line_energy)
        warnings.append("bremsa_nb1 taken from nearest radiation-field bin; exact XSTAR nbinc mapping is not yet implemented")

    aij = _finite_or_none(aij_s_inv)
    flin = _finite_or_none(oscillator_strength)
    lam_cm = _finite_or_none(wavelength_cm)
    if lam_cm is None and wavelength_A is not None:
        lam_cm = _finite_or_none(wavelength_A)
        if lam_cm is not None:
            lam_cm *= 1.0e-8
    vtherm = _finite_or_none(vtherm_cm_s)
    bremsa = _finite_or_none(bremsa_nb1)
    p1 = _finite_or_none(ptmp1)
    p2 = _finite_or_none(ptmp2)
    flinabs = _finite_or_none(flinabs_ptmp1)
    cf = _finite_or_none(cfrac)
    if cf is None:
        cf = 1.0
    cover = max(0.0, 1.0 - cf)

    pre_swap_ans1 = None
    if aij is not None and p1 is not None and p2 is not None:
        pre_swap_ans1 = aij * (p1 + p2)

    sigma_cm2 = None
    if flin is not None and lam_cm is not None and vtherm is not None and vtherm > 0.0:
        sigma_cm2 = 0.02655 * flin * lam_cm / vtherm

    pre_swap_ans2 = None
    if sigma_cm2 is not None and bremsa is not None and vtherm is not None and flinabs is not None:
        pre_swap_ans2 = sigma_cm2 * bremsa * vtherm / C_LIGHT_CM_S * flinabs * cover

    missing = []
    if pre_swap_ans1 is None:
        for name, value in [("aij_s_inv", aij), ("ptmp1", p1), ("ptmp2", p2)]:
            if value is None:
                missing.append(name)
    if pre_swap_ans2 is None:
        for name, value in [
            ("oscillator_strength", flin),
            ("wavelength_cm", lam_cm),
            ("vtherm_cm_s", vtherm),
            ("bremsa_nb1", bremsa),
            ("flinabs_ptmp1", flinabs),
        ]:
            if value is None:
                missing.append(name)
    if cover == 0.0:
        warnings.append("covering multiplier max(0,1-cfrac) is zero, so type-50 photoexcitation is zero even if other inputs are present")

    status = "ok" if pre_swap_ans1 is not None and pre_swap_ans2 is not None else "incomplete_context"
    if missing:
        warnings.append("missing inputs: " + ", ".join(sorted(set(missing))))

    terms = {
        "pre_swap_ans1_escaped_decay_s^-1": pre_swap_ans1,
        "pre_swap_ans2_photoexcitation_s^-1": pre_swap_ans2,
        "post_swap_ans1_photoexcitation_s^-1": pre_swap_ans2,
        "post_swap_ans2_escaped_decay_s^-1": pre_swap_ans1,
        "sigma_cm2": sigma_cm2,
        "lambda_cm": lam_cm,
        "vtherm_cm_s": vtherm,
        "bremsa_nb1": bremsa,
        "flinabs_ptmp1": flinabs,
        "cfrac": cf,
        "covering_multiplier": cover,
        "ptmp1": p1,
        "ptmp2": p2,
        "ptmp_sum": (p1 + p2) if p1 is not None and p2 is not None else None,
    }
    if plasma_state is not None:
        terms.update({f"plasma_{k}": v for k, v in plasma_state.to_dict().items() if k != "metadata"})
    if radiation_field is not None:
        terms.update({f"radiation_{k}": v for k, v in radiation_field.to_dict().items() if k != "metadata"})
    if escape_context is not None:
        terms.update({f"escape_{k}": v for k, v in escape_context.to_dict().items() if k != "metadata"})

    return RateEvaluation(
        process="bound_bound_radiative_type50",
        data_type=50,
        status=status,
        value_s_inv=pre_swap_ans2,
        lower_to_upper_photoexcitation_s_inv=pre_swap_ans2,
        upper_to_lower_escaped_decay_s_inv=pre_swap_ans1,
        source_formula=TYPE50_SOURCE_FORMULA,
        record_id=record_id,
        ion=ion,
        lower_level=lower_level,
        upper_level=upper_level,
        terms=terms,
        warnings=tuple(warnings),
        metadata=dict(metadata or {}),
    )


def type50_formula_summary() -> str:
    """Return the compact source-code formula string used in audits."""
    return TYPE50_SOURCE_FORMULA


__all__ = [
    "C_LIGHT_CM_S",
    "TYPE50_SOURCE_FORMULA",
    "RateEvaluation",
    "evaluate_type50_bound_bound",
    "type50_formula_summary",
]
