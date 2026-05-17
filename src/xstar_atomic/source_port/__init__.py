"""Source-faithful XSTAR-to-Python port infrastructure.

This package is intentionally separate from the historical audit modules.  It
tracks the original XSTAR source tree, preserves stage/routine provenance, and
provides an executable driver that can be filled in source order.
"""

from .inventory import (
    FortranSourceFile,
    FortranRoutine,
    XSTARSourceInventory,
    build_source_inventory,
    write_source_inventory,
)
from .ledger import (
    PortStatus,
    PortLedgerEntry,
    XSTARPortLedger,
    default_port_ledger,
)
from .runtime import (
    FortranArray,
    FortranRuntimeError,
    fortran_nint,
    fortran_sign,
    fortran_mod,
)
from .state import (
    XSTARAtomicState,
    XSTARPlasmaState,
    XSTARRadiationState,
    XSTARMatrixState,
    XSTARThermalState,
    XSTARTransferState,
    XSTARPythonState,
)
from .driver import (
    XSTARStage,
    UnportedXSTARRoutine,
    XSTARPythonDriver,
)
from .ucalc_dispatch import (
    UCalcBranch,
    UCalcDispatcher,
    default_ucalc_dispatcher,
)

__all__ = [
    "FortranSourceFile",
    "FortranRoutine",
    "XSTARSourceInventory",
    "build_source_inventory",
    "write_source_inventory",
    "PortStatus",
    "PortLedgerEntry",
    "XSTARPortLedger",
    "default_port_ledger",
    "FortranArray",
    "FortranRuntimeError",
    "fortran_nint",
    "fortran_sign",
    "fortran_mod",
    "XSTARAtomicState",
    "XSTARPlasmaState",
    "XSTARRadiationState",
    "XSTARMatrixState",
    "XSTARThermalState",
    "XSTARTransferState",
    "XSTARPythonState",
    "XSTARStage",
    "UnportedXSTARRoutine",
    "XSTARPythonDriver",
    "UCalcBranch",
    "UCalcDispatcher",
    "default_ucalc_dispatcher",
]
