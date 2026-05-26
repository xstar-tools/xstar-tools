"""Radial and spectrum parity diagnostics for the physical XSTAR runner.

This module is intentionally observational: it writes source-order summaries of
Python radial stepping/spectrum state and, when original XSTAR products are
available, compares the public FITS/log outputs without using those outputs as
Python runtime inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


def _ensure_astropy_numpy_compat() -> None:
    """Install narrow runtime shims needed by older Astropy on newer NumPy."""
    if not hasattr(np, "in1d"):
        np.in1d = np.isin  # type: ignore[attr-defined]
    try:
        import numpy.lib._function_base_impl as fbi  # type: ignore[import-not-found]
    except Exception:
        return
    if not hasattr(fbi, "_check_interpolation_as_method"):
        def _check_interpolation_as_method(method: Any, *args: Any, **kwargs: Any) -> Any:
            return method
        fbi._check_interpolation_as_method = _check_interpolation_as_method  # type: ignore[attr-defined]


def _fits_open(path: Path):
    _ensure_astropy_numpy_compat()
    from astropy.io import fits
    return fits.open(path)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        val = float(value)
    except Exception:
        return float(default)
    if not math.isfinite(val):
        return float(default)
    return val


def _rel_diff(a: float, b: float) -> float:
    aa = _as_float(a)
    bb = _as_float(b)
    den = max(abs(aa), abs(bb), 1.0e-300)
    return abs(aa - bb) / den


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        keys: list[str] = []
        for row in rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(str(key))
        fields = keys
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fields})


def _norm_name(name: str) -> str:
    return str(name).strip().lower().replace("-", "_").replace(" ", "_")


def _column_names(data: Any) -> list[str]:
    return [str(name) for name in getattr(data, "names", [])]


def _find_column(data: Any, names: Sequence[str]) -> str | None:
    mapping = {_norm_name(name): str(name) for name in _column_names(data)}
    for name in names:
        found = mapping.get(_norm_name(name))
        if found is not None:
            return found
    return None


def _hdu_data_by_name(path: Path, candidates: Sequence[str]) -> Any | None:
    if not path.is_file():
        return None
    with _fits_open(path) as hdul:
        for cand in candidates:
            try:
                return hdul[cand].data
            except Exception:
                pass
        for hdu in hdul[1:]:
            extname = str(hdu.header.get("EXTNAME", ""))
            if any(_norm_name(extname) == _norm_name(c) for c in candidates):
                return hdu.data
    return None


def _classify_radial_row(radius: float, delta_r: float, index: int, total: int) -> str:
    if index == 1 and delta_r == 0.0:
        return "initial_row"
    if index == 2 and delta_r == 0.0:
        return "repeated_initial_row"
    if radius == 0.0 and delta_r == 0.0 and index == total:
        return "zero_final_padding_row"
    if index == total:
        return "final_row"
    return "intermediate_row"


def _abundance_rows(path: Path, label: str) -> list[dict[str, Any]]:
    data = _hdu_data_by_name(path, ("ABUNDANCES", "ABUNDANCE"))
    if data is None:
        return []
    radius_col = _find_column(data, ("radius", "r"))
    delta_col = _find_column(data, ("delta_r", "delr", "delta r"))
    ion_col = _find_column(data, ("ion_parameter", "ion parameter", "xi"))
    temp_col = _find_column(data, ("temperature", "t"))
    xee_col = _find_column(data, ("x_e", "xee"))
    xpx_col = _find_column(data, ("n_p", "xpx", "density"))
    total = len(data)
    rows: list[dict[str, Any]] = []
    for i, rec in enumerate(data, start=1):
        radius = _as_float(rec[radius_col]) if radius_col else 0.0
        delta = _as_float(rec[delta_col]) if delta_col else 0.0
        rows.append({
            "source": label,
            "row_index": i,
            "row_count": total,
            "row_role": _classify_radial_row(radius, delta, i, total),
            "radius_cm": radius,
            "delta_r_cm": delta,
            "ion_parameter": _as_float(rec[ion_col]) if ion_col else "",
            "temperature_1e4K": _as_float(rec[temp_col]) if temp_col else "",
            "x_e": _as_float(rec[xee_col]) if xee_col else "",
            "n_p": _as_float(rec[xpx_col]) if xpx_col else "",
        })
    return rows


def _spectra_data(path: Path) -> Any | None:
    return _hdu_data_by_name(path, ("XSTAR_SPECTRA", "SPECTRA"))


def _spectra_comparison_rows(python_file: Path, original_file: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    py = _spectra_data(python_file)
    xo = _spectra_data(original_file)
    if py is None or xo is None:
        return [], {"ready": False, "reason": "missing xout_spect1.fits spectra table"}
    n = min(len(py), len(xo))
    e_py = _find_column(py, ("energy", "energies", "e"))
    e_xo = _find_column(xo, ("energy", "energies", "e"))
    cols = {
        "incident": (_find_column(py, ("incident",)), _find_column(xo, ("incident",))),
        "transmitted": (_find_column(py, ("transmitted",)), _find_column(xo, ("transmitted",))),
        "emit_inward": (_find_column(py, ("emit_inward",)), _find_column(xo, ("emit_inward",))),
        "emit_outward": (_find_column(py, ("emit_outward",)), _find_column(xo, ("emit_outward",))),
    }
    rows: list[dict[str, Any]] = []
    py_out: list[float] = []
    xo_out: list[float] = []
    for i in range(n):
        energy = _as_float(py[i][e_py]) if e_py else (_as_float(xo[i][e_xo]) if e_xo else float(i + 1))
        row: dict[str, Any] = {"bin_index": i + 1, "energy_eV": energy}
        for name, (pc, xc) in cols.items():
            pv = _as_float(py[i][pc]) if pc else 0.0
            xv = _as_float(xo[i][xc]) if xc else 0.0
            row[f"python_{name}"] = pv
            row[f"xstar_{name}"] = xv
            row[f"absdiff_{name}"] = abs(pv - xv)
            row[f"reldiff_{name}"] = _rel_diff(pv, xv)
            if name == "emit_outward":
                py_out.append(pv)
                xo_out.append(xv)
        rows.append(row)
    pya = np.asarray(py_out, dtype=float)
    xoa = np.asarray(xo_out, dtype=float)
    py_nz = np.nonzero(pya != 0.0)[0]
    xo_nz = np.nonzero(xoa != 0.0)[0]
    xo_only = np.nonzero((pya == 0.0) & (xoa != 0.0))[0]
    summary: dict[str, Any] = {
        "ready": True,
        "n_python_rows": int(len(py)),
        "n_xstar_rows": int(len(xo)),
        "n_compared_rows": int(n),
        "python_emit_outward_sum": float(np.sum(pya)),
        "xstar_emit_outward_sum": float(np.sum(xoa)),
        "emit_outward_sum_ratio_python_over_xstar": float(np.sum(pya) / np.sum(xoa)) if np.sum(xoa) != 0.0 else None,
        "python_emit_outward_nonzero_bins": int(py_nz.size),
        "xstar_emit_outward_nonzero_bins": int(xo_nz.size),
        "xstar_only_nonzero_bins": int(xo_only.size),
    }
    if xo_only.size:
        first = int(xo_only[0])
        last = int(xo_only[-1])
        summary.update({
            "xstar_only_first_bin": first + 1,
            "xstar_only_last_bin": last + 1,
            "xstar_only_first_energy_eV": rows[first]["energy_eV"],
            "xstar_only_last_energy_eV": rows[last]["energy_eV"],
        })
    return rows, summary


def _summarize_array(name: str, arr: Any, *, row_kind: str, pass_index: int, zone_index: int, phase: str) -> dict[str, Any]:
    a = np.asarray(arr, dtype=float).reshape(-1)
    finite = a[np.isfinite(a)]
    return {
        "row_kind": row_kind,
        "phase": phase,
        "pass_index": int(pass_index),
        "zone_index": int(zone_index),
        "array_name": name,
        "size": int(a.size),
        "nonzero_count": int(np.count_nonzero(a)),
        "sum": float(np.sum(finite)) if finite.size else 0.0,
        "max_abs": float(np.max(np.abs(finite))) if finite.size else 0.0,
        "min": float(np.min(finite)) if finite.size else 0.0,
        "max": float(np.max(finite)) if finite.size else 0.0,
    }


def append_python_radial_shell_diagnostic(state: Any, *, zone_index: int, pass_index: int, direction: int) -> None:
    """Capture Python radial state after one bounded radial shell."""
    if not bool(state.control.get("radial_spectrum_parity_diagnostic_enabled", False)):
        return
    from .radial_transfer import RadialTransferWorkspace
    workspace = state.control.get("radial_transfer_workspace")
    if not isinstance(workspace, RadialTransferWorkspace):
        return
    data = state.outputs.setdefault("radial_spectrum_parity_v0500", {})
    step_rows = data.setdefault("radial_stepping_rows", [])
    step_probe_rows = data.setdefault("step_probe_rows", [])
    opacity_rows = data.setdefault("opacity_summary_rows", [])
    spectrum_rows = data.setdefault("spectrum_accumulation_rows", [])
    row_write_rows = data.setdefault("row_write_rows", [])

    step = state.transfer.source_arrays.get("step")
    stpcut = state.transfer.source_arrays.get("stpcut")
    trnfrn = state.transfer.source_arrays.get("trnfrn")
    delr = float(getattr(step, "delr_cm", state.transfer.step_size))
    step_rows.append({
        "pass_index": int(pass_index),
        "zone_index": int(zone_index),
        "direction": int(direction),
        "r_cm": float(state.transfer.radius),
        "delr_cm": float(delr),
        "rdel_cm": float(state.transfer.radial_depth),
        "xcol_cm2": float(state.transfer.column),
        "delcol_cm2": float(delr * float(state.plasma.xpx)),
        "numrec": int(state.control.get("numrec", 0)),
        "nsteps_effective": int(state.control.get("numrec", 0)),
        "nsteps_run_script": int(state.control.get("nsteps_run_script", state.control.get("numrec", 0))),
        "nsteps_pfile_default": int(state.control.get("nsteps_pfile_default", 3)),
        "nsteps_normalized": int(state.control.get("nsteps_normalized", state.control.get("numrec", 0))),
        "nlsvn": int(state.control.get("nlsvn", 0)),
        "step_selected_bin_one_based": int(getattr(step, "selected_bin_one_based", 0)),
        "step_min_tst_bin_one_based": int(getattr(step, "min_tst_bin_one_based", 0)),
        "step_initial_delr_cm": float(getattr(step, "initial_delr_cm", 0.0)),
        "step_opacity_limited_delr_cm": float(getattr(step, "opacity_limited_delr_cm", 0.0)),
        "step_remaining_column_delr_cm": float(getattr(step, "remaining_column_delr_cm", 0.0)),
        "taulc_max_dpthc": float(np.max(np.asarray(workspace.dpthc[0], dtype=float))) if workspace.dpthc.size else 0.0,
        "dpthc_forward_max": float(np.max(np.asarray(workspace.dpthc[1], dtype=float))) if workspace.dpthc.size else 0.0,
        "dpthc_reverse_max": float(np.max(np.asarray(workspace.dpthc[0], dtype=float))) if workspace.dpthc.size else 0.0,
        "tau0_forward_max": float(np.max(np.asarray(workspace.tau0[1], dtype=float))) if workspace.tau0.size else 0.0,
        "tau0_reverse_max": float(np.max(np.asarray(workspace.tau0[0], dtype=float))) if workspace.tau0.size else 0.0,
        "tauc_forward_max": float(np.max(np.asarray(workspace.tauc[1], dtype=float))) if workspace.tauc.size else 0.0,
        "tauc_reverse_max": float(np.max(np.asarray(workspace.tauc[0], dtype=float))) if workspace.tauc.size else 0.0,
        "stpcut_max_zone_continuum_depth": float(getattr(stpcut, "max_zone_continuum_depth", 0.0)),
    })
    if step is not None:
        step_probe_rows.append({
            "row_kind": "step_f90_zone_probe",
            "pass_index": int(pass_index),
            "zone_index": int(zone_index),
            "direction": int(direction),
            "emult": float(getattr(step, "emult", 0.0)),
            "ectt_eV": float(getattr(step, "ectt_eV", 0.0)),
            "taumax": float(getattr(step, "taumax", 0.0)),
            "nsteps_effective": int(state.control.get("numrec", 0)),
            "nsteps_run_script": int(state.control.get("nsteps_run_script", state.control.get("numrec", 0))),
            "nsteps_pfile_default": int(state.control.get("nsteps_pfile_default", 3)),
            "nsteps_normalized": int(state.control.get("nsteps_normalized", state.control.get("numrec", 0))),
            "selected_kl": int(getattr(step, "selected_bin_one_based", 0)),
            "selected_epi_eV": float(getattr(step, "selected_epi_eV", 0.0)),
            "selected_opakc_cm_inv": float(getattr(step, "selected_opakc_cm_inv", 0.0)),
            "selected_dpthc": float(getattr(step, "selected_dpthc", 0.0)),
            "selected_zrems_row1": float(getattr(step, "selected_zrems", 0.0)),
            "selected_tst_cm": float(getattr(step, "selected_tst_cm", 0.0)),
            "min_tst_kl": int(getattr(step, "min_tst_bin_one_based", 0)),
            "min_tst_cm": float(getattr(step, "min_tst_cm", 0.0)),
            "min_tst_epi_eV": float(getattr(step, "min_tst_epi_eV", 0.0)),
            "min_tst_opakc_cm_inv": float(getattr(step, "min_tst_opakc_cm_inv", 0.0)),
            "min_tst_dpthc": float(getattr(step, "min_tst_dpthc", 0.0)),
            "min_tst_zrems_row1": float(getattr(step, "min_tst_zrems", 0.0)),
            "delr_initial_cm": float(getattr(step, "initial_delr_cm", 0.0)),
            "delr_after_opacity_loop_cm": float(getattr(step, "opacity_limited_delr_cm", 0.0)),
            "delr_remaining_column_cm": float(getattr(step, "remaining_column_delr_cm", 0.0)),
            "delr_final_cm": float(getattr(step, "delr_cm", 0.0)),
        })
    calc_emis_result = getattr(state.local_zone, "source_arrays", {}).get("calc_emis_all")
    context = state.control.get("calc_emis_context")
    line_rank = getattr(calc_emis_result, "line_rank_table", None)
    n_ranked_line_bins = 0
    bin4063_ranked_line_count = 0
    if line_rank is not None:
        lr = np.asarray(line_rank, dtype=int)
        if lr.ndim == 2 and lr.shape[1] > 1:
            n_ranked_line_bins = int(np.count_nonzero(np.any(lr[1:, 1:] != 0, axis=0)))
            if lr.shape[1] > 4063:
                bin4063_ranked_line_count = int(np.count_nonzero(lr[1:, 4063]))
    line_traces = [
        tr for tr in getattr(calc_emis_result, "record_traces", ())
        if str(getattr(tr, "output_role", "")).startswith("strong_line_rate_type_")
    ]
    strongest = None
    if line_traces:
        strongest = max(line_traces, key=lambda tr: abs(float(getattr(tr, "opakb1", 0.0))))
    oplin_arr = np.asarray(workspace.oplin_physical, dtype=float).reshape(-1)
    opakc_arr = np.asarray(workspace.opakc, dtype=float).reshape(-1)
    opakcont_arr = np.asarray(workspace.opakcont, dtype=float).reshape(-1)
    line_binned = opakc_arr[: min(opakc_arr.size, opakcont_arr.size)] - opakcont_arr[: min(opakc_arr.size, opakcont_arr.size)]
    strongest_index = int(getattr(strongest, "output_index", 0)) if strongest is not None else 0
    strongest_energy = 0.0
    strongest_nb1 = 0
    if strongest_index > 0 and context is not None:
        try:
            wave = float(context.line_wavelength_angstrom[strongest_index])
            if wave > 0.0:
                strongest_energy = 12398.4016 / (wave + 1.0e-36)
                epi = np.asarray(getattr(context.radiation, "epi_eV", getattr(context.radiation, "epi", ())), dtype=float).reshape(-1)
                from .radiation import nbinc
                strongest_nb1 = int(nbinc(strongest_energy, epi, int(epi.size))) if epi.size else 0
        except Exception:
            strongest_energy = 0.0
            strongest_nb1 = 0
    opacity_rows.append({
        "row_kind": "line_opacity_handoff_summary",
        "phase": "after_shell",
        "pass_index": int(pass_index),
        "zone_index": int(zone_index),
        "line_opacity_nonzero_count": int(np.count_nonzero(oplin_arr)),
        "max_oplin": float(np.max(np.abs(oplin_arr))) if oplin_arr.size else 0.0,
        "max_line_opacity_binned_into_opakc": float(np.max(np.abs(line_binned))) if line_binned.size else 0.0,
        "strongest_line_index": strongest_index,
        "strongest_line_energy": strongest_energy,
        "strongest_nb1": strongest_nb1,
        "strongest_opakb1": float(getattr(strongest, "opakb1", 0.0)) if strongest is not None else 0.0,
        "ranked_strong_line_bin_count": n_ranked_line_bins,
        "bin4063_ranked_line_candidate_count": bin4063_ranked_line_count,
        "bin4063_has_ranked_line_candidates": bool(bin4063_ranked_line_count > 0),
    })
    for name, arr in (
        ("opakc", workspace.opakc),
        ("opakcont", workspace.opakcont),
        ("oplin", workspace.oplin_physical),
        ("opakab", workspace.opakab_physical),
        ("dpthc", workspace.dpthc),
        ("dpthcont", workspace.dpthcont),
        ("tau0", workspace.tau0),
        ("tauc", workspace.tauc),
    ):
        opacity_rows.append(_summarize_array(name, arr, row_kind="opacity_attenuation", pass_index=pass_index, zone_index=zone_index, phase="after_shell"))
    for name, arr in (
        ("incident_zrems_row1", workspace.zrems[0]),
        ("transmitted_zrems_row2", workspace.zrems[1]),
        ("emit_inward_zrems_row3", workspace.zrems[2]),
        ("emit_outward_zrems_row4", workspace.zrems[3]),
        ("zremso_emit_outward_row4", workspace.zremso[3]),
        ("line_emit_outward_elum_row1", workspace.elum[0]),
        ("rrc_emit_outward_elumab_row1", workspace.elumab[0]),
    ):
        spectrum_rows.append(_summarize_array(name, arr, row_kind="spectrum_accumulation", pass_index=pass_index, zone_index=zone_index, phase="after_shell"))
    row_write_rows.append({
        "pass_index": int(pass_index),
        "zone_index": int(zone_index),
        "source_order_row_kind": "python_after_shell",
        "expected_pprint_rows_so_far": len(row_write_rows) + 1,
        "radius_cm": float(state.transfer.radius),
        "delta_r_cm": float(state.transfer.step_size),
        "column_cm2": float(state.transfer.column),
        "numrec_control": int(state.control.get("numrec", 0)),
        "legacy_pprint_enabled": bool(state.control.get("pprint_legacy_enabled", False)),
    })


def write_python_runtime_radial_spectrum_diagnostics(state: Any, out_dir: str | Path) -> dict[str, str]:
    """Write Python runtime radial/spectrum diagnostic rows captured during 142."""
    base = Path(out_dir) / "radial_spectrum_diagnostics_v0500"
    data = state.outputs.get("radial_spectrum_parity_v0500", {})
    products: dict[str, str] = {}
    tables = {
        "python_radial_stepping_csv": data.get("radial_stepping_rows", []),
        "python_step_f90_zone_probe_csv": data.get("step_probe_rows", []),
        "python_opacity_attenuation_summary_csv": data.get("opacity_summary_rows", []),
        "python_spectrum_accumulation_summary_csv": data.get("spectrum_accumulation_rows", []),
        "python_row_write_trace_csv": data.get("row_write_rows", []),
    }
    for key, rows in tables.items():
        path = base / (key.removesuffix("_csv") + ".csv")
        _write_csv(path, list(rows))
        products[key] = str(path)
    return products


def compare_radial_spectrum_products(
    original_dir: str | Path,
    python_dir: str | Path,
    *,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compare radial row history and spectrum products from existing outputs."""
    original = Path(original_dir)
    python = Path(python_dir)
    out = Path(out_dir) if out_dir is not None else python / "radial_spectrum_diagnostics_v0500"
    out.mkdir(parents=True, exist_ok=True)

    radial_rows = _abundance_rows(python / "xout_abund1.fits", "python") + _abundance_rows(original / "xout_abund1.fits", "xstar")
    radial_csv = out / "xout_abund1_radial_row_comparison.csv"
    _write_csv(radial_csv, radial_rows)

    spec_rows, spec_summary = _spectra_comparison_rows(python / "xout_spect1.fits", original / "xout_spect1.fits")
    spec_csv = out / "xout_spect1_emit_outward_comparison.csv"
    _write_csv(spec_csv, spec_rows)

    py_count = len([r for r in radial_rows if r.get("source") == "python"])
    xo_count = len([r for r in radial_rows if r.get("source") == "xstar"])
    row_summary = {
        "python_abundance_rows": int(py_count),
        "xstar_abundance_rows": int(xo_count),
        "row_count_match": bool(py_count == xo_count),
        "missing_python_intermediate_rows": max(0, xo_count - py_count),
    }
    summary = {
        "ready": True,
        "python_dir": str(python),
        "original_dir": str(original),
        "radial_row_summary": row_summary,
        "spectrum_summary": spec_summary,
        "products": {
            "radial_row_comparison_csv": str(radial_csv),
            "spectrum_emit_outward_comparison_csv": str(spec_csv),
        },
    }
    summary_path = out / "radial_spectrum_parity_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    summary["products"]["summary_json"] = str(summary_path)
    summary_rows = [{"section": "radial", **row_summary}, {"section": "spectrum", **spec_summary}]
    summary_csv = out / "radial_spectrum_parity_summary.csv"
    _write_csv(summary_csv, summary_rows)
    summary["products"]["summary_csv"] = str(summary_csv)
    return summary


__all__ = [
    "append_python_radial_shell_diagnostic",
    "write_python_runtime_radial_spectrum_diagnostics",
    "compare_radial_spectrum_products",
]
