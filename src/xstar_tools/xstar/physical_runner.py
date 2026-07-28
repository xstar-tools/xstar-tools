"""Public end-to-end execution API for the source-faithful Python XSTAR port.

The four public entry points in this module accept ordinary XSTAR parameter
names and execute the translated Python call graph.  They never invoke the
Fortran ``xstar`` executable and never read XSTAR-produced spectra, populations,
or rates as calculation inputs.

The first production scope is the constant-density, analytic-radius, built-in
power-law benchmark represented by ``helike_type69/c5_ne1``.  Unsupported
source branches fail explicitly instead of being approximated.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import copy
from hashlib import sha256
import json
import math
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from .source_real_energy_grid import source_ener_grid

from .. import __version__ as XSTAR_ATOMIC_VERSION
from ..data import resolve_atdb_path
from ..xstar_run import XSTARInputParameters, parse_xstar_command
from .atomic_database import (
    AtomicDatabaseBuildResult,
    AtomicDatabaseError,
    atomic_database_fingerprint,
    default_derived_pointer_cache_path,
    load_atomic_database_state,
)
from .bremsstrahlung import (
    BremsstrahlungContext,
    bremem_continuum_result,
)
from .compton import Comp2Context, comp2_continuum_result, load_compton_table
from .active_subsets import build_active_atdb_subset
from .backend_config import BackendSelection, resolve_backend_selection, install_backend_environment
from .compact_active_atdb import export_compact_active_atdb
from .cpp_backend_rates import rates_backend_status
from .cpp_backend_matrix import matrix_backend_status
from .cpp_backend_emissivity import emissivity_backend_status
from .cpp_backend_extra import opacity_backend_status, thermal_backend_status, engine_backend_status, eval_mg_ion_accumulator_cpp
from .dsec import CalcHMCAllDsecEvaluator, DsecMutableRuntimeState, dsec
from .linear_algebra import solver_backend_status
from .performance import normalize_profile_level, profile_component, summarize_profile, summarize_runtime_phase_map, summarize_matrix_assembly_dataflow, summarize_rate_payload_dataflow, summarize_rate_payload_batched_orchestration_shadow, summarize_rate_payload_four_family_product
from .element_equilibrium import EscapeProbabilityContext
from .emergent_emissivity import CalcEmisContext, CalcEmisWorkspace
from .continuum_diagnostics import write_continuum_diagnostics
from .emissivity import CalcEmisabContext
from .free_free import FreeFreeContext, freef_continuum_result
from .local_zone import FixedStateCalcHMCAllResult, FixedStateElementRequest
from .output_writers import (
    LevelOutputMetadata,
    LineOutputMetadata,
    OutputParameter,
    RRCOutputMetadata,
    SourceOutputMetadata,
    run_output_writer_sequence,
)
from .physical_benchmark_suite import (
    REQUIRED_XSTAR_PRODUCTS,
    ParsedXSTARCommand,
    parse_run_xstar_script,
    products_present,
)
from .physical_output_parity import (
    PhysicalOutputParityResult,
    compare_physical_output_directories,
)
from .radial_spectrum_parity import (
    compare_radial_spectrum_products,
    write_python_runtime_radial_spectrum_diagnostics,
)
from .pprint_legacy import (
    PprintAtomicMetadata,
    PprintElementMetadata,
    PprintIonMetadata,
)
from .radiation import nbinc
from .radial_transfer import (
    BoundedRadialShellResult,
    RadialTransferWorkspace,
    run_bounded_radial_multipass,
    run_bounded_radial_shell,
)
from .state import XSTARPythonState
from .thermal_balance import HeatFContext


class XSTARPythonRunnerError(RuntimeError):
    """Raised when the requested physical XSTAR command cannot run safely."""


class UnsupportedXSTARParameterError(XSTARPythonRunnerError):
    """Raised for a source branch not yet supported by the public runner."""


class XSTARPythonAcceptanceError(XSTARPythonRunnerError):
    """Raised when the strict ten-product or original-XSTAR parity gate fails."""


ProgressCallback = Callable[[str, Mapping[str, Any]], None]


def _emit_progress(
    callback: ProgressCallback | None,
    event: str,
    **details: Any,
) -> None:
    if callback is not None:
        callback(str(event), details)


def _remove_optional_diagnostic_products(out: Path) -> None:
    """Remove optional diagnostic products so reruns cannot retain stale files."""
    for dirname in (
        "radial_spectrum_diagnostics_v0499",
        "radial_spectrum_diagnostics_v0500",
    ):
        target = out / dirname
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    for name in (
        "xstar_tools_phase_snapshots.csv",
        "xstar_tools_phase_snapshots.jsonl",
        "xstar_tools_ucalc_continuum_side_effects.csv",
        "xstar_tools_ucalc_continuum_side_effects.jsonl",
        "xstar_tools_continuum_diagnostics_summary.json",
    ):
        target = out / name
        if target.exists():
            target.unlink()




def _append_xout_step_timing_footer(
    out: Path,
    *,
    timing: Mapping[str, float],
    output_breakdown: Mapping[str, float] | None = None,
) -> None:
    """Append source-like runtime accounting to ``xout_step.log``.

    This footer is intentionally independent of high-volume diagnostics.  It
    mirrors the original XSTAR convention closely enough for smoke/full
    benchmark tracking while keeping the values as reporting only.
    """
    path = out / "xout_step.log"
    if not path.exists():
        return
    total = float(timing.get("total", 0.0))
    minutes = int(total // 60.0)
    seconds = total - 60.0 * minutes
    lines = [
        "",
        f"after writespectra {float(timing.get('writespectra', 0.0)):.9g}",
        f"after writespectra2 {float(timing.get('writespectra2', 0.0)):.9g}",
        f"after writespectra3 {float(timing.get('writespectra3', 0.0)):.9g}",
        f"after writespectra4 {float(timing.get('writespectra4', 0.0)):.9g}",
    ]
    if output_breakdown:
        lines.append("output_writer_timing_breakdown:")
        for key in sorted(output_breakdown):
            try:
                value = float(output_breakdown[key])
            except Exception:
                continue
            lines.append(f"  {key} {value:.9g}")
    lines.extend([
        f"total time {total:.9g}",
        f"total time human {minutes:d} min {seconds:.3f} sec",
    ])
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

def _prepend_xout_step_startup_provenance(
    out: Path,
    *,
    state: XSTARPythonState,
    built: AtomicDatabaseBuildResult,
) -> None:
    """Prepend source-like version and ATDB provenance to ``xout_step.log``.

    Original XSTAR writes this block before the runtime report.  The Python
    product writer builds ``xout_step.log`` in one pass, so we prepend the
    equivalent immutable provenance after the file is written.  The values are
    reporting-only and do not alter physics arrays.
    """
    path = out / "xout_step.log"
    if not path.exists():
        return
    try:
        existing = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        existing = path.read_text(encoding="latin-1")
    if "xstar_tools version" in existing or "xstar_tools version" in existing:
        return

    master = built.master
    derived = built.derived
    ncn2 = int(state.control.get("ncn2", 9999))
    nry = int(state.control.get("nry", 0))
    if nry <= 0:
        try:
            nry = int(nbinc(13.6, state.radiation.epi, ncn2) + 2)
        except Exception:
            nry = 0
    date = str(getattr(master, "creation_date", "") or state.control.get("atcredate", "")).strip()
    lines = [
        f" xstar_tools version {XSTAR_ATOMIC_VERSION}",
        f" nry={nry:12d}{ncn2:12d}",
        " Loading Atomic Database...",
        f" Atomic Data Version: {date}",
        " in readtbl:",
        f" number of pointers={int(getattr(master, 'np2', 0)):12d}",
        f" number of reals={int(getattr(master, 'np1r', 0)):12d}",
        f" number of integers={int(getattr(master, 'np1i', 0)):12d}",
        f" number of characters={int(getattr(master, 'np1k', 0)):12d}",
        " initializing database...",
        f" number of lines={int(getattr(derived, 'nlsvn', 0)):12d}",
        f" number of rrcs={int(getattr(derived, 'ncsvn', 0)):12d}",
        " done with setptrs",
        "",
    ]
    path.write_text("\n".join(lines) + existing, encoding="utf-8")

def _normalize_diagnostics_mode(value: str | None) -> str:
    """Return the supported optional-diagnostic mode.

    ``full`` preserves the v0.5.35 behavior and writes high-volume runtime
    CSV/JSONL diagnostics.  ``summary`` keeps compact in-memory summary/parity
    information but suppresses high-volume runtime diagnostic products.
    ``none`` suppresses all optional runtime/parity diagnostic products while
    leaving the ten ordinary XSTAR products and main parity gate unchanged.
    """
    mode = "full" if value is None else str(value).strip().lower()
    if mode in {"on", "yes", "true", "1"}:
        return "full"
    if mode in {"off", "no", "false", "0"}:
        return "none"
    if mode not in {"full", "summary", "none"}:
        raise XSTARPythonRunnerError(
            f"invalid diagnostics mode {value!r}; expected full, summary, or none"
        )
    return mode


ERGSEV = 1.602197e-12
HC_EV_ANGSTROM = float(np.float32(12398.4016))
ELEMENT_SYMBOLS = (
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne",
    "Na", "Mg", "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca",
    "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn",
)
ABUNDANCE_PARAMETER_NAMES = tuple(symbol.lower() + "abund" for symbol in ELEMENT_SYMBOLS)
ATOMIC_MASS = (
    1.008, 4.003, 6.94, 9.012, 10.81, 12.011, 14.007, 15.999, 18.998, 20.180,
    22.990, 24.305, 26.982, 28.085, 30.974, 32.06, 35.45, 39.948, 39.098, 40.078,
    44.956, 47.867, 50.942, 51.996, 54.938, 55.845, 58.933, 58.693, 63.546, 65.38,
)
XDEF_ABUNDANCES = np.asarray(
    [
        1.00e0, 1.00e-1, 1.00e-10, 1.00e-10, 1.00e-10, 3.70e-4,
        1.10e-4, 6.80e-4, 3.98e-8, 2.80e-5, 1.78e-6, 3.50e-5,
        2.45e-6, 3.50e-5, 3.31e-7, 1.60e-5, 3.98e-7, 4.50e-6,
        8.91e-8, 2.10e-6, 1.66e-9, 1.35e-7, 2.51e-8, 7.08e-7,
        2.51e-7, 2.50e-5, 1.26e-7, 2.00e-6, 3.16e-8, 1.58e-8,
    ],
    dtype=float,
)

# Defaults are the values assigned in xstar.f90 before rread1, augmented by
# the ordinary parameter-file defaults for the public command interface.

# Literal xstar.f90 parname/partype/parcomm order used by fparmlist.
_XSTAR_OUTPUT_PARAMETER_ROWS: tuple[tuple[str, str, str], ...] = (
    ("cfrac", "real", " "),
    ("temperature", "real", "Units of 10**4 K"),
    ("lcpres", "integer", "1=yes, 0=no"),
    ("pressure", "real", "dynes/cm**2"),
    ("density", "real", "cm**(-3)"),
    ("spectrum", "string", " "),
    ("spectrum_file", "string", " "),
    ("spectun", "integer", "0=energy, 1=photons"),
    ("trad", "real", "or alpha"),
    ("rlrad38", "real", "/10**38 erg/sec"),
    ("column", "real", "cm**(-2)"),
    ("rlogxi", "real", " "),
    ("nsteps", "integer", " "),
    ("niter", "integer", " "),
    ("lwrite", "integer", "1=yes, 0=no"),
    ("lprint", "integer", "1=yes, 0=no"),
    ("lstep", "integer", " "),
    ("abundtbl", "string", "abundance table"),
    *((name, "real", " ") for name in ABUNDANCE_PARAMETER_NAMES),
    ("emult", "real", " "),
    ("taumax", "real", " "),
    ("xeemin", "real", " "),
    ("critf", "real", " "),
    ("vturbi", "real", " "),
    ("npass", "integer", " "),
    ("modelname", "string", " "),
    ("loopcontrol", "integer", " "),
)

XSTAR_PARAMETER_DEFAULTS: Mapping[str, Any] = {
    "spectrum": "pow",
    "spectrum_file": "spct.dat",
    "spectun": 0,
    "nsteps": 3,
    "niter": 0,
    "lwrite": 0,
    "lprint": 0,
    "lstep": 0,
    "npass": 1,
    "lcpres": 0,
    "emult": 0.5,
    "taumax": 5.0,
    "xeemin": 0.1,
    "critf": 1.0e-7,
    "radexp": 0.0,
    "ncn2": 9999,
    "modelname": "xstar-python",
    "abundtbl": "xdef",
    "trad": -1.0,
    "cfrac": 0.0,
    "temperature": 400.0,
    "pressure": 0.03,
    "density": 1.0e4,
    "rlrad38": 1.0e-6,
    "column": 1.0e17,
    "rlogxi": 5.0,
    "vturbi": 1.0,
    "loopcontrol": 0,
    **{
        name: (0.0 if name in {"liabund", "beabund", "babund"} else 1.0)
        for name in ABUNDANCE_PARAMETER_NAMES
    },
}


@dataclass(frozen=True)
class NormalizedXSTARParameters:
    """Typed source-compatible input values for one Python XSTAR run."""

    values: Mapping[str, Any]
    abundance_multipliers: np.ndarray
    baseline_abundances: np.ndarray
    physical_abundances: np.ndarray
    lcdd: int
    temperature_t4: float
    temperature_k: float
    density_cm3: float
    pressure_dyn_cm2: float
    luminosity_1e38: float
    ionization_parameter: float
    initial_radius_cm: float
    column_limit_cm2: float
    rmax_cm: float
    source: str | None = None

    def get(self, name: str, default: Any = None) -> Any:
        return self.values.get(str(name).strip().lower(), default)

    def as_dict(self) -> dict[str, Any]:
        result = dict(self.values)
        result.update(
            {
                "lcdd": self.lcdd,
                "temperature_k": self.temperature_k,
                "initial_radius_cm": self.initial_radius_cm,
                "physical_abundances": self.physical_abundances.tolist(),
            }
        )
        return result


@dataclass(frozen=True)
class XSTARPythonRunResult:
    """Result returned by all four public physical-runner APIs."""

    ready: bool
    parameters: NormalizedXSTARParameters
    output_dir: Path
    products: Mapping[str, Path]
    final_state: XSTARPythonState
    completed_passes: int
    completed_zones: int
    source_order: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def close(self) -> None:
        self.final_state.atomic.close()

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "parameters": self.parameters.as_dict(),
            "output_dir": str(self.output_dir),
            "products": {key: str(value) for key, value in self.products.items()},
            "completed_passes": self.completed_passes,
            "completed_zones": self.completed_zones,
            "source_order": list(self.source_order),
            "warnings": list(self.warnings),
            "provenance": dict(self.provenance),
        }


@dataclass(frozen=True)
class C5NE1AcceptanceResult:
    python_run: XSTARPythonRunResult
    original_run_dir: Path
    original_products_available: bool
    parity: PhysicalOutputParityResult | None
    all_ten_python_products_ready: bool
    all_files_match: bool

    @property
    def ready(self) -> bool:
        return bool(
            self.python_run.ready
            and self.all_ten_python_products_ready
            and self.original_products_available
            and self.parity is not None
            and self.parity.parity_run
            and self.all_files_match
        )

    def close(self) -> None:
        self.python_run.close()

    def __enter__(self) -> "C5NE1AcceptanceResult":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def as_dict(self) -> dict[str, Any]:
        return {
            "python_run": self.python_run.as_dict(),
            "original_run_dir": str(self.original_run_dir),
            "original_products_available": self.original_products_available,
            "all_ten_python_products_ready": self.all_ten_python_products_ready,
            "parity_run": bool(self.parity is not None and self.parity.parity_run),
            "all_files_match": self.all_files_match,
            "ready": self.ready,
            "xstar_outputs_used_as_python_inputs": False,
            "parity": None if self.parity is None else self.parity.as_dict(),
        }


@dataclass(frozen=True)
class XSTARPythonCacheResult:
    ready: bool
    atdb_path: Path
    pointer_cache_path: Path
    metadata_cache_path: Path
    pointer_cache_status: str
    metadata_cache_status: str
    n_records: int
    n_ions: int
    n_levels: int
    n_lines: int
    n_continua: int
    elapsed_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "atdb_path": str(self.atdb_path),
            "pointer_cache_path": str(self.pointer_cache_path),
            "metadata_cache_path": str(self.metadata_cache_path),
            "pointer_cache_status": self.pointer_cache_status,
            "metadata_cache_status": self.metadata_cache_status,
            "n_records": self.n_records,
            "n_ions": self.n_ions,
            "n_levels": self.n_levels,
            "n_lines": self.n_lines,
            "n_continua": self.n_continua,
            "elapsed_seconds": self.elapsed_seconds,
        }


def _sha256_file(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _value_map(parameters: XSTARInputParameters | ParsedXSTARCommand | Mapping[str, Any]) -> tuple[dict[str, Any], str | None]:
    if isinstance(parameters, XSTARInputParameters):
        return parameters.as_dict(), parameters.source
    if isinstance(parameters, ParsedXSTARCommand):
        return {str(k).strip().lower(): v for k, v in parameters.parameters.items()}, None
    return {str(k).strip().lower(): v for k, v in parameters.items()}, None


def normalize_xstar_parameters(
    parameters: XSTARInputParameters | ParsedXSTARCommand | Mapping[str, Any],
    *,
    zero_unspecified_abundances: bool = False,
    abundances: Mapping[str, float] | None = None,
) -> NormalizedXSTARParameters:
    """Apply source defaults and derive the ``rread1`` caller state."""

    supplied, source = _value_map(parameters)
    values = dict(XSTAR_PARAMETER_DEFAULTS)
    if zero_unspecified_abundances:
        for name in ABUNDANCE_PARAMETER_NAMES:
            values[name] = 0.0
    values.update(supplied)
    if abundances:
        by_symbol = {str(k).strip().lower(): float(v) for k, v in abundances.items()}
        for symbol, name in zip(ELEMENT_SYMBOLS, ABUNDANCE_PARAMETER_NAMES):
            if symbol.lower() in by_symbol:
                values[name] = by_symbol[symbol.lower()]

    spectrum = str(values["spectrum"]).strip().lower()
    if spectrum not in {"pow", "powerlaw", "power-law"}:
        raise UnsupportedXSTARParameterError(
            "the first public physical runner supports spectrum='pow' only; "
            f"observed {values['spectrum']!r}"
        )
    values["spectrum"] = "pow"
    abundance_table = str(values["abundtbl"]).strip().lower()[:4]
    if abundance_table != "xdef":
        raise UnsupportedXSTARParameterError(
            "the first public physical runner supports abundtbl='xdef' only"
        )
    values["abundtbl"] = abundance_table
    radexp = float(values["radexp"])
    if radexp < -99.0:
        raise UnsupportedXSTARParameterError(
            "run_xstar_python currently requires the analytic radial-density branch; "
            "tabulated density execution remains available through the lower-level radial API"
        )
    ncn2 = max(999, min(999_999, int(values["ncn2"])))
    values["ncn2"] = ncn2
    nsteps = int(values["nsteps"])
    if nsteps < 1:
        raise XSTARPythonRunnerError("nsteps must be positive")
    npass = int(values["npass"])
    if npass <= 0:
        npass = 1
    values["npass"] = npass
    niter = int(values["niter"])
    values["niter"] = niter
    lcpres = int(values["lcpres"])
    lcdd = 1 - lcpres if lcpres <= 1 else lcpres
    if lcdd not in (0, 1, 2):
        raise UnsupportedXSTARParameterError(f"unsupported lcpres/lcdd branch: {lcpres}/{lcdd}")

    t4 = float(values["temperature"])
    if not math.isfinite(t4) or t4 <= 0.0:
        raise XSTARPythonRunnerError("temperature must be positive in units of 1e4 K")
    pressure = float(values["pressure"])
    density = float(values["density"])
    xee_trial = 1.2
    if lcdd == 0:
        density = pressure / 1.38e-12 / max(t4, 1.0e-49)
    elif lcdd == 2:
        density = pressure / (xee_trial + 1.0e-34)
    if not math.isfinite(density) or density <= 0.0:
        raise XSTARPythonRunnerError("resolved hydrogen density must be positive")
    xlum = float(values["rlrad38"])
    xi = 10.0 ** float(values["rlogxi"])
    if lcdd == 0:
        ccc = 2.998e10
        r19 = math.sqrt(xlum / 12.56 / ccc / max(1.0e-49, pressure * xi))
    elif lcdd == 2:
        r19 = math.sqrt(xlum / max(1.0e-49, pressure * xi))
    else:
        r19 = math.sqrt(xlum / max(1.0e-49, density * xi))
    radius = r19 * 1.0e19
    column = float(values["column"])
    rmax = column / max(density, 1.0e-49)

    multipliers = np.asarray([float(values[name]) for name in ABUNDANCE_PARAMETER_NAMES])
    if np.any(~np.isfinite(multipliers)) or np.any(multipliers < 0.0):
        raise XSTARPythonRunnerError("element abundance multipliers must be finite and nonnegative")
    physical = multipliers * XDEF_ABUNDANCES
    values["density"] = density
    return NormalizedXSTARParameters(
        values=values,
        abundance_multipliers=multipliers,
        baseline_abundances=XDEF_ABUNDANCES.copy(),
        physical_abundances=physical,
        lcdd=lcdd,
        temperature_t4=t4,
        temperature_k=t4 * 1.0e4,
        density_cm3=density,
        pressure_dyn_cm2=pressure,
        luminosity_1e38=xlum,
        ionization_parameter=xi,
        initial_radius_cm=radius,
        column_limit_cm2=column,
        rmax_cm=rmax,
        source=source,
    )


def ener_grid(ncn2: int) -> np.ndarray:
    """Literal arithmetic-kind translation of ``ener.f90``."""
    try:
        return source_ener_grid(int(ncn2))
    except ValueError as exc:
        raise XSTARPythonRunnerError(str(exc)) from exc


def powerlaw_spectrum(*, index: float, luminosity_1e38: float, epi_eV: Sequence[float]) -> np.ndarray:
    """Translate ``ispec4 -> ispecgg`` for a built-in power law."""
    epi = np.asarray(epi_eV, dtype=float).reshape(-1)
    n = epi.size
    z = np.zeros(n, dtype=float)
    raw = np.where(epi > 0.01, np.power(epi, float(index)), 1.0e-24)
    nb1 = int(nbinc(13.6, epi, n))
    nb2 = int(nbinc(1.36e4, epi, n))
    total = 0.0
    for one in range(max(2, nb1), min(n, nb2) + 1):
        i = one - 1
        total += (raw[i] + raw[i - 1]) * (epi[i] - epi[i - 1]) / 2.0
    if total <= 0.0:
        raise XSTARPythonRunnerError("power-law 1-1000 Ry normalization is nonpositive")
    z += raw * (float(luminosity_1e38) / total / ERGSEV)

    # XSTAR immediately applies ispecgg, using a slightly different bin gate.
    total2 = 0.0
    for i in range(1, n):
        if 13.6 <= epi[i] <= 1.36e4:
            total2 += (z[i] + z[i - 1]) * (epi[i] - epi[i - 1]) / 2.0
    if total2 <= 0.0:
        raise XSTARPythonRunnerError("renormalized power-law luminosity is nonpositive")
    z *= float(luminosity_1e38) / total2 / ERGSEV
    return z


def photon_number_luminosity(zremsz: Sequence[float], epi_eV: Sequence[float]) -> float:
    """Translate the ``sum2`` result of ``ispcg2.f90``."""
    z = np.asarray(zremsz, dtype=float).reshape(-1)
    epi = np.asarray(epi_eV, dtype=float).reshape(-1)
    if z.size != epi.size:
        raise XSTARPythonRunnerError("ispcg2 arrays differ in length")
    total = 0.0
    for i in range(1, epi.size):
        if epi[i] >= 13.6:
            total += (z[i] / epi[i] + z[i - 1] / epi[i - 1]) * (epi[i] - epi[i - 1]) / 2.0
    return float(total)


OUTPUT_METADATA_CACHE_FORMAT_VERSION = 10


def default_output_metadata_cache_path(fitsfile: str | Path) -> Path:
    """Return the default vectorized output-metadata NPZ sidecar."""
    path = Path(fitsfile)
    return path.with_name(path.name + ".xstar_tools_output_metadata.npz")


def _cache_paths(atdb_path: str | Path, cache_dir: str | Path | None) -> tuple[Path, Path]:
    atdb = Path(atdb_path).resolve()
    if cache_dir is None:
        return default_derived_pointer_cache_path(atdb), default_output_metadata_cache_path(atdb)
    root = Path(cache_dir).expanduser().resolve()
    return (
        root / (atdb.name + ".xstar_tools_source_port.npz"),
        root / (atdb.name + ".xstar_tools_output_metadata.npz"),
    )


def _string_array(values: Sequence[str]) -> np.ndarray:
    text = [str(value) for value in values]
    width = max((len(value) for value in text), default=1)
    return np.asarray(text, dtype=f"U{max(1, width)}")


def save_source_output_metadata_cache(
    master: Any,
    metadata: SourceOutputMetadata,
    path: str | Path,
) -> Path:
    """Persist writer metadata as an uncompressed, vectorized NumPy NPZ."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    cache_metadata = {
        "format_version": OUTPUT_METADATA_CACHE_FORMAT_VERSION,
        "fingerprint": atomic_database_fingerprint(master),
        "cache_kind": "source_output_metadata",
        "layout": "vectorized_npz_v1",
    }
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=str(target.parent),
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            np.savez(
                handle,
                metadata_json=np.asarray(json.dumps(cache_metadata, separators=(",", ":"))),
                level_global_index=np.asarray([row.global_index for row in metadata.levels], dtype=np.int32),
                level_ion_index=np.asarray([row.ion_index for row in metadata.levels], dtype=np.int32),
                level_excitation_eV=np.asarray([row.excitation_eV for row in metadata.levels], dtype=np.float64),
                level_ion_label=_string_array([row.ion_label for row in metadata.levels]),
                level_atomic_number=np.asarray([row.atomic_number for row in metadata.levels], dtype=np.int16),
                level_label=_string_array([row.level_label for row in metadata.levels]),
                level_upper_index=np.asarray([row.upper_index for row in metadata.levels], dtype=np.int32),
                line_index=np.asarray([row.line_index for row in metadata.lines], dtype=np.int32),
                line_wavelength_angstrom=np.asarray([row.wavelength_angstrom for row in metadata.lines], dtype=np.float64),
                line_ion_label=_string_array([row.ion_label for row in metadata.lines]),
                line_lower_level=_string_array([row.lower_level for row in metadata.lines]),
                line_upper_level=_string_array([row.upper_level for row in metadata.lines]),
                line_rate_type=np.asarray([row.rate_type for row in metadata.lines], dtype=np.int16),
                line_data_type=np.asarray([row.data_type for row in metadata.lines], dtype=np.int16),
                line_atomic_mass=np.asarray([row.atomic_mass for row in metadata.lines], dtype=np.float64),
                line_natural_rate_s=np.asarray([row.natural_rate_s for row in metadata.lines], dtype=np.float64),
                line_auger_width_eV=np.asarray([row.auger_width_eV for row in metadata.lines], dtype=np.float64),
                line_auger_rate_s=np.asarray([row.auger_rate_s for row in metadata.lines], dtype=np.float64),
                line_source_record=np.asarray([row.source_record for row in metadata.lines], dtype=np.int64),
                line_lower_local_index=np.asarray([row.lower_local_index for row in metadata.lines], dtype=np.int32),
                line_upper_local_index=np.asarray([row.upper_local_index for row in metadata.lines], dtype=np.int32),
                rrc_continuum_index=np.asarray([row.continuum_index for row in metadata.rrcs], dtype=np.int32),
                rrc_level_global_index=np.asarray([row.level_global_index for row in metadata.rrcs], dtype=np.int32),
                rrc_threshold_eV=np.asarray([row.threshold_eV for row in metadata.rrcs], dtype=np.float64),
                rrc_ion_label=_string_array([row.ion_label for row in metadata.rrcs]),
                rrc_lower_level=_string_array([row.lower_level for row in metadata.rrcs]),
                rrc_upper_level=_string_array([row.upper_level for row in metadata.rrcs]),
                rrc_lower_local_index=np.asarray([row.lower_local_index for row in metadata.rrcs], dtype=np.int32),
                rrc_upper_local_index=np.asarray([row.upper_local_index for row in metadata.rrcs], dtype=np.int32),
                # v82 patch 5.20.15.1: these fields are part of the literal
                # xstarsetup/calc_emis rate-7 rank identity.  Omitting them
                # from the sidecar made every cache hit silently fall back to
                # the public RRC threshold; Type 49 must instead rank on
                # rdat1(np1r)*13.598 with default-REAL literal semantics.
                rrc_source_record=np.asarray([row.source_record for row in metadata.rrcs], dtype=np.int64),
                rrc_data_type=np.asarray([row.data_type for row in metadata.rrcs], dtype=np.int16),
                rrc_rank_threshold_eV=np.asarray([row.rank_threshold_eV for row in metadata.rrcs], dtype=np.float64),
            )
        os.replace(temporary_name, target)
    except Exception:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise
    return target


def load_source_output_metadata_cache(master: Any, path: str | Path) -> SourceOutputMetadata:
    """Load and validate vectorized writer metadata from an NPZ sidecar."""
    source = Path(path)
    with np.load(source, allow_pickle=False) as z:
        cache_metadata = json.loads(str(z["metadata_json"].item()))
        if int(cache_metadata.get("format_version", -1)) != OUTPUT_METADATA_CACHE_FORMAT_VERSION:
            raise AtomicDatabaseError(f"stale output metadata cache {source}: format version")
        if cache_metadata.get("fingerprint") != atomic_database_fingerprint(master):
            raise AtomicDatabaseError(f"stale output metadata cache {source}: ATDB fingerprint")
        levels = tuple(
            LevelOutputMetadata(
                global_index=int(a), ion_index=int(b), excitation_eV=float(c),
                ion_label=str(d), atomic_number=int(e), level_label=str(f), upper_index=int(g),
            )
            for a, b, c, d, e, f, g in zip(
                z["level_global_index"], z["level_ion_index"], z["level_excitation_eV"],
                z["level_ion_label"], z["level_atomic_number"], z["level_label"], z["level_upper_index"],
            )
        )
        lines = tuple(
            LineOutputMetadata(
                line_index=int(a), wavelength_angstrom=float(b), ion_label=str(c),
                lower_level=str(d), upper_level=str(e), rate_type=int(f), data_type=int(g),
                atomic_mass=float(h), natural_rate_s=float(i), auger_width_eV=float(j), auger_rate_s=float(k),
                source_record=int(l), lower_local_index=int(m), upper_local_index=int(n),
            )
            for a, b, c, d, e, f, g, h, i, j, k, l, m, n in zip(
                z["line_index"], z["line_wavelength_angstrom"], z["line_ion_label"],
                z["line_lower_level"], z["line_upper_level"], z["line_rate_type"],
                z["line_data_type"], z["line_atomic_mass"], z["line_natural_rate_s"],
                z["line_auger_width_eV"], z["line_auger_rate_s"],
                z["line_source_record"], z["line_lower_local_index"], z["line_upper_local_index"],
            )
        )
        rrcs = tuple(
            RRCOutputMetadata(
                continuum_index=int(a), level_global_index=int(b), threshold_eV=float(c),
                ion_label=str(d), lower_level=str(e), upper_level=str(f),
                lower_local_index=int(g), upper_local_index=int(h),
                source_record=int(i), data_type=int(j), rank_threshold_eV=float(k),
            )
            for a, b, c, d, e, f, g, h, i, j, k in zip(
                z["rrc_continuum_index"], z["rrc_level_global_index"], z["rrc_threshold_eV"],
                z["rrc_ion_label"], z["rrc_lower_level"], z["rrc_upper_level"],
                z["rrc_lower_local_index"], z["rrc_upper_local_index"],
                z["rrc_source_record"], z["rrc_data_type"], z["rrc_rank_threshold_eV"],
            )
        )
    return SourceOutputMetadata(
        levels=levels,
        lines=lines,
        rrcs=rrcs,
        provenance={
            "source": "readtbl/setptrs packed ATDB pointers",
            "source_faithful": True,
            "metadata_cache_status": "hit",
            "metadata_cache_path": str(source),
        },
    )


def _clean_label(raw: bytes | str, fallback: str) -> str:
    if isinstance(raw, bytes):
        text = raw.decode("latin-1", errors="replace")
    else:
        text = str(raw)
    text = " ".join(text.replace("\x00", " ").split())
    return text or fallback


def _record_to_ion_index(derived: Any) -> np.ndarray:
    """Build an O(1) record-to-ion map from source parent pointers."""
    n_records = int(np.asarray(derived.npar).size - 1)
    ion_record_to_index = np.zeros(n_records + 1, dtype=np.int32)
    ion_records = np.asarray(derived.ion_records, dtype=np.int64)
    valid_ions = np.flatnonzero(ion_records > 0)
    ion_record_to_index[ion_records[valid_ions]] = valid_ions.astype(np.int32)
    parent_records = np.asarray(derived.npar, dtype=np.int64)
    result = np.zeros_like(parent_records, dtype=np.int32)
    valid_parent = (parent_records > 0) & (parent_records < ion_record_to_index.size)
    result[valid_parent] = ion_record_to_index[parent_records[valid_parent]]
    # Ion-header records are useful to label themselves as well.
    result[ion_records[valid_ions]] = valid_ions.astype(np.int32)
    return result


def _build_binemis_type86_damping_map(
    master: Any, derived: Any
) -> dict[tuple[int, int], tuple[float, float, int]]:
    """Return literal ``binemis.f90`` Type-86 damping by (ion, upper level).

    ``binemis`` walks the rate-type-41 chain for an ion and matches the line
    upper local level to the second INTEGER in the Type-86 record.  On the
    first match, the third REAL is the Auger damping rate and the fourth REAL
    replaces the radiative ``egam`` rate.  Conversion to eV is deliberately
    deferred to the writer, where the source uses default-REAL ``4.14e-15``.
    """
    out: dict[tuple[int, int], tuple[float, float, int]] = {}
    if int(getattr(derived, "max_rate_type", 0)) < 41 or derived.npfi.shape[0] <= 41:
        return out
    npar = np.asarray(derived.npar, dtype=np.int64)
    npnxt = np.asarray(derived.npnxt, dtype=np.int64)
    for ion in range(1, int(derived.n_ions) + 1):
        rec = int(derived.npfi[41, ion])
        parent = int(npar[rec]) if 0 < rec < npar.size else 0
        guard = 0
        while 0 < rec < npar.size and int(npar[rec]) == parent:
            ints86 = np.asarray(master.record_integers(rec), dtype=np.int64).reshape(-1)
            reals86 = np.asarray(master.record_reals(rec), dtype=np.float64).reshape(-1)
            if ints86.size >= 2 and reals86.size >= 4:
                upper86 = int(ints86[1])
                key86 = (ion, upper86)
                if upper86 > 0 and key86 not in out:
                    out[key86] = (float(reals86[2]), float(reals86[3]), rec)
            nxt = int(npnxt[rec]) if rec < npnxt.size else 0
            if nxt == rec:
                raise AtomicDatabaseError(f"Type-86 record self-cycle at {rec}")
            rec = nxt
            guard += 1
            if guard > int(npar.size):
                raise AtomicDatabaseError("Type-86 record cycle")
    return out


def build_source_output_metadata(master: Any, derived: Any) -> SourceOutputMetadata:
    """Resolve packed ATDB pointers into writer metadata with vectorized reads.

    Only the variable-length character labels require small Python loops.  All
    parent resolution and scalar REALS/INTEGERS fields use direct NumPy gathers;
    the former per-RRC rebuild of an entire ion level table is eliminated.
    """
    pointers = np.asarray(master.nptrs.numpy())
    record_to_ion = _record_to_ion_index(derived)

    ion_labels: list[str] = [""] * (int(derived.n_ions) + 1)
    for ion_index in range(1, int(derived.n_ions) + 1):
        z = int(derived.ion_element_z[ion_index])
        stage = int(derived.ion_stage[ion_index])
        rec = int(derived.ion_records[ion_index])
        fallback = f"{ELEMENT_SYMBOLS[z-1]}_{stage}" if 1 <= z <= len(ELEMENT_SYMBOLS) else f"ion_{ion_index}"
        ion_labels[ion_index] = _clean_label(master.record_chars(rec), fallback)

    # ``setptrs`` assigns global population rows in packed-record order, but
    # ``calc_rates_level_lte`` fills ``leveltemp`` by the packed local level ID.
    # The source writers then pair ``npilev(mm,ion)`` with ``leveltemp(:,mm)``.
    # Therefore labels/energies must be resolved by (ion, local ID), not by the
    # record that happened to allocate a given global row.  This distinction is
    # observable for ions whose superlevel/continuum records are not ordered by
    # their local IDs (for example C IV in the canonical benchmark).
    level_records = np.asarray(
        derived.level_record_by_global_index[1 : int(derived.n_level_records) + 1],
        dtype=np.int64,
    )
    level_rows = pointers[level_records - 1]
    level_ions = record_to_ion[level_records]
    level_nreal = np.asarray(level_rows[:, 4], dtype=np.int64)
    level_nint = np.asarray(level_rows[:, 5], dtype=np.int64)
    level_rptr = np.asarray(level_rows[:, 7], dtype=np.int64)
    level_iptr = np.asarray(level_rows[:, 8], dtype=np.int64)
    excitation = np.zeros(level_records.size, dtype=np.float64)
    has_real = level_nreal > 0
    if np.any(has_real):
        excitation[has_real] = master.rdat1.gather(level_rptr[has_real], dtype=np.float64)
    packed_local_indices = np.zeros(level_records.size, dtype=np.int64)
    has_local = level_nint >= 2
    if np.any(has_local):
        packed_local_indices[has_local] = master.idat1.gather(
            level_iptr[has_local] + level_nint[has_local] - 2,
            dtype=np.int64,
        )
    ionization_potential = excitation.copy()
    has_ionpot = level_nreal > 3
    if np.any(has_ionpot):
        ionization_potential[has_ionpot] = master.rdat1.gather(
            level_rptr[has_ionpot] + 3,
            dtype=np.float64,
        )

    record_position_by_local: dict[tuple[int, int], int] = {}
    for pos, (ion_index, local_index) in enumerate(
        zip(level_ions, packed_local_indices)
    ):
        ion = int(ion_index)
        local = int(local_index)
        if ion > 0 and local > 0:
            # Literal leveltemp write semantics: a repeated local ID is owned by
            # the later source record.
            record_position_by_local[(ion, local)] = pos

    levels: list[LevelOutputMetadata] = []
    levels_by_key: dict[tuple[int, int], LevelOutputMetadata] = {}
    ionpot_by_key: dict[tuple[int, int], float] = {}
    npilev = np.asarray(derived.npilev, dtype=np.int64)
    nlevs = np.asarray(derived.nlevs, dtype=np.int64)
    for ion in range(1, int(derived.n_ions) + 1):
        z = int(derived.ion_element_z[ion])
        local_limit = int(nlevs[ion])
        for local in range(1, local_limit + 1):
            if local >= npilev.shape[0]:
                break
            global_index = int(npilev[local, ion])
            pos = record_position_by_local.get((ion, local))
            if global_index <= 0 or pos is None:
                continue
            rec = int(level_records[pos])
            row = LevelOutputMetadata(
                global_index=global_index,
                ion_index=ion,
                excitation_eV=float(excitation[pos]),
                ion_label=ion_labels[ion],
                atomic_number=z,
                level_label=_clean_label(master.record_chars(rec), f"level_{local}"),
                upper_index=local,
            )
            levels.append(row)
            key = (ion, local)
            levels_by_key[key] = row
            ionpot_by_key[key] = float(ionization_potential[pos])

    line_indices = np.arange(1, int(derived.nlsvn) + 1, dtype=np.int32)
    line_records = np.asarray(derived.nplin[1 : int(derived.nlsvn) + 1], dtype=np.int64)
    line_rows = pointers[line_records - 1]
    line_ions = record_to_ion[line_records]
    line_nreal = np.asarray(line_rows[:, 4], dtype=np.int64)
    line_nint = np.asarray(line_rows[:, 5], dtype=np.int64)
    line_rptr = np.asarray(line_rows[:, 7], dtype=np.int64)
    line_iptr = np.asarray(line_rows[:, 8], dtype=np.int64)
    wavelengths = np.zeros(line_records.size, dtype=np.float64)
    line_has_real = line_nreal > 0
    if np.any(line_has_real):
        wavelengths[line_has_real] = np.abs(
            master.rdat1.gather(line_rptr[line_has_real], dtype=np.float64)
        )
    lower = np.zeros(line_records.size, dtype=np.int64)
    upper = np.zeros(line_records.size, dtype=np.int64)
    has_lower = line_nint >= 1
    has_upper = line_nint >= 2
    if np.any(has_lower):
        lower[has_lower] = master.idat1.gather(line_iptr[has_lower], dtype=np.int64)
    if np.any(has_upper):
        upper[has_upper] = master.idat1.gather(line_iptr[has_upper] + 1, dtype=np.int64)
    natural = np.zeros(line_records.size, dtype=np.float64)
    natural_mask = line_nreal > 2
    if np.any(natural_mask):
        natural[natural_mask] = master.rdat1.gather(
            line_rptr[natural_mask] + 2,
            dtype=np.float64,
        )

    # v82 patch 5.20.15.4: resolve the writer-only Type-86 Auger damping
    # before constructing public line metadata.
    type86_by_ion_upper = _build_binemis_type86_damping_map(master, derived)

    lines: list[LineOutputMetadata] = []
    for pos, (line_index, ion_index) in enumerate(zip(line_indices, line_ions)):
        ion = int(ion_index)
        if ion <= 0:
            continue
        z = int(derived.ion_element_z[ion])
        low = int(lower[pos])
        up = int(upper[pos])
        low_row = levels_by_key.get((ion, low))
        up_row = levels_by_key.get((ion, up))
        auger = type86_by_ion_upper.get((ion, up))
        binemis_natural_rate = float(natural[pos])
        binemis_auger_rate = 0.0
        if auger is not None:
            binemis_auger_rate, binemis_natural_rate, _type86_record = auger
        lines.append(
            LineOutputMetadata(
                line_index=int(line_index),
                wavelength_angstrom=float(wavelengths[pos]),
                ion_label=ion_labels[ion],
                lower_level=(low_row.level_label if low_row else f"level_{low}"),
                upper_level=(up_row.level_label if up_row else f"level_{up}"),
                rate_type=int(line_rows[pos, 2]),
                data_type=int(line_rows[pos, 1]),
                atomic_mass=float(ATOMIC_MASS[z - 1]),
                natural_rate_s=binemis_natural_rate,
                auger_rate_s=binemis_auger_rate,
                source_record=int(line_records[pos]),
                lower_local_index=low,
                upper_local_index=up,
            )
        )

    continuum_indices = np.arange(1, int(derived.ncsvn) + 1, dtype=np.int32)
    continuum_records = np.asarray(derived.npcon[1 : int(derived.ncsvn) + 1], dtype=np.int64)
    continuum_rows = pointers[continuum_records - 1]
    continuum_ions = record_to_ion[continuum_records]
    continuum_nreal = np.asarray(continuum_rows[:, 4], dtype=np.int64)
    continuum_nint = np.asarray(continuum_rows[:, 5], dtype=np.int64)
    continuum_rptr = np.asarray(continuum_rows[:, 7], dtype=np.int64)
    continuum_iptr = np.asarray(continuum_rows[:, 8], dtype=np.int64)
    # Type-7 RRC source semantics from pprint.f90:
    #   idest1 = idat(np1i+nidt-2)
    #   idest2 = nlevp + idat(np1i-1+nidt-3) - 1
    # In zero-based gather coordinates this means the displayed lower local
    # bound level is the second-to-last INTEGER field, while the displayed
    # continuum/destination local level is nlevs(ion) plus the fourth-to-last
    # INTEGER field minus one.  v0.5.25 accidentally printed the final INTEGER
    # field (the ion/parent marker for this database) as the second local level,
    # producing e.g. c_vi 32 21 instead of source-like c_vi 32 33.
    continuum_local = np.zeros(continuum_records.size, dtype=np.int64)
    continuum_upper_seed = np.zeros(continuum_records.size, dtype=np.int64)
    continuum_has_local = continuum_nint >= 4
    if np.any(continuum_has_local):
        continuum_local[continuum_has_local] = master.idat1.gather(
            continuum_iptr[continuum_has_local] + continuum_nint[continuum_has_local] - 2,
            dtype=np.int64,
        )
        continuum_upper_seed[continuum_has_local] = master.idat1.gather(
            continuum_iptr[continuum_has_local] + continuum_nint[continuum_has_local] - 4,
            dtype=np.int64,
        )
    fallback_threshold = np.zeros(continuum_records.size, dtype=np.float64)
    continuum_has_real = continuum_nreal > 0
    if np.any(continuum_has_real):
        fallback_threshold[continuum_has_real] = master.rdat1.gather(
            continuum_rptr[continuum_has_real], dtype=np.float64,
        )

    # ``pprint.f90`` option 19 uses ``nlevp`` returned by
    # ``calc_rates_level_lte`` for the parent ion.  Source ``nlevp`` is the
    # ion level count used by ``leveltemp``; for RRC destination labels the
    # source then prints ``idest2 = nlevp + seed - 1``.  v0.5.27 estimated
    # ``nlevp`` from the maximum local level that appears in type-7 RRC rows.
    # That happened to fix H-like ions, but it was too small for He-like and
    # C V ions because their level blocks contain additional local levels not
    # referenced by the active type-7 rows.  Use the derived source level count
    # plus the continuum endpoint, matching the Fortran ``nlev`` semantics.
    # v0.5.28 added one extra level to nlevs, making every displayed
    # destination column one too high (34 instead of 33, 57 instead of 56).

    rrcs: list[RRCOutputMetadata] = []
    for pos, (continuum_index, ion_index, local, upper_seed) in enumerate(
        zip(continuum_indices, continuum_ions, continuum_local, continuum_upper_seed)
    ):
        ion = int(ion_index)
        local_index = int(local)
        upper_seed_index = int(upper_seed)
        if ion <= 0 or continuum_nint[pos] < 4:
            continue
        source_nlevp = int(nlevs[ion])
        upper_local_index = source_nlevp + upper_seed_index - 1 if upper_seed_index > 0 else 0
        level = levels_by_key.get((ion, local_index))
        # fstepr3.f90 writes ``eth = rlev(4,idest1)-rlev(1,idest1)``.
        # Type-13 level records store those as the fourth and first REAL
        # fields respectively.  v0.4.73-v0.4.75 used rlev(4) directly, which
        # collapsed every excited-level RRC of an ion onto the same ionization
        # potential and also fed incorrect wavelengths to calc_emis.
        threshold = _source_rrc_threshold_eV(
            level,
            ionpot_by_key.get((ion, local_index)),
            float(fallback_threshold[pos]),
        )
        global_level = (
            int(derived.npilev[local_index, ion])
            if 0 < local_index < derived.npilev.shape[0]
            else 0
        )
        data_type = int(continuum_rows[pos, 1])
        # Literal xstarsetup.f90 rate-7 rank coordinate.  Type 49 is special:
        #   eth = rdat1(np1r) * 13.598
        # with 13.598 a default REAL literal and with no 0.1-eV floor.  Other
        # rate-7 families use max(0.1d0, rlev(4)-rlev(1)).  Keep this distinct
        # from threshold_eV, which remains the physical fstepr3/UCalc edge.
        if data_type == 49:
            rank_threshold = float(fallback_threshold[pos]) * float(np.float32(13.598))
        else:
            rank_threshold = max(0.1, float(threshold))
        rrcs.append(
            RRCOutputMetadata(
                continuum_index=int(continuum_index),
                level_global_index=global_level,
                threshold_eV=float(threshold),
                ion_label=ion_labels[ion],
                lower_level=(level.level_label if level else f"level_{local_index}"),
                lower_local_index=local_index,
                upper_local_index=upper_local_index,
                source_record=int(continuum_records[pos]),
                data_type=data_type,
                rank_threshold_eV=float(rank_threshold),
            )
        )
    return SourceOutputMetadata(
        levels=tuple(levels),
        lines=tuple(lines),
        rrcs=tuple(rrcs),
        provenance={
            "source": "readtbl/setptrs packed ATDB pointers",
            "source_faithful": True,
            "metadata_builder": "vectorized_numpy_v9_rrc_literal_rank_cache",
            "metadata_cache_status": "built",
        },
    )


def _load_or_build_source_output_metadata(
    master: Any,
    derived: Any,
    *,
    cache_path: str | Path | None,
    use_cache: bool,
    rebuild_cache: bool,
) -> SourceOutputMetadata:
    path = None if cache_path is None else Path(cache_path)
    cache_failure: str | None = None
    if use_cache and path is not None and path.is_file() and not rebuild_cache:
        try:
            return load_source_output_metadata_cache(master, path)
        except (
            AtomicDatabaseError, OSError, ValueError, KeyError, TypeError,
            IndexError, EOFError, json.JSONDecodeError, zipfile.BadZipFile,
        ) as exc:
            # NPZ CRC/ZIP/member-read failures are cache corruption, not a
            # physical-run failure.  Rebuild from the authoritative ATDB and
            # atomically replace the damaged sidecar.
            cache_failure = exc.__class__.__name__
    metadata = build_source_output_metadata(master, derived)
    if use_cache and path is not None:
        save_source_output_metadata_cache(master, metadata, path)
        return SourceOutputMetadata(
            levels=metadata.levels,
            lines=metadata.lines,
            rrcs=metadata.rrcs,
            provenance={
                **dict(metadata.provenance),
                "metadata_cache_status": (
                    "rebuilt" if rebuild_cache
                    else "corrupt_rebuilt" if cache_failure is not None
                    else "miss_written"
                ),
                "metadata_cache_path": str(path),
                **(
                    {"metadata_cache_failure": cache_failure}
                    if cache_failure is not None else {}
                ),
            },
        )
    return metadata


def build_pprint_atomic_metadata(derived: Any, output_metadata: SourceOutputMetadata, abundances: np.ndarray) -> PprintAtomicMetadata:
    labels = tuple(ELEMENT_SYMBOLS)
    ion_label_by_index: dict[int, str] = {}
    for row in output_metadata.levels:
        ion_label_by_index.setdefault(int(row.ion_index), row.ion_label)
    ions: list[PprintIonMetadata] = []
    for ion_index in range(1, int(derived.n_ions) + 1):
        z = int(derived.ion_element_z[ion_index])
        stage = int(derived.ion_stage[ion_index])
        if z <= 0:
            continue
        ions.append(
            PprintIonMetadata(
                ion_index=ion_index,
                ion_label=ion_label_by_index.get(ion_index, f"{ELEMENT_SYMBOLS[z-1]}_{stage}"),
                element_index=z,
                elemental_abundance=float(abundances[z - 1]),
            )
        )
    thermal = tuple(PprintElementMetadata(i, symbol) for i, symbol in enumerate(ELEMENT_SYMBOLS, start=1))
    return PprintAtomicMetadata(
        element_labels=labels,
        ions=tuple(ions),
        thermal_elements=thermal,
        provenance={"source": "setptrs ion/element order", "source_faithful": True},
    )


def _guard(values: Sequence[float]) -> np.ndarray:
    arr = np.asarray(values, dtype=float).reshape(-1)
    return np.concatenate((np.zeros(1, dtype=float), arr))


def _radiation_namespace(state: XSTARPythonState) -> Any:
    return SimpleNamespace(
        epi=state.radiation.epi,
        bremsa=state.radiation.bremsa,
        epim=state.radiation.epim,
        epim_eV=state.radiation.epim,
        bremsam=state.radiation.bremsam,
        bremsint=state.radiation.bremsint,
    )


def _escape_context(workspace: RadialTransferWorkspace) -> EscapeProbabilityContext:
    return EscapeProbabilityContext(
        line_tau_in=workspace.tau0[0],
        line_tau_out=workspace.tau0[1],
        continuum_tau_in=workspace.tauc[0],
        continuum_tau_out=workspace.tauc[1],
        allow_missing_as_zero=False,
    )


def _element_requests(state: XSTARPythonState, parameters: NormalizedXSTARParameters) -> tuple[FixedStateElementRequest, ...]:
    workspace: RadialTransferWorkspace = state.control["radial_transfer_workspace"]
    radiation = _radiation_namespace(state)
    escape = _escape_context(workspace)
    capture_hydrogen_history = bool(
        state.control.get("zone1_dsec_capture_hydrogen_history", False)
    )
    requests: list[FixedStateElementRequest] = []
    for z, abundance in enumerate(parameters.physical_abundances, start=1):
        if float(abundance) <= 1.0e-24:
            continue
        requests.append(
            FixedStateElementRequest(
                element_z=z,
                min_ion_stage=1,
                max_ion_stage=z + 1,
                abundance=float(abundance),
                radiation=radiation,
                escape=escape,
                covering_fraction=float(parameters.get("cfrac")),
                turbulent_velocity_km_s=float(parameters.get("vturbi")),
                lfast=2,
                critf=float(parameters.get("critf")),
                use_source_ion_limits=True,
                initial_global_populations={},
                initial_population_source="xstar_init_zero_global_xilevg",
                terminal_continuum_seed_mode="source-zero",
                strict_context=True,
                allow_lstsq_fallback=False,
                allow_dense_matrix_rescue=False,
                capture_lucy_trace=bool(capture_hydrogen_history and int(z) == 1),
            )
        )
    if not requests:
        raise XSTARPythonRunnerError("no element has physical abundance above the XSTAR source floor")
    return tuple(requests)


def _calc_kwargs_factory(state: XSTARPythonState, compton_table: Any) -> Callable[[DsecMutableRuntimeState], Mapping[str, Any]]:
    def factory(runtime: DsecMutableRuntimeState) -> Mapping[str, Any]:
        epi = np.asarray(state.radiation.epim, dtype=float)
        brem = np.asarray(state.radiation.bremsam, dtype=float)[: epi.size]
        n = int(state.control["ncn2m"])
        opakc = runtime.work_arrays.get("opakc")
        brcems = runtime.work_arrays.get("brcems")
        if opakc is None:
            opakc = np.zeros(n, dtype=float)
        if brcems is None:
            brcems = np.zeros(n, dtype=float)
        # The Fortran sequence owns one mutable continuum workspace:
        #
        #   comp2 -> freef(opakc in/out) -> bremem(opakc after freef,
        #   brcems in/out) -> heatf(fresh leaf results)
        #
        # Context dataclasses are immutable snapshots, so construct them in
        # literal source order.  Building every context from the same incoming
        # arrays (the v0.4.73/v0.4.74 behavior) loses freef's in-place opakc
        # mutation before bremem and is rejected by calc_hmc_all.
        comp = Comp2Context(
            epi_eV=epi,
            bremsa=brem,
            table=compton_table,
            ncn2=n,
            source="run_xstar_python:comp2",
        )
        comp_result, _ = comp2_continuum_result(
            comp,
            temperature_k=runtime.temperature_k,
            hydrogen_density_cm3=runtime.hydrogen_density_cm3,
            electron_fraction_xee=runtime.electron_fraction_xee,
        )

        free = FreeFreeContext(
            epi_eV=epi,
            bremsa=brem,
            opakc_before_cm_inv=np.asarray(opakc, dtype=float)[:n],
            ncn2=n,
            source="run_xstar_python:freef",
        )
        free_result, _ = freef_continuum_result(
            free,
            temperature_k=runtime.temperature_k,
            hydrogen_density_cm3=runtime.hydrogen_density_cm3,
            electron_fraction_xee=runtime.electron_fraction_xee,
        )

        bremem = BremsstrahlungContext(
            epi_eV=epi,
            brcems_before=np.asarray(brcems, dtype=float)[:n],
            opakc_before_cm_inv=free_result.opakc_after_cm_inv,
            ncn2=n,
            source="run_xstar_python:bremem",
        )
        bremem_result, _ = bremem_continuum_result(
            bremem,
            temperature_k=runtime.temperature_k,
            hydrogen_density_cm3=runtime.hydrogen_density_cm3,
            electron_fraction_xee=runtime.electron_fraction_xee,
        )

        heat = HeatFContext(
            epi_eV=epi,
            brcems=bremem_result.brcems_after,
            htfreef_erg_cm3_s=free_result.htfreef_erg_cm3_s,
            cmp1=comp_result.cmp1,
            cmp2=comp_result.cmp2,
            httot_before=0.0,
            cltot_before=0.0,
            httot2_before=0.0,
            cltot2_before=0.0,
            radius_cm=float(state.transfer.radius),
            zone_thickness_cm=float(state.control.get("delr", 0.0)),
            ncn2=n,
            source="run_xstar_python:heatf",
        )
        production_mode = str(state.control.get("diagnostics_mode", "full")).lower() == "none"
        payload = {
            "compton_context": comp,
            "free_free_context": free,
            "bremem_context": bremem,
            "heatf_context": heat,
            # v0.5.42: production Mg/Ca runs should not copy source-sized
            # per-level/per-ion diagnostic spectra inside every repeated dsec
            # evaluation.  Dense native state arrays remain authoritative.
            "retain_diagnostic_arrays": not production_mode,
            "retain_element_results": not production_mode,
        }
        active_subset = state.control.get("active_atdb_subset")
        if active_subset is not None:
            payload["active_subset"] = active_subset
        if bool(state.control.get("profile_components", False)):
            payload["profile_control"] = state.control
        return payload
    return factory


def _guard_full_global_level_array(values: Sequence[float], derived: Any) -> np.ndarray:
    """Return the source-owned one-based ``nnml`` vector.

    ``calc_hmc_all`` may allocate its dense mutable arrays only through the
    largest global level index belonging to the elements active in the current
    model.  The original executable nevertheless owns full ``nnml`` arrays,
    with every inactive tail entry left at its initialized zero value.  Radial
    snapshots and ``fstepr`` detail writers therefore require that full source
    capacity rather than the active-element prefix.
    """

    array = np.asarray(values, dtype=float).reshape(-1)
    capacity = int(getattr(derived, "n_level_records", 0))
    npilev = np.asarray(getattr(derived, "npilev", ()), dtype=np.int64)
    if npilev.size:
        capacity = max(capacity, int(np.max(npilev)))
    capacity = max(capacity, int(array.size))
    guarded = np.zeros(capacity + 1, dtype=float)
    guarded[1 : array.size + 1] = array
    return guarded


def _commit_fixed_state(state: XSTARPythonState, runtime: DsecMutableRuntimeState, result: FixedStateCalcHMCAllResult) -> None:
    state.plasma.temperature = float(result.temperature_k)
    state.plasma.xpx = float(result.hydrogen_density_cm3)
    state.plasma.xee = float(result.electron_fraction_xee)
    state.plasma.electron_density = float(result.electron_density_cm3)
    state.plasma.ion_fractions = dict(result.ion_fractions)
    state.plasma.populations = _guard_full_global_level_array(
        result.global_xilevg_by_index, state.atomic.derived
    )
    state.thermal.heating = float(result.httot)
    state.thermal.cooling = float(result.cltot)
    state.thermal.residual = float(result.hmctot)
    state.thermal.electron_fraction = float(result.electron_fraction_xee)
    state.thermal.converged = bool(result.complete_fixed_state_ready)
    state.local_zone.calc_hmc_all = result
    state.local_zone.source_arrays.update(
        {
            "xilevg": _guard_full_global_level_array(
                result.global_xilevg_by_index, state.atomic.derived
            ),
            "bilevg": _guard_full_global_level_array(
                result.global_bilevg_by_index, state.atomic.derived
            ),
            "rnisg": _guard_full_global_level_array(
                result.global_rnisg_by_index, state.atomic.derived
            ),
            "xii": _ion_fraction_array(state.atomic.derived, result),
            "htt": _element_array(result.htt),
            "cll": _element_array(result.cll),
            "htt2": _element_array(result.htt2),
            "cll2": _element_array(result.cll2),
        }
    )
    state.control.update(
        {
            "htt": state.local_zone.source_arrays["htt"],
            "cll": state.local_zone.source_arrays["cll"],
            "htt2": state.local_zone.source_arrays["htt2"],
            "cll2": state.local_zone.source_arrays["cll2"],
            "xii": state.local_zone.source_arrays["xii"],
            "httot": float(result.httot),
            "cltot": float(result.cltot),
            "httot2": float(result.httot2),
            "cltot2": float(result.cltot2),
            "hmctot": float(result.hmctot),
            "htcomp": float(result.continuum.htcomp),
            "clcomp": float(result.continuum.clcomp),
            "clbrems": float(result.continuum.clbrems),
            "htfreef": float(result.continuum.htfreef),
            "physical_dsec_runtime": runtime,
        }
    )


def _ion_fraction_array(derived: Any, result: FixedStateCalcHMCAllResult) -> np.ndarray:
    values = np.zeros(int(derived.n_ions), dtype=float)
    for (z, stage), fraction in result.ion_fractions.items():
        index = result.global_ion_index_by_key.get((int(z), int(stage)), 0)
        if 1 <= int(index) <= values.size:
            values[int(index) - 1] = float(fraction)
    return values


def _element_array(values: Mapping[int, float]) -> np.ndarray:
    out = np.zeros(30, dtype=float)
    for z, value in values.items():
        if 1 <= int(z) <= 30:
            out[int(z) - 1] = float(value)
    return out


def _bind_emissivity_contexts(state: XSTARPythonState, parameters: NormalizedXSTARParameters, result: FixedStateCalcHMCAllResult) -> None:
    workspace: RadialTransferWorkspace = state.control["radial_transfer_workspace"]
    radiation = _radiation_namespace(state)
    escape = _escape_context(workspace)
    output_metadata: SourceOutputMetadata = state.control["output_atomic_metadata"]
    line_wavelength = np.zeros(int(state.control["nlsvn"]) + 1, dtype=float)
    for row in output_metadata.lines:
        if 1 <= row.line_index < line_wavelength.size:
            line_wavelength[row.line_index] = row.wavelength_angstrom
    rrc_wavelength = np.zeros(int(state.control["ncsvn"]) + 1, dtype=float)
    for row in output_metadata.rrcs:
        rank_threshold = float(getattr(row, "rank_threshold_eV", 0.0))
        if not (rank_threshold > 0.0):
            rank_threshold = float(row.threshold_eV)
        if 1 <= row.continuum_index < rrc_wavelength.size and rank_threshold > 0.0:
            # xstarsetup stores errc in wavelength units using the default-REAL
            # 12398.4016 literal.  HC_EV_ANGSTROM already carries that exact
            # float32->float64 promotion.
            rrc_wavelength[row.continuum_index] = HC_EV_ANGSTROM / max(1.0e-34, rank_threshold)

    common = dict(
        master=state.atomic.master,
        derived=state.atomic.derived,
        temperature_1e4K=float(state.plasma.temperature) / 1.0e4,
        electron_fraction_xee=float(state.plasma.xee),
        hydrogen_density_cm3=float(state.plasma.xpx),
        pressure_dyn_cm2=float(parameters.pressure_dyn_cm2),
        density_control_lcdd=int(parameters.lcdd),
        abundances_by_z={z: float(v) for z, v in enumerate(parameters.physical_abundances, start=1)},
        min_ion_stage_by_z=dict(result.mml),
        max_ion_stage_by_z=dict(result.mmu),
        xilevg=_guard_full_global_level_array(
            result.global_xilevg_by_index, state.atomic.derived
        ),
        bilevg=_guard_full_global_level_array(
            result.global_bilevg_by_index, state.atomic.derived
        ),
        rnisg=_guard_full_global_level_array(
            result.global_rnisg_by_index, state.atomic.derived
        ),
        radiation=radiation,
        escape=escape,
        covering_fraction=float(parameters.get("cfrac")),
        turbulent_velocity_km_s=float(parameters.get("vturbi")),
        critical_ion_fraction=float(parameters.get("critf")),
        radiation_temperature=float(parameters.get("trad")),
        radius_cm=float(state.transfer.radius),
        zone_thickness_cm=float(state.control.get("delr", 0.0)),
        lfast=2,
        strict_ucalc=True,
        initial_leveltemp_workspace=result.leveltemp_workspace,
        retain_traces=(str(state.control.get("diagnostics_mode", "full")).lower() != "none"),
        profile_control=state.control,
        progress_callback=state.control.get("progress_callback"),
        mg_line_kernel=str(state.control.get("mg_line_kernel", "python")),
    )
    active_subset = state.control.get("active_atdb_subset")
    if active_subset is not None:
        common["active_element_z"] = tuple(int(z) for z in getattr(active_subset, "active_element_z", ()))
        common["active_line_indices"] = np.asarray(getattr(active_subset, "line_indices", ()), dtype=np.int64)
        common["active_continuum_indices"] = np.asarray(getattr(active_subset, "continuum_indices", ()), dtype=np.int64)
        common["reusable_work_arrays"] = state.control.setdefault("calc_emis_all_work_arrays", {})
    emisab_common = dict(common)
    for key in (
        "retain_traces", "active_element_z", "active_line_indices",
        "active_continuum_indices", "reusable_work_arrays",
        "profile_control", "progress_callback", "mg_line_kernel",
    ):
        emisab_common.pop(key, None)
    state.control["calc_emisab_context"] = CalcEmisabContext(
        **emisab_common,
        workspace=workspace.emissivity.base,
        retain_traces=(str(state.control.get("diagnostics_mode", "full")).lower() != "none"),
        profile_control=state.control,
    )
    state.control["calc_emis_context"] = CalcEmisContext(
        **common,
        workspace=workspace.emissivity,
        line_wavelength_angstrom=line_wavelength,
        rrc_wavelength_angstrom=rrc_wavelength,
    )
    state.control["shared_emissivity_workspace"] = workspace.emissivity


def _source_rrc_threshold_eV(
    level: LevelOutputMetadata | None,
    ionization_potential_eV: float | None,
    fallback_eV: float,
) -> float:
    """Return the literal fstepr3 threshold ``rlev(4)-rlev(1)``.

    ``rlev(1)`` is the bound-level excitation energy and ``rlev(4)`` is the
    ionization-limit energy carried by the same type-13 level record.
    """
    if level is None or ionization_potential_eV is None:
        return float(fallback_eV)
    return float(ionization_potential_eV) - float(level.excitation_eV)


def _compact_dsec_diagnostics(
    runtime_state: XSTARPythonState,
    evaluator: CalcHMCAllDsecEvaluator,
    dsec_result: Any,
    *,
    max_cooling_terms_per_evaluation: int = 20,
) -> None:
    """Retain bounded, JSON-safe DSEC diagnostics for the physical gate.

    The full per-evaluation matrices are intentionally not retained.  For each
    trial we keep the thermal/charge residuals, per-element totals, C ion
    fractions, solver diagnostics, and the largest diagonal carbon cooling
    contributions.  These values are produced by the Python calculation only;
    original XSTAR products remain external comparison oracles.
    """
    store = runtime_state.control.setdefault(
        "physical_dsec_compact_diagnostics",
        {"evaluations": [], "carbon_cooling_terms": [], "shells": []},
    )
    evaluation_rows = store["evaluations"]
    cooling_rows = store["carbon_cooling_terms"]
    pass_index = int(runtime_state.transfer.pass_index)
    zone_index = int(runtime_state.transfer.zone_index)

    for evaluation_index, evaluation in enumerate(evaluator.evaluations, start=1):
        fixed = evaluation.fixed_state_result
        if fixed is None:
            continue
        carbon = next(
            (item for item in fixed.element_results if int(item.request.element_z) == 6),
            None,
        )
        row: dict[str, Any] = {
            "pass_index": pass_index,
            "zone_index": zone_index,
            "evaluation_index": evaluation_index,
            "temperature_K": float(fixed.temperature_k),
            "temperature_t4": float(fixed.temperature_k) / 1.0e4,
            "electron_fraction_xee": float(fixed.electron_fraction_xee),
            "elcter": float(fixed.elcter),
            "hmctot": float(fixed.hmctot),
            "httot": float(fixed.httot),
            "cltot": float(fixed.cltot),
            "carbon_heating": float(fixed.htt.get(6, 0.0)),
            "carbon_cooling": float(fixed.cll.get(6, 0.0)),
            "carbon_heating2": float(fixed.htt2.get(6, 0.0)),
            "carbon_cooling2": float(fixed.cll2.get(6, 0.0)),
            "dsec_lnerr": int(dsec_result.lnerr),
            "dsec_ntotit": int(dsec_result.ntotit),
        }
        if carbon is not None and carbon.equilibrium.solve is not None:
            solve = carbon.equilibrium.solve
            row.update(
                {
                    "carbon_solver_converged": bool(solve.converged),
                    "carbon_solver_method": str(solve.solver_method),
                    "carbon_dense_rank": int(solve.dense_rank),
                    "carbon_dense_condition_number": float(solve.dense_condition_number),
                    "carbon_max_active_relative_row_residual": float(
                        solve.max_active_relative_row_residual
                    ),
                    "carbon_normalization_error": float(solve.normalization_error),
                }
            )
            for stage in range(1, 8):
                row[f"carbon_stage_{stage}_fraction"] = float(
                    fixed.ion_fractions.get((6, stage), 0.0)
                )

            contributions: list[dict[str, Any]] = []
            assembly = carbon.equilibrium.assembly
            populations = np.asarray(solve.populations, dtype=float)
            abundance = float(carbon.request.abundance)
            for term in assembly.terms:
                if int(term.row) != int(term.column) or float(term.cj) <= 0.0:
                    continue
                compact_row = int(term.row)
                if compact_row < 1 or compact_row > populations.size:
                    continue
                population = float(populations[compact_row - 1])
                contribution_per_abundance = population * float(term.cj)
                contribution = contribution_per_abundance * abundance
                roles = assembly.basis.row(compact_row).roles
                contributions.append(
                    {
                        "pass_index": pass_index,
                        "zone_index": zone_index,
                        "evaluation_index": evaluation_index,
                        "temperature_K": float(fixed.temperature_k),
                        "hmctot": float(fixed.hmctot),
                        "record": int(term.record),
                        "data_type": int(term.data_type),
                        "rate_type": int(term.rate_type),
                        "compact_row": compact_row,
                        "population": population,
                        "cj": float(term.cj),
                        "contribution_per_abundance": contribution_per_abundance,
                        "physical_contribution": contribution,
                        "idest1": int(term.idest1),
                        "idest2": int(term.idest2),
                        "lower_endpoint": int(term.lower_endpoint),
                        "upper_endpoint": int(term.upper_endpoint),
                        "row_roles_json": json.dumps(roles, sort_keys=True),
                    }
                )
            contributions.sort(
                key=lambda item: abs(float(item["physical_contribution"])),
                reverse=True,
            )
            for rank, item in enumerate(
                contributions[: int(max_cooling_terms_per_evaluation)], start=1
            ):
                item["rank"] = rank
                cooling_rows.append(item)
        evaluation_rows.append(row)

    store["shells"].append(
        {
            "pass_index": pass_index,
            "zone_index": zone_index,
            "n_evaluations": len(evaluator.evaluations),
            "lnerr": int(dsec_result.lnerr),
            "ntotit": int(dsec_result.ntotit),
            "charge_converged": bool(dsec_result.charge_converged),
            "thermal_converged": bool(dsec_result.thermal_converged),
            "final_temperature_K": float(dsec_result.state.temperature_k),
            "final_hmctot": float(dsec_result.final_hmctot),
            "final_elcter": float(dsec_result.final_elcter),
        }
    )


def _install_physical_handlers(state: XSTARPythonState, parameters: NormalizedXSTARParameters, compton_table: Any) -> None:
    master = state.atomic.master
    derived = state.atomic.derived
    required = tuple(z for z, value in enumerate(parameters.physical_abundances, start=1) if value > 1.0e-24)
    if bool(state.control.get("active_subset_enabled", True)):
        with profile_component(
            state.control,
            "active_subset_build",
            pass_index=int(state.transfer.pass_index),
            zone_index=int(state.transfer.zone_index),
        ):
            active_subset = build_active_atdb_subset(master, derived, required)
        state.control["active_atdb_subset"] = active_subset
        state.provenance["active_atdb_subset"] = active_subset.as_summary()
    calc_kwargs_factory = _calc_kwargs_factory(state, compton_table)

    def build_runtime() -> DsecMutableRuntimeState:
        prior: DsecMutableRuntimeState | None = state.control.get("physical_dsec_runtime")
        return DsecMutableRuntimeState(
            temperature_t4=float(state.plasma.temperature) / 1.0e4,
            electron_fraction_xee=float(state.plasma.xee),
            hydrogen_density_cm3=float(state.plasma.xpx),
            element_requests=_element_requests(state, parameters),
            required_element_z=required,
            pressure=float(parameters.pressure_dyn_cm2),
            lcdd=int(parameters.lcdd),
            global_level_populations={} if prior is None else prior.global_level_populations,
            global_xilevg_by_index=None if prior is None else prior.global_xilevg_by_index,
            global_bilevg_by_index=None if prior is None else prior.global_bilevg_by_index,
            global_rnisg_by_index=None if prior is None else prior.global_rnisg_by_index,
            global_level_index_by_key={} if prior is None else prior.global_level_index_by_key,
            leveltemp_workspace=None,
            leveltemp_owner_by_column={},
            source_global_alias_writeback=True,
            reset_leveltemp_each_calc_hmc_all=True,
            retain_source_arrays=(str(state.control.get("diagnostics_mode", "full")).lower() != "none"),
        )

    def dsec_handler(runtime_state: XSTARPythonState) -> Any:
        runtime = build_runtime()

        def dsec_progress(
            evaluation_index: int,
            mutable: DsecMutableRuntimeState,
            fixed: FixedStateCalcHMCAllResult,
        ) -> None:
            if not bool(runtime_state.control.get("progress_debug", False)):
                return
            carbon_cooling = float(fixed.cll.get(6, 0.0))
            _emit_progress(
                runtime_state.control.get("progress_callback"),
                "dsec_evaluation",
                pass_index=int(runtime_state.transfer.pass_index),
                zone_index=int(runtime_state.transfer.zone_index),
                evaluation_index=int(evaluation_index),
                temperature_K=float(fixed.temperature_k),
                electron_fraction=float(fixed.electron_fraction_xee),
                hmctot=float(fixed.hmctot),
                elcter=float(fixed.elcter),
                carbon_cooling=carbon_cooling,
            )

        retain_dsec_results = str(
            runtime_state.control.get("diagnostics_mode", "full")
        ).lower() != "none"
        evaluator = CalcHMCAllDsecEvaluator(
            master=master,
            derived=derived,
            calc_kwargs_factory=calc_kwargs_factory,
            progress_callback=dsec_progress,
            retain_fixed_state_results=retain_dsec_results,
            capture_all_input_snapshots=bool(
                runtime_state.control.get("zone1_dsec_capture_all_inputs", False)
            ),
            capture_lucy_trace_element_z=(
                (1, 6)
                if bool(runtime_state.control.get("zone1_dsec_capture_hydrogen_history", False))
                else ()
            ),
            evaluation_gate_callback=runtime_state.control.get(
                "zone1_dsec_evaluation_gate_callback"
            ),
        )
        result = dsec(
            runtime,
            evaluator=evaluator,
            nlim=int(runtime_state.control.get("nlimdt", parameters.get("niter"))),
            tinf_t4=float(runtime_state.control.get("tinf", 0.099)),
        )
        if bool(result.state.provenance.get("dsec_native_orchestration", False)):
            summary = runtime_state.control.setdefault("native_thermal_engine_summary", {
                "schema_version": "0.6.48.3", "heatt_calls": 0, "continuum_bins": 0,
                "line_records": 0, "rrc_records": 0, "heatt_state_commits": 0,
                "heatt_ffi_seconds": 0.0, "heatt_native_seconds": 0.0,
                "dsec_calls": 0, "dsec_evaluations": 0, "dsec_state_commits": 0,
                "dsec_orchestration_seconds": 0.0, "dsec_callback_seconds": 0.0,
                "dsec_trace_events": 0, "dsec_trace_truncated_calls": 0,
                "dsec_terminal_statuses": [], "callback_state_propagation": True,
                "fallbacks": 0,
            })
            summary["dsec_calls"] += 1
            summary["dsec_evaluations"] += int(result.ntotit)
            summary["dsec_state_commits"] += int(result.state.calc_hmc_all_call_count)
            summary["dsec_orchestration_seconds"] += float(result.state.provenance.get("dsec_orchestration_seconds", 0.0))
            summary["dsec_callback_seconds"] += float(result.state.provenance.get("dsec_callback_seconds", 0.0))
            summary["charge_converged"] = bool(result.charge_converged)
            summary["thermal_converged"] = bool(result.thermal_converged)
            summary["lnerr"] = int(result.lnerr)
            summary["dsec_trace_events"] += int(result.state.provenance.get("dsec_trace_count", len(result.trajectory)))
            summary["dsec_trace_truncated_calls"] += int(bool(result.state.provenance.get("dsec_trace_truncated", False)))
            summary["callback_state_propagation"] = bool(result.state.provenance.get("dsec_callback_state_propagation", False))
            summary["dsec_terminal_statuses"].append({
                "call_index": int(summary["dsec_calls"]),
                "lnerr": int(result.lnerr),
                "ntotit": int(result.ntotit),
                "charge_converged": bool(result.charge_converged),
                "thermal_converged": bool(result.thermal_converged),
                "final_temperature_t4": float(result.state.temperature_t4),
                "final_electron_fraction_xee": float(result.state.electron_fraction_xee),
                "final_hmctot": float(result.final_hmctot),
                "final_elcter": float(result.final_elcter),
                "final_event": str(result.trajectory[-1].event if result.trajectory else ""),
            })
        if bool(runtime_state.control.get("zone1_dsec_capture_all_inputs", False)) and evaluator.input_snapshots:
            target_temperature_k = float(
                runtime_state.control.get("zone1_dsec_target_temperature_k", 73198.4)
            )
            source_snapshot = min(
                evaluator.input_snapshots,
                key=lambda item: abs(float(item.temperature_k) - target_temperature_k),
            )
            target_xee = float(
                runtime_state.control.get(
                    "zone1_dsec_target_electron_fraction_xee",
                    source_snapshot.electron_fraction_xee,
                )
            )
            target_xpx = float(
                runtime_state.control.get(
                    "zone1_dsec_target_hydrogen_density_cm3",
                    source_snapshot.hydrogen_density_cm3,
                )
            )
            free_context = source_snapshot.calc_kwargs.get("free_free_context")
            bremem_context = source_snapshot.calc_kwargs.get("bremem_context")
            opakc = None if free_context is None else np.asarray(
                getattr(free_context, "opakc_before_cm_inv", ()), dtype=float
            ).copy()
            brcems = None if bremem_context is None else np.asarray(
                getattr(bremem_context, "brcems_before", ()), dtype=float
            ).copy()
            target_runtime = DsecMutableRuntimeState(
                temperature_t4=target_temperature_k / 1.0e4,
                electron_fraction_xee=target_xee,
                hydrogen_density_cm3=target_xpx,
                element_requests=tuple(
                    replace(
                        copy.deepcopy(request),
                        capture_lucy_trace=(int(request.element_z) in (1, 6)),
                    )
                    for request in source_snapshot.element_requests
                ),
                required_element_z=source_snapshot.required_element_z,
                pressure=float(source_snapshot.pressure),
                lcdd=int(source_snapshot.lcdd),
                global_level_populations=dict(source_snapshot.global_level_populations),
                global_xilevg_by_index=None if source_snapshot.global_xilevg_by_index is None else np.asarray(source_snapshot.global_xilevg_by_index, dtype=float).copy(),
                global_bilevg_by_index=None if source_snapshot.global_bilevg_by_index is None else np.asarray(source_snapshot.global_bilevg_by_index, dtype=float).copy(),
                global_rnisg_by_index=None if source_snapshot.global_rnisg_by_index is None else np.asarray(source_snapshot.global_rnisg_by_index, dtype=float).copy(),
                global_level_index_by_key=dict(source_snapshot.global_level_index_by_key),
                leveltemp_workspace=copy.deepcopy(source_snapshot.leveltemp_workspace),
                leveltemp_owner_by_column=copy.deepcopy(source_snapshot.leveltemp_owner_by_column),
                source_global_alias_writeback=bool(source_snapshot.source_global_alias_writeback),
                reset_leveltemp_each_calc_hmc_all=True,
                work_arrays={"opakc": opakc, "brcems": brcems},
            )
            target_evaluator = CalcHMCAllDsecEvaluator(
                master=master,
                derived=derived,
                calc_kwargs_factory=calc_kwargs_factory,
                dispatcher=copy.deepcopy(source_snapshot.dispatcher_state),
                element_solver=copy.deepcopy(source_snapshot.element_solver_state),
                pre_matrix_solver=copy.deepcopy(source_snapshot.pre_matrix_solver_state),
            )
            target_evaluation = target_evaluator(target_runtime)
            runtime_state.control["zone1_dsec_target_result"] = target_evaluation.fixed_state_result
            runtime_state.control["zone1_dsec_target_metadata"] = {
                "source": "fixed_target_state_replay",
                "source_evaluation_index": int(source_snapshot.evaluation_index),
                "source_temperature_K": float(source_snapshot.temperature_k),
                "target_temperature_K": target_temperature_k,
                "target_electron_fraction_xee": target_xee,
                "target_hydrogen_density_cm3": target_xpx,
                "xstar_target_state_used": bool(
                    runtime_state.control.get("zone1_dsec_xstar_target_state_used", False)
                ),
            }
        if str(runtime_state.control.get("diagnostics_mode", "full")).lower() != "none":
            _compact_dsec_diagnostics(runtime_state, evaluator, result)
        runtime_state.control["physical_dsec_runtime"] = result.state
        runtime_state.control["physical_calc_evaluator"] = evaluator
        runtime_state.plasma.temperature = result.state.temperature_k
        runtime_state.plasma.xee = result.state.electron_fraction_xee
        runtime_state.plasma.xpx = result.state.hydrogen_density_cm3
        runtime_state.control["ntotit"] = int(result.ntotit)
        # Do not cosmetically adjust the source-style print option 17 iteration
        # count.  If Python takes one more thermal-balance iteration than XSTAR,
        # that is a physics/control-flow parity issue to diagnose, not a display
        # issue to hide.  Keep the printed count identical to the translated raw
        # ntotit until the extra iteration is removed at the source.
        runtime_state.control["legacy_pprint_ntotit"] = int(result.ntotit)
        runtime_state.control["legacy_pprint_hc1_percent"] = float(result.final_hmctot) * 100.0
        runtime_state.control["lnerrd"] = int(result.lnerr)
        try:
            terminal_rows = runtime_state.control.setdefault("dsec_terminal_summary", [])
            call_index = len(terminal_rows) + 1
            terminal_rows.append({
                "call_index": int(call_index),
                "native_orchestration": bool(result.state.provenance.get("dsec_native_orchestration", False)),
                "callback_state_propagation": bool(result.state.provenance.get("dsec_callback_state_propagation", False)),
                "lnerr": int(result.lnerr),
                "ntotit": int(result.ntotit),
                "temperature_iterations": int(result.temperature_iterations),
                "temperature_attempts": int(result.temperature_attempts),
                "charge_converged": bool(result.charge_converged),
                "thermal_converged": bool(result.thermal_converged),
                "source_returned": bool(result.source_returned),
                "prefix_terminated": bool(result.prefix_terminated),
                "final_temperature_t4": float(result.state.temperature_t4),
                "final_electron_fraction_xee": float(result.state.electron_fraction_xee),
                "final_hmctot": float(result.final_hmctot),
                "final_elcter": float(result.final_elcter),
                "final_event": str(result.trajectory[-1].event if result.trajectory else ""),
            })
            trajectory_rows = runtime_state.control.setdefault("dsec_residual_trajectory_summary", [])
            trajectory_rows.extend([
                {
                    "call_index": int(call_index),
                    "event_index": int(row.event_index),
                    "evaluation_index": int(row.evaluation_index),
                    "ntotit": int(row.ntotit),
                    "nnt": int(row.nnt),
                    "nntt": int(row.nntt),
                    "nnx": int(row.nnx),
                    "nnxx": int(row.nnxx),
                    "temperature_K": float(row.temperature_k),
                    "electron_fraction": float(row.electron_fraction_xee),
                    "hmctot": None if row.hmctot is None else float(row.hmctot),
                    "elcter": None if row.elcter is None else float(row.elcter),
                    "normalized_charge_residual": None if row.normalized_charge_residual is None else float(row.normalized_charge_residual),
                    "temperature_stagnation_metric": None if row.temperature_stagnation_metric is None else float(row.temperature_stagnation_metric),
                    "lnerr": int(row.lnerr),
                    "event": str(row.event),
                }
                for row in result.trajectory
            ])
            runtime_state.control["dsec_residual_trajectory_summary"] = trajectory_rows[-1024:]
        except Exception as exc:
            runtime_state.control.setdefault("dsec_trace_capture_errors", []).append(str(exc))
        return result

    def calc_hmc_all_handler(runtime_state: XSTARPythonState) -> FixedStateCalcHMCAllResult:
        runtime: DsecMutableRuntimeState | None = runtime_state.control.get("physical_dsec_runtime")
        if runtime is None:
            runtime = build_runtime()
        else:
            runtime.temperature_t4 = float(runtime_state.plasma.temperature) / 1.0e4
            runtime.electron_fraction_xee = float(runtime_state.plasma.xee)
            runtime.hydrogen_density_cm3 = float(runtime_state.plasma.xpx)
            runtime.element_requests = _element_requests(runtime_state, parameters)
        evaluator = CalcHMCAllDsecEvaluator(
            master=master,
            derived=derived,
            calc_kwargs_factory=calc_kwargs_factory,
        )
        with profile_component(
            runtime_state.control,
            "calc_hmc_all_final",
            pass_index=int(runtime_state.transfer.pass_index),
            zone_index=int(runtime_state.transfer.zone_index),
        ):
            evaluation = evaluator(runtime)
        if evaluation.fixed_state_result is None:
            raise XSTARPythonRunnerError("calc_hmc_all evaluator returned no fixed-state result")
        result = evaluation.fixed_state_result
        runtime_state.control["physical_dsec_runtime"] = runtime
        _commit_fixed_state(runtime_state, runtime, result)
        _bind_emissivity_contexts(runtime_state, parameters, result)
        return result

    state.control["dsec_source_handler"] = dsec_handler
    state.control["calc_hmc_all_source_handler"] = calc_hmc_all_handler


def _resolve_runner_atdb_path(atdb_path: str | Path | None) -> Path:
    """Resolve the production ATDB using the package-wide path policy."""
    return Path(resolve_atdb_path(atdb_path, prompt=False)).resolve()


def _build_initial_state(
    parameters: NormalizedXSTARParameters,
    *,
    atdb_path: str | Path,
    coheat_path: str | Path | None = None,
    pointer_cache: str | Path | None = None,
    metadata_cache: str | Path | None = None,
    use_cache: bool = True,
    rebuild_cache: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> tuple[XSTARPythonState, AtomicDatabaseBuildResult]:
    _emit_progress(
        progress_callback,
        "atdb_load_start",
        atdb_path=str(Path(atdb_path).resolve()),
        pointer_cache=str(pointer_cache) if pointer_cache is not None else None,
    )
    built = load_atomic_database_state(
        atdb_path,
        abundances=np.ones(30, dtype=float),
        llinabs=True,
        pointer_cache=pointer_cache,
        use_pointer_cache=use_cache,
        rebuild_pointer_cache=rebuild_cache,
    )
    _emit_progress(
        progress_callback,
        "atdb_load_done",
        pointer_cache_status=str(built.derived.provenance.get("pointer_cache_status", "not_used")),
        n_records=int(built.master.np2),
        n_ions=int(built.derived.n_ions),
        n_levels=int(built.derived.n_level_records),
        n_lines=int(built.derived.nlsvn),
        n_continua=int(built.derived.ncsvn),
    )
    state = XSTARPythonState(atomic=built.atomic_state)
    state.control["progress_callback"] = progress_callback
    derived = built.derived
    ncn2 = int(parameters.get("ncn2"))
    ncn2m = 999
    epi = ener_grid(ncn2)
    epim = ener_grid(ncn2m)
    zremsz = powerlaw_spectrum(
        index=float(parameters.get("trad")),
        luminosity_1e38=float(parameters.luminosity_1e38),
        epi_eV=epi,
    )
    shared = CalcEmisWorkspace.allocate(
        n_lines=int(derived.nlsvn),
        n_continua=int(derived.ncsvn),
        n_energy=ncn2,
    )
    workspace = RadialTransferWorkspace(
        emissivity=shared,
        zremsz=zremsz.copy(),
        dpthc=np.zeros((2, ncn2), dtype=float),
        dpthcont=np.zeros((2, ncn2), dtype=float),
        tau0=np.zeros((2, int(derived.nlsvn)), dtype=float),
        tauc=np.zeros((2, int(derived.ncsvn)), dtype=float),
        zrems=np.zeros((5, ncn2), dtype=float),
        zremso=np.zeros((5, ncn2), dtype=float),
        elumab=np.zeros((2, int(derived.ncsvn)), dtype=float),
        elumabo=np.zeros((2, int(derived.ncsvn)), dtype=float),
        elum=np.zeros((2, int(derived.nlsvn)), dtype=float),
        elumo=np.zeros((2, int(derived.nlsvn)), dtype=float),
    )
    workspace.zrems[0, :] = zremsz
    workspace.zremso[0, :] = zremsz

    state.radiation.epi = epi
    state.radiation.bremsa = np.zeros(ncn2, dtype=float)
    state.radiation.epim = epim
    # xstar.f90 allocates bremsam(ncn) and bremsint(ncn), even though
    # bremsmap/dsec consume only rows 1:ncn2m.  trnfrc owns bremsint on the
    # full high-resolution 1:ncn2 range, while bremsmap also reads the
    # reduced-grid boundary row ncn2m+1.  Preserve that shared full-capacity
    # source array and let ucalc expose only the active 1:ncn2m views.
    state.radiation.bremsam = np.zeros(ncn2, dtype=float)
    state.radiation.bremsint = np.zeros(ncn2, dtype=float)
    state.radiation.zrems = workspace.zrems
    state.radiation.zremso = workspace.zremso
    state.plasma.temperature = parameters.temperature_k
    state.plasma.xpx = parameters.density_cm3
    state.plasma.xee = 1.0
    state.plasma.electron_density = parameters.density_cm3
    state.plasma.abundances = parameters.physical_abundances.copy()
    state.transfer.radius = parameters.initial_radius_cm
    state.transfer.radial_depth = 0.0
    state.transfer.column = 0.0
    state.control.update(
        {
            "radial_transfer_workspace": workspace,
            "preallocated_emissivity_workspace": shared,
            "ncn2": ncn2,
            "ncn2m": ncn2m,
            "nlsvn": int(derived.nlsvn),
            "ncsvn": int(derived.ncsvn),
            "nlimd": int(parameters.get("niter")),
            "nlimdt": int(parameters.get("niter")),
            "emult": float(parameters.get("emult")),
            "xpxcol": parameters.column_limit_cm2,
            "taumax": float(parameters.get("taumax")),
            "xeemin": float(parameters.get("xeemin")),
            "numrec": int(parameters.get("nsteps")),
            "nsteps_normalized": int(parameters.get("nsteps")),
            "nsteps_run_script": int(parameters.get("nsteps")),
            "nsteps_pfile_default": int(XSTAR_PARAMETER_DEFAULTS.get("nsteps", 3)),
            "npass": int(parameters.get("npass")),
            "xlum": float(parameters.luminosity_1e38),
            "tinf": 0.099,
            "trad": float(parameters.get("trad")),
            # Physical-runner plasma temperature is always stored in kelvin.
            # Writer adapters use this explicit ownership flag instead of a
            # magnitude heuristic (which misrendered the 990 K floor as T4=990).
            "plasma_temperature_unit": "K",
            "vturbi": float(parameters.get("vturbi")),
            "radexp": float(parameters.get("radexp")),
            "lcdd": int(parameters.lcdd),
            # xstar.f90 passes lprisv=0 to the product-building pprint calls.
            # Verbose lprint>0 adds terminal diagnostic reports only; the
            # structured ten-product comparator intentionally ignores them.
            "lpri": 0,
            "requested_lpri": int(parameters.get("lprint")),
            "lwri": int(parameters.get("lwrite")),
            "lfix": int(parameters.get("lstep")),
            "cfrac": float(parameters.get("cfrac")),
            "critf": float(parameters.get("critf")),
            "p": float(parameters.pressure_dyn_cm2),
            "zeta": float(parameters.get("rlogxi")),
            "xi": float(parameters.ionization_parameter),
            "rmax": float(parameters.rmax_cm),
            "spectype": "pow",
            "specfile": str(parameters.get("spectrum_file")),
            "specunit": int(parameters.get("spectun")),
            "kmodelname": str(parameters.get("modelname")),
            "abndtbl": str(parameters.get("abundtbl")),
            "abel": parameters.abundance_multipliers.copy(),
            "ababs": parameters.physical_abundances.copy(),
            "enlum": photon_number_luminosity(zremsz, epi),
            "output_writers_enabled": True,
            "pprint_legacy_enabled": True,
            "continuum_phase_snapshot_enabled": True,
            "ucalc_continuum_side_effect_diagnostics_enabled": True,
            "ntotit": 0,
            "lnerrd": 0,
            "atcredate": str(getattr(built.master, "creation_date", "")),
        }
    )
    _emit_progress(
        progress_callback,
        "metadata_start",
        metadata_cache=str(metadata_cache) if metadata_cache is not None else None,
    )
    metadata = _load_or_build_source_output_metadata(
        built.master,
        derived,
        cache_path=metadata_cache,
        use_cache=use_cache,
        rebuild_cache=rebuild_cache,
    )
    _emit_progress(
        progress_callback,
        "metadata_done",
        metadata_cache_status=str(metadata.provenance.get("metadata_cache_status", "not_used")),
        n_levels=len(metadata.levels),
        n_lines=len(metadata.lines),
        n_rrcs=len(metadata.rrcs),
    )
    state.control["output_atomic_metadata"] = metadata
    state.control["pprint_atomic_metadata"] = build_pprint_atomic_metadata(
        derived, metadata, parameters.physical_abundances
    )
    table = load_compton_table(coheat_path, atdb_path=atdb_path)
    _install_physical_handlers(state, parameters, table)
    state.provenance["physical_runner"] = {
        "source_files": [
            "xstar/src/xstar/xstar.f90", "xstar/xstarlib/src/rread1.f90",
            "xstar/xstarlib/src/ener.f90", "xstar/xstarlib/src/ispec4.f90",
            "xstar/xstarlib/src/ispecgg.f90", "xstar/xstarlib/src/ispcg2.f90",
        ],
        "atdb_path": str(Path(atdb_path).resolve()),
        "atdb_sha256": _sha256_file(atdb_path),
        "xstar_outputs_used_as_inputs": False,
    }
    return state, built


def prepare_xstar_python_cache(
    *,
    atdb_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
    rebuild_cache: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> XSTARPythonCacheResult:
    """Build or validate the vectorized pointer and output-metadata NPZ caches."""
    start = time.perf_counter()
    resolved = _resolve_runner_atdb_path(atdb_path)
    pointer_cache, metadata_cache = _cache_paths(resolved, cache_dir)
    _emit_progress(
        progress_callback,
        "cache_prepare_start",
        atdb_path=str(resolved),
        pointer_cache=str(pointer_cache),
        metadata_cache=str(metadata_cache),
        rebuild_cache=bool(rebuild_cache),
    )
    built = load_atomic_database_state(
        resolved,
        abundances=np.ones(30, dtype=float),
        llinabs=True,
        pointer_cache=pointer_cache,
        use_pointer_cache=True,
        rebuild_pointer_cache=rebuild_cache,
    )
    try:
        metadata = _load_or_build_source_output_metadata(
            built.master,
            built.derived,
            cache_path=metadata_cache,
            use_cache=True,
            rebuild_cache=rebuild_cache,
        )
        result = XSTARPythonCacheResult(
            ready=pointer_cache.is_file() and metadata_cache.is_file(),
            atdb_path=resolved,
            pointer_cache_path=pointer_cache,
            metadata_cache_path=metadata_cache,
            pointer_cache_status=str(built.derived.provenance.get("pointer_cache_status", "not_used")),
            metadata_cache_status=str(metadata.provenance.get("metadata_cache_status", "not_used")),
            n_records=int(built.master.np2),
            n_ions=int(built.derived.n_ions),
            n_levels=int(built.derived.n_level_records),
            n_lines=int(built.derived.nlsvn),
            n_continua=int(built.derived.ncsvn),
            elapsed_seconds=float(time.perf_counter() - start),
        )
        _emit_progress(progress_callback, "cache_prepare_done", **result.as_dict())
        return result
    finally:
        built.atomic_state.close()


def _output_parameters(parameters: NormalizedXSTARParameters) -> tuple[OutputParameter, ...]:
    """Build the literal 56-row xstar.f90/fparmlist parameter table."""
    rows: list[OutputParameter] = []
    for name, parameter_type, comment in _XSTAR_OUTPUT_PARAMETER_ROWS:
        value = parameters.get(name)
        if parameter_type == "string":
            rows.append(OutputParameter(name, 0.0, parameter_type, str(value)))
        else:
            rows.append(OutputParameter(name, float(value), parameter_type, comment))
    if len(rows) != 56:
        raise XSTARPythonRunnerError(f"source fparmlist requires 56 rows; built {len(rows)}")
    return tuple(rows)


def run_xstar_from_parameters(
    parameters: XSTARInputParameters | ParsedXSTARCommand | Mapping[str, Any],
    *,
    atdb_path: str | Path | None = None,
    output_dir: str | Path = ".",
    input_dir: str | Path | None = None,
    coheat_path: str | Path | None = None,
    zero_unspecified_abundances: bool = False,
    abundances: Mapping[str, float] | None = None,
    overwrite: bool = True,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    rebuild_cache: bool = False,
    progress_callback: ProgressCallback | None = None,
    diagnostics_mode: str = "full",
    active_subset: bool = True,
    profile_components: str | bool = "none",
    profile_rss: bool = False,
    profile_backend_calls: bool = False,
    profile_terminal: bool = False,
    progress_debug: bool = False,
    mg_line_kernel: str = "python",
    backend: str = "python",
    rates_backend: str | None = None,
    matrix_backend: str | None = None,
    emissivity_backend: str | None = None,
    compact_atdb_export: str | Path | None = None,
    output_final_recompute: bool = True,
) -> XSTARPythonRunResult:
    """Execute the translated Python XSTAR path from normalized parameters."""
    total_start_time = time.perf_counter()
    runtime_phase_wall_timing: dict[str, float] = {}
    diagnostics_mode = _normalize_diagnostics_mode(diagnostics_mode)
    backend_selection = resolve_backend_selection(
        global_backend=backend,
        solver_backend=os.environ.get("XSTAR_ATOMIC_SOLVER_BACKEND", "python"),
        rates_backend=rates_backend,
        matrix_backend=matrix_backend,
        emissivity_backend=emissivity_backend,
    )
    install_backend_environment(backend_selection)
    del input_dir  # Reserved for spectrum/density-file source branches.
    resolved_atdb = _resolve_runner_atdb_path(atdb_path)
    normalized = normalize_xstar_parameters(
        parameters,
        zero_unspecified_abundances=zero_unspecified_abundances,
        abundances=abundances,
    )
    pointer_cache_path, metadata_cache_path = _cache_paths(resolved_atdb, cache_dir)
    _emit_progress(
        progress_callback,
        "physical_run_start",
        atdb_path=str(resolved_atdb),
        output_dir=str(Path(output_dir)),
        use_cache=bool(use_cache),
        rebuild_cache=bool(rebuild_cache),
    )
    out = Path(output_dir)
    _output_setup_t0 = time.perf_counter()
    out.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        _present, missing = products_present(out)
        if not missing:
            raise XSTARPythonRunnerError(f"all output products already exist in {out}")
    else:
        for name in REQUIRED_XSTAR_PRODUCTS:
            target = out / name
            if target.exists():
                target.unlink()
        _remove_optional_diagnostic_products(out)
    runtime_phase_wall_timing["output_cleanup_seconds"] = float(time.perf_counter() - _output_setup_t0)

    _initial_state_t0 = time.perf_counter()
    state, built = _build_initial_state(
        normalized,
        atdb_path=resolved_atdb,
        coheat_path=coheat_path,
        pointer_cache=pointer_cache_path,
        metadata_cache=metadata_cache_path,
        use_cache=use_cache,
        rebuild_cache=rebuild_cache,
        progress_callback=progress_callback,
    )
    runtime_phase_wall_timing["initialization_atomic_data_loading_seconds"] = float(time.perf_counter() - _initial_state_t0)
    state.control["runtime_phase_wall_timing"] = runtime_phase_wall_timing
    state.control["backend_selection"] = backend_selection.as_dict()
    state.provenance["backend_selection"] = backend_selection.as_dict()
    compact_export_summary = None
    if compact_atdb_export is not None:
        active_subset_obj = state.control.get("active_atdb_subset")
        _emit_progress(progress_callback, "compact_atdb_export_start", path=str(compact_atdb_export))
        compact_result = export_compact_active_atdb(
            built.master,
            built.derived,
            compact_atdb_export,
            active_subset=active_subset_obj,
        )
        compact_export_summary = compact_result.as_dict()
        state.provenance["compact_active_atdb_export"] = compact_export_summary
        _emit_progress(
            progress_callback,
            "compact_atdb_export_done",
            path=str(compact_result.path),
            n_active_ions=compact_result.n_active_ions,
            n_active_rate_records=compact_result.n_active_rate_records,
        )
    high_volume_diagnostics = diagnostics_mode == "full"
    state.control["diagnostics_mode"] = diagnostics_mode
    state.control["active_subset_enabled"] = bool(active_subset)
    state.control["profile_components"] = normalize_profile_level(profile_components)
    state.control["profile_rss"] = bool(profile_rss)
    state.control["profile_backend_calls"] = bool(profile_backend_calls)
    state.control["profile_terminal"] = bool(profile_terminal)
    state.control["progress_debug"] = bool(progress_debug)
    state.control["output_final_recompute"] = bool(output_final_recompute)
    state.control["mg_line_kernel"] = str(mg_line_kernel).strip().lower()
    state.control["radial_spectrum_parity_diagnostic_enabled"] = high_volume_diagnostics
    state.control["continuum_phase_snapshot_enabled"] = high_volume_diagnostics
    state.control["ucalc_continuum_side_effect_diagnostics_enabled"] = high_volume_diagnostics
    try:
        _emit_progress(
            progress_callback,
            "radial_start",
            requested_passes=int(normalized.get("npass")),
            first_pass_shell_count=int(normalized.get("nsteps")),
        )
        _radial_t0 = time.perf_counter()
        radial = run_bounded_radial_multipass(
            state,
            first_pass_shell_count=int(normalized.get("nsteps")),
            pass_count=int(normalized.get("npass")),
        )
        runtime_phase_wall_timing["radial_multipass_seconds"] = float(time.perf_counter() - _radial_t0)
        _emit_progress(
            progress_callback,
            "radial_done",
            completed_passes=len(radial.pass_results),
            completed_zones=sum(len(item.shell_results) for item in radial.pass_results),
        )
        if high_volume_diagnostics:
            _radial_diag_t0 = time.perf_counter()
            radial_diag_products = write_python_runtime_radial_spectrum_diagnostics(state, out)
            runtime_phase_wall_timing["radial_spectrum_diagnostics_seconds"] = float(time.perf_counter() - _radial_diag_t0)
            state.outputs["radial_spectrum_diagnostics_v0499_products"] = radial_diag_products
            _emit_progress(
                progress_callback,
                "radial_spectrum_diagnostic_done",
                product_count=len(radial_diag_products),
            )
        else:
            radial_diag_products = {}
            state.outputs["radial_spectrum_diagnostics_v0499_products"] = radial_diag_products
            _emit_progress(
                progress_callback,
                "radial_spectrum_diagnostic_skipped",
                diagnostics_mode=diagnostics_mode,
            )
        _emit_progress(
            progress_callback,
            "output_writer_start",
            output_dir=str(out),
            final_local_recompute=bool(output_final_recompute),
        )
        writer_start_time = time.perf_counter()
        writer = run_output_writer_sequence(
            state,
            out_dir=out,
            lwri=int(normalized.get("lwrite")),
            parameters=_output_parameters(normalized),
            model_name=str(normalized.get("modelname")),
            atomic_data_date=str(getattr(built.master, "creation_date", "")),
            final_local_recompute=bool(output_final_recompute),
            progress_callback=progress_callback,
        )
        writer_elapsed = time.perf_counter() - writer_start_time
        runtime_phase_wall_timing["output_writer_sequence_seconds"] = float(writer_elapsed)
        writer_breakdown = dict(getattr(writer, "timing_breakdown", {}) or {})
        _prepend_xout_step_startup_provenance(out, state=state, built=built)
        # The current writer API builds/writes the four final products as one
        # source-sequence call.  Record the exact aggregate elapsed time on
        # writespectra and explicit zeroes for the subordinate product writers
        # until they are split into separately timed calls.
        timing_footer = {
            "writespectra": float(writer_elapsed),
            "writespectra2": 0.0,
            "writespectra3": 0.0,
            "writespectra4": 0.0,
            "total": float(time.perf_counter() - total_start_time),
        }
        _append_xout_step_timing_footer(out, timing=timing_footer, output_breakdown=writer_breakdown)
        state.outputs["xout_step_timing_footer"] = dict(timing_footer)
        state.outputs["output_writer_timing_breakdown"] = dict(writer_breakdown)
        _emit_progress(
            progress_callback,
            "output_writer_done",
            source_order=list(writer.source_order),
            writer_elapsed_seconds=float(writer_elapsed),
            timing_footer=dict(timing_footer),
            timing_breakdown=dict(writer_breakdown),
        )
        if high_volume_diagnostics:
            _continuum_diag_t0 = time.perf_counter()
            continuum_diag_products = write_continuum_diagnostics(state, out)
            runtime_phase_wall_timing["continuum_diagnostics_seconds"] = float(time.perf_counter() - _continuum_diag_t0)
            if continuum_diag_products:
                state.outputs["continuum_diagnostics_products_v0530"] = continuum_diag_products
            _emit_progress(
                progress_callback,
                "continuum_diagnostic_done",
                product_count=len(continuum_diag_products),
            )
        else:
            continuum_diag_products = {}
            state.outputs["continuum_diagnostics_products_v0530"] = continuum_diag_products
            _emit_progress(
                progress_callback,
                "continuum_diagnostic_skipped",
                diagnostics_mode=diagnostics_mode,
            )
        present, missing = products_present(out)
        products = {name: out / name for name in present}
        completed_zones = sum(len(item.shell_results) for item in radial.pass_results)
        ready = not missing
        if not ready:
            raise XSTARPythonAcceptanceError(
                "Python XSTAR run did not create the strict ten-product set; missing: "
                + ", ".join(missing)
            )
        source_order = tuple(state.provenance.get("completed_source_routines", ())) + tuple(writer.source_order)
        runtime_phase_wall_timing["total_run_seconds"] = float(time.perf_counter() - total_start_time)
        state.control["runtime_phase_wall_timing"] = dict(runtime_phase_wall_timing)
        runtime_phase_timing_summary = summarize_runtime_phase_map(
            state.control,
            explicit_timing=runtime_phase_wall_timing,
            output_breakdown=writer_breakdown,
            top_n=int(os.environ.get("XSTAR_ATOMIC_RUNTIME_PHASE_TOP_N", "25") or "25"),
        )
        result = XSTARPythonRunResult(
            ready=True,
            parameters=normalized,
            output_dir=out,
            products=products,
            final_state=state,
            completed_passes=len(radial.pass_results),
            completed_zones=completed_zones,
            source_order=source_order,
            warnings=(
                ("lprint>0 verbose terminal diagnostic branches are not emitted; "
                 "all structured FITS products and comparator-visible step-log rows are retained")
                if int(normalized.get("lprint")) > 0 else ""
            ,) if int(normalized.get("lprint")) > 0 else (),
            provenance={
                "runner": "run_xstar_from_parameters",
                "package_version": "0.6.48.3",
                "release_source_version": "0.6.48.3",
                "reference_trace_schema_version": "0.6.48.3",
                "source_faithful_calculation_path": True,
                "verbose_pprint_complete": int(normalized.get("lprint")) == 0,
                "strict_ten_product_contract": True,
                "xstar_outputs_used_as_python_inputs": False,
                "diagnostics_mode": diagnostics_mode,
                "high_volume_diagnostics_enabled": bool(high_volume_diagnostics),
                "active_subset_enabled": bool(active_subset),
                "active_subset_summary": dict(state.provenance.get("active_atdb_subset", {})),
                "profile_components_enabled": normalize_profile_level(profile_components) != "none",
                "profile_components_level": normalize_profile_level(profile_components),
                "exclusive_profile_timing_enabled": normalize_profile_level(profile_components) != "none",
                "element_solver_diagnostic_gating": {
                    "schema_version": "0.6.48.3",
                    "diagnostics_mode": diagnostics_mode,
                    "residual_arrays_enabled": diagnostics_mode in {"summary", "full"},
                    "dense_svd_enabled": diagnostics_mode == "full",
                    "normalized_matrix_copy_enabled": diagnostics_mode != "none",
                    "condensed_rank_enabled": diagnostics_mode == "full",
                },
                "profile_rss_enabled": bool(profile_rss),
                "profile_backend_calls_enabled": bool(profile_backend_calls),
                "profile_terminal_enabled": bool(profile_terminal),
                "progress_debug_enabled": bool(progress_debug),
                "mg_line_kernel": str(mg_line_kernel).strip().lower(),
                "backend_selection": backend_selection.as_dict(),
                "rates_backend": rates_backend_status(backend_selection.rates_backend).as_dict(),
                "matrix_backend": {**matrix_backend_status(backend_selection.matrix_backend).as_dict(), "status": "compact_record_contributions_with_native_element_construction_solve_commit_v06451"},
                "emissivity_backend": {**emissivity_backend_status(backend_selection.emissivity_backend).as_dict(), "status": "native_source_ordered_spectral_contribution_engine_v0646"},
                "opacity_backend": {**opacity_backend_status(backend_selection.opacity_backend).as_dict(), "status": "native_line_profile_and_spectral_opacity_engine_v0646"},
                "thermal_backend": {**thermal_backend_status(backend_selection.thermal_backend).as_dict(), "status": "native_heatt_and_dsec_state_commit_v06471"},
                "engine_backend": {**engine_backend_status(backend_selection.engine_backend).as_dict(), "status": "h_he_mg_native_construction_boundary_v06451"},
                "mg_ion_accumulator": dict(state.control.get("mg_rate7_applied_cpp_speed_summary", {}).get("kernel_status", {}).get("mg_ion_accumulator", {})) or eval_mg_ion_accumulator_cpp(enabled=False).as_dict(),
                "compact_active_atdb_export": compact_export_summary,
                "performance_profile_summary": summarize_profile(state.control),
                "dsec_residual_trajectory_summary": list(state.control.get("dsec_residual_trajectory_summary", [])),
                "dsec_terminal_summary": list(state.control.get("dsec_terminal_summary", [])),
                "dsec_trace_capture_errors": list(state.control.get("dsec_trace_capture_errors", [])),
                "mg_matrix_ucalc_forensic_samples": list(state.control.get("mg_matrix_ucalc_forensic_samples", [])),
                "mg_type49_shadow_parity_enabled": bool(state.control.get("mg_type49_shadow_parity_enabled", False)),
                "mg_type49_shadow_parity_summary": dict(state.control.get("mg_type49_shadow_parity_summary", {})),
                "mg_type49_shadow_parity_samples": list(state.control.get("mg_type49_shadow_parity_samples", [])),
                "mg_type49_shadow_parity_worst_abs_samples": list(state.control.get("mg_type49_shadow_parity_worst_abs_samples", [])),
                "mg_type49_shadow_parity_worst_rel_samples": list(state.control.get("mg_type49_shadow_parity_worst_rel_samples", [])),
                "mg_type53_shadow_parity_enabled": bool(state.control.get("mg_type53_shadow_parity_enabled", False)),
                "mg_type53_shadow_parity_summary": dict(state.control.get("mg_type53_shadow_parity_summary", {})),
                "mg_type53_shadow_parity_samples": list(state.control.get("mg_type53_shadow_parity_samples", [])),
                "mg_type53_shadow_parity_worst_abs_samples": list(state.control.get("mg_type53_shadow_parity_worst_abs_samples", [])),
                "mg_type53_shadow_parity_worst_rel_samples": list(state.control.get("mg_type53_shadow_parity_worst_rel_samples", [])),
                "mg_rate7_applied_cpp_speed_summary": dict(state.control.get("mg_rate7_applied_cpp_speed_summary", {})),
                "mg_pre_matrix_coarse_cpp_summary": dict(state.control.get("mg_pre_matrix_coarse_cpp_summary", {})),
                "native_element_engine_summary": dict(state.control.get("native_element_engine_summary", {})),
                "native_spectral_engine_summary": dict(state.control.get("native_spectral_engine_summary", {})),
                "native_thermal_engine_summary": dict(state.control.get("native_thermal_engine_summary", {})),
                "mg_type4_type50_coarse_rejection_samples": list(state.control.get("mg_type4_type50_coarse_rejection_samples", [])),
                "mg_type4_upstream_shadow_probe_summary": dict(state.control.get("mg_type4_upstream_shadow_probe_summary", {})),
                "mg_type4_upstream_shadow_probe_samples": list(state.control.get("mg_type4_upstream_shadow_probe_samples", [])),
                "aggregate_timing_summary": summarize_profile(state.control),
                "runtime_phase_timing_summary": runtime_phase_timing_summary,
                "mg_matrix_assembly_dataflow_summary": summarize_matrix_assembly_dataflow(
                    state.control,
                    top_n=int(os.environ.get("XSTAR_ATOMIC_MATRIX_ASSEMBLY_DATAFLOW_TOP_N", "25") or "25"),
                ),
                "mg_rate_payload_dataflow_summary": summarize_rate_payload_dataflow(
                    state.control,
                    top_n=int(os.environ.get("XSTAR_ATOMIC_RATE_PAYLOAD_DATAFLOW_TOP_N", "25") or "25"),
                ),
                "mg_rate_payload_batched_orchestration_shadow_summary": summarize_rate_payload_batched_orchestration_shadow(
                    state.control,
                    top_n=int(os.environ.get("XSTAR_ATOMIC_RATE_PAYLOAD_BATCHED_SHADOW_TOP_N", "25") or "25"),
                ),
                "mg_rate_payload_four_family_product_summary": summarize_rate_payload_four_family_product(
                    state.control,
                    top_n=int(os.environ.get("XSTAR_ATOMIC_RATE_PAYLOAD_FOUR_FAMILY_TOP_N", "25") or "25"),
                ),
                "runtime_phase_wall_timing": dict(runtime_phase_wall_timing),
                "xout_step_timing_footer": dict(state.outputs.get("xout_step_timing_footer", {})),
                "output_writer_timing_breakdown": dict(state.outputs.get("output_writer_timing_breakdown", {})),
                "solver_backend": solver_backend_status(),
                "atdb_path": str(resolved_atdb),
                "pointer_cache_path": str(pointer_cache_path),
                "pointer_cache_status": str(built.derived.provenance.get("pointer_cache_status", "not_used")),
                "metadata_cache_path": str(metadata_cache_path),
                "metadata_cache_status": str(
                    state.control["output_atomic_metadata"].provenance.get(
                        "metadata_cache_status", "not_used"
                    )
                ),
                "vectorized_metadata_builder": True,
                "vectorized_sparse_slice": True,
            },
        )
        _emit_progress(
            progress_callback,
            "physical_run_done",
            ready=True,
            completed_passes=result.completed_passes,
            completed_zones=result.completed_zones,
            n_products=len(result.products),
        )
        return result
    except Exception:
        state.atomic.close()
        raise


def run_xstar_python(
    *,
    atdb_path: str | Path | None = None,
    output_dir: str | Path = ".",
    input_dir: str | Path | None = None,
    coheat_path: str | Path | None = None,
    zero_unspecified_abundances: bool | None = None,
    abundances: Mapping[str, float] | None = None,
    overwrite: bool = True,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    rebuild_cache: bool = False,
    progress_callback: ProgressCallback | None = None,
    diagnostics_mode: str = "full",
    active_subset: bool = True,
    profile_components: str | bool = "none",
    profile_rss: bool = False,
    profile_backend_calls: bool = False,
    profile_terminal: bool = False,
    progress_debug: bool = False,
    mg_line_kernel: str = "python",
    backend: str = "python",
    rates_backend: str | None = None,
    matrix_backend: str | None = None,
    emissivity_backend: str | None = None,
    compact_atdb_export: str | Path | None = None,
    **parameters: Any,
) -> XSTARPythonRunResult:
    """Run ported XSTAR using ordinary XSTAR keyword arguments.

    A partial set of individual ``*abund`` keywords is treated as a sparse
    Python convenience form: unspecified elements are zero.  Pass
    ``zero_unspecified_abundances=False`` to retain XSTAR parameter-file
    defaults instead.  Literal command/script APIs always retain XSTAR defaults.
    """
    if zero_unspecified_abundances is None:
        supplied_abundances = {
            str(name).strip().lower() for name in parameters
            if str(name).strip().lower() in ABUNDANCE_PARAMETER_NAMES
        }
        sparse = bool(abundances) or (0 < len(supplied_abundances) < len(ABUNDANCE_PARAMETER_NAMES))
    else:
        sparse = bool(zero_unspecified_abundances)
    return run_xstar_from_parameters(
        parameters,
        atdb_path=atdb_path,
        output_dir=output_dir,
        input_dir=input_dir,
        coheat_path=coheat_path,
        zero_unspecified_abundances=sparse,
        abundances=abundances,
        overwrite=overwrite,
        cache_dir=cache_dir,
        use_cache=use_cache,
        rebuild_cache=rebuild_cache,
        progress_callback=progress_callback,
        diagnostics_mode=diagnostics_mode,
        active_subset=active_subset,
        profile_components=profile_components,
        profile_rss=profile_rss,
        profile_backend_calls=profile_backend_calls,
        profile_terminal=profile_terminal,
        progress_debug=progress_debug,
        mg_line_kernel=mg_line_kernel,
        backend=backend,
        rates_backend=rates_backend,
        matrix_backend=matrix_backend,
        emissivity_backend=emissivity_backend,
        compact_atdb_export=compact_atdb_export,
        output_final_recompute=output_final_recompute,
    )


def _parse_literal_xstar_command(command: str) -> XSTARInputParameters:
    parsed = parse_xstar_command(command)
    if not parsed.parameters:
        raise XSTARPythonRunnerError("XSTAR command contains no key=value arguments")
    return parsed


def run_xstar_python_command(
    command: str,
    *,
    atdb_path: str | Path | None = None,
    output_dir: str | Path = ".",
    input_dir: str | Path | None = None,
    coheat_path: str | Path | None = None,
    overwrite: bool = True,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    rebuild_cache: bool = False,
    progress_callback: ProgressCallback | None = None,
    diagnostics_mode: str = "full",
    active_subset: bool = True,
    profile_components: str | bool = "none",
    profile_rss: bool = False,
    profile_backend_calls: bool = False,
    profile_terminal: bool = False,
    progress_debug: bool = False,
    mg_line_kernel: str = "python",
    backend: str = "python",
    rates_backend: str | None = None,
    matrix_backend: str | None = None,
    emissivity_backend: str | None = None,
    compact_atdb_export: str | Path | None = None,
    output_final_recompute: bool = True,
) -> XSTARPythonRunResult:
    """Parse a literal ``xstar key=value ...`` command and run Python only."""
    return run_xstar_from_parameters(
        _parse_literal_xstar_command(command),
        atdb_path=atdb_path,
        output_dir=output_dir,
        input_dir=input_dir,
        coheat_path=coheat_path,
        overwrite=overwrite,
        cache_dir=cache_dir,
        use_cache=use_cache,
        rebuild_cache=rebuild_cache,
        progress_callback=progress_callback,
        diagnostics_mode=diagnostics_mode,
        active_subset=active_subset,
        profile_components=profile_components,
        profile_rss=profile_rss,
        profile_backend_calls=profile_backend_calls,
        profile_terminal=profile_terminal,
        progress_debug=progress_debug,
        mg_line_kernel=mg_line_kernel,
        backend=backend,
        rates_backend=rates_backend,
        matrix_backend=matrix_backend,
        emissivity_backend=emissivity_backend,
        compact_atdb_export=compact_atdb_export,
        output_final_recompute=output_final_recompute,
    )


def run_xstar_python_script(
    script: str | Path,
    *,
    atdb_path: str | Path | None = None,
    output_dir: str | Path = ".",
    coheat_path: str | Path | None = None,
    overwrite: bool = True,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    rebuild_cache: bool = False,
    progress_callback: ProgressCallback | None = None,
    diagnostics_mode: str = "full",
    active_subset: bool = True,
    profile_components: str | bool = "none",
    profile_rss: bool = False,
    profile_backend_calls: bool = False,
    profile_terminal: bool = False,
    progress_debug: bool = False,
    mg_line_kernel: str = "python",
    backend: str = "python",
    rates_backend: str | None = None,
    matrix_backend: str | None = None,
    emissivity_backend: str | None = None,
    compact_atdb_export: str | Path | None = None,
    output_final_recompute: bool = True,
) -> XSTARPythonRunResult:
    """Read ``run_xstar.sh`` as data and execute the translated Python port."""
    path = Path(script)
    parsed = parse_run_xstar_script(path)
    return run_xstar_from_parameters(
        parsed,
        atdb_path=atdb_path,
        output_dir=output_dir,
        input_dir=path.parent,
        coheat_path=coheat_path,
        overwrite=overwrite,
        cache_dir=cache_dir,
        use_cache=use_cache,
        rebuild_cache=rebuild_cache,
        progress_callback=progress_callback,
        diagnostics_mode=diagnostics_mode,
        active_subset=active_subset,
        profile_components=profile_components,
        profile_rss=profile_rss,
        profile_backend_calls=profile_backend_calls,
        profile_terminal=profile_terminal,
        progress_debug=progress_debug,
        mg_line_kernel=mg_line_kernel,
        backend=backend,
        rates_backend=rates_backend,
        matrix_backend=matrix_backend,
        emissivity_backend=emissivity_backend,
        compact_atdb_export=compact_atdb_export,
        output_final_recompute=output_final_recompute,
    )



@dataclass
class Zone1DsecDiagnosticRun:
    """One bounded physical zone-1 run with every DSEC entry state retained."""

    ready: bool
    parameters: NormalizedXSTARParameters
    final_state: XSTARPythonState
    shell_result: BoundedRadialShellResult
    dsec_result: Any
    evaluator: CalcHMCAllDsecEvaluator
    products: Mapping[str, Path]
    atomic_build: AtomicDatabaseBuildResult = field(repr=False)

    def close(self) -> None:
        self.atomic_build.atomic_state.close()

    def __enter__(self) -> "Zone1DsecDiagnosticRun":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": bool(self.ready),
            "zone_index": 1,
            "n_evaluations": len(self.evaluator.evaluations),
            "n_input_snapshots": len(self.evaluator.input_snapshots),
            "final_temperature_K": float(self.final_state.plasma.temperature),
            "final_electron_fraction_xee": float(self.final_state.plasma.xee),
            "products": {key: str(value) for key, value in self.products.items()},
            "production_rates_modified": True,
            "production_rate_change_scope": (
                "ucalc_data_type_15_final_shell_threshold_plus_"
                "data_type_59_compact_fields_continuum_offset_pre_swap_zeroing_"
                "literal_nbinc_enxt_excited_parent_weight_plus_calc_ion_rates_lfpi1_"
                "plus_calc_hmc_all_live_xh0_xh1_and_strict_msolvelucy"
            ),
            "production_solver_modified": True,
            "production_solver_change_scope": (
                "msolvelucy_no_lstsq_no_dense_rescue_literal_1dminus24_"
                "normalization_ordered_diff_diff2_and_rate_type5_falpha"
            ),
            "live_hydrogen_charge_exchange_state": True,
            "production_tolerances_modified": False,
            "empirical_corrections_added": False,
        }


def run_zone1_dsec_diagnostic_from_parameters(
    parameters: XSTARInputParameters | ParsedXSTARCommand | Mapping[str, Any],
    *,
    atdb_path: str | Path | None = None,
    output_dir: str | Path = "zone1_dsec_diagnostic",
    coheat_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    rebuild_cache: bool = False,
    progress_callback: ProgressCallback | None = None,
    xstar_probe_dir: str | Path | None = None,
    enforce_cooling_gate: bool = False,
    cooling_rtol: float = 5.0e-5,
    cooling_atol: float = 1.0e-30,
) -> Zone1DsecDiagnosticRun:
    """Execute only the first physical radial shell and retain all DSEC inputs."""
    from .zone1_dsec_diagnostic import write_zone1_python_diagnostic_products
    from .zone1_dsec_probe_analysis import (
        load_xstar_target_state,
        make_carbon_cooling_gate,
    )

    resolved_atdb = _resolve_runner_atdb_path(atdb_path)
    normalized = normalize_xstar_parameters(parameters)
    pointer_cache_path, metadata_cache_path = _cache_paths(resolved_atdb, cache_dir)
    state, built = _build_initial_state(
        normalized,
        atdb_path=resolved_atdb,
        coheat_path=coheat_path,
        pointer_cache=pointer_cache_path,
        metadata_cache=metadata_cache_path,
        use_cache=use_cache,
        rebuild_cache=rebuild_cache,
        progress_callback=progress_callback,
    )
    state.control["zone1_dsec_capture_all_inputs"] = True
    state.control["zone1_dsec_capture_hydrogen_history"] = True
    state.control["zone1_dsec_target_temperature_k"] = 73198.4
    if xstar_probe_dir is not None:
        target_state = load_xstar_target_state(xstar_probe_dir)
        state.control["zone1_dsec_target_temperature_k"] = float(
            target_state["temperature_K"]
        )
        state.control["zone1_dsec_target_electron_fraction_xee"] = float(
            target_state["electron_fraction_xee"]
        )
        state.control["zone1_dsec_target_hydrogen_density_cm3"] = float(
            target_state["hydrogen_density_cm3"]
        )
        state.control["zone1_dsec_xstar_target_state_used"] = True
    if enforce_cooling_gate:
        if xstar_probe_dir is None:
            built.atomic_state.close()
            raise XSTARPythonRunnerError(
                "enforce_cooling_gate requires xstar_probe_dir"
            )
        state.control["zone1_dsec_evaluation_gate_callback"] = make_carbon_cooling_gate(
            xstar_probe_dir, rtol=cooling_rtol, atol=cooling_atol
        )
    try:
        shell = run_bounded_radial_shell(
            state, zone_index=1, pass_index=1, direction=-1, fixed_state=False
        )
        evaluator = state.control.get("physical_calc_evaluator")
        if not isinstance(evaluator, CalcHMCAllDsecEvaluator):
            raise XSTARPythonRunnerError("zone-1 DSEC evaluator was not retained")
        dsec_result = state.local_zone.source_arrays.get("dsec")
        if dsec_result is None:
            raise XSTARPythonRunnerError("zone-1 DSEC result was not retained")
        products = write_zone1_python_diagnostic_products(
            snapshots=evaluator.input_snapshots,
            evaluations=evaluator.evaluations,
            master=built.master,
            derived=built.derived,
            out_dir=output_dir,
            target_result=state.control.get("zone1_dsec_target_result"),
            target_metadata=state.control.get("zone1_dsec_target_metadata"),
        )
        ready = bool(
            evaluator.evaluations
            and len(evaluator.input_snapshots) == len(evaluator.evaluations)
            and Path(products["summary_json"]).is_file()
        )
        return Zone1DsecDiagnosticRun(
            ready=ready,
            parameters=normalized,
            final_state=state,
            shell_result=shell,
            dsec_result=dsec_result,
            evaluator=evaluator,
            products=products,
            atomic_build=built,
        )
    except Exception:
        built.atomic_state.close()
        raise


def run_zone1_dsec_diagnostic_script(
    run_script: str | Path,
    **kwargs: Any,
) -> Zone1DsecDiagnosticRun:
    """Parse one literal ``run_xstar.sh`` and execute the bounded zone-1 gate."""
    return run_zone1_dsec_diagnostic_from_parameters(
        parse_run_xstar_script(run_script), **kwargs
    )

def run_c5_ne1_acceptance(
    *,
    run_script: str | Path,
    atdb_path: str | Path | None = None,
    python_output_dir: str | Path = "python_xstar/c5_ne1",
    original_run_dir: str | Path,
    coheat_path: str | Path | None = None,
    rtol: float = 5.0e-5,
    atol: float = 1.0e-30,
    step_rtol: float = 5.0e-3,
    step_atol: float = 5.0e-3,
    require_original_products: bool = True,
    raise_on_failure: bool = True,
    cache_dir: str | Path | None = None,
    use_cache: bool = True,
    rebuild_cache: bool = False,
    progress_callback: ProgressCallback | None = None,
    diagnostics_mode: str = "full",
    active_subset: bool = True,
    profile_components: str | bool = "none",
    profile_rss: bool = False,
    profile_backend_calls: bool = False,
    profile_terminal: bool = False,
    progress_debug: bool = False,
    mg_line_kernel: str = "python",
    backend: str = "python",
    rates_backend: str | None = None,
    matrix_backend: str | None = None,
    emissivity_backend: str | None = None,
    compact_atdb_export: str | Path | None = None,
    output_final_recompute: bool = True,
) -> C5NE1AcceptanceResult:
    """Run the strict independent c5_ne1 ten-product parity acceptance gate."""
    python_run = run_xstar_python_script(
        run_script,
        atdb_path=atdb_path,
        output_dir=python_output_dir,
        coheat_path=coheat_path,
        cache_dir=cache_dir,
        use_cache=use_cache,
        rebuild_cache=rebuild_cache,
        progress_callback=progress_callback,
        diagnostics_mode=diagnostics_mode,
        active_subset=active_subset,
        profile_components=profile_components,
        profile_rss=profile_rss,
        profile_backend_calls=profile_backend_calls,
        profile_terminal=profile_terminal,
        progress_debug=progress_debug,
        mg_line_kernel=mg_line_kernel,
        backend=backend,
        rates_backend=rates_backend,
        matrix_backend=matrix_backend,
        emissivity_backend=emissivity_backend,
        compact_atdb_export=compact_atdb_export,
        output_final_recompute=output_final_recompute,
    )
    diagnostics_mode = _normalize_diagnostics_mode(diagnostics_mode)
    original = Path(original_run_dir)
    _present, missing = products_present(original)
    available = not missing
    parity: PhysicalOutputParityResult | None = None
    if available:
        _emit_progress(
            progress_callback,
            "parity_start",
            original_run_dir=str(original),
            python_output_dir=str(python_run.output_dir),
        )
        parity = compare_physical_output_directories(
            original,
            python_run.output_dir,
            rtol=rtol,
            atol=atol,
            step_rtol=step_rtol,
            step_atol=step_atol,
            required_files=REQUIRED_XSTAR_PRODUCTS,
        )
        _emit_progress(
            progress_callback,
            "parity_done",
            parity_run=bool(parity.parity_run),
            all_files_match=bool(parity.all_files_ready),
        )
        if diagnostics_mode != "none":
            radial_spectrum = compare_radial_spectrum_products(
                original,
                python_run.output_dir,
                out_dir=Path(python_run.output_dir) / "radial_spectrum_diagnostics_v0499",
                write_files=(diagnostics_mode == "full"),
            )
            python_run.final_state.outputs["radial_spectrum_parity_v0499_summary"] = radial_spectrum
            _emit_progress(
                progress_callback,
                "radial_spectrum_parity_done",
                row_count_match=bool(radial_spectrum.get("radial_row_summary", {}).get("row_count_match", False)),
                python_abundance_rows=int(radial_spectrum.get("radial_row_summary", {}).get("python_abundance_rows", 0)),
                xstar_abundance_rows=int(radial_spectrum.get("radial_row_summary", {}).get("xstar_abundance_rows", 0)),
                write_files=bool(diagnostics_mode == "full"),
            )
        else:
            _emit_progress(
                progress_callback,
                "radial_spectrum_parity_skipped",
                diagnostics_mode=diagnostics_mode,
            )
    result = C5NE1AcceptanceResult(
        python_run=python_run,
        original_run_dir=original,
        original_products_available=available,
        parity=parity,
        all_ten_python_products_ready=python_run.ready,
        all_files_match=bool(parity is not None and parity.all_files_ready),
    )
    if require_original_products and not available and raise_on_failure:
        python_run.close()
        raise XSTARPythonAcceptanceError(
            "c5_ne1 acceptance requires the ten original XSTAR products in "
            f"{original}; missing: {', '.join(missing)}"
        )
    if available and not result.all_files_match and raise_on_failure:
        python_run.close()
        raise XSTARPythonAcceptanceError(
            "c5_ne1 Python products were generated, but direct original-XSTAR parity failed"
        )
    return result


__all__ = [
    "ProgressCallback",
    "XSTARPythonRunnerError",
    "UnsupportedXSTARParameterError",
    "XSTARPythonAcceptanceError",
    "NormalizedXSTARParameters",
    "XSTARPythonRunResult",
    "C5NE1AcceptanceResult",
    "XSTARPythonCacheResult",
    "XSTAR_PARAMETER_DEFAULTS",
    "XDEF_ABUNDANCES",
    "normalize_xstar_parameters",
    "ener_grid",
    "powerlaw_spectrum",
    "photon_number_luminosity",
    "build_source_output_metadata",
    "default_output_metadata_cache_path",
    "save_source_output_metadata_cache",
    "load_source_output_metadata_cache",
    "prepare_xstar_python_cache",
    "build_pprint_atomic_metadata",
    "run_xstar_from_parameters",
    "run_xstar_python",
    "run_xstar_python_command",
    "run_xstar_python_script",
    "Zone1DsecDiagnosticRun",
    "run_zone1_dsec_diagnostic_from_parameters",
    "run_zone1_dsec_diagnostic_script",
    "run_c5_ne1_acceptance",
]
