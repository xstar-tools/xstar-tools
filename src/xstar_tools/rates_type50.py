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
    "ener=abs(E_upper-E_lower); pre-swap ans4=ans1*ener*ergsev, "
    "ans3=ans2*ener*ergsev; post-swap ans1=photoexcitation, "
    "ans2=escaped decay, ans3=-escaped*ener*ergsev, "
    "ans4=-photoexcitation*ener*ergsev"
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
    "XSTAR_C_LIGHT_CM_S",
    "evaluate_type50_ucalc_record",
]

XSTAR_C_LIGHT_CM_S = 3.0e10
XSTAR_ERG_PER_EV = 1.602176634e-12


def evaluate_type50_ucalc_record(
    decoded_line: Mapping[str, Any],
    *,
    ptmp1: float,
    ptmp2: float,
    cfrac: float,
    bremsa_nb1: float | None = None,
    flinabs_ptmp1: float | None = 1.0,
    hydrogen_density_cm3: float | None = None,
    high_wavelength_cutoff_A: float = 0.99e9,
    endpoint_energy_eV: float | None = None,
    source_erg_per_eV: float = XSTAR_ERG_PER_EV,
) -> dict[str, Any]:
    """Evaluate a decoded XSTAR type-50 record in ``ucalc`` branch order.

    The post-swap return convention is ``ans1`` lower-to-upper
    photoexcitation and ``ans2`` upper-to-lower escaped decay.  The pumping
    expression is evaluated only from an explicit same-state ``bremsa(nb1)``
    value, except when ``cfrac >= 1`` (or the XSTAR high-wavelength sentinel applies),
    where the native photoexcitation rate is exactly zero and no radiation
    context is required.  Supply the captured XSTAR ``xpx`` value through
    ``hydrogen_density_cm3`` to reproduce the source numerical floor
    ``max(A*(ptmp1+ptmp2), 1e-20*xpx)`` exactly.

    ``flinabs.f90`` in the audited XSTAR source currently returns unity; the
    argument remains explicit so future source changes or probe products can
    override it without changing this API.
    """
    def pick(*names: str) -> float | None:
        for name in names:
            value = _finite_or_none(decoded_line.get(name))
            if value is not None:
                return value
        return None

    aij = pick("A_s^-1", "A_s_inv", "aij_s_inv", "rate_s^-1")
    flin = pick("f_osc_from_A", "oscillator_strength", "flin")
    wavelength_a = pick("wavelength_A", "wavelength", "lambda_A")
    stored_wavelength_energy_ev = pick("energy_eV", "line_energy_eV")
    if stored_wavelength_energy_ev is None and wavelength_a is not None and wavelength_a > 0.0:
        stored_wavelength_energy_ev = 12398.4016 / wavelength_a
    endpoint_energy = _finite_or_none(endpoint_energy_eV)

    p1 = _finite_or_none(ptmp1)
    p2 = _finite_or_none(ptmp2)
    cf = _finite_or_none(cfrac)
    if cf is None:
        cf = 1.0
    cover = max(0.0, 1.0 - cf)
    flinabs = _finite_or_none(flinabs_ptmp1)
    if flinabs is None:
        flinabs = 1.0
    bremsa = _finite_or_none(bremsa_nb1)

    # 0.6.82.30.8.12: ucalc.f90 label 50 exits immediately when the
    # stored source wavelength is zero/disabled (elin<=1.d-34).  Do not let
    # A-value floors or endpoint-derived energies reactivate that record.
    source_zero_wavelength = (
        wavelength_a is not None and abs(float(wavelength_a)) <= 1.0e-34
    )

    escaped_raw = None
    escaped = None
    xpx = _finite_or_none(hydrogen_density_cm3)
    density_floor = 1.0e-20 * xpx if xpx is not None else None
    density_floor_applied = False
    if source_zero_wavelength:
        escaped_raw = 0.0
        escaped = 0.0
    elif aij is not None and p1 is not None and p2 is not None:
        escaped_raw = aij * (p1 + p2)
        if density_floor is not None:
            escaped = max(escaped_raw, density_floor)
            density_floor_applied = density_floor > escaped_raw
        else:
            escaped = escaped_raw

    photo = None
    radiation_context_required = True
    photo_status = "not_evaluated"
    if source_zero_wavelength:
        photo = 0.0
        radiation_context_required = False
        photo_status = "evaluated_zero_xstar_source_wavelength_gate"
    elif wavelength_a is not None and wavelength_a > high_wavelength_cutoff_A:
        photo = 0.0
        radiation_context_required = False
        photo_status = "evaluated_zero_xstar_high_wavelength_sentinel"
    elif cover == 0.0:
        photo = 0.0
        radiation_context_required = False
        photo_status = "evaluated_zero_full_covering_fraction"
    elif flin is not None and wavelength_a is not None and bremsa is not None:
        # The source forms sigma ~ 1/vtherm and then multiplies by vtherm;
        # canceling those factors is algebraically exact and avoids introducing
        # a diagnostic velocity when only the final rate is required.
        photo = (
            0.02655
            * flin
            * wavelength_a
            * 1.0e-8
            * bremsa
            / XSTAR_C_LIGHT_CM_S
            * flinabs
            * cover
        )
        photo_status = "evaluated_with_explicit_bremsa_context"

    missing: list[str] = []
    if escaped is None:
        if aij is None:
            missing.append("A_s^-1")
        if p1 is None:
            missing.append("ptmp1")
        if p2 is None:
            missing.append("ptmp2")
    if photo is None:
        if flin is None:
            missing.append("oscillator_strength")
        if wavelength_a is None:
            missing.append("wavelength_A")
        if bremsa is None:
            missing.append("bremsa_nb1")

    # Source label 50 re-derives ``ener=abs(eeup-eelo)`` from the actual
    # endpoint level energies after locating the line record, then forms both
    # energy channels from that same endpoint difference before the final
    # ans1/ans2 and ans3/ans4 swaps.  After the swap both returned energy
    # channels are negative: ans3 is escaped line cooling and ans4 is pumping
    # heating.  The stored wavelength remains relevant to the oscillator
    # strength, line-profile, and radiation-grid lookup, but not to ans3/ans4.
    decay_energy_ev = endpoint_energy
    decay_energy_source = "endpoint_energy_difference"
    ans3_cooling = None
    ans4_heating = None
    if source_zero_wavelength:
        ans3_cooling = 0.0
        ans4_heating = 0.0
    else:
        if escaped is not None and decay_energy_ev is not None:
            ans3_cooling = -escaped * decay_energy_ev * float(source_erg_per_eV)
        if photo is not None and endpoint_energy is not None:
            ans4_heating = -photo * endpoint_energy * float(source_erg_per_eV)

    # Preserve the long-standing public evaluator contract: ``status`` reports
    # whether the population-rate pair ans1/ans2 can be evaluated.  The new
    # energy-channel status is tracked independently so audit callers that do
    # not supply endpoint energies remain backward compatible.  The source-port
    # ucalc path always supplies endpoint energies and explicitly requires both
    # ans3 and ans4.
    status = (
        "evaluated"
        if escaped is not None and photo is not None
        else "not_evaluated"
    )
    energy_channel_status = (
        "evaluated"
        if ans3_cooling is not None and ans4_heating is not None
        else "not_evaluated_missing_endpoint_energy"
    )
    return {
        "status": status,
        "reason": "" if status == "evaluated" else "missing_context:" + ",".join(sorted(set(missing))),
        "energy_channel_status": energy_channel_status,
        "ans1_photoexcitation_s^-1": photo,
        "ans2_escaped_decay_s^-1": escaped,
        "escaped_decay_before_density_floor_s^-1": escaped_raw,
        "hydrogen_density_xpx_cm^-3": xpx,
        "density_floor_s^-1": density_floor,
        "density_floor_applied": density_floor_applied,
        "source_equivalent_density_floor_context": xpx is not None,
        "source_equivalent_rate_context": status == "evaluated" and xpx is not None,
        "aij_s^-1": aij,
        "oscillator_strength": flin,
        "wavelength_A": wavelength_a,
        # Backward-compatible stored-wavelength energy.  The source thermal
        # channels below intentionally use endpoint_energy_eV instead.
        "energy_eV": stored_wavelength_energy_ev,
        "endpoint_energy_eV": endpoint_energy,
        "stored_wavelength_energy_eV": stored_wavelength_energy_ev,
        "decay_energy_eV": decay_energy_ev,
        "decay_energy_source": decay_energy_source,
        "ans3_cooling_signed_erg_s^-1": ans3_cooling,
        "ans4_heating_signed_erg_s^-1": ans4_heating,
        "source_erg_per_eV": float(source_erg_per_eV),
        "ptmp1": p1,
        "ptmp2": p2,
        "ptmp_sum": (p1 + p2) if p1 is not None and p2 is not None else None,
        "cfrac": cf,
        "covering_multiplier": cover,
        "bremsa_nb1": bremsa,
        "flinabs_ptmp1": flinabs,
        "photoexcitation_status": photo_status,
        "radiation_context_required": radiation_context_required,
        "source_formula": TYPE50_SOURCE_FORMULA,
        "source_light_speed_cm_s": XSTAR_C_LIGHT_CM_S,
        "source_high_wavelength_cutoff_A": high_wavelength_cutoff_A,
        "source_zero_wavelength_gate": source_zero_wavelength,
    }
