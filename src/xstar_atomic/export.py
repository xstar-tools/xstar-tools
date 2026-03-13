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
        manifest["counts"]["emissivity_rows"] = len(emiss.get("emissivity", []))
        manifest["emissivity_summary"] = emiss.get("summary", {})

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
) -> dict:
    """Export a multi-ion CSV/JSON bundle for Athena++/superwind use."""
    ion_list = parse_ion_list(ions)
    with XSTARAtomic(fitsfile) as db:
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
    p.add_argument("--print-summary", action="store_true")
    args = p.parse_args(argv)

    wavelength = None
    if args.wavelength_min is not None or args.wavelength_max is not None:
        if args.wavelength_min is None or args.wavelength_max is None:
            raise SystemExit("Both --wavelength-min and --wavelength-max are required when selecting a wavelength range")
        wavelength = (args.wavelength_min, args.wavelength_max)

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
    )
    if args.print_summary:
        print(json.dumps(bundle, indent=2))


if __name__ == "__main__":
    main()
