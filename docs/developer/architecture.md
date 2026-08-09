# XSTAR tools architecture at the parity-freeze boundary

**Productization version:** 0.6.56  
**Qualified science revision:** `0.6.48.12.3.45.3.3.8`  
**Canonical executable authority:** XSTAR Fortran 2.59g  
**Frozen C++ production baseline:** `0.6.48.12.3.44`  
**Frozen production-zone ABI:** `6048110`

This document reconstructs the execution architecture from the canonical Fortran source and then maps that architecture onto the Python and C++ implementations. It is a productization document, not a new scientific specification.

## Authority and change policy

When sources disagree, use this order:

1. accepted qualification evidence for behavior already closed by the parity campaign;
2. executable semantics of the canonical XSTAR 2.59g Fortran source;
3. XSTAR papers and manuals for scientific explanation and context.

The parity freeze remains controlling. Documentation, comments, APIs, packaging, and orchestration may evolve without changing qualified scientific output. Any refactor of a scientific module must identify a concordance entry from `python_cpp_fortran_concordance.md` and the characterization tests protecting that entry.

## Canonical execution layers

XSTAR is easiest to reason about as six ownership layers rather than as a flat collection of rate routines.

### 1. Process initialization and parameter semantics

`xstar.f90` owns the top-level executable lifecycle. `rread1.f90` reads user parameters and performs source-defined conversions/default handling. `ener.f90`, `xstarsetup.f90`, and `init.f90` construct the energy grids, atomic-data pointers, and initial physical/radiation state.

A crucial rule is that **literal kind and parameter-reader kind are part of the executable semantics**. The accepted radius repair is the clearest example: `r = r19*(1.e+19)` uses a default-REAL literal before promotion into a `REAL(8)` expression. The source-faithful ports therefore do not replace all constants with idealized binary64 values.

### 2. Radial controller and transfer ownership

The radial controller lives primarily in `xstar.f90`, with the shell primitives in `step.f90`, `trnfrc.f90`, `stpcut.f90`, and `trnfrn.f90`.

The source order is significant:

`step -> trnfrc -> xstarcalc -> [gsmooth] -> heatt -> pprint -> savd -> stpcut -> trnfrn`

On later passes, `unsavd` restores shell state before the shell is reevaluated. The pass count is source-controlled; it is not an invented convergence loop in the Python port.

![Controller and radial flow](diagrams/controller_radial_flow.svg)

### 3. One-zone scientific solve

`xstarcalc.f90` is the canonical one-zone orchestration boundary. Its scientific order is:

1. map the incident radiation to the working grid (`bremsmap`);
2. run `dsec` when thermal balance must be solved;
3. run a final `calc_hmc_all` at the committed temperature/electron state;
4. run `calc_emisab_all` to construct integrated line/RRC quantities;
5. run `calc_emis_all` to construct full-grid emission and opacity.

This ordering explains why a local workspace may be numerically correct yet a publication product can still be wrong: publication consumes the state *after* distinct reduced-grid and full-grid producers have run.

### 4. Fixed-state ion/level solve

`calc_hmc_all` loops over elements. For each element, `calc_hmc_element` first computes a cheap total-rate ion balance, selects an adjacent active ion block, constructs compact level/LTE state, assembles the multilevel statistical-equilibrium matrix from source-order atomic records, and solves it with `msolvelucy`.

The two-step population strategy is explicitly described in the XSTAR manual:

- first solve ion fractions from total ionization/recombination rates and select materially populated adjacent stages;
- then solve the full level-population kinetic matrix for the selected stages.

The accepted C++ implementation preserves the source compact-row endpoint behavior, including the terminal clamp required by `msolvelucy` semantics.

![Local-zone solve](diagrams/local_zone_solve.svg)

### 5. Spectral construction and Type50

The source deliberately separates integrated/reduced-grid products from full-grid products:

- `calc_emisab_all` constructs integrated line emissivity/opacity and RRC quantities used by detail/publication paths;
- `calc_emis_all` constructs the emergent full-grid continuum/line opacity/emissivity state;
- `linopac` is the line-profile accumulation primitive used by the Type50 path.

The frozen optimized C++ Type50 implementation changes traversal mechanics, not science: monotone cursors and source-compatible SIMD/scalar helpers reduce repeated range searches while preserving source ordering and the accepted numerical update semantics. In 0.6.53 these files received standardized source-correspondence blocks. In 0.6.54 the comments remain documentation-only while four oracle/coheat headers are given stable names and `constants.def` is colocated with the C++ sources. The non-science refactor gate canonicalizes comments/whitespace and reverses only those approved path/identifier relocations; canonical C++ content must remain identical to 0.6.53.

### 6. Publication and terminal-state ownership

Output is not a passive serialization of one universal state. The Fortran source has multiple publication owners with different lifetimes:

- `savd` and `fstepr*` publish per-shell detail state and also provide the persistence substrate used by `unsavd` on later passes;
- `pprint` owns STEP text surfaces and `xout_abund1.fits` accumulation/finalization;
- `writespectra`, `writespectra2`, `writespectra3`, and `writespectra4` own the final spectrum, line, continuum, and RRC products respectively.

The final zero-thickness evaluation and the lifetime of local producer workspaces are therefore scientifically observable at publication surfaces. The accepted C5 709/762 repair and the accepted Ca/O structural exceptions are consequences of this ownership model, not changes to matrix physics.

![Publication ownership](diagrams/publication_ownership.svg)

## Python architecture

The Python implementation has two roles:

- a source-faithful executable reference/debug implementation;
- the controller/envelope for qualified C++ kernels and the shared production-zone path.

Major source-correspondence modules include:

| Python module | Primary source role |
|---|---|
| `atomic_database.py` | `readtbl`/`setptrs` packed database and one-based pointers |
| `ion_balance.py` | pre-matrix `calc_ion_rates -> istruc/ioneqm` |
| `element_equilibrium.py` | `levwk*`, `calc_hmc_ion`, matrix assembly, `msolvelucy` |
| `local_zone.py` | `calc_hmc_all` fixed-state element/thermal aggregation |
| `dsec.py` | source-ordered thermal/charge nonlinear controller |
| `emissivity.py` | `calc_emisab_*` integrated emissivity/opacity path |
| `emergent_emissivity.py` | `calc_emis_*`, `linopac`, full-grid spectral path |
| `radial_transfer.py` | `step`, `trnfrc`, `stpcut`, `trnfrn`, `savd/unsavd` orchestration |
| `radial_control.py` | inline `xstar.f90` pass/density control predicates |
| `saved_radial_state.py` | persistence semantics of `savd/unsavd` |
| `pprint_legacy.py` | STEP print-option semantics |
| `output_writers.py` | detail/final FITS publication ownership |
| `physical_runner.py` | executable-style parameter/state orchestration |

Some of these are frozen source files. Milestone 2 does not alter their bytes; their source correspondence is recorded in documentation and the machine-readable concordance.

## C++ architecture

The accepted C++ path is not a separate scientific model. It is a source-equivalent/optimized implementation of qualified operations plus standalone orchestration.

Important ownership areas are:

- `xstar_atdb_runtime.cpp`: native ATDB traversal, pointer/layout construction, parameter/default-real compatibility;
- `local_zone_engine.cpp`, `element_engine.cpp`, `matrix_kernels.cpp`, `level_population.cpp`, `rate_kernels.cpp`: local rate/matrix/population solve;
- `thermal_kernels.cpp`: source thermal leaves/reduction;
- `line_emissivity.cpp`, `opacity_kernels.cpp`: line/RRC/full-grid spectral kernels including Type50;
- `xstar_engine.cpp`, `xstar_run_state.*`: production state orchestration;
- `xstar_science_fits.cpp`: final/detail FITS publication;
- `xstar_step_log.cpp`: STEP/public text publication;
- `xstar_standalone.cpp`: standalone native controller;
- `cpp_backend_production_zone.py`: Python-to-native production-zone ABI (`6048110`).

All production C++ science remains pinned to the accepted C++44 baseline. Starting in 0.6.53, concise Fortran-source comments are carried in marked `XSTAR-SOURCE-CORRESPONDENCE` blocks. Version 0.6.54 additionally permits only the manifest-listed header/namespace/include relocation; a dedicated canonical non-comment gate must reduce every C++ file back to the 0.6.53 canonical content. Any other token-level change remains a freeze violation. Optimization correspondence and invariants are recorded in `python_cpp_fortran_concordance.md`.

![Backend dispatch](diagrams/backend_dispatch.svg)

## Backend interpretation before the public-mode refactor

The current tree exposes several historical/internal backend flags. Conceptually they map to four execution envelopes that Milestone 3 will name publicly:

- Python controller + Python scientific kernels;
- Python controller + modular qualified C++ kernels;
- Python controller + shared production-zone C++ evaluator;
- standalone C++ controller + the same frozen production science.

Milestone 2 documents this relationship only; it does not introduce the public backend enum or change dispatch behavior.

## Scientific invariants that architecture work must preserve

1. **Indexing:** canonical atomic-data and compact-level identity remains source/one-based where the source uses one-based indexing.
2. **Ordering:** source record and producer order is part of accepted behavior when floating-point accumulation or rank publication depends on it.
3. **Kinds:** default-REAL/default-INTEGER conversion semantics are preserved where they affect executable results.
4. **Workspace lifetime:** producer-local arrays are not assumed to survive unless the source explicitly persists or republishes them.
5. **Two-stage population solve:** preliminary ion selection and full statistical-equilibrium solve remain separate.
6. **Thermal iteration:** `dsec` remains the source nonlinear controller; it is not replaced by a generic numerical root solver.
7. **Publication separation:** numerical science, rank/order/identity diagnostics, and inventory diagnostics remain separate acceptance dimensions.
8. **Type50:** optimized traversal must retain source-equivalent profile arithmetic and update ordering under accepted qualification gates.
9. **ABI:** production-zone ABI `6048110` remains frozen until deliberately versioned.
10. **Accepted exceptions:** the frozen Ca/O `xo01_detal3` membership exceptions remain explicit metadata and must not be hidden by broader tolerances or model-specific physics.

## Refactor gate

Before merging a refactor that touches scientific behavior or a module listed by `qualification/source_concordance.json`:

1. identify the concordance ID(s) in the change description;
2. establish and run at least one current runnable characterization test for each affected behavior; preserve the listed historical characterization/qualification lineage as evidence;
3. run `python tools/qualification/check_parity_freeze.py`;
4. run `python tools/qualification/check_source_concordance.py`;
5. if a frozen/pinned source must change, treat it as a dedicated science/refactor qualification rather than ordinary productization.

See `fortran_source_map.md` for the routine-level map and `python_cpp_fortran_concordance.md` for the implementation/qualification matrix.


## 0.6.55 Python source-comment overlay

The production Python source now carries marked Fortran/source-correspondence comments parallel to the C++ comments. The comments also document the atomic-database distinction between **data type** (record formula/interpretation in `ucalc`) and **rate type** (downstream use of the returned rates). The overlay is comment-only: removing the marked leading block from every annotated module must reproduce its exact `0.6.54` bytes. See `python_fortran_source_comments.md` and `qualification/python_source_comment_overlay.json`.


## 0.6.56 active Python namespace cleanup

The active `xstar_tools.xstar` namespace contains runtime/scientific modules plus only those diagnostics that still have live callers. One-off parity-campaign audits, attribution scripts, closure/replay tools, and their dedicated tests live under `historical/python/xstar_parity_campaign/` and are excluded from normal distributions. Active `src/`, `tests/`, and `tools/` must not import those archived modules; this is enforced by `tools/qualification/check_python_history_cleanup.py`.
