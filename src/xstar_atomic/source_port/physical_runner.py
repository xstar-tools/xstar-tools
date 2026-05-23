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

from dataclasses import dataclass, field
from hashlib import sha256
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from ..data import resolve_atdb_path
from ..xstar_run import XSTARInputParameters, parse_xstar_command
from .atomic_database import AtomicDatabaseBuildResult, load_atomic_database_state
from .bremsstrahlung import BremsstrahlungContext
from .compton import Comp2Context, load_compton_table
from .dsec import CalcHMCAllDsecEvaluator, DsecMutableRuntimeState, dsec
from .element_equilibrium import EscapeProbabilityContext, build_level_table
from .emergent_emissivity import CalcEmisContext, CalcEmisWorkspace
from .emissivity import CalcEmisabContext
from .free_free import FreeFreeContext
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
from .pprint_legacy import (
    PprintAtomicMetadata,
    PprintElementMetadata,
    PprintIonMetadata,
)
from .radiation import nbinc
from .radial_transfer import RadialTransferWorkspace, run_bounded_radial_multipass
from .state import XSTARPythonState
from .thermal_balance import HeatFContext


class XSTARPythonRunnerError(RuntimeError):
    """Raised when the requested physical XSTAR command cannot run safely."""


class UnsupportedXSTARParameterError(XSTARPythonRunnerError):
    """Raised for a source branch not yet supported by the public runner."""


class XSTARPythonAcceptanceError(XSTARPythonRunnerError):
    """Raised when the strict ten-product or original-XSTAR parity gate fails."""


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
    """Literal numerical translation of ``ener.f90``."""
    n = int(ncn2)
    if n < 4:
        raise XSTARPythonRunnerError("ener requires at least four bins")
    n2 = max(2, n // 50)
    n3 = n - n2
    out = np.zeros(n, dtype=float)
    out[0] = 0.1
    ratio = (4.0e5 / 0.1) ** (1.0 / float(n3 - 1))
    for i in range(1, n3):
        out[i] = out[i - 1] * ratio
    ratio2 = (1.0e6 / 4.0e5) ** (1.0 / float(n2 - 1))
    for i in range(n3, n):
        out[i] = out[i - 1] * ratio2
    return out


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


def _clean_label(raw: bytes | str, fallback: str) -> str:
    if isinstance(raw, bytes):
        text = raw.decode("latin-1", errors="replace")
    else:
        text = str(raw)
    text = " ".join(text.replace("\x00", " ").split())
    return text or fallback


def _parent_ion_index(derived: Any, recno: int) -> int:
    ion_record = int(derived.npar[int(recno)])
    if ion_record <= 0:
        return 0
    matches = np.flatnonzero(np.asarray(derived.ion_records, dtype=int) == ion_record)
    return int(matches[0]) if matches.size else 0


def build_source_output_metadata(master: Any, derived: Any) -> SourceOutputMetadata:
    """Resolve packed ATDB pointers into the metadata consumed by the writers."""
    levels: list[LevelOutputMetadata] = []
    for global_index in range(1, int(derived.n_level_records) + 1):
        rec = int(derived.level_record_by_global_index[global_index])
        if rec <= 0:
            continue
        ion_index = _parent_ion_index(derived, rec)
        if ion_index <= 0:
            continue
        reals = master.record_reals(rec)
        ints = master.record_integers(rec)
        z = int(derived.ion_element_z[ion_index])
        stage = int(derived.ion_stage[ion_index])
        local = int(ints[-2]) if len(ints) >= 2 else global_index
        ion_label = _clean_label(master.record_chars(int(derived.ion_records[ion_index])), f"{ELEMENT_SYMBOLS[z-1]}_{stage}")
        levels.append(
            LevelOutputMetadata(
                global_index=global_index,
                ion_index=ion_index,
                excitation_eV=float(reals[0]) if len(reals) else 0.0,
                ion_label=ion_label,
                atomic_number=z,
                level_label=_clean_label(master.record_chars(rec), f"level_{local}"),
                upper_index=local,
            )
        )

    levels_by_key = {(row.ion_index, row.upper_index): row for row in levels}
    lines: list[LineOutputMetadata] = []
    for line_index in range(1, int(derived.nlsvn) + 1):
        rec = int(derived.nplin[line_index])
        header = master.header(rec)
        reals = master.record_reals(rec)
        ints = master.record_integers(rec)
        ion_index = _parent_ion_index(derived, rec)
        if ion_index <= 0:
            continue
        z = int(derived.ion_element_z[ion_index])
        stage = int(derived.ion_stage[ion_index])
        lower = int(ints[0]) if len(ints) >= 1 else 0
        upper = int(ints[1]) if len(ints) >= 2 else 0
        lower_label = levels_by_key.get((ion_index, lower))
        upper_label = levels_by_key.get((ion_index, upper))
        lines.append(
            LineOutputMetadata(
                line_index=line_index,
                wavelength_angstrom=abs(float(reals[0])) if len(reals) else 0.0,
                ion_label=_clean_label(master.record_chars(int(derived.ion_records[ion_index])), f"{ELEMENT_SYMBOLS[z-1]}_{stage}"),
                lower_level=(lower_label.level_label if lower_label else f"level_{lower}"),
                upper_level=(upper_label.level_label if upper_label else f"level_{upper}"),
                rate_type=int(header.rate_type),
                data_type=int(header.data_type),
                atomic_mass=float(ATOMIC_MASS[z - 1]),
                natural_rate_s=(float(reals[2]) if int(header.data_type) == 50 and len(reals) > 2 else 0.0),
            )
        )

    rrcs: list[RRCOutputMetadata] = []
    for continuum_index in range(1, int(derived.ncsvn) + 1):
        rec = int(derived.npcon[continuum_index])
        ints = master.record_integers(rec)
        ion_index = _parent_ion_index(derived, rec)
        if ion_index <= 0 or len(ints) < 2:
            continue
        z = int(derived.ion_element_z[ion_index])
        stage = int(derived.ion_stage[ion_index])
        local = int(ints[-2])
        level = levels_by_key.get((ion_index, local))
        try:
            table = build_level_table(master, derived, ion_index)
            threshold = float(table.require(local).ionization_potential_ev)
        except Exception:
            reals = master.record_reals(rec)
            threshold = float(reals[0]) if len(reals) else 0.0
        global_level = int(derived.npilev[local, ion_index]) if 0 < local < derived.npilev.shape[0] else 0
        ion_label = _clean_label(master.record_chars(int(derived.ion_records[ion_index])), f"{ELEMENT_SYMBOLS[z-1]}_{stage}")
        rrcs.append(
            RRCOutputMetadata(
                continuum_index=continuum_index,
                level_global_index=global_level,
                threshold_eV=threshold,
                ion_label=ion_label,
                lower_level=(level.level_label if level else f"level_{local}"),
            )
        )
    return SourceOutputMetadata(
        levels=tuple(levels),
        lines=tuple(lines),
        rrcs=tuple(rrcs),
        provenance={"source": "readtbl/setptrs packed ATDB pointers", "source_faithful": True},
    )


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
        comp = Comp2Context(epi_eV=epi, bremsa=brem, table=compton_table, ncn2=n, source="run_xstar_python:comp2")
        free = FreeFreeContext(epi_eV=epi, bremsa=brem, opakc_before_cm_inv=np.asarray(opakc, dtype=float)[:n], ncn2=n, source="run_xstar_python:freef")
        bremem = BremsstrahlungContext(epi_eV=epi, brcems_before=np.asarray(brcems, dtype=float)[:n], opakc_before_cm_inv=np.asarray(opakc, dtype=float)[:n], ncn2=n, source="run_xstar_python:bremem")
        heat = HeatFContext(
            epi_eV=epi,
            brcems=np.asarray(brcems, dtype=float)[:n],
            htfreef_erg_cm3_s=0.0,
            cmp1=0.0,
            cmp2=0.0,
            httot_before=0.0,
            cltot_before=0.0,
            httot2_before=0.0,
            cltot2_before=0.0,
            radius_cm=float(state.transfer.radius),
            zone_thickness_cm=float(state.control.get("delr", 0.0)),
            ncn2=n,
            source="run_xstar_python:heatf",
        )
        return {
            "compton_context": comp,
            "free_free_context": free,
            "bremem_context": bremem,
            "heatf_context": heat,
        }
    return factory


def _commit_fixed_state(state: XSTARPythonState, runtime: DsecMutableRuntimeState, result: FixedStateCalcHMCAllResult) -> None:
    state.plasma.temperature = float(result.temperature_k)
    state.plasma.xpx = float(result.hydrogen_density_cm3)
    state.plasma.xee = float(result.electron_fraction_xee)
    state.plasma.electron_density = float(result.electron_density_cm3)
    state.plasma.ion_fractions = dict(result.ion_fractions)
    state.plasma.populations = _guard(result.global_xilevg_by_index)
    state.thermal.heating = float(result.httot)
    state.thermal.cooling = float(result.cltot)
    state.thermal.residual = float(result.hmctot)
    state.thermal.electron_fraction = float(result.electron_fraction_xee)
    state.thermal.converged = bool(result.complete_fixed_state_ready)
    state.local_zone.calc_hmc_all = result
    state.local_zone.source_arrays.update(
        {
            "xilevg": _guard(result.global_xilevg_by_index),
            "bilevg": _guard(result.global_bilevg_by_index),
            "rnisg": _guard(result.global_rnisg_by_index),
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
        if 1 <= row.continuum_index < rrc_wavelength.size and row.threshold_eV > 0.0:
            rrc_wavelength[row.continuum_index] = HC_EV_ANGSTROM / row.threshold_eV

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
        xilevg=_guard(result.global_xilevg_by_index),
        bilevg=_guard(result.global_bilevg_by_index),
        rnisg=_guard(result.global_rnisg_by_index),
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
    )
    state.control["calc_emisab_context"] = CalcEmisabContext(
        **common,
        workspace=workspace.emissivity.base,
    )
    state.control["calc_emis_context"] = CalcEmisContext(
        **common,
        workspace=workspace.emissivity,
        line_wavelength_angstrom=line_wavelength,
        rrc_wavelength_angstrom=rrc_wavelength,
    )
    state.control["shared_emissivity_workspace"] = workspace.emissivity


def _install_physical_handlers(state: XSTARPythonState, parameters: NormalizedXSTARParameters, compton_table: Any) -> None:
    master = state.atomic.master
    derived = state.atomic.derived
    required = tuple(z for z, value in enumerate(parameters.physical_abundances, start=1) if value > 1.0e-24)

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
        )

    def dsec_handler(runtime_state: XSTARPythonState) -> Any:
        runtime = build_runtime()
        evaluator = CalcHMCAllDsecEvaluator(
            master=master,
            derived=derived,
            calc_kwargs_factory=_calc_kwargs_factory(runtime_state, compton_table),
        )
        result = dsec(
            runtime,
            evaluator=evaluator,
            nlim=int(runtime_state.control.get("nlimdt", parameters.get("niter"))),
            tinf_t4=float(runtime_state.control.get("tinf", 0.099)),
        )
        runtime_state.control["physical_dsec_runtime"] = result.state
        runtime_state.control["physical_calc_evaluator"] = evaluator
        runtime_state.plasma.temperature = result.state.temperature_k
        runtime_state.plasma.xee = result.state.electron_fraction_xee
        runtime_state.plasma.xpx = result.state.hydrogen_density_cm3
        runtime_state.control["ntotit"] = int(result.ntotit)
        runtime_state.control["lnerrd"] = int(result.lnerr)
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
            calc_kwargs_factory=_calc_kwargs_factory(runtime_state, compton_table),
        )
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


def _build_initial_state(parameters: NormalizedXSTARParameters, *, atdb_path: str | Path, coheat_path: str | Path | None = None) -> tuple[XSTARPythonState, AtomicDatabaseBuildResult]:
    built = load_atomic_database_state(atdb_path, abundances=np.ones(30, dtype=float), llinabs=True)
    state = XSTARPythonState(atomic=built.atomic_state)
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
            "npass": int(parameters.get("npass")),
            "xlum": float(parameters.luminosity_1e38),
            "tinf": 0.099,
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
            "ntotit": 0,
            "lnerrd": 0,
            "atcredate": str(getattr(built.master, "creation_date", "")),
        }
    )
    metadata = build_source_output_metadata(built.master, derived)
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
) -> XSTARPythonRunResult:
    """Execute the translated Python XSTAR path from normalized parameters."""
    del input_dir  # Reserved for spectrum/density-file source branches.
    resolved_atdb = _resolve_runner_atdb_path(atdb_path)
    normalized = normalize_xstar_parameters(
        parameters,
        zero_unspecified_abundances=zero_unspecified_abundances,
        abundances=abundances,
    )
    out = Path(output_dir)
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

    state, built = _build_initial_state(
        normalized, atdb_path=resolved_atdb, coheat_path=coheat_path
    )
    try:
        radial = run_bounded_radial_multipass(
            state,
            first_pass_shell_count=int(normalized.get("nsteps")),
            pass_count=int(normalized.get("npass")),
        )
        writer = run_output_writer_sequence(
            state,
            out_dir=out,
            lwri=int(normalized.get("lwrite")),
            parameters=_output_parameters(normalized),
            model_name=str(normalized.get("modelname")),
            atomic_data_date=str(getattr(built.master, "creation_date", "")),
            final_local_recompute=True,
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
        return XSTARPythonRunResult(
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
                "source_faithful_calculation_path": True,
                "verbose_pprint_complete": int(normalized.get("lprint")) == 0,
                "strict_ten_product_contract": True,
                "xstar_outputs_used_as_python_inputs": False,
                "atdb_path": str(resolved_atdb),
            },
        )
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
) -> XSTARPythonRunResult:
    """Parse a literal ``xstar key=value ...`` command and run Python only."""
    return run_xstar_from_parameters(
        _parse_literal_xstar_command(command),
        atdb_path=atdb_path,
        output_dir=output_dir,
        input_dir=input_dir,
        coheat_path=coheat_path,
        overwrite=overwrite,
    )


def run_xstar_python_script(
    script: str | Path,
    *,
    atdb_path: str | Path | None = None,
    output_dir: str | Path = ".",
    coheat_path: str | Path | None = None,
    overwrite: bool = True,
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
) -> C5NE1AcceptanceResult:
    """Run the strict independent c5_ne1 ten-product parity acceptance gate."""
    python_run = run_xstar_python_script(
        run_script,
        atdb_path=atdb_path,
        output_dir=python_output_dir,
        coheat_path=coheat_path,
    )
    original = Path(original_run_dir)
    _present, missing = products_present(original)
    available = not missing
    parity: PhysicalOutputParityResult | None = None
    if available:
        parity = compare_physical_output_directories(
            original,
            python_run.output_dir,
            rtol=rtol,
            atol=atol,
            step_rtol=step_rtol,
            step_atol=step_atol,
            required_files=REQUIRED_XSTAR_PRODUCTS,
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
    "XSTARPythonRunnerError",
    "UnsupportedXSTARParameterError",
    "XSTARPythonAcceptanceError",
    "NormalizedXSTARParameters",
    "XSTARPythonRunResult",
    "C5NE1AcceptanceResult",
    "XSTAR_PARAMETER_DEFAULTS",
    "XDEF_ABUNDANCES",
    "normalize_xstar_parameters",
    "ener_grid",
    "powerlaw_spectrum",
    "photon_number_luminosity",
    "build_source_output_metadata",
    "build_pprint_atomic_metadata",
    "run_xstar_from_parameters",
    "run_xstar_python",
    "run_xstar_python_command",
    "run_xstar_python_script",
    "run_c5_ne1_acceptance",
]
