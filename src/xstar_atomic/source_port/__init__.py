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
from .atomic_database import (
    AtomicDatabaseError,
    PackedRecordHeader,
    FortranPackedVector,
    FortranPointerTable,
    XSTARMasterData,
    XSTARDerivedPointers,
    AtomicDatabaseBuildResult,
    DBWK2Instruction,
    DBWK2Result,
    readtbl,
    setptrs,
    dbwk2,
    populate_atomic_state,
    load_atomic_database_state,
    register_atomic_database_stages,
    POINTER_CACHE_FORMAT_VERSION,
    atomic_database_fingerprint,
    save_derived_pointer_cache,
    load_derived_pointer_cache,
    write_atomic_database_products,
)


from .ucalc import (
    UCalcLevel,
    UCalcLevelTable,
    UCalcRecord,
    UCalcContext,
    UCalcStatus,
    UCalcProvenance,
    UCalcResult,
    UCalcExecutionError,
    UCalcUntranslatedBranch,
    UCalcBranchSpec,
    SourceFaithfulUCalc,
    complete_ucalc_branch_catalog,
    default_source_faithful_ucalc,
)
from .ucalc_inventory import (
    build_ucalc_data_type_inventory,
    build_ucalc_branch_catalog_rows,
    build_ucalc_index_only_samples,
    write_ucalc_subsystem_products,
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
    "UCalcLevel",
    "UCalcLevelTable",
    "UCalcRecord",
    "UCalcContext",
    "UCalcStatus",
    "UCalcProvenance",
    "UCalcResult",
    "UCalcExecutionError",
    "UCalcUntranslatedBranch",
    "UCalcBranchSpec",
    "SourceFaithfulUCalc",
    "complete_ucalc_branch_catalog",
    "default_source_faithful_ucalc",
    "build_ucalc_data_type_inventory",
    "build_ucalc_branch_catalog_rows",
    "build_ucalc_index_only_samples",
    "write_ucalc_subsystem_products",
    "UCalcBranch",
    "UCalcDispatcher",
    "default_ucalc_dispatcher",
    "AtomicDatabaseError",
    "PackedRecordHeader",
    "FortranPackedVector",
    "FortranPointerTable",
    "XSTARMasterData",
    "XSTARDerivedPointers",
    "AtomicDatabaseBuildResult",
    "DBWK2Instruction",
    "DBWK2Result",
    "readtbl",
    "setptrs",
    "dbwk2",
    "populate_atomic_state",
    "load_atomic_database_state",
    "register_atomic_database_stages",
    "POINTER_CACHE_FORMAT_VERSION",
    "atomic_database_fingerprint",
    "save_derived_pointer_cache",
    "load_derived_pointer_cache",
    "write_atomic_database_products",
]
