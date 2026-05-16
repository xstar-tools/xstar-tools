"""Native source-code evaluator for XSTAR data type 71.

Type 71 stores radiative cascades from superlevels to spectroscopic levels.
``calt71.f90`` returns the radiative probability, possibly interpolated on a
log-density/log-temperature grid.  ``ucalc.f90`` then applies the escape sum
and returns ``ans1=0`` and ``ans2=A*(ptmp1+ptmp2)`` for the universal matrix
insertion path.
"""
from __future__ import annotations

import ast
import math
from typing import Any, Mapping, Sequence


def _float_list(value: Any) -> list[float]:
    if isinstance(value, (list, tuple)):
        return [float(x) for x in value]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple)):
                return [float(x) for x in parsed]
        except Exception:
            pass
    return []


def _int_list(value: Any) -> list[int]:
    return [int(round(x)) for x in _float_list(value)]


def evaluate_calt71_record(
    decoded_record: Mapping[str, Any],
    *,
    temperature_k: float,
    electron_density_cm3: float,
) -> dict[str, Any]:
    """Port ``calt71.f90`` for one decoded type-71 record.

    Despite the generic argument name, source-equivalent calls must pass the
    XSTAR ``ucalc.f90`` variable ``xpx`` because the type-71 branch sets
    ``den=xpx`` before calling ``calt71``.  It does not pass ``xpx*xee``.
    """
    reals = _float_list(decoded_record.get("reals") or decoded_record.get("raw_reals"))
    ints = _int_list(decoded_record.get("ints") or decoded_record.get("raw_ints"))
    if not ints:
        nden = decoded_record.get("nden")
        ntem = decoded_record.get("ntem")
        if nden is not None and ntem is not None:
            ints = [int(nden), int(ntem)]
    out: dict[str, Any] = {
        "status": "not_evaluated",
        "reason": "",
        "aij_s^-1": None,
        "wavelength_A": None,
        "log10_aij": None,
        "nden": ints[0] if len(ints) >= 1 else None,
        "ntem": ints[1] if len(ints) >= 2 else None,
        "source": "calt71.f90",
    }
    if len(ints) < 2 or len(reals) < 4:
        out["reason"] = "missing_nden_ntem_or_reals"
        return out
    nden, ntem = int(ints[0]), int(ints[1])
    if nden <= 0 or ntem <= 0:
        out["reason"] = "invalid_grid_dimensions"
        return out
    if nden == 1 and ntem == 1:
        dtmp = math.log10(reals[2]) if reals[2] > 30.0 else reals[2]
        out.update({
            "status": "evaluated",
            "branch": "single_point",
            "aij_s^-1": 10.0 ** dtmp,
            "wavelength_A": reals[3],
            "log10_aij": dtmp,
        })
        return out

    need = nden + ntem + nden * ntem + 1
    if len(reals) < need:
        out["reason"] = f"short_grid_record_need_{need}_got_{len(reals)}"
        return out
    if temperature_k <= 0.0 or electron_density_cm3 <= 0.0:
        out["reason"] = "nonpositive_temperature_or_density"
        return out
    if nden < 2 or ntem < 2:
        out["reason"] = "grid_requires_two_points_per_axis"
        return out

    dens = reals[:nden]
    temp = reals[nden:nden + ntem]
    table0 = nden + ntem
    wav = reals[nden * ntem + nden + ntem]
    rne = math.log10(electron_density_cm3)
    rte = math.log10(temperature_k)
    notes: list[str] = []
    if rne > dens[-1]:
        rne = dens[-1]
        notes.append("logne_clipped_to_grid_max")
    if rte > temp[-1] + 1.0:
        rte = temp[-1] + 1.0
        notes.append("logT_clipped_to_grid_max_plus_one")
    if rte < temp[0] - 1.0:
        rte = temp[0] - 1.0
        notes.append("logT_clipped_to_grid_min_minus_one")

    def bracket(grid: Sequence[float], x: float) -> int:
        if x <= grid[0]:
            return 0
        for i in range(len(grid) - 1):
            if x < grid[i + 1]:
                return i
        return len(grid) - 2

    ni = bracket(dens, rne)
    ti = bracket(temp, rte)
    n0, n1 = dens[ni], dens[ni + 1]
    t0, t1 = temp[ti], temp[ti + 1]
    if n0 == n1 or t0 == t1:
        out["reason"] = "degenerate_grid_bracket"
        return out

    def table(i: int, j: int) -> float:
        return reals[table0 + i * ntem + j]

    r0 = table(ni, ti) + (table(ni, ti + 1) - table(ni, ti)) * (rte - t0) / (t1 - t0)
    r1 = table(ni + 1, ti) + (table(ni + 1, ti + 1) - table(ni + 1, ti)) * (rte - t0) / (t1 - t0)
    rec = r0 + (r1 - r0) * (rne - n0) / (n1 - n0)
    out.update({
        "status": "evaluated",
        "branch": "logne_logT_grid",
        "aij_s^-1": 10.0 ** rec,
        "wavelength_A": wav,
        "log10_aij": rec,
        "log10_ne_used": rne,
        "log10_temperature_used": rte,
        "density_bracket_index0": ni,
        "temperature_bracket_index0": ti,
        "notes": ";".join(notes),
    })
    return out


def evaluate_type71_ucalc_record(
    decoded_record: Mapping[str, Any],
    *,
    temperature_k: float,
    electron_density_cm3: float,
    ptmp1: float,
    ptmp2: float,
) -> dict[str, Any]:
    """Evaluate the complete XSTAR type-71 ``ucalc`` rate pair."""
    calt = evaluate_calt71_record(
        decoded_record,
        temperature_k=temperature_k,
        electron_density_cm3=electron_density_cm3,
    )
    p1, p2 = float(ptmp1), float(ptmp2)
    aij = calt.get("aij_s^-1")
    ans2_uncapped = float(aij) * (p1 + p2) if calt.get("status") == "evaluated" and aij is not None else None
    ints = _int_list(decoded_record.get("ints") or decoded_record.get("raw_ints"))
    ca_low_ion_code = ints[5] if len(ints) >= 6 else None
    special_ca_cap = ca_low_ion_code in {96, 97}
    ans2 = min(ans2_uncapped, 1.0e10) if ans2_uncapped is not None and special_ca_cap else ans2_uncapped
    return {
        **calt,
        "ans1_upward_s^-1": 0.0 if ans2 is not None else None,
        "ans2_downward_s^-1": ans2,
        "ans2_before_special_ca_cap_s^-1": ans2_uncapped,
        "special_ca_i_ca_ii_cap_applied": bool(special_ca_cap and ans2_uncapped is not None and ans2 < ans2_uncapped),
        "type71_idat6_code": ca_low_ion_code,
        "calt71_density_argument_semantics": "ucalc.f90 passes den=xpx directly",
        "ptmp1": p1,
        "ptmp2": p2,
        "ptmp_sum": p1 + p2,
        "source_formula": "calt71.f90 A(ne,T); ucalc.f90 type71 ans1=0, ans2=A*(ptmp1+ptmp2)",
    }


__all__ = ["evaluate_calt71_record", "evaluate_type71_ucalc_record"]
