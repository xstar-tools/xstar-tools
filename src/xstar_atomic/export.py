#!/usr/bin/env python3
"""Export decoded XSTAR atomic data for superwind/Athena++ workflows.

This module provides a lightweight export layer on top of the high-level
:class:`xstar_atomic.api.XSTARAtomic` interface.  It is intended for building
compact, versioned tables that can be consumed by Athena++/superwind
post-processing scripts without repeatedly scanning the full packed
``atdb.fits`` database.

The exporter writes CSV, optional HDF5, and JSON manifest products.
Users select the ions and wavelength/temperature ranges to export.
Large all-database exports should be done in smaller chunks.  The same
interface is intended for superwind, AGN outflow, and other plasma
post-processing workflows.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Iterable, Sequence

from .api import XSTARAtomic, parse_ion


def _flatten_rows(rows):
    out = []
    for row in rows or []:
        rr = {}
        for k, v in dict(row).items():
            if isinstance(v, (list, dict, tuple)):
                rr[k] = json.dumps(v)
            else:
                rr[k] = v
        out.append(rr)
    return out


def write_csv(path: str | Path, rows: Sequence[dict]) -> None:
    """Write a list of dictionaries to CSV.

    Parameters
    ----------
    path:
        Output filename.
    rows:
        Sequence of row dictionaries.  Nested list/dict values are stored as
        JSON strings.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _flatten_rows(rows)
    fields: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_json(path: str | Path, obj) -> None:
    """Write JSON output with stable indentation."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=False), encoding="utf-8")


def _is_number_like(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(value)
        return True
    except Exception:
        return False


def write_hdf5_rows(path: str | Path, group_name: str, rows: Sequence[dict], *, metadata: dict | None = None) -> None:
    """Append a row-dictionary table to an HDF5 file.

    Each key becomes a dataset under ``group_name``.  Numeric columns are
    stored as floating-point arrays when all non-empty values are numeric;
    otherwise the column is stored as UTF-8 strings.  This conservative
    representation is easy for post-processing codes to read and preserves
    all CSV columns.

    Parameters
    ----------
    path:
        HDF5 output filename.
    group_name:
        Name of the group to create or replace.
    rows:
        Sequence of row dictionaries.
    metadata:
        Optional group attributes.
    """
    try:
        import h5py
        import numpy as np
    except Exception as exc:  # pragma: no cover - exercised when h5py is absent
        raise RuntimeError("HDF5 export requires h5py and numpy") from exc

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _flatten_rows(rows)

    fields: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fields.append(key)

    with h5py.File(path, "a") as h5:
        if group_name in h5:
            del h5[group_name]
        grp = h5.create_group(group_name)
        grp.attrs["n_rows"] = len(rows)
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (dict, list, tuple)):
                    grp.attrs[key] = json.dumps(value)
                elif value is None:
                    grp.attrs[key] = ""
                else:
                    grp.attrs[key] = value
        str_dtype = h5py.string_dtype(encoding="utf-8")
        for field in fields:
            values = [row.get(field, "") for row in rows]
            nonempty = [v for v in values if v not in (None, "")]
            if nonempty and all(_is_number_like(v) for v in nonempty):
                arr = np.array([float(v) if v not in (None, "") else np.nan for v in values], dtype=float)
                grp.create_dataset(field, data=arr, compression="gzip")
            else:
                arr = np.array(["" if v is None else str(v) for v in values], dtype=object)
                grp.create_dataset(field, data=arr, dtype=str_dtype, compression="gzip")


def write_hdf5_manifest(path: str | Path, manifest: dict) -> None:
    """Store an export manifest JSON blob in an HDF5 file."""
    try:
        import h5py
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("HDF5 export requires h5py") from exc
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "a") as h5:
        if "manifest_json" in h5:
            del h5["manifest_json"]
        h5.create_dataset("manifest_json", data=json.dumps(manifest, indent=2))


def parse_ion_list(values: Sequence[str] | str) -> list[str]:
    """Normalize an ion list from CLI/API inputs.

    Examples
    --------
    ``"O VIII,Ne IX"`` -> ``["O VIII", "Ne IX"]``.
    """
    if isinstance(values, str):
        raw = values.split(",")
    else:
        raw = []
        for value in values:
            raw.extend(str(value).split(","))
    return [v.strip() for v in raw if v.strip()]




def parse_band_specs(values: Sequence[str] | str | None) -> list[dict]:
    """Parse X-ray band specifications.

    Parameters
    ----------
    values:
        Band specifications in the form ``name:emin:emax`` where energies are
        in keV.  A comma-separated string or a list of strings is accepted.

    Returns
    -------
    list of dict
        Dictionaries with ``band_name``, ``energy_min_keV`` and
        ``energy_max_keV``.

    Examples
    --------
    ``"soft:0.5:2.0,hard:2.0:10.0"`` or
    ``["soft:0.5:2.0", "hard:2.0:10.0"]``.
    """
    if not values:
        return []
    if isinstance(values, str):
        raw = []
        for chunk in values.split(","):
            raw.extend(chunk.split())
    else:
        raw = []
        for value in values:
            raw.extend(str(value).split(","))
    bands: list[dict] = []
    for spec in raw:
        spec = spec.strip()
        if not spec:
            continue
        parts = spec.split(":")
        if len(parts) != 3:
            raise ValueError(f"Band specification must be name:emin:emax, got {spec!r}")
        name, emin, emax = parts
        try:
            emin_f = float(emin)
            emax_f = float(emax)
        except ValueError as exc:
            raise ValueError(f"Band energies must be numeric in {spec!r}") from exc
        if not name:
            raise ValueError(f"Band name is empty in {spec!r}")
        if emax_f <= emin_f:
            raise ValueError(f"Band maximum energy must be greater than minimum in {spec!r}")
        bands.append({"band_name": name, "energy_min_keV": emin_f, "energy_max_keV": emax_f})
    return bands


def _safe_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def compute_band_emissivity_rows(emissivity_rows: Sequence[dict], bands: Sequence[dict]) -> list[dict]:
    """Aggregate line emissivity rows into broad energy bands.

    The returned coefficients are still local coefficients per ``n_e n_ion``.
    Rows with missing/null emissivity coefficients are ignored.  Energies are
    selected using the line photon energy in keV.
    """
    if not bands:
        return []
    by_temp: dict[float, list[dict]] = {}
    for row in emissivity_rows or []:
        temp = _safe_float(row.get("temperature_K"))
        if temp is None:
            continue
        by_temp.setdefault(temp, []).append(row)

    out: list[dict] = []
    for temp in sorted(by_temp):
        rows_t = by_temp[temp]
        # Preserve ion metadata even for bands with zero selected lines.  This
        # keeps CSV/HDF5 band products easy to ingest in downstream simulation
        # post-processing without special handling for blank ion names.
        ions_for_temperature = sorted({str(row.get("ion", "")) for row in rows_t if row.get("ion")})
        ion_label_for_temperature = (
            ions_for_temperature[0]
            if len(ions_for_temperature) == 1
            else ",".join(ions_for_temperature)
        )
        for band in bands:
            emin = float(band["energy_min_keV"])
            emax = float(band["energy_max_keV"])
            selected = []
            for row in rows_t:
                energy = _safe_float(row.get("energy_keV"))
                if energy is None:
                    wave = _safe_float(row.get("wavelength_A"))
                    if wave and wave > 0:
                        energy = 12.398419843320026 / wave
                if energy is None or not (emin <= energy < emax):
                    continue
                e_coeff = _safe_float(row.get("line_energy_emissivity_coeff_erg_cm3_s"))
                p_coeff = _safe_float(row.get("line_photon_emissivity_coeff_cm3_s"))
                if e_coeff is None and p_coeff is None:
                    continue
                selected.append((row, e_coeff or 0.0, p_coeff or 0.0))
            methods = sorted({str(row.get("collision_eval_method", "")) for row, _, _ in selected if row.get("collision_eval_method")})
            ions = sorted({str(row.get("ion", "")) for row, _, _ in selected if row.get("ion")})
            ion_label = (ions[0] if len(ions) == 1 else ",".join(ions)) or ion_label_for_temperature
            out.append({
                "ion": ion_label,
                "band_name": band["band_name"],
                "energy_min_keV": emin,
                "energy_max_keV": emax,
                "temperature_K": temp,
                "n_lines_in_band": len(selected),
                "energy_emissivity_coeff_erg_cm3_s": sum(v for _, v, _ in selected),
                "photon_emissivity_coeff_cm3_s": sum(v for _, _, v in selected),
                "methods_used": ",".join(methods) if methods else "none",
            })
    return out

def ion_slug(ion: str) -> str:
    """Return a filename-safe ion label such as ``o_viii``."""
    z, stage, symbol = parse_ion(ion)
    if symbol is None or stage is None:
        return str(ion).strip().lower().replace(" ", "_").replace("-", "_")
    # Use roman text if supplied by parse_ion users?  Importing here avoids a
    # top-level dependency in __init__.
    from .hierarchy import roman
    return f"{symbol.lower()}_{roman(stage).lower()}"


def export_ion_products(
    db: XSTARAtomic,
    ion: str,
    out_dir: str | Path,
    *,
    temperatures: Sequence[float] = (1e6,),
    wavelength: tuple[float, float] | None = None,
    electron_density_for_lmixing: float = 1.0,
    include_photoionization_grid: bool = False,
    make_emissivity: bool = True,
    formats: Sequence[str] = ("csv",),
    bands: Sequence[dict] | None = None,
) -> dict:
    """Export compact decoded products for one ion.

    Products are written under ``out_dir`` with filenames beginning with a
    normalized ion slug.  The returned manifest describes all written files.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    formats = tuple(str(f).lower() for f in formats)
    write_csv_products = "csv" in formats
    write_hdf5_products = "hdf5" in formats or "h5" in formats
    slug = ion_slug(ion)
    manifest: dict = {
        "ion": ion,
        "slug": slug,
        "temperatures_K": list(temperatures),
        "wavelength_A": list(wavelength) if wavelength is not None else None,
        "electron_density_for_lmixing_cm^-3": electron_density_for_lmixing,
        "formats": list(formats),
        "bands_keV": list(bands or []),
        "files": {},
        "counts": {},
    }

    levels = db.levels(ion)
    if write_csv_products:
        level_path = out_dir / f"{slug}_levels.csv"
        write_csv(level_path, levels)
        manifest["files"]["levels_csv"] = str(level_path)
    manifest["counts"]["levels"] = len(levels)

    lines = db.lines(ion, wavelength=wavelength)
    if write_csv_products:
        lines_path = out_dir / f"{slug}_lines.csv"
        write_csv(lines_path, lines)
        manifest["files"]["lines_csv"] = str(lines_path)
    manifest["counts"]["lines"] = len(lines)

    collisions = db.collisions(
        ion,
        temperatures=temperatures,
        wavelength=wavelength,
        electron_density_for_lmixing=electron_density_for_lmixing,
        include_grid=True,
    )
    if write_csv_products:
        coll_path = out_dir / f"{slug}_collisions.csv"
        coll_eval_path = out_dir / f"{slug}_collision_rates.csv"
        write_csv(coll_path, collisions.get("summary", []))
        write_csv(coll_eval_path, collisions.get("evaluated", []))
        manifest["files"]["collisions_csv"] = str(coll_path)
        manifest["files"]["collision_rates_csv"] = str(coll_eval_path)
    manifest["counts"]["collision_records"] = len(collisions.get("summary", []))
    manifest["counts"]["collision_rate_rows"] = len(collisions.get("evaluated", []))
    if "grid" in collisions:
        if write_csv_products:
            grid_path = out_dir / f"{slug}_collision_grids.csv"
            write_csv(grid_path, collisions.get("grid", []))
            manifest["files"]["collision_grids_csv"] = str(grid_path)
        manifest["counts"]["collision_grid_rows"] = len(collisions.get("grid", []))

    photo = db.photoionization(ion, include_grid=include_photoionization_grid)
    if isinstance(photo, dict):
        pi_summary = photo.get("summary", [])
        pi_grid = photo.get("grid", [])
    else:
        pi_summary = photo
        pi_grid = []
    if write_csv_products:
        pi_path = out_dir / f"{slug}_photoionization.csv"
        write_csv(pi_path, pi_summary)
        manifest["files"]["photoionization_csv"] = str(pi_path)
    manifest["counts"]["photoionization_records"] = len(pi_summary)
    if include_photoionization_grid:
        if write_csv_products:
            pi_grid_path = out_dir / f"{slug}_photoionization_grid.csv"
            write_csv(pi_grid_path, pi_grid)
            manifest["files"]["photoionization_grid_csv"] = str(pi_grid_path)
        manifest["counts"]["photoionization_grid_rows"] = len(pi_grid)

    band_rows: list[dict] = []
    if make_emissivity:
        emiss = db.emissivity(
            ion,
            wavelength=wavelength,
            temperatures=temperatures,
            electron_density_for_lmixing=electron_density_for_lmixing,
            include_unmatched_lines=True,
        )
        if write_csv_products:
            emiss_path = out_dir / f"{slug}_emissivity.csv"
            write_csv(emiss_path, emiss.get("emissivity", []))
            manifest["files"]["emissivity_csv"] = str(emiss_path)
        emiss_rows = emiss.get("emissivity", [])
        manifest["counts"]["emissivity_rows"] = len(emiss_rows)
        manifest["emissivity_summary"] = emiss.get("summary", {})
        band_rows = compute_band_emissivity_rows(emiss_rows, bands or [])
        if bands:
            manifest["counts"]["band_emissivity_rows"] = len(band_rows)
            if write_csv_products:
                band_path = out_dir / f"{slug}_band_emissivity.csv"
                write_csv(band_path, band_rows)
                manifest["files"]["band_emissivity_csv"] = str(band_path)

    if write_hdf5_products:
        h5_path = out_dir / f"{slug}_atomic.h5"
        h5_meta = {"ion": ion, "slug": slug, "temperatures_K": list(temperatures), "wavelength_A": list(wavelength) if wavelength is not None else None}
        write_hdf5_rows(h5_path, "levels", levels, metadata=h5_meta)
        write_hdf5_rows(h5_path, "lines", lines, metadata=h5_meta)
        write_hdf5_rows(h5_path, "collisions", collisions.get("summary", []), metadata=h5_meta)
        write_hdf5_rows(h5_path, "collision_rates", collisions.get("evaluated", []), metadata=h5_meta)
        if "grid" in collisions:
            write_hdf5_rows(h5_path, "collision_grids", collisions.get("grid", []), metadata=h5_meta)
        write_hdf5_rows(h5_path, "photoionization", pi_summary, metadata=h5_meta)
        if include_photoionization_grid:
            write_hdf5_rows(h5_path, "photoionization_grid", pi_grid, metadata=h5_meta)
        if make_emissivity:
            write_hdf5_rows(h5_path, "emissivity", emiss.get("emissivity", []), metadata=h5_meta)
            if bands:
                write_hdf5_rows(h5_path, "band_emissivity", band_rows, metadata={**h5_meta, "bands_keV": list(bands or [])})
        manifest["files"]["hdf5"] = str(h5_path)

    manifest_path = out_dir / f"{slug}_manifest.json"
    write_json(manifest_path, manifest)
    manifest["files"]["manifest_json"] = str(manifest_path)
    if write_hdf5_products:
        write_hdf5_manifest(manifest["files"]["hdf5"], manifest)
    return manifest


def export_superwind_bundle(
    fitsfile: str | Path,
    ions: Sequence[str] | str,
    out_dir: str | Path,
    *,
    temperatures: Sequence[float] = (1e6,),
    wavelength: tuple[float, float] | None = None,
    electron_density_for_lmixing: float = 1.0,
    include_photoionization_grid: bool = False,
    make_emissivity: bool = True,
    formats: Sequence[str] = ("csv",),
    bands: Sequence[dict] | None = None,
    index_cache: bool | str | Path = False,
    rebuild_index_cache: bool = False,
) -> dict:
    """Export a multi-ion CSV/JSON bundle for Athena++/superwind use."""
    ion_list = parse_ion_list(ions)
    with XSTARAtomic(fitsfile, index_cache=index_cache, rebuild_index_cache=rebuild_index_cache) as db:
        manifests = [
            export_ion_products(
                db,
                ion,
                out_dir,
                temperatures=temperatures,
                wavelength=wavelength,
                electron_density_for_lmixing=electron_density_for_lmixing,
                include_photoionization_grid=include_photoionization_grid,
                make_emissivity=make_emissivity,
                formats=formats,
                bands=bands,
            )
            for ion in ion_list
        ]
    bundle = {
        "fitsfile": str(fitsfile),
        "ions": ion_list,
        "out_dir": str(out_dir),
        "temperatures_K": list(temperatures),
        "wavelength_A": list(wavelength) if wavelength is not None else None,
        "electron_density_for_lmixing_cm^-3": electron_density_for_lmixing,
        "formats": list(formats),
        "bands_keV": list(bands or []),
        "index_cache_status": db.db.index_cache_status,
        "index_cache_path": str(db.db.index_cache_path) if db.db.index_cache_path is not None else None,
        "manifests": manifests,
    }
    write_json(Path(out_dir) / "atomic_export_manifest.json", bundle)
    # Backward-compatible manifest name from the first export implementation.
    write_json(Path(out_dir) / "superwind_export_manifest.json", bundle)
    if "hdf5" in [str(f).lower() for f in formats] or "h5" in [str(f).lower() for f in formats]:
        write_hdf5_manifest(Path(out_dir) / "atomic_export_manifest.h5", bundle)
    return bundle


def main(argv: Sequence[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Export decoded XSTAR atomic products for plasma post-processing workflows.")
    p.add_argument("fitsfile")
    p.add_argument("--ions", required=True, help="Comma-separated ion list, e.g. 'O VIII,Ne IX,Fe XXVI'.")
    p.add_argument("--out-dir", default="xstar_atomic_superwind_export")
    p.add_argument("--temperatures", nargs="+", type=float, default=[1e6])
    p.add_argument("--wavelength-min", type=float)
    p.add_argument("--wavelength-max", type=float)
    p.add_argument("--electron-density-for-lmixing", type=float, default=1.0)
    p.add_argument("--include-photoionization-grid", action="store_true")
    p.add_argument("--no-emissivity", action="store_true", help="Skip emissivity-table export.")
    p.add_argument("--formats", default="csv", help="Comma-separated output formats: csv, hdf5, or csv,hdf5")
    p.add_argument("--bands-kev", nargs="*", default=None,
                   help="Optional band specs name:emin:emax in keV, e.g. soft:0.5:2.0 hard:2.0:10.0")
    p.add_argument("--print-summary", action="store_true")
    p.add_argument("--index-cache", nargs="?", const=True, default=False,
                   help="Use an on-disk ATDB hierarchy index cache. Optionally provide a cache filename; default is atdb.fits.xstar_atomic_index.pkl")
    p.add_argument("--rebuild-index-cache", action="store_true",
                   help="Rebuild the ATDB hierarchy index cache before exporting")
    args = p.parse_args(argv)

    wavelength = None
    if args.wavelength_min is not None or args.wavelength_max is not None:
        if args.wavelength_min is None or args.wavelength_max is None:
            raise SystemExit("Both --wavelength-min and --wavelength-max are required when selecting a wavelength range")
        wavelength = (args.wavelength_min, args.wavelength_max)

    try:
        bands = parse_band_specs(args.bands_kev)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    bundle = export_superwind_bundle(
        args.fitsfile,
        args.ions,
        args.out_dir,
        temperatures=args.temperatures,
        wavelength=wavelength,
        electron_density_for_lmixing=args.electron_density_for_lmixing,
        include_photoionization_grid=args.include_photoionization_grid,
        make_emissivity=not args.no_emissivity,
        formats=[x.strip() for x in args.formats.split(",") if x.strip()],
        bands=bands,
        index_cache=args.index_cache,
        rebuild_index_cache=args.rebuild_index_cache,
    )
    if args.print_summary:
        print(json.dumps(bundle, indent=2))


if __name__ == "__main__":
    main()
