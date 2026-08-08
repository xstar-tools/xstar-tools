# Fortran source map

This map is based on the supplied XSTAR 2.59g source archive (`xstar_source.tar.gz`, SHA-256 `f64c8c394e05f5a056206f1143259a8830f58ddf950c1efc15a03a00572db37a`). It records the canonical executable ownership that productization must preserve.

The table intentionally distinguishes **scientific computation**, **caller-owned workspace**, and **publication lifetime**. Many parity defects arose when those were treated as interchangeable.

## Routine-level concordance

| Fortran routine/file | Scientific role | Important local/caller workspace | Python implementation | C++ implementation | Qualification evidence | Intentional deviations / notes |
|---|---|---|---|---|---|---|
| `src/xstar/xstar.f90` | Top-level executable, parameter/setup sequence, radial pass/shell controller, final-output sequence | radial counters `kk/jk/jkp`, direction `ldir`, radius/column, radiation/depth arrays, global population and product arrays | `physical_runner.py`, `driver.py`, `radial_transfer.py`, `radial_control.py` | `xstar_standalone.cpp`, `xstar_engine.cpp`, `xstar_run_state.*` | all-62 STEP 12.3.42; all-62 FITS 12.3.43.3; three-mode 12.3.44 | Python decomposes inline controller blocks into testable functions but preserves source predicates/order. |
| `rread1.f90` | Read parameters; calculate initial pressure/density/radius and source-control values | `r19`, `r`, `xpx`, `p`, `zeta`, abundance vector, `ncn2`, `npass`, `critf`, hidden switches | `physical_runner.normalize_xstar_parameters`, source-real helpers in runner/radial path | `xstar_atdb_runtime.cpp` contains source reader/default-REAL compatibility for native production | `12.3.36_FORTRAN_RREAD1_RADIUS_LITERAL_REPAIR` | `uclgsr8` source values and default-REAL literals are reproduced deliberately; `1.e+19` is not replaced by an ideal binary64 literal. |
| `ener.f90`, `bremsmap.f90`, `init.f90` | Energy-grid initialization, radiation remapping, initial global state | `epi`, `epim`, `bremsa`, `bremsam`, `bremsint`, depth/emissivity/population arrays | `physical_runner.ener_grid`, radiation helpers, initial-state builders | source-real energy-grid helpers and native run-state construction | source-port 0.4.60/0.4.63; C++ three-mode 12.3.44 | Python/C++ use explicit arrays rather than COMMON/global storage, but retain source grid values/order. |
| `xstarsetup.f90` | Load ATDB, call `setptrs`, initialize atomic/LTE support data and abundance/data tables | packed record vectors, pointer table, level temperature data | `atomic_database.readtbl`, `atomic_database.setptrs`, `populate_atomic_state` | `xstar_atdb_runtime.cpp` | atomic source-port tests; all-element fixed-state 12.3.x; C++ 12.3.44 | Memory-mapped Python FITS storage avoids a second GiB-scale copy; logical record semantics remain source-one-based. |
| `setptrs.f90` | Construct derived database topology and publication attachments | `npar`, `npfirst`, `npfi/npfe`, `npnxt`, `npilev/npilevi`, `npcon/npconi/npconi2`, `nplin/nplini`, `nlevs` | `atomic_database.setptrs`, `XSTARDerivedPointers` | native `build_pointers`/layout code in `xstar_atdb_runtime.cpp` | generic `npilev`/publication repairs through 12.3.20-22 and 12.3.43; 45.x publication qualification | Cache files may persist derived pointers, but the pointer identities are checked against the same source construction. |
| `calc_ion_rates.f90`, `istruc.f90`, `ioneqm.f90` | First-pass total-rate ionization balance and active adjacent ion-stage selection | total ionization/recombination arrays, preliminary ion fractions, `mml/mmu` | `ion_balance.calc_ion_rates`, `ioneqm`, `istruc`, `select_ion_stage_limits` | rate/element construction in `fixed_state_engine.cpp` / `element_engine.cpp` | source-port pre-matrix qualification; all-62 science 12.3.42/43 | This pass is intentionally separate from population-weighted post-solve diagnostics. |
| `calc_hmc_all.f90` | Master fixed-temperature heating/cooling/rate/population calculation across elements | global `xilevg/bilevg/rnisg`; ion rates; per-element thermal arrays; `httot/cltot/hmctot/elcter` | `local_zone.calc_hmc_all` | `fixed_state_engine.cpp`, `thermal_kernels.cpp` | Ca/O all-element matrix closure 12.3.25; all-62 12.3.42-44 | Python packages state into return objects/callbacks instead of global COMMON arrays. Source element order and reduction semantics remain qualified. |
| `calc_hmc_element.f90` | Per-element preliminary balance, compact basis, record-rate matrix assembly, solve and element diagnostics | element-local ion block, `leveltemp`, compact basis/`indb`, matrix arrays `ajise/cjise/cjise2` | `element_equilibrium.solve_element_statistical_equilibrium` plus `ion_balance` | `element_engine.cpp`, `fixed_state_engine.cpp`, `matrix_kernels.cpp` | `12.3.25_GENERIC_TERMINAL_CLAMP_ALL_ELEMENT_SEED` | C++ compact terminal rows use the accepted source endpoint clamp (`min(ipmat, indb(...))`). |
| `levwkelement.f90`, `levwk.f90` | Build per-element/ion compact level representation, superlevel mapping and LTE level populations | `leveltemp`, `rnise`, `bb`, `nsup`, `nion`, compact endpoint maps | `element_equilibrium.build_level_table`, `levwk`, `levwkelement`, `build_element_compact_basis` | `level_population.cpp`, `fixed_state_engine.cpp` | matrix/level population qualifications culminating in 12.3.25 | Python preserves explicit one-based compact topology even though NumPy storage is zero-based internally. |
| `calc_hmc_ion.f90`, `ucalc.f90` family | Traverse atomic records, evaluate rates, add source-ordered matrix/heating/cooling contributions | record-local `ans*`, endpoint identities, `leveltemp`, matrix insertion terms, escape factors | `element_equilibrium` + `ucalc.py` and type-specific helpers | `rate_kernels.cpp`, `matrix_kernels.cpp`, `fixed_state_engine.cpp` | extensive type/rate closure; all-element terminal clamp 12.3.25; three-mode 12.3.44 | C++ may batch/evaluate typed kernels, but accepted production paths preserve the source contribution ordering and active-family gates. |
| `msolvelucy.f90` | Solve multilevel statistical-equilibrium operator with Lucy superlevel iteration and normalization | compact matrices `ajisb/cjisb/cjisb2`, `indb`, `nsup`, population vector, superlevel work arrays | `element_equilibrium` Lucy solve + `linear_algebra.py` | `element_engine.cpp`, `fixed_state_engine.cpp`, `matrix_kernels.cpp` | Ca XVIII/Ca XVII matrix attribution/closure 12.3.25 | Solver representation differs, but accepted endpoint/domain, normalization, and final population semantics are source-equivalent. |
| `comp2.f90`, `freef.f90`, `bremem.f90`, `heatf.f90` | Continuum Compton/free-free heating/cooling, bremsstrahlung emissivity, final thermal aggregation | continuum opacity/emissivity, `cmp1/cmp2`, `htfreef`, heating/cooling families | `compton.py`, `free_free.py`, `bremsstrahlung.py`, `thermal_balance.py` | `thermal_kernels.cpp`, source-order thermal reducer | 0.4.39-0.4.42 source-port closures; thermal parity campaign; 12.3.44 | Native reduction is optimized but must retain source term ownership and accepted ordering. |
| `dsec.f90` | Charge/thermal equilibrium nonlinear controller; repeated `calc_hmc_all` evaluations | mutable trial temperature/electron state, previous trial global populations, bracket/secant variables, residuals and iteration counters | `dsec.dsec`, `DsecMutableRuntimeState`, `CalcHMCAllDsecEvaluator` | native controller support in `fixed_state_engine.cpp`/standalone path | DSEC source-port 0.4.45+; all-62 trajectory/STEP 12.3.42; C++ 12.3.44 | No generic root-finder substitution: branch order and source state ownership are characterization-tested. |
| `calc_emisab_all.f90`, `calc_emisab_element.f90`, `calc_emisab_ion.f90` | Integrated/reduced-grid line emissivity/opacity and RRC emissivity/absorption/threshold-opacity production | `rcem`, `oplin`, `cemab`, `cabab`, `opakab`, active ion limits and compact populations | `emissivity.calc_emisab_all/element/ion` | `line_emissivity.cpp`, `fixed_state_engine.cpp`, publication state in `xstar_science_fits.cpp` | final FITS 12.3.43.x; Python publication 45.1-45.3.3.8 | 45.3.3.8 adds an **output-only** retained publication bridge; it must not mutate physical rates/matrices/populations. |
| `calc_emis_all.f90`, `calc_emis_element.f90`, `calc_emis_ion.f90`, `rlbin.f90` | Full-grid continuum/line/RRC emission and opacity construction after integrated products are available | `rccemis`, `opakc`, `opakcont`, `fline/flinel`, feature rank/bin tables, continuum work indices | `emergent_emissivity.calc_emis_all/element/ion`, `rlbin_insert` | `line_emissivity.cpp`, `opacity_kernels.cpp`, spectral portions of `fixed_state_engine.cpp` | spectrum/continuum/detail4 closures; all-62 FITS 12.3.43.3; three-mode 12.3.44 | Python exposes rank/bin workspaces explicitly. C++ uses qualified batching/optimized traversal where bit/material parity is established. |
| `linopac.f90` (Type50 path) | Accumulate a source line profile into continuum opacity over the active energy range | line center/width, `epi`, opacity accumulator, profile/rebin bounds and source insertion order | `emergent_emissivity._source_linopac_*` plus Type50 provenance tools | `opacity_kernels.cpp`, production specialization in `fixed_state_engine.cpp` | Type50 optimization 12.3.26-31, especially 12.3.31 cursor promotion/decomposition | C++ cursor/AVX helpers alter traversal mechanics only. Accepted invariant: same source-order profile arithmetic/update semantics and bit-equivalent qualified products. |
| `step.f90` | Choose radial shell thickness from opacity/emission/line constraints and user Courant controls | `delr`, `delr0`, opacity/emission arrays, line flux, column/radius controls | `radial_transfer.step` | standalone production radial controller | radial source-port 0.4.64; all-62 STEP 12.3.42 | Source formulas/order retained; no new adaptive algorithm. |
| `trnfrc.f90`, `trnfrn.f90` | Two-stream continuum/radiation transfer into and out of a shell | `zrems`, `bremsa`, continuum depths, direction-owned rows, shell geometry | `radial_transfer.trnfrc`, `trnfrn` | `xstar_engine.cpp` / native run-state controller | radial validation 0.4.64-0.4.68; all-62 12.3.42-44 | Arrays are object-owned rather than COMMON-owned; direction ownership follows source semantics. |
| `stpcut.f90` | Limit/terminate radial stepping against total column, radius and source stop criteria | `xcol`, `xpxcol`, `r`, `rmax`, `delr`, `xee`, direction/pass state | `radial_transfer.stpcut`, `radial_control` | standalone production controller | O VII terminal-state repairs 12.3.9-11; exact radius 12.3.36; all-62 12.3.42 | Termination is source predicate logic, not a tolerance-driven Python convergence invention. |
| `savd.f90`, `unsavd.f90`, `rstepr*` | Persist and restore per-shell state across radial passes | REAL(4)-persisted scalar/population/line/RRC/continuum values; HDU insertion order; direction-owned depths | `saved_radial_state.py`, save/restore support in `radial_transfer.py` | native run-state/FITS persistence in standalone path | source-port 0.4.67; detail/publication closures 12.3.43-45 | In-memory Python snapshots model source FITS persistence for bounded execution; REAL(4) round-trip semantics are explicit. |
| `fstepr.f90` | Per-shell level/population detail writer | level identities, populations, LTE/departure state, shell metadata | `output_writers.py` detail shell publication | `xstar_science_fits.cpp` | detail population/identity closures through 12.3.43; C++ 12.3.44 | Publication-only formatting/metadata may differ internally; qualified product semantics govern. |
| `fstepr2.f90` | Per-shell detailed line writer (`xoNN_detal2.fits`) | line identity, energy, inward/outward emission, opacity/depth | `output_writers.py` | `xstar_science_fits.cpp` | detal2 inventory/activity closure 12.3.43.2; all-62 FITS | Source membership and material numerical surfaces are separately diagnosed. |
| `fstepr3.f90` | Per-shell detailed RRC/continuum-record writer (`xoNN_detal3.fits`) | `cemab`, `cabab`, `opakab`, `tauc`, canonical `npcon/npconi2`, source/level labels | `output_writers.py` + retained publication state from `emissivity.py`/`element_equilibrium.py` | `xstar_science_fits.cpp` | 45.3.3.7 C5 terminal replay; 45.3.3.8 full spectral publication; Ca/O accepted exceptions | This surface is lifetime-sensitive. Accepted Ca/O membership exceptions are structural metadata, not numerical science failures. |
| `fstepr4.f90` | Per-shell binned continuum writer (`xoNN_detal4.fits`) | `zrems`, `rccemis`, `opakc`, `dpthc` and direction-owned emission/depth | `output_writers.py` | `xstar_science_fits.cpp` | continuum/detail4 closure 5.20.14+; final all-62 FITS | Frozen after closure; no ordinary productization changes to producer science. |
| `pprint.f90` | STEP/log print surfaces, ranked line/RRC/edge diagnostics, radial summaries, abundance FITS accumulation | fixed-capacity ranked arrays, labels/identities, ion columns, timing, radial/thermal state | `pprint_legacy.py` | `xstar_step_log.cpp` | comparator repair 12.3.34; material Option15 12.3.36.1; rank attachment 12.3.41; all-62 STEP 12.3.42; 45.1/45.3.3.2 | Comparator policy separates numerical rank science, identity/order/membership, and inventory/material surfaces. |
| `writespectra.f90` | Final binned spectrum including lines -> `xout_spect1.fits` | final `zrems`, incident spectrum, continuum depths, line luminosity accumulation | `output_writers.py` final products | `xstar_science_fits.cpp` | spectrum closure 12.3.25/43.3; 12.3.44 | Final state is evaluated after radial completion; terminal producer lifetime matters. |
| `writespectra2.f90` | Final line table -> `xout_lines1.fits` | ranked/filtered line identities, energies, luminosities and depths | `output_writers.py` | `xstar_science_fits.cpp` | line identity/order/depth closure 5.20.16+; 12.3.43.3/44 | Fixed-capacity source ranking semantics retained where observable. |
| `writespectra3.f90` | Final continuum without binned lines -> `xout_cont1.fits` | incident/outward continuum and continuum-only depths | `output_writers.py` | `xstar_science_fits.cpp` | continuum closure and 12.3.43.3/44 | Product is distinct from `xout_spect1`; do not collapse ownership. |
| `writespectra4.f90` | Final RRC table -> `xout_rrc1.fits` | `elumab/elumabo`, `tauc`, source continuum identities/levels | `output_writers.py` | `xstar_science_fits.cpp` | RRC identity/999-vs-9999 closure 5.20.13; 12.3.43.3/44 | RRC row identity/source attachment is source-defined and separately qualified. |

## Top-level startup and initialization

The canonical `xstar.f90` startup is approximately:

```text
parameter/default setup
  -> rread1
  -> ener (primary and working energy grids)
  -> xstarsetup
       -> readtbl
       -> setptrs
       -> LTE/atomic support initialization
  -> pprint startup parameter/header surfaces
  -> init
  -> radial passes
```

The source itself prints `xstar version 2.59g`. The source map in this document is tied to that supplied tree rather than to an inferred generic XSTAR version.

## Parameter and default-REAL semantics

`rread1` uses the XPI/UCL parameter interface (`uclgsr8`, `uclgsi`, `uclgst`) and then performs source calculations. Two kinds of semantics matter:

1. **reader conversion semantics** - the parameter system may store a lower-kind value which is promoted by a higher-kind reader;
2. **literal semantics** - a literal such as `1.e+19` is a default REAL literal even when used in a `REAL(8)` expression.

The accepted 12.3.36 repair reproduces both where material. Future refactors must not normalize these values merely because a mathematically equivalent decimal can be written as Python/C++ binary64.

## Atomic-database pointer ownership

`setptrs` is not just an index accelerator. Its derived relationships participate in physics and publication identity. In particular:

- `npilev/npilevi` bind atomic records to level topology;
- `npcon/npconi/npconi2` bind continuum/RRC records and their source identities;
- `nplin/nplini` bind line records;
- parent/next-record chains establish traversal and attachment order.

Therefore pointer caches are acceptable only when they reproduce the canonical `setptrs` result for the same ATDB.

## Two-stage ion and level population solve

The Fortran and the XSTAR manual agree on the conceptual split:

1. use total ionization/recombination rates to estimate ion fractions and choose an adjacent active stage block;
2. assemble and solve the full multilevel kinetic operator for the selected ions.

This distinction is preserved in Python by `ion_balance.py` versus `element_equilibrium.py` and in the qualified native fixed-state engine.

## Thermal construction and `dsec`

`calc_hmc_all` is a fixed-state scientific operator: given a trial temperature/electron state and current radiation/escape state, it computes level populations, rates, heating, cooling, and charge-balance information. `dsec` is the nonlinear controller that repeatedly calls that operator.

Do not merge those responsibilities in a way that resets source-owned state between trials or changes the source branch order without dedicated characterization.

## Reduced-grid versus full-grid spectral paths

The current source explicitly places:

```text
calc_hmc_all
calc_emisab_all
calc_emis_all
```

at the end of `xstarcalc`. `calc_emisab_all` owns integrated line/RRC quantities; `calc_emis_all` owns the subsequent full-grid spectral construction. This split is required to understand detail-publication lifetime and Type50 ownership.

## STEP print-option map

`pprint.f90` documents and implements a broad set of print options. The qualification campaign most heavily exercises these:

| Option | Source role | Qualification interpretation |
|---:|---|---|
| 1 | strongest emission lines sorted by strength | numerical ranked-array comparison separated from identity/order diagnostics |
| 5 | energy sums / error | `err` is compared relatively after 12.3.34 comparator repair |
| 9 | short radial-zone summary | trajectory/zone characterization |
| 12 | append radial abundance data to `xout_abund1` | final abundance publication |
| 15 | line luminosities/depth material surface | normalized-L1 material science is primary; inventory is separate |
| 17 | column headings | exact source-style header semantics used by STEP qualification |
| 19 | recombination-continuum luminosities | RRC numerical/product publication |
| 22 | final ionization/summary quantities | terminal source state |
| 23 | strongest absorption lines sorted by strength | numerical rank science separated from identity/order/membership |
| 24 | absorption edges | inventory and numerical common-row science separated |
| 27 | ion column densities in the current port | format/default-REAL threshold fixes accepted in 45.1 |

The exact full option list remains defined by `pprint.f90`; the table above records the options with explicit frozen comparator policy.

## Terminal/final-output lifetime

After the radial passes, `xstar.f90` performs another local calculation at the final boundary, calls final STEP options, and then writes final FITS products. Per-shell detail products have already been written by `savd -> fstepr*` during the radial loop.

This means three states must not be conflated:

1. the physical local state used during a shell solve;
2. the state retained/persisted for a detail shell or later pass;
3. the terminal state consumed by final public products.

The accepted Python publication bridge at science revision 45.3.3.8 is deliberately **output-only**: it reconstructs source publication lifetime where necessary without modifying rates, matrices, populations, thermal balance, transport, or trajectory.

## Related documents

- `architecture.md` - execution and ownership overview.
- `python_cpp_fortran_concordance.md` - implementation and qualification map with stable concordance IDs.
- `../science/xstar_references.md` - literature/manual correspondence.
