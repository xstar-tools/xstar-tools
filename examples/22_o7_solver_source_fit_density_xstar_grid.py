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




def _maybe_float(value) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _normalize_ion_text(text: str) -> str:
    return str(text or "").strip().lower().replace(" ", "").replace("_", "")


def _roman_stage(stage: int) -> str | None:
    return {
        1: "i", 2: "ii", 3: "iii", 4: "iv", 5: "v", 6: "vi", 7: "vii",
        8: "viii", 9: "ix", 10: "x", 11: "xi", 12: "xii", 13: "xiii",
        14: "xiv", 15: "xv", 16: "xvi", 17: "xvii", 18: "xviii", 19: "xix",
        20: "xx", 21: "xxi", 22: "xxii", 23: "xxiii", 24: "xxiv", 25: "xxv",
    }.get(int(stage))


def _expected_ion_aliases(element: str, stage: int) -> set[str]:
    symbol = str(element).strip().lower()
    aliases = {f"{symbol}{int(stage)}"}
    roman = _roman_stage(int(stage))
    if roman:
        aliases.add(f"{symbol}{roman}")
    return aliases


def _classify_helike_row(row: dict) -> str | None:
    lower = str(row.get("lower_level", "") or row.get("lower", "")).replace(" ", "")
    upper = str(row.get("upper_level", "") or row.get("upper", "")).replace(" ", "")
    if "1s2" not in lower:
        return None
    if "2s1.3S_1" in upper:
        return "f"
    if "2p1.1P_1" in upper:
        return "r"
    if "2p1.3P_" in upper:
        return "i"
    return None


def _triplet_csv_status(path: Path, element: str, stage: int, value_column: str = "emit_outward") -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    aliases = _expected_ion_aliases(element, stage)
    counts = {"f": 0, "i": 0, "r": 0}
    value_sums = {"f": 0.0, "i": 0.0, "r": 0.0}
    n_rows = 0
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            n_rows += 1
            ion_text = _normalize_ion_text(row.get("ion", ""))
            if ion_text and ion_text not in aliases:
                continue
            kind = _classify_helike_row(row)
            if kind is None:
                continue
            val = _maybe_float(row.get(value_column))
            if val is None:
                continue
            counts[kind] += 1
            value_sums[kind] += max(val, 0.0)
    if n_rows == 0:
        return False, "empty CSV: converter found zero matching XSTAR lines"
    missing_components = [name for name, key in [("forbidden", "f"), ("intercombination", "i"), ("resonance", "r")] if counts[key] == 0]
    if missing_components:
        return False, "missing He-like component(s): " + ", ".join(missing_components)
    zero_components = [name for name, key in [("forbidden", "f"), ("intercombination", "i"), ("resonance", "r")] if value_sums[key] <= 0.0]
    if zero_components:
        return False, "non-positive XSTAR emissivity for component(s): " + ", ".join(zero_components)
    return True, f"ok counts={counts}"

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


def _ion_tag(element: str, ion_stage: int | float | str) -> str:
    """Return compact lowercase ion tag, e.g. O VII -> o7 and C V -> c5."""
    try:
        stage = int(float(str(ion_stage)))
    except ValueError:
        stage = int(str(ion_stage))
    return f"{element.strip().lower()}{stage}"


def _element_stage_from_argv(argv: Sequence[str]) -> tuple[str, int]:
    element = _get_option_value(argv, "--element", "O") or "O"
    stage_text = _get_option_value(argv, "--ion-stage", "7") or "7"
    try:
        stage = int(float(stage_text))
    except ValueError:
        stage = 7
    return element.strip(), stage


def write_xstar_grid_template(
    path: Path,
    densities: Sequence[float] = (1.0, 1.0e4, 1.0e8, 1.0e10, 1.0e12),
    element: str = "O",
    ion_stage: int = 7,
) -> None:
    """Write a density-to-XSTAR-lines mapping CSV for one He-like ion.

    For O VII, rows point to the packaged compact density-specific references
    under ``xstar_test_run/o7_ne*/``.  For other He-like ions, rows point to
    the expected locations produced by the preparation/conversion workflow,
    for example ``xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv``.  These
    paths may not exist yet; users should run XSTAR and the converter scripts
    generated by example 32 before using the grid for science validation.
    """
    tag = _ion_tag(element, ion_stage)
    label = f"{element.strip()} {int(ion_stage)}"
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
            density = float(density)
            density_tag = _density_tag_for_path(density)
            expected = Path("xstar_test_run") / f"{tag}_{density_tag}" / f"xstar_{tag}_triplet_lines.csv"
            exists_note = "ready" if expected.exists() else "missing; run XSTAR/convert workflow from example 32 first"
            writer.writerow({
                "electron_density_cm^-3": f"{density:.12g}",
                "xstar_lines_csv": str(expected),
                "xstar_value_column": "emit_outward",
                "xstar_target_label": f"{label} XSTAR ne={density:.12g} cm^-3",
                "note": exists_note,
            })


def print_template_message(path: Path, element: str = "O", ion_stage: int = 7) -> None:
    tag = _ion_tag(element, ion_stage)
    print(f"Wrote template XSTAR density-grid mapping: {path}")
    print(
        "Each row points to the expected converted He-like triplet CSV, e.g. "
        f"xstar_test_run/{tag}_ne*/xstar_{tag}_triplet_lines.csv."
    )
    print("If those files are missing, run XSTAR and the converter scripts from example 32, then rerun this command.")


def _validate_grid_csv_paths(path: Path, argv: Sequence[str]) -> None:
    """Fail early if a density-grid mapping references missing line CSVs.

    This prevents a confusing downstream error from example 20, especially for
    non-O VII candidate ions where the mapping template may have been written
    before the external XSTAR/convert workflow was run in the current tree.
    """
    if not path.exists():
        return
    element, stage = _element_stage_from_argv(argv)
    tag = _ion_tag(element, stage)
    missing: List[str] = []
    stale_o7: List[str] = []
    invalid: List[str] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ref = str(row.get("xstar_lines_csv") or row.get("path") or "").strip()
            if not ref:
                continue
            if tag != "o7" and "xstar_o7_triplet_lines.csv" in ref:
                stale_o7.append(ref)
            ref_path = Path(ref)
            if not ref_path.exists():
                missing.append(ref)
                continue
            value_column = str(row.get("xstar_value_column") or "emit_outward").strip() or "emit_outward"
            ok, reason = _triplet_csv_status(ref_path, element, stage, value_column=value_column)
            if not ok:
                invalid.append(f"{ref} ({reason})")
    if stale_o7:
        raise SystemExit(
            f"Density-grid mapping {path} still references O VII triplet CSVs for {element} {stage}: "
            + ", ".join(sorted(set(stale_o7)))
            + ". Regenerate the mapping with --write-template-grid-csv or delete it and rerun example 22; "
            + f"expected paths look like xstar_test_run/{tag}_ne*/xstar_{tag}_triplet_lines.csv."
        )
    if missing:
        raise SystemExit(
            f"Density-grid mapping {path} references missing converted XSTAR triplet CSV file(s): "
            + ", ".join(sorted(set(missing)))
            + ". Run the XSTAR/convert scripts from example 32 in this package tree, or copy the converted files "
            + f"into xstar_test_run/{tag}_ne*/ before rerunning. If the files exist in another version directory, copy those {tag}_ne* folders here."
        )
    if invalid:
        raise SystemExit(
            f"Density-grid mapping {path} references converted XSTAR triplet CSV file(s) that cannot provide a complete He-like R/G target for {element} {stage}: "
            + "; ".join(sorted(set(invalid)))
            + ". Re-run the converter with a wavelength range/ion selection that produces the forbidden, intercombination, and resonance rows, "
            + "or remove this ion from the validation grid until XSTAR outputs usable triplet lines."
        )


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
        element, stage = _element_stage_from_argv(remaining)
        write_xstar_grid_template(template_path, element=element, ion_stage=stage)
        print_template_message(template_path, element=element, ion_stage=stage)
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
        if grid_path.exists():
            _validate_grid_csv_paths(grid_path, remaining)
        if not grid_path.exists():
            element, stage = _element_stage_from_argv(remaining)
            write_xstar_grid_template(grid_path, element=element, ion_stage=stage)
            print_template_message(grid_path, element=element, ion_stage=stage)
            if not known.allow_placeholder_grid:
                raise SystemExit(
                    f"XSTAR density-grid mapping CSV was missing, so a template was written to {grid_path}. "
                    "If the converted triplet CSVs listed in the template already exist, rerun this command. "
                    "Otherwise run XSTAR and the converter scripts from example 32 first."
                )
            print("WARNING: continuing with the newly written mapping template; rows whose files are missing will fail.")
        cmd += ["--xstar-grid-summary-csv", known.xstar_grid_summary_csv]
    for item in known.xstar_lines_csv_by_density:
        cmd += ["--xstar-lines-csv-by-density", item]
    if not _has_option(cmd, "--out-dir"):
        cmd += ["--out-dir", "o7_solver_source_fit_density_xstar_grid"]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
