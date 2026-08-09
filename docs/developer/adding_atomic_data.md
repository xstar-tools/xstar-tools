# Adding or changing atomic-data/rate support

Scientific changes are outside ordinary productization. Before modifying a data/rate path:

1. identify the canonical Fortran `setptrs`/`ucalc`/caller behavior;
2. identify the data type and rate type separately;
3. update the Fortran/Python/C++ concordance entry;
4. add characterization evidence before changing frozen code;
5. test one fast affected model first;
6. widen qualification only after that model passes;
7. reopen the science revision only when the change is intentionally scientific.

The key semantic rule is: **data type determines how record constants are interpreted/calculated; rate type determines how the resulting quantity is consumed by XSTAR.**

See `docs/science/rate_data_semantics.md`, `docs/developer/fortran_source_map.md`, and `docs/developer/python_cpp_fortran_concordance.md`.
