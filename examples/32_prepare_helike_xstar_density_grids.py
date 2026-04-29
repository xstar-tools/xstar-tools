#!/usr/bin/env python3
"""Prepare XSTAR density-grid run directories for candidate He-like ions.

This helper generalizes the O VII density-grid preparation workflow to the
He-like ions that the type-69 ground-resonance audit currently flags as
candidates beyond O VII, namely C V, Mg XI, and Ca XIX.  It does **not** run
XSTAR and it does **not** validate ``suppress-resonance`` for these ions by
itself.  It writes reproducible XSTAR run scripts, conversion scripts for
``xout_lines1.fits`` -> triplet CSV, per-ion density-to-CSV mapping files, a
summary CSV, and a README describing the follow-up commands.

The generated converted CSV paths are arranged so that
``examples/31_helike_type69_ground_resonance_validation.py`` can detect supplied
references later::

    xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv
    xstar_test_run/mg11_ne1e12/xstar_mg11_triplet_lines.csv
    xstar_test_run/ca19_ne1e12/xstar_ca19_triplet_lines.csv

After XSTAR is run externally and the conversion scripts are executed, the
ion-specific mapping CSVs can be used to add real include-vs-suppress-resonance
comparisons.  Until then, these ions remain ``pending_xstar_density_grid``.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

DEFAULT_IONS = "C V,Mg XI,Ca XIX"
DEFAULT_DENSITIES: Tuple[float, ...] = (1.0, 1.0e4, 1.0e8, 1.0e10, 1.0e12)
DEFAULT_RLOGXI: Tuple[float, ...] = (1.5,)

ABUNDANCE_KEYS = [
    "h", "he", "li", "be", "b", "c", "n", "o", "f", "ne", "na", "mg", "al",
    "si", "p", "s", "cl", "ar", "k", "ca", "sc", "ti", "v", "cr", "mn", "fe",
    "co", "ni", "cu", "zn",
]

ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
ROMAN_BY_STAGE = {
    5: "V",
    6: "VI",
    7: "VII",
    9: "IX",
    11: "XI",
    13: "XIII",
    15: "XV",
    17: "XVII",
    19: "XIX",
    25: "XXV",
}

# Conservative triplet windows centered on the common He-like w/i/f complex.
# They are used only for filtering converted XSTAR line lists.
TRIPLET_WINDOWS = {
    ("C", 5): (40.0, 42.0),
    ("N", 6): (28.6, 29.8),
    ("O", 7): (21.5, 22.2),
    ("Ne", 9): (13.3, 13.9),
    ("Mg", 11): (9.05, 9.40),
    ("Si", 13): (6.55, 6.80),
    ("S", 15): (5.00, 5.15),
    ("Ar", 17): (3.92, 4.02),
    ("Ca", 19): (3.14, 3.23),
    ("Fe", 25): (1.83, 1.88),
}


def roman_to_int(text: str) -> int:
    total = 0
    prev = 0
    for ch in reversed(str(text).upper()):
        value = ROMAN_VALUES.get(ch)
        if value is None:
            raise ValueError(f"invalid Roman ion stage {text!r}")
        if value < prev:
            total -= value
        else:
            total += value
            prev = value
    return total


def normalize_symbol(text: str) -> str:
    t = str(text).strip()
    if not t:
        raise ValueError("empty element symbol")
    return t[0].upper() + t[1:].lower()


def parse_ion_spec(text: str) -> Tuple[str, int]:
    raw = str(text).strip()
    if ":" in raw:
        sym, stage = [part.strip() for part in raw.split(":", 1)]
        return normalize_symbol(sym), int(float(stage))
    m = re.match(r"^([A-Z][a-z]?)[\s_\-]*([IVXLCDM]+|\d+)$", raw, flags=re.I)
    if not m:
        raise ValueError(f"invalid ion specification {text!r}; expected e.g. 'Mg XI' or 'Mg:11'")
    sym = normalize_symbol(m.group(1))
    stage_text = m.group(2)
    stage = int(float(stage_text)) if stage_text.isdigit() else roman_to_int(stage_text)
    return sym, stage


def parse_ions(text: str) -> List[Tuple[str, int]]:
    ions: List[Tuple[str, int]] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part:
            ions.append(parse_ion_spec(part))
    return ions


def parse_densities(values: Sequence[str]) -> List[float]:
    return parse_float_grid(values, DEFAULT_DENSITIES)


def parse_rlogxi_grid(values: Sequence[str]) -> List[float]:
    return parse_float_grid(values, DEFAULT_RLOGXI)


def density_tag(value: float) -> str:
    value = float(value)
    if value == 1.0:
        return "ne1"
    exp = int(round(math.log10(value))) if value > 0 else 0
    if value > 0 and abs(value - 10.0**exp) / max(value, 1.0) < 1.0e-10:
        return f"ne1e{exp}"
    return (f"ne{value:.6g}".replace("+", "").replace(".", "p"))


def density_label(value: float) -> str:
    return f"{float(value):.12g}"


def xi_tag(value: float) -> str:
    text = f"{float(value):.12g}"
    return "xi" + text.replace("+", "").replace("-", "m").replace(".", "p")


def parse_float_grid(values: Sequence[str], default: Sequence[float]) -> List[float]:
    if not values:
        return list(default)
    out: List[float] = []
    for item in values:
        for part in str(item).replace(";", ",").split(","):
            part = part.strip()
            if part:
                out.append(float(part))
    return out


def ion_tag(symbol: str, stage: int) -> str:
    return f"{symbol.lower()}{int(stage)}"


def ion_label(symbol: str, stage: int) -> str:
    return f"{symbol} {ROMAN_BY_STAGE.get(stage, str(stage))}"


def abundance_arguments(target_symbol: str) -> str:
    target = target_symbol.lower()
    parts: List[str] = []
    for key in ABUNDANCE_KEYS:
        if key in ("h", "he"):
            value = 1
        elif key == target:
            value = 1
        else:
            value = 0
        parts.append(f"{key}abund={value}")
    # Preserve the traditional wrapped XSTAR command layout.
    lines = []
    for i in range(0, len(parts), 6):
        suffix = " \\" if i + 6 < len(parts) else ""
        lines.append("  " + " ".join(parts[i:i + 6]) + suffix)
    return "\n".join(lines)


def xstar_command(symbol: str, stage: int, density: float, modelname: str, rlogxi: float, column: float, vturbi: float, temperature: float) -> str:
    density_text = density_label(density)
    return f"""xstar \\
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \\
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \\
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \\
  modelname='{modelname}' abundtbl='xdef' \\
  trad=-1 cfrac=1.0 temperature={temperature:.12g} pressure=0.03 density={density_text} \\
  rlrad38=1e6 column={column:.12g} rlogxi={rlogxi:.12g} vturbi={vturbi:.12g} \\
{abundance_arguments(symbol)}"""


def write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    mode = path.stat().st_mode
    path.chmod(mode | 0o755)


def window_for(symbol: str, stage: int) -> Tuple[float, float]:
    try:
        return TRIPLET_WINDOWS[(symbol, stage)]
    except KeyError as exc:
        raise ValueError(f"no default triplet wavelength window for {ion_label(symbol, stage)}") from exc


def write_mapping_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["electron_density_cm^-3", "xstar_lines_csv", "xstar_value_column", "xstar_target_label"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in fields})


def write_summary_csv(path: Path, rows: Sequence[dict]) -> None:
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


def write_density_scripts(root: Path, ions: Sequence[Tuple[str, int]], densities: Sequence[float], rlogxi_values: Sequence[float], column: float, vturbi: float, temperature: float) -> List[dict]:
    rows: List[dict] = []
    if isinstance(rlogxi_values, (int, float)):
        rlogxi_list = [float(rlogxi_values)]
    else:
        rlogxi_list = list(rlogxi_values)
    multi_xi = len(rlogxi_list) > 1
    for symbol, stage in ions:
        tag = ion_tag(symbol, stage)
        label = ion_label(symbol, stage)
        wmin, wmax = window_for(symbol, stage)
        for rlogxi in rlogxi_list:
            xtag = xi_tag(rlogxi)
            ion_rows: List[dict] = []
            for density in densities:
                dtag = density_tag(density)
                stem = f"{tag}_{xtag}_{dtag}" if multi_xi else f"{tag}_{dtag}"
                run_dir = root / "xstar_runs" / "helike_type69" / stem
                csv_dir = root / "xstar_test_run" / stem
                modelname = f"xstar_atomic_{tag}_{xtag}_{dtag}"
                run_script = run_dir / "run_xstar.sh"
                convert_script = run_dir / f"convert_{tag}_triplet.sh"
                xout = run_dir / "xout_lines1.fits"
                out_csv = csv_dir / f"xstar_{tag}_triplet_lines.csv"
                write_executable(
                    run_script,
                    "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")\"\n\n"
                    + xstar_command(symbol, stage, density, modelname, rlogxi, column, vturbi, temperature)
                    + "\n",
                )
                rel_xout = os.path.relpath(xout, root)
                rel_out_csv = os.path.relpath(out_csv, root)
                convert_text = (
                    "#!/usr/bin/env bash\n"
                    "set -euo pipefail\n"
                    "cd \"$(dirname \"$0\")/../../..\"\n"
                    f"mkdir -p \"{os.path.dirname(rel_out_csv)}\"\n"
                    "PYTHONPATH=src python -m xstar_atomic.xstar_outputs \\\n"
                    f"  {rel_xout} \\\n"
                    f"  --ion \"{label}\" \\\n"
                    f"  --wavelength-min {wmin:.8g} \\\n"
                    f"  --wavelength-max {wmax:.8g} \\\n"
                    f"  --out-csv {rel_out_csv} \\\n"
                    "  --print-summary \\\n"
                    "  --print-rows\n"
                )
                write_executable(convert_script, convert_text)
                row = {
                    "ion": label,
                    "element": symbol,
                    "ion_stage": stage,
                    "ion_tag": tag,
                    "rlogxi": density_label(rlogxi),
                    "xi_tag": xtag,
                    "electron_density_cm^-3": density_label(density),
                    "density_tag": dtag,
                    "wavelength_min_A": wmin,
                    "wavelength_max_A": wmax,
                    "run_dir": os.path.relpath(run_dir, root),
                    "run_script": os.path.relpath(run_script, root),
                    "xout_lines_fits": rel_xout,
                    "convert_script": os.path.relpath(convert_script, root),
                    "xstar_lines_csv": rel_out_csv,
                    "xstar_value_column": "emit_outward",
                    "xstar_target_label": f"{label} XSTAR logxi={density_label(rlogxi)} ne={density_label(density)} cm^-3",
                }
                rows.append(row)
                ion_rows.append(row)
            mapping_name = f"xstar_{tag}_{xtag}_density_grid_references.csv" if multi_xi else f"xstar_{tag}_density_grid_references.csv"
            mapping = root / "xstar_test_run" / mapping_name
            write_mapping_csv(mapping, ion_rows)
            for row in ion_rows:
                row["mapping_csv"] = os.path.relpath(mapping, root)
    return rows

def write_readme(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    by_ion: Dict[str, List[dict]] = {}
    for row in rows:
        by_ion.setdefault(str(row["ion"]), []).append(row)
    lines: List[str] = []
    lines.append("# He-like type-69 XSTAR density-grid run plans\n")
    lines.append("Generated by `examples/32_prepare_helike_xstar_density_grids.py`.\n")
    lines.append("These scripts prepare candidate-ion XSTAR density grids for testing whether the O VII `suppress-resonance` diagnostic also helps other He-like triplets. They do not validate those ions by themselves.\n")
    for ion, ion_rows in by_ion.items():
        tag = ion_rows[0]["ion_tag"]
        mapping = ion_rows[0]["mapping_csv"]
        lines.append(f"\n## {ion}\n")
        lines.append("Run XSTAR in each density directory:\n")
        lines.append("```bash")
        for row in ion_rows:
            lines.append(f"bash {row['run_script']}")
        lines.append("```\n")
        lines.append("Convert each `xout_lines1.fits` to a triplet CSV:\n")
        lines.append("```bash")
        for row in ion_rows:
            lines.append(f"bash {row['convert_script']}")
        lines.append("```\n")
        lines.append("Mapping CSV for downstream comparison:\n")
        lines.append(f"```text\n{mapping}\n```\n")
        wmin = ion_rows[0]["wavelength_min_A"]
        wmax = ion_rows[0]["wavelength_max_A"]
        stage = ion_rows[0]["ion_stage"]
        element = ion_rows[0]["element"]
        lines.append("Suggested density-grid source-fit command after conversion:\n")
        lines.append("```bash")
        lines.append("PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \\")
        lines.append("  ../xstar/data/atdb.fits \\")
        lines.append(f"  --element {element} \\")
        lines.append(f"  --ion-stage {stage} \\")
        lines.append(f"  --wavelength-min {wmin:.8g} \\")
        lines.append(f"  --wavelength-max {wmax:.8g} \\")
        lines.append(f"  --xstar-grid-summary-csv {mapping} \\")
        lines.append("  --linear-solver svd \\")
        lines.append("  --rank-deficient-action svd \\")
        lines.append("  --negative-population-action keep \\")
        lines.append("  --prune-null-rate-levels \\")
        lines.append("  --combined-source-total-rate 1.0 \\")
        lines.append("  --index-cache \\")
        lines.append(f"  --index-cache-path .xstar_atomic_cache/atdb_{tag}_index.npz \\")
        lines.append(f"  --out-dir {tag}_solver_source_fit_density_xstar_grid \\")
        lines.append("  --print-summary")
        lines.append("```\n")
        lines.append("Note: this command reuses the existing density-grid source-fit machinery with ion-specific element/stage and wavelength options. Inspect source-level choices before treating a non-O VII run as finalized validation. The generated XSTAR references are the required first step.\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository/root directory where xstar_runs/ and xstar_test_run/ will be created")
    parser.add_argument("--ions", default=DEFAULT_IONS, help="Comma-separated candidate He-like ions, e.g. 'C V,Mg XI,Ca XIX'")
    parser.add_argument("--densities", nargs="*", default=[], help="Density grid values in cm^-3, e.g. 1 1e4 1e8 1e10 1e12")
    parser.add_argument("--rlogxi", type=float, default=None, help="Single XSTAR log ionization parameter. Kept for backward compatibility; equivalent to --rlogxi-grid VALUE")
    parser.add_argument("--rlogxi-grid", nargs="*", default=[], help="One or more XSTAR log ionization parameters, e.g. 1.5 2 2.5 3 3.5 4. Useful when an ion such as Ca XIX is absent at the default log xi")
    parser.add_argument("--column", type=float, default=1.0e20, help="XSTAR column density")
    parser.add_argument("--vturbi", type=float, default=100.0, help="XSTAR turbulent velocity")
    parser.add_argument("--temperature", type=float, default=100.0, help="Initial XSTAR temperature parameter")
    parser.add_argument("--summary-csv", default="xstar_runs/helike_type69_density_grid_run_plan.csv", help="Output run-plan summary CSV")
    parser.add_argument("--readme", default="xstar_runs/README_helike_type69_density_grids.md", help="Output Markdown file with all commands")
    parser.add_argument("--print-summary", action="store_true", help="Print generated files and commands summary")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    ions = parse_ions(args.ions)
    densities = parse_densities(args.densities)
    rlogxi_values = [float(args.rlogxi)] if args.rlogxi is not None else parse_rlogxi_grid(args.rlogxi_grid)
    rows = write_density_scripts(root, ions, densities, rlogxi_values, args.column, args.vturbi, args.temperature)
    summary = root / args.summary_csv
    readme = root / args.readme
    write_summary_csv(summary, rows)
    write_readme(readme, rows)

    if args.print_summary:
        print("Prepared He-like type-69 XSTAR density-grid run plans")
        print(f"root: {root}")
        print("ions:", ", ".join(ion_label(s, st) for s, st in ions))
        print("densities:", ", ".join(density_label(d) for d in densities))
        print("log xi values:", ", ".join(density_label(x) for x in rlogxi_values))
        print(f"summary CSV: {summary}")
        print(f"README: {readme}")
        print("per-ion mapping CSVs:")
        seen = set()
        for row in rows:
            mapping = row.get("mapping_csv")
            if mapping not in seen:
                print(f"  {row['ion']}: {mapping}")
                seen.add(mapping)
        print("run scripts:")
        for row in rows:
            print(f"  {row['ion']} ne={row['electron_density_cm^-3']}: bash {row['run_script']}")
        print("conversion scripts:")
        for row in rows:
            print(f"  {row['ion']} ne={row['electron_density_cm^-3']}: bash {row['convert_script']}")
        print("These plans do not validate suppress-resonance; run XSTAR, convert the outputs, then compare include vs suppress-resonance for each ion.")


if __name__ == "__main__":
    main()
