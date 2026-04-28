#!/usr/bin/env python3
"""Run the O VII density-grid source-fit diagnostic with density-dependent XSTAR references.

This is a convenience front end for ``examples/21_o7_solver_source_fit_density_grid.py``.
It is intended for the case where separate XSTAR ``xout_lines1.fits`` products
have already been converted to per-density triplet line CSV files.  Instead of
reusing one low-density XSTAR R/G target at all densities, each density is fitted
and validated against its own XSTAR reference.

Reference mapping can be supplied either as repeated ``DENSITY:CSV`` values::

    --xstar-lines-csv-by-density 1:xstar_o7_ne1_lines.csv \
    --xstar-lines-csv-by-density 1e10:xstar_o7_ne1e10_lines.csv

or as a CSV table::

    --auto-xstar-test-run-grid

The mapping CSV should contain a density column such as ``electron_density_cm^-3``,
``density``, or ``ne``, plus a path column such as ``xstar_lines_csv`` or
``path``.  Optional columns are ``xstar_value_column`` and ``xstar_target_label``.

The fitted source weights remain empirical/diagnostic, not physical
level-resolved recombination rates.
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path
from typing import Sequence, List


def _has_option(argv: Sequence[str], *names: str) -> bool:
    return any(arg in names or any(arg.startswith(name + "=") for name in names) for arg in argv)


def _get_option_value(argv: Sequence[str], name: str, default: str | None = None) -> str | None:
    prefix = name + "="
    for i, arg in enumerate(argv):
        if arg == name and i + 1 < len(argv):
            return str(argv[i + 1])
        if str(arg).startswith(prefix):
            return str(arg)[len(prefix):]
    return default


def _density_tag_for_path(density: float) -> str:
    mapping = {1.0: "ne1", 1.0e4: "ne1e4", 1.0e8: "ne1e8", 1.0e10: "ne1e10", 1.0e12: "ne1e12"}
    for key, tag in mapping.items():
        if abs(float(density) - key) <= max(1e-12 * max(abs(key), 1.0), 1e-9):
            return tag
    text = f"{float(density):.12g}".replace("+", "")
    return "ne" + text.replace(".", "p")


def _find_csv_density_column(row: dict) -> str | None:
    for key in ("electron_density_cm^-3", "electron_density_cm-3", "electron_density", "density", "ne"):
        if key in row and str(row[key]).strip():
            return key
    return None


def _repair_stale_helike_grid_csv(path: Path, argv: Sequence[str]) -> None:
    """Repair old candidate-ion mapping CSVs that still point to O VII placeholders.

    v0.2.87 could leave ``xstar_c5_density_grid_references.csv`` style files
    pointing to ``xstar_test_run/xstar_o7_triplet_lines.csv``.  If the expected
    per-density converted He-like triplet CSVs already exist, repair the mapping
    in place and keep a ``.bak`` copy.
    """
    element = _get_option_value(argv, "--element", "O") or "O"
    stage_text = _get_option_value(argv, "--ion-stage", "7") or "7"
    try:
        stage = int(float(stage_text))
    except ValueError:
        return
    symbol = element.strip()
    tag = f"{symbol.lower()}{stage}"
    if symbol.upper() == "O" and stage == 7:
        return
    if not path.exists():
        return
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    if not rows:
        return
    changed = False
    for row in rows:
        dcol = _find_csv_density_column(row)
        if dcol is None:
            continue
        try:
            density = float(row[dcol])
        except ValueError:
            continue
        expected = Path("xstar_test_run") / f"{tag}_{_density_tag_for_path(density)}" / f"xstar_{tag}_triplet_lines.csv"
        current = str(row.get("xstar_lines_csv") or row.get("path") or "").strip()
        if current == str(expected):
            continue
        if expected.exists() and ("xstar_o7_triplet_lines.csv" in current or not Path(current).exists()):
            if "xstar_lines_csv" not in fieldnames:
                fieldnames.append("xstar_lines_csv")
            row["xstar_lines_csv"] = str(expected)
            if "xstar_value_column" in fieldnames or not row.get("xstar_value_column"):
                if "xstar_value_column" not in fieldnames:
                    fieldnames.append("xstar_value_column")
                row["xstar_value_column"] = "emit_outward"
            if "xstar_target_label" in fieldnames or not row.get("xstar_target_label"):
                if "xstar_target_label" not in fieldnames:
                    fieldnames.append("xstar_target_label")
                row["xstar_target_label"] = f"{symbol} {stage} XSTAR ne={density:.12g} cm^-3"
            changed = True
    if changed:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})
        print(f"Repaired stale He-like density-grid mapping CSV: {path}")
        print(f"Original mapping saved as: {backup}")


def discover_xstar_test_run_grid(base: Path = Path("xstar_test_run")) -> List[str]:
    """Return DENSITY:CSV specs for packaged converted O VII density-grid references.

    The package ships only compact converted XSTAR line CSVs under
    ``xstar_test_run/o7_ne*/``.  Solver-fit density-grid directories are
    generated outputs and are not required inputs.
    """
    entries = [
        (1.0, "o7_ne1"),
        (1.0e4, "o7_ne1e4"),
        (1.0e8, "o7_ne1e8"),
        (1.0e10, "o7_ne1e10"),
        (1.0e12, "o7_ne1e12"),
    ]
    specs: List[str] = []
    missing: List[str] = []
    for density, dirname in entries:
        path = base / dirname / "xstar_o7_triplet_lines.csv"
        if path.exists():
            specs.append(f"{density:.12g}:{path}")
        else:
            missing.append(str(path))
    if missing:
        raise SystemExit(
            "Could not auto-discover packaged O VII density-grid XSTAR references; missing: "
            + ", ".join(missing)
        )
    return specs


def write_xstar_grid_template(path: Path, densities: Sequence[float] = (1.0, 1.0e4, 1.0e8, 1.0e10, 1.0e12)) -> None:
    """Write a template density-to-XSTAR-lines mapping CSV.

    The template intentionally points to the packaged low-density O VII reference
    as a placeholder for every row.  Users should replace the path column with
    CSV files converted from density-specific XSTAR runs before using the grid
    for science validation.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "electron_density_cm^-3",
                "xstar_lines_csv",
                "xstar_value_column",
                "xstar_target_label",
                "note",
            ],
        )
        writer.writeheader()
        for density in densities:
            writer.writerow({
                "electron_density_cm^-3": f"{float(density):.12g}",
                "xstar_lines_csv": "xstar_test_run/xstar_o7_triplet_lines.csv",
                "xstar_value_column": "emit_outward",
                "xstar_target_label": f"PLACEHOLDER: replace with O VII XSTAR reference at ne={float(density):.6g} cm^-3",
                "note": "Template row; replace xstar_lines_csv with a density-specific converted XSTAR line CSV.",
            })


def print_template_message(path: Path) -> None:
    print(f"Wrote template XSTAR density-grid mapping: {path}")
    print("Edit this CSV so each density points to the correct converted XSTAR O VII line CSV, then rerun the command.")
    print("For a quick low-density-placeholder test only, pass --allow-placeholder-grid to continue with the template as written.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        add_help=False,
    )
    parser.add_argument("--help", action="store_true")
    parser.add_argument("--xstar-grid-summary-csv")
    parser.add_argument("--xstar-lines-csv-by-density", action="append", default=[])
    parser.add_argument("--write-template-grid-csv", help="Write a template density-to-XSTAR-lines CSV and exit")
    parser.add_argument("--auto-xstar-test-run-grid", action="store_true", help="Use packaged converted O VII density-specific XSTAR CSVs under xstar_test_run/o7_ne*/; these are compact inputs, while density-grid solver directories remain generated outputs")
    parser.add_argument("--allow-placeholder-grid", action="store_true", help="Allow running with an auto-created placeholder grid that reuses the packaged low-density O VII reference; diagnostic only")
    known, remaining = parser.parse_known_args()

    script = Path(__file__).resolve().with_name("21_o7_solver_source_fit_density_grid.py")
    if known.help:
        subprocess.run([sys.executable, str(script), "--help"], check=True)
        print("\nDensity-dependent XSTAR front end:")
        print("  Provide --auto-xstar-test-run-grid, --xstar-grid-summary-csv, or repeated --xstar-lines-csv-by-density DENSITY:CSV.")
        print("  Preferred packaged-input mode: --auto-xstar-test-run-grid")
        print("  To create a starter CSV, run: --write-template-grid-csv xstar_test_run/xstar_o7_density_grid_references.template.csv")
        return

    if known.write_template_grid_csv:
        template_path = Path(known.write_template_grid_csv)
        write_xstar_grid_template(template_path)
        print_template_message(template_path)
        return

    if known.auto_xstar_test_run_grid or (not known.xstar_grid_summary_csv and not known.xstar_lines_csv_by_density):
        auto_specs = discover_xstar_test_run_grid()
        known.xstar_lines_csv_by_density.extend(auto_specs)
        if not known.auto_xstar_test_run_grid:
            print("Auto-discovered packaged O VII density-grid XSTAR references under xstar_test_run/o7_ne*/.")

    cmd = [sys.executable, str(script)] + remaining
    if known.xstar_grid_summary_csv:
        grid_path = Path(known.xstar_grid_summary_csv)
        _repair_stale_helike_grid_csv(grid_path, remaining)
        if not grid_path.exists():
            write_xstar_grid_template(grid_path)
            print_template_message(grid_path)
            if not known.allow_placeholder_grid:
                raise SystemExit(
                    f"XSTAR density-grid mapping CSV was missing, so a template was written to {grid_path}. "
                    "Edit it with real density-specific XSTAR CSV paths and rerun, or pass "
                    "--allow-placeholder-grid for a low-density-placeholder smoke test only."
                )
            print("WARNING: continuing with placeholder grid that reuses the low-density O VII XSTAR reference at all densities.")
        cmd += ["--xstar-grid-summary-csv", known.xstar_grid_summary_csv]
    for item in known.xstar_lines_csv_by_density:
        cmd += ["--xstar-lines-csv-by-density", item]
    if not _has_option(cmd, "--out-dir"):
        cmd += ["--out-dir", "o7_solver_source_fit_density_xstar_grid"]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
