# Data-type and rate-type semantics

XSTAR atomic records carry two distinct classifications that must not be conflated:

- **data type** selects the record layout/formula used to interpret constants and calculate a rate, cross section, or related quantity;
- **rate type** selects how XSTAR consumes the resulting quantity in the physical calculation.

The XSTAR manual and atomic-database literature explain these families; the current `ucalc.f90` dispatcher remains the executable authority for the exact active branching used by the qualified implementation.

When adding support for a record family, document both dimensions, its caller context, pointer/level topology, units, and the characterization model used to prove equivalence.

See `docs/science/xstar_references.md` for the literature mapping.
