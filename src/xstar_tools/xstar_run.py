"""XSTAR command/input handling and Python-output recreation planning.

This module provides the conservative command/parser and output-planning layer.
The executable translated physical runner is exposed separately by
``xstar_tools.xstar.physical_runner``; physical all-ATDB parity remains
an explicit benchmark gate rather than an assumption.  This module provides:

* parse a shell-style ``xstar key=value ...`` command into normalized inputs;
* list the standard XSTAR FITS products and the live internal state needed to
  recreate each one;
* write a machine-readable recreation plan that separates already-implemented,
  partially implemented, and missing source-code-parity components.

The goal is to make future pure-Python / C++-accelerated XSTAR emulation
explicit and testable instead of mixing benchmark-target extraction with solver
physics.
"""

from __future__ import annotations

import argparse
import csv
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


_BOOL_TRUE = {"yes", "true", "t"}
_BOOL_FALSE = {"no", "false", "f"}


def _coerce_xstar_value(text: str) -> Any:
    """Return a Python scalar for a simple XSTAR command value."""
    value = str(text).strip()
    low = value.lower()
    if low in _BOOL_TRUE:
        return True
    if low in _BOOL_FALSE:
        return False
    # Preserve strings with obvious non-numeric content.
    try:
        if any(ch in low for ch in (".", "e", "d")):
            return float(value.replace("D", "E").replace("d", "e"))
        return int(value)
    except Exception:
        return value


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


@dataclass
class XSTARInputParameters:
    """Normalized representation of an XSTAR command-line input set.

    Parameters are kept in a case-insensitive dictionary keyed by lower-case
    XSTAR names.  Values are lightly coerced to ``int``, ``float``, ``bool``, or
    ``str`` when possible.
    """

    parameters: Dict[str, Any] = field(default_factory=dict)
    original_tokens: List[str] = field(default_factory=list)
    source: Optional[str] = None

    def __post_init__(self) -> None:
        self.parameters = {str(k).strip().lower(): v for k, v in self.parameters.items()}

    def get(self, name: str, default: Any = None) -> Any:
        return self.parameters.get(str(name).strip().lower(), default)

    def require(self, names: Iterable[str]) -> Dict[str, Any]:
        missing = [name for name in names if self.get(name) is None]
        if missing:
            raise KeyError("Missing required XSTAR parameter(s): " + ", ".join(missing))
        return {name: self.get(name) for name in names}

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.parameters)

    def to_command(self) -> str:
        parts = ["xstar"]
        for key in sorted(self.parameters):
            value = self.parameters[key]
            sval = _format_value(value)
            if any(ch.isspace() for ch in sval) or any(ch in sval for ch in "'\\\"$"):
                sval = shlex.quote(sval)
            parts.append(f"{key}={sval}")
        return " ".join(parts)


def parse_xstar_command(command: str, *, source: Optional[str] = None) -> XSTARInputParameters:
    """Parse a shell-style ``xstar`` command into :class:`XSTARInputParameters`.

    The parser understands quoted strings and line continuations after normal
    shell tokenization by :mod:`shlex`.  Tokens without ``=`` are ignored except
    for the leading ``xstar`` executable token.
    """
    lexer = shlex.shlex(command, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = list(lexer)
    params: Dict[str, Any] = {}
    for token in tokens:
        if token == "\\":
            continue
        if token.lower() == "xstar":
            continue
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        key = key.strip().lower()
        if not key:
            continue
        params[key] = _coerce_xstar_value(value)
    return XSTARInputParameters(params, original_tokens=tokens, source=source)


def parse_xstar_command_file(path: str | Path) -> XSTARInputParameters:
    """Read and parse a file containing an XSTAR command."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return parse_xstar_command(text, source=str(path))


@dataclass(frozen=True)
class XSTAROutputProductSpec:
    """Description of one standard XSTAR output product."""

    filename: str
    purpose: str
    main_internal_state: tuple[str, ...]
    python_status: str
    next_python_components: tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "purpose": self.purpose,
            "main_internal_state": list(self.main_internal_state),
            "python_status": self.python_status,
            "next_python_components": list(self.next_python_components),
        }


STANDARD_XSTAR_OUTPUT_PRODUCTS: tuple[XSTAROutputProductSpec, ...] = (
    XSTAROutputProductSpec(
        "xout_abund1.fits",
        "radial-zone thermal, density, ionization, abundance, heating/cooling summary",
        ("zone geometry", "temperature", "electron density", "ion fractions", "heating/cooling balance"),
        "source-faithful default pprint writer implemented; physical all-ATDB radial parity pending",
        ("xstar_input driver", "ionization balance", "thermal balance", "abundance writer"),
    ),
    XSTAROutputProductSpec(
        "xout_lines1.fits",
        "integrated line list with inward/outward emission and line depths",
        ("level populations", "type-50/53/63/etc rates", "tau0", "escape probabilities", "line transfer"),
        "source-faithful final line writer implemented; physical all-ATDB parity pending",
        ("line-depth reconstruction", "calc_emis_ion parity", "FITS writer"),
    ),
    XSTAROutputProductSpec(
        "xout_rrc1.fits",
        "radiative recombination continuum output",
        ("recombination rates", "ion fractions", "continuum transfer", "temperature"),
        "source-faithful bounded writer implemented; physical all-ATDB parity pending",
        ("type-53/74 recombination parity", "RRC emissivity writer"),
    ),
    XSTAROutputProductSpec(
        "xout_cont1.fits",
        "continuum opacity/emissivity/transmission summary",
        ("epi", "opacity", "emissivity", "dpthc/tauc", "bremsa", "bremsint"),
        "source-faithful final continuum writer implemented; physical all-ATDB parity pending",
        ("continuum-grid API", "trnfrc parity", "continuum FITS writer"),
    ),
    XSTAROutputProductSpec(
        "xout_spect1.fits",
        "transmitted/emitted spectrum on the continuum grid",
        ("epi", "bremsa", "transmitted continuum", "line emission", "geometry"),
        "source-faithful bounded writer implemented; physical all-ATDB parity pending",
        ("spectrum assembly", "line+continuum transfer", "spectrum FITS writer"),
    ),
    XSTAROutputProductSpec(
        "xo01_detail.fits",
        "zone-local level populations and detail diagnostics",
        ("level populations", "global index", "ion fractions", "solver state"),
        "source-faithful detail FITS writer implemented; physical all-ATDB parity pending",
        ("population writer", "global-index parity", "detail FITS writer"),
    ),
    XSTAROutputProductSpec(
        "xo01_detal2.fits",
        "zone-local line detail including emissivities/opacities/tau_in/tau_out",
        ("tau0(1:2,line)", "line opacities", "line emissivities", "escape probabilities"),
        "source-faithful line-detail FITS writer implemented; physical all-ATDB parity pending",
        ("xstar_detail line-depth reader", "line-detail writer", "calc_hmc_ion parity"),
    ),
    XSTAROutputProductSpec(
        "xo01_detal3.fits",
        "additional zone-local diagnostics written by lprint/lwrite detail mode",
        ("heating/cooling/rate diagnostics", "local rates", "ion/level bookkeeping"),
        "source-faithful bounded writer implemented; physical all-ATDB parity pending; exact contents depend on XSTAR detail-mode branch",
        ("detail3 schema inspection", "rate-diagnostic writer"),
    ),
    XSTAROutputProductSpec(
        "xo01_detal4.fits",
        "zone-local continuum detail; enough to reconstruct epi, dpthc/tauc, and bremsa ingredients",
        ("epi", "zrems components", "continuum opacity", "fwd/bck dpth", "radius"),
        "source-faithful continuum-detail FITS writer implemented; physical all-ATDB parity pending",
        ("continuum-state reader", "bremsa reconstruction", "detail4 writer"),
    ),
)


def standard_xstar_output_products() -> List[Dict[str, Any]]:
    """Return standard XSTAR output-product specifications as dictionaries."""
    return [item.as_dict() for item in STANDARD_XSTAR_OUTPUT_PRODUCTS]


def xstar_recreation_plan(params: XSTARInputParameters | Mapping[str, Any]) -> Dict[str, Any]:
    """Build a source-code-parity plan for recreating standard XSTAR outputs.

    This is a planning/audit product, not a full simulation.  It is deliberately
    explicit about which pieces of Python physics are already available and
    which XSTAR internal arrays still need parity implementations.
    """
    if isinstance(params, XSTARInputParameters):
        pmap = params.as_dict()
        source = params.source
        command = params.to_command()
    else:
        pmap = {str(k).lower(): v for k, v in params.items()}
        source = None
        command = XSTARInputParameters(dict(pmap)).to_command()

    key_inputs = {
        "spectrum": pmap.get("spectrum"),
        "spectun": pmap.get("spectun"),
        "nsteps": pmap.get("nsteps"),
        "niter": pmap.get("niter"),
        "lwrite": pmap.get("lwrite"),
        "lprint": pmap.get("lprint"),
        "ncn2": pmap.get("ncn2"),
        "modelname": pmap.get("modelname"),
        "temperature": pmap.get("temperature"),
        "density": pmap.get("density"),
        "column": pmap.get("column"),
        "rlogxi": pmap.get("rlogxi"),
        "rlrad38": pmap.get("rlrad38"),
        "cfrac": pmap.get("cfrac"),
        "vturbi": pmap.get("vturbi"),
    }
    live_arrays_needed = [
        "epi(:)",
        "bremsa(:)",
        "bremsint(:)",
        "tau0(1:2,line)",
        "tauc/dpthc(1:2,continuum)",
        "cfrac",
        "vturbi",
        "temperature/electron density per zone",
        "ion fractions per zone",
        "level populations per zone",
    ]
    from .xstar_state import required_live_state_fields

    return {
        "status": "planning_only_not_full_xstar_recreation",
        "source": source,
        "normalized_command": command,
        "n_parameters": len(pmap),
        "parameters": pmap,
        "key_inputs": key_inputs,
        "live_arrays_needed_for_source_code_parity": live_arrays_needed,
        "live_state_schema": required_live_state_fields(),
        "output_products": standard_xstar_output_products(),
        "recommended_implementation_phases": [
            "1. Parse XSTAR inputs and build zone/radiation geometry exactly as XSTAR does.",
            "2. Reconstruct/compute continuum grid epi, bremsa, bremsint, dpthc/tauc per zone.",
            "3. Compute ion fractions and thermal balance until xout_abund1 parity is reached.",
            "4. Compute explicit-level populations with XSTAR ucalc/calc_hmc_ion parity.",
            "5. Write xo01_detail/xo01_detal2/3/4 from live state.",
            "6. Assemble xout_lines/xout_rrc/xout_cont/xout_spect from the same live state.",
            "7. Move hot loops to C++ only after Python row-by-row parity is established.",
        ],
    }


def write_xstar_recreation_plan(
    params: XSTARInputParameters | Mapping[str, Any],
    out_dir: str | Path,
    *,
    prefix: str = "xstar_python_recreation_plan",
) -> Dict[str, str]:
    """Write JSON, Markdown, and CSV recreation-plan products."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    plan = xstar_recreation_plan(params)
    json_path = out / f"{prefix}.json"
    md_path = out / f"{prefix}.md"
    csv_path = out / f"{prefix}_products.csv"
    json_path.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "purpose", "python_status", "main_internal_state", "next_python_components"])
        writer.writeheader()
        for product in plan["output_products"]:
            writer.writerow({
                "filename": product["filename"],
                "purpose": product["purpose"],
                "python_status": product["python_status"],
                "main_internal_state": "; ".join(product["main_internal_state"]),
                "next_python_components": "; ".join(product["next_python_components"]),
            })
    lines = [
        "# XSTAR Python output-recreation plan",
        "",
        f"Status: `{plan['status']}`",
        "",
        "## Key inputs",
        "",
    ]
    for key, value in plan["key_inputs"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines += ["", "## Live arrays needed", ""]
    for name in plan["live_arrays_needed_for_source_code_parity"]:
        lines.append(f"- `{name}`")
    lines += ["", "## Output products", "", "| File | Current Python status | Next components |", "|---|---|---|"]
    for product in plan["output_products"]:
        lines.append(
            f"| `{product['filename']}` | {product['python_status']} | "
            f"{'; '.join(product['next_python_components'])} |"
        )
    lines += ["", "## Implementation phases", ""]
    for phase in plan["recommended_implementation_phases"]:
        lines.append(f"- {phase}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path), "products_csv": str(csv_path)}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Create a Python XSTAR-output recreation plan from an XSTAR command.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--command", help="Shell-style xstar command string")
    group.add_argument("--command-file", help="File containing an xstar command, e.g. run_xstar.sh")
    parser.add_argument("--out-dir", default="xstar_python_recreation_plan", help="Output directory")
    parser.add_argument("--print-summary", action="store_true", help="Print written products and key status")
    args = parser.parse_args(argv)

    params = parse_xstar_command_file(args.command_file) if args.command_file else parse_xstar_command(args.command or "")
    paths = write_xstar_recreation_plan(params, args.out_dir)
    if args.print_summary:
        print("XSTAR Python output-recreation plan")
        print("-----------------------------------")
        print(f"n_parameters={len(params.parameters)}")
        for key, path in paths.items():
            print(f"{key}: {path}")
        print("status=planning_only_not_full_xstar_recreation")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
