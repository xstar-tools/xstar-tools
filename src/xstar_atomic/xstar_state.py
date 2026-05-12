"""Live XSTAR-state containers used for Python output recreation.

The classes in this module define the *state that Python must own* before it
can recreate XSTAR detail and summary FITS products from input parameters.  They
are deliberately lightweight containers: v0.3.150 does not claim to solve the
full XSTAR problem, but it makes the required live arrays explicit and gives
future solver/FITS-writer work a single source of truth.

The key arrays mirror the quantities passed through the XSTAR Fortran path
around ``calc_hmc_ion.f90`` and ``ucalc.f90``:

* ``epi(:)``: continuum energy grid;
* ``bremsa(:)`` and ``bremsint(:)``: local radiation field and its integral;
* ``tau0(1:2,line)``: inward/outward line optical depths;
* ``tauc/dpthc(1:2,continuum)``: continuum optical depths;
* ``cfrac`` and ``vturbi``: geometry/turbulence controls;
* zone-local temperature/electron density, ion fractions, and level populations.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


@dataclass
class XSTARContinuumState:
    """Continuum-grid state for one XSTAR radial zone.

    Attributes are named after the XSTAR arrays whenever practical.  ``tauc_*``
    and ``dpthc_*`` are both carried because XSTAR uses depth arrays internally
    and the detail-output FITS files expose forward/backward depth quantities.
    """

    epi: List[float] = field(default_factory=list)
    bremsa: List[float] = field(default_factory=list)
    bremsint: List[float] = field(default_factory=list)
    tauc_in: List[float] = field(default_factory=list)
    tauc_out: List[float] = field(default_factory=list)
    dpthc_forward: List[float] = field(default_factory=list)
    dpthc_backward: List[float] = field(default_factory=list)
    continuum_opacity: List[float] = field(default_factory=list)
    continuum_emissivity: List[float] = field(default_factory=list)
    source: str = "not_computed"

    def n_energy(self) -> int:
        """Return the number of continuum grid points currently stored."""
        return len(self.epi)

    def missing_fields(self) -> List[str]:
        """Return required continuum fields that are still empty."""
        missing: List[str] = []
        for name in ["epi", "bremsa", "bremsint", "tauc_in", "tauc_out"]:
            if not getattr(self, name):
                missing.append(name)
        return missing

    def as_dict(self) -> Dict[str, Any]:
        return {
            "epi": list(self.epi),
            "bremsa": list(self.bremsa),
            "bremsint": list(self.bremsint),
            "tauc_in": list(self.tauc_in),
            "tauc_out": list(self.tauc_out),
            "dpthc_forward": list(self.dpthc_forward),
            "dpthc_backward": list(self.dpthc_backward),
            "continuum_opacity": list(self.continuum_opacity),
            "continuum_emissivity": list(self.continuum_emissivity),
            "source": self.source,
            "n_energy": self.n_energy(),
            "missing_fields": self.missing_fields(),
        }


@dataclass
class XSTARLineTransferState:
    """Line-transfer state for one XSTAR radial zone.

    ``tau0_in`` and ``tau0_out`` represent ``tau0(1,line)`` and
    ``tau0(2,line)`` in XSTAR's population/line-transfer path.  ``ptmp1`` and
    ``ptmp2`` are optional cached escape-probability combinations used by the
    type-50 branch.
    """

    line_ids: List[str] = field(default_factory=list)
    wavelengths_A: List[float] = field(default_factory=list)
    tau0_in: List[float] = field(default_factory=list)
    tau0_out: List[float] = field(default_factory=list)
    ptmp1: List[float] = field(default_factory=list)
    ptmp2: List[float] = field(default_factory=list)
    line_opacity: List[float] = field(default_factory=list)
    line_emissivity: List[float] = field(default_factory=list)
    source: str = "not_computed"

    def n_lines(self) -> int:
        """Return the number of line rows currently stored."""
        return max(len(self.line_ids), len(self.wavelengths_A), len(self.tau0_in), len(self.tau0_out))

    def missing_fields(self) -> List[str]:
        """Return required line-transfer fields that are still empty."""
        missing: List[str] = []
        for name in ["tau0_in", "tau0_out"]:
            if not getattr(self, name):
                missing.append(name)
        return missing

    def as_dict(self) -> Dict[str, Any]:
        return {
            "line_ids": list(self.line_ids),
            "wavelengths_A": list(self.wavelengths_A),
            "tau0_in": list(self.tau0_in),
            "tau0_out": list(self.tau0_out),
            "ptmp1": list(self.ptmp1),
            "ptmp2": list(self.ptmp2),
            "line_opacity": list(self.line_opacity),
            "line_emissivity": list(self.line_emissivity),
            "source": self.source,
            "n_lines": self.n_lines(),
            "missing_fields": self.missing_fields(),
        }


@dataclass
class XSTARZoneState:
    """Live state for a single XSTAR radial zone."""

    zone_index: int
    radius_cm: Optional[float] = None
    thickness_cm: Optional[float] = None
    temperature: Optional[float] = None
    electron_density: Optional[float] = None
    ionization_parameter: Optional[float] = None
    cfrac: Optional[float] = None
    vturbi: Optional[float] = None
    continuum: XSTARContinuumState = field(default_factory=XSTARContinuumState)
    lines: XSTARLineTransferState = field(default_factory=XSTARLineTransferState)
    ion_fractions: Dict[str, float] = field(default_factory=dict)
    level_populations: Dict[str, List[float]] = field(default_factory=dict)
    heating_rates: Dict[str, float] = field(default_factory=dict)
    cooling_rates: Dict[str, float] = field(default_factory=dict)
    status: str = "input_seed_only"

    def missing_core_fields(self) -> List[str]:
        """Return source-code-parity fields not yet populated for this zone."""
        missing: List[str] = []
        scalar_fields = [
            "temperature",
            "electron_density",
            "cfrac",
            "vturbi",
        ]
        for name in scalar_fields:
            if getattr(self, name) is None:
                missing.append(name)
        if not self.ion_fractions:
            missing.append("ion_fractions")
        if not self.level_populations:
            missing.append("level_populations")
        missing.extend([f"continuum.{name}" for name in self.continuum.missing_fields()])
        missing.extend([f"lines.{name}" for name in self.lines.missing_fields()])
        return missing

    def as_dict(self) -> Dict[str, Any]:
        return {
            "zone_index": self.zone_index,
            "radius_cm": self.radius_cm,
            "thickness_cm": self.thickness_cm,
            "temperature": self.temperature,
            "electron_density": self.electron_density,
            "ionization_parameter": self.ionization_parameter,
            "cfrac": self.cfrac,
            "vturbi": self.vturbi,
            "continuum": self.continuum.as_dict(),
            "lines": self.lines.as_dict(),
            "ion_fractions": dict(self.ion_fractions),
            "level_populations": {key: list(value) for key, value in self.level_populations.items()},
            "heating_rates": dict(self.heating_rates),
            "cooling_rates": dict(self.cooling_rates),
            "status": self.status,
            "missing_core_fields": self.missing_core_fields(),
        }


@dataclass
class XSTARRunState:
    """Live-state container for a full XSTAR run."""

    parameters: Dict[str, Any] = field(default_factory=dict)
    zones: List[XSTARZoneState] = field(default_factory=list)
    source: Optional[str] = None
    status: str = "state_schema_created_not_full_xstar_recreation"

    def missing_core_fields_by_zone(self) -> Dict[int, List[str]]:
        return {zone.zone_index: zone.missing_core_fields() for zone in self.zones}

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "parameters": dict(self.parameters),
            "n_zones": len(self.zones),
            "zones": [zone.as_dict() for zone in self.zones],
            "missing_core_fields_by_zone": self.missing_core_fields_by_zone(),
            "required_live_state_fields": required_live_state_fields(),
        }


def required_live_state_fields() -> List[Dict[str, str]]:
    """Return the live arrays/scalars required for exact Python XSTAR parity."""
    return [
        {
            "name": "epi(:)",
            "python_field": "XSTARZoneState.continuum.epi",
            "purpose": "continuum energy grid used by nbinc and continuum transfer",
            "source_or_builder": "build from XSTAR continuum-grid setup, not final line outputs",
        },
        {
            "name": "bremsa(:)",
            "python_field": "XSTARZoneState.continuum.bremsa",
            "purpose": "local radiation field used by ucalc type-50 photoexcitation",
            "source_or_builder": "compute with trnfrc-equivalent transfer from local zrems/dpthc state",
        },
        {
            "name": "bremsint(:)",
            "python_field": "XSTARZoneState.continuum.bremsint",
            "purpose": "integrated continuum/radiation quantity used by photo processes",
            "source_or_builder": "integrate reconstructed bremsa over epi bins as XSTAR does",
        },
        {
            "name": "tau0(1:2,line)",
            "python_field": "XSTARZoneState.lines.tau0_in / tau0_out",
            "purpose": "line optical depths entering pescl and type-50 escaped decay",
            "source_or_builder": "compute during line-transfer/depth loop; detail FITS can audit final values",
        },
        {
            "name": "tauc/dpthc(1:2,continuum)",
            "python_field": "XSTARZoneState.continuum.tauc_in / tauc_out / dpthc_forward / dpthc_backward",
            "purpose": "continuum optical depths used by continuum transfer and radiation field",
            "source_or_builder": "compute during continuum transfer; xo01_detal4 can audit final zone values",
        },
        {
            "name": "cfrac",
            "python_field": "XSTARZoneState.cfrac",
            "purpose": "geometry/covering factor controlling escape and line pumping",
            "source_or_builder": "XSTAR input parameter/PARAMETERS table",
        },
        {
            "name": "vturbi",
            "python_field": "XSTARZoneState.vturbi",
            "purpose": "turbulent velocity entering vtherm for line cross sections",
            "source_or_builder": "XSTAR input parameter/PARAMETERS table",
        },
        {
            "name": "temperature/electron density per zone",
            "python_field": "XSTARZoneState.temperature / electron_density",
            "purpose": "local plasma state for ionization, recombination, collision, and thermal rates",
            "source_or_builder": "thermal/ionization iteration; xout_abund1/xo01_detail can audit final values",
        },
        {
            "name": "ion fractions per zone",
            "python_field": "XSTARZoneState.ion_fractions",
            "purpose": "ionic abundances used by emissivity, opacity, and output abundance tables",
            "source_or_builder": "ionization-balance solver; xout_abund1 can audit final values",
        },
        {
            "name": "level populations per zone",
            "python_field": "XSTARZoneState.level_populations",
            "purpose": "explicit-level populations used by line emissivities and detail output",
            "source_or_builder": "population matrix solver; xo01_detail can audit final values",
        },
    ]


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def create_initial_xstar_run_state(
    parameters: Mapping[str, Any],
    *,
    n_zones: Optional[int] = None,
    source: Optional[str] = None,
) -> XSTARRunState:
    """Create an input-seeded live-state skeleton from XSTAR parameters.

    This function intentionally does not fill solved arrays such as ``bremsa``
    or ``tau0``.  It creates the zone objects that future source-code-parity
    loops will populate and seeds scalar values available directly from the
    XSTAR input command.
    """
    pmap = {str(key).strip().lower(): value for key, value in parameters.items()}
    nz = n_zones if n_zones is not None else _as_int(pmap.get("nsteps"), 1)
    if nz <= 0:
        nz = 1
    cfrac = _as_float(pmap.get("cfrac"))
    vturbi = _as_float(pmap.get("vturbi"))
    temperature_seed = _as_float(pmap.get("temperature"))
    density_seed = _as_float(pmap.get("density"))
    rlogxi = _as_float(pmap.get("rlogxi"))
    xi = 10.0 ** rlogxi if rlogxi is not None else None
    radius_cm = None
    if pmap.get("rlrad38") is not None:
        radius_cm = (_as_float(pmap.get("rlrad38"), 0.0) or 0.0) * 1.0e38
    zones = [
        XSTARZoneState(
            zone_index=index + 1,
            radius_cm=radius_cm,
            temperature=temperature_seed,
            electron_density=density_seed,
            ionization_parameter=xi,
            cfrac=cfrac,
            vturbi=vturbi,
            status="input_seed_only",
        )
        for index in range(nz)
    ]
    return XSTARRunState(parameters=dict(pmap), zones=zones, source=source)


def create_initial_xstar_run_state_from_input(params: Any, *, n_zones: Optional[int] = None) -> XSTARRunState:
    """Create an input-seeded run state from ``XSTARInputParameters`` or mapping."""
    if hasattr(params, "as_dict"):
        return create_initial_xstar_run_state(params.as_dict(), n_zones=n_zones, source=getattr(params, "source", None))
    return create_initial_xstar_run_state(params, n_zones=n_zones)


def write_xstar_state_skeleton(
    state: XSTARRunState,
    out_dir: str | Path,
    *,
    prefix: str = "xstar_live_state_skeleton",
) -> Dict[str, str]:
    """Write JSON/Markdown/CSV products describing a live-state skeleton."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"{prefix}.json"
    md_path = out / f"{prefix}.md"
    csv_path = out / f"{prefix}_fields.csv"
    json_path.write_text(json.dumps(state.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "python_field", "purpose", "source_or_builder"])
        writer.writeheader()
        for row in required_live_state_fields():
            writer.writerow(row)
    lines = [
        "# XSTAR live-state skeleton",
        "",
        f"Status: `{state.status}`",
        "",
        f"Number of zones: `{len(state.zones)}`",
        "",
        "## Required live fields",
        "",
        "| XSTAR quantity | Python field | Builder/audit source |",
        "|---|---|---|",
    ]
    for row in required_live_state_fields():
        lines.append(f"| `{row['name']}` | `{row['python_field']}` | {row['source_or_builder']} |")
    lines += ["", "## Missing fields by zone", ""]
    for zone_index, missing in state.missing_core_fields_by_zone().items():
        preview = ", ".join(missing[:12])
        if len(missing) > 12:
            preview += f", ... ({len(missing)} total)"
        lines.append(f"- Zone {zone_index}: {preview}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path), "fields_csv": str(csv_path)}
