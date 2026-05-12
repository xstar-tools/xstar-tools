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
