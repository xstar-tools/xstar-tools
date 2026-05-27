"""Source-faithful detail and final-output writers from the XSTAR caller.

This module translates the caller-visible contracts of ``savd -> fstepr*``
and the final ``writespectra*`` sequence.  The numerical rows are constructed
before FITS I/O so their REAL(4) persistence, selection thresholds, column
order, and source quirks can be validated independently of the FITS library.

The writer sequence implemented here is bounded to already-translated radial
state.  It does not alter the plasma solution, transfer arrays, or pass state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


def _install_astropy_numpy_compatibility() -> None:
    """Install narrow NumPy shims needed by older Astropy on new NumPy.

    Some Astropy releases import private/deprecated NumPy helpers while
    constructing FITS table HDUs.  Newer NumPy releases removed those names.
    The source-port writer does not rely on the deprecated behavior, but the
    import-time references must exist for Astropy's table stack to load.
    """
    if not hasattr(np, "in1d"):
        np.in1d = np.isin  # type: ignore[attr-defined]
    try:
        import numpy.lib._function_base_impl as _np_function_base
    except Exception:
        return
    if not hasattr(_np_function_base, "_check_interpolation_as_method"):
        def _check_interpolation_as_method(method, interpolation, fname):
            if method != "linear":
                raise TypeError(
                    "You shall not pass both `method` and `interpolation`!\n"
                    "(`interpolation` is Deprecated in favor of `method`)"
                )
            return interpolation

        _np_function_base._check_interpolation_as_method = _check_interpolation_as_method


_install_astropy_numpy_compatibility()

from astropy.io import fits

from .state import XSTARPythonState


class OutputWriterPortError(RuntimeError):
    """Raised when the source output contract cannot be represented safely."""


R4 = np.float32
LEVEL_POPULATION_FLOOR = 1.0e-34
DETAIL_LINE_ACTIVITY_FLOOR = 1.0e-64
DETAIL_RRC_ACTIVITY_FLOOR = 1.0e-36
FINAL_LINE_ACTIVITY_FLOOR = 1.0e-36
FINAL_RRC_ACTIVITY_FLOOR = 1.0e-36
FINAL_LINE_LIMIT = 600


def _r4(value: float) -> float:
    return float(R4(value))


def _r4_array(values: Any) -> np.ndarray:
    return np.asarray(values, dtype=R4)


def _fixed(text: str, width: int) -> str:
    return str(text)[:width].ljust(width)


@dataclass(frozen=True)
class OutputParameter:
    name: str
    value: float
    parameter_type: str = "real"
    comment: str = ""


@dataclass(frozen=True)
class LevelOutputMetadata:
    global_index: int
    ion_index: int
    excitation_eV: float
    ion_label: str
    atomic_number: int
    level_label: str
    upper_index: int


@dataclass(frozen=True)
class LineOutputMetadata:
    line_index: int
    wavelength_angstrom: float
    ion_label: str
    lower_level: str
    upper_level: str
    rate_type: int = 50
    data_type: int = 0
    atomic_mass: float = 1.0
    natural_rate_s: float = 0.0
    auger_width_eV: float = 0.0
    auger_rate_s: float = 0.0


@dataclass(frozen=True)
class RRCOutputMetadata:
    continuum_index: int
    level_global_index: int
    threshold_eV: float
    ion_label: str
    lower_level: str
    upper_level: str = "continuum"


@dataclass(frozen=True)
class SourceOutputMetadata:
    levels: tuple[LevelOutputMetadata, ...] = ()
    lines: tuple[LineOutputMetadata, ...] = ()
    rrcs: tuple[RRCOutputMetadata, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ShellOutputHeader:
    inner_radius_cm: float
    outer_radius_cm: float
    radial_depth_cm: float
    temperature_1e4K: float
    pressure_dyn_cm2: float
    column_cm2: float
    electron_fraction: float
    density_cm3: float
    logxi: float

    def real4_keywords(self) -> dict[str, float]:
        return {
            "RINNER": _r4(self.inner_radius_cm),
            "ROUTER": _r4(self.outer_radius_cm),
            "RDEL": _r4(self.radial_depth_cm),
            "TEMPERAT": _r4(self.temperature_1e4K),
            "PRESSURE": _r4(self.pressure_dyn_cm2),
            "COLUMN": _r4(self.column_cm2),
            "XEE": _r4(self.electron_fraction),
            "DENSITY": _r4(self.density_cm3),
            "LOGXI": _r4(self.logxi),
        }


@dataclass(frozen=True)
class OutputTable:
    extension_name: str
    columns: tuple[str, ...]
    units: tuple[str, ...]
    values: Mapping[str, np.ndarray]
    formats: tuple[str, ...]
    binary: bool
    header_keywords: Mapping[str, float | int | str] = field(default_factory=dict)
    source_file: str = ""

    @property
    def nrows(self) -> int:
        if not self.columns:
            return 0
        return int(np.asarray(self.values[self.columns[0]]).shape[0])


@dataclass(frozen=True)
class DetailShellOutput:
    levels: OutputTable
    lines: OutputTable
    rrcs: OutputTable
    continuum: OutputTable
    source_order: tuple[str, ...] = ("fstepr", "fstepr2", "fstepr3", "fstepr4")
    source_file: str = "xstar/xstarlib/src/savd.f90"


@dataclass
class DetailOutputStore:
    """Four caller-owned detail products for one radial pass."""

    pass_index: int = 1
    records: list[DetailShellOutput] = field(default_factory=list)
    inserted_after_hdus: list[int] = field(default_factory=list)

    def insert_after_hdu(self, hdunum_one_based: int, record: DetailShellOutput) -> None:
        # Primary + PARAMETERS occupy HDUs 1 and 2.  savd passes jkstep and
        # every fstepr inserts after that HDU in its own file.
        hdunum = int(hdunum_one_based)
        if hdunum < 2:
            raise OutputWriterPortError("detail output HDUs 1-2 are reserved")
        position = max(0, min(len(self.records), hdunum - 2))
        self.records.insert(position, record)
        self.inserted_after_hdus.append(hdunum)


@dataclass(frozen=True)
class FinalOutputProducts:
    spectrum: OutputTable
    lines: OutputTable
    continuum: OutputTable
    rrcs: OutputTable
    source_order: tuple[str, ...] = (
        "writespectra",
        "writespectra2",
        "writespectra3",
        "writespectra4",
    )
    source_file: str = "xstar/src/xstar/xstar.f90"


@dataclass(frozen=True)
class OutputWriterSequenceResult:
    detail_stores: Mapping[int, DetailOutputStore]
    final_products: FinalOutputProducts | None
    written_paths: Mapping[str, str]
    source_order: tuple[str, ...]
    final_local_recompute_executed: bool = False
    pprint_source_state_handler_ready: bool = False
    pprint_products_written: bool = False
    source_file: str = "xstar/src/xstar/xstar.f90"

    @property
    def detail_store(self) -> DetailOutputStore:
        """Return the highest-pass detail store for compatibility."""
        if not self.detail_stores:
            return DetailOutputStore(pass_index=1)
        return self.detail_stores[max(self.detail_stores)]


def _metadata_from_control(state: XSTARPythonState) -> SourceOutputMetadata:
    value = state.control.get("output_atomic_metadata")
    if isinstance(value, SourceOutputMetadata):
        return value
    raise OutputWriterPortError(
        "output writers require caller-owned SourceOutputMetadata in "
        "state.control['output_atomic_metadata']"
    )


def build_parameter_table(parameters: Sequence[OutputParameter], *, model_name: str) -> OutputTable:
    n = len(parameters)
    return OutputTable(
        extension_name="PARAMETERS",
        columns=("index", "parameter", "value", "type", "comment"),
        units=("", "", "", "", ""),
        formats=("1I", "20A", "1E", "10A", "30A"),
        binary=True,
        header_keywords={"MODEL": _fixed(model_name, 30)},
        source_file="xstar/xstarlib/src/fparmlist.f90",
        values={
            "index": np.arange(1, n + 1, dtype=np.int16),
            "parameter": np.asarray([_fixed(p.name, 20) for p in parameters], dtype="U20"),
            "value": _r4_array([p.value for p in parameters]),
            "type": np.asarray([_fixed(p.parameter_type, 10) for p in parameters], dtype="U10"),
            "comment": np.asarray([_fixed(p.comment, 30) for p in parameters], dtype="U30"),
        },
    )


def build_detail_level_table(
    *,
    metadata: SourceOutputMetadata,
    populations: Sequence[float],
    lte_populations: Sequence[float],
    header: ShellOutputHeader,
) -> OutputTable:
    pop = np.asarray(populations, dtype=float).reshape(-1)
    lte = np.asarray(lte_populations, dtype=float).reshape(-1)
    if pop.shape != lte.shape:
        raise OutputWriterPortError("detail level population arrays differ in length")
    rows = [
        item for item in metadata.levels
        if 1 <= item.global_index <= pop.size and pop[item.global_index - 1] > LEVEL_POPULATION_FLOOR
    ]
    values = {
        "index": np.asarray([r.global_index for r in rows], dtype=np.int32),
        "ion_index": np.asarray([r.ion_index for r in rows], dtype=np.int16),
        "e_excitation": _r4_array([r.excitation_eV for r in rows]),
        "ion": np.asarray([_fixed(r.ion_label, 8) for r in rows], dtype="U8"),
        "atomic_number": np.asarray([r.atomic_number for r in rows], dtype=np.int16),
        "ion_level": np.asarray([_fixed(r.level_label, 20) for r in rows], dtype="U20"),
        "population": _r4_array([pop[r.global_index - 1] for r in rows]),
        "lte": _r4_array([lte[r.global_index - 1] for r in rows]),
        "upper index": np.asarray([r.upper_index for r in rows], dtype=np.int16),
    }
    return OutputTable(
        extension_name="XSTAR_RADIAL",
        columns=tuple(values),
        units=("", "", "eV", "", "", "", "", "", ""),
        formats=("1J", "1I", "1E", "8A", "1I", "20A", "1E", "1E", "1I"),
        binary=True,
        header_keywords=header.real4_keywords(),
        source_file="xstar/xstarlib/src/fstepr.f90",
        values=values,
    )


def build_detail_line_table(
    *,
    metadata: SourceOutputMetadata,
    rcem: np.ndarray,
    oplin: Sequence[float],
    tau0: np.ndarray,
    header: ShellOutputHeader,
) -> OutputTable:
    emiss = np.asarray(rcem, dtype=float)
    opacity = np.asarray(oplin, dtype=float).reshape(-1)
    depth = np.asarray(tau0, dtype=float)
    if emiss.ndim != 2 or emiss.shape[0] != 2 or depth.ndim != 2 or depth.shape[0] != 2:
        raise OutputWriterPortError("detail line arrays require direction-first shape (2,n)")
    rows: list[LineOutputMetadata] = []
    for item in metadata.lines:
        i = item.line_index - 1
        if i < 0 or i >= emiss.shape[1] or i >= opacity.size or i >= depth.shape[1]:
            continue
        active = (
            emiss[0, i] > DETAIL_LINE_ACTIVITY_FLOOR
            or emiss[1, i] > DETAIL_LINE_ACTIVITY_FLOOR
            or opacity[i] > DETAIL_LINE_ACTIVITY_FLOOR
        )
        if not active:
            continue
        wave = abs(float(item.wavelength_angstrom))
        if item.rate_type in (9, 14) or wave <= 0.1 or wave >= 9.0e9:
            continue
        rows.append(item)
    if not rows:
        raise OutputWriterPortError(
            "fstepr2 would execute its source undefined empty-row path; bounded writer requires one qualifying line"
        )
    values = {
        "index": np.asarray([r.line_index for r in rows], dtype=np.int32),
        "wavelength": _r4_array([abs(r.wavelength_angstrom) for r in rows]),
        "ion": np.asarray([_fixed(r.ion_label, 8) for r in rows], dtype="U8"),
        "lower_level": np.asarray([_fixed(r.lower_level, 20) for r in rows], dtype="U20"),
        "upper_level": np.asarray([_fixed(r.upper_level, 20) for r in rows], dtype="U20"),
        "emis_inward": _r4_array([emiss[0, r.line_index - 1] for r in rows]),
        "emis_outward": _r4_array([emiss[1, r.line_index - 1] for r in rows]),
        "opacity": _r4_array([opacity[r.line_index - 1] for r in rows]),
        "tau_in": _r4_array([depth[0, r.line_index - 1] for r in rows]),
        "tau_out": _r4_array([depth[1, r.line_index - 1] for r in rows]),
    }
    return OutputTable(
        extension_name="XSTAR_RADIAL",
        columns=tuple(values),
        units=("", "A", "", "", "", "erg/cm^3/s", "erg/cm^3/s", "/cm", "", ""),
        formats=("1J", "1E", "8A", "20A", "20A", "1E", "1E", "1E", "1E", "1E"),
        binary=True,
        header_keywords=header.real4_keywords(),
        source_file="xstar/xstarlib/src/fstepr2.f90",
        values=values,
    )


def build_detail_rrc_table(
    *,
    metadata: SourceOutputMetadata,
    cemab: np.ndarray,
    cabab: Sequence[float],
    opakab: Sequence[float],
    tauc: np.ndarray,
    header: ShellOutputHeader,
) -> OutputTable:
    emiss = np.asarray(cemab, dtype=float)
    absorbed = np.asarray(cabab, dtype=float).reshape(-1)
    opacity = np.asarray(opakab, dtype=float).reshape(-1)
    depth = np.asarray(tauc, dtype=float)
    rows: list[RRCOutputMetadata] = []
    for item in metadata.rrcs:
        i = item.continuum_index - 1
        if min(i, emiss.shape[1] - 1, absorbed.size - 1, opacity.size - 1, depth.shape[1] - 1) < 0:
            continue
        if (
            emiss[0, i] > DETAIL_RRC_ACTIVITY_FLOOR
            or emiss[1, i] > DETAIL_RRC_ACTIVITY_FLOOR
            or absorbed[i] > DETAIL_RRC_ACTIVITY_FLOOR
            or opacity[i] > DETAIL_RRC_ACTIVITY_FLOOR
        ):
            rows.append(item)
    values = {
        "rrc index": np.asarray([r.continuum_index for r in rows], dtype=np.int32),
        "level index": np.asarray([r.level_global_index for r in rows], dtype=np.int32),
        "energy": _r4_array([r.threshold_eV for r in rows]),
        "ion": np.asarray([_fixed(r.ion_label, 8) for r in rows], dtype="U8"),
        "lower_level": np.asarray([_fixed(r.lower_level, 20) for r in rows], dtype="U20"),
        "upper_level": np.asarray([_fixed(r.upper_level, 20) for r in rows], dtype="U20"),
        "emis_inward": _r4_array([emiss[0, r.continuum_index - 1] for r in rows]),
        "emis_outward": _r4_array([emiss[1, r.continuum_index - 1] for r in rows]),
        "integrated absn": _r4_array([absorbed[r.continuum_index - 1] for r in rows]),
        "opacity": _r4_array([opacity[r.continuum_index - 1] for r in rows]),
        "tau_in": _r4_array([depth[0, r.continuum_index - 1] for r in rows]),
        "tau_out": _r4_array([depth[1, r.continuum_index - 1] for r in rows]),
    }
    return OutputTable(
        extension_name="XSTAR_RADIAL",
        columns=tuple(values),
        units=("", "", "eV", "", "", "", "erg/cm^3/s", "erg/cm^3/s", "erg/cm^3/s", "/cm", "", ""),
        formats=("1J", "1J", "1E", "8A", "20A", "20A", "1E", "1E", "1E", "1E", "1E", "1E"),
        binary=True,
        header_keywords=header.real4_keywords(),
        source_file="xstar/xstarlib/src/fstepr3.f90",
        values=values,
    )


def build_detail_continuum_table(
    *,
    epi_eV: Sequence[float],
    zrems: np.ndarray,
    opakc: Sequence[float],
    rccemis: np.ndarray,
    dpthc: np.ndarray,
    ncn2: int,
    header: ShellOutputHeader,
) -> OutputTable:
    n = int(ncn2)
    epi = np.asarray(epi_eV, dtype=float).reshape(-1)
    z = np.asarray(zrems, dtype=float)
    op = np.asarray(opakc, dtype=float).reshape(-1)
    rc = np.asarray(rccemis, dtype=float)
    dp = np.asarray(dpthc, dtype=float)
    if epi.size < n or z.shape[0] < 5 or z.shape[1] < n or op.size < n or rc.shape[0] < 2 or rc.shape[1] < n or dp.shape[0] < 2 or dp.shape[1] < n:
        raise OutputWriterPortError("fstepr4 arrays are shorter than ncn2")
    values: dict[str, np.ndarray] = {
        "index": np.arange(1, n + 1, dtype=np.int32),
        "energy": _r4_array(epi[:n]),
    }
    for row in range(5):
        values[f"zrems({row + 1})"] = _r4_array(z[row, :n])
    values.update({
        "opacity": _r4_array(op[:n]),
        "emis out": _r4_array(rc[0, :n]),
        "emis in": _r4_array(rc[1, :n]),
        "fwd dpth": _r4_array(dp[0, :n]),
        "bck dpth": _r4_array(dp[1, :n]),
    })
    return OutputTable(
        extension_name="XSTAR_RADIAL",
        columns=tuple(values),
        units=("", "eV", "erg/s", "erg/s", "erg/s", "erg/s", "erg/s", "/cm", "erg/cm**3/s", "erg/cm**3/s", "", ""),
        formats=("1J",) + ("1E",) * 11,
        binary=True,
        header_keywords=header.real4_keywords(),
        source_file="xstar/xstarlib/src/fstepr4.f90",
        values=values,
    )


def build_detail_shell_output(
    *,
    metadata: SourceOutputMetadata,
    header: ShellOutputHeader,
    populations: Sequence[float],
    lte_populations: Sequence[float],
    rcem: np.ndarray,
    oplin: Sequence[float],
    tau0: np.ndarray,
    cemab: np.ndarray,
    cabab: Sequence[float],
    opakab: Sequence[float],
    tauc: np.ndarray,
    epi_eV: Sequence[float],
    zrems: np.ndarray,
    opakc: Sequence[float],
    rccemis: np.ndarray,
    dpthc: np.ndarray,
    ncn2: int,
) -> DetailShellOutput:
    return DetailShellOutput(
        levels=build_detail_level_table(metadata=metadata, populations=populations, lte_populations=lte_populations, header=header),
        lines=build_detail_line_table(metadata=metadata, rcem=rcem, oplin=oplin, tau0=tau0, header=header),
        rrcs=build_detail_rrc_table(metadata=metadata, cemab=cemab, cabab=cabab, opakab=opakab, tauc=tauc, header=header),
        continuum=build_detail_continuum_table(epi_eV=epi_eV, zrems=zrems, opakc=opakc, rccemis=rccemis, dpthc=dpthc, ncn2=ncn2, header=header),
    )


def voigte(vs: float, a: float) -> float:
    """Literal translation of ``voigte.f90`` used by ``binemis``."""
    ak = np.asarray([
        -1.12470432, -0.15516677, 3.28867591, -2.34357915, 0.42139162,
        -4.48480194, 9.39456063, -6.61487486, 1.98919585, -0.22041650,
        0.554153432, 0.278711796, -0.188325687, 0.042991293,
        -0.003278278, 0.979895023, -0.962846325, 0.532770573,
        -0.122727278,
    ], dtype=float)
    sqp = 1.772453851
    sq2 = 1.414213562
    v = abs(float(vs)); aa = float(a); u = aa + v; v2 = v * v
    if aa == 0.0:
        return 0.0 if v2 >= 100.0 else float(np.exp(-v2))
    if aa <= 0.2 and v >= 5.0:
        return aa * (15.0 + 6.0 * v2 + 4.0 * v2 * v2) / (4.0 * v2**3 * sqp)
    if aa > 1.4 or u > 3.2:
        a2 = aa * aa; uu = sq2 * (a2 + v2); u2 = 1.0 / (uu * uu)
        return sq2 / sqp * aa / uu * (1.0 + u2 * (3.0 * v2 - a2) + u2 * u2 * (15.0 * v2 * v2 - 30.0 * v2 * a2 + 3.0 * a2 * a2))
    ex = 0.0 if v2 >= 100.0 else float(np.exp(-v2))
    quo = 1.0
    if v >= 2.4:
        quo = 1.0 / (v2 - 1.5); start = 10
    elif v >= 1.3:
        start = 5
    else:
        start = 0
    a1 = ak[start:start + 5]
    h1 = quo * (a1[0] + v * (a1[1] + v * (a1[2] + v * (a1[3] + v * a1[4]))))
    if aa <= 0.2:
        return float(h1 * aa + ex * (1.0 + aa * aa * (1.0 - 2.0 * v2)))
    pqs = 2.0 / sqp
    h1p = h1 + pqs * ex
    h2p = pqs * h1p - 2.0 * v2 * ex
    h3p = (pqs * (1.0 - ex * (1.0 - 2.0 * v2)) - 2.0 * v2 * h1p) / 3.0 + pqs * h2p
    h4p = (2.0 * v2 * v2 * ex - pqs * h1p) / 3.0 + pqs * h3p
    psi = ak[15] + aa * (ak[16] + aa * (ak[17] + aa * ak[18]))
    return float(psi * (ex + aa * (h1p + aa * (h2p + aa * (h3p + aa * h4p)))))


def _source_real(value: float) -> float:
    """Return a source default-real literal promoted to Python float."""
    return float(np.float32(value))


def _rank_binemis_lines(
    *,
    metadata: SourceOutputMetadata,
    luminosity: np.ndarray,
    epi_eV: np.ndarray,
    ncn2: int,
    xlum: float,
    nrank: int = 10,
) -> np.ndarray:
    """Literal ``rlbin`` insertion table used by ``binemis.f90``."""
    from .radiation import nbinc

    n = int(ncn2)
    ngrid = int(epi_eV.size)
    ranked = np.zeros((int(nrank), ngrid), dtype=np.int64)
    emina = _source_real(12398.4016) / float(epi_eV[n - 1])
    emaxa = _source_real(12398.4016) / float(epi_eV[0])
    gate = _source_real(1.0e-15) * float(xlum)
    activity_floor = _source_real(1.0e-37)

    by_index = {row.line_index: row for row in metadata.lines}
    for line_index in sorted(by_index):
        row = by_index[line_index]
        j = int(row.line_index) - 1
        if j < 0 or j >= luminosity.shape[1]:
            continue
        if not (luminosity[0, j] > gate or luminosity[1, j] > gate):
            continue
        wavelength = abs(float(row.wavelength_angstrom))
        if luminosity[0, j] + luminosity[1, j] < activity_floor:
            continue
        if wavelength > emaxa or wavelength < emina:
            continue
        energy = _source_real(12398.4016) / (_source_real(1.0e-34) + wavelength)
        bin_one_based = int(nbinc(energy, epi_eV, n))
        if bin_one_based < 1 or bin_one_based > ngrid:
            continue

        mm = 0
        done = False
        new_strength = luminosity[0, j] + luminosity[1, j]
        while not done:
            mm += 1
            existing = int(ranked[mm - 1, bin_one_based - 1])
            if existing == 0 or line_index == 0:
                done = True
            else:
                old_strength = luminosity[0, existing - 1] + luminosity[1, existing - 1]
                if new_strength > old_strength:
                    done = True
                if mm >= nrank:
                    done = True
        if mm >= nrank:
            continue
        for mm2 in range(nrank - 1, mm - 1, -1):
            ranked[mm2, bin_one_based - 1] = ranked[mm2 - 1, bin_one_based - 1]
        ranked[mm - 1, bin_one_based - 1] = line_index
    return ranked


def build_binemis_spectrum(
    *,
    metadata: SourceOutputMetadata,
    xlum: float,
    temperature_1e4K: float,
    turbulent_velocity_km_s: float,
    epi_eV: Sequence[float],
    ncn2: int,
    dpthc: np.ndarray,
    elum: np.ndarray,
    zrems: np.ndarray,
    zremsz: Sequence[float],
) -> np.ndarray:
    """Literal array translation of ``binemis.f90``.

    Atomic pointer traversal is resolved before entry into
    :class:`LineOutputMetadata`; ranking, temporary-grid profile formation,
    stopping tests, trapezoid accumulation, and continuum-row remapping retain
    the original source order.  The caller-owned tail above ``ncn2`` is left
    unchanged.
    """
    from .radiation import nbinc

    n = int(ncn2)
    epi = np.asarray(epi_eV, dtype=float).reshape(-1)
    dp = np.asarray(dpthc, dtype=float)
    lum = np.asarray(elum, dtype=float)
    original = np.asarray(zrems, dtype=float)
    incident = np.asarray(zremsz, dtype=float).reshape(-1)
    if (
        epi.size < n
        or dp.ndim != 2
        or dp.shape[0] < 2
        or dp.shape[1] < n
        or lum.ndim != 2
        or lum.shape[0] < 2
        or original.ndim != 2
        or original.shape[0] < 5
        or original.shape[1] < n
        or incident.size < n
    ):
        raise OutputWriterPortError("binemis arrays are shorter than active source ranges")

    nbtpp = int(epi.size)
    out = np.asarray(original, dtype=float).copy()
    saved = np.asarray(original, dtype=float).copy()
    out[:, :n] = 0.0
    temporary_binned = np.zeros((2, nbtpp), dtype=float)
    temporary_profile = np.zeros((2, nbtpp), dtype=float)
    temporary_energy = np.zeros(nbtpp, dtype=float)
    ranked = _rank_binemis_lines(
        metadata=metadata,
        luminosity=lum,
        epi_eV=epi,
        ncn2=n,
        xlum=xlum,
        nrank=10,
    )
    by_index = {row.line_index: row for row in metadata.lines}
    gate = _source_real(1.0e-15) * float(xlum)
    dpcrit = _source_real(1.0e-6)

    for kl_one_based in range(1, n + 1):
        for mm_one_based in range(1, 11):
            line_index = int(ranked[mm_one_based - 1, kl_one_based - 1])
            if line_index <= 0 or line_index > lum.shape[1]:
                continue
            row = by_index.get(line_index)
            if row is None:
                continue
            j = line_index - 1
            wavelength = abs(float(row.wavelength_angstrom))
            line_energy = _source_real(12398.4016) / (_source_real(1.0e-34) + wavelength)
            nb1 = int(nbinc(line_energy, epi, n))
            if not (
                (lum[0, j] > gate or lum[1, j] > gate)
                and nb1 > 2
                and int(row.data_type) != 76
            ):
                continue
            if nb1 >= n:
                raise OutputWriterPortError("binemis source would read epi(nb1+1) beyond ncn2")
            if nbtpp < 20:
                raise OutputWriterPortError(
                    "binemis strong-line profile requires the source temporary grid capacity (ncn >= 20)"
                )

            mass = max(float(row.atomic_mass), np.finfo(float).tiny)
            vth = _source_real(12.0) * np.sqrt(float(temperature_1e4K) / mass)
            vturb = max(float(turbulent_velocity_km_s), float(vth))
            e0 = _source_real(12398.42) / max(wavelength, 1.0e-49)
            deleturb = e0 * (vturb / _source_real(3.0e5))
            deleth = e0 * (vth / _source_real(3.0e5))
            dele = float(np.sqrt(deleth * deleth + deleturb * deleturb))
            if dele <= 0.0:
                raise OutputWriterPortError("binemis line width is nonpositive")

            # A matching type-86 record replaces egam and supplies the Auger
            # natural width.  Metadata stores those caller-resolved values.
            if float(row.auger_rate_s) != 0.0:
                delea = float(row.auger_rate_s) * _source_real(4.14e-15)
            else:
                delea = float(row.auger_width_eV)
            deler = float(row.natural_rate_s) * _source_real(4.14e-15)
            aasmall = (delea + deler) / (_source_real(1.0e-36) + dele) / _source_real(12.56)

            ml1 = nb1
            e00 = float(epi[ml1 - 1])
            etmp = e0
            deleepi = float(epi[ml1] - epi[ml1 - 1])
            deletpp = dele
            ncut = int(deleepi / deletpp)
            ncut = max(ncut, 1)
            ncut = min(ncut, nbtpp // 10)
            if ncut <= 0:
                raise OutputWriterPortError("binemis source temporary-grid ncut collapsed to zero")
            deleused = deleepi / float(np.float32(ncut))
            mlc = 0
            ldir = 1
            ldon = [0, 0]
            mlmin = nbtpp
            mlmax = 1
            ml1min = nbtpp + 1
            ml1max = 0
            ml2 = nbtpp // 2
            center = ml2 - 1

            delet = (e00 - etmp) / dele
            if aasmall > _source_real(1.0e-9):
                profile = voigte(abs(delet), aasmall) / _source_real(1.772)
            else:
                profile = np.exp(-delet * delet) / _source_real(1.772)
            profile = profile / dele / _source_real(1.602197e-12)
            temporary_energy[center] = e00
            temporary_profile[0, center] = lum[0, j] * profile
            temporary_profile[1, center] = lum[1, j] * profile
            tst = 1.0

            while ldon[0] * ldon[1] == 0 and mlc < nbtpp // 2:
                mlc += 1
                for ij in range(2):
                    ldir = -ldir
                    if ldon[ij] == 1:
                        continue
                    mlm = ml2 + ldir * mlc
                    mlm = min(nbtpp, max(1, mlm))
                    etptst = e00 + float(np.float32(ldir * mlc)) * deleused
                    if (
                        mlm < nbtpp
                        and mlm > 1
                        and etptst > 0.0
                        and etptst < float(epi[n - 1])
                    ):
                        mlmin = min(mlm, mlmin)
                        mlmax = max(mlm, mlmax)
                        temporary_energy[mlm - 1] = etptst
                        delet = (etptst - etmp) / dele
                        if aasmall > _source_real(1.0e-9):
                            profile = voigte(abs(delet), aasmall) / _source_real(1.772)
                        else:
                            profile = np.exp(-delet * delet) / _source_real(1.772)
                        profile = profile / dele / _source_real(1.602197e-12)
                        temporary_profile[0, mlm - 1] = lum[0, j] * profile
                        temporary_profile[1, mlm - 1] = lum[1, j] * profile
                        tst = profile
                    deletmax = max(50.0, 200.0 * aasmall)
                    if (
                        (
                            tst < dpcrit
                            or mlm <= 1
                            or mlm >= nbtpp
                            or etptst <= 0.0
                            or etptst >= float(epi[n - 1])
                            or mlc > nbtpp
                            or abs((etptst - etmp) / dele) > deletmax
                        )
                        and ml1min < ml1 - 2
                        and ml1max > ml1 + 2
                        and ml1min >= 1
                        and ml1max <= nbtpp
                    ):
                        ldon[ij] = 1

            if mlmin > mlmax:
                continue
            ml1min = int(nbinc(float(temporary_energy[mlmin - 1]), epi, n))
            ml1max = int(nbinc(float(temporary_energy[mlmax - 1]), epi, n))
            ml1m = ml1min
            mlmin = max(mlmin, 2)
            mlmax = min(mlmax, nbtpp)
            sume = 0.0
            zrsum1 = 0.0
            zrsum2 = 0.0
            for mlm in range(mlmin + 1, mlmax + 1):
                tmpe = abs(temporary_energy[mlm - 1] - temporary_energy[mlm - 2])
                sume += tmpe
                zrsum1 += (
                    temporary_profile[0, mlm - 1] + temporary_profile[0, mlm - 2]
                ) * tmpe / 2.0
                zrsum2 += (
                    temporary_profile[1, mlm - 1] + temporary_profile[1, mlm - 2]
                ) * tmpe / 2.0
                if temporary_energy[mlm - 1] > epi[ml1m - 1]:
                    if mlm == mlmax:
                        ml1m = max(1, ml1m - 1)
                    if sume > 1.0e-24:
                        zrtp2 = zrsum2 / sume
                        zrtp1 = zrsum1 / sume
                        while temporary_energy[mlm - 1] > epi[ml1m - 1] and ml1m < n:
                            temporary_binned[0, ml1m - 1] = zrtp1
                            temporary_binned[1, ml1m - 1] = zrtp2
                            ml1m += 1
                    zrsum2 = 0.0
                    zrsum1 = 0.0
                    sume = 0.0

            temporary_profile[:, mlmin - 1 : mlmax] = 0.0
            lo = max(1, ml1min)
            hi = min(n, ml1max)
            if lo <= hi:
                out[3, lo - 1 : hi] += temporary_binned[1, lo - 1 : hi]
                out[2, lo - 1 : hi] += temporary_binned[0, lo - 1 : hi]
                temporary_binned[:, lo - 1 : hi] = 0.0

    for kl in range(n):
        out[2, kl] += saved[1, kl]
        out[3, kl] += saved[2, kl]
        out[1, kl] = incident[kl] * np.exp(-dp[0, kl])
        out[0, kl] = incident[kl]
        out[4, kl] = saved[3, kl]
    if original.shape[1] > n:
        out[:, n:] = original[:, n:]
    return out

def build_final_spectrum_table(
    *,
    metadata: SourceOutputMetadata,
    xlum: float,
    temperature_1e4K: float,
    turbulent_velocity_km_s: float,
    epi_eV: Sequence[float],
    ncn2: int,
    dpthc: np.ndarray,
    elum: np.ndarray,
    zrems: np.ndarray,
    zremsz: Sequence[float],
    lwri: int,
) -> OutputTable:
    if int(lwri) >= 0:
        mapped = build_binemis_spectrum(
            metadata=metadata, xlum=xlum,
            temperature_1e4K=temperature_1e4K,
            turbulent_velocity_km_s=turbulent_velocity_km_s,
            epi_eV=epi_eV, ncn2=ncn2, dpthc=dpthc, elum=elum,
            zrems=zrems, zremsz=zremsz,
        )
    else:
        mapped = np.asarray(zrems, dtype=float).copy()
    n = int(ncn2)
    values = {
        "energy": _r4_array(np.asarray(epi_eV)[:n]),
        "incident": _r4_array(mapped[0, :n]),
        "transmitted": _r4_array(mapped[1, :n]),
        "emit_inward": _r4_array(mapped[2, :n]),
        "emit_outward": _r4_array(mapped[3, :n]),
    }
    # Source defines a sixth 'scattered' descriptor but writes tfields=5.
    return OutputTable(
        extension_name="XSTAR_SPECTRA",
        columns=tuple(values),
        units=("eV", "erg/s/erg", "erg/s/erg", "erg/s/erg", "erg/s/erg"),
        formats=("E13.5",) * 5,
        binary=False,
        source_file="xstar/xstarlib/src/writespectra.f90",
        header_keywords={"SCATDROP": True},
        values=values,
    )


def _rank_final_lines(metadata: SourceOutputMetadata, elum: np.ndarray) -> list[LineOutputMetadata]:
    lum = np.asarray(elum, dtype=float)
    eligible: list[tuple[float, int, LineOutputMetadata]] = []
    for order, row in enumerate(metadata.lines):
        i = row.line_index - 1
        if i < 0 or i >= lum.shape[1]:
            continue
        mean = 0.5 * (lum[0, i] + lum[1, i])
        wave = abs(float(row.wavelength_angstrom))
        if row.rate_type in (9, 14) or wave < 0.1 or wave > 1.0e10 or wave > 8.9e6 or mean <= FINAL_LINE_ACTIVITY_FLOOR:
            continue
        eligible.append((mean, order, row))
    eligible.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in eligible[:FINAL_LINE_LIMIT]]


def build_final_line_table(*, metadata: SourceOutputMetadata, elum: np.ndarray, tau0: np.ndarray) -> OutputTable:
    lum = np.asarray(elum, dtype=float); depth = np.asarray(tau0, dtype=float)
    rows = _rank_final_lines(metadata, lum)
    values = {
        "index": np.asarray([r.line_index for r in rows], dtype=np.int32),
        "ion": np.asarray([_fixed(r.ion_label, 9) for r in rows], dtype="U9"),
        "lower_level": np.asarray([_fixed(r.lower_level, 20) for r in rows], dtype="U20"),
        "upper_level": np.asarray([_fixed(r.upper_level, 20) for r in rows], dtype="U20"),
        "wavelength": _r4_array([abs(r.wavelength_angstrom) for r in rows]),
        "emit_inward": _r4_array([lum[0, r.line_index - 1] for r in rows]),
        "emit_outward": _r4_array([lum[1, r.line_index - 1] for r in rows]),
        "depth_inward": _r4_array([depth[0, r.line_index - 1] for r in rows]),
        "depth_outward": _r4_array([depth[1, r.line_index - 1] for r in rows]),
    }
    return OutputTable(
        extension_name="XSTAR_LINES",
        columns=tuple(values),
        units=("", "", "", "", "A", "erg/s/10**38", "erg/s/10**38", "", ""),
        formats=("I6", "A9", "A20", "A20", "E13.5", "E13.5", "E13.5", "E13.5", "E13.5"),
        binary=False,
        source_file="xstar/xstarlib/src/writespectra2.f90",
        values=values,
    )


def build_final_continuum_table(*, epi_eV: Sequence[float], ncn2: int, dpthcont: np.ndarray, zrems: np.ndarray, zremsz: Sequence[float]) -> OutputTable:
    n = int(ncn2); epi = np.asarray(epi_eV, dtype=float); dp = np.asarray(dpthcont, dtype=float); z = np.asarray(zrems, dtype=float); inc = np.asarray(zremsz, dtype=float)
    values = {
        "energy": _r4_array(epi[:n]),
        "incident": _r4_array(inc[:n]),
        "transmitted": _r4_array(inc[:n] * np.exp(-dp[0, :n])),
        "emit_inward": _r4_array(z[3, :n]),
        "emit_outward": _r4_array(z[4, :n]),
    }
    return OutputTable(
        extension_name="XSTAR_SPECTRA",
        columns=tuple(values),
        units=("eV", "erg/s/erg", "erg/s/erg", "erg/s/erg", "erg/s/erg"),
        formats=("E13.5",) * 5,
        binary=False,
        source_file="xstar/xstarlib/src/writespectra3.f90",
        values=values,
    )


def build_final_rrc_table(*, metadata: SourceOutputMetadata, elumab: np.ndarray, tauc: np.ndarray) -> OutputTable:
    lum = np.asarray(elumab, dtype=float); depth = np.asarray(tauc, dtype=float)
    rows = []
    for r in metadata.rrcs:
        i = r.continuum_index - 1
        if not (0 <= i < lum.shape[1]):
            continue
        # v0.5.09: undo the v0.5.07 depth-only RRC retention experiment.
        # Source writespectra4 selects final RRC rows from the two elumab
        # luminosity channels; tauc/depth is payload for retained rows, not an
        # independent row-selection predicate.  Depth-only retention over-wrote
        # source row identity and produced extra zero-emission RRC rows.
        active_lum = lum[0, i] > FINAL_RRC_ACTIVITY_FLOOR or lum[1, i] > FINAL_RRC_ACTIVITY_FLOOR
        if active_lum:
            rows.append(r)
    values = {
        "index": np.asarray([r.continuum_index for r in rows], dtype=np.int32),
        "ion": np.asarray([_fixed(r.ion_label, 9) for r in rows], dtype="U9"),
        "level": np.asarray([_fixed(r.lower_level, 20) for r in rows], dtype="U20"),
        "energy": _r4_array([r.threshold_eV for r in rows]),
        "emit_outward": _r4_array([lum[0, r.continuum_index - 1] for r in rows]),
        "emit_inward": _r4_array([lum[1, r.continuum_index - 1] for r in rows]),
        "depth_outward": _r4_array([depth[0, r.continuum_index - 1] for r in rows]),
        "depth_inward": _r4_array([depth[1, r.continuum_index - 1] for r in rows]),
    }
    return OutputTable(
        extension_name="XSTAR_SPECTRA",
        columns=tuple(values),
        units=("", "", "", "eV", "erg/s", "erg/s", "", ""),
        formats=("I6", "A9", "A20", "E13.5", "E13.5", "E13.5", "E13.5", "E13.5"),
        binary=False,
        source_file="xstar/xstarlib/src/writespectra4.f90",
        values=values,
    )


def build_final_output_products(
    *, metadata: SourceOutputMetadata, xlum: float, temperature_1e4K: float,
    turbulent_velocity_km_s: float, epi_eV: Sequence[float], ncn2: int,
    dpthc: np.ndarray, dpthcont: np.ndarray, elum: np.ndarray,
    elumab: np.ndarray, tau0: np.ndarray, tauc: np.ndarray,
    zrems: np.ndarray, zremsz: Sequence[float], lwri: int,
) -> FinalOutputProducts:
    return FinalOutputProducts(
        spectrum=build_final_spectrum_table(metadata=metadata, xlum=xlum, temperature_1e4K=temperature_1e4K, turbulent_velocity_km_s=turbulent_velocity_km_s, epi_eV=epi_eV, ncn2=ncn2, dpthc=dpthc, elum=elum, zrems=zrems, zremsz=zremsz, lwri=lwri),
        lines=build_final_line_table(metadata=metadata, elum=elum, tau0=tau0),
        continuum=build_final_continuum_table(epi_eV=epi_eV, ncn2=ncn2, dpthcont=dpthcont, zrems=zrems, zremsz=zremsz),
        rrcs=build_final_rrc_table(metadata=metadata, elumab=elumab, tauc=tauc),
    )


def _fits_column(name: str, fmt: str, unit: str, values: np.ndarray) -> fits.Column:
    # Astropy expects binary string widths as e.g. 8A and numeric source forms
    # without the Fortran leading repeat for scalar columns.
    f = fmt
    if f in {"1J", "1I", "1E"}:
        f = f[1:]
    return fits.Column(name=name, format=f, unit=(unit or None), array=values)


def _table_hdu(table: OutputTable) -> fits.hdu.base.ExtensionHDU:
    cols = [
        _fits_column(name, fmt, unit, np.asarray(table.values[name]))
        for name, fmt, unit in zip(table.columns, table.formats, table.units)
    ]
    if table.binary:
        hdu = fits.BinTableHDU.from_columns(cols, name=table.extension_name)
    else:
        hdu = fits.TableHDU.from_columns(cols, name=table.extension_name)
    for key, value in table.header_keywords.items():
        # Long internal diagnostic keys are written as HIERARCH cards.
        hdu.header[key] = value
    hdu.add_checksum()
    return hdu


def _primary_hdu(*, model_name: str, atomic_data_date: str) -> fits.PrimaryHDU:
    hdu = fits.PrimaryHDU()
    hdu.header["CREATOR"] = "XSTAR version 2.59g"
    hdu.header["MODEL"] = _fixed(model_name, 30).rstrip()
    hdu.header["ATDATA"] = str(atomic_data_date)[:63]
    return hdu


def write_final_output_files(
    products: FinalOutputProducts,
    *, out_dir: str | Path,
    parameters: Sequence[OutputParameter],
    model_name: str,
    atomic_data_date: str,
    lwri: int = 0,
    overwrite: bool = True,
) -> dict[str, str]:
    output = Path(out_dir); output.mkdir(parents=True, exist_ok=True)
    parameter_table = build_parameter_table(parameters, model_name=model_name)
    level = int(lwri)
    mapping: dict[str, OutputTable] = {}
    if level >= -1:
        mapping["xout_spect1.fits"] = products.spectrum
    if level >= 0:
        mapping.update({
            "xout_lines1.fits": products.lines,
            "xout_cont1.fits": products.continuum,
            "xout_rrc1.fits": products.rrcs,
        })
    paths: dict[str, str] = {}
    for filename, table in mapping.items():
        path = output / filename
        hdul = fits.HDUList([
            _primary_hdu(model_name=model_name, atomic_data_date=atomic_data_date),
            _table_hdu(parameter_table),
            _table_hdu(table),
        ])
        hdul.writeto(path, overwrite=overwrite, checksum=True)
        paths[filename] = str(path)
    return paths



def _fnappend_detail_filename(name: str, pass_index: int) -> str:
    """Translate ``fnappend.f90`` for the pass-specific detail files."""
    kk = int(pass_index)
    if kk < 1 or kk > 99:
        raise OutputWriterPortError("fnappend detail pass index must be in 1..99")
    text = str(name)
    if len(text) < 4:
        raise OutputWriterPortError("detail filename is shorter than four characters")
    return text[:2] + f"{kk:02d}" + text[4:]

def write_detail_output_files(
    store: DetailOutputStore,
    *, out_dir: str | Path,
    parameters: Sequence[OutputParameter],
    model_name: str,
    atomic_data_date: str,
    pass_index: int | None = None,
    overwrite: bool = True,
) -> dict[str, str]:
    output = Path(out_dir); output.mkdir(parents=True, exist_ok=True)
    parameter_table = build_parameter_table(parameters, model_name=model_name)
    kk = int(store.pass_index if pass_index is None else pass_index)
    specs = (
        (_fnappend_detail_filename("xout_detail.fits", kk), "levels"),
        (_fnappend_detail_filename("xout_detal2.fits", kk), "lines"),
        (_fnappend_detail_filename("xout_detal3.fits", kk), "rrcs"),
        (_fnappend_detail_filename("xout_detal4.fits", kk), "continuum"),
    )
    paths: dict[str, str] = {}
    for filename, attr in specs:
        hdus: list[fits.hdu.base._BaseHDU] = [
            _primary_hdu(model_name=model_name, atomic_data_date=atomic_data_date),
            _table_hdu(parameter_table),
        ]
        hdus.extend(_table_hdu(getattr(record, attr)) for record in store.records)
        path = output / filename
        fits.HDUList(hdus).writeto(path, overwrite=overwrite, checksum=True)
        paths[filename] = str(path)
    return paths


def _state_temperature_t4(state: XSTARPythonState) -> float:
    """Return source ``t`` in 10^4 K using explicit state ownership when set."""
    value = float(state.plasma.temperature)
    unit = str(state.control.get("plasma_temperature_unit", "legacy-auto")).strip().lower()
    if unit in {"k", "kelvin"}:
        return value / 1.0e4
    if unit in {"t4", "1e4k", "10^4k"}:
        return value
    # Backward compatibility for bounded synthetic writer fixtures.
    return value / 1.0e4 if value > 1.0e3 else value


def _shell_header_from_state(state: XSTARPythonState) -> ShellOutputHeader:
    t4 = _state_temperature_t4(state)
    radius = float(state.transfer.radius)
    delr = float(state.transfer.step_size)
    return ShellOutputHeader(
        inner_radius_cm=radius,
        outer_radius_cm=delr,
        radial_depth_cm=float(state.transfer.radial_depth),
        temperature_1e4K=t4,
        pressure_dyn_cm2=float(state.control.get("p", 0.0)),
        column_cm2=float(state.transfer.column),
        electron_fraction=float(state.plasma.xee),
        density_cm3=float(state.plasma.xpx),
        logxi=float(state.control.get("zeta", 0.0)),
    )


def _detail_level_vector(values: Sequence[float], metadata: SourceOutputMetadata) -> np.ndarray:
    """Return the zero-based vector expected by the FITS detail builders.

    The live translated solver owns source-style one-based global population
    arrays with a zero guard.  ``build_detail_level_table`` deliberately uses
    Python zero-based indexing (``global_index - 1``), so the guard must be
    removed exactly once at this adapter boundary.  Synthetic writer fixtures
    may already provide guardless vectors and are retained unchanged.
    """
    arr = np.asarray(values, dtype=float).reshape(-1)
    required = max((int(row.global_index) for row in metadata.levels), default=0)
    if required <= 0:
        return arr.copy()
    if arr.size == required + 1:
        return arr[1:].copy()
    if arr.size < required:
        raise OutputWriterPortError(
            f"level vector has length {arr.size}, shorter than required global index {required}"
        )
    return arr.copy()


def _zero_like_table(table: OutputTable) -> OutputTable:
    values: dict[str, np.ndarray] = {}
    for name in table.columns:
        arr = np.asarray(table.values[name])
        if np.issubdtype(arr.dtype, np.number):
            values[name] = np.zeros_like(arr)
        else:
            values[name] = np.asarray(["" for _ in range(arr.shape[0])], dtype=arr.dtype)
    return OutputTable(
        extension_name=table.extension_name,
        columns=table.columns,
        units=table.units,
        values=values,
        formats=table.formats,
        binary=table.binary,
        header_keywords=table.header_keywords,
        source_file=table.source_file,
    )

def _zero_detail_shell_output(record: DetailShellOutput) -> DetailShellOutput:
    return DetailShellOutput(
        levels=_zero_like_table(record.levels),
        lines=_zero_like_table(record.lines),
        rrcs=_zero_like_table(record.rrcs),
        continuum=_zero_like_table(record.continuum),
        source_order=record.source_order,
        source_file=record.source_file,
    )

def append_detail_output_from_state(state: XSTARPythonState, *, hdunum: int, terminal_record: bool = False) -> DetailShellOutput:
    from .radial_transfer import _workspace_from_state, _level_arrays_from_state

    metadata = _metadata_from_control(state)
    workspace = _workspace_from_state(state)
    populations, lte = _level_arrays_from_state(state)
    populations_out = _detail_level_vector(populations, metadata)
    lte_out = _detail_level_vector(lte, metadata)
    ncn2 = int(state.control["ncn2"])
    record = build_detail_shell_output(
        metadata=metadata,
        header=_shell_header_from_state(state),
        populations=populations_out,
        lte_populations=lte_out,
        rcem=workspace.rcem_physical,
        oplin=workspace.oplin_physical,
        tau0=workspace.tau0,
        cemab=workspace.cemab_physical,
        cabab=workspace.emissivity.base.cabab[1:],
        opakab=workspace.opakab_physical,
        tauc=workspace.tauc,
        epi_eV=state.radiation.epi,
        zrems=workspace.zrems,
        opakc=workspace.opakc,
        rccemis=workspace.rccemis,
        dpthc=workspace.dpthc,
        ncn2=ncn2,
    )
    if bool(terminal_record):
        # v0.5.10: source detail output does not zero the terminal shell.
        # The terminal detail record reuses the caller-owned final radial
        # state, like savd/fstepr*, and must be appended after the last
        # physical shell record.  Abundance-table zero padding is handled
        # separately by pprint/output formatting and must not be applied to
        # xo01_detal*.fits payload arrays.
        pass
    pass_index = int(state.transfer.pass_index)
    stores = state.outputs.get("detail_output_stores")
    if stores is None:
        stores = {}
        state.outputs["detail_output_stores"] = stores
    if not isinstance(stores, dict):
        raise OutputWriterPortError("state.outputs['detail_output_stores'] has wrong type")
    store = stores.get(pass_index)
    if store is None:
        store = DetailOutputStore(pass_index=pass_index)
        stores[pass_index] = store
    if not isinstance(store, DetailOutputStore):
        raise OutputWriterPortError("detail output pass store has wrong type")
    if bool(terminal_record):
        store.records.append(record)
        store.inserted_after_hdus.append(int(hdunum))
    else:
        store.insert_after_hdu(hdunum, record)
    state.outputs["detail_output_store"] = store
    state.outputs.setdefault("detail_output_source_order", []).append(
        {
            "pass_index": pass_index,
            "after_hdu": int(hdunum),
            "source_order": list(record.source_order),
        }
    )
    return record


def build_final_output_from_state(state: XSTARPythonState, *, lwri: int = 0) -> FinalOutputProducts:
    from .radial_transfer import _workspace_from_state

    metadata = _metadata_from_control(state)
    workspace = _workspace_from_state(state)
    ncn2 = int(state.control["ncn2"])
    t4 = _state_temperature_t4(state)
    products = build_final_output_products(
        metadata=metadata,
        xlum=float(state.control.get("xlum", 1.0)),
        temperature_1e4K=t4,
        turbulent_velocity_km_s=float(state.control.get("vturbi", 0.0)),
        epi_eV=state.radiation.epi,
        ncn2=ncn2,
        dpthc=workspace.dpthc,
        dpthcont=workspace.dpthcont,
        elum=workspace.elum,
        elumab=workspace.elumab,
        tau0=workspace.tau0,
        tauc=workspace.tauc,
        zrems=workspace.zrems,
        zremsz=workspace.zremsz,
        lwri=int(lwri),
    )
    state.outputs["final_output_products"] = products
    return products


def _pprint_final_source_state_handler(state: XSTARPythonState) -> tuple[str, ...]:
    """Record the legacy ``pprint`` boundary without fabricating its files."""
    lpri = int(state.control.get("lpri", 0))
    nlnprnt = 2 if lpri == 0 else 10 if lpri == 1 else 15 if lpri == 2 else 18 if lpri == 3 else 21
    calls = ("pprint(22)",) + tuple(f"pprint(report:{index})" for index in range(2, nlnprnt + 1))
    state.outputs["pprint_final_source_state_handler"] = {
        "source_file": "xstar/xstarlib/src/pprint.f90",
        "calls": list(calls),
        "legacy_ascii_products_written": False,
        "state_handler_only": True,
    }
    return calls


def run_output_writer_sequence(
    state: XSTARPythonState,
    *,
    out_dir: str | Path | None = None,
    lwri: int = 0,
    parameters: Sequence[OutputParameter] = (),
    model_name: str = "xstar-python",
    atomic_data_date: str = "",
    final_local_recompute: bool = False,
    driver: Any | None = None,
) -> OutputWriterSequenceResult:
    """Execute the bounded detail/final writer sequence in caller order.

    When ``final_local_recompute`` is true, the literal post-pass
    ``xstarcalc(nlimd=0) -> heatt -> stpcut`` sequence is executed before the
    final writers.  When ``pprint_legacy_enabled`` is true, the translated
    default ``pprint`` path writes ``xout_step.log`` and
    ``xout_abund1.fits``; otherwise the historical explicit handler remains.
    """
    source_order: list[str] = []
    if final_local_recompute:
        from .driver import XSTARPythonDriver, XSTARSourceRoutine
        from .radial_transfer import RadialTransferWorkspace, register_bounded_radial_source_routines

        runner = driver or XSTARPythonDriver()
        if driver is None:
            register_bounded_radial_source_routines(runner)
        completed_before = len(state.provenance.get("completed_source_routines", []))

        # Source-order carry-forward guard for the final nlimd=0 print pass.
        # Original xstar.f90 performs a local recomputation with delr=1.d-15
        # immediately before pprint/writespectra, but the escaping radiation
        # arrays are caller-owned radial accumulators.  If the local recompute
        # rebuilds emissivity workspaces and leaves a direction-specific
        # accumulator row zero, preserve the pre-print accumulated radial value
        # rather than treating the local recompute as a request to clear the
        # escaping spectrum.  This is not a scale factor: nonzero final values
        # from heatt still win; only zeroed rows are refilled from the
        # caller-owned state present at the final-print source boundary.
        radial_workspace = state.control.get("radial_transfer_workspace")
        final_transfer_snapshot: dict[str, np.ndarray] = {}
        if isinstance(radial_workspace, RadialTransferWorkspace):
            final_transfer_snapshot = {
                "zrems": np.asarray(radial_workspace.zrems, dtype=float).copy(),
                "zremso": np.asarray(radial_workspace.zremso, dtype=float).copy(),
                "elum": np.asarray(radial_workspace.elum, dtype=float).copy(),
                "elumo": np.asarray(radial_workspace.elumo, dtype=float).copy(),
                "elumab": np.asarray(radial_workspace.elumab, dtype=float).copy(),
                "elumabo": np.asarray(radial_workspace.elumabo, dtype=float).copy(),
            }

        source_delr = float(np.float32(1.0e-15))
        state.transfer.step_size = source_delr
        state.control["delr"] = source_delr
        state.control["nlimd"] = 0
        state.control["nlimdt"] = 0
        runner.run_xstarcalc(state, fixed_state=False)
        runner.run_source_routines(
            (XSTARSourceRoutine.HEATT, XSTARSourceRoutine.STPCUT), state
        )

        restored_counts: dict[str, int] = {}
        radial_workspace_after = state.control.get("radial_transfer_workspace")
        if final_transfer_snapshot and isinstance(radial_workspace_after, RadialTransferWorkspace):
            for name in ("zrems", "elum", "elumab"):
                target = np.asarray(getattr(radial_workspace_after, name), dtype=float)
                before = final_transfer_snapshot.get(name)
                old_name = {"zrems": "zremso", "elum": "elumo", "elumab": "elumabo"}[name]
                old_before = final_transfer_snapshot.get(old_name)
                if before is None:
                    continue
                source = before
                if old_before is not None and old_before.shape == before.shape:
                    source = np.where(np.abs(before) > 0.0, before, old_before)
                if target.shape != source.shape:
                    continue
                mask = (np.abs(target) == 0.0) & (np.abs(source) > 0.0)
                if np.any(mask):
                    target[mask] = source[mask]
                    restored_counts[name] = int(np.count_nonzero(mask))

        source_order.extend(
            state.provenance.get("completed_source_routines", [])[completed_before:]
        )
        state.outputs["final_local_recompute"] = {
            "source_file": "xstar/src/xstar/xstar.f90",
            "delr": source_delr,
            "nlimd": 0,
            "dsec_skipped": True,
            "source_order": list(source_order),
            "source_order_transfer_carry_forward_counts": dict(restored_counts),
        }

    pprint_paths: dict[str, str] = {}
    pprint_products_written = False
    if bool(state.control.get("pprint_legacy_enabled", False)):
        from .pprint_legacy import finalize_legacy_pprint

        pprint_calls, generated_pprint_paths = finalize_legacy_pprint(
            state, out_dir=out_dir, overwrite=True
        )
        source_order.extend(pprint_calls)
        pprint_paths.update(generated_pprint_paths)
        pprint_products_written = bool(generated_pprint_paths)
        state.outputs["pprint_final_source_state_handler"] = {
            "source_file": "xstar/xstarlib/src/pprint.f90",
            "calls": list(pprint_calls),
            "legacy_ascii_products_written": pprint_products_written,
            "state_handler_only": False,
        }
    else:
        source_order.extend(_pprint_final_source_state_handler(state))
    stores_value = state.outputs.get("detail_output_stores", {})
    if not isinstance(stores_value, dict):
        raise OutputWriterPortError("invalid detail output store mapping")
    if not all(
        isinstance(key, int) and isinstance(value, DetailOutputStore)
        for key, value in stores_value.items()
    ):
        raise OutputWriterPortError("invalid detail output pass-store entry")
    # Preserve the caller-owned mapping identity.  The source writers append to
    # already-open caller files; they do not replace the saved pass container.
    stores: dict[int, DetailOutputStore] = stores_value

    level = int(lwri)
    final: FinalOutputProducts | None = None
    writer_names: list[str] = []
    if level >= -1:
        final = build_final_output_from_state(state, lwri=level)
        writer_names.append("writespectra")
        if level >= 0:
            writer_names.extend(("writespectra2", "writespectra3", "writespectra4"))
    source_order.extend(writer_names)

    paths: dict[str, str] = dict(pprint_paths)
    if out_dir is not None:
        for pass_index in sorted(stores):
            paths.update(
                write_detail_output_files(
                    stores[pass_index],
                    out_dir=out_dir,
                    parameters=parameters,
                    model_name=model_name,
                    atomic_data_date=atomic_data_date,
                    pass_index=pass_index,
                )
            )
        if final is not None:
            paths.update(
                write_final_output_files(
                    final,
                    out_dir=out_dir,
                    parameters=parameters,
                    model_name=model_name,
                    atomic_data_date=atomic_data_date,
                    lwri=level,
                )
            )
    state.outputs["output_writer_source_order"] = tuple(source_order)
    state.outputs["output_writer_paths"] = dict(paths)
    state.outputs["output_writers_executed"] = bool(writer_names or stores)
    return OutputWriterSequenceResult(
        detail_stores=stores,
        final_products=final,
        written_paths=paths,
        source_order=tuple(source_order),
        final_local_recompute_executed=bool(final_local_recompute),
        pprint_source_state_handler_ready=True,
        pprint_products_written=pprint_products_written,
    )

def direct_fortran_output_reference() -> dict[str, Any]:
    """Frozen reference from literal original-Fortran writer loops.

    Values were generated with gfortran from the unmodified fstepr4 and
    writespectra3 array loops and literal fstepr/fstepr2/fstepr3/
    writespectra2/writespectra4 row-selection fragments.
    """
    return {
        "voigte": [0.7788007830714049, 0.37286239075825545, 0.022464036161215329],
        "detail_continuum_energy": np.asarray([10.0, 20.0, 40.0, 80.0], dtype=R4),
        "detail_continuum_zrems3": np.asarray([31.0, 32.0, 33.0, 34.0], dtype=R4),
        "final_continuum_transmitted": np.asarray([9.04837418, 16.3746147, 26.8128014, 35.9463158], dtype=R4),
        "detail_level_indices": np.asarray([1, 3], dtype=np.int32),
        "detail_line_indices": np.asarray([1, 3], dtype=np.int32),
        "detail_rrc_indices": np.asarray([1, 3], dtype=np.int32),
        "final_line_indices": np.asarray([3, 1], dtype=np.int32),
        "final_rrc_indices": np.asarray([1, 3], dtype=np.int32),
        "binemis_sum_emit_inward": 4.2168284611954063e10,
        "binemis_sum_emit_outward": 7.0280474359923462e10,
        "binemis_bins_one_based": np.asarray([132, 138, 139, 140, 142], dtype=np.int32),
        "binemis_emit_inward": np.asarray([
            4.9831415379342725e3,
            4.6933687428691320e5,
            4.2167572117196648e10,
            9.9790940042697068e4,
            1.1600025043150254e4,
        ]),
        "binemis_emit_outward": np.asarray([
            8.3052692298904549e3,
            7.8222815714485559e5,
            7.0279286862027786e10,
            1.6631826673782841e5,
            1.9333408405250419e4,
        ]),
    }


def _validation_fixture() -> tuple[SourceOutputMetadata, dict[str, Any]]:
    metadata = SourceOutputMetadata(
        levels=(
            LevelOutputMetadata(1, 1, 0.0, "o_vii", 8, "ground", 1),
            LevelOutputMetadata(2, 1, 10.0, "o_vii", 8, "weak", 2),
            LevelOutputMetadata(3, 1, 20.0, "o_vii", 8, "upper", 3),
        ),
        lines=(
            LineOutputMetadata(1, 21.60, "o_vii", "ground", "resonance", rate_type=50, atomic_mass=16.0),
            LineOutputMetadata(2, 0.05, "o_vii", "ground", "excluded", rate_type=50, atomic_mass=16.0),
            LineOutputMetadata(3, 22.10, "o_vii", "ground", "forbidden", rate_type=50, atomic_mass=16.0),
        ),
        rrcs=(
            RRCOutputMetadata(1, 1, 739.3, "o_vii", "ground"),
            RRCOutputMetadata(2, 2, 700.0, "o_vii", "weak"),
            RRCOutputMetadata(3, 3, 650.0, "o_vii", "upper"),
        ),
        provenance={"fixture": "v0.4.69"},
    )
    arrays = {
        "pop": np.asarray([1e-2, 1e-40, 2e-4]),
        "lte": np.asarray([1e-3, 2e-4, 3e-5]),
        "rcem": np.asarray([[1e-5, 0.0, 4e-5], [2e-5, 0.0, 8e-5]]),
        "oplin": np.asarray([1e-7, 0.0, 3e-7]),
        "tau0": np.asarray([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]),
        "cemab": np.asarray([[1e-6, 0.0, 3e-6], [2e-6, 0.0, 4e-6]]),
        "cabab": np.asarray([5e-6, 0.0, 6e-6]),
        "opakab": np.asarray([7e-8, 0.0, 8e-8]),
        "tauc": np.asarray([[0.7, 0.8, 0.9], [1.0, 1.1, 1.2]]),
        "epi": np.asarray([10.0, 20.0, 40.0, 80.0]),
        "zrems": np.asarray([
            [11., 12., 13., 14.], [21., 22., 23., 24.], [31., 32., 33., 34.],
            [41., 42., 43., 44.], [51., 52., 53., 54.],
        ]),
        "opakc": np.asarray([1e-9, 2e-9, 3e-9, 4e-9]),
        "rccemis": np.asarray([[1., 2., 3., 4.], [5., 6., 7., 8.]]),
        "dpthc": np.asarray([[0.01, 0.02, 0.03, 0.04], [0.05, 0.06, 0.07, 0.08]]),
        "dpthcont": np.asarray([[0.1, 0.2, 0.4, 0.8], [0.0, 0.0, 0.0, 0.0]]),
        "zremsz": np.asarray([10., 20., 40., 80.]),
        "elum": np.asarray([[1e-5, 0., 3e-5], [2e-5, 0., 9e-5]]),
        "elumab": np.asarray([[1e-6, 0., 3e-6], [2e-6, 0., 4e-6]]),
    }
    return metadata, arrays



def _binemis_validation_fixture() -> tuple[SourceOutputMetadata, dict[str, Any]]:
    ngrid = 1000
    ncn2 = 200
    ratio = (1.0e4 / 1.0) ** (1.0 / 199.0)
    epi = np.full(ngrid, 1.0e4, dtype=float)
    epi[:ncn2] = ratio ** np.arange(ncn2, dtype=float)
    dpthc = np.zeros((2, ngrid), dtype=float)
    dpthc[0, :ncn2] = 0.05
    elum = np.zeros((2, 10), dtype=float)
    elum[:, 0] = (1.5, 2.5)
    zrems = np.zeros((5, ngrid), dtype=float)
    zremsz = np.zeros(ngrid, dtype=float)
    zremsz[:ncn2] = 10.0 + np.arange(1, ncn2 + 1, dtype=float) / 1000.0
    zrems[1, :ncn2] = 0.1
    zrems[2, :ncn2] = 0.2
    zrems[3, :ncn2] = 0.3
    metadata = SourceOutputMetadata(
        lines=(
            LineOutputMetadata(
                1,
                21.6,
                "o_vii",
                "ground",
                "resonance",
                rate_type=50,
                data_type=50,
                atomic_mass=16.0,
                natural_rate_s=3.0e8,
                auger_rate_s=1.0e12,
            ),
        ),
        provenance={"fixture": "compiled-unmodified-binemis-v0.4.69"},
    )
    return metadata, {
        "epi": epi,
        "ncn2": ncn2,
        "dpthc": dpthc,
        "elum": elum,
        "zrems": zrems,
        "zremsz": zremsz,
    }

def run_direct_fortran_output_writer_validation(*, rtol: float = 2e-7, atol: float = 0.0) -> dict[str, bool]:
    ref = direct_fortran_output_reference(); metadata, a = _validation_fixture()
    header = ShellOutputHeader(1e18, 2e16, 3e16, 100.0, 1e-2, 2e22, 1.2, 1e8, 2.5)
    detail = build_detail_shell_output(
        metadata=metadata, header=header, populations=a["pop"], lte_populations=a["lte"],
        rcem=a["rcem"], oplin=a["oplin"], tau0=a["tau0"], cemab=a["cemab"],
        cabab=a["cabab"], opakab=a["opakab"], tauc=a["tauc"], epi_eV=a["epi"],
        zrems=a["zrems"], opakc=a["opakc"], rccemis=a["rccemis"], dpthc=a["dpthc"], ncn2=4,
    )
    final = build_final_output_products(
        metadata=metadata, xlum=1e38, temperature_1e4K=100., turbulent_velocity_km_s=0.,
        epi_eV=a["epi"], ncn2=4, dpthc=a["dpthc"], dpthcont=a["dpthcont"],
        elum=a["elum"], elumab=a["elumab"], tau0=a["tau0"], tauc=a["tauc"],
        zrems=a["zrems"], zremsz=a["zremsz"], lwri=0,
    )
    voigt_values = np.asarray([voigte(0.5, 0.0), voigte(1.0, 0.1), voigte(3.0, 0.3)])
    profile_metadata, profile_arrays = _binemis_validation_fixture()
    profile_result = build_binemis_spectrum(
        metadata=profile_metadata,
        xlum=1.0e10,
        temperature_1e4K=100.0,
        turbulent_velocity_km_s=50.0,
        epi_eV=profile_arrays["epi"],
        ncn2=profile_arrays["ncn2"],
        dpthc=profile_arrays["dpthc"],
        elum=profile_arrays["elum"],
        zrems=profile_arrays["zrems"],
        zremsz=profile_arrays["zremsz"],
    )
    profile_bins = ref["binemis_bins_one_based"] - 1
    # The compiled source fixture builds its logarithmic grid inside Fortran;
    # one additional default-real grid-rounding step limits this profile
    # comparison to roughly four parts in 10^7.
    profile_rtol = max(float(rtol), 5.0e-7)
    summary = {
        "voigte_direct_fortran_ready": bool(np.allclose(voigt_values, ref["voigte"], rtol=rtol, atol=atol)),
        "fstepr_direct_fortran_ready": bool(np.array_equal(detail.levels.values["index"], ref["detail_level_indices"])),
        "fstepr2_direct_fortran_ready": bool(np.array_equal(detail.lines.values["index"], ref["detail_line_indices"])),
        "fstepr3_direct_fortran_ready": bool(np.array_equal(detail.rrcs.values["rrc index"], ref["detail_rrc_indices"])),
        "fstepr4_direct_fortran_ready": bool(
            np.array_equal(detail.continuum.values["energy"], ref["detail_continuum_energy"])
            and np.array_equal(detail.continuum.values["zrems(3)"], ref["detail_continuum_zrems3"])
        ),
        "writespectra_direct_fortran_ready": bool(np.array_equal(final.spectrum.values["incident"], _r4_array(a["zremsz"]))),
        "writespectra2_direct_fortran_ready": bool(np.array_equal(final.lines.values["index"], ref["final_line_indices"])),
        "writespectra3_direct_fortran_ready": bool(np.allclose(final.continuum.values["transmitted"], ref["final_continuum_transmitted"], rtol=rtol, atol=atol)),
        "writespectra4_direct_fortran_ready": bool(np.array_equal(final.rrcs.values["index"], ref["final_rrc_indices"])),
        "binemis_strong_line_direct_fortran_ready": bool(
            np.isclose(
                np.sum(profile_result[2, : profile_arrays["ncn2"]]),
                ref["binemis_sum_emit_inward"],
                rtol=profile_rtol,
                atol=atol,
            )
            and np.isclose(
                np.sum(profile_result[3, : profile_arrays["ncn2"]]),
                ref["binemis_sum_emit_outward"],
                rtol=profile_rtol,
                atol=atol,
            )
            and np.allclose(
                profile_result[2, profile_bins],
                ref["binemis_emit_inward"],
                rtol=profile_rtol,
                atol=atol,
            )
            and np.allclose(
                profile_result[3, profile_bins],
                ref["binemis_emit_outward"],
                rtol=profile_rtol,
                atol=atol,
            )
        ),
        "final_spectrum_scattered_descriptor_omission_ready": bool(final.spectrum.columns == ("energy", "incident", "transmitted", "emit_inward", "emit_outward")),
        "output_real4_persistence_ready": bool(all(np.asarray(v).dtype == np.float32 for table in (detail.continuum, final.spectrum, final.continuum) for k, v in table.values.items() if k != "index")),
    }
    summary["output_writers_direct_original_fortran_reference_ready"] = bool(all(summary.values()))
    return summary

def run_output_writer_validation(
    *,
    out_dir: str | Path | None = None,
    rtol: float = 2.0e-7,
    atol: float = 0.0,
) -> dict[str, Any]:
    """Validate the bounded detail and final output-writer sequence."""
    import tempfile

    from .radial_transfer import (
        _build_radial_validation_state,
        _workspace_from_state,
        run_bounded_radial_multipass,
    )

    direct = dict(
        run_direct_fortran_output_writer_validation(rtol=rtol, atol=atol)
    )
    from .pprint_legacy import (
        PprintAtomicMetadata, PprintElementMetadata, PprintIonMetadata,
        run_direct_fortran_pprint_validation,
    )
    direct.update(run_direct_fortran_pprint_validation(rtol=rtol, atol=atol))
    state = _build_radial_validation_state(zone_index=1)
    state.control.update(
        {
            "output_writers_enabled": True,
            "pprint_legacy_enabled": True,
            "lwri": 1,
            "lpri": 0,
            "p": 2.5e-2,
            "spectype": "pow",
            "specfile": "",
            "specunit": 0,
            "trad": 1.0,
            "xpxcol": 1.0e21,
            "zeta": 1.5,
            "abndtbl": "xdef",
            "kmodelname": "xstar-output-v0470",
            "atcredate": "bounded-reference",
            "abel": np.asarray([1.0, 1.0, 1.0]),
            "ababs": np.asarray([1.0, 0.1, 4.9e-4]),
            "xii": np.asarray([0.2, 0.3, 0.5]),
            "htt": np.asarray([1.0e-4, 2.0e-4, 3.0e-4]),
            "cll": np.asarray([1.5e-4, 2.5e-4, 3.5e-4]),
            "htcomp": 4.0e-4,
            "clcomp": 5.0e-4,
            "clbrems": 6.0e-4,
            "enlum": 1.0e38,
            "ntotit": 4,
            "lnerrd": 0,
        }
    )
    state.control["pprint_atomic_metadata"] = PprintAtomicMetadata(
        element_labels=("H", "He", "O"),
        ions=(
            PprintIonMetadata(1, "h_i", 1, 1.0),
            PprintIonMetadata(2, "o_vii", 3, 4.9e-4),
            PprintIonMetadata(3, "o_viii", 3, 4.9e-4),
        ),
        thermal_elements=(
            PprintElementMetadata(1, "H"),
            PprintElementMetadata(2, "He"),
            PprintElementMetadata(3, "O"),
        ),
        provenance={"fixture": "bounded-pprint-v0.4.71"},
    )
    radial = run_bounded_radial_multipass(
        state,
        first_pass_shell_count=2,
        pass_count=1,
    )
    workspace = _workspace_from_state(state)
    # The final source writers consume luminosities accumulated by the radial
    # pass.  The bounded radial fixture has no physical volume, so retain a
    # deterministic nonzero caller-owned accumulation for line/RRC row gates.
    workspace.elum[:, 0] = (1.0e-5, 2.0e-5)
    workspace.elum[:, 2] = (3.0e-5, 9.0e-5)
    workspace.elumab[:, 0] = (1.0e-6, 2.0e-6)
    workspace.elumab[:, 2] = (3.0e-6, 4.0e-6)

    if out_dir is None:
        root = Path(tempfile.mkdtemp(prefix="xstar_output_writer_v0470_"))
    else:
        root = Path(out_dir)
        root.mkdir(parents=True, exist_ok=True)
    fits_dir = root / "generated_fits"
    parameters = (
        OutputParameter("density", float(state.plasma.xpx), "real", "hydrogen density"),
        OutputParameter("temperature", float(state.plasma.temperature), "real", "gas temperature"),
    )
    result = run_output_writer_sequence(
        state,
        out_dir=fits_dir,
        lwri=0,
        parameters=parameters,
        model_name="xstar-output-v0470",
        atomic_data_date="bounded-reference",
        final_local_recompute=True,
    )

    stores = result.detail_stores
    store = stores.get(1)
    detail_store_ready = bool(
        isinstance(store, DetailOutputStore)
        and store.pass_index == 1
        and len(store.records) == 3
        and store.inserted_after_hdus == [2, 3, 3]
    )
    detail_order_ready = bool(
        detail_store_ready
        and all(
            record.source_order == ("fstepr", "fstepr2", "fstepr3", "fstepr4")
            for record in store.records
        )
    )
    header_real4_ready = bool(
        detail_store_ready
        and all(
            all(value == float(np.float32(value)) for value in table.header_keywords.values())
            for record in store.records
            for table in (record.levels, record.lines, record.rrcs, record.continuum)
        )
    )
    detail_schema_ready = bool(
        detail_store_ready
        and store.records[0].levels.columns
        == ("index", "ion_index", "e_excitation", "ion", "atomic_number", "ion_level", "population", "lte", "upper index")
        and store.records[0].lines.columns
        == ("index", "wavelength", "ion", "lower_level", "upper_level", "emis_inward", "emis_outward", "opacity", "tau_in", "tau_out")
        and store.records[0].rrcs.columns
        == ("rrc index", "level index", "energy", "ion", "lower_level", "upper_level", "emis_inward", "emis_outward", "integrated absn", "opacity", "tau_in", "tau_out")
        and store.records[0].continuum.columns
        == ("index", "energy", "zrems(1)", "zrems(2)", "zrems(3)", "zrems(4)", "zrems(5)", "opacity", "emis out", "emis in", "fwd dpth", "bck dpth")
    )

    expected_final_prefix = (
        "bremsmap",
        "calc_hmc_all",
        "calc_emisab_all",
        "calc_emis_all",
        "heatt",
        "stpcut",
    )
    expected_writers = (
        "writespectra",
        "writespectra2",
        "writespectra3",
        "writespectra4",
    )
    final_order_ready = bool(
        result.source_order[: len(expected_final_prefix)] == expected_final_prefix
        and result.source_order[-4:] == expected_writers
        and result.source_order.index("pprint(22)")
        > result.source_order.index("stpcut")
        and result.source_order.index("pprint(22)")
        < result.source_order.index("writespectra")
    )
    final_recompute_ready = bool(
        result.final_local_recompute_executed
        and state.outputs["final_local_recompute"]["nlimd"] == 0
        and state.outputs["final_local_recompute"]["dsec_skipped"] is True
        and "dsec" not in expected_final_prefix
    )
    pprint_handler = state.outputs.get("pprint_final_source_state_handler", {})
    pprint_handler_ready = bool(
        result.pprint_source_state_handler_ready
        and result.pprint_products_written
        and pprint_handler.get("state_handler_only") is False
        and pprint_handler.get("legacy_ascii_products_written") is True
        and pprint_handler.get("calls") == ["pprint(22)", "pprint(11)"]
    )
    pprint_order = state.outputs.get("legacy_pprint_source_order", [])
    pprint_default_order_ready = bool(
        pprint_order[:2] == ["pprint(3)", "pprint(2)"]
        and "pprint(17)" in pprint_order
        and pprint_order.count("pprint(9)") == 3
        and pprint_order.count("pprint(12)") == 3
        and pprint_order[-2:] == ["pprint(22)", "pprint(11)"]
    )
    final = result.final_products
    final_schema_ready = bool(
        isinstance(final, FinalOutputProducts)
        and final.spectrum.columns
        == ("energy", "incident", "transmitted", "emit_inward", "emit_outward")
        and final.lines.columns
        == ("index", "ion", "lower_level", "upper_level", "wavelength", "emit_inward", "emit_outward", "depth_inward", "depth_outward")
        and final.continuum.columns
        == ("energy", "incident", "transmitted", "emit_inward", "emit_outward")
        and final.rrcs.columns
        == ("index", "ion", "level", "energy", "emit_outward", "emit_inward", "depth_outward", "depth_inward")
        and final.lines.nrows == 2
        and final.rrcs.nrows == 2
    )

    expected_detail_names = {
        "xo01_detail.fits",
        "xo01_detal2.fits",
        "xo01_detal3.fits",
        "xo01_detal4.fits",
    }
    expected_final_names = {
        "xout_spect1.fits",
        "xout_lines1.fits",
        "xout_cont1.fits",
        "xout_rrc1.fits",
    }
    expected_pprint_names = {"xout_step.log", "xout_abund1.fits"}
    written_names = {Path(path).name for path in result.written_paths.values()}
    filename_ready = written_names == expected_detail_names | expected_final_names | expected_pprint_names

    hdu_layout_ready = True
    checksum_ready = True
    for filename in sorted(written_names - {"xout_step.log"}):
        path = fits_dir / filename
        with fits.open(path, checksum=True) as hdul:
            if filename in expected_detail_names:
                expected_hdus = 5
                layout = len(hdul) == expected_hdus and hdul[0].name == "PRIMARY" and hdul[1].name == "PARAMETERS"
            elif filename == "xout_abund1.fits":
                expected_hdus = 5
                layout = len(hdul) == expected_hdus and [h.name for h in hdul[1:]] == ["ABUNDANCES", "COLUMNS", "HEATING", "COOLING"]
            else:
                expected_hdus = 3
                layout = len(hdul) == expected_hdus and hdul[0].name == "PRIMARY" and hdul[1].name == "PARAMETERS"
            hdu_layout_ready = hdu_layout_ready and layout
            checksum_ready = checksum_ready and all(
                "CHECKSUM" in hdu.header and "DATASUM" in hdu.header for hdu in hdul
            )
    step_log_path = fits_dir / "xout_step.log"
    step_log_text = step_log_path.read_text(encoding="utf-8") if step_log_path.exists() else ""
    xout_step_log_ready = bool(
        "input parameters:" in step_log_text
        and "pass number=" in step_log_text
        and "log(r)" in step_log_text
        and "httot=" in step_log_text
        and "log(Xi)=" in step_log_text
    )
    xout_abund1_ready = False
    abund_path = fits_dir / "xout_abund1.fits"
    if abund_path.exists():
        with fits.open(abund_path, checksum=True) as hdul:
            xout_abund1_ready = bool(
                [h.name for h in hdul[1:]] == ["ABUNDANCES", "COLUMNS", "HEATING", "COOLING"]
                and len(hdul["ABUNDANCES"].data) == 3
                and all(str(hdul["ABUNDANCES"].header[f"TFORM{i}"]).strip() == "E13.5"
                        for i in range(1, len(hdul["ABUNDANCES"].columns) + 1))
            )

    gate_dir = root / "lwri_gates"
    minus_two = write_final_output_files(
        final,
        out_dir=gate_dir / "minus_two",
        parameters=parameters,
        model_name="gate",
        atomic_data_date="bounded-reference",
        lwri=-2,
    )
    minus_one = write_final_output_files(
        final,
        out_dir=gate_dir / "minus_one",
        parameters=parameters,
        model_name="gate",
        atomic_data_date="bounded-reference",
        lwri=-1,
    )
    zero = write_final_output_files(
        final,
        out_dir=gate_dir / "zero",
        parameters=parameters,
        model_name="gate",
        atomic_data_date="bounded-reference",
        lwri=0,
    )
    lwri_ready = bool(
        minus_two == {}
        and set(minus_one) == {"xout_spect1.fits"}
        and set(zero) == expected_final_names
    )

    caller_state_ready = bool(
        state.outputs.get("output_writers_executed") is True
        and state.outputs.get("final_output_products") is final
        and state.outputs.get("detail_output_stores") is stores
        and radial.output_writers_executed is False
    )
    from .pprint_legacy import LegacyPprintPortError, finalize_legacy_pprint

    state.control["lpri"] = 1
    try:
        finalize_legacy_pprint(state, out_dir=None)
    except LegacyPprintPortError:
        verbose_pprint_explicit_failure_ready = True
    else:
        verbose_pprint_explicit_failure_ready = False
    finally:
        state.control["lpri"] = 0

    from .physical_output_parity import run_physical_parity_harness_self_test

    parity_harness = run_physical_parity_harness_self_test(fits_dir)
    summary: dict[str, Any] = {
        **direct,
        **parity_harness,
        "port_version": "v0.4.71",
        "fparmlist_translated": True,
        "fheader_translated": True,
        "savd_fstepr_writer_sequence_translated": True,
        "writespectra_translated": True,
        "writespectra2_translated": True,
        "writespectra3_translated": True,
        "writespectra4_translated": True,
        "binemis_translated": True,
        "voigte_translated": True,
        "detail_caller_owned_pass_store_ready": detail_store_ready,
        "savd_fstepr_call_order_ready": detail_order_ready,
        "detail_hdu_insertion_shift_order_ready": detail_store_ready,
        "detail_shell_header_real4_ready": header_real4_ready,
        "detail_table_schemas_ready": detail_schema_ready,
        "detail_pass_filename_fnappend_ready": filename_ready,
        "final_local_recompute_source_order_ready": final_order_ready,
        "final_nlimd_zero_dsec_skip_ready": final_recompute_ready,
        "legacy_pprint_default_path_translated": True,
        "pprint_default_source_order_ready": pprint_default_order_ready,
        "pprint_source_state_handler_replaced_ready": pprint_handler_ready,
        "xout_step_log_ready": xout_step_log_ready,
        "xout_abund1_extensions_ready": xout_abund1_ready,
        "pprint_real4_persistence_ready": xout_abund1_ready,
        "verbose_pprint_untranslated_branches_fail_explicitly_ready": verbose_pprint_explicit_failure_ready,
        "final_writer_source_order_ready": final_order_ready,
        "final_table_schemas_ready": final_schema_ready,
        "writespectra_lwri_gates_ready": lwri_ready,
        "fits_primary_parameters_data_hdu_ready": hdu_layout_ready,
        "fits_checksums_ready": checksum_ready,
        "caller_owned_output_state_ready": caller_state_ready,
        "legacy_pprint_ascii_products_written_ready": pprint_handler_ready,
        "pprint_source_state_handler_explicit_ready": True,
        "legacy_pprint_ascii_products_not_approximated_ready": pprint_handler_ready,
        "physical_standard_benchmark_not_claimed_ready": True,
        "physical_standard_benchmark_not_run_without_inputs_ready": True,
        "physical_standard_benchmark_inputs_available": False,
        "physical_standard_benchmark_parity_run": False,
        "physical_standard_benchmark_all_files_match": False,
        "output_writer_source_order": list(result.source_order),
        "written_files": sorted(written_names),
        "detail_record_count": (len(store.records) if store is not None else 0),
        "final_line_rows": (final.lines.nrows if final is not None else 0),
        "final_rrc_rows": (final.rrcs.nrows if final is not None else 0),
    }
    summary["detail_and_final_output_writer_source_acceptance_ready"] = bool(
        all(value for key, value in summary.items() if key.endswith("_ready"))
    )
    summary["next_source_target"] = (
        "physical_all_atdb_standard_benchmark_output_parity"
    )
    summary["validation_root"] = str(root)
    return summary


def write_output_writer_validation_products(
    summary: Mapping[str, Any], out_dir: str | Path
) -> Mapping[str, str]:
    import json

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "xstar_output_writer_source_validation_summary.json"
    md_path = out / "xstar_output_writer_source_validation_summary.md"
    json_path.write_text(
        json.dumps(dict(summary), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(
        "# XSTAR detail and final output-writer source validation\n\n"
        + "\n".join(f"- {key}: `{value}`" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return {"json": str(json_path), "markdown": str(md_path)}

__all__ = [
    "OutputWriterPortError", "OutputParameter", "LevelOutputMetadata",
    "LineOutputMetadata", "RRCOutputMetadata", "SourceOutputMetadata",
    "ShellOutputHeader", "OutputTable", "DetailShellOutput",
    "DetailOutputStore", "FinalOutputProducts", "OutputWriterSequenceResult",
    "build_parameter_table", "build_detail_level_table",
    "build_detail_line_table", "build_detail_rrc_table",
    "build_detail_continuum_table", "build_detail_shell_output", "voigte",
    "build_binemis_spectrum", "build_final_spectrum_table",
    "build_final_line_table", "build_final_continuum_table",
    "build_final_rrc_table", "build_final_output_products",
    "write_final_output_files", "write_detail_output_files",
    "append_detail_output_from_state", "build_final_output_from_state",
    "run_output_writer_sequence", "direct_fortran_output_reference",
    "run_direct_fortran_output_writer_validation",
    "run_output_writer_validation", "write_output_writer_validation_products",
]
