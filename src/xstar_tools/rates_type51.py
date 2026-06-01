"""Source-code-aligned XSTAR data-type 51 collision evaluator.

This module is intentionally independent of FITS/ATDB I/O.  It evaluates one
already-decoded Burgess--Tully record with the exact temperature and rate
conventions used by the type-51 branch of ``xstarlib/src/ucalc.f90``.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Sequence


def _as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return number if math.isfinite(number) else default
    except Exception:
        return default


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        number = float(value)
        return int(round(number)) if math.isfinite(number) else default
    except Exception:
        return default


def xstar_expo(value: float) -> float:
    """XSTAR ``expo.f90``: exponentiation limited to [-60, 60]."""
    return math.exp(min(max(float(value), -60.0), 60.0))


def splinem_5(points: Sequence[float], x: float) -> float:
    """Translate XSTAR ``splinem.f90`` for the original five-point BT grid."""
    p1, p2, p3, p4, p5 = [float(v) for v in points[:5]]
    s = 1.0 / 30.0
    s2 = 32.0 * s * (19.0*p1 - 43.0*p2 + 30.0*p3 - 7.0*p4 + p5)
    s3 = 160.0 * s * (-p1 + 7.0*p2 - 12.0*p3 + 7.0*p4 - p5)
    s4 = 32.0 * s * (p1 - 7.0*p2 + 30.0*p3 - 43.0*p4 + 19.0*p5)
    if x <= 0.25:
        x0 = x - 0.125
        t3 = 0.0
        t2 = 0.5 * s2
        t1 = 4.0 * (p2 - p1)
        t0 = 0.5 * (p1 + p2) - 0.015625 * t2
    elif x <= 0.5:
        x0 = x - 0.375
        t3 = 20.0 * s * (s3 - s2)
        t2 = 0.25 * (s2 + s3)
        t1 = 4.0 * (p3 - p2) - 0.015625 * t3
        t0 = 0.5 * (p2 + p3) - 0.015625 * t2
    elif x <= 0.75:
        x0 = x - 0.625
        t3 = 20.0 * s * (s4 - s3)
        t2 = 0.25 * (s3 + s4)
        t1 = 4.0 * (p4 - p3) - 0.015625 * t3
        t0 = 0.5 * (p3 + p4) - 0.015625 * t2
    else:
        x0 = x - 0.875
        t3 = 0.0
        t2 = 0.5 * s4
        t1 = 4.0 * (p5 - p4)
        t0 = 0.5 * (p4 + p5) - 0.015625 * t2
    return t0 + x0 * (t1 + x0 * (t2 + x0 * t3))


def _natural_spline_y2(x: Sequence[float], y: Sequence[float]) -> list[float]:
    n = len(x)
    if n < 2:
        return [0.0] * n
    y2 = [0.0] * n
    u = [0.0] * n
    for i in range(1, n - 1):
        denom = x[i + 1] - x[i - 1]
        if denom == 0.0:
            continue
        sig = (x[i] - x[i - 1]) / denom
        p = sig * y2[i - 1] + 2.0
        y2[i] = (sig - 1.0) / p
        term = (y[i + 1] - y[i]) / (x[i + 1] - x[i]) - (y[i] - y[i - 1]) / (x[i] - x[i - 1])
        u[i] = (6.0 * term / denom - sig * u[i - 1]) / p
    for k in range(n - 2, -1, -1):
        y2[k] = y2[k] * y2[k + 1] + u[k]
    return y2


def _spline_eval(xa: Sequence[float], ya: Sequence[float], y2a: Sequence[float], x: float) -> float:
    if x <= xa[0]:
        return float(ya[0])
    if x >= xa[-1]:
        return float(ya[-1])
    klo, khi = 0, len(xa) - 1
    while khi - klo > 1:
        k = (khi + klo) // 2
        if xa[k] > x:
            khi = k
        else:
            klo = k
    h = xa[khi] - xa[klo]
    if h == 0.0:
        return float(ya[klo])
    a = (xa[khi] - x) / h
    b = (x - xa[klo]) / h
    return a*ya[klo] + b*ya[khi] + ((a*a*a-a)*y2a[klo] + (b*b*b-b)*y2a[khi]) * h*h / 6.0


def upsil_type51_original(k: int, eij_ryd: float, c: float, scaled: Sequence[float], temperature_k: float) -> float | None:
    """Translate XSTAR ``upsil.f90`` for five-point type-51 records."""
    if eij_ryd <= 0.0 or temperature_k <= 0.0 or len(scaled) < 5:
        return None
    e = abs(temperature_k / (1.57888e5 * eij_ryd))
    if k in (1, 4):
        denom = math.log(e + c)
        if denom == 0.0:
            return None
        x = math.log((e + c) / c) / denom
    elif k in (2, 3):
        x = e / (e + c)
    else:
        return None
    y = splinem_5(scaled[:5], x)
    if k == 1:
        y *= math.log(e + 2.71828)
    elif k == 3:
        y /= e + 1.0
    elif k == 4:
        y *= math.log(e + c)
    return float(y)


def upsil_type51_general(k: int, eij_ryd: float, c: float, xgrid: Sequence[float], ygrid: Sequence[float], temperature_k: float) -> float | None:
    """Translate XSTAR ``upsiln.f90`` for nine-point type-51 records."""
    if eij_ryd <= 0.0 or temperature_k <= 0.0 or len(xgrid) < 2 or len(xgrid) != len(ygrid):
        return None
    kte = temperature_k / eij_ryd / 1.57888e5
    if k in (1, 4):
        denom = math.log(kte + c)
        if denom == 0.0:
            return None
        xt = 1.0 - math.log(c) / denom
    elif k in (2, 3, 5, 6):
        xt = kte / (kte + c)
    else:
        return None
    sups = _spline_eval(xgrid, ygrid, _natural_spline_y2(xgrid, ygrid), xt)
    if k == 1:
        value = sups * math.log(kte + math.e)
    elif k == 2:
        value = sups
    elif k == 3:
        value = sups / (kte + 1.0)
    elif k == 4:
        value = sups * math.log(kte + c)
    elif k == 5:
        value = sups / kte if kte != 0.0 else None
    elif k == 6:
        value = 10.0 ** sups
    else:
        value = None
    return None if value is None else float(value)


def evaluate_type51_ucalc_record(
    row: Mapping[str, Any],
    temperature_k: float,
    electron_density_cm3: float,
    grid_rows_for_record: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Evaluate one decoded XSTAR type-51 record exactly as ``ucalc.f90``.

    XSTAR evaluates the BT spline at a wavelength-dependent temperature floor,
    but uses the physical plasma temperature in the Maxwellian prefactor.  The
    returned ``ans1`` is lower-to-upper excitation and ``ans2`` is upper-to-
    lower de-excitation, both in s^-1 after multiplication by electron density.
    """
    result: Dict[str, Any] = {
        "data_type": 51,
        "status": "not_evaluated",
        "reason": "",
        "formula_source": "xstarlib/src/ucalc.f90 type-51 branch",
    }
    temperature_k = _as_float(temperature_k)
    electron_density_cm3 = _as_float(electron_density_cm3)
    if temperature_k is None or electron_density_cm3 is None or temperature_k <= 0.0 or electron_density_cm3 < 0.0:
        result["reason"] = "invalid_temperature_or_density"
        return result

    eij_ryd = _as_float(row.get("eij_rdat_Ryd"))
    c_bt = _as_float(row.get("bt_scaling_c"))
    bt_type = _as_int(row.get("bt_transition_type"))
    g_lower = _as_float(row.get("g_lower"))
    g_upper = _as_float(row.get("g_upper"))
    if None in (eij_ryd, c_bt, bt_type, g_lower, g_upper):
        result["reason"] = "missing_type51_record_inputs"
        return result
    if eij_ryd <= 0.0 or c_bt <= 0.0 or g_lower <= 0.0 or g_upper <= 0.0:
        result["reason"] = "invalid_type51_record_inputs"
        return result

    points = [row for row in grid_rows_for_record if str(row.get("grid_kind") or "") == "BT_scaled"]
    points.sort(key=lambda item: _as_int(item.get("grid_index"), 0) or 0)
    bt_x = [float(_as_float(item.get("bt_x"), 0.0) or 0.0) for item in points]
    bt_y = [float(_as_float(item.get("bt_y"), 0.0) or 0.0) for item in points]
    if len(bt_y) not in (5, 9):
        result["reason"] = f"unsupported_type51_bt_point_count:{len(bt_y)}"
        return result

    eij_ev = eij_ryd * 13.605692
    wavelength_a = 12398.4016 / eij_ev
    floor_k = 2.8777e6 / wavelength_a
    bt_temperature_k = max(temperature_k, floor_k)
    if len(bt_y) == 5:
        upsilon = upsil_type51_original(bt_type, eij_ryd, c_bt, bt_y, bt_temperature_k)
        method = "upsil_5point"
    else:
        upsilon = upsil_type51_general(bt_type, eij_ryd, c_bt, bt_x, bt_y, bt_temperature_k)
        method = "upsiln_9point"
    if upsilon is None or not math.isfinite(upsilon):
        result["reason"] = "type51_bt_evaluation_failed"
        return result

    t_xstar = temperature_k / 1.0e4
    tsq = math.sqrt(t_xstar)
    ekt_ev = 0.861707 * t_xstar
    delta = eij_ev / ekt_ev
    q_deexc = 8.626e-8 * upsilon / tsq / g_upper
    q_exc = q_deexc * g_upper * xstar_expo(-delta) / g_lower
    ans1 = q_exc * electron_density_cm3
    ans2 = q_deexc * electron_density_cm3
    result.update({
        "status": "evaluated",
        "spline_method": method,
        "bt_transition_type": bt_type,
        "bt_scaling_c": c_bt,
        "n_bt_points": len(bt_y),
        "eij_rdat_Ryd": eij_ryd,
        "eij_rdat_eV": eij_ev,
        "wavelength_from_rdat_A": wavelength_a,
        "temperature_K": temperature_k,
        "bt_temperature_floor_K": floor_k,
        "bt_effective_temperature_K": bt_temperature_k,
        "bt_temperature_floor_applied": bt_temperature_k > temperature_k,
        "electron_density_cm^-3": electron_density_cm3,
        "g_lower": g_lower,
        "g_upper": g_upper,
        "upsilon": upsilon,
        "delta_e_over_kT": delta,
        "q_excitation_cm3_s": q_exc,
        "q_deexcitation_cm3_s": q_deexc,
        "ans1_excitation_s^-1": ans1,
        "ans2_deexcitation_s^-1": ans2,
        "ans5_deexcitation_energy_erg_s^-1": ans2 * eij_ev * 1.602197e-12,
        "ans6_excitation_energy_erg_s^-1": ans1 * eij_ev * 1.602197e-12,
    })
    return result
