"""Post-run diagnostics for original-XSTAR/Python physical output mismatches.

The comparator answers whether a product contract passes.  This module answers
where the first physically useful differences are, using only independently
written products.  It never feeds original XSTAR data back into the Python
calculation.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
from astropy.io import fits


_REQUIRED = (
    "xo01_detail.fits",
    "xo01_detal2.fits",
    "xo01_detal3.fits",
    "xo01_detal4.fits",
    "xout_abund1.fits",
    "xout_spect1.fits",
    "xout_lines1.fits",
    "xout_cont1.fits",
    "xout_rrc1.fits",
    "xout_step.log",
)


@dataclass(frozen=True)
class PhysicalMismatchDiagnosis:
    original_dir: Path
    python_dir: Path
    output_dir: Path
    summary: Mapping[str, Any]
    products: Mapping[str, Path]

    def as_dict(self) -> dict[str, Any]:
        return {
            "original_dir": str(self.original_dir),
            "python_dir": str(self.python_dir),
            "output_dir": str(self.output_dir),
            "summary": dict(self.summary),
            "products": {key: str(value) for key, value in self.products.items()},
        }


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("latin-1", errors="replace").strip()
    return str(value).strip()


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _fits_structure(path: Path) -> tuple[int, list[int]]:
    with fits.open(path, memmap=True) as hdus:
        rows = []
        for hdu in hdus:
            data = hdu.data
            rows.append(0 if data is None or not hasattr(data, "__len__") else len(data))
        return len(hdus), rows


def _column(data: Any, *names: str) -> np.ndarray | None:
    available = {str(name).lower(): str(name) for name in data.names}
    for name in names:
        actual = available.get(name.lower())
        if actual is not None:
            return np.asarray(data[actual])
    return None


def _first_zone_thermal(path: Path) -> dict[str, float]:
    result: dict[str, float] = {}
    with fits.open(path, memmap=True) as hdus:
        abund = hdus["ABUNDANCES"].data
        if len(abund):
            result["temperature_1e4K"] = float(_column(abund, "temperature")[0])
            result["temperature_K"] = 1.0e4 * result["temperature_1e4K"]
            result["electron_fraction"] = float(_column(abund, "x_e")[0])
            result["hydrogen_density_cm3"] = float(_column(abund, "n_p")[0])
        aliases = {
            "hydrogen": ("hydrogen", "H"),
            "helium": ("helium", "He"),
            "carbon": ("carbon", "C"),
            "compton": ("compton",),
            "brems": ("brems",),
            "total": ("total",),
        }
        for extension, prefix in (("HEATING", "heating"), ("COOLING", "cooling")):
            data = hdus[extension].data
            if not len(data):
                continue
            for canonical, names in aliases.items():
                values = _column(data, *names)
                if values is not None:
                    result[f"{prefix}_{canonical}"] = float(values[0])
    return result


def _product_structure(original: Path, python: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for filename in _REQUIRED:
        op = original / filename
        pp = python / filename
        row: dict[str, Any] = {
            "filename": filename,
            "original_present": op.is_file(),
            "python_present": pp.is_file(),
        }
        if filename.endswith(".fits") and op.is_file() and pp.is_file():
            oh, orows = _fits_structure(op)
            ph, prows = _fits_structure(pp)
            row.update(
                original_hdu_count=oh,
                python_hdu_count=ph,
                original_rows=";".join(str(value) for value in orows),
                python_rows=";".join(str(value) for value in prows),
                structure_match=bool(oh == ph and orows == prows),
            )
        rows.append(row)
    return rows


def _top_first_zone_lines(path: Path, *, limit: int = 30) -> list[dict[str, Any]]:
    with fits.open(path, memmap=True) as hdus:
        data = hdus[2].data
        inward = np.asarray(data["emis_inward"], dtype=float)
        outward = np.asarray(data["emis_outward"], dtype=float)
        strength = np.abs(inward) + np.abs(outward)
        order = np.argsort(strength)[::-1][: min(limit, strength.size)]
        rows: list[dict[str, Any]] = []
        for pos in order:
            rows.append(
                {
                    "rank": len(rows) + 1,
                    "index": int(data["index"][pos]),
                    "ion": _text(data["ion"][pos]),
                    "lower_level": _text(data["lower_level"][pos]),
                    "upper_level": _text(data["upper_level"][pos]),
                    "wavelength_angstrom": float(data["wavelength"][pos]),
                    "emis_inward": float(inward[pos]),
                    "emis_outward": float(outward[pos]),
                    "absolute_emission_sum": float(strength[pos]),
                }
            )
        return rows


def _level_population_differences(
    original: Path,
    python: Path,
    *,
    limit: int = 100,
    python_population_index_offset: int = 0,
) -> list[dict[str, Any]]:
    with fits.open(original, memmap=True) as oh, fits.open(python, memmap=True) as ph:
        od = oh[2].data
        pd = ph[2].data
        original_by_index = {int(row["index"]): row for row in od}
        python_by_index = {int(row["index"]): row for row in pd}
        rows: list[dict[str, Any]] = []
        for index in sorted(original_by_index):
            python_source_index = index + int(python_population_index_offset)
            if python_source_index not in python_by_index:
                continue
            o = original_by_index[index]
            p = python_by_index[python_source_index]
            ov = float(o["population"])
            pv = float(p["population"])
            ratio = abs(pv) / max(abs(ov), 1.0e-300)
            rows.append(
                {
                    "index": index,
                    "python_population_source_index": python_source_index,
                    "original_ion": _text(o["ion"]),
                    "python_ion": _text(p["ion"]),
                    "original_level": _text(o["ion_level"]),
                    "python_level": _text(p["ion_level"]),
                    "original_upper_index": int(o["upper index"]),
                    "python_upper_index": int(p["upper index"]),
                    "original_population": ov,
                    "python_population": pv,
                    "absolute_ratio_python_over_original": ratio,
                    "label_match": bool(
                        _text(o["ion"]) == _text(p["ion"])
                        and _text(o["ion_level"]) == _text(p["ion_level"])
                    ),
                    "python_population_index_offset": int(python_population_index_offset),
                }
            )
        rows.sort(key=lambda row: row["absolute_ratio_python_over_original"], reverse=True)
        return rows[:limit]


def diagnose_physical_output_mismatch(
    original_dir: str | Path,
    python_dir: str | Path,
    *,
    output_dir: str | Path,
    python_detail_guard_shift: bool = False,
    state: Any | None = None,
) -> PhysicalMismatchDiagnosis:
    """Write compact structural, thermal, line, and level mismatch reports."""
    original = Path(original_dir).resolve()
    python = Path(python_dir).resolve()
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)

    internal_products: dict[str, Path] = {}
    internal_summary: dict[str, Any] = {}
    if state is not None:
        compact = state.control.get("physical_dsec_compact_diagnostics", {})
        evaluation_rows = list(compact.get("evaluations", ()))
        cooling_rows = list(compact.get("carbon_cooling_terms", ()))
        shell_rows = list(compact.get("shells", ()))
        if evaluation_rows:
            path = output / "python_dsec_evaluations.csv"
            fields = [
                "pass_index", "zone_index", "evaluation_index",
                "temperature_K", "temperature_t4", "electron_fraction_xee",
                "elcter", "hmctot", "httot", "cltot",
                "carbon_heating", "carbon_cooling", "carbon_heating2",
                "carbon_cooling2", "carbon_solver_converged",
                "carbon_solver_method", "carbon_dense_rank",
                "carbon_dense_condition_number",
                "carbon_max_active_relative_row_residual",
                "carbon_normalization_error",
            ] + [f"carbon_stage_{stage}_fraction" for stage in range(1, 8)] + [
                "dsec_lnerr", "dsec_ntotit"
            ]
            _write_csv(path, evaluation_rows, fields)
            internal_products["python_dsec_evaluations_csv"] = path
        if cooling_rows:
            path = output / "python_dsec_carbon_top_cooling_terms.csv"
            _write_csv(
                path,
                cooling_rows,
                [
                    "pass_index", "zone_index", "evaluation_index", "rank",
                    "temperature_K", "hmctot", "record", "data_type",
                    "rate_type", "compact_row", "population", "cj",
                    "contribution_per_abundance", "physical_contribution",
                    "idest1", "idest2", "lower_endpoint", "upper_endpoint",
                    "row_roles_json",
                ],
            )
            internal_products["python_dsec_carbon_top_cooling_terms_csv"] = path
        if shell_rows:
            path = output / "python_dsec_shell_summary.json"
            path.write_text(
                json.dumps(shell_rows, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            internal_products["python_dsec_shell_summary_json"] = path
        internal_summary = {
            "python_dsec_shell_count": len(shell_rows),
            "python_dsec_evaluation_count": len(evaluation_rows),
            "python_dsec_carbon_cooling_term_count": len(cooling_rows),
        }

    structure = _product_structure(original, python)
    original_thermal = _first_zone_thermal(original / "xout_abund1.fits")
    python_thermal = _first_zone_thermal(python / "xout_abund1.fits")
    thermal_rows: list[dict[str, Any]] = []
    for key in sorted(set(original_thermal) | set(python_thermal)):
        ov = original_thermal.get(key, float("nan"))
        pv = python_thermal.get(key, float("nan"))
        thermal_rows.append(
            {
                "quantity": key,
                "original": ov,
                "python": pv,
                "python_over_original": pv / ov if np.isfinite(ov) and ov != 0.0 else float("nan"),
                "difference": pv - ov,
            }
        )
    top_lines = _top_first_zone_lines(python / "xo01_detal2.fits")
    levels = _level_population_differences(
        original / "xo01_detail.fits", python / "xo01_detail.fits"
    )
    corrected_levels = (
        _level_population_differences(
            original / "xo01_detail.fits",
            python / "xo01_detail.fits",
            python_population_index_offset=1,
        )
        if python_detail_guard_shift
        else []
    )

    structure_csv = output / "product_structure.csv"
    thermal_csv = output / "first_zone_thermal_comparison.csv"
    lines_csv = output / "top_python_first_zone_lines.csv"
    levels_csv = output / "largest_first_zone_level_population_ratios.csv"
    corrected_levels_csv = output / "guard_corrected_first_zone_level_population_ratios.csv"
    _write_csv(
        structure_csv,
        structure,
        [
            "filename", "original_present", "python_present", "original_hdu_count",
            "python_hdu_count", "original_rows", "python_rows", "structure_match",
        ],
    )
    _write_csv(
        thermal_csv,
        thermal_rows,
        ["quantity", "original", "python", "python_over_original", "difference"],
    )
    _write_csv(
        lines_csv,
        top_lines,
        [
            "rank", "index", "ion", "lower_level", "upper_level",
            "wavelength_angstrom", "emis_inward", "emis_outward",
            "absolute_emission_sum",
        ],
    )
    _write_csv(
        levels_csv,
        levels,
        [
            "index", "python_population_source_index", "original_ion", "python_ion",
            "original_level", "python_level", "original_upper_index", "python_upper_index",
            "original_population", "python_population", "absolute_ratio_python_over_original",
            "label_match", "python_population_index_offset",
        ],
    )
    if python_detail_guard_shift:
        _write_csv(
            corrected_levels_csv,
            corrected_levels,
            [
                "index", "python_population_source_index", "original_ion", "python_ion",
                "original_level", "python_level", "original_upper_index", "python_upper_index",
                "original_population", "python_population",
                "absolute_ratio_python_over_original", "label_match",
                "python_population_index_offset",
            ],
        )

    carbon_original = original_thermal.get("cooling_carbon", float("nan"))
    carbon_python = python_thermal.get("cooling_carbon", float("nan"))
    carbon_ratio = (
        carbon_python / carbon_original
        if np.isfinite(carbon_original) and carbon_original != 0.0
        else float("nan")
    )
    summary: dict[str, Any] = {
        "all_products_present": all(
            bool(row["original_present"] and row["python_present"]) for row in structure
        ),
        "all_fits_structures_match": all(
            bool(row.get("structure_match", True)) for row in structure
        ),
        "original_first_zone_temperature_K": original_thermal.get("temperature_K"),
        "python_first_zone_temperature_K": python_thermal.get("temperature_K"),
        "original_first_zone_carbon_cooling": carbon_original,
        "python_first_zone_carbon_cooling": carbon_python,
        "carbon_cooling_python_over_original": carbon_ratio,
        "dominant_python_first_zone_line": top_lines[0] if top_lines else None,
        "largest_level_population_ratio": levels[0] if levels else None,
        "python_detail_guard_shift_applied": bool(python_detail_guard_shift),
        "largest_guard_corrected_level_population_ratio": (
            corrected_levels[0] if corrected_levels else None
        ),
        **internal_summary,
        "interpretation": (
            "Structural radial-record differences and the first-zone thermal solution must be "
            "closed before final spectral rows can match.  The ranked line and level tables "
            "identify the dominant local-physics mismatch without using original products as "
            "Python calculation inputs."
        ),
    }
    summary_json = output / "physical_parity_diagnosis.json"
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = output / "physical_parity_diagnosis.md"
    dominant = summary["dominant_python_first_zone_line"] or {}
    largest = summary["largest_level_population_ratio"] or {}
    corrected_largest = summary["largest_guard_corrected_level_population_ratio"] or {}
    md.write_text(
        "# Physical parity diagnosis\n\n"
        f"- Original directory: `{original}`\n"
        f"- Python directory: `{python}`\n"
        f"- FITS structures all match: `{summary['all_fits_structures_match']}`\n"
        f"- Original first-zone temperature: `{summary['original_first_zone_temperature_K']:.9e}` K\n"
        f"- Python first-zone temperature: `{summary['python_first_zone_temperature_K']:.9e}` K\n"
        f"- Carbon cooling ratio (Python/original): `{carbon_ratio:.9e}`\n"
        f"- Dominant Python first-zone line: index `{dominant.get('index')}`, "
        f"`{dominant.get('ion')}` `{dominant.get('lower_level')}` → "
        f"`{dominant.get('upper_level')}`, wavelength "
        f"`{dominant.get('wavelength_angstrom')}` Å, absolute emission "
        f"`{dominant.get('absolute_emission_sum')}`\n"
        f"- Largest matched-index population ratio: index `{largest.get('index')}`, "
        f"Python/original `{largest.get('absolute_ratio_python_over_original')}`; "
        f"label match `{largest.get('label_match')}`\n"
        f"- Guard-corrected largest population ratio: index "
        f"`{corrected_largest.get('index')}`, Python/original "
        f"`{corrected_largest.get('absolute_ratio_python_over_original')}` "
        f"(applied: `{python_detail_guard_shift}`)\n\n"
        "The CSV files in this directory contain the complete compact diagnosis.\n",
        encoding="utf-8",
    )

    products = {
        "summary_json": summary_json,
        "summary_markdown": md,
        "product_structure_csv": structure_csv,
        "thermal_comparison_csv": thermal_csv,
        "top_python_lines_csv": lines_csv,
        "level_population_ratios_csv": levels_csv,
    }
    if python_detail_guard_shift:
        products["guard_corrected_level_population_ratios_csv"] = corrected_levels_csv
    products.update(internal_products)
    return PhysicalMismatchDiagnosis(original, python, output, summary, products)
