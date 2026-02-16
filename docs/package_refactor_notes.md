# Package refactor notes

This package is the first refactor of the previously standalone scripts:

| Standalone script | Package module | Console command |
|---|---|---|
| `xstar_atdb_reader_inspect.py` | `xstar_atdb.inspect` | `xstar-atdb-inspect` |
| `xstar_atdb_hierarchy.py` | `xstar_atdb.hierarchy` | `xstar-atdb-hierarchy` |
| `xstar_atdb_extract_lines_v2.py` | `xstar_atdb.lines` | `xstar-atdb-lines` |
| `xstar_atdb_extract_photoionization_v1.py` | `xstar_atdb.photoionization` | `xstar-atdb-photoionization` |
| `xstar_atdb_extract_collisions_v2b.py` | `xstar_atdb.collisions` | `xstar-atdb-collisions` |
| `xstar_atdb_extract_recombination_v3.py` | `xstar_atdb.recombination` | `xstar-atdb-recombination` |
| `xstar_atdb_make_emissivity_table_v1.py` | `xstar_atdb.emissivity` | `xstar-atdb-emissivity` |
| `xstar_atdb_level_population_solver_v2.py` | `xstar_atdb.solver` | `xstar-atdb-solver` |

The module code is intentionally close to the validated scripts so the current behavior remains reproducible.
