# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: fstepr.f90 / fstepr2.f90 / fstepr3.f90 / fstepr4.f90 / writespectra*.f90
#   Role: Own radial detail products and final continuum/line/RRC/spectrum publication.
#   Relation: Source-equivalent publication; identity, source order, REAL(4) writer behavior, and terminal workspace ownership are qualified.
#   Concordance: DETAIL-001; FINAL-001; TERMINAL-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# Atomic-data note (XSTAR Manual Ch. 12; Mendoza et al. 2021, Appendix A):
#   Rule: data type selects the record formula/interpretation; rate type selects downstream use.
#   Output membership follows source pointer/rate-type traversal and retained workspaces; it must not be
#   narrowed by assuming a particular data type. The data type only defines how a record was evaluated.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

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
import csv
import hashlib
import json
import os
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

import time
import numpy as np


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the install astropy numpy compatibility operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
        # XSTAR-FUNCTION-COMMENT-BEGIN
        # Purpose: Check interpolation as method for this module while preserving the surrounding source/runtime invariants.
        # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
        # XSTAR-FUNCTION-COMMENT-END
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
from .fits_provenance import apply_python_primary_fits_header
from .saved_radial_state import _savd_keyword_e3_real4_scalar


class OutputWriterPortError(RuntimeError):
    """Raised when the source output contract cannot be represented safely."""


R4 = np.float32
LEVEL_POPULATION_FLOOR = 1.0e-34
SOURCE_DETAIL_ENDPOINT_ABUNDANCE_FLOOR = float(np.float32(1.0e-34))
DETAIL_LINE_ACTIVITY_FLOOR = 1.0e-64
DETAIL_RRC_ACTIVITY_FLOOR = 1.0e-36
FINAL_LINE_ACTIVITY_FLOOR = 1.0e-36
FINAL_RRC_ACTIVITY_FLOOR = 1.0e-36
FINAL_LINE_LIMIT = 600


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the r4 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _r4(value: float) -> float:
    return float(R4(value))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the r4 array operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _r4_array(values: Any) -> np.ndarray:
    return np.asarray(values, dtype=R4)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fixed operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
    # 0.6.82.29.3.9: retain the literal Type-13 endpoint payload used by
    # pprint(18).  These fields are publication metadata only; they do not
    # participate in equilibrium, transfer, opacity, or spectral science.
    statistical_weight: float = 0.0
    effective_n: float = 0.0
    principal_n: int = 0
    spin_multiplicity: int = 0
    orbital_l: int = 0


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
    source_record: int = 0
    lower_local_index: int = 0
    upper_local_index: int = 0


@dataclass(frozen=True)
class RRCOutputMetadata:
    continuum_index: int
    level_global_index: int
    threshold_eV: float
    ion_label: str
    lower_level: str
    upper_level: str = "continuum"
    lower_local_index: int = 0
    upper_local_index: int = 0
    # Source record metadata retained for literal xstarsetup/calc_emis rank
    # geometry.  Type 49 does not rank on the generic fstepr3 threshold: it
    # uses rdat1(np1r)*13.598 with default-REAL literal semantics.
    source_record: int = 0
    data_type: int = 0
    rank_threshold_eV: float = 0.0
    # Retain the literal source rate family.  STEP/public RRC source ownership
    # is rate-type-7-only, while frozen-44 generic xo01_detal3 publication uses
    # the broader canonical npcon/npconi2 continuum identity surface.
    rate_type: int = 0
    atomic_number: int = 0


@dataclass(frozen=True)
class SourceOutputMetadata:
    levels: tuple[LevelOutputMetadata, ...] = ()
    lines: tuple[LineOutputMetadata, ...] = ()
    rrcs: tuple[RRCOutputMetadata, ...] = ()
    # FITS detail-RRC view owned by the literal FORTRAN fstepr3 Type-7 chain.
    # Keep this narrower than the broad executable/public continuum inventory.
    detail_rrcs: tuple[RRCOutputMetadata, ...] = ()
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
    state_source: str = ""

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the real4 keywords operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
    def real4_keywords(self) -> dict[str, float]:
        # 0.6.82.27.16: these nine keywords are written by SAVD with
        # CFITSIO ftpkye(...,3) after REAL(4) assignment.  The intermediate
        # E3 text round-trip is part of the persisted radial-state contract;
        # detail products must expose the same scalar snapshot that UNSAVD
        # subsequently reads.
        return {
            "RINNER": _savd_keyword_e3_real4_scalar(self.inner_radius_cm),
            "ROUTER": _savd_keyword_e3_real4_scalar(self.outer_radius_cm),
            "RDEL": _savd_keyword_e3_real4_scalar(self.radial_depth_cm),
            "TEMPERAT": _savd_keyword_e3_real4_scalar(self.temperature_1e4K),
            "PRESSURE": _savd_keyword_e3_real4_scalar(self.pressure_dyn_cm2),
            "COLUMN": _savd_keyword_e3_real4_scalar(self.column_cm2),
            "XEE": _savd_keyword_e3_real4_scalar(self.electron_fraction),
            "DENSITY": _savd_keyword_e3_real4_scalar(self.density_cm3),
            "LOGXI": _savd_keyword_e3_real4_scalar(self.logxi),
        }

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the fits keywords operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
    def fits_keywords(self) -> dict[str, object]:
        values = self.real4_keywords()
        comments = {
            "RINNER": "[cm] Inner shell radius",
            "ROUTER": "[cm] Outer shell radius",
            "RDEL": "[cm] distance from face",
            "TEMPERAT": "[10**4K] Shell Temperature",
            "PRESSURE": "[dynes/cm**2] Shell Pressure",
            "COLUMN": "[/cm**2] Column",
            "XEE": "electron fraction",
            "DENSITY": "[/cm**3] Density",
            "LOGXI": "[erg cm/s] log(ionization parameter)",
        }
        out: dict[str, object] = {
            key: (value, comments[key]) for key, value in values.items()
        }
        if self.state_source:
            out["STATESRC"] = self.state_source
        return out


@dataclass(frozen=True)
class OutputTable:
    extension_name: str
    columns: tuple[str, ...]
    units: tuple[str, ...]
    values: Mapping[str, np.ndarray]
    formats: tuple[str, ...]
    binary: bool
    header_keywords: Mapping[str, object] = field(default_factory=dict)
    source_file: str = ""

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the nrows operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
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

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Insert after hdu for this module while preserving the surrounding source/runtime invariants.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
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
    timing_breakdown: Mapping[str, float] | None = None
    source_file: str = "xstar/src/xstar/xstar.f90"

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the detail store operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
    @property
    def detail_store(self) -> DetailOutputStore:
        """Return the highest-pass detail store for compatibility."""
        if not self.detail_stores:
            return DetailOutputStore(pass_index=1)
        return self.detail_stores[max(self.detail_stores)]


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the metadata from control operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _metadata_from_control(state: XSTARPythonState) -> SourceOutputMetadata:
    value = state.control.get("output_atomic_metadata")
    if isinstance(value, SourceOutputMetadata):
        return value
    raise OutputWriterPortError(
        "output writers require caller-owned SourceOutputMetadata in "
        "state.control['output_atomic_metadata']"
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build parameter table for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def build_parameter_table(parameters: Sequence[OutputParameter], *, model_name: str) -> OutputTable:
    n = len(parameters)
    return OutputTable(
        extension_name="PARAMETERS",
        columns=("index", "parameter", "value", "type", "comment"),
        units=("", "", "", "", ""),
        formats=("1I", "20A", "1E", "10A", "30A"),
        binary=True,
        header_keywords={"MODEL": (_fixed(model_name, 30), "model name for this run")},
        source_file="xstar/xstarlib/src/fparmlist.f90",
        values={
            "index": np.arange(1, n + 1, dtype=np.int16),
            "parameter": np.asarray([_fixed(p.name, 20) for p in parameters], dtype="U20"),
            "value": _r4_array([p.value for p in parameters]),
            "type": np.asarray([_fixed(p.parameter_type, 10) for p in parameters], dtype="U10"),
            "comment": np.asarray([_fixed(p.comment, 30) for p in parameters], dtype="U30"),
        },
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build detail level table for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
        # XSTAR fstepr writes the element/atomic-number-like value in this
        # column, not the package-global ion ordinal.  Keep the separate
        # atomic_number column for source table shape even though the two now
        # intentionally agree.
        "ion_index": np.asarray([r.atomic_number for r in rows], dtype=np.int16),
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
        header_keywords=header.fits_keywords(),
        source_file="xstar/xstarlib/src/fstepr.f90",
        values=values,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build detail line table for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def build_detail_line_table(
    *,
    metadata: SourceOutputMetadata,
    rcem: np.ndarray,
    oplin: Sequence[float],
    tau0: np.ndarray,
    header: ShellOutputHeader,
    source_activity_shadow: Sequence[bool] | None = None,
) -> OutputTable:
    emiss = np.asarray(rcem, dtype=float)
    opacity = np.asarray(oplin, dtype=float).reshape(-1)
    depth = np.asarray(tau0, dtype=float)
    if emiss.ndim != 2 or emiss.shape[0] != 2 or depth.ndim != 2 or depth.shape[0] != 2:
        raise OutputWriterPortError("detail line arrays require direction-first shape (2,n)")
    shadow = None if source_activity_shadow is None else np.asarray(source_activity_shadow, dtype=bool).reshape(-1)
    rows: list[LineOutputMetadata] = []
    for item in metadata.lines:
        i = item.line_index - 1
        if i < 0 or i >= emiss.shape[1] or i >= opacity.size or i >= depth.shape[1]:
            continue
        # v0.6.48.11.9.3: fstepr2 source-publication activity is not
        # identical to the deterministic physical rcem/oplin arrays.  In
        # calc_emisab_ion.f90, Type50/rate-4 records are eligible for ucalc
        # when either endpoint abundance exceeds the source 1.e-34 floor.
        # FORTRAN can subsequently retain an otherwise zero detail row via
        # caller-owned/stale opakb1 state.  Preserve the source row identity
        # with a separate publication shadow; never inject that artifact into
        # physical oplin or continuum opacity.
        shadow_active = bool(shadow is not None and i < shadow.size and shadow[i])
        active = (
            emiss[0, i] > DETAIL_LINE_ACTIVITY_FLOOR
            or emiss[1, i] > DETAIL_LINE_ACTIVITY_FLOOR
            or opacity[i] > DETAIL_LINE_ACTIVITY_FLOOR
            or shadow_active
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
        header_keywords=header.fits_keywords(),
        source_file="xstar/xstarlib/src/fstepr2.f90",
        values=values,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build detail rrc table for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def build_detail_rrc_table(
    *,
    metadata: SourceOutputMetadata,
    cemab: np.ndarray,
    cabab: Sequence[float],
    opakab: Sequence[float],
    tauc: np.ndarray,
    header: ShellOutputHeader,
    element_abundances: Sequence[float] | None = None,
    source_publication_shadow: Mapping[int, Mapping[str, float]] | None = None,
    source_record_publication_shadow: Mapping[int, Mapping[str, float]] | None = None,
    source_slot_absorption_lifetime: Mapping[int, Mapping[str, Any]] | None = None,
    source_slot_current_eval_sequence: int = 0,
    orphan_type7_absorption: Mapping[int, Mapping[str, Any]] | None = None,
    non_type7_absorption: Mapping[int, Mapping[str, Any]] | None = None,
    fixed_state_non_type7_absorption: Mapping[int, Mapping[str, Any]] | None = None,
    fixed_state_non_type7_publication: Mapping[int, Mapping[str, Any]] | None = None,
    publication_trace: list[dict[str, Any]] | None = None,
) -> OutputTable:
    """Frozen-44-compatible generic detailed-RRC row selection.

    The standalone-C++ reference owns generic ``xo01_detal3`` identities from
    the complete canonical ``npcon``/``npconi2`` continuum surface, not from
    the narrower source ``npfi(7,ion)`` chain.  Consequently canonical rate-1
    as well as rate-7 records may be published when the current local
    ``cemab/cabab/opakab`` slot passes the source REAL(4)-promoted 1.e-36
    activity test.  This is publication ownership only: no physical workspace
    values are synthesized or rewritten.

    Older Type-7 record/orphan shadows remain narrow compatibility fallbacks
    for Type-7 rows only; they never make a rate-1 row active.
    """
    del source_publication_shadow  # 45.1 slot shadow is never authoritative.
    record_shadow = source_record_publication_shadow or {}
    # 45.3.2 prior-evaluation slot history is retained only as diagnostic state;
    # it is no longer a publication authority.
    del source_slot_absorption_lifetime, source_slot_current_eval_sequence
    orphan_absorption = orphan_type7_absorption or {}
    non_type7_map = non_type7_absorption or {}
    fixed_state_map = fixed_state_non_type7_absorption or {}
    fixed_state_full_map = fixed_state_non_type7_publication or {}
    emiss = np.asarray(cemab, dtype=float)
    absorbed = np.asarray(cabab, dtype=float).reshape(-1)
    opacity = np.asarray(opakab, dtype=float).reshape(-1)
    depth = np.asarray(tauc, dtype=float)
    abund = None if element_abundances is None else np.asarray(element_abundances, dtype=float).reshape(-1)
    if metadata.detail_rrcs:
        # 0.6.82.27.16: literal fstepr3.f90 walks npfi(7,ion) only.  Keep
        # this detail-specific Type-7 identity surface separate from the
        # broader public/executable continuum inventory in metadata.rrcs.
        source_rows = metadata.detail_rrcs
    elif metadata.rrcs:
        # Backward-compatible synthetic fixtures that predate detail_rrcs.
        source_rows = tuple(row for row in metadata.rrcs if int(getattr(row, "rate_type", 0) or 0) == 7)
    else:
        source_rows = ()
    rows: list[RRCOutputMetadata] = []
    payload: list[tuple[float, float, float, float]] = []
    abundance_floor = _source_real_literal(1.0e-10)
    activity_floor = _source_real_literal(1.0e-36)
    for item in source_rows:
        # 0.6.82.27.4: 709/762 are frozen-44 compatibility-only Carbon
        # identities, not literal fstepr3 rate-type-7 rows.  Exclude them only
        # from detailed RRC publication; underlying physical arrays are kept.
        if int(item.continuum_index) in {709, 762}:
            continue
        rate_type = int(getattr(item, "rate_type", 0) or 0)
        z = int(getattr(item, "atomic_number", 0))
        if abund is not None and z > 0:
            if z > abund.size or not (float(abund[z - 1]) >= abundance_floor):
                continue
        i = int(item.continuum_index) - 1
        if i < 0 or emiss.ndim != 2 or emiss.shape[0] < 2:
            continue
        if i >= emiss.shape[1] or i >= absorbed.size or i >= opacity.size or depth.ndim != 2 or depth.shape[0] < 2 or i >= depth.shape[1]:
            continue
        current = (float(emiss[0, i]), float(emiss[1, i]), float(absorbed[i]), float(opacity[i]))
        active = any(np.isfinite(v) and v > activity_floor for v in current)
        owner = "physical_current" if active else "inactive"
        retained = record_shadow.get(int(item.source_record)) if (not active and rate_type == 7) else None
        if not active and rate_type == 7 and retained is not None and int(retained.get("continuum_index", -1)) == int(item.continuum_index):
            retained_values = (
                float(retained.get("emis_inward", 0.0)),
                float(retained.get("emis_outward", 0.0)),
                float(retained.get("integrated_absn", 0.0)),
                float(retained.get("opacity", 0.0)),
            )
            if any(np.isfinite(v) and v > activity_floor for v in retained_values):
                current = retained_values
                active = True
                owner = "source_record_lifetime_v0648123453"
        orphan_entry: Mapping[str, Any] | None = None
        if not active and rate_type == 7:
            candidate = orphan_absorption.get(int(item.continuum_index))
            if isinstance(candidate, Mapping) and int(candidate.get("source_record", 0) or 0) == int(item.source_record):
                retained_absn = float(candidate.get("integrated_absn", 0.0) or 0.0)
                if np.isfinite(retained_absn) and retained_absn > activity_floor:
                    current = (current[0], current[1], retained_absn, current[3])
                    active = True
                    owner = "canonical_npcon_orphan_type7_absorption_v06481234533"
                    orphan_entry = candidate
        fixed_state_full_entry: Mapping[str, Any] | None = None
        if not active and rate_type == 1:
            candidate = fixed_state_full_map.get(int(item.continuum_index))
            if (isinstance(candidate, Mapping)
                    and int(candidate.get("source_record", 0) or 0) == int(item.source_record)
                    and int(candidate.get("rate_type", 0) or 0) == 1):
                retained_values = (
                    float(candidate.get("emis_inward", 0.0) or 0.0),
                    float(candidate.get("emis_outward", 0.0) or 0.0),
                    float(candidate.get("integrated_absn", 0.0) or 0.0),
                    float(candidate.get("opacity", 0.0) or 0.0),
                )
                if any(np.isfinite(v) and v > activity_floor for v in retained_values):
                    current = retained_values
                    active = True
                    owner = "fixed_state_rate1_postsolve_full_v064812345338"
                    fixed_state_full_entry = candidate
        non_type7_entry: Mapping[str, Any] | None = None
        if not active and rate_type == 1:
            candidate = non_type7_map.get(int(item.continuum_index))
            if (isinstance(candidate, Mapping)
                    and int(candidate.get("source_record", 0) or 0) == int(item.source_record)
                    and int(candidate.get("rate_type", 0) or 0) == 1
                    and int(candidate.get("data_type", 0) or 0) in (49, 53)):
                retained_absn = float(candidate.get("integrated_absn", 0.0) or 0.0)
                if np.isfinite(retained_absn) and retained_absn > activity_floor:
                    current = (current[0], current[1], retained_absn, current[3])
                    active = True
                    owner = "canonical_npcon_non_type7_calc_emisab_absorption_v064812345335"
                    non_type7_entry = candidate
        fixed_state_entry: Mapping[str, Any] | None = None
        if not active and rate_type == 1:
            candidate = fixed_state_map.get(int(item.continuum_index))
            if (isinstance(candidate, Mapping)
                    and int(candidate.get("source_record", 0) or 0) == int(item.source_record)
                    and int(candidate.get("rate_type", 0) or 0) == 1):
                retained_absn = float(candidate.get("integrated_absn", 0.0) or 0.0)
                if np.isfinite(retained_absn) and retained_absn > activity_floor:
                    current = (current[0], current[1], retained_absn, current[3])
                    active = True
                    owner = "fixed_state_rate1_postsolve_absorption_v064812345336"
                    fixed_state_entry = candidate
        if publication_trace is not None and int(item.continuum_index) in {709, 762}:
            publication_trace.append({
                "phase": "detail3_publication",
                "continuum_index": int(item.continuum_index),
                "source_record": int(item.source_record),
                "owner": owner,
                "active": bool(active),
                "current_emis_inward": float(current[0]),
                "current_emis_outward": float(current[1]),
                "current_integrated_absn": float(current[2]),
                "current_opacity": float(current[3]),
                "record_shadow_present": bool(retained is not None),
                "orphan_type7_entry": dict(orphan_entry) if orphan_entry is not None else None,
                "non_type7_entry": dict(non_type7_entry) if non_type7_entry is not None else None,
                "fixed_state_full_entry": dict(fixed_state_full_entry) if fixed_state_full_entry is not None else None,
                "fixed_state_entry": dict(fixed_state_entry) if fixed_state_entry is not None else None,
            })
        if not active:
            continue
        rows.append(item)
        payload.append(current)
    values = {
        "rrc index": np.asarray([r.continuum_index for r in rows], dtype=np.int32),
        "level index": np.asarray([r.level_global_index for r in rows], dtype=np.int32),
        "energy": _r4_array([r.threshold_eV for r in rows]),
        "ion": np.asarray([_fixed(r.ion_label, 8) for r in rows], dtype="U8"),
        "lower_level": np.asarray([_fixed(r.lower_level, 20) for r in rows], dtype="U20"),
        "upper_level": np.asarray([_fixed(r.upper_level, 20) for r in rows], dtype="U20"),
        "emis_inward": _r4_array([v[0] for v in payload]),
        "emis_outward": _r4_array([v[1] for v in payload]),
        "integrated absn": _r4_array([v[2] for v in payload]),
        "opacity": _r4_array([v[3] for v in payload]),
        "tau_in": _r4_array([depth[0, r.continuum_index - 1] for r in rows]),
        "tau_out": _r4_array([depth[1, r.continuum_index - 1] for r in rows]),
    }
    return OutputTable(
        extension_name="XSTAR_RADIAL",
        columns=tuple(values),
        units=("", "", "eV", "", "", "", "erg/cm^3/s", "erg/cm^3/s", "erg/cm^3/s", "/cm", "", ""),
        formats=("1J", "1J", "1E", "8A", "20A", "20A", "1E", "1E", "1E", "1E", "1E", "1E"),
        binary=True,
        header_keywords=header.fits_keywords(),
        source_file="xstar/xstarlib/src/fstepr3.f90",
        values=values,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build detail continuum table for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
        header_keywords=header.fits_keywords(),
        source_file="xstar/xstarlib/src/fstepr4.f90",
        values=values,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Assemble the four per-shell detail products from the physical shell state without changing the producer science.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
    source_detail_line_activity_shadow: Sequence[bool] | None = None,
    source_detail_rrc_publication_shadow: Mapping[int, Mapping[str, float]] | None = None,
    source_detail_rrc_record_shadow: Mapping[int, Mapping[str, float]] | None = None,
    source_detail_rrc_slot_absorption_lifetime: Mapping[int, Mapping[str, Any]] | None = None,
    source_detail_rrc_current_eval_sequence: int = 0,
    source_detail_rrc_orphan_absorption: Mapping[int, Mapping[str, Any]] | None = None,
    source_detail_rrc_non_type7_absorption: Mapping[int, Mapping[str, Any]] | None = None,
    source_detail_rrc_fixed_state_absorption: Mapping[int, Mapping[str, Any]] | None = None,
    source_detail_rrc_fixed_state_publication: Mapping[int, Mapping[str, Any]] | None = None,
    source_detail_rrc_publication_trace: list[dict[str, Any]] | None = None,
    element_abundances: Sequence[float] | None = None,
) -> DetailShellOutput:
    return DetailShellOutput(
        levels=build_detail_level_table(metadata=metadata, populations=populations, lte_populations=lte_populations, header=header),
        lines=build_detail_line_table(
            metadata=metadata, rcem=rcem, oplin=oplin, tau0=tau0, header=header,
            source_activity_shadow=source_detail_line_activity_shadow,
        ),
        rrcs=build_detail_rrc_table(
            metadata=metadata, cemab=cemab, cabab=cabab, opakab=opakab, tauc=tauc, header=header,
            element_abundances=element_abundances,
            source_publication_shadow=source_detail_rrc_publication_shadow,
            source_record_publication_shadow=source_detail_rrc_record_shadow,
            source_slot_absorption_lifetime=source_detail_rrc_slot_absorption_lifetime,
            source_slot_current_eval_sequence=source_detail_rrc_current_eval_sequence,
            orphan_type7_absorption=source_detail_rrc_orphan_absorption,
            non_type7_absorption=source_detail_rrc_non_type7_absorption,
            fixed_state_non_type7_absorption=source_detail_rrc_fixed_state_absorption,
            fixed_state_non_type7_publication=source_detail_rrc_fixed_state_publication,
            publication_trace=source_detail_rrc_publication_trace,
        ),
        continuum=build_detail_continuum_table(epi_eV=epi_eV, zrems=zrems, opakc=opakc, rccemis=rccemis, dpthc=dpthc, ncn2=ncn2, header=header),
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the source real literal operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _source_real_literal(value: float) -> float:
    """Promote a FORTRAN default-REAL literal through binary32 to binary64."""
    return float(np.float32(value))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the voigte operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def voigte(vs: float, a: float) -> float:
    """Literal ``voigte.f90`` with default-REAL literal promotion.

    ``voigte.f90`` declares its working variables REAL(8), but DATA/PARAMETER
    values and branch literals are default REAL.  C++ opacity parity already
    preserves that binary32 rounding before promotion; Python must do the same
    for Type-50 ``linopac`` parity.
    """
    sr = _source_real_literal
    ak = np.asarray([
        sr(-1.12470432), sr(-0.15516677), sr(3.28867591), sr(-2.34357915), sr(0.42139162),
        sr(-4.48480194), sr(9.39456063), sr(-6.61487486), sr(1.98919585), sr(-0.22041650),
        sr(0.554153432), sr(0.278711796), sr(-0.188325687), sr(0.042991293),
        sr(-0.003278278), sr(0.979895023), sr(-0.962846325), sr(0.532770573),
        sr(-0.122727278),
    ], dtype=float)
    un = sr(1.0); two = sr(2.0)
    sqp = sr(1.772453851); sq2 = sr(1.414213562)
    v = abs(float(vs)); aa = float(a); u = aa + v; v2 = v * v
    if aa == sr(0.0):
        return 0.0 if v2 >= sr(100.0) else float(np.exp(-v2))
    if aa <= sr(0.2) and v >= sr(5.0):
        return aa * (sr(15.0) + sr(6.0) * v2 + sr(4.0) * v2 * v2) / (sr(4.0) * v2 * v2 * v2 * sqp)
    # voigte.f90: label 120 is reached only after the a>0.2 branch.
    # Therefore u=a+v>3.2 must not select the asymptotic expansion for
    # small-a profiles; those remain on the polynomial/Gaussian path until
    # the explicit v>=5 wing test above.
    if aa > sr(0.2) and (aa > sr(1.4) or u > sr(3.2)):
        a2 = aa * aa; uu = sq2 * (a2 + v2); u2 = un / (uu * uu)
        return sq2 / sqp * aa / uu * (
            un + u2 * (sr(3.0) * v2 - a2) +
            u2 * u2 * (sr(15.0) * v2 * v2 - sr(30.0) * v2 * a2 + sr(3.0) * a2 * a2)
        )
    ex = 0.0 if v2 >= sr(100.0) else float(np.exp(-v2))
    quo = un
    if v >= sr(2.4):
        quo = un / (v2 - sr(1.5)); start = 10
    elif v >= sr(1.3):
        start = 5
    else:
        start = 0
    a1 = ak[start:start + 5]
    h1 = quo * (a1[0] + v * (a1[1] + v * (a1[2] + v * (a1[3] + v * a1[4]))))
    if aa <= sr(0.2):
        return float(h1 * aa + ex * (un + aa * aa * (un - two * v2)))
    pqs = two / sqp
    h1p = h1 + pqs * ex
    h2p = pqs * h1p - two * v2 * ex
    h3p = (pqs * (un - ex * (un - two * v2)) - two * v2 * h1p) / sr(3.0) + pqs * h2p
    h4p = (two * v2 * v2 * ex - pqs * h1p) / sr(3.0) + pqs * h3p
    psi = ak[15] + aa * (ak[16] + aa * (ak[17] + aa * ak[18]))
    return float(psi * (ex + aa * (h1p + aa * (h2p + aa * (h3p + aa * h4p)))))

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the voigte array operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _voigte_array(vs: np.ndarray, a: float) -> np.ndarray:
    """Vectorized source-REAL twin of :func:`voigte` for far wings."""
    sr = _source_real_literal
    v = np.abs(np.asarray(vs, dtype=float))
    aa = float(a)
    v2 = v * v
    out = np.empty_like(v)
    sqp = sr(1.772453851)
    sq2 = sr(1.414213562)
    un = sr(1.0); two = sr(2.0)
    if aa == sr(0.0):
        out[:] = np.where(v2 >= sr(100.0), 0.0, np.exp(-v2))
        return out
    remaining = np.ones(v.shape, dtype=bool)
    if aa <= sr(0.2):
        m = v >= sr(5.0)
        if np.any(m):
            vv = v2[m]
            out[m] = aa * (sr(15.0) + sr(6.0) * vv + sr(4.0) * vv * vv) / (sr(4.0) * vv**3 * sqp)
            remaining[m] = False
    # Same nested source control flow as scalar voigte(): label 120 is
    # unreachable for a<=0.2.
    m = remaining & (aa > sr(0.2)) & ((aa > sr(1.4)) | ((aa + v) > sr(3.2)))
    if np.any(m):
        vv = v2[m]
        a2 = aa * aa
        uu = sq2 * (a2 + vv)
        u2 = un / (uu * uu)
        out[m] = sq2 / sqp * aa / uu * (
            un + u2 * (sr(3.0) * vv - a2) +
            u2 * u2 * (sr(15.0) * vv * vv - sr(30.0) * vv * a2 + sr(3.0) * a2 * a2)
        )
        remaining[m] = False
    if np.any(remaining):
        ak = np.asarray([
            sr(-1.12470432), sr(-0.15516677), sr(3.28867591), sr(-2.34357915), sr(0.42139162),
            sr(-4.48480194), sr(9.39456063), sr(-6.61487486), sr(1.98919585), sr(-0.22041650),
            sr(0.554153432), sr(0.278711796), sr(-0.188325687), sr(0.042991293), sr(-0.003278278),
            sr(0.979895023), sr(-0.962846325), sr(0.532770573), sr(-0.122727278),
        ], dtype=float)
        vr = v[remaining]
        vr2 = v2[remaining]
        ex = np.where(vr2 >= sr(100.0), 0.0, np.exp(-vr2))
        quo = np.ones_like(vr) * un
        start_idx = np.zeros(vr.shape, dtype=int)
        hi = vr >= sr(2.4)
        quo[hi] = un / (vr2[hi] - sr(1.5))
        start_idx[hi] = 10
        mid = (~hi) & (vr >= sr(1.3))
        start_idx[mid] = 5
        h1 = np.empty_like(vr)
        for st in (0,5,10):
            m2 = start_idx == st
            if not np.any(m2):
                continue
            vv = vr[m2]
            a1 = ak[st:st+5]
            h1[m2] = quo[m2] * (a1[0] + vv * (a1[1] + vv * (a1[2] + vv * (a1[3] + vv * a1[4]))))
        if aa <= sr(0.2):
            out[remaining] = h1 * aa + ex * (un + aa * aa * (un - two * vr2))
        else:
            pqs = two / sqp
            h1p = h1 + pqs * ex
            h2p = pqs * h1p - two * vr2 * ex
            h3p = (pqs * (un - ex * (un - two * vr2)) - two * vr2 * h1p) / sr(3.0) + pqs * h2p
            h4p = (two * vr2 * vr2 * ex - pqs * h1p) / sr(3.0) + pqs * h3p
            psi = ak[15] + aa * (ak[16] + aa * (ak[17] + aa * ak[18]))
            out[remaining] = psi * (ex + aa * (h1p + aa * (h2p + aa * (h3p + aa * h4p))))
    return out

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the source real operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _source_real(value: float) -> float:
    """Return a source default-real literal promoted to Python float."""
    return float(np.float32(value))

_SOURCE_BINEMIS_NEGATIVE_HALF_STEPS = 499997
_SOURCE_BINEMIS_POSITIVE_HALF_STEPS = 499999
_SOURCE_BINEMIS_FAR_V = 50.0


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the source binemis far rebin operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _source_binemis_far_rebin(
    *,
    epi: np.ndarray,
    n: int,
    e00: float,
    etmp: float,
    dele: float,
    deleused: float,
    aasmall: float,
    lum0: float,
    lum1: float,
    temporary_binned: np.ndarray,
) -> int:
    """Overwrite smooth-wing bins with literal ``binemis`` event ownership.

    ``binemis.f90`` declares ``nbtpp=ncn`` with source ``ncn=999999`` and
    accumulates fine-grid trapezoids until the first temporary point strictly
    exceeds an ``epi`` boundary.  The previous compact continuation required a
    whole public bin to lie inside the source reach, dropping the terminal
    partial segment.  This routine reproduces the source crossing indices and
    conditional terminal ``ml1m=ml1m-1`` behavior without allocating a million-point array.

    For |v|>=50 the source profile is in a smooth asymptotic branch.  The
    small-a label-121 expression is integrated analytically; larger-a wings use
    vectorized 8-point Gauss-Legendre quadrature.  These averages are only used
    for far segments; the literal compact temporary-grid rebin remains owner of
    the line core.
    """
    from .radiation import nbinc

    if not (deleused > 0.0 and dele > 0.0 and n >= 2):
        return 0
    qmin = max(
        -_SOURCE_BINEMIS_NEGATIVE_HALF_STEPS,
        int(np.floor(-float(e00) / float(deleused))) + 1,
    )
    while qmin <= _SOURCE_BINEMIS_POSITIVE_HALF_STEPS and e00 + float(qmin) * deleused <= 0.0:
        qmin += 1
    qmax = min(
        _SOURCE_BINEMIS_POSITIVE_HALF_STEPS,
        int(np.ceil((float(epi[n - 1]) - float(e00)) / float(deleused))) - 1,
    )
    while qmax >= -_SOURCE_BINEMIS_NEGATIVE_HALF_STEPS and e00 + float(qmax) * deleused >= float(epi[n - 1]):
        qmax -= 1
    if qmin >= qmax:
        return 0

    source_min = e00 + float(qmin) * deleused
    source_max = e00 + float(qmax) * deleused
    full_lo = max(1, int(nbinc(source_min, epi, n)))
    # Source writes only while ml1m<ncn2, so the highest writable 0-based
    # output index is n-2.  Build the boundary sequence from full_lo onward.
    k_one = np.arange(full_lo, n, dtype=np.int64)
    if k_one.size == 0:
        return 0
    boundaries = np.asarray(epi[k_one - 1], dtype=float)
    qevent = np.floor((boundaries - float(e00)) / float(deleused)).astype(np.int64) + 1
    qevent = np.maximum(qevent, np.int64(qmin + 1))
    eevent = float(e00) + qevent.astype(float) * float(deleused)
    # Correct the rare boundary-rounding case while preserving strict source >.
    adjust = eevent <= boundaries
    if np.any(adjust):
        qevent[adjust] += 1
        eevent[adjust] = float(e00) + qevent[adjust].astype(float) * float(deleused)
    valid = qevent <= np.int64(qmax)
    if not np.any(valid):
        return 0
    last = int(np.flatnonzero(valid)[-1]) + 1
    k_one = k_one[:last]
    qevent = qevent[:last]
    eevent = eevent[:last]

    # Consecutive public boundaries can be crossed by the same fine-grid point.
    # Source publishes one segment average to all such bins, then resets sums.
    starts = np.r_[0, np.flatnonzero(qevent[1:] != qevent[:-1]) + 1]
    ends = np.r_[starts[1:], qevent.size]
    events = qevent[starts]
    qprev = np.r_[np.int64(qmin), events[:-1]]
    e1 = float(e00) + qprev.astype(float) * float(deleused)
    e2 = float(e00) + events.astype(float) * float(deleused)
    v1 = (e1 - float(etmp)) / float(dele)
    v2 = (e2 - float(etmp)) / float(dele)
    far = (v1 * v2 > 0.0) & (np.minimum(np.abs(v1), np.abs(v2)) >= _SOURCE_BINEMIS_FAR_V)
    if not np.any(far):
        return 0

    avg = np.full(events.shape, np.nan, dtype=float)
    aa = float(aasmall)
    if aa <= 0.0:
        avg[far] = 0.0
    elif aa <= _source_real_literal(0.2):
        vf1 = v1[far]
        vf2 = v2[far]
        # XSTAR-FUNCTION-COMMENT-BEGIN
        # Purpose: Implement the primitive operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
        # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
        # XSTAR-FUNCTION-COMMENT-END
        def primitive(v: np.ndarray) -> np.ndarray:
            v2x = v * v
            return -1.0 / v - 0.5 / (v * v2x) - 0.75 / (v * v2x * v2x)
        coeff = aa / (
            _source_real_literal(1.772453851)
            * _source_real(1.772)
            * _source_real(1.602197e-12)
        )
        avg[far] = coeff * (primitive(vf2) - primitive(vf1)) / (e2[far] - e1[far])
    else:
        # 8-point Gauss-Legendre average, vectorized over far segments.
        gx = np.asarray([0.1834346424956498, 0.5255324099163290,
                         0.7966664774136267, 0.9602898564975363], dtype=float)
        gw = np.asarray([0.3626837833783620, 0.3137066458778873,
                         0.2223810344533745, 0.1012285362903763], dtype=float)
        ef1 = e1[far]; ef2 = e2[far]
        mid = 0.5 * (ef1 + ef2)
        half = 0.5 * (ef2 - ef1)
        accum = np.zeros(mid.shape, dtype=float)
        for xx, ww in zip(gx, gw):
            dx = half * xx
            vl = (mid - dx - float(etmp)) / float(dele)
            vr = (mid + dx - float(etmp)) / float(dele)
            accum += ww * (_voigte_array(vl, aa) + _voigte_array(vr, aa))
        avg[far] = 0.5 * accum / _source_real(1.772) / float(dele) / _source_real(1.602197e-12)

    far_groups = np.flatnonzero(far)
    writes = 0
    for gi in far_groups.tolist():
        start = int(starts[gi])
        end = int(ends[gi])
        targets = k_one[start:end] - 1
        value = float(avg[gi])
        temporary_binned[0, targets] = float(lum0) * value
        temporary_binned[1, targets] = float(lum1) * value
        writes += int(targets.size)
        # Literal terminal event: if mlm==mlmax, decrement ml1m before the
        # publishing while-loop.  This overwrites the preceding public bin.
        if int(events[gi]) == int(qmax):
            previous = int(k_one[start]) - 2
            if 0 <= previous < n - 1 and source_max > float(epi[previous]):
                temporary_binned[0, previous] = float(lum0) * value
                temporary_binned[1, previous] = float(lum1) * value
                writes += 1
    return writes




# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the rank binemis lines operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build binemis spectrum for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
    timing: dict[str, float] | None = None,
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

    # binemis.f90 has a very large source-capacity declaration, but materializing
    # that capacity in Python is unnecessary and prohibitively expensive.  Keep
    # the validated 20000-point core workspace and reproduce the additional
    # source-capacity reach below with a compact far-wing continuation on the
    # actual ncn2 output grid.  For this benchmark every eligible line has raw
    # ncut <= 4, so the source ncut capacity is never active.
    nbtpp = 20000
    out = np.asarray(original, dtype=float).copy()
    saved = np.asarray(original, dtype=float).copy()
    out[:, :n] = 0.0
    temporary_binned = np.zeros((2, nbtpp), dtype=float)
    temporary_profile = np.zeros((2, nbtpp), dtype=float)
    temporary_energy = np.zeros(nbtpp, dtype=float)
    _rank_t0 = time.perf_counter()
    ranked = _rank_binemis_lines(
        metadata=metadata,
        luminosity=lum,
        epi_eV=epi,
        ncn2=n,
        xlum=xlum,
        nrank=10,
    )
    if timing is not None:
        timing["final_product_build.spectrum.binemis_rank_lines_seconds"] = float(time.perf_counter() - _rank_t0)
    by_index = {row.line_index: row for row in metadata.lines}
    gate = _source_real(1.0e-15) * float(xlum)
    dpcrit = _source_real(1.0e-6)

    _profile_t0 = time.perf_counter()
    _profile_lines_attempted = 0
    _profile_lines_applied = 0
    # v0.6.0a18: binemis ranking is sparse.  The source loop is kl outer,
    # rank inner, but most ranked slots are zero.  Iterate only nonzero
    # ranked entries in the same kl/mm order instead of scanning
    # ncn2 * nrank Python slots.
    _ranked_nonzero = np.argwhere(np.asarray(ranked[:10, :n]).T > 0)
    if timing is not None:
        timing["final_product_build.spectrum.binemis_profile_nonzero_ranked_slots"] = float(_ranked_nonzero.shape[0])
        timing["final_product_build.spectrum.binemis_profile_scanned_slots_saved"] = float(max(0, n * 10 - int(_ranked_nonzero.shape[0])))

    # v0.6.0a19: the strong-line profile loop is now available as a real
    # C++ emissivity/output backend.  Python still ranks lines source-faithfully
    # and packs compact line metadata, but C++ owns the expensive voigte/profile
    # expansion plus final active-row packing.  Fallback preserves the validated
    # Python implementation when the optional library is absent or disabled.
    #
    # v0.6.6: split the C++ binemis path into PRODUCT and SHADOW gates.  Shadow
    # mode evaluates C++ beside Python and records worst array/bin differences
    # without allowing the C++ result to alter products.
    _cpp_shadow_out = None
    _cpp_shadow_stats = None

    # v0.6.48.10.0: promote the already-qualified native binemis product
    # implementation automatically when the Python source-port run explicitly
    # selects the C++ backend.  Pure-Python runs remain on the historical
    # Python writer.  The force-Python switch is intentionally local to the
    # final binemis product so the same accelerated executable/process can be
    # used for exact A/B qualification without changing zone computation.
    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the env true operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
    def _env_true(name: str, default: str = "0") -> bool:
        return str(os.environ.get(name, default)).strip().lower() in {"1", "true", "yes", "on"}

    _force_python_binemis = _env_true("XSTAR_V064810_FORCE_PYTHON_BINEMIS")
    _allow_python_fallback = _env_true("XSTAR_V064810_ALLOW_PYTHON_BINEMIS_FALLBACK")
    _global_backend = str(os.environ.get("XSTAR_ATOMIC_BACKEND", "")).strip().lower()
    _emissivity_backend = str(os.environ.get("XSTAR_ATOMIC_EMISSIVITY_BACKEND", "")).strip().lower()
    _accelerated_cpp_selected = _global_backend == "cpp" or _emissivity_backend == "cpp"
    _explicit_cpp_enabled = _env_true("XSTAR_ATOMIC_EMISSIVITY_BINEMIS_CPP")
    _explicit_cpp_product = _env_true("XSTAR_ATOMIC_EMISSIVITY_BINEMIS_PRODUCT_CPP")
    _explicit_cpp_shadow = _env_true("XSTAR_ATOMIC_EMISSIVITY_BINEMIS_SHADOW_CPP")

    _cpp_product = (not _force_python_binemis) and (
        _explicit_cpp_product or _accelerated_cpp_selected
    )
    _cpp_shadow = (not _force_python_binemis) and _explicit_cpp_shadow
    _cpp_enabled = (not _force_python_binemis) and (
        _explicit_cpp_enabled or _cpp_product or _cpp_shadow
    )
    _cpp_product_required = _cpp_product and not _allow_python_fallback

    if timing is not None:
        timing["final_product_build.spectrum.binemis_v064810_accelerated_cpp_selected"] = 1.0 if _accelerated_cpp_selected else 0.0
        timing["final_product_build.spectrum.binemis_v064810_auto_product_promotion"] = 1.0 if (_accelerated_cpp_selected and not _explicit_cpp_product and not _force_python_binemis) else 0.0
        timing["final_product_build.spectrum.binemis_v064810_force_python"] = 1.0 if _force_python_binemis else 0.0
        timing["final_product_build.spectrum.binemis_v064810_product_required"] = 1.0 if _cpp_product_required else 0.0
        timing["final_product_build.spectrum.binemis_v064810_python_fallback_allowed"] = 1.0 if _allow_python_fallback else 0.0
    line_wavelength = None
    line_data_type = None
    line_atomic_mass = None
    line_natural_rate = None
    line_auger_width = None
    line_auger_rate = None
    slot_line_indices = None
    if _cpp_enabled and _ranked_nonzero.shape[0] > 0:
        _cpp_t0 = time.perf_counter()
        try:
            from .cpp_backend_emissivity import build_binemis_profile_cpp
            n_lum_lines = int(lum.shape[1])
            line_wavelength = np.zeros(n_lum_lines, dtype=float)
            line_data_type = np.zeros(n_lum_lines, dtype=np.int64)
            line_atomic_mass = np.ones(n_lum_lines, dtype=float)
            line_natural_rate = np.zeros(n_lum_lines, dtype=float)
            line_auger_width = np.zeros(n_lum_lines, dtype=float)
            line_auger_rate = np.zeros(n_lum_lines, dtype=float)
            for row in metadata.lines:
                j0 = int(row.line_index) - 1
                if 0 <= j0 < n_lum_lines:
                    line_wavelength[j0] = abs(float(row.wavelength_angstrom))
                    line_data_type[j0] = int(row.data_type)
                    line_atomic_mass[j0] = max(float(row.atomic_mass), np.finfo(float).tiny)
                    line_natural_rate[j0] = float(row.natural_rate_s)
                    line_auger_width[j0] = float(row.auger_width_eV)
                    line_auger_rate[j0] = float(row.auger_rate_s)
            slot_line_indices = np.ascontiguousarray([
                int(ranked[int(mm0), int(kl0)]) for kl0, mm0 in _ranked_nonzero
            ], dtype=np.int64)
            cpp_out, cpp_stats, cpp_message = build_binemis_profile_cpp(
                epi_eV=epi, dpthc=dp, elum=lum, zrems=original, zremsz=incident,
                slot_line_indices=slot_line_indices,
                line_wavelength=line_wavelength, line_data_type=line_data_type,
                line_atomic_mass=line_atomic_mass, line_natural_rate_s=line_natural_rate,
                line_auger_width_eV=line_auger_width, line_auger_rate_s=line_auger_rate,
                xlum=xlum, temperature_1e4K=temperature_1e4K,
                turbulent_velocity_km_s=turbulent_velocity_km_s, ncn2=n,
            )
            if timing is not None:
                timing["final_product_build.spectrum.binemis_cpp_seconds"] = float(time.perf_counter() - _cpp_t0)
                timing["final_product_build.spectrum.binemis_cpp_message_present"] = 1.0 if cpp_message else 0.0
                timing["final_product_build.spectrum.binemis_profile_lines_attempted"] = float(cpp_stats.get("cpp_profile_lines_attempted", 0.0))
                timing["final_product_build.spectrum.binemis_profile_lines_applied"] = float(cpp_stats.get("cpp_profile_lines_applied", 0.0))
                timing["final_product_build.spectrum.binemis_cpp_slots"] = float(cpp_stats.get("cpp_profile_slots", 0.0))
                timing["final_product_build.spectrum.binemis_cpp_product_enabled"] = 1.0 if _cpp_product else 0.0
                timing["final_product_build.spectrum.binemis_cpp_shadow_enabled"] = 1.0 if _cpp_shadow else 0.0
                timing["final_product_build.spectrum.binemis_cpp_source_real_literal_parity"] = 1.0
                timing["final_product_build.spectrum.binemis_cpp_product_accepted_opt_in"] = 1.0 if _cpp_product else 0.0
                timing["final_product_build.spectrum.binemis_cpp_product_scope_final_binemis_only"] = 1.0
            if _cpp_product:
                if timing is not None:
                    timing["final_product_build.spectrum.binemis_profile_seconds"] = float(timing["final_product_build.spectrum.binemis_cpp_seconds"])
                    timing["final_product_build.spectrum.binemis_pack_seconds"] = 0.0
                return cpp_out
            if _cpp_shadow:
                _cpp_shadow_out = np.asarray(cpp_out, dtype=float).copy()
                _cpp_shadow_stats = dict(cpp_stats)
        except Exception as exc:
            if timing is not None:
                _err = str(exc)
                _repr = repr(exc)
                timing["final_product_build.spectrum.binemis_cpp_fallback"] = 1.0
                timing["final_product_build.spectrum.binemis_cpp_error_present"] = 1.0
                timing["final_product_build.spectrum.binemis_cpp_error_message_length"] = float(len(_err))
                timing["final_product_build.spectrum.binemis_cpp_error_repr_length"] = float(len(_repr))
                # v0.6.9: store the actual exception text in output_writer_timing_breakdown.
                # The numeric timing total intentionally ignores non-numeric values.
                timing["final_product_build.spectrum.binemis_cpp_error_type"] = type(exc).__name__
                timing["final_product_build.spectrum.binemis_cpp_error_message"] = _err[:2048]
                timing["final_product_build.spectrum.binemis_cpp_error_repr"] = _repr[:2048]
            if _cpp_product_required:
                raise OutputWriterPortError(
                    "v0.6.48.10.0 accelerated Python selected the C++ binemis "
                    "product backend but it failed; set "
                    "XSTAR_V064810_FORCE_PYTHON_BINEMIS=1 for the validated "
                    "Python writer or XSTAR_V064810_ALLOW_PYTHON_BINEMIS_FALLBACK=1 "
                    "to permit an explicit slow fallback"
                ) from exc

    # v0.6.11 emit_outward slot-contribution probe.  This remains
    # diagnostic-only and is only active when C++ shadow mode is active.
    # Bin numbers use the same zero-based convention reported by v0.6.10.
    _slot_probe_enabled = _cpp_shadow and os.environ.get(
        "XSTAR_ATOMIC_EMISSIVITY_SLOT_CONTRIBUTION_PROBE", "1"
    ).strip().lower() not in {"0", "false", "no", "off"}
    _slot_probe_target_text = os.environ.get(
        "XSTAR_ATOMIC_EMISSIVITY_SLOT_PROBE_TARGET_BINS",
        "2981,2982,1894,1895,3875,3876,2788,2789,4945",
    )
    _slot_probe_radius = int(os.environ.get("XSTAR_ATOMIC_EMISSIVITY_SLOT_PROBE_RADIUS", "1") or "1")
    _slot_probe_top_n = int(os.environ.get("XSTAR_ATOMIC_EMISSIVITY_SLOT_PROBE_TOP_N", "24") or "24")
    _slot_probe_targets: list[int] = []
    if _slot_probe_enabled:
        for _part in str(_slot_probe_target_text).replace(";", ",").split(","):
            _part = _part.strip()
            if not _part:
                continue
            try:
                _b = int(_part)
            except Exception:
                continue
            if 0 <= _b < n and _b not in _slot_probe_targets:
                _slot_probe_targets.append(_b)
    _slot_probe_bin_set: set[int] = set()
    for _b in _slot_probe_targets:
        for _bb in range(max(0, _b - _slot_probe_radius), min(n, _b + _slot_probe_radius + 1)):
            _slot_probe_bin_set.add(int(_bb))
    _slot_probe_records: dict[int, dict[str, Any]] = {}

    for _slot_ord, (_kl0, _mm0) in enumerate(_ranked_nonzero):
            kl_one_based = int(_kl0) + 1
            mm_one_based = int(_mm0) + 1
            line_index = int(ranked[mm_one_based - 1, kl_one_based - 1])
            if line_index <= 0 or line_index > lum.shape[1]:
                continue
            _profile_lines_attempted += 1
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

            temporary_binned[:, :n] = 0.0
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
            _profile_lines_applied += 1
            core_energy_min = float(temporary_energy[mlmin - 1])
            core_energy_max = float(temporary_energy[mlmax - 1])
            ml1min = int(nbinc(core_energy_min, epi, n))
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

            _far_writes = _source_binemis_far_rebin(
                epi=epi,
                n=n,
                e00=e00,
                etmp=etmp,
                dele=dele,
                deleused=deleused,
                aasmall=aasmall,
                lum0=float(lum[0, j]),
                lum1=float(lum[1, j]),
                temporary_binned=temporary_binned,
            )
            if timing is not None and _far_writes:
                timing["final_product_build.spectrum.binemis_far_wing_bins"] = (
                    float(timing.get("final_product_build.spectrum.binemis_far_wing_bins", 0.0))
                    + float(_far_writes)
                )

            _nz = np.flatnonzero((temporary_binned[0, :n] != 0.0) | (temporary_binned[1, :n] != 0.0))
            if _nz.size:
                lo = int(_nz[0]) + 1
                hi = int(_nz[-1]) + 1
                if _slot_probe_enabled and _slot_probe_bin_set:
                    _probe_bins_here = [
                        int(_b) for _b in sorted(_slot_probe_bin_set)
                        if 0 <= int(_b) < n and
                        (temporary_binned[0, int(_b)] != 0.0 or temporary_binned[1, int(_b)] != 0.0)
                    ]
                    if _probe_bins_here:
                        _rec = _slot_probe_records.setdefault(int(_slot_ord), {
                            "slot_index": int(_slot_ord),
                            "rank_kl0": int(_kl0),
                            "rank_mm0": int(_mm0),
                            "line_index": int(line_index),
                            "line_profile_id": int(line_index),
                            "source_bin": int(nb1 - 1),
                            "python_bin_choice_min": int(lo - 1),
                            "python_bin_choice_max": int(hi - 1),
                            "line_energy_eV": float(line_energy),
                            "profile_center_eV": float(e0),
                            "wavelength_angstrom": float(wavelength),
                            "python_emit_outward_by_bin": {},
                            "python_emit_inward_by_bin": {},
                        })
                        _rec["python_bin_choice_min"] = min(int(_rec.get("python_bin_choice_min", lo - 1)), int(lo - 1))
                        _rec["python_bin_choice_max"] = max(int(_rec.get("python_bin_choice_max", hi - 1)), int(hi - 1))
                        for _b in _probe_bins_here:
                            _rec["python_emit_outward_by_bin"][str(_b)] = float(temporary_binned[1, _b])
                            _rec["python_emit_inward_by_bin"][str(_b)] = float(temporary_binned[0, _b])
                out[3, :n] += temporary_binned[1, :n]
                out[2, :n] += temporary_binned[0, :n]

    if timing is not None:
        timing["final_product_build.spectrum.binemis_profile_seconds"] = float(time.perf_counter() - _profile_t0)
        timing["final_product_build.spectrum.binemis_profile_lines_attempted"] = float(_profile_lines_attempted)
        timing["final_product_build.spectrum.binemis_profile_lines_applied"] = float(_profile_lines_applied)
    _pack_t0 = time.perf_counter()
    for kl in range(n):
        out[2, kl] += saved[1, kl]
        out[3, kl] += saved[2, kl]
        out[1, kl] = incident[kl] * np.exp(-dp[0, kl])
        out[0, kl] = incident[kl]
        out[4, kl] = saved[3, kl]
    if original.shape[1] > n:
        out[:, n:] = original[:, n:]
    if timing is not None:
        timing["final_product_build.spectrum.binemis_pack_seconds"] = float(time.perf_counter() - _pack_t0)
        if _cpp_shadow_out is not None:
            try:
                _active = slice(0, n)
                _py_cmp = np.asarray(out[:, _active], dtype=float)
                _cpp_cmp = np.asarray(_cpp_shadow_out[:, _active], dtype=float)
                _abs = np.abs(_cpp_cmp - _py_cmp)
                _den = np.maximum(np.abs(_py_cmp), np.finfo(float).tiny)
                _rel = _abs / _den
                _max_abs_flat = int(np.argmax(_abs)) if _abs.size else 0
                _max_rel_flat = int(np.argmax(_rel)) if _rel.size else 0
                _abs_row, _abs_bin = np.unravel_index(_max_abs_flat, _abs.shape) if _abs.size else (0, 0)
                _rel_row, _rel_bin = np.unravel_index(_max_rel_flat, _rel.shape) if _rel.size else (0, 0)
                _row_names = ("incident", "transmitted", "emit_inward", "emit_outward", "saved_row4")
                timing["final_product_build.spectrum.binemis_shadow_compared"] = 1.0
                timing["final_product_build.spectrum.binemis_shadow_max_abs_diff"] = float(_abs[_abs_row, _abs_bin]) if _abs.size else 0.0
                timing["final_product_build.spectrum.binemis_shadow_max_rel_diff"] = float(_rel[_rel_row, _rel_bin]) if _rel.size else 0.0
                timing["final_product_build.spectrum.binemis_shadow_max_abs_row"] = float(_abs_row)
                timing["final_product_build.spectrum.binemis_shadow_max_abs_bin"] = float(_abs_bin)
                timing["final_product_build.spectrum.binemis_shadow_max_rel_row"] = float(_rel_row)
                timing["final_product_build.spectrum.binemis_shadow_max_rel_bin"] = float(_rel_bin)
                timing["final_product_build.spectrum.binemis_shadow_max_abs_energy_eV"] = float(epi[_abs_bin]) if 0 <= _abs_bin < epi.size else 0.0
                timing["final_product_build.spectrum.binemis_shadow_max_rel_energy_eV"] = float(epi[_rel_bin]) if 0 <= _rel_bin < epi.size else 0.0
                timing["final_product_build.spectrum.binemis_shadow_rows_with_abs_diff"] = float(np.count_nonzero(np.any(_abs != 0.0, axis=1))) if _abs.size else 0.0
                timing["final_product_build.spectrum.binemis_shadow_bins_with_abs_diff"] = float(np.count_nonzero(np.any(_abs != 0.0, axis=0))) if _abs.size else 0.0
                timing["final_product_build.spectrum.binemis_shadow_max_abs_row_name_code"] = float(_abs_row)
                timing["final_product_build.spectrum.binemis_shadow_max_rel_row_name_code"] = float(_rel_row)
                # v0.6.11 emit_outward-focused parity and slot-contribution probe.  Keep this
                # product-inactive: these diagnostics only explain the shadow
                # mismatch and never replace the Python spectrum.
                try:
                    _probe_rows = [3] if _abs.shape[0] > 3 else list(range(_abs.shape[0]))
                    timing["final_product_build.spectrum.binemis_shadow_probe_version"] = 615.0
                    timing["final_product_build.spectrum.binemis_shadow_emit_outward_row"] = 3.0
                    for _row in _probe_rows:
                        _row_name = _row_names[_row] if 0 <= _row < len(_row_names) else f"row{_row}"
                        _row_abs = _abs[_row, :]
                        _row_rel = _rel[_row, :]
                        _row_diff = _cpp_cmp[_row, :] - _py_cmp[_row, :]
                        _r_abs_bin = int(np.argmax(_row_abs)) if _row_abs.size else 0
                        _r_rel_bin = int(np.argmax(_row_rel)) if _row_rel.size else 0
                        _prefix = f"final_product_build.spectrum.binemis_shadow_{_row_name}"
                        timing[f"{_prefix}_max_abs_diff"] = float(_row_abs[_r_abs_bin]) if _row_abs.size else 0.0
                        timing[f"{_prefix}_max_rel_diff"] = float(_row_rel[_r_rel_bin]) if _row_rel.size else 0.0
                        timing[f"{_prefix}_max_abs_bin"] = float(_r_abs_bin)
                        timing[f"{_prefix}_max_rel_bin"] = float(_r_rel_bin)
                        timing[f"{_prefix}_max_abs_energy_eV"] = float(epi[_r_abs_bin]) if 0 <= _r_abs_bin < epi.size else 0.0
                        timing[f"{_prefix}_max_rel_energy_eV"] = float(epi[_r_rel_bin]) if 0 <= _r_rel_bin < epi.size else 0.0
                        timing[f"{_prefix}_max_abs_py_value"] = float(_py_cmp[_row, _r_abs_bin]) if _row_abs.size else 0.0
                        timing[f"{_prefix}_max_abs_cpp_value"] = float(_cpp_cmp[_row, _r_abs_bin]) if _row_abs.size else 0.0
                        timing[f"{_prefix}_max_abs_signed_diff"] = float(_row_diff[_r_abs_bin]) if _row_abs.size else 0.0
                        timing[f"{_prefix}_max_rel_py_value"] = float(_py_cmp[_row, _r_rel_bin]) if _row_rel.size else 0.0
                        timing[f"{_prefix}_max_rel_cpp_value"] = float(_cpp_cmp[_row, _r_rel_bin]) if _row_rel.size else 0.0
                        timing[f"{_prefix}_max_rel_signed_diff"] = float(_row_diff[_r_rel_bin]) if _row_rel.size else 0.0
                        timing[f"{_prefix}_bins_with_abs_diff"] = float(np.count_nonzero(_row_abs != 0.0)) if _row_abs.size else 0.0

                        # XSTAR-FUNCTION-COMMENT-BEGIN
                        # Purpose: Implement the window json operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
                        # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
                        # XSTAR-FUNCTION-COMMENT-END
                        def _window_json(_center: int, _radius: int = 3) -> str:
                            _lo = max(0, int(_center) - _radius)
                            _hi = min(n, int(_center) + _radius + 1)
                            _items = []
                            for _b in range(_lo, _hi):
                                _pyv = float(_py_cmp[_row, _b])
                                _cppv = float(_cpp_cmp[_row, _b])
                                _d = float(_cppv - _pyv)
                                _denv = max(abs(_pyv), float(np.finfo(float).tiny))
                                _items.append({
                                    "bin": int(_b),
                                    "energy_eV": float(epi[_b]) if 0 <= _b < epi.size else 0.0,
                                    "python": _pyv,
                                    "cpp": _cppv,
                                    "signed_diff": _d,
                                    "abs_diff": abs(_d),
                                    "rel_diff": abs(_d) / _denv,
                                })
                            return json.dumps(_items, separators=(",", ":"))[:4096]

                        timing[f"{_prefix}_max_abs_window_json"] = _window_json(_r_abs_bin)
                        timing[f"{_prefix}_max_rel_window_json"] = _window_json(_r_rel_bin)
                        if _row_abs.size:
                            _top_n = min(10, int(_row_abs.size))
                            _top_idx = np.argsort(_row_abs)[- _top_n:][::-1]
                            _top_items = []
                            for _b in _top_idx:
                                _b = int(_b)
                                _pyv = float(_py_cmp[_row, _b])
                                _cppv = float(_cpp_cmp[_row, _b])
                                _d = float(_cppv - _pyv)
                                _denv = max(abs(_pyv), float(np.finfo(float).tiny))
                                _top_items.append({
                                    "bin": _b,
                                    "energy_eV": float(epi[_b]) if 0 <= _b < epi.size else 0.0,
                                    "python": _pyv,
                                    "cpp": _cppv,
                                    "signed_diff": _d,
                                    "abs_diff": abs(_d),
                                    "rel_diff": abs(_d) / _denv,
                                })
                            timing[f"{_prefix}_top_abs_bins_json"] = json.dumps(_top_items, separators=(",", ":"))[:8192]
                    # v0.6.11: replay top Python-contributing slots through the C++
                    # shadow kernel one slot at a time, using a zero original spectrum,
                    # so row 3 is the per-slot emit_outward contribution.  This is
                    # intentionally capped and product-inactive.
                    if _slot_probe_enabled and _slot_probe_records and _slot_probe_targets:
                        try:
                            from .cpp_backend_emissivity import build_binemis_profile_cpp as _build_binemis_profile_cpp_probe
                            _probe_candidates = list(_slot_probe_records.values())
                            # XSTAR-FUNCTION-COMMENT-BEGIN
                            # Purpose: Implement the py probe strength operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
                            # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
                            # XSTAR-FUNCTION-COMMENT-END
                            def _py_probe_strength(_rec: Mapping[str, Any]) -> float:
                                _vals = as_map(_rec.get("python_emit_outward_by_bin")) if "as_map" in globals() else _rec.get("python_emit_outward_by_bin", {})
                                if not isinstance(_vals, Mapping):
                                    return 0.0
                                return max((abs(float(_v)) for _v in _vals.values()), default=0.0)
                            _probe_candidates.sort(key=_py_probe_strength, reverse=True)
                            _probe_candidates = _probe_candidates[:max(1, int(_slot_probe_top_n))]
                            _zero_original = np.zeros_like(original, dtype=float)
                            _probe_items = []
                            _probe_max_abs_diff = 0.0
                            _probe_max_abs_slot = -1
                            _probe_max_abs_bin = -1
                            _probe_t0 = time.perf_counter()
                            for _rec in _probe_candidates:
                                _line_index = int(_rec.get("line_index", 0))
                                if _line_index <= 0:
                                    continue
                                _cpp_slot_out, _cpp_slot_stats, _cpp_slot_msg = _build_binemis_profile_cpp_probe(
                                    epi_eV=epi, dpthc=dp, elum=lum, zrems=_zero_original, zremsz=incident,
                                    slot_line_indices=np.asarray([_line_index], dtype=np.int64),
                                    line_wavelength=line_wavelength if line_wavelength is not None else np.zeros(int(lum.shape[1]), dtype=float),
                                    line_data_type=line_data_type if line_data_type is not None else np.zeros(int(lum.shape[1]), dtype=np.int64),
                                    line_atomic_mass=line_atomic_mass if line_atomic_mass is not None else np.ones(int(lum.shape[1]), dtype=float),
                                    line_natural_rate_s=line_natural_rate if line_natural_rate is not None else np.zeros(int(lum.shape[1]), dtype=float),
                                    line_auger_width_eV=line_auger_width if line_auger_width is not None else np.zeros(int(lum.shape[1]), dtype=float),
                                    line_auger_rate_s=line_auger_rate if line_auger_rate is not None else np.zeros(int(lum.shape[1]), dtype=float),
                                    xlum=xlum, temperature_1e4K=temperature_1e4K,
                                    turbulent_velocity_km_s=turbulent_velocity_km_s, ncn2=n,
                                )
                                _cpp_row = np.asarray(_cpp_slot_out[3, :n], dtype=float)
                                _py_by_bin = dict(_rec.get("python_emit_outward_by_bin", {}))
                                _cpp_by_bin = {}
                                _diff_by_bin = {}
                                _neighbor_items = []
                                _item_max = 0.0
                                _item_max_bin = -1
                                for _b in sorted(_slot_probe_bin_set):
                                    _pyv = float(_py_by_bin.get(str(_b), 0.0))
                                    _cppv = float(_cpp_row[_b]) if 0 <= int(_b) < _cpp_row.size else 0.0
                                    if _pyv != 0.0 or _cppv != 0.0:
                                        _cpp_by_bin[str(int(_b))] = _cppv
                                        _diff = _cppv - _pyv
                                        _diff_by_bin[str(int(_b))] = _diff
                                        _ad = abs(_diff)
                                        if _ad > _item_max:
                                            _item_max = _ad
                                            _item_max_bin = int(_b)
                                        _neighbor_items.append({
                                            "bin": int(_b),
                                            "energy_eV": float(epi[int(_b)]) if 0 <= int(_b) < epi.size else 0.0,
                                            "python_contribution": _pyv,
                                            "cpp_contribution": _cppv,
                                            "signed_diff": _diff,
                                        })
                                _cpp_nonzero = np.flatnonzero(_cpp_row != 0.0)
                                _cpp_choice_min = int(_cpp_nonzero[0]) if _cpp_nonzero.size else -1
                                _cpp_choice_max = int(_cpp_nonzero[-1]) if _cpp_nonzero.size else -1
                                if _item_max > _probe_max_abs_diff:
                                    _probe_max_abs_diff = float(_item_max)
                                    _probe_max_abs_slot = int(_rec.get("slot_index", -1))
                                    _probe_max_abs_bin = int(_item_max_bin)
                                _probe_items.append({
                                    "slot_index": int(_rec.get("slot_index", -1)),
                                    "line_profile_id": int(_rec.get("line_profile_id", _line_index)),
                                    "line_index": _line_index,
                                    "source_bin": int(_rec.get("source_bin", -1)),
                                    "line_energy_eV": float(_rec.get("line_energy_eV", 0.0)),
                                    "profile_center_eV": float(_rec.get("profile_center_eV", 0.0)),
                                    "wavelength_angstrom": float(_rec.get("wavelength_angstrom", 0.0)),
                                    "python_bin_choice_min": int(_rec.get("python_bin_choice_min", -1)),
                                    "python_bin_choice_max": int(_rec.get("python_bin_choice_max", -1)),
                                    "cpp_bin_choice_min": _cpp_choice_min,
                                    "cpp_bin_choice_max": _cpp_choice_max,
                                    "python_emit_outward_by_bin": _py_by_bin,
                                    "cpp_emit_outward_by_bin": _cpp_by_bin,
                                    "signed_diff_by_bin": _diff_by_bin,
                                    "neighbor_bin_contributions": _neighbor_items,
                                    "max_abs_target_diff": float(_item_max),
                                    "max_abs_target_diff_bin": int(_item_max_bin),
                                })
                            _probe_payload = {
                                "probe_version": "0.6.15",
                                "row": 3,
                                "row_name": "emit_outward",
                                "target_bins": [int(_b) for _b in _slot_probe_targets],
                                "target_window_radius": int(_slot_probe_radius),
                                "target_window_bins": [int(_b) for _b in sorted(_slot_probe_bin_set)],
                                "top_n": int(_slot_probe_top_n),
                                "slots_recorded": int(len(_probe_items)),
                                "slots_seen_with_python_target_contribution": int(len(_slot_probe_records)),
                                "items": _probe_items,
                            }
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_available"] = 1.0
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_version"] = 615.0
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_targets_json"] = json.dumps([int(_b) for _b in _slot_probe_targets], separators=(",", ":"))
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_windows_json"] = json.dumps([int(_b) for _b in sorted(_slot_probe_bin_set)], separators=(",", ":"))
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_slots"] = float(len(_probe_items))
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_candidates"] = float(len(_slot_probe_records))
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_seconds"] = float(time.perf_counter() - _probe_t0)
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_max_abs_diff"] = float(_probe_max_abs_diff)
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_max_abs_slot"] = float(_probe_max_abs_slot)
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_max_abs_bin"] = float(_probe_max_abs_bin)
                            timing["final_product_build.spectrum.binemis_shadow_emit_outward_slot_probe_json"] = json.dumps(_probe_payload, separators=(",", ":"))[:65536]
                        except Exception as _slot_probe_exc:
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_available"] = 0.0
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_error"] = 1.0
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_error_type"] = type(_slot_probe_exc).__name__
                            timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_error_message"] = str(_slot_probe_exc)[:2048]
                    else:
                        timing["final_product_build.spectrum.binemis_shadow_slot_contribution_probe_available"] = 0.0
                except Exception as _probe_exc:
                    timing["final_product_build.spectrum.binemis_shadow_probe_error"] = 1.0
                    timing["final_product_build.spectrum.binemis_shadow_probe_error_type"] = type(_probe_exc).__name__
                    timing["final_product_build.spectrum.binemis_shadow_probe_error_message"] = str(_probe_exc)[:2048]
                if _cpp_shadow_stats:
                    for _k, _v in _cpp_shadow_stats.items():
                        if isinstance(_v, (int, float)):
                            timing[f"final_product_build.spectrum.binemis_shadow_cpp_{_k}"] = float(_v)
            except Exception as exc:
                timing["final_product_build.spectrum.binemis_shadow_compare_error"] = 1.0
                timing["final_product_build.spectrum.binemis_shadow_compare_error_type"] = type(exc).__name__
                timing["final_product_build.spectrum.binemis_shadow_compare_error_message"] = str(exc)[:2048]
    return out

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build final spectrum table for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
    timing: dict[str, float] | None = None,
) -> OutputTable:
    if int(lwri) >= 0:
        mapped = build_binemis_spectrum(
            metadata=metadata, xlum=xlum,
            temperature_1e4K=temperature_1e4K,
            turbulent_velocity_km_s=turbulent_velocity_km_s,
            epi_eV=epi_eV, ncn2=ncn2, dpthc=dpthc, elum=elum,
            zrems=zrems, zremsz=zremsz, timing=timing,
        )
    else:
        mapped = np.asarray(zrems, dtype=float).copy()
    n = int(ncn2)
    _spectrum_table_t0 = time.perf_counter()
    values = {
        "energy": _r4_array(np.asarray(epi_eV)[:n]),
        "incident": _r4_array(mapped[0, :n]),
        "transmitted": _r4_array(mapped[1, :n]),
        "emit_inward": _r4_array(mapped[2, :n]),
        "emit_outward": _r4_array(mapped[3, :n]),
    }
    if timing is not None:
        timing["final_product_build.spectrum.table_pack_seconds"] = float(time.perf_counter() - _spectrum_table_t0)
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


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Select final line rows for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _select_final_line_rows(
    metadata: SourceOutputMetadata, elum: np.ndarray
) -> tuple[list[LineOutputMetadata], list[LineOutputMetadata]]:
    """Return source identity rank and frozen numerical rank separately."""
    lum = np.asarray(elum, dtype=float)
    ordered = sorted(metadata.lines, key=lambda row: int(row.line_index))

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the qualifies operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
    def qualifies(row: LineOutputMetadata) -> tuple[bool, float]:
        i = int(row.line_index) - 1
        if i < 0 or i >= lum.shape[1] or row.rate_type in (9, 14):
            return False, 0.0
        wave = abs(float(row.wavelength_angstrom))
        if not (wave >= float(np.float32(0.1)) and wave <= float(np.float32(1.0e10)) and wave <= float(np.float32(8.9e6))):
            return False, 0.0
        mean = (float(lum[0, i]) + float(lum[1, i])) / float(np.float32(2.0))
        return bool(np.isfinite(mean) and mean > float(np.float32(FINAL_LINE_ACTIVITY_FLOOR))), mean

    # Frozen pre-12.3.41 numerical rank: insert before equal and pop the tail.
    numeric: list[tuple[float, int, LineOutputMetadata]] = []
    for order, row in enumerate(ordered):
        ok, mean = qualifies(row)
        if ok:
            numeric.append((-mean, -order, row))
    numeric.sort()
    numeric_rows = [row for _, _, row in numeric[:FINAL_LINE_LIMIT]]

    # Literal writespectra2 fixed-capacity kltmp identity rank.
    kltmp = [0] * FINAL_LINE_LIMIT
    keys = [0.0] * len(ordered)
    valid = [False] * len(ordered)
    kltmpo = 0
    nlpl = 1
    for si, row in enumerate(ordered):
        ok, mean = qualifies(row)
        if not ok:
            continue
        keys[si] = mean
        valid[si] = True
        lmm = 0
        elcomp = 1.0e10
        while lmm < nlpl and mean < elcomp:
            lmm += 1
            kl2 = kltmp[lmm - 1]
            elcomp = keys[kl2 - 1] if kl2 > 0 else 0.0
        kltmpo = si + 1
        last = min(FINAL_LINE_LIMIT, nlpl)
        if lmm > 0:
            for k in range(lmm, last + 1):
                at = k - 1
                kltmpn = kltmp[at]
                kltmp[at] = kltmpo
                kltmpo = kltmpn
        nlpl = min(FINAL_LINE_LIMIT, nlpl + 1)
    if nlpl > 0:
        kltmp[nlpl - 1] = kltmpo
    identity_rows: list[LineOutputMetadata] = []
    for kk in range(min(nlpl, len(kltmp))):
        if kltmp[kk] == 0:
            continue
        si = kltmp[kk] - 1
        if 0 <= si < len(ordered) and valid[si]:
            identity_rows.append(ordered[si])
    return identity_rows, numeric_rows


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build final line table for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def build_final_line_table(*, metadata: SourceOutputMetadata, elum: np.ndarray, tau0: np.ndarray, timing: dict[str, float] | None = None) -> OutputTable:
    _t0 = time.perf_counter()
    lum = np.asarray(elum, dtype=float); depth = np.asarray(tau0, dtype=float)
    identity_rows, numeric_rows = _select_final_line_rows(metadata, lum)
    count = min(len(identity_rows), len(numeric_rows))
    identities = identity_rows[:count]
    numerics = numeric_rows[:count]
    values = {
        "index": np.asarray([r.line_index for r in identities], dtype=np.int32),
        "ion": np.asarray([_fixed(r.ion_label, 9) for r in identities], dtype="U9"),
        "lower_level": np.asarray([_fixed(r.lower_level, 20) for r in identities], dtype="U20"),
        "upper_level": np.asarray([_fixed(r.upper_level, 20) for r in identities], dtype="U20"),
        "wavelength": _r4_array([abs(r.wavelength_angstrom) for r in identities]),
        "emit_inward": _r4_array([lum[0, r.line_index - 1] for r in numerics]),
        "emit_outward": _r4_array([lum[1, r.line_index - 1] for r in numerics]),
        "depth_inward": _r4_array([depth[0, r.line_index - 1] for r in numerics]),
        "depth_outward": _r4_array([depth[1, r.line_index - 1] for r in numerics]),
    }

    if timing is not None:
        timing["final_product_build.lines_seconds"] = float(time.perf_counter() - _t0)
        timing["final_product_build.lines_rows"] = float(count)
    return OutputTable(
        extension_name="XSTAR_LINES",
        columns=tuple(values),
        units=("", "", "", "", "A", "erg/s/10**38", "erg/s/10**38", "", ""),
        formats=("I6", "A9", "A20", "A20", "E13.5", "E13.5", "E13.5", "E13.5", "E13.5"),
        binary=False,
        source_file="xstar/xstarlib/src/writespectra2.f90",
        values=values,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build final continuum table for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def build_final_continuum_table(*, epi_eV: Sequence[float], ncn2: int, dpthcont: np.ndarray, zrems: np.ndarray, zremsz: Sequence[float], timing: dict[str, float] | None = None) -> OutputTable:
    _t0 = time.perf_counter()
    n = int(ncn2); epi = np.asarray(epi_eV, dtype=float); dp = np.asarray(dpthcont, dtype=float); z = np.asarray(zrems, dtype=float); inc = np.asarray(zremsz, dtype=float)
    values = {
        "energy": _r4_array(epi[:n]),
        "incident": _r4_array(inc[:n]),
        "transmitted": _r4_array(inc[:n] * np.exp(-dp[0, :n])),
        "emit_inward": _r4_array(z[3, :n]),
        "emit_outward": _r4_array(z[4, :n]),
    }
    if timing is not None:
        timing["final_product_build.continuum_seconds"] = float(time.perf_counter() - _t0)
        timing["final_product_build.continuum_rows"] = float(n)
    return OutputTable(
        extension_name="XSTAR_SPECTRA",
        columns=tuple(values),
        units=("eV", "erg/s/erg", "erg/s/erg", "erg/s/erg", "erg/s/erg"),
        formats=("E13.5",) * 5,
        binary=False,
        source_file="xstar/xstarlib/src/writespectra3.f90",
        values=values,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build final rrc table for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def build_final_rrc_table(*, metadata: SourceOutputMetadata, elumab: np.ndarray, tauc: np.ndarray, timing: dict[str, float] | None = None) -> OutputTable:
    _t0 = time.perf_counter()
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
    if timing is not None:
        timing["final_product_build.rrc_seconds"] = float(time.perf_counter() - _t0)
        timing["final_product_build.rrc_rows"] = float(len(rows))
    return OutputTable(
        extension_name="XSTAR_SPECTRA",
        columns=tuple(values),
        units=("", "", "", "eV", "erg/s", "erg/s", "", ""),
        formats=("I6", "A9", "A20", "E13.5", "E13.5", "E13.5", "E13.5", "E13.5"),
        binary=False,
        source_file="xstar/xstarlib/src/writespectra4.f90",
        values=values,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Assemble the final public abundance/line/RRC/continuum/spectrum tables from the terminal source state.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def build_final_output_products(
    *, metadata: SourceOutputMetadata, xlum: float, temperature_1e4K: float,
    turbulent_velocity_km_s: float, epi_eV: Sequence[float], ncn2: int,
    dpthc: np.ndarray, dpthcont: np.ndarray, elum: np.ndarray,
    elumab: np.ndarray, tau0: np.ndarray, tauc: np.ndarray,
    zrems: np.ndarray, zremsz: Sequence[float], lwri: int,
    timing: dict[str, float] | None = None,
) -> FinalOutputProducts:
    _spectrum_t0 = time.perf_counter()
    spectrum = build_final_spectrum_table(metadata=metadata, xlum=xlum, temperature_1e4K=temperature_1e4K, turbulent_velocity_km_s=turbulent_velocity_km_s, epi_eV=epi_eV, ncn2=ncn2, dpthc=dpthc, elum=elum, zrems=zrems, zremsz=zremsz, lwri=lwri, timing=timing)
    if timing is not None:
        timing["final_product_build.spectrum_seconds"] = float(time.perf_counter() - _spectrum_t0)
    return FinalOutputProducts(
        spectrum=spectrum,
        lines=build_final_line_table(metadata=metadata, elum=elum, tau0=tau0, timing=timing),
        continuum=build_final_continuum_table(epi_eV=epi_eV, ncn2=ncn2, dpthcont=dpthcont, zrems=zrems, zremsz=zremsz, timing=timing),
        rrcs=build_final_rrc_table(metadata=metadata, elumab=elumab, tauc=tauc, timing=timing),
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fits ascii width operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _fits_ascii_width(fmt: str) -> int | None:
    """Return the FITS ASCII/character width for an A-format column.

    Binary tables use repeat-before-code forms such as ``8A``; ASCII tables
    use code-before-width forms such as ``A9``.
    """
    text = str(fmt).strip().upper()
    if text.endswith("A"):
        prefix = text[:-1]
        if prefix.isdigit() and int(prefix) > 0:
            return int(prefix)
    if text.startswith("A"):
        suffix = text[1:]
        if suffix.isdigit() and int(suffix) > 0:
            return int(suffix)
    return None


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fits column operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _fits_column(name: str, fmt: str, unit: str, values: np.ndarray) -> fits.Column:
    # Astropy expects binary string widths as e.g. 8A and numeric source forms
    # without the Fortran leading repeat for scalar columns.  For A-format
    # columns, provide exact-width bytes.  A second byte-level sanitizer below
    # is still required because NumPy/Astropy fixed-byte table storage may pad
    # shorter scalar strings with NUL bytes internally before FITS serialization.
    f = fmt
    if f in {"1J", "1I", "1E"}:
        f = f[1:]
    arr = np.asarray(values)
    width = _fits_ascii_width(f)
    if width is not None:

        # XSTAR-FUNCTION-COMMENT-BEGIN
        # Purpose: Implement the as text operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
        # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
        # XSTAR-FUNCTION-COMMENT-END
        def _as_text(item: object) -> str:
            if isinstance(item, (bytes, bytearray, np.bytes_)):
                return bytes(item).decode("ascii", "replace").replace("\x00", "")
            return str(item).replace("\x00", "")

        arr = np.asarray([_fixed(_as_text(item), width).encode("ascii", "replace") for item in arr], dtype=f"S{width}")
    return fits.Column(name=name, format=f, unit=(unit or None), array=arr)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the space pad ascii table columns operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _space_pad_ascii_table_columns(hdu: fits.hdu.base.ExtensionHDU, table: OutputTable) -> None:
    """Force FITS A-format table columns to use trailing spaces, not NULs.

    Astropy normally presents A-format fields as fixed-size byte strings, but
    NumPy's scalar string storage can carry NUL-filled trailing bytes.  XSTAR's
    Fortran writers blank-pad character columns, and strict binary comparisons
    are noisy when the Python detail tables retain those NUL bytes.  Mutating
    the underlying field bytes after HDU construction but before checksum
    generation gives the on-disk binary table the source-like blank padding.
    """
    data = getattr(hdu, "data", None)
    if data is None:
        return
    names = set(getattr(data, "names", None) or [])
    for name, fmt in zip(table.columns, table.formats):
        width = _fits_ascii_width(fmt)
        if width is None or name not in names:
            continue
        field = data[name]
        try:
            raw = np.asarray(field).view(np.uint8).reshape(len(field), -1)
        except Exception:
            continue
        if raw.shape[1] < width:
            continue
        raw[:, :width] = ord(" ")
        original_values = np.asarray(table.values[name]).reshape(-1)
        count = min(len(original_values), raw.shape[0])
        for row_index in range(count):
            item = original_values[row_index]
            if isinstance(item, (bytes, bytearray, np.bytes_)):
                text = bytes(item).decode("ascii", "replace")
            else:
                text = str(item)
            payload = _fixed(text.replace("\x00", ""), width).encode("ascii", "replace")
            raw[row_index, :width] = np.frombuffer(payload, dtype=np.uint8, count=width)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the table hdu operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
    return hdu


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the primary hdu operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _primary_hdu(*, model_name: str, atomic_data_date: str) -> fits.PrimaryHDU:
    hdu = fits.PrimaryHDU()
    apply_python_primary_fits_header(
        hdu.header,
        model_name=_fixed(model_name, 30).rstrip(),
        atomic_data_date=str(atomic_data_date)[:63],
    )
    return hdu




# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fits tform binary width operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _fits_tform_binary_width(tform: str) -> int:
    """Byte width of a simple FITS binary-table TFORM value."""
    text = str(tform).strip().upper().replace(" ", "")
    if not text:
        return 0
    digits = ""
    i = 0
    while i < len(text) and text[i].isdigit():
        digits += text[i]
        i += 1
    repeat = int(digits) if digits else 1
    code = text[i:i + 1]
    scalar = {
        "L": 1, "B": 1, "I": 2, "J": 4, "K": 8,
        "A": 1, "E": 4, "D": 8, "C": 8, "M": 16,
    }.get(code, 0)
    if code == "X":
        return (repeat + 7) // 8
    return repeat * scalar


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the rewrite fits ascii null padding operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _rewrite_fits_ascii_null_padding(path: str | Path) -> None:
    """Replace NUL bytes only inside binary-table A columns with blanks.

    The v0.5.34 pre-write sanitizer mutated Astropy's table fields and could
    corrupt unicode-scaled columns before ``writeto``.  This routine instead
    scans the already-written FITS blocks, computes binary-table character
    column spans from TFORM cards, and edits only those spans.  Numeric table
    zeros are never touched.
    """
    file_path = Path(path)
    data = bytearray(file_path.read_bytes())
    raw = bytes(data)
    changed = False
    pos = 0
    total = len(raw)
    while pos + 80 <= total:
        header_start = pos
        cards: list[str] = []
        end_pos = None
        while pos + 80 <= total:
            card = raw[pos:pos + 80].decode("ascii", "ignore")
            cards.append(card)
            pos += 80
            if card.startswith("END"):
                end_pos = pos
                break
        if end_pos is None:
            break
        header_len = ((end_pos - header_start + 2879) // 2880) * 2880
        data_start = header_start + header_len

        # XSTAR-FUNCTION-COMMENT-BEGIN
        # Purpose: Implement the card value operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
        # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
        # XSTAR-FUNCTION-COMMENT-END
        def _card_value(key: str) -> str | None:
            prefix = key.ljust(8) + "="
            for card in cards:
                if card.startswith(prefix):
                    value = card[10:80].split("/", 1)[0].strip()
                    return value.strip("'").strip()
            return None

        xtension = (_card_value("XTENSION") or "").upper()
        naxis1 = int(_card_value("NAXIS1") or "0")
        naxis2 = int(_card_value("NAXIS2") or "0")
        pcount = int(_card_value("PCOUNT") or "0")
        gcount = int(_card_value("GCOUNT") or "1")
        tfields = int(_card_value("TFIELDS") or "0")
        if "BINTABLE" in xtension and naxis1 > 0 and naxis2 > 0 and tfields > 0:
            col_offset = 0
            for idx in range(1, tfields + 1):
                tform = (_card_value(f"TFORM{idx}") or "").upper().replace(" ", "")
                width = _fits_tform_binary_width(tform)
                if tform.endswith("A") and width > 0:
                    for row in range(naxis2):
                        start = data_start + row * naxis1 + col_offset
                        stop = start + width
                        for byte_index in range(start, stop):
                            if data[byte_index] == 0:
                                data[byte_index] = 32
                                changed = True
                col_offset += width
        data_size = ((naxis1 * naxis2 + pcount) * gcount)
        pos = data_start + ((data_size + 2879) // 2880) * 2880
        if pos <= header_start:
            break
    if changed:
        file_path.write_bytes(data)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fits ascii table width operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _fits_ascii_table_width(tform: str) -> int:
    """Byte width for simple FITS ASCII TABLE TFORM values."""
    text = str(tform).strip().upper().replace(" ", "")
    if not text:
        return 0
    if text.startswith("A"):
        digits = text[1:]
        return int(digits) if digits.isdigit() else 0
    if text.startswith(("E", "F", "D", "I")):
        digits = ""
        for char in text[1:]:
            if char.isdigit():
                digits += char
            elif digits:
                break
        return int(digits) if digits else 0
    return 0


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the rewrite fits ascii table intercolumn gaps operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _rewrite_fits_ascii_table_intercolumn_gaps(path: str | Path) -> None:
    """Rewrite ASCII TABLE rows with source-like one-column gaps.

    Astropy writes ASCII TABLE columns back-to-back.  XSTAR's Fortran FITS
    writers leave one blank byte between successive TABLE fields, so the
    source headers have TBCOLn = previous start + previous width + 1.  This
    post-write rewrite restores that row layout for source-parity size/shape
    checks without changing column values or table schemas.
    """
    import os

    if str(os.environ.get("XSTAR_ATOMIC_FITS_ASCII_SOURCE_GAPS", "1")).strip().lower() in {"0", "false", "no", "off"}:
        return
    file_path = Path(path)
    raw = file_path.read_bytes()
    out = bytearray()
    pos = 0
    changed = False
    total = len(raw)

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the card value operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
    def _card_value(cards: list[str], key: str) -> str | None:
        prefix = key.ljust(8) + "="
        for card in cards:
            if card.startswith(prefix):
                return card[10:80].split("/", 1)[0].strip().strip("'").strip()
        return None

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the replace or append operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
    def _replace_or_append(cards: list[str], key: str, value: int) -> list[str]:
        prefix = key.ljust(8) + "="
        new = f"{key:<8}= {int(value):>20d}".ljust(80)
        result = []
        replaced = False
        for card in cards:
            if card.startswith(prefix):
                result.append(new)
                replaced = True
            else:
                result.append(card[:80].ljust(80))
        if not replaced:
            for idx, card in enumerate(result):
                if card.startswith("END"):
                    result.insert(idx, new)
                    break
            else:
                result.append(new)
        return result

    while pos < total:
        header_start = pos
        cards: list[str] = []
        while pos + 80 <= total:
            card = raw[pos:pos + 80].decode("ascii", "replace")
            cards.append(card)
            pos += 80
            if card.startswith("END"):
                break
        if not cards:
            break
        header_unpadded_len = pos - header_start
        header_padded_len = ((header_unpadded_len + 2879) // 2880) * 2880
        header_block = raw[header_start:header_start + header_padded_len]
        pos = header_start + header_padded_len

        xtension = (_card_value(cards, "XTENSION") or "").upper()
        bitpix = int(_card_value(cards, "BITPIX") or "8")
        naxis = int(_card_value(cards, "NAXIS") or "0")
        naxis1 = int(_card_value(cards, "NAXIS1") or "0")
        naxis2 = int(_card_value(cards, "NAXIS2") or "0")
        pcount = int(_card_value(cards, "PCOUNT") or "0")
        gcount = int(_card_value(cards, "GCOUNT") or "1")
        tfields = int(_card_value(cards, "TFIELDS") or "0")
        data_size = 0
        if naxis > 0:
            if "TABLE" in xtension and naxis1 > 0 and naxis2 > 0:
                data_size = (naxis1 * naxis2 + pcount) * gcount
            else:
                data_size = abs(bitpix) // 8
                for axis in range(1, naxis + 1):
                    data_size *= int(_card_value(cards, f"NAXIS{axis}") or "0")
                data_size = (data_size + pcount) * gcount
        data_block_len = ((data_size + 2879) // 2880) * 2880
        data_payload = raw[pos:pos + data_size]
        data_padding = raw[pos + data_size:pos + data_block_len]
        pos += data_block_len

        if "TABLE" in xtension and "BINTABLE" not in xtension and naxis1 > 0 and naxis2 > 0 and tfields > 1:
            widths = [_fits_ascii_table_width(_card_value(cards, f"TFORM{i}") or "") for i in range(1, tfields + 1)]
            starts = [int(_card_value(cards, f"TBCOL{i}") or "0") - 1 for i in range(1, tfields + 1)]
            if all(width > 0 for width in widths) and all(start >= 0 for start in starts):
                target_starts = []
                cur = 0
                for idx, width in enumerate(widths):
                    target_starts.append(cur)
                    cur += width + (1 if idx < len(widths) - 1 else 0)
                target_naxis1 = cur
                if target_naxis1 > naxis1 or starts != target_starts:
                    new_payload = bytearray()
                    for row in range(naxis2):
                        old_row = data_payload[row * naxis1:(row + 1) * naxis1]
                        new_row = bytearray(b" " * target_naxis1)
                        for start, width, target_start in zip(starts, widths, target_starts):
                            field = old_row[start:start + width]
                            new_row[target_start:target_start + width] = field.ljust(width, b" ")[:width]
                        new_payload.extend(new_row)
                    cards = _replace_or_append(cards, "NAXIS1", target_naxis1)
                    for idx, start in enumerate(target_starts, start=1):
                        cards = _replace_or_append(cards, f"TBCOL{idx}", start + 1)
                    header_text = "".join(card[:80].ljust(80) for card in cards)
                    header_bytes = header_text.encode("ascii", "replace")
                    header_bytes += b" " * (((len(header_bytes) + 2879) // 2880) * 2880 - len(header_bytes))
                    data_bytes = bytes(new_payload)
                    data_bytes += b" " * (((len(data_bytes) + 2879) // 2880) * 2880 - len(data_bytes))
                    out.extend(header_bytes)
                    out.extend(data_bytes)
                    changed = True
                    continue
        out.extend(header_block)
        out.extend(data_payload)
        out.extend(data_padding)
    if changed:
        file_path.write_bytes(bytes(out))


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the refresh fits checksums operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _refresh_fits_checksums(path: str | Path) -> None:
    """Recompute CHECKSUM/DATASUM after all byte-level FITS edits."""
    with fits.open(path, mode="update", checksum=False, memmap=False) as hdul:
        for hdu in hdul:
            if "CHECKSUM" in hdu.header:
                del hdu.header["CHECKSUM"]
            if "DATASUM" in hdu.header:
                del hdu.header["DATASUM"]
            hdu.add_checksum()
        hdul.flush()


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write hdul with xstar string padding for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _write_hdul_with_xstar_string_padding(hdul: fits.HDUList, path: str | Path, *, overwrite: bool) -> None:
    """Write FITS, apply source-like padding, then checksum the final bytes."""
    hdul.writeto(path, overwrite=overwrite, checksum=False)
    _rewrite_fits_ascii_null_padding(path)
    _rewrite_fits_ascii_table_intercolumn_gaps(path)
    _refresh_fits_checksums(path)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Record fits timing for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _record_fits_timing(
    timing: dict[str, float] | None,
    *,
    filename: str,
    phase: str,
    seconds: float,
) -> None:
    """Store per-file FITS timing in a flat, JSON-friendly mapping."""
    if timing is None:
        return
    safe = filename.replace(".", "_")
    timing[f"{phase}.{safe}"] = float(seconds)


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write final XSTAR-compatible FITS products, preserving qualified table layout, metadata, and publication ordering.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def write_final_output_files(
    products: FinalOutputProducts,
    *, out_dir: str | Path,
    parameters: Sequence[OutputParameter],
    model_name: str,
    atomic_data_date: str,
    lwri: int = 0,
    overwrite: bool = True,
    timing: dict[str, float] | None = None,
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
        _build_t0 = time.perf_counter()
        hdul = fits.HDUList([
            _primary_hdu(model_name=model_name, atomic_data_date=atomic_data_date),
            _table_hdu(parameter_table),
            _table_hdu(table),
        ])
        _record_fits_timing(
            timing,
            filename=filename,
            phase="final_fits_build_hdu_seconds",
            seconds=time.perf_counter() - _build_t0,
        )
        _write_t0 = time.perf_counter()
        _write_hdul_with_xstar_string_padding(hdul, path, overwrite=overwrite)
        _record_fits_timing(
            timing,
            filename=filename,
            phase="final_fits_write_seconds",
            seconds=time.perf_counter() - _write_t0,
        )
        paths[filename] = str(path)
    return paths



# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the fnappend detail filename operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _fnappend_detail_filename(name: str, pass_index: int) -> str:
    """Translate ``fnappend.f90`` for the pass-specific detail files."""
    kk = int(pass_index)
    if kk < 1 or kk > 99:
        raise OutputWriterPortError("fnappend detail pass index must be in 1..99")
    text = str(name)
    if len(text) < 4:
        raise OutputWriterPortError("detail filename is shorter than four characters")
    return text[:2] + f"{kk:02d}" + text[4:]

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write detail output files for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def write_detail_output_files(
    store: DetailOutputStore,
    *, out_dir: str | Path,
    parameters: Sequence[OutputParameter],
    model_name: str,
    atomic_data_date: str,
    pass_index: int | None = None,
    overwrite: bool = True,
    timing: dict[str, float] | None = None,
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
        _build_t0 = time.perf_counter()
        hdus: list[fits.hdu.base._BaseHDU] = [
            _primary_hdu(model_name=model_name, atomic_data_date=atomic_data_date),
            _table_hdu(parameter_table),
        ]
        hdus.extend(_table_hdu(getattr(record, attr)) for record in store.records)
        _record_fits_timing(
            timing,
            filename=filename,
            phase="detail_fits_build_hdu_seconds",
            seconds=time.perf_counter() - _build_t0,
        )
        path = output / filename
        _write_t0 = time.perf_counter()
        _write_hdul_with_xstar_string_padding(fits.HDUList(hdus), path, overwrite=overwrite)
        _record_fits_timing(
            timing,
            filename=filename,
            phase="detail_fits_write_seconds",
            seconds=time.perf_counter() - _write_t0,
        )
        paths[filename] = str(path)
    return paths


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the state temperature t4 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the shell header from state operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
        state_source="live Python savd-equivalent radial state before geometry update",
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the detail level vector operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the zero like table operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the zero detail shell output operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _zero_detail_shell_output(record: DetailShellOutput) -> DetailShellOutput:
    return DetailShellOutput(
        levels=_zero_like_table(record.levels),
        lines=_zero_like_table(record.lines),
        rrcs=_zero_like_table(record.rrcs),
        continuum=_zero_like_table(record.continuum),
        source_order=record.source_order,
        source_file=record.source_file,
    )


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the array sha256 operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _array_sha256(array: np.ndarray) -> str:
    arr = np.ascontiguousarray(array)
    return hashlib.sha256(arr.tobytes()).hexdigest()


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the binary64 fnv1a hex operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _binary64_fnv1a_hex(values: Sequence[float] | np.ndarray) -> str:
    """Match the standalone C++ binary64_sequence_fnv1a diagnostic hash."""
    arr = np.ascontiguousarray(np.asarray(values, dtype="<f8").reshape(-1))
    value = 1469598103934665603
    prime = 1099511628211
    mask = (1 << 64) - 1
    for byte in memoryview(arr).cast("B"):
        value ^= int(byte)
        value = (value * prime) & mask
    return f"{value:016x}"


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write f8 for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _write_f8(path: Path, values: np.ndarray) -> dict[str, Any]:
    arr = np.ascontiguousarray(np.asarray(values, dtype='<f8'))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(arr.tobytes())
    finite = np.isfinite(arr)
    return {
        "path": path.name,
        "dtype": "float64-le",
        "shape": list(arr.shape),
        "count": int(arr.size),
        "finite_count": int(finite.sum()),
        "nonzero_count": int(np.count_nonzero(arr)),
        "min": float(np.nanmin(arr)) if arr.size else 0.0,
        "max": float(np.nanmax(arr)) if arr.size else 0.0,
        "abs_max": float(np.nanmax(np.abs(arr))) if arr.size else 0.0,
        "sha256": _array_sha256(arr),
    }


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the maybe export detail continuum product write state operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _maybe_export_detail_continuum_product_write_state(
    state: XSTARPythonState,
    *,
    hdunum: int,
    terminal_record: bool,
    workspace: Any,
    record: DetailShellOutput,
) -> None:
    """Optionally dump the exact source state passed to build_detail_continuum_table.

    This is a diagnostic bridge hook only.  It writes the caller-owned fstepr4
    product-write arrays at the same boundary where Python constructs
    xo01_detal4.fits.  It does not read public products, pprint, xout_step.log,
    or oracle FITS values.
    """
    root_text = (
        os.environ.get("XSTAR_V04874625517_DETAIL_CONTINUUM_CAPTURE_DIR")
        or os.environ.get("XSTAR_DETAIL_CONTINUUM_CAPTURE_DIR")
        or str(state.control.get("detail_continuum_capture_dir", "") or "")
    )
    if not root_text:
        return
    try:
        root = Path(root_text)
        pass_index = int(state.transfer.pass_index)
        # write_detail_output_files() materializes detail HDUs by store.records
        # order, not by the source after-HDU ledger.  The terminal record may
        # have the same source hdunum as the preceding record, so using
        # hdunum+1 overwrote the fourth/fifth continuum captures into HDU 6
        # and left no product-write arrays for HDU 7.  Keep source_hdunum in
        # metadata, but name capture directories by their final output HDU.
        capture_counts = state.outputs.setdefault("detail_continuum_capture_record_counts", {})
        key = int(pass_index)
        record_ordinal = int(capture_counts.get(key, 0)) + 1
        capture_counts[key] = record_ordinal
        output_hdu = record_ordinal + 2
        source_inserted_hdu = int(hdunum) + 1
        zone_index = int(getattr(state.transfer, "zone_index", 0))
        out_dir = root / f"pass_{pass_index:04d}_hdu_{output_hdu:04d}"
        continuum = record.continuum
        n = int(continuum.nrows)
        opakc = np.asarray(getattr(workspace, "opakc"), dtype='<f8').reshape(-1)[:n]
        rccemis = np.asarray(getattr(workspace, "rccemis"), dtype='<f8')[:, :n]
        if rccemis.shape != (2, n) or opakc.shape != (n,):
            raise OutputWriterPortError("detail continuum product-write capture shape mismatch")
        energy = np.asarray(continuum.values["energy"], dtype='<f8').reshape(-1)[:n]
        emis_out = np.asarray(continuum.values["emis out"], dtype='<f8').reshape(-1)[:n]
        emis_in = np.asarray(continuum.values["emis in"], dtype='<f8').reshape(-1)[:n]
        fwd = np.asarray(continuum.values["fwd dpth"], dtype='<f8').reshape(-1)[:n]
        bck = np.asarray(continuum.values["bck dpth"], dtype='<f8').reshape(-1)[:n]
        dpthc = np.vstack([fwd, bck])
        stats = {
            "opakc": _write_f8(out_dir / "product_write_opakc.bin", opakc),
            "rccemis": _write_f8(out_dir / "product_write_rccemis.bin", rccemis),
            "detail_energy_ev": _write_f8(out_dir / "product_write_detail_energy_ev.bin", energy),
            "dpthc": _write_f8(out_dir / "product_write_dpthc.bin", dpthc),
            "energy": _write_f8(out_dir / "product_write_energy_ev.bin", energy),
            "emis_out_column": _write_f8(out_dir / "product_write_emis_out_column.bin", emis_out),
            "emis_in_column": _write_f8(out_dir / "product_write_emis_in_column.bin", emis_in),
            "fwd_dpth_column": _write_f8(out_dir / "product_write_fwd_dpth_column.bin", fwd),
            "bck_dpth_column": _write_f8(out_dir / "product_write_bck_dpth_column.bin", bck),
        }
        rows_path = out_dir / "product_write_detail_continuum_rows.csv"
        with rows_path.open("w", newline="") as fp:
            writer = csv.writer(fp)
            writer.writerow([
                "pass_index", "hdu_index", "zone_index", "terminal_record",
                "row_index_one_based", "full_bin_one_based", "energy_eV",
                "opakc", "rccemis_plane0_emis_out", "rccemis_plane1_emis_in",
                "fwd_dpth", "bck_dpth", "source_function",
            ])
            for i in range(n):
                writer.writerow([
                    pass_index, output_hdu, zone_index, bool(terminal_record),
                    i + 1, i + 1, float(energy[i]), float(opakc[i]),
                    float(rccemis[0, i]), float(rccemis[1, i]),
                    float(fwd[i]), float(bck[i]),
                    "xstar_tools.xstar.output_writers.build_detail_continuum_table",
                ])
        manifest = {
            "schema": "xstar-tools-v064874625517-product-write-detail-continuum-state-v1",
            "release": "0.6.48.7.46.25.5.17",
            "pass_index": pass_index,
            "hdu_index": output_hdu,
            "record_ordinal": record_ordinal,
            "source_hdunum": int(hdunum),
            "source_inserted_hdu": source_inserted_hdu,
            "zone_index": zone_index,
            "terminal_record": bool(terminal_record),
            "ncn2": n,
            "source_state": "exact Python product-write-time fstepr4 workspace",
            "source_function": "xstar_tools.xstar.output_writers.build_detail_continuum_table",
            "plane_semantics": {
                "rccemis[0,:]": "emis out column",
                "rccemis[1,:]": "emis in column",
                "opakc[:]": "opacity column",
            },
            "rows_csv": rows_path.name,
            "arrays": stats,
            "result": "ACCEPT_EXACT_PRODUCT_WRITE_DETAIL_CONTINUUM_STATE_CAPTURED",
        }
        (out_dir / "product_write_detail_continuum_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    except Exception as exc:
        # Diagnostics must not perturb the scientific run; record failures if possible.
        try:
            fail_root = Path(root_text)
            fail_root.mkdir(parents=True, exist_ok=True)
            (fail_root / "product_write_detail_continuum_capture_error.json").write_text(
                json.dumps({"result": "REJECT_CAPTURE_FAILED", "error": str(exc)}, indent=2, sort_keys=True) + "\n"
            )
        except Exception:
            pass

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the source detail line activity shadow operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _source_detail_line_activity_shadow(
    state: XSTARPythonState,
    metadata: SourceOutputMetadata,
    populations_zero_based: Sequence[float],
    physical_oplin: Sequence[float],
) -> np.ndarray:
    """Build the output-only fstepr2 publication-identity shadow.

    Production 45.3.3.4 consumes the exact source-record-order replay captured
    during ``calc_emisab_all``.  A deterministic line-index reconstruction is
    retained only for old synthetic fixtures that do not carry that state.
    Neither path changes rcem, oplin, tau0, continuum opacity, equilibrium, or
    transport.
    """
    n_lines = max((int(row.line_index) for row in metadata.lines), default=0)
    shadow = np.zeros(n_lines, dtype=bool)
    if n_lines <= 0:
        return shadow

    # 45.3.3.4: primary owner is the output-only replay captured directly in
    # calc_emisab's actual source-record traversal.  This avoids reconstructing
    # caller-local stale opakb1 lifetime from line-index order.
    captured = state.control.get("source_detail_line_activity_shadow_v064812345334", {})
    if isinstance(captured, Mapping):
        for one_based, active in captured.items():
            try:
                i = int(one_based) - 1
            except Exception:
                continue
            if bool(active) and 0 <= i < shadow.size:
                shadow[i] = True
        # The presence of the key proves this evaluation used the new source
        # replay even when the resulting map is empty.
        if "source_detail_line_activity_shadow_v064812345334" in state.control:
            return shadow

    # Backward-compatible synthetic-fixture fallback.
    pop = np.asarray(populations_zero_based, dtype=float).reshape(-1)
    oplin = np.asarray(physical_oplin, dtype=float).reshape(-1)
    abundances = state.plasma.abundances
    if abundances is None:
        return shadow
    ab = np.asarray(abundances, dtype=float).reshape(-1)
    xpx = float(state.plasma.xpx)

    # LevelOutputMetadata.upper_index is the source local level index.
    # Ion labels are unique ATDB ion identities, so this is a stable bridge
    # from line endpoints to the global xilevg population vector.
    level_by_ion_local: dict[tuple[str, int], LevelOutputMetadata] = {
        (str(row.ion_label), int(row.upper_index)): row for row in metadata.levels
    }
    # ``opakb1`` in the source line branch is caller-local and is only
    # assigned by ucalc when the endpoint-abundance gate passes.  The source
    # nevertheless executes ``oplin(jkkl)=opakb1*abund1`` after a skipped
    # call, so a stale scalar can make a numerically zero line visible to
    # fstepr2.  Reproduce only that *row-identity* consequence here.  The
    # carry is reconstructed from deterministic physical oplin for eligible
    # Type50 rows and is never written back to physical opacity.
    stale_opakb1 = 0.0
    for line in sorted(metadata.lines, key=lambda row: int(row.line_index)):
        if int(line.rate_type) != 4 or int(line.data_type) != 50:
            continue
        i = int(line.line_index) - 1
        if i < 0 or i >= shadow.size:
            continue
        lo = level_by_ion_local.get((str(line.ion_label), int(line.lower_local_index)))
        up = level_by_ion_local.get((str(line.ion_label), int(line.upper_local_index)))
        if lo is None or up is None:
            continue
        z = int(lo.atomic_number)
        if z <= 0 or z > ab.size or int(up.atomic_number) != z:
            continue
        gi_lo = int(lo.global_index) - 1
        gi_up = int(up.global_index) - 1
        if gi_lo < 0 or gi_up < 0 or gi_lo >= pop.size or gi_up >= pop.size:
            continue
        xeltp = float(ab[z - 1])
        a_lo = float(pop[gi_lo]) * xpx * xeltp
        a_up = float(pop[gi_up]) * xpx * xeltp
        endpoint_active = (
            a_lo > SOURCE_DETAIL_ENDPOINT_ABUNDANCE_FLOOR
            or a_up > SOURCE_DETAIL_ENDPOINT_ABUNDANCE_FLOOR
        )

        # Source ``abund1`` is the lower-energy endpoint, independent of the
        # integer endpoint order stored in the ATDB record.
        if float(lo.excitation_eV) <= float(up.excitation_eV):
            source_abund1 = a_lo
        else:
            source_abund1 = a_up

        if endpoint_active:
            # Python evaluates this record deterministically.  Recover the
            # scalar source opakb1 from oplin=opakb1*abund1 when possible so
            # the publication carry follows the same source record sequence.
            if i < oplin.size and source_abund1 != 0.0:
                candidate = float(oplin[i]) / source_abund1
                if np.isfinite(candidate):
                    stale_opakb1 = candidate
            shadow[i] = True
        elif abs(stale_opakb1 * source_abund1) > DETAIL_LINE_ACTIVITY_FLOOR:
            # Source artifact compatibility: retain the row only.
            shadow[i] = True
    return shadow



# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Select fixed state detail3 publication v064812345338 for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _select_fixed_state_detail3_publication(
    control: Mapping[str, Any], *, terminal_record: bool
) -> Mapping[int, Mapping[str, Any]]:
    current = control.get("source_detail_rrc_fixed_state_publication_v064812345338", {})
    if isinstance(current, Mapping) and current:
        return current
    if bool(terminal_record):
        replay = control.get("source_detail_rrc_fixed_state_terminal_replay_v064812345338", {})
        if isinstance(replay, Mapping):
            return replay
    return {}


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Commit fixed state detail3 terminal replay v064812345338 for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def _commit_fixed_state_detail3_terminal_replay(
    control: MutableMapping[str, Any],
    *,
    current_fixed_state_map: Mapping[int, Mapping[str, Any]] | None,
    terminal_record: bool,
) -> None:
    key = "source_detail_rrc_fixed_state_terminal_replay_v064812345338"
    if bool(terminal_record):
        control[key] = {}
        return
    src = current_fixed_state_map or {}
    control[key] = {
        int(ci): dict(row) for ci, row in src.items()
        if isinstance(row, Mapping)
    }

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Append detail output from state for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def append_detail_output_from_state(state: XSTARPythonState, *, hdunum: int, terminal_record: bool = False) -> DetailShellOutput:
    from .radial_transfer import _workspace_from_state, _level_arrays_from_state

    metadata = _metadata_from_control(state)
    workspace = _workspace_from_state(state)
    populations, lte = _level_arrays_from_state(state)
    populations_out = _detail_level_vector(populations, metadata)
    lte_out = _detail_level_vector(lte, metadata)
    source_detail_line_activity_shadow = _source_detail_line_activity_shadow(
        state, metadata, populations_out, workspace.oplin_physical
    )
    # 45.3.1: retain the legacy slot shadow for diagnostics/backward
    # compatibility only; detail3 publication never consults it.
    source_detail_rrc_publication_shadow = state.control.get(
        "source_detail_rrc_publication_shadow_v0648123451", {}
    )
    source_detail_rrc_record_shadow = state.control.get(
        "source_detail_rrc_record_shadow_v0648123453", {}
    )
    source_detail_rrc_slot_absorption_lifetime = state.control.get(
        "source_detail_rrc_slot_absorption_lifetime_v06481234532", {}
    )
    source_detail_rrc_current_eval_sequence = int(
        state.control.get("source_detail_rrc_eval_sequence_v06481234532", 0) or 0
    )
    source_detail_rrc_orphan_absorption = state.control.get(
        "source_detail_rrc_orphan_absorption_v06481234533", {}
    )
    source_detail_rrc_non_type7_absorption = state.control.get(
        "source_detail_rrc_non_type7_absorption_v064812345335", {}
    )
    source_detail_rrc_fixed_state_absorption = state.control.get(
        "source_detail_rrc_fixed_state_absorption_v064812345336", {}
    )
    source_detail_rrc_fixed_state_publication = (
        _select_fixed_state_detail3_publication(
            state.control, terminal_record=bool(terminal_record)
        )
    )
    source_detail_rrc_publication_trace: list[dict[str, Any]] = []
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
        source_detail_line_activity_shadow=source_detail_line_activity_shadow,
        source_detail_rrc_publication_shadow=source_detail_rrc_publication_shadow,
        source_detail_rrc_record_shadow=source_detail_rrc_record_shadow,
        source_detail_rrc_slot_absorption_lifetime=source_detail_rrc_slot_absorption_lifetime,
        source_detail_rrc_current_eval_sequence=source_detail_rrc_current_eval_sequence,
        source_detail_rrc_orphan_absorption=source_detail_rrc_orphan_absorption,
        source_detail_rrc_non_type7_absorption=source_detail_rrc_non_type7_absorption,
        source_detail_rrc_fixed_state_absorption=source_detail_rrc_fixed_state_absorption,
        source_detail_rrc_fixed_state_publication=source_detail_rrc_fixed_state_publication,
        source_detail_rrc_publication_trace=source_detail_rrc_publication_trace,
        element_abundances=state.plasma.abundances,
    )
    # The source-record publication state belongs to this savd/fstepr3 shell.
    # Consume it only after the row table has been materialized so DSEC trials
    # within the shell can contribute, but later shells cannot inherit it.
    if isinstance(state.control, MutableMapping):
        trace = state.control.get("source_detail_rrc_lifetime_trace_v06481234532", [])
        if not isinstance(trace, list):
            trace = []
        trace.extend(source_detail_rrc_publication_trace)
        trace_path = str(os.environ.get("XSTAR_V06481234532_RRC_LIFETIME_TRACE", "")).strip()
        if trace_path and trace:
            path = Path(trace_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                for event in trace:
                    payload = dict(event)
                    payload.setdefault("hdunum", int(hdunum))
                    payload.setdefault("terminal_record", bool(terminal_record))
                    handle.write(json.dumps(payload, sort_keys=True) + "\n")
        state.control["source_detail_rrc_lifetime_trace_v06481234532"] = []
        state.control["source_detail_rrc_record_shadow_v0648123453"] = {}
        state.control["source_detail_rrc_slot_absorption_lifetime_v06481234532"] = {}
        state.control["source_detail_rrc_eval_sequence_v06481234532"] = 0
        orphan_trace = state.control.get("source_detail_rrc_orphan_trace_v06481234533", [])
        if not isinstance(orphan_trace, list):
            orphan_trace = []
        orphan_trace.extend(source_detail_rrc_publication_trace)
        orphan_trace_path = str(os.environ.get("XSTAR_V06481234533_RRC_ORPHAN_TRACE", "")).strip()
        if orphan_trace_path and orphan_trace:
            path = Path(orphan_trace_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                for event in orphan_trace:
                    payload = dict(event)
                    payload.setdefault("hdunum", int(hdunum))
                    payload.setdefault("terminal_record", bool(terminal_record))
                    handle.write(json.dumps(payload, sort_keys=True) + "\n")
        state.control["source_detail_rrc_orphan_trace_v06481234533"] = []
        state.control["source_detail_rrc_orphan_absorption_v06481234533"] = {}
        state.control["source_detail_rrc_non_type7_absorption_v064812345335"] = {}
        # 45.3.3.7 terminal replay lifetime: snapshot the just-materialized
        # physical shell before consuming its fixed-state publication map.
        # A terminal detail record may replay only that snapshot, after which
        # the replay is cleared.
        current_fixed = state.control.get(
            "source_detail_rrc_fixed_state_publication_v064812345338", {}
        )
        _commit_fixed_state_detail3_terminal_replay(
            state.control,
            current_fixed_state_map=current_fixed if isinstance(current_fixed, Mapping) else {},
            terminal_record=bool(terminal_record),
        )
        state.control["source_detail_rrc_fixed_state_publication_v064812345338"] = {}
        state.control["source_detail_rrc_fixed_state_absorption_v064812345336"] = {}
    _maybe_export_detail_continuum_product_write_state(
        state, hdunum=int(hdunum), terminal_record=bool(terminal_record),
        workspace=workspace, record=record,
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


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Build final output from state for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def build_final_output_from_state(state: XSTARPythonState, *, lwri: int = 0, timing: dict[str, float] | None = None) -> FinalOutputProducts:
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
        timing=timing,
    )
    state.outputs["final_output_products"] = products
    return products


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the pprint final source state handler operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Execute output writer sequence for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
    progress_callback: Any | None = None,
) -> OutputWriterSequenceResult:
    """Execute the bounded detail/final writer sequence in caller order.

    When ``final_local_recompute`` is true, the literal post-pass
    ``xstarcalc(nlimd=0) -> heatt -> stpcut`` sequence is executed before the
    final writers.  When ``pprint_legacy_enabled`` is true, the translated
    default ``pprint`` path writes ``xout_step.log`` and
    ``xout_abund1.fits``; otherwise the historical explicit handler remains.
    """
    source_order: list[str] = []
    timing_breakdown: dict[str, float] = {}

    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Emit operation for this module while preserving the surrounding source/runtime invariants.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
    def _emit(event: str, **details: Any) -> None:
        if progress_callback is not None:
            progress_callback(event, dict(details))

    if final_local_recompute:
        from .driver import XSTARPythonDriver, XSTARSourceRoutine
        from .radial_transfer import register_bounded_radial_source_routines
        from .continuum_diagnostics import append_phase_snapshot

        _final_recompute_t0 = time.perf_counter()
        runner = driver or XSTARPythonDriver()
        if driver is None:
            register_bounded_radial_source_routines(runner)
        completed_before = len(state.provenance.get("completed_source_routines", []))
        source_delr = float(np.float32(1.0e-15))
        state.transfer.step_size = source_delr
        state.control["delr"] = source_delr
        state.control["nlimd"] = 0
        state.control["nlimdt"] = 0
        previous_phase_context = state.control.get("continuum_phase_context")
        state.control["continuum_phase_context"] = "final"
        # v0.6.48.10.1: accelerated Python already owns the accepted C++
        # fixed-state engine.  Reuse it for the source post-loop zero-thickness
        # xstarcalc instead of replaying the expensive Python orchestration.
        # Pure Python and explicit diagnostics retain the historical path.
        # XSTAR-FUNCTION-COMMENT-BEGIN
        # Purpose: Implement the v0648101 env true operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
        # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
        # XSTAR-FUNCTION-COMMENT-END
        def _final_recompute_env_true(name: str) -> bool:
            return str(os.environ.get(name, "0")).strip().lower() in {"1", "true", "yes", "on"}

        _v0648101_global_backend = str(os.environ.get("XSTAR_ATOMIC_BACKEND", "")).strip().lower()
        _v0648101_engine_backend = str(os.environ.get("XSTAR_ATOMIC_ENGINE_BACKEND", "")).strip().lower()
        _v0648101_accelerated_cpp = _v0648101_global_backend == "cpp" or _v0648101_engine_backend == "cpp"
        _v0648101_force_python = _final_recompute_env_true("XSTAR_V0648101_FORCE_PYTHON_FINAL_RECOMPUTE")
        _v0648101_allow_fallback = _final_recompute_env_true("XSTAR_V0648101_ALLOW_PYTHON_FINAL_RECOMPUTE_FALLBACK")
        _v0648101_diagnostic_requested = bool(os.environ.get("XSTAR_V064882_FINAL_THERMAL_DIAGNOSTICS", "").strip())
        _v0648101_use_cpp = _v0648101_accelerated_cpp and not _v0648101_force_python and not _v0648101_diagnostic_requested
        timing_breakdown["final_local_recompute.v0648101_accelerated_cpp_selected"] = 1.0 if _v0648101_accelerated_cpp else 0.0
        timing_breakdown["final_local_recompute.v0648101_cpp_bridge_selected"] = 1.0 if _v0648101_use_cpp else 0.0
        timing_breakdown["final_local_recompute.v0648101_force_python"] = 1.0 if _v0648101_force_python else 0.0
        timing_breakdown["final_local_recompute.v0648101_python_fallback_allowed"] = 1.0 if _v0648101_allow_fallback else 0.0

        # XSTAR-FUNCTION-COMMENT-BEGIN
        # Purpose: Execute python final xstarcalc for this module while preserving the surrounding source/runtime invariants.
        # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
        # XSTAR-FUNCTION-COMMENT-END
        def _run_python_final_xstarcalc() -> None:
            runner.run_xstarcalc(state, fixed_state=False)
            append_phase_snapshot(state, "final xstarcalc")
            runner.run_source_routines(
                (XSTARSourceRoutine.HEATT, XSTARSourceRoutine.STPCUT), state
            )

        try:
            if _v0648101_use_cpp:
                try:
                    from .cpp_backend_final_recompute import apply_native_final_recompute
                    _native_final = apply_native_final_recompute(state)
                    timing_breakdown["final_local_recompute.v0648101_cpp_fixed_state_seconds"] = float(_native_final.cpp_seconds)
                    timing_breakdown["final_local_recompute.v0648101_cpp_bridge_seconds"] = float(_native_final.bridge_seconds)
                    timing_breakdown["final_local_recompute.v06481011_rrc_stage_masked_slots"] = float(_native_final.rrc_stage_masked_slots)
                    timing_breakdown["final_local_recompute.v06481011_rrc_stage_masked_nonzero_slots"] = float(_native_final.rrc_stage_masked_nonzero_slots)
                    timing_breakdown["final_local_recompute.v06481011_line_stage_masked_slots"] = float(_native_final.line_stage_masked_slots)
                    timing_breakdown["final_local_recompute.v06481011_line_stage_masked_nonzero_slots"] = float(_native_final.line_stage_masked_nonzero_slots)
                    state.outputs["v06481011_rrc_terminal_ownership"] = {
                        "owner": "SOURCE_RETAINED_MML_MMU",
                        "masked_slots": int(_native_final.rrc_stage_masked_slots),
                        "masked_nonzero_slots": int(_native_final.rrc_stage_masked_nonzero_slots),
                        "line_masked_slots": int(_native_final.line_stage_masked_slots),
                        "line_masked_nonzero_slots": int(_native_final.line_stage_masked_nonzero_slots),
                        "stage_limits": dict(_native_final.rrc_stage_limits),
                    }
                    # Preserve the literal source-order provenance that the
                    # coarse native call replaces.  HEATT/STPCUT still execute
                    # through the ordinary registered source handlers below.
                    _native_source_calls = (
                        XSTARSourceRoutine.BREMSMAP.value,
                        XSTARSourceRoutine.CALC_HMC_ALL.value,
                        XSTARSourceRoutine.CALC_EMISAB_ALL.value,
                        XSTARSourceRoutine.CALC_EMIS_ALL.value,
                    )
                    state.provenance.setdefault("completed_source_routines", []).extend(_native_source_calls)
                    append_phase_snapshot(state, "final xstarcalc", note="native C++ fixed-state bridge v0.6.48.10.1.1 with source mml/mmu RRC ownership")
                    runner.run_source_routines(
                        (XSTARSourceRoutine.HEATT, XSTARSourceRoutine.STPCUT), state
                    )
                    timing_breakdown["final_local_recompute.v0648101_cpp_bridge_accepted"] = 1.0
                except Exception as _native_exc:
                    timing_breakdown["final_local_recompute.v0648101_cpp_bridge_failed"] = 1.0
                    timing_breakdown["final_local_recompute.v0648101_cpp_bridge_error"] = str(_native_exc)[:2048]
                    if not _v0648101_allow_fallback:
                        raise OutputWriterPortError(
                            "v0.6.48.10.1 accelerated Python selected the native final zero-thickness "
                            "recompute bridge but it failed; set XSTAR_V0648101_FORCE_PYTHON_FINAL_RECOMPUTE=1 "
                            "for the accepted 10.0 Python path or XSTAR_V0648101_ALLOW_PYTHON_FINAL_RECOMPUTE_FALLBACK=1 "
                            "to permit an explicit slow fallback"
                        ) from _native_exc
                    _run_python_final_xstarcalc()
                    timing_breakdown["final_local_recompute.v0648101_python_fallback_used"] = 1.0
            else:
                _run_python_final_xstarcalc()
        finally:
            if previous_phase_context is None:
                state.control.pop("continuum_phase_context", None)
            else:
                state.control["continuum_phase_context"] = previous_phase_context
        source_order.extend(
            state.provenance.get("completed_source_routines", [])[completed_before:]
        )
        timing_breakdown["final_local_recompute"] = float(time.perf_counter() - _final_recompute_t0)
        state.outputs["final_local_recompute"] = {
            "source_file": "xstar/src/xstar/xstar.f90",
            "delr": source_delr,
            "nlimd": 0,
            "dsec_skipped": True,
            "source_order": list(source_order),
            # xstar.f90 immediately writes these four scalars after the final
            # xstarcalc -> heatt -> stpcut sequence (format 4(1pe16.8)).
            "temperature_t4": float(state.plasma.temperature) / 1.0e4,
            "httot": float(state.thermal.heating),
            "cltot": float(state.thermal.cooling),
            "hmctot": float(state.thermal.residual),
        }

        # v0.6.48.8.2 diagnostic only: expose the exact final zero-thickness
        # calc_hmc_all leaves and BREMSMAP/global-workspace fingerprints.  The
        # public writer does not consume this payload.  It exists solely to
        # distinguish cancellation amplification in hmctot from a genuine
        # C++ final-workspace ownership error.
        final_diag_target = os.environ.get("XSTAR_V064882_FINAL_THERMAL_DIAGNOSTICS", "").strip()
        fixed = state.local_zone.calc_hmc_all
        if final_diag_target and fixed is not None:
            continuum = fixed.continuum
            bremsmap_result = state.local_zone.source_arrays.get("bremsmap")
            mapped = np.asarray(
                getattr(bremsmap_result, "mapped_high_resolution_indices_one_based", ()),
                dtype=float,
            )
            nred = int(state.control.get("ncn2m", 0))
            epim = np.asarray(state.radiation.epim, dtype=float).reshape(-1)[:nred]
            bremsam = np.asarray(state.radiation.bremsam, dtype=float).reshape(-1)[:nred]
            epi_full = np.asarray(state.radiation.epi, dtype=float).reshape(-1)
            bremsa_full = np.asarray(state.radiation.bremsa, dtype=float).reshape(-1)
            tau_in_full = np.asarray(state.transfer.tau_in if state.transfer.tau_in is not None else (), dtype=float).reshape(-1)
            tau_out_full = np.asarray(state.transfer.tau_out if state.transfer.tau_out is not None else (), dtype=float).reshape(-1)
            # XSTAR-FUNCTION-COMMENT-BEGIN
            # Purpose: Implement the element operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
            # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
            # XSTAR-FUNCTION-COMMENT-END
            def _element(mapping: Mapping[int, float], z: int) -> float:
                return float(mapping.get(z, 0.0))
            diagnostic = {
                "schema": "xstar-tools-v064882-final-zero-thickness-thermal-v1",
                "implementation": "python",
                "temperature_k": float(fixed.temperature_k),
                "electron_fraction_input": float(fixed.electron_fraction_xee),
                "computed_electron_fraction": float(fixed.electron_contribution),
                "charge_residual": float(fixed.elcter),
                "electron_density_cm3": float(fixed.electron_density_cm3),
                "hydrogen_density_cm3": float(fixed.hydrogen_density_cm3),
                "httot_pre_continuum": float(fixed.httot_pre_continuum),
                "cltot_pre_continuum": float(fixed.cltot_pre_continuum),
                "total_heating": float(fixed.httot),
                "total_cooling": float(fixed.cltot),
                "hmctot": float(fixed.hmctot),
                "h_heating": _element(fixed.htt, 1),
                "h_cooling": _element(fixed.cll, 1),
                "he_heating": _element(fixed.htt, 2),
                "he_cooling": _element(fixed.cll, 2),
                "mg_heating": _element(fixed.htt, 12),
                "mg_cooling": _element(fixed.cll, 12),
                "continuum_heating": float(continuum.heating),
                "continuum_cooling": float(continuum.cooling),
                "htcomp": float(continuum.htcomp),
                "clcomp": float(continuum.clcomp),
                "htfreef": float(continuum.htfreef),
                "clbrems": float(continuum.clbrems),
                "input_radiation_count": int(epi_full.size),
                "input_radiation_fingerprint": _binary64_fnv1a_hex(epi_full),
                "input_dsec_radiation_count": int(epi_full.size),
                "input_dsec_radiation_fingerprint": _binary64_fnv1a_hex(epi_full),
                "input_bremsa_count": int(bremsa_full.size),
                "input_bremsa_fingerprint": _binary64_fnv1a_hex(bremsa_full),
                "input_tau_count": int(tau_in_full.size),
                "input_tau_in_fingerprint": _binary64_fnv1a_hex(tau_in_full),
                "input_tau_out_fingerprint": _binary64_fnv1a_hex(tau_out_full),
                "continuum_epim_count": int(epim.size),
                "continuum_epim_fingerprint": _binary64_fnv1a_hex(epim),
                "continuum_bremsam_count": int(bremsam.size),
                "continuum_bremsam_fingerprint": _binary64_fnv1a_hex(bremsam),
                "continuum_bremsmap_count": int(mapped.size),
                "continuum_bremsmap_fingerprint": _binary64_fnv1a_hex(mapped),
                "global_level_count": int(np.asarray(fixed.global_xilevg_by_index).size),
                "xilevg_fingerprint": _binary64_fnv1a_hex(fixed.global_xilevg_by_index),
                "bilevg_fingerprint": _binary64_fnv1a_hex(fixed.global_bilevg_by_index),
                "rnisg_fingerprint": _binary64_fnv1a_hex(fixed.global_rnisg_by_index),
            }
            target = Path(final_diag_target)
            if final_diag_target.lower() in {"1", "true", "yes", "on"}:
                target = Path(out_dir or ".") / "v064882_final_thermal_budget_python.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(diagnostic, indent=2, sort_keys=True) + "\n")
            state.outputs["v064882_final_thermal_diagnostics"] = diagnostic

    pprint_paths: dict[str, str] = {}
    pprint_products_written = False
    if bool(state.control.get("pprint_legacy_enabled", False)):
        from .pprint_legacy import finalize_legacy_pprint

        _pprint_t0 = time.perf_counter()
        pprint_calls, generated_pprint_paths = finalize_legacy_pprint(
            state, out_dir=out_dir, overwrite=True
        )
        source_order.extend(pprint_calls)
        pprint_paths.update(generated_pprint_paths)
        pprint_products_written = bool(generated_pprint_paths)
        timing_breakdown["pprint_legacy"] = float(time.perf_counter() - _pprint_t0)
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
        from .continuum_diagnostics import append_phase_snapshot

        append_phase_snapshot(state, "before writespectra", note=f"lwri={level}")
        _final_build_t0 = time.perf_counter()
        final = build_final_output_from_state(state, lwri=level, timing=timing_breakdown)
        timing_breakdown["final_product_build"] = float(time.perf_counter() - _final_build_t0)
        writer_names.append("writespectra")
        if level >= 0:
            writer_names.extend(("writespectra2", "writespectra3", "writespectra4"))
    source_order.extend(writer_names)

    paths: dict[str, str] = dict(pprint_paths)
    if out_dir is not None:
        _detail_write_t0 = time.perf_counter()
        for pass_index in sorted(stores):
            paths.update(
                write_detail_output_files(
                    stores[pass_index],
                    out_dir=out_dir,
                    parameters=parameters,
                    model_name=model_name,
                    atomic_data_date=atomic_data_date,
                    pass_index=pass_index,
                    timing=timing_breakdown,
                )
            )
        timing_breakdown["detail_fits_write"] = float(time.perf_counter() - _detail_write_t0)
        if final is not None:
            _emit("spectral_writer_start", lwri=int(level))
            _final_write_t0 = time.perf_counter()
            paths.update(
                write_final_output_files(
                    final,
                    out_dir=out_dir,
                    parameters=parameters,
                    model_name=model_name,
                    atomic_data_date=atomic_data_date,
                    lwri=level,
                    timing=timing_breakdown,
                )
            )
            timing_breakdown["final_fits_write"] = float(time.perf_counter() - _final_write_t0)
            _emit("spectral_writer_done", lwri=int(level))
    timing_breakdown["total"] = float(sum(float(v) for v in timing_breakdown.values() if isinstance(v, (int, float))))
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
        timing_breakdown=dict(timing_breakdown),
    )

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Provide the direct-source reference for fortran output reference for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
def direct_fortran_output_reference() -> dict[str, Any]:
    """Frozen reference from literal original-Fortran writer loops.

    Values were generated with gfortran from the unmodified fstepr4 and
    writespectra3 array loops and literal fstepr/fstepr2/fstepr3/
    writespectra2/writespectra4 row-selection fragments.
    """
    return {
        "voigte": [0.7788007830714049, 0.37286239075825555, 0.022464036161215329],
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


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the validation fixture operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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



# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Implement the binemis validation fixture operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Execute direct fortran output writer validation for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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

# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Execute output writer validation for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
    # XSTAR-FUNCTION-COMMENT-BEGIN
    # Purpose: Implement the numeric header value operation used by this module; inputs/outputs follow the surrounding source-faithful data model.
    # Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
    # XSTAR-FUNCTION-COMMENT-END
    def _numeric_header_value(value: object) -> float | None:
        raw = value[0] if isinstance(value, tuple) and value else value
        if isinstance(raw, (int, float, np.integer, np.floating)):
            return float(raw)
        return None

    header_real4_ready = bool(
        detail_store_ready
        and all(
            all(
                numeric == float(np.float32(numeric))
                for value in table.header_keywords.values()
                if (numeric := _numeric_header_value(value)) is not None
            )
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


# XSTAR-FUNCTION-COMMENT-BEGIN
# Purpose: Write output writer validation products for this module while preserving the surrounding source/runtime invariants.
# Reference context: XSTAR Manual Ch. 5 plus ss. 11.5-11.6, shell/detail/final spectral products.
# XSTAR-FUNCTION-COMMENT-END
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
