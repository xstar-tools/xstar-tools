## v0.4.98 xout_abund1 element-column header hotfix

v0.4.98 fixes the legacy `pprint(11)` FITS column names for the `HEATING` and `COOLING` extensions of `xout_abund1.fits`. XSTAR uses full element names (`hydrogen`, `helium`, `lithium`, ...), while the Python writer had emitted element symbols (`H`, `He`, `Li`, ...). The fix only changes FITS table headers; abundance values, radial stepping, spectra, DSEC, rates, solvers, and diagnostics are unchanged.


## v0.4.87 diagnostic helper link hotfix

v0.4.87 changes only the original-XSTAR observation helper: `xap_zone1_alias_reset` is emitted as an external subroutine so the existing `calc_hmc_all` call resolves at link time. Production Python physics is identical to v0.4.86.

## v0.4.86 exact source-order carbon state-path probe

v0.4.86 is diagnostic-only. It adds matching Python and original-XSTAR observations from live `calc_hmc_all` entry state through incoming carbon mapping, compact pre-solve state, every source-ordered `msolvelucy` outer/fixed iteration, final `xii`, element/global writeback, and continuum/ground aliases. The analyzer reports the first divergent phase and source locus. No production physics changes. See `V0486_SOURCE_ORDER_STATE_PATH_PROBE.md` and `V0486_EARLY_ISSUES_STATUS.md`.

## v0.4.85 live hydrogen state and strict production Lucy solver

v0.4.85 reconstructs `xh0/xh1` from the incoming dense global H I ground population at every `calc_hmc_all` entry, matching `xpx*xilevg(1)*abel(1)` and its ionized complement. Production `msolvelucy` now has no least-squares fallback or dense rescue and uses literal ordered normalization and convergence arithmetic. Standalone diagnostic contexts retain recovery only when explicitly enabled. See `V0485_LIVE_HYDROGEN_STRICT_MSOLVELUCY.md`.

## v0.4.84 preliminary-rate/grid parity and resilient caches

v0.4.84 addresses the remaining v0.4.83 zone-1 differences without changing the restored 24-evaluation DSEC branch. Preliminary `calc_ion_rates` now passes the literal local `lfpi=1`; type 59 and `phintfo` use the source one-based `huntf/nbinc/enxt` continuum traversal and excited-parent statistical weight; logical carbon cooling is keyed by stable physical identities. Both large NPZ sidecars now recover from CRC/ZIP/NumPy member corruption by rebuilding atomically from `atdb.fits`. See `V0484_PRELIMINARY_LFPI_TYPE59_GRID_CACHE_RECOVERY.md`.

## v0.4.83 type-59 source-guard zero-return hotfix

v0.4.83 fixes the return status of the literal type-59
`idest4 > idest3 + 1` guard. Original `ucalc.f90` branches to label 9000,
returning zero rates normally; Python had marked the selected row as blocked
and strict `calc_ion_rates` aborted on record 5386. The guard is unchanged,
but it now returns a ready zero record in ordinary and index-only execution.
All v0.4.82 record-6077 physics corrections remain unchanged. See
`V0483_TYPE59_SOURCE_ZERO_RETURN.md`.

## v0.4.82 C IV data-type-59 correction

v0.4.82 corrects the actual dominant C IV preliminary-rate divergence proven
by the v0.4.81 record comparison. For compact six-real type-59 records, the
Verner coefficients now start at `reals[1]`; `idest2` uses the fourth packed
integer from the end rather than the independent `idest4` field; and source
inverse-field zeroing is applied before the universal heating/cooling swap.
Record 6077 therefore retains forward photo-heating in `ans4`/`ans6` and zeros
post-swap `ans2`/`ans3`/`ans5`, exactly as `ucalc.f90` does.

No original-XSTAR rebuild is required. Rerun the Python zone-1 diagnostic and
the analyzer using `V0482_TYPE59_CORRECTION.md`. No other production rate,
solver, DSEC, radial, FITS, tolerance, or cache behavior changes.

## v0.4.81 optional data-type-15 probe handling

v0.4.81 corrects the analyzer's interpretation of the original-XSTAR probe
contract. The type-15 shell/effective CSVs are lazily created and are required
only when a selected preliminary C IV record has **data type 15**. A rate-type-15
record of data type 95 does not make those files applicable. The analyzer now
reports the proof as non-applicable, keeps C IV record-level parity as a separate
gate, and continues the topology/population/cooling comparison. No production
physics or Fortran instrumentation changes. See
`V0481_OPTIONAL_TYPE15_PROBE.md`.

## v0.4.80 memory-safe zone-1 analyzer

v0.4.80 is an analysis-only hotfix over v0.4.79. It streams the enormous
original-XSTAR probe CSVs instead of materializing them and adds
`--skip-input-fingerprints` plus `--progress`. Existing v0.4.79 original probe
outputs and Python diagnostics can be reused. No production physics changes.

The uploaded Python record audit shows that the remaining C IV outlier is data
type 59 record 6077; the type-15 record is negligible. Complete the repaired
original-record comparison before changing type 59.

## v0.4.79 C IV type-15 proof and literal threshold correction

v0.4.79 is a bounded physical correction release for the first concrete
zone-1 divergence found by v0.4.78. Original `ucalc.f90` data type 15 reads a
parent threshold, then overwrites `ett` and `ddd` in its shell loop and passes
the **final shell** values to both `bkhsgo` and `phintfo`. The Python port had
retained the parent threshold. v0.4.79 preserves both values in diagnostics but
uses the final shell threshold and `d` in production, with no other rate,
solver, DSEC, radial, writer, tolerance, or cache change.

The original-XSTAR probe now captures every selected preliminary C IV
`calc_ion_rates` record, type-15 shell thresholds and `d` values, cumulative
`pirti`/`rrrti`, the carbon compact initial vector, the first condensed
normalization row, and selected C V populations. The comparator implements the
ten requested gates and compares C V coefficients and carbon cooling under
stable logical keys rather than trajectory-dependent compact indices.

Use `V0479_TYPE15_WORKFLOW.md`. First-zone parity is not claimed until the
instrumented original XSTAR and production-ATDB Python runs produce
`thermal_root_may_continue=true`.

## v0.4.78 bounded zone-1 DSEC diagnostic

v0.4.78 isolates the first `c5_ne1` DSEC call before any further full radial
parity attempt.  It captures every mutable `calc_hmc_all` entry state, performs
exact same-entry replay, compares original/Python C IV-C VI rates at
`73198.4 K`, audits the selected C V matrix rows and all contributing ATDB
records, and can stop before the thermal root finder commits the first
mismatching carbon cooling term.

Use `examples/146_prepare_xstar_zone1_dsec_probe.py` for the original-XSTAR
probe, `examples/145_diagnose_xstar_zone1_dsec.py` for the one-zone Python run,
and `examples/147_analyze_xstar_zone1_dsec_probe.py` for the cross-comparison.
The full command sequence is in `V0478_ZONE1_DSEC_WORKFLOW.md`.  No production
rate or acceptance tolerance changes in this release.

## v0.4.72 public physical Python runner API and c5_ne1 acceptance gate

v0.4.72 adds the first public end-to-end execution API for the translated
Python XSTAR call graph:

- `run_xstar_python(**parameters)` accepts ordinary XSTAR keyword arguments;
- `run_xstar_python_command(command)` parses a literal `xstar key=value ...`
  command and runs Python only;
- `run_xstar_python_script(run_xstar.sh)` reads the script as data without
  sourcing or executing it;
- `run_xstar_from_parameters(parameters)` is the common typed execution path.

The runner resolves `atdb.fits` through the package data-path policy, applies
the source `rread1` pressure/density/radius setup, builds the literal `ener`
grid and built-in power-law spectrum, initializes caller-owned local/radial
state, executes the translated radial/pass calculation, and writes the strict
ten-product set. Original XSTAR products are never calculation inputs.

The direct Python convenience API supports sparse abundance shorthand. A call
that supplies only `habund`, `heabund`, and `cabund` sets all unspecified
elements to zero. Literal command and script APIs retain XSTAR parameter-file
defaults unless every abundance is supplied explicitly.

The FITS `PARAMETERS` extension now uses the literal 56-row
`xstar.f90 -> pprint(3) -> fparmlist` name/type/comment order, including string
values in the source comment column and REAL(4) persistence. The input
`lprint=1` value is retained in that table. The untranslated verbose terminal
`pprint` reports are not emitted; all structured FITS products and the
comparator-visible zone/final rows of `xout_step.log` remain enabled.

`run_c5_ne1_acceptance()` provides the strict gate requested for
`helike_type69/c5_ne1`: it first generates all ten Python products independently,
then compares them directly against the original-XSTAR directory using the
existing schema/value comparator. The gate cannot pass when an original product
is missing, and never uses original outputs to seed Python state.

The uploaded `original_xstar.tar.gz` intentionally omits the generated products,
and the release environment does not contain the production `atdb.fits` or an
installed XSTAR executable. Consequently, package-level API/gate tests pass, but
physical all-ATDB c5_ne1 output parity is not claimed in this release. The next
acceptance action is to run the new API on the user's production ATDB after
regenerating the ten original products.

Run the Python case and strict comparison with:

```bash
PYTHONPATH=src python examples/142_run_xstar_python.py \
  --run-script original_xstar/helike_type69/c5_ne1/run_xstar.sh \
  --atdb /home/adanehka/mhd/xstar/xstar/data/atdb.fits \
  --output-dir python_xstar/helike_type69/c5_ne1 \
  --original-run-dir original_xstar/helike_type69/c5_ne1 \
  --summary-json c5_ne1_physical_parity_v0472.json \
  --print-summary
```

## v0.4.71 original-XSTAR physical benchmark

Inventory the supplied 62-case run-script tree and prepare the canonical
four-case C V / O VII / Mg XI / Ca XIX benchmark:

```bash
PYTHONPATH=src python examples/141_benchmark_original_xstar_outputs.py \
  --suite-archive original_xstar.tar.gz \
  --out-dir xstar_physical_benchmark_v0471 \
  --selection canonical-four \
  --print-summary
```

To regenerate the omitted original XSTAR products, add `--run-original` and,
when needed, `--xstar-executable /path/to/xstar`. To compare independent Python
outputs, mirror the case directory structure below a Python root and add
`--python-run-root /path/to/python_results`. The benchmark requires all ten
detail/final products per case and exits with status 2 for any missing file or
mismatch. XSTAR outputs are comparison oracles only; they never initialize the
Python calculation.

The current release does not yet contain the general physical Python
input-to-state runner, so inventory/regeneration is ready but physical all-ATDB
parity is not claimed.

## v0.4.70 legacy `pprint` products and physical output-parity harness

v0.4.70 replaces the final non-writing `pprint` handler for the source-default
`lpri=0` path. The bounded radial caller now preserves the default legacy
sequence:

```text
pprint(3) -> pprint(2)
per pass: pprint(17)
per shell: pprint(9) -> [final pass: pprint(12)]
terminal shell state: pprint(9) -> [final pass: pprint(12)]
final local recompute: pprint(22) -> pprint(11)
```

The translated path writes `xout_step.log` and `xout_abund1.fits` with the
source `ABUNDANCES`, `COLUMNS`, `HEATING`, and `COOLING` extensions. It
preserves final-pass-only accumulation, the terminal `numrec` row, source
REAL(4) persistence through `E13.5` ASCII columns, the ion-column trapezoid,
and the option-11 `n_p` unit-field typo. Verbose `lpri>0` diagnostic report
branches fail explicitly rather than being approximated.

A new independent output comparator checks HDU names, table schemas, row
counts, strings, every numeric column, pass-specific detail files, and the
structured zone/final rows of `xout_step.log`. XSTAR products remain diagnostic
oracles only and never become production inputs. The comparator self-test
passes on the bounded product set.

Physical all-ATDB standard-benchmark parity is **not claimed in this release**:
the release environment did not contain a paired original-XSTAR and Python
physical benchmark run. Supply both directories to execute the open gate:

```bash
PYTHONPATH=src python examples/140_validate_xstar_pprint_physical_output.py \
  --out-dir xstar_output_writer_source_validation_v0470 \
  --xstar-run-dir /path/to/original_xstar_run \
  --python-run-dir /path/to/python_run \
  --print-summary
```

Without the two physical directories, the command validates the bounded source
translation and records that physical parity was not run.

## v0.4.69 detail and final FITS output writers

v0.4.69 translates the bounded output sequence after the accepted radial
control path. Per-shell saving now composes
`savd -> fstepr -> fstepr2 -> fstepr3 -> fstepr4` into caller-owned per-pass
detail stores and writes the source pass-specific FITS names. The final caller
executes `xstarcalc(nlimd=0) -> heatt -> stpcut`, records the literal `pprint`
boundary, and then runs `writespectra -> writespectra2 -> writespectra3 ->
writespectra4` under the source `lwri` gates.

The port preserves REAL(4) persistence, one-based HDU insertion and shifting,
level/line/RRC activity gates, the 600-line limit, transmitted continuum, the
five-field `writespectra` scattered-column omission, caller-owned state
identity, and FITS checksums. Direct references cover original `voigte`, the
strong-line `binemis` chain, and detail/final row construction.

Legacy `pprint` ASCII reports remain an explicit source-state handler and are
not fabricated. Physical all-ATDB standard-benchmark output parity remains the
next acceptance stage.

Run:

```bash
PYTHONPATH=src python examples/139_validate_xstar_output_writers.py \
  --out-dir xstar_output_writer_source_validation_v0469 \
  --print-summary
```

## v0.4.68 tabulated radial density and fixed pass-control contract

v0.4.68 closes the remaining bounded radial-control path before output writers.
It translates the inline `radexp < -99` branch in `xstar.f90` and makes the
source pass-convergence contract explicit.

The caller-owned `TabulatedRadialDensityState` reproduces the sequential
`density.dat` unit. The first radius/density pair is consumed before the pass
loop. One further pair is read after every shell, after the saved-state boundary
and before `stpcut`. The source assignment order is preserved:

```text
read rnew, dennew
-> delr = rnew - r
-> reject delr < 0 as "radius error"
-> r = rnew
-> xpx = dennew
-> rdel = rdel + delr
-> xcol = xcol + xpx*delr
```

At end of file, the sequential read returns nonzero `iostat` while retaining the
previous `rnew` and `dennew`. This gives a final zero-width update and terminates
the next literal shell-loop test. The Python path does not rewind the density
stream or invent additional rows.

The pass contract now records that XSTAR uses a fixed requested number of
passes, directions `ldir=(-1)**kk`, and no adaptive comparison between
successive passes. `numrec <= 0` forces `npass=1`. The exact first-pass and
repeated-pass predicates are exposed in provenance. Output writers remain
excluded.

Run:

```bash
PYTHONPATH=src python examples/138_validate_xstar_radial_density_pass_control.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0468 \
  --print-summary
```

## v0.4.67 translated `unsavd` and bounded repeated radial passes

v0.4.67 translates `unsavd.f90`, validates its caller-visible restoration
against the unmodified original Fortran, and adds the caller-owned saved
shell/pass state required by the radial driver. The bounded model now executes
three alternating passes without entering any output writer:

```text
pass 1, ldir=-1: initialize -> shells -> saved REAL(4) records
pass 2, ldir=+1: unsavd -> shell calculation, with nlimdt=0
pass 3, ldir=-1: unsavd -> shell calculation, with nlimdt=nlimd
```

The in-memory persistence contract reproduces the source `savd`/`unsavd`
interface rather than the FITS output mechanism: values are rounded through
REAL(4), HDUs 1--2 are reserved, each record is inserted after the requested
one-based HDU, and later records shift exactly as CFITSIO `ftcrhd` would shift
them. For the two-shell fixture, pass 1 stores shell 1 at HDU 3, inserts the
terminal record at HDU 4, and shifts shell 2 to HDU 5. Passes 2 and 3 therefore
restore HDUs `5, 4, 3` in source order.

`unsavd` restores the saved scalars, populations, line/RRC/continuum arrays,
and only the optical-depth row owned by the current direction. The saved
`zrems` table is read into a local temporary and intentionally does not replace
the caller array, matching the original source. Tabulated radial density,
explicit pass-convergence control, and output writers remain unported.

Run:

```bash
PYTHONPATH=src python examples/137_validate_xstar_unsavd_multipass.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0467 \
  --print-summary
```

## v0.4.66 translated `gsmooth` and nonzero-turbulence radial branch

v0.4.66 translates `gsmooth.f90` and `gsmooth2.f90`, validates the combined
thermal/turbulent velocity and all four smoothed arrays against the unmodified
original Fortran, and closes the optional source branch before `heatt`:

```text
[first-pass zones > 1: step]
-> trnfrc
-> xstarcalc
-> [gsmooth when vturbi > 1.e-34]
-> heatt
-> inline radius/density/radial-depth/column update
-> stpcut
-> trnfrn
```

The translation preserves the wrapper order
`brcems -> rccemis(1) -> rccemis(2) -> opakc`, bins 1--2, the 20-keV
pass-through, plus/minus trapezoid walks, literal stopping tests, binary32
source constants, and caller-owned tails. The same caller arrays are smoothed
before translated `heatt` consumes them.

Reverse passes still fail at missing `unsavd`; multipass restoration, tabulated
radial density, and output writers remain explicitly unported.

Run:

```bash
PYTHONPATH=src python examples/136_validate_xstar_gsmooth_radial_shell.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0466 \
  --print-summary
```

## v0.4.65 translated `heatt` and bounded radial composition

v0.4.65 translates `heatt.f90`, validates its caller-visible continuum, line,
RRC, and mutable-level-workspace outputs against the unmodified original
Fortran, and replaces the v0.4.64 handler at the same radial source slot:

```text
[first-pass zones > 1: step]
-> trnfrc
-> xstarcalc
-> [gsmooth when vturbi > 1.e-34]
-> heatt
-> inline radius/density/column update
-> stpcut
-> trnfrn
```

The translation preserves active-range mutation and caller-owned tails, old
versus current luminosity-array ownership, the source's retained final
continuum-only `optp2` value in the first inward line term, packed
source-order RRC traversal, and partial `leveltemp` overwrite. The original
routine's local `cmp1` and `cmp2` are uninitialized and affect only local
Compton diagnostic totals; the Python result marks that diagnostic as
source-uninitialized instead of inventing values.

`gsmooth`, `unsavd`, reverse/multipass restoration, and output writers remain
explicitly unported. Nonzero turbulent velocity and reverse passes continue to
fail at their exact source boundaries.

Run:

```bash
PYTHONPATH=src python examples/135_validate_xstar_heatt_radial_shell.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0465 \
  --print-summary
```

## v0.4.64 bounded radial-shell caller and transfer kernels

v0.4.64 begins Milestone 5 without opening output writers. It translates the
four radial kernels with no unresolved atomic-data dependency:

```text
step
trnfrc
stpcut
trnfrn
```

and composes them around the accepted local caller in the exact first-pass
sequence:

```text
[step for zones > 1] -> trnfrc -> xstarcalc -> [gsmooth if vturbi > 0]
-> heatt -> inline radius/column update -> stpcut -> trnfrn
```

`heatt` remains an explicit source-state handler. Reverse/multipass shells fail
at missing `unsavd`, and nonzero turbulent velocity fails at missing `gsmooth`;
neither path is approximated. The direct kernel fixture uses outputs generated
by compiling the unmodified XSTAR routines with only dimension/module stubs.
The expanded caller fixture confirms zone-1 `step` skipping, later-zone `step`,
shared caller-owned arrays, the exact failure boundaries, and exclusion of all
output writers.

Run:

```bash
PYTHONPATH=src python examples/134_validate_xstar_bounded_radial_shell.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0464 \
  --print-summary
```

## v0.4.63 complete local `xstarcalc` assembly

The user-side v0.4.62 validation confirms the complete `calc_emis_all` source
chain. v0.4.63 assembles the accepted local-zone routines in literal
`xstarcalc.f90` order:

```text
bremsmap -> [dsec] -> calc_hmc_all -> calc_emisab_all -> calc_emis_all
```

The brackets denote the source `nlimdt == 0` skip branch. The driver now also
preserves `lpri` save/zero/restore and the final
`nry = nbinc(13.6, epi, ncn2) + 2` assignment.

Composition exposed one real ownership correction: `calc_emisab_all` consumes
the reduced `epim(1:ncn2m)` grid while continuum arrays remain dimensioned on
the full caller grid. The port now requires capacity for the active reduced
range and preserves all higher caller-owned rows. The bounded complete-local
fixture passes call-order, skip, shared-workspace, reduced/full-grid, ranking,
array-continuity, and final-state gates. Radial transfer and output are next.

Run:

```bash
PYTHONPATH=src python examples/133_validate_xstar_complete_local_xstarcalc.py \
  --out-dir xstar_complete_local_xstarcalc_source_validation_v0463 \
  --print-summary
```

## v0.4.62 source-faithful `calc_emis_all`

The user-side v0.4.61 validation closes the complete
`calc_emisab_all -> calc_emisab_element -> calc_emisab_ion` gate. v0.4.62
advances one source-order step and translates:

```text
xstarcalc.f90
  -> calc_emis_all.f90
  -> rlbin.f90
  -> calc_emis_element.f90
  -> calc_emis_ion.f90
  -> freef.f90
  -> bremem.f90
```

The translation ranks the precomputed `calc_emisab_all` line/RRC arrays before
resetting the continuum workspace, preserves the source `rlbin` insertion
order and its effective `nrank-1` retention limit, retains caller-owned
`fline` and `flinel`, rebuilds only the source-owned continuum state, and
replays the complete all-ion compact alias map including inactive-ion offsets.
It also preserves the rate-type-9 double `ucalc` call and rate-type-42 reuse of
the most recently retained continuum pointer.

The bounded validation fixture exercises strong RRC and line output, continuum
side effects, Thomson reset, `freef`, and `bremem`. A passing run reports
`calc_emis_all_source_acceptance_ready=True`; the next source-order target is
the complete local `xstarcalc` sequence.

Run:

```bash
PYTHONPATH=src python examples/132_validate_xstar_calc_emis_all.py \
  --out-dir xstar_calc_emis_all_source_validation_v0462 \
  --print-summary
```

## v0.4.61 source-faithful `calc_emisab_all`

The user-side v0.4.60 validation confirms the complete `bremsmap -> nbinc ->
huntf` gate. v0.4.61 translates `calc_emisab_all.f90 ->
calc_emisab_element.f90 -> calc_emisab_ion.f90` while preserving source-owned
output resets, caller-owned continuum workspaces, all-ion compact aliases,
inactive-ion offsets, mutable `leveltemp`, one-based line/RRC pointers, and the
rate-type 4/7/9/14 branches. Type-53 `ucalc` diagnostics expose the continuum
opacity and RRC-emissivity increments needed to reproduce its array side
effects. The bounded example 131 validation passes and advances to
`calc_emis_all`.

## v0.4.60 source-faithful `bremsmap`

The v0.4.59 offline acceptance run confirms `ready_to_advance_to_bremsmap=True`.
v0.4.60 translates the exact `xstarcalc.f90 -> bremsmap.f90 -> nbinc.f90 ->
huntf.f90` path.  The implementation preserves the reduced `nbinc` search
extent, binary32-rounded default-real constants, caller-owned `bremsam` tail,
the literal descending `1:ncn2m` `bremsint` update, and the incoming
`bremsint(ncn2m+1)` tail boundary inherited from `trnfrc`.

Two frozen cases were generated by compiling the unmodified XSTAR routines
with only minimal `globaldata/constants` stubs.  Python reproduces every mapped
`bremsam` value and every mutated `bremsint` value within `2e-15` relative
tolerance.  The source routine can now mutate `XSTARPythonState.radiation` and
register as the `BREMSMAP` driver routine.  `calc_emisab_all` is the next
source-order target.

Run:

```bash
PYTHONPATH=src python examples/130_validate_xstar_bremsmap.py \
  --out-dir xstar_bremsmap_source_validation_v0460 \
  --print-summary
```

## v0.4.59 final normalized-residual source semantics

The user-side v0.4.58 exact post-`dsec` replay reproduces the complete captured
call-entry runtime and continuum state.  Every underlying fixed-state quantity
passes: runtime, continuum components, primary and secondary heating/cooling
totals, electron contribution, charge residual, and charge identity.  The only
strict failure is `hmctot`, whose relative difference is amplified by cancellation
near thermal equilibrium.

Python and XSTAR independently reproduce the literal `heatf.f90` expression

```text
hmctot = 2 * (httot - cltot) / (1e-37 + httot + cltot)
```

with values `6.007235133655397e-5` and `8.259870956279396e-5`.  Both satisfy
XSTAR's actual `dsec.f90` convergence condition `abs(hmctot) <= 1.e-4`.
Therefore the strict residual mismatch does not change the source convergence
decision and is retained as a diagnostic rather than a physics blocker.

v0.4.59 adds:

- source-expression and source-convergence classification for the exact final
  replay;
- `examples/129_validate_xstar_dsec_final_residual_semantics.py`;
- `xstar-atomic-validate-dsec-final-residual-semantics`;
- an offline reanalysis path that consumes a completed v0.4.58 result tree and
  requires no ATDB read, XSTAR rebuild, or 33-evaluation rerun; and
- separate strict and source-semantic final-state fields.

The O VII local-zone Milestone-4 `dsec` gate is source-semantically accepted.
Strict floating-point trajectory, transition-array, natural-root, and normalized
residual differences remain visible.  `bremsmap` is now the next source-order
translation target.  Production defaults remain `dense-source`,
`reset-per-call`, and `source-zero`.

## v0.4.58 exact post-`dsec` final-call replay

The user-side v0.4.57 unrestricted run converged naturally in the same 33
`calc_hmc_all` evaluations as XSTAR and preserved the complete event sequence,
integer controls, and thermal/charge residual signs.  The only thermal trajectory
row outside the 0.5% relative gate was evaluation 24 `hmctot`, where both codes
remain negative and differ by `2.180338e-5` in a normalized residual close to
zero.  Every underlying heating/cooling component passes; the largest component
differences are only a few `1e-12`.

The naturally converged Python root is `T4=7.664826496730516`, versus the XSTAR
post-`dsec` input `T4=7.665518557731817` (about `9.03e-5` relative).  This small
root displacement explains the strict runtime and continuum-workspace failures
in the natural post-`dsec` fixed-state comparison, while all primary/secondary
thermal totals, charge quantities, and `hmctot` pass their physical tolerances.

v0.4.58 adds:

- `--post-dsec-input-mode natural|compare-both` to the physical runner;
- exact replay of the correlated XSTAR post-`dsec` call-entry runtime, radiation,
  escape arrays, continuum workspaces, dense global populations, and `leveltemp`;
- `examples/128_validate_xstar_dsec_post_final_replay.py`;
- `xstar-atomic-validate-dsec-post-final-replay`;
- source-semantic trajectory classification that treats event/integer/residual-
  sign parity separately from normalized near-zero residual magnitude; and
- a final gate that requires the exact post-`dsec` replay to reproduce the fixed
  state before `bremsmap` is unlocked.

Production defaults remain `dense-source`, `reset-per-call`, and `source-zero`.
No XSTAR rebuild or new capture is required.

## v0.4.57 unrestricted source-zero `dsec` acceptance

The v0.4.56 user run passes the bounded four-evaluation source-semantic gate.
All four thermal decompositions and source branch/residual decisions pass, and
the natural evaluation-2 initial/final Lucy populations, source-order `xtot`,
thermal families, and element arrays agree with XSTAR.  Strict runtime parity
remains false only because approximately `2e-11` charge-workspace roundoff is
carried into later secant variables; it does not change a branch or residual
sign/value decision.

v0.4.57 adds the unrestricted convergence and final-state wrapper:

```text
examples/127_validate_xstar_dsec_source_zero_unrestricted.py
xstar-atomic-validate-dsec-source-zero-unrestricted
```

It forces the accepted production state semantics:

```text
--global-writeback-mode dense-source
--leveltemp-lifecycle reset-per-call
--terminal-continuum-seed-mode source-zero
```

The wrapper removes the four-evaluation limit, compares all captured XSTAR
`dsec` evaluations, executes the correlated post-`dsec` `calc_hmc_all` call,
and reports both strict and source-semantic acceptance.  `bremsmap` remains
blocked until this unrestricted user-side run converges and its final fixed
state passes.

## v0.4.56 natural source-zero `dsec` prefix

The user-side v0.4.55 causality run confirms that XSTAR's literal terminal
compact-row initialization

```fortran
x(ipmat2+1)=0.
```

was the primary evaluation-2 discrepancy.  With the production `source-zero`
seed, the exact-replay evaluation-2 cooling and residual now agree with XSTAR at
roughly the `10^-6` relative level, and all active Lucy-population and thermal
family gates pass.

v0.4.56 adds a natural four-evaluation prefix check:

```text
examples/126_validate_xstar_dsec_source_zero_prefix.py
xstar-atomic-validate-dsec-source-zero-prefix
```

It runs without exact transition-state substitution and keeps the production
state semantics:

```text
--global-writeback-mode dense-source
--leveltemp-lifecycle reset-per-call
--terminal-continuum-seed-mode source-zero
```

The report distinguishes strict floating-point workspace equality from
source-control equivalence (event sequence, integer branch state, residual
sign/value, and final prefix state).  Full unrestricted `dsec`, emissivity, and
transfer acceptance remain later gates.

## v0.4.55 terminal compact-continuum solver seed

The v0.4.54 exact evaluation-2 internal audit isolated the first failure to the
pre-`msolvelucy` population vector.  For H, He, and O, every compact row passed
except the final continuum/normalization row.  XSTAR explicitly writes that
row to zero after all selected-ion population mappings:

```fortran
x(ipmat2+1)=0.
ipmat2=ipmat2+1
call msolvelucy(...)
```

v0.4.55 mirrors this source order by default:

```text
--global-writeback-mode dense-source
--leveltemp-lifecycle reset-per-call
--terminal-continuum-seed-mode source-zero
```

Use `examples/125_validate_xstar_dsec_terminal_continuum_seed.py` or
`xstar-atomic-validate-dsec-terminal-seed` to compare the corrected seed with
the historical `legacy-global` behavior under exact evaluation-2 replay and
full internal parity.  No XSTAR rebuild or new probe capture is required.
Physical `dsec` parity remains open until that user-side scan is evaluated.

## v0.4.54 exact evaluation-2 internal parity

The user-side v0.4.53 exact replay passed every captured evaluation-2 call-entry
state gate, but changed the pre-continuum cooling deficit by only about
`2.2e-6` of its XSTAR discrepancy.  The remaining error is therefore inside
the translated evaluation-2 calculation rather than in evaluation-1 state
writeback.

v0.4.54 reuses the existing detailed same-call XSTAR probe and applies the
complete pre-continuum parity audit directly to the exact-replayed Python
evaluation 2.  It compares pre-matrix ion rates and selection, matrix topology
and coefficients, Lucy entry and final populations, source-order `xtot`, thermal
data/rate families, and element heating/cooling arrays.  Run
`examples/124_validate_xstar_dsec_evaluation2_internals.py` or
`xstar-atomic-validate-dsec-eval2-internals`.  No XSTAR rebuild or new XSTAR run
is required when the v0.4.51 evaluation-2 directory contains the detailed
probe products.  Production defaults remain unchanged.

## v0.4.53 exact evaluation-transition replay

The v0.4.52 four-mode physical run proved that dense native global alias
writeback and per-call `leveltemp` reset are source-correct but do not cause the
remaining evaluation-2 primary cooling discrepancy.  v0.4.53 adds a decisive
diagnostic-only replay:

```text
P: Python evaluation-1 output -> Python evaluation 2
X: exact captured XSTAR evaluation-2 entry state -> Python evaluation 2
```

Python still computes all rates, matrices, populations, and thermal totals.
Run `examples/123_validate_xstar_dsec_exact_transition_replay.py` or the
`xstar-atomic-validate-dsec-exact-replay` entry point.  The physical runner
also writes `xstar_dsec_element_thermal_decomposition.csv` for every evaluation.
No XSTAR rebuild is required.

# xstar-atomic
> **Current development baseline: v0.4.76.** The first real all-ATDB Python run now completes. v0.4.76 restores literal first-pass control, fixes temperature/detail/local-level/RRC output semantics, upgrades the metadata cache to v3, and adds per-DSEC thermal and carbon-rate diagnostics. C V thermal/population parity remains open; no empirical correction is used.



## Full XSTAR Python source port

Starting with v0.4.0, the primary goal is a source-faithful Python
implementation of the complete XSTAR execution path.  The project now includes
a Fortran-compatible runtime layer, typed whole-program state, source inventory
and call-graph tools, a translation ledger, an executable stage driver, and a
unified `ucalc` dispatcher.  Existing atomic audits remain correctness oracles,
but new development proceeds by translating complete source routines and
subsystems.

See [`XSTAR_PYTHON_PORT.md`](XSTAR_PYTHON_PORT.md).

### v0.4.52 corrects repeated-`dsec` mutable-state ownership

The v0.4.51 evaluation-2 transition diagnostic proved that runtime, radiation,
escape arrays, continuum workspaces, and global mapping already matched XSTAR.
The remaining structural differences were the native global population arrays
and the lifecycle of `leveltemp` between consecutive `calc_hmc_all` calls.

v0.4.52 makes dense native-index `xilevg`, `bilevg`, and `rnisg` arrays the
authoritative repeated-call state.  It replays the full Fortran ion-order
writeback, including inactive boundary ions and the shared lower-continuum /
next-ion-ground workspace position, while preserving the distinct `1d-48` and
`1e-37` `bilevg` floors.  It also restores `leveltemp` to the captured call-entry
state before each physical evaluation; source-ordered sharing and partial
writes remain unchanged within each call.

`examples/122_validate_xstar_dsec_transition_causality.py` runs four controlled
two-evaluation modes to measure the independent and combined effects of these
corrections.  The production runner defaults to both corrections.  No new
Fortran probe is required; use the v0.4.48 instrumented XSTAR executable and
v0.4.51 evaluation-2 capture.

### v0.4.51 captures the evaluation-2 `dsec` transition state

The first call-correlated physical evaluation now matches XSTAR, but the
v0.4.50 four-evaluation prefix first diverges in the pre-continuum cooling
state entering evaluation 2. v0.4.51 adds a diagnostic-only transition-state
comparison between the Python state immediately after evaluation 1/control
update and the exact XSTAR state immediately before evaluation 2.

The comparison covers runtime scalars, incident/attenuated continuum arrays,
line and continuum optical-depth arrays, carried `opakc`/`brcems` workspaces,
complete global `xilevg`, `bilevg`, and `rnisg`, and the `leveltemp` slots read by `ucalc.f90`. Raw all-slot
`leveltemp` values plus `nlpt`/`iltp` are also written for diagnosis. Python
snapshots are captured only for requested evaluation indices, so normal full
`dsec` runs do not deep-copy these large states at every call.

Use `examples/121_validate_xstar_dsec_transition_state.py` or the
`xstar-atomic-validate-dsec-transition` entry point. The existing v0.4.48
instrumented XSTAR executable already supports selecting evaluation 2; no
Fortran rebuild is required.

### v0.4.50 fixes optional physical-`dsec` progress reporting

The call-correlated example-119 runner now reports compact-basis sizes from
`ElementEquilibriumResult.assembly.basis`.  In v0.4.49, `--progress` referenced
a nonexistent direct `basis` attribute and aborted after the expensive first
physical evaluation.  The correction is Python-only; reuse the v0.4.48 XSTAR
probe build and products.

### v0.4.49 accepts the exact source-zero first `dsec` population probe

v0.4.49 fixes the call-correlated example-119 startup path.  The first
internal `dsec` call legitimately enters with an all-zero global `xilevg`; the
matching compact population probes are now accepted only in that explicitly
verified context.  Ordinary fixed-state references still require a positive
population sum.

### v0.4.48 correlates `dsec` with its exact `calc_hmc_all` states

The first v0.4.47 physical run showed correct branch order through XSTAR event
88 but used the historical call-73 continuum/escape context for `dsec` call 1.
v0.4.48 adds a shared Fortran call-correlation module, captures the exact first
internal input state and the distinct post-`dsec` reference, and records a full
thermal decomposition for every evaluation. Example 119 now accepts separate
input/final references or resolves them automatically from the correlation CSV.

For faster diagnosis, `--maximum-evaluations 1` runs and compares only the first
physical evaluation; `--progress` prints T4, xee, residuals, and compact-basis
sizes as the full run proceeds. Generate the required combined probe with:

```text
examples/120_prepare_xstar_dsec_matching_probe.py
xstar-atomic-prepare-dsec-matching-probe
```

A new XSTAR rebuild is required because both `dsec.f90` and `calc_hmc_all.f90`
receive additional diagnostic hooks. No scientific XSTAR state is modified.

### v0.4.47 fixes dynamic `dsec` population remapping

The first production execution of example 119 exposed a source-state bug in
v0.4.46: the runner replayed the converged 607-row oxygen compact vector at the
initial `T4=100` trial, where `istruc` selected a 367-row basis. XSTAR instead
carries one global `xilevg` workspace and remaps it after every active-ion
selection. v0.4.47 now preserves that global state, starts call 1 from the exact
`init.f90` all-zero population workspace, remaps in literal source order with
shared-alias overwrite semantics, and preserves stale inactive rows if a later
trial expands the ion range. Compact vectors remain diagnostics only.

No XSTAR rebuild is required; reuse the v0.4.45 twelve-hook trajectory build
and rerun `examples/119_validate_xstar_dsec_complete.py`.

### v0.4.46 adds the physical `dsec` acceptance runner

`examples/119_validate_xstar_dsec_complete.py` now connects the mutable
`DsecMutableRuntimeState` to the real translated `calc_hmc_all` evaluator. It
uses the selected XSTAR `dsec` begin row for the initial/control state,
recomputes `comp2 -> freef -> bremem -> heatf` at every trial. In
v0.4.47 the runner preserves global `xilevg` and shared `leveltemp` state across
trials, remapping the global populations onto each current compact basis before
it compares the complete
trajectory with the instrumented XSTAR reference, and writes the final bounded
acceptance products in the same process. The release does not add emissivity or
transfer physics and does not claim acceptance until the production run passes.

### v0.4.45 translates the stateful `dsec` control algorithm

The accepted fixed-state `calc_hmc_all` result is now wrapped by a literal
translation of XSTAR's nested electron-fraction and temperature iteration:

```text
mutable local-zone state
-> repeated calc_hmc_all trials
-> charge bracket/secant
-> thermal bracket/secant
-> trajectory-level parity
```

`DsecMutableRuntimeState` carries the final compact populations for every active
element and the complete shared `leveltemp` workspace from one trial into the
next. This is essential: XSTAR does not restart each `dsec` evaluation from the
original fixed-state seed.

The exact `dsec.f90` branch order is preserved, including positive and negative
`nlim`, the `tinf` proximity gate, source default-real constants, multiplicative
bracketing, far-from-equilibrium double steps, secant updates, convergence
limits, and `lnerr` behavior. A diagnostic-only Fortran helper records every
branch-relevant event, and the Python validator checks event order, integer
control state, runtime state, residual values, and residual signs. Near zero,
absolute residual gates are used instead of unstable relative-only comparisons.

```text
xstar-atomic-port-dsec synthetic --out-dir dsec_synthetic_v0445
xstar-atomic-prepare-dsec-probe --out-dir dsec_probe_v0445
examples/117_port_xstar_dsec.py
examples/118_prepare_xstar_dsec_probe.py
```

The algorithm, mutable-state plumbing, probe, parity tools, and synthetic branch
tests are complete. Physical bounded `dsec` acceptance remains pending the first
instrumented XSTAR run. No emissivity or transfer physics is added in v0.4.45.
After that production gate, source order is `bremsmap -> calc_emisab_all ->
calc_emis_all -> complete xstarcalc`.

### v0.4.44 corrects complete fixed-state thermal-state ownership

The complete fixed-state Python path remains:

```text
positive-abundance H/He/O element loop
-> comp2 -> freef -> bremem -> heatf
-> final calc_hmc_all thermal/charge state
```

v0.4.44 does not change any physical rate, matrix, solver, continuum kernel, or
XSTAR probe. It separates the pre-continuum element-loop totals from the final
post-`heatf` totals on `FixedStateCalcHMCAllResult` and makes the pre-continuum
validator consume the correct snapshot. The four explicit fields are:

```text
httot_pre_continuum
cltot_pre_continuum
httot2_pre_continuum
cltot2_pre_continuum
```

The final public `httot`, `cltot`, `httot2`, and `cltot2` fields retain their
post-`heatf` meaning. Regression tests enforce:

```text
final - pre-continuum = translated continuum contribution
```

Example 116 reuses the existing v0.4.43 seventeen-hook XSTAR products; no XSTAR
rebuild is required. The next source target remains `dsec`, but only after the
corrected complete fixed-state acceptance gate passes.

### v0.4.43 completes fixed-state `calc_hmc_all` closure

The translated fixed-state local-zone path now reaches the return from
`calc_hmc_all`:

```text
all positive-abundance elements
  -> comp2 -> freef -> bremem -> heatf
  -> final thermal and charge state
```

The new complete-state validator executes the full translated chain, compares
current same-call pre-continuum and continuum products, and then validates
`enelec`, `elcter`, both heating/cooling total pairs, and `hmctot` against a
single final XSTAR probe row. The helper now has seventeen hooks; the added hook
is after `heatf` and immediately before `calc_hmc_all` returns.

```text
xstar-atomic-port-complete-fixed-state
examples/116_validate_xstar_calc_hmc_all_complete_fixed_state.py
```

Acceptance preserves the frozen oxygen, H/He/O, Compton, free--free,
bremsstrahlung, and heatf gates. After physical call-73 acceptance, the next
source target is `dsec`.

### v0.4.42 translates local thermal accumulation

The source-faithful fixed-state local-zone path now reaches:

```text
calc_hmc_all -> comp2 -> freef -> bremem -> heatf
```

`heatf` integrates the translated bremsstrahlung emissivity over the continuum,
converts `cmp1` and `cmp2` into volumetric Compton heating/cooling, adds
`htfreef`, and mutates `httot`, `cltot`, `httot2`, and `cltot2` in literal source
order before evaluating `hmctot`. The incoming element heating/cooling totals are
therefore retained and augmented rather than replaced.

The bounded helper now has sixteen hooks. The three new hooks snapshot incoming
thermal totals, capture the exact per-bin cumulative bremsstrahlung cooling
integral, and record the final primary/secondary totals and `hmctot`. The new CLI
and example are:

```text
xstar-atomic-port-heatf
examples/115_port_xstar_heatf.py
```

Acceptance requires exact `heatf` parity plus the frozen oxygen, H/He/O,
v0.4.39 Compton, v0.4.40 free--free, and v0.4.41 bremsstrahlung regressions.
After acceptance, the next bounded target is complete fixed-state
`calc_hmc_all` thermal/charge parity, followed by `dsec`.

### v0.4.41 translates thermal bremsstrahlung emissivity

The source-faithful local-zone path now continues in literal order through:

```text
calc_hmc_all -> comp2 -> freef -> bremem
```

`bremem` preserves source-rounded constants, the unity Gaunt factor, complete
clearing of the caller-owned `brcems` workspace, per-bin thermal
bremsstrahlung emissivity, and the currently inactive Kirchhoff-opacity
branch. The post-`freef` `opakc` array is therefore preserved exactly. `heatf`
remains deferred, so Compton, free--free, and bremsstrahlung terms are exported
but are not yet accumulated into complete heating/cooling totals.

The bounded helper now has thirteen hooks. The two new hooks snapshot the
incoming `brcems`/`opakc` workspaces before `bremem` and capture exact per-bin
`brtmp`, final `brcems`, `bbee`, and unchanged `opakc` inside the source loop.
The new CLI and example are:

```text
xstar-atomic-port-bremem
examples/114_port_xstar_bremem.py
```

Acceptance requires exact emissivity, workspace-reset, and opacity-preservation
parity plus the frozen oxygen, H/He/O, v0.4.39 Compton, and v0.4.40 free-free
regressions. After acceptance, source order continues with `heatf`.

### v0.4.40 translates the free--free absorption subsystem

The source-faithful local-zone path now continues in literal order through:

```text
calc_hmc_all -> comp2 -> freef
```

`freef` preserves the source-rounded constants, unity Gaunt factor, stimulated
absorption factor, in-place `opakc` mutation, and trapezoidal `htfreef`
integration. The incoming opacity workspace is explicit state rather than an
assumed zero array. `bremem` and `heatf` remain deferred, so continuum terms are
reported but are not yet accumulated into complete heating/cooling totals.

The bounded helper now has eleven hooks: one captures `opakc` immediately before
`freef`, and one captures exact per-bin `opaff`, updated `opakc`, and cumulative
`htfreef` inside the source loop. The new CLI and example are:

```text
xstar-atomic-port-freef
examples/113_port_xstar_freef.py
```

Acceptance requires exact free--free opacity and `htfreef` parity plus the
frozen oxygen, H/He/O, and v0.4.39 Compton regressions. After acceptance, source
order continues with `bremem`, then `heatf`.

### v0.4.39 translates the relativistic Compton subsystem

The source-faithful local-zone path now continues beyond the accepted H/He/O
element loop through:

```text
calc_hmc_all -> comp2 -> cmpfnc -> hunt3 -> global coheat.dat state
```

The implementation preserves the 101-by-101 XSTAR Compton table, its source
array orientation, one-based interpolation semantics, default-real rounded
constants, and source-order trapezoidal integrations over `epi` and `bremsa`.
The fixed-state result exports `cmp1`, `cmp2`, `htcomp`, and `clcomp`, while
leaving them unaccumulated until the source `heatf` routine is translated.

A ninth bounded XSTAR hook, inserted immediately after `call comp2`, captures
the exact same-call continuum and Compton outputs. The new CLI and example are:

```text
xstar-atomic-port-compton
examples/112_port_xstar_comp2.py
```

The accepted v0.4.34 oxygen and v0.4.38 H/He/O pre-continuum gates are packaged
as mandatory regressions. Package and direct original-Fortran tests validate
the translation; physical call-73 Compton acceptance requires rebuilding XSTAR
with the nine-hook helper and obtaining `v0439_comp2_acceptance_ready=True`.
After acceptance, source order continues with `freef`, then `bremem`, then
`heatf`.

### v0.4.36 closes the bounded H/He/O pre-continuum differences

v0.4.36 translates the four omitted H I data-type 62/rate-type 3 records
488--491 through the native `calt6062` source branch. Their endpoint pairs are
1--4, 1--7, 1--8, and 1--9, restoring the 16 missing hydrogen matrix terms.
A focused diagnostic product records their packed endpoints, quantum metadata,
evaluated rates, and matrix insertions.

Same-call matrix parity is now keyed by `(element_z, source_record, role)` rather
than shifted term position. Initial-population parity validates all 718 H/He/O
compact rows independently. The new bounded gate is
`all_element_pre_continuum_acceptance_ready=True`, which requires the accepted
oxygen call-73 regression, complete H/He/O detailed solver and thermal parity,
and zero milestone-blocking rows. No XSTAR rebuild is required; reuse the
v0.4.35 all-element call-73 probe products. Physical acceptance still requires
a production rerun of example 108.

### v0.4.35 starts the full positive-abundance fixed-state element loop

v0.4.35 begins the source-order expansion beyond the accepted oxygen-only
pre-continuum gate. The active element set is read from the selected XSTAR
`calc_hmc_all` element probe and contains every source element with
`abel(jk) > 1e-24`; inactive zero-abundance ATDB elements are not falsely
required for charge-scope closure. The new all-element plan preserves source
order, abundance, `mml/mmu`, same-call seed coverage, matrix coverage, final
solver coverage, thermal-family coverage, and mutable-workspace coverage.

The accepted v0.4.34 oxygen call-73 result is packaged and enforced as a
mandatory regression prerequisite. The new CLI and example are:

```text
xstar-atomic-port-all-elements
examples/108_port_xstar_calc_hmc_all_all_elements_fixed_state.py
```

The existing call-73 probe can start an H/He/O execution with
`--initial-population-policy use-available`: oxygen uses its exact same-call
`xileve` seed while H and He use the translated autonomous fallback. Complete
all-element parity requires rebuilding the unchanged eight-hook instrumentation
with `XSTAR_ATOMIC_HMC_TARGET_ELEMENT=0`, rerunning XSTAR, and then using
`--initial-population-policy require-all`. This release stops before
`comp2 -> freef -> bremem -> heatf`; no complete local-zone result is claimed.

### v0.4.34 separated LTE state, complete leveltemp workspace, and source cached integration

v0.4.34 closes the three source-state differences isolated by the complete
v0.4.33 oxygen diagnosis. The `levwkelement` LTE vector is now retained as
`lte_populations` while the captured same-call `xileve` state remains the
independent `msolvelucy` seed. Global `rnisg` and `bilevg` therefore use source
`rnise` without disturbing the already validated solver state.

The shared `leveltemp` array is represented through source `ndl=5000` with
zero-valued untouched columns before the ordered partial writes. The cached
`phint53hunt` branch also preserves the source's stale `atmp22` value instead of
recomputing it. These changes target the exact v0.4.33 discrepancy groups
`35/349/205/196/7/2`. Example 107 audits those groups and requires all six to
be zero in the v0.4.34 result. No new XSTAR build is needed; reuse the existing
eight-hook probe CSVs and require
`oxygen_pre_continuum_acceptance_ready=True`.


### v0.4.33 exact mutable-workspace tracing and same-call solver-state replay

v0.4.33 follows the first production v0.4.32 oxygen diagnosis without
expanding the physical scope. The element-rate translation now reconstructs
the shared mutable `leveltemp` array by replaying all active-ion writes made by
`levwkelement`, then preserving higher columns through the second
`calc_hmc_ion` pass. Every type-49/type-53/type-99 rate-7 record records the
exact `leveltemp%rlev(1,idest1/idest2)` values and the ion/write that last owned
each retained column.

The bounded XSTAR helper expands to eight insertion hooks. It captures the
exact mutable `leveltemp` reads after `ucalc`, and it now writes the complete
compact `x` vector immediately before `msolvelucy`; matrix term population
columns alone cannot reconstruct rows that are absent from the sparse operator.
The fixed-state comparator can replay this same-call `xileve` input state and
requires exact seed parity before oxygen acceptance. This corrects the source
semantics: `calc_hmc_element` seeds `msolvelucy` from the incoming global
`xilevg` state, not from the LTE `rnise` vector returned by `levwkelement`.

A fresh instrumented XSTAR run is required to determine whether the corrected
workspace and input-state history close the 11 active final populations, 18
outer-start populations, O III/O IV/O VI `xtot`, eight thermal-family rows, and
one `cll2` row. No physical oxygen acceptance is claimed until
`oxygen_pre_continuum_acceptance_ready=True`.

### v0.4.32 source counters, synchronized snapshot gate, and energy-workspace parity

v0.4.32 is limited to four source-semantic corrections identified by the
production v0.4.31 oxygen run. The compact element basis now preserves XSTAR's
`nionp` counter across inactive lower ion stages, so O III--O VIII retain source
counters 3--8 and `xtot` is accumulated into the corresponding global element
slots. The final-`msolvelucy` snapshot gate now tests only internal XSTAR
synchronization: one iteration tuple across both files, matching compact
matrix dimensions, and matrix population columns identical to the synchronized
population table. Python and XSTAR are no longer required to converge in the
same number of iterations.

The type-54 energy channel now uses the source dimensionless
`delt = DeltaE/(0.861707*T_1e4)` before conversion to erg. The element second
pass also preserves the mutable `leveltemp` workspace: current columns
`1:nlev` are overwritten while higher columns retain the preceding ion's
values, matching the type-49/type-53/type-99 electron-energy corrections.
Physical oxygen acceptance still requires a fresh production example-105 rerun;
all-element expansion remains blocked until
`oxygen_pre_continuum_acceptance_ready=True`.

### v0.4.30 Fortran probe numeric compatibility

v0.4.30 accepts width-compressed Fortran exponents such as `1.23-107` in the
calc_hmc_all matrix and thermal probe readers, while newly generated probes
write explicit `E±ddd` exponents. This is an I/O-only hotfix; the v0.4.29
physics and acceptance gates are unchanged. Existing six-hook probe CSVs can be
reused without rebuilding XSTAR.

### v0.4.29 type-50 thermal closure and same-call matrix parity

v0.4.29 restores the source type-50 `ans3/ans4` bound-bound energy channels, captures XSTAR thermal accumulators by data type and rate type, and compares the exact sparse `aj1/aj2/cj/cj2` term list from the same `msolvelucy` call. Exact topology and active `(A_python-A_XSTAR) @ x_XSTAR` closure form the milestone matrix gate; all coefficient differences remain available through a separate strict gate.

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

### v0.4.37 H/He type-77 source gate

The complete H/He/O call-73 rerun isolated the remaining hydrogen blocker to
`ucalc.f90` type 77. XSTAR skips `calt77` and returns exact zero when the mutable
endpoint energy separation is below 1 eV. v0.4.37 reproduces that source gate,
retains the four zero matrix roles, and adds example 110 for the final
all-element pre-continuum acceptance check.

### v0.4.38 final-x `xiin` versus outer-start `xtot`

The v0.4.37 rerun confirmed the type-77 correction and left one H I global-ion
row. XSTAR `calc_hmc_element` constructs `xii` from the returned final compact
population vector `x`, and `calc_hmc_all` copies that value to `xiin`. In
contrast, `msolvelucy` accumulates diagnostic `xtot` from `xo`, the population
vector at the start of the final Lucy outer iteration. v0.4.38 keeps these
vectors separate: final `x` drives `xiin`, charge conservation, and the fully
stripped residual; final-outer-start `xo` remains the source of `xtotg`.
Example 111 validates the split and the all-element pre-continuum acceptance.

## Source-faithful `calc_emisab_all` (v0.4.61)

v0.4.61 translates the bounded emissivity/opacity abundance chain
`calc_emisab_all -> calc_emisab_element -> calc_emisab_ion`. It preserves the
Fortran output-reset boundary, caller-owned continuum-array side effects,
all-ion compact alias mapping, inactive-ion offsets, active-ion `leveltemp`
mutation, and rate types 4, 7, 9, and 14.

```bash
PYTHONPATH=src python examples/131_validate_xstar_calc_emisab_all.py \
  --out-dir xstar_calc_emisab_all_source_validation_v0461 \
  --print-summary
```

The next source-order target is `calc_emis_all`; full `xstarcalc`, radial
transfer, and output writers remain unported.

## v0.6.0a22 C++ parity policy

The current source-faithful Python path is the reference for enabling C++ accelerators.  Original Fortran XSTAR products are close but not bit-for-bit identical to the Python port, so C++ work is now gated against Python-reference products first.  Type-49/type-53 Mg direct accumulators, pre-matrix shortcuts, and C++ binemis remain opt-in until a Python-reference vs C++-candidate parity gate passes for `xout_step.log` and FITS products.

Use the C++ parity gate after running one default Python reference directory and one C++ candidate directory:

```bash
xstar-tools-cpp-parity-gate \
  --reference-dir python_xstar_tools_benchmark_v0600a22/helike_type69_mg11_ne1e8 \
  --candidate-dir python_xstar_tools_benchmark_v0600a22_cpp_type49/helike_type69_mg11_ne1e8 \
  --out-json cpp_parity_type49.json
```


### v0.6.0a29 C++ auto-backend policy

The Mg `rate_type=7` / `data_type=49` matrix path is enabled for `matrix-backend=auto` after the v0.6.0a28 shadow-parity gate matched all compared records against the Python reference.  Type51, type53, broader direct accumulation, pre-matrix shortcuts, and C++ binemis remain opt-in until they pass the same Python-vs-C++ gate. Source scanning remains available because the promoted type49 path uses it only to enumerate candidate records.  To opt out of type49 while using `auto`, set `XSTAR_ATOMIC_MATRIX_MG_ION_TYPE49_PHOTO_AUTO=0` or `XSTAR_ATOMIC_MATRIX_MG_ION_TYPE49_PHOTO_CPP=0`.
