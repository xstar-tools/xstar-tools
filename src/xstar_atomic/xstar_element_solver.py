"""Pure-Python reference scaffold for XSTAR-like element-coupled solvers.

This module is intentionally a *reference/diagnostic* implementation, not a
fast production backend.  It mirrors the high-level XSTAR source-code flow
``calc_hmc_element -> calc_hmc_ion -> ucalc -> msolvelucy`` by building one
Python object for an element, with one ion block per selected charge state.

The current implementation assembles XSTAR-ATDB radiative and collisional rates
for each ion block and solves the requested He-like ion with the same
statistical-equilibrium machinery used by :mod:`xstar_atomic.solver`.  It also
records adjacent-ion coupling candidates from bound-free/recombination-like ATDB
records so that later versions can replace the placeholder source terms with
XSTAR-like recombination/photoionization coupling.

The design goal is to make the physics path explicit and testable before a C++
backend is added for speed.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from .hierarchy import ATDB, Z_TO_SYMBOL, roman
from .lines import choose_z, extract_levels, extract_lines
from .collisions import extract_collisions
from .recombination import extract_recombination_records, evaluate_records, allocation_levels
from .solver import (
    assemble_rate_matrix,
    build_collision_rates_for_T,
    build_graph_edges,
    build_level_set,
    build_radiative_transitions,
    classify_helike_triplet_line,
    connected_components,
    line_energy_erg,
    make_helike_triplet_diagnostics,
    make_line_output_rows,
    maybe_float,
    maybe_int,
    prune_null_rate_levels_for_solve,
    select_output_lines,
    solve_steady_state,
)

BOUND_FREE_RATE_TYPES = {1, 2, 5, 6, 7, 8}
BOUND_FREE_DATA_TYPES = {1, 2, 6, 7, 22, 30, 49, 53, 59, 70, 74, 95, 99}

# Terms whose rate coefficients can be evaluated in the current Python
# reference implementation and assembled as prototype adjacent-ion source terms.
# Many XSTAR adjacent-ion records (for example data type 53/74/99
# photoionization/DR resonance data and type 57/95 collisional ionization data)
# are deliberately catalogued but not converted to rates here, because doing so
# requires XSTAR's continuum/radiation-field and ion-balance context.
EVALUABLE_RECOMBINATION_DATA_TYPES = {1, 7, 8, 22, 30, 37, 38, 39}
PHOTOIONIZATION_LIKE_DATA_TYPES = {49, 53, 59, 70, 74, 85, 88, 99}
COLLISIONAL_IONIZATION_LIKE_DATA_TYPES = {57, 95}
SUPERLEVEL_CASCADE_DATA_TYPES = {70, 71, 74, 77, 99}


@dataclass
class IonBlockDiagnostics:
    element: str
    element_z: int
    ion_stage: int
    ion_label: str
    n_records: int
    n_levels_decoded: int
    n_levels_used: int
    n_radiative_lines_total: int
    n_radiative_lines_used: int
    n_collision_records_total: int
    n_collision_eval_rows_total: int
    n_collision_eval_rows_used: int
    n_graph_components: int
    n_graph_edges: int
    matrix_size: int
    matrix_nnz: int
    solve_status: str
    solver: str
    solver_warning: str


@dataclass
class CouplingCandidateSummary:
    element: str
    element_z: int
    lower_ion_stage: int
    upper_ion_stage: int
    n_candidate_records: int
    data_type_counts: Dict[str, int]
    rate_type_counts: Dict[str, int]
    status: str = "catalogued_not_yet_assembled"


def _counts(rows: Iterable[dict], key: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for row in rows:
        k = str(row.get(key, ""))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: kv[0]))


def write_csv(path: str | Path, rows: Sequence[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys: List[str] = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _solver_args(**kwargs) -> SimpleNamespace:
    defaults = dict(
        include_two_photon=False,
        include_superlevel=False,
        wavelength_min=None,
        wavelength_max=None,
        energy_min_kev=None,
        energy_max_kev=None,
        lower_level=None,
        upper_level=None,
        max_level=None,
        levels=None,
        collision_rate_scale=[],
        collision_record_scale=[],
        collision_record_direction_scale=[],
        type69_ground_excitation_mode="include",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _normalise_triplet(line_rows: Sequence[dict]) -> dict:
    sums = {"f": 0.0, "i": 0.0, "r": 0.0}
    for row in line_rows:
        comp = classify_helike_triplet_line(row)
        val = maybe_float(row.get("line_energy_emissivity_per_ion_erg_s^-1"))
        if comp in sums and val is not None and math.isfinite(val):
            sums[comp] += max(float(val), 0.0)
    total = sum(sums.values())
    if total > 0:
        frac = {f"{k}_fraction": sums[k] / total for k in ("f", "i", "r")}
    else:
        frac = {f"{k}_fraction": 0.0 for k in ("f", "i", "r")}
    R = sums["f"] / sums["i"] if sums["i"] > 0 else None
    G = (sums["f"] + sums["i"]) / sums["r"] if sums["r"] > 0 else None
    return {**{f"{k}_emissivity": sums[k] for k in ("f", "i", "r")}, **frac, "R": R, "G": G}


def _select_records(db: ATDB, z: int, ion_stage: int, *, use_cache: bool, cache_path: Optional[str]) -> list:
    return db.select_records(z=z, ion_stage=ion_stage, use_cache=use_cache, cache_path=cache_path)




def _safe_exp1(x: float) -> Optional[float]:
    """Return E1(x)=integral_x^inf exp(-t)/t dt with optional scipy fallback.

    This helper is used only for diagnostic type-95 Bryans CI evaluation.
    It avoids making scipy a hard runtime dependency; if scipy is unavailable,
    it uses stable small-x and large-x approximations sufficient for audit
    classification rather than precision production rates.
    """
    if not math.isfinite(x) or x <= 0.0:
        return None
    try:  # scipy is optional in pyproject [sparse]; do not require it.
        from scipy.special import exp1  # type: ignore
        val = float(exp1(x))
        return val if math.isfinite(val) and val >= 0.0 else None
    except Exception:
        pass
    gamma = 0.5772156649015329
    if x < 1.0:
        # E1(x) = -gamma - ln x - sum_{k>=1} (-x)^k/(k*k!)
        term = 1.0
        fact = 1.0
        ssum = 0.0
        for k in range(1, 80):
            fact *= k
            term = ((-x) ** k) / (k * fact)
            ssum += term
            if abs(term) < 1.0e-14:
                break
        val = -gamma - math.log(x) - ssum
        return max(val, 0.0) if math.isfinite(val) else None
    # Continued asymptotic series is adequate for audit at x >= 1.
    term = 1.0
    series = 1.0
    sign = -1.0
    for k in range(1, 80):
        term *= k / x
        add = sign * term
        series += add
        sign *= -1.0
        if abs(add) < 1.0e-14:
            break
        # Stop before divergent asymptotic tail dominates.
        if abs(add) > abs(series) * 10:
            break
    val = math.exp(-x) * series / x
    return max(val, 0.0) if math.isfinite(val) else None


def _interp_linear(x: float, xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if not xs or not ys or len(xs) != len(ys):
        return None
    pairs = sorted((float(a), float(b)) for a, b in zip(xs, ys) if math.isfinite(float(a)) and math.isfinite(float(b)))
    if not pairs:
        return None
    if x <= pairs[0][0]:
        return pairs[0][1]
    if x >= pairs[-1][0]:
        return pairs[-1][1]
    for (x0, y0), (x1, y1) in zip(pairs[:-1], pairs[1:]):
        if x0 <= x <= x1:
            if abs(x1 - x0) < 1.0e-300:
                return y0
            return y0 + (x - x0) * (y1 - y0) / (x1 - x0)
    return None


def _guess_ucalc_levels(data_type: int, rate_type: int, ints: Sequence[int], *, nlevp: Optional[int] = None) -> dict:
    """Infer XSTAR ucalc local level/continuum indices from packed integers.

    The returned values are best-effort diagnostics matching the formulas seen
    in ``ucalc.f90``.  They are not used to alter the matrix unless an evaluator
    explicitly supports the record class.
    """
    vals = [int(x) for x in ints]
    out = {"idest1_guess": None, "idest2_guess": None, "idest3_guess": None, "idest4_guess": None, "nlevp_used": nlevp}
    try:
        if data_type == 53:
            if len(vals) >= 2:
                out["idest1_guess"] = vals[-2]
            if len(vals) >= 3 and nlevp is not None:
                out["idest2_guess"] = int(nlevp) + vals[-3] - 1
            if len(vals) >= 1:
                out["idest3_guess"] = vals[-1]
                out["idest4_guess"] = vals[-1] + 1
        elif data_type == 59:
            # ucalc.f90 type 59 uses idest1=idat(nidt-2),
            # idest2=nlevp+idat(nidt-3)-1, idest3=idat(nidt-1),
            # idest4=idat(nidt-3).
            if len(vals) >= 2:
                out["idest1_guess"] = vals[-2]
            if len(vals) >= 3 and nlevp is not None:
                out["idest2_guess"] = int(nlevp) + vals[-3] - 1
            if len(vals) >= 1:
                out["idest3_guess"] = vals[-1]
            if len(vals) >= 3:
                out["idest4_guess"] = vals[-3]
        elif data_type == 57:
            if len(vals) >= 2:
                out["idest1_guess"] = vals[-2]
            out["idest2_guess"] = nlevp
        elif data_type == 74:
            if len(vals) >= 2:
                out["idest1_guess"] = vals[-2]
            out["idest2_guess"] = nlevp
            if len(vals) >= 1:
                out["idest3_guess"] = vals[-1]
                out["idest4_guess"] = vals[-1] + 1
        elif data_type == 95:
            if rate_type == 5:
                if vals:
                    out["idest1_guess"] = vals[0]
                if len(vals) >= 2 and nlevp is not None:
                    out["idest2_guess"] = int(nlevp) - 1 + vals[1]
                elif nlevp is not None:
                    out["idest2_guess"] = nlevp
            else:
                out["idest1_guess"] = 1
                out["idest2_guess"] = 1
            if vals:
                out["idest3_guess"] = vals[-1]
                out["idest4_guess"] = vals[-1] + 1
        elif data_type == 99:
            if len(vals) >= 2:
                out["idest1_guess"] = vals[-2]
            if len(vals) >= 3 and nlevp is not None:
                out["idest2_guess"] = int(nlevp) + vals[-3] - 1
    except Exception:
        pass
    return out



def _xstar_expo(x: float) -> float:
    """XSTAR ``expo`` helper: exp(x) with the historical +/-60 clamp."""
    return math.exp(min(max(float(x), -60.0), 60.0))


def _xstar_expint_em1(x: float) -> Optional[float]:
    """Return XSTAR ``expint`` value ``em1 = x * exp(x) * E1(x)``.

    The polynomial/rational approximations mirror ``xstarlib/src/expint.f90``
    and are used here only for source-code-guided type-57 diagnostics.
    """
    x = float(x)
    if not math.isfinite(x) or x == 0.0:
        return None
    if x > 1.0:
        b1 = 9.5733223454
        b2 = 25.6329561486
        b3 = 21.0996530827
        b4 = 3.9584969228
        c1 = 8.5733287401
        c2 = 18.0590169730
        c3 = 8.6347608925
        c4 = 0.2677737343
        den = x**4 + b1*x**3 + b2*x*x + b3*x + b4
        if den == 0.0:
            return None
        return (x**4 + c1*x**3 + c2*x*x + c3*x + c4) / den
    a0 = -0.57721566
    a1 = 0.99999193
    a2 = -0.24991055
    a3 = 0.05519968
    a4 = -0.00976004
    a5 = 0.00107857
    try:
        if x > 0.0:
            e1 = a0 + a1*x + a2*x*x + a3*x**3 + a4*x**4 + a5*x**5 - math.log(x)
        else:
            e1 = -a0 + a1*x + a2*x*x + a3*x**3 + a4*x**4 + a5*x**5 - math.log(-x)
        return e1 * x * _xstar_expo(x)
    except Exception:
        return None


def _xstar_eint(t: float) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Return XSTAR ``eint`` outputs E1, E2, E3 for diagnostic calt57 use."""
    t = float(t)
    ss = _xstar_expint_em1(t)
    if ss is None:
        return None, None, None
    try:
        e1 = ss / max(1.0e-34, t * _xstar_expo(t))
        e2 = math.exp(-t) - t * e1
        # Follow the source expression literally: 0.5*(expo(-t)-t*e2).
        e3 = 0.5 * (_xstar_expo(-t) - t * e2)
        return e1, e2, e3
    except Exception:
        return None, None, None


def _xstar_szirc(n: int, temperature: float, rz: float, rno: float) -> Optional[float]:
    """Port of XSTAR ``szirc`` semiempirical hydrogenic CI rate."""
    abethe = [1.134, 0.603, 0.412, 0.313, 0.252, 0.211, 0.181, 0.159, 0.142, 0.128, 1.307]
    hbethe = [1.48, 3.64, 5.93, 8.32, 10.75, 12.90, 15.05, 17.20, 19.35, 21.50, 2.15]
    rbethe = [2.20, 1.90, 1.73, 1.65, 1.60, 1.56, 1.54, 1.52, 1.52, 1.52, 1.52]
    if n <= 0 or temperature <= 0.0 or rz <= 0.0 or rno <= 1.0:
        return None
    boltz = 1.38066e-16
    eion = 2.179874e-11
    const = 4.6513e-3
    rc = float(int(rno))
    if rc <= 1.0:
        return None
    if n < 11:
        an = abethe[n - 1]
        hn = hbethe[n - 1]
        rrn = rbethe[n - 1]
    else:
        an = abethe[10] / float(n)
        hn = hbethe[10] * float(n)
        rrn = rbethe[10]
    tt = temperature * boltz
    rn = float(n)
    try:
        yy = rz * rz * eion / tt * (1.0 / rn / rn - 1.0 / rc / rc - 0.25 * (1.0 / (rc - 1.0) ** 2 - 1.0 / rc / rc))
    except Exception:
        return None
    if yy <= 0.0:
        return None
    e1, e2, e3 = _xstar_eint(yy)
    if e1 is None or e2 is None or e3 is None:
        return None
    try:
        cii = const * math.sqrt(tt) * (rn ** 5) / (rz ** 4) * an * yy * (
            e1 / rn
            - (math.exp(-yy) - yy * e3) / (3.0 * rn)
            + (yy * e2 - 2.0 * yy * e1 + math.exp(-yy)) * 3.0 * hn / rn / (3.0 - rrn)
            + (e1 - e2) * 3.36 * yy
        )
        return cii if math.isfinite(cii) and cii >= 0.0 else None
    except Exception:
        return None


def _xstar_irc(n: int, temperature: float, rc: float, rno: float) -> Optional[float]:
    """Port of XSTAR ``irc`` collisional ionization helper."""
    if n <= 0 or temperature <= 0.0 or rc <= 0.0 or rno <= float(n):
        return None
    if abs(rc - 1.0) > 0.0:
        return _xstar_szirc(n, temperature, rc, rno)
    try:
        xo = 1.0 - n * n / rno / rno
        if xo <= 0.0:
            return None
        yn = xo * 157803.0 / (temperature * n * n)
        if yn <= 0.0:
            return None
        if n < 2:
            an = 1.9603 * n * (1.133 / 3.0 / xo**3 - 0.4059 / 4.0 / xo**4 + 0.07014 / 5.0 / xo**5)
            bn = 2.0 / 3.0 * n * n / xo * (3.0 + 2.0 / xo - 0.603 / xo / xo)
            rn = 0.45
        elif n == 2:
            an = 1.9603 * n * (1.0785 / 3.0 / xo**3 - 0.2319 / 4.0 / xo**4 + 0.02947 / 5.0 / xo**5)
            bn = (4.0 - 18.63 / n + 36.24 / (n * n) - 28.09 / (n * n * n)) / n
            bn = 2.0 / 3.0 * n * n / xo * (3.0 + 2.0 / xo + bn / xo / xo)
            rn = 0.653
        else:
            g0 = (0.9935 + 0.2328 / n - 0.1296 / (n * n)) / 3.0 / xo**3
            g1 = -(0.6282 - 0.5598 / n + 0.5299 / (n * n)) / (n * 4.0) / xo**4
            g2 = (0.3887 - 1.181 / n + 1.470 / (n * n)) / (n * n * 5.0) / xo**5
            an = 1.9603 * n * (g0 + g1 + g2)
            bn = (4.0 - 18.63 / n + 36.24 / (n * n) - 28.09 / (n * n * n)) / n
            bn = (3.0 + 2.0 / xo + bn / xo / xo) * 2.0 * n * n / 3.0 / xo
            rn = 1.94 * n ** (-1.57)
        rn *= xo
        zn = rn + yn
        ey = _xstar_expint_em1(yn)
        ez = _xstar_expint_em1(zn)
        if ey is None or ez is None or zn <= 0.0:
            return None
        se = an * (ey / yn / yn - math.exp(-rn) * ez / zn / zn)
        ey2 = 1.0 + 1.0 / yn - ey * (2.0 / yn + 1.0)
        ez2 = math.exp(-rn) * (1.0 + 1.0 / zn - ez * (1.0 / zn + 1.0))
        se = se + (bn - an * math.log(2.0 * n * n / xo)) * (ey2 - ez2)
        se = se * math.sqrt(temperature) * yn * yn * n * n * 1.095e-10 / xo
        return se if math.isfinite(se) and se >= 0.0 else None
    except Exception:
        return None


def _xstar_calt57(te: float, den2: float, e: float, ep: float, n: int) -> dict:
    """Port/audit of XSTAR ``calt57`` for type-57 collisional ionization.

    Returns the rate coefficient ``cion`` [cm^3/s] and inverse three-body
    coefficient ``crec`` [cm^6/s] before XSTAR's ``ucalc`` multiplies by density
    and statistical weights.  This remains diagnostic in v0.3.18+ and is not
    assembled into the matrix by default.
    """
    if n <= 0:
        return {"python_eval_status": "type57_bad_principal_quantum_number"}
    if te <= 0.0 or den2 <= 0.0:
        return {"python_eval_status": "type57_bad_temperature_or_density"}
    if ep < e:
        return {"python_eval_status": "type57_ep_less_than_level_energy", "type57_cion_cm3_s": 0.0, "type57_crec_cm6_s": 0.0}
    try:
        rn = float(n)
        rk = 1.16058e4
        cb = 13.605692 * 1.6021e-19 / 1.3805e-23
        rio = (ep - e) / 13.6
        if rio <= 0.0:
            return {"python_eval_status": "type57_nonpositive_effective_threshold", "type57_rio": rio, "type57_cion_cm3_s": 0.0, "type57_crec_cm6_s": 0.0}
        rc = math.sqrt(rio) * rn
        den = min(float(den2), 1.0e18)
        tmin = 3.8e4 * rc * math.sqrt(rc)
        temp = max(float(te), tmin)
        rno = math.sqrt(1.8887e8 * rc / den ** 0.3333)
        rno2 = (1.814e26 * (rc ** 6) / 2.0 / den) ** 0.13333
        rno = min(rno, rno2)
        if int(rno) <= n:
            return {
                "python_eval_status": "type57_rno_not_above_n_no_rate",
                "type57_rio": rio, "type57_rc": rc, "type57_tmin_K": tmin,
                "type57_temp_used_K": temp, "type57_rno": rno,
                "type57_cion_cm3_s": 0.0, "type57_crec_cm6_s": 0.0,
            }
        ciono = _xstar_irc(n, temp, rc, rno)
        if ciono is None:
            return {
                "python_eval_status": "type57_irc_failed",
                "type57_rio": rio, "type57_rc": rc, "type57_tmin_K": tmin,
                "type57_temp_used_K": temp, "type57_rno": rno,
            }
        cion = 0.0
        crec = 0.0
        if te < tmin:
            beta = 0.25 * (math.sqrt((100.0 * rc + 91.0) / (4.0 * rc + 3.0)) - 5.0)
            wte = (math.log(1.0 + te / cb / rio)) ** (beta / (1.0 + te / cb * rio))
            wtm = (math.log(1.0 + tmin / cb / rio)) ** (beta / (1.0 + tmin / cb * rio))
            ete, _e2, _e3 = _xstar_eint(rio / te * cb)
            etm, _e2m, _e3m = _xstar_eint(rio / tmin * cb)
            if ete is None or etm is None or ete < 1.0e-20:
                return {
                    "python_eval_status": "type57_low_temperature_extrapolation_failed",
                    "type57_rio": rio, "type57_rc": rc, "type57_tmin_K": tmin,
                    "type57_temp_used_K": temp, "type57_rno": rno,
                    "type57_cion_cm3_s": 0.0, "type57_crec_cm6_s": 0.0,
                }
            cion = ciono * math.sqrt(tmin / te) * ete / (etm + 1.0e-30) * wte / (wtm + 1.0e-30)
        else:
            cion = ciono
        if cion <= 1.0e-24:
            return {
                "python_eval_status": "type57_rate_below_xstar_cutoff",
                "type57_rio": rio, "type57_rc": rc, "type57_tmin_K": tmin,
                "type57_temp_used_K": temp, "type57_rno": rno,
                "type57_ciono_cm3_s": ciono,
                "type57_cion_cm3_s": 0.0, "type57_crec_cm6_s": 0.0,
            }
        cion = cion / float(n * n)
        crec = cion * 2.0779e-16 * math.exp(min((ep - e) * rk / te, 60.0)) / te ** 1.5
        return {
            "python_eval_status": "evaluated_type57_calt57_diagnostic",
            "type57_rio": rio,
            "type57_rc": rc,
            "type57_tmin_K": tmin,
            "type57_temp_used_K": temp,
            "type57_rno": rno,
            "type57_ciono_cm3_s": ciono,
            "type57_cion_cm3_s": cion,
            "type57_crec_cm6_s": crec,
        }
    except Exception as exc:
        return {"python_eval_status": f"type57_exception_{exc.__class__.__name__}"}


def _level_lookup(level_rows: Sequence[dict]) -> Dict[int, dict]:
    out: Dict[int, dict] = {}
    for row in level_rows:
        lev = maybe_int(row.get("level_index"))
        if lev is not None:
            out[int(lev)] = row
    return out


def _type57_prefixed_eval(prefix: str, ev: dict, *, electron_density: float, g_lo: Optional[float], ggup: float, eth_eV: Optional[float]) -> dict:
    """Return prefixed diagnostic columns for one type-57 energy convention."""
    cion = maybe_float(ev.get("type57_cion_cm3_s"))
    crec = maybe_float(ev.get("type57_crec_cm6_s"))
    rinf = None if g_lo is None else g_lo / (1.0e-48 + ggup)
    ans1 = None if cion is None else cion * float(electron_density)
    ans2 = None if crec is None or rinf is None else crec * rinf * float(electron_density) * float(electron_density)
    ergsev = 1.602197e-12
    eth = None if eth_eV is None else max(0.0, float(eth_eV))
    return {
        f"{prefix}_eval_status": ev.get("python_eval_status"),
        f"{prefix}_rio": ev.get("type57_rio"),
        f"{prefix}_rc": ev.get("type57_rc"),
        f"{prefix}_tmin_K": ev.get("type57_tmin_K"),
        f"{prefix}_temp_used_K": ev.get("type57_temp_used_K"),
        f"{prefix}_rno": ev.get("type57_rno"),
        f"{prefix}_ciono_cm3_s": ev.get("type57_ciono_cm3_s"),
        f"{prefix}_cion_cm3_s": cion,
        f"{prefix}_crec_cm6_s": crec,
        f"{prefix}_rate_forward_s^-1": ans1,
        f"{prefix}_rate_inverse_s^-1": ans2,
        f"{prefix}_ans6_energy_loss_erg_s^-1": None if ans1 is None or eth is None else -ans1 * eth * ergsev,
        f"{prefix}_ans5_inverse_energy_erg_s^-1": None if ans2 is None or eth is None else -ans2 * eth * ergsev,
    }


def _evaluate_type57_calt57_record(
    reals: Sequence[float],
    ints: Sequence[int],
    *,
    temperature: float,
    electron_density: float,
    nlevp: Optional[int],
    level_rows: Optional[Sequence[dict]] = None,
    type57_energy_convention: str = "compare",
    triplet_source_mode: str = "none",
    triplet_source_scale: object = 1.0,
    type99_proxy_scale: object = "1",
    type53_flat_proxy_scale: object = 1.0,
    radiation_field_mode: str = "none",
    full_global_linear_solver: str = "xstar-lucy",
    full_global_rank_deficient_action: str = "svd",
    full_global_negative_population_action: str = "keep",
    full_global_prune_null_rate_levels: bool = True,
) -> dict:
    """Evaluate XSTAR type-57 using the ported ``calt57`` path for audit only.

    v0.3.21 writes side-by-side diagnostics for alternate energy conventions
    and lets the caller select which convention populates the primary
    ``python_eval_status`` / ``python_rate_*`` audit columns.
    This is needed because ``ucalc.f90`` currently passes ``ep=eth`` whereas
    ``calt57.f90`` documents ``ep`` as the fourth real of the type-6 level
    record.  No type-57 rate is assembled from any convention here.
    """
    convention = str(type57_energy_convention or "compare").strip().lower().replace("_", "-")
    aliases = {
        "ucalc": "ucalc-eth",
        "eth": "ucalc-eth",
        "ucalceth": "ucalc-eth",
        "rlev4": "abs-rlev4",
        "abs": "abs-rlev4",
        "absolute-rlev4": "abs-rlev4",
        "threshold": "threshold-only",
        "thresholdonly": "threshold-only",
    }
    convention = aliases.get(convention, convention)
    if convention not in {"compare", "ucalc-eth", "abs-rlev4", "threshold-only"}:
        convention = "compare"
    rd = [float(x) for x in reals]
    it = [int(x) for x in ints]
    if len(it) < 2:
        return {"python_eval_status": "type57_missing_integer_indices"}
    i57 = it[0]
    idest1 = it[-2]
    if i57 <= 0:
        return {"python_eval_status": "type57_bad_i57_n"}
    if nlevp is not None and (idest1 <= 1 or idest1 > int(nlevp)):
        return {"python_eval_status": "type57_idest1_outside_ucalc_range", "type57_n_principal": i57}
    levels = _level_lookup(level_rows or [])
    lev = levels.get(int(idest1), {})
    e1 = maybe_float(lev.get("energy_eV"))
    g_lo = maybe_float(lev.get("statistical_weight_g"))
    ip_abs = maybe_float(lev.get("ionization_potential_eV"))
    eth = maybe_float(lev.get("binding_from_continuum_eV"))
    if eth is None and ip_abs is not None and e1 is not None:
        eth = ip_abs - e1
    if e1 is None:
        # The record real is usually the effective charge; keep it in the audit,
        # but do not use it as level energy because ucalc takes e1 from rlev.
        return {"python_eval_status": "type57_missing_destination_level_energy", "type57_n_principal": i57, "type57_destination_level": idest1}
    if eth is None:
        return {"python_eval_status": "type57_missing_destination_binding_energy", "type57_n_principal": i57, "type57_destination_level": idest1, "type57_level_energy_eV": e1}
    tz = float(temperature)  # user-facing API already passes Kelvin; ucalc's t*1e4 equals Kelvin.
    ggup = 1.0
    # XSTAR uses the continuum/parent statistical weight in rlev(2,nlevp).  The
    # present ion-level table often lacks that continuum row, so use 1 as an
    # explicit diagnostic placeholder until the element matrix has the parent
    # continuum level available.

    # Visible current ucalc.f90 path: e=e1, ep=eth.  This gives ep<e for many
    # excited levels and therefore returns zero in calt57.
    ev_ucalc = _xstar_calt57(tz, float(electron_density), float(e1), float(eth), int(i57))
    out = {
        **ev_ucalc,
        "type57_n_principal": i57,
        "type57_destination_level": idest1,
        "type57_level_energy_eV": e1,
        "type57_binding_or_eth_eV": eth,
        "type57_ionization_potential_rlev4_eV": ip_abs,
        "type57_ep_ucalc_eth_eV": eth,
        "type57_ep_legacy_rlev4_minus_e1_eV": None if ip_abs is None else ip_abs - e1,
        "type57_ep_absolute_rlev4_eV": ip_abs,
        "type57_stat_weight_lower": g_lo,
        "type57_stat_weight_continuum_assumed": ggup,
        "type57_selected_energy_convention": convention,
        "type57_source_provenance_ucalc": "xstarlib/src/ucalc.f90 type 57: e1=rlev(1,idest1), eth=max(0,rlev(1,nlevp)-rlev(1,idest1)), ep=eth, call calt57",
        "type57_source_provenance_calt57": "xstarlib/src/calt57.f90 documents e=level energy and ep=fourth real in type-6 level record; calt57 internally gates ep>=e",
        "type57_source_provenance_irc": "xstarlib/src/irc.f90 with szirc/eint/expint/expo is ported diagnostically; no type-57 matrix assembly is performed",
    }
    out.update(_type57_prefixed_eval(
        "type57_ucalc_eth", ev_ucalc,
        electron_density=electron_density, g_lo=g_lo, ggup=ggup, eth_eV=eth,
    ))

    # Direct calt57.f90 documentation convention: ep is rlev(4), i.e. the
    # absolute level ionization-potential column.  Then calt57's internal
    # (ep-e) equals the physical binding threshold.
    ev_abs = None
    if ip_abs is not None:
        ev_abs = _xstar_calt57(tz, float(electron_density), float(e1), float(ip_abs), int(i57))
        out.update(_type57_prefixed_eval(
            "type57_abs_rlev4", ev_abs,
            electron_density=electron_density, g_lo=g_lo, ggup=ggup, eth_eV=eth,
        ))
    else:
        out.update({
            "type57_abs_rlev4_eval_status": "type57_missing_absolute_rlev4",
            "type57_abs_rlev4_cion_cm3_s": None,
            "type57_abs_rlev4_crec_cm6_s": None,
            "type57_abs_rlev4_rate_forward_s^-1": None,
            "type57_abs_rlev4_rate_inverse_s^-1": None,
        })

    # Threshold-only diagnostic: e=0, ep=eth.  This is not an XSTAR assembly
    # path; it checks whether the calt57 kernel itself produces a finite rate
    # when supplied the effective threshold directly.
    ev_thr = _xstar_calt57(tz, float(electron_density), 0.0, float(eth), int(i57))
    out.update(_type57_prefixed_eval(
        "type57_threshold_only", ev_thr,
        electron_density=electron_density, g_lo=g_lo, ggup=ggup, eth_eV=eth,
    ))

    # v0.3.21: select which convention populates the primary, backward-compatible
    # audit columns.  ``compare`` deliberately keeps the visible ucalc convention
    # as primary while still writing all alternate convention columns.
    convention_map = {
        "compare": ("type57_ucalc_eth", ev_ucalc, "visible_ucalc_eth_compare_default"),
        "ucalc-eth": ("type57_ucalc_eth", ev_ucalc, "visible_ucalc_eth"),
        "abs-rlev4": ("type57_abs_rlev4", ev_abs, "abs_rlev4_documented_calt57"),
        "threshold-only": ("type57_threshold_only", ev_thr, "threshold_only_diagnostic"),
    }
    selected_prefix, selected_ev, selected_label = convention_map[convention]
    if selected_ev is None:
        selected_ev = {"python_eval_status": f"type57_selected_{convention}_not_available", "type57_cion_cm3_s": None, "type57_crec_cm6_s": None}
    cion = maybe_float(selected_ev.get("type57_cion_cm3_s"))
    crec = maybe_float(selected_ev.get("type57_crec_cm6_s"))
    ans1 = None if cion is None else cion * float(electron_density)
    rinf = None if g_lo is None else g_lo / (1.0e-48 + ggup)
    ans2 = None if crec is None or rinf is None else crec * rinf * float(electron_density) * float(electron_density)
    ergsev = 1.602197e-12
    out.update({
        "python_eval_status": selected_ev.get("python_eval_status"),
        "python_rate_forward_s^-1": ans1,
        "python_rate_inverse_s^-1": ans2,
        "type57_selected_convention_label": selected_label,
        "type57_selected_rate_column_prefix": selected_prefix,
        "type57_selected_cion_cm3_s": cion,
        "type57_selected_crec_cm6_s": crec,
        "type57_ans6_energy_loss_erg_s^-1": None if ans1 is None else -ans1 * float(eth) * ergsev,
        "type57_ans5_inverse_energy_erg_s^-1": None if ans2 is None else -ans2 * float(eth) * ergsev,
        "type57_calt57_energy_convention_note": "primary python_* columns follow --type57-energy-convention; compare/default keeps visible ucalc ep=eth primary; abs_rlev4 uses calt57 documented ep=rlev4; threshold_only is diagnostic only",
        "type57_assembly_note": "diagnostic_only_not_assembled_into_matrix",
    })

    ucalc_rate = maybe_float(out.get("type57_ucalc_eth_rate_forward_s^-1"))
    abs_rate = maybe_float(out.get("type57_abs_rlev4_rate_forward_s^-1"))
    thr_rate = maybe_float(out.get("type57_threshold_only_rate_forward_s^-1"))
    if (ucalc_rate is None or ucalc_rate == 0.0) and abs_rate is not None and abs_rate > 0.0:
        out["type57_best_nonzero_convention"] = "abs_rlev4_documented_calt57"
        out["type57_energy_convention_conflict"] = True
    elif (ucalc_rate is None or ucalc_rate == 0.0) and thr_rate is not None and thr_rate > 0.0:
        out["type57_best_nonzero_convention"] = "threshold_only_diagnostic"
        out["type57_energy_convention_conflict"] = True
    else:
        out["type57_best_nonzero_convention"] = "visible_ucalc_eth" if ucalc_rate and ucalc_rate > 0.0 else "none"
        out["type57_energy_convention_conflict"] = False

    # ucalc zeros both ans1 and ans2 for destination level 1 because more
    # accurate ground-level rates are supplied by data types 95 or 25.
    if idest1 == 1 and out.get("python_eval_status") == "evaluated_type57_calt57_diagnostic":
        out["python_eval_status"] = "evaluated_type57_calt57_ground_zeroed_by_ucalc"
        out["python_rate_forward_s^-1"] = 0.0
        out["python_rate_inverse_s^-1"] = 0.0
    return out


def _classify_type57_matrix_role(
    *,
    record_ion_stage: int,
    target_ion_stage: int,
    parent_ion_stage: int,
    destination_level: Optional[int],
    level_indices: Optional[Sequence[int]] = None,
    nlevp: Optional[int] = None,
    selected_forward_rate: Optional[float] = None,
    selected_inverse_rate: Optional[float] = None,
) -> dict:
    """Classify how a type-57 record would enter an element matrix.

    This is intentionally diagnostic-only.  XSTAR type 57 represents
    electron-impact ionization from a bound level plus an inverse three-body
    recombination term from the adjacent continuum.  The current Python
    reference solver still solves one ion block at a time, so it has no explicit
    parent-continuum column/population.  v0.3.21 therefore reports candidate
    local source/sink indices and the reason assembly is unsafe.
    """
    levels = [int(x) for x in (level_indices or [])]
    idx = {lev: i for i, lev in enumerate(levels)}
    dest = None if destination_level is None else int(destination_level)
    rec_stage = int(record_ion_stage)
    target = int(target_ion_stage)
    parent = int(parent_ion_stage)

    # XSTAR ion-stage convention used here: C V target stage 5 ionizes to
    # adjacent C VI parent stage 6.  Thus the record ion stage is the lower
    # bound ion for a target-parent pair when rec_stage == target and
    # parent == target + 1.
    pair_matches = (rec_stage == target and parent == target + 1)
    record_is_parent_stage = (rec_stage == parent)
    local_index = idx.get(dest) if dest is not None else None
    in_local_matrix = local_index is not None
    primary_forward_nonzero = selected_forward_rate is not None and selected_forward_rate > 0.0
    primary_inverse_nonzero = selected_inverse_rate is not None and selected_inverse_rate > 0.0

    if pair_matches and in_local_matrix:
        role = "target_lower_ion_level_to_parent_continuum_ci_sink_with_inverse_tbr_source"
        forward_sink_ion_stage = target
        inverse_source_ion_stage = target
        inverse_parent_stage = parent
        sink_index = local_index
        source_index = local_index
    elif pair_matches and not in_local_matrix:
        role = "target_lower_ion_type57_level_not_in_current_local_matrix"
        forward_sink_ion_stage = target
        inverse_source_ion_stage = target
        inverse_parent_stage = parent
        sink_index = None
        source_index = None
    elif record_is_parent_stage:
        role = "record_belongs_to_parent_ion_not_target_parent_pair_sink_to_next_higher_stage"
        forward_sink_ion_stage = parent
        inverse_source_ion_stage = parent
        inverse_parent_stage = parent + 1
        sink_index = None
        source_index = None
    else:
        role = "record_ion_stage_not_matched_to_current_target_parent_pair"
        forward_sink_ion_stage = rec_stage
        inverse_source_ion_stage = rec_stage
        inverse_parent_stage = rec_stage + 1
        sink_index = None
        source_index = None

    reasons = []
    if not pair_matches:
        reasons.append("record_ion_stage_is_not_current_lower_target_ion")
    if not in_local_matrix:
        reasons.append("destination_level_not_in_current_pruned_target_level_matrix")
    if nlevp is None:
        reasons.append("parent_continuum_level_index_nlevp_not_explicit_in_python_matrix")
    else:
        reasons.append("parent_continuum_column_population_not_available_in_single_ion_block_solver")
    reasons.append("continuum_statistical_weight_is_placeholder_until_parent_continuum_row_is_explicit")
    reasons.append("type57_energy_convention_conflict_must_be_resolved_before_physical_assembly")
    reasons.append("inverse_three_body_recombination_requires_full_element_population_balance")

    return {
        "type57_matrix_role_classifier_version": "v0.3.21",
        "type57_matrix_lower_ion_stage": target,
        "type57_matrix_upper_ion_stage": parent,
        "type57_matrix_record_ion_stage": rec_stage,
        "type57_matrix_destination_ion_stage": target if pair_matches else rec_stage,
        "type57_matrix_destination_level": dest,
        "type57_matrix_destination_in_current_level_set": bool(in_local_matrix),
        "type57_matrix_candidate_local_index_0based": local_index,
        "type57_matrix_candidate_local_index_1based": None if local_index is None else local_index + 1,
        "type57_matrix_candidate_nlevp_continuum_level": nlevp,
        "type57_forward_rate_would_be_sink_from_lower_ion": bool(pair_matches),
        "type57_forward_rate_would_be_sink_from_upper_ion": bool(record_is_parent_stage),
        "type57_forward_sink_ion_stage": forward_sink_ion_stage,
        "type57_forward_sink_level": dest,
        "type57_forward_sink_vector_index_0based": sink_index,
        "type57_forward_full_matrix_row_if_sink": sink_index,
        "type57_forward_full_matrix_col_if_sink": sink_index,
        "type57_inverse_three_body_recombination_source_candidate": bool(pair_matches),
        "type57_inverse_source_ion_stage": inverse_source_ion_stage,
        "type57_inverse_parent_source_ion_stage": inverse_parent_stage,
        "type57_inverse_source_level": dest,
        "type57_inverse_source_vector_index_0based": source_index,
        "type57_inverse_full_matrix_row_if_source": source_index,
        "type57_inverse_full_matrix_col_if_source": "parent_continuum_column_not_present",
        "type57_selected_forward_rate_nonzero": bool(primary_forward_nonzero),
        "type57_selected_inverse_rate_nonzero": bool(primary_inverse_nonzero),
        "type57_matrix_role_classification": role,
        "type57_matrix_safe_to_assemble": False,
        "type57_matrix_unsafe_reason": ";".join(reasons),
        "type57_matrix_assembly_note": "classifier_only_not_assembled; candidate sink/source indices are local to the current target ion block, not a complete element-wide matrix",
    }


def _level_label_for(level_rows: Optional[Sequence[dict]], level: Optional[int]) -> str:
    """Return a best-effort level label for an integer level index."""
    if level is None:
        return ""
    try:
        ilev = int(level)
    except Exception:
        return ""
    for row in level_rows or []:
        if maybe_int(row.get("level_index")) == ilev:
            return str(row.get("level_label") or row.get("configuration") or "")
    return ""


def _is_helike_triplet_upper_label(label: str) -> bool:
    """Heuristic identifier for He-like f/i/r upper levels in decoded labels."""
    txt = str(label or "").replace(" ", "").lower()
    if not txt:
        return False
    # These labels appear in XSTAR decoded level names for the He-like triplet
    # upper terms.  Keep this heuristic narrow; it is an audit hint, not a
    # physical assembly rule.
    return any(tok in txt for tok in ("1s1.2s1.3s_1", "1s1.2p1.3p_", "1s1.2p1.1p_1"))


def _audit_recombination_source_role(
    *,
    data_type: int,
    rate_type: Optional[int],
    record_ion_stage: Optional[int],
    target_ion_stage: int,
    parent_ion_stage: int,
    destination_level: Optional[int],
    level_rows: Optional[Sequence[dict]] = None,
    level_indices: Optional[Sequence[int]] = None,
) -> dict:
    """Classify recombination-like rows for adjacent C VI -> C V audits.

    This helper is intentionally diagnostic.  It annotates total RR/DR rows and
    level-specific inverse bound-free rows with the source/destination stages
    and whether the destination is an excited level or a He-like triplet upper
    candidate.  It performs no matrix assembly.
    """
    dt = int(data_type)
    rt = None if rate_type is None else int(rate_type)
    rec_stage = None if record_ion_stage is None else int(record_ion_stage)
    target = int(target_ion_stage)
    parent = int(parent_ion_stage)
    dest = None if destination_level is None else int(destination_level)
    levels = [int(x) for x in (level_indices or [])]
    in_matrix = dest in set(levels) if dest is not None else False
    label = _level_label_for(level_rows, dest)
    is_excited = dest is not None and dest > 1
    triplet_upper = bool(is_excited and _is_helike_triplet_upper_label(label))
    pair_matches = (rec_stage == target and parent == target + 1)
    if dt == 59:
        family = "type59_photoionization_inverse_recombination"
        xstar_gate = "suppressed_by_ucalc_if_rate_type_1_or_destination_level_gt_1"
    elif dt in EVALUABLE_RECOMBINATION_DATA_TYPES:
        family = "implemented_total_electron_recombination"
        xstar_gate = "not_type59_gate_total_recombination_treated_as_ground_or_allocated_source"
    else:
        family = "recombination_like_inventory_or_related_record"
        xstar_gate = "not_evaluated_by_current_recombination_audit"
    return {
        "recomb_audit_classifier_version": "v0.3.22",
        "recomb_audit_family": family,
        "recomb_record_ion_stage": rec_stage,
        "recomb_parent_source_ion_stage": parent if pair_matches else (None if rec_stage is None else rec_stage + 1),
        "recomb_destination_ion_stage": target if pair_matches else rec_stage,
        "recomb_destination_level": dest,
        "recomb_destination_label": label,
        "recomb_destination_in_current_level_set": bool(in_matrix),
        "recomb_destination_level_kind": "excited" if is_excited else ("ground" if dest == 1 else "unknown"),
        "recomb_record_matches_current_parent_pair": bool(pair_matches),
        "recomb_would_feed_excited_level": bool(is_excited),
        "recomb_would_feed_helike_triplet_upper_candidate": bool(triplet_upper),
        "recomb_xstar_excited_level_gate": xstar_gate,
        "recomb_matrix_safe_to_assemble": False,
        "recomb_matrix_unsafe_reason": "diagnostic_only; full element population balance and source-code branch validation required before assembly",
    }


def _audit_type59_recombination_record(
    reals: Sequence[float],
    ints: Sequence[int],
    *,
    rate_type: int,
    record_ion_stage: int,
    target_ion_stage: int,
    parent_ion_stage: int,
    nlevp: Optional[int] = None,
    level_rows: Optional[Sequence[dict]] = None,
    level_indices: Optional[Sequence[int]] = None,
) -> dict:
    """Audit XSTAR type-59 photoionization/inverse-recombination records.

    The visible ``ucalc.f90`` type-59 branch computes bound-free rates through
    ``phintfo`` and then explicitly zeros the recombination outputs for
    ``rate_type == 1`` or ``idest1 > 1``::

        if ((nrdesc.eq.1).or.(idest1.gt.1)) then
          ans6=0.; ans4=0.; ans2=0.
        endif

    Therefore type-59 records that nominally point to excited levels are
    important to audit, but should not be assumed to feed the He-like triplet
    unless this gate and the surrounding continuum/radiation context are fully
    reproduced.
    """
    vals = [int(x) for x in ints]
    rd = [float(x) for x in reals]
    idest1 = vals[-2] if len(vals) >= 2 else None
    idest3 = vals[-1] if len(vals) >= 1 else None
    idest4 = vals[-3] if len(vals) >= 3 else None
    idest2 = (int(nlevp) + idest4 - 1) if (nlevp is not None and idest4 is not None) else None
    ett_preview = rd[0] if len(rd) >= 1 else None
    e0_preview = rd[1] if len(rd) >= 2 else None
    s0_preview = rd[2] if len(rd) >= 3 else None
    dest = None if idest1 is None else int(idest1)
    rt = int(rate_type)
    suppress = (rt == 1) or (dest is not None and dest > 1)
    reasons = []
    if rt == 1:
        reasons.append("rate_type_1_total_or_special_branch")
    if dest is not None and dest > 1:
        reasons.append("destination_level_gt_1_excited_recombination_zeroed")
    if not reasons:
        reasons.append("not_suppressed_by_visible_type59_gate_but_still_requires_phintfo_radiation_context")
    base = _audit_recombination_source_role(
        data_type=59,
        rate_type=rt,
        record_ion_stage=record_ion_stage,
        target_ion_stage=target_ion_stage,
        parent_ion_stage=parent_ion_stage,
        destination_level=dest,
        level_rows=level_rows,
        level_indices=level_indices,
    )
    can_feed = bool(base.get("recomb_would_feed_helike_triplet_upper_candidate")) and not suppress
    out = {
        "type59_audit_classifier_version": "v0.3.22",
        "type59_source_provenance_ucalc": "xstarlib/src/ucalc.f90 type 59 calls phintfo, then zeros ans2/ans4/ans6 when nrdesc==1 or idest1>1",
        "type59_source_provenance_gate": "if ((nrdesc.eq.1).or.(idest1.gt.1)) then ans6=0; ans4=0; ans2=0",
        "type59_source_provenance_context": "type 59 requires continuum grid/radiation-field inputs and linked parent/cross-section record via derivedpointers%npar/ml before physical rates can be assembled",
        "type59_idest1_destination_level": dest,
        "type59_idest2_continuum_or_parent_level_guess": idest2,
        "type59_idest3_guess": idest3,
        "type59_idest4_or_continuum_offset_guess": idest4,
        "type59_threshold_energy_preview_eV": ett_preview,
        "type59_e0_preview": e0_preview,
        "type59_s0_preview": s0_preview,
        "type59_would_recombine_to_excited_level": bool(dest is not None and dest > 1),
        "type59_ucalc_recombination_outputs_suppressed": bool(suppress),
        "type59_suppression_reason": ";".join(reasons),
        "type59_can_feed_helike_triplet_upper_after_visible_gate": bool(can_feed),
        "type59_triplet_feed_reason": "triplet_upper_and_not_suppressed" if can_feed else ("destination_is_triplet_upper_but_visible_ucalc_gate_suppresses_recombination" if base.get("recomb_would_feed_helike_triplet_upper_candidate") else "destination_not_identified_as_helike_triplet_upper"),
        "type59_matrix_role_classification": "bound_free_photoionization_sink_with_inverse_recombination_from_parent_continuum_suppressed_for_excited_destinations" if suppress else "bound_free_photoionization_sink_with_inverse_recombination_candidate_requires_phintfo_context",
        "type59_matrix_safe_to_assemble": False,
        "type59_matrix_unsafe_reason": "requires_phintfo_radiation_continuum_context; linked_parent_cross_section_record_not_explicitly_resolved; visible_ucalc_gate_suppresses_excited_level_recombination" if suppress else "requires_phintfo_radiation_continuum_context_and_element_wide_parent_continuum_population",
        "python_eval_status": "type59_audited_recombination_outputs_suppressed_by_ucalc_gate" if suppress else "type59_audited_not_suppressed_but_not_evaluated_requires_phintfo_context",
    }
    out.update(base)
    return out

def _evaluate_type95_bryans_ci(reals: Sequence[float], ints: Sequence[int], *, temperature: float, electron_density: float) -> dict:
    """Diagnostic approximation to ucalc type-95 Bryans collisional ionization.

    Mirrors the visible ucalc.f90 branch sufficiently to classify whether a
    record can supply an electron-impact ionization sink.  It is not yet used
    as an assembled production coupling term.
    """
    rd = [float(x) for x in reals]
    if len(rd) < 4:
        return {"python_eval_status": "type95_missing_coefficients"}
    ee = rd[0]
    if ee <= 0.0 or temperature <= 0.0:
        return {"python_eval_status": "type95_bad_threshold_or_temperature"}
    nspline = int((len(rd) - 2) // 2)
    if nspline < 2 or len(rd) < 2 + 2 * nspline:
        return {"python_eval_status": "type95_bad_spline_layout", "type95_nspline": nspline}
    ekt = 0.861707 * (float(temperature) / 1.0e4)
    tt = ekt / ee
    if tt <= 0.0:
        return {"python_eval_status": "type95_bad_tt", "type95_tt": tt}
    try:
        xx = 1.0 - 0.693147 / math.log(tt + 2.0)
    except Exception:
        return {"python_eval_status": "type95_bad_x_transform", "type95_tt": tt}
    xs = rd[2:2 + nspline]
    ys = rd[2 + nspline:2 + 2 * nspline]
    rho = _interp_linear(xx, xs, ys)
    e1 = _safe_exp1(1.0 / tt)
    if rho is None or e1 is None:
        return {"python_eval_status": "type95_interpolation_or_exp1_failed", "type95_tt": tt, "type95_xx": xx}
    citmp1 = 1.0e-6 * e1 * rho / math.sqrt(max(tt * ee ** 3, 1.0e-300))
    ans1 = citmp1 * electron_density
    return {
        "python_eval_status": "evaluated_type95_bryans_ci_diagnostic",
        "python_rate_forward_s^-1": max(float(ans1), 0.0),
        "type95_threshold_eV": ee,
        "type95_tt": tt,
        "type95_xx": xx,
        "type95_rho": rho,
        "type95_exp1": e1,
        "type95_nspline": nspline,
    }


def audit_ucalc_adjacent_record(
    db: ATDB,
    rec,
    *,
    target_ion_stage: int,
    parent_ion_stage: int,
    temperature: float,
    electron_density: float,
    nlevp: Optional[int] = None,
    level_rows: Optional[Sequence[dict]] = None,
    level_indices: Optional[Sequence[int]] = None,
    type57_energy_convention: str = "compare",
    triplet_source_mode: str = "none",
    triplet_source_scale: object = 1.0,
    type99_proxy_scale: object = "1",
) -> dict:
    """Return a source-code-guided audit row for an adjacent-ion record.

    The intent is to document how XSTAR's ``ucalc.f90`` would treat candidate
    adjacent-ion records before we decide whether a clean Python/C++ evaluator
    can assemble them into the element matrix.
    """
    h = db.header(rec.recno)
    rd = db.real_slice(h)
    it = db.int_slice(h)
    dt = int(rec.data_type)
    rt = int(rec.rate_type)
    level_guess = _guess_ucalc_levels(dt, rt, it, nlevp=nlevp)
    row = {
        "record": rec.recno,
        "record_ion_stage": rec.ion_stage,
        "data_type": dt,
        "rate_type": rt,
        "nreal": rec.nreal,
        "nint": rec.nint,
        "nchar": rec.nchar,
        "target_ion_stage": target_ion_stage,
        "parent_ion_stage": parent_ion_stage,
        "ucalc_source_file": "xstarlib/src/ucalc.f90",
        "ucalc_branch": f"type_{dt}",
        "ucalc_ans1_role": "",
        "ucalc_ans2_role": "",
        "python_eval_status": "not_attempted",
        "assembly_status": "catalogued_not_assembled",
        "requires_context": "",
        "matrix_role_if_implemented": "",
        "raw_reals_preview": str(list(rd[:8])),
        "raw_ints_preview": str(list(it[:8])),
        **level_guess,
    }
    if dt == 53:
        row.update({
            "ucalc_ans1_role": "photoionization_rate_from_bound_level_to_continuum",
            "ucalc_ans2_role": "radiative_recombination_inverse_from_phint53_milne",
            "requires_context": "radiation_field_epi_bremsa_opacity_escape_probabilities_population_abundances",
            "matrix_role_if_implemented": "bound_free_sink_from_target_level_and_recombination_source_from_parent_continuum",
            "python_eval_status": "not_evaluated_requires_phint53_radiation_field",
        })
    elif dt == 57:
        row.update({
            "ucalc_ans1_role": "collisional_ionization_sink_from_target_level",
            "ucalc_ans2_role": "three_body_recombination_inverse_from_calt57",
            "requires_context": "destination_level_energy_binding_statistical_weight_and_parent_continuum_weight",
            "matrix_role_if_implemented": "electron_impact_ionization_sink_from_target_level_and_inverse_three_body_recombination_source_from_parent_continuum",
        })
        row.update(_evaluate_type57_calt57_record(
            rd, it,
            temperature=temperature,
            electron_density=electron_density,
            nlevp=nlevp,
            level_rows=level_rows,
            type57_energy_convention=type57_energy_convention,
        ))
        row.update(_classify_type57_matrix_role(
            record_ion_stage=int(rec.ion_stage),
            target_ion_stage=target_ion_stage,
            parent_ion_stage=parent_ion_stage,
            destination_level=maybe_int(row.get("type57_destination_level") or row.get("idest1_guess")),
            level_indices=level_indices,
            nlevp=nlevp,
            selected_forward_rate=maybe_float(row.get("python_rate_forward_s^-1")),
            selected_inverse_rate=maybe_float(row.get("python_rate_inverse_s^-1")),
        ))
    elif dt == 59:
        row.update({
            "ucalc_ans1_role": "photoionization_rate_from_bound_level_to_continuum_from_phintfo",
            "ucalc_ans2_role": "inverse_recombination_from_parent_continuum_zeroed_for_rate_type_1_or_excited_destinations",
            "requires_context": "radiation_field_continuum_grid_bremsa_opacity_escape_probabilities_linked_parent_cross_section_record",
            "matrix_role_if_implemented": "bound_free_sink_from_target_level_with_inverse_recombination_source_if_not_suppressed_by_ucalc_gate",
        })
        row.update(_audit_type59_recombination_record(
            rd, it,
            rate_type=rt,
            record_ion_stage=int(rec.ion_stage),
            target_ion_stage=target_ion_stage,
            parent_ion_stage=parent_ion_stage,
            nlevp=nlevp,
            level_rows=level_rows,
            level_indices=level_indices,
        ))
    elif dt == 74:
        row.update({
            "ucalc_ans1_role": "dielectronic_resonance_photoionization_delta_rate",
            "ucalc_ans2_role": "dielectronic_recombination_inverse_alpha_from_calt74",
            "requires_context": "radiation_continuum_epi_bremsa_calt74_resonance_delta_integration",
            "matrix_role_if_implemented": "dr_resonance_sink_source_pair",
            "python_eval_status": "not_evaluated_requires_calt74_and_radiation_grid",
        })
    elif dt == 95:
        row.update({
            "ucalc_ans1_role": "bryans_collisional_ionization_sink",
            "ucalc_ans2_role": "inverse_three_body_recombination_from_detailed_balance",
            "requires_context": "level_degeneracies_parent_continuum_for_inverse_rate",
            "matrix_role_if_implemented": "collisional_ionization_sink_with_optional_inverse_source",
        })
        row.update(_evaluate_type95_bryans_ci(rd, it, temperature=temperature, electron_density=electron_density))
    elif dt == 99:
        row.update({
            "ucalc_ans1_role": "superlevel_photoionization_rate",
            "ucalc_ans2_role": "superlevel_recombination_inverse",
            "requires_context": "superlevel_linked_records_radiation_field_phint53pl_population_escape_probabilities",
            "matrix_role_if_implemented": "superlevel_bound_free_sink_source_pair",
            "python_eval_status": "not_evaluated_requires_linked_superlevel_phint53pl_context",
        })
    return row


def _triplet_component_from_level_label(label: str) -> str:
    """Return f/i/r for a He-like triplet upper-level label when identifiable."""
    txt = str(label or "").replace(" ", "").lower()
    if not txt:
        return ""
    if "1s1.2s1.3s_1" in txt:
        return "f"
    if "1s1.2p1.3p_" in txt:
        return "i"
    if "1s1.2p1.1p_1" in txt:
        return "r"
    return ""


def _superlevel_stage_relation(record_ion_stage: int, target_ion_stage: int, parent_ion_stage: int) -> str:
    rec = int(record_ion_stage)
    target = int(target_ion_stage)
    parent = int(parent_ion_stage)
    if rec == target:
        return "target_ion_stage"
    if rec == parent:
        return "parent_ion_stage"
    if rec == target - 1:
        return "lower_than_target_ion_stage"
    if rec == parent + 1:
        return "higher_than_parent_ion_stage"
    return "not_current_target_parent_pair"


def _audit_superlevel_cascade_record(
    db: ATDB,
    rec,
    *,
    target_ion_stage: int,
    parent_ion_stage: int,
    level_rows: Sequence[dict],
    level_indices: Optional[Sequence[int]] = None,
) -> dict:
    """Classify type 70/71/74/77/99 superlevel/cascade records.

    This is a diagnostic inventory only.  It follows the database-paper/manual
    descriptions of the record layouts and reports whether any record provides
    a plausible superlevel -> spectroscopic cascade route into the He-like
    triplet upper levels.  No rate from this audit is assembled into the matrix.
    """
    h = db.header(rec.recno)
    rd = [float(x) for x in db.real_slice(h)]
    it = [int(x) for x in db.int_slice(h)]
    dt = int(rec.data_type)
    rt = int(rec.rate_type)
    rec_stage = int(rec.ion_stage)
    level_set = set(int(x) for x in (level_indices or []))

    def lab(level):
        return _level_label_for(level_rows, level)

    def comp(level):
        return _triplet_component_from_level_label(lab(level))

    # Common fields, populated below as far as the data type permits.
    lower_level = None
    upper_level = None
    spectroscopic_level = None
    superlevel_level = None
    destination_level = None
    parent_continuum_level = None
    cascade_direction = ""
    route_kind = ""
    source_provenance = ""
    requires = []
    unsafe = []

    if dt == 70:
        # Appendix: type 70 coefficients for recombination and PI cross section
        # of superlevels; i8=level+, i9=ion+, i10=level, i11=ion.
        final_level = it[7] if len(it) >= 8 else None
        final_ion = it[8] if len(it) >= 9 else None
        initial_level = it[9] if len(it) >= 10 else None
        initial_ion = it[10] if len(it) >= 11 else None
        superlevel_level = initial_level
        destination_level = final_level
        parent_continuum_level = final_level
        route_kind = "superlevel_recombination_photoionization_coefficient"
        cascade_direction = "parent_continuum_or_final_level_to_superlevel_candidate"
        source_provenance = "Bautista_Kallman_2001_appendix_type70_coefficients_for_recombination_and_photoionization_cross_sections_of_superlevels"
        requires += ["radiation_field_or_milne_inverse_context", "superlevel_population_balance", "linked_type71_or_type77_decay_routes"]
        unsafe += ["type70_rate_not_evaluated_without_phint53pl_or_superlevel_bound_free_context", "superlevel_population_column_not_explicit_in_current_matrix"]
        extra = {
            "type70_i8_final_level_plus": final_level,
            "type70_i9_final_ion_plus": final_ion,
            "type70_i10_superlevel_or_initial_level": initial_level,
            "type70_i11_initial_ion": initial_ion,
            "type70_n_coefficients": len(rd),
        }
    elif dt == 71:
        # Appendix: radiative transition rates from superlevels to spectroscopic
        # levels; i3=lower level, i4=upper level, i5=Z, i6=ion.
        lower_level = it[2] if len(it) >= 3 else None
        upper_level = it[3] if len(it) >= 4 else None
        spectroscopic_level = lower_level
        superlevel_level = upper_level
        destination_level = lower_level
        route_kind = "radiative_superlevel_to_spectroscopic_cascade"
        cascade_direction = "superlevel_upper_to_spectroscopic_lower"
        source_provenance = "Bautista_Kallman_2001_appendix_type71_radiative_transition_rates_from_superlevels_to_spectroscopic_levels"
        requires += ["superlevel_population_from_type70_or_other_recombination_source"]
        unsafe += ["superlevel_population_not_solved_explicitly", "cascade_branching_not_normalized_over_all_superlevel_decays"]
        extra = {
            "type71_lower_spectroscopic_level": lower_level,
            "type71_upper_superlevel_level": upper_level,
            "type71_A_or_rate_preview_s^-1": rd[0] if rd else None,
            "type71_wavelength_or_energy_preview": rd[1] if len(rd) > 1 else None,
        }
    elif dt == 77:
        # Appendix: collisional transition rates from superlevels to
        # spectroscopic levels; same level integer layout as type 71.
        lower_level = it[2] if len(it) >= 3 else None
        upper_level = it[3] if len(it) >= 4 else None
        spectroscopic_level = lower_level
        superlevel_level = upper_level
        destination_level = lower_level
        route_kind = "collisional_superlevel_to_spectroscopic_cascade"
        cascade_direction = "superlevel_upper_to_spectroscopic_lower"
        source_provenance = "Bautista_Kallman_2001_appendix_type77_collision_transition_rates_from_superlevels_to_spectroscopic_levels"
        requires += ["electron_density", "temperature", "superlevel_population"]
        unsafe += ["type77_rate_evaluator_not_ported", "superlevel_population_not_solved_explicitly"]
        extra = {
            "type77_lower_spectroscopic_level": lower_level,
            "type77_upper_superlevel_level": upper_level,
            "type77_coefficients_preview": str(rd[:8]),
            "type77_coefficient0_proxy": rd[0] if rd else None,
        }
    elif dt == 74:
        # Appendix: DR delta functions added to PI cross sections; i5=level+,
        # i6=ion+, i7=level, i8=nion.  Treat as possible recombination/cascade
        # source only after the linked bound-free context is available.
        final_level = it[4] if len(it) >= 5 else None
        final_ion = it[5] if len(it) >= 6 else None
        initial_level = it[6] if len(it) >= 7 else None
        initial_ion = it[7] if len(it) >= 8 else None
        destination_level = final_level
        spectroscopic_level = final_level
        superlevel_level = initial_level
        route_kind = "dielectronic_recombination_delta_photoionization_cross_section"
        cascade_direction = "dr_resonance_or_parent_level_to_recombined_level_candidate"
        source_provenance = "Bautista_Kallman_2001_appendix_type74_delta_functions_added_to_photoionization_cross_sections_to_match_ADF_DR_rates"
        requires += ["calt74_resonance_delta_integration", "radiation_or_milne_context", "linked_parent_continuum_population"]
        unsafe += ["type74_not_a_direct_cascade_rate", "requires_calt74_and_full_bound_free_context"]
        final_label = lab(final_level)
        initial_label = lab(initial_level)
        extra = {
            "type74_i5_final_level_plus": final_level,
            "type74_i6_final_ion_plus": final_ion,
            "type74_i7_initial_level": initial_level,
            "type74_i8_initial_ion": initial_ion,
            "type74_n_delta_coefficients": len(rd),
            "type74_parent_or_final_level": final_level,
            "type74_parent_or_final_ion_index": final_ion,
            "type74_parent_or_final_label": final_label,
            "type74_parent_or_final_level_kind": _level_kind_from_label(final_label),
            "type74_parent_or_final_triplet_component": comp(final_level),
            "type74_recombined_or_source_level": initial_level,
            "type74_recombined_or_source_ion_index": initial_ion,
            "type74_recombined_or_source_label": initial_label,
            "type74_recombined_or_source_level_kind": _level_kind_from_label(initial_label),
            "type74_recombined_or_source_triplet_component": comp(initial_level),
        }
    elif dt == 99:
        # Newer XSTAR superlevel PI/RR records: layout is not fully documented
        # in the 2001 appendix, so keep raw destination guesses conservative.
        g = _guess_ucalc_levels(dt, rt, it, nlevp=None)
        destination_level = maybe_int(g.get("idest1_guess"))
        spectroscopic_level = destination_level
        route_kind = "superlevel_photoionization_recombination_linked_record"
        cascade_direction = "superlevel_bound_free_context_required"
        source_provenance = "ucalc_type99_superlevel_photoionization_recombination_phint53pl_context_not_fully_documented_in_2001_appendix"
        requires += ["linked_superlevel_records", "radiation_field", "phint53pl_context", "superlevel_population_balance"]
        unsafe += ["type99_layout_requires_source_code_linkage_validation", "not_a_standalone_cascade_rate"]
        extra = {"type99_idest1_guess": g.get("idest1_guess"), "type99_idest2_guess": g.get("idest2_guess"), "type99_raw_int_count": len(it)}
    else:
        extra = {}
        route_kind = "not_superlevel_cascade_audit_type"
        unsafe.append("unsupported_data_type_for_superlevel_audit")

    comp_level = spectroscopic_level if spectroscopic_level is not None else destination_level
    component = comp(comp_level)
    feeds_f = component == "f"
    feeds_i = component == "i"
    feeds_r = component == "r"
    feeds_any = bool(component)
    in_matrix = bool(comp_level in level_set) if comp_level is not None else False
    stage_relation = _superlevel_stage_relation(rec_stage, target_ion_stage, parent_ion_stage)

    if not feeds_any:
        unsafe.append("no_direct_destination_match_to_identified_helike_triplet_upper_level")
    if rec_stage != int(target_ion_stage):
        unsafe.append("record_not_in_current_helike_target_ion_stage")
    if not in_matrix and comp_level is not None:
        unsafe.append("candidate_destination_level_not_in_current_pruned_matrix")

    row = {
        "record": rec.recno,
        "data_type": dt,
        "rate_type": rt,
        "record_ion_stage": rec_stage,
        "target_ion_stage": target_ion_stage,
        "parent_ion_stage": parent_ion_stage,
        "stage_relation_to_target_parent": stage_relation,
        "superlevel_audit_version": "v0.3.24",
        "superlevel_route_kind": route_kind,
        "superlevel_source_provenance": source_provenance,
        "cascade_direction": cascade_direction,
        "lower_level": lower_level,
        "upper_level": upper_level,
        "superlevel_level": superlevel_level,
        "spectroscopic_level": spectroscopic_level,
        "destination_level": destination_level,
        "parent_continuum_level": parent_continuum_level,
        "destination_label": lab(comp_level),
        "destination_in_current_level_set": in_matrix,
        "cascade_feed_component": component,
        "feeds_forbidden_upper": feeds_f,
        "feeds_intercombination_upper": feeds_i,
        "feeds_resonance_upper": feeds_r,
        "feeds_any_triplet_component": feeds_any,
        "requires_radiation_grid": any("radiation" in x for x in requires),
        "requires_parent_continuum_population": any("continuum" in x or "parent" in x for x in requires),
        "requires_superlevel_population": any("superlevel_population" in x for x in requires),
        "matrix_safe_to_assemble": False,
        "unsafe_reason": ";".join(dict.fromkeys(unsafe + ["diagnostic_only_not_assembled"])),
        "required_context": ";".join(dict.fromkeys(requires)),
        "raw_reals_preview": str(rd[:8]),
        "raw_ints_preview": str(it[:12]),
    }
    row.update(extra)
    return row


def build_superlevel_cascade_audit(
    db: ATDB,
    *,
    z: int,
    target_ion_stage: int,
    parent_ion_stage: int,
    level_rows: Sequence[dict],
    level_indices: Optional[Sequence[int]] = None,
    use_cache: bool = True,
    cache_path: Optional[str] = None,
) -> List[dict]:
    """Return diagnostic-only superlevel/cascade audit rows for one ion pair."""
    rows: List[dict] = []
    for stage in (target_ion_stage, parent_ion_stage):
        for rec in _select_records(db, z, stage, use_cache=use_cache, cache_path=cache_path):
            if int(rec.data_type) in SUPERLEVEL_CASCADE_DATA_TYPES:
                row = _audit_superlevel_cascade_record(
                    db,
                    rec,
                    target_ion_stage=target_ion_stage,
                    parent_ion_stage=parent_ion_stage,
                    level_rows=level_rows,
                    level_indices=level_indices,
                )
                row.update({"element": Z_TO_SYMBOL.get(z, str(z)), "element_z": z})
                rows.append(row)
    return rows


def _truthy(value) -> bool:
    """Return True for CSV-safe booleans used in diagnostic rows."""
    return value is True or str(value).strip().lower() in {"true", "1", "yes", "y"}


def _branch_component_label(component: str) -> str:
    return {"f": "forbidden", "i": "intercombination", "r": "resonance"}.get(str(component or ""), "other")


def _level_kind_from_label(label: str) -> str:
    """Classify an ATDB level label as spectroscopic, superlevel, continuum, or unknown."""
    txt = str(label or "").strip().lower()
    if not txt:
        return "unknown"
    if "continuum" in txt:
        return "continuum"
    if "superlevel" in txt:
        return "superlevel"
    return "spectroscopic"


def build_superlevel_branching_audit(superlevel_rows: Sequence[dict]) -> List[dict]:
    """Summarise diagnostic type-71/type-77 branching by superlevel.

    Type 71 rows have direct radiative A-value-like weights in the database
    audit.  Type 77 rows are collisional superlevel-to-spectroscopic records;
    the full rate evaluator is not ported yet, so v0.3.24 reports a count-based
    branching proxy for type 77 rather than pretending the fit coefficients are
    physical rates.  These rows are diagnostic only and are never assembled into
    the element matrix.
    """
    groups: Dict[Tuple[int, int, int], List[dict]] = {}
    for row in superlevel_rows:
        dt = maybe_int(row.get("data_type"))
        if dt not in {71, 77}:
            continue
        sl = maybe_int(row.get("superlevel_level"))
        rec_stage = maybe_int(row.get("record_ion_stage"))
        if sl is None or rec_stage is None:
            continue
        groups.setdefault((int(dt), int(rec_stage), int(sl)), []).append(row)

    out: List[dict] = []
    for (dt, rec_stage, sl), rows in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])):
        if dt == 71:
            weight_basis = "type71_radiative_A_s^-1"
            def weight(row):
                val = maybe_float(row.get("type71_A_or_rate_preview_s^-1"))
                return float(val) if val is not None and math.isfinite(float(val)) and float(val) > 0.0 else 0.0
            unsafe_extra = "superlevel_population_not_solved_explicitly;branching_is_radiative_only_until_type70_population_source_is_available"
        else:
            weight_basis = "type77_count_proxy_no_rate_evaluator"
            def weight(row):
                return 1.0
            unsafe_extra = "type77_rate_evaluator_not_ported;count_proxy_is_not_a_physical_collisional_branching_rate;superlevel_population_not_solved_explicitly"

        weights = [weight(r) for r in rows]
        total = float(sum(weights))
        comp_weight = {"f": 0.0, "i": 0.0, "r": 0.0, "other": 0.0}
        comp_count = {"f": 0, "i": 0, "r": 0, "other": 0}
        dest_levels = {"f": [], "i": [], "r": [], "other": []}
        dest_labels = {"f": [], "i": [], "r": [], "other": []}
        for r, w in zip(rows, weights):
            comp = str(r.get("cascade_feed_component") or "")
            if comp not in {"f", "i", "r"}:
                comp = "other"
            comp_weight[comp] += float(w)
            comp_count[comp] += 1
            lev = r.get("spectroscopic_level") if r.get("spectroscopic_level") not in (None, "") else r.get("destination_level")
            lab = r.get("destination_label")
            if lev not in dest_levels[comp]:
                dest_levels[comp].append(lev)
            if lab not in dest_labels[comp]:
                dest_labels[comp].append(lab)

        def frac(c):
            return comp_weight[c] / total if total > 0.0 else None

        triplet_weight = comp_weight["f"] + comp_weight["i"] + comp_weight["r"]
        triplet_count = comp_count["f"] + comp_count["i"] + comp_count["r"]
        row0 = rows[0]
        out.append({
            "branching_audit_version": "v0.3.24",
            "data_type": dt,
            "record_ion_stage": rec_stage,
            "target_ion_stage": row0.get("target_ion_stage"),
            "parent_ion_stage": row0.get("parent_ion_stage"),
            "superlevel_level": sl,
            "branching_route_kind": "type71_radiative_superlevel_branching" if dt == 71 else "type77_collisional_superlevel_branching_proxy",
            "branching_weight_basis": weight_basis,
            "n_outgoing_records": len(rows),
            "total_branch_weight": total,
            "weight_to_forbidden": comp_weight["f"],
            "weight_to_intercombination": comp_weight["i"],
            "weight_to_resonance": comp_weight["r"],
            "weight_to_triplet_total": triplet_weight,
            "weight_to_other": comp_weight["other"],
            "B_f": frac("f"),
            "B_i": frac("i"),
            "B_r": frac("r"),
            "B_triplet_total": triplet_weight / total if total > 0.0 else None,
            "B_other": comp_weight["other"] / total if total > 0.0 else None,
            "n_to_forbidden": comp_count["f"],
            "n_to_intercombination": comp_count["i"],
            "n_to_resonance": comp_count["r"],
            "n_to_triplet_total": triplet_count,
            "n_to_other": comp_count["other"],
            "forbidden_destination_levels": ";".join(str(x) for x in dest_levels["f"] if x not in (None, "")),
            "intercombination_destination_levels": ";".join(str(x) for x in dest_levels["i"] if x not in (None, "")),
            "resonance_destination_levels": ";".join(str(x) for x in dest_levels["r"] if x not in (None, "")),
            "forbidden_destination_labels": ";".join(str(x) for x in dest_labels["f"] if x not in (None, "")),
            "intercombination_destination_labels": ";".join(str(x) for x in dest_labels["i"] if x not in (None, "")),
            "resonance_destination_labels": ";".join(str(x) for x in dest_labels["r"] if x not in (None, "")),
            "cascade_naturally_favors_forbidden": bool(total > 0.0 and comp_weight["f"] >= comp_weight["i"] and comp_weight["f"] >= comp_weight["r"] and comp_weight["f"] > 0.0),
            "cascade_dominant_triplet_component": max(("f", "i", "r", "other"), key=lambda c: comp_weight[c]) if total > 0.0 else "",
            "matrix_safe_to_assemble": False,
            "unsafe_reason": unsafe_extra + ";diagnostic_only_not_assembled",
        })
    return out


def _source_proxy_from_row(row: dict) -> float:
    """Return a transparent nonphysical source proxy for superlevel-source audits.

    The type-70/74/99 source records are not yet evaluated as XSTAR physical
    rates.  v0.3.25 therefore uses one count unit per source candidate for the
    source-weighted branch diagnostic, while also reporting coefficient-magnitude
    previews separately.  This makes source_proxy * B_f/i/r easy to interpret as
    a source-presence weighted feed proxy, not an assembled rate.
    """
    return 1.0


def _source_coeff_abs_sum(row: dict) -> Optional[float]:
    """Best-effort coefficient-magnitude diagnostic from raw_reals_preview."""
    txt = str(row.get("raw_reals_preview") or "").strip()
    if not txt:
        return None
    try:
        vals = json.loads(txt.replace("'", '"'))
    except Exception:
        try:
            import ast
            vals = ast.literal_eval(txt)
        except Exception:
            return None
    if not isinstance(vals, (list, tuple)):
        return None
    nums = []
    for val in vals:
        try:
            f = float(val)
            if math.isfinite(f):
                nums.append(abs(f))
        except Exception:
            pass
    return float(sum(nums)) if nums else None


def _source_superlevel_key(row: dict) -> Optional[int]:
    """Return the best candidate superlevel index for type 70/74/99 rows."""
    dt = maybe_int(row.get("data_type"))
    if dt == 70:
        for key in ("type70_i10_superlevel_or_initial_level", "superlevel_level", "destination_level"):
            val = maybe_int(row.get(key))
            if val is not None:
                return int(val)
    if dt == 74:
        for key in ("type74_i7_initial_level", "superlevel_level", "destination_level"):
            val = maybe_int(row.get(key))
            if val is not None:
                return int(val)
    if dt == 99:
        for key in ("type99_idest1_guess", "destination_level", "spectroscopic_level", "superlevel_level"):
            val = maybe_int(row.get(key))
            if val is not None:
                return int(val)
    val = maybe_int(row.get("superlevel_level"))
    return None if val is None else int(val)


def build_superlevel_source_audit(superlevel_rows: Sequence[dict], branching_rows: Sequence[dict]) -> List[dict]:
    """Link type-70/74/99 source candidates to v0.3.24 branch fractions.

    The output is one diagnostic row per (record ion stage, superlevel).  It
    identifies source-candidate records of types 70/74/99, attaches radiative
    type-71 and collisional-proxy type-77 f/i/r branch fractions for that same
    superlevel when available, and reports source_proxy * B_f/i/r feed proxies.

    No source, branch, or source-weighted proxy is assembled into the solver.
    """
    source_rows = [r for r in superlevel_rows if maybe_int(r.get("data_type")) in {70, 74, 99}]
    branch_by_key: Dict[Tuple[int, int, int], dict] = {}
    for br in branching_rows:
        dt = maybe_int(br.get("data_type"))
        st = maybe_int(br.get("record_ion_stage"))
        sl = maybe_int(br.get("superlevel_level"))
        if dt is None or st is None or sl is None:
            continue
        branch_by_key[(int(st), int(sl), int(dt))] = br

    keys = set()
    grouped: Dict[Tuple[int, int], List[dict]] = {}
    for row in source_rows:
        st = maybe_int(row.get("record_ion_stage"))
        sl = _source_superlevel_key(row)
        if st is None or sl is None:
            continue
        key = (int(st), int(sl))
        keys.add(key)
        grouped.setdefault(key, []).append(row)
    for br in branching_rows:
        st = maybe_int(br.get("record_ion_stage"))
        sl = maybe_int(br.get("superlevel_level"))
        if st is not None and sl is not None:
            keys.add((int(st), int(sl)))

    out: List[dict] = []
    for st, sl in sorted(keys, key=lambda x: (x[0], x[1])):
        rows = grouped.get((st, sl), [])
        rows_by_dt = {70: [], 74: [], 99: []}
        for row in rows:
            dt = maybe_int(row.get("data_type"))
            if dt in rows_by_dt:
                rows_by_dt[int(dt)].append(row)
        records_by_dt = {
            dt: ";".join(str(r.get("record")) for r in rows_by_dt[dt] if r.get("record") not in (None, ""))
            for dt in (70, 74, 99)
        }
        coeff_abs_by_dt = {}
        for dt in (70, 74, 99):
            coeffs = [_source_coeff_abs_sum(r) for r in rows_by_dt[dt]]
            coeff_abs_by_dt[dt] = float(sum(c for c in coeffs if c is not None)) if any(c is not None for c in coeffs) else None
        n70 = len(rows_by_dt[70])
        n74 = len(rows_by_dt[74])
        n99 = len(rows_by_dt[99])
        source_proxy = float(sum(_source_proxy_from_row(r) for r in rows))
        # Prefer type-71 physical radiative branching for source-weighted proxy.
        br71 = branch_by_key.get((st, sl, 71), {})
        br77 = branch_by_key.get((st, sl, 77), {})
        def bval(br: dict, key: str) -> Optional[float]:
            val = maybe_float(br.get(key)) if br else None
            return float(val) if val is not None and math.isfinite(float(val)) else None
        type71_Bf, type71_Bi, type71_Br = bval(br71, "B_f"), bval(br71, "B_i"), bval(br71, "B_r")
        type71_Bt = bval(br71, "B_triplet_total")
        type77_Bf, type77_Bi, type77_Br = bval(br77, "B_f"), bval(br77, "B_i"), bval(br77, "B_r")
        type77_Bt = bval(br77, "B_triplet_total")
        has_branch = bool(br71 or br77)
        has_type71 = bool(br71)
        has_type77 = bool(br77)
        def prod(b: Optional[float]) -> Optional[float]:
            return None if b is None else source_proxy * float(b)
        unsafe = ["source_proxy_is_count_based_not_a_physical_rate", "type70_74_99_bound_free_source_rates_not_evaluated", "superlevel_population_not_solved_explicitly", "diagnostic_only_not_assembled"]
        if not rows:
            unsafe.append("branching_superlevel_has_no_type70_74_99_source_candidate_in_current_audit")
        if not has_branch:
            unsafe.append("source_superlevel_has_no_type71_or_type77_branching_fraction_in_current_audit")
        target_stage = rows[0].get("target_ion_stage") if rows else (br71 or br77).get("target_ion_stage")
        parent_stage = rows[0].get("parent_ion_stage") if rows else (br71 or br77).get("parent_ion_stage")
        out.append({
            "source_audit_version": "v0.3.25",
            "record_ion_stage": st,
            "target_ion_stage": target_stage,
            "parent_ion_stage": parent_stage,
            "superlevel_level": sl,
            "n_type70_source_candidates": n70,
            "type70_records": records_by_dt[70],
            "type70_coeff_abs_sum_preview": coeff_abs_by_dt[70],
            "n_type74_dr_delta_source_candidates": n74,
            "type74_records": records_by_dt[74],
            "type74_coeff_abs_sum_preview": coeff_abs_by_dt[74],
            "n_type99_superlevel_source_candidates": n99,
            "type99_records": records_by_dt[99],
            "type99_coeff_abs_sum_preview": coeff_abs_by_dt[99],
            "n_total_source_candidates": len(rows),
            "source_proxy_basis": "count_per_type70_74_99_source_candidate_nonphysical",
            "source_proxy_total": source_proxy,
            "has_type71_branching": has_type71,
            "has_type77_branching_proxy": has_type77,
            "has_any_branching": has_branch,
            "type71_B_f": type71_Bf,
            "type71_B_i": type71_Bi,
            "type71_B_r": type71_Br,
            "type71_B_triplet_total": type71_Bt,
            "type77_B_f_proxy": type77_Bf,
            "type77_B_i_proxy": type77_Bi,
            "type77_B_r_proxy": type77_Br,
            "type77_B_triplet_total_proxy": type77_Bt,
            "source_weighted_type71_feed_f_proxy": prod(type71_Bf),
            "source_weighted_type71_feed_i_proxy": prod(type71_Bi),
            "source_weighted_type71_feed_r_proxy": prod(type71_Br),
            "source_weighted_type71_feed_triplet_proxy": prod(type71_Bt),
            "source_weighted_type77_feed_f_proxy": prod(type77_Bf),
            "source_weighted_type77_feed_i_proxy": prod(type77_Bi),
            "source_weighted_type77_feed_r_proxy": prod(type77_Br),
            "source_weighted_type77_feed_triplet_proxy": prod(type77_Bt),
            "source_weighted_preferred_feed_f_proxy": prod(type71_Bf if type71_Bf is not None else type77_Bf),
            "source_weighted_preferred_feed_i_proxy": prod(type71_Bi if type71_Bi is not None else type77_Bi),
            "source_weighted_preferred_feed_r_proxy": prod(type71_Br if type71_Br is not None else type77_Br),
            "source_weighted_preferred_feed_triplet_proxy": prod(type71_Bt if type71_Bt is not None else type77_Bt),
            "preferred_branch_basis": "type71_radiative_A_s^-1" if has_type71 else ("type77_count_proxy_no_rate_evaluator" if has_type77 else "none"),
            "source_has_branch_to_forbidden": bool((type71_Bf or 0.0) > 0.0 or (type77_Bf or 0.0) > 0.0),
            "source_has_branch_to_intercombination": bool((type71_Bi or 0.0) > 0.0 or (type77_Bi or 0.0) > 0.0),
            "source_has_branch_to_resonance": bool((type71_Br or 0.0) > 0.0 or (type77_Br or 0.0) > 0.0),
            "source_weighted_proxy_dominant_component": max(
                ("f", "i", "r", "none"),
                key=lambda c: {
                    "f": prod(type71_Bf if type71_Bf is not None else type77_Bf) or 0.0,
                    "i": prod(type71_Bi if type71_Bi is not None else type77_Bi) or 0.0,
                    "r": prod(type71_Br if type71_Br is not None else type77_Br) or 0.0,
                    "none": 0.0,
                }[c],
            ),
            "matrix_safe_to_assemble": False,
            "unsafe_reason": ";".join(dict.fromkeys(unsafe)),
        })
    return out

def build_type74_linkage_audit(superlevel_rows: Sequence[dict], branching_rows: Sequence[dict]) -> List[dict]:
    """Deep diagnostic linkage audit for type-74 DR delta records.

    Type 74 records are not direct cascade rates.  The 2001 XSTAR database
    appendix describes them as delta functions added to photoionization cross
    sections to match dielectronic-recombination rates.  In the inverse Milne
    sense, the target/recombined level is most naturally associated with the
    record's ``i7`` level, while ``i5``/``i6`` identify the final/parent side of
    the partial photoionization channel.  This audit reports both sides and
    checks whether the recombined/source level can directly feed a He-like f/i/r
    upper level or maps to a superlevel with type-71/type-77 cascade branches.

    No type-74 rate, link, or source term is assembled into the matrix.
    """
    type74_rows = [r for r in superlevel_rows if maybe_int(r.get("data_type")) == 74]
    branch_by_key: Dict[Tuple[int, int, int], dict] = {}
    for br in branching_rows:
        dt = maybe_int(br.get("data_type"))
        st = maybe_int(br.get("record_ion_stage"))
        sl = maybe_int(br.get("superlevel_level"))
        if dt is None or st is None or sl is None:
            continue
        branch_by_key[(int(st), int(sl), int(dt))] = br

    out: List[dict] = []
    for row in type74_rows:
        st = maybe_int(row.get("record_ion_stage"))
        target_stage = maybe_int(row.get("target_ion_stage"))
        parent_stage = maybe_int(row.get("parent_ion_stage"))
        src_level = maybe_int(row.get("type74_recombined_or_source_level") or row.get("type74_i7_initial_level"))
        src_label = str(row.get("type74_recombined_or_source_label") or "")
        src_kind = str(row.get("type74_recombined_or_source_level_kind") or _level_kind_from_label(src_label))
        src_comp = str(row.get("type74_recombined_or_source_triplet_component") or "")
        final_level = maybe_int(row.get("type74_parent_or_final_level") or row.get("type74_i5_final_level_plus"))
        final_label = str(row.get("type74_parent_or_final_label") or row.get("destination_label") or "")
        final_kind = str(row.get("type74_parent_or_final_level_kind") or _level_kind_from_label(final_label))
        final_comp = str(row.get("type74_parent_or_final_triplet_component") or "")

        br71_src = branch_by_key.get((int(st), int(src_level), 71)) if st is not None and src_level is not None else {}
        br77_src = branch_by_key.get((int(st), int(src_level), 77)) if st is not None and src_level is not None else {}
        br71_final = branch_by_key.get((int(st), int(final_level), 71)) if st is not None and final_level is not None else {}
        br77_final = branch_by_key.get((int(st), int(final_level), 77)) if st is not None and final_level is not None else {}

        source_is_superlevel = src_kind == "superlevel"
        final_is_superlevel = final_kind == "superlevel"
        source_is_spectroscopic = src_kind == "spectroscopic"
        final_is_spectroscopic = final_kind == "spectroscopic"

        linked_type71 = bool((source_is_superlevel and br71_src) or (final_is_superlevel and br71_final))
        linked_type77 = bool((source_is_superlevel and br77_src) or (final_is_superlevel and br77_final))
        linked_branch = (
            br71_src if (source_is_superlevel and br71_src) else
            br71_final if (final_is_superlevel and br71_final) else
            br77_src if (source_is_superlevel and br77_src) else
            br77_final if (final_is_superlevel and br77_final) else
            {}
        )

        def bval(br: dict, key: str) -> Optional[float]:
            val = maybe_float(br.get(key)) if br else None
            return float(val) if val is not None and math.isfinite(float(val)) else None

        Bf = bval(linked_branch, "B_f")
        Bi = bval(linked_branch, "B_i")
        Br = bval(linked_branch, "B_r")
        Bt = bval(linked_branch, "B_triplet_total")

        route_parts: List[str] = []
        if src_comp in {"f", "i", "r"}:
            route_parts.append(f"direct_inverse_dr_delta_to_{_branch_component_label(src_comp)}_upper_candidate")
        if final_comp in {"f", "i", "r"}:
            route_parts.append(f"parent_or_final_side_matches_{_branch_component_label(final_comp)}_upper_not_primary_inverse_feed")
        if linked_type71:
            route_parts.append("via_superlevel_type71_radiative_branch")
        if linked_type77:
            route_parts.append("via_superlevel_type77_collisional_branch_proxy")
        if not route_parts:
            route_parts.append("no_identified_f_i_r_feed_route")

        reasons: List[str] = []
        if not (br71_src or br77_src or br71_final or br77_final):
            reasons.append("no_type71_or_type77_branch_with_same_numeric_source_or_final_level")
        if (br71_src or br77_src) and not source_is_superlevel:
            reasons.append("same_numeric_source_level_has_branch_record_but_source_level_is_spectroscopic_not_superlevel")
        if (br71_final or br77_final) and not final_is_superlevel:
            reasons.append("same_numeric_final_level_has_branch_record_but_final_level_is_spectroscopic_not_superlevel")
        if source_is_spectroscopic and not src_comp:
            reasons.append("source_level_is_spectroscopic_but_not_a_helike_triplet_upper_level")
        if final_is_spectroscopic and not final_comp:
            reasons.append("parent_or_final_level_is_spectroscopic_but_not_a_helike_triplet_upper_level")
        if not linked_type71 and not linked_type77:
            reasons.append("no_valid_superlevel_branch_link_after_level_kind_check")
        if not src_label:
            reasons.append("source_level_label_missing_from_current_target_level_table")
        if not final_label:
            reasons.append("parent_or_final_level_label_missing_from_current_target_level_table")

        out.append({
            "type74_linkage_audit_version": "v0.3.26",
            "record": row.get("record"),
            "data_type": 74,
            "rate_type": row.get("rate_type"),
            "record_ion_stage": st,
            "target_ion_stage": target_stage,
            "parent_ion_stage": parent_stage,
            "stage_relation_to_target_parent": row.get("stage_relation_to_target_parent"),
            "type74_raw_ints_preview": row.get("raw_ints_preview"),
            "type74_raw_reals_preview": row.get("raw_reals_preview"),
            "type74_i5_parent_or_final_level": final_level,
            "type74_i6_parent_or_final_ion_index": row.get("type74_i6_final_ion_plus"),
            "type74_i7_recombined_or_source_level": src_level,
            "type74_i8_recombined_or_source_ion_index": row.get("type74_i8_initial_ion"),
            "source_level": src_level,
            "source_level_label": src_label,
            "source_level_kind": src_kind,
            "source_level_triplet_component": src_comp,
            "source_level_is_spectroscopic": source_is_spectroscopic,
            "source_level_is_superlevel": source_is_superlevel,
            "source_level_direct_triplet_feed_candidate": bool(src_comp in {"f", "i", "r"}),
            "parent_or_final_level": final_level,
            "parent_or_final_level_label": final_label,
            "parent_or_final_level_kind": final_kind,
            "parent_or_final_triplet_component": final_comp,
            "parent_or_final_level_is_spectroscopic": final_is_spectroscopic,
            "parent_or_final_level_is_superlevel": final_is_superlevel,
            "same_numeric_source_level_has_type71_branch": bool(br71_src),
            "same_numeric_source_level_has_type77_branch": bool(br77_src),
            "same_numeric_final_level_has_type71_branch": bool(br71_final),
            "same_numeric_final_level_has_type77_branch": bool(br77_final),
            "valid_type71_superlevel_branch_link": linked_type71,
            "valid_type77_superlevel_branch_link": linked_type77,
            "linked_branch_basis": "type71_radiative_A_s^-1" if linked_type71 else ("type77_count_proxy_no_rate_evaluator" if linked_type77 else "none"),
            "linked_B_f": Bf,
            "linked_B_i": Bi,
            "linked_B_r": Br,
            "linked_B_triplet_total": Bt,
            "possible_feed_route": ";".join(dict.fromkeys(route_parts)),
            "possible_feed_component_direct": src_comp,
            "possible_feed_component_via_branch": max(("f", "i", "r", "none"), key=lambda c: {"f": Bf or 0.0, "i": Bi or 0.0, "r": Br or 0.0, "none": 0.0}[c]) if linked_branch else "none",
            "can_feed_forbidden_candidate": bool(src_comp == "f" or (Bf or 0.0) > 0.0),
            "can_feed_intercombination_candidate": bool(src_comp == "i" or (Bi or 0.0) > 0.0),
            "can_feed_resonance_candidate": bool(src_comp == "r" or (Br or 0.0) > 0.0),
            "can_feed_any_triplet_candidate": bool(src_comp in {"f", "i", "r"} or (Bt or 0.0) > 0.0),
            "branch_link_status": "valid_superlevel_branch_link" if (linked_type71 or linked_type77) else ("direct_spectroscopic_triplet_target" if src_comp in {"f", "i", "r"} else "unlinked"),
            "why_no_branch_found_if_unlinked": ";".join(dict.fromkeys(reasons)) if not (linked_type71 or linked_type77) else "",
            "matrix_safe_to_assemble": False,
            "unsafe_reason": ";".join(dict.fromkeys([
                "type74_delta_record_is_not_a_direct_cascade_rate",
                "requires_calt74_delta_integration_and_bound_free_milne_context",
                "requires_explicit_superlevel_or_recombined_level_population_balance_before_assembly",
                "diagnostic_only_not_assembled",
            ])),
        })
    return out


def _xstar_calt74_alpha_diagnostic(temperature: float, reals: Sequence[float]) -> dict:
    """Diagnostic Python port of the recombination part of XSTAR calt74.

    XSTAR ``calt74`` evaluates delta functions added to photoionization cross
    sections to match dielectronic-recombination rates.  Its recombination
    output ``alpha`` is a coefficient before the statistical-weight correction;
    ``ucalc.f90`` subsequently applies ``alpha *= g(recombined)/g(continuum)``.

    This helper ports only that recombination coefficient.  It does not use the
    radiation-grid photoionization integral and it does not assemble any matrix
    term.  The units follow the XSTAR routine convention as closely as possible
    for diagnostic comparison.
    """
    try:
        rd = [float(x) for x in reals]
        temp = float(temperature)
    except Exception:
        return {"type74_eval_status": "type74_bad_input"}
    nrd = len(rd)
    if nrd < 3:
        return {"type74_eval_status": "type74_too_few_real_coefficients", "type74_n_real_coefficients": nrd}
    m = (nrd - 1) // 2
    if m <= 0 or (1 + 2 * m) > nrd:
        return {"type74_eval_status": "type74_bad_delta_coefficient_layout", "type74_n_real_coefficients": nrd, "type74_m_delta_count": m}
    if temp <= 0.0 or not math.isfinite(temp):
        return {"type74_eval_status": "type74_bad_temperature", "type74_temperature_K": temp}

    # Literal constants/structure from xstarlib/src/calt74.f90.
    te = temp * 1.38066e-16
    ryk = 4.589343e10
    factor = 213.9577e-9
    xt = rd[0]
    energies = rd[1:1 + m]
    heights = rd[1 + m:1 + 2 * m]
    alpha_sum = 0.0
    used = 0
    skipped = 0
    for x, hgh in zip(energies, heights):
        arg = x / ryk / te
        if arg < 40.0:
            alpha_sum += math.exp(-arg) * (x + xt) * (x + xt) * hgh
            used += 1
        else:
            skipped += 1
    alpha = alpha_sum * factor / (te ** 1.5) / ryk / ryk
    return {
        "type74_eval_status": "evaluated_type74_calt74_dr_alpha_diagnostic",
        "type74_alpha_unweighted_cm3_s": alpha,
        "type74_n_real_coefficients": nrd,
        "type74_m_delta_count": m,
        "type74_delta_terms_used": used,
        "type74_delta_terms_skipped_arg_ge_40": skipped,
        "type74_xt_coeff_preview": xt,
        "type74_delta_energy_coeff_min": min(energies) if energies else None,
        "type74_delta_energy_coeff_max": max(energies) if energies else None,
        "type74_delta_height_abs_sum": sum(abs(h) for h in heights),
    }


def build_type74_triplet_source_audit(
    type74_linkage_rows: Sequence[dict],
    *,
    temperature: float,
    electron_density: float,
    level_rows: Optional[Sequence[dict]] = None,
    parent_population_proxy: float = 1.0,
) -> List[dict]:
    """Evaluate direct type-74 f/i/r triplet source candidates diagnostically.

    The input rows come from the v0.3.26 deep type-74 linkage audit.  Only rows
    whose recombined/source side maps directly to a He-like triplet upper level
    are evaluated here.  The output is a type-74-only source-vector diagnostic:
    candidate source rates into f/i/r are summed, normalized, and compared to a
    built-in C V ne=1e8 XSTAR triplet target when applicable.

    This is not a physical matrix assembly.  It omits the radiation-grid
    photoionization rate and still uses a placeholder parent population.
    """
    levels = _level_lookup(level_rows or [])
    rows: List[dict] = []
    totals = {"f": 0.0, "i": 0.0, "r": 0.0}

    for row in type74_linkage_rows:
        comp = str(row.get("source_level_triplet_component") or "")
        if comp not in {"f", "i", "r"}:
            continue
        raw = row.get("type74_raw_reals_preview")
        reals: List[float] = []
        if isinstance(raw, str):
            # raw preview is written as a Python list string in v0.3.26.  Avoid
            # importing ast globally; parse conservatively for floats.
            import ast
            try:
                parsed = ast.literal_eval(raw)
                if isinstance(parsed, (list, tuple)):
                    reals = [float(x) for x in parsed]
            except Exception:
                reals = []
        elif isinstance(raw, (list, tuple)):
            reals = [float(x) for x in raw]

        ev = _xstar_calt74_alpha_diagnostic(float(temperature), reals)
        src_level = maybe_int(row.get("source_level"))
        lev = levels.get(int(src_level), {}) if src_level is not None else {}
        g_recombined = maybe_float(lev.get("statistical_weight_g"))
        g_continuum = 1.0
        alpha = maybe_float(ev.get("type74_alpha_unweighted_cm3_s"))
        stat_factor = None if g_recombined is None else float(g_recombined) / g_continuum
        alpha_weighted = None if alpha is None or stat_factor is None else alpha * stat_factor
        source_rate = None if alpha_weighted is None else alpha_weighted * float(electron_density) * float(parent_population_proxy)
        if source_rate is not None and math.isfinite(float(source_rate)) and source_rate > 0.0:
            totals[comp] += float(source_rate)

        rows.append({
            "type74_triplet_source_audit_version": "v0.3.27",
            "record": row.get("record"),
            "data_type": 74,
            "rate_type": row.get("rate_type"),
            "record_ion_stage": row.get("record_ion_stage"),
            "target_ion_stage": row.get("target_ion_stage"),
            "parent_ion_stage": row.get("parent_ion_stage"),
            "temperature_K": temperature,
            "electron_density_cm^-3": electron_density,
            "destination_level": src_level,
            "destination_label": row.get("source_level_label"),
            "triplet_component": comp,
            "type74_direct_triplet_candidate": True,
            **ev,
            "type74_recombined_stat_weight_g": g_recombined,
            "type74_parent_continuum_stat_weight_assumed": g_continuum,
            "type74_statistical_weight_factor_glo_over_ggup": stat_factor,
            "candidate_alpha_weighted_cm3_s": alpha_weighted,
            "candidate_source_rate_s^-1": source_rate,
            "candidate_source_rate_note": "source_rate = alpha_unweighted * g_recombined/g_continuum * ne * parent_population_proxy; diagnostic only",
            "matrix_safe_to_assemble": False,
            "unsafe_reason": ";".join([
                "type74_direct_triplet_source_is_diagnostic_only",
                "requires_full_calt74_bound_free_context_and_parent_continuum_population_before_assembly",
                "parent_population_proxy_is_placeholder",
                "global_element_matrix_not_yet_implemented",
            ]),
        })

    total = totals["f"] + totals["i"] + totals["r"]
    frac = {k: (totals[k] / total if total > 0.0 else 0.0) for k in ("f", "i", "r")}
    # Built-in reference target from the current C V ne=1e8 benchmark used in
    # this development thread.  For other ions/stages the fields remain blank.
    target = None
    stages = {maybe_int(r.get("target_ion_stage")) for r in rows}
    if stages == {5}:
        tf, ti, tr = 0.807706, 0.00663334, 0.185660
        tsum = tf + ti + tr
        target = {"f": tf / tsum, "i": ti / tsum, "r": tr / tsum}
    l2 = None
    if target is not None:
        l2 = math.sqrt(sum((frac[k] - target[k]) ** 2 for k in ("f", "i", "r")))
    dominant = max(("f", "i", "r", "none"), key=lambda k: {"f": frac["f"], "i": frac["i"], "r": frac["r"], "none": 0.0}[k])
    rows.append({
        "type74_triplet_source_audit_version": "v0.3.27",
        "record": "TOTAL_TYPE74_DIRECT_TRIPLET",
        "data_type": 74,
        "rate_type": "aggregate",
        "temperature_K": temperature,
        "electron_density_cm^-3": electron_density,
        "triplet_component": "aggregate",
        "n_direct_triplet_candidate_rows": len([r for r in rows if r.get("type74_direct_triplet_candidate")]),
        "total_source_rate_f_s^-1": totals["f"],
        "total_source_rate_i_s^-1": totals["i"],
        "total_source_rate_r_s^-1": totals["r"],
        "total_source_rate_triplet_s^-1": total,
        "source_fraction_f": frac["f"],
        "source_fraction_i": frac["i"],
        "source_fraction_r": frac["r"],
        "source_vector_dominant_component": dominant,
        "xstar_target_name": "C_V_ne1e8_fir_fraction" if target is not None else "not_available_for_this_target_stage",
        "xstar_target_fraction_f": None if target is None else target["f"],
        "xstar_target_fraction_i": None if target is None else target["i"],
        "xstar_target_fraction_r": None if target is None else target["r"],
        "source_vector_minus_target_f": None if target is None else frac["f"] - target["f"],
        "source_vector_minus_target_i": None if target is None else frac["i"] - target["i"],
        "source_vector_minus_target_r": None if target is None else frac["r"] - target["r"],
        "source_vector_l2_distance_to_target": l2,
        "matrix_safe_to_assemble": False,
        "unsafe_reason": "aggregate_diagnostic_only_not_assembled",
    })
    return rows




def _parse_triplet_source_scales(value: object) -> List[float]:
    """Parse one or more diagnostic triplet-source scale factors."""
    if value is None:
        return [1.0]
    if isinstance(value, (int, float)):
        vals = [float(value)]
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            vals = [1.0]
        else:
            vals = []
            for part in text.replace(";", ",").split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    vals.append(float(part))
                except Exception:
                    raise ValueError(f"Invalid --triplet-source-scale value {part!r}")
    else:
        vals = []
        try:
            for item in value:  # type: ignore[operator]
                vals.append(float(item))
        except TypeError:
            vals = [float(value)]
    vals = [v for v in vals if math.isfinite(float(v))]
    return vals or [1.0]


def _scale_source_by_level(source_by_level: Dict[int, float], scale: float) -> Dict[int, float]:
    return {int(k): float(v) * float(scale) for k, v in source_by_level.items()}


def _xstar_triplet_target(target_ion_stage: int) -> Optional[dict]:
    """Return built-in normalized XSTAR f/i/r benchmark targets when known.

    These targets are development diagnostics used by the C V source-vector
    experiments. They are intentionally limited: for other ions or density
    cases, callers receive None and should still write the scan without target
    distances.
    """
    try:
        stage = int(target_ion_stage)
    except Exception:
        return None
    if stage == 5:
        tf, ti, tr = 0.807706, 0.00663334, 0.185660
        tsum = tf + ti + tr
        if tsum > 0.0:
            return {
                "name": "C_V_ne1e8_fir_fraction",
                "f": tf / tsum,
                "i": ti / tsum,
                "r": tr / tsum,
            }
    return None


def build_triplet_source_scale_scan(
    *,
    baseline_triplet: dict,
    scan_triplets: Sequence[tuple[float, dict, dict]],
    source_by_level: Dict[int, float],
    type74_triplet_source_rows: Sequence[dict],
    target_ion_stage: int,
    mode: str,
) -> List[dict]:
    """Build a scale-scan table for diagnostic type-74 triplet source injection."""
    target = _xstar_triplet_target(target_ion_stage)
    base = _triplet_fraction_record("baseline", baseline_triplet, target=target)
    total_source = sum(float(v) for v in source_by_level.values()) if source_by_level else 0.0
    levels = ";".join(str(k) for k in sorted(source_by_level))
    common = {
        "triplet_source_mode": mode,
        "unscaled_total_type74_source_rate_s^-1": total_source,
        "n_injected_source_levels": len(source_by_level),
        "injected_source_levels": levels,
        "type74_direct_candidate_rows": sum(1 for r in type74_triplet_source_rows if _truthy(r.get("type74_direct_triplet_candidate"))),
        "diagnostic_note": "scale * evaluated type-74 direct triplet source was injected into the current single-ion source vector; this is a diagnostic scan, not the final element-wide matrix assembly.",
    }
    rows: List[dict] = []
    base.update(common)
    base.update({
        "triplet_source_scale": 0.0,
        "scaled_total_injected_source_rate_s^-1": 0.0,
        "scan_status": "baseline_no_extra_source",
    })
    rows.append(base)
    for scale, trip, block in scan_triplets:
        rec = _triplet_fraction_record("type74_source_injected_scaled", trip, target=target)
        rec.update(common)
        rec.update({
            "triplet_source_scale": float(scale),
            "scaled_total_injected_source_rate_s^-1": float(scale) * total_source,
            "injected_matrix_size": block.get("matrix_size"),
            "injected_solve_status": block.get("solve_status"),
            "injected_extra_source_sum_s^-1": block.get("extra_source_sum_s^-1"),
            "scan_status": "scale_solved",
        })
        rows.append(rec)
    if target is not None:
        rows.append({
            "case": "xstar_target",
            "triplet_source_mode": mode,
            "triplet_source_scale": "target",
            "f_fraction": target["f"],
            "i_fraction": target["i"],
            "r_fraction": target["r"],
            "target_f_fraction": target["f"],
            "target_i_fraction": target["i"],
            "target_r_fraction": target["r"],
            "delta_f_minus_target": 0.0,
            "delta_i_minus_target": 0.0,
            "delta_r_minus_target": 0.0,
            "l2_distance_to_target": 0.0,
            "scan_status": "reference_target",
        })
    return rows

def _type74_direct_triplet_source_by_level(rows: Sequence[dict]) -> Dict[int, float]:
    """Return level-index -> diagnostic source rate from type-74 triplet rows."""
    out: Dict[int, float] = {}
    for row in rows:
        if str(row.get("record")) == "TOTAL_TYPE74_DIRECT_TRIPLET":
            continue
        if not _truthy(row.get("type74_direct_triplet_candidate")):
            continue
        lev = maybe_int(row.get("destination_level"))
        rate = maybe_float(row.get("candidate_source_rate_s^-1"))
        if lev is None or rate is None or not math.isfinite(float(rate)) or float(rate) <= 0.0:
            continue
        out[int(lev)] = out.get(int(lev), 0.0) + float(rate)
    return out


def _triplet_fraction_record(label: str, trip: dict, *, target: Optional[dict] = None) -> dict:
    f = maybe_float(trip.get("f_fraction")) or 0.0
    i = maybe_float(trip.get("i_fraction")) or 0.0
    r = maybe_float(trip.get("r_fraction")) or 0.0
    rec = {
        "case": label,
        "f_fraction": f,
        "i_fraction": i,
        "r_fraction": r,
        "R": trip.get("R"),
        "G": trip.get("G"),
    }
    if target is not None:
        rec.update({
            "target_f_fraction": target.get("f"),
            "target_i_fraction": target.get("i"),
            "target_r_fraction": target.get("r"),
            "delta_f_minus_target": f - float(target.get("f", 0.0)),
            "delta_i_minus_target": i - float(target.get("i", 0.0)),
            "delta_r_minus_target": r - float(target.get("r", 0.0)),
            "l2_distance_to_target": math.sqrt((f - float(target.get("f", 0.0))) ** 2 + (i - float(target.get("i", 0.0))) ** 2 + (r - float(target.get("r", 0.0))) ** 2),
        })
    return rec


def build_triplet_source_injection_comparison(
    *,
    baseline_triplet: dict,
    injected_triplet: dict,
    type74_triplet_source_rows: Sequence[dict],
    target_ion_stage: int,
    mode: str,
) -> List[dict]:
    """Build before/after f/i/r comparison for diagnostic triplet source injection."""
    source_map = _type74_direct_triplet_source_by_level(type74_triplet_source_rows)
    total_source = sum(float(v) for v in source_map.values())
    target = _xstar_triplet_target(target_ion_stage)
    rows = []
    meta = {
        "triplet_source_mode": mode,
        "source_level_rates": ";".join(f"{lev}:{rate:.8e}" for lev, rate in sorted(source_map.items())),
        "total_injected_source_rate_s^-1": total_source,
        "n_injected_source_levels": len(source_map),
        "source_is_diagnostic_only": True,
        "injection_note": "type-74 direct triplet source rates were added to the existing single-ion source vector for a diagnostic before/after solve; this is not the final element-wide matrix assembly.",
    }
    for rec in (
        _triplet_fraction_record("baseline", baseline_triplet, target=target),
        _triplet_fraction_record("type74_source_injected", injected_triplet, target=target),
    ):
        rec.update(meta)
        rows.append(rec)
    if target is not None:
        rec = {
            "case": "xstar_target",
            "f_fraction": target["f"],
            "i_fraction": target["i"],
            "r_fraction": target["r"],
            "R": target["f"] / target["i"] if target["i"] else None,
            "G": (target["f"] + target["i"]) / target["r"] if target["r"] else None,
            "target_f_fraction": target["f"],
            "target_i_fraction": target["i"],
            "target_r_fraction": target["r"],
            "delta_f_minus_target": 0.0,
            "delta_i_minus_target": 0.0,
            "delta_r_minus_target": 0.0,
            "l2_distance_to_target": 0.0,
        }
        rec.update(meta)
        rows.append(rec)
    return rows

def build_adjacent_coupling_terms(
    db: ATDB,
    *,
    z: int,
    target_ion_stage: int,
    parent_ion_stage: int,
    temperature: float,
    electron_density: float,
    level_indices: Sequence[int],
    level_rows: Sequence[dict],
    coupling_mode: str = "recombination-source",
    coupling_source_mode: str = "record-destination",
    selected_source_levels: Optional[Sequence[int]] = None,
    include_charge_exchange: bool = False,
    parent_population_proxy: float = 1.0,
    type57_energy_convention: str = "compare",
) -> Tuple[np.ndarray, np.ndarray, List[dict]]:
    """Build prototype adjacent-ion source/sink vectors for one target ion.

    This is a source-code-guided reference implementation of the part of the
    XSTAR ``calc_hmc_element -> calc_hmc_ion -> ucalc`` path that couples an
    ion to its adjacent higher ion.  The current implementation is conservative:

    * electron recombination records with implemented temperature fits are
      evaluated and assembled as source terms into the target ion;
    * photoionization-like records (notably data types 53, 74, 99) and
      collisional-ionization-like records (57, 95) are catalogued but not used
      as rates, because they require XSTAR's radiation field / electron-impact
      ionization context;
    * the assembled source vector has units of s^-1 in the same prototype
      convention used by :func:`solve_steady_state`.

    The function returns ``(source_vector, sink_rates, rows)`` where ``rows`` is
    a transparent audit trail containing both assembled and unassembled records.
    """
    n = len(level_indices)
    source = np.zeros(n, dtype=float)
    sink = np.zeros(n, dtype=float)
    idx = {int(lev): k for k, lev in enumerate(level_indices)}
    nlevp_guess = (max(idx) + 1) if idx else None
    selected = [int(x) for x in (selected_source_levels or [])]
    rows: List[dict] = []

    if str(coupling_mode or "none").lower() in {"", "none", "catalog", "catalogue", "catalog-only"}:
        mode = "catalog_only"
    else:
        mode = "assemble_recombination_source"

    records = _select_records(db, z, target_ion_stage, use_cache=True, cache_path=None)
    recomb_rows = extract_recombination_records(db, records, z, target_ion_stage)
    evaluated = evaluate_records(db, recomb_rows, [temperature], include_charge_exchange=include_charge_exchange)
    for rec in evaluated:
        if int(rec.get("parent_ion_stage") or -1) != int(parent_ion_stage):
            continue
        dt = int(rec.get("data_type") or -1)
        alpha = maybe_float(rec.get("alpha_cm3_s"))
        assembled = False
        allocation_note = ""
        allocated_levels: List[Tuple[int, float, str]] = []
        source_rate_total = None
        if mode == "assemble_recombination_source" and dt in EVALUABLE_RECOMBINATION_DATA_TYPES and alpha is not None and alpha > 0.0:
            source_rate_total = float(alpha) * float(electron_density) * float(parent_population_proxy)
            try:
                allocated_levels = allocation_levels(
                    coupling_source_mode,
                    selected,
                    list(level_rows),
                    rec,
                )
            except Exception as exc:
                allocated_levels = []
                allocation_note = f"allocation_error:{exc.__class__.__name__}"
            if not allocated_levels and coupling_source_mode not in {"none", "catalog"}:
                # Fall back to ground if the requested allocation mode yielded no
                # usable level.  This mirrors XSTAR's tendency to assign many
                # total recombination records to idest1=1, but keeps the note.
                allocated_levels = [(1, 1.0, "fallback_total_recombination_to_ground")]
            wsum = sum(max(float(w), 0.0) for _lev, w, _note in allocated_levels)
            if wsum > 0.0:
                for lev, w, note in allocated_levels:
                    if int(lev) in idx and w > 0.0:
                        source[idx[int(lev)]] += source_rate_total * float(w) / wsum
                        assembled = True
                        allocation_note = note
        base_row = {
            "element": Z_TO_SYMBOL.get(z, str(z)),
            "element_z": z,
            "target_ion_stage": target_ion_stage,
            "parent_ion_stage": parent_ion_stage,
            "record": rec.get("record"),
            "data_type": dt,
            "rate_type": rec.get("rate_type"),
            "coupling_role": "adjacent_recombination_source",
            "temperature_K": temperature,
            "electron_density_cm^-3": electron_density,
            "alpha_cm3_s": alpha,
            "source_rate_total_s^-1": source_rate_total,
            "destination_level": rec.get("destination_level"),
            "coupling_mode": coupling_mode,
            "coupling_source_mode": coupling_source_mode,
            "assembled": bool(assembled),
            "assembly_status": "assembled_recombination_source" if assembled else ("catalogued_evaluable_but_not_assembled" if alpha is not None else rec.get("eval_method")),
            "allocation_note": allocation_note,
            "ucalc_branch": f"type_{dt}",
            "ucalc_source_file": "xstarlib/src/ucalc.f90",
            "ucalc_ans1_role": "",
            "ucalc_ans2_role": "electron_recombination_source_coefficient",
            "matrix_role_if_implemented": "adjacent_parent_to_target_source",
            "requires_context": "temperature_and_electron_density_only_for_current_total_recombination_fit",
            "python_eval_status": rec.get("eval_method"),
        }
        base_row.update(_audit_recombination_source_role(
            data_type=dt,
            rate_type=maybe_int(rec.get("rate_type")),
            record_ion_stage=maybe_int(rec.get("ion_stage") or target_ion_stage),
            target_ion_stage=target_ion_stage,
            parent_ion_stage=parent_ion_stage,
            destination_level=maybe_int(rec.get("destination_level")),
            level_rows=level_rows,
            level_indices=level_indices,
        ))
        rows.append(base_row)

    # Preserve the important but not-yet-evaluable adjacent-ion records called
    # out in the source-code audit.  These rows are intentionally not converted
    # into rates yet.
    for stage in (target_ion_stage, parent_ion_stage):
        for r in _select_records(db, z, stage, use_cache=True, cache_path=None):
            if r.data_type in PHOTOIONIZATION_LIKE_DATA_TYPES or r.data_type in COLLISIONAL_IONIZATION_LIKE_DATA_TYPES or r.rate_type in {1, 5, 7}:
                role = "photoionization_like_sink_or_inverse_recombination" if r.data_type in PHOTOIONIZATION_LIKE_DATA_TYPES or r.rate_type in {1, 7} else "collisional_ionization_like_sink"
                audit = audit_ucalc_adjacent_record(
                    db, r,
                    target_ion_stage=target_ion_stage,
                    parent_ion_stage=parent_ion_stage,
                    temperature=temperature,
                    electron_density=electron_density,
                    nlevp=nlevp_guess,
                    level_rows=level_rows,
                    level_indices=level_indices,
                    type57_energy_convention=type57_energy_convention,
                )
                audit.update({
                    "element": Z_TO_SYMBOL.get(z, str(z)),
                    "element_z": z,
                    "record_ion_stage": stage,
                    "coupling_role": role,
                    "temperature_K": temperature,
                    "electron_density_cm^-3": electron_density,
                    "assembled": False,
                    "coupling_mode": coupling_mode,
                })
                if not str(audit.get("assembly_status") or "").startswith("catalogued"):
                    audit["assembly_status"] = "catalogued_not_assembled_ucalc_audit"
                rows.append(audit)

    return source, sink, rows



def _classify_global_level_kind(row: dict) -> str:
    """Classify a level row for the v0.3.31 global element index.

    This is intentionally diagnostic and conservative.  XSTAR level records
    explicitly mark some rows as ``superlevel`` or ``continuum`` in the
    character label; otherwise we keep the row as spectroscopic, even when it
    lies above the ionization threshold (autoionizing spectroscopic/satellite
    levels are still explicit states in the later matrix plan).
    """
    label = str(row.get("level_label") or "").strip().lower()
    if "continuum" in label or label == "cont" or label.startswith("continuum"):
        return "continuum"
    # XSTAR/ATDB labels for superlevels are not always written as the
    # literal word ``superlevel``.  In the C V block, the superlevel rows
    # appear as labels such as ``sprlevls`` and ``sprlevlt``; those rows are
    # the same levels linked by type-71/type-77/type-99 superlevel cascade
    # diagnostics and must be represented as explicit superlevel states before
    # global matrix assembly.
    if (
        "superlevel" in label
        or "super level" in label
        or label == "super"
        or label.startswith("sprlev")
        or label.startswith("sup")
    ):
        return "superlevel"
    return "spectroscopic"


def _global_index_triplet_component(row: dict, *, he_like_stage: int) -> str:
    if maybe_int(row.get("ion_stage")) != int(he_like_stage):
        return ""
    return _triplet_component_from_level_label(str(row.get("level_label") or ""))


def build_element_global_index(
    db: ATDB,
    *,
    z: int,
    stages: Sequence[int],
    he_like_stage: int,
    max_level: Optional[int] = None,
    use_cache: bool = True,
    cache_path: Optional[str] = None,
) -> List[dict]:
    """Build the explicit element-wide state index scaffold.

    v0.3.31 does not yet assemble or solve the global matrix.  It creates the
    canonical state map needed for that next step: one row per decoded level for
    all selected ion stages plus an explicit parent-continuum placeholder for
    each lower->upper adjacent pair when no continuum row is already obvious.
    """
    rows: List[dict] = []
    seen: set[tuple[int, str]] = set()
    for stage in sorted({int(s) for s in stages if int(s) > 0}, reverse=True):
        records = _select_records(db, z, stage, use_cache=use_cache, cache_path=cache_path)
        levels = extract_levels(db, records, z, stage)
        for lev in levels:
            level_index = maybe_int(lev.get("level_index"))
            if level_index is None:
                continue
            if max_level is not None and int(level_index) > int(max_level):
                # Keep continuum-like levels even if they happen to sit beyond
                # max_level; they are structural rows needed by the global map.
                k_tmp = _classify_global_level_kind(lev)
                if k_tmp not in {"continuum", "superlevel"}:
                    continue
            level_kind = _classify_global_level_kind(lev)
            comp = _global_index_triplet_component(lev, he_like_stage=he_like_stage)
            key = (int(stage), str(level_index))
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "global_index": None,  # filled after placeholders are appended
                "element": Z_TO_SYMBOL.get(z, str(z)),
                "element_z": z,
                "ion_stage": int(stage),
                "ion_roman": roman(int(stage)),
                "level_index": int(level_index),
                "level_kind": level_kind,
                "energy_eV": lev.get("energy_eV"),
                "stat_weight": lev.get("statistical_weight_g"),
                "statistical_weight_g": lev.get("statistical_weight_g"),
                "configuration": lev.get("level_label"),
                "level_label": lev.get("level_label"),
                "ionization_potential_eV": lev.get("ionization_potential_eV"),
                "binding_from_continuum_eV": lev.get("binding_from_continuum_eV"),
                "is_triplet_upper": bool(comp),
                "triplet_component": comp,
                "is_superlevel": level_kind == "superlevel",
                "is_continuum": level_kind == "continuum",
                "is_parent_continuum_placeholder": False,
                "parent_ion_stage": "",
                "parent_level_index": "",
                "continuum_represents_parent": False,
                "source": "decoded_type6_level_record",
            })

    # Add explicit continuum/parent-continuum placeholders for adjacent stages.
    # These placeholders are the structural prerequisite for later matrix terms
    # like C V(level) <-> C VI(parent continuum).  They are not solved in v0.3.31.
    stage_set = {int(s) for s in stages if int(s) > 0}
    for lower in sorted(stage_set, reverse=True):
        upper = lower + 1
        if upper not in stage_set:
            continue
        has_cont = any(
            maybe_int(r.get("ion_stage")) == lower and bool(r.get("is_continuum"))
            for r in rows
        )
        if has_cont:
            continue
        key = (int(lower), "parent_continuum_placeholder")
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "global_index": None,
            "element": Z_TO_SYMBOL.get(z, str(z)),
            "element_z": z,
            "ion_stage": int(lower),
            "ion_roman": roman(int(lower)),
            "level_index": 0,
            "level_kind": "parent_continuum_placeholder",
            "energy_eV": "",
            "stat_weight": 1.0,
            "statistical_weight_g": 1.0,
            "configuration": f"{Z_TO_SYMBOL.get(z, str(z))} {roman(int(upper))} parent continuum placeholder",
            "level_label": f"parent continuum placeholder for {Z_TO_SYMBOL.get(z, str(z))} {roman(int(upper))}",
            "ionization_potential_eV": "",
            "binding_from_continuum_eV": 0.0,
            "is_triplet_upper": False,
            "triplet_component": "",
            "is_superlevel": False,
            "is_continuum": True,
            "is_parent_continuum_placeholder": True,
            "parent_ion_stage": int(upper),
            "parent_level_index": 1,
            "continuum_represents_parent": True,
            "source": "v0.3.32_explicit_parent_continuum_placeholder",
        })

    # When a lower-ion continuum row already exists, keep it as the physical
    # continuum state and annotate it with the adjacent parent ion represented
    # by that continuum.  This avoids duplicating the continuum row while still
    # making the future global matrix mapping explicit.
    for r in rows:
        stage = maybe_int(r.get("ion_stage"))
        if stage is None or not bool(r.get("is_continuum")):
            continue
        upper = int(stage) + 1
        if upper in stage_set:
            r["parent_ion_stage"] = int(upper)
            r["parent_level_index"] = 1
            r["continuum_represents_parent"] = True

    def _sort_key(r: dict):
        stage = maybe_int(r.get("ion_stage")) or 0
        placeholder = 1 if r.get("is_parent_continuum_placeholder") else 0
        li = maybe_int(r.get("level_index"))
        if li is None:
            li = 10**9
        return (-stage, placeholder, li, str(r.get("configuration") or ""))

    rows.sort(key=_sort_key)
    for i, r in enumerate(rows):
        r["global_index"] = i
    return rows


def _global_index_summary(rows: Sequence[dict]) -> dict:
    def _counts(col: str) -> dict:
        out: Dict[str, int] = {}
        for r in rows:
            key = r.get(col)
            key = "" if key is None else str(key)
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: kv[0]))
    return {
        "n_global_index_rows": len(rows),
        "rows_by_ion_stage": _counts("ion_stage"),
        "rows_by_level_kind": _counts("level_kind"),
        "n_triplet_upper_rows": sum(1 for r in rows if bool(r.get("is_triplet_upper"))),
        "triplet_component_counts": _counts("triplet_component"),
        "n_superlevel_rows": sum(1 for r in rows if bool(r.get("is_superlevel"))),
        "n_continuum_rows": sum(1 for r in rows if bool(r.get("is_continuum"))),
        "n_parent_continuum_placeholders": sum(1 for r in rows if bool(r.get("is_parent_continuum_placeholder"))),
        "provenance": {
            "mode": "v0.3.32 fixes superlevel classification and parent-continuum mapping in xstar_like_element_solver_global_index.csv.",
            "assembly": "No global matrix terms are assembled from this index yet; it is the structural prerequisite for the later pure-Python element-wide solve.",
        },
    }


def _global_index_lookup(rows: Sequence[dict]) -> Dict[tuple[int, int], dict]:
    """Return ``(ion_stage, level_index) -> global-index row`` for real levels.

    Placeholder continuum rows may use level_index=0 and are therefore kept
    out of the normal bound-bound lookup.  Bound-bound matrix terms should only
    connect decoded levels present in the global state index.
    """
    out: Dict[tuple[int, int], dict] = {}
    for row in rows:
        stage = maybe_int(row.get("ion_stage"))
        level = maybe_int(row.get("level_index"))
        gidx = maybe_int(row.get("global_index"))
        if stage is None or level is None or gidx is None:
            continue
        out[(int(stage), int(level))] = row
    return out


def build_global_bound_bound_matrix_terms(
    transition_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
) -> List[dict]:
    """Map existing intra-ion bound-bound transition logs onto global indices.

    v0.3.33 is a scaffold for the later element-wide linear system.  It does
    not solve the global matrix yet.  For each current per-ion bound-bound
    transition ``from_level -> to_level`` it writes the two matrix entries that
    would appear in a population-rate matrix with column = source state and row
    = destination state:

    * an off-diagonal gain term ``M[to, from] += rate``;
    * a diagonal loss term ``M[from, from] -= rate``.

    Only radiative and collisional bound-bound transition kinds from the current
    per-ion assembly are mapped.  Bound-free, recombination, type-74 source,
    and superlevel-source terms remain diagnostic-only and are not included here.
    """
    lookup = _global_index_lookup(global_index_rows)
    out: List[dict] = []
    allowed = {
        "radiative_decay",
        "collisional_excitation",
        "collisional_deexcitation",
        "phenomenological_same_n_lmixing",
    }
    term_id = 0
    for tr in transition_rows:
        kind = str(tr.get("kind") or "")
        if kind not in allowed:
            continue
        stage = maybe_int(tr.get("ion_stage"))
        from_level = maybe_int(tr.get("from_level"))
        to_level = maybe_int(tr.get("to_level"))
        rate = maybe_float(tr.get("rate_s^-1"))
        if stage is None or from_level is None or to_level is None or rate is None:
            continue
        if not math.isfinite(float(rate)) or float(rate) <= 0.0:
            continue
        from_row = lookup.get((int(stage), int(from_level)))
        to_row = lookup.get((int(stage), int(to_level)))
        if from_row is None or to_row is None:
            missing = []
            if from_row is None:
                missing.append("from_level_missing_from_global_index")
            if to_row is None:
                missing.append("to_level_missing_from_global_index")
            # Keep a skipped row for auditability; it is not a matrix entry.
            out.append({
                "global_term_id": term_id,
                "matrix_term_kind": "skipped_bound_bound_transition",
                "matrix_role": "not_assembled_missing_global_index",
                "element": tr.get("element"),
                "ion_stage": int(stage),
                "transition_kind": kind,
                "from_level": int(from_level),
                "to_level": int(to_level),
                "rate_s^-1": float(rate),
                "signed_rate_s^-1": 0.0,
                "record": tr.get("record"),
                "source_method": tr.get("source_method"),
                "assembly_status": "skipped",
                "skip_reason": ";".join(missing),
                "provenance": "v0.3.33_global_bound_bound_matrix_scaffold",
            })
            term_id += 1
            continue
        from_g = int(from_row["global_index"])
        to_g = int(to_row["global_index"])
        common = {
            "element": tr.get("element"),
            "element_z": from_row.get("element_z"),
            "ion_stage": int(stage),
            "ion_roman": from_row.get("ion_roman"),
            "transition_kind": kind,
            "from_level": int(from_level),
            "to_level": int(to_level),
            "from_global_index": from_g,
            "to_global_index": to_g,
            "from_level_label": from_row.get("level_label"),
            "to_level_label": to_row.get("level_label"),
            "from_level_kind": from_row.get("level_kind"),
            "to_level_kind": to_row.get("level_kind"),
            "rate_s^-1": float(rate),
            "record": tr.get("record"),
            "source_method": tr.get("source_method"),
            "temperature_K": tr.get("temperature_K"),
            "electron_density_cm^-3": tr.get("electron_density_cm^-3"),
            "assembly_status": "assembled_global_bound_bound_scaffold",
            "skip_reason": "",
            "provenance": "v0.3.33_global_bound_bound_matrix_scaffold",
        }
        out.append({
            "global_term_id": term_id,
            "matrix_term_kind": "offdiag_gain",
            "matrix_role": "bound_bound_gain_to_destination",
            "matrix_row_global_index": to_g,
            "matrix_col_global_index": from_g,
            "signed_rate_s^-1": float(rate),
            **common,
        })
        term_id += 1
        out.append({
            "global_term_id": term_id,
            "matrix_term_kind": "diagonal_loss",
            "matrix_role": "bound_bound_loss_from_source",
            "matrix_row_global_index": from_g,
            "matrix_col_global_index": from_g,
            "signed_rate_s^-1": -float(rate),
            **common,
        })
        term_id += 1
    return out


def _global_bound_bound_matrix_terms_summary(rows: Sequence[dict]) -> dict:
    assembled = [r for r in rows if str(r.get("assembly_status")) == "assembled_global_bound_bound_scaffold"]
    skipped = [r for r in rows if str(r.get("assembly_status")) == "skipped"]
    return {
        "n_global_bound_bound_matrix_term_rows": len(rows),
        "n_global_bound_bound_assembled_rows": len(assembled),
        "n_global_bound_bound_skipped_rows": len(skipped),
        "rows_by_matrix_term_kind": _counts(rows, "matrix_term_kind"),
        "rows_by_transition_kind": _counts(assembled, "transition_kind"),
        "rows_by_ion_stage": _counts(assembled, "ion_stage"),
        "n_unique_matrix_positions": len({
            (maybe_int(r.get("matrix_row_global_index")), maybe_int(r.get("matrix_col_global_index")))
            for r in assembled
            if maybe_int(r.get("matrix_row_global_index")) is not None and maybe_int(r.get("matrix_col_global_index")) is not None
        }),
        "provenance": {
            "mode": "v0.3.33 maps current per-ion bound-bound radiative/collisional transition logs onto the explicit global_index rows.",
            "assembly": "Diagnostic scaffold only: writes sparse-like global matrix term triplets but does not solve the global element matrix yet.",
            "terms": "For each transition j->i, writes offdiag M[i,j]+=rate and diagonal M[j,j]-=rate.",
        },
    }


def build_global_superlevel_cascade_matrix_terms(
    superlevel_cascade_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
) -> List[dict]:
    """Map type-71 superlevel cascades onto global-index matrix entries.

    v0.3.35 keeps this diagnostic/scaffold-only.  For every type-71 record
    that can be mapped to an explicit superlevel row and an explicit
    spectroscopic row in ``xstar_like_element_solver_global_index.csv``, write
    the two matrix triplets needed by the future element-wide population
    matrix:

    * ``M[spectroscopic, superlevel] += A`` for the radiative cascade gain;
    * ``M[superlevel, superlevel] -= A`` for the superlevel loss.

    Type-77 collisional superlevel cascades and type-70/74/99 source terms are
    deliberately not included here.  They still require separate rate/source
    evaluators and parent-continuum population handling.
    """
    lookup = _global_index_lookup(global_index_rows)
    out: List[dict] = []
    term_id = 0
    for row in superlevel_cascade_rows:
        dt = maybe_int(row.get("data_type"))
        if dt != 71:
            continue
        stage = maybe_int(row.get("record_ion_stage"))
        lower = maybe_int(row.get("type71_lower_spectroscopic_level") or row.get("spectroscopic_level") or row.get("lower_level"))
        upper = maybe_int(row.get("type71_upper_superlevel_level") or row.get("superlevel_level") or row.get("upper_level"))
        rate = maybe_float(row.get("type71_A_or_rate_preview_s^-1"))
        if stage is None or lower is None or upper is None or rate is None:
            out.append({
                "global_superlevel_term_id": term_id,
                "matrix_term_kind": "skipped_type71_superlevel_cascade",
                "matrix_role": "not_assembled_missing_required_field",
                "data_type": dt,
                "record": row.get("record"),
                "ion_stage": stage if stage is not None else "",
                "spectroscopic_level": lower if lower is not None else "",
                "superlevel_level": upper if upper is not None else "",
                "rate_s^-1": rate if rate is not None else "",
                "signed_rate_s^-1": 0.0,
                "assembly_status": "skipped",
                "skip_reason": "missing_stage_or_level_or_type71_rate",
                "provenance": "v0.3.35_global_type71_superlevel_cascade_matrix_scaffold",
            })
            term_id += 1
            continue
        if not math.isfinite(float(rate)) or float(rate) <= 0.0:
            out.append({
                "global_superlevel_term_id": term_id,
                "matrix_term_kind": "skipped_type71_superlevel_cascade",
                "matrix_role": "not_assembled_nonpositive_rate",
                "data_type": dt,
                "record": row.get("record"),
                "ion_stage": int(stage),
                "spectroscopic_level": int(lower),
                "superlevel_level": int(upper),
                "rate_s^-1": float(rate),
                "signed_rate_s^-1": 0.0,
                "assembly_status": "skipped",
                "skip_reason": "nonpositive_or_nonfinite_type71_rate",
                "provenance": "v0.3.35_global_type71_superlevel_cascade_matrix_scaffold",
            })
            term_id += 1
            continue
        spec_row = lookup.get((int(stage), int(lower)))
        super_row = lookup.get((int(stage), int(upper)))
        missing = []
        if spec_row is None:
            missing.append("spectroscopic_level_missing_from_global_index")
        if super_row is None:
            missing.append("superlevel_level_missing_from_global_index")
        if super_row is not None and str(super_row.get("level_kind") or "") != "superlevel":
            missing.append("upper_level_is_not_classified_as_superlevel")
        if spec_row is not None and str(spec_row.get("level_kind") or "") == "continuum":
            missing.append("lower_level_is_continuum_not_spectroscopic_destination")
        if missing:
            out.append({
                "global_superlevel_term_id": term_id,
                "matrix_term_kind": "skipped_type71_superlevel_cascade",
                "matrix_role": "not_assembled_unmappable_or_misclassified_levels",
                "data_type": dt,
                "rate_type": row.get("rate_type"),
                "record": row.get("record"),
                "element": row.get("element"),
                "element_z": row.get("element_z"),
                "ion_stage": int(stage),
                "spectroscopic_level": int(lower),
                "superlevel_level": int(upper),
                "spectroscopic_global_index": "" if spec_row is None else spec_row.get("global_index"),
                "superlevel_global_index": "" if super_row is None else super_row.get("global_index"),
                "spectroscopic_level_label": "" if spec_row is None else spec_row.get("level_label"),
                "superlevel_level_label": "" if super_row is None else super_row.get("level_label"),
                "spectroscopic_level_kind": "" if spec_row is None else spec_row.get("level_kind"),
                "superlevel_level_kind": "" if super_row is None else super_row.get("level_kind"),
                "rate_s^-1": float(rate),
                "signed_rate_s^-1": 0.0,
                "assembly_status": "skipped",
                "skip_reason": ";".join(missing),
                "provenance": "v0.3.35_global_type71_superlevel_cascade_matrix_scaffold",
            })
            term_id += 1
            continue
        spec_g = int(spec_row["global_index"])
        super_g = int(super_row["global_index"])
        comp = row.get("cascade_feed_component") or _triplet_component_from_level_label(str(spec_row.get("level_label") or ""))
        common = {
            "data_type": 71,
            "rate_type": row.get("rate_type"),
            "record": row.get("record"),
            "element": row.get("element"),
            "element_z": row.get("element_z"),
            "ion_stage": int(stage),
            "ion_roman": spec_row.get("ion_roman"),
            "transition_kind": "type71_radiative_superlevel_cascade",
            "spectroscopic_level": int(lower),
            "superlevel_level": int(upper),
            "spectroscopic_global_index": spec_g,
            "superlevel_global_index": super_g,
            "spectroscopic_level_label": spec_row.get("level_label"),
            "superlevel_level_label": super_row.get("level_label"),
            "spectroscopic_level_kind": spec_row.get("level_kind"),
            "superlevel_level_kind": super_row.get("level_kind"),
            "destination_triplet_component": comp,
            "feeds_forbidden_upper": bool(row.get("feeds_forbidden_upper")),
            "feeds_intercombination_upper": bool(row.get("feeds_intercombination_upper")),
            "feeds_resonance_upper": bool(row.get("feeds_resonance_upper")),
            "feeds_any_triplet_component": bool(row.get("feeds_any_triplet_component")),
            "rate_s^-1": float(rate),
            "assembly_status": "assembled_global_type71_superlevel_cascade_scaffold",
            "skip_reason": "",
            "provenance": "v0.3.35_global_type71_superlevel_cascade_matrix_scaffold",
            "notes": "Diagnostic scaffold only; no global element-wide solve includes these terms yet.",
        }
        out.append({
            "global_superlevel_term_id": term_id,
            "matrix_term_kind": "offdiag_gain",
            "matrix_role": "type71_superlevel_cascade_gain_to_spectroscopic_destination",
            "matrix_row_global_index": spec_g,
            "matrix_col_global_index": super_g,
            "signed_rate_s^-1": float(rate),
            **common,
        })
        term_id += 1
        out.append({
            "global_superlevel_term_id": term_id,
            "matrix_term_kind": "diagonal_loss",
            "matrix_role": "type71_superlevel_cascade_loss_from_superlevel_source",
            "matrix_row_global_index": super_g,
            "matrix_col_global_index": super_g,
            "signed_rate_s^-1": -float(rate),
            **common,
        })
        term_id += 1
    return out


def _global_superlevel_cascade_matrix_terms_summary(rows: Sequence[dict]) -> dict:
    assembled = [r for r in rows if str(r.get("assembly_status")) == "assembled_global_type71_superlevel_cascade_scaffold"]
    skipped = [r for r in rows if str(r.get("assembly_status")) == "skipped"]
    return {
        "n_global_superlevel_cascade_matrix_term_rows": len(rows),
        "n_global_superlevel_cascade_assembled_rows": len(assembled),
        "n_global_superlevel_cascade_skipped_rows": len(skipped),
        "rows_by_matrix_term_kind": _counts(rows, "matrix_term_kind"),
        "rows_by_ion_stage": _counts(assembled, "ion_stage"),
        "rows_by_destination_triplet_component": _counts(assembled, "destination_triplet_component"),
        "n_unique_type71_records_assembled": len({str(r.get("record")) for r in assembled if str(r.get("matrix_term_kind")) == "offdiag_gain"}),
        "n_terms_feeding_triplet_upper": sum(1 for r in assembled if bool(r.get("feeds_any_triplet_component")) and str(r.get("matrix_term_kind")) == "offdiag_gain"),
        "total_type71_gain_rate_s^-1": sum(float(maybe_float(r.get("rate_s^-1")) or 0.0) for r in assembled if str(r.get("matrix_term_kind")) == "offdiag_gain"),
        "total_type71_triplet_gain_rate_s^-1": sum(float(maybe_float(r.get("rate_s^-1")) or 0.0) for r in assembled if str(r.get("matrix_term_kind")) == "offdiag_gain" and bool(r.get("feeds_any_triplet_component"))),
        "provenance": {
            "mode": "v0.3.35 maps type-71 radiative superlevel-to-spectroscopic cascade records onto explicit global_index rows.",
            "assembly": "Diagnostic scaffold only: writes M[spectroscopic,superlevel]+=A and M[superlevel,superlevel]-=A matrix triplets but does not include them in the solved global matrix yet.",
            "excluded": "Type-77 collisional superlevel cascades and type-70/type-74/type-99 superlevel source terms remain diagnostic-only.",
        },
    }



def _find_parent_continuum_global_row(global_index_rows: Sequence[dict], *, ion_stage: int) -> Optional[dict]:
    """Return the continuum row in ``ion_stage`` representing the next parent ion.

    v0.3.38 uses this only for a diagnostic type-99 source scaffold.  The
    continuum row is not yet solved as a physically normalised parent-ion
    population, but it provides the explicit column needed by the later global
    C VI + C V matrix.
    """
    parent = int(ion_stage) + 1
    for row in global_index_rows:
        st = maybe_int(row.get("ion_stage"))
        if st != int(ion_stage):
            continue
        if not bool(row.get("is_continuum")):
            continue
        pr = maybe_int(row.get("parent_ion_stage"))
        if pr is None or int(pr) == parent:
            return row
    return None


def build_global_superlevel_source_matrix_terms(
    superlevel_source_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
) -> List[dict]:
    """Map type-99 superlevel source candidates onto the global index.

    v0.3.38 is a diagnostic scaffold, not a physical type-99 evaluator.  The
    source audit already identifies type-99 records associated with a given
    superlevel.  This routine maps those candidates to explicit global-index
    rows and writes transparent proxy terms that future element-wide assembly can
    replace by real XSTAR ``phint53pl``/superlevel recombination rates:

    * a source-vector proxy into the superlevel row;
    * when a parent-continuum row exists, a parent-continuum -> superlevel
      off-diagonal matrix proxy;
    * a matching parent-continuum diagonal-loss proxy, clearly marked as a
      proxy, so the future matrix topology is explicit.

    The proxy value is the type-99 coefficient-magnitude preview when available;
    otherwise it falls back to one count unit per type-99 source candidate.  No
    proxy term is included in any solved matrix in this version.
    """
    lookup = _global_index_lookup(global_index_rows)
    out: List[dict] = []
    term_id = 0
    for row in superlevel_source_rows:
        n99_val = maybe_float(row.get("n_type99_superlevel_source_candidates"))
        n99 = int(n99_val) if n99_val is not None and math.isfinite(float(n99_val)) else 0
        if n99 <= 0:
            continue
        stage = maybe_int(row.get("record_ion_stage") or row.get("target_ion_stage"))
        sl = maybe_int(row.get("superlevel_level"))
        if stage is None or sl is None:
            out.append({
                "global_superlevel_source_term_id": term_id,
                "matrix_term_kind": "skipped_type99_superlevel_source",
                "matrix_role": "not_assembled_missing_stage_or_superlevel",
                "data_type": 99,
                "ion_stage": stage if stage is not None else "",
                "superlevel_level": sl if sl is not None else "",
                "n_type99_source_candidates": n99,
                "type99_records": row.get("type99_records"),
                "source_proxy_value": 0.0,
                "signed_rate_proxy": 0.0,
                "assembly_status": "skipped",
                "skip_reason": "missing_record_ion_stage_or_superlevel_level",
                "provenance": "v0.3.38_global_type99_superlevel_source_scaffold",
            })
            term_id += 1
            continue
        super_row = lookup.get((int(stage), int(sl)))
        cont_row = _find_parent_continuum_global_row(global_index_rows, ion_stage=int(stage))
        if super_row is None:
            out.append({
                "global_superlevel_source_term_id": term_id,
                "matrix_term_kind": "skipped_type99_superlevel_source",
                "matrix_role": "not_assembled_superlevel_not_in_global_index",
                "data_type": 99,
                "ion_stage": int(stage),
                "superlevel_level": int(sl),
                "n_type99_source_candidates": n99,
                "type99_records": row.get("type99_records"),
                "source_proxy_value": 0.0,
                "signed_rate_proxy": 0.0,
                "assembly_status": "skipped",
                "skip_reason": "superlevel_row_not_found_in_global_index",
                "provenance": "v0.3.38_global_type99_superlevel_source_scaffold",
            })
            term_id += 1
            continue
        coeff = maybe_float(row.get("type99_coeff_abs_sum_preview"))
        if coeff is not None and math.isfinite(float(coeff)) and float(coeff) > 0.0:
            proxy = float(coeff)
            proxy_basis = "type99_coeff_abs_sum_preview"
        else:
            proxy = float(n99)
            proxy_basis = "type99_candidate_count_proxy"
        parent_stage = int(stage) + 1
        common = {
            "data_type": 99,
            "rate_type": "type99_superlevel_photoionization_recombination_linked_record",
            "ion_stage": int(stage),
            "parent_ion_stage": parent_stage,
            "superlevel_level": int(sl),
            "superlevel_global_index": maybe_int(super_row.get("global_index")),
            "superlevel_level_label": super_row.get("level_label"),
            "superlevel_level_kind": super_row.get("level_kind"),
            "n_type99_source_candidates": n99,
            "type99_records": row.get("type99_records"),
            "type99_coeff_abs_sum_preview": row.get("type99_coeff_abs_sum_preview"),
            "source_proxy_basis": proxy_basis,
            "source_proxy_value": proxy,
            "has_type71_branching": row.get("has_type71_branching"),
            "type71_B_f": row.get("type71_B_f"),
            "type71_B_i": row.get("type71_B_i"),
            "type71_B_r": row.get("type71_B_r"),
            "type71_B_triplet_total": row.get("type71_B_triplet_total"),
            "source_has_branch_to_forbidden": row.get("source_has_branch_to_forbidden"),
            "source_has_branch_to_intercombination": row.get("source_has_branch_to_intercombination"),
            "source_has_branch_to_resonance": row.get("source_has_branch_to_resonance"),
            "source_weighted_type71_feed_proxy_f": row.get("source_weighted_type71_feed_proxy_f"),
            "source_weighted_type71_feed_proxy_i": row.get("source_weighted_type71_feed_proxy_i"),
            "source_weighted_type71_feed_proxy_r": row.get("source_weighted_type71_feed_proxy_r"),
            "matrix_safe_to_solve": False,
            "unsafe_reason": "diagnostic_proxy_only;type99_phint53pl_rate_not_evaluated;parent_continuum_population_not_physically_normalized",
            "provenance": "v0.3.38_global_type99_superlevel_source_scaffold",
        }
        out.append({
            "global_superlevel_source_term_id": term_id,
            "matrix_term_kind": "source_vector_gain_proxy",
            "matrix_role": "b[superlevel_global_index] += type99_source_proxy",
            "matrix_row_global_index": maybe_int(super_row.get("global_index")),
            "matrix_col_global_index": "",
            "signed_rate_proxy": proxy,
            "rate_proxy": proxy,
            "assembly_status": "assembled_global_type99_superlevel_source_scaffold_proxy",
            "skip_reason": "",
            **common,
        })
        term_id += 1
        if cont_row is None:
            out.append({
                "global_superlevel_source_term_id": term_id,
                "matrix_term_kind": "skipped_parent_continuum_to_superlevel_proxy",
                "matrix_role": "not_assembled_parent_continuum_row_missing",
                "matrix_row_global_index": maybe_int(super_row.get("global_index")),
                "matrix_col_global_index": "",
                "signed_rate_proxy": 0.0,
                "rate_proxy": proxy,
                "assembly_status": "skipped",
                "skip_reason": "parent_continuum_row_not_found_for_ion_stage",
                **common,
            })
            term_id += 1
            continue
        parent_g = maybe_int(cont_row.get("global_index"))
        out.append({
            "global_superlevel_source_term_id": term_id,
            "matrix_term_kind": "offdiag_parent_continuum_to_superlevel_proxy",
            "matrix_role": "M[superlevel_global_index,parent_continuum_global_index] += type99_source_proxy",
            "matrix_row_global_index": maybe_int(super_row.get("global_index")),
            "matrix_col_global_index": parent_g,
            "parent_continuum_global_index": parent_g,
            "parent_continuum_level_index": cont_row.get("level_index"),
            "parent_continuum_level_label": cont_row.get("level_label"),
            "signed_rate_proxy": proxy,
            "rate_proxy": proxy,
            "assembly_status": "assembled_global_type99_superlevel_source_scaffold_proxy",
            "skip_reason": "",
            **common,
        })
        term_id += 1
        out.append({
            "global_superlevel_source_term_id": term_id,
            "matrix_term_kind": "diagonal_parent_continuum_loss_proxy",
            "matrix_role": "M[parent_continuum_global_index,parent_continuum_global_index] -= type99_source_proxy",
            "matrix_row_global_index": parent_g,
            "matrix_col_global_index": parent_g,
            "parent_continuum_global_index": parent_g,
            "parent_continuum_level_index": cont_row.get("level_index"),
            "parent_continuum_level_label": cont_row.get("level_label"),
            "signed_rate_proxy": -proxy,
            "rate_proxy": proxy,
            "assembly_status": "assembled_global_type99_superlevel_source_scaffold_proxy",
            "skip_reason": "",
            **common,
        })
        term_id += 1
    return out


def _global_superlevel_source_matrix_terms_summary(rows: Sequence[dict]) -> dict:
    assembled = [r for r in rows if str(r.get("assembly_status")) == "assembled_global_type99_superlevel_source_scaffold_proxy"]
    skipped = [r for r in rows if str(r.get("assembly_status")) == "skipped"]
    gain = [r for r in assembled if str(r.get("matrix_term_kind")) == "source_vector_gain_proxy"]
    return {
        "n_global_superlevel_source_matrix_term_rows": len(rows),
        "n_global_superlevel_source_assembled_proxy_rows": len(assembled),
        "n_global_superlevel_source_skipped_rows": len(skipped),
        "rows_by_matrix_term_kind": _counts(rows, "matrix_term_kind"),
        "rows_by_ion_stage": _counts(assembled, "ion_stage"),
        "n_unique_type99_record_groups": len({str(r.get("type99_records")) for r in gain if r.get("type99_records") not in (None, "")}),
        "n_source_vector_gain_proxy_rows": len(gain),
        "total_type99_source_proxy_value": sum(float(maybe_float(r.get("source_proxy_value")) or 0.0) for r in gain),
        "source_proxy_basis_counts": _counts(gain, "source_proxy_basis"),
        "n_source_rows_with_type71_branching": sum(1 for r in gain if str(r.get("has_type71_branching")).strip().lower() in {"true", "1", "yes"}),
        "provenance": {
            "mode": "v0.3.38 maps type-99 superlevel source candidates onto explicit global_index rows.",
            "assembly": "Diagnostic scaffold only: writes source-vector and parent-continuum matrix proxy terms but does not include them in a solved matrix.",
            "excluded": "Type-99 phint53pl physical rates, radiation-field integrals, and full parent-continuum population balance are not evaluated yet.",
        },
    }

def _triplet_l2_distance(model: dict, target: Optional[dict]) -> Optional[float]:
    if not target:
        return None
    try:
        diffs = [
            float(model.get(f"{c}_fraction") or 0.0) - float(target.get(c) or target.get(f"{c}_fraction") or 0.0)
            for c in ("f", "i", "r")
        ]
        return float(math.sqrt(sum(d * d for d in diffs)))
    except Exception:
        return None


def _make_line_rows_with_population(line_rows: Sequence[dict], pop_by_level: Dict[int, float], solve_info: dict) -> List[dict]:
    """Copy line rows and replace emissivities using a supplied level population map."""
    out: List[dict] = []
    for row in line_rows:
        upper = maybe_int(row.get("upper_level"))
        A = maybe_float(row.get("A_s^-1"))
        eerg = line_energy_erg(row)
        pop = float(pop_by_level.get(int(upper), 0.0)) if upper is not None else 0.0
        photon = pop * float(A) if A is not None and A > 0 else 0.0
        energy = photon * float(eerg) if eerg is not None and eerg > 0 else 0.0
        new = dict(row)
        new["upper_population_fraction"] = pop
        new["line_photon_emissivity_per_ion_s^-1"] = photon
        new["line_energy_emissivity_per_ion_erg_s^-1"] = energy
        ne = maybe_float(row.get("electron_density_cm^-3"))
        new["line_energy_emissivity_coeff_per_ne_nion_erg_cm3_s"] = energy / ne if ne and ne > 0 else None
        new["matrix_size"] = solve_info.get("matrix_size")
        new["matrix_rank"] = solve_info.get("matrix_rank")
        new["condition_number"] = solve_info.get("condition_number")
        new["solver"] = solve_info.get("solver")
        new["solver_warning"] = solve_info.get("solver_warning")
        out.append(new)
    return out


def _assemble_source_vector_from_coupling_rows(
    *,
    level_indices: Sequence[int],
    coupling_rows: Sequence[dict],
    ion_stage: int,
) -> tuple[np.ndarray, List[dict]]:
    """Rebuild the old single-ion adjacent source vector from assembled audit rows."""
    idx = {int(lev): k for k, lev in enumerate(level_indices)}
    source = np.zeros(len(level_indices), dtype=float)
    rows: List[dict] = []
    for r in coupling_rows:
        if not bool(r.get("assembled")):
            continue
        target_stage = maybe_int(r.get("target_ion_stage"))
        dest = maybe_int(r.get("destination_level"))
        rate = maybe_float(r.get("source_rate_total_s^-1"))
        if target_stage != int(ion_stage) or dest is None or rate is None or not math.isfinite(float(rate)):
            continue
        applied = int(dest) in idx and float(rate) != 0.0
        if applied:
            source[idx[int(dest)]] += float(rate)
        rows.append({
            "source_record": r.get("record"),
            "source_data_type": r.get("data_type"),
            "source_rate_type": r.get("rate_type"),
            "destination_level": int(dest),
            "source_rate_s^-1": float(rate),
            "applied_to_global_bound_bound_block": bool(applied),
            "source_reconstruction_note": "rebuilt_from_assembled_adjacent_coupling_terms",
        })
    return source, rows


def build_global_bound_bound_solve_comparison(
    *,
    global_index_rows: Sequence[dict],
    global_bound_bound_matrix_terms: Sequence[dict],
    populations: Sequence[dict],
    line_rows: Sequence[dict],
    coupling_rows: Sequence[dict],
    ion_stage: int,
    linear_solver: str = "svd",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
) -> List[dict]:
    """Solve a diagnostic global-index bound-bound-only block for one ion.

    This v0.3.34 helper is an equivalence test.  It assembles the requested
    ion's block from the v0.3.33 global matrix-term rows, rebuilds the same
    adjacent source vector used by the old per-ion solve, solves the block, and
    compares populations and He-like triplet fractions against the existing
    per-ion outputs.
    """
    ion_stage = int(ion_stage)
    try:
        type99_proxy_scale = float(type99_proxy_scale)
    except Exception:
        type99_proxy_scale = 1.0
    if not math.isfinite(type99_proxy_scale):
        type99_proxy_scale = 1.0
    ion_global_rows = [
        r for r in global_index_rows
        if maybe_int(r.get("ion_stage")) == ion_stage and not bool(r.get("is_continuum"))
    ]
    global_to_level: Dict[int, int] = {}
    for r in ion_global_rows:
        g = maybe_int(r.get("global_index"))
        lev = maybe_int(r.get("level_index"))
        if g is not None and lev is not None:
            global_to_level[int(g)] = int(lev)

    used_globals: set[int] = set()
    for t in global_bound_bound_matrix_terms:
        if str(t.get("assembly_status")) != "assembled_global_bound_bound_scaffold":
            continue
        if maybe_int(t.get("ion_stage")) != ion_stage:
            continue
        row = maybe_int(t.get("matrix_row_global_index"))
        col = maybe_int(t.get("matrix_col_global_index"))
        if row in global_to_level and col in global_to_level:
            used_globals.add(int(row))
            used_globals.add(int(col))

    for r in coupling_rows:
        if bool(r.get("assembled")) and maybe_int(r.get("target_ion_stage")) == ion_stage:
            dest = maybe_int(r.get("destination_level"))
            if dest is not None:
                for g, lev in global_to_level.items():
                    if lev == int(dest):
                        used_globals.add(g)
    for r in line_rows:
        if maybe_int(r.get("ion_stage")) == ion_stage:
            for key in ("lower_level", "upper_level"):
                lev = maybe_int(r.get(key))
                if lev is not None:
                    for g, glev in global_to_level.items():
                        if glev == int(lev):
                            used_globals.add(g)

    selected_globals = sorted(used_globals)
    level_indices = [global_to_level[g] for g in selected_globals]
    g_to_local = {g: k for k, g in enumerate(selected_globals)}
    n = len(selected_globals)
    R = np.zeros((n, n), dtype=float)
    n_offdiag = 0
    n_diag = 0
    diag_from_terms = np.zeros(n, dtype=float)
    for t in global_bound_bound_matrix_terms:
        if str(t.get("assembly_status")) != "assembled_global_bound_bound_scaffold":
            continue
        if maybe_int(t.get("ion_stage")) != ion_stage:
            continue
        row = maybe_int(t.get("matrix_row_global_index"))
        col = maybe_int(t.get("matrix_col_global_index"))
        rate = maybe_float(t.get("signed_rate_s^-1"))
        if row is None or col is None or rate is None or row not in g_to_local or col not in g_to_local:
            continue
        if str(t.get("matrix_term_kind")) == "offdiag_gain" and row != col and float(rate) > 0.0:
            R[g_to_local[int(row)], g_to_local[int(col)]] += float(rate)
            n_offdiag += 1
        elif str(t.get("matrix_term_kind")) == "diagonal_loss" and row == col:
            diag_from_terms[g_to_local[int(row)]] += float(rate)
            n_diag += 1

    expected_diag = -np.sum(R, axis=0)
    diag_linf = float(np.max(np.abs(diag_from_terms - expected_diag))) if n else 0.0
    source_vector, source_rows = _assemble_source_vector_from_coupling_rows(
        level_indices=level_indices,
        coupling_rows=coupling_rows,
        ion_stage=ion_stage,
    )
    if n == 0:
        pop = np.array([], dtype=float)
        solve_info = {"matrix_size": 0, "solution_status": "empty", "solver_warning": "empty global bound-bound block"}
    else:
        pop, solve_info = solve_steady_state(
            R,
            source_vector=source_vector if np.count_nonzero(source_vector) else None,
            sink_rates=None,
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
        )
        solve_info["solution_status"] = "ok" if not solve_info.get("solver_warning") else "warning"

    global_pop_by_level = {int(lev): float(pop[k]) for k, lev in enumerate(level_indices)}
    old_pop_by_level: Dict[int, float] = {}
    for r in populations:
        if maybe_int(r.get("ion_stage")) == ion_stage:
            lev = maybe_int(r.get("level_index"))
            val = maybe_float(r.get("population_fraction"))
            if lev is not None and val is not None:
                old_pop_by_level[int(lev)] = float(val)

    selected_line_rows = [r for r in line_rows if maybe_int(r.get("ion_stage")) == ion_stage]
    global_line_rows = _make_line_rows_with_population(selected_line_rows, global_pop_by_level, solve_info)
    old_triplet = _normalise_triplet(selected_line_rows)
    global_triplet = _normalise_triplet(global_line_rows)
    target = _xstar_triplet_target(ion_stage)
    old_l2 = _triplet_l2_distance(old_triplet, target)
    global_l2 = _triplet_l2_distance(global_triplet, target)

    rows: List[dict] = []
    rows.append({
        "row_kind": "summary",
        "comparison_case": "per_ion_baseline",
        "ion_stage": ion_stage,
        "n_levels": len(old_pop_by_level),
        "n_global_indices": n,
        "n_offdiag_gain_terms": n_offdiag,
        "n_diagonal_loss_terms": n_diag,
        "diag_loss_linf_mismatch_s^-1": diag_linf,
        "source_sum_s^-1": float(np.sum(source_vector)) if len(source_vector) else 0.0,
        "n_source_terms_nonzero": int(np.count_nonzero(source_vector)) if len(source_vector) else 0,
        "f_fraction": old_triplet.get("f_fraction"),
        "i_fraction": old_triplet.get("i_fraction"),
        "r_fraction": old_triplet.get("r_fraction"),
        "R": old_triplet.get("R"),
        "G": old_triplet.get("G"),
        "l2_distance_to_target": old_l2,
        "solve_status": "baseline_existing_per_ion_solve",
        "solver": "existing_per_ion_solver",
        "provenance": "v0.3.34_global_bound_bound_only_solve_comparison",
    })
    rows.append({
        "row_kind": "summary",
        "comparison_case": "global_bound_bound_block",
        "ion_stage": ion_stage,
        "n_levels": n,
        "n_global_indices": n,
        "n_offdiag_gain_terms": n_offdiag,
        "n_diagonal_loss_terms": n_diag,
        "diag_loss_linf_mismatch_s^-1": diag_linf,
        "source_sum_s^-1": float(np.sum(source_vector)) if len(source_vector) else 0.0,
        "n_source_terms_nonzero": int(np.count_nonzero(source_vector)) if len(source_vector) else 0,
        "f_fraction": global_triplet.get("f_fraction"),
        "i_fraction": global_triplet.get("i_fraction"),
        "r_fraction": global_triplet.get("r_fraction"),
        "R": global_triplet.get("R"),
        "G": global_triplet.get("G"),
        "l2_distance_to_target": global_l2,
        "delta_f_global_minus_baseline": float(global_triplet.get("f_fraction") or 0.0) - float(old_triplet.get("f_fraction") or 0.0),
        "delta_i_global_minus_baseline": float(global_triplet.get("i_fraction") or 0.0) - float(old_triplet.get("i_fraction") or 0.0),
        "delta_r_global_minus_baseline": float(global_triplet.get("r_fraction") or 0.0) - float(old_triplet.get("r_fraction") or 0.0),
        "solve_status": solve_info.get("solution_status"),
        "solver": solve_info.get("solver"),
        "solver_warning": solve_info.get("solver_warning"),
        "matrix_rank": solve_info.get("matrix_rank"),
        "condition_number": solve_info.get("condition_number"),
        "provenance": "v0.3.34_global_bound_bound_only_solve_comparison",
    })
    for lev in sorted(set(old_pop_by_level) | set(global_pop_by_level)):
        old = old_pop_by_level.get(int(lev), 0.0)
        new = global_pop_by_level.get(int(lev), 0.0)
        rows.append({
            "row_kind": "population",
            "comparison_case": "population_by_level",
            "ion_stage": ion_stage,
            "level_index": int(lev),
            "old_population_fraction": old,
            "global_population_fraction": new,
            "delta_global_minus_old": new - old,
            "abs_delta_global_minus_old": abs(new - old),
            "provenance": "v0.3.34_global_bound_bound_only_solve_comparison",
        })
    for sr in source_rows:
        row = {"row_kind": "source", "comparison_case": "rebuilt_source_vector", "ion_stage": ion_stage}
        row.update(sr)
        row["provenance"] = "v0.3.34_global_bound_bound_only_solve_comparison"
        rows.append(row)
    return rows


def _global_bound_bound_solve_comparison_summary(rows: Sequence[dict]) -> dict:
    summaries = [r for r in rows if str(r.get("row_kind")) == "summary"]
    pops = [r for r in rows if str(r.get("row_kind")) == "population"]
    global_case = next((r for r in summaries if str(r.get("comparison_case")) == "global_bound_bound_block"), {})
    base_case = next((r for r in summaries if str(r.get("comparison_case")) == "per_ion_baseline"), {})
    max_abs_delta = None
    if pops:
        vals = [maybe_float(r.get("abs_delta_global_minus_old")) for r in pops]
        vals = [float(v) for v in vals if v is not None]
        max_abs_delta = max(vals) if vals else None
    return {
        "n_global_bound_bound_solve_comparison_rows": len(rows),
        "n_population_comparison_rows": len(pops),
        "baseline_f_fraction": base_case.get("f_fraction"),
        "global_f_fraction": global_case.get("f_fraction"),
        "baseline_i_fraction": base_case.get("i_fraction"),
        "global_i_fraction": global_case.get("i_fraction"),
        "baseline_r_fraction": base_case.get("r_fraction"),
        "global_r_fraction": global_case.get("r_fraction"),
        "global_solve_status": global_case.get("solve_status"),
        "global_solver_warning": global_case.get("solver_warning"),
        "max_abs_population_delta": max_abs_delta,
        "diag_loss_linf_mismatch_s^-1": global_case.get("diag_loss_linf_mismatch_s^-1"),
        "source_sum_s^-1": global_case.get("source_sum_s^-1"),
        "provenance": {
            "mode": "v0.3.34 solves a diagnostic global-index bound-bound-only block for the He-like ion.",
            "assembly": "This is an intra-ion equivalence test using current bound-bound terms and the old adjacent source vector; it is not yet the full element-wide coupled solve.",
        },
    }


def build_global_bound_bound_type71_solve_comparison(
    *,
    global_index_rows: Sequence[dict],
    global_bound_bound_matrix_terms: Sequence[dict],
    global_superlevel_cascade_matrix_terms: Sequence[dict],
    populations: Sequence[dict],
    line_rows: Sequence[dict],
    coupling_rows: Sequence[dict],
    ion_stage: int,
    linear_solver: str = "svd",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
) -> List[dict]:
    """Solve an extended He-like global block with bound-bound + type-71 terms.

    This v0.3.36 helper is a structural diagnostic.  It assembles the same
    C V (or other He-like target) global-index bound-bound block verified in
    v0.3.34, adds the v0.3.35 type-71 superlevel -> spectroscopic cascade
    matrix terms, rebuilds the same adjacent source vector used by the current
    per-ion solve, and compares the resulting populations/triplet diagnostics
    against both the old per-ion baseline and the bound-bound-only global block.

    No type-70/type-74/type-99 superlevel source terms are included here, so
    superlevel populations are expected to remain un-driven unless they are
    populated by other assembled source terms in later versions.
    """
    ion_stage = int(ion_stage)
    ion_global_rows = [
        r for r in global_index_rows
        if maybe_int(r.get("ion_stage")) == ion_stage and not bool(r.get("is_continuum"))
    ]
    global_to_level: Dict[int, int] = {}
    global_to_row: Dict[int, dict] = {}
    for r in ion_global_rows:
        g = maybe_int(r.get("global_index"))
        lev = maybe_int(r.get("level_index"))
        if g is not None and lev is not None:
            global_to_level[int(g)] = int(lev)
            global_to_row[int(g)] = r

    used_globals: set[int] = set()
    for terms, status in (
        (global_bound_bound_matrix_terms, "assembled_global_bound_bound_scaffold"),
        (global_superlevel_cascade_matrix_terms, "assembled_global_type71_superlevel_cascade_scaffold"),
    ):
        for t in terms:
            if str(t.get("assembly_status")) != status:
                continue
            if maybe_int(t.get("ion_stage")) != ion_stage:
                continue
            row = maybe_int(t.get("matrix_row_global_index"))
            col = maybe_int(t.get("matrix_col_global_index"))
            if row in global_to_level and col in global_to_level:
                used_globals.add(int(row))
                used_globals.add(int(col))

    for r in coupling_rows:
        if bool(r.get("assembled")) and maybe_int(r.get("target_ion_stage")) == ion_stage:
            dest = maybe_int(r.get("destination_level"))
            if dest is not None:
                for g, lev in global_to_level.items():
                    if lev == int(dest):
                        used_globals.add(g)
    for r in line_rows:
        if maybe_int(r.get("ion_stage")) == ion_stage:
            for key in ("lower_level", "upper_level"):
                lev = maybe_int(r.get(key))
                if lev is not None:
                    for g, glev in global_to_level.items():
                        if glev == int(lev):
                            used_globals.add(g)

    selected_globals = sorted(used_globals)
    level_indices = [global_to_level[g] for g in selected_globals]
    g_to_local = {g: k for k, g in enumerate(selected_globals)}
    n = len(selected_globals)
    R = np.zeros((n, n), dtype=float)
    n_bb_offdiag = 0
    n_bb_diag = 0
    n_t71_offdiag = 0
    n_t71_diag = 0
    diag_from_terms = np.zeros(n, dtype=float)

    def add_terms(terms: Sequence[dict], status: str, source_label: str) -> None:
        nonlocal n_bb_offdiag, n_bb_diag, n_t71_offdiag, n_t71_diag
        for t in terms:
            if str(t.get("assembly_status")) != status:
                continue
            if maybe_int(t.get("ion_stage")) != ion_stage:
                continue
            row = maybe_int(t.get("matrix_row_global_index"))
            col = maybe_int(t.get("matrix_col_global_index"))
            rate = maybe_float(t.get("signed_rate_s^-1"))
            if row is None or col is None or rate is None or row not in g_to_local or col not in g_to_local:
                continue
            kind = str(t.get("matrix_term_kind"))
            if kind == "offdiag_gain" and row != col and float(rate) > 0.0:
                R[g_to_local[int(row)], g_to_local[int(col)]] += float(rate)
                if source_label == "bound_bound":
                    n_bb_offdiag += 1
                else:
                    n_t71_offdiag += 1
            elif kind == "diagonal_loss" and row == col:
                diag_from_terms[g_to_local[int(row)]] += float(rate)
                if source_label == "bound_bound":
                    n_bb_diag += 1
                else:
                    n_t71_diag += 1

    add_terms(global_bound_bound_matrix_terms, "assembled_global_bound_bound_scaffold", "bound_bound")
    add_terms(global_superlevel_cascade_matrix_terms, "assembled_global_type71_superlevel_cascade_scaffold", "type71")

    expected_diag = -np.sum(R, axis=0)
    diag_linf = float(np.max(np.abs(diag_from_terms - expected_diag))) if n else 0.0
    source_vector, source_rows = _assemble_source_vector_from_coupling_rows(
        level_indices=level_indices,
        coupling_rows=coupling_rows,
        ion_stage=ion_stage,
    )
    if n == 0:
        pop = np.array([], dtype=float)
        solve_info = {"matrix_size": 0, "solution_status": "empty", "solver_warning": "empty global bound-bound+type71 block"}
    else:
        pop, solve_info = solve_steady_state(
            R,
            source_vector=source_vector if np.count_nonzero(source_vector) else None,
            sink_rates=None,
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
        )
        solve_info["solution_status"] = "ok" if not solve_info.get("solver_warning") else "warning"

    global_pop_by_level = {int(lev): float(pop[k]) for k, lev in enumerate(level_indices)}
    old_pop_by_level: Dict[int, float] = {}
    for r in populations:
        if maybe_int(r.get("ion_stage")) == ion_stage:
            lev = maybe_int(r.get("level_index"))
            val = maybe_float(r.get("population_fraction"))
            if lev is not None and val is not None:
                old_pop_by_level[int(lev)] = float(val)

    selected_line_rows = [r for r in line_rows if maybe_int(r.get("ion_stage")) == ion_stage]
    global_line_rows = _make_line_rows_with_population(selected_line_rows, global_pop_by_level, solve_info)
    old_triplet = _normalise_triplet(selected_line_rows)
    global_triplet = _normalise_triplet(global_line_rows)
    target = _xstar_triplet_target(ion_stage)
    old_l2 = _triplet_l2_distance(old_triplet, target)
    global_l2 = _triplet_l2_distance(global_triplet, target)

    n_superlevels = sum(1 for g in selected_globals if str(global_to_row.get(g, {}).get("level_kind")) == "superlevel")
    superlevel_population_sum = sum(
        float(pop[k]) for k, g in enumerate(selected_globals)
        if str(global_to_row.get(g, {}).get("level_kind")) == "superlevel"
    ) if len(pop) else 0.0

    rows: List[dict] = []
    rows.append({
        "row_kind": "summary",
        "comparison_case": "per_ion_baseline",
        "ion_stage": ion_stage,
        "n_levels": len(old_pop_by_level),
        "n_global_indices": n,
        "n_superlevel_indices": n_superlevels,
        "n_bound_bound_offdiag_gain_terms": n_bb_offdiag,
        "n_bound_bound_diagonal_loss_terms": n_bb_diag,
        "n_type71_offdiag_gain_terms": n_t71_offdiag,
        "n_type71_diagonal_loss_terms": n_t71_diag,
        "diag_loss_linf_mismatch_s^-1": diag_linf,
        "source_sum_s^-1": float(np.sum(source_vector)) if len(source_vector) else 0.0,
        "n_source_terms_nonzero": int(np.count_nonzero(source_vector)) if len(source_vector) else 0,
        "superlevel_population_sum": None,
        "f_fraction": old_triplet.get("f_fraction"),
        "i_fraction": old_triplet.get("i_fraction"),
        "r_fraction": old_triplet.get("r_fraction"),
        "R": old_triplet.get("R"),
        "G": old_triplet.get("G"),
        "l2_distance_to_target": old_l2,
        "solve_status": "baseline_existing_per_ion_solve",
        "solver": "existing_per_ion_solver",
        "provenance": "v0.3.36_global_bound_bound_plus_type71_solve_comparison",
    })
    rows.append({
        "row_kind": "summary",
        "comparison_case": "global_bound_bound_plus_type71_block",
        "ion_stage": ion_stage,
        "n_levels": n,
        "n_global_indices": n,
        "n_superlevel_indices": n_superlevels,
        "n_bound_bound_offdiag_gain_terms": n_bb_offdiag,
        "n_bound_bound_diagonal_loss_terms": n_bb_diag,
        "n_type71_offdiag_gain_terms": n_t71_offdiag,
        "n_type71_diagonal_loss_terms": n_t71_diag,
        "diag_loss_linf_mismatch_s^-1": diag_linf,
        "source_sum_s^-1": float(np.sum(source_vector)) if len(source_vector) else 0.0,
        "n_source_terms_nonzero": int(np.count_nonzero(source_vector)) if len(source_vector) else 0,
        "superlevel_population_sum": superlevel_population_sum,
        "f_fraction": global_triplet.get("f_fraction"),
        "i_fraction": global_triplet.get("i_fraction"),
        "r_fraction": global_triplet.get("r_fraction"),
        "R": global_triplet.get("R"),
        "G": global_triplet.get("G"),
        "l2_distance_to_target": global_l2,
        "delta_f_global_minus_baseline": float(global_triplet.get("f_fraction") or 0.0) - float(old_triplet.get("f_fraction") or 0.0),
        "delta_i_global_minus_baseline": float(global_triplet.get("i_fraction") or 0.0) - float(old_triplet.get("i_fraction") or 0.0),
        "delta_r_global_minus_baseline": float(global_triplet.get("r_fraction") or 0.0) - float(old_triplet.get("r_fraction") or 0.0),
        "solve_status": solve_info.get("solution_status"),
        "solver": solve_info.get("solver"),
        "solver_warning": solve_info.get("solver_warning"),
        "matrix_rank": solve_info.get("matrix_rank"),
        "condition_number": solve_info.get("condition_number"),
        "provenance": "v0.3.36_global_bound_bound_plus_type71_solve_comparison",
    })
    for k, g in enumerate(selected_globals):
        lev = global_to_level[g]
        old = old_pop_by_level.get(int(lev), 0.0)
        new = global_pop_by_level.get(int(lev), 0.0)
        grow = global_to_row.get(g, {})
        rows.append({
            "row_kind": "population",
            "comparison_case": "population_by_global_index",
            "ion_stage": ion_stage,
            "global_index": int(g),
            "level_index": int(lev),
            "level_label": grow.get("level_label"),
            "level_kind": grow.get("level_kind"),
            "is_superlevel": bool(grow.get("is_superlevel")),
            "old_population_fraction": old,
            "global_population_fraction": new,
            "delta_global_minus_old": new - old,
            "abs_delta_global_minus_old": abs(new - old),
            "provenance": "v0.3.36_global_bound_bound_plus_type71_solve_comparison",
        })
    for sr in source_rows:
        row = {"row_kind": "source", "comparison_case": "rebuilt_source_vector", "ion_stage": ion_stage}
        row.update(sr)
        row["provenance"] = "v0.3.36_global_bound_bound_plus_type71_solve_comparison"
        rows.append(row)
    return rows


def _global_bound_bound_type71_solve_comparison_summary(rows: Sequence[dict]) -> dict:
    summaries = [r for r in rows if str(r.get("row_kind")) == "summary"]
    pops = [r for r in rows if str(r.get("row_kind")) == "population"]
    global_case = next((r for r in summaries if str(r.get("comparison_case")) == "global_bound_bound_plus_type71_block"), {})
    base_case = next((r for r in summaries if str(r.get("comparison_case")) == "per_ion_baseline"), {})
    vals = [maybe_float(r.get("abs_delta_global_minus_old")) for r in pops]
    vals = [float(v) for v in vals if v is not None]
    super_vals = [maybe_float(r.get("global_population_fraction")) for r in pops if bool(r.get("is_superlevel"))]
    super_vals = [float(v) for v in super_vals if v is not None]
    return {
        "n_global_bound_bound_type71_solve_comparison_rows": len(rows),
        "n_population_comparison_rows": len(pops),
        "baseline_f_fraction": base_case.get("f_fraction"),
        "global_type71_f_fraction": global_case.get("f_fraction"),
        "baseline_i_fraction": base_case.get("i_fraction"),
        "global_type71_i_fraction": global_case.get("i_fraction"),
        "baseline_r_fraction": base_case.get("r_fraction"),
        "global_type71_r_fraction": global_case.get("r_fraction"),
        "global_type71_solve_status": global_case.get("solve_status"),
        "global_type71_solver_warning": global_case.get("solver_warning"),
        "n_type71_offdiag_gain_terms": global_case.get("n_type71_offdiag_gain_terms"),
        "n_type71_diagonal_loss_terms": global_case.get("n_type71_diagonal_loss_terms"),
        "superlevel_population_sum": global_case.get("superlevel_population_sum"),
        "max_superlevel_population": max(super_vals) if super_vals else None,
        "max_abs_population_delta": max(vals) if vals else None,
        "diag_loss_linf_mismatch_s^-1": global_case.get("diag_loss_linf_mismatch_s^-1"),
        "source_sum_s^-1": global_case.get("source_sum_s^-1"),
        "provenance": {
            "mode": "v0.3.36 solves a diagnostic global-index block with bound-bound plus type-71 superlevel cascade terms for the He-like ion.",
            "assembly": "This is still an intra-ion scaffold test; type-70/type-74/type-99 superlevel sources and full adjacent-ion balance are not included.",
        },
    }


def build_global_bound_bound_type71_type99_proxy_solve_comparison(
    *,
    global_index_rows: Sequence[dict],
    global_bound_bound_matrix_terms: Sequence[dict],
    global_superlevel_cascade_matrix_terms: Sequence[dict],
    global_superlevel_source_matrix_terms: Sequence[dict],
    populations: Sequence[dict],
    line_rows: Sequence[dict],
    coupling_rows: Sequence[dict],
    ion_stage: int,
    linear_solver: str = "svd",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    type99_proxy_scale: float = 1.0,
) -> List[dict]:
    """Solve a diagnostic He-like global block with type-99 proxy sources.

    v0.3.39 is deliberately nonphysical.  It takes the structural global block
    used by the v0.3.36 bound-bound+type71 comparison and adds the v0.3.38
    type-99 ``source_vector_gain_proxy`` rows to the source vector.  The proxy
    values are not XSTAR ``phint53pl`` rates; they are only topology/source-scale
    placeholders used to test how feeding mapped superlevels redirects the
    type-71 cascade solution.  v0.3.40 adds ``type99_proxy_scale`` so the
    proxy source normalization can be scanned without treating it as physical.
    """
    ion_stage = int(ion_stage)
    ion_global_rows = [
        r for r in global_index_rows
        if maybe_int(r.get("ion_stage")) == ion_stage and not bool(r.get("is_continuum"))
    ]
    global_to_level: Dict[int, int] = {}
    global_to_row: Dict[int, dict] = {}
    for r in ion_global_rows:
        g = maybe_int(r.get("global_index"))
        lev = maybe_int(r.get("level_index"))
        if g is not None and lev is not None:
            global_to_level[int(g)] = int(lev)
            global_to_row[int(g)] = r

    used_globals: set[int] = set()
    for terms, status in (
        (global_bound_bound_matrix_terms, "assembled_global_bound_bound_scaffold"),
        (global_superlevel_cascade_matrix_terms, "assembled_global_type71_superlevel_cascade_scaffold"),
    ):
        for t in terms:
            if str(t.get("assembly_status")) != status:
                continue
            if maybe_int(t.get("ion_stage")) != ion_stage:
                continue
            row = maybe_int(t.get("matrix_row_global_index"))
            col = maybe_int(t.get("matrix_col_global_index"))
            if row in global_to_level and col in global_to_level:
                used_globals.add(int(row))
                used_globals.add(int(col))

    for t in global_superlevel_source_matrix_terms:
        if str(t.get("assembly_status")) != "assembled_global_type99_superlevel_source_scaffold_proxy":
            continue
        if str(t.get("matrix_term_kind")) != "source_vector_gain_proxy":
            continue
        if maybe_int(t.get("ion_stage")) != ion_stage:
            continue
        row = maybe_int(t.get("matrix_row_global_index"))
        if row in global_to_level:
            used_globals.add(int(row))

    for r in coupling_rows:
        if bool(r.get("assembled")) and maybe_int(r.get("target_ion_stage")) == ion_stage:
            dest = maybe_int(r.get("destination_level"))
            if dest is not None:
                for g, lev in global_to_level.items():
                    if lev == int(dest):
                        used_globals.add(g)
    for r in line_rows:
        if maybe_int(r.get("ion_stage")) == ion_stage:
            for key in ("lower_level", "upper_level"):
                lev = maybe_int(r.get(key))
                if lev is not None:
                    for g, glev in global_to_level.items():
                        if glev == int(lev):
                            used_globals.add(g)

    selected_globals = sorted(used_globals)
    level_indices = [global_to_level[g] for g in selected_globals]
    g_to_local = {g: k for k, g in enumerate(selected_globals)}
    n = len(selected_globals)
    R = np.zeros((n, n), dtype=float)
    n_bb_offdiag = n_bb_diag = n_t71_offdiag = n_t71_diag = 0
    diag_from_terms = np.zeros(n, dtype=float)

    def add_terms(terms: Sequence[dict], status: str, source_label: str) -> None:
        nonlocal n_bb_offdiag, n_bb_diag, n_t71_offdiag, n_t71_diag
        for t in terms:
            if str(t.get("assembly_status")) != status:
                continue
            if maybe_int(t.get("ion_stage")) != ion_stage:
                continue
            row = maybe_int(t.get("matrix_row_global_index"))
            col = maybe_int(t.get("matrix_col_global_index"))
            rate = maybe_float(t.get("signed_rate_s^-1"))
            if row is None or col is None or rate is None or row not in g_to_local or col not in g_to_local:
                continue
            kind = str(t.get("matrix_term_kind"))
            if kind == "offdiag_gain" and row != col and float(rate) > 0.0:
                R[g_to_local[int(row)], g_to_local[int(col)]] += float(rate)
                if source_label == "bound_bound":
                    n_bb_offdiag += 1
                else:
                    n_t71_offdiag += 1
            elif kind == "diagonal_loss" and row == col:
                diag_from_terms[g_to_local[int(row)]] += float(rate)
                if source_label == "bound_bound":
                    n_bb_diag += 1
                else:
                    n_t71_diag += 1

    add_terms(global_bound_bound_matrix_terms, "assembled_global_bound_bound_scaffold", "bound_bound")
    add_terms(global_superlevel_cascade_matrix_terms, "assembled_global_type71_superlevel_cascade_scaffold", "type71")

    expected_diag = -np.sum(R, axis=0)
    diag_linf = float(np.max(np.abs(diag_from_terms - expected_diag))) if n else 0.0

    source_vector, source_rows = _assemble_source_vector_from_coupling_rows(
        level_indices=level_indices,
        coupling_rows=coupling_rows,
        ion_stage=ion_stage,
    )
    n_type99_proxy_source_terms = 0
    type99_proxy_source_sum = 0.0
    for t in global_superlevel_source_matrix_terms:
        if str(t.get("assembly_status")) != "assembled_global_type99_superlevel_source_scaffold_proxy":
            continue
        if str(t.get("matrix_term_kind")) != "source_vector_gain_proxy":
            continue
        if maybe_int(t.get("ion_stage")) != ion_stage:
            continue
        g = maybe_int(t.get("matrix_row_global_index"))
        proxy = maybe_float(t.get("signed_rate_proxy"))
        if g is None or proxy is None or g not in g_to_local:
            continue
        k = g_to_local[int(g)]
        scaled_proxy = float(proxy) * float(type99_proxy_scale)
        source_vector[k] += scaled_proxy
        n_type99_proxy_source_terms += 1
        type99_proxy_source_sum += scaled_proxy
        source_rows.append({
            "source_family": "type99_superlevel_proxy_source",
            "source_record": t.get("type99_records"),
            "source_data_type": 99,
            "source_rate_type": t.get("rate_type"),
            "destination_level": global_to_level.get(int(g)),
            "destination_global_index": int(g),
            "destination_level_label": global_to_row.get(int(g), {}).get("level_label"),
            "destination_level_kind": global_to_row.get(int(g), {}).get("level_kind"),
            "source_rate_s^-1": scaled_proxy,
            "unscaled_source_rate_proxy_s^-1": float(proxy),
            "type99_proxy_scale": type99_proxy_scale,
            "source_proxy_basis": t.get("source_proxy_basis"),
            "source_proxy_value": t.get("source_proxy_value"),
            "applied_to_global_bound_bound_type71_type99_proxy_block": True,
            "warning": "diagnostic_proxy_only_not_physical_type99_phint53pl_rate",
        })

    if n == 0:
        pop = np.array([], dtype=float)
        solve_info = {"matrix_size": 0, "solution_status": "empty", "solver_warning": "empty global bound-bound+type71+type99proxy block"}
    else:
        pop, solve_info = solve_steady_state(
            R,
            source_vector=source_vector if np.count_nonzero(source_vector) else None,
            sink_rates=None,
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
        )
        solve_info["solution_status"] = "ok" if not solve_info.get("solver_warning") else "warning"

    global_pop_by_level = {int(lev): float(pop[k]) for k, lev in enumerate(level_indices)}
    old_pop_by_level: Dict[int, float] = {}
    for r in populations:
        if maybe_int(r.get("ion_stage")) == ion_stage:
            lev = maybe_int(r.get("level_index"))
            val = maybe_float(r.get("population_fraction"))
            if lev is not None and val is not None:
                old_pop_by_level[int(lev)] = float(val)

    selected_line_rows = [r for r in line_rows if maybe_int(r.get("ion_stage")) == ion_stage]
    global_line_rows = _make_line_rows_with_population(selected_line_rows, global_pop_by_level, solve_info)
    old_triplet = _normalise_triplet(selected_line_rows)
    global_triplet = _normalise_triplet(global_line_rows)
    target = _xstar_triplet_target(ion_stage)
    old_l2 = _triplet_l2_distance(old_triplet, target)
    global_l2 = _triplet_l2_distance(global_triplet, target)

    n_superlevels = sum(1 for g in selected_globals if str(global_to_row.get(g, {}).get("level_kind")) == "superlevel")
    superlevel_population_sum = sum(
        float(pop[k]) for k, g in enumerate(selected_globals)
        if str(global_to_row.get(g, {}).get("level_kind")) == "superlevel"
    ) if len(pop) else 0.0

    rows: List[dict] = []
    common_summary = {
        "ion_stage": ion_stage,
        "n_global_indices": n,
        "n_superlevel_indices": n_superlevels,
        "n_bound_bound_offdiag_gain_terms": n_bb_offdiag,
        "n_bound_bound_diagonal_loss_terms": n_bb_diag,
        "n_type71_offdiag_gain_terms": n_t71_offdiag,
        "n_type71_diagonal_loss_terms": n_t71_diag,
        "n_type99_proxy_source_terms": n_type99_proxy_source_terms,
        "type99_proxy_scale": type99_proxy_scale,
        "type99_proxy_source_sum_s^-1": type99_proxy_source_sum,
        "diag_loss_linf_mismatch_s^-1": diag_linf,
    }
    rows.append({
        "row_kind": "summary",
        "comparison_case": "per_ion_baseline",
        "n_levels": len(old_pop_by_level),
        "source_sum_s^-1": float(np.sum(source_vector)) - type99_proxy_source_sum if len(source_vector) else 0.0,
        "n_source_terms_nonzero": None,
        "superlevel_population_sum": None,
        "f_fraction": old_triplet.get("f_fraction"),
        "i_fraction": old_triplet.get("i_fraction"),
        "r_fraction": old_triplet.get("r_fraction"),
        "R": old_triplet.get("R"),
        "G": old_triplet.get("G"),
        "l2_distance_to_target": old_l2,
        "solve_status": "baseline_existing_per_ion_solve",
        "solver": "existing_per_ion_solver",
        "provenance": "v0.3.39_global_bound_bound_plus_type71_plus_type99_proxy_solve_comparison",
        **common_summary,
    })
    rows.append({
        "row_kind": "summary",
        "comparison_case": "global_bound_bound_plus_type71_plus_type99_proxy_block",
        "n_levels": n,
        "source_sum_s^-1": float(np.sum(source_vector)) if len(source_vector) else 0.0,
        "n_source_terms_nonzero": int(np.count_nonzero(source_vector)) if len(source_vector) else 0,
        "superlevel_population_sum": superlevel_population_sum,
        "f_fraction": global_triplet.get("f_fraction"),
        "i_fraction": global_triplet.get("i_fraction"),
        "r_fraction": global_triplet.get("r_fraction"),
        "R": global_triplet.get("R"),
        "G": global_triplet.get("G"),
        "l2_distance_to_target": global_l2,
        "delta_f_global_minus_baseline": float(global_triplet.get("f_fraction") or 0.0) - float(old_triplet.get("f_fraction") or 0.0),
        "delta_i_global_minus_baseline": float(global_triplet.get("i_fraction") or 0.0) - float(old_triplet.get("i_fraction") or 0.0),
        "delta_r_global_minus_baseline": float(global_triplet.get("r_fraction") or 0.0) - float(old_triplet.get("r_fraction") or 0.0),
        "solve_status": solve_info.get("solution_status"),
        "solver": solve_info.get("solver"),
        "solver_warning": solve_info.get("solver_warning"),
        "matrix_rank": solve_info.get("matrix_rank"),
        "condition_number": solve_info.get("condition_number"),
        "warning": "type99_source_terms_are_proxy_values_not_physical_rates",
        "provenance": "v0.3.39_global_bound_bound_plus_type71_plus_type99_proxy_solve_comparison",
        **common_summary,
    })
    for k, g in enumerate(selected_globals):
        lev = global_to_level[g]
        old = old_pop_by_level.get(int(lev), 0.0)
        new = global_pop_by_level.get(int(lev), 0.0)
        grow = global_to_row.get(g, {})
        rows.append({
            "row_kind": "population",
            "comparison_case": "population_by_global_index",
            "ion_stage": ion_stage,
            "global_index": int(g),
            "level_index": int(lev),
            "level_label": grow.get("level_label"),
            "level_kind": grow.get("level_kind"),
            "is_superlevel": bool(grow.get("is_superlevel")),
            "old_population_fraction": old,
            "global_population_fraction": new,
            "delta_global_minus_old": new - old,
            "abs_delta_global_minus_old": abs(new - old),
            "provenance": "v0.3.39_global_bound_bound_plus_type71_plus_type99_proxy_solve_comparison",
        })
    for sr in source_rows:
        row = {"row_kind": "source", "comparison_case": "rebuilt_source_vector_plus_type99_proxy", "ion_stage": ion_stage}
        row.update(sr)
        row["provenance"] = "v0.3.39_global_bound_bound_plus_type71_plus_type99_proxy_solve_comparison"
        rows.append(row)
    return rows


def _global_bound_bound_type71_type99_proxy_solve_comparison_summary(rows: Sequence[dict]) -> dict:
    summaries = [r for r in rows if str(r.get("row_kind")) == "summary"]
    pops = [r for r in rows if str(r.get("row_kind")) == "population"]
    global_case = next((r for r in summaries if str(r.get("comparison_case")) == "global_bound_bound_plus_type71_plus_type99_proxy_block"), {})
    base_case = next((r for r in summaries if str(r.get("comparison_case")) == "per_ion_baseline"), {})
    vals = [maybe_float(r.get("abs_delta_global_minus_old")) for r in pops]
    vals = [float(v) for v in vals if v is not None]
    super_vals = [maybe_float(r.get("global_population_fraction")) for r in pops if bool(r.get("is_superlevel"))]
    super_vals = [float(v) for v in super_vals if v is not None]
    return {
        "n_global_bound_bound_type71_type99_proxy_solve_comparison_rows": len(rows),
        "n_population_comparison_rows": len(pops),
        "baseline_f_fraction": base_case.get("f_fraction"),
        "global_type71_type99_proxy_f_fraction": global_case.get("f_fraction"),
        "baseline_i_fraction": base_case.get("i_fraction"),
        "global_type71_type99_proxy_i_fraction": global_case.get("i_fraction"),
        "baseline_r_fraction": base_case.get("r_fraction"),
        "global_type71_type99_proxy_r_fraction": global_case.get("r_fraction"),
        "global_type71_type99_proxy_solve_status": global_case.get("solve_status"),
        "global_type71_type99_proxy_solver_warning": global_case.get("solver_warning"),
        "n_type99_proxy_source_terms": global_case.get("n_type99_proxy_source_terms"),
        "type99_proxy_source_sum_s^-1": global_case.get("type99_proxy_source_sum_s^-1"),
        "superlevel_population_sum": global_case.get("superlevel_population_sum"),
        "max_superlevel_population": max(super_vals) if super_vals else None,
        "max_abs_population_delta": max(vals) if vals else None,
        "l2_distance_to_target": global_case.get("l2_distance_to_target"),
        "provenance": {
            "mode": "v0.3.39 solves a diagnostic global-index block with bound-bound plus type-71 cascade terms and nonphysical type-99 proxy source-vector rows.",
            "assembly": "Type-99 proxy values are not physical phint53pl rates and this is not the final element-wide coupled matrix solve.",
        },
    }




def build_global_bound_bound_type71_type99_type53_proxy_solve_comparison(
    *,
    global_index_rows: Sequence[dict],
    global_bound_bound_matrix_terms: Sequence[dict],
    global_superlevel_cascade_matrix_terms: Sequence[dict],
    global_superlevel_source_matrix_terms: Sequence[dict],
    global_type53_flat_proxy_matrix_terms: Sequence[dict],
    populations: Sequence[dict],
    line_rows: Sequence[dict],
    coupling_rows: Sequence[dict],
    ion_stage: int,
    linear_solver: str = "svd",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    type99_proxy_scale: float = 1.0,
) -> List[dict]:
    """Solve a diagnostic He-like block with type-53 flat proxy sinks.

    v0.3.46 diagnostic only: start from the v0.3.39 global-index block
    (bound-bound + type-71 cascade + nonphysical type-99 proxy source-vector
    rows) and add v0.3.45 type-53 flat-field photoionization proxy loss terms
    as *sink_rates* for mapped bound levels.  The continuum/parent side is not
    solved as a physical population in this block, so the off-diagonal
    bound->continuum topology rows are intentionally not included in the local
    He-like block solve.  This tests the direction of bound-level
    photoionization losses before XSTAR phint53/Milne rates and full adjacent-ion
    balance are implemented.
    """
    ion_stage = int(ion_stage)
    ion_global_rows = [
        r for r in global_index_rows
        if maybe_int(r.get("ion_stage")) == ion_stage and not bool(r.get("is_continuum"))
    ]
    global_to_level: Dict[int, int] = {}
    global_to_row: Dict[int, dict] = {}
    for r in ion_global_rows:
        g = maybe_int(r.get("global_index"))
        lev = maybe_int(r.get("level_index"))
        if g is not None and lev is not None:
            global_to_level[int(g)] = int(lev)
            global_to_row[int(g)] = r

    used_globals: set[int] = set()
    for terms, status in (
        (global_bound_bound_matrix_terms, "assembled_global_bound_bound_scaffold"),
        (global_superlevel_cascade_matrix_terms, "assembled_global_type71_superlevel_cascade_scaffold"),
    ):
        for t in terms:
            if str(t.get("assembly_status")) != status:
                continue
            if maybe_int(t.get("ion_stage")) != ion_stage:
                continue
            row = maybe_int(t.get("matrix_row_global_index"))
            col = maybe_int(t.get("matrix_col_global_index"))
            if row in global_to_level and col in global_to_level:
                used_globals.add(int(row))
                used_globals.add(int(col))

    for t in global_superlevel_source_matrix_terms:
        if str(t.get("assembly_status")) != "assembled_global_type99_superlevel_source_scaffold_proxy":
            continue
        if str(t.get("matrix_term_kind")) != "source_vector_gain_proxy":
            continue
        if maybe_int(t.get("ion_stage")) != ion_stage:
            continue
        row = maybe_int(t.get("matrix_row_global_index"))
        if row in global_to_level:
            used_globals.add(int(row))

    for t in global_type53_flat_proxy_matrix_terms:
        if str(t.get("assembly_status")) != "diagnostic_proxy_topology_only_not_used_in_solve":
            continue
        if str(t.get("matrix_term_kind")) != "diagonal_bound_photoion_proxy_loss":
            continue
        if maybe_int(t.get("target_ion_stage")) != ion_stage:
            continue
        row = maybe_int(t.get("matrix_row_global_index"))
        if row in global_to_level:
            used_globals.add(int(row))

    for r in coupling_rows:
        if bool(r.get("assembled")) and maybe_int(r.get("target_ion_stage")) == ion_stage:
            dest = maybe_int(r.get("destination_level"))
            if dest is not None:
                for g, lev in global_to_level.items():
                    if lev == int(dest):
                        used_globals.add(g)
    for r in line_rows:
        if maybe_int(r.get("ion_stage")) == ion_stage:
            for key in ("lower_level", "upper_level"):
                lev = maybe_int(r.get(key))
                if lev is not None:
                    for g, glev in global_to_level.items():
                        if glev == int(lev):
                            used_globals.add(g)

    selected_globals = sorted(used_globals)
    level_indices = [global_to_level[g] for g in selected_globals]
    g_to_local = {g: k for k, g in enumerate(selected_globals)}
    n = len(selected_globals)
    R = np.zeros((n, n), dtype=float)
    n_bb_offdiag = n_bb_diag = n_t71_offdiag = n_t71_diag = 0
    diag_from_terms = np.zeros(n, dtype=float)

    def add_terms(terms: Sequence[dict], status: str, source_label: str) -> None:
        nonlocal n_bb_offdiag, n_bb_diag, n_t71_offdiag, n_t71_diag
        for t in terms:
            if str(t.get("assembly_status")) != status:
                continue
            if maybe_int(t.get("ion_stage")) != ion_stage:
                continue
            row = maybe_int(t.get("matrix_row_global_index"))
            col = maybe_int(t.get("matrix_col_global_index"))
            rate = maybe_float(t.get("signed_rate_s^-1"))
            if row is None or col is None or rate is None or row not in g_to_local or col not in g_to_local:
                continue
            kind = str(t.get("matrix_term_kind"))
            if kind == "offdiag_gain" and row != col and float(rate) > 0.0:
                R[g_to_local[int(row)], g_to_local[int(col)]] += float(rate)
                if source_label == "bound_bound":
                    n_bb_offdiag += 1
                else:
                    n_t71_offdiag += 1
            elif kind == "diagonal_loss" and row == col:
                diag_from_terms[g_to_local[int(row)]] += float(rate)
                if source_label == "bound_bound":
                    n_bb_diag += 1
                else:
                    n_t71_diag += 1

    add_terms(global_bound_bound_matrix_terms, "assembled_global_bound_bound_scaffold", "bound_bound")
    add_terms(global_superlevel_cascade_matrix_terms, "assembled_global_type71_superlevel_cascade_scaffold", "type71")

    expected_diag = -np.sum(R, axis=0)
    diag_linf = float(np.max(np.abs(diag_from_terms - expected_diag))) if n else 0.0

    source_vector, source_rows = _assemble_source_vector_from_coupling_rows(
        level_indices=level_indices,
        coupling_rows=coupling_rows,
        ion_stage=ion_stage,
    )
    n_type99_proxy_source_terms = 0
    type99_proxy_source_sum = 0.0
    for t in global_superlevel_source_matrix_terms:
        if str(t.get("assembly_status")) != "assembled_global_type99_superlevel_source_scaffold_proxy":
            continue
        if str(t.get("matrix_term_kind")) != "source_vector_gain_proxy":
            continue
        if maybe_int(t.get("ion_stage")) != ion_stage:
            continue
        g = maybe_int(t.get("matrix_row_global_index"))
        proxy = maybe_float(t.get("signed_rate_proxy"))
        if g is None or proxy is None or g not in g_to_local:
            continue
        k = g_to_local[int(g)]
        scaled_proxy = float(proxy) * float(type99_proxy_scale)
        source_vector[k] += scaled_proxy
        n_type99_proxy_source_terms += 1
        type99_proxy_source_sum += scaled_proxy
        source_rows.append({
            "source_family": "type99_superlevel_proxy_source",
            "source_record": t.get("type99_records"),
            "source_data_type": 99,
            "destination_level": global_to_level.get(int(g)),
            "destination_global_index": int(g),
            "destination_level_label": global_to_row.get(int(g), {}).get("level_label"),
            "destination_level_kind": global_to_row.get(int(g), {}).get("level_kind"),
            "source_rate_s^-1": scaled_proxy,
            "unscaled_source_rate_proxy_s^-1": float(proxy),
            "type99_proxy_scale": type99_proxy_scale,
            "applied_to_global_bound_bound_type71_type99_type53_proxy_block": True,
            "warning": "diagnostic_proxy_only_not_physical_type99_phint53pl_rate",
        })

    sink_rates = np.zeros(n, dtype=float)
    sink_rows: List[dict] = []
    n_type53_proxy_sink_terms = 0
    type53_proxy_sink_sum = 0.0
    for t in global_type53_flat_proxy_matrix_terms:
        if str(t.get("assembly_status")) != "diagnostic_proxy_topology_only_not_used_in_solve":
            continue
        if str(t.get("matrix_term_kind")) != "diagonal_bound_photoion_proxy_loss":
            continue
        if maybe_int(t.get("target_ion_stage")) != ion_stage:
            continue
        g = maybe_int(t.get("matrix_row_global_index"))
        rate = maybe_float(t.get("rate_proxy_s^-1"))
        if g is None or rate is None or g not in g_to_local:
            continue
        k = g_to_local[int(g)]
        sink_rates[k] += float(rate)
        n_type53_proxy_sink_terms += 1
        type53_proxy_sink_sum += float(rate)
        sink_rows.append({
            "sink_family": "type53_flat_photoionization_proxy_sink",
            "sink_record": t.get("record"),
            "sink_data_type": 53,
            "source_level": global_to_level.get(int(g)),
            "source_global_index": int(g),
            "source_level_label": global_to_row.get(int(g), {}).get("level_label"),
            "source_level_kind": global_to_row.get(int(g), {}).get("level_kind"),
            "continuum_or_parent_global_index": t.get("continuum_or_parent_global_index"),
            "sink_rate_s^-1": float(rate),
            "type53_flat_proxy_scale": t.get("type53_flat_proxy_scale"),
            "applied_as_sink_rate_only": True,
            "warning": "diagnostic_flat_proxy_only_not_physical_phint53_rate_parent_population_not_solved",
        })

    if n == 0:
        pop = np.array([], dtype=float)
        solve_info = {"matrix_size": 0, "solution_status": "empty", "solver_warning": "empty global bound-bound+type71+type99proxy+type53proxy block"}
    else:
        pop, solve_info = solve_steady_state(
            R,
            source_vector=source_vector if np.count_nonzero(source_vector) else None,
            sink_rates=sink_rates if np.count_nonzero(sink_rates) else None,
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
        )
        solve_info["solution_status"] = "ok" if not solve_info.get("solver_warning") else "warning"

    global_pop_by_level = {int(lev): float(pop[k]) for k, lev in enumerate(level_indices)}
    old_pop_by_level: Dict[int, float] = {}
    for r in populations:
        if maybe_int(r.get("ion_stage")) == ion_stage:
            lev = maybe_int(r.get("level_index"))
            val = maybe_float(r.get("population_fraction"))
            if lev is not None and val is not None:
                old_pop_by_level[int(lev)] = float(val)

    selected_line_rows = [r for r in line_rows if maybe_int(r.get("ion_stage")) == ion_stage]
    global_line_rows = _make_line_rows_with_population(selected_line_rows, global_pop_by_level, solve_info)
    old_triplet = _normalise_triplet(selected_line_rows)
    global_triplet = _normalise_triplet(global_line_rows)
    target = _xstar_triplet_target(ion_stage)
    old_l2 = _triplet_l2_distance(old_triplet, target)
    global_l2 = _triplet_l2_distance(global_triplet, target)

    n_superlevels = sum(1 for g in selected_globals if str(global_to_row.get(g, {}).get("level_kind")) == "superlevel")
    superlevel_population_sum = sum(
        float(pop[k]) for k, g in enumerate(selected_globals)
        if str(global_to_row.get(g, {}).get("level_kind")) == "superlevel"
    ) if len(pop) else 0.0

    rows: List[dict] = []
    common_summary = {
        "ion_stage": ion_stage,
        "n_global_indices": n,
        "n_superlevel_indices": n_superlevels,
        "n_bound_bound_offdiag_gain_terms": n_bb_offdiag,
        "n_bound_bound_diagonal_loss_terms": n_bb_diag,
        "n_type71_offdiag_gain_terms": n_t71_offdiag,
        "n_type71_diagonal_loss_terms": n_t71_diag,
        "n_type99_proxy_source_terms": n_type99_proxy_source_terms,
        "type99_proxy_scale": type99_proxy_scale,
        "type99_proxy_source_sum_s^-1": type99_proxy_source_sum,
        "n_type53_proxy_sink_terms": n_type53_proxy_sink_terms,
        "type53_proxy_sink_sum_s^-1": type53_proxy_sink_sum,
        "diag_loss_linf_mismatch_s^-1": diag_linf,
        "source_sum_s^-1": float(np.sum(source_vector)) - type99_proxy_source_sum if len(source_vector) else 0.0,
        "total_source_sum_s^-1": float(np.sum(source_vector)) if len(source_vector) else 0.0,
        "n_source_terms_nonzero": int(np.count_nonzero(source_vector)) if len(source_vector) else 0,
        "n_sink_terms_nonzero": int(np.count_nonzero(sink_rates)) if len(sink_rates) else 0,
    }
    rows.append({
        "row_kind": "summary",
        "comparison_case": "per_ion_baseline",
        **common_summary,
        "superlevel_population_sum": None,
        "f_fraction": old_triplet.get("f_fraction"),
        "i_fraction": old_triplet.get("i_fraction"),
        "r_fraction": old_triplet.get("r_fraction"),
        "R": old_triplet.get("R"),
        "G": old_triplet.get("G"),
        "l2_distance_to_target": old_l2,
        "solve_status": "baseline_existing_per_ion_solve",
        "solver": "existing_per_ion_solver",
        "provenance": "v0.3.46_global_bound_bound_type71_type99_type53_proxy_solve_comparison",
    })
    rows.append({
        "row_kind": "summary",
        "comparison_case": "global_bound_bound_plus_type71_plus_type99_plus_type53_proxy_block",
        **common_summary,
        "superlevel_population_sum": superlevel_population_sum,
        "f_fraction": global_triplet.get("f_fraction"),
        "i_fraction": global_triplet.get("i_fraction"),
        "r_fraction": global_triplet.get("r_fraction"),
        "R": global_triplet.get("R"),
        "G": global_triplet.get("G"),
        "l2_distance_to_target": global_l2,
        "delta_f_global_minus_baseline": float(global_triplet.get("f_fraction") or 0.0) - float(old_triplet.get("f_fraction") or 0.0),
        "delta_i_global_minus_baseline": float(global_triplet.get("i_fraction") or 0.0) - float(old_triplet.get("i_fraction") or 0.0),
        "delta_r_global_minus_baseline": float(global_triplet.get("r_fraction") or 0.0) - float(old_triplet.get("r_fraction") or 0.0),
        "solve_status": solve_info.get("solution_status"),
        "solver": solve_info.get("solver"),
        "solver_warning": solve_info.get("solver_warning"),
        "matrix_rank": solve_info.get("matrix_rank"),
        "condition_number": solve_info.get("condition_number"),
        "provenance": "v0.3.46_global_bound_bound_type71_type99_type53_proxy_solve_comparison",
    })
    for k, g in enumerate(selected_globals):
        lev = global_to_level[g]
        old = old_pop_by_level.get(int(lev), 0.0)
        new = global_pop_by_level.get(int(lev), 0.0)
        grow = global_to_row.get(g, {})
        rows.append({
            "row_kind": "population",
            "comparison_case": "population_by_global_index",
            "ion_stage": ion_stage,
            "global_index": int(g),
            "level_index": int(lev),
            "level_label": grow.get("level_label"),
            "level_kind": grow.get("level_kind"),
            "is_superlevel": bool(grow.get("is_superlevel")),
            "old_population_fraction": old,
            "global_population_fraction": new,
            "delta_global_minus_old": new - old,
            "abs_delta_global_minus_old": abs(new - old),
            "provenance": "v0.3.46_global_bound_bound_type71_type99_type53_proxy_solve_comparison",
        })
    for sr in source_rows:
        row = {"row_kind": "source", "comparison_case": "rebuilt_source_vector_plus_type99_proxy", "ion_stage": ion_stage}
        row.update(sr)
        row["provenance"] = "v0.3.46_global_bound_bound_type71_type99_type53_proxy_solve_comparison"
        rows.append(row)
    for sk in sink_rows:
        row = {"row_kind": "sink", "comparison_case": "type53_flat_proxy_sink_vector", "ion_stage": ion_stage}
        row.update(sk)
        row["provenance"] = "v0.3.46_global_bound_bound_type71_type99_type53_proxy_solve_comparison"
        rows.append(row)
    return rows


def _global_bound_bound_type71_type99_type53_proxy_solve_comparison_summary(rows: Sequence[dict]) -> dict:
    summaries = [r for r in rows if str(r.get("row_kind")) == "summary"]
    pops = [r for r in rows if str(r.get("row_kind")) == "population"]
    global_case = next((r for r in summaries if str(r.get("comparison_case")) == "global_bound_bound_plus_type71_plus_type99_plus_type53_proxy_block"), {})
    base_case = next((r for r in summaries if str(r.get("comparison_case")) == "per_ion_baseline"), {})
    vals = [maybe_float(r.get("abs_delta_global_minus_old")) for r in pops]
    vals = [float(v) for v in vals if v is not None]
    super_vals = [maybe_float(r.get("global_population_fraction")) for r in pops if bool(r.get("is_superlevel"))]
    super_vals = [float(v) for v in super_vals if v is not None]
    return {
        "n_global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows": len(rows),
        "n_population_comparison_rows": len(pops),
        "baseline_f_fraction": base_case.get("f_fraction"),
        "global_type71_type99_type53_proxy_f_fraction": global_case.get("f_fraction"),
        "baseline_i_fraction": base_case.get("i_fraction"),
        "global_type71_type99_type53_proxy_i_fraction": global_case.get("i_fraction"),
        "baseline_r_fraction": base_case.get("r_fraction"),
        "global_type71_type99_type53_proxy_r_fraction": global_case.get("r_fraction"),
        "global_type71_type99_type53_proxy_solve_status": global_case.get("solve_status"),
        "global_type71_type99_type53_proxy_solver_warning": global_case.get("solver_warning"),
        "n_type99_proxy_source_terms": global_case.get("n_type99_proxy_source_terms"),
        "type99_proxy_source_sum_s^-1": global_case.get("type99_proxy_source_sum_s^-1"),
        "n_type53_proxy_sink_terms": global_case.get("n_type53_proxy_sink_terms"),
        "type53_proxy_sink_sum_s^-1": global_case.get("type53_proxy_sink_sum_s^-1"),
        "superlevel_population_sum": global_case.get("superlevel_population_sum"),
        "max_superlevel_population": max(super_vals) if super_vals else None,
        "max_abs_population_delta": max(vals) if vals else None,
        "l2_distance_to_target": global_case.get("l2_distance_to_target"),
        "provenance": {
            "mode": "v0.3.46 solves a diagnostic global-index block with bound-bound, type-71 cascade, nonphysical type-99 proxy sources, and type-53 flat photoionization proxy sinks.",
            "assembly": "Type-53 proxy sinks are not phint53 rates and parent-continuum populations are not solved in the full adjacent-ion matrix yet.",
        },
    }

def build_global_bound_bound_type71_type99_proxy_scale_scan(
    *,
    global_index_rows: Sequence[dict],
    global_bound_bound_matrix_terms: Sequence[dict],
    global_superlevel_cascade_matrix_terms: Sequence[dict],
    global_superlevel_source_matrix_terms: Sequence[dict],
    populations: Sequence[dict],
    line_rows: Sequence[dict],
    coupling_rows: Sequence[dict],
    ion_stage: int,
    type99_proxy_scale: object = "1",
    linear_solver: str = "svd",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
) -> List[dict]:
    """Scan nonphysical type-99 proxy source normalization.

    v0.3.40 diagnostic only: for each scale, solve the same He-like
    bound-bound+type71 block as v0.3.39, but multiply the type-99
    ``source_vector_gain_proxy`` rows by the requested scale.  The output is a
    compact summary table intended to diagnose whether the type99->superlevel
    ->type71 topology can move the line fractions toward a target before the
    physical XSTAR phint53pl radiation integrals are ported.
    """
    scales = _parse_triplet_source_scales(type99_proxy_scale)
    rows: List[dict] = []
    baseline_rows = build_global_bound_bound_type71_type99_proxy_solve_comparison(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        populations=populations,
        line_rows=line_rows,
        coupling_rows=coupling_rows,
        ion_stage=ion_stage,
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
        type99_proxy_scale=0.0,
    )
    base_summary = next((r for r in baseline_rows if str(r.get("comparison_case")) == "global_bound_bound_plus_type71_plus_type99_proxy_block"), None)
    if base_summary:
        rows.append({
            "row_kind": "baseline_type71_no_type99_proxy",
            "type99_proxy_scale": 0.0,
            "f_fraction": base_summary.get("f_fraction"),
            "i_fraction": base_summary.get("i_fraction"),
            "r_fraction": base_summary.get("r_fraction"),
            "R": base_summary.get("R"),
            "G": base_summary.get("G"),
            "l2_distance_to_target": base_summary.get("l2_distance_to_target"),
            "source_sum_s^-1": base_summary.get("source_sum_s^-1"),
            "type99_proxy_source_sum_s^-1": base_summary.get("type99_proxy_source_sum_s^-1"),
            "n_type99_proxy_source_terms": base_summary.get("n_type99_proxy_source_terms"),
            "superlevel_population_sum": base_summary.get("superlevel_population_sum"),
            "solve_status": base_summary.get("solve_status"),
            "solver_warning": base_summary.get("solver_warning"),
            "matrix_rank": base_summary.get("matrix_rank"),
            "condition_number": base_summary.get("condition_number"),
            "warning": "baseline has type-71 cascade terms but type-99 proxy scale set to zero",
            "provenance": "v0.3.40_type99_proxy_scale_scan",
        })
    for scale in scales:
        comp_rows = build_global_bound_bound_type71_type99_proxy_solve_comparison(
            global_index_rows=global_index_rows,
            global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
            global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
            global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
            populations=populations,
            line_rows=line_rows,
            coupling_rows=coupling_rows,
            ion_stage=ion_stage,
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
            type99_proxy_scale=float(scale),
        )
        summ = next((r for r in comp_rows if str(r.get("comparison_case")) == "global_bound_bound_plus_type71_plus_type99_proxy_block"), {})
        rows.append({
            "row_kind": "type99_proxy_scale_scan",
            "type99_proxy_scale": float(scale),
            "f_fraction": summ.get("f_fraction"),
            "i_fraction": summ.get("i_fraction"),
            "r_fraction": summ.get("r_fraction"),
            "R": summ.get("R"),
            "G": summ.get("G"),
            "l2_distance_to_target": summ.get("l2_distance_to_target"),
            "source_sum_s^-1": summ.get("source_sum_s^-1"),
            "type99_proxy_source_sum_s^-1": summ.get("type99_proxy_source_sum_s^-1"),
            "n_type99_proxy_source_terms": summ.get("n_type99_proxy_source_terms"),
            "superlevel_population_sum": summ.get("superlevel_population_sum"),
            "delta_f_global_minus_baseline": summ.get("delta_f_global_minus_baseline"),
            "delta_i_global_minus_baseline": summ.get("delta_i_global_minus_baseline"),
            "delta_r_global_minus_baseline": summ.get("delta_r_global_minus_baseline"),
            "solve_status": summ.get("solve_status"),
            "solver_warning": summ.get("solver_warning"),
            "matrix_rank": summ.get("matrix_rank"),
            "condition_number": summ.get("condition_number"),
            "warning": "diagnostic_type99_proxy_scale_only_not_physical_phint53pl_rate",
            "provenance": "v0.3.40_type99_proxy_scale_scan",
        })
    return rows


def _type99_proxy_scale_scan_summary(rows: Sequence[dict]) -> dict:
    scan_rows = [r for r in rows if str(r.get("row_kind")) == "type99_proxy_scale_scan"]
    def _finite_l2(r: dict) -> float:
        v = maybe_float(r.get("l2_distance_to_target"))
        return float(v) if v is not None and math.isfinite(float(v)) else float("inf")
    best = min(scan_rows, key=_finite_l2) if scan_rows else None
    base = next((r for r in rows if str(r.get("row_kind")) == "baseline_type71_no_type99_proxy"), {})
    return {
        "n_type99_proxy_scale_scan_rows": len(rows),
        "n_scales": len(scan_rows),
        "baseline_no_type99_proxy_l2_distance_to_target": base.get("l2_distance_to_target"),
        "best_scale": None if best is None else best.get("type99_proxy_scale"),
        "best_l2_distance_to_target": None if best is None else best.get("l2_distance_to_target"),
        "best_f_fraction": None if best is None else best.get("f_fraction"),
        "best_i_fraction": None if best is None else best.get("i_fraction"),
        "best_r_fraction": None if best is None else best.get("r_fraction"),
        "best_type99_proxy_source_sum_s^-1": None if best is None else best.get("type99_proxy_source_sum_s^-1"),
        "provenance": {
            "mode": "v0.3.40 scans nonphysical type-99 proxy source-vector scale in the global bound-bound+type71 diagnostic block.",
            "assembly": "Type-99 proxy values are not physical phint53pl rates and the full adjacent-ion element-wide matrix is not solved yet.",
        },
    }


def build_radiation_context_rows(
    *,
    radiation_field_mode: str = "none",
    temperature: float,
    electron_density: float,
    element: str,
    element_z: int,
    stages: Sequence[int],
    he_like_stage: int,
) -> List[dict]:
    """Return a diagnostic radiation-context scaffold for type-53 work."""
    mode = str(radiation_field_mode or "none").strip().lower()
    if mode not in {"none", "flat", "blackbody", "table"}:
        mode = "none"
    has_placeholder_grid = mode in {"flat", "blackbody", "table"}
    if has_placeholder_grid:
        energy_min_ev = 1.0
        energy_max_ev = 1.0e5
        n_energy_grid_points = 256
        grid_status = "placeholder_log_energy_grid_not_used_for_rates"
    else:
        energy_min_ev = None
        energy_max_ev = None
        n_energy_grid_points = 0
        grid_status = "not_constructed_radiation_field_mode_none"
    return [{
        "row_kind": "radiation_context",
        "radiation_context_version": "v0.3.45",
        "radiation_field_mode": mode,
        "element": element,
        "element_z": element_z,
        "stages": ";".join(str(int(s)) for s in stages),
        "he_like_stage": he_like_stage,
        "temperature_K": temperature,
        "electron_density_cm^-3": electron_density,
        "energy_grid_status": grid_status,
        "n_energy_grid_points": n_energy_grid_points,
        "energy_min_eV": energy_min_ev,
        "energy_max_eV": energy_max_ev,
        "mean_intensity_status": "not_available" if mode == "none" else "placeholder_not_physical",
        "photon_flux_status": "not_available" if mode == "none" else "placeholder_not_physical",
        "photoionization_integral_status": "not_evaluated_requires_phint53_port",
        "milne_inverse_recombination_status": "not_evaluated_requires_milne_or_xstar_inverse_context",
        "opacity_escape_probability_status": "not_available",
        "assembly_status": "context_scaffold_only_not_used_in_matrix",
        "warning": "type53 physical rates are not evaluated; v0.3.45 adds only flat-field proxy diagnostics",
        "provenance": "v0.3.45_type53_flat_proxy_scaffold",
    }]


def _global_index_lookup_one(rows: Sequence[dict], ion_stage: Optional[int], level_index: Optional[int]) -> Optional[int]:
    if ion_stage is None or level_index is None:
        return None
    for row in rows:
        if maybe_int(row.get("ion_stage")) == int(ion_stage) and maybe_int(row.get("level_index")) == int(level_index):
            return maybe_int(row.get("global_index"))
    return None


def _continuum_global_for_parent(rows: Sequence[dict], *, target_ion_stage: int, parent_ion_stage: int) -> Optional[int]:
    for row in rows:
        if maybe_int(row.get("ion_stage")) == int(target_ion_stage) and bool(row.get("is_continuum")):
            pstage = maybe_int(row.get("parent_ion_stage"))
            if pstage is None or pstage == int(parent_ion_stage):
                return maybe_int(row.get("global_index"))
    return None


def build_type53_rate_audit_rows(
    *,
    adjacent_audit_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
    radiation_context_rows: Sequence[dict],
    he_like_stage: int,
) -> List[dict]:
    """Build a diagnostic type-53 radiation/photoionization audit."""
    mode = "none"
    if radiation_context_rows:
        mode = str(radiation_context_rows[0].get("radiation_field_mode", "none"))
    out: List[dict] = []
    for ar in adjacent_audit_rows:
        if maybe_int(ar.get("data_type")) != 53:
            continue
        rec_stage = maybe_int(ar.get("record_ion_stage"))
        target_stage = maybe_int(ar.get("target_ion_stage")) or rec_stage or int(he_like_stage)
        parent_stage = maybe_int(ar.get("parent_ion_stage")) or (target_stage + 1 if target_stage is not None else None)
        bound_level = maybe_int(ar.get("idest1_guess"))
        continuum_guess = maybe_int(ar.get("idest2_guess"))
        final_or_parent_level = maybe_int(ar.get("idest3_guess"))
        bound_g = _global_index_lookup_one(global_index_rows, rec_stage, bound_level)
        continuum_g = _global_index_lookup_one(global_index_rows, rec_stage, continuum_guess)
        if continuum_g is None and target_stage is not None and parent_stage is not None:
            continuum_g = _continuum_global_for_parent(global_index_rows, target_ion_stage=target_stage, parent_ion_stage=parent_stage)
        status = "not_evaluated_no_radiation_field" if mode == "none" else "not_evaluated_placeholder_radiation_context_only"
        missing = []
        if bound_g is None:
            missing.append("bound_level_global_index")
        if continuum_g is None:
            missing.append("continuum_or_parent_global_index")
        missing += ["phint53_photoionization_integral", "milne_inverse_recombination_integral", "radiation_field_J_E_or_flux", "opacity_escape_probability_context"]
        out.append({
            "row_kind": "type53_rate_audit",
            "type53_audit_version": "v0.3.45",
            "record": ar.get("record"),
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "record_ion_stage": rec_stage,
            "target_ion_stage": target_stage,
            "parent_ion_stage": parent_stage,
            "bound_level": bound_level,
            "bound_global_index": bound_g,
            "continuum_level_guess": continuum_guess,
            "continuum_or_parent_global_index": continuum_g,
            "final_or_parent_level_guess": final_or_parent_level,
            "radiation_field_mode": mode,
            "photoionization_rate_s^-1": "",
            "inverse_recombination_rate_s^-1": "",
            "photoionization_integral_status": status,
            "milne_inverse_status": "not_evaluated_requires_phint53_inverse_context",
            "matrix_role_if_implemented": "M[continuum_or_parent,bound]+=photoion_sink_and_M[bound,continuum_or_parent]+=inverse_recomb_source",
            "requires_context": ar.get("requires_context") or "radiation_field_epi_bremsa_opacity_escape_probabilities_population_abundances",
            "matrix_safe_to_assemble": False,
            "missing_requirements": ";".join(missing),
            "assembly_status": "diagnostic_only_not_assembled",
            "provenance": "v0.3.45_type53_flat_proxy_scaffold",
            "raw_reals_preview": ar.get("raw_reals_preview"),
            "raw_ints_preview": ar.get("raw_ints_preview"),
        })
    return out


def _type53_rate_audit_summary(rows: Sequence[dict]) -> dict:
    return {
        "n_type53_rate_audit_rows": len(rows),
        "radiation_field_mode_counts": _counts(rows, "radiation_field_mode"),
        "photoionization_integral_status_counts": _counts(rows, "photoionization_integral_status"),
        "matrix_safe_to_assemble_counts": _counts(rows, "matrix_safe_to_assemble"),
        "n_rows_with_bound_global_index": sum(1 for r in rows if r.get("bound_global_index") not in (None, "")),
        "n_rows_with_continuum_or_parent_global_index": sum(1 for r in rows if r.get("continuum_or_parent_global_index") not in (None, "")),
    }


def _parse_preview_numbers(value: object) -> List[float]:
    """Parse an ATDB preview list that may already be a list or a CSV string."""
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        out = []
        for x in value:
            fx = maybe_float(x)
            if fx is not None and math.isfinite(fx):
                out.append(float(fx))
        return out
    text = str(value).strip()
    if not text:
        return []
    try:
        import ast
        parsed = ast.literal_eval(text)
    except Exception:
        parsed = None
    if isinstance(parsed, (list, tuple)):
        out = []
        for x in parsed:
            fx = maybe_float(x)
            if fx is not None and math.isfinite(fx):
                out.append(float(fx))
        return out
    # Fallback for strings such as "1,2,3".
    out = []
    for part in text.replace("[", "").replace("]", "").split(","):
        fx = maybe_float(part.strip())
        if fx is not None and math.isfinite(fx):
            out.append(float(fx))
    return out


def build_type53_flat_proxy_rate_audit_rows(
    *,
    type53_rate_audit_rows: Sequence[dict],
    radiation_context_rows: Sequence[dict],
    type53_flat_proxy_scale: object = 1.0,
) -> List[dict]:
    """Build diagnostic flat-field proxy rates for type-53 photoionization.

    This is explicitly not XSTAR's ``phint53`` integral.  It uses the absolute
    sum of the previewed type-53 real coefficients as a topology/rate-shape
    proxy under a unit flat placeholder radiation field.  The result is only
    intended to test matrix direction and record mapping before the physical
    radiation integral is ported.
    """
    try:
        scale = float(type53_flat_proxy_scale)
    except Exception:
        scale = 1.0
    if not math.isfinite(scale):
        scale = 1.0
    mode = "none"
    ngrid = 0
    emin = None
    emax = None
    if radiation_context_rows:
        ctx = radiation_context_rows[0]
        mode = str(ctx.get("radiation_field_mode", "none"))
        ngrid = maybe_int(ctx.get("n_energy_grid_points")) or 0
        emin = maybe_float(ctx.get("energy_min_eV"))
        emax = maybe_float(ctx.get("energy_max_eV"))
    rows: List[dict] = []
    for ar in type53_rate_audit_rows:
        reals = _parse_preview_numbers(ar.get("raw_reals_preview"))
        # Ignore leading zero/flag-like coefficient when present; keep a clear audit
        # trail by reporting both the full and trimmed sums.
        coeff_abs_sum_full = sum(abs(x) for x in reals)
        trimmed = reals[1:] if reals and abs(reals[0]) == 0.0 else reals
        coeff_abs_sum_trimmed = sum(abs(x) for x in trimmed)
        flat_field_integral_proxy = coeff_abs_sum_trimmed
        rate_proxy = scale * flat_field_integral_proxy if mode != "none" else 0.0
        bound_g = maybe_int(ar.get("bound_global_index"))
        cont_g = maybe_int(ar.get("continuum_or_parent_global_index"))
        safe_topology = bound_g is not None and cont_g is not None
        rows.append({
            "row_kind": "type53_flat_proxy_rate_audit",
            "type53_flat_proxy_version": "v0.3.45",
            "record": ar.get("record"),
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "record_ion_stage": ar.get("record_ion_stage"),
            "target_ion_stage": ar.get("target_ion_stage"),
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "bound_level": ar.get("bound_level"),
            "bound_global_index": bound_g,
            "continuum_or_parent_global_index": cont_g,
            "final_or_parent_level_guess": ar.get("final_or_parent_level_guess"),
            "radiation_field_mode": mode,
            "n_energy_grid_points": ngrid,
            "energy_min_eV": emin,
            "energy_max_eV": emax,
            "type53_flat_proxy_scale": scale,
            "n_preview_real_coefficients": len(reals),
            "type53_coeff_abs_sum_full_preview": coeff_abs_sum_full,
            "type53_coeff_abs_sum_trimmed_preview": coeff_abs_sum_trimmed,
            "flat_field_integral_proxy": flat_field_integral_proxy,
            "photoionization_rate_proxy_s^-1": rate_proxy,
            "inverse_recombination_rate_proxy_s^-1": 0.0,
            "proxy_rate_basis": "scale_times_abs_sum_of_previewed_type53_real_coefficients_under_unit_flat_placeholder_field",
            "matrix_role_if_assembled": "M[continuum_or_parent,bound]+=photoion_proxy_sink_and_M[bound,bound]-=photoion_proxy_sink",
            "topology_safe_for_proxy_matrix": safe_topology,
            "matrix_safe_to_assemble_physically": False,
            "assembly_status": "diagnostic_flat_proxy_not_assembled",
            "missing_physical_requirements": "phint53_photoionization_integral;radiation_field_J_E_or_flux;opacity_escape_probability_context;milne_inverse_recombination_integral",
            "warning": "nonphysical_flat_field_proxy_rate_do_not_compare_as_XSTAR_rate",
            "provenance": "v0.3.45_type53_flat_field_proxy_rate_audit",
            "raw_reals_preview": ar.get("raw_reals_preview"),
            "raw_ints_preview": ar.get("raw_ints_preview"),
        })
    return rows


def build_global_type53_flat_proxy_matrix_terms(
    type53_flat_proxy_rate_audit_rows: Sequence[dict],
) -> List[dict]:
    """Map type-53 flat proxy photoionization sinks onto global matrix triplets."""
    rows: List[dict] = []
    tid = 0
    for ar in type53_flat_proxy_rate_audit_rows:
        bound_g = maybe_int(ar.get("bound_global_index"))
        cont_g = maybe_int(ar.get("continuum_or_parent_global_index"))
        rate = maybe_float(ar.get("photoionization_rate_proxy_s^-1")) or 0.0
        safe = bool(ar.get("topology_safe_for_proxy_matrix")) and bound_g is not None and cont_g is not None
        base = {
            "record": ar.get("record"),
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "record_ion_stage": ar.get("record_ion_stage"),
            "target_ion_stage": ar.get("target_ion_stage"),
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "bound_level": ar.get("bound_level"),
            "bound_global_index": bound_g,
            "continuum_or_parent_global_index": cont_g,
            "radiation_field_mode": ar.get("radiation_field_mode"),
            "type53_flat_proxy_scale": ar.get("type53_flat_proxy_scale"),
            "proxy_rate_basis": ar.get("proxy_rate_basis"),
            "matrix_safe_to_assemble_physically": False,
            "provenance": "v0.3.45_type53_flat_proxy_matrix_topology",
        }
        if not safe:
            tid += 1
            rows.append({
                **base,
                "global_type53_flat_proxy_term_id": tid,
                "row_kind": "global_type53_flat_proxy_matrix_term",
                "matrix_term_kind": "skipped_photoionization_sink_proxy",
                "matrix_role": "skipped_missing_global_index_mapping",
                "matrix_row_global_index": "",
                "matrix_col_global_index": "",
                "signed_rate_proxy_s^-1": "",
                "rate_proxy_s^-1": rate,
                "assembly_status": "skipped_proxy_topology_incomplete",
                "skip_reason": "missing_bound_or_continuum_global_index",
            })
            continue
        tid += 1
        rows.append({
            **base,
            "global_type53_flat_proxy_term_id": tid,
            "row_kind": "global_type53_flat_proxy_matrix_term",
            "matrix_term_kind": "offdiag_bound_to_continuum_photoion_proxy_gain",
            "matrix_role": "M[continuum_or_parent_global_index,bound_global_index]+=photoionization_proxy_rate",
            "matrix_row_global_index": cont_g,
            "matrix_col_global_index": bound_g,
            "signed_rate_proxy_s^-1": rate,
            "rate_proxy_s^-1": rate,
            "assembly_status": "diagnostic_proxy_topology_only_not_used_in_solve",
            "skip_reason": "",
        })
        tid += 1
        rows.append({
            **base,
            "global_type53_flat_proxy_term_id": tid,
            "row_kind": "global_type53_flat_proxy_matrix_term",
            "matrix_term_kind": "diagonal_bound_photoion_proxy_loss",
            "matrix_role": "M[bound_global_index,bound_global_index]-=photoionization_proxy_rate",
            "matrix_row_global_index": bound_g,
            "matrix_col_global_index": bound_g,
            "signed_rate_proxy_s^-1": -rate,
            "rate_proxy_s^-1": rate,
            "assembly_status": "diagnostic_proxy_topology_only_not_used_in_solve",
            "skip_reason": "",
        })
    return rows


def _type53_flat_proxy_rate_audit_summary(rows: Sequence[dict]) -> dict:
    rates = [maybe_float(r.get("photoionization_rate_proxy_s^-1")) or 0.0 for r in rows]
    return {
        "n_type53_flat_proxy_rate_audit_rows": len(rows),
        "radiation_field_mode_counts": _counts(rows, "radiation_field_mode"),
        "n_topology_safe_for_proxy_matrix": sum(1 for r in rows if bool(r.get("topology_safe_for_proxy_matrix"))),
        "total_photoionization_rate_proxy_s^-1": sum(rates),
        "max_photoionization_rate_proxy_s^-1": max(rates) if rates else None,
        "proxy_scale_values": sorted({r.get("type53_flat_proxy_scale") for r in rows}),
        "warning": "Nonphysical flat-field proxy; XSTAR phint53/Milne rates are not evaluated.",
    }


def _global_type53_flat_proxy_matrix_terms_summary(rows: Sequence[dict]) -> dict:
    rates = [maybe_float(r.get("rate_proxy_s^-1")) or 0.0 for r in rows if "skipped" not in str(r.get("matrix_term_kind"))]
    return {
        "n_global_type53_flat_proxy_matrix_term_rows": len(rows),
        "matrix_term_kind_counts": _counts(rows, "matrix_term_kind"),
        "assembly_status_counts": _counts(rows, "assembly_status"),
        "total_abs_rate_proxy_s^-1": sum(abs(x) for x in rates),
        "warning": "Proxy matrix triplets are diagnostic topology only and are not used in the solve.",
    }



def build_full_global_matrix_terms(
    *,
    global_index_rows: Sequence[dict],
    global_bound_bound_matrix_terms: Sequence[dict],
    global_superlevel_cascade_matrix_terms: Sequence[dict],
    global_superlevel_source_matrix_terms: Sequence[dict],
    global_type53_flat_proxy_matrix_terms: Sequence[dict],
    coupling_rows: Sequence[dict],
    he_like_stage: int,
) -> List[dict]:
    """Combine current global-index scaffolds into one full element matrix topology.

    Diagnostic/topology-only v0.3.47 inventory for the future C VI+C V matrix.
    It combines bound-bound blocks, type-71 cascade terms, type-99 proxy
    parent-continuum topology, type-53 flat photoionization proxy topology, and
    mappable type-1 recombination source/topology rows.  It is not solved here.
    """
    out: List[dict] = []
    tid = 0

    def _add(row: dict, *, component: str, source_row_kind: str, status: str = "assembled_full_global_topology_scaffold") -> None:
        nonlocal tid
        r = dict(row)
        signed = maybe_float(r.get("signed_rate_s^-1"))
        if signed is None:
            signed = maybe_float(r.get("signed_rate_proxy_s^-1"))
        if signed is None:
            signed = maybe_float(r.get("signed_rate_proxy"))
        rate = maybe_float(r.get("rate_s^-1"))
        if rate is None:
            rate = maybe_float(r.get("rate_proxy_s^-1"))
        if rate is None:
            rate = maybe_float(r.get("rate_proxy"))
        if rate is None:
            rate = maybe_float(r.get("source_rate_s^-1"))
        if rate is None:
            rate = maybe_float(r.get("source_rate_total_s^-1"))
        r.update({
            "full_global_term_id": tid,
            "row_kind": "full_global_matrix_term",
            "full_global_component": component,
            "source_row_kind": source_row_kind,
            "full_global_assembly_status": status,
            "full_global_signed_rate_s^-1": "" if signed is None else float(signed),
            "full_global_rate_s^-1": "" if rate is None else float(rate),
            "full_global_provenance": "v0.3.47_full_global_CVI_CV_matrix_topology_scaffold",
        })
        out.append(r)
        tid += 1

    for r in global_bound_bound_matrix_terms:
        if str(r.get("assembly_status")) == "assembled_global_bound_bound_scaffold":
            _add(r, component="bound_bound_blocks_CVI_CV", source_row_kind="global_bound_bound_matrix_term")

    for r in global_superlevel_cascade_matrix_terms:
        if str(r.get("assembly_status")) == "assembled_global_type71_superlevel_cascade_scaffold":
            _add(r, component="type71_superlevel_cascade", source_row_kind="global_superlevel_cascade_matrix_term")

    for r in global_superlevel_source_matrix_terms:
        if str(r.get("assembly_status")) != "assembled_global_type99_superlevel_source_scaffold_proxy":
            continue
        kind = str(r.get("matrix_term_kind"))
        if kind in {"offdiag_parent_continuum_to_superlevel_proxy", "diagonal_parent_continuum_loss_proxy"}:
            _add(r, component="type99_parent_continuum_to_superlevel_proxy", source_row_kind="global_superlevel_source_matrix_term")
        elif kind == "source_vector_gain_proxy":
            _add(r, component="type99_superlevel_source_vector_proxy", source_row_kind="global_superlevel_source_vector_term")

    for r in global_type53_flat_proxy_matrix_terms:
        if str(r.get("assembly_status")) == "diagnostic_proxy_topology_only_not_used_in_solve":
            _add(r, component="type53_flat_photoionization_proxy", source_row_kind="global_type53_flat_proxy_matrix_term")

    lookup = _global_index_lookup(global_index_rows)
    for cr in coupling_rows:
        if not bool(cr.get("assembled")):
            continue
        if maybe_int(cr.get("data_type")) != 1:
            continue
        target_stage = maybe_int(cr.get("target_ion_stage"))
        dest = maybe_int(cr.get("destination_level"))
        rate = maybe_float(cr.get("source_rate_total_s^-1"))
        if target_stage is None or dest is None or rate is None:
            continue
        dest_row = lookup.get((int(target_stage), int(dest)))
        cont_row = _find_parent_continuum_global_row(global_index_rows, ion_stage=int(target_stage))
        if dest_row is None:
            _add({
                "matrix_term_kind": "skipped_type1_recombination_source",
                "matrix_role": "not_assembled_destination_missing_global_index",
                "data_type": 1,
                "record": cr.get("record"),
                "ion_stage": int(target_stage),
                "destination_level": int(dest),
                "source_rate_s^-1": float(rate),
                "rate_s^-1": float(rate),
                "signed_rate_s^-1": 0.0,
                "assembly_status": "skipped",
                "skip_reason": "destination_level_not_found_in_global_index",
                "provenance": "v0.3.47_type1_recombination_source_topology_scaffold",
            }, component="type1_recombination_source_vector", source_row_kind="assembled_adjacent_coupling_source_term", status="skipped")
            continue
        dest_g = maybe_int(dest_row.get("global_index"))
        parent_g = maybe_int(cont_row.get("global_index")) if cont_row else None
        common = {
            "data_type": 1,
            "rate_type": cr.get("rate_type"),
            "record": cr.get("record"),
            "ion_stage": int(target_stage),
            "target_ion_stage": int(target_stage),
            "parent_ion_stage": cr.get("parent_ion_stage") or (int(target_stage) + 1),
            "destination_level": int(dest),
            "destination_global_index": dest_g,
            "destination_level_label": dest_row.get("level_label"),
            "parent_continuum_global_index": "" if parent_g is None else parent_g,
            "parent_continuum_level_index": "" if cont_row is None else cont_row.get("level_index"),
            "source_rate_s^-1": float(rate),
            "rate_s^-1": float(rate),
            "assembly_status": "assembled_global_type1_recombination_source_topology",
            "skip_reason": "",
            "matrix_safe_to_solve_physically": False,
            "unsafe_reason": "source_vector_or_parent_continuum_proxy_only;full_global_population_normalization_not_solved_yet",
            "provenance": "v0.3.47_type1_recombination_source_topology_scaffold",
        }
        _add({
            **common,
            "matrix_term_kind": "type1_recombination_source_vector",
            "matrix_role": "b[destination_global_index] += type1_recombination_source_rate",
            "matrix_row_global_index": dest_g,
            "matrix_col_global_index": "",
            "signed_rate_s^-1": float(rate),
        }, component="type1_recombination_source_vector", source_row_kind="assembled_adjacent_coupling_source_term")
        if parent_g is not None:
            _add({
                **common,
                "matrix_term_kind": "offdiag_parent_continuum_to_type1_destination_proxy",
                "matrix_role": "M[destination_global_index,parent_continuum_global_index] += type1_recombination_rate_proxy",
                "matrix_row_global_index": dest_g,
                "matrix_col_global_index": parent_g,
                "signed_rate_s^-1": float(rate),
                "assembly_status": "assembled_global_type1_parent_continuum_topology_proxy",
            }, component="type1_parent_continuum_to_destination_proxy", source_row_kind="assembled_adjacent_coupling_matrix_proxy")
            _add({
                **common,
                "matrix_term_kind": "diagonal_parent_continuum_type1_loss_proxy",
                "matrix_role": "M[parent_continuum_global_index,parent_continuum_global_index] -= type1_recombination_rate_proxy",
                "matrix_row_global_index": parent_g,
                "matrix_col_global_index": parent_g,
                "signed_rate_s^-1": -float(rate),
                "assembly_status": "assembled_global_type1_parent_continuum_topology_proxy",
            }, component="type1_parent_continuum_to_destination_proxy", source_row_kind="assembled_adjacent_coupling_matrix_proxy")
    return out


def _full_global_matrix_terms_summary(rows: Sequence[dict]) -> dict:
    matrix_rows = [r for r in rows if maybe_int(r.get("matrix_row_global_index")) is not None and maybe_int(r.get("matrix_col_global_index")) is not None]
    source_rows = [r for r in rows if maybe_int(r.get("matrix_row_global_index")) is not None and maybe_int(r.get("matrix_col_global_index")) is None]
    skipped = [r for r in rows if str(r.get("full_global_assembly_status")) == "skipped" or str(r.get("assembly_status")) == "skipped"]
    return {
        "n_full_global_matrix_term_rows": len(rows),
        "n_full_global_matrix_triplet_rows": len(matrix_rows),
        "n_full_global_source_vector_rows": len(source_rows),
        "n_full_global_skipped_rows": len(skipped),
        "rows_by_component": _counts(rows, "full_global_component"),
        "rows_by_matrix_term_kind": _counts(rows, "matrix_term_kind"),
        "rows_by_ion_stage": _counts(rows, "ion_stage"),
        "n_unique_matrix_positions": len({
            (maybe_int(r.get("matrix_row_global_index")), maybe_int(r.get("matrix_col_global_index")))
            for r in matrix_rows
        }),
        "total_positive_rate_or_proxy_s^-1": sum(max(0.0, float(maybe_float(r.get("full_global_signed_rate_s^-1")) or 0.0)) for r in rows),
        "total_negative_rate_or_proxy_s^-1": sum(min(0.0, float(maybe_float(r.get("full_global_signed_rate_s^-1")) or 0.0)) for r in rows),
        "warning": "Topology scaffold only: includes nonphysical proxy rows and source-vector rows; the full C VI+C V normalized matrix is not solved in v0.3.47.",
    }





def _xstar_lucy_lu_solve(A: np.ndarray, b: np.ndarray, *, max_improve: int = 2):
    """Solve ``A x = b`` using the XSTAR ``leqt2f`` style diagnostic path.

    XSTAR's ``leqt2f`` calls Numerical Recipes ``ludcmp``/``lubksb`` and then
    ``mprove`` for iterative improvement.  NumPy does not expose the pivoted LU
    factors used by ``numpy.linalg.solve``; for this pure-Python diagnostic we
    use ``numpy.linalg.solve`` as the LU-backed dense solve and then perform
    explicit iterative improvement by solving for residual corrections.
    """
    x = np.linalg.solve(A, b)
    improvement_norms: List[float] = []
    for _ in range(int(max(0, max_improve))):
        residual = b - A @ x
        rnorm = float(np.linalg.norm(residual))
        improvement_norms.append(rnorm)
        if rnorm <= 1.0e-12 * (1.0 + float(np.linalg.norm(b))):
            break
        dx = np.linalg.solve(A, residual)
        x = x + dx
    return x, improvement_norms


def _xstar_lucy_condensed_solve(
    M: np.ndarray,
    active_indices: Sequence[int],
    global_to_row: Mapping[int, dict],
    *,
    max_outer: int = 50,
    max_inner: int = 20,
    crit: float = 1.0e-2,
    crit2: float = 1.0e-2,
):
    """Diagnostic port of the XSTAR ``msolvelucy`` population iteration.

    This intentionally mirrors the structure of ``msolvelucy`` rather than the
    previous SVD pseudo-inverse solver:

    * build level-to-superlevel memberships;
    * form fractional populations ``rr(level)=x(level)/p(superlevel)``;
    * build a condensed superlevel matrix from the full rate matrix;
    * replace the last condensed row by number conservation;
    * solve the condensed system with an LU-style solve plus iterative
      improvement (``leqt2f`` analogue);
    * expand back to level populations and apply the Lucy fixed-point update.

    It is still diagnostic because the matrix terms contain type-53/type-99/type-1
    proxy rates, not physical XSTAR ``phint53``/``phint53pl`` rates.
    """
    n_full = int(M.shape[0])
    active = [int(i) for i in active_indices]
    if not active:
        return np.zeros(n_full, dtype=float), {
            "solver": "xstar_msolvelucy_lu",
            "solve_status": "empty",
            "solver_warning": "no active global_index rows",
        }
    # The current global index already contains explicit XSTAR-style superlevel
    # and continuum rows.  Keep low/spectroscopic rows explicit and let explicit
    # superlevel/continuum rows act as their own condensed states.  This is the
    # least destructive first diagnostic analogue to XSTAR's nsup array.
    super_keys = []
    super_key_to_local = {}
    local_to_super = []
    for g in active:
        row = global_to_row.get(int(g), {})
        # Future versions can map multiple high-n spectroscopic rows into one
        # superlevel.  For v0.3.50, preserving each global row avoids hiding the
        # triplet upper populations while still exercising the msolvelucy logic.
        key = (str(row.get("ion_stage", "")), str(row.get("level_kind", "")), int(g))
        if key not in super_key_to_local:
            super_key_to_local[key] = len(super_keys)
            super_keys.append(key)
        local_to_super.append(super_key_to_local[key])
    nsup = len(super_keys)
    global_to_active_local = {g: k for k, g in enumerate(active)}
    M_active = M[np.ix_(active, active)].astype(float, copy=True)
    # XSTAR initializes/iterates with a normalized population vector.  Start from
    # statistical weights when available; otherwise uniform.
    x = np.zeros(len(active), dtype=float)
    for k, g in enumerate(active):
        wg = maybe_float(global_to_row.get(int(g), {}).get("statistical_weight_g"))
        if wg is None or not math.isfinite(float(wg)) or float(wg) <= 0.0:
            wg = 1.0
        x[k] = float(wg)
    if float(np.sum(x)) <= 0.0:
        x[:] = 1.0
    x /= float(np.sum(x))
    diff = float("inf")
    diff2 = float("inf")
    niter = 0
    nit3 = 0
    last_lu_improvement_norms: List[float] = []
    lu_failures = 0
    last_condensed_rank = None
    last_condensed_condition = None
    for outer in range(int(max_outer)):
        niter = outer + 1
        xo = x.copy()
        p = np.zeros(nsup, dtype=float)
        for k, sp in enumerate(local_to_super):
            p[sp] += x[k]
        rr = np.ones_like(x)
        for k, sp in enumerate(local_to_super):
            if p[sp] > 1.0e-36:
                rr[k] = x[k] / (1.0e-48 + p[sp])
            else:
                rr[k] = 1.0
        A_sup = np.zeros((nsup, nsup), dtype=float)
        # Condense sum_i M_ij rr_j P_super(j), matching the conservation form
        # implied by msolvelucy's rr-weighted superlevel matrix.
        for i_local in range(len(active)):
            spi = local_to_super[i_local]
            for j_local in range(len(active)):
                val = M_active[i_local, j_local]
                if val != 0.0:
                    spj = local_to_super[j_local]
                    A_sup[spi, spj] += float(val) * float(rr[j_local])
        b_sup = np.zeros(nsup, dtype=float)
        nspcon = nsup - 1
        A_solve = A_sup.copy()
        A_solve[nspcon, :] = 1.0
        b_sup[nspcon] = 1.0
        try:
            last_condensed_rank = int(np.linalg.matrix_rank(A_solve))
            svals = np.linalg.svd(A_solve, compute_uv=False)
            if len(svals) and float(np.min(np.abs(svals))) > 0.0:
                last_condensed_condition = float(np.max(np.abs(svals)) / np.min(np.abs(svals)))
            else:
                last_condensed_condition = None
        except Exception:
            last_condensed_rank = None
            last_condensed_condition = None
        try:
            p_new, last_lu_improvement_norms = _xstar_lucy_lu_solve(A_solve, b_sup, max_improve=2)
        except Exception:
            lu_failures += 1
            # XSTAR's LU path does not use SVD.  For a diagnostic CSV rather than
            # a crash, fall back to least-squares but mark this clearly.
            p_new, *_ = np.linalg.lstsq(A_solve, b_sup, rcond=None)
            last_lu_improvement_norms = []
        x = np.zeros_like(x)
        for k, sp in enumerate(local_to_super):
            x[k] = float(rr[k]) * float(p_new[sp])
        # Lucy fixed-point update on level populations using total incoming and
        # outgoing rates.  This follows the riu/rui/ril/rli spirit in msolvelucy.
        for inner in range(int(max_inner)):
            nit3 += 1
            x_old_inner = x.copy()
            gain = np.zeros_like(x)
            loss = np.zeros_like(x)
            for i in range(len(active)):
                # Incoming positive off-diagonal rates into i from j.
                for j in range(len(active)):
                    if i == j:
                        continue
                    rate = M_active[i, j]
                    if rate > 0.0:
                        gain[i] += rate * max(0.0, x[j])
                loss_i = -M_active[i, i]
                if loss_i > 0.0:
                    loss[i] = loss_i
            x_new = np.where(loss > 0.0, gain / (loss + 1.0e-24), x)
            sx = float(np.sum(x_new))
            if sx != 0.0 and math.isfinite(sx):
                x_new = x_new / sx
            x = x_new
            diff2 = 0.0
            for old, new in zip(x_old_inner, x):
                if new > 1.0e-6:
                    tst = old / new
                    diff2 += (tst - 1.0) * (tst - 1.0)
                    if diff2 >= 1.0e3:
                        break
            if diff2 < crit2:
                break
        diff = 0.0
        for old, new in zip(xo, x):
            if new > 1.0e-6:
                denom = old + new
                if denom != 0.0:
                    d = min(1.0e10, (old - new) / denom)
                    diff += d * d
                    if diff >= 1.0e3:
                        break
        if diff < crit:
            break
    pop = np.zeros(n_full, dtype=float)
    for k, g in enumerate(active):
        pop[int(g)] = float(x[k])
    meta = {
        "solver": "xstar_msolvelucy_lu",
        "solve_status": "warning" if lu_failures else "ok",
        "solver_warning": "" if not lu_failures else f"condensed_lu_failed_{lu_failures}_times_lstsq_used_for_diagnostic_continuation",
        "xstar_lucy_n_superlevels": int(nsup),
        "xstar_lucy_niter": int(niter),
        "xstar_lucy_nit3": int(nit3),
        "xstar_lucy_diff": float(diff) if math.isfinite(float(diff)) else None,
        "xstar_lucy_diff2": float(diff2) if math.isfinite(float(diff2)) else None,
        "xstar_lucy_crit": float(crit),
        "xstar_lucy_crit2": float(crit2),
        "xstar_lucy_lu_failures": int(lu_failures),
        "xstar_lucy_last_condensed_rank": last_condensed_rank,
        "xstar_lucy_last_condensed_condition": last_condensed_condition,
        "xstar_lucy_last_lu_improvement_norms_json": json.dumps(last_lu_improvement_norms),
    }
    return pop, meta

def build_full_global_normalized_solve_comparison(
    *,
    global_index_rows: Sequence[dict],
    full_global_matrix_terms: Sequence[dict],
    line_rows: Sequence[dict],
    he_like_stage: int,
    linear_solver: str = "svd",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    prune_null_rate_levels: bool = True,
    svd_rcond: Optional[float] = None,
) -> List[dict]:
    """Solve the first diagnostic full C VI+C V normalized global matrix.

    v0.3.50 diagnostic: assemble a dense matrix over all explicit
    ``global_index`` rows from ``xstar_like_element_solver_full_global_matrix_terms.csv``.
    Only matrix triplet rows are used; source-vector rows are deliberately
    excluded.  One row is replaced by the normalization equation
    ``sum_i n_i = 1``.  The full-global path now exposes rank-aware/SVD
    controls similar to the earlier He-like/O VII source-fit solver.  The
    rates include proxy topology terms, so the solution is not a physical
    XSTAR population solution yet.
    """
    he_like_stage = int(he_like_stage)
    indexed_rows: List[dict] = []
    for r in global_index_rows:
        g = maybe_int(r.get("global_index"))
        if g is not None:
            rr = dict(r)
            rr["global_index"] = int(g)
            indexed_rows.append(rr)
    if not indexed_rows:
        return [{
            "row_kind": "summary",
            "comparison_case": "full_global_normalized_proxy_topology_solve",
            "solve_status": "empty",
            "solver_warning": "no global_index rows available",
            "provenance": "v0.3.50_full_global_xstar_lucy_solve_comparison",
        }]

    indexed_rows = sorted(indexed_rows, key=lambda r: int(r.get("global_index")))
    max_g = max(int(r.get("global_index")) for r in indexed_rows)
    n = max_g + 1
    global_to_row = {int(r.get("global_index")): r for r in indexed_rows}
    global_to_ion_level = {
        int(r.get("global_index")): (maybe_int(r.get("ion_stage")), maybe_int(r.get("level_index")))
        for r in indexed_rows
    }

    M = np.zeros((n, n), dtype=float)
    n_triplet_rows_used = 0
    n_source_vector_rows_excluded = 0
    n_skipped_bad_index = 0
    n_skipped_bad_rate = 0
    component_counts: Dict[str, int] = {}
    kind_counts: Dict[str, int] = {}
    for t in full_global_matrix_terms:
        row = maybe_int(t.get("matrix_row_global_index"))
        col = maybe_int(t.get("matrix_col_global_index"))
        if row is not None and col is None:
            n_source_vector_rows_excluded += 1
            continue
        if row is None or col is None:
            n_skipped_bad_index += 1
            continue
        if int(row) < 0 or int(col) < 0 or int(row) >= n or int(col) >= n:
            n_skipped_bad_index += 1
            continue
        rate = maybe_float(t.get("full_global_signed_rate_s^-1"))
        if rate is None:
            rate = maybe_float(t.get("signed_rate_s^-1"))
        if rate is None:
            rate = maybe_float(t.get("signed_rate_proxy_s^-1"))
        if rate is None:
            rate = maybe_float(t.get("signed_rate_proxy"))
        if rate is None or not math.isfinite(float(rate)):
            n_skipped_bad_rate += 1
            continue
        M[int(row), int(col)] += float(rate)
        n_triplet_rows_used += 1
        comp = str(t.get("full_global_component", ""))
        kind = str(t.get("matrix_term_kind", ""))
        component_counts[comp] = component_counts.get(comp, 0) + 1
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    # Optionally prune isolated/null-rate rows before solving.  This mirrors the
    # earlier rank-aware He-like solver option while preserving the original
    # global-index numbering in the output table.  Rows outside the active set
    # get zero population in the expanded diagnostic vector.
    row_norm = np.sum(np.abs(M), axis=1)
    col_norm = np.sum(np.abs(M), axis=0)
    null_rate_tolerance = 1.0e-300
    if prune_null_rate_levels:
        active_indices = [i for i in range(n) if (row_norm[i] > null_rate_tolerance or col_norm[i] > null_rate_tolerance)]
        if not active_indices:
            active_indices = list(range(n))
    else:
        active_indices = list(range(n))
    inactive_indices = [i for i in range(n) if i not in set(active_indices)]
    M_solve = M[np.ix_(active_indices, active_indices)] if active_indices else M.copy()
    n_solve = int(M_solve.shape[0])

    # Diagnostic normalization row.  XSTAR's msolvelucy replaces one row of the
    # condensed superlevel system by number conservation and then calls the
    # Numerical-Recipes LU path (leqt2f -> ludcmp/lubksb/mprove).  Here we keep
    # the same number-conservation row idea, but allow SVD/lstsq fallbacks for
    # rank-deficient proxy-topology matrices.
    requested_solver = str(linear_solver or "svd").lower()
    rank_action = str(rank_deficient_action or "svd").lower()
    neg_action = str(negative_population_action or "keep").lower()
    normalization_row_local = 0
    normalization_row = int(active_indices[normalization_row_local]) if active_indices else 0
    A = M_solve.copy()
    b = np.zeros(n_solve, dtype=float)
    if n_solve:
        A[normalization_row_local, :] = 1.0
        b[normalization_row_local] = 1.0

    def _svd_lstsq_local(Ain: np.ndarray, bin: np.ndarray, rcond: Optional[float] = None):
        U, svals_local, Vt = np.linalg.svd(Ain, full_matrices=False)
        if rcond is None:
            cutoff = np.finfo(float).eps * max(Ain.shape) * (float(svals_local[0]) if len(svals_local) else 0.0)
        else:
            cutoff = float(rcond) * (float(svals_local[0]) if len(svals_local) else 0.0)
        inv = np.array([1.0 / sv if sv > cutoff else 0.0 for sv in svals_local], dtype=float)
        x = Vt.T @ (inv * (U.T @ bin)) if len(svals_local) else np.zeros(Ain.shape[1], dtype=float)
        rank_local = int(np.sum(svals_local > cutoff)) if len(svals_local) else 0
        return x, rank_local, svals_local, cutoff

    solve_status = "ok"
    solver = ""
    xstar_meta: Dict[str, object] = {}
    solver_warning = ""
    svd_cutoff = None
    try:
        svals_pre = np.linalg.svd(A, compute_uv=False) if n_solve else np.array([], dtype=float)
        rank_pre = int(np.linalg.matrix_rank(A)) if n_solve else 0
    except Exception:
        svals_pre = np.array([], dtype=float)
        rank_pre = None
    rank_deficient = bool(rank_pre is not None and rank_pre < n_solve)

    try:
        if requested_solver in {"xstar-lucy", "xstar_lucy", "lucy", "msolvelucy"}:
            pop_xstar, xstar_meta = _xstar_lucy_condensed_solve(
                M,
                active_indices,
                global_to_row,
                max_outer=50,
                max_inner=20,
                crit=1.0e-2,
                crit2=1.0e-2,
            )
            pop_solve = np.array([pop_xstar[int(g)] for g in active_indices], dtype=float)
            solver = str(xstar_meta.get("solver") or "xstar_msolvelucy_lu")
            solve_status = str(xstar_meta.get("solve_status") or "ok")
            solver_warning = str(xstar_meta.get("solver_warning") or "")
            rank = int(rank_pre) if rank_pre is not None else int(np.linalg.matrix_rank(A))
            svals = svals_pre if len(svals_pre) else np.linalg.svd(A, compute_uv=False)
        elif requested_solver == "svd" or (rank_deficient and rank_action == "svd"):
            solver = "numpy.linalg.svd_lstsq"
            pop_solve, rank, svals, svd_cutoff = _svd_lstsq_local(A, b, svd_rcond)
            solve_status = "warning" if rank_deficient else "ok"
            if rank_deficient:
                solver_warning = f"matrix rank deficient ({rank}/{n_solve}); solved with SVD pseudoinverse"
        elif requested_solver == "lstsq" or (rank_deficient and rank_action == "lstsq"):
            solver = "numpy.linalg.lstsq_rank_deficient" if rank_deficient else "numpy.linalg.lstsq"
            pop_solve, residuals_tmp, rank_tmp, svals_tmp = np.linalg.lstsq(A, b, rcond=None)
            rank = int(rank_tmp)
            svals = np.asarray(svals_tmp, dtype=float)
            solve_status = "warning" if rank_deficient else "ok"
            if rank_deficient:
                solver_warning = f"matrix rank deficient ({rank}/{n_solve}); solved with lstsq"
        else:
            solver = "numpy.linalg.solve"
            pop_solve = np.linalg.solve(A, b)
            rank = int(rank_pre) if rank_pre is not None else int(np.linalg.matrix_rank(A))
            svals = svals_pre if len(svals_pre) else np.linalg.svd(A, compute_uv=False)
    except Exception as exc:
        if rank_action == "svd":
            try:
                solver = "numpy.linalg.svd_lstsq"
                pop_solve, rank, svals, svd_cutoff = _svd_lstsq_local(A, b, svd_rcond)
                solve_status = "warning"
                solver_warning = f"solve_failed_then_svd_used: {exc}"
            except Exception as exc2:
                pop_solve = np.zeros(n_solve, dtype=float)
                rank = 0
                svals = np.array([], dtype=float)
                solve_status = "failed"
                solver_warning = f"solve_and_svd_failed: {exc}; {exc2}"
        else:
            try:
                solver = "numpy.linalg.lstsq"
                pop_solve, residuals_tmp, rank_tmp, svals_tmp = np.linalg.lstsq(A, b, rcond=None)
                rank = int(rank_tmp)
                svals = np.asarray(svals_tmp, dtype=float)
                solve_status = "warning"
                solver_warning = f"solve_failed_then_lstsq_used: {exc}"
            except Exception as exc2:
                pop_solve = np.zeros(n_solve, dtype=float)
                rank = 0
                svals = np.array([], dtype=float)
                solve_status = "failed"
                solver_warning = f"solve_and_lstsq_failed: {exc}; {exc2}"

    pop = np.zeros(n, dtype=float)
    for local_i, global_i in enumerate(active_indices):
        if local_i < len(pop_solve):
            pop[int(global_i)] = float(pop_solve[local_i])
    if neg_action == "clip":
        pop = np.where(pop < 0.0, 0.0, pop)
        psum = float(np.sum(pop))
        if psum > 0.0:
            pop = pop / psum
        solve_status = "warning" if solve_status == "ok" else solve_status
        solver_warning = (solver_warning + "; " if solver_warning else "") + "negative populations clipped and renormalized"
    elif neg_action == "error" and np.any(pop < -1.0e-12):
        solve_status = "failed"
        solver_warning = (solver_warning + "; " if solver_warning else "") + "negative populations present and negative_population_action=error"

    condition_number = None
    if isinstance(svals, np.ndarray) and len(svals) and float(np.min(np.abs(svals))) > 0.0:
        condition_number = float(np.max(np.abs(svals)) / np.min(np.abs(svals)))
    residual_norm = float(np.linalg.norm(A @ pop_solve - b)) if len(pop_solve) else None
    full_residual_norm = float(np.linalg.norm(M @ pop)) if len(pop) else None
    normalization_residual = float(np.sum(pop) - 1.0) if len(pop) else None
    n_negative = int(np.sum(pop < -1.0e-12)) if len(pop) else 0
    min_population = float(np.min(pop)) if len(pop) else None
    max_population = float(np.max(pop)) if len(pop) else None
    sum_population = float(np.sum(pop)) if len(pop) else 0.0
    # Compare He-like triplet fractions using global populations projected back
    # to the target He-like level indices.
    he_like_pop_by_level: Dict[int, float] = {}
    for g, (stage, lev) in global_to_ion_level.items():
        if stage == he_like_stage and lev is not None and g < len(pop):
            he_like_pop_by_level[int(lev)] = float(pop[g])
    selected_line_rows = [r for r in line_rows if maybe_int(r.get("ion_stage")) == he_like_stage]
    global_line_rows = _make_line_rows_with_population(selected_line_rows, he_like_pop_by_level, {
        "solver": solver,
        "solver_warning": solver_warning,
        "solution_status": solve_status,
    })
    baseline_triplet = _normalise_triplet(selected_line_rows)
    full_triplet = _normalise_triplet(global_line_rows)
    target = _xstar_triplet_target(he_like_stage)
    baseline_l2 = _triplet_l2_distance(baseline_triplet, target)
    full_l2 = _triplet_l2_distance(full_triplet, target)

    ion_population_sums: Dict[str, float] = {}
    kind_population_sums: Dict[str, float] = {}
    for g, val in enumerate(pop):
        grow = global_to_row.get(g, {})
        ion_key = str(grow.get("ion_stage", ""))
        kind_key = str(grow.get("level_kind", ""))
        ion_population_sums[ion_key] = ion_population_sums.get(ion_key, 0.0) + float(val)
        kind_population_sums[kind_key] = kind_population_sums.get(kind_key, 0.0) + float(val)

    rows: List[dict] = []
    common = {
        "n_global_indices": n,
        "n_active_global_indices_solved": n_solve,
        "n_pruned_null_rate_global_indices": len(inactive_indices),
        "prune_null_rate_levels": bool(prune_null_rate_levels),
        "solver_requested": requested_solver,
        "rank_deficient_action": rank_action,
        "negative_population_action": neg_action,
        "xstar_lucy_n_superlevels": xstar_meta.get("xstar_lucy_n_superlevels"),
        "xstar_lucy_niter": xstar_meta.get("xstar_lucy_niter"),
        "xstar_lucy_nit3": xstar_meta.get("xstar_lucy_nit3"),
        "xstar_lucy_diff": xstar_meta.get("xstar_lucy_diff"),
        "xstar_lucy_diff2": xstar_meta.get("xstar_lucy_diff2"),
        "xstar_lucy_crit": xstar_meta.get("xstar_lucy_crit"),
        "xstar_lucy_crit2": xstar_meta.get("xstar_lucy_crit2"),
        "xstar_lucy_lu_failures": xstar_meta.get("xstar_lucy_lu_failures"),
        "xstar_lucy_last_condensed_rank": xstar_meta.get("xstar_lucy_last_condensed_rank"),
        "xstar_lucy_last_condensed_condition": xstar_meta.get("xstar_lucy_last_condensed_condition"),
        "xstar_lucy_last_lu_improvement_norms_json": xstar_meta.get("xstar_lucy_last_lu_improvement_norms_json"),
        "svd_rcond": svd_rcond,
        "svd_cutoff": svd_cutoff,
        "matrix_rank_before_normalization": rank_pre,
        "matrix_rank_deficient_after_normalization": bool(rank is not None and rank < n_solve),
        "full_rate_matrix_residual_norm_excluding_normalization": full_residual_norm,
        "normalization_residual": normalization_residual,
        "n_matrix_triplet_rows_used": n_triplet_rows_used,
        "n_source_vector_rows_excluded": n_source_vector_rows_excluded,
        "n_skipped_bad_index_rows": n_skipped_bad_index,
        "n_skipped_bad_rate_rows": n_skipped_bad_rate,
        "normalization_row_global_index": normalization_row,
        "normalization_equation": "sum_all_global_populations_equals_1",
        "matrix_rank_after_normalization": rank,
        "condition_number_after_normalization": condition_number,
        "residual_norm": residual_norm,
        "n_negative_populations": n_negative,
        "min_population": min_population,
        "max_population": max_population,
        "sum_population": sum_population,
        "rows_by_component_used": json.dumps(dict(sorted(component_counts.items())), sort_keys=True),
        "rows_by_matrix_term_kind_used": json.dumps(dict(sorted(kind_counts.items())), sort_keys=True),
        "ion_population_sums_json": json.dumps(dict(sorted(ion_population_sums.items())), sort_keys=True),
        "level_kind_population_sums_json": json.dumps(dict(sorted(kind_population_sums.items())), sort_keys=True),
        "warning": "diagnostic proxy-topology normalized solve; source-vector rows excluded; XSTAR uses msolvelucy with LU on a condensed superlevel matrix; v0.3.50 adds an xstar-lucy diagnostic mode following that structure, while SVD/lstsq remain available for rank-deficient proxy topology; type53/type99/type1 proxy topology terms are not physical XSTAR rates",
        "provenance": "v0.3.50_full_global_xstar_lucy_solve_comparison",
    }
    rows.append({
        "row_kind": "summary",
        "comparison_case": "per_ion_baseline",
        "f_fraction": baseline_triplet.get("f_fraction"),
        "i_fraction": baseline_triplet.get("i_fraction"),
        "r_fraction": baseline_triplet.get("r_fraction"),
        "R": baseline_triplet.get("R"),
        "G": baseline_triplet.get("G"),
        "l2_distance_to_target": baseline_l2,
        "solve_status": "baseline_existing_per_ion_solve",
        "solver": "existing_per_ion_solver",
        **common,
    })
    rows.append({
        "row_kind": "summary",
        "comparison_case": "full_global_normalized_proxy_topology_solve",
        "f_fraction": full_triplet.get("f_fraction"),
        "i_fraction": full_triplet.get("i_fraction"),
        "r_fraction": full_triplet.get("r_fraction"),
        "R": full_triplet.get("R"),
        "G": full_triplet.get("G"),
        "l2_distance_to_target": full_l2,
        "delta_f_global_minus_baseline": float(full_triplet.get("f_fraction") or 0.0) - float(baseline_triplet.get("f_fraction") or 0.0),
        "delta_i_global_minus_baseline": float(full_triplet.get("i_fraction") or 0.0) - float(baseline_triplet.get("i_fraction") or 0.0),
        "delta_r_global_minus_baseline": float(full_triplet.get("r_fraction") or 0.0) - float(baseline_triplet.get("r_fraction") or 0.0),
        "solve_status": solve_status,
        "solver": solver,
        "solver_warning": solver_warning,
        **common,
    })
    for g in range(n):
        grow = global_to_row.get(g, {})
        rows.append({
            "row_kind": "population",
            "comparison_case": "full_global_population_by_global_index",
            "global_index": g,
            "ion_stage": grow.get("ion_stage"),
            "level_index": grow.get("level_index"),
            "level_label": grow.get("level_label"),
            "level_kind": grow.get("level_kind"),
            "triplet_component": grow.get("triplet_component"),
            "is_triplet_upper": grow.get("is_triplet_upper"),
            "is_superlevel": grow.get("is_superlevel"),
            "is_continuum": grow.get("is_continuum"),
            "population_fraction": float(pop[g]) if g < len(pop) else 0.0,
            "population_abs": abs(float(pop[g])) if g < len(pop) else 0.0,
            "population_negative": bool(g < len(pop) and pop[g] < -1.0e-12),
            "provenance": "v0.3.50_full_global_xstar_lucy_solve_comparison",
        })
    return rows


def _full_global_normalized_solve_comparison_summary(rows: Sequence[dict]) -> dict:
    summaries = [r for r in rows if str(r.get("row_kind")) == "summary"]
    pops = [r for r in rows if str(r.get("row_kind")) == "population"]
    global_case = next((r for r in summaries if str(r.get("comparison_case")) == "full_global_normalized_proxy_topology_solve"), {})
    base_case = next((r for r in summaries if str(r.get("comparison_case")) == "per_ion_baseline"), {})
    return {
        "n_full_global_normalized_solve_comparison_rows": len(rows),
        "n_population_rows": len(pops),
        "baseline_f_fraction": base_case.get("f_fraction"),
        "full_global_f_fraction": global_case.get("f_fraction"),
        "baseline_i_fraction": base_case.get("i_fraction"),
        "full_global_i_fraction": global_case.get("i_fraction"),
        "baseline_r_fraction": base_case.get("r_fraction"),
        "full_global_r_fraction": global_case.get("r_fraction"),
        "full_global_solve_status": global_case.get("solve_status"),
        "full_global_solver": global_case.get("solver"),
        "full_global_solver_requested": global_case.get("solver_requested"),
        "full_global_solver_warning": global_case.get("solver_warning"),
        "full_global_l2_distance_to_target": global_case.get("l2_distance_to_target"),
        "n_matrix_triplet_rows_used": global_case.get("n_matrix_triplet_rows_used"),
        "n_source_vector_rows_excluded": global_case.get("n_source_vector_rows_excluded"),
        "n_negative_populations": global_case.get("n_negative_populations"),
        "sum_population": global_case.get("sum_population"),
        "ion_population_sums_json": global_case.get("ion_population_sums_json"),
        "level_kind_population_sums_json": global_case.get("level_kind_population_sums_json"),
        "warning": "Diagnostic normalized solve over proxy topology rows only; not a physical XSTAR element solution.",
    }

def build_ion_rate_block(
    db: ATDB,
    *,
    z: int,
    ion_stage: int,
    temperature: float,
    electron_density: float,
    wavelength_min: Optional[float] = None,
    wavelength_max: Optional[float] = None,
    max_level: Optional[int] = None,
    component_mode: str = "all",
    ground_level: int = 1,
    prune_null_rate_levels: bool = True,
    linear_solver: str = "svd",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    use_cache: bool = True,
    cache_path: Optional[str] = None,
    adjacent_parent_stage: Optional[int] = None,
    adjacent_coupling_mode: str = "catalog",
    adjacent_coupling_source_mode: str = "record-destination",
    adjacent_coupling_selected_levels: Optional[Sequence[int]] = None,
    include_charge_exchange: bool = False,
    type57_energy_convention: str = "compare",
    extra_source_by_level: Optional[dict] = None,
    extra_source_label: str = "",
) -> Tuple[dict, List[dict], List[dict], List[dict], List[dict], List[dict]]:
    """Build and solve one ion block for the reference element solver.

    Returns ``(block_summary, population_rows, line_rows, transition_rows,
    diagnostics_rows)``.  The function is deliberately verbose and writes no
    files; examples handle file I/O so this can be used in tests.
    """
    records = _select_records(db, z, ion_stage, use_cache=use_cache, cache_path=cache_path)
    levels = extract_levels(db, records, z, ion_stage)
    lines = extract_lines(db, records, z, ion_stage)
    collisions, _collision_grid, collision_eval = extract_collisions(db, records, z, ion_stage, [temperature], electron_density_cm3=electron_density)

    args = _solver_args(wavelength_min=wavelength_min, wavelength_max=wavelength_max, max_level=max_level)
    output_lines = select_output_lines(lines, args)
    level_indices = build_level_set(levels, lines, collisions, args)
    level_set = set(level_indices)
    rad_lines = build_radiative_transitions(lines, level_set, args)
    coll_rows_T = build_collision_rates_for_T(collision_eval, level_set, temperature, electron_density, args)
    edges = build_graph_edges(rad_lines, coll_rows_T, level_set)
    comps = connected_components(level_indices, edges)

    # Component pruning is intentionally conservative in this first reference
    # implementation.  It is useful for isolated-ion diagnostics but can hide
    # source/sink paths in an element-wide solve, so only ground-mode is special.
    if component_mode == "ground" and comps:
        keep = next((set(c) for c in comps if ground_level in c), set(level_indices))
        level_indices = [lev for lev in level_indices if lev in keep]
        level_set = set(level_indices)
        rad_lines = build_radiative_transitions(lines, level_set, args)
        coll_rows_T = build_collision_rates_for_T(collision_eval, level_set, temperature, electron_density, args)

    Rmat, transition_log = assemble_rate_matrix(level_indices, rad_lines, coll_rows_T)
    source_vector = np.zeros(len(level_indices), dtype=float)
    sink_rates = np.zeros(len(level_indices), dtype=float)
    coupling_rows: List[dict] = []
    if adjacent_parent_stage is not None and len(level_indices):
        source_vector, sink_rates, coupling_rows = build_adjacent_coupling_terms(
            db,
            z=z,
            target_ion_stage=ion_stage,
            parent_ion_stage=int(adjacent_parent_stage),
            temperature=temperature,
            electron_density=electron_density,
            level_indices=level_indices,
            level_rows=levels,
            coupling_mode=adjacent_coupling_mode,
            coupling_source_mode=adjacent_coupling_source_mode,
            selected_source_levels=adjacent_coupling_selected_levels,
            include_charge_exchange=include_charge_exchange,
            type57_energy_convention=type57_energy_convention,
        )

    extra_source_rows: List[dict] = []
    if extra_source_by_level and len(level_indices):
        idx_extra = {int(lev): k for k, lev in enumerate(level_indices)}
        for lev_raw, rate_raw in dict(extra_source_by_level).items():
            lev = maybe_int(lev_raw)
            rate = maybe_float(rate_raw)
            applied = False
            if lev is not None and rate is not None and math.isfinite(float(rate)) and float(rate) != 0.0 and int(lev) in idx_extra:
                source_vector[idx_extra[int(lev)]] += float(rate)
                applied = True
            extra_source_rows.append({
                "element": Z_TO_SYMBOL.get(z, str(z)),
                "element_z": z,
                "ion_stage": ion_stage,
                "level_index": lev,
                "extra_source_rate_s^-1": rate,
                "extra_source_label": extra_source_label,
                "extra_source_applied": bool(applied),
            })

    if prune_null_rate_levels:
        pruned, prune_info = prune_null_rate_levels_for_solve(level_indices, Rmat, source_vector, sink_rates, output_lines, ground_level)
        if pruned != level_indices:
            keep_idx = [level_indices.index(lev) for lev in pruned]
            level_indices = pruned
            source_vector = source_vector[keep_idx]
            sink_rates = sink_rates[keep_idx]
            level_set = set(level_indices)
            rad_lines = build_radiative_transitions(lines, level_set, args)
            coll_rows_T = build_collision_rates_for_T(collision_eval, level_set, temperature, electron_density, args)
            Rmat, transition_log = assemble_rate_matrix(level_indices, rad_lines, coll_rows_T)
    else:
        prune_info = {"enabled": False}

    if len(level_indices) == 0:
        pop = np.array([], dtype=float)
        solve_info = {"solver": "none", "solver_warning": "empty level set", "matrix_size": 0, "matrix_nnz": 0, "solution_status": "empty"}
    else:
        pop, solve_info = solve_steady_state(
            Rmat,
            source_vector=source_vector if np.count_nonzero(source_vector) else None,
            sink_rates=sink_rates if np.count_nonzero(sink_rates) else None,
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
        )
        solve_info["solution_status"] = "ok" if not solve_info.get("solver_warning") else "warning"
    level_by_index = {maybe_int(row.get("level_index")): row for row in levels if maybe_int(row.get("level_index")) is not None}
    rad_rates_from_upper: Dict[int, float] = {}
    for row in rad_lines:
        u = maybe_int(row.get("upper_level"))
        A = maybe_float(row.get("A_s^-1"))
        if u is not None and A is not None and A > 0:
            rad_rates_from_upper[u] = rad_rates_from_upper.get(u, 0.0) + A

    line_rows = make_line_output_rows(output_lines, level_indices, pop, temperature, electron_density, solve_info, level_by_index, rad_rates_from_upper) if len(level_indices) else []
    pop_rows: List[dict] = []
    idx = {lev: k for k, lev in enumerate(level_indices)}
    for lev in level_indices:
        base = level_by_index.get(lev, {})
        pop_rows.append({
            "element": Z_TO_SYMBOL.get(z, str(z)),
            "ion_stage": ion_stage,
            "ion_roman": roman(ion_stage),
            "level_index": lev,
            "level_label": base.get("level_label"),
            "energy_eV": base.get("energy_eV"),
            "statistical_weight_g": base.get("statistical_weight_g"),
            "ionization_potential_eV": base.get("ionization_potential_eV"),
            "binding_from_continuum_eV": base.get("binding_from_continuum_eV"),
            "population_fraction": float(pop[idx[lev]]) if len(pop) else 0.0,
            "temperature_K": temperature,
            "electron_density_cm^-3": electron_density,
        })

    for row in transition_log:
        row["element"] = Z_TO_SYMBOL.get(z, str(z))
        row["ion_stage"] = ion_stage
        row["temperature_K"] = temperature
        row["electron_density_cm^-3"] = electron_density

    block_diag = IonBlockDiagnostics(
        element=Z_TO_SYMBOL.get(z, str(z)),
        element_z=z,
        ion_stage=ion_stage,
        ion_label=f"{Z_TO_SYMBOL.get(z, str(z))} {roman(ion_stage)}",
        n_records=len(records),
        n_levels_decoded=len(levels),
        n_levels_used=len(level_indices),
        n_radiative_lines_total=len(lines),
        n_radiative_lines_used=len(rad_lines),
        n_collision_records_total=len(collisions),
        n_collision_eval_rows_total=len(collision_eval),
        n_collision_eval_rows_used=len(coll_rows_T),
        n_graph_components=len(comps),
        n_graph_edges=len(edges),
        matrix_size=int(Rmat.shape[0]) if Rmat is not None else 0,
        matrix_nnz=int(np.count_nonzero(Rmat)) if Rmat is not None else 0,
        solve_status=str(solve_info.get("solution_status", "unknown")),
        solver=str(solve_info.get("solver", "")),
        solver_warning=str(solve_info.get("solver_warning", "")),
    )
    block_summary = asdict(block_diag)
    block_summary["prune_null_rate_levels"] = prune_info
    block_summary["triplet"] = _normalise_triplet(line_rows)
    block_summary["adjacent_coupling_mode"] = adjacent_coupling_mode
    block_summary["type57_energy_convention"] = type57_energy_convention
    block_summary["adjacent_parent_stage"] = adjacent_parent_stage
    block_summary["n_adjacent_coupling_rows"] = len(coupling_rows)
    block_summary["n_adjacent_coupling_assembled"] = sum(1 for r in coupling_rows if r.get("assembled"))
    block_summary["adjacent_source_sum_s^-1"] = float(np.sum(source_vector)) if len(source_vector) else 0.0
    block_summary["adjacent_sink_sum_s^-1"] = float(np.sum(sink_rates)) if len(sink_rates) else 0.0
    block_summary["extra_source_label"] = extra_source_label
    block_summary["extra_source_sum_s^-1"] = float(sum(float(r.get("extra_source_rate_s^-1") or 0.0) for r in extra_source_rows if r.get("extra_source_applied"))) if extra_source_rows else 0.0
    if extra_source_rows:
        for r in extra_source_rows:
            r["coupling_role"] = "diagnostic_extra_source_vector"
            r["data_type"] = 74 if "type74" in str(extra_source_label) else "extra"
            r["assembled"] = bool(r.get("extra_source_applied"))
            r["assembly_status"] = "assembled_diagnostic_extra_source" if r.get("extra_source_applied") else "not_applied"
            coupling_rows.append(r)
    return block_summary, pop_rows, line_rows, transition_log, make_helike_triplet_diagnostics(line_rows), coupling_rows


def catalog_adjacent_coupling_candidates(
    db: ATDB,
    *,
    z: int,
    lower_ion_stage: int,
    upper_ion_stage: int,
    use_cache: bool = True,
    cache_path: Optional[str] = None,
) -> CouplingCandidateSummary:
    """Catalogue ATDB records likely involved in adjacent-ion coupling.

    XSTAR's element-wide solver couples adjacent ions through many record types.
    This first Python reference version does not evaluate those rates yet; it
    records how many candidate records exist so the next implementation step is
    explicit and reproducible.
    """
    rows: List[dict] = []
    for stage in (lower_ion_stage, upper_ion_stage):
        records = _select_records(db, z, stage, use_cache=use_cache, cache_path=cache_path)
        for rec in records:
            if rec.rate_type in BOUND_FREE_RATE_TYPES or rec.data_type in BOUND_FREE_DATA_TYPES:
                rows.append({"data_type": rec.data_type, "rate_type": rec.rate_type, "ion_stage": stage, "record": rec.recno})
    return CouplingCandidateSummary(
        element=Z_TO_SYMBOL.get(z, str(z)),
        element_z=z,
        lower_ion_stage=lower_ion_stage,
        upper_ion_stage=upper_ion_stage,
        n_candidate_records=len(rows),
        data_type_counts=_counts(rows, "data_type"),
        rate_type_counts=_counts(rows, "rate_type"),
    )


def solve_element_reference(
    fitsfile: str | Path | None,
    *,
    element: str | int,
    he_like_stage: int,
    temperature: float,
    electron_density: float,
    adjacent_stages: Optional[Sequence[int]] = None,
    wavelength_min: Optional[float] = None,
    wavelength_max: Optional[float] = None,
    max_level: Optional[int] = None,
    component_mode: str = "all",
    prune_null_rate_levels: bool = True,
    linear_solver: str = "svd",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    index_cache: bool = True,
    index_cache_path: Optional[str] = None,
    adjacent_coupling_mode: str = "recombination-source",
    adjacent_coupling_source_mode: str = "record-destination",
    adjacent_coupling_selected_levels: Optional[Sequence[int]] = None,
    include_charge_exchange: bool = False,
    type57_energy_convention: str = "compare",
    triplet_source_mode: str = "none",
    triplet_source_scale: object = 1.0,
    type99_proxy_scale: object = "1",
    type53_flat_proxy_scale: object = 1.0,
    radiation_field_mode: str = "none",
    full_global_linear_solver: str = "xstar-lucy",
    full_global_rank_deficient_action: str = "svd",
    full_global_negative_population_action: str = "keep",
    full_global_prune_null_rate_levels: bool = True,
) -> dict:
    z = choose_z(str(element)) if not isinstance(element, int) else int(element)
    if z is None:
        raise ValueError(f"Could not parse element {element!r}")
    stages = list(adjacent_stages) if adjacent_stages else [he_like_stage + 1, he_like_stage]
    stages = sorted({int(s) for s in stages if int(s) > 0}, reverse=True)
    with ATDB(fitsfile, load_reals=False, prompt_for_data=False) as db:
        global_index_rows = build_element_global_index(
            db,
            z=z,
            stages=stages,
            he_like_stage=he_like_stage,
            max_level=max_level,
            use_cache=index_cache,
            cache_path=index_cache_path,
        )
        ion_blocks: List[dict] = []
        populations: List[dict] = []
        line_rows: List[dict] = []
        transitions: List[dict] = []
        global_bound_bound_matrix_terms: List[dict] = []
        triplet_rows: List[dict] = []
        assembled_coupling_terms: List[dict] = []
        for stage in stages:
            parent_stage = stage + 1 if (stage + 1) in stages else None
            block, pops, lines, trans, trips, cterms = build_ion_rate_block(
                db,
                z=z,
                ion_stage=stage,
                temperature=temperature,
                electron_density=electron_density,
                wavelength_min=wavelength_min if stage == he_like_stage else None,
                wavelength_max=wavelength_max if stage == he_like_stage else None,
                max_level=max_level,
                component_mode=component_mode,
                prune_null_rate_levels=prune_null_rate_levels,
                linear_solver=linear_solver,
                rank_deficient_action=rank_deficient_action,
                negative_population_action=negative_population_action,
                use_cache=index_cache,
                cache_path=index_cache_path,
                adjacent_parent_stage=parent_stage,
                adjacent_coupling_mode=adjacent_coupling_mode if parent_stage is not None else "none",
                adjacent_coupling_source_mode=adjacent_coupling_source_mode,
                adjacent_coupling_selected_levels=adjacent_coupling_selected_levels,
                include_charge_exchange=include_charge_exchange,
                type57_energy_convention=type57_energy_convention,
            )
            ion_blocks.append(block)
            populations.extend(pops)
            line_rows.extend(lines)
            transitions.extend(trans)
            assembled_coupling_terms.extend(cterms)
            for tr in trips:
                tr["diagnostic_ion_stage"] = stage
                triplet_rows.append(tr)
        coupling = []
        superlevel_cascade_audit_rows: List[dict] = []
        superlevel_branching_audit_rows: List[dict] = []
        superlevel_source_audit_rows: List[dict] = []
        type74_linkage_audit_rows: List[dict] = []
        type74_triplet_source_audit_rows: List[dict] = []
        triplet_source_injection_comparison_rows: List[dict] = []
        triplet_source_scale_scan_rows: List[dict] = []
        global_bound_bound_solve_comparison_rows: List[dict] = []
        global_bound_bound_type71_solve_comparison_rows: List[dict] = []
        global_bound_bound_type71_type99_proxy_solve_comparison_rows: List[dict] = []
        global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows: List[dict] = []
        global_superlevel_cascade_matrix_terms: List[dict] = []
        if he_like_stage + 1 in stages:
            coupling.append(asdict(catalog_adjacent_coupling_candidates(
                db,
                z=z,
                lower_ion_stage=he_like_stage,
                upper_ion_stage=he_like_stage + 1,
                use_cache=index_cache,
                cache_path=index_cache_path,
            )))
            target_level_rows = [r for r in populations if maybe_int(r.get("ion_stage")) == he_like_stage]
            target_level_indices = [int(r.get("level_index")) for r in target_level_rows if maybe_int(r.get("level_index")) is not None]
            superlevel_cascade_audit_rows = build_superlevel_cascade_audit(
                db,
                z=z,
                target_ion_stage=he_like_stage,
                parent_ion_stage=he_like_stage + 1,
                level_rows=target_level_rows,
                level_indices=target_level_indices,
                use_cache=index_cache,
                cache_path=index_cache_path,
            )
            superlevel_branching_audit_rows = build_superlevel_branching_audit(superlevel_cascade_audit_rows)
            superlevel_source_audit_rows = build_superlevel_source_audit(superlevel_cascade_audit_rows, superlevel_branching_audit_rows)
            type74_linkage_audit_rows = build_type74_linkage_audit(superlevel_cascade_audit_rows, superlevel_branching_audit_rows)
            type74_triplet_source_audit_rows = build_type74_triplet_source_audit(
                type74_linkage_audit_rows,
                temperature=temperature,
                electron_density=electron_density,
                level_rows=target_level_rows,
            )
            if str(triplet_source_mode or "none").lower() == "type74-direct-diagnostic":
                source_by_level = _type74_direct_triplet_source_by_level(type74_triplet_source_audit_rows)
                if source_by_level:
                    baseline_triplet = _normalise_triplet([r for r in line_rows if maybe_int(r.get("ion_stage")) == he_like_stage])
                    scale_values = _parse_triplet_source_scales(triplet_source_scale)
                    scan_triplets: List[tuple[float, dict, dict]] = []
                    first_block = None
                    first_lines = None
                    first_scale = scale_values[0]
                    for scale in scale_values:
                        scaled_source_by_level = _scale_source_by_level(source_by_level, scale)
                        _block2, _pops2, _lines2, _trans2, _trips2, _cterms2 = build_ion_rate_block(
                            db,
                            z=z,
                            ion_stage=he_like_stage,
                            temperature=temperature,
                            electron_density=electron_density,
                            wavelength_min=wavelength_min,
                            wavelength_max=wavelength_max,
                            max_level=max_level,
                            component_mode=component_mode,
                            prune_null_rate_levels=prune_null_rate_levels,
                            linear_solver=linear_solver,
                            rank_deficient_action=rank_deficient_action,
                            negative_population_action=negative_population_action,
                            use_cache=index_cache,
                            cache_path=index_cache_path,
                            adjacent_parent_stage=he_like_stage + 1 if (he_like_stage + 1) in stages else None,
                            adjacent_coupling_mode=adjacent_coupling_mode,
                            adjacent_coupling_source_mode=adjacent_coupling_source_mode,
                            adjacent_coupling_selected_levels=adjacent_coupling_selected_levels,
                            include_charge_exchange=include_charge_exchange,
                            type57_energy_convention=type57_energy_convention,
                            extra_source_by_level=scaled_source_by_level,
                            extra_source_label=f"type74-direct-diagnostic-scale-{scale:g}",
                        )
                        injected_triplet = _normalise_triplet(_lines2)
                        scan_triplets.append((float(scale), injected_triplet, _block2))
                        if first_block is None:
                            first_block = _block2
                            first_lines = _lines2
                            first_scale = float(scale)
                    triplet_source_scale_scan_rows = build_triplet_source_scale_scan(
                        baseline_triplet=baseline_triplet,
                        scan_triplets=scan_triplets,
                        source_by_level=source_by_level,
                        type74_triplet_source_rows=type74_triplet_source_audit_rows,
                        target_ion_stage=he_like_stage,
                        mode=str(triplet_source_mode),
                    )
                    if first_lines is not None and first_block is not None:
                        injected_triplet = _normalise_triplet(first_lines)
                        triplet_source_injection_comparison_rows = build_triplet_source_injection_comparison(
                            baseline_triplet=baseline_triplet,
                            injected_triplet=injected_triplet,
                            type74_triplet_source_rows=type74_triplet_source_audit_rows,
                            target_ion_stage=he_like_stage,
                            mode=str(triplet_source_mode),
                        )
                        # Keep the injected run separate from the baseline outputs.
                        for r in triplet_source_injection_comparison_rows:
                            r["triplet_source_scale"] = first_scale
                            r["scaled_total_injected_source_rate_s^-1"] = (maybe_float(r.get("total_injected_source_rate_s^-1")) or 0.0) * first_scale
                            r["injected_matrix_size"] = first_block.get("matrix_size")
                            r["injected_solve_status"] = first_block.get("solve_status")
                            r["injected_extra_source_sum_s^-1"] = first_block.get("extra_source_sum_s^-1")
    global_bound_bound_matrix_terms = build_global_bound_bound_matrix_terms(transitions, global_index_rows)
    global_superlevel_cascade_matrix_terms = build_global_superlevel_cascade_matrix_terms(
        superlevel_cascade_audit_rows,
        global_index_rows,
    )
    global_superlevel_source_matrix_terms = build_global_superlevel_source_matrix_terms(
        superlevel_source_audit_rows,
        global_index_rows,
    )
    global_bound_bound_solve_comparison_rows = build_global_bound_bound_solve_comparison(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        populations=populations,
        line_rows=line_rows,
        coupling_rows=assembled_coupling_terms,
        ion_stage=he_like_stage,
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
    )
    global_bound_bound_type71_solve_comparison_rows = build_global_bound_bound_type71_solve_comparison(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        populations=populations,
        line_rows=line_rows,
        coupling_rows=assembled_coupling_terms,
        ion_stage=he_like_stage,
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
    )
    global_bound_bound_type71_type99_proxy_solve_comparison_rows = build_global_bound_bound_type71_type99_proxy_solve_comparison(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        populations=populations,
        line_rows=line_rows,
        coupling_rows=assembled_coupling_terms,
        ion_stage=he_like_stage,
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
        type99_proxy_scale=1.0,
    )
    type99_proxy_scale_scan_rows = build_global_bound_bound_type71_type99_proxy_scale_scan(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        populations=populations,
        line_rows=line_rows,
        coupling_rows=assembled_coupling_terms,
        ion_stage=he_like_stage,
        type99_proxy_scale=type99_proxy_scale,
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
    )
    radiation_context_rows = build_radiation_context_rows(
        radiation_field_mode=radiation_field_mode,
        temperature=temperature,
        electron_density=electron_density,
        element=Z_TO_SYMBOL.get(z, str(z)),
        element_z=z,
        stages=stages,
        he_like_stage=he_like_stage,
    )
    type53_rate_audit_rows = build_type53_rate_audit_rows(
        adjacent_audit_rows=assembled_coupling_terms,
        global_index_rows=global_index_rows,
        radiation_context_rows=radiation_context_rows,
        he_like_stage=he_like_stage,
    )
    type53_flat_proxy_rate_audit_rows = build_type53_flat_proxy_rate_audit_rows(
        type53_rate_audit_rows=type53_rate_audit_rows,
        radiation_context_rows=radiation_context_rows,
        type53_flat_proxy_scale=type53_flat_proxy_scale,
    )
    global_type53_flat_proxy_matrix_terms = build_global_type53_flat_proxy_matrix_terms(
        type53_flat_proxy_rate_audit_rows
    )
    full_global_matrix_terms = build_full_global_matrix_terms(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
        coupling_rows=assembled_coupling_terms,
        he_like_stage=he_like_stage,
    )
    global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows = build_global_bound_bound_type71_type99_type53_proxy_solve_comparison(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
        populations=populations,
        line_rows=line_rows,
        coupling_rows=assembled_coupling_terms,
        ion_stage=he_like_stage,
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
        type99_proxy_scale=1.0,
    )
    full_global_normalized_solve_comparison_rows = build_full_global_normalized_solve_comparison(
        global_index_rows=global_index_rows,
        full_global_matrix_terms=full_global_matrix_terms,
        line_rows=line_rows,
        he_like_stage=he_like_stage,
        linear_solver=full_global_linear_solver,
        rank_deficient_action=full_global_rank_deficient_action,
        negative_population_action=full_global_negative_population_action,
        prune_null_rate_levels=full_global_prune_null_rate_levels,
    )
    selected_lines = [r for r in line_rows if maybe_int(r.get("ion_stage")) == he_like_stage]
    return {
        "summary": {
            "mode": "pure_python_reference_element_solver_scaffold",
            "element": Z_TO_SYMBOL.get(z, str(z)),
            "element_z": z,
            "he_like_stage": he_like_stage,
            "temperature_K": temperature,
            "electron_density_cm^-3": electron_density,
            "stages": stages,
            "n_ion_blocks": len(ion_blocks),
            "n_population_rows": len(populations),
            "n_line_rows": len(line_rows),
            "n_transition_rows": len(transitions),
            "n_global_index_rows": len(global_index_rows),
            "global_index_summary": _global_index_summary(global_index_rows),
            "n_global_bound_bound_matrix_term_rows": len(global_bound_bound_matrix_terms),
            "global_bound_bound_matrix_terms_summary": _global_bound_bound_matrix_terms_summary(global_bound_bound_matrix_terms),
            "n_global_bound_bound_solve_comparison_rows": len(global_bound_bound_solve_comparison_rows),
            "global_bound_bound_solve_comparison_summary": _global_bound_bound_solve_comparison_summary(global_bound_bound_solve_comparison_rows),
            "n_global_bound_bound_type71_solve_comparison_rows": len(global_bound_bound_type71_solve_comparison_rows),
            "global_bound_bound_type71_solve_comparison_summary": _global_bound_bound_type71_solve_comparison_summary(global_bound_bound_type71_solve_comparison_rows),
            "n_global_bound_bound_type71_type99_proxy_solve_comparison_rows": len(global_bound_bound_type71_type99_proxy_solve_comparison_rows),
            "global_bound_bound_type71_type99_proxy_solve_comparison_summary": _global_bound_bound_type71_type99_proxy_solve_comparison_summary(global_bound_bound_type71_type99_proxy_solve_comparison_rows),
            "n_type99_proxy_scale_scan_rows": len(type99_proxy_scale_scan_rows),
            "type99_proxy_scale_scan_summary": _type99_proxy_scale_scan_summary(type99_proxy_scale_scan_rows),
            "radiation_field_mode": radiation_field_mode,
            "n_radiation_context_rows": len(radiation_context_rows),
            "n_type53_rate_audit_rows": len(type53_rate_audit_rows),
            "type53_rate_audit_summary": _type53_rate_audit_summary(type53_rate_audit_rows),
            "n_type53_flat_proxy_rate_audit_rows": len(type53_flat_proxy_rate_audit_rows),
            "type53_flat_proxy_rate_audit_summary": _type53_flat_proxy_rate_audit_summary(type53_flat_proxy_rate_audit_rows),
            "n_global_type53_flat_proxy_matrix_term_rows": len(global_type53_flat_proxy_matrix_terms),
            "global_type53_flat_proxy_matrix_terms_summary": _global_type53_flat_proxy_matrix_terms_summary(global_type53_flat_proxy_matrix_terms),
            "n_full_global_matrix_term_rows": len(full_global_matrix_terms),
            "full_global_matrix_terms_summary": _full_global_matrix_terms_summary(full_global_matrix_terms),
            "n_full_global_normalized_solve_comparison_rows": len(full_global_normalized_solve_comparison_rows),
            "full_global_linear_solver": full_global_linear_solver,
            "full_global_rank_deficient_action": full_global_rank_deficient_action,
            "full_global_negative_population_action": full_global_negative_population_action,
            "full_global_prune_null_rate_levels": bool(full_global_prune_null_rate_levels),
            "full_global_normalized_solve_comparison_summary": _full_global_normalized_solve_comparison_summary(full_global_normalized_solve_comparison_rows),
            "n_global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows": len(global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows),
            "global_bound_bound_type71_type99_type53_proxy_solve_comparison_summary": _global_bound_bound_type71_type99_type53_proxy_solve_comparison_summary(global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows),
            "n_global_superlevel_cascade_matrix_term_rows": len(global_superlevel_cascade_matrix_terms),
            "global_superlevel_cascade_matrix_terms_summary": _global_superlevel_cascade_matrix_terms_summary(global_superlevel_cascade_matrix_terms),
            "n_global_superlevel_source_matrix_term_rows": len(global_superlevel_source_matrix_terms),
            "global_superlevel_source_matrix_terms_summary": _global_superlevel_source_matrix_terms_summary(global_superlevel_source_matrix_terms),
            "adjacent_coupling_status": adjacent_coupling_mode,
            "type57_energy_convention": type57_energy_convention,
            "triplet_source_mode": triplet_source_mode,
            "n_adjacent_coupling_terms": len(assembled_coupling_terms),
            "n_adjacent_coupling_assembled": sum(1 for r in assembled_coupling_terms if r.get("assembled")),
            "he_like_triplet": _normalise_triplet(selected_lines),
        },
        "ion_blocks": ion_blocks,
        "global_index": global_index_rows,
        "coupling_candidates": coupling,
        "populations": populations,
        "line_rows": line_rows,
        "transition_rows": transitions,
        "global_bound_bound_matrix_terms": global_bound_bound_matrix_terms,
        "global_superlevel_cascade_matrix_terms": global_superlevel_cascade_matrix_terms,
        "global_superlevel_source_matrix_terms": global_superlevel_source_matrix_terms,
        "global_bound_bound_solve_comparison": global_bound_bound_solve_comparison_rows,
        "global_bound_bound_type71_solve_comparison": global_bound_bound_type71_solve_comparison_rows,
        "global_bound_bound_type71_type99_proxy_solve_comparison": global_bound_bound_type71_type99_proxy_solve_comparison_rows,
        "global_bound_bound_type71_type99_type53_proxy_solve_comparison": global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows,
        "type99_proxy_scale_scan": type99_proxy_scale_scan_rows,
        "radiation_context": radiation_context_rows,
        "type53_rate_audit": type53_rate_audit_rows,
        "type53_flat_proxy_rate_audit": type53_flat_proxy_rate_audit_rows,
        "global_type53_flat_proxy_matrix_terms": global_type53_flat_proxy_matrix_terms,
        "full_global_matrix_terms": full_global_matrix_terms,
        "full_global_normalized_solve_comparison": full_global_normalized_solve_comparison_rows,
        "triplet_rows": triplet_rows,
        "adjacent_coupling_terms": assembled_coupling_terms,
        "superlevel_cascade_audit": superlevel_cascade_audit_rows,
        "superlevel_branching_audit": superlevel_branching_audit_rows,
        "superlevel_source_audit": superlevel_source_audit_rows,
        "type74_linkage_audit": type74_linkage_audit_rows,
        "type74_triplet_source_audit": type74_triplet_source_audit_rows,
        "triplet_source_injection_comparison": triplet_source_injection_comparison_rows,
        "triplet_source_scale_scan": triplet_source_scale_scan_rows,
    }


def _superlevel_cascade_audit_summary(rows: Sequence[dict]) -> dict:
    """Summarise diagnostic superlevel/cascade audit rows."""
    def _counts_value(col: str) -> dict:
        vals = {}
        for r in rows:
            key = r.get(col)
            key = "" if key is None else str(key)
            vals[key] = vals.get(key, 0) + 1
        return vals
    def _n_true(col: str) -> int:
        return sum(1 for r in rows if str(r.get(col)).lower() == "true" or r.get(col) is True)
    return {
        "n_superlevel_cascade_rows": len(rows),
        "data_type_counts": _counts_value("data_type"),
        "route_kind_counts": _counts_value("superlevel_route_kind"),
        "stage_relation_counts": _counts_value("stage_relation_to_target_parent"),
        "cascade_feed_component_counts": _counts_value("cascade_feed_component"),
        "feeds_any_triplet_component_rows": _n_true("feeds_any_triplet_component"),
        "feeds_forbidden_upper_rows": _n_true("feeds_forbidden_upper"),
        "feeds_intercombination_upper_rows": _n_true("feeds_intercombination_upper"),
        "feeds_resonance_upper_rows": _n_true("feeds_resonance_upper"),
        "requires_superlevel_population_rows": _n_true("requires_superlevel_population"),
        "requires_parent_continuum_population_rows": _n_true("requires_parent_continuum_population"),
        "requires_radiation_grid_rows": _n_true("requires_radiation_grid"),
        "matrix_safe_to_assemble_counts": _counts_value("matrix_safe_to_assemble"),
        "provenance": {
            "type70": "Bautista & Kallman 2001 appendix: coefficients for recombination and photoionization cross sections of superlevels.",
            "type71": "Bautista & Kallman 2001 appendix: radiative transition rates from superlevels to spectroscopic levels.",
            "type74": "Bautista & Kallman 2001 appendix: delta functions added to photoionization cross sections to match DR recombination rates.",
            "type77": "Bautista & Kallman 2001 appendix: collisional transition rates from superlevels to spectroscopic levels.",
            "type99": "XSTAR source-code-guided audit: superlevel photoionization/recombination context requires linked phint53pl records.",
            "assembly": "No superlevel/cascade rate is assembled into the element matrix in v0.3.23.",
        },
    }



def _superlevel_branching_audit_summary(rows: Sequence[dict]) -> dict:
    """Summarise v0.3.24 type-71/type-77 superlevel branching rows."""
    def _counts_value(col: str) -> dict:
        vals = {}
        for r in rows:
            key = r.get(col)
            key = "" if key is None else str(key)
            vals[key] = vals.get(key, 0) + 1
        return vals
    def _sum_float(col: str) -> float:
        total = 0.0
        for r in rows:
            val = maybe_float(r.get(col))
            if val is not None and math.isfinite(float(val)):
                total += float(val)
        return total
    def _max_row(dt: int, col: str):
        candidates = [r for r in rows if maybe_int(r.get("data_type")) == dt and maybe_float(r.get(col)) is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda r: maybe_float(r.get(col)) or -1.0)
    type71_max_trip = _max_row(71, "B_triplet_total")
    type77_max_trip = _max_row(77, "B_triplet_total")
    return {
        "n_superlevel_branching_rows": len(rows),
        "data_type_counts": _counts_value("data_type"),
        "weight_basis_counts": _counts_value("branching_weight_basis"),
        "dominant_component_counts": _counts_value("cascade_dominant_triplet_component"),
        "forbidden_favored_counts": _counts_value("cascade_naturally_favors_forbidden"),
        "total_type71_triplet_weight": _sum_float("weight_to_triplet_total"),
        "total_type71_forbidden_weight": sum(float(maybe_float(r.get("weight_to_forbidden")) or 0.0) for r in rows if maybe_int(r.get("data_type")) == 71),
        "total_type71_intercombination_weight": sum(float(maybe_float(r.get("weight_to_intercombination")) or 0.0) for r in rows if maybe_int(r.get("data_type")) == 71),
        "total_type71_resonance_weight": sum(float(maybe_float(r.get("weight_to_resonance")) or 0.0) for r in rows if maybe_int(r.get("data_type")) == 71),
        "max_type71_triplet_branch_superlevel": None if type71_max_trip is None else type71_max_trip.get("superlevel_level"),
        "max_type71_triplet_branch_fraction": None if type71_max_trip is None else type71_max_trip.get("B_triplet_total"),
        "max_type77_triplet_branch_superlevel": None if type77_max_trip is None else type77_max_trip.get("superlevel_level"),
        "max_type77_triplet_branch_fraction": None if type77_max_trip is None else type77_max_trip.get("B_triplet_total"),
        "matrix_safe_to_assemble_counts": _counts_value("matrix_safe_to_assemble"),
        "provenance": {
            "type71": "Branching weights are summed from type-71 radiative superlevel-to-spectroscopic A-value-like coefficients.",
            "type77": "Type-77 branching is count-proxy only in v0.3.24 because the collisional superlevel rate evaluator is not yet ported.",
            "assembly": "No superlevel branching or cascade rate is assembled into the element matrix in v0.3.24.",
        },
    }

def _type57_audit_summary(rows: Sequence[dict]) -> dict:
    """Summarise type-57 diagnostic audit/provenance rows."""
    t57 = [r for r in rows if maybe_int(r.get("data_type")) == 57]
    def _n_nonzero(col: str) -> int:
        return sum(1 for r in t57 if (maybe_float(r.get(col)) or 0.0) > 0.0)
    def _counts_value(col: str) -> dict:
        vals = {}
        for r in t57:
            key = r.get(col)
            key = "" if key is None else str(key)
            vals[key] = vals.get(key, 0) + 1
        return vals
    return {
        "n_type57_rows": len(t57),
        "selected_energy_convention_counts": _counts_value("type57_selected_energy_convention"),
        "primary_python_eval_status_counts": _counts_value("python_eval_status"),
        "ucalc_eth_eval_status_counts": _counts_value("type57_ucalc_eth_eval_status"),
        "abs_rlev4_eval_status_counts": _counts_value("type57_abs_rlev4_eval_status"),
        "threshold_only_eval_status_counts": _counts_value("type57_threshold_only_eval_status"),
        "nonzero_ucalc_eth_forward_rates": _n_nonzero("type57_ucalc_eth_rate_forward_s^-1"),
        "nonzero_abs_rlev4_forward_rates": _n_nonzero("type57_abs_rlev4_rate_forward_s^-1"),
        "nonzero_threshold_only_forward_rates": _n_nonzero("type57_threshold_only_rate_forward_s^-1"),
        "best_nonzero_convention_counts": _counts_value("type57_best_nonzero_convention"),
        "energy_convention_conflict_counts": _counts_value("type57_energy_convention_conflict"),
        "matrix_role_classification_counts": _counts_value("type57_matrix_role_classification"),
        "matrix_destination_in_current_level_set_counts": _counts_value("type57_matrix_destination_in_current_level_set"),
        "forward_sink_from_lower_ion_counts": _counts_value("type57_forward_rate_would_be_sink_from_lower_ion"),
        "inverse_tbr_source_candidate_counts": _counts_value("type57_inverse_three_body_recombination_source_candidate"),
        "matrix_safe_to_assemble_counts": _counts_value("type57_matrix_safe_to_assemble"),
        "provenance": {
            "ucalc": "xstarlib/src/ucalc.f90 type 57 sets e1=rlev(1,idest1), eth=max(0,rlev(1,nlevp)-rlev(1,idest1)), ep=eth before calling calt57.",
            "calt57": "xstarlib/src/calt57.f90 documents e as level energy and ep as the fourth real of the type-6 level record; its internal gate requires ep >= e.",
            "irc_path": "The v0.3.21 diagnostic evaluator ports the calt57 -> irc -> szirc/eint/expint/expo numerical path and remains audit-only.",
            "assembly": "No type-57 rate is assembled into the element matrix in v0.3.21.",
        },
    }


def _type59_recombination_audit_summary(rows: Sequence[dict]) -> dict:
    """Summarise type-59 and related recombination-to-level audit rows."""
    t59 = [r for r in rows if maybe_int(r.get("data_type")) == 59]
    related = [r for r in rows if str(r.get("recomb_audit_family") or "")]
    def _counts_value(seq: Sequence[dict], col: str) -> dict:
        vals = {}
        for r in seq:
            key = r.get(col)
            key = "" if key is None else str(key)
            vals[key] = vals.get(key, 0) + 1
        return vals
    def _n_true(seq: Sequence[dict], col: str) -> int:
        return sum(1 for r in seq if str(r.get(col)).lower() == "true" or r.get(col) is True)
    return {
        "n_type59_rows": len(t59),
        "n_related_recombination_audit_rows": len(related),
        "related_recombination_family_counts": _counts_value(related, "recomb_audit_family"),
        "related_destination_level_kind_counts": _counts_value(related, "recomb_destination_level_kind"),
        "related_triplet_upper_candidate_rows": _n_true(related, "recomb_would_feed_helike_triplet_upper_candidate"),
        "type59_python_eval_status_counts": _counts_value(t59, "python_eval_status"),
        "type59_suppressed_counts": _counts_value(t59, "type59_ucalc_recombination_outputs_suppressed"),
        "type59_suppression_reason_counts": _counts_value(t59, "type59_suppression_reason"),
        "type59_excited_destination_rows": _n_true(t59, "type59_would_recombine_to_excited_level"),
        "type59_triplet_upper_after_gate_rows": _n_true(t59, "type59_can_feed_helike_triplet_upper_after_visible_gate"),
        "type59_matrix_safe_to_assemble_counts": _counts_value(t59, "type59_matrix_safe_to_assemble"),
        "provenance": {
            "ucalc_type59": "xstarlib/src/ucalc.f90 type 59 constructs bound-free cross sections, calls phintfo, and then zeros ans2/ans4/ans6 when nrdesc==1 or idest1>1.",
            "gate": "The visible gate suppresses recombination into excited levels for type 59, so excited-level triplet feeding cannot be inferred directly from these rows without reproducing the full XSTAR context.",
            "assembly": "No type-59 or related bound-free inverse recombination rate is assembled into the element matrix in v0.3.22.",
        },
    }



def _superlevel_source_audit_summary(rows: Sequence[dict]) -> dict:
    """Summarise v0.3.25 type-70/74/99 source × branch proxy rows."""
    def _counts_value(col: str) -> dict:
        vals = {}
        for r in rows:
            key = r.get(col)
            key = "" if key is None else str(key)
            vals[key] = vals.get(key, 0) + 1
        return vals
    def _sum_float(col: str) -> float:
        total = 0.0
        for r in rows:
            val = maybe_float(r.get(col))
            if val is not None and math.isfinite(float(val)):
                total += float(val)
        return total
    def _max_row(col: str):
        candidates = [r for r in rows if maybe_float(r.get(col)) is not None]
        if not candidates:
            return None
        return max(candidates, key=lambda r: maybe_float(r.get(col)) or -1.0)
    max_trip = _max_row("source_weighted_preferred_feed_triplet_proxy")
    return {
        "n_superlevel_source_audit_rows": len(rows),
        "rows_with_type70_candidates": sum(1 for r in rows if (maybe_float(r.get("n_type70_source_candidates")) or 0.0) > 0.0),
        "rows_with_type74_candidates": sum(1 for r in rows if (maybe_float(r.get("n_type74_dr_delta_source_candidates")) or 0.0) > 0.0),
        "rows_with_type99_candidates": sum(1 for r in rows if (maybe_float(r.get("n_type99_superlevel_source_candidates")) or 0.0) > 0.0),
        "total_type70_candidates": int(_sum_float("n_type70_source_candidates")),
        "total_type74_candidates": int(_sum_float("n_type74_dr_delta_source_candidates")),
        "total_type99_candidates": int(_sum_float("n_type99_superlevel_source_candidates")),
        "branch_basis_counts": _counts_value("preferred_branch_basis"),
        "dominant_component_counts": _counts_value("source_weighted_proxy_dominant_component"),
        "rows_with_forbidden_branch": _counts_value("source_has_branch_to_forbidden"),
        "rows_with_intercombination_branch": _counts_value("source_has_branch_to_intercombination"),
        "rows_with_resonance_branch": _counts_value("source_has_branch_to_resonance"),
        "total_source_proxy": _sum_float("source_proxy_total"),
        "total_preferred_feed_f_proxy": _sum_float("source_weighted_preferred_feed_f_proxy"),
        "total_preferred_feed_i_proxy": _sum_float("source_weighted_preferred_feed_i_proxy"),
        "total_preferred_feed_r_proxy": _sum_float("source_weighted_preferred_feed_r_proxy"),
        "total_preferred_feed_triplet_proxy": _sum_float("source_weighted_preferred_feed_triplet_proxy"),
        "max_preferred_feed_triplet_superlevel": None if max_trip is None else max_trip.get("superlevel_level"),
        "max_preferred_feed_triplet_proxy": None if max_trip is None else max_trip.get("source_weighted_preferred_feed_triplet_proxy"),
        "matrix_safe_to_assemble_counts": _counts_value("matrix_safe_to_assemble"),
        "provenance": {
            "source_proxy": "v0.3.25 uses one nonphysical count unit per type-70/74/99 source candidate and reports source_proxy * B_f/i/r only as a diagnostic feed proxy.",
            "branch_linkage": "Branch fractions are imported from the v0.3.24 type-71/type-77 superlevel branching audit for the same record ion stage and superlevel index.",
            "assembly": "No type-70/74/99 source or source-weighted superlevel cascade term is assembled into the element matrix in v0.3.25.",
        },
    }

def _type74_linkage_audit_summary(rows: Sequence[dict]) -> dict:
    """Summarise the v0.3.26 deep type-74 linkage audit."""
    def _counts_value(col: str) -> dict:
        vals = {}
        for r in rows:
            key = r.get(col)
            key = "" if key is None else str(key)
            vals[key] = vals.get(key, 0) + 1
        return vals
    def _n_true(col: str) -> int:
        return sum(1 for r in rows if _truthy(r.get(col)))
    return {
        "n_type74_linkage_rows": len(rows),
        "source_level_kind_counts": _counts_value("source_level_kind"),
        "parent_or_final_level_kind_counts": _counts_value("parent_or_final_level_kind"),
        "branch_link_status_counts": _counts_value("branch_link_status"),
        "possible_feed_route_counts": _counts_value("possible_feed_route"),
        "direct_forbidden_source_candidates": sum(1 for r in rows if str(r.get("source_level_triplet_component") or "") == "f"),
        "direct_intercombination_source_candidates": sum(1 for r in rows if str(r.get("source_level_triplet_component") or "") == "i"),
        "direct_resonance_source_candidates": sum(1 for r in rows if str(r.get("source_level_triplet_component") or "") == "r"),
        "can_feed_forbidden_candidates": _n_true("can_feed_forbidden_candidate"),
        "can_feed_intercombination_candidates": _n_true("can_feed_intercombination_candidate"),
        "can_feed_resonance_candidates": _n_true("can_feed_resonance_candidate"),
        "can_feed_any_triplet_candidates": _n_true("can_feed_any_triplet_candidate"),
        "valid_type71_superlevel_branch_links": _n_true("valid_type71_superlevel_branch_link"),
        "valid_type77_superlevel_branch_links": _n_true("valid_type77_superlevel_branch_link"),
        "same_numeric_source_type71_branch_rows": _n_true("same_numeric_source_level_has_type71_branch"),
        "same_numeric_source_type77_branch_rows": _n_true("same_numeric_source_level_has_type77_branch"),
        "matrix_safe_to_assemble_counts": _counts_value("matrix_safe_to_assemble"),
        "provenance": {
            "type74_layout": "Bautista & Kallman 2001 appendix: i5=level+, i6=ion+, i7=level, i8=nion for DR delta functions added to photoionization cross sections.",
            "interpretation": "v0.3.26 reports both the parent/final level side and the recombined/source level side; it does not assemble type-74 records.",
        },
    }


def _type74_triplet_source_audit_summary(rows: Sequence[dict]) -> dict:
    """Summarise the v0.3.27 type-74 direct triplet source diagnostic."""
    def _counts_value(col: str) -> dict:
        vals = {}
        for r in rows:
            key = r.get(col)
            key = "" if key is None else str(key)
            vals[key] = vals.get(key, 0) + 1
        return vals
    candidates = [r for r in rows if r.get("type74_direct_triplet_candidate") is True]
    agg = next((r for r in rows if str(r.get("record")) == "TOTAL_TYPE74_DIRECT_TRIPLET"), {})
    return {
        "n_type74_triplet_source_rows": len(rows),
        "n_direct_triplet_candidate_rows": len(candidates),
        "triplet_component_counts": _counts_value("triplet_component"),
        "eval_status_counts": _counts_value("type74_eval_status"),
        "total_source_rate_f_s^-1": agg.get("total_source_rate_f_s^-1"),
        "total_source_rate_i_s^-1": agg.get("total_source_rate_i_s^-1"),
        "total_source_rate_r_s^-1": agg.get("total_source_rate_r_s^-1"),
        "total_source_rate_triplet_s^-1": agg.get("total_source_rate_triplet_s^-1"),
        "source_fraction_f": agg.get("source_fraction_f"),
        "source_fraction_i": agg.get("source_fraction_i"),
        "source_fraction_r": agg.get("source_fraction_r"),
        "source_vector_dominant_component": agg.get("source_vector_dominant_component"),
        "xstar_target_name": agg.get("xstar_target_name"),
        "source_vector_l2_distance_to_target": agg.get("source_vector_l2_distance_to_target"),
        "matrix_safe_to_assemble_counts": _counts_value("matrix_safe_to_assemble"),
        "provenance": {
            "calt74": "v0.3.27 ports only the recombination-alpha part of xstarlib/src/calt74.f90 for direct type-74 triplet candidates.",
            "ucalc": "ucalc.f90 type 74 applies alpha *= g(recombined)/g(continuum); v0.3.27 uses g(continuum)=1 placeholder until the global continuum row exists.",
            "assembly": "No type-74 source term is assembled into the matrix in v0.3.27.",
        },
    }


def _triplet_source_injection_comparison_summary(rows: Sequence[dict]) -> dict:
    """Summarise the v0.3.28 diagnostic type-74 triplet source injection."""
    def _row(case: str) -> dict:
        return next((r for r in rows if str(r.get("case")) == case), {})
    base = _row("baseline")
    inj = _row("type74_source_injected")
    target = _row("xstar_target")
    return {
        "n_triplet_source_injection_rows": len(rows),
        "triplet_source_mode": inj.get("triplet_source_mode") or base.get("triplet_source_mode"),
        "total_injected_source_rate_s^-1": inj.get("total_injected_source_rate_s^-1") or base.get("total_injected_source_rate_s^-1"),
        "n_injected_source_levels": inj.get("n_injected_source_levels") or base.get("n_injected_source_levels"),
        "baseline_f_fraction": base.get("f_fraction"),
        "baseline_i_fraction": base.get("i_fraction"),
        "baseline_r_fraction": base.get("r_fraction"),
        "injected_f_fraction": inj.get("f_fraction"),
        "injected_i_fraction": inj.get("i_fraction"),
        "injected_r_fraction": inj.get("r_fraction"),
        "target_f_fraction": target.get("f_fraction") or inj.get("target_f_fraction"),
        "target_i_fraction": target.get("i_fraction") or inj.get("target_i_fraction"),
        "target_r_fraction": target.get("r_fraction") or inj.get("target_r_fraction"),
        "baseline_l2_distance_to_target": base.get("l2_distance_to_target"),
        "injected_l2_distance_to_target": inj.get("l2_distance_to_target"),
        "delta_l2_injected_minus_baseline": None if maybe_float(inj.get("l2_distance_to_target")) is None or maybe_float(base.get("l2_distance_to_target")) is None else float(inj.get("l2_distance_to_target")) - float(base.get("l2_distance_to_target")),
        "provenance": {
            "mode": "v0.3.28 adds --triplet-source-mode type74-direct-diagnostic, which injects evaluated type-74 direct triplet source rates into the existing single-ion source vector for a diagnostic before/after solve.",
            "assembly": "This is not the final element-wide matrix assembly and remains off by default.",
        },
    }


def _triplet_source_scale_scan_summary(rows: Sequence[dict]) -> dict:
    """Summarise the v0.3.29 diagnostic source-scale scan."""
    scale_rows = [r for r in rows if str(r.get("case")) == "type74_source_injected_scaled"]
    best = None
    for r in scale_rows:
        d = maybe_float(r.get("l2_distance_to_target"))
        if d is None:
            continue
        if best is None or float(d) < float(best.get("l2_distance_to_target")):
            best = r
    base = next((r for r in rows if str(r.get("case")) == "baseline"), {})
    return {
        "n_triplet_source_scale_scan_rows": len(rows),
        "n_scale_solutions": len(scale_rows),
        "scales": [r.get("triplet_source_scale") for r in scale_rows],
        "baseline_l2_distance_to_target": base.get("l2_distance_to_target"),
        "best_scale": None if best is None else best.get("triplet_source_scale"),
        "best_l2_distance_to_target": None if best is None else best.get("l2_distance_to_target"),
        "best_f_fraction": None if best is None else best.get("f_fraction"),
        "best_i_fraction": None if best is None else best.get("i_fraction"),
        "best_r_fraction": None if best is None else best.get("r_fraction"),
        "unscaled_total_type74_source_rate_s^-1": base.get("unscaled_total_type74_source_rate_s^-1"),
        "provenance": {
            "mode": "v0.3.29 adds --triplet-source-scale and writes xstar_like_element_solver_triplet_source_scale_scan.csv for diagnostic type-74 direct-source injection scale tests.",
            "assembly": "The scale scan remains a single-ion diagnostic source-vector experiment, not the final XSTAR-like global element matrix assembly.",
        },
    }

def write_element_solver_outputs(result: dict, out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    audit_rows = result.get("adjacent_coupling_terms", [])
    superlevel_rows = result.get("superlevel_cascade_audit", [])
    superlevel_branching_rows = result.get("superlevel_branching_audit", [])
    superlevel_source_rows = result.get("superlevel_source_audit", [])
    type74_linkage_rows = result.get("type74_linkage_audit", [])
    type74_triplet_source_rows = result.get("type74_triplet_source_audit", [])
    triplet_source_injection_rows = result.get("triplet_source_injection_comparison", [])
    triplet_source_scale_scan_rows = result.get("triplet_source_scale_scan", [])
    global_bound_bound_solve_comparison_rows = result.get("global_bound_bound_solve_comparison", [])
    global_bound_bound_type71_solve_comparison_rows = result.get("global_bound_bound_type71_solve_comparison", [])
    global_bound_bound_type71_type99_proxy_solve_comparison_rows = result.get("global_bound_bound_type71_type99_proxy_solve_comparison", [])
    global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows = result.get("global_bound_bound_type71_type99_type53_proxy_solve_comparison", [])
    type99_proxy_scale_scan_rows = result.get("type99_proxy_scale_scan", [])
    radiation_context_rows = result.get("radiation_context", [])
    type53_rate_audit_rows = result.get("type53_rate_audit", [])
    type53_flat_proxy_rate_audit_rows = result.get("type53_flat_proxy_rate_audit", [])
    global_type53_flat_proxy_matrix_terms = result.get("global_type53_flat_proxy_matrix_terms", [])
    full_global_matrix_terms = result.get("full_global_matrix_terms", [])
    full_global_normalized_solve_comparison_rows = result.get("full_global_normalized_solve_comparison", [])
    global_superlevel_cascade_matrix_terms = result.get("global_superlevel_cascade_matrix_terms", [])
    global_superlevel_source_matrix_terms = result.get("global_superlevel_source_matrix_terms", [])
    if "summary" in result:
        result["summary"] = dict(result.get("summary", {}))
        result["summary"]["type57_audit_summary"] = _type57_audit_summary(audit_rows)
        result["summary"]["type59_recombination_audit_summary"] = _type59_recombination_audit_summary(audit_rows)
        result["summary"]["superlevel_cascade_audit_summary"] = _superlevel_cascade_audit_summary(superlevel_rows)
        result["summary"]["superlevel_branching_audit_summary"] = _superlevel_branching_audit_summary(superlevel_branching_rows)
        result["summary"]["superlevel_source_audit_summary"] = _superlevel_source_audit_summary(superlevel_source_rows)
        result["summary"]["type74_linkage_audit_summary"] = _type74_linkage_audit_summary(type74_linkage_rows)
        result["summary"]["type74_triplet_source_audit_summary"] = _type74_triplet_source_audit_summary(type74_triplet_source_rows)
        if triplet_source_injection_rows:
            result["summary"]["triplet_source_injection_comparison_summary"] = _triplet_source_injection_comparison_summary(triplet_source_injection_rows)
        if triplet_source_scale_scan_rows:
            result["summary"]["triplet_source_scale_scan_summary"] = _triplet_source_scale_scan_summary(triplet_source_scale_scan_rows)
        if global_bound_bound_solve_comparison_rows:
            result["summary"]["global_bound_bound_solve_comparison_summary"] = _global_bound_bound_solve_comparison_summary(global_bound_bound_solve_comparison_rows)
        if global_bound_bound_type71_solve_comparison_rows:
            result["summary"]["global_bound_bound_type71_solve_comparison_summary"] = _global_bound_bound_type71_solve_comparison_summary(global_bound_bound_type71_solve_comparison_rows)
        if global_bound_bound_type71_type99_proxy_solve_comparison_rows:
            result["summary"]["global_bound_bound_type71_type99_proxy_solve_comparison_summary"] = _global_bound_bound_type71_type99_proxy_solve_comparison_summary(global_bound_bound_type71_type99_proxy_solve_comparison_rows)
        if global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows:
            result["summary"]["global_bound_bound_type71_type99_type53_proxy_solve_comparison_summary"] = _global_bound_bound_type71_type99_type53_proxy_solve_comparison_summary(global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows)
        if type99_proxy_scale_scan_rows:
            result["summary"]["type99_proxy_scale_scan_summary"] = _type99_proxy_scale_scan_summary(type99_proxy_scale_scan_rows)
        if type53_rate_audit_rows:
            result["summary"]["type53_rate_audit_summary"] = _type53_rate_audit_summary(type53_rate_audit_rows)
        if type53_flat_proxy_rate_audit_rows:
            result["summary"]["type53_flat_proxy_rate_audit_summary"] = _type53_flat_proxy_rate_audit_summary(type53_flat_proxy_rate_audit_rows)
        if global_type53_flat_proxy_matrix_terms:
            result["summary"]["global_type53_flat_proxy_matrix_terms_summary"] = _global_type53_flat_proxy_matrix_terms_summary(global_type53_flat_proxy_matrix_terms)
        if full_global_matrix_terms:
            result["summary"]["full_global_matrix_terms_summary"] = _full_global_matrix_terms_summary(full_global_matrix_terms)
        if full_global_normalized_solve_comparison_rows:
            result["summary"]["full_global_normalized_solve_comparison_summary"] = _full_global_normalized_solve_comparison_summary(full_global_normalized_solve_comparison_rows)
        if global_superlevel_cascade_matrix_terms:
            result["summary"]["global_superlevel_cascade_matrix_terms_summary"] = _global_superlevel_cascade_matrix_terms_summary(global_superlevel_cascade_matrix_terms)
        if global_superlevel_source_matrix_terms:
            result["summary"]["global_superlevel_source_matrix_terms_summary"] = _global_superlevel_source_matrix_terms_summary(global_superlevel_source_matrix_terms)
    write_csv(out / "xstar_like_element_solver_ion_blocks.csv", result.get("ion_blocks", []))
    write_csv(out / "xstar_like_element_solver_global_index.csv", result.get("global_index", []))
    write_csv(out / "xstar_like_element_solver_coupling_candidates.csv", result.get("coupling_candidates", []))
    write_csv(out / "xstar_like_element_solver_adjacent_coupling_terms.csv", result.get("adjacent_coupling_terms", []))
    write_csv(out / "xstar_like_element_solver_ucalc_adjacent_audit.csv", audit_rows)
    write_csv(out / "xstar_like_element_solver_superlevel_cascade_audit.csv", superlevel_rows)
    write_csv(out / "xstar_like_element_solver_superlevel_branching_audit.csv", superlevel_branching_rows)
    write_csv(out / "xstar_like_element_solver_superlevel_source_audit.csv", superlevel_source_rows)
    write_csv(out / "xstar_like_element_solver_type74_linkage_audit.csv", type74_linkage_rows)
    write_csv(out / "xstar_like_element_solver_type74_triplet_source_audit.csv", type74_triplet_source_rows)
    write_csv(out / "xstar_like_element_solver_triplet_source_injection_comparison.csv", triplet_source_injection_rows)
    write_csv(out / "xstar_like_element_solver_triplet_source_scale_scan.csv", triplet_source_scale_scan_rows)
    write_csv(out / "xstar_like_element_solver_populations.csv", result.get("populations", []))
    write_csv(out / "xstar_like_element_solver_lines.csv", result.get("line_rows", []))
    write_csv(out / "xstar_like_element_solver_transitions.csv", result.get("transition_rows", []))
    write_csv(out / "xstar_like_element_solver_global_bound_bound_matrix_terms.csv", result.get("global_bound_bound_matrix_terms", []))
    write_csv(out / "xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv", global_superlevel_cascade_matrix_terms)
    write_csv(out / "xstar_like_element_solver_global_superlevel_source_matrix_terms.csv", global_superlevel_source_matrix_terms)
    write_csv(out / "xstar_like_element_solver_global_bound_bound_solve_comparison.csv", global_bound_bound_solve_comparison_rows)
    write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv", global_bound_bound_type71_solve_comparison_rows)
    write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_type99_proxy_solve_comparison.csv", global_bound_bound_type71_type99_proxy_solve_comparison_rows)
    write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_type99_type53_proxy_solve_comparison.csv", global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows)
    write_csv(out / "xstar_like_element_solver_type99_proxy_scale_scan.csv", type99_proxy_scale_scan_rows)
    write_csv(out / "xstar_like_element_solver_radiation_context.csv", radiation_context_rows)
    write_csv(out / "xstar_like_element_solver_type53_rate_audit.csv", type53_rate_audit_rows)
    write_csv(out / "xstar_like_element_solver_type53_flat_proxy_rate_audit.csv", type53_flat_proxy_rate_audit_rows)
    write_csv(out / "xstar_like_element_solver_global_type53_flat_proxy_matrix_terms.csv", global_type53_flat_proxy_matrix_terms)
    write_csv(out / "xstar_like_element_solver_full_global_matrix_terms.csv", full_global_matrix_terms)
    write_csv(out / "xstar_like_element_solver_full_global_normalized_solve_comparison.csv", full_global_normalized_solve_comparison_rows)
    write_csv(out / "xstar_like_element_solver_triplet.csv", result.get("triplet_rows", []))
    (out / "xstar_like_element_solver_summary.json").write_text(json.dumps(result.get("summary", {}), indent=2), encoding="utf-8")
    lines = ["# XSTAR-like element-solver summary", "", "This is a pure-Python reference/scaffold run.", ""]
    summ = result.get("summary", {})
    for key in sorted(summ):
        lines.append(f"- **{key}**: `{summ[key]}`")
    lines.append("")
    lines.append("Adjacent-ion coupling records are catalogued with ucalc-style branch annotations; evaluable recombination records may also be assembled as prototype source terms when adjacent_coupling_mode requests it. Type-57 records are evaluated diagnostically through the ported calt57 path but are not assembled by default. Type-59 inverse recombination/photoionization records are audited for the XSTAR excited-level recombination suppression gate and are not assembled. Photoionization/DR/superlevel records are audited but not blindly treated as rates without XSTAR radiation-field context. Type-71/type-77 superlevel branching fractions, type-70/74/99 source × branch proxies, the v0.3.26 deep type-74 linkage audit, the v0.3.27 direct type-74 triplet-source diagnostic, and the v0.3.28 optional type-74 direct source-injection before/after solve, and v0.3.29 type-74 direct source scale scan; v0.3.30 fixes the scale-scan target helper, and v0.3.31 writes an explicit global element state index, v0.3.32 fixes superlevel/continuum classification, and v0.3.33 writes a diagnostic global bound-bound matrix-term scaffold from the current per-ion radiative/collisional transition logs; v0.3.34 solves the He-like intra-ion global-index bound-bound block as an equivalence test against the current per-ion solve; v0.3.35 maps type-71 superlevel cascade terms onto global-index matrix triplets; v0.3.36 solves an extended He-like global block including bound-bound plus type-71 cascade terms as a diagnostic scaffold; v0.3.37 fixes the output handoff so the bound-bound+type71 solve-comparison rows are written to CSV; v0.3.38 maps diagnostic type-99 superlevel source candidates onto global-index source/matrix proxy rows; v0.3.39 solves a diagnostic bound-bound+type71 block with nonphysical type-99 proxy source-vector rows; v0.3.40 adds a type-99 proxy scale scan and writes xstar_like_element_solver_type99_proxy_scale_scan.csv; v0.3.41/v0.3.42 fix the CLI-to-solver handoff for the type-99 proxy scale option; v0.3.43 adds a type-53 radiation-context scaffold and xstar_like_element_solver_type53_rate_audit.csv without evaluating phint53/Milne physical rates; v0.3.45 adds a diagnostic flat-field type-53 photoionization-rate proxy and global matrix topology rows without assembling them; v0.3.46 solves a diagnostic bound-bound+type71+type99-proxy block with type-53 flat photoionization proxy sinks; v0.3.47 writes xstar_like_element_solver_full_global_matrix_terms.csv by combining C VI/C V bound-bound blocks, C V type-71 cascades, type-99 parent-continuum-to-superlevel proxy topology, type-53 flat photoionization proxy topology, and mappable type-1 recombination source/topology rows; v0.3.48 adds xstar_like_element_solver_full_global_normalized_solve_comparison.csv, the first diagnostic normalized full-global proxy-topology solve over all global_index rows with source-vector rows excluded; diagnostic source audits remain nonphysical and the normalized solve is not yet a physical XSTAR element solution.")
    t57sum = summ.get("type57_audit_summary", {}) if isinstance(summ, dict) else {}
    if t57sum:
        lines.extend([
            "",
            "## Type-57 source-code provenance",
            "",
            "- `ucalc.f90` type 57 visible branch uses `e1=rlev(1,idest1)`, `eth=max(0,rlev(1,nlevp)-rlev(1,idest1))`, and `ep=eth` before `call calt57`.",
            "- `calt57.f90` documents `e` as level energy and `ep` as the fourth real of the type-6 level record; its internal gate requires `ep >= e`.",
            "- v0.3.21 writes `ucalc-eth`, `abs-rlev4`, and `threshold-only` diagnostics side by side and lets `--type57-energy-convention` choose only the primary `python_*` audit columns.",
            "- Type 57 remains diagnostic-only and is not assembled into the element matrix.",
            "",
            f"- **type57 rows**: `{t57sum.get('n_type57_rows')}`",
            f"- **selected convention counts**: `{t57sum.get('selected_energy_convention_counts')}`",
            f"- **nonzero ucalc-eth forward rates**: `{t57sum.get('nonzero_ucalc_eth_forward_rates')}`",
            f"- **nonzero abs-rlev4 forward rates**: `{t57sum.get('nonzero_abs_rlev4_forward_rates')}`",
            f"- **nonzero threshold-only forward rates**: `{t57sum.get('nonzero_threshold_only_forward_rates')}`",
            f"- **matrix role classification counts**: `{t57sum.get('matrix_role_classification_counts')}`",
            f"- **matrix safe-to-assemble counts**: `{t57sum.get('matrix_safe_to_assemble_counts')}`",
        ])
    t59sum = summ.get("type59_recombination_audit_summary", {}) if isinstance(summ, dict) else {}
    if t59sum:
        lines.extend([
            "",
            "## Type-59 recombination-to-excited-level audit",
            "",
            "- `ucalc.f90` type 59 calls `phintfo` for bound-free photoionization/inverse recombination terms, then zeros `ans2`, `ans4`, and `ans6` when `nrdesc == 1` or `idest1 > 1`.",
            "- v0.3.22 reports which type-59 or related recombination rows would nominally feed excited levels, which rows are suppressed by the visible XSTAR gate, and whether any unsuppressed row is a He-like triplet-upper candidate.",
            "- Type 59 remains diagnostic-only and is not assembled into the element matrix.",
            "",
            f"- **type59 rows**: `{t59sum.get('n_type59_rows')}`",
            f"- **related recombination audit rows**: `{t59sum.get('n_related_recombination_audit_rows')}`",
            f"- **related family counts**: `{t59sum.get('related_recombination_family_counts')}`",
            f"- **related destination-kind counts**: `{t59sum.get('related_destination_level_kind_counts')}`",
            f"- **type59 suppressed counts**: `{t59sum.get('type59_suppressed_counts')}`",
            f"- **type59 suppression reasons**: `{t59sum.get('type59_suppression_reason_counts')}`",
            f"- **type59 excited-destination rows**: `{t59sum.get('type59_excited_destination_rows')}`",
            f"- **type59 triplet-upper rows after gate**: `{t59sum.get('type59_triplet_upper_after_gate_rows')}`",
        ])
    slsum = summ.get("superlevel_cascade_audit_summary", {}) if isinstance(summ, dict) else {}
    if slsum:
        lines.extend([
            "",
            "## Superlevel cascade audit",
            "",
            "- v0.3.23/v0.3.24 inventories data types 70/71/74/77/99 for possible superlevel recombination/cascade routes into He-like triplet upper levels.",
            "- Type 70/74/99 require bound-free radiation/Milne or linked superlevel context; type 71/77 can identify superlevel-to-spectroscopic cascade destinations but still require explicit superlevel populations.",
            "- No superlevel/cascade or branching rate is assembled into the element matrix.",
            "",
            f"- **superlevel audit rows**: `{slsum.get('n_superlevel_cascade_rows')}`",
            f"- **data type counts**: `{slsum.get('data_type_counts')}`",
            f"- **route kind counts**: `{slsum.get('route_kind_counts')}`",
            f"- **triplet-feed component counts**: `{slsum.get('cascade_feed_component_counts')}`",
            f"- **feeds any triplet component rows**: `{slsum.get('feeds_any_triplet_component_rows')}`",
            f"- **feeds forbidden/intercombination/resonance rows**: `{slsum.get('feeds_forbidden_upper_rows')}` / `{slsum.get('feeds_intercombination_upper_rows')}` / `{slsum.get('feeds_resonance_upper_rows')}`",
            f"- **matrix safe-to-assemble counts**: `{slsum.get('matrix_safe_to_assemble_counts')}`",
        ])
    brsum = summ.get("superlevel_branching_audit_summary", {}) if isinstance(summ, dict) else {}
    if brsum:
        lines.extend([
            "",
            "## Superlevel branching audit",
            "",
            "- v0.3.24 groups type-71/type-77 superlevel-to-spectroscopic rows by superlevel and computes diagnostic f/i/r branch fractions.",
            "- Type 71 uses radiative A-value-like weights. Type 77 uses a count proxy because the collisional superlevel rate evaluator is not yet ported.",
            "- Branching rows remain diagnostic-only and are not assembled into the element matrix.",
            "",
            f"- **superlevel branching rows**: `{brsum.get('n_superlevel_branching_rows')}`",
            f"- **data type counts**: `{brsum.get('data_type_counts')}`",
            f"- **weight-basis counts**: `{brsum.get('weight_basis_counts')}`",
            f"- **dominant component counts**: `{brsum.get('dominant_component_counts')}`",
            f"- **forbidden-favored counts**: `{brsum.get('forbidden_favored_counts')}`",
            f"- **type-71 f/i/r total weights**: `{brsum.get('total_type71_forbidden_weight')}` / `{brsum.get('total_type71_intercombination_weight')}` / `{brsum.get('total_type71_resonance_weight')}`",
            f"- **max type-71 triplet-branch superlevel/fraction**: `{brsum.get('max_type71_triplet_branch_superlevel')}` / `{brsum.get('max_type71_triplet_branch_fraction')}`",
            f"- **max type-77 triplet-branch superlevel/fraction**: `{brsum.get('max_type77_triplet_branch_superlevel')}` / `{brsum.get('max_type77_triplet_branch_fraction')}`",
            f"- **matrix safe-to-assemble counts**: `{brsum.get('matrix_safe_to_assemble_counts')}`",
        ])
    srcsum = summ.get("superlevel_source_audit_summary", {}) if isinstance(summ, dict) else {}
    if srcsum:
        lines.extend([
            "",
            "## Superlevel source × branch audit",
            "",
            "- v0.3.25 links type-70/74/99 superlevel source candidates to the v0.3.24 type-71/type-77 branching fractions for the same superlevel.",
            "- The source proxy is one nonphysical count unit per type-70/74/99 source candidate; source_proxy × B_f/i/r is a diagnostic feed proxy, not a rate.",
            "- Source-weighted proxy rows remain diagnostic-only and are not assembled into the element matrix.",
            "",
            f"- **superlevel source audit rows**: `{srcsum.get('n_superlevel_source_audit_rows')}`",
            f"- **total type-70/type-74/type-99 candidates**: `{srcsum.get('total_type70_candidates')}` / `{srcsum.get('total_type74_candidates')}` / `{srcsum.get('total_type99_candidates')}`",
            f"- **branch basis counts**: `{srcsum.get('branch_basis_counts')}`",
            f"- **dominant source-weighted component counts**: `{srcsum.get('dominant_component_counts')}`",
            f"- **total preferred f/i/r feed proxies**: `{srcsum.get('total_preferred_feed_f_proxy')}` / `{srcsum.get('total_preferred_feed_i_proxy')}` / `{srcsum.get('total_preferred_feed_r_proxy')}`",
            f"- **total preferred triplet feed proxy**: `{srcsum.get('total_preferred_feed_triplet_proxy')}`",
            f"- **max preferred triplet superlevel/proxy**: `{srcsum.get('max_preferred_feed_triplet_superlevel')}` / `{srcsum.get('max_preferred_feed_triplet_proxy')}`",
            f"- **matrix safe-to-assemble counts**: `{srcsum.get('matrix_safe_to_assemble_counts')}`",
        ])
    t74sum = summ.get("type74_linkage_audit_summary", {}) if isinstance(summ, dict) else {}
    if t74sum:
        lines.extend([
            "",
            "## Type-74 DR-delta linkage audit",
            "",
            "- v0.3.26 decodes each type-74 DR delta record into its parent/final level side (`i5`/`i6`) and recombined/source level side (`i7`/`i8`).",
            "- The audit classifies whether the recombined/source level is a spectroscopic level or superlevel, checks direct f/i/r triplet-upper matches, and tests whether any valid type-71/type-77 superlevel branch is available.",
            "- Type 74 remains diagnostic-only: delta records are not assembled until `calt74`/Milne bound-free context and explicit population balance are implemented.",
            "",
            f"- **type-74 linkage rows**: `{t74sum.get('n_type74_linkage_rows')}`",
            f"- **source-level kind counts**: `{t74sum.get('source_level_kind_counts')}`",
            f"- **branch-link status counts**: `{t74sum.get('branch_link_status_counts')}`",
            f"- **direct f/i/r source candidates**: `{t74sum.get('direct_forbidden_source_candidates')}` / `{t74sum.get('direct_intercombination_source_candidates')}` / `{t74sum.get('direct_resonance_source_candidates')}`",
            f"- **can feed f/i/r candidates**: `{t74sum.get('can_feed_forbidden_candidates')}` / `{t74sum.get('can_feed_intercombination_candidates')}` / `{t74sum.get('can_feed_resonance_candidates')}`",
            f"- **valid type-71/type-77 superlevel branch links**: `{t74sum.get('valid_type71_superlevel_branch_links')}` / `{t74sum.get('valid_type77_superlevel_branch_links')}`",
            f"- **same-numeric source type-71/type-77 branch rows**: `{t74sum.get('same_numeric_source_type71_branch_rows')}` / `{t74sum.get('same_numeric_source_type77_branch_rows')}`",
            f"- **matrix safe-to-assemble counts**: `{t74sum.get('matrix_safe_to_assemble_counts')}`",
        ])
    t74src = summ.get("type74_triplet_source_audit_summary", {}) if isinstance(summ, dict) else {}
    if t74src:
        lines.extend([
            "",
            "## Type-74 direct triplet-source diagnostic",
            "",
            "- v0.3.27 evaluates the recombination-alpha part of `calt74.f90` for type-74 records whose recombined/source level directly matches a He-like f/i/r triplet upper level.",
            "- The diagnostic applies the `ucalc.f90` statistical-weight correction `alpha *= g(recombined)/g(continuum)` with a placeholder continuum weight of 1 until the global element matrix has an explicit continuum row.",
            "- The resulting f/i/r source-vector shape is compared to the C V ne=1e8 XSTAR target when applicable. No type-74 source term is assembled into the matrix.",
            "",
            f"- **direct triplet candidates**: `{t74src.get('n_direct_triplet_candidate_rows')}`",
            f"- **component counts**: `{t74src.get('triplet_component_counts')}`",
            f"- **eval status counts**: `{t74src.get('eval_status_counts')}`",
            f"- **total f/i/r source rates**: `{t74src.get('total_source_rate_f_s^-1')}` / `{t74src.get('total_source_rate_i_s^-1')}` / `{t74src.get('total_source_rate_r_s^-1')}`",
            f"- **source-vector f/i/r fractions**: `{t74src.get('source_fraction_f')}` / `{t74src.get('source_fraction_i')}` / `{t74src.get('source_fraction_r')}`",
            f"- **dominant source-vector component**: `{t74src.get('source_vector_dominant_component')}`",
            f"- **target comparison**: `{t74src.get('xstar_target_name')}`, L2=`{t74src.get('source_vector_l2_distance_to_target')}`",
            f"- **matrix safe-to-assemble counts**: `{t74src.get('matrix_safe_to_assemble_counts')}`",
        ])
    (out / "xstar_like_element_solver_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
