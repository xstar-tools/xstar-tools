# xstar-atomic


## Full XSTAR Python source port

Starting with v0.4.0, the primary goal is a source-faithful Python
implementation of the complete XSTAR execution path.  The project now includes
a Fortran-compatible runtime layer, typed whole-program state, source inventory
and call-graph tools, a translation ledger, an executable stage driver, and a
unified `ucalc` dispatcher.  Existing atomic audits remain correctness oracles,
but new development proceeds by translating complete source routines and
subsystems.

See [`XSTAR_PYTHON_PORT.md`](XSTAR_PYTHON_PORT.md).


### v0.4.28 abundance-aware thermal parity and XSTAR-vector closure

v0.4.28 reads the selected element abundance from the bounded XSTAR element probe unless the CLI explicitly overrides it, exports both scaled and per-abundance thermal products, and evaluates the translated element matrix on the captured XSTAR population vector. New row, record, family, and thermal-channel products separate population-vector effects from remaining coefficient/source-semantic differences. Active and strict level gates remain independent, and an explicit acceptance gate combines pre-matrix state, active levels, global ions, element thermal parity, and matrix closure.

### v0.4.27 active-level parity and type-77 source closure

v0.4.27 reproduces the two source `bilevg` floors, preserves zero dominant-record IDs on final continuum rows, adds a dedicated element-array XSTAR probe, and splits strict global-level diagnostics from the active-population milestone gate. It also corrects the type-77 temperature floor to use the endpoint-energy wavelength while retaining the record wavelength for detailed balance, with a diagnostic-only fixed-population impact audit.

### v0.4.26 source-global mapping and second-pass rate separation

v0.4.26 maps global levels through the literal `npilev(local ordinal, ion)`
pointer, keeps preliminary `calc_ion_rates` values separate from second-pass
`calc_hmc_ion` `pirt/rrrt`, and resolves element heating/cooling arrays through
the source element ordinal rather than atomic number.  The production
acceptance gate is a new example-105 global-array rerun; continuum leaves remain
next only after that structural parity is confirmed.

### v0.4.25 scope-aware pre-continuum parity

v0.4.25 uses the XSTAR probe's captured `critf` by default, compares `mml/mmu/critf` once per element, and joins Python ion/level products to the real XSTAR global indices. Oxygen-only runs now compare the oxygen `xiin`, `pirt/rrrt`, `stotg/atotg/xtotg`, level-population/LTE/departure/rate arrays, and per-element heating/cooling while correctly marking all-element totals as `not_comparable_subset_scope`.

### v0.4.24 pre-matrix ion balance and bounded local-zone probe

v0.4.24 completes the source first pass used before the multilevel element matrix: `calc_ion_rates -> istruc/ioneqm -> mml/mmu`. The fixed-state `calc_hmc_all` path now distinguishes preliminary `pirt/rrrt` from post-solve `stotg/atotg`, uses `istruc`-derived ion limits by default, and fixes the one-based `rnise` level mapping. A bounded diagnostic XSTAR probe captures the first-pass element arrays and the full state immediately before `comp2`; example 105 can compare those products directly. Continuum leaves and `dsec` remain the next coherent work.

### v0.4.23 type-49 closure and fixed-state local-zone core

v0.4.23 corrects the label-49 packed parent destination from `integers[-3]` to the source-faithful `integers[-4]`, adds exact source-routine execution plans for `xstarcalc` and the zone loop, and begins Milestone 4 with a fixed-temperature/fixed-electron-fraction `calc_hmc_all` core. The new core reuses the validated element solver and accumulates source-shaped ion fractions, ionization/recombination rates, level diagnostics, heating/cooling, and charge residuals. Continuum leaves, full all-element fixed-state parity, `dsec`, emissivity, and transfer remain explicit next work.

### v0.4.22 type-56 closure and frozen oxygen Milestone 3

The v0.4.21 oxygen run preserves 607/607 population parity and isolates the last immediate Milestone-3 family to three O VIII type-56 records. XSTAR `hunt3` extrapolates with the first tabulated interval below the temperature grid and then applies `cijpp=max(0,cijpp)`; Python previously flat-clamped to the first positive upsilon. At solve call 219 the source extrapolation is negative, so records 22861--22863 are exact zero. v0.4.22 ports that edge behavior, refreshes the source translation ledger to mark Milestones 1--3 complete for their validated scope, and bundles an immutable oxygen O III--O VIII Milestone-3 benchmark. The next coherent source-port target is `calc_hmc_all -> dsec -> calc_emis_all -> xstarcalc`.

### v0.4.21 exact type-53 pre-parent threshold gate

The v0.4.20 oxygen run retained complete population parity but left 180 type-53/rate-7 terms outside the strict matrix tolerance. All 45 affected O IV records are exact zero in XSTAR. Label 53 tests `rlev(4,idest1)-rlev(1,idest1) <= 0` before adding an excited-parent energy; Python instead clamped the base threshold to zero and then added the parent correction. v0.4.21 preserves the literal source ordering and returns evaluated zero terms for those records. No fitted scale is used.

### v0.4.20 current-source continuum constants and population-parity milestone

The v0.4.19 exact-state oxygen run is the first native 607-row solve to pass population parity, with final L1 difference `1.9974981259622204e-05` and all rows within the 0.5% gate. The leading remaining matched-topology rate discrepancy is type 99/rate 7. Current XSTAR continuum integrators derive `kT=0.8617333262145178*T4` eV from `constants.f90`, while Python retained the older `0.861707*T4` coefficient. v0.4.20 uses the current source constants in `phintfo/phint53hunt` without changing formulas that literally use the historical coefficient. No fitted scale is used.

### v0.4.19 exact type-53 excited-parent endpoint

The v0.4.18 exact-state run confirmed type 57/rate 5 is ready and ranked type 53/rate 7 next. XSTAR decodes the type-53 parent-level offset from the fourth packed integer from the end; Python used the third-from-last linked parent-ion field, routing 702 of 733 records to incorrect endpoints and supplying incorrect excited-parent thresholds and weights to `phint53`. v0.4.19 uses `integers[-4]`, preserves the bound level at `[-2]`, and adds a realistic packed-tail regression. No fitted scale is used.


### v0.4.18 literal type-57 `e1`/`eth` handoff

The v0.4.17 exact-state run confirmed type 63 is resolved and ranked type 57/rate 5 next. XSTAR calls `calt57` with `e=rlev(1,idest1)` and `ep=eth=rlev(1,nlevp)-rlev(1,idest1)`. The Python source-port branch had supplied the absolute parent continuum energy as `ep`, creating nonzero rates where XSTAR returns zero and changing all active ionization coefficients. v0.4.18 now applies the literal `ep=eth` convention and the source pre-kernel gates. No fitted scale is used.

### v0.4.17 exact record-order quantum handoff for same-`n` type 63

The v0.4.16 rerun remained unchanged because the same-`n` evaluator was still called with energy-ordered lower/upper quantum numbers while receiving packed record-order statistical weights. v0.4.17 passes the packed initial/final `n,l` values into the native `amcrs/velimp` branch and derives the public excitation/de-excitation representation only after native `ans1/ans2` have been formed. No collision kernel or fitted scale is changed.

### v0.4.16 same-n type-63 record-order channels

The v0.4.15 rerun showed that the nine remaining type-63 failures were all same-`n` `amcrs/velimp` records. v0.4.15 corrected only the `nf != ni` Bautista branch, so the same-`n` path still returned energy-ordered rates. v0.4.16 exposes the literal XSTAR `ans1/ans2` channels from the same-`n` branch using the packed initial/final endpoints and their statistical weights. No collision kernel or fitted scale is changed.

### v0.4.15 literal type-63 record-order matrix channels

The v0.4.14 exact-state run moved the first failing family to type 63/rate 3. All 2,120 type-63 terms matched topologically, but 36 terms from nine O VII records had their forward and reverse channels exchanged because those packed records store the higher endpoint first. v0.4.15 preserves XSTAR's literal `idest1 -> idest2` `ans1` channel and `idest2 -> idest1` `ans2` channel instead of converting them to an energy-ordered collision convention. The validated Bautista `anl1`/`erc` kernel is unchanged.

### v0.4.14 exact type-99 `phint53hunt` grid control

After v0.4.13 corrected type-99 endpoints, all 28 matrix terms matched XSTAR topologically and the reverse rates agreed at roughly `1e-6` relative precision, but most forward rates remained 1.5--2.4% high. v0.4.14 ports the literal `huntf`/`nbinc` nearest-log-grid rule and the one-based `phint53hunt` stride loop. Python no longer forces the high-energy `nphint` endpoint into every refinement pass. No fitted scale is used, and the existing solve-call-219 probes can be reused.

### v0.4.13 exact type-99 endpoint and density semantics

The solve-call-219 exact-state run improved the final oxygen population L1 difference to about 0.192 and ranked type 99/rate 7 next. v0.4.13 now decodes the type-99 parent-level offset from packed integer `[-4]`, restoring the source continuum/next-ion-ground aliases, and evaluates `calt99` at `den=xpx` while retaining `xnx=xpx*xee` for `phint53hunt` and the final recombination rate. Existing XSTAR probe products can be reused.

### v0.4.12 exact type-74 and type-95 source corrections

The exact solve-call-219 run exposed 42 strict blockers, all from type-74 delta-resonance records. The source permits a zero DR coefficient while retaining a nonzero live-radiation forward rate; v0.4.12 now evaluates `calt74` directly on the live radiation arrays, preserves zero reverse coefficients, and uses the exact label-74 endpoints and statistical-weight handoff. The same release corrects label 95 to use `eint`'s ordinary `E1(x)` result rather than the scaled `expint` value and reproduces the Fortran spline indexing.

### v0.4.11 exact-state parity preflight

Population and iteration-state parity now run only after a strict native element solve has actually executed. If the selected XSTAR solve-call runtime exposes context-blocked source records, example 102 still writes the complete partial assembly, record-level matrix comparison, and grouped blocker products instead of stopping with an early parity exception. Inspect `xstar_element_assembly_blocker_summary.csv/.json/.md` to select the next source routine to correct.

### v0.4.10 captured-zone runtime context

When `--xstar-population-probe-csv` is supplied, example 102 now uses the selected solve call's exact `T`, `xpx`, `xee`, and `cfrac` before evaluating any native rate. This avoids comparing a Python matrix assembled at nominal CLI values with an XSTAR matrix captured at a different converged zone state. Use `--population-probe-runtime-policy check` to require explicit inputs to match, or `ignore` only for a controlled mismatch experiment.

### v0.4.9 oxygen record-level matrix parity

The Milestone-3 acceptance path now stops at the first true XSTAR/Python divergence. The v0.4.8 state products show exact outer-iteration-1 populations and `rr` fractions; the first mismatch is the raw condensed superlevel matrix. v0.4.9 can join the complete native 607-row matrix manifest directly to the existing XSTAR `ucalc` and `calc_hmc_ion` probe products and rank the responsible data/rate family without replacing any production coefficient.

Add these options to the normal oxygen parity command:

```bash
  --xstar-ucalc-probe-csv     xstar_runs/helike_type69/o7_ne1e8/xstar_ucalc_record_probe.csv   --xstar-matrix-probe-csv     xstar_runs/helike_type69/o7_ne1e8/xstar_calc_hmc_ion_matrix_probe.csv
```

Outputs include `xstar_full_element_matrix_parity_details.csv`, a family summary, and the first failing type/rate pair. The same release also corrects label-76 two-photon decay channel semantics and reports state failures in actual Lucy execution order.

### v0.4.3 complete element statistical-equilibrium subsystem

The next original-source sequence is now available as one direct execution path:

```text
levwkelement
  -> calc_hmc_ion
  -> calc_hmc_element
  -> msolvelucy
```

It builds XSTAR's compact element basis with shared continuum/ground aliases,
traverses all ion records through the v0.4.1 pointers, evaluates them through
the v0.4.2 `ucalc` dispatcher, assembles the full gain/loss and
heating/cooling matrices, applies the normalization equation, and solves the
populations with the translated Lucy superlevel iteration and linear-algebra
helpers.  The default oxygen target O III--O VIII has 607 compact rows.

```bash
PYTHONPATH=src python examples/102_port_xstar_element_equilibrium.py \
  --atdb /path/to/xstar/data/atdb.fits \
  --pointer-cache /path/to/xstar_atomic_derived_pointers.npz \
  --element-z 8 --min-ion-stage 3 --max-ion-stage 8 \
  --temperature-k 1.0e6 \
  --hydrogen-density-cm3 1.0e8 \
  --electron-fraction-xee 1.0 \
  --live-rate-grid-probe-csv /path/to/xstar_live_rate_grid_probe.csv \
  --escape-npz /path/to/xstar_escape_state.npz \
  --out-dir xstar_o_element_equilibrium_v043 \
  --print-summary
```

Strict readiness requires complete source-equivalent radiation and optical-depth
state.  Records missing that context are reported as blockers; the port does not
insert probe-derived matrix coefficients.  Six-row and 119-row products are now
regression subsets only.

### v0.4.2 complete `ucalc` subsystem

The complete packed-record execution boundary of `ucalc.f90` is now available:

```text
packed ATDB record
  -> data/rate type identification
  -> idat/rdat/cdat decoding
  -> source branch and called leaf routines
  -> ans1..ans6, idest1..idest4, opacity, diagnostics, provenance
```

All source labels 1 through 102 are registered.  Physical branches execute
natively when their required plasma, level, pointer, and radiation context is
present; missing context is reported explicitly and is never replaced by a
proxy.  Source-defined metadata and disabled branches return source no-op
results.

Run the subsystem inventory against a production database with:

```bash
PYTHONPATH=src python examples/101_port_xstar_ucalc.py \
  --atdb /path/to/xstar/data/atdb.fits \
  --pointer-cache /path/to/xstar_atomic_derived_pointers.npz \
  --out-dir xstar_ucalc_source_port_v042 \
  --print-summary
```

This does not evaluate all 1.2 million records numerically because a full XSTAR
zone state is not yet available.  It does decode and dispatch one record for
every active ATDB data type and reports native/no-op/untranslated coverage.

### v0.4.1 atomic-database subsystem

The translated Python driver now completes the first three XSTAR stages:

```text
setup -> read_atomic_database -> build_pointers
```

Run the source-faithful `readtbl -> setptrs` port with:

```bash
PYTHONPATH=src python examples/100_port_xstar_atomic_database.py \
  --atdb /path/to/xstar/data/atdb.fits \
  --out-dir xstar_atomic_database_port_v041 \
  --print-summary
```

This creates a reusable fingerprinted pointer cache and summaries of elements,
ions, levels, lines, continua, and rate families.  The packed FITS vectors stay
memory mapped, so the production database is not duplicated in memory.

Generate the source inventory from the supplied XSTAR tarball with:

```bash
PYTHONPATH=src python examples/99_inventory_xstar_source_port.py \
  --source-tar xstar_source.tar.gz \
  --out-dir xstar_python_source_port_inventory_v0400 \
  --print-summary
```

The official `atdb.fits` remains external because it is large; use
`xstar-atomic-download-data` or provide a local file through `XSTAR_ATDB`.



> **v0.3.209:** fixes the real O VII type-53 parity blocker by deriving XSTAR's active continuum index `nlevp` from the direct `ucalc` endpoint and the packed parent offset. v0.3.208 used the maximum extracted level index (`110`) instead of the active XSTAR continuum row (`79`), which introduced a false parent excitation and invalidated all type-53 rates. The exact live-radiation `phint53` kernel is unchanged; rerun examples 97 and 98 to test the corrected decoder.

> **v0.3.208:** adds an exact live-radiation type-53 `phint53`/`ucalc` reference implementation and controlled parity/integration gates. The gate consumes an explicitly selected live `epim`/`bremsam`/`bremsint` capture, validates state provenance, compares `ans1..ans6` and compact matrix insertions, and does not apply the unresolved empirical approximately-44 scale. Real O VII acceptance remains required before the type-53 milestone is considered complete.

Latest local development note: **v0.3.202** adds a native-assembly readiness audit for the validated six-row O VII conditional solve. It ranks internal and external rate-family influence and defines the implementation order: type 51 internal coupling, type 50/type 71 external closure, then exact live-radiation type 53. No solver physics or empirical type-53 scale correction is introduced.

Latest documentation note: **v0.3.200** adds a comprehensive Markdown and LaTeX guide to the packed `atdb.fits` structures, XSTAR Fortran source layout, record-to-rate-to-matrix data flow, physical equations, C V/O VII/Mg XI/Ca XIX benchmark interpretation, findings through v0.3.199, the unresolved type-53 approximately 44 scale, and the staged Python/C++ implementation roadmap. This is a documentation-only release; solver physics is unchanged.

Latest local development note: v0.3.198 fixes whole-run element leakage in `examples/89_audit_xstar_priority_matrix_closure.py`. Before compact endpoint mapping, per-record XSTAR probe selections are now restricted to the reconstructed element `jkk_ion` blocks. In the O VII v0.3.197 latest-per-record audit, all 7,432 apparent unmapped endpoints came from unrelated `jkk_ion=1--3`, while the O-element blocks are `jkk_ion=31--36`. The release adds an element-filter summary CSV and leaves native solver physics unchanged.
Latest package note: **v0.3.198** is an audit correctness fix; rerun example 89 with the same command.


Latest local development note: v0.3.197 fixes full-element priority matrix-manifest selection and endpoint mapping. Matrix endpoints are now translated exactly as XSTAR does in `calc_hmc_element.f90`, `compact_ipmat2 = ion_ipmat2_offset + indbi`, including adjacent-ion/superlevel endpoints with `indbi > nlev`. Non-matrix `ucalc` metadata records are separated from true four-row matrix records, and the full-element audit defaults to latest-per-record selection.
Latest package note: **v0.3.197** updates `examples/89_audit_xstar_priority_matrix_closure.py`; no default solver physics is changed.


Latest local development note: v0.3.196 derives an exact compact-matrix closure manifest for the staged high-population basis rows from the raw XSTAR `ucalc` and `calc_hmc_ion` probes.
Latest package note: **v0.3.196** adds `examples/89_audit_xstar_priority_matrix_closure.py`, preserving shared parent-continuum aliases while mapping every selected Fortran matrix insertion into compact `ipmat2` coordinates.

Latest local development note: v0.3.194 converts the exact XSTAR compact element topology into a full 607-row Python basis scaffold with explicit mapped rows, shared aliases, missing-row priorities, and population-closure tiers.
Latest package note: **v0.3.194** adds `examples/87_build_xstar_full_element_basis_scaffold.py`. It consumes the v0.3.193 remap audit, assigns deterministic placeholder indices for missing XSTAR rows, and prepares staged full-element basis expansion without changing default solver physics.


Latest package note: **v0.3.194** adds `examples/87_build_xstar_full_element_basis_scaffold.py`. It consumes the v0.3.193 remap audit, assigns deterministic placeholder indices for missing XSTAR rows, and prepares staged full-element basis expansion without changing default solver physics.

Latest package note: **v0.3.190** adds a population/source-closure parity audit for the validated `xstar_population_closure_probe.csv`. The new `examples/83_audit_xstar_population_closure_parity.py` selects an XSTAR element solve occurrence, compares the post-`msolvelucy` population vector against preserved Python solver population products, and reports overlap rows plus XSTAR `ipmat2` rows missing from the current Python local basis. No default solver physics changed.

Latest package note: **v0.3.188** adds population/source closure probe preparation for `calc_hmc_element.f90`. It writes a Fortran helper and before/after-`msolvelucy` insertion snippets to generate `xstar_population_closure_probe.csv`, then validates paired population-vector captures. This is the next parity layer after record-level `ucalc`/matrix parity and exact-rate replay showed negligible O VII triplet-population movement. No default solver physics changed.

## v0.3.187

Population/source closure diagnosis update: fixes replay family selector aliases so `type50` matches legacy `data_type_50` family keys, and adds `examples/81_diagnose_xstar_population_closure_from_replay_scan.py`. The current O VII family replay scan shows exact-`ucalc` rate replays move triplet population fractions by only ~8.36e-7, so the next source-code-equivalent target is XSTAR population/source closure rather than another isolated rate-family replay. No default solver physics changed.

## v0.3.185

Record-level replay solve reporting update: adds population-based triplet diagnostics, line-triplet availability status, and writes original plus replay normalized solve products. No default physics changed.

## v0.3.183

- Add branch-aware record-level blocker diagnosis for source-code local matrix parity.
- Include type-99 parent/superlevel closure rows using `type99_records` when generic `record` is absent.
- Add per-record branch-ratio columns and recommended next actions for type-53, type-50, type-77, and type-99 closure blockers.

Latest package note: **v0.3.182** adds occurrence-rank/local-state selection diagnostics to the record-level matrix parity audit. Full XSTAR probes contain many repeated `ucalc` calls over zones and passes, while the preserved Python matrix is one local state. `examples/78_audit_xstar_record_level_matrix_parity.py` now supports `--selection occurrence-rank --occurrence-rank N` and `--scan-occurrence-ranks`, writing an occurrence-scan CSV to identify the Fortran epoch that best matches the Python matrix before interpreting family-level mismatches. This is diagnostic infrastructure only; no solver physics or empirical triplet tuning changed.

Latest package note: **v0.3.177** fixes the full local parity probe helper for HEASoft/XSTAR fixed-form Fortran builds. The generated `xstar_atomic_full_parity_probe_helpers.f90`, after-`ucalc` insertion block, and matrix-insertion notes now use fixed-form continuation in column 6 and avoid free-form trailing `&`, so the helper can compile in XSTAR builds that treat `.f90` sources as fixed form. This is an instrumentation compatibility fix only; no solver physics, rate formulas, or empirical triplet tuning changed.

# xstar-atomic

Latest package note: **v0.3.176** adds full local parity probe preparation/validation for the required XSTAR debug products `xstar_ucalc_record_probe.csv` and `xstar_calc_hmc_ion_matrix_probe.csv`. It writes schemas, an external Fortran helper, a `calc_hmc_ion.f90` after-`ucalc` insertion block, and matrix-insertion probe notes, then validates whether captured probes are ready for record-level `ucalc`/`ajisi` matrix parity. This is instrumentation infrastructure only; no solver physics or empirical triplet tuning changed.

Latest package note: **v0.3.175** adds a source-code-equivalent local closure audit for full XSTAR matrix/population parity. It inventories each preserved matrix family, flags proxy/scaffold and incomplete parent/superlevel closure rows, records the Fortran subroutines that must be matched (`ucalc`, `calc_hmc_ion`, `levwkelement`, `msolvelucy`, type-70/74/99 closure), and writes ucalc/matrix/population probe schemas plus a staged implementation plan. This is an audit/probe-planning release only; no solver physics or empirical triplet tuning changed.

Latest package note: **v0.3.174** adds a controlled type-53 live-bremsam matrix-replacement solve audit. It consumes the example-74 live `phint53` records, replaces only type-53 photoionization gain/loss rows in a preserved full-global matrix with live `epim(:)/bremsam(:)` `phint53` ans1 rates, and re-solves the matrix to show how f/i/r changes. This is diagnostic only; default solver physics is unchanged.

Latest package note: **v0.3.173** adds the first type-53 `phint53` audit against an instrumented XSTAR live rate-grid probe. It reads `xstar_live_rate_grid_probe.csv`, selects a captured `epim(:)/bremsam(:)/bremsint(:)` state, recomputes the photoionization `ans1` side on live `bremsam(:)`, and compares to preserved full-global type-53 matrix rows. The O VII probe confirms the current Python matrix type-53 photoionization rates still exceed live-bremsam `phint53` rates by about 44×, so the remaining gap is now localized to the solver's proxy `xstar-powerlaw` type-53 normalization rather than `xo01_detal4` column choice. No solver physics changed.


- `docs/user_guide.md`
- `docs/user_guide.tex`
- `docs/xstar_atdb_source_physics_implementation_guide.md`
- `docs/xstar_atdb_source_physics_implementation_guide.tex`
- `docs/sphinx/source/user_guide.rst`
- `docs/sphinx/source/api.rst`

The simple workflow API includes:

```python
import xstar_atomic as xa

db = xa.open_database("/path/to/atdb.fits")
levels = xa.get_levels("O VII", db=db)
lines = xa.get_lines("O VII", db=db, wavelength=(21.4, 22.2))
rate = xa.calc_rate("type50", aij_s_inv=..., oscillator_strength=..., wavelength_A=...)
triplet = xa.calc_triplet("O VII", rows=xstar_line_rows)
```

The expert object API exposes namespace-style entry points:

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic("/path/to/atdb.fits")
ctx = db.context.from_xstar_run("xstar_runs/helike_type69/o7_ne1e8", ion="O VII")
rate = db.rates.type50("O VII", aij_s_inv=..., oscillator_strength=..., wavelength_A=...)
comparison = db.validate.compare_xstar_run("xstar_runs/helike_type69/o7_ne1e8", ion="O VII")
```

Benchmark solver products can be preserved and handed to the detail-state rate audit:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --standard-helike-suite \
  --xstar-runs-root xstar_runs \
  --run-solver \
  --solver-preset xstar-local-state \
  --write-solver-products \
  --out-dir helike_local_reproduction_suite_solver

PYTHONPATH=src python examples/61_audit_xstar_detail_type50_rates.py \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --benchmark-dir helike_local_reproduction_suite_solver \
  --out-dir xstar_detail_type50_rate_audit_o7_with_matrix
```


Python XSTAR-output recreation planning is available for future full-emulation work:

```python
import xstar_atomic as xa

params = xa.parse_xstar_command("xstar spectrum='pow' nsteps=10 density=1 rlogxi=1.5 cfrac=1.0")
plan = xa.xstar_recreation_plan(params)
paths = xa.write_xstar_recreation_plan(params, "xstar_python_recreation_plan")
```

CLI wrapper:

```bash
PYTHONPATH=src python examples/58_plan_xstar_output_recreation.py \
  --command-file xstar_runs/helike_type69/o7_ne1e8/run_xstar.sh \
  --out-dir xstar_python_recreation_plan_o7 \
  --print-summary
```

Public namespace modules are available for future API growth: `xstar_atomic.rates`, `xstar_atomic.solve`, `xstar_atomic.matrix`, `xstar_atomic.validate`, and `xstar_atomic.runs`.
The same-run XSTAR reproduction API is now available:

```python
target = xa.build_xstar_local_target(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
)
comparison = xa.reproduce_xstar_run(
    "xstar_runs/helike_type69/o7_ne1e8",
    ion="O VII",
    run_solver=False,
)
```

Single-ion CLI wrapper:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --out-dir xstar_o7_local_reproduction \
  --print-summary
```

Four-ion standard suite:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --standard-helike-suite \
  --xstar-runs-root xstar_runs \
  --out-dir helike_local_reproduction_suite \
  --print-summary
```

Four-ion solver comparison using the local-state validation preset:

```bash
PYTHONPATH=src python examples/56_reproduce_xstar_local_outputs.py \
  --standard-helike-suite \
  --xstar-runs-root xstar_runs \
  --run-solver \
  --solver-preset xstar-local-state \
  --out-dir helike_local_reproduction_suite_solver_v03144 \
  --print-summary
```

The quick workflow solver remains available with `--solver-preset workflow-default`, but it is not the same path used in the earlier source-code-first local-state validations.

v0.3.145 adds the first opt-in matrix injection of XSTAR type-50 photoexcitation / line pumping through `xstar-line-escape-and-pumping`.  The implementation follows the `ucalc.f90` type-50 algebra on the explicit solver `epi`/`bremsa` grid and remains a validation mode until the same-run C/O/Mg/Ca benchmark is inspected.

## Earlier v0.3.128 API infrastructure

New public objects and functions:

```python
from xstar_atomic import (
    LocalPlasmaState,
    RadiationField,
    EscapeContext,
    XSTARContext,
    RateEvaluation,
    evaluate_type50_bound_bound,
    type50_line_pumping,
)
```

## Examples

See `examples/README.md` for grouped runnable examples and recommended learning paths. The most advanced validation examples remain diagnostic/source-code-first workflows and may require same-run XSTAR outputs.


## XSTAR live-state model

v0.3.150 introduces explicit Python containers for the live arrays required to recreate XSTAR outputs from input parameters.  The state model includes `epi(:)`, `bremsa(:)`, `bremsint(:)`, `tau0(1:2,line)`, `tauc/dpthc(1:2,continuum)`, `cfrac`, `vturbi`, zone-local temperature/electron density, ion fractions, and level populations.  These containers are schema/state infrastructure, not a complete XSTAR replacement yet.

```python
import xstar_atomic as xa

params = xa.parse_xstar_command("xstar nsteps=10 density=1 rlogxi=1.5 cfrac=1.0 vturbi=100")
state = xa.create_initial_xstar_run_state_from_input(params)
print(state.zones[0].missing_core_fields())
```

Command-line skeleton writer:

```bash
PYTHONPATH=src python examples/59_create_xstar_live_state_skeleton.py \
  --command-file xstar_runs/helike_type69/o7_ne1e8/run_xstar.sh \
  --out-dir xstar_live_state_skeleton_o7 \
  --print-summary
```


### XSTAR detail live-state population

The package can populate the Python live-state containers from XSTAR detail outputs written with `lwrite=1`/`lprint=1`:

```python
import xstar_atomic as xa
state = xa.read_xstar_detail_run_state("xstar_runs/helike_type69/o7_ne1e8")
paths = xa.write_xstar_detail_state(state, "xstar_detail_live_state_o7")
```

This maps `epi(:)`, reconstructed `bremsa(:)`, `bremsint(:)`, `tau0(1:2,line)`, `tauc/dpthc`, `cfrac`, `vturbi`, local `T/ne`, ion fractions, and level populations into one Python state object.

### XSTAR detail-state type-50 rate audit

For source-code parity work, use example 61 to audit type-50 rates directly from XSTAR detail outputs:

```bash
PYTHONPATH=src python examples/61_audit_xstar_detail_type50_rates.py \
  --run-dir xstar_runs/helike_type69/o7_ne1e8 \
  --ion "O VII" \
  --out-dir xstar_detail_type50_rate_audit_o7 \
  --print-summary
```

This reads `xo01_detal2.fits` and `xo01_detal4.fits`, computes `ptmp1`, `ptmp2`, escaped decay, and photoexcitation using the XSTAR `calc_hmc_ion.f90`/`ucalc.f90` type-50 formula, and writes CSV/JSON/Markdown audit products.




### v0.3.181 record-level local matrix parity audit

v0.3.181 adds `examples/78_audit_xstar_record_level_matrix_parity.py`, which consumes the validated full-parity XSTAR probes (`xstar_ucalc_record_probe.csv` and `xstar_calc_hmc_ion_matrix_probe.csv`) together with a preserved Python full-global matrix.  The audit matches Python matrix records to the latest instrumented XSTAR `ucalc` call for the same ATDB record, joins the four `calc_hmc_ion` `ajisi/indbi` rows, checks that the Fortran matrix rows are self-consistent with `ans1` and `ans2`, and reports Python/Fortran rate agreement by record and rate family.

Example:

```bash
PYTHONPATH=src python examples/78_audit_xstar_record_level_matrix_parity.py \
  --benchmark-dir helike_local_reproduction_suite_solver_v03156 \
  --ion "O VII" \
  --ucalc-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_ucalc_record_probe.csv \
  --matrix-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_calc_hmc_ion_matrix_probe.csv \
  --out-dir xstar_record_level_matrix_parity_audit_o7_v03181 \
  --print-summary
```

This audit is diagnostic only.  It does not change solver defaults; it identifies which local matrix families are already source-code-equivalent and which still use proxy/scaffold or incomplete parent/superlevel closure logic.

### v0.3.180 full-parity probe shared-capture fix

v0.3.180 fixes the full-parity probe CSV association problem found after the first O VII instrumented XSTAR run. Previous helpers wrote an independent matrix-row `capture_index`, so `xstar_calc_hmc_ion_matrix_probe.csv` could not be matched to `xstar_ucalc_record_probe.csv`: every matrix row appeared to be a separate record. The v0.3.180 helper now stores the most recent `ucalc` capture id and writes it as the matrix probe `capture_index`, while the independent matrix-row counter is written as `matrix_capture_index`. The validator detects legacy independent-counter CSVs and reports `matrix_capture_index_status=independent_matrix_capture_index_needs_v03180_rerun`. This is a probe/validation fix only; no solver physics or rate formula changed.

### v0.3.179 full-parity probe linker compatibility fix

v0.3.179 adds backward-compatible Fortran wrappers for the older long probe routine names (`xstar_atomic_probe_ucalc_record`, `xstar_atomic_probe_matrix_row`) while retaining the v0.3.178 short helper routines (`xap_ucalc`, `xap_mrow`). This fixes HEASoft/XSTAR link errors when `calc_hmc_ion.f90` still contains older insertion snippets. It is a probe/linker compatibility fix only; no solver physics or rate formula is changed.

### v0.3.178 full-parity probe helper compiler fix

v0.3.178 regenerates the full local parity probe helper as conservative free-form Fortran (`xap_ucalc`, `xap_mrow`) matching the observed HEASoft/XSTAR `.f90` compile path. It is a probe/instrumentation fix only; no solver physics or rate formula is changed.


### Priority compact-matrix row-balance audit

After example 89 reports a complete source-code-derived matrix manifest, example 90 evaluates the selected compact XSTAR row equations directly against the captured post-`msolvelucy` population vector:

```bash
PYTHONPATH=src python examples/90_audit_xstar_priority_matrix_balance.py \
  --priority-matrix-closure-audit xstar_priority_matrix_closure_o7_v03198_latest \
  --population-closure-parity-audit xstar_population_closure_parity_audit_o7_v03190_rank73 \
  --out-dir xstar_priority_matrix_balance_o7_v03199 \
  --print-summary
```

The audit aggregates the probed Fortran `ajisi(1,:)` coefficients into compact `ipmat2` entries and reports `sum_j A_ij x_j` for every activated priority row. It is a diagnostic gate before native compact-matrix/RHS assembly; no solver defaults are changed.


### Source-faithful escape state (v0.4.4)

Build line and RRC optical-depth arrays from an XSTAR run:

```bash
xstar-atomic-port-escape \
  --atdb /path/to/atdb.fits \
  --pointer-cache /path/to/xstar_atomic_derived_pointers.npz \
  --xstar-run-dir /path/to/xstar_run \
  --zone last \
  --out-npz xstar_escape_state.npz \
  --out-dir xstar_escape_state_v044 \
  --print-summary
```

The builder uses `xo01_detal2.fits` for line depths and `xo01_detal3.fits` for
RRC depths. It does not use the continuum-grid `xo01_detal4.fits` as an RRC
optical-depth substitute.


### Full oxygen runtime-context correction (v0.4.5)

The production element command now decodes type-50 A values, collision metadata, type-53 cross sections, and type-99 thresholds directly from the packed ATDB/runtime level state. When `--xstar-run-dir` is used, sparse `detal2/detal3` rows are reconstructed through zone history by default:

```bash
PYTHONPATH=src python examples/102_port_xstar_element_equilibrium.py \
  --atdb /path/to/atdb.fits \
  --pointer-cache xstar_atomic_database_port_v041/xstar_atomic_derived_pointers.npz \
  --element-z 8 --min-ion-stage 3 --max-ion-stage 8 \
  --temperature-k 1e6 --hydrogen-density-cm3 1e8 --electron-fraction-xee 1 \
  --live-rate-grid-probe-csv /path/to/xstar_live_rate_grid_probe.csv \
  --xstar-run-dir /path/to/xstar_run --escape-zone last \
  --escape-detail-policy source_sparse_reconstruct \
  --out-dir xstar_o_element_equilibrium_v045 --print-summary
```

Use `--escape-detail-policy strict_selected_zone` when only rows explicitly present in the selected radial HDU may be accepted.


### Oxygen population and `msolvelucy` state parity (v0.4.7)

The v0.4.6 O III--O VIII production run assembled all 607 compact rows and converged the translated Lucy solver, but solver convergence alone does not establish XSTAR population parity. v0.4.7 adds the missing acceptance layer.

Supply the paired XSTAR population probe used in the earlier basis work:

```bash
PYTHONPATH=src python examples/102_port_xstar_element_equilibrium.py \
  --atdb /path/to/atdb.fits \
  --pointer-cache xstar_atomic_database_port_v041/xstar_atomic_derived_pointers.npz \
  --element-z 8 --min-ion-stage 3 --max-ion-stage 8 \
  --temperature-k 1.0e6 --hydrogen-density-cm3 1.0e8 \
  --electron-fraction-xee 1.0 \
  --live-rate-grid-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_live_rate_grid_probe.csv \
  --live-rate-grid-state last \
  --escape-npz xstar_o7_escape_state_v045.npz \
  --xstar-population-probe-csv xstar_runs/helike_type69/o7_ne1e8/xstar_population_closure_probe.csv \
  --xstar-population-solve-call-id 219 \
  --write-msolvelucy-trace \
  --out-dir xstar_o_element_equilibrium_v047 \
  --print-summary
```

The command performs two Python solves with the same native matrix:

1. the normal source-faithful LTE-seeded solve;
2. a controlled solve initialized from XSTAR's captured pre-`msolvelucy` vector.

If the second solve matches XSTAR while the first does not, initialization is the blocker. If both fail, the assembled operator or supplied runtime state is the blocker. Products include complete row, ion, superlevel, residual, outer-iteration, condensed-matrix, and fixed-point comparisons.

For iteration-level XSTAR state parity, generate the one-time debug instrumentation:

```bash
PYTHONPATH=src python examples/104_prepare_xstar_msolvelucy_state_probe.py \
  --out-dir xstar_msolvelucy_state_probe_v047 \
  --print-summary
```

After rebuilding and rerunning the same XSTAR case, add:

```text
--xstar-msolvelucy-state-probe-dir <directory-containing-the-five-state-probe-CSVs>
```

No probed coefficient or population is used by the production matrix assembly.

### Final strict-assembly source controls (v0.4.6)

The v0.4.5 production rerun left 531 blockers. These were not missing runtime state: 243 type-63 records are source-defined zero transitions, and 288 O VII type-53/type-74 parent endpoints are clamped by XSTAR's `msolvelucy` rule `min(ipmat, indb)`. v0.4.6 reproduces both behaviors and reports every raw-to-clamped endpoint in the matrix-term products. The next rerun should reach the 607-row solver directly.

### Oxygen condensed-matrix parity correction (v0.4.8)

The first v0.4.7 state comparison showed that all 607 `nsup` assignments and the first-iteration `rr` fractions agree with XSTAR. Two apparent earlier failures were comparison artifacts: compact ion counters were compared with physical ion stages, and the captured pre-solve vector was normalized before the controlled seeded solve. v0.4.8 corrects both.

The first physical mismatch was then traced to type-86 Auger endpoint decoding. XSTAR label 86 reads packed integer fields `[-4]` and `[-5]`; the previous Python translation used `[-3]` and `[-4]`. The correction restores source-faithful compact placement of these large rates. Rerun the same example 102 command with the existing XSTAR state probes; no new XSTAR instrumentation run is required.
