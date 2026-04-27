#!/usr/bin/env python3
"""Prepare O VII XSTAR density-grid runs for density-dependent triplet validation.

This helper does not run XSTAR itself.  It creates run directories, shell
scripts containing the full XSTAR commands, conversion commands for
``xout_lines1.fits`` -> O VII triplet CSV, and a density-to-CSV mapping file for
``examples/22_o7_solver_source_fit_density_xstar_grid.py``.

The default grid is designed to complement the O VII solver-source-fit density
workflow::

    ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3

The generated XSTAR models use the same O-only, ``rlogxi=1.5`` setup as the
existing O VII validation run, with only density varied.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

DEFAULT_DENSITIES: Tuple[float, ...] = (1.0, 1.0e4, 1.0e8, 1.0e10, 1.0e12)


def density_tag(value: float) -> str:
    """Return a compact directory-safe density tag."""
    value = float(value)
    if value == 1.0:
        return "ne1"
    exp = int(round(__import__("math").log10(value))) if value > 0 else 0
    if abs(value - 10.0**exp) / max(value, 1.0) < 1.0e-10:
        return f"ne1e{exp}"
    return (f"ne{value:.6g}".replace("+", "").replace(".", "p"))


def density_label(value: float) -> str:
    return f"{float(value):.12g}"


def xstar_command(density: float, modelname: str) -> str:
    """Return the full O VII XSTAR command for one density."""
    density_text = density_label(density)
    return f"""xstar \\
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \\
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \\
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \\
  modelname='{modelname}' abundtbl='xdef' \\
  trad=-1 cfrac=1.0 temperature=100 pressure=0.03 density={density_text} \\
  rlrad38=1e6 column=1e20 rlogxi=1.5 vturbi=100 \\
  habund=1 heabund=1 \\
  liabund=0 beabund=0 babund=0 cabund=0 nabund=0 \\
  oabund=1 fabund=0 neabund=0 naabund=0 mgabund=0 \\
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \\
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \\
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0"""


def write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    mode = path.stat().st_mode
    path.chmod(mode | 0o755)


def write_density_scripts(root: Path, densities: Sequence[float]) -> List[dict]:
    rows: List[dict] = []
    for density in densities:
        tag = density_tag(density)
        run_dir = root / "xstar_runs" / f"o7_{tag}"
        csv_dir = root / "xstar_test_run" / f"o7_{tag}"
        modelname = f"xstar_atomic_o7_xi15_{tag}"
        run_script = run_dir / "run_xstar.sh"
        convert_script = run_dir / "convert_o7_triplet.sh"
        xout = run_dir / "xout_lines1.fits"
        out_csv = csv_dir / "xstar_o7_triplet_lines.csv"
        write_executable(run_script, "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")\"\n\n" + xstar_command(density, modelname) + "\n")
        rel_xout = os.path.relpath(xout, root)
        rel_out_csv = os.path.relpath(out_csv, root)
        write_executable(
            convert_script,
            f"""#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p "{os.path.dirname(rel_out_csv)}"
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \\
  {rel_xout} \\
  --ion "O VII" \\
  --wavelength-min 21.5 \\
  --wavelength-max 22.2 \\
  --out-csv {rel_out_csv} \\
  --print-summary \\
  --print-rows
""",
        )
        rows.append({
            "electron_density_cm^-3": density_label(density),
            "tag": tag,
            "run_dir": os.path.relpath(run_dir, root),
            "run_script": os.path.relpath(run_script, root),
            "xout_lines_fits": rel_xout,
            "convert_script": os.path.relpath(convert_script, root),
            "xstar_lines_csv": rel_out_csv,
            "xstar_value_column": "emit_outward",
            "xstar_target_label": f"O VII XSTAR ne={density_label(density)} cm^-3",
        })
    return rows


def write_mapping_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["electron_density_cm^-3", "xstar_lines_csv", "xstar_value_column", "xstar_target_label"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "electron_density_cm^-3": row["electron_density_cm^-3"],
                "xstar_lines_csv": row["xstar_lines_csv"],
                "xstar_value_column": row["xstar_value_column"],
                "xstar_target_label": row["xstar_target_label"],
            })


def write_summary_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "electron_density_cm^-3", "tag", "run_dir", "run_script",
        "xout_lines_fits", "convert_script", "xstar_lines_csv",
        "xstar_value_column", "xstar_target_label",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_readme(path: Path, rows: Sequence[dict], mapping_csv: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append("# O VII XSTAR density-grid runs\n")
    lines.append("This directory set was generated by `examples/23_prepare_o7_xstar_density_grid.py`.\n")
    lines.append("Run XSTAR externally in each clean run directory, convert `xout_lines1.fits` to O VII triplet CSV files, then run the density-dependent source-fit comparison.\n")
    lines.append("\n## 1. Run XSTAR at each density\n")
    lines.append("Each script below contains the full XSTAR command.\n")
    lines.append("\n```bash")
    for row in rows:
        lines.append(row["run_script"])
    lines.append("```\n")
    for row in rows:
        lines.append(f"### ne = {row['electron_density_cm^-3']} cm^-3\n")
        lines.append(f"Directory: `{row['run_dir']}`\n")
        lines.append("```bash")
        lines.append(f"bash {row['run_script']}")
        lines.append("```\n")
        lines.append("Full command in that script:\n")
        modelname = f"xstar_atomic_o7_xi15_{row['tag']}"
        lines.append("```bash")
        lines.append(xstar_command(float(row["electron_density_cm^-3"]), modelname))
        lines.append("```\n")
    lines.append("## 2. Convert XSTAR line FITS files to O VII triplet CSV files\n")
    lines.append("After each XSTAR run produces `xout_lines1.fits`, run:\n")
    lines.append("\n```bash")
    for row in rows:
        lines.append(f"bash {row['convert_script']}")
    lines.append("```\n")
    lines.append("Equivalent explicit conversion commands:\n")
    for row in rows:
        lines.append(f"### ne = {row['electron_density_cm^-3']} cm^-3\n")
        lines.append("```bash")
        lines.append("PYTHONPATH=src python -m xstar_atomic.xstar_outputs \\")
        lines.append(f"  {row['xout_lines_fits']} \\")
        lines.append("  --ion \"O VII\" \\")
        lines.append("  --wavelength-min 21.5 \\")
        lines.append("  --wavelength-max 22.2 \\")
        lines.append(f"  --out-csv {row['xstar_lines_csv']} \\")
        lines.append("  --print-summary \\")
        lines.append("  --print-rows")
        lines.append("```\n")
    lines.append("## 3. Run the density-dependent XSTAR-grid comparison\n")
    lines.append("The generated mapping CSV is:\n")
    lines.append(f"\n```text\n{mapping_csv}\n```\n")
    lines.append("Run:\n")
    lines.append("\n```bash")
    lines.append("PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \\")
    lines.append("  ../xstar/data/atdb.fits \\")
    lines.append(f"  --xstar-grid-summary-csv {mapping_csv} \\")
    lines.append("  --linear-solver svd \\")
    lines.append("  --rank-deficient-action svd \\")
    lines.append("  --negative-population-action keep \\")
    lines.append("  --prune-null-rate-levels \\")
    lines.append("  --combined-source-total-rate 1.0 \\")
    lines.append("  --index-cache \\")
    lines.append("  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \\")
    lines.append("  --out-dir o7_solver_source_fit_density_xstar_grid \\")
    lines.append("  --print-summary")
    lines.append("```\n")
    lines.append("## Notes\n")
    lines.append("These XSTAR runs vary density only and keep the O VII validation setup (`rlogxi=1.5`, O-only, power-law spectrum) fixed.  The empirical source-fit weights remain diagnostic and are not physical level-resolved recombination rates.\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_densities(values: Sequence[str]) -> List[float]:
    if not values:
        return list(DEFAULT_DENSITIES)
    out: List[float] = []
    for item in values:
        for part in str(item).split(","):
            part = part.strip()
            if part:
                out.append(float(part))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository/root directory where xstar_runs/ and xstar_test_run/ will be created")
    parser.add_argument("--densities", nargs="*", default=[], help="Density grid values in cm^-3, e.g. 1 1e4 1e8 1e10 1e12")
    parser.add_argument("--mapping-csv", default="xstar_o7_density_grid_references.csv", help="Output density-to-XSTAR-lines mapping CSV")
    parser.add_argument("--summary-csv", default="xstar_runs/o7_density_grid_run_plan.csv", help="Output run-plan summary CSV")
    parser.add_argument("--readme", default="xstar_runs/README_o7_density_grid.md", help="Output Markdown file with all commands")
    parser.add_argument("--print-summary", action="store_true", help="Print generated files and commands summary")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    densities = parse_densities(args.densities)
    rows = write_density_scripts(root, densities)
    mapping = root / args.mapping_csv
    summary = root / args.summary_csv
    readme = root / args.readme
    write_mapping_csv(mapping, rows)
    write_summary_csv(summary, rows)
    write_readme(readme, rows, os.path.relpath(mapping, root))

    if args.print_summary:
        print("Prepared O VII XSTAR density-grid run plan")
        print(f"root: {root}")
        print("densities:", ", ".join(density_label(d) for d in densities))
        print(f"mapping CSV: {mapping}")
        print(f"summary CSV: {summary}")
        print(f"README: {readme}")
        print("run scripts:")
        for row in rows:
            print(f"  {row['electron_density_cm^-3']}: bash {row['run_script']}")
        print("conversion scripts:")
        for row in rows:
            print(f"  {row['electron_density_cm^-3']}: bash {row['convert_script']}")


if __name__ == "__main__":
    main()
