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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

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
        if data_type in {53, 59}:
            if len(vals) >= 2:
                out["idest1_guess"] = vals[-2]
            if len(vals) >= 3 and nlevp is not None:
                out["idest2_guess"] = int(nlevp) + vals[-3] - 1
            if len(vals) >= 1:
                out["idest3_guess"] = vals[-1]
                out["idest4_guess"] = vals[-1] + 1
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
            "requires_context": "calt57_effective_charge_formula_level_energies_degeneracies_parent_continuum",
            "matrix_role_if_implemented": "electron_impact_ionization_sink_and_inverse_three_body_recombination",
            "python_eval_status": "not_evaluated_calt57_not_yet_ported",
        })
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
        )

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
    block_summary["adjacent_parent_stage"] = adjacent_parent_stage
    block_summary["n_adjacent_coupling_rows"] = len(coupling_rows)
    block_summary["n_adjacent_coupling_assembled"] = sum(1 for r in coupling_rows if r.get("assembled"))
    block_summary["adjacent_source_sum_s^-1"] = float(np.sum(source_vector)) if len(source_vector) else 0.0
    block_summary["adjacent_sink_sum_s^-1"] = float(np.sum(sink_rates)) if len(sink_rates) else 0.0
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
) -> dict:
    z = choose_z(str(element)) if not isinstance(element, int) else int(element)
    if z is None:
        raise ValueError(f"Could not parse element {element!r}")
    stages = list(adjacent_stages) if adjacent_stages else [he_like_stage + 1, he_like_stage]
    stages = sorted({int(s) for s in stages if int(s) > 0}, reverse=True)
    with ATDB(fitsfile, load_reals=False, prompt_for_data=False) as db:
        ion_blocks: List[dict] = []
        populations: List[dict] = []
        line_rows: List[dict] = []
        transitions: List[dict] = []
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
        if he_like_stage + 1 in stages:
            coupling.append(asdict(catalog_adjacent_coupling_candidates(
                db,
                z=z,
                lower_ion_stage=he_like_stage,
                upper_ion_stage=he_like_stage + 1,
                use_cache=index_cache,
                cache_path=index_cache_path,
            )))
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
            "adjacent_coupling_status": adjacent_coupling_mode,
            "n_adjacent_coupling_terms": len(assembled_coupling_terms),
            "n_adjacent_coupling_assembled": sum(1 for r in assembled_coupling_terms if r.get("assembled")),
            "he_like_triplet": _normalise_triplet(selected_lines),
        },
        "ion_blocks": ion_blocks,
        "coupling_candidates": coupling,
        "populations": populations,
        "line_rows": line_rows,
        "transition_rows": transitions,
        "triplet_rows": triplet_rows,
        "adjacent_coupling_terms": assembled_coupling_terms,
    }


def write_element_solver_outputs(result: dict, out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "xstar_like_element_solver_ion_blocks.csv", result.get("ion_blocks", []))
    write_csv(out / "xstar_like_element_solver_coupling_candidates.csv", result.get("coupling_candidates", []))
    write_csv(out / "xstar_like_element_solver_adjacent_coupling_terms.csv", result.get("adjacent_coupling_terms", []))
    write_csv(out / "xstar_like_element_solver_ucalc_adjacent_audit.csv", result.get("adjacent_coupling_terms", []))
    write_csv(out / "xstar_like_element_solver_populations.csv", result.get("populations", []))
    write_csv(out / "xstar_like_element_solver_lines.csv", result.get("line_rows", []))
    write_csv(out / "xstar_like_element_solver_transitions.csv", result.get("transition_rows", []))
    write_csv(out / "xstar_like_element_solver_triplet.csv", result.get("triplet_rows", []))
    (out / "xstar_like_element_solver_summary.json").write_text(json.dumps(result.get("summary", {}), indent=2), encoding="utf-8")
    lines = ["# XSTAR-like element-solver summary", "", "This is a pure-Python reference/scaffold run.", ""]
    summ = result.get("summary", {})
    for key in sorted(summ):
        lines.append(f"- **{key}**: `{summ[key]}`")
    lines.append("")
    lines.append("Adjacent-ion coupling records are catalogued with ucalc-style branch annotations; evaluable recombination records may also be assembled as prototype source terms when adjacent_coupling_mode requests it. Photoionization/DR/superlevel records are audited but not blindly treated as rates without XSTAR radiation-field context.")
    (out / "xstar_like_element_solver_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
