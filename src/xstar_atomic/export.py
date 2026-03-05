#!/usr/bin/env python3
"""Export decoded XSTAR atomic data for superwind/Athena++ workflows.

This module provides a lightweight export layer on top of the high-level
:class:`xstar_atomic.api.XSTARAtomic` interface.  It is intended for building
compact, versioned tables that can be consumed by Athena++/superwind
post-processing scripts without repeatedly scanning the full packed
``atdb.fits`` database.

The first implementation writes CSV and JSON products and keeps the scope
explicit: users select the ions and wavelength/temperature ranges to export.
Large all-database exports should be done in smaller chunks.
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
) -> dict:
    """Export compact decoded products for one ion.

    Products are written under ``out_dir`` with filenames beginning with a
    normalized ion slug.  The returned manifest describes all written files.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = ion_slug(ion)
    manifest: dict = {
        "ion": ion,
        "slug": slug,
        "temperatures_K": list(temperatures),
        "wavelength_A": list(wavelength) if wavelength is not None else None,
        "electron_density_for_lmixing_cm^-3": electron_density_for_lmixing,
        "files": {},
        "counts": {},
    }

    levels = db.levels(ion)
    level_path = out_dir / f"{slug}_levels.csv"
    write_csv(level_path, levels)
    manifest["files"]["levels_csv"] = str(level_path)
    manifest["counts"]["levels"] = len(levels)

    lines = db.lines(ion, wavelength=wavelength)
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
    coll_path = out_dir / f"{slug}_collisions.csv"
    coll_eval_path = out_dir / f"{slug}_collision_rates.csv"
    write_csv(coll_path, collisions.get("summary", []))
    write_csv(coll_eval_path, collisions.get("evaluated", []))
    manifest["files"]["collisions_csv"] = str(coll_path)
    manifest["files"]["collision_rates_csv"] = str(coll_eval_path)
    manifest["counts"]["collision_records"] = len(collisions.get("summary", []))
    manifest["counts"]["collision_rate_rows"] = len(collisions.get("evaluated", []))
    if "grid" in collisions:
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
    pi_path = out_dir / f"{slug}_photoionization.csv"
    write_csv(pi_path, pi_summary)
    manifest["files"]["photoionization_csv"] = str(pi_path)
    manifest["counts"]["photoionization_records"] = len(pi_summary)
    if include_photoionization_grid:
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
        emiss_path = out_dir / f"{slug}_emissivity.csv"
        write_csv(emiss_path, emiss.get("emissivity", []))
        manifest["files"]["emissivity_csv"] = str(emiss_path)
        manifest["counts"]["emissivity_rows"] = len(emiss.get("emissivity", []))
        manifest["emissivity_summary"] = emiss.get("summary", {})

    manifest_path = out_dir / f"{slug}_manifest.json"
    write_json(manifest_path, manifest)
    manifest["files"]["manifest_json"] = str(manifest_path)
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
        "manifests": manifests,
    }
    write_json(Path(out_dir) / "superwind_export_manifest.json", bundle)
    return bundle


def main(argv: Sequence[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Export decoded XSTAR atomic products for superwind/Athena++ post-processing.")
    p.add_argument("fitsfile")
    p.add_argument("--ions", required=True, help="Comma-separated ion list, e.g. 'O VIII,Ne IX,Fe XXVI'.")
    p.add_argument("--out-dir", default="xstar_atomic_superwind_export")
    p.add_argument("--temperatures", nargs="+", type=float, default=[1e6])
    p.add_argument("--wavelength-min", type=float)
    p.add_argument("--wavelength-max", type=float)
    p.add_argument("--electron-density-for-lmixing", type=float, default=1.0)
    p.add_argument("--include-photoionization-grid", action="store_true")
    p.add_argument("--no-emissivity", action="store_true", help="Skip emissivity-table export.")
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
    )
    if args.print_summary:
        print(json.dumps(bundle, indent=2))


if __name__ == "__main__":
    main()
