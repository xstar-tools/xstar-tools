# Changelog

This changelog summarizes the major **scientific, numerical, performance, interface,
and distribution changes** in [xstar-tools](https://github.com/xstar-tools/xstar-tools).
It is organized by substantive release groups rather than every experimental
subversion. Routine documentation updates, examples, one-off diagnostics, and
intermediate CI or qualification repairs are consolidated. Milestone numbers
are not necessarily published PyPI or conda-forge versions. Full experimental
history remains available through the Git commit and tag history.

## Scientific and compatibility baseline

- **Reference implementation:** FORTRAN XSTAR 2.59g. Scientific equivalence is
  assessed against frozen FORTRAN products and, where appropriate, an accepted
  C++ baseline. Building or installing a package does not by itself establish
  numerical or physical equivalence.
- **Accepted science revision:** `0.6.90.5.5`, requalified and frozen in package
  `0.6.90.5.8`. The preceding science freeze was
  `0.6.48.12.3.45.3.3.8`. A package version is not necessarily a new science
  revision.
- **Stable native interfaces:** C API ABI `60487`, production-zone ABI
  `6048110`, fixed-state interfaces `60486`/`60488`, and XSPEC-table ABI `1`
  across the later frozen-science portability and packaging work.
- **Atomic database:** the scientific `atdb.fits` reference data are supplied
  separately, not included in regular packages. `coheat.dat` is likewise
  discovered at runtime where needed.
- **Qualification policy:** discrete states, iteration trajectories, record
  identity, and file schemas have exact checks; physical arrays and spectra
  are assessed under the applicable frozen numerical criteria. Failed or
  incomplete qualifications are not reported as accepted releases.

## 0.6.91.5 — Linux ARM64 conda-forge availability (2026-10-09)

**Status: ACCEPT — architecture enablement, not a new science release.**

- Enabled conda-forge `linux-aarch64` builds through the independent feedstock,
  rerendered its CI (feedstock PR #6), and passed the native ARM64 build matrix.
- Confirmed published conda-forge packages for **xstar-tools `0.6.90.5.8`** on
  Linux AArch64 for Python **3.11, 3.12, 3.13, 3.14, and 3.15**. The published
  conda package version is `0.6.90.5.8`, not the `0.6.91.5` milestone number.
- Added native `ubuntu-24.04-arm` source-build and installation qualification,
  using an exact local source distribution and conda-forge-provided CFITSIO.
- Preserved existing `linux-64`, `osx-arm64`, and `osx-64` conda packages.
  Windows conda support remains explicitly excluded.
- Preserved the accepted source science revision, floating-point policy,
  numerical tolerances, native ABI values, and the external atomic-data model.

## 0.6.91.1–0.6.91.4 — Linux ARM64 build, scientific testing, and PyPI packaging (2026-10-08)

### Native ARM64 build (`0.6.91.1`)

- **Status: ACCEPT.** Qualified a Linux AArch64 native source build and link
  on `ubuntu-24.04-arm`, distinguishing native execution from cross-compilation
  or emulated x86 binaries.
- Verified all 14 native shared libraries and five executables, together with
  their ELF architecture, dependencies, loader behavior, frontend startup,
  ABI/version identity, and frozen source hashes.
- Retained the existing non-MPI production target, strict floating-point
  compiler policy, and exact science-source freeze.

### ARM64 science qualification (`0.6.91.2`)

- **Platform-level scientific regression: ACCEPT.** Native ARM64 physics and
  retained fixed-state reference checks passed, covering the established
  platform regression scope.
- Added tests for fixed-state calculations, spectral products, heating and
  cooling, convergence behavior, and retained STEP/FITS reference products.
- Defined a separate full real-model comparison requiring authenticated
  `atdb.fits`, `coheat.dat`, and pre-existing FORTRAN/accepted-C++ reference
  hashes, including single-element and multi-element cases with `mnabund=1`.
- **Independent full real-model host result: `NOT_RUN`.** The additional
  external, hash-pinned model/reference bundle was unavailable. This is an
  unexecuted optional comparison, not a failed numerical test or a reversal
  of the accepted platform-level regression. Synthetic FITS comparator
  fixtures test comparison logic; they are not physical acceptance oracles.

### Native PyPI wheels (`0.6.91.3–0.6.91.4`)

- Implemented `manylinux_2_28_aarch64` wheel construction, auditwheel repair,
  and isolated post-install native checks, without bundling `atdb.fits` or MPI.
- Recorded accepted ARM64 packaging results for CPython **3.11 and 3.13**;
  the broader release matrix was not thereby established for every Python
  version.
- **Five-host cross-platform closure (`0.6.91.4`): ACCEPT.** All five native
  CPython 3.13 wheel/build and clean-installed-runtime qualification jobs
  passed on Linux x86_64/AArch64, macOS arm64/x86_64, and Windows UCRT64 AMD64;
  the independent aggregate accepted the five-host result.
- This acceptance applies to the qualified CPython 3.13 wheels, not to every
  version in the broader PyPI release matrix, and is not evidence that a new
  PyPI source release was published or that the optional ARM64 full-model
  comparison ran.
- No accepted physics formulas, C++ numerical algorithms, or frozen native
  scientific ABI values changed during this ARM64 packaging series.

## 0.6.90.5.5–0.6.90.5.8 — Mn Type-49 physics correction and science refreeze (2026-10-05)

**Status: accepted scientific change. Science revision `0.6.90.5.5`.**

### Source-faithful Type-49 handling (`0.6.90.5.5`)

- Corrected native lowering of Type-49 atomic records that the FORTRAN `ucalc`
  implementation returns from **before** accessing photoionization-curve data.
  Such records must not be rejected simply because they lack a full curve.
- Preserved source records with `idest1 <= 0`, `idest1 >= nlevp`, or
  `nrdt <= 0` in their original order, with a zero scientific contribution,
  rather than raising an incorrect `short payload` error.
- Added an explicit internal source-skipped opcode. The record retains its
  identity and ordering but does not add a transition-matrix, opacity, or
  spectrum contribution.
- Made genuine malformed-payload errors more informative without weakening
  the validity checks for records that must execute the Type-49 integral.
- Preserved the XSTAR Manual's abundance defaults, notably **`mnabund=1.0`**.
  Disabling Mn or changing a physical input default was not accepted as a
  workaround for the original failure.

### FORTRAN scientific requalification (`0.6.90.5.8`)

- Requalified the correction against FORTRAN XSTAR 2.59g using the all-element
  model with `mnabund=1`, then explicitly advanced the accepted science
  revision to the version where the numerical behavior changed: `0.6.90.5.5`.
- Obtained exact STEP trajectory and exact `ntotit` agreement in the retained
  comparison.
- Measured Mn ionic-fraction normalized L1 difference at or below `4.60e-3`
  and Mn heating/cooling difference below `9e-4`.
- Confirmed that material differences in public spectra, continuum,
  recombination continua (RRC), and common lines remained within the
  established **1% normalized-L1** envelope.
- Kept first-zone detailed-product row-inventory differences visible as
  structural diagnostics; later-zone row inventories matched.
- No C API, production-zone, fixed-state, or XSPEC-table ABI changes were made.

### Related runtime improvements (`0.6.90.5.3–0.6.90.5.7`)

- Preferred an initialized HEASoft CFITSIO installation, with fallback to
  standalone discovery through `pkg-config`, Homebrew, or normal linker paths.
- Made standard `xstar-cpp` text output resemble FORTRAN XSTAR's physical
  zone/pass progress rather than printing extensive version-tagged telemetry.
- Retained the diagnostic stream under `--debug` or `XSTAR_CPP_DEBUG=1`,
  without removing numerical counters or changing physical calculations.

## 0.6.90–0.6.90.5.2 — Conda-forge distribution and project cleanup (September 2026)

**Status: conda-forge release campaign accepted. No physics change.**

- Replaced the historical conda recipe seed with a modern conda v1 recipe,
  based on a specified PyPI source distribution and SHA-256.
- Added a dedicated `conda` native build profile using conda's external
  CFITSIO dependency, omitting optional MPI and Python-embedding components.
- Qualified native conda source builds on Linux x86_64, macOS arm64, and
  macOS Intel x86_64 (`0.6.90.1`).
- Verified the public conda-forge **`0.6.89.5`** packages on `linux-64`,
  `osx-arm64`, and `osx-64` by clean-installing them and testing native
  command-line programs, loader/ABI surfaces, and a pinned offline
  bremsstrahlung calculation (`0.6.90.2`).
- Clarified that native Windows support uses **PyPI/MSYS2 UCRT64/MinGW-w64**;
  Windows conda, MSVC, and Windows MPI are not supported or planned.
- Consolidated obsolete development reports and one-off qualification scripts,
  retaining the compact active parity-freeze/source-hash policy (`0.6.90.3`).
- Improved Python/native API documentation, the CLI reference, Sphinx HTML,
  and LaTeX/PDF generation (`0.6.90.4–0.6.90.5.2`). These documentation-only
  subversions are not treated as separate scientific milestones.

## 0.6.89–0.6.89.5 — Native cross-platform PyPI wheels (September 2026)

- Reworked packaging so Python wheels include the native C++ libraries and
  executables required by the supported, non-MPI runtime.
- Added Linux x86_64 `manylinux_2_28` wheel builds with pinned CFITSIO and
  auditwheel repair (`0.6.89.2` and qualification fixes).
- Added native macOS arm64 and Intel x86_64 wheels using `delocate` and
  architecture-specific Mach-O dependencies (`0.6.89.3`).
- Added Windows AMD64 Python wheels built with MSYS2 UCRT64/MinGW-w64 and
  repaired with `delvewheel`, including the required CFITSIO and MinGW DLL
  discovery (`0.6.89.4` and follow-up packaging fixes).
- Provided native `xstar-cpp`, `xstar-xspec-initable`, `xstar-xspec-table`,
  and `xstar-xspec` alongside the public Python interfaces. MPI binaries
  remain outside ordinary wheels and require a separate native build.
- Kept the optional standalone Python-embedding plugin outside the ordinary
  wheel payload to avoid runtime dependence on a bundled `libpython`.
- Consolidated Linux/macOS/Windows artifact production and native smoke checks
  into the `0.6.89.5` cross-platform release-closure campaign, with a
  CPython 3.9–3.14 wheel matrix. Its upload-ready bundle/qualification status
  must not be confused with proof that each artifact was published. Native
  architecture, repair, loader, and ABI checks do not alter scientific formulas.
- Retained external `atdb.fits` discovery. Repaired PyPI wheels carry their
  necessary CFITSIO runtime dependencies; conda instead uses conda CFITSIO.

## 0.6.88–0.6.88.6.1.2.1 — Native portability: Linux, macOS, Windows (August–September 2026)

**Status: four-host non-MPI qualification accepted.**

- Introduced common Makefile variables for native library/executable names,
  platform-specific linking, rpaths, threads, and filesystem support.
- Added a shared dynamic-library layer: `dlopen`/`dlsym` on Linux/macOS and
  `LoadLibraryW`/`GetProcAddress` on Windows. Loader and plugin lookup now use
  `.so`, `.dylib`, or `.dll` as appropriate.
- Added a platform process abstraction for local child-process execution.
  Windows uses `CreateProcessW` rather than attempting POSIX `fork()`.
- Completed macOS native compile/link closure with Mach-O `@rpath` install
  names and `@loader_path` sibling-library discovery on arm64 and Intel.
- Completed the Windows MSYS2 UCRT64/MinGW-w64 build, including PE DLLs,
  import libraries, path conversions at CFITSIO/C boundaries, loader behavior,
  embedded-Python DLL lookup, and process-based XSTAR2XSPEC scheduling.
- Strengthened fixed-state cross-platform comparison: exact discrete states,
  record visits, FITS schema, and row identities; nonidentical finite
  floating-point values must meet both the `1e-13` relative and `64` ULP
  bounds where exact bytes are compiler/architecture-dependent.
- **Accepted hosts (`0.6.88.6.1.2.1`):** Linux GCC x86_64, macOS Apple
  Silicon arm64, macOS Intel x86_64, and Windows UCRT64 AMD64.
- Preserved the accepted C++ science revision and public ABIs. **Windows MPI
  is not supported**; Linux HPC MPI remains a separately built capability.

## 0.6.83–0.6.87 — Native XSTAR2XSPEC planning and parallel execution (August 2026)

### Native grid generation (`0.6.83–0.6.83.2`)

- Implemented `xstar-xspec-initable` as the native XSTAR `xstinitable`
  replacement, constructing parameter grids with canonical interpolated,
  additive, and constant parameter classes.
- Preserved source parameter ordering, logarithmic/linear float32 sampling,
  highest-index-fastest Cartesian traversal, and 1-based `loopcontrol` values.
- Wrote the canonical `xstinitable.lis` and initial `xstinitable.fits` table.
  The frozen 2-by-3 MPI_XSTAR fixture has six jobs and a byte-exact command
  list, with FITS stable fields compared apart from volatile metadata.
- Made `xstar-cpp` command emission the default while retaining
  `--xstar fortran`. Added IRAF-style parameter-file and trailing
  `name=value` overrides without changing grid mathematics.
- Added fallback discovery of `atdb.fits` and `coheat.dat` from
  `$HEADAS/refdata`, behind explicit paths and `XSTAR_DATA`.

### Serial and local-process orchestration (`0.6.84–0.6.85.1`)

- Added native `xstar-xspec`: grid generation, isolated `xstar-cpp` jobs,
  source-ordered STEP concatenation, and final XSPEC table publication.
- Reproduced the four canonical frozen table payloads—AIN, AOUT, MTABLE, and
  ETABLE—bit-exactly in the retained 2-by-3 reference grid.
- Added bounded local-process parallelism while preserving `loopcontrol` as
  the sole final-output placement key, independent of worker completion order.
- Repaired the first parallel-host failure so scheduler logs or unrelated
  files can coexist with XSTAR products. Failed runs retain incomplete
  products for inspection rather than deleting them.
- Added per-job success markers and restart checking that prevents partial
  failed jobs from being reused as successful results. The corrected four-job
  host run and restart were accepted in `0.6.85.1`.

### True MPI (`0.6.86–0.6.87`)

- Added optional `xstar-xspec-mpi`, using an MPI-3 atomic work counter to
  distribute pending grid jobs dynamically across ranks.
- Allowed every rank, including rank 0, to execute a child job. Rank 0 alone
  handles canonical plan creation and final STEP/table assembly after global
  success.
- Preserved the already-qualified file-based inter-stage interface;
  intermediate FITS and STEP products require a **shared filesystem**.
- Subsequent real-host qualification accepted a two-rank four-job execution
  and restart reusing all completed jobs.
- Standardized `--processes N` for ordinary local processes (with `--workers`
  and `-j` aliases). MPI uses launcher-level `-np N`; these concepts are
  intentionally distinct.

## 0.6.82.31–0.6.82.40.2.46.1 — Production C++ speed and memory (August 2026)

**Goal:** reduce C++ overhead while keeping the frozen FORTRAN-equivalent
scientific trajectory, output products, source-record order, and strict
floating-point semantics.

### Compact atomic execution and bound-free workspaces (`0.6.82.31–0.6.82.37`)

- Reused immutable source-program information rather than rebuilding
  expensive record lookups, matrix-only state, and atom/ion selectors.
- Introduced compact hot execution headers and source-order record indexes,
  separating frequently accessed evaluator fields from cold publication
  metadata without changing atomic source identities.
- Reduced retained Type-49/53 bound-free sidecar and revisit storage. Cached
  `sgbar` values only for source intervals actually consumed by the integral,
  not dense unused grids; exact values and integration order were preserved.
- Reduced accepted-boundary duplication of evaluated records and diagnostics,
  using compact publication rows while retaining richer states for explicit
  forensic/reference modes.
- Removed dead temporary vector capacities and avoided unnecessary allocator
  retention across radial-zone publication. These were ownership/lifetime
  optimizations, not physical-rate recalculations.

### Spectral/Type-50 and publication improvements (`0.6.82.38–0.6.82.39.2`)

- Replaced large sparse Type-50 profile schedules with a compact indexed
  representation tied to the compiled `ProgramRecord`. The broad reference
  dense schedule occupied about **2.13 MB**, versus about **152.7 MB** for
  the preceding sparse schedule reported in the development record.
- Introduced direct spectral-record indexing and corrected a reconstruction
  performance regression without changing opacity sums or source ordering.
- Optimized Type-50 small-core bound searches and AVX2 far-wing offsets while
  preserving the historical scalar profile, rebinning, and sequential
  accumulation semantics.
- Transferred publication-state and spectral-buffer ownership rather than
  creating duplicate full-sized arrays. Exact products remained a gating
  condition for accepting these paths.
- The broad-model memory program reduced the retained working-set footprint
  substantially; individual intermediate candidates were rejected when they
  improved only time or only memory while violating frozen guardrails.

### Low-ionization and controller hot paths (`0.6.82.40.2.x`)

- Used controlled H+He+C models at `rlogxi=-3`, `+1`, and `+4` to separate
  algorithmic work from observation overhead and compiler effects. Source
  science and STEP outputs had to remain equivalent to the frozen FORTRAN
  references during each accepted optimization.
- Reused the already-live reduced-continuum workspace; removed redundant
  grid rebuilding, copies, and temporary diagnostic vectors.
- Reduced contribution-list map construction, repeated element traversal,
  and unnecessary post-pass discovery, preserving canonical contribution
  order and matrix identities.
- Streamlined detailed RRC and spectrum/FITS publication by avoiding redundant
  row copies, map construction, and generic scalar dispatch where exact
  retained workspaces were already available.
- Reduced redundant canonical thermal-ledger fingerprint scans on trusted
  production paths. Rich diagnostic/forensic paths retain their validation.
- Optimized SAVD snapshot materialization and move ownership while retaining
  source `REAL(4)` quantization, FITS-E3 publication conversion, and historic
  multipass restore semantics.
- Retained the strict portable GCC `-O3` floating-point policy; speculative
  compiler and numerical shortcuts were not silently promoted.

### Production baseline and benchmarking (`0.6.82.40.2.46.1`)

- **Maintainer-accepted production base:** `0.6.82.40.2.46.1`. Its formal
  performance-gate history, including narrowly rejected individual runs,
  remains auditable and is not retroactively relabeled.
- The later accepted multi-element `xi=1`, `ne=1e12` workstation C++ case
  took approximately **11 minutes** with peak RSS about **3.69 GB**, compared
  with a FORTRAN reference near **15 minutes** and approximately **2.55 GB**.
  These are case-specific results, **not** a claim of universal C++ speedup.
- Low-ionization regimes can still be slower than FORTRAN; the broad and
  high-ionization outcomes do not justify asserting a uniform acceleration.
- Numerous attempted changes were explicitly rejected or left as
  attribution-only experiments (including alternative Type-50 preparation,
  Type-53 exponent reuse, and other speculative caching/ownership paths).
  The production ancestry follows accepted scientific and performance gates.

## 0.6.82.29–0.6.82.30.8.14 — Detailed outputs and Fe/Al/N parity (August 2026)

### Source-equivalent public and detailed outputs

- Reconstructed and qualified FORTRAN-style public output options, including
  continuum opacity/emissivity, line energy and luminosity, detailed
  recombination continua, atomic identifiers, thermal totals, and other
  `pprint`/`lprint` products.
- Corrected publication-only differences in line selection, source-local
  endpoint eligibility, energy-bin ownership, local widths, pre-/post-smoothing
  state, and final pass accumulation. The distinction between **physical
  state changes** and **serialization/publication corrections** remained
  explicit during validation.
- Repaired `npass=1` SAVD/detail ownership and source-faithful pass/final
  lifetime, preserving the numerical values and row order delivered to FITS.
- Added systematic tests for the XSTAR Manual Table-1 parameter defaults and
  individual parameter controls, not only common benchmark configurations.

### Fe atomic rates and matrix orientation (`0.6.82.30.8.x`)

- Corrected source identity for Fe Type-57 packed shell quantum numbers and
  Type-75/96 Fe satellite endpoints.
- Corrected **Type-82 unresolved transition array (UTA)** endpoint orientation:
  the two source levels must be arranged by their actual energies at the
  fixed-program boundary before inserting matrix terms.
- Eliminated an upper/lower-level transpose that affected the Fe population
  matrix. The isolated Fe comparison then accepted the FORTRAN STEP path,
  `ntotit`, material results, and public spectrum.
- Follow-up performance changes to hot-record storage and deferred
  publication retained the corrected physical source identities and rates.

### Nitrogen and aluminum corrections

- Corrected source-zero cases for Type-50/91 wavelength handling and Type-56
  degenerate/interpolation boundaries, eliminating spurious **N VI** rate and
  matrix contributions (`0.6.82.30.8.12`).
- Corrected **Al XII Type-70** next-ion level and threshold ownership and
  source-equivalent bound-free integration (`0.6.82.30.8.14`).
- **Accepted broad multi-element qualification at `0.6.82.30.8.14`:** the
  retained physical STEP structure, exact `ntotit`, material scientific
  results, and public spectrum met the FORTRAN reference criteria.
- The subsequent `0.6.82.30.8.15` detailed-publication inventory repair was
  a **candidate**. Its N VI/O IV/Mg II/Si VI/Ni VI inventory proposals were
  deferred, not incorporated into the accepted `0.6.82.30.8.14` science
  baseline or the following performance-production ancestry.

## 0.6.82–0.6.82.28 — Multi-element physics, thermal balance, and convergence (August 2026)

### Atomic data and bound-free rates

- Extended native record lowering for realistic compositions across **Z=1–30**.
  Retained source-valid atomic endpoints even when the raw destination lies
  beyond a compact element-matrix dimension; applied the source matrix alias
  only at the actual consumption boundary (`0.6.82.1`).
- Generalized source-faithful **Type-49 photoionization/Milne** rate
  commitment to every active element, rather than relying on a special
  H/He/C/Mg behavior split (`0.6.82.11`).
- Generalized **Type-53 recombination/escape** terms to use each record's
  live optical depths, covering fraction `cfrac`, and the canonical source
  escape-factor equations (`0.6.82.10`).
- Promoted the canonical **Type-51 Burgess–Tully collision evaluator** to
  ordinary production across active elements (`0.6.82.12`).
- Maintained FORTRAN ion-sequence restrictions and source ordering rather than
  enabling a process solely because a type exists in the atomic catalog.

### Thermal and population corrections

- Corrected **Type-85 heavy-element photoheating** endpoint/answer-channel
  ownership, restoring nonzero scientific heating that was missing from the
  multi-element C++ path (`0.6.82.4–0.6.82.5`).
- Restored the FORTRAN division between trial-state HMC evaluations and full
  emission/spectrum work. Intermediate DSEC temperature/electron trials do
  not needlessly publish a complete accepted-state spectrum.
- Corrected the low-temperature **Type-63** collision cutoff at `delt > 50`
  (`0.6.82.7`) and the persistent `rnisi(20000)` LTE workspace lifetime
  (`0.6.82.8`).
- Corrected the **`msolvelucy`** fixed-point iteration control and its
  population/convergence behavior (`0.6.82.9`). These corrections affect
  physical solution trajectories, not just diagnostics.
- Restored last-physical-zone STEP reporting and literal DSEC `ntotit`
  values rather than reconstructing convergence histories after the solve
  (`0.6.82.5–0.6.82.6`).

### Qualification boundaries

- Exercised low-, moderate-, and high-ionization regimes, including model
  families that diverged at different slab depths. Intermediate science
  proposals remained open until actual reference runs met the frozen gates.
- Extended source-equivalent `npass`, `lwrite`, and `lprint` behavior and
  multipass/SAVD detailed-publication ownership (`0.6.82.27–0.6.82.29`).
- The later Fe/Al/N and multi-element scientific acceptance is described in
  the next release group; not every `0.6.82.x` intermediate experiment was
  independently accepted.

## 0.6.69–0.6.81.1 — Public tools and XSPEC table parity (August 2026)

- Promoted **`xstar-cpp`** to a standalone, Python-independent native
  frontend with parameter-file input, trailing `name=value` overrides,
  atomic-data discovery, status/progress output, and native ABI checks.
- Consolidated user-facing Python APIs and CLI commands for execution,
  atomic-data exploration, output reading, diagnostic comparisons, and
  backend selection without changing accepted scientific formulas.
- Reproduced canonical XSTAR2TABLE energy-edge indexing: the upper energy
  index represents an **edge**, so the table-bin count is `high-low`, not
  `high-low+1` (`0.6.81.1`).
- Restored the source C floating-point normalization order for additive
  AIN/AOUT spectra rather than prematurely rounding a constant to float32.
- Verified bit-exact `ENERG_LO`, `ENERG_HI`, `PARAMVAL`, and `INTPSPEC`
  payloads for the four canonical XSPEC products of a frozen 2-by-3 grid.
- Continued layered qualification: model/STEP parity, accepted scientific
  tolerances, exact record/file contracts, and product-level regression.

## 0.6.48.12–0.6.48.12.3.45.3.3.8 — All-element coverage and first science freeze (July–August 2026)

### Complete physical UCalc type coverage

- Extended the native atomic-data lowerer from **32 previously qualified
  physical types to all 78 physical FORTRAN UCalc data types** across Z=1–30.
- Implemented source-generic fallback evaluation for previously unsupported
  analytic, collision, ionization/recombination, charge-transfer, bound-free,
  and bound-bound types; preserved source aliases where equivalent kernels
  already existed (including Type-52/Type-91 aliases).
- Added all-element full-grid opacity publication, not just matrix-rate
  coverage, for newly active continuum-producing processes.
- Added an audit of physical source-type coverage and a Z=1–30 installed
  atomic-data inventory; encountered unsupported physical records were
  treated as errors rather than silently ignored.

### Source-state and publication parity

- Promoted generic Type-49/53 photoionization and recombination integrals,
  matching their source record contexts and supporting active elements
  outside earlier H/He/Mg-specific cases.
- Corrected Ca level, ionization-stage, and thermal/source-output ownership,
  plus source-order level populations and scientific state propagation.
- Corrected live radius-dependent ionization parameter, hydrogen entry-state
  ownership, and terminal thermal state handling in native zone execution.
- Repaired detailed line/RRC/abundance and opacity/emission publication for
  Ca, O, and other qualified ion cases without substituting publication
  adjustments for changes to physical solvers.

### Scientific freeze

- Established **`0.6.48.12.3.45.3.3.8`** as the accepted science parity
  reference used for subsequent productization, performance optimization,
  cross-platform builds, and binary distribution.
- Preserved source SHA-256 checks, numerical comparison baselines, and public
  ABI boundaries around later work. The freeze label identifies the accepted
  science configuration, not every future package's release version.

## 0.6.44–0.6.48.11 — Python-to-C++ scientific-engine migration (June–July 2026)

### Native interfaces and element solves (`0.6.44–0.6.45`)

- Added stable native C interfaces, persistent C++ backend contexts, and
  controlled Python/C++ backend selection.
- Migrated source-ordered element rate matrices, heating/cooling terms,
  population normalization, and the Lucy/fixed-point solve to C++.
- Compared native element/rate outputs with Python and FORTRAN references,
  retaining explicit fallback paths during the incremental transition.

### Opacity, radiative transfer, and thermal balance (`0.6.46–0.6.47`)

- Corrected **Type-50 line-center opacity** and Gaussian/Voigt profile
  integration, including the source `huntf` boundary convention, rounding
  order, floating-point contraction policy, and sequential accumulation.
- Added native continuum, line, and RRC heating/cooling contributions and
  stateful radial transport and thermal balance.
- Introduced source-equivalent DSEC temperature/electron convergence,
  with accepted-zone state carried forward into subsequent radial calls.

### Standalone production (`0.6.48–0.6.48.11`)

- Produced a compiled native science path supporting a qualified case with
  **61 callback-free evaluations**, the nine standard scientific FITS
  outputs, and FORTRAN-style STEP logging.
- Extended the fixed-state record evaluation to a persistent zone engine
  with prepared Type-49/53 bound-free inputs and complete emission/opacity
  publication.
- Added final-spectrum recomputation at the accepted boundary rather than
  treating trial-state diagnostics as final physical outputs.
- Corrected carbon Type-53 committed Milne/recombination rates, live
  hydrogen ionization entry state, and `xi = L/(n r^2)` radial evolution.
- These releases established the C++ architecture that the later
  all-element qualification and performance campaigns hardened.

## 0.6.0a–0.6.43 — Early native acceleration (May–June 2026)

- Renamed the project/distribution from **`xstar-atomic`** to **`xstar-tools`**
  while carrying forward the atomic-data APIs.
- Introduced initial C++ atomic-rate and matrix-building kernels, first
  targeting selected Mg processes and progressively larger element operations.
- Added native interfaces for emissivity, opacity, line profiles, rate
  contributions, and population matrices with source-order comparisons.
- Retained Python fallbacks for paths not yet scientifically qualified.
  One-off microkernel speedups were not treated as evidence of whole-model
  acceleration or parity.

## 0.3–0.5 — Source-guided Python XSTAR science implementation (April–May 2026)

- Developed a Python implementation of XSTAR-style level-population solving,
  atomic rate evaluation, adjacent-ion coupling, temperature balance, and
  line/continuum emissivity.
- Translated FORTRAN physical families, including Type-50 radiative-line
  opacity; Type-51/56/63 collisions; Type-53 bound-free recombination;
  Type-59/99 source-record behavior; and line escape/source emission terms.
- Reconciled the FORTRAN matrix assembly, accumulation order, population
  normalization, and Lucy convergence behavior in the Python reference path.
- Corrected live hydrogen/charge-exchange coupling and removed ordinary
  production numerical rescue strategies that were not part of the source
  solver's scientific contract.
- Expanded STEP logging, detailed line and RRC outputs, FITS publication,
  and FORTRAN-style print options. Compared physical state separately from
  output row inventory, source identifiers, and metadata differences.
- Used the Python implementation as a scientific stepping stone toward the
  persistent native C++ runtime, not as a substitute for FORTRAN acceptance.

## 0.1–0.2 — Atomic-data toolkit foundations (February–April 2026)

- Introduced the original **`xstar-atomic`** toolkit for working with XSTAR
  atomic data stored in `atdb.fits`.
- Added low-level FITS record access and the high-level **`XSTARAtomic`** API
  for elements, ions, energy levels, transitions, and source record metadata.
- Supported photoionization and recombination inspection, line emissivities,
  transition/collision queries, and Burgess–Tully/CHIANTI-style collisional
  rate families (including Types 51/98 and 56).
- Implemented the Type-63 same-principal-quantum-number `l`-mixing collision
  branch with its physical density/impact-parameter limit.
- Added source-identity checks, real-ATDB smoke tests, and Python command-line
  utilities. The atomic database remained a separate scientific input.

---

**Reading this history:** release-group headings combine related changes; they
do not mean every intermediate candidate was accepted, published, or included
in the final production ancestry. A passed build, wheel smoke, or platform
regression is not an end-to-end FORTRAN scientific model comparison. For
rejected experiments, compiler settings, reference hashes, and detailed
per-model results, consult historical commits, tags, and retained qualification
manifests.
