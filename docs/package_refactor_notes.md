# Package refactor notes

This package is the first refactor of the previously standalone scripts:

| Standalone script | Package module | Console command |
|---|---|---|
| `xstar_atomic_reader_inspect.py` | `xstar_atomic.inspect` | `xstar-atomic-inspect` |
| `xstar_atomic_hierarchy.py` | `xstar_atomic.hierarchy` | `xstar-atomic-hierarchy` |
| `xstar_atomic_extract_lines_v2.py` | `xstar_atomic.lines` | `xstar-atomic-lines` |
| `xstar_atomic_extract_photoionization_v1.py` | `xstar_atomic.photoionization` | `xstar-atomic-photoionization` |
| `xstar_atomic_extract_collisions_v2b.py` | `xstar_atomic.collisions` | `xstar-atomic-collisions` |
| `xstar_atomic_extract_recombination_v3.py` | `xstar_atomic.recombination` | `xstar-atomic-recombination` |
| `xstar_atomic_make_emissivity_table_v1.py` | `xstar_atomic.emissivity` | `xstar-atomic-emissivity` |
| `xstar_atomic_level_population_solver_v2.py` | `xstar_atomic.solver` | `xstar-atomic-solver` |

The module code is intentionally close to the validated scripts so the current behavior remains reproducible.
