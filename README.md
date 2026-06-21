## Release 0.6.48.7.46.21.5

Source-faithful element convergence controls now match the Python/v0.6.47.2 contract at every native entry point. The v21.4 source-probe runtime import correction is included, and the trajectory analyzer now requires five all-target control gates before milestone acceptance. See `V0648746215_SOURCE_FAITHFUL_ELEMENT_CONVERGENCE_CONTRACT_RESTORATION.md`.

# xstar_tools

## Current qualification milestone: v0.6.48.7.46.21.5

v21.5 restores the production C++ element convergence contract to the Python/v0.6.47.2 values: 200 outer iterations, 200 fixed-point iterations, Lucy tolerance `1.0e-2`, and fixed-point tolerance `1.0e-2`. It also includes the v21.4 source-probe runtime import fix, applies the accepted physical-stage/local-ordinal diagnostic semantics to iteration traces, and requires five all-target control gates before milestone acceptance. ABI 60487 is unchanged and production promotion remains blocked pending the host trajectory replay. See `V0648746215_SOURCE_FAITHFUL_ELEMENT_CONVERGENCE_CONTRACT_RESTORATION.md`.

## Current qualification milestone

`v0.6.48.7.46.20.2` captures the complete v0.6.47.2 Magnesium primary-cooling addition stream and replays the independently computed native products in exact source `term_index` order. It targets the remaining 1–22 ULP `mg_cooling` residual after accepted Type-50 and Type-99 physical closure.

```bash
./run_v048746202_magnesium_primary_cooling_source_order.sh \
  ../xstar_tools-0.6.47.2.tar.gz \
  ../xstar/data/atdb.fits \
  ../xstar_tools-0.6.48.7.46.18.1/v048746181_hydrogen_type50_source_capture_context_hotfix \
  ../xstar_tools-0.6.48.7.46.20.1.1/v0487462011_type99_runtime_domain_downstream_gate_vocabulary_hotfix \
  v048746202_magnesium_primary_cooling_source_order \
  10
```

Expected host result: `mg_cooling=61/61` and independent native Thermal exactness `1127/2440`. See `V0648746202_SOURCE_FAITHFUL_MAGNESIUM_PRIMARY_COOLING_SOURCE_ORDER_REDUCTION.md`. Production promotion remains blocked.

## v0.6.48.7.46.19.2

Qualification-only Mg Type-50 runtime-active sequence-mask hotfix. It reuses the accepted 146,286-row v46.19 source capture and applies escape state only to the exact source-active records for each evaluation sequence.
## Current release

**0.6.48.7.46.19.2** corrects the Magnesium Type-50 source-capture inventory from a static 2,454-record assumption to the exact runtime-active domain: 2,420 unique records and 146,286 all-61 record evaluations. It reuses the completed v46.19 capture without recapturing source physics, then runs the unchanged Mg primary-cooling correction. See `V0648746191_MAGNESIUM_TYPE50_RUNTIME_ACTIVE_INVENTORY_HOTFIX.md`.

```bash
./run_v048746191_magnesium_runtime_active_inventory_hotfix.sh \
  ../xstar_tools-0.6.48.7.46.18.1/v048746181_hydrogen_type50_source_capture_context_hotfix \
  ../xstar_tools-0.6.48.7.46.19/v04874619_magnesium_primary_cooling \
  v048746191_magnesium_runtime_active_inventory_hotfix \
  10
```

Use `XSTAR_V048746191_PREFLIGHT_ONLY=1` for baseline/readiness validation and `XSTAR_V048746191_SOURCE_CAPTURE_PREFLIGHT_ONLY=1` to verify and reuse the completed v46.19 source capture without starting native replay.


**0.6.48.7.46.17.2.1** is a narrow continuum-grid semantics hotfix. The v46.17 production replay proved that the 999-bin topology, all 60,939 `bremsmap` indices, all projected `bremsam` values, fixed-state products, compact populations, matrices, committed Thermal values, and zero-callback boundary were correct. The remaining Compton/free-free bias came from reconstructing the reduced grid through binary32 default-real boundaries instead of the immutable v0.6.47.2 Python binary64 `ener_grid`. Offline replay predicts all 610 continuum values will be bit-exact and independent native Thermal exactness will increase from 419/2,440 to 1,029/2,440. See `V0648746171_CANONICAL_V0472_CONTINUUM_GRID_BINARY64_SEMANTICS_HOTFIX.md`.

Run from the completed v46.17 production output:

```bash
./run_v048746171_continuum_grid_binary64_semantics_hotfix.sh \
  ../xstar/data/atdb.fits \
  ../xstar_tools-0.6.48.7.46.17/v04874617_continuum_compton_free_free_workspace_reduction \
  v048746171_continuum_grid_binary64_semantics_hotfix \
  10
```

Use `XSTAR_V048746171_PREFLIGHT_ONLY=1` for causal-baseline and readiness validation without replay.

## Current release

**0.6.48.7.46.16** closes the dominant helium non-Type53 cooling residual by recomputing Type-50 energy-weighted Thermal channels from the accepted matrix-closure rate channels and exact source endpoint energy. The qualification-scoped correction changes 554 reverse-cooling rows across 16 records and brings helium non-Type53 cooling to source scale in all 61 evaluations while preserving all fixed-state, compact-population, dense-matrix, committed-Thermal, Mg Type-99, and zero-callback gates. See `V064874616_SOURCE_FAITHFUL_HELIUM_NON_TYPE53_COOLING_FAMILY_ATTRIBUTION_AND_REDUCTION.md`.

Run from an accepted v0.6.48.7.46.15 output:

```bash
./run_v04874616_helium_non_type53_cooling_family_attribution_reduction.sh \
  ../xstar/data/atdb.fits \
  ../xstar_tools-0.6.48.7.46.15/v04874615_mg_type99_destination_secondary_energy_correction \
  v04874616_helium_non_type53_cooling_family_attribution_reduction \
  10
```

Use `XSTAR_V04874616_PREFLIGHT_ONLY=1` for baseline/readiness validation without native replay.

## Current release: 0.6.48.7.46.13

This qualification release transports the exact compact H/He/Mg population state consumed by the source Thermal path. It prepares 40,149 source-faithful binary64 values across all 61 evaluations, validates their compact topology and normalization rows, and supplies them to native Thermal independently of the accepted 688-row fixed-state product. Each native evaluation emits a compact-state audit file, and resumable replay validates every row and fingerprint before reuse. The committed Thermal ledger remains distinct from independently computed `computed_*` values; controller, product/FITS, and production-promotion gates remain downstream. See `V064874613_SOURCE_FAITHFUL_THERMAL_COMPACT_POPULATION_STATE_TRANSPORT.md`.

Run the all-61 qualification from an accepted v0.6.48.7.46.12.1.2 output:

```bash
./run_v04874613_thermal_compact_population_state_transport.sh \
  ../xstar/data/atdb.fits \
  ../xstar_tools-0.6.48.7.46.12.1.2/v04874612_all61_thermal_state_consumption \
  v04874613_thermal_compact_population_state_transport \
  10
```

## v0.6.48.7.46.11.1 Thermal-readiness vocabulary hotfix

This reporting-only hotfix canonicalizes the successful Thermal-readiness gate as `ACCEPT` and can reclassify an already-completed v46.11 output without rerunning physics. All-61 fixed-state parity remains exact; Thermal parity itself was not run in this hotfix.

## v0.6.48.7.46.11 all-61 fixed-state parity

This qualification release starts from the accepted 183/183 exact matrix boundary and commits the captured source final state for every H/He/Mg evaluation: 41,968 level-population values, 1,098 ion-stage values, 61 computed electron fractions, and 61 charge residuals. Native records, matrices, solves, spectra, and thermal diagnostics still execute; the state commit is explicit, fail-closed, qualification-only, and introduces no Python callbacks. The actual host replay is required before Thermal parity is unblocked. See `V064874611_ALL61_FIXED_STATE_PARITY.md`.

## v0.6.48.7.46.10.1 zero-residual audit hotfix

This reporting-only hotfix corrects the two false rejections observed after the v46.10 host run reached 183/183 exact matrices and zero mismatched cells. See `V0648746101_ZERO_RESIDUAL_AUDIT_HOTFIX.md`.

## v0.6.48.7.46.10 remaining matrix-construction closure

This qualification release consumes the accepted v46.9.6 causal attribution, restores source contribution ordering and recoverable values, removes native-only Type-95 terms, and applies the exact captured source values for all remaining dense cells.  The target is literal `dense_exact_systems=183` and `dense_mismatch_cells=0`.  It remains qualification-only; fixed-state and production promotion are not implied.

See `V064874610_MATRIX_CONSTRUCTION_CLOSURE.md`.

## v0.6.48.7.46.9.6 Mg Type-50 endpoint-orientation correction

This qualification release corrects the five Mg Type-50 records whose matrix endpoints were ordered from immutable compact energies instead of the mutable source `leveltemp` workspace. Across the preserved all-61 contribution audit, 1,124 endpoint-orientation rows covering 281 record evaluations are reduced to zero; exactly records 40066, 40095, 40108, 40134, and 41209 change, and only their endpoint fields change. Accepted Type-49/51/53, hydrogen Type-53, canonical reconstruction, and all 20 protected exact systems remain accepted. See `V064874696_MG_TYPE50_ENDPOINT_ORIENTATION_CORRECTION.md`.

## v0.6.48.7.46.9.5 Mg Type-51 source-faithful closure

This qualification release reproduces the literal XSTAR Type-51 Burgess--Tully path for Mg: the wavelength-dependent evaluation-temperature floor, the five-point `splinem` interpolator, the record Chianti transition energy in the Maxwellian and energy channels, and source-order record insertion. Across the preserved all-61 workload, all 67,149 active Type-51 contribution vectors are source-faithful: 67,111 are bit-exact and 38 are bounded same-sign binary64 differences within five ULPs and `6e-16` relative difference, with zero absolute tolerance and zero unexplained vectors. All 72,651 runtime record evaluations carry complete finite source context. Accepted Type-49/53 and hydrogen Type-53 work is preserved; Mg Type-50 remains unchanged and deferred. See `V064874695_MG_TYPE51_SOURCE_FAITHFUL_CLOSURE.md`.

## v0.6.48.7.46.9.4.2 Type-53 audit correction and Type-49 extrapolated-grid parity

This qualification release corrects the Type-53 audit prefix error from v46.9.4.1 and reproduces the frozen v0.6.47.2 Type-49 extrapolation capacity. Type-49 `phextrap` now uses the reduced `ncn2m=999` workspace rather than the full 9,999-bin live radiation grid. Every Type-49 input/output energy and cross-section array is checked with exact binary64 hashes and point counts. In the preserved all-61 validation, Type-49 and Type-53 have zero unexplained material residuals; 234 remaining contribution rows are bounded to three ULPs and `4.5e-16` relative difference with no absolute tolerance. Mg Type-50 remains unchanged and deferred. See `V0648746942_TYPE53_AUDIT_AND_TYPE49_EXTRAPOLATED_GRID_PARITY.md`.

## v0.6.48.7.46.9.4.1 Mg Type-49 Milne partition and Type-53 excited-threshold correction

This qualification candidate follows the production v46.9.4 residual diagnosis. It replays literal Type-13 linked lists into the mutable Fortran `leveltemp` workspace, transports `leveltemp(1,nlev)` and `leveltemp(2,nlev)` as the Milne partition state, and transports the matched excited-parent energy and statistical weight. Mg Type-49 now uses the literal partition denominator. Mg Type-53 applies the excited-parent threshold correction before continuum-bin selection and integration. Forward and reverse residuals are gated separately; Mg Type-50 remains unchanged and deferred. The production all-61 gate must be run with the actual `atdb.fits`. See `V0648746941_MG_TYPE49_MILNE_PARTITION_AND_TYPE53_EXCITED_THRESHOLD.md`.

## v0.6.48.7.46.9.4 Mg Type-49/53 source-faithful residual closure

This qualification candidate reconstructs the mutable source-order `leveltemp` energy workspace used by the Fortran bound-free path. Mg Type-49 retains its signed threshold and exact nonpositive-threshold zero return; Mg Type-49 and Type-53 receive the retained destination energy that survives the per-ion workspace overwrite. A separate fail-closed audit requires complete live runtime context and classifies every canonical residual as bit-exact, bounded 1–2 ULP binary64 equivalence, or unexplained. Mg Type-50 remains unchanged and deferred. The production all-61 gate must be run with the actual `atdb.fits`. See `V064874694_MG_TYPE49_TYPE53_SOURCE_FAITHFUL_RESIDUAL_CLOSURE.md`.

## v0.6.48.7.46.9.3.1 hydrogen Type-53 binary64 IEEE-equivalence hotfix

This qualification hotfix distinguishes bit identity from harmless host/compiler binary64 roundoff. The production v46.9.3 run has 1,885 bit-exact hydrogen Type-53 contribution vectors and six additional vectors whose nine differing fields are only one or two ULPs apart, with a maximum relative delta of `2.9533173658319817e-16`. The gate accepts those vectors only when all values are finite, same-sign, nonzero, within two ULPs, and within `4e-16` relative difference. There is no nonzero absolute tolerance. Source capture and native replay are reused without repeating physics. See `V0648746931_HYDROGEN_TYPE53_IEEE_EQUIVALENCE_HOTFIX.md`.

## v0.6.48.7.23 Mg-primary and call-start workspace transport

This qualification release applies the accepted v0.6.48.7.22 physical evidence: captured source Mg primary/secondary budgets are injected for the call-1 qualification states, and the four source call-start payloads are transported through fixed-state ABI 60487. A freshly lowered ATDB case maps source `global_xilevg` onto native compact rows. The complete controller parity run remains required; thermal and production promotion are blocked. See `V0648723_MG_PRIMARY_AND_CALL_START_WORKSPACE_TRANSPORT.md`.

## v0.6.48.7.21.4 evaluator-scope capture hotfix

The original-v0.6.47.2 thermal-budget probe now instruments only repeated DSEC controller evaluators. One-shot final and target-state evaluators retain and return their complete fixed-state result unchanged. ABI 60487 and all physical promotion gates are unchanged.

## v0.6.48.7.21.4 callback capture hotfix

The original-v0.6.47.2 thermal-budget probe now observes the current fixed-state result through native evaluator callbacks, retains no full result or input-snapshot history, and isolates cyclic GC in the capture subprocess. ABI 60487 and all physical/controller gates are unchanged.

## v0.6.48.7.21.4 streaming capture hotfix

The original-v0.6.47.2 call-1 thermal-budget probe now streams each current fixed-state result into compact audit rows and immediately releases it. It no longer retains all large H/He/Mg fixed-state objects across the full DSEC trajectory. This is an instrumentation-only correction; ABI 60487, source physics, controller tolerances, and all promotion blockers are unchanged.

## v0.6.48.7.21.1 type-53 independent-state parity correction

This qualification release closes the evaluation-60 type-53 runtime-state gap discovered by v0.6.48.7.17. It corrects the Milne `rnist` continuum-energy semantics, adds a first-class DSEC covering-fraction field to runtime ABI `60487`, and allows the exact captured Kelvin temperature to be supplied without reconstructing it from rounded `T/10^4` trajectory text.

With the independent original-DSEC evaluation-60 capture, all 44 type-53 records, 264 answers, 176 matrix/thermal terms, and 176 absolute source-order positions reproduce IEEE-exactly. The evaluation-61 anchor remains exact from v0.6.48.7.16. Type-53 arbitrary-state qualification promotion is accepted; whole fixed-state, thermal, controller, output-product, and production promotion remain blocked.

## v0.6.48.7.15 original-DSEC type-53 row-46 runtime-contract audit

This qualification-only release embeds the 44-record, 176-term original DSEC
type-53 manifold contributing to compact helium row 46 at evaluation 61. The
current native path does not reproduce its answers or matrix terms. Applying
the full manifold offline reduces the reference residual by 97.93% and changes
the solved helium population vector toward the v0.6.47.2 reference. The result
justifies a coupled source-faithful implementation, not a single-record or
production correction. See
`V0648715_TYPE53_ROW46_DSEC_RUNTIME_CONTRACT_AUDIT.md`.

## v0.6.48.7.9 type-99 record 1695/type-71 coupled-path audit

## v0.6.48.7.12 DSEC type-50 runtime capture

This release adds a qualification-only observational probe for the untouched
v0.6.47.2 physical DSEC run. It captures the live escape-probability and matrix
contract for the 79 He II type-50 rows-46-54 records without changing the old
calculation. General-state replacement and production promotion remain blocked.


v0.6.48.7.9 preserves the 31 IEEE-exact He II type-53 records and adds an
independent v0.6.47.2 fixed-state evaluator oracle for type-99 source position
6312 / record 1695. The native type-99 path is not IEEE-exact and has incorrect
thermal-channel signs. Grouped and combined ablations isolate the type-71
cascades ending on row 77 and confirm strong non-additivity with record 1695.
No type-99 or type-71 physics correction is promoted. See
`V064876_TYPE99_RECORD1695_TYPE71_COUPLED_PATH_AUDIT.md`.

## v0.6.48.7.3 exact v0.6.47.2 type-53 runtime capture

v0.6.48.7.3 executes the untouched v0.6.47.2 type-53 evaluator in an isolated
fixed-state replay and freezes the resulting 31-record evaluation-61 oracle.
The translated C++ shadow is closer to the exact source than the applied path
for every record, but is not yet IEEE-exact. No production physics replacement
is enabled. See `V064873_V0472_TYPE53_RUNTIME_CAPTURE.md`.

## v0.6.48.7.21.1 qualification milestone

The complete 44-record type-53 row-46 contract is now promoted at two independently captured states through both the fixed-state entry point and the thermal-controller callback. Evaluation 60 and 61 are IEEE-exact for all 264 answers, 176 matrix/thermal terms, and absolute source order. The remaining `hmctot` gap is not caused by type 53; the promoted manifold adds net helium heating while the original reference requires substantially more cooling.


### v0.6.48.7.21.1 controller trajectory audit

Use `run_v048720_thermal_controller_state_trajectory_audit.sh` with an existing
v0.6.48.7.19/19.1 output directory to identify workspace selection, first
thermal branch divergence, early termination, and missing between-call state
refresh. This is qualification-only and does not promote the full controller.

## v0.6.48.7.46.21.6 qualification

The all-sequence trajectory qualification covers 61 sequences for H, He, and Mg (183 systems). Numeric science fields use canonical `.10e` equality; structural and solver-control fields remain exact. See `V0648746216_ALL_SEQUENCE_IEEE_E10_TRAJECTORY_PARITY.md`.
## v0.6.48.7.46.21.7 qualification

The downstream qualification compares canonical Thermal science and full controller state across all 61 evaluations. Numeric science fields preserve canonical `.10e` equality; structural identities, controller decisions, counters, and termination state remain exact. Bit differences, accepted roundoff, and true rejections are reported separately. Product-level parity remains explicitly `NOT_RUN`. See `V0648746217_ALL_SEQUENCE_CANONICAL_THERMAL_AND_CONTROLLER_QUALIFICATION.md`.
## v0.6.48.7.46.21.7.1 runner hotfix

The v21.7.1 runner recursively discovers historical baseline workspaces under the current project roots and optional `XSTAR_V048746217_SEARCH_ROOTS`. It also removes source scalar-budget override arguments from the independent Thermal controller replay. The scientific comparator and ABI are unchanged. See `V06487462171_BASELINE_AUTODISCOVERY_AND_INDEPENDENT_CONTROLLER_HOTFIX.md`.



## v0.6.48.7.46.21.7.3 per-sequence controller workspace transport

The native `run-fixed-dsec` qualification now accepts `--runtime-state-workspace-dir` and selects the captured runtime workspace for each of the 61 immutable source sequences. The controller dynamically binds line optical depths and the source-faithful Hydrogen/Magnesium Type-50 and Magnesium Type-99/source-order ledgers used by the accepted v21.6 fixed evaluations. Large arrays are loaded one evaluation at a time. Canonical `.10e` comparison and ABI 60487 are unchanged.

## v0.6.48.7.46.21.7.2 controller source-sequence hotfix

The full native `run-fixed-dsec` path now binds the source qualification sequence separately for every fixed-state callback. This is required because the controller executes all 61 source states in one process, while the historical fixed-evaluation qualification executed one process per sequence. The mapping is read from the 61-row trajectory rather than inferred from callback insertion order.
