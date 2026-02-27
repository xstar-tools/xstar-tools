#!/usr/bin/env python3
"""
xstar_atomic_extract_collisions_v2b.py

Second-pass collisional-excitation extractor - patched v2b marker 2026-05-18 for XSTAR's packed atdb.fits.

This script builds on:
  * xstar_atomic_hierarchy.py
  * xstar_atomic_extract_lines_v2.py

It decodes bound-bound collisional records (rate_type=3) and joins them to
validated XSTAR level and radiative-line information.

Implemented/decoded data types
------------------------------
  51 : OP/CHIANTI Burgess-Tully effective collision strengths
       - XSTAR ucalc.f90: type 51
       - idat[0] = BT transition type
       - idat[1], idat[2] = level indices, then reordered by energy
       - rdat[0] = transition energy in Ryd
       - rdat[1] = BT scaling parameter c
       - rdat[2:] = 5- or 9-point scaled effective collision strengths

  56 : tabulated effective collision strengths, Bautista
       - XSTAR ucalc.f90: type 56
       - idat[0], idat[1] = level indices, then reordered by energy
       - rdat[0:ntmp] = log10(T/K) grid
       - rdat[ntmp:2*ntmp] = effective collision strength Upsilon(T)

  63 : Bautista n,l algorithmic collision records
       - XSTAR ucalc.f90: type 63
       - level mapping inferred from final integer fields
       - v2 evaluates nf != ni and |Delta l|=1 by translating anl1/erc
       - same-n l-changing/amcrs branch is evaluated with the ecm=0 velimp branch

  98 : CHIANTI 2016 Burgess-Tully effective collision strengths
       - XSTAR ucalc.f90: type 98
       - idat[0], idat[1] = level indices, then reordered by energy
       - idat[-2] = BT transition type
       - rdat[0] = transition energy in Ryd
       - rdat[2] = BT scaling parameter c
       - rdat[3:3+ntem] = scaled temperature grid
       - rdat[3+ntem:3+2*ntem] = scaled collision-strength grid

Rate coefficient convention
---------------------------
For records where an effective collision strength Upsilon(T) can be evaluated,
this script reports the standard XSTAR-equivalent coefficients:

  q_excitation   = 8.626e-6 * Upsilon(T) * exp(-DeltaE/kT) / (g_lower sqrt(T))
  q_deexcitation = 8.626e-6 * Upsilon(T)                  / (g_upper sqrt(T))

with T in K, DeltaE and kT in eV, and q in cm^3 s^-1.

Examples
--------
# Summary of O VIII collision records
python xstar_atomic_extract_collisions_v2b.py ./xstar/data/atdb.fits \
  --element O --ion-stage 8 --summary

# Search O VIII collisional excitation connected to Ly-alpha upper levels
python xstar_atomic_extract_collisions_v2b.py ./xstar/data/atdb.fits \
  --element O --ion-stage 8 --search --lower-level 1 --limit 20

# Evaluate at temperatures useful for CIE/photoionized-plasma tests
python xstar_atomic_extract_collisions_v2b.py ./xstar/data/atdb.fits \
  --element O --ion-stage 8 --search --lower-level 1 \
  --temperatures 1e5 1e6 1e7 --limit 20

# Export compact tables
python xstar_atomic_extract_collisions_v2b.py ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --summary-csv o8_collisions_summary.csv \
  --grid-csv o8_collisions_grid.csv \
  --eval-csv o8_collisions_eval.csv \
  --temperatures 1e5 1e6 1e7
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from .hierarchy import ATDB, SYMBOL_TO_Z, IndexedRecord
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Could not import xstar_atomic_hierarchy.py. Put this script in the same "
        "directory as xstar_atomic_hierarchy.py. Original error: " + repr(exc)
    )

try:
    from .lines import extract_levels, level_maps, roman, write_csv
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Could not import xstar_atomic_extract_lines_v2.py. Put this script in the same "
        "directory as xstar_atomic_extract_lines_v2.py. Original error: " + repr(exc)
    )

HC_EV_A = 12398.4016
RYD_EV = 13.605692
KB_EV_PER_K = 8.61707e-5
QCOEF = 8.626e-6  # cm^3 s^-1 K^1/2, XSTAR 8.626e-8 with t=T/1e4

COLLISION_DATA_TYPES = {51, 56, 63, 98}


def choose_z(element: Optional[str]) -> Optional[int]:
    if not element:
        return None
    text = element.strip()
    if text.isdigit():
        return int(text)
    z = SYMBOL_TO_Z.get(text.upper())
    if z is None:
        raise ValueError(f"Unknown element: {element}")
    return z


def safe_int(x):
    try:
        return int(x)
    except Exception:
        return None


def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def row_match(record: IndexedRecord, z: Optional[int], ion_stage: Optional[int]) -> bool:
    if z is not None and record.element_z != z:
        return False
    if ion_stage is not None and record.ion_stage != ion_stage:
        return False
    return True


def preview_list(values: Iterable, max_n: int = 16) -> str:
    vals = list(values) if values is not None else []
    if len(vals) <= max_n:
        return json.dumps(vals)
    return json.dumps(vals[:max_n] + [f"... {len(vals)-max_n} more"])


def physical_order(a: Optional[int], b: Optional[int], energies: Dict[int, float]) -> Tuple[Optional[int], Optional[int]]:
    if a is None or b is None:
        return a, b
    ea = energies.get(int(a))
    eb = energies.get(int(b))
    if ea is None or eb is None:
        return int(a), int(b)
    if ea <= eb:
        return int(a), int(b)
    return int(b), int(a)


def delta_from_levels(lower: Optional[int], upper: Optional[int], energies: Dict[int, float]) -> Optional[float]:
    if lower is None or upper is None:
        return None
    lo = energies.get(int(lower))
    up = energies.get(int(upper))
    if lo is None or up is None:
        return None
    return abs(float(up) - float(lo))


def q_rates_from_upsilon(upsilon: Optional[float], delta_e_ev: Optional[float], g_lower: Optional[float], g_upper: Optional[float], temperature_k: float) -> Tuple[Optional[float], Optional[float]]:
    if upsilon is None or delta_e_ev is None or g_lower in (None, 0, 0.0) or g_upper in (None, 0, 0.0):
        return None, None
    if temperature_k <= 0:
        return None, None
    kT = KB_EV_PER_K * temperature_k
    if kT <= 0:
        return None, None
    rootT = math.sqrt(temperature_k)
    try:
        u = max(0.0, float(upsilon))
        q_exc = QCOEF * u * math.exp(-float(delta_e_ev) / kT) / (float(g_lower) * rootT)
        q_deexc = QCOEF * u / (float(g_upper) * rootT)
        return q_exc, q_deexc
    except Exception:
        return None, None


# ----------------------------------------------------------------------
# Burgess-Tully spline helpers, translated from XSTAR upsil.f90/upsiln.f90
# ----------------------------------------------------------------------

def splinem_5(p: Sequence[float], x: float) -> float:
    """XSTAR splinem.f90 5-point spline for x in approximately [0, 1]."""
    p1, p2, p3, p4, p5 = [float(v) for v in p[:5]]
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


def natural_spline_y2(x: Sequence[float], y: Sequence[float]) -> List[float]:
    """Natural cubic spline second derivatives, following prepspline.f90."""
    n = len(x)
    if n < 2:
        return [0.0] * n
    y2 = [0.0] * n
    u = [0.0] * n
    y2[0] = 0.0
    u[0] = 0.0
    for i in range(1, n - 1):
        denom = x[i+1] - x[i-1]
        if denom == 0:
            continue
        sig = (x[i] - x[i-1]) / denom
        p = sig * y2[i-1] + 2.0
        y2[i] = (sig - 1.0) / p
        term = (y[i+1] - y[i]) / (x[i+1] - x[i]) - (y[i] - y[i-1]) / (x[i] - x[i-1])
        u[i] = (6.0 * term / denom - sig * u[i-1]) / p
    y2[-1] = 0.0
    for k in range(n - 2, -1, -1):
        y2[k] = y2[k] * y2[k+1] + u[k]
    return y2


def spline_eval(xa: Sequence[float], ya: Sequence[float], y2a: Sequence[float], x: float) -> float:
    """Evaluate a natural cubic spline, with endpoint clamping for robustness."""
    n = len(xa)
    if n == 0:
        return float("nan")
    if n == 1:
        return float(ya[0])
    if x <= xa[0]:
        return float(ya[0])
    if x >= xa[-1]:
        return float(ya[-1])
    klo = 0
    khi = n - 1
    while khi - klo > 1:
        k = (khi + klo) // 2
        if xa[k] > x:
            khi = k
        else:
            klo = k
    h = xa[khi] - xa[klo]
    if h == 0:
        return float(ya[klo])
    a = (xa[khi] - x) / h
    b = (x - xa[klo]) / h
    return (a*ya[klo] + b*ya[khi] + ((a*a*a-a)*y2a[klo] + (b*b*b-b)*y2a[khi]) * (h*h) / 6.0)


def upsil_bt_original(k: int, eij_ryd: float, c: float, scaled: Sequence[float], temperature_k: float) -> Optional[float]:
    """XSTAR upsil.f90 for 5-point BT records."""
    if eij_ryd <= 0 or temperature_k <= 0 or len(scaled) < 5:
        return None
    e = abs(temperature_k / (1.57888e5 * eij_ryd))
    if k in (1, 4):
        denom = math.log(e + c)
        if denom == 0:
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
        y /= (e + 1.0)
    elif k == 4:
        y *= math.log(e + c)
    return float(y)


def upsil_bt_general(k: int, eij_ryd: float, c: float, xgrid: Sequence[float], ygrid: Sequence[float], temperature_k: float) -> Optional[float]:
    """XSTAR upsiln.f90 for general BT spline records."""
    if eij_ryd <= 0 or temperature_k <= 0 or len(xgrid) < 2 or len(xgrid) != len(ygrid):
        return None
    kte = temperature_k / eij_ryd / 1.57888e5
    if k in (1, 4):
        denom = math.log(kte + c)
        if denom == 0:
            return None
        xt = 1.0 - math.log(c) / denom
    elif k in (2, 3, 5, 6):
        xt = kte / (kte + c)
    else:
        return None
    y2 = natural_spline_y2(xgrid, ygrid)
    sups = spline_eval(xgrid, ygrid, y2, xt)
    if k == 1:
        ups = sups * math.log(kte + math.e)
    elif k == 2:
        ups = sups
    elif k == 3:
        ups = sups / (kte + 1.0)
    elif k == 4:
        ups = sups * math.log(kte + c)
    elif k == 5:
        ups = sups / kte if kte != 0 else None
    elif k == 6:
        ups = 10.0 ** sups
    else:
        ups = None
    return None if ups is None else float(ups)


def interp_type56_upsilon(logT_grid: Sequence[float], ups_grid: Sequence[float], temperature_k: float) -> Optional[float]:
    if len(logT_grid) == 0 or len(logT_grid) != len(ups_grid) or temperature_k <= 0:
        return None
    x = math.log10(temperature_k)
    if len(logT_grid) == 1:
        return float(ups_grid[0])
    # XSTAR linearly interpolates in logT but not logUpsilon, with max(1e-48,...)
    pairs = sorted(zip([float(v) for v in logT_grid], [float(v) for v in ups_grid]))
    xs = [p[0] for p in pairs]
    ys = [max(1.0e-48, p[1]) for p in pairs]
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        if xs[i] <= x <= xs[i+1]:
            return ys[i] + (ys[i+1] - ys[i]) * (x - xs[i]) / (xs[i+1] - xs[i] + 1e-300)
    return ys[-1]




# ----------------------------------------------------------------------
# Type-63 Bautista n,l algorithmic evaluator
# ----------------------------------------------------------------------

def xstar_expo(x: float) -> float:
    """XSTAR expo.f90: exp(x) limited to [-60, 60]."""
    return math.exp(min(max(float(x), -60.0), 60.0))


def dfact_log(n: int) -> float:
    """XSTAR dfact.f90: log(n!), with n<=0 returning 0 by Fortran loop behavior."""
    try:
        n = int(n)
    except Exception:
        return 0.0
    if n <= 0:
        return 0.0
    return math.lgamma(n + 1.0)


def hgf_int(ia: int, ib: int, ic: int, x: float) -> float:
    """XSTAR hgf.f90 finite hypergeometric polynomial for integer parameters."""
    ia = int(ia)
    ib = int(ib)
    ic = int(ic)
    i = min(-ia, -ib)
    ser = 1.0
    hyp = 1.0
    if i < 0:
        return hyp
    for n in range(0, i + 1):
        den = (n + 1.0) * (ic + n)
        if den == 0:
            return float("nan")
        ser = ser * (ia + n) * (ib + n) * x / den
        hyp += ser
    return hyp


def anl1_py(ni: int, nf: int, lf: int, iq: int) -> Tuple[float, float]:
    """Translate XSTAR anl1.f90.

    Returns (alm, alp), the A-value-like angular factors used by type-63
    collision redistribution. This follows the original loop and branch logic.
    """
    ni = int(ni)
    nf = int(nf)
    lf = int(lf)
    iq = int(iq)
    alm = 0.0
    alp = 0.0
    if ni <= 0 or nf <= 0 or iq <= 0:
        return alm, alp
    for li in range(lf - 1, lf + 2, 2):
        if li < 0:
            continue
        if lf > li:
            n = nf
            np_ = ni
            l = lf
        else:
            n = ni
            np_ = nf
            l = li
        if n == np_:
            continue
        try:
            x1 = dfact_log(n + l)
            x2 = dfact_log(np_ + l - 1)
            x3 = dfact_log(2 * l - 1)
            x4 = dfact_log(n - l - 1)
            x5 = dfact_log(np_ - l)
            ia1 = -n + l + 1
            ia2 = ia1 - 2
            ib = -np_ + l
            ic = 2 * l
            x = -4.0 * n * np_ / ((n - np_) * (n - np_))
            y1 = hgf_int(ia1, ib, ic, x)
            y2 = hgf_int(ia2, ib, ic, x)
            rev = abs(n - np_)
            rn = float(n + np_)
            tlog = (l + 1) * math.log(4.0 * float(n * np_)) + (rn - 2.0*l - 2.0) * math.log(float(rev))
            tlog = tlog - math.log(4.0) - rn * math.log(rn)
            diff = abs(y1 - y2 * (float(rev) / rn) ** 2)
            if diff <= 0.0:
                continue
            ylog = math.log(diff) + tlog
            elog = 2.0 * ylog + x1 + x2 - 2.0*x3 - x4 - x5
            # Avoid numerical overflow; XSTAR data only need finite positive values.
            if elog < -745:
                t = 0.0
            elif elog > 700:
                t = math.exp(700)
            else:
                t = math.exp(elog)
            an = 2.6761e09 * (iq ** 4) * max(li, lf) * t / (2.0 * li + 1.0)
            dum = (1.0/(nf*nf) - 1.0/(ni*ni)) ** 3
            an *= dum
            if li < lf:
                alm = an
            if li > lf:
                alp = an
        except Exception:
            continue
    return float(alm), float(alp)


def impcfn_py(x: float) -> Tuple[float, float]:
    """Translate XSTAR impcfn.f90."""
    x = float(x)
    if x <= 0:
        x = 1e-300
    a = [0.9947187, 0.6030883, -2.372843, 1.864266, -0.6305845, 8.1104480e-02]
    b = [0.2551543, -0.5455462, 0.3096816, 4.2568920e-02, -2.0123060e-02, -4.9607030e-03]
    pi = math.pi
    if x <= 2.0:
        xsi = 0.0
        phi = 0.0
        y = math.log(x)
        for n in range(6):
            xsi += a[n] * x ** n
            phi += b[n] * y ** n
        if x == 1.0:
            phi = b[0]
        if x < 0.05:
            xsi = 1.0 + 0.01917 / 0.05 * x
            y = math.log(1.1229 / x)
            phi = y + x*x/4.0 * (1.0 - 2.0*y*y)
    else:
        xsi = pi * x * math.exp(-2.0*x) * (1.0 + 0.25/x + 1.0/(32.0*x*x))
        phi = pi/2.0 * math.exp(-2.0*x) * (1.0 + 0.25/x - 3.0/(32.0*x*x))
    return float(xsi), float(phi)


def impactn_py(n: int, m: int, temp: float, ic: int, amn: float, *, max_outer: int = 10000) -> float:
    """Translate XSTAR impactn.f90; returns cmm, the symmetrical collision quantity.

    The original code uses an adaptive impact-parameter integration with a goto loop.
    max_outer is a safety guard only; normal records converge quickly.
    """
    n = int(n); m = int(m); ic = int(ic); temp = float(temp); amn = float(amn)
    if n <= 0 or m <= 0 or ic <= 0 or temp <= 0.0 or amn <= 0.0:
        return 0.0
    xm = 157888.0 * float(ic * ic) / temp / float(m * m)
    if xm > 60.0:
        return 0.0
    rm = 1.0
    z1 = 1.0
    tk = 8.617e-5 * temp
    inc = 1
    jm = 90 * inc
    ecm = 109737.0 * float(ic * ic) * (1.0/float(n*n) - 1.0/float(m*m))
    ecm3 = ecm ** 3
    ecm = -ecm
    if ecm3 == 0.0:
        return 0.0
    psi = 1.644e5 * amn / ecm3
    po = (5.0 * float(n*n) + 1.0) / 4.0 / float(ic)
    cr = 0.0
    fi = 0.0
    wo = 0.0
    b = 10.0
    ev = abs(ecm) / 8065.48
    outer = 0
    while True:
        outer += 1
        if outer > max_outer:
            break
        delb = b / 100.0 / float(inc)
        jumped = False
        for _j in range(1, jm + 1):
            b = b - delb
            if b <= 0.0:
                b = 1e-300
            xsi, phi = impcfn_py(b)
            inside = 2.0 * xsi * psi
            if inside < 0.0:
                continue
            w = float(ic) * rm * ev / b * math.sqrt(inside)
            wi = w + ecm / 8065.48 / 2.0
            if wi / tk >= 100.0:
                jumped = True
                break
            if wi <= 0.0:
                continue
            if w == 0.0:
                continue
            bo = po * ev / 2.0 / w * math.sqrt(max(wi * rm / 13.60, 0.0))
            _xsw, phw = impcfn_py(bo)
            ff = min((xsi/2.0 + phi), phw)
            # XSTAR line 107: only strong coupling is used.
            ff = (xsi/2.0 + phi)
            ff = ff * math.exp(-wi / tk)
            crinc = (fi + ff) / 2.0 * (wi - wo)
            cr += crinc
            if cr < 1.0e-20:
                continue
            fi = ff
            wo = wi
            if (crinc / cr < 1.0e-5) and (crinc > 1.0e-7):
                jumped = True
                break
        if jumped:
            break
    if tk == 0.0:
        return 0.0
    cr = 6.900e-5 * z1*z1 * math.sqrt(rm / temp) * psi * cr / tk
    cmm = cr * m * m * math.exp(min(xm, 700.0))
    return float(max(0.0, cmm))


def expint_scaled_py(x: float) -> float:
    """Translate XSTAR expint.f90.

    Returns em1 = x*exp(x)*E1(x) using the same approximations as XSTAR.
    """
    x = float(x)
    if x > 1.0:
        b1 = 9.5733223454
        b2 = 25.6329561486
        b3 = 21.0996530827
        b4 = 3.9584969228
        c1 = 8.5733287401
        c2 = 18.0590169730
        c3 = 8.6347608925
        c4 = 0.2677737343
        return (x**4 + c1*x**3 + c2*x*x + c3*x + c4) / (x**4 + b1*x**3 + b2*x*x + b3*x + b4)
    a0 = -0.57721566
    a1 = 0.99999193
    a2 = -0.24991055
    a3 = 0.05519968
    a4 = -0.00976004
    a5 = 0.00107857
    if x > 0.0:
        e1 = a0 + a1*x + a2*x*x + a3*x**3 + a4*x**4 + a5*x**5 - math.log(x)
    elif x < 0.0:
        e1 = -a0 + a1*x + a2*x*x + a3*x**3 + a4*x**4 + a5*x**5 - math.log(-x)
    else:
        return float("inf")
    return e1 * x * xstar_expo(x)


def eint_py(t: float) -> Tuple[float, float, float]:
    """Translate XSTAR eint.f90."""
    t = float(t)
    if t == 0.0:
        return 0.0, 0.0, 0.0
    ss = expint_scaled_py(t)
    e1 = ss / max(1.0e-34, t * xstar_expo(t))
    e2 = math.exp(-t) - t * e1
    e3 = 0.5 * (xstar_expo(-t) - t * e2)
    return float(e1), float(e2), float(e3)


def szcoll_py(ni: int, nj: int, tt: float, ic: int) -> float:
    """Translate XSTAR szcoll.f90 for ic>=10 branch of erc."""
    ni = int(ni); nj = int(nj); ic = int(ic); tt = float(tt)
    if ni <= 0 or nj <= ni or ic <= 0 or tt <= 0.0:
        return 0.0
    abethe = [1.30, 0.59, 0.38, 0.286, 0.229, 0.192, 0.164, 0.141, 0.121, 0.105, 0.100]
    hbethe = [1.48, 3.64, 5.93, 8.32, 10.75, 12.90, 15.05, 17.20, 19.35, 21.50, 2.15]
    rbethe = [1.83, 1.60, 1.53, 1.495, 1.475, 1.46, 1.45, 1.45, 1.46, 1.47, 1.48]
    fvg1 = [1.133, 1.0785, 0.9935, 0.2328, -0.1296]
    fvg2 = [-0.4059, -0.2319, 0.6282, -0.5598, 0.5299]
    fvg3 = [0.07014, 0.02947, 0.3887, -1.181, 1.47]
    eion = 1.578203e5
    const = 8.63e-6
    rn2 = (float(ni) / float(nj)) ** 2
    if ni == 1:
        g1, g2, g3 = fvg1[0], fvg2[0], fvg3[0]
    elif ni == 2:
        g1, g2, g3 = fvg1[1], fvg2[1], fvg3[1]
    else:
        g1 = fvg1[2] + fvg1[3]/ni + fvg1[4]/(ni*ni)
        g2 = (fvg2[2] + fvg2[3]/ni + fvg2[4]/(ni*ni)) / ni * (-1.0)
        g3 = (fvg3[2] + fvg3[3]/ni + fvg3[4]/(ni*ni)) / (ni*ni)
    xx = 1.0 - rn2
    if xx == 0.0:
        return 0.0
    gaunt = g1 + g2/xx + g3/(xx*xx)
    fnn = 1.9603 * gaunt / (xx**3) * ni / (nj**3)
    if ni < 11:
        an = abethe[ni-1]
        hn = hbethe[ni-1]
        rrn = rbethe[ni-1]
    else:
        an = abethe[10] / float(ni)
        hn = hbethe[10] * float(ni)
        rrn = rbethe[10]
    ann = fnn * 4.0 * (ni**4) / xx
    dnn = ann * hn * (xx**rrn - an*rn2)
    cnn = 1.12 * ni * ann * xx
    if (nj - ni) == 1:
        cnn *= math.exp(-0.006 * ((ni - 1)**6) / ic)
    yy = eion * ic * ic * (1.0/float(ni*ni) - 1.0/float(nj*nj)) / tt
    e1, _e2, _e3 = eint_py(yy)
    rate = const / math.sqrt(tt) / ni / ni / ic / ic * (dnn*math.exp(-yy) + (ann + yy*(cnn-dnn))*e1)
    return float(max(0.0, rate))


def erc_py(n: int, m: int, temp_k: float, ic: int, a_sum: float) -> Tuple[float, float]:
    """Translate XSTAR erc.f90.

    Returns (se, sd): excitation and de-excitation coefficients in cm^3/s.
    """
    n = int(n); m = int(m); ic = int(ic); t = float(temp_k); a = float(a_sum)
    if n <= 0 or m <= n or ic <= 0 or t <= 0.0:
        return 0.0, 0.0
    rn = float(n); rm = float(m); ric = float(ic)
    if ic != 1:
        if ic < 10:
            ym0 = 157803.0 * ic * ic / t / (m*m)
            if ym0 > 40.0:
                return 0.0, 0.0
            sm = impactn_py(n, m, t, ic, a)
            ym = 157803.0 * ric * ric / t / (rm*rm)
            xn = (1.0/(rn*rn) - 1.0/(rm*rm))
            yn = 157803.0 * ric * ric * xn / t
            s = sm / (rn*rn) / math.exp(min(ym, 700.0))
            sd = s * rn*rn / (rm*rm)
            se = s * math.exp(-yn) if yn < 40.0 else 0.0
            return float(max(0.0, se)), float(max(0.0, sd))
        se = szcoll_py(n, m, t, ic)
        ym = 157803.0 * ric * ric / t / (rm*rm)
        xn = (1.0/(rn*rn) - 1.0/(rm*rm))
        yn = 157803.0 * ric * ric * xn / t
        sd = se * math.exp(min(50.0, yn)) * (rn*rn) / (rm*rm)
        return float(max(0.0, se)), float(max(0.0, sd))

    # Neutral H branch from erc.f90. Rare for XSTAR ions but included for completeness.
    xn = (1.0/(rn*rn) - 1.0/(rm*rm))
    if xn == 0.0:
        return 0.0, 0.0
    f = -1.2456e-10 * a / (xn*xn)
    yn = 157803.0 * xn / t
    ym = 157803.0 / t / (rm*rm)
    z = 1.94 * xn * rn**0.43 + yn
    if n == 1:
        z = yn + 0.45 * xn
    dif = z - yn
    e1y_scaled = expint_scaled_py(yn)
    e1z_scaled = expint_scaled_py(z)
    # XSTAR expint returns scaled values; erc uses them as e1y/e1z directly.
    e2 = (1.0 - e1y_scaled)/yn - xstar_expo(-dif)*(1.0 - e1z_scaled)/z
    ann = -2.0 * f * rm*rm / xn / rn / rn
    bn = (4.0 - 18.63/rn + 36.24/(rn*rn) - 28.09/(rn**3)) / rn
    if n == 1:
        bn = -0.603
    bnn = (1.0 + 4.0/(xn*rn*rn*3.0) + bn/(rn**4*xn*xn)) * 4.0/(rm**3*xn*xn)
    s = ann*((1.0/yn + 0.5)*e1y_scaled/yn - (1.0/z + 0.5)*e1z_scaled*xstar_expo(-dif)/z)
    s += e2 * (bnn - ann*math.log(2.0/xn))
    s = 1.095e-10 * yn*yn * math.sqrt(t) * s / xn
    sd = s * rn/rm * rn/rm
    se = s * xstar_expo(-yn)
    return float(max(0.0, se)), float(max(0.0, sd))



def xstar_e1_from_scaled(x: float) -> float:
    """Return E1(x) from XSTAR's scaled expint approximation."""
    x = float(x)
    if x <= 0.0:
        return float("inf")
    return expint_scaled_py(x) / max(1.0e-300, x * xstar_expo(x))


def velimp_py(n: int, l: int, temp: float, ic: int, z1: float, rm: float, ne: float, sum_a: float) -> float:
    """Translate the ecm=0 branch of XSTAR velimp.f90.

    This is used by the type-63 same-n l-mixing branch through amcrs.f90.
    It returns the l -> l-1 l-changing collision coefficient in cm^3/s-like
    XSTAR units.  The density enters only through the impact-parameter cutoff.
    """
    n = int(n); l = int(l); ic = int(ic)
    temp = float(temp); z1 = float(z1); rm = float(rm); ne = float(ne); sum_a = float(sum_a)
    if n <= 0 or l <= 0 or l >= n or ic <= 0 or temp <= 0.0 or rm <= 0.0 or ne <= 0.0 or sum_a <= 0.0:
        return 0.0
    den = l * (n*n - l*l) + (l + 1) * (n*n - (l + 1)*(l + 1))
    dnl = 6.0 * z1 / ic * z1 / ic * n*n * (n*n - l*l - l - 1)
    if den <= 0.0 or dnl <= 0.0:
        return 0.0
    pi = 2.0 * math.acos(0.0)
    pa = 0.72 / sum_a
    pd = 6.90 * math.sqrt(temp / ne)
    alfa = 3.297e-12 * rm / temp
    b = 1.157 * math.sqrt(dnl)
    bb = b*b
    va = pd / pa
    vd = b / pd
    if va <= 0.0 or vd <= 0.0 or alfa <= 0.0:
        return 0.0
    vb = math.sqrt(va * vd)
    ava = alfa * va*va
    avb = alfa * vb*vb
    avd = alfa * vd*vd
    xa = xstar_expo(-ava)
    xb = xstar_expo(-avb)
    xd = xstar_expo(-avd)
    ea = xstar_e1_from_scaled(ava) if ava < 50.0 else 0.0
    eb = xstar_e1_from_scaled(avb)
    ed = xstar_e1_from_scaled(avd) if avd < 50.0 else 0.0
    if va > vd:
        if avb > 1.0e-3:
            cn = math.sqrt(pi*alfa) * (pa*pa*(2.0/alfa/alfa - xb*(vb**4 + 2.0*vb*vb/alfa + 2.0/alfa/alfa)) + bb*xb + 2.0*bb*eb - bb*ea)
        else:
            cn = math.sqrt(pi*alfa) * bb * (1.0 + avb*(1.0/3.0 - avb/4.0) + 2.0*eb - ea)
    else:
        if ava > 1.0e-3:
            ca = math.sqrt(pi*alfa) * pa*pa * (2.0/alfa/alfa - xa*(va**4 + 2.0*va*va/alfa + 2.0/alfa/alfa))
        else:
            ca = math.sqrt(pi*alfa) * pd*pd * va**4 * alfa * (1.0/3.0 - ava/4.0 + ava*ava/10.0)
        cad = math.sqrt(pi*alfa) * pd*pd / alfa * (xa*(1.0 + ava) - xd*(1.0 + avd))
        cd = math.sqrt(pi*alfa) * bb * (xd + ed)
        cn = ca + cad + cd
    cn = cn * l * (n*n - l*l) / den
    if not math.isfinite(cn):
        return 0.0
    return float(max(0.0, cn))


def evaluate_type63_same_n_lmixing(
    ni: int,
    li: int,
    nf: int,
    lf: int,
    iq: int,
    temperature_k: float,
    electron_density_cm3: float = 1.0,
    g_lower: Optional[float] = None,
    g_upper: Optional[float] = None,
) -> Tuple[Optional[float], Optional[float], Optional[float], dict]:
    """Evaluate XSTAR ucalc.f90 type-63 same-n l-changing branch.

    The branch calls amcrs with ecm forced to zero, which reduces to the
    Pengelly-Seaton/Hummer-Storey impact-parameter cutoff implemented in
    velimp.f90.  The returned rates are resolved between the two adjacent-l
    sublevels using the same detailed-balance convention as XSTAR.
    """
    diag = {
        "type63_case": "same_n_lmixing",
        "type63_reason": "",
        "type63_same_n_sum_A": None,
        "type63_same_n_cn_l_high_to_low_cm3_s": None,
        "type63_same_n_lii": None,
        "type63_same_n_lff": None,
        "type63_same_n_ne_cm^-3": electron_density_cm3,
        "type63_iq": iq,
    }
    vals = [ni, li, nf, lf, iq]
    if any(v is None for v in vals):
        diag["type63_reason"] = "missing quantum numbers or ionic charge"
        return None, None, None, diag
    ni = int(ni); nf = int(nf); li = int(li); lf = int(lf); iq = int(iq)
    if ni <= 0 or nf <= 0 or li < 0 or lf < 0 or iq <= 0:
        diag["type63_reason"] = "invalid quantum numbers or ionic charge"
        return None, None, None, diag
    if nf != ni:
        diag["type63_reason"] = "not_same_n"
        return None, None, None, diag
    if abs(lf - li) != 1:
        diag["type63_reason"] = "same_n_delta_l_not_equal_1"
        return None, None, None, diag
    if temperature_k <= 0.0 or electron_density_cm3 <= 0.0:
        diag["type63_reason"] = "nonpositive_temperature_or_density"
        return None, None, None, diag
    lff = min(lf, li)
    lii = max(lf, li)
    li1 = max(1, lff)
    sum_a = 0.0
    for nn in range(li1, ni):
        if lii >= 1:
            _alm, alp = anl1_py(ni, nn, lii - 1, iq)
            sum_a += alp
        if nn > lii + 1:
            alm, _alp = anl1_py(ni, nn, lii + 1, iq)
            sum_a += alm
    diag["type63_same_n_sum_A"] = sum_a
    diag["type63_same_n_lii"] = lii
    diag["type63_same_n_lff"] = lff
    if sum_a <= 0.0:
        diag["type63_reason"] = "nonpositive_same_n_radiative_sum"
        return None, None, sum_a, diag
    psi = 0.75 / (iq*iq) * lii / (2.0*lii + 1.0) * ni*ni * (ni*ni - lii*lii)
    # XSTAR ucalc passes tbig=t*1e4 because its internal temperature variable
    # is scaled.  Here the API temperature is already Kelvin, so pass it through.
    cn = velimp_py(ni, lii, temperature_k, iq, 1.0, 1800.0, electron_density_cm3, sum_a)
    diag["type63_same_n_cn_l_high_to_low_cm3_s"] = cn
    diag["type63_same_n_psi"] = psi
    if cn <= 0.0:
        diag["type63_reason"] = "nonpositive_same_n_lmixing_rate"
        return None, None, sum_a, diag
    gl = float(g_lower) if g_lower not in (None, 0, 0.0) else float(2*lff + 1)
    gu = float(g_upper) if g_upper not in (None, 0, 0.0) else float(2*lii + 1)
    # cn is for l_high -> l_low.  The reverse low-l -> high-l rate follows
    # the XSTAR detailed-balance factor.  Map this onto the energy-ordered
    # lower->upper / upper->lower convention used by xstar-atomic.
    if li > lf:  # lower level has higher l, upper has lower l
        q_lower_to_upper = cn
        q_upper_to_lower = cn * gl / gu if gu != 0.0 else None
    else:        # lower level has lower l, upper has higher l
        q_upper_to_lower = cn
        q_lower_to_upper = cn * gu / gl if gl != 0.0 else None
    diag["type63_reason"] = "evaluated_same_n_lmixing_amcrs_velimp"
    return q_lower_to_upper, q_upper_to_lower, sum_a, diag

def evaluate_type63_nf_ne_ni(ni: int, li: int, nf: int, lf: int, iq: int, temperature_k: float) -> Tuple[Optional[float], Optional[float], Optional[float], dict]:
    """Evaluate XSTAR ucalc.f90 type-63 branch for nf != ni and |lf-li|=1.

    Returns (q_excitation, q_deexcitation, angular_sum, diagnostics). The q values
    follow XSTAR ans1/ans2 before density multiplication: excitation low->high and
    de-excitation high->low when the decoded row is ordered by energy.
    """
    diag = {
        "type63_case": None,
        "type63_reason": "",
        "type63_angular_sum": None,
        "type63_aa1": None,
        "type63_n_lower_shell": None,
        "type63_n_upper_shell": None,
        "type63_iq": iq,
    }
    vals = [ni, li, nf, lf, iq]
    if any(v is None for v in vals):
        diag["type63_case"] = "not_evaluated"
        diag["type63_reason"] = "missing quantum numbers or ionic charge"
        return None, None, None, diag
    ni = int(ni); li = int(li); nf = int(nf); lf = int(lf); iq = int(iq)
    if ni <= 0 or nf <= 0 or li < 0 or lf < 0 or iq <= 0:
        diag["type63_case"] = "not_evaluated"
        diag["type63_reason"] = "invalid quantum numbers or ionic charge"
        return None, None, None, diag
    if nf == ni:
        diag["type63_case"] = "same_n"
        diag["type63_reason"] = "type63_same_n_lmixing_not_yet_implemented"
        return None, None, None, diag
    if abs(lf - li) != 1:
        diag["type63_case"] = "not_evaluated"
        diag["type63_reason"] = "delta_l_not_equal_1"
        return None, None, None, diag
    if temperature_k <= 0:
        diag["type63_case"] = "not_evaluated"
        diag["type63_reason"] = "nonpositive_temperature"
        return None, None, None, diag

    nu = max(ni, nf)
    nll = min(ni, nf)

    # In the XSTAR type-63 branch the shell sum is over the angular
    # momenta lff of the lower-n shell.  For common ground -> np records
    # (n_lower=1, l_lower=0, n_upper>1, l_upper=1), the literal Fortran
    # aa1 selector `if (lff.eq.lf ...)` leaves aa1=0 because the only
    # lower-shell lff is 0 while the upper level has lf=1.  For an explicit
    # Python table of energy-ordered transitions, the physically intended
    # branch factor is the A-value connecting the actual lower-shell l to
    # the actual upper-shell l.  We therefore compute the shell sum as in
    # XSTAR, then select aa1 explicitly from anl1(n_upper_shell,n_lower_shell,
    # l_lower_shell,iq).  The old Fortran-like selector is retained as
    # aa1_fortran_selector for diagnostics.
    lower_shell_l = li if ni == nll else lf
    upper_shell_l = lf if nf == nu else li

    sum_a = 0.0
    aa1_fortran_selector = 0.0
    for lff in range(0, nll):
        alm, alp = anl1_py(nu, nll, lff, iq)
        sum_a += alp * (2*lff + 3)
        if lff > 0:
            sum_a += alm * (2*lff - 1)
        # Literal ucalc.f90 selector, kept only as a diagnostic.
        if lff == lf and li > lf:
            aa1_fortran_selector = alp
        if lff == lf and li < lf:
            aa1_fortran_selector = alm

    aa1 = 0.0
    if 0 <= lower_shell_l < nll and abs(upper_shell_l - lower_shell_l) == 1:
        alm_b, alp_b = anl1_py(nu, nll, lower_shell_l, iq)
        aa1 = alp_b if upper_shell_l > lower_shell_l else alm_b

    diag["type63_case"] = "nf_ne_ni_delta_l_1"
    diag["type63_angular_sum"] = sum_a
    diag["type63_aa1"] = aa1
    diag["type63_aa1_fortran_selector"] = aa1_fortran_selector
    diag["type63_lower_shell_l"] = lower_shell_l
    diag["type63_upper_shell_l"] = upper_shell_l
    diag["type63_n_lower_shell"] = nll
    diag["type63_n_upper_shell"] = nu
    if sum_a <= 0.0:
        diag["type63_reason"] = "nonpositive_angular_sum"
        return None, None, sum_a, diag
    if aa1 <= 0.0:
        diag["type63_reason"] = "nonpositive_selected_branch_A"
        return None, None, sum_a, diag

    se, sd = erc_py(nll, nu, temperature_k, iq, sum_a)
    # Explicit lower-energy -> upper-energy and upper-energy -> lower-energy
    # coefficients.  se/sd are shell rates from erc; the branching factor
    # distributes them over the resolved l sublevels.
    q_exc = se * (2*upper_shell_l + 1) * aa1 / sum_a
    q_deexc = sd * (2*lower_shell_l + 1) * aa1 / sum_a
    diag["type63_reason"] = "evaluated"
    if aa1_fortran_selector <= 0.0:
        diag["type63_reason"] = "evaluated_with_explicit_branch_selector"
    diag["type63_se_shell_cm3_s"] = se
    diag["type63_sd_shell_cm3_s"] = sd
    return float(max(0.0, q_exc)), float(max(0.0, q_deexc)), sum_a, diag

# ----------------------------------------------------------------------
# Record decoder
# ----------------------------------------------------------------------

def decode_collision_record(db: ATDB, r: IndexedRecord, labels: Dict[int, str], energies: Dict[int, float], gs: Dict[int, float], level_by_index: Dict[int, dict]) -> Tuple[dict, List[dict]]:
    h = db.header(r.recno)
    rd = [float(x) for x in db.real_slice(h)]
    it = [int(x) for x in db.int_slice(h)]
    ch = db.char_slice(h)

    source_format = "unknown"
    lower = upper = None
    eij_ryd = None
    c_bt = None
    bt_type = None
    bt_x = []
    bt_y = []
    logT_grid = []
    ups_grid = []
    grid_rows: List[dict] = []
    notes = ""

    if r.data_type == 51:
        source_format = "BT_CHIANTI_pre2016_type51"
        bt_type = safe_int(it[0]) if len(it) > 0 else None
        lev_a = safe_int(it[2]) if len(it) > 2 else None
        lev_b = safe_int(it[1]) if len(it) > 1 else None
        lower, upper = physical_order(lev_a, lev_b, energies)
        eij_ryd = safe_float(rd[0]) if len(rd) > 0 else None
        c_bt = safe_float(rd[1]) if len(rd) > 1 else None
        if len(rd) == 7:
            bt_x = [0.0, 0.25, 0.5, 0.75, 1.0]
            bt_y = rd[2:7]
            notes = "5-point original BT spline; evaluated with XSTAR splinem/upsil translation"
        elif len(rd) == 11:
            bt_x = [0.125 * i for i in range(9)]
            bt_y = rd[2:11]
            notes = "9-point BT spline; evaluated with XSTAR upsiln translation"
        else:
            notes = f"unexpected nreal={len(rd)} for type 51"
    elif r.data_type == 56:
        source_format = "tabulated_upsilon_type56"
        lev_a = safe_int(it[0]) if len(it) > 0 else None
        lev_b = safe_int(it[1]) if len(it) > 1 else None
        lower, upper = physical_order(lev_a, lev_b, energies)
        ntmp = len(rd) // 2
        logT_grid = rd[:ntmp]
        ups_grid = rd[ntmp:2*ntmp]
        notes = "tabulated Upsilon(log10 T[K]); linear interpolation follows ucalc type 56"
        for j, (lt, u) in enumerate(zip(logT_grid, ups_grid), start=1):
            grid_rows.append({"grid_index": j, "grid_kind": "logT_Upsilon", "log10_T_K": lt, "temperature_K": 10.0**lt, "upsilon": u})
    elif r.data_type == 98:
        source_format = "BT_CHIANTI2016_type98"
        lev_a = safe_int(it[0]) if len(it) > 0 else None
        lev_b = safe_int(it[1]) if len(it) > 1 else None
        lower, upper = physical_order(lev_a, lev_b, energies)
        eij_ryd = safe_float(rd[0]) if len(rd) > 0 else None
        c_bt = safe_float(rd[2]) if len(rd) > 2 else None
        ntem = (len(rd) - 3) // 2 if len(rd) >= 3 else 0
        bt_x = rd[3:3+ntem]
        bt_y = rd[3+ntem:3+2*ntem]
        bt_type = safe_int(it[-2]) if len(it) >= 2 else None
        notes = "CHIANTI 2016 BT spline; evaluated with XSTAR upsiln translation"
    elif r.data_type == 63:
        source_format = "bautista_nl_algorithm_type63"
        # From ucalc type 63: idest1=idat[np1i-1+nidt-3], idest2=idat[np1i+nidt-3].
        # Converted to Python offsets: idat[nidt-4], idat[nidt-3].
        lev_a = safe_int(it[-4]) if len(it) >= 4 else None
        lev_b = safe_int(it[-3]) if len(it) >= 3 else None
        lower, upper = physical_order(lev_a, lev_b, energies)
        notes = "Bautista n,l algorithmic collision record; v2 evaluates nf!=ni and |Delta l|=1 via anl1/erc; same-n l-mixing/amcrs is diagnostic-only"
    else:
        source_format = f"unhandled_data_type_{r.data_type}"

    delta_e_ev = delta_from_levels(lower, upper, energies)
    wavelength_a = HC_EV_A / delta_e_ev if delta_e_ev and delta_e_ev > 0 else None
    if eij_ryd is not None and eij_ryd > 0:
        eij_ev_from_rdat = eij_ryd * RYD_EV
        wavelength_from_eij_a = HC_EV_A / eij_ev_from_rdat if eij_ev_from_rdat > 0 else None
    else:
        eij_ev_from_rdat = None
        wavelength_from_eij_a = None

    lower_level_row = level_by_index.get(lower, {}) if lower is not None else {}
    upper_level_row = level_by_index.get(upper, {}) if upper is not None else {}
    n_lower = lower_level_row.get("n_principal")
    l_lower = lower_level_row.get("orbital_l")
    n_upper = upper_level_row.get("n_principal")
    l_upper = upper_level_row.get("orbital_l")
    # For type 63, XSTAR's iq is idat[nidt-2] in Fortran, i.e. Python it[-2].
    type63_iq = safe_int(it[-2]) if (r.data_type == 63 and len(it) >= 2) else None
    type63_initial_level = lev_a if r.data_type == 63 else None
    type63_final_level = lev_b if r.data_type == 63 else None

    summary = {
        "record": r.recno,
        "element_z": r.element_z,
        "element": r.element_symbol,
        "ion_stage": r.ion_stage,
        "ion_roman": roman(r.ion_stage),
        "ion": r.ion_label,
        "charge": r.charge_label,
        "data_type": r.data_type,
        "rate_type": r.rate_type,
        "source_format": source_format,
        "lower_level": lower,
        "upper_level": upper,
        "lower_label": labels.get(lower, "") if lower is not None else "",
        "upper_label": labels.get(upper, "") if upper is not None else "",
        "g_lower": gs.get(lower) if lower is not None else None,
        "g_upper": gs.get(upper) if upper is not None else None,
        "n_lower": n_lower,
        "l_lower": l_lower,
        "n_upper": n_upper,
        "l_upper": l_upper,
        "type63_iq": type63_iq,
        "type63_initial_level": type63_initial_level,
        "type63_final_level": type63_final_level,
        "delta_e_level_eV": delta_e_ev,
        "wavelength_from_levels_A": wavelength_a,
        "energy_from_levels_keV": delta_e_ev / 1000.0 if delta_e_ev is not None else None,
        "eij_rdat_Ryd": eij_ryd,
        "eij_rdat_eV": eij_ev_from_rdat,
        "wavelength_from_rdat_A": wavelength_from_eij_a,
        "bt_transition_type": bt_type,
        "bt_scaling_c": c_bt,
        "n_bt_points": len(bt_y),
        "n_tabulated_points": len(ups_grid),
        "char_label": ch,
        "notes": notes,
        "type63_capability": (
            "not_type63" if r.data_type != 63 else
            "missing_quantum_numbers" if None in (n_lower, l_lower, n_upper, l_upper, type63_iq) else
            "type63_same_n_lmixing_evaluable" if int(n_lower) == int(n_upper) and abs(int(l_upper) - int(l_lower)) == 1 else
            "same_n_delta_l_not_equal_1" if int(n_lower) == int(n_upper) else
            "delta_l_not_equal_1" if abs(int(l_upper) - int(l_lower)) != 1 else
            "type63_nf_ne_ni_delta_l_1_evaluable"
        ),
        "nreal": r.nreal,
        "nint": r.nint,
        "nchar": r.nchar,
        "raw_reals": preview_list(rd),
        "raw_ints": preview_list(it),
    }

    if bt_y:
        for j, (xv, yv) in enumerate(zip(bt_x, bt_y), start=1):
            grid_rows.append({"grid_index": j, "grid_kind": "BT_scaled", "bt_x": xv, "bt_y": yv})

    return summary, grid_rows


def evaluate_collision_row(row: dict, temperature_k: float, grid_rows_for_record: List[dict], electron_density_cm3: float = 1.0) -> dict:
    dt = int(row["data_type"])
    ups = None
    q_exc = None
    q_deexc = None
    method = "not_evaluated"
    diagnostic = ""
    extra_diag = {}

    if dt == 56:
        logT = [g["log10_T_K"] for g in grid_rows_for_record if g.get("grid_kind") == "logT_Upsilon"]
        upsgrid = [g["upsilon"] for g in grid_rows_for_record if g.get("grid_kind") == "logT_Upsilon"]
        ups = interp_type56_upsilon(logT, upsgrid, temperature_k)
        method = "linear_logT_type56"
    elif dt == 51:
        bt_x = [g["bt_x"] for g in grid_rows_for_record if g.get("grid_kind") == "BT_scaled"]
        bt_y = [g["bt_y"] for g in grid_rows_for_record if g.get("grid_kind") == "BT_scaled"]
        k = row.get("bt_transition_type")
        eij = row.get("eij_rdat_Ryd")
        c = row.get("bt_scaling_c")
        if k is not None and eij is not None and c is not None:
            if len(bt_y) == 5:
                ups = upsil_bt_original(int(k), float(eij), float(c), bt_y, temperature_k)
                method = "BT_5pt_upsil_type51"
            elif len(bt_y) >= 2:
                ups = upsil_bt_general(int(k), float(eij), float(c), bt_x, bt_y, temperature_k)
                method = "BT_general_upsiln_type51"
        if ups is None:
            diagnostic = "missing_or_invalid_BT_inputs"
    elif dt == 98:
        bt_x = [g["bt_x"] for g in grid_rows_for_record if g.get("grid_kind") == "BT_scaled"]
        bt_y = [g["bt_y"] for g in grid_rows_for_record if g.get("grid_kind") == "BT_scaled"]
        k = row.get("bt_transition_type")
        eij = row.get("eij_rdat_Ryd")
        c = row.get("bt_scaling_c")
        if k is not None and eij is not None and c is not None:
            ups = upsil_bt_general(int(k), float(eij), float(c), bt_x, bt_y, temperature_k)
            method = "BT_general_upsiln_type98"
        if ups is None:
            diagnostic = "missing_or_invalid_BT_inputs"
    elif dt == 63:
        if row.get("n_lower") is not None and row.get("n_upper") is not None and int(row.get("n_lower")) == int(row.get("n_upper")):
            q_exc, q_deexc, _sum_a, diag = evaluate_type63_same_n_lmixing(
                row.get("n_lower"),
                row.get("l_lower"),
                row.get("n_upper"),
                row.get("l_upper"),
                row.get("type63_iq"),
                temperature_k,
                electron_density_cm3=electron_density_cm3,
                g_lower=row.get("g_lower"),
                g_upper=row.get("g_upper"),
            )
            method = diag.get("type63_reason") or "type63_same_n_not_evaluated"
            if method == "evaluated_same_n_lmixing_amcrs_velimp":
                method = "type63_same_n_lmixing_amcrs_velimp"
        else:
            q_exc, q_deexc, _sum_a, diag = evaluate_type63_nf_ne_ni(
                row.get("n_lower"),
                row.get("l_lower"),
                row.get("n_upper"),
                row.get("l_upper"),
                row.get("type63_iq"),
                temperature_k,
            )
            method = diag.get("type63_reason") or "type63_not_evaluated"
            if method in ("evaluated", "evaluated_with_explicit_branch_selector"):
                method = "type63_anl1_erc_nf_ne_ni_delta_l_1"
        diagnostic = diag.get("type63_reason", "")
        extra_diag = diag
    else:
        diagnostic = f"unhandled_data_type_{dt}"

    if dt != 63:
        q_exc, q_deexc = q_rates_from_upsilon(
            ups,
            row.get("delta_e_level_eV"),
            row.get("g_lower"),
            row.get("g_upper"),
            temperature_k,
        )

    out = {
        "record": row["record"],
        "element": row["element"],
        "ion_stage": row["ion_stage"],
        "ion_roman": row["ion_roman"],
        "data_type": row["data_type"],
        "rate_type": row["rate_type"],
        "source_format": row.get("source_format"),
        "lower_level": row["lower_level"],
        "upper_level": row["upper_level"],
        "lower_label": row["lower_label"],
        "upper_label": row["upper_label"],
        "n_lower": row.get("n_lower"),
        "l_lower": row.get("l_lower"),
        "n_upper": row.get("n_upper"),
        "l_upper": row.get("l_upper"),
        "type63_iq": row.get("type63_iq"),
        "delta_e_eV": row["delta_e_level_eV"],
        "wavelength_A": row["wavelength_from_levels_A"],
        "temperature_K": temperature_k,
        "electron_density_for_lmixing_cm^-3": electron_density_cm3,
        "upsilon": ups,
        "q_excitation_cm3_s": q_exc,
        "q_deexcitation_cm3_s": q_deexc,
        "eval_method": method,
        "eval_diagnostic": diagnostic,
    }
    for key in (
        "type63_case",
        "type63_reason",
        "type63_angular_sum",
        "type63_aa1",
        "type63_aa1_fortran_selector",
        "type63_lower_shell_l",
        "type63_upper_shell_l",
        "type63_n_lower_shell",
        "type63_n_upper_shell",
        "type63_se_shell_cm3_s",
        "type63_sd_shell_cm3_s",
        "type63_same_n_sum_A",
        "type63_same_n_cn_l_high_to_low_cm3_s",
        "type63_same_n_lii",
        "type63_same_n_lff",
        "type63_same_n_ne_cm^-3",
        "type63_same_n_psi",
    ):
        if key in extra_diag:
            out[key] = extra_diag[key]
    return out


def extract_collisions(db: ATDB, records: List[IndexedRecord], z: Optional[int], ion_stage: Optional[int], temperatures: Sequence[float], electron_density_cm3: float = 1.0) -> Tuple[List[dict], List[dict], List[dict]]:
    levels = extract_levels(db, records, z, ion_stage)
    level_by_index, labels, energies, gs = level_maps(levels)

    summary_rows: List[dict] = []
    grid_rows: List[dict] = []
    eval_rows: List[dict] = []
    grid_by_record: Dict[int, List[dict]] = {}

    for r in records:
        if not row_match(r, z, ion_stage):
            continue
        if r.rate_type != 3 and r.data_type not in COLLISION_DATA_TYPES:
            continue
        if r.data_type not in COLLISION_DATA_TYPES:
            continue
        summary, grid = decode_collision_record(db, r, labels, energies, gs, level_by_index)
        summary_rows.append(summary)
        expanded_grid = []
        for g in grid:
            gg = {
                "record": r.recno,
                "element": summary["element"],
                "ion_stage": summary["ion_stage"],
                "ion_roman": summary["ion_roman"],
                "data_type": summary["data_type"],
                "rate_type": summary["rate_type"],
                "lower_level": summary["lower_level"],
                "upper_level": summary["upper_level"],
                "lower_label": summary["lower_label"],
                "upper_label": summary["upper_label"],
                **g,
            }
            expanded_grid.append(gg)
        grid_by_record[r.recno] = expanded_grid
        grid_rows.extend(expanded_grid)

    summary_rows.sort(key=lambda x: (x.get("wavelength_from_levels_A") is None, x.get("wavelength_from_levels_A") or 1e99, x.get("record") or 0))
    if temperatures:
        for row in summary_rows:
            for T in temperatures:
                eval_rows.append(evaluate_collision_row(row, float(T), grid_by_record.get(row["record"], []), electron_density_cm3=electron_density_cm3))

    return summary_rows, grid_rows, eval_rows


def filter_rows(rows: List[dict], args) -> List[dict]:
    out = []
    for row in rows:
        if args.data_type is not None and row.get("data_type") != args.data_type:
            continue
        if args.lower_level is not None and row.get("lower_level") != args.lower_level:
            continue
        if args.upper_level is not None and row.get("upper_level") != args.upper_level:
            continue
        w = row.get("wavelength_from_levels_A")
        if args.wavelength_min is not None and (w is None or w < args.wavelength_min):
            continue
        if args.wavelength_max is not None and (w is None or w > args.wavelength_max):
            continue
        e = row.get("energy_from_levels_keV")
        if args.energy_min_kev is not None and (e is None or e < args.energy_min_kev):
            continue
        if args.energy_max_kev is not None and (e is None or e > args.energy_max_kev):
            continue
        out.append(row)
    return out


def counts_by(rows: List[dict], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        k = str(row.get(key))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: kv[0]))


def main() -> None:
    p = argparse.ArgumentParser(description="Extract collisional-excitation records from XSTAR atdb.fits")
    p.add_argument("fitsfile")
    p.add_argument("--element", help="Element symbol or Z, e.g. O or 8")
    p.add_argument("--ion-stage", type=int, help="Ion stage, e.g. 8 for O VIII")
    p.add_argument("--summary", action="store_true", help="Print compact summary")
    p.add_argument("--search", action="store_true", help="Print matching decoded collision rows as JSON")
    p.add_argument("--data-type", type=int, help="Filter data type, e.g. 51, 56, 63, 98")
    p.add_argument("--lower-level", type=int)
    p.add_argument("--upper-level", type=int)
    p.add_argument("--wavelength-min", type=float, help="Filter wavelength from level energies, Angstrom")
    p.add_argument("--wavelength-max", type=float, help="Filter wavelength from level energies, Angstrom")
    p.add_argument("--energy-min-kev", type=float)
    p.add_argument("--energy-max-kev", type=float)
    p.add_argument("--temperatures", nargs="*", type=float, default=[], help="Temperatures in Kelvin for q_ij evaluation")
    p.add_argument("--electron-density", type=float, default=1.0, help="Electron density cm^-3 used only for type-63 same-n l-mixing cutoff")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--summary-csv")
    p.add_argument("--grid-csv")
    p.add_argument("--eval-csv")
    args = p.parse_args()

    z = choose_z(args.element)
    db = ATDB(Path(args.fitsfile), load_reals=True)
    records, elements, ions = db.build_index()
    summary_rows, grid_rows, eval_rows = extract_collisions(db, records, z, args.ion_stage, args.temperatures, electron_density_cm3=args.electron_density)

    if args.summary_csv:
        write_csv(args.summary_csv, summary_rows)
    if args.grid_csv:
        write_csv(args.grid_csv, grid_rows)
    if args.eval_csv:
        write_csv(args.eval_csv, eval_rows)

    filtered = filter_rows(summary_rows, args)

    if args.summary:
        out = {
            "fitsfile": args.fitsfile,
            "element_filter": args.element,
            "z_filter": z,
            "ion_stage_filter": args.ion_stage,
            "n_collision_records": len(summary_rows),
            "n_grid_rows": len(grid_rows),
            "n_eval_rows": len(eval_rows),
            "counts_by_data_type": counts_by(summary_rows, "data_type"),
            "counts_by_source_format": counts_by(summary_rows, "source_format"),
        }
        print(json.dumps(out, indent=2))

    if args.search:
        out = {
            "query": {
                "element": args.element,
                "z": z,
                "ion_stage": args.ion_stage,
                "data_type": args.data_type,
                "lower_level": args.lower_level,
                "upper_level": args.upper_level,
                "wavelength_min_A": args.wavelength_min,
                "wavelength_max_A": args.wavelength_max,
                "energy_min_keV": args.energy_min_kev,
                "energy_max_keV": args.energy_max_kev,
                "temperatures_K": args.temperatures,
                "electron_density_for_lmixing_cm^-3": args.electron_density,
            },
            "n_matches": len(filtered),
            "matches": filtered[:args.limit],
        }
        if args.temperatures:
            filtered_records = {row["record"] for row in filtered[:args.limit]}
            out["evaluated_rates"] = [row for row in eval_rows if row["record"] in filtered_records]
        print(json.dumps(out, indent=2))

    if not (args.summary or args.search or args.summary_csv or args.grid_csv or args.eval_csv):
        print(json.dumps({
            "n_collision_records": len(summary_rows),
            "hint": "Use --summary, --search, or --summary-csv/--grid-csv/--eval-csv",
        }, indent=2))


if __name__ == "__main__":
    main()
