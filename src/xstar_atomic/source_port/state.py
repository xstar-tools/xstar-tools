"""Typed state containers for the source-faithful Python XSTAR port."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np


@dataclass
class XSTARAtomicState:
    """Packed ATDB tables and pointer structures created by ``readtbl/setptrs``.

    ``master`` and ``derived`` are typed source-port objects.  The legacy
    ``tables``/``pointers`` dictionaries remain populated for compatibility
    with pre-v0.4 audit code while the whole-program port is assembled.
    """

    atdb_path: Optional[str] = None
    master: Optional[Any] = None
    derived: Optional[Any] = None
    tables: Dict[str, Any] = field(default_factory=dict)
    pointers: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)

    def close(self) -> None:
        """Close any memory-mapped FITS handle owned by the atomic state."""
        if self.master is not None and hasattr(self.master, "close"):
            self.master.close()


@dataclass
class XSTARPlasmaState:
    """Local thermodynamic, density, abundance, and population state."""

    temperature: float = 0.0
    xpx: float = 0.0
    xee: float = 0.0
    electron_density: float = 0.0
    populations: Optional[np.ndarray] = None
    ion_fractions: Optional[Any] = None
    abundances: Optional[np.ndarray] = None


@dataclass
class XSTARRadiationState:
    """High-resolution and reduced XSTAR radiation grids."""

    epi: Optional[np.ndarray] = None
    bremsa: Optional[np.ndarray] = None
    epim: Optional[np.ndarray] = None
    bremsam: Optional[np.ndarray] = None
    bremsint: Optional[np.ndarray] = None
    zrems: Optional[np.ndarray] = None
    zremso: Optional[np.ndarray] = None
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class XSTARMatrixState:
    """Ion-local and compact element statistical-equilibrium matrices."""

    ion_matrix: Optional[np.ndarray] = None
    compact_matrix: Optional[np.ndarray] = None
    rhs: Optional[np.ndarray] = None
    aliases: Dict[str, int] = field(default_factory=dict)
    basis_metadata: Dict[int, Dict[str, Any]] = field(default_factory=dict)


@dataclass
class XSTARThermalState:
    """Heating, cooling, and thermal-convergence state."""

    heating: float = 0.0
    cooling: float = 0.0
    electron_fraction: float = 0.0
    residual: float = 0.0
    converged: bool = False


@dataclass
class XSTARLocalZoneState:
    """Mutable products of ``calc_hmc_all`` and the local ``xstarcalc`` path."""

    calc_hmc_all: Optional[Any] = None
    fixed_state_ready: bool = False
    thermal_iteration_ready: bool = False
    emissivity_ready: bool = False
    source_arrays: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class XSTARTransferState:
    """Radial zone/pass transfer and optical-depth state."""

    zone_index: int = 0
    pass_index: int = 0
    direction: int = 1
    radius: float = 0.0
    radial_depth: float = 0.0
    column: float = 0.0
    step_size: float = 0.0
    tau_in: Optional[np.ndarray] = None
    tau_out: Optional[np.ndarray] = None
    converged: bool = False
    source_arrays: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class XSTARPythonState:
    """Top-level mutable state passed through the translated XSTAR call graph."""

    atomic: XSTARAtomicState = field(default_factory=XSTARAtomicState)
    plasma: XSTARPlasmaState = field(default_factory=XSTARPlasmaState)
    radiation: XSTARRadiationState = field(default_factory=XSTARRadiationState)
    matrix: XSTARMatrixState = field(default_factory=XSTARMatrixState)
    thermal: XSTARThermalState = field(default_factory=XSTARThermalState)
    local_zone: XSTARLocalZoneState = field(default_factory=XSTARLocalZoneState)
    transfer: XSTARTransferState = field(default_factory=XSTARTransferState)
    control: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    provenance: Dict[str, Any] = field(default_factory=dict)
