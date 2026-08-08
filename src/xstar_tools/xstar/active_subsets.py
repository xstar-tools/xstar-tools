# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-BEGIN
# Source correspondence:
#   Fortran: setptrs.f90 plus calc_hmc*/calc_emis* source-index traversal
#   Role: Build source-indexed active element/ion/level/line/continuum subsets without renumbering XSTAR identities.
#   Relation: Index/cache transformation only; source pointer identity and ordering remain authoritative.
#   Concordance: DB-001; BACKEND-001
#   Qualification: accepted science revision 0.6.48.12.3.45.3.3.8; frozen C++ baseline 0.6.48.12.3.44.
# Atomic-data note (XSTAR Manual Ch. 12; Mendoza et al. 2021, Appendix A):
#   Rule: data type selects the record formula/interpretation; rate type selects downstream use.
#   Subset selection may filter records for work size but must preserve the original record header,
#   including independent data-type and rate-type meanings.
# XSTAR-PYTHON-SOURCE-CORRESPONDENCE-END

"""Per-run active ATDB subset indexes for memory-sensitive XSTAR runs.

The first implementation is deliberately conservative: it precomputes and
caches source-identical lookup maps for the active elements/ions/levels.  The
runtime uses these indexes in selected hot paths such as calc_emis_all
feature ranking, while preserving source-indexed output arrays for writers.  This module is structured so a future ``xstar_tools.xstar.solver`` or
``xstar_tools.atomic.indexes`` move can keep the same object boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class ActiveATDBSubset:
    """Source-indexed active element/ion/level maps for one model case."""

    active_element_z: tuple[int, ...]
    global_ion_index_by_key: Mapping[tuple[int, int], int]
    ion_record_to_index: Mapping[int, int]
    global_element_index_by_z: Mapping[int, int]
    global_element_index_source: str
    global_level_index_by_key: Mapping[tuple[int, int, int], int]
    n_global_levels_active: int
    n_global_levels_capacity: int
    ion_indices: np.ndarray = field(repr=False)
    level_indices: np.ndarray = field(repr=False)
    continuum_indices: np.ndarray = field(repr=False)
    line_indices: np.ndarray = field(repr=False)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def as_summary(self) -> dict[str, Any]:
        return {
            "active_element_z": list(self.active_element_z),
            "n_active_elements": len(self.active_element_z),
            "n_active_ions": int(self.ion_indices.size),
            "n_active_levels": int(self.level_indices.size),
            "n_active_continua": int(self.continuum_indices.size),
            "n_active_lines": int(self.line_indices.size),
            "n_global_levels_active": int(self.n_global_levels_active),
            "n_global_levels_capacity": int(self.n_global_levels_capacity),
            "global_element_index_source": str(self.global_element_index_source),
        }


def _one_based_indices(mask: np.ndarray) -> np.ndarray:
    return np.nonzero(np.asarray(mask, dtype=bool))[0].astype(np.int64)


def build_active_atdb_subset(master: Any, derived: Any, active_element_z: Sequence[int]) -> ActiveATDBSubset:
    """Precompute active element/ion/level/continuum lookup structures.

    Arrays in ``derived`` are mostly one-based source arrays with slot 0 unused.
    Returned index arrays preserve those source indices.
    """
    active = tuple(sorted({int(z) for z in active_element_z if int(z) > 0}))
    active_set = set(active)

    n_ions = int(getattr(derived, "n_ions", 0))
    ion_records = np.asarray(getattr(derived, "ion_records", ()), dtype=np.int64).reshape(-1)
    ion_stages = np.asarray(getattr(derived, "ion_stage", ()), dtype=np.int64).reshape(-1)
    ion_elements = np.asarray(getattr(derived, "ion_element_z", ()), dtype=np.int64).reshape(-1)
    ion_limit = min(n_ions + 1, ion_records.size, ion_stages.size, ion_elements.size)
    ion_mask = np.zeros(max(ion_limit, 1), dtype=bool)
    if ion_limit > 1:
        ion_mask[1:ion_limit] = np.isin(ion_elements[1:ion_limit], list(active_set))
    ion_indices = _one_based_indices(ion_mask)

    global_ion_index_by_key: dict[tuple[int, int], int] = {}
    ion_record_to_index: dict[int, int] = {}
    for ion_index in ion_indices:
        ii = int(ion_index)
        rec = int(ion_records[ii]) if ii < ion_records.size else 0
        z = int(ion_elements[ii]) if ii < ion_elements.size else 0
        stage = int(ion_stages[ii]) if ii < ion_stages.size else 0
        if rec > 0:
            ion_record_to_index[rec] = ii
        if z > 0 and stage > 0:
            global_ion_index_by_key[(z, stage)] = ii

    available_element_z = {int(z) for z in ion_elements[:ion_limit] if int(z) > 0}
    global_element_index_by_z: dict[int, int] = {}
    source = "packed_type11_element_ordinal"
    element_records = np.asarray(getattr(derived, "element_records", ()), dtype=np.int64).reshape(-1)
    for element_index in range(1, element_records.size):
        rec = int(element_records[element_index])
        if rec <= 0 or not hasattr(master, "record_integers"):
            continue
        integers = np.asarray(master.record_integers(rec), dtype=np.int64).reshape(-1)
        if integers.size and int(integers[0]) > 0 and int(integers[0]) in active_set:
            global_element_index_by_z[int(integers[0])] = int(element_index)
    if not global_element_index_by_z:
        source = "synthetic_sorted_element_fallback"
        for element_index, z in enumerate(sorted(available_element_z & active_set), start=1):
            global_element_index_by_z[int(z)] = int(element_index)

    npilev = np.asarray(getattr(derived, "npilev", ()), dtype=np.int64)
    nlevs = np.asarray(getattr(derived, "nlevs", ()), dtype=np.int64).reshape(-1)
    global_level_index_by_key: dict[tuple[int, int, int], int] = {}
    level_values: list[int] = []
    if npilev.ndim == 2:
        for ion_index in ion_indices:
            ii = int(ion_index)
            if ii >= min(ion_stages.size, ion_elements.size, nlevs.size, npilev.shape[1]):
                continue
            z = int(ion_elements[ii])
            stage = int(ion_stages[ii])
            nlev = int(nlevs[ii])
            for local_ordinal in range(1, min(nlev + 1, npilev.shape[0])):
                global_idx = int(npilev[local_ordinal, ii])
                if global_idx > 0:
                    global_level_index_by_key[(z, stage, local_ordinal)] = global_idx
                    level_values.append(global_idx)
    level_indices = np.asarray(sorted(set(level_values)), dtype=np.int64)
    n_global_active = int(level_indices.max()) if level_indices.size else 0
    capacity = int(getattr(derived, "n_level_records", 0))
    if npilev.size:
        capacity = max(capacity, int(np.max(npilev)))

    # v0.5.44: Build hard active feature lists from source pointer ownership.
    # Lines and continua are indexed by nplin/npcon; their parent chain leads
    # to the owning ion record, and ion_record_to_index gives the element Z.
    # This lets calc_emis_all rank only features for H, He, and the active
    # abundance element instead of walking every ATDB line/RRC every zone.
    line_indices = np.zeros(0, dtype=np.int64)
    try:
        n_lines = int(getattr(derived, "nlsvn", 0))
        nplin = np.asarray(getattr(derived, "nplin", ()), dtype=np.int64).reshape(-1)
        npar = np.asarray(getattr(derived, "npar", ()), dtype=np.int64).reshape(-1)
        values: list[int] = []
        for line_index in range(1, min(n_lines + 1, nplin.size)):
            rec = int(nplin[line_index])
            ion_rec = int(npar[rec]) if 0 < rec < npar.size else 0
            ion_index = int(ion_record_to_index.get(ion_rec, 0))
            z = int(ion_elements[ion_index]) if 0 < ion_index < ion_elements.size else 0
            if z in active_set:
                values.append(line_index)
        line_indices = np.asarray(values, dtype=np.int64)
    except Exception:
        line_indices = np.zeros(0, dtype=np.int64)

    continuum_indices = np.zeros(0, dtype=np.int64)
    try:
        n_cont = int(getattr(derived, "ncsvn", 0))
        npcon = np.asarray(getattr(derived, "npcon", ()), dtype=np.int64).reshape(-1)
        npar = np.asarray(getattr(derived, "npar", ()), dtype=np.int64).reshape(-1)
        values = []
        for continuum_index in range(1, min(n_cont + 1, npcon.size)):
            rec = int(npcon[continuum_index])
            ion_rec = int(npar[rec]) if 0 < rec < npar.size else 0
            ion_index = int(ion_record_to_index.get(ion_rec, 0))
            z = int(ion_elements[ion_index]) if 0 < ion_index < ion_elements.size else 0
            if z in active_set:
                values.append(continuum_index)
        continuum_indices = np.asarray(values, dtype=np.int64)
    except Exception:
        continuum_indices = np.zeros(0, dtype=np.int64)

    return ActiveATDBSubset(
        active_element_z=active,
        global_ion_index_by_key=global_ion_index_by_key,
        ion_record_to_index=ion_record_to_index,
        global_element_index_by_z=global_element_index_by_z,
        global_element_index_source=source,
        global_level_index_by_key=global_level_index_by_key,
        n_global_levels_active=n_global_active,
        n_global_levels_capacity=capacity,
        ion_indices=ion_indices,
        level_indices=level_indices,
        continuum_indices=continuum_indices,
        line_indices=line_indices,
        provenance={"builder": "build_active_atdb_subset", "source_faithful_indices": True},
    )
