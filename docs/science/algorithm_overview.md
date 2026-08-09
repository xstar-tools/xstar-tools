# Algorithm overview

At a high level, a source-faithful XSTAR calculation performs:

1. parameter/data initialization and atomic-record pointer construction;
2. shell/radial controller setup;
3. local ionization/thermal/rate construction;
4. statistical-equilibrium matrix assembly and solve for selected ions/levels;
5. emissivity, opacity, and line/RRC/continuum construction;
6. radial transfer, convergence, and shell-state updates;
7. STEP and final FITS publication.

The exact numerical/discrete semantics are defined by the accepted qualification evidence and canonical XSTAR Fortran source. Literature equations explain the physical model but do not by themselves specify record traversal, numerical kinds, cutoffs, workspace lifetime, publication ordering, or accepted source quirks.

See `docs/developer/fortran_source_map.md` for the routine-level map and `docs/developer/python_cpp_fortran_concordance.md` for implementation correspondence.
