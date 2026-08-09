# Python / C++ / Fortran concordance

This document assigns stable **concordance IDs** to scientific ownership boundaries. Refactors should cite these IDs rather than relying on historical version names alone.

**Science revision:** `0.6.48.12.3.45.3.3.8`  
**C++ baseline:** `0.6.48.12.3.44`  
**Production-zone ABI:** `6048110`

## How to read the map

Implementation status uses three terms:

- **source-exact** - control flow, ordering, data-kind behavior, and observable source semantics are deliberately reproduced;
- **mathematically equivalent** - representation differs, but the same source equations/operator are evaluated and qualified;
- **optimized-equivalent** - the source operation is transformed for performance, with explicit invariants and qualification showing accepted products are preserved.

The terms do not supersede qualification evidence. The parity freeze remains the release gate.

## Concordance matrix

| ID | Fortran authority | Python implementation | C++ implementation | Status | Characterization / qualification evidence |
|---|---|---|---|---|---|
| `ARCH-001` | `xstar.f90`, `xstarcalc.f90` | `driver.py`, `physical_runner.py`, `radial_transfer.py` | `xstar_engine.cpp`, `xstar_standalone.cpp`, `xstar_run_state.*` | source-exact orchestration contract / equivalent storage | `tests/test_source_characterization_current.py::test_arch_001_controller_one_zone_boundary`; all-62 12.3.42-44 |
| `INPUT-001` | `rread1.f90` | parameter normalization and source-real helpers in `physical_runner.py` / radial setup | `xstar_atdb_runtime.cpp` reader/default-real helpers | source-exact where executable kinds matter | `tests/test_source_characterization_current.py::test_input_001_fortran_input_semantics_anchor`; 12.3.36 `rread1` radius repair; all-62 STEP |
| `DB-001` | `readtbl.f90`, `setptrs.f90`, `xstarsetup.f90` | `atomic_database.py` (`readtbl`, `setptrs`, pointer/cache validation) | `xstar_atdb_runtime.cpp` native reader/pointer layout | source-exact identities with equivalent storage | `tests/test_source_characterization_current.py::test_db_001_atomic_database_pointer_topology_anchor`; all-element qualification; 12.3.44 |
| `ION-001` | `calc_ion_rates.f90`, `istruc.f90`, `ioneqm.f90`, first pass of `calc_hmc_element.f90` | `ion_balance.py` | fixed-state/element engine total-rate pass | source-exact stage-selection logic | `tests/test_source_characterization_current.py::test_ion_001_pre_matrix_ion_balance_anchor`; pre-matrix ion-balance qualification; all-62 |
| `LEVEL-001` | `levwkelement.f90`, `levwk.f90` | `element_equilibrium.py` compact basis and LTE tables | `level_population.cpp`, fixed-state layout | mathematically equivalent representation with source-one-based topology | `tests/test_source_characterization_current.py::test_level_001_compact_level_topology_anchor`; 12.3.25 level/matrix closure |
| `MATRIX-001` | `calc_hmc_ion.f90`, `calc_hmc_element.f90`, `msolvelucy.f90` | `element_equilibrium.py`, `linear_algebra.py` | `local_zone_engine.cpp`, `element_engine.cpp`, `matrix_kernels.cpp` | source-equivalent operator/solve | `tests/test_source_characterization_current.py::test_matrix_001_matrix_assembly_and_solve_anchor`; 12.3.25 terminal clamp; 12.3.44 |
| `THERM-001` | `calc_hmc_all.f90`, `comp2.f90`, `freef.f90`, `bremem.f90`, `heatf.f90` | `local_zone.py`, `compton.py`, `free_free.py`, `bremsstrahlung.py`, `thermal_balance.py` | `thermal_kernels.cpp`, fixed-state thermal reduction | source-equivalent, selected native reductions optimized-equivalent | `tests/test_source_characterization_current.py::test_therm_001_thermal_construction_anchor`; thermal parity; 12.3.44 |
| `DSEC-001` | `dsec.f90` | `dsec.py` | fixed-state/standalone DSEC controller support | source-exact nonlinear branch/order contract | `tests/test_source_characterization_current.py::test_dsec_001_nonlinear_controller_anchor`; DSEC ownership/trajectory closure; 12.3.42 |
| `EMISAB-001` | `calc_emisab_all/element/ion.f90` | `emissivity.py` | `line_emissivity.cpp`, fixed-state product state, `xstar_science_fits.cpp` | source-exact producer order; output lifetime bridge qualified separately | `tests/test_source_characterization_current.py::test_emisab_001_reduced_grid_publication_anchor`; 12.3.43.x; 45.3.3.8 |
| `EMIS-001` | `calc_emis_all/element/ion.f90`, `rlbin.f90` | `emergent_emissivity.py` | `line_emissivity.cpp`, `opacity_kernels.cpp`, spectral fixed-state path | source-equivalent / optimized-equivalent where qualified | `tests/test_source_characterization_current.py::test_emis_001_full_grid_emission_opacity_anchor`; continuum/spectrum closure; 12.3.43.3/44 |
| `TYPE50-001` | `linopac.f90`, Type50 `ucalc` producer context | `_source_linopac_*` in `emergent_emissivity.py`; Type50 provenance helpers | `opacity_kernels.cpp`, Type50 production specialization in `local_zone_engine.cpp` | optimized-equivalent | `tests/test_source_characterization_current.py::test_type50_001_line_profile_opacity_anchor`; Type50 12.3.26-31; 12.3.44 |
| `RADIAL-001` | inline `xstar.f90`, `step.f90`, `trnfrc.f90`, `stpcut.f90`, `trnfrn.f90` | `radial_transfer.py`, `radial_control.py` | native run controller/state | source-exact predicates/order, equivalent object storage | `tests/test_source_characterization_current.py::test_radial_001_transfer_termination_anchor`; O7 terminal repair; 12.3.42-44 |
| `STATE-001` | `savd.f90`, `unsavd.f90`, `rstepr*` | `saved_radial_state.py`, save/restore in `radial_transfer.py` | native run-state/detail persistence | source-exact persistence semantics | `tests/test_source_characterization_current.py::test_state_001_saved_radial_state_anchor`; 12.3.43-45 state-lifetime qualification |
| `DETAIL-001` | `fstepr.f90`, `fstepr2.f90`, `fstepr3.f90`, `fstepr4.f90` | `output_writers.py` plus producer-owned retained publication state | `xstar_science_fits.cpp` | source-equivalent publication with accepted structural exceptions | `tests/test_source_characterization_current.py::test_detail_001_detail_publication_anchor`; 12.3.43.3; 45.3.3.7/8 |
| `STEP-001` | `pprint.f90` | `pprint_legacy.py` | `xstar_step_log.cpp` | source-exact formatting/rank semantics where qualified | `tests/test_source_characterization_current.py::test_step_001_step_print_anchor`; comparator 12.3.34/36.1/41/42; 45.1/45.3.3.2 |
| `FINAL-001` | `writespectra*.f90` and final sequence in `xstar.f90` | `output_writers.py` | `xstar_science_fits.cpp` | source-equivalent final publication | `tests/test_source_characterization_current.py::test_final_001_final_product_writers_anchor`; all-62 FITS 12.3.43.3; three-mode 12.3.44; Python 45.3.3.8 |
| `BACKEND-001` | no single Fortran routine; source contract is the `xstarcalc`/radial scientific boundary | Python driver + modular adapters + `cpp_backend_production_zone.py` | `xstar_api*`, backend plugins, `xstar_engine.cpp`, standalone | productization dispatch layer over qualified science | `tests/test_source_characterization_current.py::test_backend_001_public_mode_mapping_anchor`; ABI 6048110 freeze; three-mode 12.3.44; public modes 0.6.60 |
| `TERMINAL-001` | final `xstar.f90` `xstarcalc`/`pprint`/`writespectra*`; `savd/fstepr*` lifetime | retained terminal publication state in frozen Python publisher modules | terminal retained state in native run/FITS writers | source-exact ownership/lifetime intent; publication bridge output-only | `tests/test_source_characterization_current.py::test_terminal_001_terminal_lifetime_anchor`; 43.x lifetime attribution; C5 45.3.3.7; detail3 45.3.3.8 |

## Detailed equivalence notes

### `INPUT-001` - default-REAL and parameter-reader semantics

The accepted port treats Fortran kinds as observable when the source does. The radius calculation is the canonical example:

```fortran
r = r19*(1.e+19)
```

The decimal expression is not interpreted as an abstract real number; the default-REAL literal is rounded at the source kind and then promoted. The native implementation similarly models the relevant `uclgsr8` conversion path. This is **source-exact numeric semantics**, not a mathematical simplification.

### `DB-001` - database pointer construction

Python uses memory-mapped FITS packed vectors and explicit dataclasses rather than COMMON blocks. C++ uses native reader/layout objects. Those are storage transformations only. `npar`, level, continuum, and line attachment identities remain governed by `setptrs` traversal and are validated as scientific/publication state.

### `MATRIX-001` - compact matrix endpoints and Lucy solve

The accepted matrix repair established that the source solver consumes compact endpoint ranges using clamped endpoints. A translated record whose local endpoint is at/after the terminal compact row must therefore be clamped to the source solver's `ipmat` domain rather than dropped as invalid. This is frozen by 12.3.25 and is part of the source operator definition.

The C++ solver may store dense/compact intermediates differently from Fortran. Qualification is based on the resulting source operator, populations, rates, thermal totals, and downstream products.

### `THERM-001` - source-order thermal reductions

The C++ thermal path groups and vectorizes selected computations, but the production reduction maintains the accepted source ownership and ordered accumulation semantics where roundoff affects qualified products. Performance transformations must not silently reorder a surface already shown to be order-sensitive.

### `DSEC-001` - nonlinear controller

`dsec` is not simply “find the root of heating minus cooling.” It is a stateful Fortran controller whose trial sequence, bracketing/secant logic, branch order, and population ownership can alter the next evaluation. Python therefore follows the source labels/branches rather than substituting `scipy.optimize` or another generic solver.

### `EMISAB-001` and `DETAIL-001` - producer versus publication lifetime

`calc_emisab_all` produces physical integrated line/RRC values. `fstepr3` publishes a particular source-visible continuum/RRC inventory at shell-save time. The accepted 45.3.3.8 Python bridge retains publication values without writing them back into physical `cemab`, `cabab`, or `opakab`. This is a deliberate boundary:

> Publication repair may restore source lifetime/ownership; it must not change the physical state merely to force row inventory.

The accepted Ca and O7 `xo01_detal3` exceptions remain structural membership exceptions under the frozen material criterion.

### `TYPE50-001` - optimized C++ line-profile path

Canonical operation: `linopac` walks the relevant energy range for each source line and accumulates the line-profile opacity into the continuum opacity array.

Accepted production transformations include monotone cursor advancement and specialized vector/scalar profile generation. The frozen invariants are:

1. line/record production order remains source-compatible;
2. active range and boundary decisions are source-equivalent;
3. per-bin update uses the accepted source arithmetic/update semantics;
4. optimization fallbacks do not change qualified numerical products;
5. production and reference paths passed the accepted Type50 decomposition and downstream FITS/STEP parity gates.

The production science remains frozen. Version 0.6.53 introduced reversible top-of-file C++ correspondence comments. Version 0.6.54 adds only an approved native-layout/name relocation plus source-derived atomic-data comments: four version-labeled runtime headers are renamed, `constants.def` is colocated with the C++ sources, and no C++ file may include a parent-directory header. The 0.6.54 refactor gate removes comments/formatting and reverses only the explicitly listed path/identifier aliases; the resulting canonical C++ content must match 0.6.53.

### `RADIAL-001` - radial controller

The Python port factors inline blocks from `xstar.f90` into functions for testing, but source order remains part of the contract. In particular, `stpcut` termination and the exact initial radius feed the shell trajectory; changing either can shift all downstream zone states even if the local-zone solver is unchanged.

### `STATE-001` and `TERMINAL-001` - state lifetime

The source has multiple lifetimes:

- local workspaces inside a zone evaluation;
- shell values persisted by `savd/fstepr*` and restored by `unsavd`;
- final/terminal state consumed by final `pprint` and `writespectra*`.

A refactor must state which lifetime it owns. “Last value in memory” is not a sufficient publication contract.

### `STEP-001` - comparator policy is part of qualification, not the physics

The current comparator deliberately separates:

- ranked numerical science by rank position;
- line identity/order/membership diagnostics;
- common-row numerical science;
- inventory/membership differences;
- normalized-L1 material surfaces.

This prevents sort artifacts or tiny tails from being misclassified as numerical physics failures while still retaining structural diagnostics.

## Pinned-source comment policy

Milestone 2 adds concise `Source correspondence` comments to important **unpinned** Python/C ABI files. It does **not** edit:

- any C++ production source pinned by `qualification/parity_freeze_science_hashes.json`;
- frozen Python production files such as `emissivity.py`, `element_equilibrium.py`, `output_writers.py`, `pprint_legacy.py`, `driver.py`, or `physical_runner.py`.

For pinned sources, this document is the source-origin comment layer until a deliberate refactor qualification permits changing their frozen hashes.

## Refactor checklist

A scientific refactor PR should include a statement like:

```text
Concordance: MATRIX-001, THERM-001
Characterization:
  pytest -q tests/test_source_characterization_current.py::test_matrix_001_matrix_assembly_and_solve_anchor
  pytest -q tests/test_source_characterization_current.py::test_therm_001_thermal_construction_anchor
Freeze:
  python tools/qualification/check_parity_freeze.py
  python tools/qualification/check_source_concordance.py
```

The current characterization anchor is `tests/test_source_characterization_current.py`; the `historical_characterization_tests` entries in `qualification/source_concordance.json` preserve earlier qualification/characterization lineage. Some old tests still depend on legacy import names or optional scientific dependencies and are therefore not a claim that every listed test runs in every productization environment. Before changing a scientific implementation, the affected concordance ID must have at least one **current runnable characterization test** in the target development environment. If the listed lineage is stale, unavailable, or too expensive, add or modernize a small characterization fixture **before** changing the implementation; do not simply drop the concordance requirement.


## C++ source correspondence comments and 0.6.54 native-layout refactor

All 47 `.cpp`, `.h`, and `.hpp` files under `src/xstar_tools/xstar/cpp/` now begin with a concise marked block containing: Fortran authority, C++ role, implementation relation, concordance IDs, and qualification boundary. Files that are C++ infrastructure or historical oracle data explicitly say that they have **no direct Fortran routine**, while identifying the scientific boundary or source behavior they support.

The comments do not redefine the scientific baseline. `qualification/cpp_source_comment_overlay.json` pins the current annotated and top-comment-normalized bytes. `qualification/cpp_non_science_refactor_0_6_54.json` separately proves that, after comment/whitespace removal and reversal of only the approved stable-name/include relocations, all 47 C++/header files retain the same canonical non-comment content as 0.6.53. The frozen C++44 production manifest remains untouched.


## 0.6.55 Python source-comment overlay

The production Python source now carries marked Fortran/source-correspondence comments parallel to the C++ comments. The comments also document the atomic-database distinction between **data type** (record formula/interpretation in `ucalc`) and **rate type** (downstream use of the returned rates). The overlay is comment-only: removing the marked leading block from every annotated module must reproduce its exact `0.6.54` bytes. See `python_fortran_source_comments.md` and `qualification/python_source_comment_overlay.json`.


## 0.6.56 active-namespace note

The source concordance maps production behavior, not the historical parity-campaign tooling surface. `0.6.56` archives one-off Python audit/attribution/closure modules that have no live runtime caller. The Type53 diagnostic formerly named `type53_semantics.py` remains provenance only; active Type53 science remains mapped through the UCalc/ionization/matrix implementation entries. Historical characterization lineage does not replace the current runnable characterization-test requirement for future scientific refactors.
