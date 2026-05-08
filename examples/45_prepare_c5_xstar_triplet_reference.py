#!/usr/bin/env python3
"""Prepare or convert a real C V XSTAR triplet-line reference CSV.

The O VII reference-depth validation uses converted XSTAR line output such as
``xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv``.  This helper creates the
analogous C V target path and either:

* converts an existing XSTAR ``xout_lines1.fits`` file to
  ``xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv``; or
* writes a reproducible C V XSTAR run script plus a conversion script that can
  be run after XSTAR produces ``xout_lines1.fits``.

It does not run XSTAR itself.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence


def _density_tag(value: float) -> str:
    value = float(value)
    if value == 1.0:
        return "ne1"
    if value > 0:
        import math

        exp = int(round(math.log10(value)))
        if abs(value - 10.0**exp) / max(value, 1.0) < 1.0e-10:
            return f"ne1e{exp}"
    text = f"{value:.12g}"
    return "ne" + text.replace("+", "").replace(".", "p")


def _density_label(value: float) -> str:
    return f"{float(value):.12g}"


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o755)


def _write_csv(path: Path, rows: Sequence[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _xstar_command(density: float, modelname: str, rlogxi: float, column: float, vturbi: float, temperature: float) -> str:
    density_text = _density_label(density)
    return f"""xstar \\
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \\
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \\
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \\
  modelname='{modelname}' abundtbl='xdef' \\
  trad=-1 cfrac=1.0 temperature={temperature:.12g} pressure=0.03 density={density_text} \\
  rlrad38=1e6 column={column:.12g} rlogxi={rlogxi:.12g} vturbi={vturbi:.12g} \\
  habund=1 heabund=1 \\
  liabund=0 beabund=0 babund=0 cabund=1 nabund=0 \\
  oabund=0 fabund=0 neabund=0 naabund=0 mgabund=0 \\
  alabund=0 siabund=0 pabund=0 sabund=0 clabund=0 arabund=0 \\
  kabund=0 caabund=0 scabund=0 tiabund=0 vabund=0 crabund=0 \\
  mnabund=0 feabund=0 coabund=0 niabund=0 cuabund=0 znabund=0"""


def _convert_existing_fits(fits_path: Path, out_csv: Path, summary_json: Optional[Path]) -> int:
    from xstar_atomic.xstar_outputs import convert_xout_lines

    result = convert_xout_lines(
        fits_path,
        out_csv=out_csv,
        ion="C V",
        wavelength_min=40.0,
        wavelength_max=42.0,
    )
    if summary_json is not None:
        import json

        summary_json.parent.mkdir(parents=True, exist_ok=True)
        summary_json.write_text(json.dumps(result["summary"], indent=2, sort_keys=True), encoding="utf-8")
    return len(result["rows"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository/root directory where xstar_runs/ and xstar_test_run/ live")
    parser.add_argument("--density", type=float, default=1.0e8, help="Electron density in cm^-3. Default 1e8.")
    parser.add_argument("--rlogxi", type=float, default=1.5, help="XSTAR log ionization parameter used in the O VII reference plan. Default 1.5.")
    parser.add_argument("--column", type=float, default=1.0e20)
    parser.add_argument("--vturbi", type=float, default=100.0)
    parser.add_argument("--temperature", type=float, default=100.0, help="XSTAR input temperature parameter for the reference run plan. Default 100, matching the O VII grid helper.")
    parser.add_argument("--xout-lines-fits", help="Optional existing C V XSTAR xout_lines1.fits to convert immediately")
    parser.add_argument("--out-csv", help="Output C V triplet CSV. Default xstar_test_run/c5_<density>/xstar_c5_triplet_lines.csv")
    parser.add_argument("--summary-json", help="Optional JSON summary path for immediate FITS conversion")
    parser.add_argument("--mapping-csv", default="xstar_test_run/xstar_c5_density_grid_references.csv")
    parser.add_argument("--run-plan-csv", default="xstar_runs/c5_ne1e8_run_plan.csv")
    parser.add_argument("--readme", default="xstar_runs/README_c5_triplet_reference.md")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    dtag = _density_tag(args.density)
    stem = f"c5_{dtag}"
    run_dir = root / "xstar_runs" / stem
    csv_dir = root / "xstar_test_run" / stem
    out_csv = Path(args.out_csv) if args.out_csv else csv_dir / "xstar_c5_triplet_lines.csv"
    if not out_csv.is_absolute():
        out_csv = root / out_csv
    summary_json = Path(args.summary_json) if args.summary_json else None
    if summary_json is not None and not summary_json.is_absolute():
        summary_json = root / summary_json
    xout = run_dir / "xout_lines1.fits"
    modelname = f"xstar_atomic_c5_xi15_{dtag}"
    run_script = run_dir / "run_xstar.sh"
    convert_script = run_dir / "convert_c5_triplet.sh"

    _write_executable(run_script, "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")\"\n\n" + _xstar_command(args.density, modelname, args.rlogxi, args.column, args.vturbi, args.temperature) + "\n")
    rel_xout = os.path.relpath(xout, root)
    rel_out = os.path.relpath(out_csv, root)
    _write_executable(
        convert_script,
        "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")/../..\"\n"
        f"mkdir -p \"{os.path.dirname(rel_out)}\"\n"
        "PYTHONPATH=src python -m xstar_atomic.xstar_outputs \\\n"
        f"  {rel_xout} \\\n"
        "  --ion \"C V\" \\\n"
        "  --wavelength-min 40.0 \\\n"
        "  --wavelength-max 42.0 \\\n"
        f"  --out-csv {rel_out} \\\n"
        "  --print-summary \\\n"
        "  --print-rows\n",
    )

    row = {
        "electron_density_cm^-3": _density_label(args.density),
        "xstar_lines_csv": rel_out,
        "xstar_value_column": "emit_outward",
        "xstar_target_label": f"C V XSTAR ne={_density_label(args.density)} cm^-3",
        "run_script": os.path.relpath(run_script, root),
        "convert_script": os.path.relpath(convert_script, root),
        "xout_lines_fits": rel_xout,
    }
    _write_csv(root / args.mapping_csv, [{k: row[k] for k in ("electron_density_cm^-3", "xstar_lines_csv", "xstar_value_column", "xstar_target_label")}])
    _write_csv(root / args.run_plan_csv, [row])

    readme = root / args.readme
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(
        "# C V XSTAR triplet reference\n\n"
        "This plan creates the C V analog of `xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv`.\n\n"
        "## Run XSTAR\n\n"
        f"```bash\nbash {row['run_script']}\n```\n\n"
        "## Convert xout_lines1.fits to triplet CSV\n\n"
        f"```bash\nbash {row['convert_script']}\n```\n\n"
        "Equivalent explicit conversion command:\n\n"
        "```bash\n"
        "PYTHONPATH=src python -m xstar_atomic.xstar_outputs \\\n"
        f"  {row['xout_lines_fits']} \\\n"
        "  --ion \"C V\" \\\n"
        "  --wavelength-min 40.0 \\\n"
        "  --wavelength-max 42.0 \\\n"
        f"  --out-csv {row['xstar_lines_csv']} \\\n"
        "  --print-summary \\\n"
        "  --print-rows\n"
        "```\n",
        encoding="utf-8",
    )

    converted_rows = None
    if args.xout_lines_fits:
        converted_rows = _convert_existing_fits(Path(args.xout_lines_fits), out_csv, summary_json)

    if args.print_summary:
        print("C V XSTAR triplet reference preparation")
        print("---------------------------------------")
        print(f"root: {root}")
        print(f"density: {_density_label(args.density)} cm^-3")
        print(f"run script: {run_script}")
        print(f"convert script: {convert_script}")
        print(f"target CSV: {out_csv}")
        print(f"mapping CSV: {root / args.mapping_csv}")
        print(f"README: {readme}")
        if converted_rows is not None:
            print(f"converted rows: {converted_rows}")


if __name__ == "__main__":
    main()
