#!/usr/bin/env python3
"""Prepare Mg XI and Ca XIX XSTAR triplet targets and validation commands.

This helper is the Mg/Ca analog of the C V and O VII target workflows.  It
writes reproducible XSTAR run scripts, conversion scripts for ``xout_lines1.fits``
into triplet CSV files, a target-plan CSV, and a README containing the solver and
comparison commands needed to validate Mg XI and Ca XIX against real XSTAR
``emit_outward`` line targets.

The script does not run XSTAR.  After running the generated ``run_xstar.sh`` and
``convert_*_triplet.sh`` scripts locally, compare with
``examples/43_compare_xstar_detail_populations.py``.  Starting in v0.3.111, that
comparison script automatically derives the target f/i/r from a supplied
``--xstar-triplet-lines-csv`` instead of falling back to the historical C V
built-in target.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import re
from pathlib import Path
from typing import Iterable, Sequence

ABUNDANCE_KEYS = [
    "h", "he", "li", "be", "b", "c", "n", "o", "f", "ne", "na", "mg", "al",
    "si", "p", "s", "cl", "ar", "k", "ca", "sc", "ti", "v", "cr", "mn", "fe",
    "co", "ni", "cu", "zn",
]
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
ROMAN_BY_STAGE = {5: "V", 7: "VII", 11: "XI", 19: "XIX"}
TRIPLET_WINDOWS = {
    ("Mg", 11): (9.05, 9.40),
    ("Ca", 19): (3.14, 3.23),
}
DEFAULT_IONS = "Mg XI,Ca XIX"
DEFAULT_RLOGXI = (1.5, 2.0, 2.5, 3.0, 3.5, 4.0)
COMMON_SOLVER_ARGS = """  --temperature 1000000 --electron-density 1e8 \\
  --max-level 80 \\
  --adjacent-coupling-mode recombination-source \\
  --adjacent-coupling-source-mode record-destination \\
  --index-cache \\
  --type57-energy-convention abs-rlev4 \\
  --triplet-source-mode type74-direct-diagnostic \\
  --triplet-source-scale 1,1e2,1e4,1e6,1e8,1e10 \\
  --type99-proxy-scale 0,1e-8,1e-6,1e-4,1e-2,1,1e2 \\
  --radiation-field-mode xstar-powerlaw \\
  --radiation-bremsa-scale 1e18 \\
  --radiation-powerlaw-index 1.0 \\
  --radiation-n-energy-grid 512 \\
  --type53-flat-proxy-scale 1 \\
  --type53-phint53-scale 1,1e5,1e10,1e15,1e18,1e20 \\
  --inverse-recombination-mode xstar-ucalc \\
  --ion-fraction-closure xstar-calc-ion-rates \\
  --full-global-linear-solver xstar-lucy \\
  --full-global-topology xstar-continuum-alias-superlevels \\
  --type50-bound-bound-treatment xstar-line-escape \\
  --type50-escape-factor 0.35"""


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
    raw = str(text).strip()
    if not raw:
        raise ValueError("empty element symbol")
    return raw[0].upper() + raw[1:].lower()


def parse_ion_spec(text: str) -> tuple[str, int]:
    raw = str(text).strip()
    if ":" in raw:
        sym, stage = [part.strip() for part in raw.split(":", 1)]
        return normalize_symbol(sym), int(float(stage))
    m = re.match(r"^([A-Z][a-z]?)[\s_\-]*([IVXLCDM]+|\d+)$", raw, flags=re.I)
    if not m:
        raise ValueError(f"invalid ion specification {text!r}; expected e.g. 'Mg XI' or 'Ca XIX'")
    stage_text = m.group(2)
    stage = int(float(stage_text)) if stage_text.isdigit() else roman_to_int(stage_text)
    return normalize_symbol(m.group(1)), stage


def parse_ions(text: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for part in str(text).replace(";", ",").split(","):
        part = part.strip()
        if part:
            ion = parse_ion_spec(part)
            if ion not in TRIPLET_WINDOWS:
                raise ValueError(f"no built-in Mg/Ca triplet window for {ion_label(*ion)}")
            out.append(ion)
    return out


def parse_float_grid(values: Sequence[str], default: Sequence[float]) -> list[float]:
    if not values:
        return list(default)
    out: list[float] = []
    for item in values:
        for part in str(item).replace(";", ",").split(","):
            part = part.strip()
            if part:
                out.append(float(part))
    return out


def tag_float(prefix: str, value: float) -> str:
    text = f"{float(value):.12g}"
    if value > 0:
        exp = int(round(math.log10(value)))
        if abs(value - 10.0**exp) / max(value, 1.0) < 1e-10:
            text = f"1e{exp}"
    return prefix + text.replace("+", "").replace("-", "m").replace(".", "p")


def density_label(value: float) -> str:
    return f"{float(value):.12g}"


def ion_tag(symbol: str, stage: int) -> str:
    return f"{symbol.lower()}{int(stage)}"


def ion_label(symbol: str, stage: int) -> str:
    return f"{symbol} {ROMAN_BY_STAGE.get(stage, str(stage))}"


def abundance_arguments(target_symbol: str) -> str:
    target = target_symbol.lower()
    parts: list[str] = []
    for key in ABUNDANCE_KEYS:
        if key in {"h", "he"} or key == target:
            value = 1
        else:
            value = 0
        parts.append(f"{key}abund={value}")
    lines: list[str] = []
    for i in range(0, len(parts), 6):
        suffix = " \\" if i + 6 < len(parts) else ""
        lines.append("  " + " ".join(parts[i : i + 6]) + suffix)
    return "\n".join(lines)


def xstar_command(symbol: str, density: float, modelname: str, rlogxi: float, column: float, vturbi: float, temperature: float) -> str:
    return f"""xstar \\
  spectrum='pow' spectrum_file='spect.dat' spectun=0 \\
  nsteps=10 niter=99 lwrite=1 lprint=1 lstep=0 npass=1 \\
  lcpres=0 emult=0.5 taumax=5.0 xeemin=0.1 critf=1e-6 radexp=0.0 ncn2=9999 \\
  modelname='{modelname}' abundtbl='xdef' \\
  trad=-1 cfrac=1.0 temperature={temperature:.12g} pressure=0.03 density={density_label(density)} \\
  rlrad38=1e6 column={column:.12g} rlogxi={rlogxi:.12g} vturbi={vturbi:.12g} \\
{abundance_arguments(symbol)}"""


def write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o755)


def write_csv(path: Path, rows: Sequence[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def solver_out_dir(tag: str, xi_tag: str, density_tag: str) -> str:
    return f"{tag}_xstar_like_element_solver_v03111_{xi_tag}_{density_tag}_superlevels"


def build_rows(root: Path, ions: Iterable[tuple[str, int]], density: float, rlogxi_values: Sequence[float], column: float, vturbi: float, temperature: float) -> list[dict]:
    rows: list[dict] = []
    dtag = tag_float("ne", density)
    for symbol, stage in ions:
        tag = ion_tag(symbol, stage)
        label = ion_label(symbol, stage)
        wmin, wmax = TRIPLET_WINDOWS[(symbol, stage)]
        for xi in rlogxi_values:
            xtag = tag_float("xi", xi)
            stem = f"{tag}_{xtag}_{dtag}"
            run_dir = root / "xstar_runs" / "mg_ca_triplet_targets" / stem
            csv_dir = root / "xstar_test_run" / stem
            out_csv = csv_dir / f"xstar_{tag}_triplet_lines.csv"
            xout = run_dir / "xout_lines1.fits"
            run_script = run_dir / "run_xstar.sh"
            convert_script = run_dir / f"convert_{tag}_triplet.sh"
            modelname = f"xstar_atomic_{tag}_{xtag}_{dtag}"
            write_executable(run_script, "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")\"\n\n" + xstar_command(symbol, density, modelname, xi, column, vturbi, temperature) + "\n")
            rel_xout = os.path.relpath(xout, root)
            rel_csv = os.path.relpath(out_csv, root)
            write_executable(
                convert_script,
                "#!/usr/bin/env bash\nset -euo pipefail\ncd \"$(dirname \"$0\")/../../..\"\n"
                f"mkdir -p \"{os.path.dirname(rel_csv)}\"\n"
                "PYTHONPATH=src python -m xstar_atomic.xstar_outputs \\\n"
                f"  {rel_xout} \\\n"
                f"  --ion \"{label}\" \\\n"
                f"  --wavelength-min {wmin:.8g} \\\n"
                f"  --wavelength-max {wmax:.8g} \\\n"
                f"  --out-csv {rel_csv} \\\n"
                "  --print-summary \\\n"
                "  --print-rows\n",
            )
            out_dir = solver_out_dir(tag, xtag, dtag)
            solver_cmd = (
                "PYTHONPATH=src python examples/42_xstar_like_element_solver_demo.py \\\n"
                "  ../xstar/data/atdb.fits \\\n"
                f"  --element {symbol} --he-like-stage {stage} \\\n"
                f"  --wavelength-min {wmin:.8g} --wavelength-max {wmax:.8g} \\\n"
                f"{COMMON_SOLVER_ARGS} \\\n"
                f"  --out-dir {out_dir} \\\n"
                "  --print-summary"
            )
            compare_cmd = (
                "PYTHONPATH=src python examples/43_compare_xstar_detail_populations.py \\\n"
                f"  --solver-out-dir {out_dir} \\\n"
                f"  --element {symbol} --he-like-stage {stage} \\\n"
                "  --comparison-case full_global_xstar_tau0_calc_emis_ion \\\n"
                f"  --xstar-triplet-lines-csv {rel_csv} \\\n"
                "  --xstar-value-column emit_outward \\\n"
                "  --target-f nan --target-i nan --target-r nan \\\n"
                "  --print-summary"
            )
            rows.append(
                {
                    "ion": label,
                    "element": symbol,
                    "he_like_stage": stage,
                    "ion_tag": tag,
                    "rlogxi": density_label(xi),
                    "xi_tag": xtag,
                    "electron_density_cm^-3": density_label(density),
                    "density_tag": dtag,
                    "wavelength_min_A": wmin,
                    "wavelength_max_A": wmax,
                    "run_script": os.path.relpath(run_script, root),
                    "convert_script": os.path.relpath(convert_script, root),
                    "xout_lines_fits": rel_xout,
                    "xstar_lines_csv": rel_csv,
                    "xstar_value_column": "emit_outward",
                    "solver_out_dir": out_dir,
                    "solver_command": solver_cmd,
                    "compare_command": compare_cmd,
                }
            )
    return rows


def write_readme(path: Path, rows: Sequence[dict]) -> None:
    lines: list[str] = []
    lines.append("# Mg XI / Ca XIX XSTAR triplet target plan\n")
    lines.append("Generated by `examples/47_prepare_mg_ca_xstar_triplet_targets.py`.\n")
    lines.append("Run XSTAR for the log-xi values that produce nonzero He-like triplet emission, convert the line FITS files, then compare the solver against the converted `emit_outward` target with `examples/43_compare_xstar_detail_populations.py`.\n")
    by_ion: dict[str, list[dict]] = {}
    for row in rows:
        by_ion.setdefault(str(row["ion"]), []).append(row)
    for ion, ion_rows in by_ion.items():
        lines.append(f"\n## {ion}\n")
        lines.append("Run and convert candidates:\n")
        lines.append("```bash")
        for row in ion_rows:
            lines.append(f"bash {row['run_script']}")
            lines.append(f"bash {row['convert_script']}")
        lines.append("```\n")
        lines.append("Solver/compare commands for each candidate target:\n")
        for row in ion_rows:
            lines.append(f"\n### {ion} logxi={row['rlogxi']} ne={row['electron_density_cm^-3']}\n")
            lines.append("```bash")
            lines.append(row["solver_command"])
            lines.append("\n")
            lines.append(row["compare_command"])
            lines.append("```")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--ions", default=DEFAULT_IONS)
    parser.add_argument("--density", type=float, default=1.0e8)
    parser.add_argument("--rlogxi-grid", nargs="*", default=[])
    parser.add_argument("--column", type=float, default=1.0e20)
    parser.add_argument("--vturbi", type=float, default=100.0)
    parser.add_argument("--temperature", type=float, default=100.0)
    parser.add_argument("--summary-csv", default="xstar_runs/mg_ca_triplet_target_plan.csv")
    parser.add_argument("--readme", default="xstar_runs/README_mg_ca_triplet_targets.md")
    parser.add_argument("--print-summary", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()
    ions = parse_ions(args.ions)
    rlogxi = parse_float_grid(args.rlogxi_grid, DEFAULT_RLOGXI)
    rows = build_rows(root, ions, args.density, rlogxi, args.column, args.vturbi, args.temperature)
    summary = root / args.summary_csv
    readme = root / args.readme
    write_csv(summary, rows)
    write_readme(readme, rows)
    if args.print_summary:
        print("Prepared Mg XI / Ca XIX XSTAR triplet target plan")
        print("--------------------------------------------------")
        print(f"root: {root}")
        print("ions:", ", ".join(ion_label(*ion) for ion in ions))
        print("density:", density_label(args.density))
        print("log xi grid:", ", ".join(density_label(x) for x in rlogxi))
        print(f"summary CSV: {summary}")
        print(f"README: {readme}")
        for row in rows:
            print(f"{row['ion']} logxi={row['rlogxi']}: bash {row['run_script']} ; bash {row['convert_script']}")


if __name__ == "__main__":
    main()
