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


def _sum_float(rows: Sequence[dict], col: str) -> float:
    """Return a finite float sum for *col* across a sequence of row dictionaries.

    This module has several local summary helpers with nested ``_sum_float``
    functions.  The type-53 ``phint53`` summary added in v0.3.52 needs a
    module-level helper because it is shared by multiple summary functions.
    Missing, non-numeric, NaN, and infinite values are ignored, matching the
    behavior of the older nested helpers.
    """
    total = 0.0
    for row in rows:
        val = maybe_float(row.get(col))
        if val is not None and math.isfinite(float(val)):
            total += float(val)
    return total


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




def _xstar_pescl_source(tau: float) -> float:
    """Port XSTAR ``pescl.f90`` line escape probability."""
    tau = float(tau or 0.0)
    pi = 3.1415927
    tauw = 1.0e5
    if tau < 1.0:
        if tau < 1.0e-5:
            val = 1.0
        else:
            aa = 2.0 * tau
            val = (1.0 - math.exp(-aa)) / aa
    else:
        bb = 0.5 * math.sqrt(max(0.0, math.log(tau))) / (1.0 + tau / tauw)
        val = 1.0 / (tau * math.sqrt(pi) * (1.2 + bb))
    return float(val / 2.0)


def _xstar_calc_emis_ptmp_from_tau(tau1: float, tau2: float, cfrac: float) -> tuple[float, float]:
    """Port the ``calc_emis_ion.f90`` type-4/type-9 line escape channels."""
    cfrac = max(0.0, min(1.0, float(cfrac or 0.0)))
    ptmp1 = _xstar_pescl_source(float(tau1 or 0.0)) * (1.0 - cfrac)
    ptmp2 = _xstar_pescl_source(float(tau2 or 0.0)) * (1.0 - cfrac) + 2.0 * _xstar_pescl_source(float(tau1 or 0.0) + float(tau2 or 0.0)) * cfrac
    return float(ptmp1), float(ptmp2)




_XSTAR_APPROX_ATOMIC_MASS_AMU = {
    "H": 1.0079, "He": 4.0026, "Li": 6.94, "Be": 9.0122, "B": 10.81,
    "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974,
    "S": 32.06, "Cl": 35.45, "Ar": 39.948, "K": 39.098, "Ca": 40.078,
    "Fe": 55.845,
}


def _xstar_atomic_mass_amu_from_symbol(symbol: object) -> float:
    sym = str(symbol or "").strip()
    if not sym:
        return 1.0
    sym = sym[0].upper() + sym[1:].lower()
    return float(_XSTAR_APPROX_ATOMIC_MASS_AMU.get(sym, max(1.0, float(SYMBOL_TO_Z.get(sym, 1) or 1))))


def _xstar_type50_line_opacity_context(
    *,
    line: Mapping[str, object],
    lower_row: Optional[Mapping[str, object]],
    upper_row: Optional[Mapping[str, object]],
    lower_population: float,
    temperature_K: float,
    vturb_km_s: float,
    line_column_density_cm2: float,
    tau1_column_fraction: float,
    tau2_column_fraction: float,
    cfrac: float,
) -> dict:
    """Reconstruct the XSTAR type-50 line optical-depth context.

    The visible XSTAR source path is::

      ucalc.f90 type 50:
        flin=(1d-16)*aij*ggup*elin**2/(0.667274*gglo)
        vtherm=sqrt((vturb*1d5)**2 + (1.29d6/sqrt(a/t))**2)
        sigvtherm=(0.02655)*flin*elin*1d-8/vtherm
        opakb1=sigvtherm*abund1

      calc_emisab_ion.f90 / stpcut.f90:
        oplin(jkkl)=opakb1 [line opacity per length]
        tau0(lind,jkkl)+=oplin(jkkl)*delr

    In the stand-alone ATDB demo there is no radial transfer history, so the
    caller supplies an equivalent column for ``xpx*xeltp*delr``.  The lower
    level column is then ``xileve_lower * column`` and the source-code optical
    depth is ``tau=sigvtherm*N_lower`` for each direction.
    """
    A = float(maybe_float(line.get("A_s^-1")) or 0.0)
    lam = float(maybe_float(line.get("wavelength_A")) or 0.0)
    if A <= 0.0 or lam <= 0.0:
        return {"status": "not_evaluated_missing_A_or_wavelength"}
    g_lo = float(maybe_float((lower_row or {}).get("statistical_weight_g")) or maybe_float((lower_row or {}).get("stat_weight")) or 1.0)
    g_up = float(maybe_float((upper_row or {}).get("statistical_weight_g")) or maybe_float((upper_row or {}).get("stat_weight")) or 1.0)
    if g_lo <= 0.0:
        g_lo = 1.0
    if g_up <= 0.0:
        g_up = 1.0
    element = line.get("element") or (lower_row or {}).get("element") or (upper_row or {}).get("element")
    atomic_mass = _xstar_atomic_mass_amu_from_symbol(element)
    t_xstar = max(float(temperature_K or 0.0) / 1.0e4, 1.0e-30)
    vtherm = math.sqrt((float(vturb_km_s or 0.0) * 1.0e5) ** 2 + (1.29e6 / math.sqrt(max(atomic_mass / t_xstar, 1.0e-300))) ** 2)
    flin = 1.0e-16 * A * g_up * lam * lam / (0.667274 * g_lo)
    sigvtherm = 0.02655 * flin * lam * 1.0e-8 / max(vtherm, 1.0e-300)
    col_total = max(0.0, float(line_column_density_cm2 or 0.0))
    lower_column = max(0.0, float(lower_population or 0.0)) * col_total
    tau1 = sigvtherm * lower_column * max(0.0, float(tau1_column_fraction or 0.0))
    tau2 = sigvtherm * lower_column * max(0.0, float(tau2_column_fraction or 0.0))
    ptmp1, ptmp2 = _xstar_calc_emis_ptmp_from_tau(tau1, tau2, cfrac)
    return {
        "status": "evaluated_source_code_tau0_from_type50_sigvtherm_and_supplied_column",
        "xstar_tau0_source_code_path": "ucalc.f90 type50 sigvtherm -> calc_emisab_ion/stpcut tau0=tau0+oplin*delr; standalone column replaces xpx*xeltp*delr",
        "xstar_line_column_density_cm^-2": col_total,
        "xstar_line_lower_level_column_cm^-2": lower_column,
        "xstar_line_tau1_column_fraction": float(tau1_column_fraction or 0.0),
        "xstar_line_tau2_column_fraction": float(tau2_column_fraction or 0.0),
        "xstar_line_cfrac": max(0.0, min(1.0, float(cfrac or 0.0))),
        "xstar_line_vturb_km_s": float(vturb_km_s or 0.0),
        "xstar_line_temperature_t_1e4K": t_xstar,
        "xstar_line_atomic_mass_amu": atomic_mass,
        "xstar_line_vtherm_cm_s": vtherm,
        "xstar_line_flin_oscillator_strength": flin,
        "xstar_line_sigvtherm_cm2": sigvtherm,
        "xstar_line_tau1": tau1,
        "xstar_line_tau2": tau2,
        "xstar_line_ptmp1": ptmp1,
        "xstar_line_ptmp2": ptmp2,
        "xstar_line_ptmp_sum": ptmp1 + ptmp2,
    }

def _component_fraction_summary_from_emissivities(values: Mapping[str, float]) -> dict:
    f = max(0.0, float(values.get("f", 0.0) or 0.0))
    i = max(0.0, float(values.get("i", 0.0) or 0.0))
    r = max(0.0, float(values.get("r", 0.0) or 0.0))
    total = f + i + r
    return {
        "f_emissivity": f,
        "i_emissivity": i,
        "r_emissivity": r,
        "f_fraction": f / total if total > 0.0 else 0.0,
        "i_fraction": i / total if total > 0.0 else 0.0,
        "r_fraction": r / total if total > 0.0 else 0.0,
        "R": f / i if i > 0.0 else None,
        "G": (f + i) / r if r > 0.0 else None,
    }


def build_calc_emis_ion_triplet_emergent_rows(
    *,
    global_index_rows: Sequence[dict],
    line_rows: Sequence[dict],
    full_global_normalized_solve_comparison_rows: Sequence[dict],
    type50_ucalc_rate_audit_rows: Sequence[dict],
    he_like_stage: int,
    temperature_K: float,
    xstar_line_column_density: object = 0.0,
    xstar_line_vturb_km_s: object = 0.0,
    xstar_line_cfrac: object = 0.0,
    xstar_line_tau1_fraction: object = 1.0,
    xstar_line_tau2_fraction: object = 1.0,
) -> List[dict]:
    """Build XSTAR ``calc_emis_ion`` emergent-triplet line rows.

    v0.3.87 ports the source-code line-output construction for the selected
    He-like triplet records.  For line data (XSTAR type-50 / rate-type-4),
    ``ucalc.f90`` computes an escaped decay rate ``A*(ptmp1+ptmp2)``, computes
    any lower-to-upper photoexcitation rate, and then swaps the rates so that
    ``ans1`` is pumping and ``ans2`` is escaped decay.  ``calc_emis_ion.f90``
    then writes local emergent flux channels as::

        fline(1)=max((ans2*abund2 - ans1*abund1) * E * ptmp1, 0)
        fline(2)=max((ans2*abund2 - ans1*abund1) * E * ptmp2, 0)

    where ``ptmp1`` and ``ptmp2`` come from ``pescl(tau0)`` and covering
    fraction.  v0.3.87 adds the XSTAR tau0 context feeding these ptmp values:
    it reconstructs the type-50 oscillator strength, thermal width, line
    cross section, lower-level column, and directional tau0 values.  The
    old common matrix escape proxy is no longer used for the emergent-line
    comparison; it remains only in the population matrix if explicitly chosen.
    """
    he_like_stage = int(he_like_stage)
    lookup = _global_index_lookup(global_index_rows)
    pop_by_global: Dict[int, float] = {}
    pop_by_ion_level: Dict[tuple[int, int], float] = {}
    for r in full_global_normalized_solve_comparison_rows:
        if str(r.get("row_kind")) != "population":
            continue
        g = maybe_int(r.get("global_index"))
        st = maybe_int(r.get("ion_stage"))
        lev = maybe_int(r.get("level_index"))
        val = maybe_float(r.get("xstar_xileve_emissivity_population"))
        if val is None:
            val = maybe_float(r.get("population_fraction"))
        if val is None:
            continue
        if g is not None:
            pop_by_global[int(g)] = float(val)
        if st is not None and lev is not None:
            pop_by_ion_level[(int(st), int(lev))] = float(val)
    type50_by_record: Dict[int, dict] = {}
    for r in type50_ucalc_rate_audit_rows:
        rec = maybe_int(r.get("record"))
        if rec is not None:
            type50_by_record[int(rec)] = r
    target = _xstar_triplet_target(he_like_stage)
    line_column_density = max(0.0, float(maybe_float(xstar_line_column_density) or 0.0))
    line_vturb = max(0.0, float(maybe_float(xstar_line_vturb_km_s) or 0.0))
    line_cfrac = max(0.0, min(1.0, float(maybe_float(xstar_line_cfrac) or 0.0)))
    tau1_fraction = max(0.0, float(maybe_float(xstar_line_tau1_fraction) or 0.0))
    tau2_fraction = max(0.0, float(maybe_float(xstar_line_tau2_fraction) or 0.0))
    rows: List[dict] = []
    sums_raw = {"f": 0.0, "i": 0.0, "r": 0.0}
    sums_trans = {"f": 0.0, "i": 0.0, "r": 0.0}
    sums_xstar_tau0 = {"f": 0.0, "i": 0.0, "r": 0.0}
    # XSTAR transparent line escape from source functions.
    tau0_ptmp1, tau0_ptmp2 = _xstar_calc_emis_ptmp_from_tau(0.0, 0.0, 0.0)
    for line in line_rows:
        if maybe_int(line.get("ion_stage")) != he_like_stage:
            continue
        comp = classify_helike_triplet_line(line)
        if comp not in {"f", "i", "r"}:
            continue
        rec = maybe_int(line.get("record"))
        lower = maybe_int(line.get("lower_level"))
        upper = maybe_int(line.get("upper_level"))
        if lower is None or upper is None:
            continue
        lower_row = lookup.get((he_like_stage, int(lower)))
        upper_row = lookup.get((he_like_stage, int(upper)))
        lower_global = maybe_int(lower_row.get("global_index")) if lower_row else None
        upper_global = maybe_int(upper_row.get("global_index")) if upper_row else None
        lower_pop = pop_by_global.get(int(lower_global), pop_by_ion_level.get((he_like_stage, int(lower)), 0.0)) if lower_global is not None else pop_by_ion_level.get((he_like_stage, int(lower)), 0.0)
        upper_pop = pop_by_global.get(int(upper_global), pop_by_ion_level.get((he_like_stage, int(upper)), 0.0)) if upper_global is not None else pop_by_ion_level.get((he_like_stage, int(upper)), 0.0)
        A = maybe_float(line.get("A_s^-1")) or 0.0
        eerg = line_energy_erg(line) or 0.0
        raw = max(float(upper_pop) * float(A) * float(eerg), 0.0)
        # Transparent source-code construction: tau0=0 => pescl=0.5 for each channel,
        # ptmp1+ptmp2=1, ans1=0, ans2=A.
        trans_ans1 = 0.0
        trans_ans2 = float(A) * (tau0_ptmp1 + tau0_ptmp2)
        trans_net = trans_ans2 * float(upper_pop) - trans_ans1 * float(lower_pop)
        trans_f1 = max(trans_net * float(eerg) * tau0_ptmp1, 0.0)
        trans_f2 = max(trans_net * float(eerg) * tau0_ptmp2, 0.0)
        # v0.3.87 source-code tau0 construction: compute component-specific
        # line optical depth from the type-50 oscillator strength and a supplied
        # equivalent XSTAR abundance column.  This replaces the former common
        # triplet escape proxy in the emergent-line path.
        tau_ctx = _xstar_type50_line_opacity_context(
            line=line,
            lower_row=lower_row,
            upper_row=upper_row,
            lower_population=float(lower_pop),
            temperature_K=float(temperature_K),
            vturb_km_s=line_vturb,
            line_column_density_cm2=line_column_density,
            tau1_column_fraction=tau1_fraction,
            tau2_column_fraction=tau2_fraction,
            cfrac=line_cfrac,
        )
        x_ptmp1 = float(tau_ctx.get("xstar_line_ptmp1") or tau0_ptmp1)
        x_ptmp2 = float(tau_ctx.get("xstar_line_ptmp2") or tau0_ptmp2)
        x_ans1 = 0.0
        x_ans2 = float(A) * (x_ptmp1 + x_ptmp2)
        x_net = x_ans2 * float(upper_pop) - x_ans1 * float(lower_pop)
        x_f1 = max(x_net * float(eerg) * x_ptmp1, 0.0)
        x_f2 = max(x_net * float(eerg) * x_ptmp2, 0.0)
        sums_raw[comp] += raw
        sums_trans[comp] += (trans_f1 + trans_f2)
        sums_xstar_tau0[comp] += (x_f1 + x_f2)
        rows.append({
            "row_kind": "calc_emis_ion_triplet_emergent_line",
            "component": comp,
            "record": rec,
            "ion_stage": he_like_stage,
            "lower_level": int(lower),
            "upper_level": int(upper),
            "lower_global_index": lower_global,
            "upper_global_index": upper_global,
            "lower_label": line.get("lower_label"),
            "upper_label": line.get("upper_label"),
            "wavelength_A": line.get("wavelength_A"),
            "energy_eV": line.get("energy_eV"),
            "photon_energy_erg": eerg,
            "A_s^-1": float(A),
            "xstar_xileve_lower_population": float(lower_pop),
            "xstar_xileve_upper_population": float(upper_pop),
            "raw_pop_A_E_erg_s^-1": raw,
            "transparent_tau1": 0.0,
            "transparent_tau2": 0.0,
            "transparent_cfrac": 0.0,
            "transparent_ptmp1_pescl": tau0_ptmp1,
            "transparent_ptmp2_pescl": tau0_ptmp2,
            "transparent_ucalc_ans1_lower_to_upper_s^-1": trans_ans1,
            "transparent_ucalc_ans2_upper_to_lower_s^-1": trans_ans2,
            "transparent_calc_emis_fline1_erg_s^-1": trans_f1,
            "transparent_calc_emis_fline2_erg_s^-1": trans_f2,
            "transparent_calc_emis_fline_total_erg_s^-1": trans_f1 + trans_f2,
            "xstar_tau0_line_column_density_cm^-2": tau_ctx.get("xstar_line_column_density_cm^-2", ""),
            "xstar_tau0_lower_level_column_cm^-2": tau_ctx.get("xstar_line_lower_level_column_cm^-2", ""),
            "xstar_tau0_vturb_km_s": tau_ctx.get("xstar_line_vturb_km_s", ""),
            "xstar_tau0_vtherm_cm_s": tau_ctx.get("xstar_line_vtherm_cm_s", ""),
            "xstar_tau0_flin_oscillator_strength": tau_ctx.get("xstar_line_flin_oscillator_strength", ""),
            "xstar_tau0_sigvtherm_cm2": tau_ctx.get("xstar_line_sigvtherm_cm2", ""),
            "xstar_tau0_tau1": tau_ctx.get("xstar_line_tau1", ""),
            "xstar_tau0_tau2": tau_ctx.get("xstar_line_tau2", ""),
            "xstar_tau0_cfrac": tau_ctx.get("xstar_line_cfrac", ""),
            "xstar_tau0_ptmp1": x_ptmp1,
            "xstar_tau0_ptmp2": x_ptmp2,
            "xstar_tau0_ptmp_sum": x_ptmp1 + x_ptmp2,
            "xstar_tau0_ucalc_ans1_lower_to_upper_s^-1": x_ans1,
            "xstar_tau0_ucalc_ans2_upper_to_lower_s^-1": x_ans2,
            "xstar_tau0_calc_emis_net_rate_s^-1": x_net,
            "xstar_tau0_calc_emis_fline1_erg_s^-1": x_f1,
            "xstar_tau0_calc_emis_fline2_erg_s^-1": x_f2,
            "xstar_tau0_calc_emis_fline_total_erg_s^-1": x_f1 + x_f2,
            "xstar_tau0_attenuation_vs_raw_pop_A_E": (x_f1 + x_f2) / raw if raw > 0.0 else "",
            "source_code_formula": "calc_emis_ion.f90 type-4/type-9: fline=max((ans2*abund2-ans1*abund1)*E*ptmp,0); ucalc.f90 type-50 provides ans2=A*(ptmp1+ptmp2) after tau0->pescl escape",
            "tau0_context_status": tau_ctx.get("status", ""),
            "tau0_source_code_path": tau_ctx.get("xstar_tau0_source_code_path", ""),
            "provenance": "v0.3.87_exact_calc_emis_ion_triplet_emergent_line_construction",
        })
    for label, sums in (("raw_pop_A_E", sums_raw), ("transparent_tau0_calc_emis_ion", sums_trans), ("xstar_tau0_calc_emis_ion", sums_xstar_tau0)):
        summ = _component_fraction_summary_from_emissivities(sums)
        rows.append({
            "row_kind": "calc_emis_ion_triplet_emergent_summary",
            "comparison_case": label,
            "f_fraction": summ["f_fraction"],
            "i_fraction": summ["i_fraction"],
            "r_fraction": summ["r_fraction"],
            "R": summ["R"],
            "G": summ["G"],
            "l2_distance_to_target": _triplet_l2_distance(summ, target),
            "f_emissivity_erg_s^-1": summ["f_emissivity"],
            "i_emissivity_erg_s^-1": summ["i_emissivity"],
            "r_emissivity_erg_s^-1": summ["r_emissivity"],
            "total_triplet_emissivity_erg_s^-1": summ["f_emissivity"] + summ["i_emissivity"] + summ["r_emissivity"],
            "target_f_fraction": target.get("f") if target else "",
            "target_i_fraction": target.get("i") if target else "",
            "target_r_fraction": target.get("r") if target else "",
            "source_code_formula": "calc_emis_ion.f90 fline channels with ucalc.f90 type-50 swapped ans1/ans2",
            "provenance": "v0.3.87_exact_calc_emis_ion_triplet_emergent_line_construction",
        })
    return rows


def _calc_emis_ion_triplet_emergent_summary(rows: Sequence[dict]) -> dict:
    summaries = [r for r in rows if r.get("row_kind") == "calc_emis_ion_triplet_emergent_summary"]
    by_case = {str(r.get("comparison_case")): r for r in summaries}
    xstar_tau = by_case.get("xstar_tau0_calc_emis_ion", {})
    transparent = by_case.get("transparent_tau0_calc_emis_ion", {})
    return {
        "n_calc_emis_ion_triplet_emergent_rows": len(rows),
        "n_calc_emis_ion_triplet_emergent_line_rows": sum(1 for r in rows if r.get("row_kind") == "calc_emis_ion_triplet_emergent_line"),
        "xstar_tau0_f_fraction": xstar_tau.get("f_fraction", ""),
        "xstar_tau0_i_fraction": xstar_tau.get("i_fraction", ""),
        "xstar_tau0_r_fraction": xstar_tau.get("r_fraction", ""),
        "xstar_tau0_R": xstar_tau.get("R", ""),
        "xstar_tau0_G": xstar_tau.get("G", ""),
        "xstar_tau0_l2_distance_to_target": xstar_tau.get("l2_distance_to_target", ""),
        "transparent_f_fraction": transparent.get("f_fraction", ""),
        "transparent_i_fraction": transparent.get("i_fraction", ""),
        "transparent_r_fraction": transparent.get("r_fraction", ""),
        "conclusion_scope": "Ports calc_emis_ion fline formula and XSTAR tau0->pescl context for triplet records; standalone column options replace the missing radial transfer history.",
        "provenance": "v0.3.87_exact_calc_emis_ion_triplet_emergent_line_construction",
    }


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
    type53_phint53_scale: object = 1.0,
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
            "type53_nreal_full": len(rd),
            "type53_nint_full": len(it),
            "type53_raw_reals_full": str(list(rd)),
            "type53_raw_ints_full": str(list(it)),
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


def _xstar_calt74_rate_alpha_diagnostic(
    temperature: float,
    reals: Sequence[float],
    *,
    radiation_context_rows: Sequence[dict] | None = None,
) -> dict:
    """Diagnostic Python port of XSTAR ``calt74`` rate and alpha.

    This follows ``xstarlib/src/calt74.f90`` more directly than the older
    v0.3.27 alpha-only helper.  XSTAR receives an energy grid ``xse`` in eV
    and a radiation/flux-like array ``xss`` (``bremsa`` in ``ucalc.f90``),
    evaluates delta-function resonances at ``(x_i + xt) * Ry``, linearly
    interpolates ``xss`` there, and returns both:

    * ``rate``  -- forward photoionization delta contribution before matrix use
    * ``alpha`` -- inverse DR recombination coefficient before the
      ``gglo/ggup`` statistical-weight correction applied in ``ucalc``.

    The radiation array is still the deterministic placeholder used by the
    current diagnostic radiation context, so absolute rates are not physical
    XSTAR rates.  The algebra, coefficient layout, interpolation, constants,
    and statistical-weight handoff are source-code aligned diagnostics.
    """
    try:
        rd = [float(x) for x in reals]
        temp = float(temperature)
    except Exception:
        return {"type74_calt74_status": "type74_bad_input"}
    nrd = len(rd)
    if nrd < 3:
        return {"type74_calt74_status": "type74_too_few_real_coefficients", "type74_n_real_coefficients": nrd}
    m = (nrd - 1) // 2
    if m <= 0 or (1 + 2 * m) > nrd:
        return {"type74_calt74_status": "type74_bad_delta_coefficient_layout", "type74_n_real_coefficients": nrd, "type74_m_delta_count": m}
    if temp <= 0.0 or not math.isfinite(temp):
        return {"type74_calt74_status": "type74_bad_temperature", "type74_temperature_K": temp}

    # Constants are literal values from calt74.f90.  ``ry`` is the Rydberg in eV.
    te = temp * 1.38066e-16
    ryk = 4.589343e10
    factor = 213.9577e-9
    ry_eV = 13.60569253
    xt = rd[0]
    energies = rd[1:1 + m]
    heights = rd[1 + m:1 + 2 * m]

    alpha_sum = 0.0
    alpha_terms_used = 0
    alpha_terms_skipped = 0
    for x, hgh in zip(energies, heights):
        arg = x / ryk / te
        if arg < 40.0:
            alpha_sum += math.exp(-arg) * (x + xt) * (x + xt) * hgh
            alpha_terms_used += 1
        else:
            alpha_terms_skipped += 1
    alpha = alpha_sum * factor / (te ** 1.5) / ryk / ryk

    ctx = dict((radiation_context_rows or [{}])[0] if radiation_context_rows else {})
    mode = str(ctx.get("radiation_field_mode", "none"))
    ngrid = maybe_int(ctx.get("n_energy_grid_points")) or 256
    emin = maybe_float(ctx.get("energy_min_eV")) or 1.0
    emax = maybe_float(ctx.get("energy_max_eV")) or 1.0e5
    bscale_ctx = maybe_float(ctx.get("radiation_bremsa_scale")) or 1.0
    powerlaw_ctx = maybe_float(ctx.get("radiation_powerlaw_index")) or 1.0
    grid = _log_energy_grid(float(emin), float(emax), max(int(ngrid), 2))
    bremsa = [_placeholder_bremsa_value(e, mode=mode, temperature_K=temp, bremsa_scale=bscale_ctx, powerlaw_index=powerlaw_ctx) for e in grid]

    rate_sum = 0.0
    rate_terms_used = 0
    rate_terms_outside_grid = 0
    resonance_energies_eV = []
    for x, hgh in zip(energies, heights):
        eres = (x + xt) * ry_eV
        resonance_energies_eV.append(eres)
        if not (math.isfinite(eres) and len(grid) >= 2 and grid[0] <= eres <= grid[-1]):
            rate_terms_outside_grid += 1
            continue
        # Source-compatible linear interpolation of xss at resonance energy.
        xsec = None
        for i in range(len(grid) - 1):
            if grid[i] <= eres <= grid[i + 1]:
                dx = grid[i + 1] - grid[i]
                if dx == 0.0:
                    xsec = bremsa[i]
                else:
                    xsec = bremsa[i] + (bremsa[i + 1] - bremsa[i]) * (eres - grid[i]) / dx
                break
        if xsec is None:
            rate_terms_outside_grid += 1
            continue
        rate_sum += xsec * hgh
        rate_terms_used += 1
    rate = rate_sum * 4.752e-22
    return {
        "type74_calt74_status": "evaluated_type74_calt74_rate_alpha_diagnostic",
        "type74_rate_unweighted_s^-1": rate,
        "type74_alpha_unweighted_cm3_s": alpha,
        "type74_n_real_coefficients": nrd,
        "type74_m_delta_count": m,
        "type74_xt_coeff": xt,
        "type74_delta_terms_alpha_used": alpha_terms_used,
        "type74_delta_terms_alpha_skipped_arg_ge_40": alpha_terms_skipped,
        "type74_delta_terms_rate_used": rate_terms_used,
        "type74_delta_terms_rate_outside_grid": rate_terms_outside_grid,
        "type74_delta_energy_coeff_min": min(energies) if energies else None,
        "type74_delta_energy_coeff_max": max(energies) if energies else None,
        "type74_delta_height_abs_sum": sum(abs(h) for h in heights),
        "type74_resonance_energy_eV_min": min(resonance_energies_eV) if resonance_energies_eV else None,
        "type74_resonance_energy_eV_max": max(resonance_energies_eV) if resonance_energies_eV else None,
        "radiation_field_mode": mode,
        "radiation_bremsa_scale": bscale_ctx,
        "radiation_powerlaw_index": powerlaw_ctx,
        "radiation_grid_min_eV": min(grid) if grid else None,
        "radiation_grid_max_eV": max(grid) if grid else None,
        "provenance": "v0.3.57_source_aligned_calt74_rate_alpha_diagnostic",
    }


def _xstar_calt74_alpha_diagnostic(temperature: float, reals: Sequence[float]) -> dict:
    """Backward-compatible wrapper for the older alpha-only diagnostic name."""
    ev = _xstar_calt74_rate_alpha_diagnostic(temperature, reals, radiation_context_rows=[])
    # Preserve the old status/key names used by existing type-74 source audits.
    out = dict(ev)
    if str(out.get("type74_calt74_status", "")).startswith("evaluated"):
        out["type74_eval_status"] = "evaluated_type74_calt74_dr_alpha_diagnostic"
    else:
        out["type74_eval_status"] = out.get("type74_calt74_status")
    out["type74_xt_coeff_preview"] = out.get("type74_xt_coeff")
    out["type74_delta_terms_used"] = out.get("type74_delta_terms_alpha_used")
    out["type74_delta_terms_skipped_arg_ge_40"] = out.get("type74_delta_terms_alpha_skipped_arg_ge_40")
    return out


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


def build_xstar_matrix_topology_audit_rows(
    global_index_rows: Sequence[dict],
    *,
    stages: Optional[Sequence[int]] = None,
) -> List[dict]:
    """Audit current explicit global-index topology against XSTAR element indexing.

    The visible XSTAR ``calc_hmc_element.f90`` element assembly advances the
    matrix pointer by ``nlev-1`` for each ion.  In that topology the continuum
    level of an ion is not an independent extra population; it represents the
    next ion's ground state.  The same routine also assigns the ion ground to
    one ``nsup`` group and the spectroscopic excited levels ``2..nlev-1`` to a
    shared excited superlevel before the Lucy solve.

    This audit is intentionally topology-only.  It does not alter the current
    Python global index, matrix assembly, or solver.  It records which current
    rows would be kept, aliased, or condensed by the XSTAR-style topology.
    """
    rows: List[dict] = []
    if not global_index_rows:
        return [{
            "audit_kind": "xstar_matrix_topology_summary",
            "status": "no_global_index_rows",
            "provenance": "v0.3.76_xstar_element_matrix_topology_audit",
        }]

    by_stage: Dict[int, List[dict]] = {}
    by_stage_level: Dict[tuple[int, int], dict] = {}
    by_global: Dict[int, dict] = {}
    for r in global_index_rows:
        stage = maybe_int(r.get("ion_stage"))
        gi = maybe_int(r.get("global_index"))
        li = maybe_int(r.get("level_index"))
        if gi is not None:
            by_global[int(gi)] = r
        if stage is None:
            continue
        by_stage.setdefault(int(stage), []).append(r)
        if li is not None:
            by_stage_level[(int(stage), int(li))] = r

    stage_order = [int(s) for s in (stages or sorted(by_stage, reverse=True)) if int(s) in by_stage]
    if not stage_order:
        stage_order = sorted(by_stage, reverse=True)

    # Conceptual XSTAR ipmat scaffold: each ion contributes nlev-1 new slots.
    # The final continuum level is marked as an alias to the next ion ground
    # when that parent ground is present in the current adjacent-stage model.
    ipmat_start_by_stage: Dict[int, int] = {}
    xstar_slot_by_stage_level: Dict[tuple[int, int], int] = {}
    ipmat = 0
    stage_counts: Dict[int, dict] = {}
    for stage in stage_order:
        stage_rows = list(by_stage.get(stage, []))
        real_levels = [r for r in stage_rows if maybe_int(r.get("level_index")) is not None and not bool(r.get("is_parent_continuum_placeholder"))]
        level_indices = sorted({int(maybe_int(r.get("level_index"))) for r in real_levels if maybe_int(r.get("level_index")) is not None})
        nlev = max(level_indices) if level_indices else 0
        ipmat_start_by_stage[stage] = ipmat
        for li in level_indices:
            if nlev > 0 and li == nlev and (stage + 1, 1) in by_stage_level:
                # Continuum of this ion represents the next ion ground.
                parent = by_stage_level.get((stage + 1, 1))
                parent_g = maybe_int(parent.get("global_index")) if parent else None
                # Use the current parent global index for audit readability;
                # XSTAR's condensed slot number is listed separately.
                xstar_slot_by_stage_level[(stage, li)] = int(parent_g) if parent_g is not None else ipmat + max(0, li - 1)
            else:
                xstar_slot_by_stage_level[(stage, li)] = ipmat + max(0, li - 1)
        stage_counts[stage] = {
            "n_current_rows": len(stage_rows),
            "n_real_level_rows": len(real_levels),
            "nlev_inferred_max_level_index": nlev,
            "xstar_ipmat_start": ipmat,
            "xstar_ipmat_increment_nlev_minus_1": max(0, nlev - 1),
            "has_parent_stage_ground_for_continuum_alias": bool((stage + 1, 1) in by_stage_level),
        }
        ipmat += max(0, nlev - 1)

    group_members: Dict[str, List[int]] = {}
    def _add_group(label: str, gi: Optional[int]) -> None:
        if gi is None:
            return
        group_members.setdefault(label, []).append(int(gi))

    # First pass: assign XSTAR group labels.
    per_row_info: Dict[int, dict] = {}
    for r in sorted(global_index_rows, key=lambda rr: maybe_int(rr.get("global_index")) if maybe_int(rr.get("global_index")) is not None else 10**9):
        gi = maybe_int(r.get("global_index"))
        stage = maybe_int(r.get("ion_stage"))
        li = maybe_int(r.get("level_index"))
        if gi is None or stage is None:
            continue
        stage = int(stage)
        li_val = int(li) if li is not None else None
        nlev = int(stage_counts.get(stage, {}).get("nlev_inferred_max_level_index") or 0)
        parent_stage = maybe_int(r.get("parent_ion_stage"))
        parent_row = by_stage_level.get((int(parent_stage), 1)) if parent_stage is not None else None
        parent_g = maybe_int(parent_row.get("global_index")) if parent_row else None
        parent_label = parent_row.get("level_label") if parent_row else ""
        is_cont = bool(r.get("is_continuum")) or str(r.get("level_kind") or "").lower() == "continuum"
        is_placeholder = bool(r.get("is_parent_continuum_placeholder"))
        if is_placeholder:
            role = "python_parent_continuum_placeholder_not_xstar_independent_row"
            group = f"stage{parent_stage}:ground_alias_from_placeholder" if parent_stage is not None else "placeholder_unmapped"
            alias_g = parent_g
            condensed = True
            kept = False
        elif is_cont and parent_g is not None:
            role = "continuum_level_alias_to_parent_ion_ground"
            group = f"stage{parent_stage}:ground"
            alias_g = parent_g
            condensed = True
            kept = False
        elif li_val == 1:
            role = "ion_ground_independent_nsup_group"
            group = f"stage{stage}:ground"
            alias_g = gi
            condensed = False
            kept = True
        elif li_val is not None and nlev > 0 and li_val < nlev:
            role = "excited_spectroscopic_level_in_shared_nsup_group"
            group = f"stage{stage}:excited_levels_2_to_nlev_minus_1"
            alias_g = ""
            condensed = True
            kept = False
        elif li_val is not None:
            # Last level without an adjacent parent available, or an unusual row.
            role = "last_level_without_parent_alias_or_unmapped"
            group = f"stage{stage}:last_or_unmapped"
            alias_g = gi
            condensed = False
            kept = True
        else:
            role = "unmapped_noninteger_level_index"
            group = f"stage{stage}:unmapped"
            alias_g = ""
            condensed = False
            kept = True
        _add_group(group, int(gi))
        per_row_info[int(gi)] = {
            "xstar_matrix_role": role,
            "xstar_nsup_group_label": group,
            "xstar_alias_current_global_index": alias_g,
            "xstar_would_keep_as_independent_population_row": kept,
            "xstar_would_condense_or_alias_current_row": condensed,
            "parent_ground_current_global_index": parent_g if parent_g is not None else "",
            "parent_ground_label": parent_label,
            "xstar_conceptual_slot_or_alias": xstar_slot_by_stage_level.get((stage, li_val), "") if li_val is not None else "",
        }

    for r in sorted(global_index_rows, key=lambda rr: maybe_int(rr.get("global_index")) if maybe_int(rr.get("global_index")) is not None else 10**9):
        gi = maybe_int(r.get("global_index"))
        stage = maybe_int(r.get("ion_stage"))
        li = maybe_int(r.get("level_index"))
        if gi is None:
            continue
        info = per_row_info.get(int(gi), {})
        group = str(info.get("xstar_nsup_group_label") or "")
        members = group_members.get(group, [])
        rows.append({
            "audit_kind": "xstar_matrix_topology_row",
            "current_global_index": int(gi),
            "element": r.get("element"),
            "ion_stage": stage if stage is not None else "",
            "ion_roman": r.get("ion_roman"),
            "level_index": li if li is not None else "",
            "level_kind": r.get("level_kind"),
            "level_label": r.get("level_label"),
            "configuration": r.get("configuration"),
            "is_continuum": bool(r.get("is_continuum")),
            "continuum_represents_parent": bool(r.get("continuum_represents_parent")),
            "parent_ion_stage": r.get("parent_ion_stage"),
            "parent_level_index": r.get("parent_level_index"),
            "parent_ground_current_global_index": info.get("parent_ground_current_global_index", ""),
            "parent_ground_label": info.get("parent_ground_label", ""),
            "current_python_lucy_condensed_key": f"({stage},{r.get('level_kind')},{gi})",
            "current_python_explicit_row_status": "independent_current_global_row",
            "xstar_source_ipmat_rule": "calc_hmc_element.f90 advances ipmat by nlev-1, so ion continuum aliases the next ion ground",
            "xstar_source_nsup_rule": "calc_hmc_element.f90 assigns level 1 to one nsup group and levels 2..nlev-1 to a shared excited nsup group",
            "xstar_matrix_role": info.get("xstar_matrix_role", ""),
            "xstar_conceptual_slot_or_alias": info.get("xstar_conceptual_slot_or_alias", ""),
            "xstar_alias_current_global_index": info.get("xstar_alias_current_global_index", ""),
            "xstar_nsup_group_label": group,
            "xstar_nsup_group_size_current_rows": len(members),
            "xstar_nsup_group_member_global_indices": ";".join(str(x) for x in members),
            "xstar_would_keep_as_independent_population_row": bool(info.get("xstar_would_keep_as_independent_population_row", False)),
            "xstar_would_condense_or_alias_current_row": bool(info.get("xstar_would_condense_or_alias_current_row", False)),
            "diagnostic_consequence": "current_explicit_topology_may_overresolve_excited_other_levels_and_duplicate_parent_continuum" if bool(info.get("xstar_would_condense_or_alias_current_row", False)) else "current_row_matches_or_approximates_an_xstar_independent_group",
            "provenance": "v0.3.76_xstar_element_matrix_topology_audit",
        })

    for stage in stage_order:
        stage_rows = [r for r in global_index_rows if maybe_int(r.get("ion_stage")) == stage]
        c = stage_counts.get(stage, {})
        n_condense = sum(1 for r in stage_rows if per_row_info.get(int(maybe_int(r.get("global_index")) or -1), {}).get("xstar_would_condense_or_alias_current_row"))
        n_keep = sum(1 for r in stage_rows if per_row_info.get(int(maybe_int(r.get("global_index")) or -1), {}).get("xstar_would_keep_as_independent_population_row"))
        n_excited = sum(1 for r in stage_rows if per_row_info.get(int(maybe_int(r.get("global_index")) or -1), {}).get("xstar_matrix_role") == "excited_spectroscopic_level_in_shared_nsup_group")
        n_alias = sum(1 for r in stage_rows if "alias" in str(per_row_info.get(int(maybe_int(r.get("global_index")) or -1), {}).get("xstar_matrix_role")))
        rows.append({
            "audit_kind": "xstar_matrix_topology_stage_summary",
            "ion_stage": stage,
            "ion_roman": roman(stage),
            "n_current_global_rows_for_stage": len(stage_rows),
            "n_real_level_rows": c.get("n_real_level_rows", ""),
            "nlev_inferred_max_level_index": c.get("nlev_inferred_max_level_index", ""),
            "xstar_ipmat_start": c.get("xstar_ipmat_start", ""),
            "xstar_ipmat_increment_nlev_minus_1": c.get("xstar_ipmat_increment_nlev_minus_1", ""),
            "n_rows_xstar_would_keep_independent": n_keep,
            "n_rows_xstar_would_condense_or_alias": n_condense,
            "n_excited_rows_in_shared_nsup_group": n_excited,
            "n_continuum_or_placeholder_alias_rows": n_alias,
            "has_parent_stage_ground_for_continuum_alias": c.get("has_parent_stage_ground_for_continuum_alias", ""),
            "diagnostic_note": "XSTAR topology has far fewer independent groups than the current explicit Python global-index rows for this ion.",
            "provenance": "v0.3.76_xstar_element_matrix_topology_audit",
        })

    total_current = len(global_index_rows)
    total_keep = sum(1 for info in per_row_info.values() if info.get("xstar_would_keep_as_independent_population_row"))
    total_condense = sum(1 for info in per_row_info.values() if info.get("xstar_would_condense_or_alias_current_row"))
    excited_groups = sorted({str(info.get("xstar_nsup_group_label")) for info in per_row_info.values() if "excited_levels" in str(info.get("xstar_nsup_group_label"))})
    alias_rows = [gi for gi, info in per_row_info.items() if "alias" in str(info.get("xstar_matrix_role"))]
    rows.append({
        "audit_kind": "xstar_matrix_topology_summary",
        "n_current_global_index_rows": total_current,
        "n_current_rows_xstar_would_keep_independent": total_keep,
        "n_current_rows_xstar_would_condense_or_alias": total_condense,
        "n_xstar_excited_nsup_groups_detected": len(excited_groups),
        "xstar_excited_nsup_group_labels": ";".join(excited_groups),
        "n_continuum_alias_or_placeholder_rows_detected": len(alias_rows),
        "continuum_alias_or_placeholder_global_indices": ";".join(str(x) for x in sorted(alias_rows)),
        "primary_hypothesis": "remaining_f_over_r_mismatch_may_come_from_current_explicit_topology_overresolving_excited_other_levels_and_not_aliasing_continuum_to_parent_ground_like_xstar",
        "xstar_source_reference": "calc_hmc_element.f90 ipmat=ipmat+nlev-1 and nsup(mm+ipmat2)=nsp for mm=2..nlev-1",
        "behavior_change": "audit_only_no_solver_or_matrix_change",
        "provenance": "v0.3.76_xstar_element_matrix_topology_audit",
    })
    return rows


def _xstar_matrix_topology_audit_summary(rows: Sequence[dict]) -> dict:
    summary = next((r for r in rows if r.get("audit_kind") == "xstar_matrix_topology_summary"), {})
    stage_rows = [r for r in rows if r.get("audit_kind") == "xstar_matrix_topology_stage_summary"]
    return {
        "n_xstar_matrix_topology_audit_rows": len(rows),
        "n_topology_row_records": sum(1 for r in rows if r.get("audit_kind") == "xstar_matrix_topology_row"),
        "n_stage_summary_rows": len(stage_rows),
        "n_current_global_index_rows": summary.get("n_current_global_index_rows", ""),
        "n_current_rows_xstar_would_keep_independent": summary.get("n_current_rows_xstar_would_keep_independent", ""),
        "n_current_rows_xstar_would_condense_or_alias": summary.get("n_current_rows_xstar_would_condense_or_alias", ""),
        "n_xstar_excited_nsup_groups_detected": summary.get("n_xstar_excited_nsup_groups_detected", ""),
        "n_continuum_alias_or_placeholder_rows_detected": summary.get("n_continuum_alias_or_placeholder_rows_detected", ""),
        "primary_hypothesis": summary.get("primary_hypothesis", ""),
        "provenance": "v0.3.76_xstar_element_matrix_topology_audit",
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



def _normalise_type50_bound_bound_treatment(value: object) -> str:
    """Return a supported v0.3.67 type-50 bound-bound treatment string."""
    text = str(value or "raw-A").strip().lower().replace("_", "-")
    aliases = {
        "": "raw-A",
        "none": "raw-A",
        "default": "raw-A",
        "raw": "raw-A",
        "raw-a": "raw-A",
        "raw-A": "raw-A",
        "xstar-escape": "xstar-escape",
        "escape": "xstar-escape",
        "xstar-escape-photoexcitation": "xstar-escape-photoexcitation",
        "escape-photoexcitation": "xstar-escape-photoexcitation",
        "photoexcitation": "xstar-escape-photoexcitation",
    }
    if text not in aliases:
        raise ValueError(f"Unsupported type-50 bound-bound treatment {value!r}")
    return aliases[text]


def _bounded_nonnegative_float(value: object, default: float = 0.0) -> float:
    val = maybe_float(value)
    if val is None or not math.isfinite(float(val)):
        return float(default)
    return max(0.0, float(val))


def _infer_transition_data_type(row: Mapping[str, object]) -> Optional[int]:
    data_type = maybe_int(row.get("data_type"))
    if data_type is not None:
        return int(data_type)
    text = str(row.get("source_method") or "")
    if "data_type_" in text:
        try:
            return int(text.split("data_type_", 1)[1].split("_", 1)[0])
        except Exception:
            return None
    return None


def _is_type50_radiative_transition(row: Mapping[str, object]) -> bool:
    return str(row.get("kind") or row.get("transition_kind") or "") == "radiative_decay" and _infer_transition_data_type(row) == 50


def _type50_effective_rates(
    row: Mapping[str, object],
    *,
    treatment: str,
    escape_factor: object = 1.0,
    photoexcitation_scale: object = 0.0,
) -> dict:
    """Return controlled v0.3.67 XSTAR-ucalc-style type-50 rate proxies.

    XSTAR's ``ucalc`` type-50 branch does not pass a raw A-value directly to
    the population matrix.  It forms an escaped downward rate roughly
    ``A*(ptmp1+ptmp2)`` and an upward radiation-field pumping term.  This helper
    keeps the default ``raw-A`` behavior unchanged while exposing a controlled
    diagnostic treatment for testing the impact of escape and pumping.
    """
    treatment_norm = _normalise_type50_bound_bound_treatment(treatment)
    raw_a = _bounded_nonnegative_float(row.get("rate_s^-1"), 0.0)
    user_escape = _bounded_nonnegative_float(escape_factor, 1.0)
    user_escape = min(user_escape, 1.0)
    # In the absence of a ported optical-depth/escape calculation, split the
    # user-supplied total escape factor equally into the two XSTAR fline channels.
    ptmp1 = 0.5 * user_escape
    ptmp2 = 0.5 * user_escape
    ptmp_sum = ptmp1 + ptmp2
    if treatment_norm == "raw-A" or not _is_type50_radiative_transition(row):
        decay = raw_a
        ptmp1 = 0.5
        ptmp2 = 0.5
        ptmp_sum = 1.0
        pumping = 0.0
    else:
        decay = raw_a * ptmp_sum
        pumping_scale = _bounded_nonnegative_float(photoexcitation_scale, 0.0)
        pumping = raw_a * pumping_scale if treatment_norm == "xstar-escape-photoexcitation" else 0.0
    return {
        "type50_bound_bound_treatment": treatment_norm,
        "raw_A_s^-1": raw_a,
        "ptmp1_proxy": ptmp1,
        "ptmp2_proxy": ptmp2,
        "ptmp_sum_proxy": ptmp_sum,
        "escaped_decay_rate_s^-1": decay,
        "photoexcitation_rate_s^-1": pumping,
        "decay_rate_multiplier_vs_raw_A": (decay / raw_a) if raw_a > 0 else None,
        "photoexcitation_rate_multiplier_vs_raw_A": (pumping / raw_a) if raw_a > 0 else None,
        "ucalc_ans1_matrix_lower_to_upper_proxy_s^-1": pumping,
        "ucalc_ans2_matrix_upper_to_lower_proxy_s^-1": decay,
        "ucalc_context_status": "raw_A_default" if treatment_norm == "raw-A" else "diagnostic_escape_proxy_no_real_tau_or_bremsa_line_integral",
    }

def build_global_bound_bound_matrix_terms(
    transition_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
    *,
    type50_bound_bound_treatment: str = "raw-A",
    type50_escape_factor: object = 1.0,
    type50_photoexcitation_scale: object = 0.0,
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
        type50_rates = _type50_effective_rates(
            tr,
            treatment=type50_bound_bound_treatment,
            escape_factor=type50_escape_factor,
            photoexcitation_scale=type50_photoexcitation_scale,
        )
        effective_rate = float(type50_rates["escaped_decay_rate_s^-1"]) if _is_type50_radiative_transition(tr) else float(rate)
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
                "rate_s^-1": effective_rate,
                "raw_rate_s^-1": float(rate),
                "signed_rate_s^-1": 0.0,
                **type50_rates,
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
            "rate_s^-1": effective_rate,
            "raw_rate_s^-1": float(rate),
            **type50_rates,
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
            "signed_rate_s^-1": effective_rate,
            **common,
        })
        term_id += 1
        out.append({
            "global_term_id": term_id,
            "matrix_term_kind": "diagonal_loss",
            "matrix_role": "bound_bound_loss_from_source",
            "matrix_row_global_index": from_g,
            "matrix_col_global_index": from_g,
            "signed_rate_s^-1": -effective_rate,
            **common,
        })
        term_id += 1
        if _is_type50_radiative_transition(tr) and str(type50_rates.get("type50_bound_bound_treatment")) == "xstar-escape-photoexcitation":
            pump_rate = float(type50_rates.get("photoexcitation_rate_s^-1") or 0.0)
            if pump_rate > 0.0:
                pump_common = dict(common)
                pump_common.update({
                    "transition_kind": "radiative_photoexcitation",
                    "from_level": int(to_level),
                    "to_level": int(from_level),
                    "from_global_index": to_g,
                    "to_global_index": from_g,
                    "from_level_label": to_row.get("level_label"),
                    "to_level_label": from_row.get("level_label"),
                    "from_level_kind": to_row.get("level_kind"),
                    "to_level_kind": from_row.get("level_kind"),
                    "rate_s^-1": pump_rate,
                    "matrix_safe_to_solve_physically": False,
                    "unsafe_reason": "diagnostic type-50 photoexcitation proxy; real XSTAR bremsa/flinabs line integral not yet ported",
                })
                out.append({
                    "global_term_id": term_id,
                    "matrix_term_kind": "offdiag_gain",
                    "matrix_role": "type50_photoexcitation_gain_to_upper_proxy",
                    "matrix_row_global_index": from_g,
                    "matrix_col_global_index": to_g,
                    "signed_rate_s^-1": pump_rate,
                    **pump_common,
                })
                term_id += 1
                out.append({
                    "global_term_id": term_id,
                    "matrix_term_kind": "diagonal_loss",
                    "matrix_role": "type50_photoexcitation_loss_from_lower_proxy",
                    "matrix_row_global_index": to_g,
                    "matrix_col_global_index": to_g,
                    "signed_rate_s^-1": -pump_rate,
                    **pump_common,
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
        "rows_by_type50_bound_bound_treatment": _counts(assembled, "type50_bound_bound_treatment"),
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
    radiation_bremsa_scale: object = 1.0,
    radiation_energy_min_eV: Optional[float] = None,
    radiation_energy_max_eV: Optional[float] = None,
    radiation_n_energy_grid: int = 256,
    radiation_powerlaw_index: float = 1.0,
) -> List[dict]:
    """Return an XSTAR-style diagnostic radiation/bremsa context.

    XSTAR passes ``epi`` and ``bremsa`` arrays to ``ucalc``, ``phint53`` and
    ``calt74``.  This context is still diagnostic, but v0.3.58 makes the
    arrays explicit, configurable, and consistently reused by the type-53 and
    type-74 kernels.
    """
    mode = str(radiation_field_mode or "none").strip().lower()
    if mode not in {"none", "flat", "blackbody", "table", "powerlaw", "xstar-powerlaw"}:
        mode = "none"
    try:
        bscale = float(radiation_bremsa_scale)
    except Exception:
        bscale = 1.0
    if not math.isfinite(bscale):
        bscale = 1.0
    try:
        alpha = float(radiation_powerlaw_index)
    except Exception:
        alpha = 1.0
    if not math.isfinite(alpha):
        alpha = 1.0
    has_grid = mode != "none"
    if has_grid:
        energy_min_ev = float(radiation_energy_min_eV) if radiation_energy_min_eV is not None else 1.0
        energy_max_ev = float(radiation_energy_max_eV) if radiation_energy_max_eV is not None else 1.0e5
        if not math.isfinite(energy_min_ev) or energy_min_ev <= 0.0:
            energy_min_ev = 1.0
        if not math.isfinite(energy_max_ev) or energy_max_ev <= energy_min_ev:
            energy_max_ev = 1.0e5
        n_energy_grid_points = max(int(radiation_n_energy_grid or 256), 8)
        grid_status = "explicit_log_epi_grid_for_diagnostic_bremsa"
        grid = _log_energy_grid(energy_min_ev, energy_max_ev, n_energy_grid_points)
        bremsa = [_placeholder_bremsa_value(e, mode=mode, temperature_K=temperature, bremsa_scale=bscale, powerlaw_index=alpha) for e in grid]
        bremsint = _bremsint_from_grid(grid, bremsa)
        total_bremsa_energy_flux = _trapz(grid, bremsa)
        total_bremsa_over_E = _trapz(grid, [b / max(e, 1.0e-300) for e, b in zip(grid, bremsa)])
    else:
        energy_min_ev = None
        energy_max_ev = None
        n_energy_grid_points = 0
        grid_status = "not_constructed_radiation_field_mode_none"
        grid = []
        bremsa = []
        bremsint = []
        total_bremsa_energy_flux = 0.0
        total_bremsa_over_E = 0.0
    return [{
        "row_kind": "radiation_context",
        "radiation_context_version": "v0.3.58",
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
        "radiation_bremsa_scale": bscale,
        "radiation_powerlaw_index": alpha,
        "bremsa_units_assumed": "erg_s^-1_cm^-2_erg^-1_as_expected_by_XSTAR_phint53_calt74",
        "bremsint_status": "computed_cumulative_integral_from_each_epi_bin_to_grid_max" if has_grid else "not_available",
        "total_bremsa_integral_over_eV_grid": total_bremsa_energy_flux,
        "total_bremsa_over_E_integral": total_bremsa_over_E,
        "bremsa_min": min(bremsa) if bremsa else None,
        "bremsa_max": max(bremsa) if bremsa else None,
        "bremsa_mean": (sum(bremsa) / len(bremsa)) if bremsa else None,
        "bremsint_min": min(bremsint) if bremsint else None,
        "bremsint_max": max(bremsint) if bremsint else None,
        "mean_intensity_status": "not_available" if mode == "none" else "diagnostic_bremsa_array_available_not_full_XSTAR_transfer",
        "photon_flux_status": "not_available" if mode == "none" else "diagnostic_bremsa_over_E_available",
        "photoionization_integral_status": "phint53_forward_kernel_uses_this_bremsa_grid" if has_grid else "not_evaluated_no_radiation_field",
        "milne_inverse_recombination_status": "diagnostic_inverse_topology_only_real_milne_pending",
        "opacity_escape_probability_status": "not_available",
        "assembly_status": "radiation_bremsa_context_used_by_diagnostic_kernels",
        "warning": "v0.3.58 improves epi/bremsa bookkeeping and normalization controls, but this is still not the full XSTAR radiation-transfer bremsa context.",
        "provenance": "v0.3.58_xstar_style_bremsa_context",
    }]



def build_bremsa_context_rows(radiation_context_rows: Sequence[dict]) -> List[dict]:
    """Write the explicit diagnostic XSTAR-style epi/bremsa grid used by kernels."""
    if not radiation_context_rows:
        return []
    ctx = radiation_context_rows[0]
    mode = str(ctx.get("radiation_field_mode", "none"))
    if mode == "none":
        return []
    ngrid = maybe_int(ctx.get("n_energy_grid_points")) or 0
    emin = maybe_float(ctx.get("energy_min_eV"))
    emax = maybe_float(ctx.get("energy_max_eV"))
    temp = maybe_float(ctx.get("temperature_K")) or 1.0
    bscale = maybe_float(ctx.get("radiation_bremsa_scale")) or 1.0
    alpha = maybe_float(ctx.get("radiation_powerlaw_index")) or 1.0
    if ngrid < 2 or emin is None or emax is None or emax <= emin:
        return []
    grid = _log_energy_grid(float(emin), float(emax), int(ngrid))
    bremsa = [_placeholder_bremsa_value(e, mode=mode, temperature_K=float(temp), bremsa_scale=float(bscale), powerlaw_index=float(alpha)) for e in grid]
    bremsint = _bremsint_from_grid(grid, bremsa)
    rows: List[dict] = []
    for i, (e, b, bi) in enumerate(zip(grid, bremsa, bremsint), start=1):
        rows.append({
            "row_kind": "bremsa_context",
            "bremsa_context_version": "v0.3.58",
            "grid_index": i,
            "epi_eV": e,
            "bremsa_erg_s^-1_cm^-2_erg^-1": b,
            "bremsint_cumulative_to_grid_max": bi,
            "bremsa_over_E": b / max(e, 1.0e-300),
            "radiation_field_mode": mode,
            "radiation_bremsa_scale": bscale,
            "radiation_powerlaw_index": alpha,
            "temperature_K": temp,
            "provenance": "v0.3.58_explicit_xstar_style_epi_bremsa_grid",
        })
    return rows


def _bremsa_context_summary(rows: Sequence[dict]) -> dict:
    return {
        "n_bremsa_context_rows": len(rows),
        "radiation_field_mode_counts": _counts(rows, "radiation_field_mode"),
        "energy_min_eV": min([maybe_float(r.get("epi_eV")) or float("inf") for r in rows], default=None),
        "energy_max_eV": max([maybe_float(r.get("epi_eV")) or 0.0 for r in rows], default=None),
        "bremsa_min": min([maybe_float(r.get("bremsa_erg_s^-1_cm^-2_erg^-1")) or 0.0 for r in rows], default=None),
        "bremsa_max": max([maybe_float(r.get("bremsa_erg_s^-1_cm^-2_erg^-1")) or 0.0 for r in rows], default=None),
    }

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
            "type53_raw_reals_full": ar.get("type53_raw_reals_full"),
            "type53_raw_ints_full": ar.get("type53_raw_ints_full"),
            "type53_nreal_full": ar.get("type53_nreal_full"),
            "type53_nint_full": ar.get("type53_nint_full"),
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



def _type53_cross_section_pairs_from_reals(value: object) -> tuple[List[float], List[float]]:
    """Decode type-53 rdat pairs as (energy above threshold in Ry, sigma in cm^2).

    XSTAR's ucalc type-53 branch uses rdat pairs as::

        etmpp(k) = rdat(2*k-1)                # Ry above threshold
        stmpp(k) = max(rdat(2*k), 0) * 1e-18 # Mb -> cm^2

    This helper accepts the full stored real list when available and falls back
    to the preview list for dry/incomplete audits.
    """
    vals = _parse_preview_numbers(value)
    n = len(vals) // 2
    if n <= 0:
        return [], []
    e_ry: List[float] = []
    sigma_cm2: List[float] = []
    for i in range(n):
        e = maybe_float(vals[2 * i])
        sig_mb = maybe_float(vals[2 * i + 1])
        if e is None or sig_mb is None:
            continue
        if not (math.isfinite(e) and math.isfinite(sig_mb)):
            continue
        e_ry.append(float(e))
        sigma_cm2.append(max(float(sig_mb), 0.0) * 1.0e-18)
    return e_ry, sigma_cm2

def _type53_cross_section_pairs_mb_from_reals(value: object) -> tuple[List[float], List[float]]:
    """Decode type-53 rdat pairs as (energy above threshold in Ry, sigma in Mb).

    This keeps the cross section in the same units passed to XSTAR's
    ``milne.f90`` source-code validation path.  The normal phint53 helper above
    converts the same values to cm^2 because ``phint53.f90`` receives ``stmpp``
    after ``ucalc.f90`` multiplies the raw Mb value by ``1.d-18``.
    """
    vals = _parse_preview_numbers(value)
    n = len(vals) // 2
    if n <= 0:
        return [], []
    e_ry: List[float] = []
    sigma_mb: List[float] = []
    for i in range(n):
        e = maybe_float(vals[2 * i])
        sig_mb = maybe_float(vals[2 * i + 1])
        if e is None or sig_mb is None:
            continue
        if not (math.isfinite(e) and math.isfinite(sig_mb)):
            continue
        e_ry.append(float(e))
        sigma_mb.append(max(float(sig_mb), 0.0))
    return e_ry, sigma_mb


def _xstar_milne_intin(x1: float, x2: float, x0: float, temperature_K: float) -> tuple[float, float]:
    """Python port of XSTAR ``intin.f90`` for the ``milne.f90`` audit."""
    ryk = 7.2438e15
    temp = max(float(temperature_K), 1.0e-300)
    s1 = float(x1) * ryk / temp
    s2 = float(x2) * ryk / temp
    s0 = float(x0) * ryk / temp
    delt = ryk / temp
    if delt <= 0.0 or not math.isfinite(delt):
        return 0.0, 0.0
    if (s1 - s0) < 90.0:
        try:
            ri2 = math.exp(s0 - s1) * ((s1 * s1 + 2.0 * s1 + 2.0) - math.exp(s1 - s2) * (s2 * s2 + 2.0 * s2 + 2.0)) / delt / math.sqrt(delt)
        except OverflowError:
            ri2 = 0.0
        if s0 < 1.0e-3 and s2 < 1.0e-3 and s1 < 1.0e-3:
            ri2 = 0.0
    else:
        ri2 = 0.0
    try:
        rr = math.exp(s0 - s1) * ((s1 ** 3) - math.exp(s1 - s2) * (s2 ** 3))
    except OverflowError:
        rr = 0.0
    ri3 = (rr / delt / math.sqrt(delt) + 3.0 * ri2) / delt
    if not math.isfinite(ri2):
        ri2 = 0.0
    if not math.isfinite(ri3):
        ri3 = 0.0
    return float(ri2), float(ri3)


def _evaluate_xstar_milne_f90_integral(*, e_ry: Sequence[float], sigma_mb: Sequence[float], threshold_ry: float, temperature_K: float) -> dict:
    """Evaluate the source-code ``milne.f90`` integral for type-53 data."""
    pairs = sorted((float(e), max(float(s), 0.0)) for e, s in zip(e_ry, sigma_mb) if math.isfinite(float(e)) and math.isfinite(float(s)))
    if len(pairs) < 2:
        return {"milne_f90_status": "not_evaluated_too_few_cross_section_pairs"}
    x = [p[0] for p in pairs]
    y = [p[1] for p in pairs]
    eth = maybe_float(threshold_ry)
    if eth is None or not math.isfinite(float(eth)) or float(eth) <= 0.0:
        return {"milne_f90_status": "not_evaluated_missing_or_bad_threshold_ry"}
    ry_erg = 2.17896e-11
    st = (x[0] + float(eth)) * ry_erg
    total = 0.0
    prev_total = 1.0
    crit = 0.01
    n_intervals = 0
    stopped_by_convergence = False
    for i in range(1, len(x)):
        if abs(total - prev_total) <= crit * abs(total) and i > 1:
            stopped_by_convergence = True
            break
        s1 = (x[i - 1] + float(eth)) * ry_erg
        s2 = (x[i] + float(eth)) * ry_erg
        if s2 < s1:
            return {"milne_f90_status": "not_evaluated_nonmonotonic_energy_grid"}
        v1 = y[i - 1]
        v2 = y[i]
        if v1 != 0.0 or v2 != 0.0:
            rb = (v2 - v1) / (s2 - s1 + 1.0e-24)
            ra = v2 - rb * s2
            ri2, ri3 = _xstar_milne_intin(s1, s2, st, temperature_K)
            prev_total = total
            total += ra * ri2 + rb * ri3
        n_intervals += 1
    alpha = total * 0.79788 * 40.4153
    if not math.isfinite(alpha):
        alpha = 0.0
    return {
        "milne_f90_status": "evaluated_source_code_milne_f90_integral",
        "milne_f90_threshold_ry": float(eth),
        "milne_f90_n_cross_section_pairs": len(x),
        "milne_f90_n_intervals_used": n_intervals,
        "milne_f90_stopping_rule": "converged_abs_delta_lt_0p01_sum" if stopped_by_convergence else "reached_end_of_cross_section_grid",
        "milne_f90_sum_integral": total,
        "milne_f90_alpha_cm3_s": max(float(alpha), 0.0),
        "milne_f90_source_file": "xstarlib/src/milne.f90",
        "milne_f90_intin_source_file": "xstarlib/src/intin.f90",
    }


def _evaluate_phint53_milne_ans2_integral(
    *,
    e_ry: Sequence[float],
    sigma_cm2: Sequence[float],
    threshold_eV: float,
    temperature_K: float,
    electron_density: float,
    bound_stat_weight: Optional[float],
    continuum_stat_weight: Optional[float],
    ptmp_sum: float = 1.0,
    n_energy_grid_points: int = 512,
) -> dict:
    """Evaluate the recombination-side integral used in ``phint53.f90``.

    This ports the source-code terms contributing to ``rrrt``/``ans2``:
    ``rnist * bbnurjp * sigma(E) * exp[-(E-Eth)/kT] * 12.56/E``.
    ``rnist`` is reconstructed from available level weights; exact XSTAR
    ``ethion``/``emltlv`` arrays remain an explicitly reported approximation.
    """
    if not e_ry or not sigma_cm2 or len(e_ry) != len(sigma_cm2):
        return {"phint53_milne_ans2_status": "not_evaluated_missing_cross_section_pairs"}
    eth = maybe_float(threshold_eV)
    if eth is None or not math.isfinite(float(eth)) or float(eth) <= 0.0:
        return {"phint53_milne_ans2_status": "not_evaluated_missing_or_bad_threshold_eV"}
    gb = maybe_float(bound_stat_weight)
    gc = maybe_float(continuum_stat_weight)
    if gb is None or gc is None or gc <= 0.0:
        return {"phint53_milne_ans2_status": "not_evaluated_missing_statistical_weights"}
    pairs = sorted((float(eth) + max(float(e), 0.0) * 13.605692, max(float(s), 0.0)) for e, s in zip(e_ry, sigma_cm2) if math.isfinite(float(e)) and math.isfinite(float(s)))
    if len(pairs) < 2:
        return {"phint53_milne_ans2_status": "not_evaluated_too_few_cross_section_pairs"}
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    emin = max(float(eth), xs[0])
    emax = xs[-1]
    if emax <= emin:
        return {"phint53_milne_ans2_status": "not_evaluated_empty_energy_range"}
    ngrid = max(int(n_energy_grid_points or 0), 16)
    grid = _log_energy_grid(emin, emax, ngrid)
    kT_eV = 8.61707e-5 * max(float(temperature_K), 1.0e-300)
    q2 = 2.07e-16 * max(float(electron_density), 0.0) * (max(float(temperature_K), 1.0e-300) ** -1.5)
    rs = q2 / max(float(gc), 1.0e-300)
    rnist0 = float(gb) * rs
    first_edge_eV = max(0.0, float(e_ry[0]) * 13.605692)
    seed_exp = math.exp(-min(max(first_edge_eV / max(kT_eV, 1.0e-300), 0.0), 700.0))
    rnist = rnist0 * seed_exp
    total = 0.0
    cooling_eV = 0.0
    prev_e = grid[0]
    prev_sig = _interp_piecewise_linear_local(prev_e, xs, ys)
    prev_exp = math.exp(-min(max((prev_e - float(eth)) / max(kT_eV, 1.0e-300), 0.0), 700.0))
    prev_bbn = (min(2.0e4, prev_e) ** 3) * 1.571e22 * 2.0
    prev_y = rnist * prev_bbn * prev_sig * prev_exp * 12.56 / max(prev_e, 1.0e-300) * max(float(ptmp_sum), 0.0)
    prev_c = prev_y * prev_e
    used = 0
    for e in grid[1:]:
        sig = _interp_piecewise_linear_local(e, xs, ys)
        expfac = math.exp(-min(max((e - float(eth)) / max(kT_eV, 1.0e-300), 0.0), 700.0))
        bbn = (min(2.0e4, e) ** 3) * 1.571e22 * 2.0
        y = rnist * bbn * sig * expfac * 12.56 / max(e, 1.0e-300) * max(float(ptmp_sum), 0.0)
        c = y * e
        de = e - prev_e
        if de > 0.0:
            total += 0.5 * (prev_y + y) * de
            cooling_eV += 0.5 * (prev_c + c) * de
            used += 1
        prev_e, prev_y, prev_c = e, y, c
    return {
        "phint53_milne_ans2_status": "evaluated_source_code_phint53_rrrt_integral_with_reconstructed_rnist",
        "phint53_milne_threshold_eV": float(eth),
        "phint53_milne_n_energy_grid_points": ngrid,
        "phint53_milne_n_intervals_used": used,
        "phint53_milne_energy_min_eV": emin,
        "phint53_milne_energy_max_eV": emax,
        "phint53_milne_q2_saha_prefactor": q2,
        "phint53_milne_rnist_proxy_before_grid_edge_exp": rnist0,
        "phint53_milne_first_edge_exp_factor": seed_exp,
        "phint53_milne_rnist_proxy": rnist,
        "phint53_milne_ptmp_sum": max(float(ptmp_sum), 0.0),
        "phint53_milne_ans2_rrrt_s^-1": max(float(total), 0.0),
        "phint53_milne_rrcl_proxy_eV_s^-1": max(float(cooling_eV), 0.0),
        "phint53_milne_source_file": "xstarlib/src/phint53.f90",
        "phint53_milne_missing_context": "exact_ethion_ethtmp_and_emltlv_arrays;real_ptmp1_ptmp2_escape_probabilities;continuum_grid_binning_identical_to_XSTAR",
    }


def _log_energy_grid(emin: float, emax: float, n: int) -> List[float]:
    if n <= 1:
        return [float(emin), float(emax)]
    emin = max(float(emin), 1.0e-30)
    emax = max(float(emax), emin * 1.000001)
    l0 = math.log(emin)
    l1 = math.log(emax)
    return [math.exp(l0 + (l1 - l0) * i / (n - 1)) for i in range(n)]


def _interp_piecewise_linear_local(x: float, xs: Sequence[float], ys: Sequence[float]) -> float:
    if not xs or not ys or len(xs) != len(ys):
        return 0.0
    if x < xs[0] or x > xs[-1]:
        return 0.0
    if x == xs[-1]:
        return float(ys[-1])
    for i in range(len(xs) - 1):
        x0 = float(xs[i]); x1 = float(xs[i + 1])
        if x0 <= x <= x1:
            y0 = float(ys[i]); y1 = float(ys[i + 1])
            if abs(x1 - x0) <= 1.0e-300:
                return y0
            f = (x - x0) / (x1 - x0)
            return y0 + f * (y1 - y0)
    return 0.0


def _trapz(x: Sequence[float], y: Sequence[float]) -> float:
    total = 0.0
    for i in range(max(0, min(len(x), len(y)) - 1)):
        dx = float(x[i + 1]) - float(x[i])
        if dx > 0.0:
            total += 0.5 * (float(y[i]) + float(y[i + 1])) * dx
    return float(total)


def _bremsint_from_grid(grid: Sequence[float], bremsa: Sequence[float]) -> List[float]:
    """Return cumulative XSTAR-like bremsint from each bin to the high-energy edge."""
    n = min(len(grid), len(bremsa))
    out = [0.0 for _ in range(n)]
    running = 0.0
    for i in range(n - 2, -1, -1):
        dx = float(grid[i + 1]) - float(grid[i])
        if dx > 0.0:
            running += 0.5 * (float(bremsa[i]) + float(bremsa[i + 1])) * dx
        out[i] = running
    return out


def _placeholder_bremsa_value(
    energy_eV: float,
    *,
    mode: str,
    temperature_K: float,
    bremsa_scale: float = 1.0,
    powerlaw_index: float = 1.0,
) -> float:
    """Diagnostic continuum flux with XSTAR ``bremsa`` units.

    XSTAR expects ``bremsa`` in erg s^-1 cm^-2 erg^-1 on the ``epi`` energy
    grid.  The full XSTAR radiative-transfer continuum is not yet ported, but
    v0.3.58 makes the diagnostic array explicit and scalable so ``phint53`` and
    ``calt74`` use the same source-code-style input.
    """
    mode = str(mode or "none").lower()
    try:
        scale = float(bremsa_scale)
    except Exception:
        scale = 1.0
    if not math.isfinite(scale):
        scale = 1.0
    if mode == "none":
        return 0.0
    e = max(float(energy_eV), 1.0e-300)
    if mode == "blackbody":
        kT_eV = max(8.617333262e-5 * max(float(temperature_K), 1.0), 1.0e-30)
        x = max(e / kT_eV, 0.0)
        if x > 700.0:
            return 0.0
        # Normalized Planck-like shape; scale carries the absolute XSTAR bremsa units.
        shape = (e / max(kT_eV, 1.0e-300)) ** 3 / max(math.expm1(x), 1.0e-300)
        return scale * shape
    if mode in {"powerlaw", "xstar-powerlaw", "table"}:
        try:
            alpha = float(powerlaw_index)
        except Exception:
            alpha = 1.0
        if not math.isfinite(alpha):
            alpha = 1.0
        return scale * (e / 1000.0) ** (-alpha)
    # flat: constant XSTAR-style bremsa array value in erg s^-1 cm^-2 erg^-1.
    return scale


def _evaluate_type53_phint53_photoionization_kernel(
    *,
    e_ry: Sequence[float],
    sigma_cm2: Sequence[float],
    threshold_eV: float,
    radiation_mode: str,
    temperature_K: float,
    n_energy_grid_points: int,
    bremsa_scale: float = 1.0,
    powerlaw_index: float = 1.0,
    energy_min_eV: Optional[float],
    energy_max_eV: Optional[float],
) -> dict:
    """Evaluate the photoionization part of XSTAR phint53 diagnostically.

    This ports the forward photoionization integral used by XSTAR ``phint53``:
    the type-53 cross section is mapped onto the continuum grid and integrated
    with the same algebraic kernel, ``sigma(E) * bremsa(E) / E``.  The Milne
    inverse recombination, opacity/emissivity arrays, escape probabilities, and
    the real XSTAR radiation field are still pending.
    """
    if not e_ry or not sigma_cm2 or len(e_ry) != len(sigma_cm2):
        return {"phint53_status": "not_evaluated_missing_cross_section_pairs"}
    eth = maybe_float(threshold_eV)
    if eth is None or not math.isfinite(eth) or eth <= 0.0:
        return {"phint53_status": "not_evaluated_missing_or_bad_threshold_eV"}
    mode = str(radiation_mode or "none").lower()
    if mode == "none":
        return {"phint53_status": "not_evaluated_no_radiation_field"}
    energies = [eth + max(float(x), 0.0) * 13.605692 for x in e_ry]
    pairs = sorted((e, s) for e, s in zip(energies, sigma_cm2) if math.isfinite(e) and math.isfinite(s) and e > 0.0)
    if len(pairs) < 2:
        return {"phint53_status": "not_evaluated_too_few_cross_section_pairs"}
    xs = [p[0] for p in pairs]
    ys = [max(p[1], 0.0) for p in pairs]
    emin = max(float(energy_min_eV) if energy_min_eV else xs[0], xs[0])
    emax = min(float(energy_max_eV) if energy_max_eV else xs[-1], xs[-1])
    if emax <= emin:
        return {
            "phint53_status": "not_evaluated_energy_grid_outside_cross_section_range",
            "phint53_threshold_eV": eth,
            "phint53_cross_section_min_eV": xs[0],
            "phint53_cross_section_max_eV": xs[-1],
        }
    ngrid = max(int(n_energy_grid_points or 0), 8)
    grid = _log_energy_grid(emin, emax, ngrid)
    rate = 0.0
    heat_eVs = 0.0
    used = 0
    prev_e = grid[0]
    prev_sig = _interp_piecewise_linear_local(prev_e, xs, ys)
    prev_b = _placeholder_bremsa_value(prev_e, mode=mode, temperature_K=temperature_K, bremsa_scale=bremsa_scale, powerlaw_index=powerlaw_index)
    prev_y = prev_sig * prev_b / max(prev_e, 1.0e-300)
    prev_h = prev_y * max(prev_e - eth, 0.0)
    for e in grid[1:]:
        sig = _interp_piecewise_linear_local(e, xs, ys)
        b = _placeholder_bremsa_value(e, mode=mode, temperature_K=temperature_K, bremsa_scale=bremsa_scale, powerlaw_index=powerlaw_index)
        y = sig * b / max(e, 1.0e-300)
        h = y * max(e - eth, 0.0)
        de = e - prev_e
        if de > 0.0:
            rate += 0.5 * (prev_y + y) * de
            heat_eVs += 0.5 * (prev_h + h) * de
            used += 1
        prev_e, prev_y, prev_h = e, y, h
    return {
        "phint53_status": "evaluated_phint53_photoionization_kernel_with_placeholder_radiation",
        "phint53_threshold_eV": eth,
        "phint53_n_cross_section_pairs": len(xs),
        "phint53_cross_section_min_eV": xs[0],
        "phint53_cross_section_max_eV": xs[-1],
        "phint53_energy_grid_min_eV": emin,
        "phint53_energy_grid_max_eV": emax,
        "phint53_n_energy_grid_points": ngrid,
        "phint53_n_intervals_used": used,
        "phint53_photoionization_rate_s^-1": max(float(rate), 0.0),
        "phint53_photoheating_proxy_eV_s^-1": max(float(heat_eVs), 0.0),
        "phint53_radiation_field_status": "diagnostic_xstar_style_bremsa_context_not_full_transfer",
        "phint53_milne_status": "not_evaluated",
    }


def build_type53_phint53_rate_audit_rows(
    *,
    type53_rate_audit_rows: Sequence[dict],
    radiation_context_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
    temperature: float,
    type53_phint53_scale: object = 1.0,
) -> List[dict]:
    """Build first type-53 phint53 photoionization-kernel diagnostics."""
    scale_values = _parse_triplet_source_scales(type53_phint53_scale)
    scale = float(scale_values[0]) if scale_values else 1.0
    if not math.isfinite(scale):
        scale = 1.0
    ctx = radiation_context_rows[0] if radiation_context_rows else {}
    mode = str(ctx.get("radiation_field_mode", "none"))
    ngrid = maybe_int(ctx.get("n_energy_grid_points")) or 0
    emin = maybe_float(ctx.get("energy_min_eV"))
    emax = maybe_float(ctx.get("energy_max_eV"))
    bscale_ctx = maybe_float(ctx.get("radiation_bremsa_scale")) or 1.0
    powerlaw_ctx = maybe_float(ctx.get("radiation_powerlaw_index")) or 1.0
    by_g = {maybe_int(r.get("global_index")): r for r in global_index_rows if maybe_int(r.get("global_index")) is not None}
    rows: List[dict] = []
    for ar in type53_rate_audit_rows:
        full = ar.get("type53_raw_reals_full") or ar.get("raw_reals_preview")
        e_ry, sigma_cm2 = _type53_cross_section_pairs_from_reals(full)
        bg = maybe_int(ar.get("bound_global_index"))
        bound_row = by_g.get(bg) if bg is not None else None
        threshold = None
        if bound_row is not None:
            threshold = maybe_float(bound_row.get("binding_from_continuum_eV"))
            if threshold is None or threshold <= 0.0:
                threshold = maybe_float(bound_row.get("ionization_potential_eV"))
        eval_row = _evaluate_type53_phint53_photoionization_kernel(
            e_ry=e_ry,
            sigma_cm2=sigma_cm2,
            threshold_eV=float(threshold) if threshold is not None else float("nan"),
            radiation_mode=mode,
            temperature_K=temperature,
            n_energy_grid_points=ngrid,
            bremsa_scale=bscale_ctx,
            powerlaw_index=powerlaw_ctx,
            energy_min_eV=emin,
            energy_max_eV=emax,
        )
        rate0 = maybe_float(eval_row.get("phint53_photoionization_rate_s^-1")) or 0.0
        rate = scale * rate0
        cont_g = maybe_int(ar.get("continuum_or_parent_global_index"))
        safe = bg is not None and cont_g is not None and rate > 0.0
        rows.append({
            "row_kind": "type53_phint53_rate_audit",
            "type53_phint53_version": "v0.3.52",
            "record": ar.get("record"),
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "record_ion_stage": ar.get("record_ion_stage"),
            "target_ion_stage": ar.get("target_ion_stage"),
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "bound_level": ar.get("bound_level"),
            "bound_global_index": bg,
            "continuum_or_parent_global_index": cont_g,
            "radiation_field_mode": mode,
            "radiation_bremsa_scale": bscale_ctx,
            "radiation_powerlaw_index": powerlaw_ctx,
            "type53_phint53_scale": scale,
            "photoionization_rate_unscaled_s^-1": rate0,
            "photoionization_rate_s^-1": rate,
            "inverse_recombination_rate_s^-1": 0.0,
            "matrix_role_if_assembled": "M[continuum_or_parent,bound]+=phint53_photoionization_rate_and_M[bound,bound]-=phint53_photoionization_rate",
            "topology_safe_for_physical_matrix": safe,
            "matrix_safe_to_assemble_physically": safe,
            "assembly_status": "phint53_photoionization_kernel_evaluated_matrix_ready" if safe else "phint53_not_matrix_ready",
            "missing_physical_requirements": "milne_inverse_recombination_integral;real_xstar_radiation_field_bremsa;opacity_escape_probability_context",
            "warning": "forward_phint53_kernel_ported_but_radiation_field_is_placeholder_and_milne_is_not_evaluated",
            "provenance": "v0.3.52_type53_phint53_photoionization_kernel",
            **eval_row,
        })
    return rows


def build_global_type53_phint53_matrix_terms(type53_phint53_rate_audit_rows: Sequence[dict]) -> List[dict]:
    """Map evaluated type-53 phint53 photoionization rates onto global matrix triplets."""
    rows: List[dict] = []
    tid = 0
    for ar in type53_phint53_rate_audit_rows:
        bound_g = maybe_int(ar.get("bound_global_index"))
        cont_g = maybe_int(ar.get("continuum_or_parent_global_index"))
        rate = maybe_float(ar.get("photoionization_rate_s^-1")) or 0.0
        safe = bool(ar.get("topology_safe_for_physical_matrix")) and bound_g is not None and cont_g is not None and rate > 0.0
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
            "type53_phint53_scale": ar.get("type53_phint53_scale"),
            "phint53_status": ar.get("phint53_status"),
            "matrix_safe_to_assemble_physically": safe,
            "provenance": "v0.3.52_type53_phint53_matrix_topology",
        }
        if not safe:
            tid += 1
            rows.append({
                **base,
                "global_type53_phint53_term_id": tid,
                "row_kind": "global_type53_phint53_matrix_term",
                "matrix_term_kind": "skipped_phint53_photoionization",
                "matrix_role": "skipped_missing_mapping_or_zero_rate",
                "matrix_row_global_index": "",
                "matrix_col_global_index": "",
                "signed_rate_s^-1": "",
                "rate_s^-1": rate,
                "assembly_status": "skipped_phint53_topology_or_rate_incomplete",
                "skip_reason": "missing_bound_or_continuum_global_index_or_zero_rate",
            })
            continue
        tid += 1
        rows.append({
            **base,
            "global_type53_phint53_term_id": tid,
            "row_kind": "global_type53_phint53_matrix_term",
            "matrix_term_kind": "offdiag_bound_to_continuum_phint53_gain",
            "matrix_role": "M[continuum_or_parent_global_index,bound_global_index]+=phint53_photoionization_rate",
            "matrix_row_global_index": cont_g,
            "matrix_col_global_index": bound_g,
            "signed_rate_s^-1": rate,
            "rate_s^-1": rate,
            "assembly_status": "assembled_phint53_photoionization_kernel_topology",
            "skip_reason": "",
        })
        tid += 1
        rows.append({
            **base,
            "global_type53_phint53_term_id": tid,
            "row_kind": "global_type53_phint53_matrix_term",
            "matrix_term_kind": "diagonal_bound_phint53_photoionization_loss",
            "matrix_role": "M[bound_global_index,bound_global_index]-=phint53_photoionization_rate",
            "matrix_row_global_index": bound_g,
            "matrix_col_global_index": bound_g,
            "signed_rate_s^-1": -rate,
            "rate_s^-1": rate,
            "assembly_status": "assembled_phint53_photoionization_kernel_topology",
            "skip_reason": "",
        })
    return rows


def _type53_phint53_rate_audit_summary(rows: Sequence[dict]) -> dict:
    return {
        "n_type53_phint53_rate_audit_rows": len(rows),
        "phint53_status_counts": _counts(rows, "phint53_status"),
        "assembly_status_counts": _counts(rows, "assembly_status"),
        "radiation_field_mode_counts": _counts(rows, "radiation_field_mode"),
        "n_rows_matrix_safe": sum(1 for r in rows if bool(r.get("matrix_safe_to_assemble_physically"))),
        "total_phint53_photoionization_rate_s^-1": _sum_float(rows, "photoionization_rate_s^-1"),
        "max_phint53_photoionization_rate_s^-1": max([maybe_float(r.get("photoionization_rate_s^-1")) or 0.0 for r in rows] or [0.0]),
    }


def _global_type53_phint53_matrix_terms_summary(rows: Sequence[dict]) -> dict:
    return {
        "n_global_type53_phint53_matrix_term_rows": len(rows),
        "matrix_term_kind_counts": _counts(rows, "matrix_term_kind"),
        "assembly_status_counts": _counts(rows, "assembly_status"),
        "n_offdiag_phint53_gain_rows": sum(1 for r in rows if str(r.get("matrix_term_kind")) == "offdiag_bound_to_continuum_phint53_gain"),
        "n_diagonal_phint53_loss_rows": sum(1 for r in rows if str(r.get("matrix_term_kind")) == "diagonal_bound_phint53_photoionization_loss"),
        "total_phint53_rate_s^-1": _sum_float(rows, "rate_s^-1"),
    }


def build_radiation_normalization_audit_rows(
    *,
    radiation_context_rows: Sequence[dict],
    type53_phint53_rate_audit_rows: Sequence[dict],
    type53_phint53_scale: object = 1.0,
) -> List[dict]:
    """Audit placeholder radiation normalization used by the phint53 kernel."""
    ctx = radiation_context_rows[0] if radiation_context_rows else {}
    mode = str(ctx.get("radiation_field_mode", "none"))
    ngrid = maybe_int(ctx.get("n_energy_grid_points")) or 256
    emin = maybe_float(ctx.get("energy_min_eV")) or 1.0
    emax = maybe_float(ctx.get("energy_max_eV")) or 1.0e5
    temp = maybe_float(ctx.get("temperature_K")) or 1.0
    bscale_ctx = maybe_float(ctx.get("radiation_bremsa_scale")) or 1.0
    powerlaw_ctx = maybe_float(ctx.get("radiation_powerlaw_index")) or 1.0
    grid = _log_energy_grid(float(emin), float(emax), max(int(ngrid), 2))
    bremsa = [_placeholder_bremsa_value(e, mode=mode, temperature_K=float(temp), bremsa_scale=bscale_ctx, powerlaw_index=powerlaw_ctx) for e in grid]
    bremsint = _bremsint_from_grid(grid, bremsa)
    weighted = [b / max(e, 1.0e-300) for e, b in zip(grid, bremsa)]
    unscaled_total = _sum_float(type53_phint53_rate_audit_rows, "photoionization_rate_unscaled_s^-1")
    scaled_current_total = _sum_float(type53_phint53_rate_audit_rows, "photoionization_rate_s^-1")
    scales = _parse_triplet_source_scales(type53_phint53_scale)
    rows: List[dict] = []
    rows.append({
        "row_kind": "radiation_normalization_audit",
        "audit_case": "placeholder_radiation_context",
        "radiation_field_mode": mode,
        "n_energy_grid_points": len(grid),
        "energy_min_eV": min(grid) if grid else None,
        "energy_max_eV": max(grid) if grid else None,
        "temperature_K": temp,
        "radiation_bremsa_scale": bscale_ctx,
        "radiation_powerlaw_index": powerlaw_ctx,
        "bremsint_min": min(bremsint) if bremsint else None,
        "bremsint_max": max(bremsint) if bremsint else None,
        "bremsa_min_placeholder": min(bremsa) if bremsa else None,
        "bremsa_max_placeholder": max(bremsa) if bremsa else None,
        "bremsa_mean_placeholder": (sum(bremsa) / len(bremsa)) if bremsa else None,
        "bremsa_over_E_min_placeholder": min(weighted) if weighted else None,
        "bremsa_over_E_max_placeholder": max(weighted) if weighted else None,
        "bremsa_over_E_mean_placeholder": (sum(weighted) / len(weighted)) if weighted else None,
        "n_type53_phint53_rows": len(type53_phint53_rate_audit_rows),
        "n_phint53_evaluated_rows": sum(1 for r in type53_phint53_rate_audit_rows if str(r.get("phint53_status", "")).startswith("evaluated")),
        "total_unscaled_phint53_rate_s^-1": unscaled_total,
        "total_current_scaled_phint53_rate_s^-1": scaled_current_total,
        "type53_phint53_scale_values": ",".join(f"{float(x):g}" for x in scales),
        "radiation_normalization_status": "diagnostic_xstar_style_bremsa_grid_not_full_transfer",
        "warning": "The phint53 forward kernel now uses an explicit diagnostic epi/bremsa grid, but this is still not the full XSTAR radiation-transfer continuum.",
        "provenance": "v0.3.58_xstar_style_bremsa_normalization_audit",
    })
    for scale in scales:
        rows.append({
            "row_kind": "radiation_normalization_audit",
            "audit_case": "phint53_scale_factor",
            "radiation_field_mode": mode,
            "type53_phint53_scale": float(scale),
            "total_unscaled_phint53_rate_s^-1": unscaled_total,
            "total_scaled_phint53_rate_s^-1": unscaled_total * float(scale),
            "scale_needed_for_total_rate_1_s^-1": None if unscaled_total <= 0.0 else 1.0 / unscaled_total,
            "scale_needed_for_total_rate_1e2_s^-1": None if unscaled_total <= 0.0 else 1.0e2 / unscaled_total,
            "scale_needed_for_total_rate_1e4_s^-1": None if unscaled_total <= 0.0 else 1.0e4 / unscaled_total,
            "radiation_normalization_status": "scale_audit_only",
            "warning": "Scale rows multiply the placeholder-radiation phint53 kernel and are diagnostic only.",
            "provenance": "v0.3.54_type53_phint53_radiation_normalization_audit",
        })
    return rows


def _radiation_normalization_audit_summary(rows: Sequence[dict]) -> dict:
    scale_rows = [r for r in rows if str(r.get("audit_case")) == "phint53_scale_factor"]
    context = next((r for r in rows if str(r.get("audit_case")) == "placeholder_radiation_context"), {})
    return {
        "n_radiation_normalization_audit_rows": len(rows),
        "radiation_field_mode": context.get("radiation_field_mode"),
        "n_type53_phint53_rows": context.get("n_type53_phint53_rows"),
        "total_unscaled_phint53_rate_s^-1": context.get("total_unscaled_phint53_rate_s^-1"),
        "scale_values": [r.get("type53_phint53_scale") for r in scale_rows],
        "max_scaled_total_phint53_rate_s^-1": max([maybe_float(r.get("total_scaled_phint53_rate_s^-1")) or 0.0 for r in scale_rows], default=0.0),
        "warning": "Radiation normalization remains placeholder-only; use scale scan before porting the real XSTAR bremsa/radiation context.",
    }


def build_type53_phint53_scale_scan_rows(
    *,
    type53_rate_audit_rows: Sequence[dict],
    radiation_context_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
    global_bound_bound_matrix_terms: Sequence[dict],
    global_superlevel_cascade_matrix_terms: Sequence[dict],
    global_superlevel_source_matrix_terms: Sequence[dict],
    global_type53_flat_proxy_matrix_terms: Sequence[dict],
    coupling_rows: Sequence[dict],
    line_rows: Sequence[dict],
    he_like_stage: int,
    temperature: float,
    type53_phint53_scale: object = 1.0,
    inverse_recombination_mode: str = "none",
    type53_milne_scale: object = 1.0,
    type74_inverse_scale: object = 1.0,
    full_global_linear_solver: str = "xstar-lucy",
    full_global_rank_deficient_action: str = "svd",
    full_global_negative_population_action: str = "keep",
    full_global_prune_null_rate_levels: bool = True,
    full_global_topology: str = "explicit-current",
) -> List[dict]:
    """Scan diagnostic type-53 phint53 scale factors through the full-global solve."""
    scales = _parse_triplet_source_scales(type53_phint53_scale)
    rows: List[dict] = []
    target = _xstar_triplet_target(int(he_like_stage))
    if target is not None:
        rows.append({
            "row_kind": "type53_phint53_scale_scan",
            "scan_case": "xstar_target",
            "type53_phint53_scale": "target",
            "f_fraction": target["f"],
            "i_fraction": target["i"],
            "r_fraction": target["r"],
            "provenance": "v0.3.54_type53_phint53_scale_scan",
        })
    for scale in scales:
        audit = build_type53_phint53_rate_audit_rows(
            type53_rate_audit_rows=type53_rate_audit_rows,
            radiation_context_rows=radiation_context_rows,
            global_index_rows=global_index_rows,
            temperature=temperature,
            type53_phint53_scale=float(scale),
        )
        matrix_terms = build_global_type53_phint53_matrix_terms(audit)
        full_terms = build_full_global_matrix_terms(
            global_index_rows=global_index_rows,
            global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
            global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
            global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
            global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
            global_type53_phint53_matrix_terms=matrix_terms,
            coupling_rows=coupling_rows,
            he_like_stage=he_like_stage,
        )
        solve_rows = build_full_global_normalized_solve_comparison(
            global_index_rows=global_index_rows,
            full_global_matrix_terms=full_terms,
            line_rows=line_rows,
            he_like_stage=he_like_stage,
            linear_solver=full_global_linear_solver,
            rank_deficient_action=full_global_rank_deficient_action,
            negative_population_action=full_global_negative_population_action,
            prune_null_rate_levels=full_global_prune_null_rate_levels,
            full_global_topology=full_global_topology,
        )
        summary = next((r for r in solve_rows if str(r.get("row_kind")) == "summary" and str(r.get("comparison_case")) == "full_global_normalized_proxy_topology_solve"), {})
        rows.append({
            "row_kind": "type53_phint53_scale_scan",
            "scan_case": "full_global_xstar_lucy_phint53_scaled",
            "type53_phint53_scale": float(scale),
            "n_type53_phint53_rate_audit_rows": len(audit),
            "n_global_type53_phint53_matrix_term_rows": len(matrix_terms),
            "total_unscaled_phint53_rate_s^-1": _sum_float(audit, "photoionization_rate_unscaled_s^-1"),
            "total_scaled_phint53_rate_s^-1": _sum_float(audit, "photoionization_rate_s^-1"),
            "matrix_source_preference": "phint53_kernel_when_available_else_flat_proxy",
            "solver": summary.get("solver"),
            "solve_status": summary.get("solve_status"),
            "solver_warning": summary.get("solver_warning"),
            "sum_population": summary.get("sum_population"),
            "normalization_residual": summary.get("normalization_residual"),
            "residual_norm": summary.get("residual_norm"),
            "n_negative_populations": summary.get("n_negative_populations"),
            "f_fraction": summary.get("f_fraction"),
            "i_fraction": summary.get("i_fraction"),
            "r_fraction": summary.get("r_fraction"),
            "R": summary.get("R"),
            "G": summary.get("G"),
            "l2_distance_to_target": summary.get("l2_distance_to_target"),
            "ion_population_sums_json": summary.get("ion_population_sums_json"),
            "level_kind_population_sums_json": summary.get("level_kind_population_sums_json"),
            "xstar_lucy_niter": summary.get("xstar_lucy_niter"),
            "xstar_lucy_diff": summary.get("xstar_lucy_diff"),
            "xstar_lucy_last_condensed_rank": summary.get("xstar_lucy_last_condensed_rank"),
            "xstar_lucy_last_condensed_condition": summary.get("xstar_lucy_last_condensed_condition"),
            "provenance": "v0.3.54_type53_phint53_scale_scan",
            "warning": "Scale scan uses placeholder-radiation phint53 forward kernel; absolute scale is not physical XSTAR radiation normalization.",
        })
    return rows


def _type53_phint53_scale_scan_summary(rows: Sequence[dict]) -> dict:
    scan_rows = [r for r in rows if str(r.get("scan_case")) == "full_global_xstar_lucy_phint53_scaled"]
    best = None
    for r in scan_rows:
        d = maybe_float(r.get("l2_distance_to_target"))
        if d is None:
            continue
        if best is None or float(d) < float(best.get("l2_distance_to_target")):
            best = r
    return {
        "n_type53_phint53_scale_scan_rows": len(rows),
        "n_scale_solutions": len(scan_rows),
        "scale_values": [r.get("type53_phint53_scale") for r in scan_rows],
        "best_scale": None if best is None else best.get("type53_phint53_scale"),
        "best_l2_distance_to_target": None if best is None else best.get("l2_distance_to_target"),
        "best_f_fraction": None if best is None else best.get("f_fraction"),
        "best_i_fraction": None if best is None else best.get("i_fraction"),
        "best_r_fraction": None if best is None else best.get("r_fraction"),
        "warning": "Scale scan is diagnostic only because phint53 still uses placeholder radiation normalization.",
    }




def build_type50_escape_factor_scan_rows(
    *,
    transition_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
    global_superlevel_cascade_matrix_terms: Sequence[dict],
    global_superlevel_source_matrix_terms: Sequence[dict],
    global_type53_flat_proxy_matrix_terms: Sequence[dict],
    global_type53_phint53_matrix_terms: Sequence[dict],
    global_type53_milne_matrix_terms: Sequence[dict],
    global_type74_inverse_matrix_terms: Sequence[dict],
    global_type74_calt74_matrix_terms: Sequence[dict],
    coupling_rows: Sequence[dict],
    line_rows: Sequence[dict],
    he_like_stage: int,
    type50_escape_factor_scan: object = "0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.75,1",
    type50_photoexcitation_scale: object = 0.0,
    triplet_coupling_treatment: str = "normal",
    linear_solver: str = "xstar-lucy",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    prune_null_rate_levels: bool = True,
) -> List[dict]:
    """Scan controlled XSTAR-ucalc-style type-50 escape factors.

    The scan rebuilds only the bound-bound matrix terms with
    ``type50_bound_bound_treatment='xstar-escape'`` and varied proxy
    ``ptmp1+ptmp2`` escape factors.  All other matrix components are held at
    the primary run settings.  This is diagnostic-only until real XSTAR optical
    depths, ``pescl``/``pescv``, and radiative pumping terms are ported.
    """
    factors = _parse_triplet_source_scales(type50_escape_factor_scan)
    rows: List[dict] = []
    target = _xstar_triplet_target(int(he_like_stage))
    if target is not None:
        rows.append({
            "row_kind": "type50_escape_factor_scan",
            "scan_case": "xstar_target",
            "type50_escape_factor": "target",
            "f_fraction": target["f"],
            "i_fraction": target["i"],
            "r_fraction": target["r"],
            "R": target.get("R"),
            "G": target.get("G"),
            "provenance": "v0.3.70_type50_escape_factor_scan",
        })
    coupling_treatment_norm = _normalise_triplet_coupling_treatment(triplet_coupling_treatment)
    for factor0 in factors:
        factor = min(max(float(factor0), 0.0), 1.0)
        bb_terms = build_global_bound_bound_matrix_terms(
            transition_rows,
            global_index_rows,
            type50_bound_bound_treatment="xstar-escape",
            type50_escape_factor=factor,
            type50_photoexcitation_scale=type50_photoexcitation_scale,
        )
        full_terms_unsuppressed = build_full_global_matrix_terms(
            global_index_rows=global_index_rows,
            global_bound_bound_matrix_terms=bb_terms,
            global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
            global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
            global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
            global_type53_phint53_matrix_terms=global_type53_phint53_matrix_terms,
            global_type53_milne_matrix_terms=global_type53_milne_matrix_terms,
            global_type74_inverse_matrix_terms=global_type74_inverse_matrix_terms,
            global_type74_calt74_matrix_terms=global_type74_calt74_matrix_terms,
            coupling_rows=coupling_rows,
            he_like_stage=he_like_stage,
        )
        suppressed_terms, suppressed_rows = suppress_triplet_3p_to_3s_radiative_terms(
            full_terms_unsuppressed,
            he_like_stage=he_like_stage,
        )
        full_terms = suppressed_terms if coupling_treatment_norm == "suppress-3p-to-3s-radiative" else full_terms_unsuppressed
        solve_rows = build_full_global_normalized_solve_comparison(
            global_index_rows=global_index_rows,
            full_global_matrix_terms=full_terms,
            line_rows=line_rows,
            he_like_stage=he_like_stage,
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
            prune_null_rate_levels=prune_null_rate_levels,
        )
        sol = next((r for r in solve_rows if str(r.get("row_kind")) == "summary" and str(r.get("comparison_case")) == "full_global_normalized_proxy_topology_solve"), solve_rows[0] if solve_rows else {})
        type50_detail = [r for r in bb_terms if _is_type50_radiative_transition(r) and str(r.get("matrix_term_kind")) in {"offdiag_gain", "diagonal_loss"}]
        triplet_uv = [
            r for r in type50_detail
            if maybe_int(r.get("ion_stage")) == int(he_like_stage)
            and "1s1.2p1.3P" in str(r.get("from_level_label") or "")
            and "1s1.2s1.3S" in str(r.get("to_level_label") or "")
        ]
        rows.append({
            "row_kind": "type50_escape_factor_scan",
            "scan_case": "full_global_type50_escape_factor",
            "type50_bound_bound_treatment": "xstar-escape",
            "type50_escape_factor": factor,
            "type50_photoexcitation_scale": float(_bounded_nonnegative_float(type50_photoexcitation_scale, 0.0)),
            "triplet_coupling_treatment": coupling_treatment_norm,
            "n_global_bound_bound_matrix_term_rows": len(bb_terms),
            "n_type50_matrix_rows": len(type50_detail),
            "n_triplet_3p_to_3s_type50_matrix_rows": len(triplet_uv),
            "sum_triplet_3p_to_3s_raw_A_s^-1": _sum_float(triplet_uv, "raw_A_s^-1"),
            "sum_triplet_3p_to_3s_escaped_rate_s^-1": _sum_float(triplet_uv, "escaped_decay_rate_s^-1"),
            "n_full_global_matrix_terms": len(full_terms),
            "n_suppressed_triplet_coupling_terms": len(suppressed_rows) if coupling_treatment_norm == "suppress-3p-to-3s-radiative" else 0,
            "solver": sol.get("solver"),
            "solve_status": sol.get("solve_status"),
            "solver_warning": sol.get("solver_warning"),
            "f_fraction": sol.get("f_fraction"),
            "i_fraction": sol.get("i_fraction"),
            "r_fraction": sol.get("r_fraction"),
            "R": sol.get("R"),
            "G": sol.get("G"),
            "l2_distance_to_target": sol.get("l2_distance_to_target"),
            "sum_population": sol.get("sum_population"),
            "normalization_residual": sol.get("normalization_residual"),
            "residual_norm": sol.get("residual_norm"),
            "n_negative_populations": sol.get("n_negative_populations"),
            "ion_population_sums_json": sol.get("ion_population_sums_json"),
            "level_kind_population_sums_json": sol.get("level_kind_population_sums_json"),
            "xstar_lucy_niter": sol.get("xstar_lucy_niter"),
            "xstar_lucy_diff": sol.get("xstar_lucy_diff"),
            "xstar_lucy_last_condensed_rank": sol.get("xstar_lucy_last_condensed_rank"),
            "xstar_lucy_last_condensed_condition": sol.get("xstar_lucy_last_condensed_condition"),
            "provenance": "v0.3.70_type50_escape_factor_scan",
            "warning": "Diagnostic scan only: escape factor is a controlled ptmp1+ptmp2 proxy, not a real XSTAR tau/pescl calculation.",
        })
    return _add_refined_triplet_target_metrics(rows, he_like_stage=he_like_stage)


def _type50_escape_factor_scan_summary(rows: Sequence[dict]) -> dict:
    scan_rows = [r for r in rows if str(r.get("scan_case")) == "full_global_type50_escape_factor"]
    def _best_by(col: str):
        best = None
        for r in scan_rows:
            val = maybe_float(r.get(col))
            if val is None:
                continue
            if best is None or float(val) < float(best.get(col)):
                best = r
        return best
    best_l2 = _best_by("l2_distance_to_target") or _best_by("l2_distance_to_target_recomputed")
    best_i = _best_by("i_abs_error_to_target")
    return {
        "n_type50_escape_factor_scan_rows": len(rows),
        "scan_cases": _counts(rows, "scan_case"),
        "escape_factor_values": [r.get("type50_escape_factor") for r in scan_rows],
        "best_l2_escape_factor": None if best_l2 is None else best_l2.get("type50_escape_factor"),
        "best_l2_distance_to_target": None if best_l2 is None else best_l2.get("l2_distance_to_target"),
        "best_l2_f_fraction": None if best_l2 is None else best_l2.get("f_fraction"),
        "best_l2_i_fraction": None if best_l2 is None else best_l2.get("i_fraction"),
        "best_l2_r_fraction": None if best_l2 is None else best_l2.get("r_fraction"),
        "best_i_escape_factor": None if best_i is None else best_i.get("type50_escape_factor"),
        "best_i_abs_error_to_target": None if best_i is None else best_i.get("i_abs_error_to_target"),
        "best_i_f_fraction": None if best_i is None else best_i.get("f_fraction"),
        "best_i_i_fraction": None if best_i is None else best_i.get("i_fraction"),
        "best_i_r_fraction": None if best_i is None else best_i.get("r_fraction"),
        "warning": "Type-50 escape-factor scan is diagnostic only until real XSTAR optical-depth and escape-probability contexts are ported.",
    }


def _normalise_inverse_recombination_mode(mode: str | None) -> str:
    """Normalize inverse-recombination diagnostic mode names."""
    m = str(mode or "none").strip().lower().replace("_", "-")
    aliases = {
        "off": "none",
        "false": "none",
        "0": "none",
        "type53": "type53-milne-diagnostic",
        "milne": "type53-milne-diagnostic",
        "type53-milne": "type53-milne-diagnostic",
        "type74": "type74-direct-diagnostic",
        "dr": "type74-direct-diagnostic",
        "type53-type74": "type53-type74",
        "type53+type74": "type53-type74",
        "all": "type53-type74",
        "xstar": "xstar-ucalc",
        "ucalc": "xstar-ucalc",
        "xstar-ucalc": "xstar-ucalc",
        "type53-phint53-type74-calt74": "xstar-ucalc",
    }
    m = aliases.get(m, m)
    if m not in {"none", "type53-milne-diagnostic", "type74-direct-diagnostic", "type53-type74", "xstar-ucalc"}:
        m = "none"
    return m


def _mode_includes_type53_inverse(mode: str | None) -> bool:
    """Return True for the older diagnostic type-53 inverse proxy path."""
    return _normalise_inverse_recombination_mode(mode) in {"type53-milne-diagnostic", "type53-type74"}


def _mode_includes_type74_inverse(mode: str | None) -> bool:
    """Return True for the older direct type-74 inverse proxy path."""
    return _normalise_inverse_recombination_mode(mode) in {"type74-direct-diagnostic", "type53-type74"}


def _mode_includes_xstar_ucalc_inverse(mode: str | None) -> bool:
    """Return True for the source-code-aligned XSTAR ucalc inverse path."""
    return _normalise_inverse_recombination_mode(mode) == "xstar-ucalc"


def build_type53_milne_inverse_audit_rows(
    *,
    type53_phint53_rate_audit_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
    inverse_recombination_mode: str = "none",
    type53_milne_scale: object = 1.0,
) -> List[dict]:
    """Build a first diagnostic Milne inverse-recombination scaffold for type 53.

    This is deliberately conservative.  It maps the inverse topology implied by
    the type-53 bound-free pair, but uses a tiny detailed-balance proxy derived
    from the already evaluated forward phint53 rate.  The real XSTAR Milne
    inverse kernel still requires the radiation/electron continuum context used
    by XSTAR and is not claimed to be physical here.
    """
    mode = _normalise_inverse_recombination_mode(inverse_recombination_mode)
    enabled = _mode_includes_type53_inverse(mode)
    _milne_scales = _parse_triplet_source_scales(type53_milne_scale)
    milne_scale = float(_milne_scales[0]) if _milne_scales else 1.0
    if not math.isfinite(milne_scale):
        milne_scale = 1.0
    by_g = {maybe_int(r.get("global_index")): r for r in global_index_rows if maybe_int(r.get("global_index")) is not None}
    rows: List[dict] = []
    for ar in type53_phint53_rate_audit_rows:
        bound_g = maybe_int(ar.get("bound_global_index"))
        cont_g = maybe_int(ar.get("continuum_or_parent_global_index"))
        bound = by_g.get(bound_g) if bound_g is not None else None
        cont = by_g.get(cont_g) if cont_g is not None else None
        fwd = maybe_float(ar.get("photoionization_rate_s^-1")) or 0.0
        # Diagnostic-only detailed-balance placeholder: scale by statistical
        # weight ratio and suppress strongly until a real Milne integral is ported.
        gb = maybe_float(bound.get("stat_weight")) if bound else None
        gc = maybe_float(cont.get("stat_weight")) if cont else None
        stat = 1.0
        if gb is not None and gc is not None and gc > 0.0:
            stat = max(0.0, gb / gc)
        inv_unscaled = fwd * stat * 1.0e-6
        inv = inv_unscaled * milne_scale if enabled else 0.0
        safe = enabled and bound_g is not None and cont_g is not None and inv > 0.0
        rows.append({
            "row_kind": "type53_milne_inverse_audit",
            "type53_milne_inverse_version": "v0.3.56",
            "inverse_recombination_mode": mode,
            "record": ar.get("record"),
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "record_ion_stage": ar.get("record_ion_stage"),
            "target_ion_stage": ar.get("target_ion_stage"),
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "bound_level": ar.get("bound_level"),
            "bound_global_index": bound_g,
            "continuum_or_parent_global_index": cont_g,
            "photoionization_rate_s^-1": fwd,
            "statistical_weight_factor_bound_over_continuum": stat,
            "type53_milne_scale": milne_scale,
            "milne_inverse_rate_unscaled_s^-1": inv_unscaled,
            "milne_inverse_rate_s^-1": inv,
            "milne_status": "diagnostic_milne_topology_proxy_enabled" if enabled else "disabled_by_inverse_recombination_mode",
            "topology_safe_for_inverse_matrix": safe,
            "matrix_safe_to_assemble_physically": False,
            "matrix_role_if_assembled": "M[bound,continuum_or_parent]+=milne_inverse_rate_and_M[continuum_or_parent,continuum_or_parent]-=milne_inverse_rate",
            "assembly_status": "diagnostic_milne_inverse_topology_proxy_ready" if safe else "diagnostic_milne_inverse_not_ready_or_disabled",
            "missing_physical_requirements": "true_milne_integral;electron_continuum_context;real_xstar_radiation_field;opacity_escape_probability_context",
            "warning": "diagnostic topology/rate proxy only; not a physical XSTAR Milne inverse recombination rate",
            "provenance": "v0.3.56_type53_milne_inverse_recombination_scaffold",
        })
    return rows


def build_global_type53_milne_matrix_terms(type53_milne_inverse_audit_rows: Sequence[dict]) -> List[dict]:
    """Map diagnostic type-53 Milne inverse-recombination proxy rows to matrix triplets."""
    rows: List[dict] = []
    tid = 0
    for ar in type53_milne_inverse_audit_rows:
        bound_g = maybe_int(ar.get("bound_global_index"))
        cont_g = maybe_int(ar.get("continuum_or_parent_global_index"))
        rate = maybe_float(ar.get("milne_inverse_rate_s^-1")) or 0.0
        safe = bool(ar.get("topology_safe_for_inverse_matrix")) and bound_g is not None and cont_g is not None and rate > 0.0
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
            "inverse_recombination_mode": ar.get("inverse_recombination_mode"),
            "type53_milne_scale": ar.get("type53_milne_scale"),
            "milne_status": ar.get("milne_status"),
            "matrix_safe_to_assemble_physically": False,
            "provenance": "v0.3.56_type53_milne_inverse_matrix_topology",
        }
        if not safe:
            tid += 1
            rows.append({
                **base,
                "global_type53_milne_term_id": tid,
                "row_kind": "global_type53_milne_matrix_term",
                "matrix_term_kind": "skipped_milne_inverse_recombination",
                "matrix_role": "skipped_disabled_or_missing_mapping_or_zero_rate",
                "matrix_row_global_index": "",
                "matrix_col_global_index": "",
                "signed_rate_s^-1": "",
                "rate_s^-1": rate,
                "assembly_status": "skipped_milne_inverse_topology_or_rate_incomplete",
                "skip_reason": "disabled_or_missing_bound_or_continuum_global_index_or_zero_rate",
            })
            continue
        tid += 1
        rows.append({
            **base,
            "global_type53_milne_term_id": tid,
            "row_kind": "global_type53_milne_matrix_term",
            "matrix_term_kind": "offdiag_continuum_to_bound_milne_inverse_gain",
            "matrix_role": "M[bound_global_index,continuum_or_parent_global_index]+=milne_inverse_rate_proxy",
            "matrix_row_global_index": bound_g,
            "matrix_col_global_index": cont_g,
            "signed_rate_s^-1": rate,
            "rate_s^-1": rate,
            "assembly_status": "assembled_diagnostic_milne_inverse_topology_proxy",
            "skip_reason": "",
        })
        tid += 1
        rows.append({
            **base,
            "global_type53_milne_term_id": tid,
            "row_kind": "global_type53_milne_matrix_term",
            "matrix_term_kind": "diagonal_continuum_milne_inverse_loss",
            "matrix_role": "M[continuum_or_parent_global_index,continuum_or_parent_global_index]-=milne_inverse_rate_proxy",
            "matrix_row_global_index": cont_g,
            "matrix_col_global_index": cont_g,
            "signed_rate_s^-1": -rate,
            "rate_s^-1": rate,
            "assembly_status": "assembled_diagnostic_milne_inverse_topology_proxy",
            "skip_reason": "",
        })
    return rows


def build_type74_inverse_recombination_audit_rows(
    *,
    type74_triplet_source_audit_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
    inverse_recombination_mode: str = "none",
    type74_inverse_scale: object = 1.0,
) -> List[dict]:
    """Map direct type-74 DR-delta source candidates into inverse-recombination topology rows."""
    mode = _normalise_inverse_recombination_mode(inverse_recombination_mode)
    enabled = _mode_includes_type74_inverse(mode)
    _type74_scales = _parse_triplet_source_scales(type74_inverse_scale)
    type74_scale = float(_type74_scales[0]) if _type74_scales else 1.0
    if not math.isfinite(type74_scale):
        type74_scale = 1.0
    lookup = _global_index_lookup(global_index_rows)
    rows: List[dict] = []
    for ar in type74_triplet_source_audit_rows:
        if str(ar.get("type74_direct_triplet_candidate")).lower() != "true":
            continue
        stage = maybe_int(ar.get("target_ion_stage"))
        dest = maybe_int(ar.get("destination_level"))
        if stage is None or dest is None:
            continue
        dest_row = lookup.get((stage, dest))
        cont_row = _find_parent_continuum_global_row(global_index_rows, ion_stage=stage)
        dest_g = maybe_int(dest_row.get("global_index")) if dest_row else None
        cont_g = maybe_int(cont_row.get("global_index")) if cont_row else None
        rate0 = maybe_float(ar.get("candidate_source_rate_s^-1")) or 0.0
        rate = rate0 * type74_scale if enabled else 0.0
        safe = enabled and dest_g is not None and cont_g is not None and rate > 0.0
        rows.append({
            "row_kind": "type74_inverse_recombination_audit",
            "type74_inverse_version": "v0.3.56",
            "inverse_recombination_mode": mode,
            "record": ar.get("record"),
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "target_ion_stage": stage,
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "destination_level": dest,
            "destination_global_index": dest_g,
            "parent_continuum_global_index": cont_g,
            "triplet_component": ar.get("triplet_component"),
            "type74_eval_status": ar.get("type74_eval_status"),
            "type74_inverse_scale": type74_scale,
            "type74_inverse_rate_unscaled_s^-1": rate0,
            "type74_inverse_rate_s^-1": rate,
            "topology_safe_for_inverse_matrix": safe,
            "matrix_safe_to_assemble_physically": False,
            "assembly_status": "diagnostic_type74_inverse_topology_proxy_ready" if safe else "diagnostic_type74_inverse_not_ready_or_disabled",
            "matrix_role_if_assembled": "M[destination,parent_continuum]+=type74_DR_delta_rate_and_M[parent_continuum,parent_continuum]-=rate",
            "missing_physical_requirements": "full_calt74_bound_free_context;parent_continuum_population;DR_delta_balance_context",
            "warning": "diagnostic direct DR-delta source topology only; rate uses prior parent_population_proxy convention",
            "provenance": "v0.3.56_type74_inverse_recombination_scaffold",
        })
    return rows



def build_type74_calt74_rate_audit_rows(
    *,
    type74_linkage_rows: Sequence[dict],
    radiation_context_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
    inverse_recombination_mode: str = "none",
    temperature: float,
    type74_inverse_scale: object = 1.0,
) -> List[dict]:
    """Evaluate type-74 rows with a source-aligned calt74 diagnostic.

    v0.3.57 ports both outputs from XSTAR ``calt74``: forward DR-delta
    photoionization ``rate`` and inverse DR ``alpha``.  ``ucalc.f90`` then
    applies ``alpha *= gglo/ggup`` where ``gglo`` is the recombined/destination
    level statistical weight and ``ggup`` is the parent-continuum statistical
    weight.  Absolute rates still depend on the placeholder radiation context.
    """
    mode = _normalise_inverse_recombination_mode(inverse_recombination_mode)
    enabled = _mode_includes_type74_inverse(mode) or _mode_includes_xstar_ucalc_inverse(mode)
    scales = _parse_triplet_source_scales(type74_inverse_scale)
    scale = float(scales[0]) if scales else 1.0
    if not math.isfinite(scale):
        scale = 1.0
    lookup = _global_index_lookup(global_index_rows)
    rows: List[dict] = []
    for lr in type74_linkage_rows:
        if maybe_int(lr.get("data_type")) != 74:
            continue
        stage = maybe_int(lr.get("target_ion_stage"))
        dest = maybe_int(lr.get("type74_i7_recombined_or_source_level") or lr.get("source_level"))
        parent_stage = maybe_int(lr.get("parent_ion_stage")) or (stage + 1 if stage is not None else None)
        if stage is None or dest is None:
            continue
        raw = lr.get("type74_raw_reals_preview") or lr.get("raw_reals_preview")
        reals = _parse_preview_numbers(raw)
        ev = _xstar_calt74_rate_alpha_diagnostic(
            float(temperature),
            reals,
            radiation_context_rows=radiation_context_rows,
        )
        dest_row = lookup.get((stage, dest))
        cont_row = _find_parent_continuum_global_row(global_index_rows, ion_stage=stage)
        dest_g = maybe_int(dest_row.get("global_index")) if dest_row else None
        cont_g = maybe_int(cont_row.get("global_index")) if cont_row else None
        gglo = maybe_float(dest_row.get("stat_weight")) if dest_row else None
        ggup = maybe_float(cont_row.get("stat_weight")) if cont_row else None
        stat_factor = 0.0
        if gglo is not None and ggup not in (None, 0.0):
            stat_factor = float(gglo) / float(ggup)
        alpha0 = maybe_float(ev.get("type74_alpha_unweighted_cm3_s")) or 0.0
        rate_forward0 = maybe_float(ev.get("type74_rate_unweighted_s^-1")) or 0.0
        alpha_weighted0 = alpha0 * stat_factor
        inv_rate = alpha_weighted0 * scale if enabled else 0.0
        safe = enabled and dest_g is not None and cont_g is not None and inv_rate > 0.0
        rows.append({
            "row_kind": "type74_calt74_rate_audit",
            "type74_calt74_version": "v0.3.57",
            "inverse_recombination_mode": mode,
            "record": lr.get("record"),
            "data_type": lr.get("data_type"),
            "rate_type": lr.get("rate_type"),
            "target_ion_stage": stage,
            "parent_ion_stage": parent_stage,
            "destination_level": dest,
            "destination_global_index": dest_g,
            "parent_continuum_global_index": cont_g,
            "triplet_component": lr.get("source_level_triplet_component") or lr.get("possible_feed_component_direct"),
            "destination_stat_weight_gglo": gglo,
            "parent_continuum_stat_weight_ggup": ggup,
            "statistical_weight_factor_gglo_over_ggup": stat_factor,
            "type74_inverse_scale": scale,
            "type74_calt74_rate_forward_unscaled_s^-1": rate_forward0,
            "type74_calt74_alpha_unweighted_cm3_s": alpha0,
            "type74_calt74_alpha_weighted_cm3_s": alpha_weighted0,
            "type74_calt74_inverse_rate_unscaled_s^-1": alpha_weighted0,
            "type74_calt74_inverse_rate_s^-1": inv_rate,
            "topology_safe_for_inverse_matrix": safe,
            "matrix_safe_to_assemble_physically": False,
            "assembly_status": "diagnostic_type74_calt74_inverse_topology_ready" if safe else "diagnostic_type74_calt74_not_ready_or_disabled",
            "matrix_role_if_assembled": "M[destination,parent_continuum]+=alpha*gglo/ggup_and_M[parent,parent]-=same",
            "missing_physical_requirements": "real_xstar_bremsa_for_forward_rate;closed_parent_continuum_population;validated_calt74_full_context",
            "warning": "source-aligned calt74 diagnostic; inverse alpha uses XSTAR gglo/ggup correction but parent continuum balance remains proxy topology",
            "provenance": "v0.3.57_type74_calt74_rate_alpha_diagnostic",
            **ev,
        })
    return rows


def build_global_type74_calt74_matrix_terms(type74_calt74_rate_audit_rows: Sequence[dict]) -> List[dict]:
    """Map source-aligned calt74 inverse alpha rows onto global matrix triplets."""
    rows: List[dict] = []
    tid = 0
    for ar in type74_calt74_rate_audit_rows:
        dest_g = maybe_int(ar.get("destination_global_index"))
        cont_g = maybe_int(ar.get("parent_continuum_global_index"))
        rate = maybe_float(ar.get("type74_calt74_inverse_rate_s^-1")) or 0.0
        safe = bool(ar.get("topology_safe_for_inverse_matrix")) and dest_g is not None and cont_g is not None and rate > 0.0
        base = {
            "record": ar.get("record"),
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "target_ion_stage": ar.get("target_ion_stage"),
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "destination_level": ar.get("destination_level"),
            "destination_global_index": dest_g,
            "parent_continuum_global_index": cont_g,
            "triplet_component": ar.get("triplet_component"),
            "inverse_recombination_mode": ar.get("inverse_recombination_mode"),
            "type74_inverse_scale": ar.get("type74_inverse_scale"),
            "type74_calt74_status": ar.get("type74_calt74_status"),
            "type74_calt74_alpha_weighted_cm3_s": ar.get("type74_calt74_alpha_weighted_cm3_s"),
            "type74_calt74_rate_forward_unscaled_s^-1": ar.get("type74_calt74_rate_forward_unscaled_s^-1"),
            "matrix_safe_to_assemble_physically": False,
            "provenance": "v0.3.57_type74_calt74_matrix_topology",
        }
        if not safe:
            tid += 1
            rows.append({
                **base,
                "global_type74_calt74_term_id": tid,
                "row_kind": "global_type74_calt74_matrix_term",
                "matrix_term_kind": "skipped_type74_calt74_inverse_recombination",
                "matrix_role": "skipped_disabled_or_missing_mapping_or_zero_rate",
                "matrix_row_global_index": "",
                "matrix_col_global_index": "",
                "signed_rate_s^-1": "",
                "rate_s^-1": rate,
                "assembly_status": "skipped_type74_calt74_topology_or_rate_incomplete",
                "skip_reason": "disabled_or_missing_destination_or_parent_continuum_global_index_or_zero_rate",
            })
            continue
        tid += 1
        rows.append({
            **base,
            "global_type74_calt74_term_id": tid,
            "row_kind": "global_type74_calt74_matrix_term",
            "matrix_term_kind": "offdiag_parent_continuum_to_type74_calt74_destination_gain",
            "matrix_role": "M[destination_global_index,parent_continuum_global_index]+=type74_calt74_alpha_weighted",
            "matrix_row_global_index": dest_g,
            "matrix_col_global_index": cont_g,
            "signed_rate_s^-1": rate,
            "rate_s^-1": rate,
            "assembly_status": "assembled_diagnostic_type74_calt74_inverse_topology",
            "skip_reason": "",
        })
        tid += 1
        rows.append({
            **base,
            "global_type74_calt74_term_id": tid,
            "row_kind": "global_type74_calt74_matrix_term",
            "matrix_term_kind": "diagonal_parent_continuum_type74_calt74_loss",
            "matrix_role": "M[parent_continuum_global_index,parent_continuum_global_index]-=type74_calt74_alpha_weighted",
            "matrix_row_global_index": cont_g,
            "matrix_col_global_index": cont_g,
            "signed_rate_s^-1": -rate,
            "rate_s^-1": rate,
            "assembly_status": "assembled_diagnostic_type74_calt74_inverse_topology",
            "skip_reason": "",
        })
    return rows


def _type74_calt74_rate_audit_summary(rows: Sequence[dict]) -> dict:
    return {
        "n_type74_calt74_rate_audit_rows": len(rows),
        "rows_by_triplet_component": _counts(rows, "triplet_component"),
        "rows_by_status": _counts(rows, "type74_calt74_status"),
        "rows_by_assembly_status": _counts(rows, "assembly_status"),
        "total_type74_calt74_forward_rate_unscaled_s^-1": _sum_float(rows, "type74_calt74_rate_forward_unscaled_s^-1"),
        "total_type74_calt74_alpha_unweighted_cm3_s": _sum_float(rows, "type74_calt74_alpha_unweighted_cm3_s"),
        "total_type74_calt74_alpha_weighted_cm3_s": _sum_float(rows, "type74_calt74_alpha_weighted_cm3_s"),
        "total_type74_calt74_inverse_rate_s^-1": _sum_float(rows, "type74_calt74_inverse_rate_s^-1"),
        "warning": "Source-aligned calt74 diagnostic; absolute forward rate still depends on placeholder radiation field and inverse topology still depends on parent-continuum closure.",
    }


def _global_type74_calt74_matrix_terms_summary(rows: Sequence[dict]) -> dict:
    return {
        "n_global_type74_calt74_matrix_term_rows": len(rows),
        "rows_by_matrix_term_kind": _counts(rows, "matrix_term_kind"),
        "rows_by_assembly_status": _counts(rows, "assembly_status"),
        "total_signed_rate_s^-1": _sum_float(rows, "signed_rate_s^-1"),
        "total_rate_s^-1": _sum_float(rows, "rate_s^-1"),
    }




def build_phint53_milne_integral_audit_rows(
    *,
    type53_phint53_rate_audit_rows: Sequence[dict],
    type53_rate_audit_rows: Sequence[dict] = (),
    type53_milne_inverse_audit_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
    he_like_stage: int,
    temperature: float,
    electron_density: float,
) -> List[dict]:
    """Build a source-code-aligned audit of the type-53 Milne inverse integral.

    v0.3.72 ports the two XSTAR source paths that matter for the recombination
    side of type-53 records:

    * ``phint53.f90``: the ``rrrt``/``ans2`` integral over the mapped continuum
      cross section, with a reconstructed ``rnist`` LTE seed.
    * ``milne.f90`` + ``intin.f90``: the independent Milne-relation check that
      ``ucalc.f90`` uses to compare ``alphamilne*xnx`` against ``ans2``.

    This function is audit-only.  It does not assemble the new rates into the
    matrix; it exposes whether the older Python proxy is on the right scale and
    component balance before any physical treatment is introduced.
    """
    by_record_milne = {r.get("record"): r for r in type53_milne_inverse_audit_rows}
    by_record_raw53 = {r.get("record"): r for r in type53_rate_audit_rows}
    by_g = {maybe_int(r.get("global_index")): r for r in global_index_rows if maybe_int(r.get("global_index")) is not None}
    rows: List[dict] = []
    component_sums: Dict[str, dict] = {}

    def _acc(comp: str, key: str, value: float) -> None:
        d = component_sums.setdefault(comp, {"component": comp, "n_rows": 0})
        d[key] = float(d.get(key, 0.0)) + float(value or 0.0)

    for ar in type53_phint53_rate_audit_rows:
        rec = ar.get("record")
        raw_ar = by_record_raw53.get(rec, {})
        full = (
            ar.get("type53_raw_reals_full")
            or ar.get("raw_reals_preview")
            or raw_ar.get("type53_raw_reals_full")
            or raw_ar.get("raw_reals_preview")
        )
        e_ry, sigma_cm2 = _type53_cross_section_pairs_from_reals(full)
        e_ry_mb, sigma_mb = _type53_cross_section_pairs_mb_from_reals(full)
        bg = maybe_int(ar.get("bound_global_index"))
        cg = maybe_int(ar.get("continuum_or_parent_global_index"))
        bound = by_g.get(bg) if bg is not None else None
        cont = by_g.get(cg) if cg is not None else None
        comp = _global_index_triplet_component(bound or {}, he_like_stage=he_like_stage) or "other"
        threshold_eV = None
        if bound is not None:
            threshold_eV = maybe_float(bound.get("binding_from_continuum_eV"))
            if threshold_eV is None or threshold_eV <= 0.0:
                threshold_eV = maybe_float(bound.get("ionization_potential_eV"))
        if threshold_eV is None:
            threshold_eV = maybe_float(ar.get("phint53_threshold_eV"))
        threshold_ry = (float(threshold_eV) / 13.605692) if threshold_eV is not None and math.isfinite(float(threshold_eV)) else float("nan")
        gb = maybe_float(bound.get("stat_weight")) if bound else None
        gc = maybe_float(cont.get("stat_weight")) if cont else None
        ph_milne = _evaluate_phint53_milne_ans2_integral(
            e_ry=e_ry,
            sigma_cm2=sigma_cm2,
            threshold_eV=float(threshold_eV) if threshold_eV is not None else float("nan"),
            temperature_K=float(temperature),
            electron_density=float(electron_density),
            bound_stat_weight=gb,
            continuum_stat_weight=gc,
            ptmp_sum=1.0,
            n_energy_grid_points=maybe_int(ar.get("phint53_n_energy_grid_points")) or 512,
        )
        mf = _evaluate_xstar_milne_f90_integral(
            e_ry=e_ry_mb,
            sigma_mb=sigma_mb,
            threshold_ry=threshold_ry,
            temperature_K=float(temperature),
        )
        alpha = maybe_float(mf.get("milne_f90_alpha_cm3_s")) or 0.0
        milne_f90_rate = alpha * max(float(electron_density), 0.0)
        ph_ans2 = maybe_float(ph_milne.get("phint53_milne_ans2_rrrt_s^-1")) or 0.0
        current_proxy = maybe_float(by_record_milne.get(rec, {}).get("milne_inverse_rate_s^-1")) or 0.0
        current_unscaled = maybe_float(by_record_milne.get(rec, {}).get("milne_inverse_rate_unscaled_s^-1")) or 0.0
        fwd = maybe_float(ar.get("photoionization_rate_s^-1")) or 0.0
        ratio_proxy_ph = (current_proxy / ph_ans2) if ph_ans2 > 0.0 else ""
        ratio_proxy_mf = (current_proxy / milne_f90_rate) if milne_f90_rate > 0.0 else ""
        ratio_ph_mf = (ph_ans2 / milne_f90_rate) if milne_f90_rate > 0.0 else ""
        rows.append({
            "row_kind": "phint53_milne_integral_audit",
            "provenance": "v0.3.72_source_code_aligned_phint53_milne_integral_audit",
            "audit_case": "type53_phint53_milne_integral",
            "record": rec,
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "target_ion_stage": ar.get("target_ion_stage"),
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "bound_level": ar.get("bound_level"),
            "bound_global_index": bg,
            "continuum_or_parent_global_index": cg,
            "bound_label": bound.get("level_label") if bound else "",
            "continuum_or_parent_label": cont.get("level_label") if cont else "",
            "triplet_component": comp,
            "bound_stat_weight_gglo": gb,
            "continuum_stat_weight_ggup": gc,
            "statistical_weight_factor_gglo_over_ggup": (gb / gc) if gb is not None and gc not in (None, 0.0) else "",
            "threshold_eV": threshold_eV,
            "threshold_ry": threshold_ry,
            "temperature_K": temperature,
            "electron_density_cm^-3": electron_density,
            "current_python_forward_photoionization_ans1_s^-1": fwd,
            "type53_cross_section_source": "type53_rate_audit_raw_reals_full" if raw_ar.get("type53_raw_reals_full") else ("type53_rate_audit_raw_reals_preview" if raw_ar.get("raw_reals_preview") else "type53_phint53_rate_audit"),
            "type53_n_cross_section_pairs_available": len(e_ry),
            "current_python_proxy_milne_ans2_scaled_s^-1": current_proxy,
            "current_python_proxy_milne_ans2_unscaled_s^-1": current_unscaled,
            "source_code_phint53_milne_ans2_rrrt_s^-1": ph_ans2,
            "source_code_milne_f90_alpha_cm3_s": alpha,
            "source_code_milne_f90_rate_alpha_ne_s^-1": milne_f90_rate,
            "current_proxy_over_phint53_ans2": ratio_proxy_ph,
            "current_proxy_over_milne_f90_alpha_ne": ratio_proxy_mf,
            "phint53_ans2_over_milne_f90_alpha_ne": ratio_ph_mf,
            "xstar_source_files": "xstarlib/src/ucalc.f90;xstarlib/src/phint53.f90;xstarlib/src/milne.f90;xstarlib/src/intin.f90",
            "xstar_ucalc_debug_check": "ucalc compares alphamilne*xnx against phint53 ans2 for type53 when verbose",
            "matrix_assembly_status": "audit_only_not_assembled",
            "warning": "source-code integral audit only; exact ethion/ethtmp/emltlv arrays and ptmp escape factors still need full XSTAR context",
            **ph_milne,
            **mf,
        })
        component_sums.setdefault(comp, {"component": comp, "n_rows": 0})["n_rows"] += 1
        _acc(comp, "current_python_proxy_milne_ans2_scaled_sum_s^-1", current_proxy)
        _acc(comp, "source_code_phint53_milne_ans2_sum_s^-1", ph_ans2)
        _acc(comp, "source_code_milne_f90_alpha_ne_sum_s^-1", milne_f90_rate)
        _acc(comp, "current_python_forward_photoionization_ans1_sum_s^-1", fwd)

    for comp in sorted(component_sums):
        d = component_sums[comp]
        proxy = float(d.get("current_python_proxy_milne_ans2_scaled_sum_s^-1", 0.0))
        phsum = float(d.get("source_code_phint53_milne_ans2_sum_s^-1", 0.0))
        mfsum = float(d.get("source_code_milne_f90_alpha_ne_sum_s^-1", 0.0))
        rows.append({
            "row_kind": "phint53_milne_integral_audit",
            "provenance": "v0.3.72_source_code_aligned_phint53_milne_integral_audit",
            "audit_case": "component_summary",
            "triplet_component": comp,
            "n_rows": d.get("n_rows", 0),
            "current_python_forward_photoionization_ans1_sum_s^-1": d.get("current_python_forward_photoionization_ans1_sum_s^-1", 0.0),
            "current_python_proxy_milne_ans2_scaled_sum_s^-1": proxy,
            "source_code_phint53_milne_ans2_sum_s^-1": phsum,
            "source_code_milne_f90_alpha_ne_sum_s^-1": mfsum,
            "proxy_over_phint53_ans2_sum": (proxy / phsum) if phsum > 0.0 else "",
            "proxy_over_milne_f90_alpha_ne_sum": (proxy / mfsum) if mfsum > 0.0 else "",
            "phint53_ans2_over_milne_f90_alpha_ne_sum": (phsum / mfsum) if mfsum > 0.0 else "",
            "diagnostic_interpretation": "component-level source-code Milne closure summary; use f/r sums before changing matrix rates",
        })

    rows.append({
        "row_kind": "phint53_milne_integral_audit",
        "provenance": "v0.3.72_source_code_aligned_phint53_milne_integral_audit",
        "audit_case": "audit_summary",
        "n_type53_rows": len(type53_phint53_rate_audit_rows),
        "n_total_rows_including_summaries": len(rows) + 1,
        "purpose": "port/source-audit real phint53 Milne inverse integral terms before any treatment or scan",
        "main_hypothesis": "remaining_f_over_r_mismatch_is_due_to_type53_Milne_closure_and_adjacent_ion_normalization_not_type50_escape_alone",
        "warning": "audit_only; no solver or matrix behavior is intentionally changed",
    })
    return rows


def _phint53_milne_integral_audit_summary(rows: Sequence[dict]) -> dict:
    component_rows = [r for r in rows if str(r.get("audit_case")) == "component_summary"]
    return {
        "n_phint53_milne_integral_audit_rows": len(rows),
        "audit_case_counts": _counts(rows, "audit_case"),
        "triplet_component_counts": _counts(rows, "triplet_component"),
        "total_current_python_proxy_milne_ans2_scaled_s^-1": _sum_float(rows, "current_python_proxy_milne_ans2_scaled_s^-1"),
        "total_source_code_phint53_milne_ans2_s^-1": _sum_float(rows, "source_code_phint53_milne_ans2_rrrt_s^-1"),
        "total_source_code_milne_f90_alpha_ne_s^-1": _sum_float(rows, "source_code_milne_f90_rate_alpha_ne_s^-1"),
        "component_summaries": component_rows,
        "warning": "v0.3.72 audit only; source-code Milne integral terms are not assembled into the solver.",
    }


def build_global_type53_xstar_ucalc_matrix_terms(
    phint53_milne_integral_audit_rows: Sequence[dict],
    *,
    inverse_recombination_mode: str = "none",
) -> List[dict]:
    """Map source-code phint53 Milne ans2 rows onto the full-global matrix.

    v0.3.78 introduces the first direct XSTAR ``ucalc`` inverse-recombination
    path.  For ``--inverse-recombination-mode xstar-ucalc`` this uses the
    source-code phint53/milne audit rate instead of the older scaled proxy:

        M[bound, parent_continuum] += ans2
        M[parent_continuum, parent_continuum] -= ans2

    Exact XSTAR ethion/ethtmp/emltlv arrays and escape factors are still
    reconstructed, so the rows are marked experimental rather than final.
    """
    mode = _normalise_inverse_recombination_mode(inverse_recombination_mode)
    enabled = _mode_includes_xstar_ucalc_inverse(mode)
    rows: List[dict] = []
    tid = 0
    for ar in phint53_milne_integral_audit_rows:
        if str(ar.get("audit_case")) != "type53_phint53_milne_integral":
            continue
        bound_g = maybe_int(ar.get("bound_global_index"))
        cont_g = maybe_int(ar.get("continuum_or_parent_global_index"))
        rate = maybe_float(ar.get("source_code_phint53_milne_ans2_rrrt_s^-1")) or 0.0
        status = str(ar.get("phint53_milne_ans2_status") or "")
        safe = enabled and bound_g is not None and cont_g is not None and rate > 0.0 and status.startswith("evaluated_")
        base = {
            "record": ar.get("record"),
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "target_ion_stage": ar.get("target_ion_stage"),
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "bound_level": ar.get("bound_level"),
            "bound_global_index": bound_g,
            "continuum_or_parent_global_index": cont_g,
            "triplet_component": ar.get("triplet_component"),
            "inverse_recombination_mode": mode,
            "phint53_milne_ans2_status": ar.get("phint53_milne_ans2_status"),
            "source_code_phint53_milne_ans2_rrrt_s^-1": rate,
            "source_code_milne_f90_rate_alpha_ne_s^-1": ar.get("source_code_milne_f90_rate_alpha_ne_s^-1"),
            "current_python_proxy_milne_ans2_scaled_s^-1": ar.get("current_python_proxy_milne_ans2_scaled_s^-1"),
            "matrix_safe_to_assemble_physically": False,
            "provenance": "v0.3.78_xstar_ucalc_type53_phint53_milne_matrix",
            "warning": "experimental source-code ucalc path using reconstructed phint53/milne context; not yet exact XSTAR runtime state",
        }
        if not safe:
            tid += 1
            rows.append({
                **base,
                "global_type53_xstar_ucalc_term_id": tid,
                "row_kind": "global_type53_milne_matrix_term",
                "matrix_term_kind": "skipped_xstar_ucalc_phint53_milne_inverse",
                "matrix_role": "skipped_disabled_or_missing_mapping_or_zero_source_code_ans2",
                "matrix_row_global_index": "",
                "matrix_col_global_index": "",
                "signed_rate_s^-1": "",
                "rate_s^-1": rate,
                "assembly_status": "skipped_xstar_ucalc_phint53_milne_inverse",
                "skip_reason": "mode_not_xstar_ucalc_or_missing_bound_or_continuum_global_index_or_zero_rate_or_unevaluated_integral",
            })
            continue
        tid += 1
        rows.append({
            **base,
            "global_type53_xstar_ucalc_term_id": tid,
            "row_kind": "global_type53_milne_matrix_term",
            "matrix_term_kind": "offdiag_parent_continuum_to_bound_xstar_ucalc_phint53_milne_gain",
            "matrix_role": "M[bound_global_index,continuum_or_parent_global_index]+=phint53_ans2",
            "matrix_row_global_index": bound_g,
            "matrix_col_global_index": cont_g,
            "signed_rate_s^-1": rate,
            "rate_s^-1": rate,
            "assembly_status": "assembled_xstar_ucalc_phint53_milne_inverse",
            "skip_reason": "",
        })
        tid += 1
        rows.append({
            **base,
            "global_type53_xstar_ucalc_term_id": tid,
            "row_kind": "global_type53_milne_matrix_term",
            "matrix_term_kind": "diagonal_parent_continuum_xstar_ucalc_phint53_milne_loss",
            "matrix_role": "M[continuum_or_parent_global_index,continuum_or_parent_global_index]-=phint53_ans2",
            "matrix_row_global_index": cont_g,
            "matrix_col_global_index": cont_g,
            "signed_rate_s^-1": -rate,
            "rate_s^-1": rate,
            "assembly_status": "assembled_xstar_ucalc_phint53_milne_inverse",
            "skip_reason": "",
        })
    return rows


def build_type53_type74_ucalc_closure_audit_rows(
    *,
    type53_phint53_rate_audit_rows: Sequence[dict],
    type53_rate_audit_rows: Sequence[dict] = (),
    type53_milne_inverse_audit_rows: Sequence[dict] = (),
    type74_calt74_rate_audit_rows: Sequence[dict],
    type74_inverse_recombination_audit_rows: Sequence[dict],
    global_index_rows: Sequence[dict],
    he_like_stage: int,
    temperature: float,
    electron_density: float,
) -> List[dict]:
    """Audit source-code-aligned type-53/type-74 recombination closure.

    This v0.3.71 audit is intentionally read-only.  It puts the current Python
    proxy rates next to the XSTAR ``ucalc.f90`` semantics that still need to be
    ported before the C V f/r balance can be treated as physical:

    * type 53: ``phint53`` returns a forward photoionization ``ans1`` and a
      Milne/recombination ``ans2`` using LTE/Saha/statistical context.
    * type 74: ``calt74`` returns a forward delta-photoionization rate and an
      inverse DR alpha that XSTAR multiplies by ``gglo/ggup`` before matrix use.

    No row from this audit is assembled into the solver matrix.
    """
    meta = _global_index_metadata(global_index_rows)
    by_record_milne: Dict[object, dict] = {r.get("record"): r for r in type53_milne_inverse_audit_rows}
    by_record_t74_proxy: Dict[object, dict] = {r.get("record"): r for r in type74_inverse_recombination_audit_rows}
    kT_eV = 8.617333262e-5 * max(float(temperature), 1.0e-300)
    rows: List[dict] = []

    component_sums: Dict[str, dict] = {}
    def _acc(comp: str, key: str, value: object) -> None:
        c = str(comp or "other")
        d = component_sums.setdefault(c, {"component": c, "n_rows": 0})
        d[key] = float(d.get(key, 0.0)) + float(maybe_float(value) or 0.0)

    # Type-53 phint53/Milne closure rows.
    for ar in type53_phint53_rate_audit_rows:
        bg = maybe_int(ar.get("bound_global_index"))
        cg = maybe_int(ar.get("continuum_or_parent_global_index"))
        bound = meta.get(bg, {}) if bg is not None else {}
        cont = meta.get(cg, {}) if cg is not None else {}
        comp = _global_index_triplet_component(bound, he_like_stage=he_like_stage) or "other"
        milne = by_record_milne.get(ar.get("record"), {})
        gb = maybe_float(bound.get("stat_weight") or bound.get("statistical_weight_g"))
        gc = maybe_float(cont.get("stat_weight") or cont.get("statistical_weight_g"))
        stat = (gb / gc) if (gb is not None and gc not in (None, 0.0)) else ""
        bind_eV = maybe_float(bound.get("binding_from_continuum_eV") or bound.get("ionization_potential_eV"))
        # XSTAR ucalc type-53 builds a Saha/LTE-like seed using q2=2.07e-16*n_e*T^-1.5
        # and an exponential energy factor.  We report the diagnostic ingredients;
        # the real emltlv/rnist handoff still requires the exact XSTAR level arrays.
        q2 = 2.07e-16 * float(electron_density) * (max(float(temperature), 1.0e-300) ** -1.5)
        boltz = ""
        saha_seed = ""
        if bind_eV is not None and math.isfinite(bind_eV):
            x = min(max(float(bind_eV) / max(kT_eV, 1.0e-300), -700.0), 700.0)
            boltz = math.exp(x)
            if isinstance(stat, float):
                saha_seed = q2 * stat * boltz
        photo = maybe_float(ar.get("photoionization_rate_s^-1")) or 0.0
        inv_proxy = maybe_float(milne.get("milne_inverse_rate_s^-1")) or 0.0
        inv_unscaled = maybe_float(milne.get("milne_inverse_rate_unscaled_s^-1")) or 0.0
        ratio_inv_photo = (inv_proxy / photo) if photo > 0.0 else ""
        rows.append({
            "row_kind": "type53_type74_ucalc_closure_audit",
            "audit_case": "type53_phint53_milne_closure",
            "provenance": "v0.3.71_source_code_aligned_type53_type74_closure_audit",
            "ucalc_source_file": "xstarlib/src/ucalc.f90",
            "xstar_source_routine": "phint53",
            "record": ar.get("record"),
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "target_ion_stage": ar.get("target_ion_stage"),
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "destination_or_bound_level": ar.get("bound_level"),
            "destination_or_bound_global_index": bg,
            "parent_continuum_global_index": cg,
            "destination_or_bound_label": bound.get("level_label"),
            "parent_continuum_label": cont.get("level_label"),
            "triplet_component": comp,
            "gglo_destination_or_bound": gb,
            "ggup_parent_or_continuum": gc,
            "statistical_weight_factor_gglo_over_ggup": stat,
            "binding_from_continuum_eV": bind_eV,
            "temperature_K": temperature,
            "electron_density_cm^-3": electron_density,
            "kT_eV": kT_eV,
            "xstar_q2_saha_prefactor_proxy": q2,
            "xstar_boltzmann_factor_proxy": boltz,
            "xstar_rnist_lte_seed_proxy": saha_seed,
            "xstar_ucalc_ans1_role": "photoionization_bound_to_parent_continuum_from_phint53",
            "xstar_ucalc_ans2_role": "milne_recombination_parent_continuum_to_bound_from_phint53",
            "current_python_ans1_photoionization_rate_s^-1": photo,
            "current_python_ans2_milne_inverse_rate_s^-1": inv_proxy,
            "current_python_milne_unscaled_rate_s^-1": inv_unscaled,
            "current_inverse_over_forward_ratio": ratio_inv_photo,
            "phint53_status": ar.get("phint53_status"),
            "current_milne_status": milne.get("milne_status"),
            "current_type53_milne_scale": milne.get("type53_milne_scale"),
            "closure_gap": "milne_ans2_is_currently_proxy_scaled_from_forward_rate_not_the_source_code_phint53_inverse_integral",
            "matrix_assembly_status": milne.get("assembly_status") or ar.get("assembly_status"),
            "missing_xstar_context": "exact_emltlv_rnist_arrays;true_Milne_integral;real_bremsa_radiation_field;optical_depth_escape_context;element_ion_fraction_normalization",
            "warning": "audit_only_not_assembled; use to identify phint53/Milne closure mismatch before changing rates",
        })
        component_sums.setdefault(comp, {"component": comp, "n_rows": 0})["n_rows"] += 1
        _acc(comp, "type53_photoionization_rate_sum_s^-1", photo)
        _acc(comp, "type53_current_milne_inverse_rate_sum_s^-1", inv_proxy)

    # Type-74 calt74/DR closure rows.
    for ar in type74_calt74_rate_audit_rows:
        rec = ar.get("record")
        proxy = by_record_t74_proxy.get(rec, {})
        comp = str(ar.get("triplet_component") or "other")
        alpha_unw = maybe_float(ar.get("type74_calt74_alpha_unweighted_cm3_s")) or 0.0
        alpha_w = maybe_float(ar.get("type74_calt74_alpha_weighted_cm3_s")) or 0.0
        forward = maybe_float(ar.get("type74_calt74_rate_forward_unscaled_s^-1")) or 0.0
        calt_inv = maybe_float(ar.get("type74_calt74_inverse_rate_s^-1")) or 0.0
        old_inv = maybe_float(proxy.get("type74_inverse_rate_s^-1")) or 0.0
        ratio_old_calt = (old_inv / calt_inv) if calt_inv > 0.0 else ""
        rows.append({
            "row_kind": "type53_type74_ucalc_closure_audit",
            "audit_case": "type74_calt74_dr_closure",
            "provenance": "v0.3.71_source_code_aligned_type53_type74_closure_audit",
            "ucalc_source_file": "xstarlib/src/ucalc.f90",
            "xstar_source_routine": "calt74",
            "record": rec,
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "target_ion_stage": ar.get("target_ion_stage"),
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "destination_or_bound_level": ar.get("destination_level"),
            "destination_or_bound_global_index": ar.get("destination_global_index"),
            "parent_continuum_global_index": ar.get("parent_continuum_global_index"),
            "destination_or_bound_label": meta.get(maybe_int(ar.get("destination_global_index")) or -1, {}).get("level_label"),
            "parent_continuum_label": meta.get(maybe_int(ar.get("parent_continuum_global_index")) or -1, {}).get("level_label"),
            "triplet_component": comp,
            "gglo_destination_or_bound": ar.get("destination_stat_weight_gglo"),
            "ggup_parent_or_continuum": ar.get("parent_continuum_stat_weight_ggup"),
            "statistical_weight_factor_gglo_over_ggup": ar.get("statistical_weight_factor_gglo_over_ggup"),
            "temperature_K": temperature,
            "electron_density_cm^-3": electron_density,
            "xstar_ucalc_ans1_role": "forward_delta_photoionization_rate_from_calt74",
            "xstar_ucalc_ans2_role": "inverse_DR_alpha_after_gglo_over_ggup_correction",
            "current_python_calt74_forward_rate_s^-1": forward,
            "current_python_calt74_alpha_unweighted_cm3_s": alpha_unw,
            "current_python_calt74_alpha_weighted_cm3_s": alpha_w,
            "current_python_calt74_inverse_rate_s^-1": calt_inv,
            "current_older_type74_inverse_proxy_rate_s^-1": old_inv,
            "older_type74_proxy_over_calt74_weighted_ratio": ratio_old_calt,
            "type74_calt74_status": ar.get("type74_calt74_status"),
            "current_type74_inverse_scale": ar.get("type74_inverse_scale"),
            "closure_gap": "calt74_gglo_over_ggup_is_audited_but_parent_continuum_population_and_absolute_radiation_context_are_still_proxy",
            "matrix_assembly_status": ar.get("assembly_status"),
            "missing_xstar_context": "real_bremsa_radiation_field;validated_parent_continuum_population;full_element_ion_fraction_closure;line_escape/opacity_context",
            "warning": "audit_only_not_assembled; compares source-aligned calt74 alpha with older direct type74 inverse proxy",
        })
        component_sums.setdefault(comp, {"component": comp, "n_rows": 0})["n_rows"] += 1
        _acc(comp, "type74_calt74_forward_rate_sum_s^-1", forward)
        _acc(comp, "type74_calt74_inverse_rate_sum_s^-1", calt_inv)
        _acc(comp, "type74_older_inverse_proxy_rate_sum_s^-1", old_inv)

    for comp in sorted(component_sums):
        d = component_sums[comp]
        t53inv = float(d.get("type53_current_milne_inverse_rate_sum_s^-1", 0.0))
        t74inv = float(d.get("type74_calt74_inverse_rate_sum_s^-1", 0.0))
        old74 = float(d.get("type74_older_inverse_proxy_rate_sum_s^-1", 0.0))
        rows.append({
            "row_kind": "type53_type74_ucalc_closure_audit",
            "audit_case": "component_summary",
            "provenance": "v0.3.71_source_code_aligned_type53_type74_closure_audit",
            "triplet_component": comp,
            "n_rows": d.get("n_rows", 0),
            "type53_photoionization_rate_sum_s^-1": d.get("type53_photoionization_rate_sum_s^-1", 0.0),
            "type53_current_milne_inverse_rate_sum_s^-1": t53inv,
            "type74_calt74_forward_rate_sum_s^-1": d.get("type74_calt74_forward_rate_sum_s^-1", 0.0),
            "type74_calt74_inverse_rate_sum_s^-1": t74inv,
            "type74_older_inverse_proxy_rate_sum_s^-1": old74,
            "total_current_source_code_aligned_inverse_proxy_s^-1": t53inv + t74inv,
            "total_current_older_inverse_proxy_s^-1": t53inv + old74,
            "older_vs_calt74_inverse_delta_s^-1": old74 - t74inv,
            "diagnostic_interpretation": "component-level closure summary; compare f/r source ratios against triplet target before adding any treatment",
        })

    rows.append({
        "row_kind": "type53_type74_ucalc_closure_audit",
        "audit_case": "audit_summary",
        "provenance": "v0.3.71_source_code_aligned_type53_type74_closure_audit",
        "n_type53_rows": len(type53_phint53_rate_audit_rows),
        "n_type74_calt74_rows": len(type74_calt74_rate_audit_rows),
        "n_total_rows_including_summaries": len(rows) + 1,
        "purpose": "locate f/r mismatch in source-code semantics rather than empirical scale scans",
        "main_hypothesis": "remaining_f_over_r_mismatch_is_due_to_type53_phint53_Milne_and_type74_calt74_closure_not_type50_escape_alone",
        "warning": "audit_only; no solver or physical-rate behavior is intentionally changed",
    })
    return rows


def _type53_type74_ucalc_closure_audit_summary(rows: Sequence[dict]) -> dict:
    component_rows = [r for r in rows if str(r.get("audit_case")) == "component_summary"]
    return {
        "n_type53_type74_ucalc_closure_audit_rows": len(rows),
        "audit_case_counts": _counts(rows, "audit_case"),
        "triplet_component_counts": _counts(rows, "triplet_component"),
        "total_type53_photoionization_rate_s^-1": _sum_float(rows, "current_python_ans1_photoionization_rate_s^-1"),
        "total_type53_milne_inverse_rate_s^-1": _sum_float(rows, "current_python_ans2_milne_inverse_rate_s^-1"),
        "total_type74_calt74_inverse_rate_s^-1": _sum_float(rows, "current_python_calt74_inverse_rate_s^-1"),
        "component_inverse_source_sums": {str(r.get("triplet_component")): r.get("total_current_source_code_aligned_inverse_proxy_s^-1") for r in component_rows},
        "warning": "v0.3.71 audit only; type53 Milne inverse, real radiation field, and element ion-fraction closure remain pending.",
    }

def build_global_type74_inverse_matrix_terms(type74_inverse_recombination_audit_rows: Sequence[dict]) -> List[dict]:
    """Map diagnostic type-74 inverse DR-delta rows into global matrix triplets."""
    rows: List[dict] = []
    tid = 0
    for ar in type74_inverse_recombination_audit_rows:
        dest_g = maybe_int(ar.get("destination_global_index"))
        cont_g = maybe_int(ar.get("parent_continuum_global_index"))
        rate = maybe_float(ar.get("type74_inverse_rate_s^-1")) or 0.0
        safe = bool(ar.get("topology_safe_for_inverse_matrix")) and dest_g is not None and cont_g is not None and rate > 0.0
        base = {
            "record": ar.get("record"),
            "data_type": ar.get("data_type"),
            "rate_type": ar.get("rate_type"),
            "target_ion_stage": ar.get("target_ion_stage"),
            "parent_ion_stage": ar.get("parent_ion_stage"),
            "destination_level": ar.get("destination_level"),
            "destination_global_index": dest_g,
            "parent_continuum_global_index": cont_g,
            "triplet_component": ar.get("triplet_component"),
            "inverse_recombination_mode": ar.get("inverse_recombination_mode"),
            "type74_inverse_scale": ar.get("type74_inverse_scale"),
            "matrix_safe_to_assemble_physically": False,
            "provenance": "v0.3.56_type74_inverse_matrix_topology",
        }
        if not safe:
            tid += 1
            rows.append({
                **base,
                "global_type74_inverse_term_id": tid,
                "row_kind": "global_type74_inverse_matrix_term",
                "matrix_term_kind": "skipped_type74_inverse_recombination",
                "matrix_role": "skipped_disabled_or_missing_mapping_or_zero_rate",
                "matrix_row_global_index": "",
                "matrix_col_global_index": "",
                "signed_rate_s^-1": "",
                "rate_s^-1": rate,
                "assembly_status": "skipped_type74_inverse_topology_or_rate_incomplete",
                "skip_reason": "disabled_or_missing_destination_or_parent_continuum_global_index_or_zero_rate",
            })
            continue
        tid += 1
        rows.append({
            **base,
            "global_type74_inverse_term_id": tid,
            "row_kind": "global_type74_inverse_matrix_term",
            "matrix_term_kind": "offdiag_parent_continuum_to_type74_destination_gain",
            "matrix_role": "M[destination_global_index,parent_continuum_global_index]+=type74_inverse_rate_proxy",
            "matrix_row_global_index": dest_g,
            "matrix_col_global_index": cont_g,
            "signed_rate_s^-1": rate,
            "rate_s^-1": rate,
            "assembly_status": "assembled_diagnostic_type74_inverse_topology_proxy",
            "skip_reason": "",
        })
        tid += 1
        rows.append({
            **base,
            "global_type74_inverse_term_id": tid,
            "row_kind": "global_type74_inverse_matrix_term",
            "matrix_term_kind": "diagonal_parent_continuum_type74_inverse_loss",
            "matrix_role": "M[parent_continuum_global_index,parent_continuum_global_index]-=type74_inverse_rate_proxy",
            "matrix_row_global_index": cont_g,
            "matrix_col_global_index": cont_g,
            "signed_rate_s^-1": -rate,
            "rate_s^-1": rate,
            "assembly_status": "assembled_diagnostic_type74_inverse_topology_proxy",
            "skip_reason": "",
        })
    return rows


def _type53_milne_inverse_audit_summary(rows: Sequence[dict]) -> dict:
    return {
        "n_type53_milne_inverse_audit_rows": len(rows),
        "rows_by_status": _counts(rows, "milne_status"),
        "rows_by_assembly_status": _counts(rows, "assembly_status"),
        "total_milne_inverse_rate_s^-1": _sum_float(rows, "milne_inverse_rate_s^-1"),
        "total_milne_inverse_rate_unscaled_s^-1": _sum_float(rows, "milne_inverse_rate_unscaled_s^-1"),
        "warning": "Diagnostic Milne inverse scaffold only; true XSTAR Milne integral is not yet evaluated.",
    }


def _global_type53_milne_matrix_terms_summary(rows: Sequence[dict]) -> dict:
    return {
        "n_global_type53_milne_matrix_term_rows": len(rows),
        "rows_by_matrix_term_kind": _counts(rows, "matrix_term_kind"),
        "rows_by_assembly_status": _counts(rows, "assembly_status"),
        "total_signed_rate_s^-1": _sum_float(rows, "signed_rate_s^-1"),
        "total_rate_s^-1": _sum_float(rows, "rate_s^-1"),
    }


def _type74_inverse_recombination_audit_summary(rows: Sequence[dict]) -> dict:
    return {
        "n_type74_inverse_recombination_audit_rows": len(rows),
        "rows_by_triplet_component": _counts(rows, "triplet_component"),
        "rows_by_assembly_status": _counts(rows, "assembly_status"),
        "total_type74_inverse_rate_s^-1": _sum_float(rows, "type74_inverse_rate_s^-1"),
        "warning": "Diagnostic type-74 inverse DR-delta topology only; true parent-continuum balance is pending.",
    }


def _global_type74_inverse_matrix_terms_summary(rows: Sequence[dict]) -> dict:
    return {
        "n_global_type74_inverse_matrix_term_rows": len(rows),
        "rows_by_matrix_term_kind": _counts(rows, "matrix_term_kind"),
        "rows_by_assembly_status": _counts(rows, "assembly_status"),
        "total_signed_rate_s^-1": _sum_float(rows, "signed_rate_s^-1"),
        "total_rate_s^-1": _sum_float(rows, "rate_s^-1"),
    }


def build_inverse_recombination_scale_scan_rows(
    *,
    global_index_rows: Sequence[dict],
    global_bound_bound_matrix_terms: Sequence[dict],
    global_superlevel_cascade_matrix_terms: Sequence[dict],
    global_superlevel_source_matrix_terms: Sequence[dict],
    global_type53_flat_proxy_matrix_terms: Sequence[dict],
    global_type53_phint53_matrix_terms: Sequence[dict],
    type53_phint53_rate_audit_rows: Sequence[dict],
    type74_triplet_source_audit_rows: Sequence[dict],
    coupling_rows: Sequence[dict],
    line_rows: Sequence[dict],
    he_like_stage: int,
    inverse_recombination_mode: str = "none",
    type53_milne_scale: object = "1",
    type74_inverse_scale: object = "1",
    linear_solver: str = "xstar-lucy",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    prune_null_rate_levels: bool = True,
) -> List[dict]:
    """Scan independent diagnostic inverse-recombination scale factors.

    XSTAR uses the Milne branch from phint53 and DR-delta rates from type 74 in
    ucalc/calt74, so scanning the two inverse channels independently is a useful
    diagnostic before the real radiation/continuum context is ported.  This scan
    still uses the v0.3.55 proxy inverse rates; it tests matrix sensitivity and
    scale, not physical correctness.
    """
    mode = _normalise_inverse_recombination_mode(inverse_recombination_mode)
    milne_scales = _parse_triplet_source_scales(type53_milne_scale)
    type74_scales = _parse_triplet_source_scales(type74_inverse_scale)
    rows: List[dict] = []

    def _run_case(case: str, ms: float, ts: float) -> dict:
        milne_audit = build_type53_milne_inverse_audit_rows(
            type53_phint53_rate_audit_rows=type53_phint53_rate_audit_rows,
            global_index_rows=global_index_rows,
            inverse_recombination_mode=mode,
            type53_milne_scale=ms,
        )
        milne_terms = build_global_type53_milne_matrix_terms(milne_audit)
        t74_audit = build_type74_inverse_recombination_audit_rows(
            type74_triplet_source_audit_rows=type74_triplet_source_audit_rows,
            global_index_rows=global_index_rows,
            inverse_recombination_mode=mode,
            type74_inverse_scale=ts,
        )
        t74_terms = build_global_type74_inverse_matrix_terms(t74_audit)
        full_terms = build_full_global_matrix_terms(
            global_index_rows=global_index_rows,
            global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
            global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
            global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
            global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
            global_type53_phint53_matrix_terms=global_type53_phint53_matrix_terms,
            global_type53_milne_matrix_terms=milne_terms,
            global_type74_inverse_matrix_terms=t74_terms,
            coupling_rows=coupling_rows,
            he_like_stage=he_like_stage,
        )
        comp_rows = build_full_global_normalized_solve_comparison(
            global_index_rows=global_index_rows,
            full_global_matrix_terms=full_terms,
            line_rows=line_rows,
            he_like_stage=he_like_stage,
            linear_solver=linear_solver,
            rank_deficient_action=rank_deficient_action,
            negative_population_action=negative_population_action,
            prune_null_rate_levels=prune_null_rate_levels,
        )
        sol = next((r for r in comp_rows if str(r.get("row_kind")) == "summary" and str(r.get("comparison_case")) == "full_global_normalized_proxy_topology_solve"), comp_rows[0] if comp_rows else {})
        return {
            "row_kind": "inverse_recombination_scale_scan",
            "scan_case": case,
            "inverse_recombination_mode": mode,
            "type53_milne_scale": float(ms),
            "type74_inverse_scale": float(ts),
            "n_type53_milne_audit_rows": len(milne_audit),
            "n_global_type53_milne_matrix_term_rows": len(milne_terms),
            "total_milne_inverse_rate_unscaled_s^-1": _sum_float(milne_audit, "milne_inverse_rate_unscaled_s^-1"),
            "total_milne_inverse_rate_scaled_s^-1": _sum_float(milne_audit, "milne_inverse_rate_s^-1"),
            "n_type74_inverse_audit_rows": len(t74_audit),
            "n_global_type74_inverse_matrix_term_rows": len(t74_terms),
            "total_type74_inverse_rate_unscaled_s^-1": _sum_float(t74_audit, "type74_inverse_rate_unscaled_s^-1"),
            "total_type74_inverse_rate_scaled_s^-1": _sum_float(t74_audit, "type74_inverse_rate_s^-1"),
            "solver": sol.get("solver"),
            "solve_status": sol.get("solve_status"),
            "solver_warning": sol.get("solver_warning"),
            "f_fraction": sol.get("f_fraction"),
            "i_fraction": sol.get("i_fraction"),
            "r_fraction": sol.get("r_fraction"),
            "R": sol.get("R"),
            "G": sol.get("G"),
            "l2_distance_to_target": sol.get("l2_distance_to_target"),
            "sum_population": sol.get("sum_population"),
            "normalization_residual": sol.get("normalization_residual"),
            "residual_norm": sol.get("residual_norm"),
            "n_negative_populations": sol.get("n_negative_populations"),
            "ion_population_sums_json": sol.get("ion_population_sums_json"),
            "level_kind_population_sums_json": sol.get("level_kind_population_sums_json"),
            "xstar_lucy_niter": sol.get("xstar_lucy_niter"),
            "xstar_lucy_diff": sol.get("xstar_lucy_diff"),
            "n_matrix_terms": len(full_terms),
            "provenance": "v0.3.56_inverse_recombination_independent_scale_scan",
            "warning": "Independent inverse-recombination scan uses diagnostic proxy inverse rates; true XSTAR Milne/calt74 balance and radiation context are pending.",
        }

    rows.append(_run_case("baseline_primary_scales", milne_scales[0] if milne_scales else 1.0, type74_scales[0] if type74_scales else 1.0))
    base_type74 = type74_scales[0] if type74_scales else 1.0
    for ms in milne_scales:
        rows.append(_run_case("type53_milne_scale_scan_type74_fixed", ms, base_type74))
    base_milne = milne_scales[0] if milne_scales else 1.0
    for ts in type74_scales:
        rows.append(_run_case("type74_inverse_scale_scan_milne_fixed", base_milne, ts))
    # Include a compact full grid when both lists are modest; this helps expose
    # degeneracies but avoids runaway output for very long user lists.
    if len(milne_scales) * len(type74_scales) <= 64:
        for ms in milne_scales:
            for ts in type74_scales:
                if ms == base_milne and ts == base_type74:
                    continue
                rows.append(_run_case("type53_milne_x_type74_inverse_grid", ms, ts))
    return rows

def _inverse_recombination_scale_scan_summary(rows: Sequence[dict]) -> dict:
    scan_rows = [r for r in rows if str(r.get("row_kind")) == "inverse_recombination_scale_scan"]
    best = None
    for r in scan_rows:
        d = maybe_float(r.get("l2_distance_to_target"))
        if d is None:
            continue
        if best is None or float(d) < float(best.get("l2_distance_to_target")):
            best = r
    return {
        "n_inverse_recombination_scale_scan_rows": len(rows),
        "scan_cases": _counts(rows, "scan_case"),
        "modes": sorted({str(r.get("inverse_recombination_mode")) for r in rows}),
        "type53_milne_scale_values": sorted({float(maybe_float(r.get("type53_milne_scale")) or 0.0) for r in rows}),
        "type74_inverse_scale_values": sorted({float(maybe_float(r.get("type74_inverse_scale")) or 0.0) for r in rows}),
        "best_scan_case": None if best is None else best.get("scan_case"),
        "best_type53_milne_scale": None if best is None else best.get("type53_milne_scale"),
        "best_type74_inverse_scale": None if best is None else best.get("type74_inverse_scale"),
        "best_l2_distance_to_target": None if best is None else best.get("l2_distance_to_target"),
        "best_f_fraction": None if best is None else best.get("f_fraction"),
        "best_i_fraction": None if best is None else best.get("i_fraction"),
        "best_r_fraction": None if best is None else best.get("r_fraction"),
        "warning": "Independent inverse-recombination scans are diagnostic only until true XSTAR Milne/calt74 rates and continuum balance are ported.",
    }



def _add_refined_triplet_target_metrics(rows: Sequence[dict], *, he_like_stage: int) -> List[dict]:
    """Add target-aware metrics to inverse-recombination refined scan rows.

    The refined scan is meant to diagnose the region where f and r are already
    close to the C V XSTAR target but intercombination remains low.  The added
    fields therefore include both the ordinary L2 distance and an
    intercombination-weighted score.  The score is diagnostic only and should not
    be treated as a physical objective function.
    """
    target = _xstar_triplet_target(he_like_stage)
    if target is None:
        return [dict(r) for r in rows]
    tf = float(target.get("f", 0.0))
    ti = float(target.get("i", 0.0))
    tr = float(target.get("r", 0.0))
    out: List[dict] = []
    for r0 in rows:
        r = dict(r0)
        f = maybe_float(r.get("f_fraction")) or 0.0
        i = maybe_float(r.get("i_fraction")) or 0.0
        rr = maybe_float(r.get("r_fraction")) or 0.0
        df = float(f) - tf
        di = float(i) - ti
        dr = float(rr) - tr
        l2 = math.sqrt(df * df + di * di + dr * dr)
        fr_l2 = math.sqrt(df * df + dr * dr)
        i_abs = abs(di)
        # Up-weight i because the current good region matches f/r reasonably but
        # systematically underpredicts intercombination.  This is a diagnostic
        # ranking, not a fit statistic.
        weighted = math.sqrt(df * df + (5.0 * di) * (5.0 * di) + dr * dr)
        r.update({
            "target_f_fraction": tf,
            "target_i_fraction": ti,
            "target_r_fraction": tr,
            "delta_f_minus_target": df,
            "delta_i_minus_target": di,
            "delta_r_minus_target": dr,
            "l2_distance_to_target_recomputed": l2,
            "fr_l2_distance_to_target": fr_l2,
            "i_abs_error_to_target": i_abs,
            "i_fraction_to_target_ratio": (float(i) / ti if ti > 0.0 else ""),
            "intercombination_weighted_score_w5": weighted,
        })
        out.append(r)
    return out


def build_inverse_recombination_refined_scale_scan_rows(
    *,
    global_index_rows: Sequence[dict],
    global_bound_bound_matrix_terms: Sequence[dict],
    global_superlevel_cascade_matrix_terms: Sequence[dict],
    global_superlevel_source_matrix_terms: Sequence[dict],
    global_type53_flat_proxy_matrix_terms: Sequence[dict],
    global_type53_phint53_matrix_terms: Sequence[dict],
    type53_phint53_rate_audit_rows: Sequence[dict],
    type74_triplet_source_audit_rows: Sequence[dict],
    coupling_rows: Sequence[dict],
    line_rows: Sequence[dict],
    he_like_stage: int,
    inverse_recombination_mode: str = "none",
    type53_milne_refined_scale: object = "1e9,3e9,1e10,3e10,1e11",
    type74_inverse_refined_scale: object = "1e8,3e8,1e9,3e9,1e10,3e10,1e11,3e11,1e12",
    linear_solver: str = "xstar-lucy",
    rank_deficient_action: str = "svd",
    negative_population_action: str = "keep",
    prune_null_rate_levels: bool = True,
) -> List[dict]:
    """Refined inverse-recombination scale scan around the promising region.

    v0.3.58 showed that the coarse scan becomes close to the C V f/r target near
    type53_milne_scale ~ 1e10 and type74_inverse_scale ~ 1e8--1e12, but i is
    still low.  This routine writes a narrower grid with intercombination-aware
    ranking fields.
    """
    rows = build_inverse_recombination_scale_scan_rows(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
        global_type53_phint53_matrix_terms=global_type53_phint53_matrix_terms,
        type53_phint53_rate_audit_rows=type53_phint53_rate_audit_rows,
        type74_triplet_source_audit_rows=type74_triplet_source_audit_rows,
        coupling_rows=coupling_rows,
        line_rows=line_rows,
        he_like_stage=he_like_stage,
        inverse_recombination_mode=inverse_recombination_mode,
        type53_milne_scale=type53_milne_refined_scale,
        type74_inverse_scale=type74_inverse_refined_scale,
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
        prune_null_rate_levels=prune_null_rate_levels,
    )
    out: List[dict] = []
    for r0 in _add_refined_triplet_target_metrics(rows, he_like_stage=he_like_stage):
        r = dict(r0)
        r["refined_scan_region"] = "type53_milne_1e9_to_1e11_type74_1e8_to_1e12_default" 
        r["provenance"] = "v0.3.59_refined_inverse_recombination_scale_scan"
        r["warning"] = "Refined scan is diagnostic; rates remain scaled proxy/source-aligned inverse-recombination terms until physical XSTAR Milne/calt74 and continuum closure are complete."
        out.append(r)
    return out


def _inverse_recombination_refined_scale_scan_summary(rows: Sequence[dict]) -> dict:
    scan_rows = [r for r in rows if str(r.get("row_kind")) == "inverse_recombination_scale_scan"]
    def _best_by(col: str):
        best = None
        for r in scan_rows:
            val = maybe_float(r.get(col))
            if val is None:
                continue
            if best is None or float(val) < float(best.get(col)):
                best = r
        return best
    best_l2 = _best_by("l2_distance_to_target") or _best_by("l2_distance_to_target_recomputed")
    best_i = _best_by("i_abs_error_to_target")
    best_w = _best_by("intercombination_weighted_score_w5")
    def _pack(prefix: str, r: Optional[dict]) -> dict:
        if r is None:
            return {f"{prefix}_scan_case": None}
        return {
            f"{prefix}_scan_case": r.get("scan_case"),
            f"{prefix}_type53_milne_scale": r.get("type53_milne_scale"),
            f"{prefix}_type74_inverse_scale": r.get("type74_inverse_scale"),
            f"{prefix}_f_fraction": r.get("f_fraction"),
            f"{prefix}_i_fraction": r.get("i_fraction"),
            f"{prefix}_r_fraction": r.get("r_fraction"),
            f"{prefix}_l2_distance_to_target": r.get("l2_distance_to_target"),
            f"{prefix}_i_abs_error_to_target": r.get("i_abs_error_to_target"),
            f"{prefix}_intercombination_weighted_score_w5": r.get("intercombination_weighted_score_w5"),
        }
    summary = {
        "n_inverse_recombination_refined_scale_scan_rows": len(rows),
        "scan_cases": _counts(rows, "scan_case"),
        "type53_milne_scale_values": sorted({float(maybe_float(r.get("type53_milne_scale")) or 0.0) for r in rows}),
        "type74_inverse_scale_values": sorted({float(maybe_float(r.get("type74_inverse_scale")) or 0.0) for r in rows}),
        "warning": "Refined inverse-recombination scans are diagnostic and intercombination-weighted metrics are ranking aids only.",
    }
    summary.update(_pack("best_l2", best_l2))
    summary.update(_pack("best_i", best_i))
    summary.update(_pack("best_intercombination_weighted", best_w))
    return summary

def build_full_global_matrix_terms(
    *,
    global_index_rows: Sequence[dict],
    global_bound_bound_matrix_terms: Sequence[dict],
    global_superlevel_cascade_matrix_terms: Sequence[dict],
    global_superlevel_source_matrix_terms: Sequence[dict],
    global_type53_flat_proxy_matrix_terms: Sequence[dict],
    global_type53_phint53_matrix_terms: Sequence[dict] | None = None,
    global_type53_milne_matrix_terms: Sequence[dict] | None = None,
    global_type74_inverse_matrix_terms: Sequence[dict] | None = None,
    global_type74_calt74_matrix_terms: Sequence[dict] | None = None,
    coupling_rows: Sequence[dict] = (),
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

    phint53_terms = list(global_type53_phint53_matrix_terms or [])
    n_phint53_assembled = sum(1 for r in phint53_terms if str(r.get("assembly_status")) == "assembled_phint53_photoionization_kernel_topology")
    if n_phint53_assembled > 0:
        for r in phint53_terms:
            if str(r.get("assembly_status")) == "assembled_phint53_photoionization_kernel_topology":
                _add(r, component="type53_phint53_photoionization_kernel", source_row_kind="global_type53_phint53_matrix_term")
    else:
        for r in global_type53_flat_proxy_matrix_terms:
            if str(r.get("assembly_status")) == "diagnostic_proxy_topology_only_not_used_in_solve":
                _add(r, component="type53_flat_photoionization_proxy", source_row_kind="global_type53_flat_proxy_matrix_term")

    for r in (global_type53_milne_matrix_terms or []):
        status = str(r.get("assembly_status"))
        if status == "assembled_diagnostic_milne_inverse_topology_proxy":
            _add(r, component="type53_milne_inverse_recombination_proxy", source_row_kind="global_type53_milne_matrix_term")
        elif status == "assembled_xstar_ucalc_phint53_milne_inverse":
            _add(r, component="type53_xstar_ucalc_phint53_milne_inverse", source_row_kind="global_type53_milne_matrix_term")

    calt74_terms = list(global_type74_calt74_matrix_terms or [])
    n_calt74_assembled = sum(1 for r in calt74_terms if str(r.get("assembly_status")) == "assembled_diagnostic_type74_calt74_inverse_topology")
    if n_calt74_assembled > 0:
        for r in calt74_terms:
            if str(r.get("assembly_status")) == "assembled_diagnostic_type74_calt74_inverse_topology":
                _add(r, component="type74_calt74_inverse_recombination_diagnostic", source_row_kind="global_type74_calt74_matrix_term")
    else:
        for r in (global_type74_inverse_matrix_terms or []):
            if str(r.get("assembly_status")) == "assembled_diagnostic_type74_inverse_topology_proxy":
                _add(r, component="type74_direct_inverse_recombination_proxy", source_row_kind="global_type74_inverse_matrix_term")

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



def build_type50_ucalc_rate_audit_rows(
    *,
    global_bound_bound_matrix_terms: Sequence[dict],
    he_like_stage: int,
) -> List[dict]:
    """Audit v0.3.67 XSTAR-ucalc-style type-50 bound-bound rate treatment.

    One row is emitted for each assembled type-50 radiative decay off-diagonal
    term.  Photoexcitation proxy rows are summarized through their matching
    treatment columns rather than emitted as separate primary transition rows.
    """
    out: List[dict] = []
    seen = set()
    for row in global_bound_bound_matrix_terms:
        if str(row.get("matrix_term_kind") or "") != "offdiag_gain":
            continue
        if str(row.get("transition_kind") or "") != "radiative_decay":
            continue
        if _infer_transition_data_type(row) != 50:
            continue
        key = (row.get("record"), row.get("ion_stage"), row.get("from_level"), row.get("to_level"))
        if key in seen:
            continue
        seen.add(key)
        raw_a = _bounded_nonnegative_float(row.get("raw_A_s^-1") if row.get("raw_A_s^-1") not in (None, "") else row.get("raw_rate_s^-1"), 0.0)
        eff = _bounded_nonnegative_float(row.get("escaped_decay_rate_s^-1") if row.get("escaped_decay_rate_s^-1") not in (None, "") else row.get("rate_s^-1"), 0.0)
        pump = _bounded_nonnegative_float(row.get("photoexcitation_rate_s^-1"), 0.0)
        from_label = str(row.get("from_level_label") or "")
        to_label = str(row.get("to_level_label") or "")
        is_triplet_uv_drain = (maybe_int(row.get("ion_stage")) == int(he_like_stage) and "1s1.2p1.3P" in from_label and "1s1.2s1.3S" in to_label)
        out.append({
            "row_kind": "type50_ucalc_rate_audit",
            "element": row.get("element"),
            "ion_stage": row.get("ion_stage"),
            "record": row.get("record"),
            "from_level": row.get("from_level"),
            "to_level": row.get("to_level"),
            "from_global_index": row.get("from_global_index"),
            "to_global_index": row.get("to_global_index"),
            "from_level_label": from_label,
            "to_level_label": to_label,
            "is_helike_3p_to_3s_uv_drain": bool(is_triplet_uv_drain),
            "raw_A_s^-1": raw_a,
            "current_matrix_decay_rate_s^-1": row.get("rate_s^-1"),
            "type50_bound_bound_treatment": row.get("type50_bound_bound_treatment"),
            "ptmp1_proxy": row.get("ptmp1_proxy"),
            "ptmp2_proxy": row.get("ptmp2_proxy"),
            "ptmp_sum_proxy": row.get("ptmp_sum_proxy"),
            "escaped_decay_rate_s^-1": eff,
            "photoexcitation_rate_s^-1": pump,
            "decay_rate_multiplier_vs_raw_A": (eff / raw_a) if raw_a > 0 else "",
            "photoexcitation_rate_multiplier_vs_raw_A": (pump / raw_a) if raw_a > 0 else "",
            "ucalc_ans1_matrix_lower_to_upper_proxy_s^-1": row.get("ucalc_ans1_matrix_lower_to_upper_proxy_s^-1"),
            "ucalc_ans2_matrix_upper_to_lower_proxy_s^-1": row.get("ucalc_ans2_matrix_upper_to_lower_proxy_s^-1"),
            "ucalc_context_status": row.get("ucalc_context_status"),
            "xstar_source_path": "ucalc.f90 type-50: ans2 radiative decay is A*(ptmp1+ptmp2); ans1 radiative excitation/pumping requires bremsa/flinabs context",
            "provenance": "v0.3.67_type50_ucalc_bound_bound_rate_audit",
        })
    if out:
        triplet = [r for r in out if r.get("is_helike_3p_to_3s_uv_drain")]
        out.append({
            "row_kind": "type50_ucalc_rate_audit_summary",
            "n_type50_rows": len(out),
            "n_helike_3p_to_3s_uv_drain_rows": len(triplet),
            "sum_raw_A_helike_3p_to_3s_s^-1": sum(float(r.get("raw_A_s^-1") or 0.0) for r in triplet),
            "sum_escaped_decay_helike_3p_to_3s_s^-1": sum(float(r.get("escaped_decay_rate_s^-1") or 0.0) for r in triplet),
            "sum_photoexcitation_3s_to_3p_proxy_s^-1": sum(float(r.get("photoexcitation_rate_s^-1") or 0.0) for r in triplet),
            "treatment": triplet[0].get("type50_bound_bound_treatment") if triplet else "",
            "diagnostic_note": "Default raw-A reproduces v0.3.66. xstar-escape and xstar-escape-photoexcitation are controlled diagnostics until real tau, pescl/pescv, bremsa, and flinabs are ported.",
            "provenance": "v0.3.67_type50_ucalc_bound_bound_rate_audit",
        })
    return out


def _type50_ucalc_rate_audit_summary(rows: Sequence[dict]) -> dict:
    detail = [r for r in rows if str(r.get("row_kind")) == "type50_ucalc_rate_audit"]
    triplet = [r for r in detail if bool(r.get("is_helike_3p_to_3s_uv_drain"))]
    return {
        "n_type50_ucalc_rate_audit_rows": len(rows),
        "n_type50_detail_rows": len(detail),
        "n_helike_3p_to_3s_uv_drain_rows": len(triplet),
        "rows_by_type50_bound_bound_treatment": _counts(detail, "type50_bound_bound_treatment"),
        "sum_raw_A_helike_3p_to_3s_s^-1": sum(float(r.get("raw_A_s^-1") or 0.0) for r in triplet),
        "sum_escaped_decay_helike_3p_to_3s_s^-1": sum(float(r.get("escaped_decay_rate_s^-1") or 0.0) for r in triplet),
        "sum_photoexcitation_3s_to_3p_proxy_s^-1": sum(float(r.get("photoexcitation_rate_s^-1") or 0.0) for r in triplet),
        "provenance": "v0.3.67_type50_ucalc_bound_bound_rate_audit",
    }


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




def _normalise_triplet_coupling_treatment(value: object) -> str:
    """Return a supported v0.3.63 triplet-coupling treatment string."""
    text = str(value or "normal").strip().lower().replace("_", "-")
    aliases = {
        "": "normal",
        "none": "normal",
        "default": "normal",
        "audit": "audit-only",
        "audit-only": "audit-only",
        "normal": "normal",
        "suppress": "suppress-3p-to-3s-radiative",
        "suppress-3p-3s": "suppress-3p-to-3s-radiative",
        "suppress-3p-to-3s": "suppress-3p-to-3s-radiative",
        "suppress-3p-to-3s-radiative": "suppress-3p-to-3s-radiative",
    }
    if text not in aliases:
        raise ValueError(f"Unsupported triplet coupling treatment {value!r}")
    return aliases[text]


def _is_3p_to_3s_radiative_drain_term(row: Mapping[str, object], *, he_like_stage: int) -> bool:
    """Identify the suspicious He-like 1s2p 3P_J -> 1s2s 3S1 type-50 drain terms.

    The full-global matrix uses column=source and row=destination.  These
    records appear as both off-diagonal gain rows M[3S,3P]+=A and diagonal
    loss rows M[3P,3P]-=A, but the common metadata retains
    from_level_label=3P and to_level_label=3S for both rows.
    """
    if maybe_int(row.get("ion_stage")) != int(he_like_stage):
        return False
    if str(row.get("transition_kind") or "") != "radiative_decay":
        return False
    if "data_type_50" not in str(row.get("source_method") or ""):
        return False
    from_label = str(row.get("from_level_label") or "")
    to_label = str(row.get("to_level_label") or "")
    if "1s1.2p1.3P" not in from_label:
        return False
    if "1s1.2s1.3S" not in to_label:
        return False
    role = str(row.get("matrix_term_kind") or "")
    return role in {"offdiag_gain", "diagonal_loss"}


def suppress_triplet_3p_to_3s_radiative_terms(
    full_global_matrix_terms: Sequence[dict],
    *,
    he_like_stage: int,
) -> Tuple[List[dict], List[dict]]:
    """Return (filtered_terms, suppressed_terms) for the v0.3.63 diagnostic test."""
    kept: List[dict] = []
    suppressed: List[dict] = []
    for row in full_global_matrix_terms:
        if _is_3p_to_3s_radiative_drain_term(row, he_like_stage=he_like_stage):
            r = dict(row)
            r["triplet_coupling_treatment"] = "suppress-3p-to-3s-radiative"
            r["suppression_reason"] = "diagnostic suppression of type-50 1s2p 3P_J -> 1s2s 3S1 radiative population-transfer drain"
            suppressed.append(r)
        else:
            kept.append(dict(row))
    return kept, suppressed


def _summary_row_from_full_global_solve(rows: Sequence[dict]) -> dict:
    for row in rows:
        if row.get("row_kind") == "summary" and row.get("comparison_case") == "full_global_normalized_proxy_topology_solve":
            return dict(row)
    return {}


def build_triplet_coupling_suppression_comparison_rows(
    *,
    global_index_rows: Sequence[dict],
    full_global_matrix_terms: Sequence[dict],
    line_rows: Sequence[dict],
    he_like_stage: int,
    linear_solver: str,
    rank_deficient_action: str,
    negative_population_action: str,
    prune_null_rate_levels: bool,
) -> List[dict]:
    """Compare normal vs suppressed 3P_J->3S1 radiative-drain full-global solves.

    This is a controlled v0.3.63 diagnostic: it deliberately suppresses only
    the type-50 population-transfer terms identified in v0.3.62, while leaving
    intercombination-to-ground, forbidden-to-ground, resonance, type-63
    collisional coupling, type-53, type-74, type-99, and type-71 terms intact.
    """
    suppressed_matrix_terms, suppressed_terms = suppress_triplet_3p_to_3s_radiative_terms(
        full_global_matrix_terms, he_like_stage=he_like_stage
    )
    normal_rows = build_full_global_normalized_solve_comparison(
        global_index_rows=global_index_rows,
        full_global_matrix_terms=full_global_matrix_terms,
        line_rows=line_rows,
        he_like_stage=he_like_stage,
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
        prune_null_rate_levels=prune_null_rate_levels,
    )
    suppressed_rows = build_full_global_normalized_solve_comparison(
        global_index_rows=global_index_rows,
        full_global_matrix_terms=suppressed_matrix_terms,
        line_rows=line_rows,
        he_like_stage=he_like_stage,
        linear_solver=linear_solver,
        rank_deficient_action=rank_deficient_action,
        negative_population_action=negative_population_action,
        prune_null_rate_levels=prune_null_rate_levels,
    )
    normal = _summary_row_from_full_global_solve(normal_rows)
    supp = _summary_row_from_full_global_solve(suppressed_rows)
    out: List[dict] = []
    def _emit(case: str, row: Mapping[str, object], *, n_suppressed: int) -> None:
        out.append({
            "row_kind": "triplet_coupling_suppression_summary",
            "comparison_case": case,
            "triplet_coupling_treatment": "normal" if case == "normal_full_global" else "suppress-3p-to-3s-radiative",
            "n_suppressed_matrix_terms": 0 if case == "normal_full_global" else n_suppressed,
            "f_fraction": row.get("f_fraction"),
            "i_fraction": row.get("i_fraction"),
            "r_fraction": row.get("r_fraction"),
            "R": row.get("R"),
            "G": row.get("G"),
            "l2_distance_to_target": row.get("l2_distance_to_target"),
            "solve_status": row.get("solve_status"),
            "solver": row.get("solver"),
            "n_negative_populations": row.get("n_negative_populations"),
            "sum_population": row.get("sum_population"),
            "ion_population_sums_json": row.get("ion_population_sums_json"),
            "level_kind_population_sums_json": row.get("level_kind_population_sums_json"),
            "diagnostic_note": "v0.3.63 controlled diagnostic; suppression is not physical by default",
        })
    _emit("normal_full_global", normal, n_suppressed=len(suppressed_terms))
    _emit("suppress_3p_to_3s_radiative", supp, n_suppressed=len(suppressed_terms))
    if normal and supp:
        out.append({
            "row_kind": "triplet_coupling_suppression_delta",
            "comparison_case": "suppressed_minus_normal",
            "triplet_coupling_treatment": "suppress-3p-to-3s-radiative",
            "n_suppressed_matrix_terms": len(suppressed_terms),
            "delta_f": float(maybe_float(supp.get("f_fraction")) or 0.0) - float(maybe_float(normal.get("f_fraction")) or 0.0),
            "delta_i": float(maybe_float(supp.get("i_fraction")) or 0.0) - float(maybe_float(normal.get("i_fraction")) or 0.0),
            "delta_r": float(maybe_float(supp.get("r_fraction")) or 0.0) - float(maybe_float(normal.get("r_fraction")) or 0.0),
            "delta_l2": float(maybe_float(supp.get("l2_distance_to_target")) or 0.0) - float(maybe_float(normal.get("l2_distance_to_target")) or 0.0),
            "diagnostic_note": "Positive delta_i would support the v0.3.62 hypothesis that type-50 3P->3S drains suppress intercombination emission.",
        })
    for i, row in enumerate(suppressed_terms):
        out.append({
            "row_kind": "suppressed_matrix_term",
            "comparison_case": "suppressed_3p_to_3s_radiative_term",
            "suppressed_term_index": i,
            "full_global_term_id": row.get("full_global_term_id"),
            "record": row.get("record"),
            "transition_kind": row.get("transition_kind"),
            "source_method": row.get("source_method"),
            "matrix_term_kind": row.get("matrix_term_kind"),
            "matrix_role": row.get("matrix_role"),
            "matrix_row_global_index": row.get("matrix_row_global_index"),
            "matrix_col_global_index": row.get("matrix_col_global_index"),
            "from_level": row.get("from_level"),
            "to_level": row.get("to_level"),
            "from_level_label": row.get("from_level_label"),
            "to_level_label": row.get("to_level_label"),
            "rate_s^-1": row.get("rate_s^-1"),
            "signed_rate_s^-1": row.get("signed_rate_s^-1"),
            "full_global_component": row.get("full_global_component"),
            "suppression_reason": row.get("suppression_reason"),
        })
    return out


def _triplet_coupling_suppression_comparison_summary(rows: Sequence[dict]) -> dict:
    summaries = [r for r in rows if r.get("row_kind") == "triplet_coupling_suppression_summary"]
    delta = next((r for r in rows if r.get("row_kind") == "triplet_coupling_suppression_delta"), {})
    suppressed_terms = [r for r in rows if r.get("row_kind") == "suppressed_matrix_term"]
    normal = next((r for r in summaries if r.get("comparison_case") == "normal_full_global"), {})
    supp = next((r for r in summaries if r.get("comparison_case") == "suppress_3p_to_3s_radiative"), {})
    return {
        "n_triplet_coupling_suppression_comparison_rows": len(rows),
        "n_suppressed_matrix_terms": len(suppressed_terms),
        "normal_f_fraction": normal.get("f_fraction"),
        "normal_i_fraction": normal.get("i_fraction"),
        "normal_r_fraction": normal.get("r_fraction"),
        "suppressed_f_fraction": supp.get("f_fraction"),
        "suppressed_i_fraction": supp.get("i_fraction"),
        "suppressed_r_fraction": supp.get("r_fraction"),
        "delta_i_suppressed_minus_normal": delta.get("delta_i"),
        "delta_l2_suppressed_minus_normal": delta.get("delta_l2"),
        "warning": "Diagnostic comparison only; suppressing type-50 3P_J->3S1 radiative drains is not a physical default.",
    }





def _xstar_ludcmp(a: np.ndarray, *, tiny: float = 1.0e-30):
    """Numerical-Recipes-style LU decomposition with scaled partial pivoting.

    This mirrors the algorithmic role of XSTAR's ``ludcmp`` routine closely
    enough for the diagnostic Python solver: a single matrix is factorized into
    compact LU storage plus a pivot vector, and subsequent right-hand sides are
    solved by ``_xstar_lubksb``.  No SciPy dependency is used here.
    """
    lu = np.array(a, dtype=float, copy=True)
    if lu.ndim != 2 or lu.shape[0] != lu.shape[1]:
        raise np.linalg.LinAlgError("ludcmp requires a square matrix")
    n = int(lu.shape[0])
    indx = np.zeros(n, dtype=int)
    vv = np.zeros(n, dtype=float)
    d = 1.0

    for i in range(n):
        big = float(np.max(np.abs(lu[i, :]))) if n else 0.0
        if big <= 0.0 or not math.isfinite(big):
            raise np.linalg.LinAlgError("singular matrix in ludcmp row scaling")
        vv[i] = 1.0 / big

    for j in range(n):
        for i in range(j):
            s = lu[i, j]
            if i:
                s -= float(np.dot(lu[i, :i], lu[:i, j]))
            lu[i, j] = s

        big = -1.0
        imax = j
        for i in range(j, n):
            s = lu[i, j]
            if j:
                s -= float(np.dot(lu[i, :j], lu[:j, j]))
            lu[i, j] = s
            dum = vv[i] * abs(s)
            if dum >= big:
                big = dum
                imax = i

        if j != imax:
            lu[[j, imax], :] = lu[[imax, j], :]
            d = -d
            vv[imax] = vv[j]

        indx[j] = imax
        if abs(float(lu[j, j])) <= tiny:
            lu[j, j] = tiny

        if j != n - 1:
            dum = 1.0 / float(lu[j, j])
            lu[j + 1 :, j] *= dum

    return lu, indx, d


def _xstar_lubksb(lu: np.ndarray, indx: np.ndarray, b: np.ndarray):
    """Back-substitution companion for ``_xstar_ludcmp``."""
    n = int(lu.shape[0])
    x = np.array(b, dtype=float, copy=True).reshape(n)
    ii = -1
    for i in range(n):
        ip = int(indx[i])
        s = x[ip]
        x[ip] = x[i]
        if ii >= 0:
            s -= float(np.dot(lu[i, ii:i], x[ii:i]))
        elif s != 0.0:
            ii = i
        x[i] = s

    for i in range(n - 1, -1, -1):
        s = x[i]
        if i + 1 < n:
            s -= float(np.dot(lu[i, i + 1 :], x[i + 1 :]))
        x[i] = s / float(lu[i, i])
    return x


def _xstar_mprove(A: np.ndarray, b: np.ndarray, lu: np.ndarray, indx: np.ndarray, x: np.ndarray):
    """One XSTAR/NR-style iterative-improvement correction."""
    residual = np.array(b, dtype=float, copy=False) - np.array(A, dtype=float, copy=False) @ x
    rnorm = float(np.linalg.norm(residual))
    dx = _xstar_lubksb(lu, indx, residual)
    return x + dx, rnorm, float(np.linalg.norm(dx))



def _xstar_continuum_alias_map(global_to_row: Mapping[int, dict]) -> Dict[int, int]:
    """Return XSTAR calc_hmc_element continuum aliases for explicit rows.

    XSTAR advances the element-matrix pointer by ``nlev-1`` for each ion.
    Consequently the continuum row of ion q is not an independent state; it is
    the same matrix row as the ground state of ion q+1.  This helper maps the
    explicit Python continuum/parent-continuum placeholder rows onto the parent
    ion ground global row when that row is present.
    """
    ion_level_to_global: Dict[tuple[int, int], int] = {}
    for gg, rr in global_to_row.items():
        st = maybe_int(rr.get("ion_stage"))
        lev = maybe_int(rr.get("level_index"))
        if st is not None and lev is not None:
            ion_level_to_global[(int(st), int(lev))] = int(gg)
    alias: Dict[int, int] = {}
    for gg, rr in global_to_row.items():
        is_cont = bool(rr.get("is_continuum")) or bool(rr.get("is_parent_continuum_placeholder")) or bool(rr.get("continuum_represents_parent"))
        if not is_cont:
            continue
        parent_stage = maybe_int(rr.get("parent_ion_stage"))
        parent_level = maybe_int(rr.get("parent_level_index")) or 1
        if parent_stage is None:
            continue
        pg = ion_level_to_global.get((int(parent_stage), int(parent_level)))
        if pg is not None and int(pg) != int(gg):
            alias[int(gg)] = int(pg)
    return alias


def _safe_exp_for_levwk(x: float) -> float:
    if x > 700.0:
        return math.exp(700.0)
    if x < -700.0:
        return 0.0
    return math.exp(x)


def _xstar_levwk_seed_weights(
    active: Sequence[int],
    global_to_row: Mapping[int, dict],
    *,
    temperature_K: Optional[float] = None,
    electron_density: Optional[float] = None,
) -> np.ndarray:
    """Approximate the XSTAR levwk/levwkelement LTE seed over active rows.

    This implements the source-code structure from ``levwk.f90`` and the
    chained element partitioning in ``levwkelement.f90`` using decoded type-6
    level energies and statistical weights already present in the Python global
    index.  It is used only to initialize the Lucy iteration; it does not impose
    LTE on the converged solution.
    """
    active = [int(a) for a in active]
    out = np.zeros(len(active), dtype=float)
    if not active:
        return out
    tm = float(temperature_K or 0.0)
    ne = float(electron_density or 0.0)
    if tm <= 0.0 or ne <= 0.0 or not math.isfinite(tm) or not math.isfinite(ne):
        return out
    kT_eV = 8.617333262145e-5 * tm
    if kT_eV <= 0.0:
        return out
    q2 = 2.07e-16 * ne * (tm ** (-1.5))
    by_stage: Dict[int, List[tuple[int, dict]]] = {}
    for idx, g in enumerate(active):
        rr = global_to_row.get(int(g), {})
        st = maybe_int(rr.get("ion_stage"))
        lev = maybe_int(rr.get("level_index"))
        is_cont = bool(rr.get("is_continuum")) or bool(rr.get("is_parent_continuum_placeholder")) or bool(rr.get("continuum_represents_parent"))
        if st is None or lev is None or is_cont:
            continue
        by_stage.setdefault(int(st), []).append((idx, rr))
    # XSTAR steps through ions in database order and chains the last LTE entry
    # of one ion into the first continuum/ground entry of the next.  We preserve
    # the selected stage ordering used by the element solver (highest stage to
    # lowest stage) and use levwk within each ion.
    previous_last = None
    previous_last_rnisi = None
    previous_prev_rnisi = None
    for stage in sorted(by_stage, reverse=True):
        items = sorted(by_stage[stage], key=lambda x: maybe_int(x[1].get("level_index")) or 10**9)
        if not items:
            continue
        # Choose the maximum ionization-potential/continuum energy in the ion
        # as ethion, matching levwk's use of rlev(1,nlev).  If unavailable, use
        # the largest decoded level energy as a fallback.
        eth_candidates=[]
        for _, rr in items:
            ip = maybe_float(rr.get("ionization_potential_eV"))
            en = maybe_float(rr.get("energy_eV"))
            if ip is not None and math.isfinite(float(ip)) and float(ip) > 0:
                eth_candidates.append(float(ip))
            elif en is not None and math.isfinite(float(en)):
                eth_candidates.append(float(en))
        ethion=max(eth_candidates) if eth_candidates else 0.0
        g_cont=maybe_float(items[-1][1].get("statistical_weight_g")) or 1.0
        rs=q2/max(float(g_cont),1.0e-300)
        rnisi=[]
        for _, rr in items:
            en=maybe_float(rr.get("energy_eV")) or 0.0
            g=maybe_float(rr.get("statistical_weight_g")) or 1.0
            dE=max(0.0, float(ethion)-float(en))
            explev2=_safe_exp_for_levwk(-dE/kT_eV)
            val=float(g)*rs/max(explev2,1.0e-300)
            if not math.isfinite(val) or val <= 0.0:
                val=1.0e-300
            rnisi.append(val)
        # levwk sets continuum to 1 before normalizing; for decoded rows that
        # lack an explicit continuum this still gives a finite top-level scale.
        if rnisi:
            rnisi[-1]=max(rnisi[-1],1.0)
        bb=sum(rnisi) if rnisi else 0.0
        if bb>0.0 and math.isfinite(bb):
            rnisi=[v/bb for v in rnisi]
        for k,(idx, rr) in enumerate(items):
            if previous_last is None:
                out[idx]=rnisi[k]
            else:
                if k == 0:
                    # First level of the next ion inherits chained normalization.
                    out[idx]=previous_last
                else:
                    denom=rnisi[k-1] if k-1 < len(rnisi) else 1.0
                    out[idx]=min(1.0e66, out[items[k-1][0]]*rnisi[k]/max(denom,1.0e-300))
        if items:
            previous_last=out[items[-1][0]]
            previous_last_rnisi=rnisi[-1] if rnisi else None
            previous_prev_rnisi=rnisi[-2] if len(rnisi)>1 else None
    if not np.any(out>0.0):
        return out
    s=float(np.sum(out))
    if s>0.0 and math.isfinite(s):
        out/=s
    return out




def _xstar_msolvelucy_pairs_from_matrix(M_active: np.ndarray) -> List[dict]:
    """Reconstruct XSTAR-style ``ajisb`` two-rate pairs from the dense matrix.

    ``calc_hmc_ion.f90`` stores each physical two-level process as forward and
    reverse rates ``ans1`` and ``ans2`` plus two diagonal bookkeeping rows.  The
    Lucy solver does not directly condense the already-expanded dense matrix;
    it uses the two off-diagonal ``ajisb`` entries and the current within-
    superlevel fractions ``rr``.  This helper derives the same pair abstraction
    from the current diagnostic matrix by treating positive off-diagonal matrix
    terms as source->destination rates.

    For local indices ``llo < lup``:
      * ``ans1`` is the upward/low-to-high rate, i.e. M[lup, llo].
      * ``ans2`` is the downward/high-to-low rate, i.e. M[llo, lup].

    The returned rows are then expanded internally exactly as in
    ``calc_hmc_ion.f90`` / ``msolvelucy.f90``.
    """
    pairs: List[dict] = []
    n = int(M_active.shape[0]) if M_active is not None else 0
    for llo in range(n):
        for lup in range(llo + 1, n):
            ans1 = float(M_active[lup, llo]) if M_active[lup, llo] > 0.0 else 0.0
            ans2 = float(M_active[llo, lup]) if M_active[llo, lup] > 0.0 else 0.0
            if ans1 > 0.0 or ans2 > 0.0:
                pairs.append({
                    "llo": int(llo),
                    "lup": int(lup),
                    "ans1_low_to_high_s^-1": float(ans1),
                    "ans2_high_to_low_s^-1": float(ans2),
                })
    return pairs


def _xstar_msolvelucy_apply_pair_condensation(
    pairs: Sequence[Mapping[str, object]],
    rr: np.ndarray,
    local_to_super: Sequence[int],
    nsup: int,
) -> np.ndarray:
    """Construct the condensed superlevel matrix using XSTAR's ``ajisb`` rules."""
    A_sup = np.zeros((int(nsup), int(nsup)), dtype=float)
    for pair in pairs:
        llo = int(pair.get("llo"))
        lup = int(pair.get("lup"))
        ans1 = float(pair.get("ans1_low_to_high_s^-1") or 0.0)
        ans2 = float(pair.get("ans2_high_to_low_s^-1") or 0.0)
        # calc_hmc_ion entry 1: indb=(lup,llo), ajisb=(ans1,ans2)
        # msolvelucy: A(nspm,nspn)+=ajisb1*rr(nn); A(nspm,nspm)-=ajisb2*rr(mm)
        for mm, nn, aj1, aj2 in (
            (lup, llo, ans1, ans2),
            (llo, lup, ans2, ans1),
        ):
            nspm = int(local_to_super[mm])
            nspn = int(local_to_super[nn])
            if nspn != nspm and nspn >= 0 and nspm >= 0:
                if abs(aj1) > 1.0e-48 or abs(aj2) > 1.0e-48:
                    A_sup[nspm, nspn] += float(aj1) * float(rr[nn])
                    A_sup[nspm, nspm] -= float(aj2) * float(rr[mm])
    return A_sup


def _xstar_msolvelucy_fixed_point_update_from_pairs(
    pairs: Sequence[Mapping[str, object]],
    x: np.ndarray,
) -> np.ndarray:
    """One XSTAR msolvelucy inner ``riu/rui/ril/rli`` fixed-point update."""
    n = int(len(x))
    riu = np.zeros(n, dtype=float)
    ril = np.zeros(n, dtype=float)
    rui = np.zeros(n, dtype=float)
    rli = np.zeros(n, dtype=float)
    for pair in pairs:
        llo = int(pair.get("llo"))
        lup = int(pair.get("lup"))
        ans1 = abs(float(pair.get("ans1_low_to_high_s^-1") or 0.0))
        ans2 = abs(float(pair.get("ans2_high_to_low_s^-1") or 0.0))
        # Entry indb=(lup,llo): nn < mm branch in msolvelucy.
        ril[lup] += ans2
        rli[lup] += ans1 * max(0.0, float(x[llo]))
        # Entry indb=(llo,lup): nn > mm branch in msolvelucy.
        riu[llo] += ans1
        rui[llo] += ans2 * max(0.0, float(x[lup]))
    x_new = (rli + rui) / (ril + riu + 1.0e-24)
    sx = float(np.sum(x_new))
    if sx != 0.0 and math.isfinite(sx):
        x_new = x_new / sx
    return x_new



def _xstar_msolvelucy_ajisb_entries_from_pairs(
    pairs: Sequence[Mapping[str, object]],
) -> List[dict]:
    """Expand two-rate pairs into the four ``calc_hmc_ion`` ajisb rows.

    XSTAR ``calc_hmc_ion.f90`` stores each bidirectional rate pair as two
    off-diagonal rows plus two diagonal bookkeeping rows.  The diagonal rows are
    ignored by the ``msolvelucy`` condensed-population and fixed-point loops
    because they have ``nn == mm``, but carrying them explicitly makes the local
    implementation follow the source-code iteration structure and preserves the
    ajisb-entry accounting.
    """
    entries: List[dict] = []
    for pair in pairs:
        llo = int(pair.get("llo"))
        lup = int(pair.get("lup"))
        ans1 = float(pair.get("ans1_low_to_high_s^-1") or 0.0)
        ans2 = float(pair.get("ans2_high_to_low_s^-1") or 0.0)
        if ans1 == 0.0 and ans2 == 0.0:
            continue
        # Off-diagonal gain/loss rows used by msolvelucy.
        entries.append({
            "row_role": "offdiag_lup_llo",
            "mm": int(lup),
            "nn": int(llo),
            "ajisb1": float(ans1),
            "ajisb2": float(ans2),
            "llo": int(llo),
            "lup": int(lup),
        })
        entries.append({
            "row_role": "offdiag_llo_lup",
            "mm": int(llo),
            "nn": int(lup),
            "ajisb1": float(ans2),
            "ajisb2": float(ans1),
            "llo": int(llo),
            "lup": int(lup),
        })
        # Diagonal bookkeeping rows.  These do not enter the nn.gt.mm / nn.lt.mm
        # fixed-point branches, but are part of the four-row ajisb structure.
        entries.append({
            "row_role": "diag_lup_lup",
            "mm": int(lup),
            "nn": int(lup),
            "ajisb1": -abs(float(ans2)),
            "ajisb2": -abs(float(ans2)),
            "llo": int(llo),
            "lup": int(lup),
        })
        entries.append({
            "row_role": "diag_llo_llo",
            "mm": int(llo),
            "nn": int(llo),
            "ajisb1": -abs(float(ans1)),
            "ajisb2": -abs(float(ans1)),
            "llo": int(llo),
            "lup": int(lup),
        })
    return entries


def _xstar_msolvelucy_apply_ajisb_condensation(
    entries: Sequence[Mapping[str, object]],
    rr: np.ndarray,
    local_to_super: Sequence[int],
    nsup: int,
) -> np.ndarray:
    """Construct the condensed matrix by looping over ajisb rows as XSTAR does."""
    A_sup = np.zeros((int(nsup), int(nsup)), dtype=float)
    n_local = int(len(local_to_super))
    for entry in entries:
        mm = int(entry.get("mm"))
        nn = int(entry.get("nn"))
        if mm < 0 or nn < 0 or mm >= n_local or nn >= n_local:
            continue
        nspm = int(local_to_super[mm])
        nspn = int(local_to_super[nn])
        aj1 = float(entry.get("ajisb1") or 0.0)
        aj2 = float(entry.get("ajisb2") or 0.0)
        if (
            nspn != nspm
            and nspn >= 0
            and nspm >= 0
            and (abs(aj1) > 1.0e-48 or abs(aj2) > 1.0e-48)
        ):
            A_sup[nspm, nspn] += aj1 * float(rr[nn])
            A_sup[nspm, nspm] -= aj2 * float(rr[mm])
    return A_sup


def _xstar_msolvelucy_fixed_point_subiteration_exact(
    entries: Sequence[Mapping[str, object]],
    x: np.ndarray,
    *,
    max_inner: int,
    crit2: float,
    eps2: float = 1.0e-6,
) -> tuple[np.ndarray, dict]:
    """Run the exact XSTAR ``riu/rui/ril/rli`` fixed-point sub-iteration.

    This mirrors the inner ``nit2`` loop in ``msolvelucy.f90`` after the
    condensed superlevel solve has set ``x(mm)=rr(mm)*p(nsup(mm))``:

    * zero ``riu``, ``rui``, ``ril``, and ``rli``;
    * loop over ajisb rows with ``nn > mm`` and ``nn < mm`` branches;
    * update ``x(mm)=(rli(mm)+rui(mm))/(ril(mm)+riu(mm)+1d-24)``;
    * renormalize by the total ``xm``;
    * test convergence using the source-code ``diff2`` expression.

    No non-negativity clipping is applied to incoming populations; this is
    intentional because the source routine uses the current ``x(nn)`` directly.
    """
    n = int(len(x))
    x = np.array(x, dtype=float, copy=True)
    diff2 = 10.0
    nit2 = 0
    last_riu = np.zeros(n, dtype=float)
    last_rui = np.zeros(n, dtype=float)
    last_ril = np.zeros(n, dtype=float)
    last_rli = np.zeros(n, dtype=float)
    while nit2 < int(max_inner) and diff2 >= float(crit2):
        nit2 += 1
        xoo = x.copy()
        riu = np.zeros(n, dtype=float)
        rui = np.zeros(n, dtype=float)
        ril = np.zeros(n, dtype=float)
        rli = np.zeros(n, dtype=float)
        for entry in entries:
            mm = int(entry.get("mm"))
            nn = int(entry.get("nn"))
            if mm < 0 or nn < 0 or mm >= n or nn >= n:
                continue
            aj1 = float(entry.get("ajisb1") or 0.0)
            aj2 = float(entry.get("ajisb2") or 0.0)
            if nn > mm:
                riu[mm] += abs(aj2)
                rui[mm] += abs(aj1) * float(x[nn])
            elif nn < mm:
                ril[mm] += abs(aj2)
                rli[mm] += abs(aj1) * float(x[nn])
        x = (rli + rui) / (ril + riu + 1.0e-24)
        xm = float(np.sum(x))
        if xm != 0.0 and math.isfinite(xm):
            x = x / (1.0e-24 + xm)
        diff2 = 0.0
        tst = 0.0
        m2 = 0
        while diff2 < 1.0e3 and m2 < n and tst < 1.0e3:
            tst = 1.0
            if x[m2] > eps2:
                tst = float(xoo[m2]) / float(x[m2])
            diffs = (tst - 1.0) * (tst - 1.0)
            diff2 += diffs
            m2 += 1
        last_riu, last_rui, last_ril, last_rli = riu, rui, ril, rli
    meta = {
        "nit2": int(nit2),
        "diff2": float(diff2),
        "riu": last_riu,
        "rui": last_rui,
        "ril": last_ril,
        "rli": last_rli,
        "riu_sum": float(np.sum(last_riu)),
        "rui_sum": float(np.sum(last_rui)),
        "ril_sum": float(np.sum(last_ril)),
        "rli_sum": float(np.sum(last_rli)),
    }
    return x, meta


def build_calc_ion_rates_istruc_audit_rows(
    *,
    he_like_stage: int,
    stages: Sequence[int],
    adjacent_audit_rows: Sequence[dict],
    type53_phint53_rate_audit_rows: Sequence[dict],
    phint53_milne_integral_audit_rows: Sequence[dict],
    type74_calt74_rate_audit_rows: Sequence[dict],
    include_charge_exchange: bool = False,
) -> List[dict]:
    """Build a pre-matrix XSTAR ``calc_ion_rates``/``istruc`` audit table.

    v0.3.84 tightens this reconstruction to the visible source-code logic in
    ``calc_ion_rates.f90``.  That routine loops over records and calls
    ``ucalc`` with ``lfpi=1``.  It then increments total ionization ``pirti``
    only for rate types 1, 15, and rate-type 7 records whose destination level
    is the ground/state ``idest1=1``.  It increments total recombination
    ``rrrti`` only for rate types 8 and 6, using ``ans1`` total recombination
    rates.  Level-resolved Milne/type-53 inverse terms and calt74 weighted-alpha
    terms are retained as explicit recombination-side candidates, but are marked
    as not included in the source-code ``rrrti`` total unless a later port of the
    exact XSTAR total-rate array shows otherwise.
    """
    he_like_stage = int(he_like_stage)
    parent_stage = he_like_stage + 1
    rows: List[dict] = []

    def _level_is_ground(level: object) -> bool:
        try:
            return int(float(str(level))) == 1
        except Exception:
            return False

    def _pirti_included(rate_type: object, level: object) -> tuple[bool, str]:
        rt = maybe_int(rate_type)
        if rt in {1, 15}:
            return True, "calc_ion_rates.f90 pirti += ans1 for lrtyp=1 or 15"
        if rt == 7 and _level_is_ground(level):
            return True, "calc_ion_rates.f90 pirti += ans1 for lrtyp=7 only when idest1=1"
        if rt == 7:
            return False, "excluded_from_pirti: calc_ion_rates.f90 requires lrtyp=7 with idest1=1; excited-level bound-free rows are level-population rates only"
        return False, "excluded_from_pirti: rate_type not in source-code calc_ion_rates ionization set {1,15,7-ground}"

    def _rrrti_included(rate_type: object) -> tuple[bool, str]:
        rt = maybe_int(rate_type)
        if rt in {6, 8}:
            return True, "calc_ion_rates.f90 rrrti += ans1 for lrtyp=6 or 8 total recombination rows"
        return False, "excluded_from_rrrti: source-code calc_ion_rates recombination total uses lrtyp=6 or 8 ans1, not level-resolved inverse ans2"

    def add_row(source: str, family: str, process: str, from_stage: int, to_stage: int,
                rate: object, record: object = None, data_type: object = None,
                rate_type: object = None, level: object = None, status: str = "evaluated",
                note: str = "", calc_role: str = "candidate") -> None:
        r = maybe_float(rate)
        if r is None or not math.isfinite(float(r)) or float(r) <= 0.0:
            return
        # Source-code inclusion flags.
        pirti_inc, pirti_reason = (False, "not_an_ionization_process")
        rrrti_inc, rrrti_reason = (False, "not_a_recombination_process")
        if str(calc_role) == "pirti_candidate":
            pirti_inc, pirti_reason = _pirti_included(rate_type, level)
        elif str(calc_role) == "rrrti_total_candidate":
            rrrti_inc, rrrti_reason = _rrrti_included(rate_type)
        elif str(calc_role) == "rrrti_level_resolved_candidate":
            rrrti_inc = False
            rrrti_reason = "diagnostic recombination candidate only: level-resolved inverse ans2/alpha is not summed into calc_ion_rates.f90 rrrti"
        elif str(calc_role) == "excluded_inventory":
            pirti_reason = "inventory/diagnostic row not included by calc_ion_rates.f90 total-rate gate"
            rrrti_reason = "inventory/diagnostic row not included by calc_ion_rates.f90 total-rate gate"
        included_total = bool(pirti_inc or rrrti_inc)
        equation_role = "pirti" if pirti_inc else ("rrrti" if rrrti_inc else "not_in_calc_ion_rates_total")
        rows.append({
            "row_kind": "calc_ion_rates_istruc_audit",
            "provenance": "v0.3.85_source_code_gated_calc_ion_rates_istruc_reconstruction",
            "source_table": source,
            "rate_family": family,
            "ion_process": process,
            "record": record,
            "data_type": data_type,
            "rate_type": rate_type,
            "from_ion_stage": int(from_stage),
            "to_ion_stage": int(to_stage),
            "target_ion_stage": he_like_stage,
            "parent_ion_stage": parent_stage,
            "level": level,
            "rate_s^-1": float(r),
            "calc_ion_rates_role_candidate": calc_role,
            "calc_ion_rates_pirti_included": bool(pirti_inc),
            "calc_ion_rates_rrrti_included": bool(rrrti_inc),
            "calc_ion_rates_total_included": bool(included_total),
            "calc_ion_rates_equation_role": equation_role,
            "calc_ion_rates_inclusion_reason": pirti_reason if str(calc_role).startswith("pirti") else rrrti_reason,
            "status": status,
            "note": note,
        })

    # Bound-free photoionization rows.  In calc_ion_rates.f90 only ground-level
    # lrtyp=7 rows contribute to pirti; excited-level rows remain visible in the
    # audit but are not used for the ion-stage closure total.
    for r in type53_phint53_rate_audit_rows:
        st = maybe_int(r.get("target_ion_stage")); par = maybe_int(r.get("parent_ion_stage"))
        if st is None or par is None:
            continue
        lev = r.get("bound_level")
        add_row(
            "xstar_like_element_solver_type53_phint53_rate_audit.csv",
            "photoionization",
            "type53_phint53_bound_free_photoionization",
            int(st), int(par),
            r.get("photoionization_rate_s^-1") if r.get("photoionization_rate_s^-1") not in (None, "") else r.get("phint53_photoionization_rate_s^-1"),
            record=r.get("record"), data_type=r.get("data_type"), rate_type=r.get("rate_type"), level=lev,
            status=str(r.get("phint53_status") or r.get("assembly_status") or "evaluated"),
            note="pre-matrix photoionization candidate; v0.3.85 source-code gate includes only calc_ion_rates lrtyp=7,idest1=1 rows in pirti",
            calc_role="pirti_candidate",
        )

    # Level-resolved Milne inverse rows are useful diagnostics, but calc_ion_rates
    # does not add lrtyp=7 ans2 to rrrti in the visible source branch.  Keep both
    # phint53 rrrt and independent milne.f90 alpha*ne for recombination-side audit.
    for r in phint53_milne_integral_audit_rows:
        if str(r.get("row_kind")) != "phint53_milne_integral_audit":
            continue
        st = maybe_int(r.get("target_ion_stage")); par = maybe_int(r.get("parent_ion_stage"))
        if st is None or par is None:
            continue
        common = dict(record=r.get("record"), data_type=r.get("data_type"), rate_type=r.get("rate_type"), level=r.get("bound_level"),
                      status=str(r.get("phint53_milne_ans2_status") or "evaluated"))
        add_row(
            "xstar_like_element_solver_phint53_milne_integral_audit.csv",
            "radiative_recombination_level_resolved_candidate",
            "type53_phint53_milne_inverse_recombination_rrrt_candidate_not_rrrti",
            int(par), int(st), r.get("source_code_phint53_milne_ans2_rrrt_s^-1"),
            note="source-code phint53.f90 rrrt/ans2 level-resolved candidate; not summed into calc_ion_rates.f90 rrrti gate",
            calc_role="rrrti_level_resolved_candidate", **common,
        )
        add_row(
            "xstar_like_element_solver_phint53_milne_integral_audit.csv",
            "radiative_recombination_level_resolved_candidate",
            "type53_milne_f90_alpha_ne_candidate_not_rrrti",
            int(par), int(st), r.get("source_code_milne_f90_rate_alpha_ne_s^-1"),
            note="independent milne.f90 alpha*ne check; diagnostic candidate, not calc_ion_rates.f90 rrrti",
            calc_role="rrrti_level_resolved_candidate", **common,
        )

    for r in type74_calt74_rate_audit_rows:
        st = maybe_int(r.get("target_ion_stage")); par = maybe_int(r.get("parent_ion_stage"))
        if st is None or par is None:
            continue
        lev = r.get("destination_level")
        add_row(
            "xstar_like_element_solver_type74_calt74_rate_audit.csv",
            "photoionization",
            "type74_calt74_dr_delta_forward_photoionization",
            int(st), int(par),
            r.get("type74_calt74_rate_forward_unscaled_s^-1") if r.get("type74_calt74_rate_forward_unscaled_s^-1") not in (None, "") else r.get("type74_rate_unweighted_s^-1"),
            record=r.get("record"), data_type=r.get("data_type"), rate_type=r.get("rate_type"), level=lev,
            status=str(r.get("type74_calt74_status") or r.get("assembly_status") or "evaluated"),
            note="calt74 forward candidate; calc_ion_rates lrtyp=7 gate would include only idest1=1 rows",
            calc_role="pirti_candidate",
        )
        add_row(
            "xstar_like_element_solver_type74_calt74_rate_audit.csv",
            "dielectronic_recombination_level_resolved_candidate",
            "type74_calt74_weighted_alpha_inverse_candidate_not_rrrti",
            int(par), int(st),
            r.get("type74_calt74_inverse_rate_s^-1") if r.get("type74_calt74_inverse_rate_s^-1") not in (None, "") else r.get("type74_calt74_inverse_rate_unscaled_s^-1"),
            record=r.get("record"), data_type=r.get("data_type"), rate_type=r.get("rate_type"), level=lev,
            status=str(r.get("type74_calt74_status") or r.get("assembly_status") or "evaluated"),
            note="calt74 weighted alpha inverse candidate; not a calc_ion_rates.f90 lrtyp=6/8 total recombination row",
            calc_role="rrrti_level_resolved_candidate",
        )

    for r in adjacent_audit_rows:
        dt = maybe_int(r.get("data_type")); rt = maybe_int(r.get("rate_type")); rec = r.get("record")
        if dt == 1:
            add_row(
                "xstar_like_element_solver_ucalc_adjacent_audit.csv",
                "radiative_recombination_total_rr_ap",
                "type1_total_rr_ap_recombination_rrrti",
                int(maybe_int(r.get("parent_ion_stage")) or parent_stage),
                int(maybe_int(r.get("target_ion_stage")) or he_like_stage),
                r.get("source_rate_total_s^-1"),
                record=rec, data_type=dt, rate_type=rt, level=r.get("destination_level"),
                status=str(r.get("python_eval_status") or r.get("assembly_status") or "evaluated"),
                note="source-code total recombination row: calc_ion_rates.f90 rrrti += ans1 for lrtyp=8/6",
                calc_role="rrrti_total_candidate",
            )
        elif dt == 57:
            lower = int(maybe_int(r.get("type57_matrix_lower_ion_stage")) or he_like_stage)
            upper = int(maybe_int(r.get("type57_matrix_upper_ion_stage")) or parent_stage)
            add_row(
                "xstar_like_element_solver_ucalc_adjacent_audit.csv",
                "collisional_ionization_candidate",
                "type57_collisional_ionization_forward_candidate_not_pirti",
                lower, upper, r.get("python_rate_forward_s^-1"),
                record=rec, data_type=dt, rate_type=rt, level=r.get("type57_matrix_destination_level"),
                status=str(r.get("python_eval_status") or r.get("type57_selected_convention_label") or "evaluated"),
                note="decoded type-57 candidate; visible calc_ion_rates gate does not include lrtyp=5 in pirti",
                calc_role="excluded_inventory",
            )
            add_row(
                "xstar_like_element_solver_ucalc_adjacent_audit.csv",
                "three_body_recombination_candidate",
                "type57_three_body_recombination_inverse_candidate_not_rrrti",
                upper, lower, r.get("python_rate_inverse_s^-1"),
                record=rec, data_type=dt, rate_type=rt, level=r.get("type57_matrix_destination_level"),
                status=str(r.get("python_eval_status") or r.get("type57_selected_convention_label") or "evaluated"),
                note="decoded type-57 inverse candidate; visible calc_ion_rates gate does not include lrtyp=5 in rrrti",
                calc_role="excluded_inventory",
            )
        elif dt == 95:
            lower = int(maybe_int(r.get("target_ion_stage")) or he_like_stage)
            upper = int(maybe_int(r.get("parent_ion_stage")) or parent_stage)
            add_row(
                "xstar_like_element_solver_ucalc_adjacent_audit.csv",
                "collisional_ionization",
                "type95_bryans_collisional_ionization_pirti",
                lower, upper, r.get("python_rate_forward_s^-1"),
                record=rec, data_type=dt, rate_type=rt, level=r.get("idest1_guess"),
                status=str(r.get("python_eval_status") or "evaluated"),
                note="type95/Bryans collisional ionization candidate; included in pirti only for calc_ion_rates lrtyp=15 gate",
                calc_role="pirti_candidate",
            )
        elif include_charge_exchange and dt in {2, 3, 4, 5, 6, 9}:
            # Future source-code charge-exchange branches can be added here when
            # their density partners and target-stage direction are ported.
            pass

    stages_sorted = sorted({he_like_stage, parent_stage})
    low, high = int(stages_sorted[0]), int(stages_sorted[-1])
    ion_total_included = sum(float(r.get("rate_s^-1") or 0.0) for r in rows if bool(r.get("calc_ion_rates_pirti_included")) and int(r.get("from_ion_stage")) == low and int(r.get("to_ion_stage")) == high)
    rec_total_included = sum(float(r.get("rate_s^-1") or 0.0) for r in rows if bool(r.get("calc_ion_rates_rrrti_included")) and int(r.get("from_ion_stage")) == high and int(r.get("to_ion_stage")) == low)
    ion_total_candidates = sum(float(r.get("rate_s^-1") or 0.0) for r in rows if int(r.get("from_ion_stage")) == low and int(r.get("to_ion_stage")) == high)
    rec_total_candidates = sum(float(r.get("rate_s^-1") or 0.0) for r in rows if int(r.get("from_ion_stage")) == high and int(r.get("to_ion_stage")) == low)
    denom = ion_total_included + rec_total_included
    if denom > 0.0 and math.isfinite(denom) and ion_total_included > 0.0 and rec_total_included > 0.0:
        x_low = rec_total_included / denom
        x_high = ion_total_included / denom
        status = "evaluated_source_code_gated_calc_ion_rates_istruc_balance"
    else:
        x_low = x_high = float("nan")
        status = "not_evaluated_missing_source_code_gated_bidirectional_total_rates"
    by_family: Dict[str, float] = {}
    by_family_included: Dict[str, float] = {}
    by_process_included: Dict[str, float] = {}
    for r in rows:
        fam = str(r.get("rate_family") or "")
        val = float(r.get("rate_s^-1") or 0.0)
        by_family[fam] = by_family.get(fam, 0.0) + val
        if bool(r.get("calc_ion_rates_total_included")):
            by_family_included[fam] = by_family_included.get(fam, 0.0) + val
            proc = str(r.get("ion_process") or "")
            by_process_included[proc] = by_process_included.get(proc, 0.0) + val
    rows.append({
        "row_kind": "calc_ion_rates_istruc_summary",
        "provenance": "v0.3.85_source_code_gated_calc_ion_rates_istruc_reconstruction",
        "status": status,
        "low_ion_stage": low,
        "high_ion_stage": high,
        "ionization_total_low_to_high_s^-1": ion_total_included,
        "recombination_total_high_to_low_s^-1": rec_total_included,
        "candidate_ionization_total_low_to_high_s^-1": ion_total_candidates,
        "candidate_recombination_total_high_to_low_s^-1": rec_total_candidates,
        "target_fraction_low_stage": x_low,
        "target_fraction_high_stage": x_high,
        "n_detail_rows": len([r for r in rows if r.get("row_kind") == "calc_ion_rates_istruc_audit"]),
        "n_source_code_included_rows": len([r for r in rows if bool(r.get("calc_ion_rates_total_included"))]),
        "rate_family_sums_json": json.dumps(by_family, sort_keys=True),
        "source_code_included_rate_family_sums_json": json.dumps(by_family_included, sort_keys=True),
        "source_code_included_process_sums_json": json.dumps(by_process_included, sort_keys=True),
        "purpose": "source-code-gated pre-matrix calc_ion_rates/istruc closure; level-resolved inverse candidates audited separately from rrrti totals",
        "main_recombination_diagnosis": "calc_ion_rates.f90 rrrti is populated by lrtyp=6/8 total recombination rows; type53/type74 inverse candidates are not total rrrti rows in the visible source-code branch",
    })
    return rows


def _compute_xstar_calc_ion_rates_istruc_closure(
    calc_ion_rates_istruc_audit_rows: Sequence[dict],
) -> dict:
    """Return ion-fraction targets from source-code-gated pre-matrix totals."""
    detail = [r for r in calc_ion_rates_istruc_audit_rows if str(r.get("row_kind")) == "calc_ion_rates_istruc_audit"]
    stages = sorted({int(r.get("from_ion_stage")) for r in detail if maybe_int(r.get("from_ion_stage")) is not None} |
                    {int(r.get("to_ion_stage")) for r in detail if maybe_int(r.get("to_ion_stage")) is not None})
    flow: Dict[tuple[int, int], float] = {}
    candidate_flow: Dict[tuple[int, int], float] = {}
    by_family: Dict[str, float] = {}
    by_family_included: Dict[str, float] = {}
    for r in detail:
        a = maybe_int(r.get("from_ion_stage")); b = maybe_int(r.get("to_ion_stage")); rate = maybe_float(r.get("rate_s^-1"))
        if a is None or b is None or rate is None or not math.isfinite(float(rate)) or float(rate) <= 0.0:
            continue
        candidate_flow[(int(a), int(b))] = candidate_flow.get((int(a), int(b)), 0.0) + float(rate)
        fam = str(r.get("rate_family") or "")
        by_family[fam] = by_family.get(fam, 0.0) + float(rate)
        if bool(r.get("calc_ion_rates_total_included")):
            flow[(int(a), int(b))] = flow.get((int(a), int(b)), 0.0) + float(rate)
            by_family_included[fam] = by_family_included.get(fam, 0.0) + float(rate)
    targets: Dict[int, float] = {}
    status = "not_applied"
    note = "requires exactly two adjacent stages and finite source-code-gated calc_ion_rates pirti/rrrti totals"
    if len(stages) == 2:
        low, high = int(stages[0]), int(stages[1])
        ion = float(flow.get((low, high), 0.0))
        rec = float(flow.get((high, low), 0.0))
        denom = ion + rec
        if denom > 0.0 and math.isfinite(denom) and ion > 0.0 and rec > 0.0:
            targets[low] = rec / denom
            targets[high] = ion / denom
            status = "applied_source_code_gated_calc_ion_rates_istruc_balance"
            note = "x_low=R/(I+R), x_high=I/(I+R) from source-code-gated pirti/rrrti totals before level-matrix assembly"
    return {
        "status": status,
        "note": note,
        "stages": stages,
        "flow_rates": {f"{a}->{b}": v for (a, b), v in sorted(flow.items())},
        "candidate_flow_rates": {f"{a}->{b}": v for (a, b), v in sorted(candidate_flow.items())},
        "rate_family_sums": by_family,
        "source_code_included_rate_family_sums": by_family_included,
        "targets": targets,
        "target_sum": float(sum(targets.values())) if targets else 0.0,
        "source": "pre_matrix_source_code_gated_calc_ion_rates_istruc_audit",
    }


def _compute_xstar_istruc_ion_fraction_closure(
    M: np.ndarray,
    active: Sequence[int],
    global_to_row: Mapping[int, dict],
) -> dict:
    """Estimate the two-stage XSTAR ``calc_ion_rates``/``istruc`` closure.

    XSTAR computes total ionization/recombination rates before the detailed
    ``calc_hmc_element`` level solve.  This helper extracts the same kind of
    adjacent-stage balance from the already assembled full-global matrix: all
    positive off-diagonal rates that move population from one ion stage to a
    different ion stage are summed as stage-to-stage flow coefficients.  For the
    two-stage C VI/C V diagnostic used here, the equilibrium is

        x_low * I(low->high) = x_high * R(high->low),
        x_low + x_high = 1.

    It is intentionally conservative: if there are not exactly two stages or if
    one side of the balance is missing, the caller can ignore the closure.
    """
    active = [int(a) for a in active]
    stages = sorted({int(maybe_int(global_to_row.get(g, {}).get("ion_stage"))) for g in active if maybe_int(global_to_row.get(g, {}).get("ion_stage")) is not None})
    flow: Dict[tuple[int, int], float] = {}
    for i, gi in enumerate(active):
        sti = maybe_int(global_to_row.get(int(gi), {}).get("ion_stage"))
        if sti is None:
            continue
        for j, gj in enumerate(active):
            if i == j:
                continue
            stj = maybe_int(global_to_row.get(int(gj), {}).get("ion_stage"))
            if stj is None or int(stj) == int(sti):
                continue
            rate = float(M[int(gi), int(gj)]) if int(gi) < M.shape[0] and int(gj) < M.shape[1] else 0.0
            if rate > 0.0 and math.isfinite(rate):
                flow[(int(stj), int(sti))] = flow.get((int(stj), int(sti)), 0.0) + rate
    targets: Dict[int, float] = {}
    status = "not_applied"
    note = "requires exactly two adjacent stages and finite bidirectional flow"
    if len(stages) == 2:
        low, high = int(stages[0]), int(stages[1])
        ion = float(flow.get((low, high), 0.0))
        rec = float(flow.get((high, low), 0.0))
        denom = ion + rec
        if denom > 0.0 and math.isfinite(denom) and ion > 0.0 and rec > 0.0:
            targets[low] = rec / denom
            targets[high] = ion / denom
            status = "applied_two_stage_istruc_balance"
            note = "x_low=R/(I+R), x_high=I/(I+R) from summed inter-stage matrix rates"
    return {
        "status": status,
        "note": note,
        "stages": stages,
        "flow_rates": {f"{a}->{b}": v for (a, b), v in sorted(flow.items())},
        "targets": targets,
        "target_sum": float(sum(targets.values())) if targets else 0.0,
    }


def _apply_ion_fraction_targets_to_active(
    x: np.ndarray,
    active: Sequence[int],
    global_to_row: Mapping[int, dict],
    targets: Mapping[int, float],
) -> np.ndarray:
    """Rescale active level populations so each ion stage matches target sum."""
    if not targets:
        sx = float(np.sum(x))
        if sx > 0.0 and math.isfinite(sx):
            return x / sx
        return x
    x = np.array(x, dtype=float, copy=True)
    active = [int(a) for a in active]
    for st, targ in targets.items():
        idxs = [k for k, g in enumerate(active) if maybe_int(global_to_row.get(int(g), {}).get("ion_stage")) == int(st)]
        if not idxs:
            continue
        current = float(np.sum(x[idxs]))
        if current > 0.0 and math.isfinite(current):
            x[idxs] *= float(targ) / current
        else:
            x[idxs] = float(targ) / max(len(idxs), 1)
    # Stages not covered by the closure are kept but renormalized into any
    # leftover probability mass, if present.
    covered = set(int(k) for k in targets.keys())
    other = [k for k, g in enumerate(active) if (maybe_int(global_to_row.get(int(g), {}).get("ion_stage")) not in covered)]
    leftover = max(0.0, 1.0 - float(sum(float(v) for v in targets.values())))
    if other:
        cur = float(np.sum(x[other]))
        if cur > 0.0 and math.isfinite(cur):
            x[other] *= leftover / cur
        else:
            x[other] = leftover / len(other)
    sx = float(np.sum(x))
    if sx > 0.0 and math.isfinite(sx):
        x /= sx
    return x

def _xstar_lucy_lu_solve(A: np.ndarray, b: np.ndarray, *, max_improve: int = 2):
    """Solve ``A x = b`` using an explicit XSTAR ``leqt2f`` analogue.

    XSTAR's ``leqt2f`` calls Numerical Recipes ``ludcmp``/``lubksb`` and then
    ``mprove`` for iterative improvement.  v0.3.51 uses local pure-Python/NumPy
    versions of those steps instead of delegating the LU step to SciPy or to
    ``numpy.linalg.solve``.
    """
    lu, indx, _ = _xstar_ludcmp(A)
    x = _xstar_lubksb(lu, indx, b)
    improvement_norms: List[float] = []
    for _ in range(int(max(0, max_improve))):
        x, rnorm, dxnorm = _xstar_mprove(A, b, lu, indx, x)
        improvement_norms.append(rnorm)
        if rnorm <= 1.0e-12 * (1.0 + float(np.linalg.norm(b))) or dxnorm <= 1.0e-14 * (1.0 + float(np.linalg.norm(x))):
            break
    return x, improvement_norms


def _xstar_lucy_condensed_solve(
    M: np.ndarray,
    active_indices: Sequence[int],
    global_to_row: Mapping[int, dict],
    *,
    topology_mode: str = "explicit-current",
    population_seed: str = "xstar-levwkelement",
    ion_fraction_closure: str = "none",
    ion_fraction_closure_info: Optional[Mapping[str, object]] = None,
    temperature_K: Optional[float] = None,
    electron_density: Optional[float] = None,
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
    # Build XSTAR/Lucy condensed-state memberships.  The historical diagnostic
    # mode kept every explicit global row as its own condensed state.  v0.3.76
    # adds source-code-motivated topology experiments based on calc_hmc_element:
    # (1) continuum rows can alias to the next-ion ground row, and (2) levels
    # 2..nlev-1 can share one excited-state nsup group per ion.  The returned
    # population vector is still expanded over the original explicit rows using
    # the Lucy rr(level)=x(level)/p(superlevel) iteration, so existing line audits
    # can continue to inspect level-resolved populations.
    topology = str(topology_mode or "explicit-current").strip().lower().replace("_", "-")
    if topology not in {"explicit-current", "xstar-continuum-alias", "xstar-continuum-alias-superlevels"}:
        topology = "explicit-current"
    ion_level_to_global = {}
    for gg, rr in global_to_row.items():
        st = maybe_int(rr.get("ion_stage"))
        lev = maybe_int(rr.get("level_index"))
        if st is not None and lev is not None:
            ion_level_to_global[(int(st), int(lev))] = int(gg)

    def _topology_super_key(g: int, row: Mapping[str, object]):
        stage = maybe_int(row.get("ion_stage"))
        lev = maybe_int(row.get("level_index"))
        kind = str(row.get("level_kind") or "")
        is_cont = bool(row.get("is_continuum")) or bool(row.get("is_parent_continuum_placeholder")) or bool(row.get("continuum_represents_parent"))
        parent_stage = maybe_int(row.get("parent_ion_stage"))
        parent_level = maybe_int(row.get("parent_level_index"))
        if topology in {"xstar-continuum-alias", "xstar-continuum-alias-superlevels"} and is_cont and parent_stage is not None:
            plevel = int(parent_level) if parent_level is not None else 1
            pg = ion_level_to_global.get((int(parent_stage), plevel))
            return ("xstar_parent_ground_alias", int(parent_stage), plevel, pg if pg is not None else "missing")
        if topology == "xstar-continuum-alias-superlevels" and stage is not None and lev is not None:
            if int(lev) == 1:
                return ("xstar_ground_nsup", int(stage))
            if int(lev) > 1 and not is_cont:
                return ("xstar_excited_nsup", int(stage))
        return ("explicit", str(stage if stage is not None else ""), kind, int(g))

    super_keys = []
    super_key_to_local = {}
    local_to_super = []
    for g in active:
        row = global_to_row.get(int(g), {})
        key = _topology_super_key(int(g), row)
        if key not in super_key_to_local:
            super_key_to_local[key] = len(super_keys)
            super_keys.append(key)
        local_to_super.append(super_key_to_local[key])
    nsup = len(super_keys)
    global_to_active_local = {g: k for k, g in enumerate(active)}
    M_active = M[np.ix_(active, active)].astype(float, copy=True)
    # v0.3.85: msolvelucy does not condense the dense matrix directly.
    # calc_hmc_ion builds two-rate ajisb pairs (ans1 low->high, ans2 high->low)
    # plus diagonal bookkeeping rows; msolvelucy constructs the condensed matrix
    # from those pairs and the current rr=x/p superlevel fractions.
    xstar_pairs = _xstar_msolvelucy_pairs_from_matrix(M_active)
    xstar_ajisb_entries = _xstar_msolvelucy_ajisb_entries_from_pairs(xstar_pairs)
    # XSTAR calls levwkelement before msolvelucy to build the LTE/partition
    # seed rnise over the element.  Prefer that source-code seed when enough
    # level metadata are present, otherwise fall back to the older statistical
    # weight initialization.
    seed_mode = str(population_seed or "xstar-levwkelement").strip().lower().replace("_", "-")
    x = np.zeros(len(active), dtype=float)
    if seed_mode in {"xstar-levwkelement", "levwkelement", "xstar"}:
        x = _xstar_levwk_seed_weights(active, global_to_row, temperature_K=temperature_K, electron_density=electron_density)
    rnise_seed = np.array(x, dtype=float, copy=True)
    if float(np.sum(x)) <= 0.0 or not np.all(np.isfinite(x)):
        x = np.zeros(len(active), dtype=float)
        for k, g in enumerate(active):
            wg = maybe_float(global_to_row.get(int(g), {}).get("statistical_weight_g"))
            if wg is None or not math.isfinite(float(wg)) or float(wg) <= 0.0:
                wg = 1.0
            x[k] = float(wg)
        seed_mode = "statistical-weight-fallback"
    if float(np.sum(x)) <= 0.0:
        x[:] = 1.0
        seed_mode = "uniform-fallback"
    x /= float(np.sum(x))
    if float(np.sum(rnise_seed)) <= 0.0 or not np.all(np.isfinite(rnise_seed)):
        rnise_seed = np.array(x, dtype=float, copy=True)
    else:
        rnise_seed = rnise_seed / max(float(np.sum(rnise_seed)), 1.0e-300)
    closure_mode = str(ion_fraction_closure or "none").strip().lower().replace("_", "-")
    closure_info = dict(ion_fraction_closure_info or {})
    # XSTAR calc_hmc_element.f90 uses calc_ion_rates -> istruc to choose the ion
    # limits (mml/mmu) before levwkelement and then calls msolvelucy with only a
    # number-conservation row in the condensed superlevel system.  It does not
    # re-impose the istruc ion fractions as hard constraints during the Lucy
    # iteration.  v0.3.79-v0.3.82 incorrectly used these rates as per-stage hard
    # normalization targets, which drove the C V/C VI test almost entirely into
    # C VI.  Keep the source-code ion-fraction targets in metadata, but do not
    # rescale the Lucy vector by them.
    closure_targets_reported = {int(k): float(v) for k, v in (closure_info.get("targets") or {}).items()} if closure_mode in {"xstar-istruc", "istruc", "xstar-ion-balance", "xstar-calc-ion-rates", "calc-ion-rates"} else {}
    closure_targets: Dict[int, float] = {}
    diff = float("inf")
    diff2 = float("inf")
    niter = 0
    nit3 = 0
    last_lu_improvement_norms: List[float] = []
    lu_failures = 0
    last_condensed_rank = None
    last_condensed_condition = None
    nit2_last = 0
    nit2_total = 0
    last_fixed_point_meta: Dict[str, object] = {}
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
        A_sup = _xstar_msolvelucy_apply_ajisb_condensation(xstar_ajisb_entries, rr, local_to_super, nsup)
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
        # Source-code note: do not hard-apply calc_ion_rates/istruc targets here;
        # msolvelucy enforces total number conservation only.
        # Exact XSTAR fixed-point sub-iteration on the level populations.
        # This is the msolvelucy.f90 nit2 loop using riu/rui/ril/rli from the
        # full ajisb row list, followed by global normalization.
        x, fixed_point_meta = _xstar_msolvelucy_fixed_point_subiteration_exact(
            xstar_ajisb_entries,
            x,
            max_inner=int(max_inner),
            crit2=float(crit2),
            eps2=1.0e-6,
        )
        nit2_last = int(fixed_point_meta.get("nit2") or 0)
        nit2_total += nit2_last
        nit3 += nit2_last
        diff2 = float(fixed_point_meta.get("diff2") or 0.0)
        last_fixed_point_meta = fixed_point_meta
        # Source-code note: do not hard-apply calc_ion_rates/istruc targets here;
        # msolvelucy enforces total number conservation only.
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
    # Final XSTAR msolvelucy bookkeeping: p(superlevel), rr(level)=x/p,
    # rnise from levwkelement, and bileve=xileve/rnise for emissivity output.
    p_final = np.zeros(nsup, dtype=float)
    for k, sp in enumerate(local_to_super):
        p_final[sp] += float(x[k])
    detail_by_global: Dict[str, dict] = {}
    for k, g in enumerate(active):
        sp = int(local_to_super[k])
        rr_final = float(x[k]) / (1.0e-48 + float(p_final[sp])) if p_final[sp] > 1.0e-36 else 1.0
        rn = float(rnise_seed[k]) if k < len(rnise_seed) else 0.0
        b_departure = float(x[k]) / (1.0e-37 + rn) if rn > 0.0 else None
        last_riu = last_fixed_point_meta.get("riu")
        last_rui = last_fixed_point_meta.get("rui")
        last_ril = last_fixed_point_meta.get("ril")
        last_rli = last_fixed_point_meta.get("rli")
        detail_by_global[str(int(g))] = {
            "xstar_ipmat2_index": int(k + 1),
            "xstar_nsup": int(sp + 1),
            "xstar_superlevel_population_p": float(p_final[sp]),
            "xstar_rr_fraction_within_superlevel": float(rr_final),
            "xstar_levwkelement_rnise": float(rn),
            "xstar_bileve_departure_coefficient": b_departure,
            "xstar_xileve_emissivity_population": float(x[k]),
            "xstar_msolvelucy_riu": float(last_riu[k]) if isinstance(last_riu, np.ndarray) and k < len(last_riu) else None,
            "xstar_msolvelucy_rui": float(last_rui[k]) if isinstance(last_rui, np.ndarray) and k < len(last_rui) else None,
            "xstar_msolvelucy_ril": float(last_ril[k]) if isinstance(last_ril, np.ndarray) and k < len(last_ril) else None,
            "xstar_msolvelucy_rli": float(last_rli[k]) if isinstance(last_rli, np.ndarray) and k < len(last_rli) else None,
        }
    pop = np.zeros(n_full, dtype=float)
    for k, g in enumerate(active):
        pop[int(g)] = float(x[k])
    meta = {
        "solver": "xstar_msolvelucy_lu",
        "xstar_population_construction_mode": "calc_hmc_element_levwkelement_msolvelucy_exact_p_rr_b_ipmat_nsup_fixed_point",
        "xstar_msolvelucy_uses_fortran_ajisb_pairs": True,
        "xstar_msolvelucy_fixed_point_mode": "exact_fortran_riu_rui_ril_rli_subiteration",
        "xstar_msolvelucy_fixed_point_population_clipping": False,
        "xstar_msolvelucy_n_two_rate_pairs": int(len(xstar_pairs)),
        "xstar_msolvelucy_n_ajisb_entries_equivalent": int(len(xstar_ajisb_entries)),
        "xstar_msolvelucy_final_p_json": json.dumps([float(v) for v in p_final]),
        "xstar_msolvelucy_last_riu_sum": float(last_fixed_point_meta.get("riu_sum") or 0.0),
        "xstar_msolvelucy_last_rui_sum": float(last_fixed_point_meta.get("rui_sum") or 0.0),
        "xstar_msolvelucy_last_ril_sum": float(last_fixed_point_meta.get("ril_sum") or 0.0),
        "xstar_msolvelucy_last_rli_sum": float(last_fixed_point_meta.get("rli_sum") or 0.0),
        "_xstar_msolvelucy_population_detail_by_global": detail_by_global,
        "solve_status": "warning" if lu_failures else "ok",
        "solver_warning": "" if not lu_failures else f"condensed_lu_failed_{lu_failures}_times_lstsq_used_for_diagnostic_continuation",
        "xstar_lucy_n_superlevels": int(nsup),
        "xstar_lucy_niter": int(niter),
        "xstar_lucy_nit2_last": int(nit2_last),
        "xstar_lucy_nit2_total": int(nit2_total),
        "xstar_lucy_nit3": int(nit3),
        "xstar_lucy_diff": float(diff) if math.isfinite(float(diff)) else None,
        "xstar_lucy_diff2": float(diff2) if math.isfinite(float(diff2)) else None,
        "xstar_lucy_crit": float(crit),
        "xstar_lucy_crit2": float(crit2),
        "xstar_lucy_lu_failures": int(lu_failures),
        "xstar_lucy_last_condensed_rank": last_condensed_rank,
        "xstar_lucy_last_condensed_condition": last_condensed_condition,
        "xstar_lucy_last_lu_improvement_norms_json": json.dumps(last_lu_improvement_norms),
        "xstar_lucy_topology_mode": topology,
        "xstar_lucy_population_seed_mode": seed_mode,
        "xstar_istruc_ion_fraction_closure_mode": closure_mode,
        "xstar_istruc_ion_fraction_closure_status": closure_info.get("status") if closure_info else "not_requested",
        "xstar_istruc_ion_fraction_targets_json": json.dumps({str(k): float(v) for k, v in sorted(closure_targets_reported.items())}, sort_keys=True),
        "xstar_istruc_ion_fraction_flow_rates_json": json.dumps(closure_info.get("flow_rates") or {}, sort_keys=True),
        "xstar_istruc_ion_fraction_source": closure_info.get("source") if closure_info else "",
        "xstar_istruc_ion_fraction_rate_family_sums_json": json.dumps(closure_info.get("rate_family_sums") or {}, sort_keys=True),
        "xstar_istruc_ion_fraction_source_code_included_rate_family_sums_json": json.dumps(closure_info.get("source_code_included_rate_family_sums") or {}, sort_keys=True),
        "xstar_istruc_ion_fraction_candidate_flow_rates_json": json.dumps(closure_info.get("candidate_flow_rates") or {}, sort_keys=True),
        "xstar_istruc_ion_fraction_targets_applied": False,
        "xstar_istruc_ion_fraction_targets_application_status": ("not_applied_source_code_uses_istruc_for_ion_limits_and_levwkelement_seed_not_hard_lucy_constraint" if closure_mode != "none" and closure_targets_reported else ("skipped_no_valid_targets" if closure_mode != "none" else "not_requested")),
        "xstar_lucy_super_keys_json": json.dumps([list(k) for k in super_keys]),
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
    full_global_topology: str = "explicit-current",
    ion_fraction_closure: str = "none",
    calc_ion_rates_istruc_audit_rows: Optional[Sequence[dict]] = None,
    temperature_K: Optional[float] = None,
    electron_density: Optional[float] = None,
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
    topology_requested = str(full_global_topology or "explicit-current").strip().lower().replace("_", "-")
    if topology_requested not in {"explicit-current", "xstar-continuum-alias", "xstar-continuum-alias-superlevels"}:
        topology_requested = "explicit-current"
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
            "provenance": "v0.3.85_full_global_xstar_lucy_nr_lu_solve_comparison",
        }]

    indexed_rows = sorted(indexed_rows, key=lambda r: int(r.get("global_index")))
    max_g = max(int(r.get("global_index")) for r in indexed_rows)
    n = max_g + 1
    global_to_row = {int(r.get("global_index")): r for r in indexed_rows}
    global_to_ion_level = {
        int(r.get("global_index")): (maybe_int(r.get("ion_stage")), maybe_int(r.get("level_index")))
        for r in indexed_rows
    }
    # v0.3.77: apply the calc_hmc_element nlev-1 continuum alias at the
    # matrix-index level for XSTAR topology modes.  Earlier v0.3.76 only
    # grouped the explicit continuum row with the parent ground in the Lucy
    # superlevel membership; XSTAR never creates that separate continuum row.
    continuum_alias_map = _xstar_continuum_alias_map(global_to_row) if topology_requested in {"xstar-continuum-alias", "xstar-continuum-alias-superlevels"} else {}

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
        row = continuum_alias_map.get(int(row), int(row))
        col = continuum_alias_map.get(int(col), int(col))
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

    closure_requested = str(ion_fraction_closure or "none").strip().lower().replace("_", "-")
    if closure_requested not in {"none", "xstar-istruc", "istruc", "xstar-ion-balance", "xstar-calc-ion-rates", "calc-ion-rates"}:
        closure_requested = "none"
    if closure_requested in {"xstar-calc-ion-rates", "calc-ion-rates", "xstar-istruc", "istruc", "xstar-ion-balance"} and calc_ion_rates_istruc_audit_rows:
        ion_closure_info = _compute_xstar_calc_ion_rates_istruc_closure(calc_ion_rates_istruc_audit_rows)
        ion_closure_info["requested_mode"] = closure_requested
    elif closure_requested != "none":
        ion_closure_info = _compute_xstar_istruc_ion_fraction_closure(M, active_indices, global_to_row)
        ion_closure_info["requested_mode"] = closure_requested
        ion_closure_info["source"] = "assembled_full_global_matrix_fallback"
    else:
        ion_closure_info = {"status": "not_requested", "targets": {}, "flow_rates": {}, "source": "none"}

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
                topology_mode=topology_requested,
                population_seed="xstar-levwkelement",
                ion_fraction_closure=closure_requested,
                ion_fraction_closure_info=ion_closure_info,
                temperature_K=temperature_K,
                electron_density=electron_density,
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
        "full_global_topology_requested": topology_requested,
        "xstar_matrix_continuum_alias_count": len(continuum_alias_map),
        "xstar_matrix_continuum_alias_json": json.dumps({str(k): int(v) for k, v in sorted(continuum_alias_map.items())}, sort_keys=True),
        "xstar_lucy_topology_mode": xstar_meta.get("xstar_lucy_topology_mode"),
        "xstar_lucy_population_seed_mode": xstar_meta.get("xstar_lucy_population_seed_mode"),
        "xstar_population_construction_mode": xstar_meta.get("xstar_population_construction_mode"),
        "xstar_msolvelucy_uses_fortran_ajisb_pairs": xstar_meta.get("xstar_msolvelucy_uses_fortran_ajisb_pairs"),
        "xstar_msolvelucy_fixed_point_mode": xstar_meta.get("xstar_msolvelucy_fixed_point_mode"),
        "xstar_msolvelucy_fixed_point_population_clipping": xstar_meta.get("xstar_msolvelucy_fixed_point_population_clipping"),
        "xstar_msolvelucy_n_two_rate_pairs": xstar_meta.get("xstar_msolvelucy_n_two_rate_pairs"),
        "xstar_msolvelucy_n_ajisb_entries_equivalent": xstar_meta.get("xstar_msolvelucy_n_ajisb_entries_equivalent"),
        "xstar_msolvelucy_final_p_json": xstar_meta.get("xstar_msolvelucy_final_p_json"),
        "xstar_msolvelucy_last_riu_sum": xstar_meta.get("xstar_msolvelucy_last_riu_sum"),
        "xstar_msolvelucy_last_rui_sum": xstar_meta.get("xstar_msolvelucy_last_rui_sum"),
        "xstar_msolvelucy_last_ril_sum": xstar_meta.get("xstar_msolvelucy_last_ril_sum"),
        "xstar_msolvelucy_last_rli_sum": xstar_meta.get("xstar_msolvelucy_last_rli_sum"),
        "xstar_istruc_ion_fraction_closure_requested": closure_requested,
        "xstar_istruc_ion_fraction_closure_status": xstar_meta.get("xstar_istruc_ion_fraction_closure_status") or ion_closure_info.get("status"),
        "xstar_istruc_ion_fraction_targets_json": xstar_meta.get("xstar_istruc_ion_fraction_targets_json") or json.dumps({str(k): float(v) for k, v in sorted((ion_closure_info.get("targets") or {}).items())}, sort_keys=True),
        "xstar_istruc_ion_fraction_flow_rates_json": xstar_meta.get("xstar_istruc_ion_fraction_flow_rates_json") or json.dumps(ion_closure_info.get("flow_rates") or {}, sort_keys=True),
        "xstar_istruc_ion_fraction_source": xstar_meta.get("xstar_istruc_ion_fraction_source") or ion_closure_info.get("source"),
        "xstar_istruc_ion_fraction_rate_family_sums_json": xstar_meta.get("xstar_istruc_ion_fraction_rate_family_sums_json") or json.dumps(ion_closure_info.get("rate_family_sums") or {}, sort_keys=True),
        "xstar_istruc_ion_fraction_source_code_included_rate_family_sums_json": xstar_meta.get("xstar_istruc_ion_fraction_source_code_included_rate_family_sums_json") or json.dumps(ion_closure_info.get("source_code_included_rate_family_sums") or {}, sort_keys=True),
        "xstar_istruc_ion_fraction_candidate_flow_rates_json": xstar_meta.get("xstar_istruc_ion_fraction_candidate_flow_rates_json") or json.dumps(ion_closure_info.get("candidate_flow_rates") or {}, sort_keys=True),
        "xstar_istruc_ion_fraction_targets_applied": xstar_meta.get("xstar_istruc_ion_fraction_targets_applied"),
        "xstar_istruc_ion_fraction_targets_application_status": xstar_meta.get("xstar_istruc_ion_fraction_targets_application_status"),
        "xstar_lucy_super_keys_json": xstar_meta.get("xstar_lucy_super_keys_json"),
        "rank_deficient_action": rank_action,
        "negative_population_action": neg_action,
        "xstar_lucy_n_superlevels": xstar_meta.get("xstar_lucy_n_superlevels"),
        "xstar_lucy_niter": xstar_meta.get("xstar_lucy_niter"),
        "xstar_lucy_nit2_last": xstar_meta.get("xstar_lucy_nit2_last"),
        "xstar_lucy_nit2_total": xstar_meta.get("xstar_lucy_nit2_total"),
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
        "normalization_equation": "sum_all_global_populations_equals_1" if closure_requested == "none" else "xstar_istruc_stage_fractions_plus_sum_all_global_populations_equals_1",
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
        "warning": "diagnostic proxy-topology normalized solve; source-vector rows excluded; XSTAR uses msolvelucy with LU on a condensed superlevel matrix; v0.3.85 implements the exact msolvelucy riu/rui/ril/rli fixed-point sub-iteration with p, rr, bmatsup, ipmat2 ordering, nsup memberships, and bileve=xileve/rnise emissivity populations. SVD/lstsq remain available for non-Lucy rank-deficient proxy topology; type53/type99/type1 proxy topology terms are not yet a complete physical XSTAR element model",
        "provenance": "v0.3.85_full_global_xstar_lucy_nr_lu_solve_comparison",
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
    lucy_detail_by_global = xstar_meta.get("_xstar_msolvelucy_population_detail_by_global") or {}
    for g in range(n):
        grow = global_to_row.get(g, {})
        lucy_detail = lucy_detail_by_global.get(str(g), {}) if isinstance(lucy_detail_by_global, dict) else {}
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
            "xstar_ipmat2_index": lucy_detail.get("xstar_ipmat2_index"),
            "xstar_nsup": lucy_detail.get("xstar_nsup"),
            "xstar_superlevel_population_p": lucy_detail.get("xstar_superlevel_population_p"),
            "xstar_rr_fraction_within_superlevel": lucy_detail.get("xstar_rr_fraction_within_superlevel"),
            "xstar_levwkelement_rnise": lucy_detail.get("xstar_levwkelement_rnise"),
            "xstar_bileve_departure_coefficient": lucy_detail.get("xstar_bileve_departure_coefficient"),
            "xstar_xileve_emissivity_population": lucy_detail.get("xstar_xileve_emissivity_population"),
            "xstar_msolvelucy_riu": lucy_detail.get("xstar_msolvelucy_riu"),
            "xstar_msolvelucy_rui": lucy_detail.get("xstar_msolvelucy_rui"),
            "xstar_msolvelucy_ril": lucy_detail.get("xstar_msolvelucy_ril"),
            "xstar_msolvelucy_rli": lucy_detail.get("xstar_msolvelucy_rli"),
            "population_abs": abs(float(pop[g])) if g < len(pop) else 0.0,
            "population_negative": bool(g < len(pop) and pop[g] < -1.0e-12),
            "provenance": "v0.3.85_full_global_xstar_lucy_nr_lu_solve_comparison",
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
    type53_phint53_scale: object = 1.0,
    inverse_recombination_mode: str = "none",
    type53_milne_scale: object = 1.0,
    type74_inverse_scale: object = 1.0,
    type53_milne_refined_scale: object = "1e9,3e9,1e10,3e10,1e11",
    type74_inverse_refined_scale: object = "1e8,3e8,1e9,3e9,1e10,3e10,1e11,3e11,1e12",
    triplet_coupling_treatment: str = "normal",
    type50_bound_bound_treatment: str = "raw-A",
    type50_escape_factor: object = 1.0,
    type50_photoexcitation_scale: object = 0.0,
    type50_escape_factor_scan: object = "0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.75,1",
    radiation_field_mode: str = "none",
    radiation_bremsa_scale: object = 1.0,
    radiation_energy_min_eV: Optional[float] = None,
    radiation_energy_max_eV: Optional[float] = None,
    radiation_n_energy_grid: int = 256,
    radiation_powerlaw_index: float = 1.0,
    full_global_linear_solver: str = "xstar-lucy",
    full_global_rank_deficient_action: str = "svd",
    full_global_negative_population_action: str = "keep",
    full_global_prune_null_rate_levels: bool = True,
    full_global_topology: str = "explicit-current",
    ion_fraction_closure: str = "none",
    xstar_line_column_density: object = 0.0,
    xstar_line_vturb_km_s: object = 0.0,
    xstar_line_cfrac: object = 0.0,
    xstar_line_tau1_fraction: object = 1.0,
    xstar_line_tau2_fraction: object = 1.0,
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
        type53_milne_inverse_audit_rows: List[dict] = []
        global_type53_milne_matrix_terms: List[dict] = []
        type74_inverse_recombination_audit_rows: List[dict] = []
        global_type74_inverse_matrix_terms: List[dict] = []
        type74_calt74_rate_audit_rows: List[dict] = []
        global_type74_calt74_matrix_terms: List[dict] = []
        calc_ion_rates_istruc_audit_rows: List[dict] = []
        inverse_recombination_scale_scan_rows: List[dict] = []
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
    type50_bound_bound_treatment_norm = _normalise_type50_bound_bound_treatment(type50_bound_bound_treatment)
    global_bound_bound_matrix_terms = build_global_bound_bound_matrix_terms(
        transitions,
        global_index_rows,
        type50_bound_bound_treatment=type50_bound_bound_treatment_norm,
        type50_escape_factor=type50_escape_factor,
        type50_photoexcitation_scale=type50_photoexcitation_scale,
    )
    type50_ucalc_rate_audit_rows = build_type50_ucalc_rate_audit_rows(
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        he_like_stage=he_like_stage,
    )
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
        radiation_bremsa_scale=radiation_bremsa_scale,
        radiation_energy_min_eV=radiation_energy_min_eV,
        radiation_energy_max_eV=radiation_energy_max_eV,
        radiation_n_energy_grid=radiation_n_energy_grid,
        radiation_powerlaw_index=radiation_powerlaw_index,
    )
    bremsa_context_rows = build_bremsa_context_rows(radiation_context_rows)
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
    type53_phint53_rate_audit_rows = build_type53_phint53_rate_audit_rows(
        type53_rate_audit_rows=type53_rate_audit_rows,
        radiation_context_rows=radiation_context_rows,
        global_index_rows=global_index_rows,
        temperature=temperature,
        type53_phint53_scale=type53_phint53_scale,
    )
    global_type53_phint53_matrix_terms = build_global_type53_phint53_matrix_terms(
        type53_phint53_rate_audit_rows
    )
    type53_milne_inverse_audit_rows = build_type53_milne_inverse_audit_rows(
        type53_phint53_rate_audit_rows=type53_phint53_rate_audit_rows,
        global_index_rows=global_index_rows,
        inverse_recombination_mode=inverse_recombination_mode,
        type53_milne_scale=type53_milne_scale,
    )
    global_type53_milne_matrix_terms = build_global_type53_milne_matrix_terms(
        type53_milne_inverse_audit_rows
    )
    type74_inverse_recombination_audit_rows = build_type74_inverse_recombination_audit_rows(
        type74_triplet_source_audit_rows=type74_triplet_source_audit_rows,
        global_index_rows=global_index_rows,
        inverse_recombination_mode=inverse_recombination_mode,
        type74_inverse_scale=type74_inverse_scale,
    )
    global_type74_inverse_matrix_terms = build_global_type74_inverse_matrix_terms(
        type74_inverse_recombination_audit_rows
    )
    type74_calt74_rate_audit_rows = build_type74_calt74_rate_audit_rows(
        type74_linkage_rows=type74_linkage_audit_rows,
        radiation_context_rows=radiation_context_rows,
        global_index_rows=global_index_rows,
        inverse_recombination_mode=inverse_recombination_mode,
        temperature=temperature,
        type74_inverse_scale=type74_inverse_scale,
    )
    global_type74_calt74_matrix_terms = build_global_type74_calt74_matrix_terms(
        type74_calt74_rate_audit_rows
    )
    type53_type74_ucalc_closure_audit_rows = build_type53_type74_ucalc_closure_audit_rows(
        type53_phint53_rate_audit_rows=type53_phint53_rate_audit_rows,
        type53_rate_audit_rows=type53_rate_audit_rows,
        type53_milne_inverse_audit_rows=type53_milne_inverse_audit_rows,
        type74_calt74_rate_audit_rows=type74_calt74_rate_audit_rows,
        type74_inverse_recombination_audit_rows=type74_inverse_recombination_audit_rows,
        global_index_rows=global_index_rows,
        he_like_stage=he_like_stage,
        temperature=temperature,
        electron_density=electron_density,
    )
    phint53_milne_integral_audit_rows = build_phint53_milne_integral_audit_rows(
        type53_phint53_rate_audit_rows=type53_phint53_rate_audit_rows,
        type53_rate_audit_rows=type53_rate_audit_rows,
        type53_milne_inverse_audit_rows=type53_milne_inverse_audit_rows,
        global_index_rows=global_index_rows,
        he_like_stage=he_like_stage,
        temperature=temperature,
        electron_density=electron_density,
    )
    calc_ion_rates_istruc_audit_rows = build_calc_ion_rates_istruc_audit_rows(
        he_like_stage=he_like_stage,
        stages=stages,
        adjacent_audit_rows=assembled_coupling_terms,
        type53_phint53_rate_audit_rows=type53_phint53_rate_audit_rows,
        phint53_milne_integral_audit_rows=phint53_milne_integral_audit_rows,
        type74_calt74_rate_audit_rows=type74_calt74_rate_audit_rows,
        include_charge_exchange=include_charge_exchange,
    )
    global_type53_xstar_ucalc_matrix_terms = build_global_type53_xstar_ucalc_matrix_terms(
        phint53_milne_integral_audit_rows,
        inverse_recombination_mode=inverse_recombination_mode,
    )
    if _mode_includes_xstar_ucalc_inverse(inverse_recombination_mode):
        global_type53_milne_matrix_terms = global_type53_xstar_ucalc_matrix_terms
    radiation_normalization_audit_rows = build_radiation_normalization_audit_rows(
        radiation_context_rows=radiation_context_rows,
        type53_phint53_rate_audit_rows=type53_phint53_rate_audit_rows,
        type53_phint53_scale=type53_phint53_scale,
    )
    type53_phint53_scale_scan_rows = build_type53_phint53_scale_scan_rows(
        type53_rate_audit_rows=type53_rate_audit_rows,
        radiation_context_rows=radiation_context_rows,
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
        coupling_rows=assembled_coupling_terms,
        line_rows=line_rows,
        he_like_stage=he_like_stage,
        temperature=temperature,
        type53_phint53_scale=type53_phint53_scale,
        full_global_linear_solver=full_global_linear_solver,
        full_global_rank_deficient_action=full_global_rank_deficient_action,
        full_global_negative_population_action=full_global_negative_population_action,
        full_global_prune_null_rate_levels=full_global_prune_null_rate_levels,
        full_global_topology=full_global_topology,
    )
    full_global_matrix_terms_unsuppressed = build_full_global_matrix_terms(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
        global_type53_phint53_matrix_terms=global_type53_phint53_matrix_terms,
        global_type53_milne_matrix_terms=global_type53_milne_matrix_terms,
        global_type74_inverse_matrix_terms=global_type74_inverse_matrix_terms,
        global_type74_calt74_matrix_terms=global_type74_calt74_matrix_terms,
        coupling_rows=assembled_coupling_terms,
        he_like_stage=he_like_stage,
    )
    triplet_coupling_treatment_norm = _normalise_triplet_coupling_treatment(triplet_coupling_treatment)
    suppressed_full_global_matrix_terms, suppressed_triplet_coupling_terms = suppress_triplet_3p_to_3s_radiative_terms(
        full_global_matrix_terms_unsuppressed,
        he_like_stage=he_like_stage,
    )
    if triplet_coupling_treatment_norm == "suppress-3p-to-3s-radiative":
        full_global_matrix_terms = suppressed_full_global_matrix_terms
    else:
        full_global_matrix_terms = full_global_matrix_terms_unsuppressed
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
        full_global_topology=full_global_topology,
        ion_fraction_closure=ion_fraction_closure,
        calc_ion_rates_istruc_audit_rows=calc_ion_rates_istruc_audit_rows,
        temperature_K=temperature,
        electron_density=electron_density,
    )
    type50_escape_factor_scan_rows = build_type50_escape_factor_scan_rows(
        transition_rows=transitions,
        global_index_rows=global_index_rows,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
        global_type53_phint53_matrix_terms=global_type53_phint53_matrix_terms,
        global_type53_milne_matrix_terms=global_type53_milne_matrix_terms,
        global_type74_inverse_matrix_terms=global_type74_inverse_matrix_terms,
        global_type74_calt74_matrix_terms=global_type74_calt74_matrix_terms,
        coupling_rows=assembled_coupling_terms,
        line_rows=line_rows,
        he_like_stage=he_like_stage,
        type50_escape_factor_scan=type50_escape_factor_scan,
        type50_photoexcitation_scale=type50_photoexcitation_scale,
        triplet_coupling_treatment=triplet_coupling_treatment_norm,
        linear_solver=full_global_linear_solver,
        rank_deficient_action=full_global_rank_deficient_action,
        negative_population_action=full_global_negative_population_action,
        prune_null_rate_levels=full_global_prune_null_rate_levels,
    )
    triplet_coupling_suppression_comparison_rows = build_triplet_coupling_suppression_comparison_rows(
        global_index_rows=global_index_rows,
        full_global_matrix_terms=full_global_matrix_terms_unsuppressed,
        line_rows=line_rows,
        he_like_stage=he_like_stage,
        linear_solver=full_global_linear_solver,
        rank_deficient_action=full_global_rank_deficient_action,
        negative_population_action=full_global_negative_population_action,
        prune_null_rate_levels=full_global_prune_null_rate_levels,
    )
    inverse_recombination_scale_scan_rows = build_inverse_recombination_scale_scan_rows(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
        global_type53_phint53_matrix_terms=global_type53_phint53_matrix_terms,
        type53_phint53_rate_audit_rows=type53_phint53_rate_audit_rows,
        type74_triplet_source_audit_rows=type74_triplet_source_audit_rows,
        coupling_rows=assembled_coupling_terms,
        line_rows=line_rows,
        he_like_stage=he_like_stage,
        inverse_recombination_mode=inverse_recombination_mode,
        type53_milne_scale=type53_milne_scale,
        type74_inverse_scale=type74_inverse_scale,
        linear_solver=full_global_linear_solver,
        rank_deficient_action=full_global_rank_deficient_action,
        negative_population_action=full_global_negative_population_action,
        prune_null_rate_levels=full_global_prune_null_rate_levels,
    )
    inverse_recombination_refined_scale_scan_rows = build_inverse_recombination_refined_scale_scan_rows(
        global_index_rows=global_index_rows,
        global_bound_bound_matrix_terms=global_bound_bound_matrix_terms,
        global_superlevel_cascade_matrix_terms=global_superlevel_cascade_matrix_terms,
        global_superlevel_source_matrix_terms=global_superlevel_source_matrix_terms,
        global_type53_flat_proxy_matrix_terms=global_type53_flat_proxy_matrix_terms,
        global_type53_phint53_matrix_terms=global_type53_phint53_matrix_terms,
        type53_phint53_rate_audit_rows=type53_phint53_rate_audit_rows,
        type74_triplet_source_audit_rows=type74_triplet_source_audit_rows,
        coupling_rows=assembled_coupling_terms,
        line_rows=line_rows,
        he_like_stage=he_like_stage,
        inverse_recombination_mode=inverse_recombination_mode,
        type53_milne_refined_scale=type53_milne_refined_scale,
        type74_inverse_refined_scale=type74_inverse_refined_scale,
        linear_solver=full_global_linear_solver,
        rank_deficient_action=full_global_rank_deficient_action,
        negative_population_action=full_global_negative_population_action,
        prune_null_rate_levels=full_global_prune_null_rate_levels,
    )
    intercombination_feed_audit_rows = build_intercombination_feed_audit_rows(
        global_index_rows=global_index_rows,
        full_global_matrix_terms=full_global_matrix_terms,
        full_global_normalized_solve_comparison_rows=full_global_normalized_solve_comparison_rows,
        he_like_stage=he_like_stage,
    )
    triplet_component_balance_audit_rows = build_triplet_component_balance_audit_rows(
        global_index_rows=global_index_rows,
        full_global_matrix_terms=full_global_matrix_terms,
        full_global_normalized_solve_comparison_rows=full_global_normalized_solve_comparison_rows,
        he_like_stage=he_like_stage,
    )
    triplet_alpha_gamma_audit_rows = build_triplet_alpha_gamma_audit_rows(
        global_index_rows=global_index_rows,
        full_global_matrix_terms=full_global_matrix_terms,
        full_global_normalized_solve_comparison_rows=full_global_normalized_solve_comparison_rows,
        he_like_stage=he_like_stage,
    )
    triplet_emissivity_branch_audit_rows = build_triplet_emissivity_branch_audit_rows(
        global_index_rows=global_index_rows,
        line_rows=line_rows,
        full_global_matrix_terms=full_global_matrix_terms,
        full_global_normalized_solve_comparison_rows=full_global_normalized_solve_comparison_rows,
        he_like_stage=he_like_stage,
    )
    calc_emis_triplet_audit_rows = build_calc_emis_triplet_audit_rows(
        global_index_rows=global_index_rows,
        line_rows=line_rows,
        full_global_normalized_solve_comparison_rows=full_global_normalized_solve_comparison_rows,
        he_like_stage=he_like_stage,
    )
    calc_emis_context_audit_rows = build_calc_emis_context_audit_rows(
        global_index_rows=global_index_rows,
        line_rows=line_rows,
        full_global_matrix_terms=full_global_matrix_terms,
        full_global_normalized_solve_comparison_rows=full_global_normalized_solve_comparison_rows,
        he_like_stage=he_like_stage,
    )
    calc_emis_ion_triplet_emergent_rows = build_calc_emis_ion_triplet_emergent_rows(
        global_index_rows=global_index_rows,
        line_rows=line_rows,
        full_global_normalized_solve_comparison_rows=full_global_normalized_solve_comparison_rows,
        type50_ucalc_rate_audit_rows=type50_ucalc_rate_audit_rows,
        he_like_stage=he_like_stage,
        temperature_K=temperature,
        xstar_line_column_density=xstar_line_column_density,
        xstar_line_vturb_km_s=xstar_line_vturb_km_s,
        xstar_line_cfrac=xstar_line_cfrac,
        xstar_line_tau1_fraction=xstar_line_tau1_fraction,
        xstar_line_tau2_fraction=xstar_line_tau2_fraction,
    )
    # Add compact calc_emis_ion emergent triplet summaries to the primary full-global
    # comparison CSV so users can compare raw pop*A*E and emergent fline fractions
    # in one place.
    for _ce in calc_emis_ion_triplet_emergent_rows:
        if _ce.get("row_kind") == "calc_emis_ion_triplet_emergent_summary":
            full_global_normalized_solve_comparison_rows.append({
                "row_kind": "summary",
                "comparison_case": "full_global_" + str(_ce.get("comparison_case")),
                "f_fraction": _ce.get("f_fraction"),
                "i_fraction": _ce.get("i_fraction"),
                "r_fraction": _ce.get("r_fraction"),
                "R": _ce.get("R"),
                "G": _ce.get("G"),
                "l2_distance_to_target": _ce.get("l2_distance_to_target"),
                "solve_status": "postprocess_calc_emis_ion_line_construction",
                "solver": full_global_linear_solver,
                "full_global_topology_requested": full_global_topology,
                "xstar_calc_emis_ion_source_code_formula": _ce.get("source_code_formula"),
                "provenance": "v0.3.87_exact_calc_emis_ion_triplet_emergent_line_construction",
            })
    triplet_coupling_record_audit_rows = build_triplet_coupling_record_audit_rows(
        global_index_rows=global_index_rows,
        full_global_matrix_terms=full_global_matrix_terms_unsuppressed,
        full_global_normalized_solve_comparison_rows=full_global_normalized_solve_comparison_rows,
        he_like_stage=he_like_stage,
    )
    xstar_matrix_topology_audit_rows = build_xstar_matrix_topology_audit_rows(
        global_index_rows=global_index_rows,
        stages=stages,
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
            "n_xstar_matrix_topology_audit_rows": len(xstar_matrix_topology_audit_rows),
            "xstar_matrix_topology_audit_summary": _xstar_matrix_topology_audit_summary(xstar_matrix_topology_audit_rows),
            "n_global_bound_bound_matrix_term_rows": len(global_bound_bound_matrix_terms),
            "global_bound_bound_matrix_terms_summary": _global_bound_bound_matrix_terms_summary(global_bound_bound_matrix_terms),
            "type50_bound_bound_treatment": type50_bound_bound_treatment_norm,
            "type50_escape_factor": type50_escape_factor,
            "type50_photoexcitation_scale": type50_photoexcitation_scale,
            "n_type50_ucalc_rate_audit_rows": len(type50_ucalc_rate_audit_rows),
            "type50_ucalc_rate_audit_summary": _type50_ucalc_rate_audit_summary(type50_ucalc_rate_audit_rows),
            "type50_escape_factor_scan": type50_escape_factor_scan,
            "n_type50_escape_factor_scan_rows": len(type50_escape_factor_scan_rows),
            "type50_escape_factor_scan_summary": _type50_escape_factor_scan_summary(type50_escape_factor_scan_rows),
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
            "radiation_context_summary": radiation_context_rows[0] if radiation_context_rows else {},
            "n_bremsa_context_rows": len(bremsa_context_rows),
            "bremsa_context_summary": _bremsa_context_summary(bremsa_context_rows),
            "n_type53_rate_audit_rows": len(type53_rate_audit_rows),
            "type53_rate_audit_summary": _type53_rate_audit_summary(type53_rate_audit_rows),
            "n_type53_flat_proxy_rate_audit_rows": len(type53_flat_proxy_rate_audit_rows),
            "type53_flat_proxy_rate_audit_summary": _type53_flat_proxy_rate_audit_summary(type53_flat_proxy_rate_audit_rows),
            "n_global_type53_flat_proxy_matrix_term_rows": len(global_type53_flat_proxy_matrix_terms),
            "global_type53_flat_proxy_matrix_terms_summary": _global_type53_flat_proxy_matrix_terms_summary(global_type53_flat_proxy_matrix_terms),
            "n_type53_phint53_rate_audit_rows": len(type53_phint53_rate_audit_rows),
            "type53_phint53_rate_audit_summary": _type53_phint53_rate_audit_summary(type53_phint53_rate_audit_rows),
            "n_global_type53_phint53_matrix_term_rows": len(global_type53_phint53_matrix_terms),
            "global_type53_phint53_matrix_terms_summary": _global_type53_phint53_matrix_terms_summary(global_type53_phint53_matrix_terms),
            "inverse_recombination_mode": _normalise_inverse_recombination_mode(inverse_recombination_mode),
            "type53_milne_scale": (_parse_triplet_source_scales(type53_milne_scale)[0] if _parse_triplet_source_scales(type53_milne_scale) else 1.0),
            "type74_inverse_scale": (_parse_triplet_source_scales(type74_inverse_scale)[0] if _parse_triplet_source_scales(type74_inverse_scale) else 1.0),
            "n_type53_milne_inverse_audit_rows": len(type53_milne_inverse_audit_rows),
            "type53_milne_inverse_audit_summary": _type53_milne_inverse_audit_summary(type53_milne_inverse_audit_rows),
            "n_global_type53_milne_matrix_term_rows": len(global_type53_milne_matrix_terms),
            "global_type53_milne_matrix_terms_summary": _global_type53_milne_matrix_terms_summary(global_type53_milne_matrix_terms),
            "n_type74_inverse_recombination_audit_rows": len(type74_inverse_recombination_audit_rows),
            "type74_inverse_recombination_audit_summary": _type74_inverse_recombination_audit_summary(type74_inverse_recombination_audit_rows),
            "n_global_type74_inverse_matrix_term_rows": len(global_type74_inverse_matrix_terms),
            "global_type74_inverse_matrix_terms_summary": _global_type74_inverse_matrix_terms_summary(global_type74_inverse_matrix_terms),
            "n_type74_calt74_rate_audit_rows": len(type74_calt74_rate_audit_rows),
            "type74_calt74_rate_audit_summary": _type74_calt74_rate_audit_summary(type74_calt74_rate_audit_rows),
            "n_global_type74_calt74_matrix_term_rows": len(global_type74_calt74_matrix_terms),
            "global_type74_calt74_matrix_terms_summary": _global_type74_calt74_matrix_terms_summary(global_type74_calt74_matrix_terms),
            "n_calc_ion_rates_istruc_audit_rows": len(calc_ion_rates_istruc_audit_rows),
            "calc_ion_rates_istruc_audit_summary": _calc_ion_rates_istruc_audit_summary(calc_ion_rates_istruc_audit_rows),
            "n_type53_type74_ucalc_closure_audit_rows": len(type53_type74_ucalc_closure_audit_rows),
            "type53_type74_ucalc_closure_audit_summary": _type53_type74_ucalc_closure_audit_summary(type53_type74_ucalc_closure_audit_rows),
            "n_phint53_milne_integral_audit_rows": len(phint53_milne_integral_audit_rows),
            "phint53_milne_integral_audit_summary": _phint53_milne_integral_audit_summary(phint53_milne_integral_audit_rows),
            "n_inverse_recombination_scale_scan_rows": len(inverse_recombination_scale_scan_rows),
            "inverse_recombination_scale_scan_summary": _inverse_recombination_scale_scan_summary(inverse_recombination_scale_scan_rows),
            "n_inverse_recombination_refined_scale_scan_rows": len(inverse_recombination_refined_scale_scan_rows),
            "inverse_recombination_refined_scale_scan_summary": _inverse_recombination_refined_scale_scan_summary(inverse_recombination_refined_scale_scan_rows),
            "n_intercombination_feed_audit_rows": len(intercombination_feed_audit_rows),
            "intercombination_feed_audit_summary": _intercombination_feed_audit_summary(intercombination_feed_audit_rows),
            "n_triplet_component_balance_audit_rows": len(triplet_component_balance_audit_rows),
            "triplet_component_balance_audit_summary": _triplet_component_balance_audit_summary(triplet_component_balance_audit_rows),
            "n_triplet_alpha_gamma_audit_rows": len(triplet_alpha_gamma_audit_rows),
            "triplet_alpha_gamma_audit_summary": _triplet_alpha_gamma_audit_summary(triplet_alpha_gamma_audit_rows),
            "n_triplet_emissivity_branch_audit_rows": len(triplet_emissivity_branch_audit_rows),
            "triplet_emissivity_branch_audit_summary": _triplet_emissivity_branch_audit_summary(triplet_emissivity_branch_audit_rows),
            "n_calc_emis_triplet_audit_rows": len(calc_emis_triplet_audit_rows),
            "calc_emis_triplet_audit_summary": _calc_emis_triplet_audit_summary(calc_emis_triplet_audit_rows),
            "n_calc_emis_context_audit_rows": len(calc_emis_context_audit_rows),
            "calc_emis_context_audit_summary": _calc_emis_context_audit_summary(calc_emis_context_audit_rows),
            "n_calc_emis_ion_triplet_emergent_rows": len(calc_emis_ion_triplet_emergent_rows),
            "calc_emis_ion_triplet_emergent_summary": _calc_emis_ion_triplet_emergent_summary(calc_emis_ion_triplet_emergent_rows),
            "triplet_coupling_treatment": triplet_coupling_treatment_norm,
            "n_triplet_coupling_suppressed_matrix_terms": len(suppressed_triplet_coupling_terms),
            "n_triplet_coupling_suppression_comparison_rows": len(triplet_coupling_suppression_comparison_rows),
            "triplet_coupling_suppression_comparison_summary": _triplet_coupling_suppression_comparison_summary(triplet_coupling_suppression_comparison_rows),
            "n_triplet_coupling_record_audit_rows": len(triplet_coupling_record_audit_rows),
            "triplet_coupling_record_audit_summary": _triplet_coupling_record_audit_summary(triplet_coupling_record_audit_rows),
            "n_radiation_normalization_audit_rows": len(radiation_normalization_audit_rows),
            "radiation_normalization_audit_summary": _radiation_normalization_audit_summary(radiation_normalization_audit_rows),
            "n_type53_phint53_scale_scan_rows": len(type53_phint53_scale_scan_rows),
            "type53_phint53_scale_scan_summary": _type53_phint53_scale_scan_summary(type53_phint53_scale_scan_rows),
            "type53_matrix_source_preference": "phint53_kernel_when_available_else_flat_proxy",
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
        "xstar_matrix_topology_audit": xstar_matrix_topology_audit_rows,
        "coupling_candidates": coupling,
        "populations": populations,
        "line_rows": line_rows,
        "transition_rows": transitions,
        "global_bound_bound_matrix_terms": global_bound_bound_matrix_terms,
        "type50_ucalc_rate_audit": type50_ucalc_rate_audit_rows,
        "type50_escape_factor_scan": type50_escape_factor_scan_rows,
        "global_superlevel_cascade_matrix_terms": global_superlevel_cascade_matrix_terms,
        "global_superlevel_source_matrix_terms": global_superlevel_source_matrix_terms,
        "global_bound_bound_solve_comparison": global_bound_bound_solve_comparison_rows,
        "global_bound_bound_type71_solve_comparison": global_bound_bound_type71_solve_comparison_rows,
        "global_bound_bound_type71_type99_proxy_solve_comparison": global_bound_bound_type71_type99_proxy_solve_comparison_rows,
        "global_bound_bound_type71_type99_type53_proxy_solve_comparison": global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows,
        "type99_proxy_scale_scan": type99_proxy_scale_scan_rows,
        "radiation_context": radiation_context_rows,
        "bremsa_context": bremsa_context_rows,
        "type53_rate_audit": type53_rate_audit_rows,
        "type53_flat_proxy_rate_audit": type53_flat_proxy_rate_audit_rows,
        "global_type53_flat_proxy_matrix_terms": global_type53_flat_proxy_matrix_terms,
        "type53_phint53_rate_audit": type53_phint53_rate_audit_rows,
        "global_type53_phint53_matrix_terms": global_type53_phint53_matrix_terms,
        "type53_milne_inverse_audit": type53_milne_inverse_audit_rows,
        "global_type53_milne_matrix_terms": global_type53_milne_matrix_terms,
        "type74_inverse_recombination_audit": type74_inverse_recombination_audit_rows,
        "global_type74_inverse_matrix_terms": global_type74_inverse_matrix_terms,
        "type74_calt74_rate_audit": type74_calt74_rate_audit_rows,
        "global_type74_calt74_matrix_terms": global_type74_calt74_matrix_terms,
        "calc_ion_rates_istruc_audit": calc_ion_rates_istruc_audit_rows,
        "type53_type74_ucalc_closure_audit": type53_type74_ucalc_closure_audit_rows,
        "phint53_milne_integral_audit": phint53_milne_integral_audit_rows,
        "inverse_recombination_scale_scan": inverse_recombination_scale_scan_rows,
        "inverse_recombination_refined_scale_scan": inverse_recombination_refined_scale_scan_rows,
        "intercombination_feed_audit": intercombination_feed_audit_rows,
        "triplet_component_balance_audit": triplet_component_balance_audit_rows,
        "triplet_alpha_gamma_audit": triplet_alpha_gamma_audit_rows,
        "triplet_emissivity_branch_audit": triplet_emissivity_branch_audit_rows,
        "calc_emis_triplet_audit": calc_emis_triplet_audit_rows,
        "calc_emis_context_audit": calc_emis_context_audit_rows,
        "calc_emis_ion_triplet_emergent": calc_emis_ion_triplet_emergent_rows,
        "triplet_coupling_record_audit": triplet_coupling_record_audit_rows,
        "triplet_coupling_suppression_comparison": triplet_coupling_suppression_comparison_rows,
        "radiation_normalization_audit": radiation_normalization_audit_rows,
        "type53_phint53_scale_scan": type53_phint53_scale_scan_rows,
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



def _truthy_value(value: object) -> bool:
    """Return True for common CSV/string boolean true values."""
    if value is True:
        return True
    if value is False or value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _row_global_index(row: Mapping[str, object], *keys: str) -> Optional[int]:
    """Return the first valid integer global-index value from *keys*."""
    for key in keys:
        val = maybe_int(row.get(key))
        if val is not None:
            return val
    return None


def _triplet_global_index_sets(global_index_rows: Sequence[dict], *, ion_stage: int) -> Dict[str, List[int]]:
    """Return global-index lists for f/i/r triplet upper levels."""
    out = {"f": [], "i": [], "r": []}
    for row in global_index_rows:
        if maybe_int(row.get("ion_stage")) != ion_stage:
            continue
        comp = str(row.get("triplet_component") or "").strip().lower()
        if comp in out and _truthy_value(row.get("is_triplet_upper")):
            gi = maybe_int(row.get("global_index"))
            if gi is not None:
                out[comp].append(gi)
    return out


def _global_index_metadata(global_index_rows: Sequence[dict]) -> Dict[int, dict]:
    meta = {}
    for row in global_index_rows:
        gi = maybe_int(row.get("global_index"))
        if gi is not None:
            meta[gi] = row
    return meta


def _full_global_population_map(full_global_normalized_solve_comparison_rows: Sequence[dict]) -> Dict[int, float]:
    """Extract population by global index from the normalized-solve comparison rows."""
    pop = {}
    for row in full_global_normalized_solve_comparison_rows:
        if row.get("row_kind") != "population":
            continue
        gi = maybe_int(row.get("global_index"))
        val = maybe_float(row.get("population_fraction"))
        if gi is not None and val is not None and math.isfinite(float(val)):
            pop[gi] = float(val)
    return pop


def build_intercombination_feed_audit_rows(
    *,
    global_index_rows: Sequence[dict],
    full_global_matrix_terms: Sequence[dict],
    full_global_normalized_solve_comparison_rows: Sequence[dict],
    he_like_stage: int,
) -> List[dict]:
    """Audit all currently assembled routes into/out of the He-like i upper levels.

    This is a diagnostic accounting table added in v0.3.60.  It focuses on the
    C V/O VII/etc. intercombination upper levels (1s2p 3P_J) and records every
    full-global matrix term that either feeds those levels, removes population
    from them, or appears as their diagonal loss.  Rates are whatever the current
    diagnostic matrix contains (physical bound-bound rates plus proxy/topology
    terms for the still-incomplete continuum/recombination channels).
    """
    meta = _global_index_metadata(global_index_rows)
    pops = _full_global_population_map(full_global_normalized_solve_comparison_rows)
    triplet_sets = _triplet_global_index_sets(global_index_rows, ion_stage=he_like_stage)
    i_targets = set(triplet_sets.get("i", []))
    f_targets = set(triplet_sets.get("f", []))
    r_targets = set(triplet_sets.get("r", []))
    all_triplet = f_targets | i_targets | r_targets
    rows: List[dict] = []
    term_id = 0
    for term in full_global_matrix_terms:
        row_gi = _row_global_index(term, "matrix_row_global_index", "row_global_index")
        col_gi = _row_global_index(term, "matrix_col_global_index", "col_global_index")
        rate = maybe_float(term.get("full_global_rate_s^-1") or term.get("rate_s^-1") or term.get("rate_proxy") or term.get("source_rate_s^-1"))
        signed = maybe_float(term.get("full_global_signed_rate_s^-1") or term.get("signed_rate_s^-1") or term.get("signed_rate_proxy"))
        if rate is None and signed is not None:
            rate = abs(float(signed))
        if rate is None:
            continue
        if not math.isfinite(float(rate)):
            continue
        touches_i = (row_gi in i_targets) or (col_gi in i_targets)
        if not touches_i:
            continue
        if row_gi in i_targets and col_gi != row_gi:
            route_role = "incoming_feed_to_intercombination_upper"
            target_gi = row_gi
            partner_gi = col_gi
        elif col_gi in i_targets and row_gi != col_gi:
            route_role = "outgoing_branch_or_coupling_from_intercombination_upper"
            target_gi = col_gi
            partner_gi = row_gi
        elif row_gi in i_targets and col_gi == row_gi:
            route_role = "diagonal_loss_on_intercombination_upper"
            target_gi = row_gi
            partner_gi = None
        else:
            continue
        target = meta.get(target_gi, {})
        partner = meta.get(partner_gi, {}) if partner_gi is not None else {}
        component_partner = partner.get("triplet_component") or ""
        if partner_gi in f_targets:
            partner_triplet_family = "f"
        elif partner_gi in i_targets:
            partner_triplet_family = "i"
        elif partner_gi in r_targets:
            partner_triplet_family = "r"
        elif partner_gi in all_triplet:
            partner_triplet_family = str(component_partner)
        else:
            partner_triplet_family = "non_triplet_or_continuum"
        pop_target = pops.get(target_gi, 0.0)
        contribution_proxy = float(rate) * float(pop_target)
        rows.append({
            "audit_row_id": term_id,
            "audit_kind": "intercombination_feed_branch_audit",
            "route_role": route_role,
            "target_global_index": target_gi,
            "target_level_index": target.get("level_index"),
            "target_level_label": target.get("level_label"),
            "target_triplet_component": target.get("triplet_component"),
            "target_population_fraction": pop_target,
            "partner_global_index": partner_gi if partner_gi is not None else "",
            "partner_ion_stage": partner.get("ion_stage", ""),
            "partner_level_index": partner.get("level_index", ""),
            "partner_level_label": partner.get("level_label", ""),
            "partner_level_kind": partner.get("level_kind", ""),
            "partner_triplet_family": partner_triplet_family,
            "matrix_term_kind": term.get("matrix_term_kind", ""),
            "matrix_role": term.get("matrix_role", ""),
            "full_global_component": term.get("full_global_component", ""),
            "transition_kind": term.get("transition_kind", ""),
            "data_type": term.get("data_type", ""),
            "record": term.get("record", ""),
            "rate_s^-1": float(rate),
            "signed_rate_s^-1": signed if signed is not None else "",
            "population_weighted_rate_proxy_s^-1": contribution_proxy,
            "diagnostic_note": "v0.3.60 audit; proxy/topology continuum terms are not physical XSTAR rates yet",
        })
        term_id += 1
    return rows


def _component_balance_for_indices(
    component: str,
    indices: Sequence[int],
    *,
    meta: Mapping[int, dict],
    pops: Mapping[int, float],
    full_global_matrix_terms: Sequence[dict],
) -> dict:
    idx = set(indices)
    incoming = 0.0
    outgoing = 0.0
    diagonal_loss = 0.0
    radiative_out = 0.0
    collisional_in = 0.0
    collisional_out = 0.0
    type71_in = 0.0
    type53_milne_in = 0.0
    type74_in = 0.0
    type53_photo_loss = 0.0
    n_in = n_out = n_diag = 0
    for term in full_global_matrix_terms:
        row_gi = _row_global_index(term, "matrix_row_global_index", "row_global_index")
        col_gi = _row_global_index(term, "matrix_col_global_index", "col_global_index")
        rate = maybe_float(term.get("full_global_rate_s^-1") or term.get("rate_s^-1") or term.get("rate_proxy") or term.get("source_rate_s^-1"))
        signed = maybe_float(term.get("full_global_signed_rate_s^-1") or term.get("signed_rate_s^-1") or term.get("signed_rate_proxy"))
        if rate is None and signed is not None:
            rate = abs(float(signed))
        if rate is None or not math.isfinite(float(rate)):
            continue
        rate = float(rate)
        comp_name = str(term.get("full_global_component") or "")
        trans_kind = str(term.get("transition_kind") or "")
        if row_gi in idx and col_gi != row_gi:
            incoming += rate
            n_in += 1
            if "type71" in comp_name:
                type71_in += rate
            if "type53_milne" in comp_name:
                type53_milne_in += rate
            if "type74" in comp_name:
                type74_in += rate
            if "collisional" in trans_kind:
                collisional_in += rate
        if col_gi in idx and row_gi != col_gi:
            outgoing += rate
            n_out += 1
            if "radiative_decay" in trans_kind:
                radiative_out += rate
            if "collisional" in trans_kind:
                collisional_out += rate
            if "type53_phint53" in comp_name:
                type53_photo_loss += rate
        if row_gi in idx and col_gi == row_gi:
            diagonal_loss += rate
            n_diag += 1
    pop_sum = sum(float(pops.get(i, 0.0)) for i in idx)
    label_summary = ";".join(str(meta.get(i, {}).get("level_label", i)) for i in sorted(idx))
    return {
        "component": component,
        "global_indices": ";".join(str(i) for i in sorted(idx)),
        "level_labels": label_summary,
        "population_sum": pop_sum,
        "incoming_rate_sum_s^-1": incoming,
        "outgoing_offdiag_rate_sum_s^-1": outgoing,
        "diagonal_loss_rate_sum_s^-1": diagonal_loss,
        "n_incoming_terms": n_in,
        "n_outgoing_terms": n_out,
        "n_diagonal_loss_terms": n_diag,
        "type71_cascade_in_rate_sum_s^-1": type71_in,
        "type53_milne_in_rate_sum_s^-1": type53_milne_in,
        "type74_inverse_in_rate_sum_s^-1": type74_in,
        "collisional_in_rate_sum_s^-1": collisional_in,
        "collisional_out_rate_sum_s^-1": collisional_out,
        "radiative_out_rate_sum_s^-1": radiative_out,
        "type53_photoionization_loss_rate_sum_s^-1": type53_photo_loss,
        "population_weighted_radiative_out_proxy_s^-1": pop_sum * radiative_out,
    }


def build_triplet_component_balance_audit_rows(
    *,
    global_index_rows: Sequence[dict],
    full_global_matrix_terms: Sequence[dict],
    full_global_normalized_solve_comparison_rows: Sequence[dict],
    he_like_stage: int,
) -> List[dict]:
    """Summarise source/loss balance for f/i/r upper-level groups."""
    meta = _global_index_metadata(global_index_rows)
    pops = _full_global_population_map(full_global_normalized_solve_comparison_rows)
    triplet_sets = _triplet_global_index_sets(global_index_rows, ion_stage=he_like_stage)
    rows = []
    for comp in ["f", "i", "r"]:
        row = _component_balance_for_indices(
            comp,
            triplet_sets.get(comp, []),
            meta=meta,
            pops=pops,
            full_global_matrix_terms=full_global_matrix_terms,
        )
        row["audit_kind"] = "triplet_component_balance"
        row["diagnostic_note"] = "v0.3.60 component balance; population-weighted radiative proxy is not a replacement for full emissivity calculation"
        rows.append(row)
    # Add a compact i/f/r comparison row to make sorting easier in spreadsheets.
    by = {r["component"]: r for r in rows}
    fpop = maybe_float(by.get("f", {}).get("population_sum")) or 0.0
    ipop = maybe_float(by.get("i", {}).get("population_sum")) or 0.0
    rpop = maybe_float(by.get("r", {}).get("population_sum")) or 0.0
    rows.append({
        "audit_kind": "triplet_component_balance_summary",
        "component": "summary",
        "population_sum_f": fpop,
        "population_sum_i": ipop,
        "population_sum_r": rpop,
        "i_over_f_population_ratio": (ipop / fpop if fpop else ""),
        "i_over_r_population_ratio": (ipop / rpop if rpop else ""),
        "incoming_rate_i_over_f": ((maybe_float(by.get("i", {}).get("incoming_rate_sum_s^-1")) or 0.0) / (maybe_float(by.get("f", {}).get("incoming_rate_sum_s^-1")) or 0.0) if (maybe_float(by.get("f", {}).get("incoming_rate_sum_s^-1")) or 0.0) else ""),
        "incoming_rate_i_over_r": ((maybe_float(by.get("i", {}).get("incoming_rate_sum_s^-1")) or 0.0) / (maybe_float(by.get("r", {}).get("incoming_rate_sum_s^-1")) or 0.0) if (maybe_float(by.get("r", {}).get("incoming_rate_sum_s^-1")) or 0.0) else ""),
        "diagnostic_note": "summary ratios for locating the low-intercombination bottleneck",
    })
    return rows



def _global_index_by_ion_level(global_index_rows: Sequence[dict]) -> Dict[Tuple[int, int], int]:
    """Return ``(ion_stage, level_index) -> global_index`` for explicit rows."""
    out: Dict[Tuple[int, int], int] = {}
    for r in global_index_rows:
        g = maybe_int(r.get("global_index"))
        stage = maybe_int(r.get("ion_stage"))
        lev = maybe_int(r.get("level_index"))
        if g is not None and stage is not None and lev is not None:
            out[(int(stage), int(lev))] = int(g)
    return out


def _term_signed_rate(term: Mapping[str, object]) -> Optional[float]:
    """Extract the signed matrix coefficient from a full-global term row."""
    for key in (
        "full_global_signed_rate_s^-1",
        "signed_rate_s^-1",
        "signed_rate_proxy_s^-1",
        "signed_rate_proxy",
    ):
        val = maybe_float(term.get(key))
        if val is not None and math.isfinite(float(val)):
            return float(val)
    return None


def _term_positive_rate(term: Mapping[str, object]) -> Optional[float]:
    """Extract a positive rate magnitude from a full-global term row."""
    for key in (
        "full_global_rate_s^-1",
        "rate_s^-1",
        "photoionization_rate_s^-1",
        "inverse_rate_s^-1",
        "rate_proxy_s^-1",
        "source_rate_s^-1",
        "rate_proxy",
    ):
        val = maybe_float(term.get(key))
        if val is not None and math.isfinite(float(val)):
            return abs(float(val))
    sval = _term_signed_rate(term)
    return abs(sval) if sval is not None else None


def build_triplet_alpha_gamma_audit_rows(
    *,
    global_index_rows: Sequence[dict],
    full_global_matrix_terms: Sequence[dict],
    full_global_normalized_solve_comparison_rows: Sequence[dict],
    he_like_stage: int,
) -> List[dict]:
    """Build an XSTAR-source-aligned alpha/gamma balance audit for f/i/r uppers.

    XSTAR ``msolvelucy`` uses population/fraction weighted terms rather than raw
    incoming rate sums.  This diagnostic therefore reports source-population
    weighted feed terms ``alpha = sum_j rate(i<-j) * n_j`` and loss terms
    ``gamma = sum_j rate(j<-i)`` for each triplet upper.  It remains a diagnostic
    proxy because the matrix terms may still contain nonphysical scaffolds.
    """
    he_like_stage = int(he_like_stage)
    meta = _global_index_metadata(global_index_rows)
    pops = _full_global_population_map(full_global_normalized_solve_comparison_rows)
    triplet_sets = _triplet_global_index_sets(global_index_rows, ion_stage=he_like_stage)
    triplet_indices = {comp: [int(x) for x in triplet_sets.get(comp, [])] for comp in ("f", "i", "r")}

    rows: List[dict] = []
    component_totals: Dict[str, Dict[str, float]] = {c: {"alpha": 0.0, "gamma_pop": 0.0, "pop": 0.0, "gamma": 0.0} for c in ("f", "i", "r")}

    for comp, indices in triplet_indices.items():
        for gi in indices:
            pop_i = float(pops.get(int(gi), 0.0))
            alpha = 0.0
            gamma = 0.0
            diag_loss = 0.0
            n_alpha = n_gamma = n_diag = 0
            feed_by_component: Dict[str, float] = {}
            loss_by_component: Dict[str, float] = {}
            dominant_feed = (0.0, None, None, None)  # weighted, source gi, component, term
            dominant_loss = (0.0, None, None, None)
            for term in full_global_matrix_terms:
                row_gi = _row_global_index(term, "matrix_row_global_index", "row_global_index")
                col_gi = _row_global_index(term, "matrix_col_global_index", "col_global_index")
                rate = _term_positive_rate(term)
                signed = _term_signed_rate(term)
                if rate is None or not math.isfinite(rate):
                    continue
                component_name = str(term.get("full_global_component") or "")
                matrix_kind = str(term.get("matrix_term_kind") or "")
                # Source -> this level feed: M[this, source] += rate.
                if row_gi == gi and col_gi is not None and col_gi != gi:
                    src_pop = float(pops.get(int(col_gi), 0.0))
                    weighted = rate * src_pop
                    alpha += weighted
                    n_alpha += 1
                    feed_by_component[component_name] = feed_by_component.get(component_name, 0.0) + weighted
                    if abs(weighted) > dominant_feed[0]:
                        dominant_feed = (abs(weighted), int(col_gi), component_name, term)
                # This level -> destination loss: M[dest, this] += rate.
                if col_gi == gi and row_gi is not None and row_gi != gi:
                    gamma += rate
                    n_gamma += 1
                    loss_by_component[component_name] = loss_by_component.get(component_name, 0.0) + rate
                    if rate > dominant_loss[0]:
                        dominant_loss = (rate, int(row_gi), component_name, term)
                # Diagonal drain on this level.
                if row_gi == gi and col_gi == gi:
                    dval = abs(float(signed)) if signed is not None else rate
                    diag_loss += dval
                    n_diag += 1
                    loss_by_component[component_name] = loss_by_component.get(component_name, 0.0) + dval
            gamma_total = gamma if gamma > 0.0 else diag_loss
            if diag_loss > gamma_total:
                gamma_total = diag_loss
            alpha_over_gamma = alpha / gamma_total if gamma_total > 0.0 else None
            pop_over_alpha_gamma = pop_i / alpha_over_gamma if alpha_over_gamma and alpha_over_gamma != 0.0 else None
            df_term = dominant_feed[3] or {}
            dl_term = dominant_loss[3] or {}
            rows.append({
                "audit_kind": "triplet_alpha_gamma_level",
                "component": comp,
                "global_index": gi,
                "ion_stage": meta.get(gi, {}).get("ion_stage"),
                "level_index": meta.get(gi, {}).get("level_index"),
                "level_label": meta.get(gi, {}).get("level_label"),
                "population_fraction": pop_i,
                "alpha_source_population_weighted_feed_s^-1": alpha,
                "gamma_loss_rate_sum_s^-1": gamma_total,
                "gamma_offdiag_loss_rate_sum_s^-1": gamma,
                "gamma_diagonal_loss_rate_sum_s^-1": diag_loss,
                "alpha_over_gamma_population_proxy": alpha_over_gamma,
                "population_over_alpha_gamma_proxy": pop_over_alpha_gamma,
                "n_alpha_feed_terms": n_alpha,
                "n_gamma_loss_terms": n_gamma,
                "n_diagonal_loss_terms": n_diag,
                "alpha_by_component_json": json.dumps(dict(sorted(feed_by_component.items())), sort_keys=True),
                "gamma_by_component_json": json.dumps(dict(sorted(loss_by_component.items())), sort_keys=True),
                "dominant_alpha_source_global_index": dominant_feed[1] if dominant_feed[1] is not None else "",
                "dominant_alpha_source_level_label": meta.get(dominant_feed[1], {}).get("level_label", "") if dominant_feed[1] is not None else "",
                "dominant_alpha_component": dominant_feed[2] or "",
                "dominant_alpha_weighted_rate_s^-1": dominant_feed[0],
                "dominant_alpha_record": df_term.get("record", df_term.get("source_record", "")),
                "dominant_alpha_matrix_term_kind": df_term.get("matrix_term_kind", ""),
                "dominant_gamma_destination_global_index": dominant_loss[1] if dominant_loss[1] is not None else "",
                "dominant_gamma_destination_level_label": meta.get(dominant_loss[1], {}).get("level_label", "") if dominant_loss[1] is not None else "",
                "dominant_gamma_component": dominant_loss[2] or "",
                "dominant_gamma_rate_s^-1": dominant_loss[0],
                "dominant_gamma_record": dl_term.get("record", dl_term.get("source_record", "")),
                "dominant_gamma_matrix_term_kind": dl_term.get("matrix_term_kind", ""),
                "diagnostic_note": "v0.3.61 XSTAR-like alpha/gamma audit: alpha uses source population times feed rate; gamma uses loss rates. Matrix terms may still include proxy topology.",
            })
            component_totals[comp]["alpha"] += alpha
            component_totals[comp]["gamma_pop"] += gamma_total * pop_i
            component_totals[comp]["pop"] += pop_i
            component_totals[comp]["gamma"] += gamma_total

    for comp in ("f", "i", "r"):
        t = component_totals[comp]
        rows.append({
            "audit_kind": "triplet_alpha_gamma_component_summary",
            "component": comp,
            "population_fraction_sum": t["pop"],
            "alpha_source_population_weighted_feed_sum_s^-1": t["alpha"],
            "population_weighted_gamma_loss_sum_s^-1": t["gamma_pop"],
            "gamma_loss_rate_sum_s^-1": t["gamma"],
            "alpha_minus_population_weighted_gamma_s^-1": t["alpha"] - t["gamma_pop"],
            "alpha_over_population_weighted_gamma": (t["alpha"] / t["gamma_pop"] if t["gamma_pop"] > 0.0 else ""),
            "diagnostic_note": "component-level XSTAR-like steady-state balance proxy",
        })
    # Compact comparison row.
    f = component_totals["f"]; i = component_totals["i"]; r = component_totals["r"]
    rows.append({
        "audit_kind": "triplet_alpha_gamma_summary",
        "component": "summary",
        "population_i_over_f": (i["pop"] / f["pop"] if f["pop"] else ""),
        "population_i_over_r": (i["pop"] / r["pop"] if r["pop"] else ""),
        "alpha_i_over_f": (i["alpha"] / f["alpha"] if f["alpha"] else ""),
        "alpha_i_over_r": (i["alpha"] / r["alpha"] if r["alpha"] else ""),
        "gamma_pop_i_over_f": (i["gamma_pop"] / f["gamma_pop"] if f["gamma_pop"] else ""),
        "gamma_pop_i_over_r": (i["gamma_pop"] / r["gamma_pop"] if r["gamma_pop"] else ""),
        "diagnostic_note": "summary ratios; use with emissivity audit to separate population-balance and line-accounting effects",
    })
    return rows


def build_triplet_emissivity_branch_audit_rows(
    *,
    global_index_rows: Sequence[dict],
    line_rows: Sequence[dict],
    full_global_matrix_terms: Sequence[dict],
    full_global_normalized_solve_comparison_rows: Sequence[dict],
    he_like_stage: int,
) -> List[dict]:
    """Audit triplet line branching/emissivity accounting from solved populations.

    The current line rows use a simple ``n_upper*A*E`` proxy.  XSTAR's
    ``calc_emis_ion`` includes net ``ucalc`` emissivities, line selection, and
    escape probabilities.  This audit records the simple proxy alongside fields
    that make the missing XSTAR factors explicit.
    """
    he_like_stage = int(he_like_stage)
    meta = _global_index_metadata(global_index_rows)
    by_ion_level = _global_index_by_ion_level(global_index_rows)
    pops = _full_global_population_map(full_global_normalized_solve_comparison_rows)
    # Total radiative A out of each upper level from decoded line list.
    total_A_by_upper: Dict[int, float] = {}
    for row in line_rows:
        if maybe_int(row.get("ion_stage")) != he_like_stage:
            continue
        upper = maybe_int(row.get("upper_level"))
        A = maybe_float(row.get("A_s^-1"))
        if upper is not None and A is not None and A > 0.0:
            total_A_by_upper[int(upper)] = total_A_by_upper.get(int(upper), 0.0) + float(A)

    rows: List[dict] = []
    component_sums: Dict[str, Dict[str, float]] = {c: {"energy": 0.0, "photon": 0.0, "pop": 0.0, "A": 0.0, "n": 0.0} for c in ("f", "i", "r")}
    for row in line_rows:
        if maybe_int(row.get("ion_stage")) != he_like_stage:
            continue
        comp = classify_helike_triplet_line(row)
        if comp not in {"f", "i", "r"}:
            continue
        upper = maybe_int(row.get("upper_level"))
        lower = maybe_int(row.get("lower_level"))
        if upper is None:
            continue
        ug = by_ion_level.get((he_like_stage, int(upper)))
        lg = by_ion_level.get((he_like_stage, int(lower))) if lower is not None else None
        upper_pop = float(pops.get(int(ug), 0.0)) if ug is not None else 0.0
        lower_pop = float(pops.get(int(lg), 0.0)) if lg is not None else 0.0
        A = maybe_float(row.get("A_s^-1")) or 0.0
        Eerg = line_energy_erg(row) or 0.0
        total_A = total_A_by_upper.get(int(upper), 0.0)
        branch = float(A) / total_A if total_A > 0.0 and A > 0.0 else None
        simple_photon = max(upper_pop, 0.0) * max(float(A), 0.0)
        simple_energy = simple_photon * max(float(Eerg), 0.0)
        # XSTAR calc_emis_ion has two escape-probability channels.  Until tau/cfrac
        # are available, record transparent placeholders separately from the simple
        # proxy rather than hiding this missing physics.
        pescl_tau1_placeholder = 1.0
        pescl_tau2_placeholder = 1.0
        cfrac_placeholder = 0.0
        ptmp1 = pescl_tau1_placeholder * (1.0 - cfrac_placeholder)
        ptmp2 = pescl_tau2_placeholder * (1.0 - cfrac_placeholder) + 2.0 * pescl_tau1_placeholder * cfrac_placeholder
        xstar_like_energy_ptmp1 = simple_energy * ptmp1
        xstar_like_energy_ptmp2 = simple_energy * ptmp2
        component_sums[comp]["energy"] += simple_energy
        component_sums[comp]["photon"] += simple_photon
        component_sums[comp]["pop"] += upper_pop
        component_sums[comp]["A"] += float(A)
        component_sums[comp]["n"] += 1.0
        rows.append({
            "audit_kind": "triplet_emissivity_branch_line",
            "component": comp,
            "record": row.get("record"),
            "ion_stage": he_like_stage,
            "upper_level": upper,
            "lower_level": lower,
            "upper_global_index": ug if ug is not None else "",
            "lower_global_index": lg if lg is not None else "",
            "upper_label": row.get("upper_label"),
            "lower_label": row.get("lower_label"),
            "wavelength_A": row.get("wavelength_A"),
            "energy_eV": row.get("energy_eV"),
            "photon_energy_erg": Eerg,
            "A_s^-1": A,
            "total_A_from_upper_decoded_lines_s^-1": total_A,
            "branching_fraction_from_upper_decoded_lines": branch,
            "upper_population_fraction": upper_pop,
            "lower_population_fraction": lower_pop,
            "simple_pop_A_photon_emissivity_s^-1": simple_photon,
            "simple_pop_A_energy_emissivity_erg_s^-1": simple_energy,
            "xstar_like_transparent_ptmp1_energy_proxy_erg_s^-1": xstar_like_energy_ptmp1,
            "xstar_like_transparent_ptmp2_energy_proxy_erg_s^-1": xstar_like_energy_ptmp2,
            "ptmp1_escape_placeholder": ptmp1,
            "ptmp2_escape_placeholder": ptmp2,
            "missing_xstar_emissivity_context": "ucalc_net_ans1_ans2;abund1_abund2;optical_depth_tau1_tau2;escape_probability_pescl;cfrac;strong_line_filtering_nlbin_ncbin",
            "diagnostic_note": "v0.3.61 branch audit: transparent XSTAR-like proxy equals simple pop*A*E until escape/net-emissivity context is ported",
        })

    total_energy = sum(component_sums[c]["energy"] for c in ("f", "i", "r"))
    target = _xstar_triplet_target(he_like_stage)
    for comp in ("f", "i", "r"):
        frac = component_sums[comp]["energy"] / total_energy if total_energy > 0.0 else 0.0
        target_frac = maybe_float((target or {}).get(comp) or (target or {}).get(f"{comp}_fraction"))
        rows.append({
            "audit_kind": "triplet_emissivity_branch_component_summary",
            "component": comp,
            "n_lines": int(component_sums[comp]["n"]),
            "upper_population_fraction_sum_over_lines": component_sums[comp]["pop"],
            "A_s^-1_sum_over_lines": component_sums[comp]["A"],
            "simple_pop_A_photon_emissivity_sum_s^-1": component_sums[comp]["photon"],
            "simple_pop_A_energy_emissivity_sum_erg_s^-1": component_sums[comp]["energy"],
            "component_fraction_from_simple_emissivity": frac,
            "target_component_fraction": target_frac,
            "delta_fraction_minus_target": (frac - target_frac if target_frac is not None else ""),
            "diagnostic_note": "component summary for deciding whether low i is a population or line-accounting problem",
        })
    fE = component_sums["f"]["energy"]
    iE = component_sums["i"]["energy"]
    rE = component_sums["r"]["energy"]
    rows.append({
        "audit_kind": "triplet_emissivity_branch_summary",
        "component": "summary",
        "f_energy_sum_erg_s^-1": fE,
        "i_energy_sum_erg_s^-1": iE,
        "r_energy_sum_erg_s^-1": rE,
        "f_fraction": fE / total_energy if total_energy else 0.0,
        "i_fraction": iE / total_energy if total_energy else 0.0,
        "r_fraction": rE / total_energy if total_energy else 0.0,
        "R": fE / iE if iE > 0.0 else "",
        "G": (fE + iE) / rE if rE > 0.0 else "",
        "missing_xstar_context_summary": "transparent proxy only; calc_emis_ion net emissivity and escape probabilities not yet ported",
    })
    return rows





def build_calc_emis_triplet_audit_rows(
    *,
    global_index_rows: Sequence[dict],
    line_rows: Sequence[dict],
    full_global_normalized_solve_comparison_rows: Sequence[dict],
    he_like_stage: int,
) -> List[dict]:
    """Build a calc_emis_ion-style audit for He-like triplet line output.

    XSTAR's ``calc_emis_ion`` recomputes ``ucalc`` for selected strong lines and
    forms line channels approximately as::

        fline(1) = max((ans2*abund2 - ans1*abund1) * E * ptmp1, 0)
        fline(2) = max((ans2*abund2 - ans1*abund1) * E * ptmp2, 0)

    where ``abund1`` and ``abund2`` contain the lower/upper level populations
    times ion/element abundance factors, and ``ptmp1``/``ptmp2`` contain escape
    probabilities and continuum-covering geometry.  The current pure-Python
    scaffold does not yet port the full ``calc_emis_ion`` context, so this audit
    writes a transparent, source-code-aligned proxy with explicit placeholders.
    """
    he_like_stage = int(he_like_stage)
    by_ion_level = _global_index_by_ion_level(global_index_rows)
    pops = _full_global_population_map(full_global_normalized_solve_comparison_rows)
    target = _xstar_triplet_target(he_like_stage) or {}

    rows: List[dict] = []
    component_sums: Dict[str, Dict[str, float]] = {
        c: {"simple": 0.0, "fline1": 0.0, "fline2": 0.0, "fline_total": 0.0, "photon": 0.0, "n": 0.0}
        for c in ("f", "i", "r")
    }
    all_triplet_records = []
    for row in line_rows:
        if maybe_int(row.get("ion_stage")) != he_like_stage:
            continue
        comp = classify_helike_triplet_line(row)
        if comp not in {"f", "i", "r"}:
            continue
        all_triplet_records.append(str(row.get("record") or ""))
        upper = maybe_int(row.get("upper_level"))
        lower = maybe_int(row.get("lower_level"))
        if upper is None or lower is None:
            continue
        ug = by_ion_level.get((he_like_stage, int(upper)))
        lg = by_ion_level.get((he_like_stage, int(lower)))
        upper_pop = float(pops.get(int(ug), 0.0)) if ug is not None else 0.0
        lower_pop = float(pops.get(int(lg), 0.0)) if lg is not None else 0.0
        A = maybe_float(row.get("A_s^-1")) or 0.0
        Eerg = line_energy_erg(row) or 0.0
        EeV = maybe_float(row.get("energy_eV"))
        # Transparent proxy for ucalc type-4/50 line emissivity.
        # In the no-stimulated/transparent limit ans2≈A_ul and ans1≈0, so
        # fline(1) is equal to simple n_upper*A*E.  fline(2) is the second XSTAR
        # channel and is reported separately, not used to redefine the current
        # triplet ratio.
        ans2_emission_proxy_s_inv = max(float(A), 0.0)
        ans1_absorption_or_stimulated_proxy_s_inv = 0.0
        xeltp_proxy = 1.0
        xpx_proxy = 1.0
        abund1_lower_proxy = lower_pop * xpx_proxy * xeltp_proxy
        abund2_upper_proxy = upper_pop * xpx_proxy * xeltp_proxy
        net_rate_proxy = ans2_emission_proxy_s_inv * abund2_upper_proxy - ans1_absorption_or_stimulated_proxy_s_inv * abund1_lower_proxy
        tau1_proxy = 0.0
        tau2_proxy = 0.0
        cfrac_proxy = 0.0
        pescl_tau1_proxy = 1.0
        pescl_tau2_proxy = 1.0
        pescl_tau1_plus_tau2_proxy = 1.0
        ptmp1_proxy = pescl_tau1_proxy * (1.0 - cfrac_proxy)
        ptmp2_proxy = pescl_tau2_proxy * (1.0 - cfrac_proxy) + 2.0 * pescl_tau1_plus_tau2_proxy * cfrac_proxy
        fline1_proxy = max(net_rate_proxy * Eerg * ptmp1_proxy, 0.0)
        fline2_proxy = max(net_rate_proxy * Eerg * ptmp2_proxy, 0.0)
        simple_energy = max(upper_pop, 0.0) * max(float(A), 0.0) * max(Eerg, 0.0)
        simple_photon = max(upper_pop, 0.0) * max(float(A), 0.0)
        component_sums[comp]["simple"] += simple_energy
        component_sums[comp]["fline1"] += fline1_proxy
        component_sums[comp]["fline2"] += fline2_proxy
        component_sums[comp]["fline_total"] += fline1_proxy + fline2_proxy
        component_sums[comp]["photon"] += simple_photon
        component_sums[comp]["n"] += 1.0
        rows.append({
            "audit_kind": "calc_emis_triplet_line",
            "component": comp,
            "contributes_to_triplet_ratio_proxy": True,
            "record": row.get("record"),
            "ion_stage": he_like_stage,
            "lower_level": lower,
            "upper_level": upper,
            "lower_global_index": lg if lg is not None else "",
            "upper_global_index": ug if ug is not None else "",
            "lower_label": row.get("lower_label"),
            "upper_label": row.get("upper_label"),
            "wavelength_A": row.get("wavelength_A"),
            "energy_eV": EeV,
            "photon_energy_erg": Eerg,
            "A_s^-1": A,
            "lower_population_fraction": lower_pop,
            "upper_population_fraction": upper_pop,
            "xstar_calc_emis_abund1_lower_proxy": abund1_lower_proxy,
            "xstar_calc_emis_abund2_upper_proxy": abund2_upper_proxy,
            "xstar_ucalc_ans1_absorption_or_stimulated_proxy_s^-1": ans1_absorption_or_stimulated_proxy_s_inv,
            "xstar_ucalc_ans2_emission_proxy_s^-1": ans2_emission_proxy_s_inv,
            "xstar_net_rate_proxy_ans2_abund2_minus_ans1_abund1_s^-1": net_rate_proxy,
            "tau1_proxy": tau1_proxy,
            "tau2_proxy": tau2_proxy,
            "cfrac_proxy": cfrac_proxy,
            "pescl_tau1_proxy": pescl_tau1_proxy,
            "pescl_tau2_proxy": pescl_tau2_proxy,
            "pescl_tau1_plus_tau2_proxy": pescl_tau1_plus_tau2_proxy,
            "ptmp1_proxy": ptmp1_proxy,
            "ptmp2_proxy": ptmp2_proxy,
            "simple_pop_A_E_energy_proxy_erg_s^-1": simple_energy,
            "simple_pop_A_photon_proxy_s^-1": simple_photon,
            "calc_emis_fline1_transparent_proxy_erg_s^-1": fline1_proxy,
            "calc_emis_fline2_transparent_proxy_erg_s^-1": fline2_proxy,
            "calc_emis_fline_total_transparent_proxy_erg_s^-1": fline1_proxy + fline2_proxy,
            "simple_to_calc_emis_fline1_ratio": (simple_energy / fline1_proxy if fline1_proxy > 0.0 else ""),
            "strong_line_selection_status": "selected_output_line_proxy; nlbin/ncbin strong-line lists not yet ported",
            "missing_calc_emis_ion_context": "true ucalc ans1/ans2 with stimulated terms; tau0/tauc optical depths; pescl/pescv; cfrac; xpx/xeltp abundance factors; nlbin/ncbin strong-line filtering",
            "xstar_source_reference": "calc_emis_ion.f90 type-4/type-9 branch: fline=max((ans2*abund2-ans1*abund1)*E*ptmp,0)",
            "diagnostic_note": "v0.3.64 transparent calc_emis_ion-style audit; channel-1 proxy should equal simple pop*A*E when ans1=0 and escape=1",
        })

    total_simple = sum(component_sums[c]["simple"] for c in ("f", "i", "r"))
    total_fline1 = sum(component_sums[c]["fline1"] for c in ("f", "i", "r"))
    total_fline_total = sum(component_sums[c]["fline_total"] for c in ("f", "i", "r"))
    for comp in ("f", "i", "r"):
        target_frac = maybe_float(target.get(comp) or target.get(f"{comp}_fraction"))
        frac_simple = component_sums[comp]["simple"] / total_simple if total_simple > 0.0 else 0.0
        frac_fline1 = component_sums[comp]["fline1"] / total_fline1 if total_fline1 > 0.0 else 0.0
        frac_total = component_sums[comp]["fline_total"] / total_fline_total if total_fline_total > 0.0 else 0.0
        rows.append({
            "audit_kind": "calc_emis_triplet_component_summary",
            "component": comp,
            "n_lines": int(component_sums[comp]["n"]),
            "simple_pop_A_E_energy_sum_erg_s^-1": component_sums[comp]["simple"],
            "simple_photon_sum_s^-1": component_sums[comp]["photon"],
            "calc_emis_fline1_transparent_sum_erg_s^-1": component_sums[comp]["fline1"],
            "calc_emis_fline2_transparent_sum_erg_s^-1": component_sums[comp]["fline2"],
            "calc_emis_fline_total_transparent_sum_erg_s^-1": component_sums[comp]["fline_total"],
            "fraction_simple_pop_A_E": frac_simple,
            "fraction_calc_emis_fline1_transparent": frac_fline1,
            "fraction_calc_emis_fline_total_transparent": frac_total,
            "target_component_fraction": target_frac,
            "delta_fline1_fraction_minus_target": (frac_fline1 - target_frac if target_frac is not None else ""),
            "diagnostic_note": "component summary for source-code-aligned calc_emis_ion transparent proxy",
        })
    f1 = component_sums["f"]["fline1"]
    i1 = component_sums["i"]["fline1"]
    r1 = component_sums["r"]["fline1"]
    rows.append({
        "audit_kind": "calc_emis_triplet_summary",
        "component": "summary",
        "n_triplet_line_records": len([x for x in all_triplet_records if x]),
        "triplet_records": ";".join([x for x in all_triplet_records if x]),
        "f_fraction_calc_emis_fline1_transparent": f1 / total_fline1 if total_fline1 else 0.0,
        "i_fraction_calc_emis_fline1_transparent": i1 / total_fline1 if total_fline1 else 0.0,
        "r_fraction_calc_emis_fline1_transparent": r1 / total_fline1 if total_fline1 else 0.0,
        "R_calc_emis_fline1_transparent": f1 / i1 if i1 > 0.0 else "",
        "G_calc_emis_fline1_transparent": (f1 + i1) / r1 if r1 > 0.0 else "",
        "total_simple_pop_A_E_energy_erg_s^-1": total_simple,
        "total_calc_emis_fline1_transparent_erg_s^-1": total_fline1,
        "total_calc_emis_fline_total_transparent_erg_s^-1": total_fline_total,
        "simple_to_fline1_total_ratio": total_simple / total_fline1 if total_fline1 > 0.0 else "",
        "conclusion_scope": "If transparent fractions equal simple fractions, remaining differences require porting true calc_emis_ion contexts: ucalc net ans1/ans2, escape/opacity, abundance factors, and strong-line filtering.",
        "provenance": "v0.3.64_calc_emis_ion_style_triplet_line_output_audit",
    })
    return rows


def _calc_emis_triplet_audit_summary(rows: Sequence[dict]) -> dict:
    summary = next((r for r in rows if r.get("audit_kind") == "calc_emis_triplet_summary"), {})
    comps = {r.get("component"): r for r in rows if r.get("audit_kind") == "calc_emis_triplet_component_summary"}
    return {
        "n_calc_emis_triplet_audit_rows": len(rows),
        "n_calc_emis_triplet_line_rows": sum(1 for r in rows if r.get("audit_kind") == "calc_emis_triplet_line"),
        "f_fraction": summary.get("f_fraction_calc_emis_fline1_transparent", comps.get("f", {}).get("fraction_calc_emis_fline1_transparent", "")),
        "i_fraction": summary.get("i_fraction_calc_emis_fline1_transparent", comps.get("i", {}).get("fraction_calc_emis_fline1_transparent", "")),
        "r_fraction": summary.get("r_fraction_calc_emis_fline1_transparent", comps.get("r", {}).get("fraction_calc_emis_fline1_transparent", "")),
        "R": summary.get("R_calc_emis_fline1_transparent", ""),
        "G": summary.get("G_calc_emis_fline1_transparent", ""),
        "simple_to_fline1_total_ratio": summary.get("simple_to_fline1_total_ratio", ""),
        "missing_context": "true calc_emis_ion ucalc ans1/ans2, optical depth, escape probability, covering fraction, abundance scaling, and strong-line filtering",
        "provenance": "v0.3.64_calc_emis_ion_style_triplet_line_output_audit",
    }

def _line_output_balance_context(
    *,
    global_index: Optional[int],
    full_global_matrix_terms: Sequence[dict],
    populations: Mapping[int, float],
) -> dict:
    """Summarise matrix-population context for one global level.

    This is not a full XSTAR ``ucalc`` port.  It converts the already assembled
    full-global matrix rows into source-population-weighted feeds and outgoing
    loss-rate sums so that the line-output audit can show what runtime context is
    available and what remains a placeholder.
    """
    if global_index is None:
        return {
            "alpha_source_population_weighted_feed_s^-1": 0.0,
            "gamma_offdiag_loss_rate_sum_s^-1": 0.0,
            "gamma_diagonal_loss_rate_sum_s^-1": 0.0,
            "gamma_loss_rate_context_s^-1": 0.0,
            "n_alpha_feed_terms": 0,
            "n_gamma_loss_terms": 0,
            "n_diagonal_loss_terms": 0,
            "dominant_alpha_component": "",
            "dominant_alpha_record": "",
            "dominant_gamma_component": "",
            "dominant_gamma_record": "",
            "alpha_by_component_json": "{}",
            "gamma_by_component_json": "{}",
        }
    gi = int(global_index)
    alpha = 0.0
    gamma_offdiag = 0.0
    gamma_diag = 0.0
    n_alpha = n_gamma = n_diag = 0
    alpha_by_component: Dict[str, float] = {}
    gamma_by_component: Dict[str, float] = {}
    dominant_alpha = (0.0, "", "")
    dominant_gamma = (0.0, "", "")
    for term in full_global_matrix_terms:
        row_gi = _row_global_index(term, "matrix_row_global_index", "row_global_index")
        col_gi = _row_global_index(term, "matrix_col_global_index", "col_global_index")
        rate = _term_positive_rate(term)
        signed = _term_signed_rate(term)
        if rate is None or not math.isfinite(float(rate)):
            continue
        component_name = str(term.get("full_global_component") or term.get("source_method") or "")
        record = str(term.get("record") or term.get("source_record") or "")
        if row_gi == gi and col_gi is not None and col_gi != gi:
            src_pop = float(populations.get(int(col_gi), 0.0))
            weighted = abs(float(rate)) * src_pop
            alpha += weighted
            n_alpha += 1
            alpha_by_component[component_name] = alpha_by_component.get(component_name, 0.0) + weighted
            if weighted > dominant_alpha[0]:
                dominant_alpha = (weighted, component_name, record)
        if col_gi == gi and row_gi is not None and row_gi != gi:
            rval = abs(float(rate))
            gamma_offdiag += rval
            n_gamma += 1
            gamma_by_component[component_name] = gamma_by_component.get(component_name, 0.0) + rval
            if rval > dominant_gamma[0]:
                dominant_gamma = (rval, component_name, record)
        if row_gi == gi and col_gi == gi:
            dval = abs(float(signed)) if signed is not None else abs(float(rate))
            gamma_diag += dval
            n_diag += 1
            gamma_by_component[component_name] = gamma_by_component.get(component_name, 0.0) + dval
    gamma_context = max(gamma_offdiag, gamma_diag)
    return {
        "alpha_source_population_weighted_feed_s^-1": alpha,
        "gamma_offdiag_loss_rate_sum_s^-1": gamma_offdiag,
        "gamma_diagonal_loss_rate_sum_s^-1": gamma_diag,
        "gamma_loss_rate_context_s^-1": gamma_context,
        "population_from_alpha_over_gamma_context": (alpha / gamma_context if gamma_context > 0.0 else ""),
        "n_alpha_feed_terms": n_alpha,
        "n_gamma_loss_terms": n_gamma,
        "n_diagonal_loss_terms": n_diag,
        "dominant_alpha_component": dominant_alpha[1],
        "dominant_alpha_record": dominant_alpha[2],
        "dominant_gamma_component": dominant_gamma[1],
        "dominant_gamma_record": dominant_gamma[2],
        "alpha_by_component_json": json.dumps(dict(sorted(alpha_by_component.items())), sort_keys=True),
        "gamma_by_component_json": json.dumps(dict(sorted(gamma_by_component.items())), sort_keys=True),
    }


def build_calc_emis_context_audit_rows(
    *,
    global_index_rows: Sequence[dict],
    line_rows: Sequence[dict],
    full_global_matrix_terms: Sequence[dict],
    full_global_normalized_solve_comparison_rows: Sequence[dict],
    he_like_stage: int,
) -> List[dict]:
    """Build a v0.3.65 audit for the missing XSTAR line-output runtime context.

    v0.3.64 showed that the transparent ``calc_emis_ion`` proxy is identical to
    ``n_upper*A*E``.  This follow-up audit keeps that transparent baseline but
    adds the matrix-population context available to an eventual ``ucalc`` port,
    plus the line-accounting correction factors that would be needed to reproduce
    the XSTAR f/i/r target while holding the solved populations fixed.
    """
    he_like_stage = int(he_like_stage)
    by_ion_level = _global_index_by_ion_level(global_index_rows)
    pops = _full_global_population_map(full_global_normalized_solve_comparison_rows)
    target = _xstar_triplet_target(he_like_stage) or {}
    target_frac = {
        c: maybe_float(target.get(c) or target.get(f"{c}_fraction"))
        for c in ("f", "i", "r")
    }
    rows: List[dict] = []
    component_sums: Dict[str, Dict[str, float]] = {
        c: {"transparent": 0.0, "photon": 0.0, "n": 0.0, "upper_pop": 0.0, "alpha": 0.0, "gamma_pop": 0.0}
        for c in ("f", "i", "r")
    }
    line_cache: List[dict] = []
    for row in line_rows:
        if maybe_int(row.get("ion_stage")) != he_like_stage:
            continue
        comp = classify_helike_triplet_line(row)
        if comp not in {"f", "i", "r"}:
            continue
        upper = maybe_int(row.get("upper_level"))
        lower = maybe_int(row.get("lower_level"))
        if upper is None or lower is None:
            continue
        ug = by_ion_level.get((he_like_stage, int(upper)))
        lg = by_ion_level.get((he_like_stage, int(lower)))
        upper_pop = float(pops.get(int(ug), 0.0)) if ug is not None else 0.0
        lower_pop = float(pops.get(int(lg), 0.0)) if lg is not None else 0.0
        A = maybe_float(row.get("A_s^-1")) or 0.0
        Eerg = line_energy_erg(row) or 0.0
        transparent = max(upper_pop, 0.0) * max(float(A), 0.0) * max(float(Eerg), 0.0)
        photon = max(upper_pop, 0.0) * max(float(A), 0.0)
        ctx = _line_output_balance_context(global_index=ug, full_global_matrix_terms=full_global_matrix_terms, populations=pops)
        component_sums[comp]["transparent"] += transparent
        component_sums[comp]["photon"] += photon
        component_sums[comp]["n"] += 1.0
        component_sums[comp]["upper_pop"] += upper_pop
        component_sums[comp]["alpha"] += maybe_float(ctx.get("alpha_source_population_weighted_feed_s^-1")) or 0.0
        gamma = maybe_float(ctx.get("gamma_loss_rate_context_s^-1")) or 0.0
        component_sums[comp]["gamma_pop"] += gamma * upper_pop
        line_cache.append({
            "row": row, "component": comp, "upper": upper, "lower": lower,
            "ug": ug, "lg": lg, "upper_pop": upper_pop, "lower_pop": lower_pop,
            "A": float(A), "Eerg": float(Eerg), "transparent": transparent, "photon": photon,
            "ctx": ctx,
        })

    total_transparent = sum(component_sums[c]["transparent"] for c in ("f", "i", "r"))
    current_frac = {
        c: (component_sums[c]["transparent"] / total_transparent if total_transparent > 0.0 else 0.0)
        for c in ("f", "i", "r")
    }
    # Required component multipliers are only a diagnostic.  They answer: if the
    # solved populations and A-values are kept fixed, how much would line-output
    # accounting need to rescale each component to match the XSTAR fractions?
    required_scale = {
        c: (target_frac[c] / current_frac[c] if target_frac[c] is not None and current_frac[c] > 0.0 else "")
        for c in ("f", "i", "r")
    }
    i_only_scale = ""
    if component_sums["i"]["transparent"] > 0.0 and target_frac.get("i") is not None and target_frac["i"] is not None and target_frac["i"] < 1.0:
        i_only_scale = target_frac["i"] * (component_sums["f"]["transparent"] + component_sums["r"]["transparent"]) / (component_sums["i"]["transparent"] * (1.0 - target_frac["i"]))

    for item in line_cache:
        comp = item["component"]
        ctx = item["ctx"]
        comp_scale = required_scale.get(comp, "")
        required_ans2 = item["A"] * float(comp_scale) if isinstance(comp_scale, (int, float)) and math.isfinite(float(comp_scale)) else ""
        required_ptmp = comp_scale
        escape_only_feasible = isinstance(required_ptmp, (int, float)) and 0.0 <= float(required_ptmp) <= 1.0
        rows.append({
            "audit_kind": "calc_emis_context_line",
            "component": comp,
            "record": item["row"].get("record"),
            "ion_stage": he_like_stage,
            "lower_level": item["lower"],
            "upper_level": item["upper"],
            "lower_global_index": item["lg"] if item["lg"] is not None else "",
            "upper_global_index": item["ug"] if item["ug"] is not None else "",
            "lower_label": item["row"].get("lower_label"),
            "upper_label": item["row"].get("upper_label"),
            "wavelength_A": item["row"].get("wavelength_A"),
            "energy_eV": item["row"].get("energy_eV"),
            "photon_energy_erg": item["Eerg"],
            "A_s^-1": item["A"],
            "lower_population_fraction": item["lower_pop"],
            "upper_population_fraction": item["upper_pop"],
            "transparent_pop_A_E_erg_s^-1": item["transparent"],
            "transparent_pop_A_photon_s^-1": item["photon"],
            "current_component_fraction_transparent": current_frac[comp],
            "target_component_fraction": target_frac.get(comp),
            "component_target_over_current_fraction_scale": comp_scale,
            "i_only_scale_needed_if_f_r_fixed": i_only_scale if comp == "i" else "",
            "required_ans2_emission_rate_for_component_scale_s^-1": required_ans2,
            "required_ptmp_escape_multiplier_for_component_scale": required_ptmp,
            "escape_only_component_scale_feasible": escape_only_feasible,
            "ucalc_ans2_current_transparent_A_s^-1": item["A"],
            "ucalc_ans1_current_transparent_absorption_or_stimulated_s^-1": 0.0,
            "abund1_lower_current_population_proxy": item["lower_pop"],
            "abund2_upper_current_population_proxy": item["upper_pop"],
            "tau1_current_placeholder": 0.0,
            "tau2_current_placeholder": 0.0,
            "ptmp1_current_transparent": 1.0,
            "ptmp2_current_transparent": 1.0,
            "alpha_source_population_weighted_feed_s^-1": ctx.get("alpha_source_population_weighted_feed_s^-1", ""),
            "gamma_loss_rate_context_s^-1": ctx.get("gamma_loss_rate_context_s^-1", ""),
            "population_from_alpha_over_gamma_context": ctx.get("population_from_alpha_over_gamma_context", ""),
            "population_minus_alpha_over_gamma_context": (item["upper_pop"] - float(ctx.get("population_from_alpha_over_gamma_context")) if isinstance(ctx.get("population_from_alpha_over_gamma_context"), (int, float)) else ""),
            "gamma_offdiag_loss_rate_sum_s^-1": ctx.get("gamma_offdiag_loss_rate_sum_s^-1", ""),
            "gamma_diagonal_loss_rate_sum_s^-1": ctx.get("gamma_diagonal_loss_rate_sum_s^-1", ""),
            "n_alpha_feed_terms": ctx.get("n_alpha_feed_terms", ""),
            "n_gamma_loss_terms": ctx.get("n_gamma_loss_terms", ""),
            "n_diagonal_loss_terms": ctx.get("n_diagonal_loss_terms", ""),
            "dominant_alpha_component": ctx.get("dominant_alpha_component", ""),
            "dominant_alpha_record": ctx.get("dominant_alpha_record", ""),
            "dominant_gamma_component": ctx.get("dominant_gamma_component", ""),
            "dominant_gamma_record": ctx.get("dominant_gamma_record", ""),
            "alpha_by_component_json": ctx.get("alpha_by_component_json", "{}"),
            "gamma_by_component_json": ctx.get("gamma_by_component_json", "{}"),
            "missing_calc_emis_ion_context": "true ucalc ans1/ans2 with stimulated terms; tau0/tauc optical depths; pescl/pescv escape probabilities; cfrac geometry; xpx/xeltp abundance factors; nlbin/ncbin strong-line filtering",
            "diagnostic_note": "v0.3.65 context audit: reports available matrix-population context and required line-accounting multipliers; it does not alter the solve.",
        })

    for comp in ("f", "i", "r"):
        frac = current_frac[comp]
        tfrac = target_frac.get(comp)
        scale = required_scale.get(comp, "")
        rows.append({
            "audit_kind": "calc_emis_context_component_summary",
            "component": comp,
            "n_lines": int(component_sums[comp]["n"]),
            "transparent_pop_A_E_sum_erg_s^-1": component_sums[comp]["transparent"],
            "transparent_pop_A_photon_sum_s^-1": component_sums[comp]["photon"],
            "upper_population_fraction_sum_over_lines": component_sums[comp]["upper_pop"],
            "current_fraction_transparent": frac,
            "target_component_fraction": tfrac,
            "delta_current_minus_target": (frac - tfrac if tfrac is not None else ""),
            "target_over_current_fraction_scale": scale,
            "escape_only_scale_feasible": (isinstance(scale, (int, float)) and 0.0 <= float(scale) <= 1.0),
            "component_alpha_source_population_weighted_feed_sum_s^-1": component_sums[comp]["alpha"],
            "component_population_weighted_gamma_loss_sum_s^-1": component_sums[comp]["gamma_pop"],
            "alpha_over_population_weighted_gamma": (component_sums[comp]["alpha"] / component_sums[comp]["gamma_pop"] if component_sums[comp]["gamma_pop"] > 0.0 else ""),
            "diagnostic_note": "required scale is a line-output-accounting diagnostic, not a physical correction.",
        })

    rows.append({
        "audit_kind": "calc_emis_context_summary",
        "component": "summary",
        "f_fraction_transparent": current_frac["f"],
        "i_fraction_transparent": current_frac["i"],
        "r_fraction_transparent": current_frac["r"],
        "target_f_fraction": target_frac.get("f"),
        "target_i_fraction": target_frac.get("i"),
        "target_r_fraction": target_frac.get("r"),
        "f_target_over_current_scale": required_scale.get("f", ""),
        "i_target_over_current_scale": required_scale.get("i", ""),
        "r_target_over_current_scale": required_scale.get("r", ""),
        "i_only_scale_needed_if_f_r_fixed": i_only_scale,
        "R_transparent": (component_sums["f"]["transparent"] / component_sums["i"]["transparent"] if component_sums["i"]["transparent"] > 0.0 else ""),
        "G_transparent": ((component_sums["f"]["transparent"] + component_sums["i"]["transparent"]) / component_sums["r"]["transparent"] if component_sums["r"]["transparent"] > 0.0 else ""),
        "conclusion_scope": "If required scale exceeds unity, pure escape attenuation cannot raise that component in channel 1; a true ucalc/strong-line/context change or population-balance change is required.",
        "provenance": "v0.3.65_calc_emis_ion_runtime_context_audit",
    })
    return rows


def _calc_emis_context_audit_summary(rows: Sequence[dict]) -> dict:
    summary = next((r for r in rows if r.get("audit_kind") == "calc_emis_context_summary"), {})
    return {
        "n_calc_emis_context_audit_rows": len(rows),
        "n_calc_emis_context_line_rows": sum(1 for r in rows if r.get("audit_kind") == "calc_emis_context_line"),
        "f_fraction_transparent": summary.get("f_fraction_transparent", ""),
        "i_fraction_transparent": summary.get("i_fraction_transparent", ""),
        "r_fraction_transparent": summary.get("r_fraction_transparent", ""),
        "i_target_over_current_scale": summary.get("i_target_over_current_scale", ""),
        "i_only_scale_needed_if_f_r_fixed": summary.get("i_only_scale_needed_if_f_r_fixed", ""),
        "missing_context": "true calc_emis_ion ucalc net emissivity, optical-depth/escape channels, abundance factors, covering fraction, and strong-line filtering",
        "provenance": "v0.3.65_calc_emis_ion_runtime_context_audit",
    }


def _infer_xstar_data_type_from_term(term: Mapping[str, object]) -> Optional[int]:
    """Infer an ATDB/XSTAR data type from a full-global matrix term."""
    dt = maybe_int(term.get("data_type"))
    if dt is not None:
        return dt
    sm = str(term.get("source_method") or "")
    for token in sm.replace("-", "_").split("_"):
        if token.startswith("type"):
            val = maybe_int(token[4:])
            if val is not None:
                return val
    if sm.startswith("data_type_"):
        parts = sm.split("_")
        for i, part in enumerate(parts[:-1]):
            if part == "type":
                val = maybe_int(parts[i + 1])
                if val is not None:
                    return val
    return None


def _xstar_coupling_source_note(data_type: Optional[int], transition_kind: str, source_method: str) -> str:
    """Human-readable source-code expectation for triplet coupling records."""
    if data_type == 50 or transition_kind == "radiative_decay":
        return "type50 radiative A-value path: ucalc/calc_hmc_ion assemble one-way upper->lower gain plus upper diagonal loss"
    if data_type == 63 or "type63" in source_method:
        return "type63 same-n L-changing path: ucalc computes density-scaled ans1/ans2 with amcrs and statistical-weight partner rates"
    if data_type in {67, 68, 69}:
        return "He-like effective-collision-strength path: ucalc computes collisional excitation/de-excitation ans1/ans2 with detailed balance"
    return "generic full-global matrix term; inspect source_method/transition_kind"


def build_triplet_coupling_record_audit_rows(
    *,
    global_index_rows: Sequence[dict],
    full_global_matrix_terms: Sequence[dict],
    full_global_normalized_solve_comparison_rows: Sequence[dict],
    he_like_stage: int,
) -> List[dict]:
    """Audit direct 1s2s 3S1 <-> 1s2p 3P_J coupling records.

    Added in v0.3.62 after the v0.3.61 alpha/gamma audit showed that the
    intercombination upper levels have tiny steady-state populations because
    their dominant loss routes return to the forbidden upper level.  This audit
    validates the raw matrix terms against the XSTAR source-code roles: type-50
    radiative decays, type-63 same-n L-changing collisions, and He-like
    type-67/68/69 effective-collision-strength routes.
    """
    meta = _global_index_metadata(global_index_rows)
    pops = _full_global_population_map(full_global_normalized_solve_comparison_rows)
    triplet_sets = _triplet_global_index_sets(global_index_rows, ion_stage=he_like_stage)
    f_set = set(triplet_sets.get("f", []))
    i_set = set(triplet_sets.get("i", []))
    if not f_set or not i_set:
        return []

    selected_records: set[int] = set()
    for term in full_global_matrix_terms:
        row_gi = _row_global_index(term, "matrix_row_global_index", "row_global_index")
        col_gi = _row_global_index(term, "matrix_col_global_index", "col_global_index")
        rec = maybe_int(term.get("record"))
        if rec is None:
            continue
        if (row_gi in f_set and col_gi in i_set) or (row_gi in i_set and col_gi in f_set):
            selected_records.add(int(rec))

    rows: List[dict] = []
    detail_rows: List[dict] = []
    for term in full_global_matrix_terms:
        rec = maybe_int(term.get("record"))
        if rec is None or int(rec) not in selected_records:
            continue
        row_gi = _row_global_index(term, "matrix_row_global_index", "row_global_index")
        col_gi = _row_global_index(term, "matrix_col_global_index", "col_global_index")
        if row_gi not in (f_set | i_set) and col_gi not in (f_set | i_set):
            continue
        rate = maybe_float(term.get("full_global_rate_s^-1") or term.get("rate_s^-1") or term.get("rate_proxy") or term.get("source_rate_s^-1"))
        signed = maybe_float(term.get("full_global_signed_rate_s^-1") or term.get("signed_rate_s^-1") or term.get("signed_rate_proxy"))
        if rate is None and signed is not None:
            rate = abs(float(signed))
        if rate is None or not math.isfinite(float(rate)):
            continue
        rate = float(rate)
        dt = _infer_xstar_data_type_from_term(term)
        transition_kind = str(term.get("transition_kind") or "")
        source_method = str(term.get("source_method") or "")
        row_comp = "f" if row_gi in f_set else ("i" if row_gi in i_set else "other")
        col_comp = "f" if col_gi in f_set else ("i" if col_gi in i_set else "other")
        if row_comp == "i" and col_comp == "f" and row_gi != col_gi:
            coupling_role = "f_to_i_gain"
        elif row_comp == "f" and col_comp == "i" and row_gi != col_gi:
            coupling_role = "i_to_f_gain"
        elif row_comp == "i" and col_comp == "i" and row_gi == col_gi:
            coupling_role = "i_diagonal_loss"
        elif row_comp == "f" and col_comp == "f" and row_gi == col_gi:
            coupling_role = "f_diagonal_loss"
        else:
            coupling_role = "other_touching_f_or_i"
        src_pop = pops.get(int(col_gi), 0.0) if col_gi is not None else 0.0
        dst_pop = pops.get(int(row_gi), 0.0) if row_gi is not None else 0.0
        ne = maybe_float(term.get("electron_density_cm^-3"))
        rate_coeff = rate / float(ne) if ne and ne > 0.0 and ("collisional" in transition_kind or dt in {63, 67, 68, 69}) else ""
        expected = _xstar_coupling_source_note(dt, transition_kind, source_method)
        detail = {
            "audit_kind": "triplet_3S_3P_coupling_record_detail",
            "record": int(rec),
            "data_type_inferred": dt if dt is not None else "",
            "transition_kind": transition_kind,
            "source_method": source_method,
            "matrix_term_kind": term.get("matrix_term_kind", ""),
            "matrix_role": term.get("matrix_role", ""),
            "coupling_role": coupling_role,
            "row_global_index": row_gi if row_gi is not None else "",
            "row_component": row_comp,
            "row_level_index": meta.get(row_gi, {}).get("level_index", "") if row_gi is not None else "",
            "row_level_label": meta.get(row_gi, {}).get("level_label", "") if row_gi is not None else "",
            "col_global_index": col_gi if col_gi is not None else "",
            "col_component": col_comp,
            "col_level_index": meta.get(col_gi, {}).get("level_index", "") if col_gi is not None else "",
            "col_level_label": meta.get(col_gi, {}).get("level_label", "") if col_gi is not None else "",
            "rate_s^-1": rate,
            "signed_rate_s^-1": signed if signed is not None else "",
            "electron_density_cm^-3": ne if ne is not None else "",
            "rate_coefficient_cm3_s_if_density_scaled": rate_coeff,
            "source_population_fraction_col": src_pop,
            "destination_population_fraction_row": dst_pop,
            "source_population_weighted_rate_s^-1": src_pop * rate,
            "destination_population_weighted_rate_s^-1": dst_pop * rate,
            "xstar_ucalc_expected_role": expected,
            "validation_comment": "record selected because it directly couples 1s2s 3S1 and 1s2p 3P_J, or is its diagonal partner",
        }
        detail_rows.append(detail)
        rows.append(detail)

    # Summary rows by record.
    by_rec: Dict[int, List[dict]] = {}
    for row in detail_rows:
        by_rec.setdefault(int(row["record"]), []).append(row)
    for rec, rec_rows in sorted(by_rec.items()):
        f_to_i = sum(float(r["rate_s^-1"]) for r in rec_rows if r.get("coupling_role") == "f_to_i_gain")
        i_to_f = sum(float(r["rate_s^-1"]) for r in rec_rows if r.get("coupling_role") == "i_to_f_gain")
        f_diag = sum(float(r["rate_s^-1"]) for r in rec_rows if r.get("coupling_role") == "f_diagonal_loss")
        i_diag = sum(float(r["rate_s^-1"]) for r in rec_rows if r.get("coupling_role") == "i_diagonal_loss")
        f_to_i_weighted = sum(float(r["source_population_weighted_rate_s^-1"]) for r in rec_rows if r.get("coupling_role") == "f_to_i_gain")
        i_to_f_weighted = sum(float(r["source_population_weighted_rate_s^-1"]) for r in rec_rows if r.get("coupling_role") == "i_to_f_gain")
        dtypes = sorted({str(r.get("data_type_inferred")) for r in rec_rows if str(r.get("data_type_inferred"))})
        trans = sorted({str(r.get("transition_kind")) for r in rec_rows if str(r.get("transition_kind"))})
        source_methods = sorted({str(r.get("source_method")) for r in rec_rows if str(r.get("source_method"))})
        if "50" in dtypes or "radiative_decay" in trans:
            validation = "radiative_3P_to_3S_drain_present; compare whether XSTAR should include this A-value in the triplet model"
        elif any(dt in {"63", "67", "68", "69"} for dt in dtypes) or any("collisional" in t for t in trans):
            validation = "collisional_pair_present; check ans1/ans2 direction, density scaling, and detailed balance"
        else:
            validation = "generic_pair_present"
        rows.append({
            "audit_kind": "triplet_3S_3P_coupling_record_summary",
            "record": rec,
            "data_type_inferred_set": ";".join(dtypes),
            "transition_kind_set": ";".join(trans),
            "source_method_set": ";".join(source_methods),
            "n_matrix_terms_for_record": len(rec_rows),
            "f_to_i_gain_rate_sum_s^-1": f_to_i,
            "i_to_f_gain_rate_sum_s^-1": i_to_f,
            "f_diagonal_loss_rate_sum_s^-1": f_diag,
            "i_diagonal_loss_rate_sum_s^-1": i_diag,
            "f_to_i_source_population_weighted_feed_s^-1": f_to_i_weighted,
            "i_to_f_source_population_weighted_feed_s^-1": i_to_f_weighted,
            "i_to_f_over_f_to_i_rate_ratio": (i_to_f / f_to_i if f_to_i > 0.0 else ""),
            "i_to_f_over_f_to_i_population_weighted_ratio": (i_to_f_weighted / f_to_i_weighted if f_to_i_weighted > 0.0 else ""),
            "validation_comment": validation,
            "xstar_source_alignment_note": "Bautista/Kallman rate matrix includes radiative and electron/proton impact terms; XSTAR ucalc type50/type63/type67-69 should decide whether this coupling is radiative or collisional.",
        })

    # Compact global conclusion row.
    radiative_i_to_f = sum(float(r.get("rate_s^-1") or 0.0) for r in detail_rows if r.get("coupling_role") == "i_to_f_gain" and (r.get("data_type_inferred") == 50 or r.get("transition_kind") == "radiative_decay"))
    coll_f_to_i = sum(float(r.get("rate_s^-1") or 0.0) for r in detail_rows if r.get("coupling_role") == "f_to_i_gain" and (r.get("data_type_inferred") in {63, 67, 68, 69} or "collisional" in str(r.get("transition_kind"))))
    coll_i_to_f = sum(float(r.get("rate_s^-1") or 0.0) for r in detail_rows if r.get("coupling_role") == "i_to_f_gain" and (r.get("data_type_inferred") in {63, 67, 68, 69} or "collisional" in str(r.get("transition_kind"))))
    rows.append({
        "audit_kind": "triplet_3S_3P_coupling_audit_summary",
        "record": "summary",
        "n_selected_records": len(by_rec),
        "n_detail_rows": len(detail_rows),
        "radiative_i_to_f_gain_rate_sum_s^-1": radiative_i_to_f,
        "collisional_f_to_i_gain_rate_sum_s^-1": coll_f_to_i,
        "collisional_i_to_f_gain_rate_sum_s^-1": coll_i_to_f,
        "radiative_i_to_f_over_collisional_f_to_i_rate_ratio": (radiative_i_to_f / coll_f_to_i if coll_f_to_i > 0.0 else ""),
        "diagnostic_conclusion": "large radiative 3P_J->3S1 drain terms can suppress intercombination populations unless XSTAR line/level handling treats these routes differently or additional 3P_J feeds are missing",
    })
    return rows


def _triplet_coupling_record_audit_summary(rows: Sequence[dict]) -> dict:
    summary = next((r for r in rows if r.get("audit_kind") == "triplet_3S_3P_coupling_audit_summary"), {})
    rec_summaries = [r for r in rows if r.get("audit_kind") == "triplet_3S_3P_coupling_record_summary"]
    return {
        "n_triplet_coupling_audit_rows": len(rows),
        "n_triplet_coupling_records": len(rec_summaries),
        "radiative_i_to_f_gain_rate_sum_s^-1": summary.get("radiative_i_to_f_gain_rate_sum_s^-1", ""),
        "collisional_f_to_i_gain_rate_sum_s^-1": summary.get("collisional_f_to_i_gain_rate_sum_s^-1", ""),
        "collisional_i_to_f_gain_rate_sum_s^-1": summary.get("collisional_i_to_f_gain_rate_sum_s^-1", ""),
        "radiative_i_to_f_over_collisional_f_to_i_rate_ratio": summary.get("radiative_i_to_f_over_collisional_f_to_i_rate_ratio", ""),
        "provenance": "v0.3.62_triplet_3S_3P_coupling_record_audit",
    }

def _triplet_alpha_gamma_audit_summary(rows: Sequence[dict]) -> dict:
    comps = {r.get("component"): r for r in rows if r.get("audit_kind") == "triplet_alpha_gamma_component_summary"}
    return {
        "n_triplet_alpha_gamma_audit_rows": len(rows),
        "alpha_f_s^-1": comps.get("f", {}).get("alpha_source_population_weighted_feed_sum_s^-1", ""),
        "alpha_i_s^-1": comps.get("i", {}).get("alpha_source_population_weighted_feed_sum_s^-1", ""),
        "alpha_r_s^-1": comps.get("r", {}).get("alpha_source_population_weighted_feed_sum_s^-1", ""),
        "population_f": comps.get("f", {}).get("population_fraction_sum", ""),
        "population_i": comps.get("i", {}).get("population_fraction_sum", ""),
        "population_r": comps.get("r", {}).get("population_fraction_sum", ""),
        "provenance": "v0.3.61_triplet_alpha_gamma_source_aligned_audit",
    }


def _triplet_emissivity_branch_audit_summary(rows: Sequence[dict]) -> dict:
    comps = {r.get("component"): r for r in rows if r.get("audit_kind") == "triplet_emissivity_branch_component_summary"}
    summary = next((r for r in rows if r.get("audit_kind") == "triplet_emissivity_branch_summary"), {})
    return {
        "n_triplet_emissivity_branch_audit_rows": len(rows),
        "n_triplet_line_rows": sum(1 for r in rows if r.get("audit_kind") == "triplet_emissivity_branch_line"),
        "f_fraction": summary.get("f_fraction", comps.get("f", {}).get("component_fraction_from_simple_emissivity", "")),
        "i_fraction": summary.get("i_fraction", comps.get("i", {}).get("component_fraction_from_simple_emissivity", "")),
        "r_fraction": summary.get("r_fraction", comps.get("r", {}).get("component_fraction_from_simple_emissivity", "")),
        "missing_xstar_context": "calc_emis_ion net ucalc emissivity; pescl escape probabilities; cfrac; strong-line filtering",
        "provenance": "v0.3.61_triplet_emissivity_branch_audit",
    }

def _intercombination_feed_audit_summary(rows: Sequence[dict]) -> dict:
    def counts(col: str) -> dict:
        out = {}
        for r in rows:
            k = str(r.get(col) or "")
            out[k] = out.get(k, 0) + 1
        return out
    return {
        "n_intercombination_feed_audit_rows": len(rows),
        "route_role_counts": counts("route_role"),
        "component_counts": counts("full_global_component"),
        "transition_kind_counts": counts("transition_kind"),
        "incoming_feed_rate_sum_s^-1": sum(float(r.get("rate_s^-1") or 0.0) for r in rows if r.get("route_role") == "incoming_feed_to_intercombination_upper"),
        "outgoing_branch_rate_sum_s^-1": sum(float(r.get("rate_s^-1") or 0.0) for r in rows if r.get("route_role") == "outgoing_branch_or_coupling_from_intercombination_upper"),
        "diagonal_loss_rate_sum_s^-1": sum(float(r.get("rate_s^-1") or 0.0) for r in rows if r.get("route_role") == "diagonal_loss_on_intercombination_upper"),
        "provenance": "v0.3.60_intercombination_branch_audit",
    }


def _triplet_component_balance_audit_summary(rows: Sequence[dict]) -> dict:
    comps = {r.get("component"): r for r in rows if r.get("audit_kind") == "triplet_component_balance"}
    return {
        "n_triplet_component_balance_rows": len(rows),
        "population_sum_f": comps.get("f", {}).get("population_sum", ""),
        "population_sum_i": comps.get("i", {}).get("population_sum", ""),
        "population_sum_r": comps.get("r", {}).get("population_sum", ""),
        "incoming_rate_sum_f_s^-1": comps.get("f", {}).get("incoming_rate_sum_s^-1", ""),
        "incoming_rate_sum_i_s^-1": comps.get("i", {}).get("incoming_rate_sum_s^-1", ""),
        "incoming_rate_sum_r_s^-1": comps.get("r", {}).get("incoming_rate_sum_s^-1", ""),
        "radiative_out_rate_sum_f_s^-1": comps.get("f", {}).get("radiative_out_rate_sum_s^-1", ""),
        "radiative_out_rate_sum_i_s^-1": comps.get("i", {}).get("radiative_out_rate_sum_s^-1", ""),
        "radiative_out_rate_sum_r_s^-1": comps.get("r", {}).get("radiative_out_rate_sum_s^-1", ""),
        "provenance": "v0.3.60_triplet_component_balance_audit",
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


def _calc_ion_rates_istruc_audit_summary(rows: Sequence[dict]) -> dict:
    detail = [r for r in rows if str(r.get("row_kind")) == "calc_ion_rates_istruc_audit"]
    summary = next((r for r in rows if str(r.get("row_kind")) == "calc_ion_rates_istruc_summary"), {})
    by_family: Dict[str, float] = {}
    by_process: Dict[str, float] = {}
    flow: Dict[str, float] = {}
    for r in detail:
        rate = float(maybe_float(r.get("rate_s^-1")) or 0.0)
        fam = str(r.get("rate_family") or "")
        proc = str(r.get("ion_process") or "")
        a = r.get("from_ion_stage"); b = r.get("to_ion_stage")
        by_family[fam] = by_family.get(fam, 0.0) + rate
        by_process[proc] = by_process.get(proc, 0.0) + rate
        flow[f"{a}->{b}"] = flow.get(f"{a}->{b}", 0.0) + rate
    return {
        "n_calc_ion_rates_istruc_rows": len(rows),
        "n_detail_rows": len(detail),
        "status": summary.get("status", ""),
        "low_ion_stage": summary.get("low_ion_stage", ""),
        "high_ion_stage": summary.get("high_ion_stage", ""),
        "ionization_total_low_to_high_s^-1": summary.get("ionization_total_low_to_high_s^-1", ""),
        "recombination_total_high_to_low_s^-1": summary.get("recombination_total_high_to_low_s^-1", ""),
        "target_fraction_low_stage": summary.get("target_fraction_low_stage", ""),
        "target_fraction_high_stage": summary.get("target_fraction_high_stage", ""),
        "rate_family_sums": by_family,
        "ion_process_sums": by_process,
        "flow_sums": flow,
        "provenance": "v0.3.80_pre_matrix_calc_ion_rates_istruc_reconstruction",
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
    bremsa_context_rows = result.get("bremsa_context", [])
    type53_rate_audit_rows = result.get("type53_rate_audit", [])
    type53_flat_proxy_rate_audit_rows = result.get("type53_flat_proxy_rate_audit", [])
    global_type53_flat_proxy_matrix_terms = result.get("global_type53_flat_proxy_matrix_terms", [])
    type53_phint53_rate_audit_rows = result.get("type53_phint53_rate_audit", [])
    global_type53_phint53_matrix_terms = result.get("global_type53_phint53_matrix_terms", [])
    type53_milne_inverse_audit_rows = result.get("type53_milne_inverse_audit", [])
    global_type53_milne_matrix_terms = result.get("global_type53_milne_matrix_terms", [])
    type74_inverse_recombination_audit_rows = result.get("type74_inverse_recombination_audit", [])
    global_type74_inverse_matrix_terms = result.get("global_type74_inverse_matrix_terms", [])
    type74_calt74_rate_audit_rows = result.get("type74_calt74_rate_audit", [])
    global_type74_calt74_matrix_terms = result.get("global_type74_calt74_matrix_terms", [])
    calc_ion_rates_istruc_audit_rows = result.get("calc_ion_rates_istruc_audit", [])
    type53_type74_ucalc_closure_audit_rows = result.get("type53_type74_ucalc_closure_audit", [])
    phint53_milne_integral_audit_rows = result.get("phint53_milne_integral_audit", [])
    xstar_matrix_topology_audit_rows = result.get("xstar_matrix_topology_audit", [])
    inverse_recombination_scale_scan_rows = result.get("inverse_recombination_scale_scan", [])
    inverse_recombination_refined_scale_scan_rows = result.get("inverse_recombination_refined_scale_scan", [])
    radiation_normalization_audit_rows = result.get("radiation_normalization_audit", [])
    type53_phint53_scale_scan_rows = result.get("type53_phint53_scale_scan", [])
    full_global_matrix_terms = result.get("full_global_matrix_terms", [])
    full_global_normalized_solve_comparison_rows = result.get("full_global_normalized_solve_comparison", [])
    triplet_alpha_gamma_audit_rows = result.get("triplet_alpha_gamma_audit", [])
    triplet_emissivity_branch_audit_rows = result.get("triplet_emissivity_branch_audit", [])
    calc_emis_triplet_audit_rows = result.get("calc_emis_triplet_audit", [])
    calc_emis_context_audit_rows = result.get("calc_emis_context_audit", [])
    calc_emis_ion_triplet_emergent_rows = result.get("calc_emis_ion_triplet_emergent", [])
    type50_ucalc_rate_audit_rows = result.get("type50_ucalc_rate_audit", [])
    type50_escape_factor_scan_rows = result.get("type50_escape_factor_scan", [])
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
        if type53_phint53_rate_audit_rows:
            result["summary"]["type53_phint53_rate_audit_summary"] = _type53_phint53_rate_audit_summary(type53_phint53_rate_audit_rows)
        if global_type53_phint53_matrix_terms:
            result["summary"]["global_type53_phint53_matrix_terms_summary"] = _global_type53_phint53_matrix_terms_summary(global_type53_phint53_matrix_terms)
        if type53_milne_inverse_audit_rows:
            result["summary"]["type53_milne_inverse_audit_summary"] = _type53_milne_inverse_audit_summary(type53_milne_inverse_audit_rows)
        if global_type53_milne_matrix_terms:
            result["summary"]["global_type53_milne_matrix_terms_summary"] = _global_type53_milne_matrix_terms_summary(global_type53_milne_matrix_terms)
        if type74_inverse_recombination_audit_rows:
            result["summary"]["type74_inverse_recombination_audit_summary"] = _type74_inverse_recombination_audit_summary(type74_inverse_recombination_audit_rows)
        if global_type74_inverse_matrix_terms:
            result["summary"]["global_type74_inverse_matrix_terms_summary"] = _global_type74_inverse_matrix_terms_summary(global_type74_inverse_matrix_terms)
        if type74_calt74_rate_audit_rows:
            result["summary"]["type74_calt74_rate_audit_summary"] = _type74_calt74_rate_audit_summary(type74_calt74_rate_audit_rows)
        if global_type74_calt74_matrix_terms:
            result["summary"]["global_type74_calt74_matrix_terms_summary"] = _global_type74_calt74_matrix_terms_summary(global_type74_calt74_matrix_terms)
        if calc_ion_rates_istruc_audit_rows:
            result["summary"]["calc_ion_rates_istruc_audit_summary"] = _calc_ion_rates_istruc_audit_summary(calc_ion_rates_istruc_audit_rows)
        if type53_type74_ucalc_closure_audit_rows:
            result["summary"]["type53_type74_ucalc_closure_audit_summary"] = _type53_type74_ucalc_closure_audit_summary(type53_type74_ucalc_closure_audit_rows)
        if phint53_milne_integral_audit_rows:
            result["summary"]["phint53_milne_integral_audit_summary"] = _phint53_milne_integral_audit_summary(phint53_milne_integral_audit_rows)
        if xstar_matrix_topology_audit_rows:
            result["summary"]["xstar_matrix_topology_audit_summary"] = _xstar_matrix_topology_audit_summary(xstar_matrix_topology_audit_rows)
        if inverse_recombination_scale_scan_rows:
            result["summary"]["inverse_recombination_scale_scan_summary"] = _inverse_recombination_scale_scan_summary(inverse_recombination_scale_scan_rows)
        if bremsa_context_rows:
            result["summary"]["bremsa_context_summary"] = _bremsa_context_summary(bremsa_context_rows)
        if radiation_normalization_audit_rows:
            result["summary"]["radiation_normalization_audit_summary"] = _radiation_normalization_audit_summary(radiation_normalization_audit_rows)
        if type53_phint53_scale_scan_rows:
            result["summary"]["type53_phint53_scale_scan_summary"] = _type53_phint53_scale_scan_summary(type53_phint53_scale_scan_rows)
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
        if triplet_alpha_gamma_audit_rows:
            result["summary"]["triplet_alpha_gamma_audit_summary"] = _triplet_alpha_gamma_audit_summary(triplet_alpha_gamma_audit_rows)
        if triplet_emissivity_branch_audit_rows:
            result["summary"]["triplet_emissivity_branch_audit_summary"] = _triplet_emissivity_branch_audit_summary(triplet_emissivity_branch_audit_rows)
        if calc_emis_triplet_audit_rows:
            result["summary"]["calc_emis_triplet_audit_summary"] = _calc_emis_triplet_audit_summary(calc_emis_triplet_audit_rows)
        if calc_emis_context_audit_rows:
            result["summary"]["calc_emis_context_audit_summary"] = _calc_emis_context_audit_summary(calc_emis_context_audit_rows)
        if calc_emis_ion_triplet_emergent_rows:
            result["summary"]["calc_emis_ion_triplet_emergent_summary"] = _calc_emis_ion_triplet_emergent_summary(calc_emis_ion_triplet_emergent_rows)
        if global_superlevel_cascade_matrix_terms:
            result["summary"]["global_superlevel_cascade_matrix_terms_summary"] = _global_superlevel_cascade_matrix_terms_summary(global_superlevel_cascade_matrix_terms)
        if global_superlevel_source_matrix_terms:
            result["summary"]["global_superlevel_source_matrix_terms_summary"] = _global_superlevel_source_matrix_terms_summary(global_superlevel_source_matrix_terms)
    write_csv(out / "xstar_like_element_solver_ion_blocks.csv", result.get("ion_blocks", []))
    write_csv(out / "xstar_like_element_solver_global_index.csv", result.get("global_index", []))
    write_csv(out / "xstar_like_element_solver_xstar_matrix_topology_audit.csv", xstar_matrix_topology_audit_rows)
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
    write_csv(out / "xstar_like_element_solver_type50_ucalc_rate_audit.csv", type50_ucalc_rate_audit_rows)
    write_csv(out / "xstar_like_element_solver_type50_escape_factor_scan.csv", type50_escape_factor_scan_rows)
    write_csv(out / "xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv", global_superlevel_cascade_matrix_terms)
    write_csv(out / "xstar_like_element_solver_global_superlevel_source_matrix_terms.csv", global_superlevel_source_matrix_terms)
    write_csv(out / "xstar_like_element_solver_global_bound_bound_solve_comparison.csv", global_bound_bound_solve_comparison_rows)
    write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv", global_bound_bound_type71_solve_comparison_rows)
    write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_type99_proxy_solve_comparison.csv", global_bound_bound_type71_type99_proxy_solve_comparison_rows)
    write_csv(out / "xstar_like_element_solver_global_bound_bound_type71_type99_type53_proxy_solve_comparison.csv", global_bound_bound_type71_type99_type53_proxy_solve_comparison_rows)
    write_csv(out / "xstar_like_element_solver_type99_proxy_scale_scan.csv", type99_proxy_scale_scan_rows)
    write_csv(out / "xstar_like_element_solver_radiation_context.csv", radiation_context_rows)
    write_csv(out / "xstar_like_element_solver_bremsa_context.csv", bremsa_context_rows)
    write_csv(out / "xstar_like_element_solver_type53_rate_audit.csv", type53_rate_audit_rows)
    write_csv(out / "xstar_like_element_solver_type53_flat_proxy_rate_audit.csv", type53_flat_proxy_rate_audit_rows)
    write_csv(out / "xstar_like_element_solver_global_type53_flat_proxy_matrix_terms.csv", global_type53_flat_proxy_matrix_terms)
    write_csv(out / "xstar_like_element_solver_type53_phint53_rate_audit.csv", type53_phint53_rate_audit_rows)
    write_csv(out / "xstar_like_element_solver_global_type53_phint53_matrix_terms.csv", global_type53_phint53_matrix_terms)
    write_csv(out / "xstar_like_element_solver_type53_milne_inverse_audit.csv", type53_milne_inverse_audit_rows)
    write_csv(out / "xstar_like_element_solver_global_type53_milne_matrix_terms.csv", global_type53_milne_matrix_terms)
    write_csv(out / "xstar_like_element_solver_type74_inverse_recombination_audit.csv", type74_inverse_recombination_audit_rows)
    write_csv(out / "xstar_like_element_solver_global_type74_inverse_matrix_terms.csv", global_type74_inverse_matrix_terms)
    write_csv(out / "xstar_like_element_solver_type74_calt74_rate_audit.csv", type74_calt74_rate_audit_rows)
    write_csv(out / "xstar_like_element_solver_global_type74_calt74_matrix_terms.csv", global_type74_calt74_matrix_terms)
    write_csv(out / "xstar_like_element_solver_calc_ion_rates_istruc_audit.csv", calc_ion_rates_istruc_audit_rows)
    write_csv(out / "xstar_like_element_solver_type53_type74_ucalc_closure_audit.csv", type53_type74_ucalc_closure_audit_rows)
    write_csv(out / "xstar_like_element_solver_phint53_milne_integral_audit.csv", phint53_milne_integral_audit_rows)
    write_csv(out / "xstar_like_element_solver_inverse_recombination_scale_scan.csv", inverse_recombination_scale_scan_rows)
    write_csv(out / "xstar_like_element_solver_inverse_recombination_refined_scale_scan.csv", inverse_recombination_refined_scale_scan_rows)
    write_csv(out / "xstar_like_element_solver_intercombination_feed_audit.csv", result.get("intercombination_feed_audit", []))
    write_csv(out / "xstar_like_element_solver_triplet_component_balance_audit.csv", result.get("triplet_component_balance_audit", []))
    write_csv(out / "xstar_like_element_solver_triplet_alpha_gamma_audit.csv", triplet_alpha_gamma_audit_rows)
    write_csv(out / "xstar_like_element_solver_triplet_emissivity_branch_audit.csv", triplet_emissivity_branch_audit_rows)
    write_csv(out / "xstar_like_element_solver_calc_emis_triplet_audit.csv", calc_emis_triplet_audit_rows)
    write_csv(out / "xstar_like_element_solver_calc_emis_context_audit.csv", calc_emis_context_audit_rows)
    write_csv(out / "xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv", calc_emis_ion_triplet_emergent_rows)
    write_csv(out / "xstar_like_element_solver_triplet_coupling_record_audit.csv", result.get("triplet_coupling_record_audit", []))
    write_csv(out / "xstar_like_element_solver_triplet_coupling_suppression_comparison.csv", result.get("triplet_coupling_suppression_comparison", []))
    write_csv(out / "xstar_like_element_solver_radiation_normalization_audit.csv", radiation_normalization_audit_rows)
    write_csv(out / "xstar_like_element_solver_type53_phint53_scale_scan.csv", type53_phint53_scale_scan_rows)
    write_csv(out / "xstar_like_element_solver_full_global_matrix_terms.csv", full_global_matrix_terms)
    write_csv(out / "xstar_like_element_solver_full_global_normalized_solve_comparison.csv", full_global_normalized_solve_comparison_rows)
    write_csv(out / "xstar_like_element_solver_triplet.csv", result.get("triplet_rows", []))
    (out / "xstar_like_element_solver_summary.json").write_text(json.dumps(result.get("summary", {}), indent=2), encoding="utf-8")
    lines = ["# XSTAR-like element-solver summary", "", "This is a pure-Python reference/scaffold run.", ""]
    summ = result.get("summary", {})
    for key in sorted(summ):
        lines.append(f"- **{key}**: `{summ[key]}`")
    lines.append("")
    lines.append("Adjacent-ion coupling records are catalogued with ucalc-style branch annotations; evaluable recombination records may also be assembled as prototype source terms when adjacent_coupling_mode requests it. Type-57 records are evaluated diagnostically through the ported calt57 path but are not assembled by default. Type-59 inverse recombination/photoionization records are audited for the XSTAR excited-level recombination suppression gate and are not assembled. Photoionization/DR/superlevel records are audited but not blindly treated as rates without XSTAR radiation-field context. Type-71/type-77 superlevel branching fractions, type-70/74/99 source × branch proxies, the v0.3.26 deep type-74 linkage audit, the v0.3.27 direct type-74 triplet-source diagnostic, and the v0.3.28 optional type-74 direct source-injection before/after solve, and v0.3.29 type-74 direct source scale scan; v0.3.30 fixes the scale-scan target helper, and v0.3.31 writes an explicit global element state index, v0.3.32 fixes superlevel/continuum classification, and v0.3.33 writes a diagnostic global bound-bound matrix-term scaffold from the current per-ion radiative/collisional transition logs; v0.3.34 solves the He-like intra-ion global-index bound-bound block as an equivalence test against the current per-ion solve; v0.3.35 maps type-71 superlevel cascade terms onto global-index matrix triplets; v0.3.36 solves an extended He-like global block including bound-bound plus type-71 cascade terms as a diagnostic scaffold; v0.3.37 fixes the output handoff so the bound-bound+type71 solve-comparison rows are written to CSV; v0.3.38 maps diagnostic type-99 superlevel source candidates onto global-index source/matrix proxy rows; v0.3.39 solves a diagnostic bound-bound+type71 block with nonphysical type-99 proxy source-vector rows; v0.3.40 adds a type-99 proxy scale scan and writes xstar_like_element_solver_type99_proxy_scale_scan.csv; v0.3.41/v0.3.42 fix the CLI-to-solver handoff for the type-99 proxy scale option; v0.3.43 adds a type-53 radiation-context scaffold and xstar_like_element_solver_type53_rate_audit.csv without evaluating phint53/Milne physical rates; v0.3.45 adds a diagnostic flat-field type-53 photoionization-rate proxy and global matrix topology rows without assembling them; v0.3.46 solves a diagnostic bound-bound+type71+type99-proxy block with type-53 flat photoionization proxy sinks; v0.3.47 writes xstar_like_element_solver_full_global_matrix_terms.csv by combining C VI/C V bound-bound blocks, C V type-71 cascades, type-99 parent-continuum-to-superlevel proxy topology, type-53 flat photoionization proxy topology, and mappable type-1 recombination source/topology rows; v0.3.48 adds xstar_like_element_solver_full_global_normalized_solve_comparison.csv, the first diagnostic normalized full-global proxy-topology solve over all global_index rows with source-vector rows excluded; v0.3.50/v0.3.51 add an XSTAR-Lucy/LU diagnostic solver path; v0.3.52/v0.3.53 add the first type-53 phint53 forward-kernel diagnostic; v0.3.54 adds xstar_like_element_solver_radiation_normalization_audit.csv and xstar_like_element_solver_type53_phint53_scale_scan.csv for placeholder-radiation normalization/scale testing; v0.3.55 adds inverse-recombination-mode scaffolds for type-53 Milne and type-74 DR-delta inverse topology with xstar_like_element_solver_type53_milne_inverse_audit.csv, xstar_like_element_solver_global_type53_milne_matrix_terms.csv, xstar_like_element_solver_type74_inverse_recombination_audit.csv, xstar_like_element_solver_global_type74_inverse_matrix_terms.csv, and xstar_like_element_solver_inverse_recombination_scale_scan.csv; v0.3.56 extends that scan with independent --type53-milne-scale and --type74-inverse-scale controls informed by the XSTAR phint53/milne and calt74 branches; v0.3.59 adds a refined inverse-recombination scan around the good C V region with intercombination-sensitive ranking metrics in xstar_like_element_solver_inverse_recombination_refined_scale_scan.csv; diagnostic source audits remain nonphysical and the normalized solve is not yet a physical XSTAR element solution.")
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
