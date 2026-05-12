"""Readers that populate Python live-state objects from XSTAR detail outputs.

This module is a bridge between the current XSTAR-output audit workflow and a
future full Python/C++ XSTAR reimplementation.  It does not solve the XSTAR
plasma problem from first principles.  Instead, it reads the per-zone detail
products that XSTAR can write with ``lwrite=1``/``lprint=1`` and maps them into
:class:`xstar_atomic.xstar_state.XSTARRunState`.

The mapping is intentionally source-code oriented:

* ``xo01_detal4.fits`` -> ``epi(:)``, continuum depths/opacity/emissivity, and
  reconstructed ``bremsa(:)``/``bremsint(:)`` using the same geometric form used
  by XSTAR's transfer path;
* ``xo01_detal2.fits`` -> ``tau0(1:2,line)`` plus line opacity/emissivity;
* ``xo01_detail.fits`` -> explicit level populations;
* ``xout_abund1.fits`` -> zone-local temperature, electron density, ionization
  parameter, and ion fractions;
* ``PARAMETERS`` tables / ``run_xstar.sh`` -> ``cfrac`` and ``vturbi``.

These readers are useful for exact row-by-row audits.  The reconstructed
``bremsa`` is an output-state reconstruction from detail products, not yet a
replacement for XSTAR's live in-memory transfer arrays during iteration.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .xstar_outputs import read_fits_table_hdus, read_xout_abundances, read_xout_parameters
from .xstar_run import parse_xstar_command_file
from .xstar_state import XSTARContinuumState, XSTARLineTransferState, XSTARRunState, XSTARZoneState

_BASIC_ABUNDANCE_COLUMNS = {
    "radius",
    "delta_r",
    "ion_parameter",
    "x_e",
    "n_p",
    "pressure",
    "temperature",
    "frac_heat_error",
}


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        val = float(value)
        if not math.isfinite(val):
            return default
        return val
    except Exception:
        return default


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def _parameter_map_from_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for row in rows:
        key = _as_str(row.get("parameter") or row.get("name")).lower()
        if not key:
            continue
        out[key] = row.get("value")
    return out


def read_xstar_parameters_from_run_dir(run_dir: str | Path) -> Dict[str, Any]:
    """Read XSTAR scalar parameters from a run directory.

    ``PARAMETERS`` tables are preferred because they are written by XSTAR.  If no
    FITS parameter table is available, ``run_xstar.sh`` is parsed as a fallback.
    """
    root = Path(run_dir)
    for name in ("xout_abund1.fits", "xout_lines1.fits", "xo01_detail.fits", "xo01_detal4.fits"):
        path = root / name
        if path.exists():
            rows = read_xout_parameters(path)
            pmap = _parameter_map_from_rows(rows)
            if pmap:
                return pmap
    command_file = root / "run_xstar.sh"
    if command_file.exists():
        params = parse_xstar_command_file(command_file)
        return params.as_dict()
    return {}


def _abundance_temperature_K(row: Mapping[str, Any]) -> Optional[float]:
    """Return temperature in K from XSTAR ABUNDANCES row.

    XSTAR's ``xout_abund1`` table reports ``temperature`` in units of 10^4 K.
    """
    temp = _as_float(row.get("temperature"))
    return temp * 1.0e4 if temp is not None else None


def _abundance_electron_density(row: Mapping[str, Any]) -> Optional[float]:
    xe = _as_float(row.get("x_e"))
    np_ = _as_float(row.get("n_p"))
    if xe is not None and np_ is not None:
        return xe * np_
    return xe if xe is not None else np_


def _ion_fractions_from_abundance_row(row: Mapping[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key, value in row.items():
        key_s = str(key).strip().lower()
        if key_s in _BASIC_ABUNDANCE_COLUMNS:
            continue
        val = _as_float(value)
        if val is not None:
            out[key_s] = val
    return out


def _is_zero_abundance_sentinel(row: Mapping[str, Any]) -> bool:
    """Return True for the all-zero sentinel row written by some XSTAR outputs.

    XSTAR detail files can contain one additional final radial HDU whose line and
    continuum arrays are meaningful final/cumulative output-state products, while
    ``xout_abund1.fits`` can contain a trailing all-zero ABUNDANCES row.  Treating
    that row as a real physical zone makes the Python state report
    ``T=ne=logxi=0`` even though the associated detail HDU still has populated
    arrays.  For such sentinel rows, the reader carries forward the most recent
    valid local plasma state.
    """
    if not row:
        return False
    scalar_keys = [
        "radius",
        "delta_r",
        "ion_parameter",
        "x_e",
        "n_p",
        "pressure",
        "temperature",
    ]
    scalar_sum = sum(abs(float(_as_float(row.get(key), 0.0) or 0.0)) for key in scalar_keys)
    if scalar_sum > 0.0:
        return False
    ion_sum = 0.0
    for key, value in row.items():
        key_s = str(key).strip().lower()
        if key_s in _BASIC_ABUNDANCE_COLUMNS:
            continue
        ion_sum += abs(float(_as_float(value, 0.0) or 0.0))
        if ion_sum > 0.0:
            return False
    return True


def _zrems_total(row: Mapping[str, Any]) -> float:
    total = 0.0
    for idx in range(1, 6):
        val = _as_float(row.get(f"zrems({idx})"), 0.0) or 0.0
        total += val
    return total


def reconstruct_bremsa_from_detal4_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    radius_cm: Optional[float],
    attenuation_column: str = "fwd_dpth",
) -> List[float]:
    """Reconstruct an output-state ``bremsa(:)`` proxy from ``xo01_detal4`` rows.

    The reconstruction follows the geometric factor in XSTAR's transfer path:

    ``bremsa(j) = zrems_total(j) * exp(-dpthc(1,j)) / (12.56 * (r/1e19)^2)``.

    The returned array is an audit reconstruction from detail-output rows.  It
    should not be confused with the exact live in-memory ``bremsa`` used during
    all iterations unless the corresponding detail dump was written at the same
    point in the source-code path.
    """
    r = float(radius_cm or 0.0)
    denom = 12.56 * (r / 1.0e19) ** 2 if r > 0 else None
    out: List[float] = []
    for row in rows:
        z = _zrems_total(row)
        depth = _as_float(row.get(attenuation_column), 0.0) or 0.0
        if denom is None or denom <= 0.0:
            out.append(0.0)
        else:
            out.append(float(z * math.exp(-max(depth, 0.0)) / denom))
    return out


def reconstruct_bremsint(epi: Sequence[float], bremsa: Sequence[float]) -> List[float]:
    """Return a cumulative trapezoidal integral of ``bremsa`` over ``epi``."""
    n = min(len(epi), len(bremsa))
    if n <= 0:
        return []
    out = [0.0]
    acc = 0.0
    for i in range(1, n):
        dx = float(epi[i]) - float(epi[i - 1])
        acc += 0.5 * (float(bremsa[i]) + float(bremsa[i - 1])) * dx
        out.append(float(acc))
    return out


def _xstar_pescl(tau: Any) -> float:
    """Port the scalar XSTAR ``pescl.f90`` escape probability used for audits."""
    tau_f = max(float(_as_float(tau, 0.0) or 0.0), 0.0)
    pi = 3.1415927
    tauw = 1.0e5
    if tau_f < 1.0:
        if tau_f < 1.0e-5:
            val = 1.0
        else:
            aa = 2.0 * tau_f
            val = (1.0 - math.exp(-aa)) / aa
    else:
        bb = 0.5 * math.sqrt(max(0.0, math.log(tau_f))) / (1.0 + tau_f / tauw)
        val = 1.0 / (tau_f * math.sqrt(pi) * (1.2 + bb))
    return float(val / 2.0)


def _ptmp_from_tau(tau_in: Any, tau_out: Any, cfrac: Any) -> tuple[float, float]:
    c = max(0.0, min(1.0, float(_as_float(cfrac, 0.0) or 0.0)))
    t1 = float(_as_float(tau_in, 0.0) or 0.0)
    t2 = float(_as_float(tau_out, 0.0) or 0.0)
    ptmp1 = _xstar_pescl(t1) * (1.0 - c)
    ptmp2 = _xstar_pescl(t2) * (1.0 - c) + 2.0 * _xstar_pescl(t1 + t2) * c
    return float(ptmp1), float(ptmp2)


def pescl_xstar(tau: Any) -> float:
    """Public scalar port of XSTAR ``pescl.f90`` for line-rate audits."""
    return _xstar_pescl(tau)


def ptmp_from_tau_xstar(tau_in: Any, tau_out: Any, cfrac: Any) -> tuple[float, float]:
    """Return XSTAR ``ptmp1, ptmp2`` from ``calc_hmc_ion.f90``.

    XSTAR forms the directional line escape terms as::

        ptmp1 = pescl(tau_in) * (1 - cfrac)
        ptmp2 = pescl(tau_out) * (1 - cfrac)
              + 2 * pescl(tau_in + tau_out) * cfrac

    The pair is passed to ``ucalc.f90`` type 50.
    """
    return _ptmp_from_tau(tau_in, tau_out, cfrac)


def xstar_nbinc_index(energy_eV: float, epi_grid: Sequence[float]) -> tuple[Optional[int], Optional[int]]:
    """Return ``(python_index, fortran_nb1)`` using the XSTAR ``nbinc`` convention."""
    if not epi_grid:
        return None, None
    e = float(energy_eV)
    n = len(epi_grid)
    n_guard = max(2, n // 50)
    n_search = max(1, n - n_guard)
    if e <= float(epi_grid[0]):
        return 0, 1
    best = 0
    for i in range(0, n_search - 1):
        if float(epi_grid[i]) <= e < float(epi_grid[i + 1]):
            return i, i + 1
        if float(epi_grid[i]) <= e:
            best = i
    best = min(best, n - 1)
    return best, best + 1


_ATOMIC_MASS_FOR_SYMBOL = {
    "H": 1.0, "HE": 4.0, "LI": 7.0, "BE": 9.0, "B": 11.0,
    "C": 12.0, "N": 14.0, "O": 16.0, "NE": 20.0, "NA": 23.0,
    "MG": 24.0, "AL": 27.0, "SI": 28.0, "P": 31.0, "S": 32.0,
    "CL": 35.5, "AR": 40.0, "K": 39.0, "CA": 40.0, "FE": 56.0,
}


def atomic_mass_number_from_ion(ion: str | None) -> float:
    """Return the approximate mass number used by XSTAR type-50 velocity audits."""
    if not ion:
        return 1.0
    token = str(ion).replace("_", " ").replace("-", " ").strip().split()[0].upper()
    return float(_ATOMIC_MASS_FOR_SYMBOL.get(token, 1.0))


def type50_vtherm_xstar(*, temperature_K: Optional[float], vturb_km_s: Any, atomic_mass_number: float) -> Optional[float]:
    """Port XSTAR's type-50 thermal+turbulent velocity width.

    ``ucalc.f90`` receives temperature in units of ``1e4 K`` and evaluates the
    same thermal+turbulent quadrature used by the Python full-global solver.
    """
    temp = _as_float(temperature_K)
    if temp is None or temp <= 0.0:
        return None
    vturb = _as_float(vturb_km_s, 0.0) or 0.0
    t_1e4 = max(float(temp) / 1.0e4, 1.0e-300)
    a = max(float(atomic_mass_number), 1.0e-300)
    return float(((float(vturb) * 1.0e5) ** 2 + (1.29e6 / math.sqrt(a / t_1e4)) ** 2) ** 0.5)


def oscillator_strength_from_A_xstar(*, A_s_inv: Any, wavelength_A: Any, g_upper: Any = None, g_lower: Any = None) -> Optional[float]:
    """Reconstruct XSTAR ``flin`` from A-value, wavelength, and level weights.

    This mirrors the relation already used by the full-global solver:
    ``flin = 1e-16 * A * g_upper * lambda_A^2 / (0.667274 * g_lower)``.
    """
    A = _as_float(A_s_inv)
    w = _as_float(wavelength_A)
    gu = _as_float(g_upper)
    gl = _as_float(g_lower)
    if A is None or w is None or A <= 0.0 or w <= 0.0:
        return None
    if gu is None or gu <= 0.0 or gl is None or gl <= 0.0:
        return None
    return float(1.0e-16 * A * gu * w * w / (0.667274 * gl))


def _zone_hdus(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    return read_fits_table_hdus(path, "XSTAR_RADIAL")


def read_xstar_detail_run_state(
    run_dir: str | Path,
    *,
    command_file: str | Path | None = None,
    include_level_populations: bool = True,
    include_line_transfer: bool = True,
    include_continuum: bool = True,
) -> XSTARRunState:
    """Populate :class:`XSTARRunState` from XSTAR detail/output FITS files.

    This is an audit-state reader.  It uses XSTAR's own detail products to fill
    the Python live-state schema so that future solver and FITS-writer work can
    compare row-by-row against XSTAR.
    """
    root = Path(run_dir)
    params = read_xstar_parameters_from_run_dir(root)
    if command_file is not None and not params:
        params = parse_xstar_command_file(command_file).as_dict()
    elif not params and (root / "run_xstar.sh").exists():
        params = parse_xstar_command_file(root / "run_xstar.sh").as_dict()
    params = {str(k).strip().lower(): v for k, v in params.items()}

    abund = read_xout_abundances(root / "xout_abund1.fits") if (root / "xout_abund1.fits").exists() else {}
    abund_rows = abund.get("abundances", [])
    n_zones = len(abund_rows)
    detail_hdus = _zone_hdus(root / "xo01_detail.fits") if include_level_populations else []
    line_hdus = _zone_hdus(root / "xo01_detal2.fits") if include_line_transfer else []
    cont_hdus = _zone_hdus(root / "xo01_detal4.fits") if include_continuum else []
    n_zones = max(n_zones, len(detail_hdus), len(line_hdus), len(cont_hdus), 1)

    cfrac = _as_float(params.get("cfrac"))
    vturbi = _as_float(params.get("vturbi"))
    zones: List[XSTARZoneState] = []
    last_valid_arow: Mapping[str, Any] = {}
    last_valid_index: Optional[int] = None
    for zi in range(n_zones):
        raw_arow = abund_rows[zi] if zi < len(abund_rows) else {}
        used_carried_abundance = False
        if raw_arow and not _is_zero_abundance_sentinel(raw_arow):
            arow: Mapping[str, Any] = raw_arow
            last_valid_arow = raw_arow
            last_valid_index = zi + 1
        elif last_valid_arow:
            arow = last_valid_arow
            used_carried_abundance = True
        else:
            arow = raw_arow
        radius = _as_float(arow.get("radius"))
        delta_r = _as_float(arow.get("delta_r"))
        logxi = _as_float(arow.get("ion_parameter"))
        zone = XSTARZoneState(
            zone_index=zi + 1,
            radius_cm=radius,
            thickness_cm=delta_r,
            temperature=_abundance_temperature_K(arow) if arow else None,
            electron_density=_abundance_electron_density(arow) if arow else None,
            ionization_parameter=logxi,
            cfrac=cfrac,
            vturbi=vturbi,
            ion_fractions=_ion_fractions_from_abundance_row(arow) if arow else {},
            status="populated_from_xstar_detail_outputs",
        )
        if used_carried_abundance:
            zone.status = "populated_from_xstar_detail_outputs_with_carried_abundance_state"
            setattr(zone, "abundance_row_source", f"carried_forward_from_abundance_row_{last_valid_index}")
        else:
            setattr(zone, "abundance_row_source", f"abundance_row_{zi + 1}" if raw_arow else "missing_abundance_row")
        if include_level_populations and zi < len(detail_hdus):
            pops_by_ion: Dict[str, List[float]] = {}
            records_by_ion: Dict[str, List[Dict[str, Any]]] = {}
            for row in detail_hdus[zi].get("rows", []):
                ion = _as_str(row.get("ion")).lower()
                val = _as_float(row.get("population"))
                if not ion or val is None:
                    continue
                pops_by_ion.setdefault(ion, []).append(val)
                records_by_ion.setdefault(ion, []).append(dict(row))
            zone.level_populations = pops_by_ion
            # ``level_population_records`` was added in v0.3.151 but keep this
            # assignment dynamic so older pickled/user objects still load.
            setattr(zone, "level_population_records", records_by_ion)
        if include_line_transfer and zi < len(line_hdus):
            rows = list(line_hdus[zi].get("rows", []))
            line_ids = [_as_str(row.get("index")) for row in rows]
            wavelengths = [float(_as_float(row.get("wavelength"), 0.0) or 0.0) for row in rows]
            tau_in = [float(_as_float(row.get("tau_in"), 0.0) or 0.0) for row in rows]
            tau_out = [float(_as_float(row.get("tau_out"), 0.0) or 0.0) for row in rows]
            ptmp_pairs = [_ptmp_from_tau(t1, t2, cfrac) for t1, t2 in zip(tau_in, tau_out)]
            zone.lines = XSTARLineTransferState(
                line_ids=line_ids,
                wavelengths_A=wavelengths,
                tau0_in=tau_in,
                tau0_out=tau_out,
                ptmp1=[p[0] for p in ptmp_pairs],
                ptmp2=[p[1] for p in ptmp_pairs],
                line_opacity=[float(_as_float(row.get("opacity"), 0.0) or 0.0) for row in rows],
                line_emissivity=[float(_as_float(row.get("emis_outward"), 0.0) or 0.0) for row in rows],
                source="xo01_detal2.fits:XSTAR_RADIAL",
            )
            setattr(zone.lines, "line_records", rows)
        if include_continuum and zi < len(cont_hdus):
            rows = list(cont_hdus[zi].get("rows", []))
            epi = [float(_as_float(row.get("energy"), 0.0) or 0.0) for row in rows]
            bremsa = reconstruct_bremsa_from_detal4_rows(rows, radius_cm=radius)
            zone.continuum = XSTARContinuumState(
                epi=epi,
                bremsa=bremsa,
                bremsint=reconstruct_bremsint(epi, bremsa),
                tauc_in=[float(_as_float(row.get("fwd_dpth"), 0.0) or 0.0) for row in rows],
                tauc_out=[float(_as_float(row.get("bck_dpth"), 0.0) or 0.0) for row in rows],
                dpthc_forward=[float(_as_float(row.get("fwd_dpth"), 0.0) or 0.0) for row in rows],
                dpthc_backward=[float(_as_float(row.get("bck_dpth"), 0.0) or 0.0) for row in rows],
                continuum_opacity=[float(_as_float(row.get("opacity"), 0.0) or 0.0) for row in rows],
                continuum_emissivity=[float(_as_float(row.get("emis_out"), 0.0) or 0.0) for row in rows],
                source="xo01_detal4.fits:XSTAR_RADIAL;bremsa_reconstructed_from_zrems_total",
            )
            setattr(zone.continuum, "continuum_records", rows)
        zones.append(zone)
    return XSTARRunState(parameters=params, zones=zones, source=str(root), status="populated_from_xstar_detail_outputs_not_full_recreation")


def _normalise_ion_key(text: Any) -> str:
    return str(text or "").strip().lower().replace(" ", "_").replace("-", "_")


def _line_kind_from_detail_row(row: Mapping[str, Any]) -> str:
    """Classify common He-like triplet rows as f/i/r when possible."""
    upper = _normalise_ion_key(row.get("upper_level"))
    wav = _as_float(row.get("wavelength"))
    if "2s1.3s_1" in upper or "2s1.3s" in upper:
        return "f"
    if "2p1.1p_1" in upper or "2p1.1p" in upper:
        return "r"
    if "2p1.3p" in upper:
        return "i"
    # wavelength fallbacks for O VII-like examples; broad enough to be harmless
    # only inside a user-specified narrow wavelength window.
    if wav is not None:
        if 22.0 <= wav <= 22.2:
            return "f"
        if 21.55 <= wav <= 21.65:
            return "r"
        if 21.75 <= wav <= 21.90:
            return "i"
    return "other"


def _first_existing_numeric(row: Mapping[str, Any], keys: Sequence[str]) -> Optional[float]:
    for key in keys:
        val = _as_float(row.get(key))
        if val is not None:
            return val
    return None


def _match_atdb_line(detail_row: Mapping[str, Any], atdb_lines: Sequence[Mapping[str, Any]], tolerance_A: float) -> Optional[Mapping[str, Any]]:
    wav = _as_float(detail_row.get("wavelength"))
    if wav is None:
        return None
    best = None
    best_dw = None
    d_lower = _normalise_ion_key(detail_row.get("lower_level"))
    d_upper = _normalise_ion_key(detail_row.get("upper_level"))
    for row in atdb_lines:
        aw = _first_existing_numeric(row, ["wavelength_A", "wavelength", "lambda_A"])
        if aw is None:
            continue
        dw = abs(float(aw) - float(wav))
        if dw > tolerance_A:
            continue
        # Prefer label-consistent rows when decoded labels are available, but do
        # not require exact string equality because XSTAR output labels can omit
        # some punctuation/degeneracy details.
        score = dw
        al = _normalise_ion_key(row.get("lower_label") or row.get("lower_level_label"))
        au = _normalise_ion_key(row.get("upper_label") or row.get("upper_level_label"))
        if d_lower and al and d_lower != al:
            score += 0.01
        if d_upper and au and d_upper != au:
            score += 0.01
        if best is None or score < float(best_dw):
            best = row
            best_dw = score
    return best


def _read_csv_rows(path: str | Path | None) -> List[Dict[str, Any]]:
    if path is None or not str(path).strip():
        return []
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _match_matrix_row(detail_row: Mapping[str, Any], atdb_row: Mapping[str, Any] | None, matrix_rows: Sequence[Mapping[str, Any]], tolerance_A: float) -> Optional[Mapping[str, Any]]:
    if not matrix_rows:
        return None
    rec = str((atdb_row or {}).get("record") or (atdb_row or {}).get("record_id") or "").strip()
    if rec:
        for row in matrix_rows:
            if str(row.get("record") or row.get("record_id") or row.get("atdb_record") or "").strip() == rec:
                return row
    wav = _as_float(detail_row.get("wavelength"))
    if wav is None:
        return None
    best = None
    best_dw = None
    for row in matrix_rows:
        mw = _first_existing_numeric(row, ["wavelength_A", "wavelength", "lambda_A", "line_wavelength_A"])
        if mw is None:
            continue
        dw = abs(float(mw) - float(wav))
        if dw <= tolerance_A and (best is None or dw < float(best_dw)):
            best = row
            best_dw = dw
    return best


def _matrix_rate_from_row(row: Mapping[str, Any] | None) -> Optional[float]:
    if not row:
        return None
    return _first_existing_numeric(row, [
        "rate_s^-1", "rate_s_inv", "matrix_rate_s^-1", "matrix_rate", "effective_rate_s^-1",
        "type50_effective_downward_rate_s^-1", "upper_to_lower_escaped_decay_s^-1",
    ])


def audit_xstar_detail_type50_rates(
    run_dir: str | Path,
    *,
    ion: str = "O VII",
    atdb: str | Path | None = None,
    zone_index: int | str = "last",
    wavelength_min: float | None = None,
    wavelength_max: float | None = None,
    tolerance_A: float = 0.03,
    matrix_terms_csv: str | Path | None = None,
) -> List[Dict[str, Any]]:
    """Audit XSTAR detail-state type-50 rates for He-like triplet lines.

    The function reads ``xo01_detal2.fits``/``xo01_detal4.fits`` through
    :func:`read_xstar_detail_run_state`, matches selected detail line rows to
    ATDB type-50 records when an ``atdb`` path is supplied, and evaluates the
    same type-50 escaped-decay/photoexcitation algebra used by ``ucalc.f90``.

    The returned rows are CSV-friendly and include optional residuals against a
    solver matrix-term CSV if one is supplied.  Without a matrix CSV, the matrix
    columns are left blank and the rate audit is still complete.
    """
    state = read_xstar_detail_run_state(run_dir)
    if not state.zones:
        return []
    if isinstance(zone_index, str) and zone_index.lower() == "last":
        zone = state.zones[-1]
    else:
        zi = int(zone_index)
        if zi < 1 or zi > len(state.zones):
            raise ValueError(f"zone_index must be 1..{len(state.zones)} or 'last'")
        zone = state.zones[zi - 1]
    ion_key = _normalise_ion_key(ion)
    detail_rows = []
    line_records = getattr(zone.lines, "line_records", []) or []
    for row in line_records:
        if _normalise_ion_key(row.get("ion")) != ion_key:
            continue
        wav = _as_float(row.get("wavelength"))
        if wav is None:
            continue
        if wavelength_min is not None and wav < wavelength_min:
            continue
        if wavelength_max is not None and wav > wavelength_max:
            continue
        detail_rows.append(row)

    atdb_lines: List[Mapping[str, Any]] = []
    if atdb is not None and str(atdb).strip():
        try:
            from .api import XSTARAtomic
            db = XSTARAtomic(str(atdb))
            # Query a slightly wider wavelength range to permit matching.
            if wavelength_min is not None and wavelength_max is not None:
                wsel = (float(wavelength_min) - tolerance_A, float(wavelength_max) + tolerance_A)
            else:
                waves = [_as_float(r.get("wavelength")) for r in detail_rows]
                waves = [float(w) for w in waves if w is not None]
                wsel = (min(waves) - tolerance_A, max(waves) + tolerance_A) if waves else None
            atdb_lines = db.lines(ion, wavelength=wsel, data_type=50) if wsel else db.lines(ion, data_type=50)
        except Exception:
            atdb_lines = []

    matrix_rows = _read_csv_rows(matrix_terms_csv)
    out_rows: List[Dict[str, Any]] = []
    for row in detail_rows:
        wav = _as_float(row.get("wavelength"))
        energy_eV = 12398.4016 / float(wav) if wav and wav > 0.0 else None
        atdb_row = _match_atdb_line(row, atdb_lines, tolerance_A) if atdb_lines else None
        matrix_row = _match_matrix_row(row, atdb_row, matrix_rows, tolerance_A)
        tau_in = _as_float(row.get("tau_in"), 0.0) or 0.0
        tau_out = _as_float(row.get("tau_out"), 0.0) or 0.0
        ptmp1, ptmp2 = ptmp_from_tau_xstar(tau_in, tau_out, zone.cfrac)
        A = None
        flin = None
        record = None
        lower_level = None
        upper_level = None
        lower_label = None
        upper_label = None
        if atdb_row:
            record = atdb_row.get("record") or atdb_row.get("record_id")
            A = _first_existing_numeric(atdb_row, ["A_s^-1", "A_s_inv", "rate_s^-1", "rate_s_inv"])
            flin = _first_existing_numeric(atdb_row, ["f_osc_from_A", "oscillator_strength", "flin"])
            lower_level = atdb_row.get("lower_level")
            upper_level = atdb_row.get("upper_level")
            lower_label = atdb_row.get("lower_label")
            upper_label = atdb_row.get("upper_label")
        mass = atomic_mass_number_from_ion(ion)
        vtherm = type50_vtherm_xstar(temperature_K=zone.temperature, vturb_km_s=zone.vturbi, atomic_mass_number=mass)
        idx, nb1 = xstar_nbinc_index(float(energy_eV), zone.continuum.epi) if energy_eV is not None else (None, None)
        bremsa_nb1 = None
        if idx is not None and idx < len(zone.continuum.bremsa):
            bremsa_nb1 = float(zone.continuum.bremsa[idx])
        escaped_decay = float(A) * (ptmp1 + ptmp2) if A is not None else None
        photo = None
        sigma = None
        if flin is not None and wav is not None and vtherm is not None and vtherm > 0.0 and bremsa_nb1 is not None:
            sigma = 0.02655 * float(flin) * float(wav) * 1.0e-8 / float(vtherm)
            photo = sigma * float(bremsa_nb1) * float(vtherm) / 3.0e10 * 1.0 * max(0.0, 1.0 - float(zone.cfrac or 0.0))
        matrix_rate = _matrix_rate_from_row(matrix_row)
        out_rows.append({
            "zone_index": zone.zone_index,
            "ion": ion,
            "line_kind": _line_kind_from_detail_row(row),
            "detail_index": row.get("index"),
            "detail_wavelength_A": wav,
            "detail_lower_level": row.get("lower_level"),
            "detail_upper_level": row.get("upper_level"),
            "detail_emis_inward": row.get("emis_inward"),
            "detail_emis_outward": row.get("emis_outward"),
            "detail_opacity": row.get("opacity"),
            "tau_in": tau_in,
            "tau_out": tau_out,
            "pescl_tau_in": pescl_xstar(tau_in),
            "pescl_tau_out": pescl_xstar(tau_out),
            "pescl_tau_sum": pescl_xstar(float(tau_in) + float(tau_out)),
            "cfrac": zone.cfrac,
            "vturbi_km_s^-1": zone.vturbi,
            "temperature_K": zone.temperature,
            "electron_density_cm^-3": zone.electron_density,
            "ptmp1": ptmp1,
            "ptmp2": ptmp2,
            "ptmp_sum": ptmp1 + ptmp2,
            "atdb_record": record,
            "atdb_lower_level": lower_level,
            "atdb_upper_level": upper_level,
            "atdb_lower_label": lower_label,
            "atdb_upper_label": upper_label,
            "atdb_A_s^-1": A,
            "atdb_flin": flin,
            "line_energy_eV": energy_eV,
            "nbinc_python_index": idx,
            "nbinc_fortran_nb1": nb1,
            "bremsa_nb1": bremsa_nb1,
            "atomic_mass_number": mass,
            "vtherm_cm_s": vtherm,
            "sigma_cm2": sigma,
            "ucalc_pre_swap_ans1_escaped_decay_s^-1": escaped_decay,
            "ucalc_pre_swap_ans2_photoexcitation_s^-1": photo,
            "ucalc_post_swap_ans1_photoexcitation_s^-1": photo,
            "ucalc_post_swap_ans2_escaped_decay_s^-1": escaped_decay,
            "photoexcitation_expected_zero_from_cfrac": bool(float(zone.cfrac or 0.0) >= 1.0),
            "matrix_match_status": "matched" if matrix_row else "not_supplied_or_not_matched",
            "matrix_rate_s^-1": matrix_rate,
            "matrix_minus_ucalc_escaped_decay_s^-1": (float(matrix_rate) - float(escaped_decay)) if matrix_rate is not None and escaped_decay is not None else None,
            "source_code_formula": "calc_hmc_ion.f90 ptmp1/ptmp2 + ucalc.f90 type50 ans1=A*(ptmp1+ptmp2), ans2=sigma*bremsa(nb1)*vtherm/3e10*flinabs(ptmp1)*(1-cfrac), final swap",
        })
    return out_rows


def write_xstar_detail_type50_rate_audit(rows: Sequence[Mapping[str, Any]], out_dir: str | Path, *, prefix: str = "xstar_detail_type50_rate_audit") -> Dict[str, str]:
    """Write CSV/JSON/Markdown outputs for detail-state type-50 audit rows."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / f"{prefix}.csv"
    fields = list(rows[0].keys()) if rows else ["status"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
    json_path = out / f"{prefix}.json"
    json_path.write_text(json.dumps([dict(r) for r in rows], indent=2, sort_keys=True), encoding="utf-8")
    md_path = out / f"{prefix}.md"
    lines = [
        "# XSTAR detail type-50 rate audit",
        "",
        f"Rows: `{len(rows)}`",
        "",
        "This audit evaluates the XSTAR source-code type-50 terms from detail-state `tau0`, `epi`, and reconstructed `bremsa` arrays.",
        "",
        "| kind | wavelength (A) | tau_in | tau_out | ptmp sum | A (s^-1) | escaped decay (s^-1) | photoexcitation (s^-1) | matrix status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('line_kind')} | {row.get('detail_wavelength_A')} | {row.get('tau_in')} | {row.get('tau_out')} | "
            f"{row.get('ptmp_sum')} | {row.get('atdb_A_s^-1')} | {row.get('ucalc_pre_swap_ans1_escaped_decay_s^-1')} | "
            f"{row.get('ucalc_pre_swap_ans2_photoexcitation_s^-1')} | {row.get('matrix_match_status')} |"
        )
    lines += [
        "",
        "## Source-code path",
        "",
        "`calc_hmc_ion.f90` forms `ptmp1` and `ptmp2` from `tau0` and `cfrac`, then `ucalc.f90` type 50 computes escaped decay and photoexcitation and swaps the returned branches.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"csv": str(csv_path), "json": str(json_path), "markdown": str(md_path)}

def summarize_xstar_detail_state(state: XSTARRunState) -> List[Dict[str, Any]]:
    """Return one summary row per populated zone."""
    rows: List[Dict[str, Any]] = []
    for zone in state.zones:
        rows.append({
            "zone_index": zone.zone_index,
            "temperature_K": zone.temperature,
            "electron_density_cm^-3": zone.electron_density,
            "ionization_parameter_logxi": zone.ionization_parameter,
            "radius_cm": zone.radius_cm,
            "delta_r_cm": zone.thickness_cm,
            "cfrac": zone.cfrac,
            "vturbi_km_s^-1": zone.vturbi,
            "n_ion_fractions": len(zone.ion_fractions),
            "n_level_population_ions": len(zone.level_populations),
            "n_level_population_rows": sum(len(v) for v in zone.level_populations.values()),
            "n_line_rows": zone.lines.n_lines(),
            "n_continuum_points": zone.continuum.n_energy(),
            "continuum_missing_fields": ";".join(zone.continuum.missing_fields()),
            "line_missing_fields": ";".join(zone.lines.missing_fields()),
            "missing_core_fields": ";".join(zone.missing_core_fields()),
            "abundance_row_source": getattr(zone, "abundance_row_source", ""),
            "status": zone.status,
        })
    return rows


def write_xstar_detail_state(
    state: XSTARRunState,
    out_dir: str | Path,
    *,
    prefix: str = "xstar_detail_live_state",
    write_full_json: bool = False,
) -> Dict[str, str]:
    """Write JSON/Markdown/CSV summaries for a populated detail state."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_rows = summarize_xstar_detail_state(state)
    summary_csv = out / f"{prefix}_zones.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        fields = list(summary_rows[0].keys()) if summary_rows else ["zone_index", "status"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in summary_rows:
            writer.writerow(row)
    fields_csv = out / f"{prefix}_field_status.csv"
    with fields_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["zone_index", "field", "present", "count_or_value", "source"])
        writer.writeheader()
        for zone in state.zones:
            rows = [
                ("epi(:)", bool(zone.continuum.epi), len(zone.continuum.epi), zone.continuum.source),
                ("bremsa(:)", bool(zone.continuum.bremsa), len(zone.continuum.bremsa), zone.continuum.source),
                ("bremsint(:)", bool(zone.continuum.bremsint), len(zone.continuum.bremsint), zone.continuum.source),
                ("tau0(1:2,line)", bool(zone.lines.tau0_in and zone.lines.tau0_out), zone.lines.n_lines(), zone.lines.source),
                ("tauc/dpthc(1:2,continuum)", bool(zone.continuum.tauc_in and zone.continuum.tauc_out), len(zone.continuum.tauc_in), zone.continuum.source),
                ("cfrac", zone.cfrac is not None, zone.cfrac, "PARAMETERS/run_xstar.sh"),
                ("vturbi", zone.vturbi is not None, zone.vturbi, "PARAMETERS/run_xstar.sh"),
                ("temperature/electron density per zone", zone.temperature is not None and zone.electron_density is not None, f"{zone.temperature}/{zone.electron_density}", f"xout_abund1.fits:ABUNDANCES:{getattr(zone, 'abundance_row_source', '')}"),
                ("ion fractions per zone", bool(zone.ion_fractions), len(zone.ion_fractions), f"xout_abund1.fits:ABUNDANCES:{getattr(zone, 'abundance_row_source', '')}"),
                ("level populations per zone", bool(zone.level_populations), sum(len(v) for v in zone.level_populations.values()), "xo01_detail.fits:XSTAR_RADIAL"),
            ]
            for field, present, count, source in rows:
                writer.writerow({"zone_index": zone.zone_index, "field": field, "present": bool(present), "count_or_value": count, "source": source})
    md_path = out / f"{prefix}.md"
    lines = [
        "# XSTAR detail live-state population",
        "",
        f"Status: `{state.status}`",
        "",
        f"Source: `{state.source}`",
        "",
        f"Number of zones: `{len(state.zones)}`",
        "",
        "## Zone summary",
        "",
        "| Zone | T (K) | ne (cm^-3) | log xi | n(level rows) | n(line rows) | n(continuum) | missing core fields |",
        "|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['zone_index']} | {row['temperature_K']} | {row['electron_density_cm^-3']} | {row['ionization_parameter_logxi']} | "
            f"{row['n_level_population_rows']} | {row['n_line_rows']} | {row['n_continuum_points']} | `{row['missing_core_fields']}` |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "`bremsa(:)` is reconstructed from `xo01_detal4.fits` as an output-state audit quantity using the XSTAR geometric attenuation form. Exact in-iteration parity still requires reproducing the source-code transfer loop that produced the detail file.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    paths = {"markdown": str(md_path), "zones_csv": str(summary_csv), "fields_csv": str(fields_csv)}
    if write_full_json:
        json_path = out / f"{prefix}.json"
        json_path.write_text(json.dumps(state.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
        paths["json"] = str(json_path)
    return paths
