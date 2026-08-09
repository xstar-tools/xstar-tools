# Equations and source correspondence

The project distinguishes three forms of correspondence:

- **source-exact/source-faithful** — control predicates, record traversal, numerical semantics, and publication behavior intentionally track Fortran;
- **mathematically equivalent** — the same physical relation is expressed differently while preserving qualified numerical behavior;
- **optimized-equivalent** — a transformed C++ implementation is accepted because dedicated science/product gates prove equivalence.

Important maps:

- `docs/developer/fortran_source_map.md` — canonical Fortran routines and workspaces;
- `docs/developer/python_cpp_fortran_concordance.md` — Python/C++ implementation mapping;
- `docs/science/xstar_references.md` — papers/manuals and their algorithmic context.

The authority hierarchy remains accepted qualification evidence, then canonical executable semantics, then literature for explanation/context.
