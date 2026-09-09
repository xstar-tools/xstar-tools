# Python / Fortran source-comment index

**Productization version:** `0.6.56`  
**Science revision:** `0.6.48.12.3.45.3.3.8`  
**Frozen C++ scientific baseline:** `0.6.48.12.3.44`

This index is the Python companion to `cpp_fortran_source_comments.md`. The marked top-of-file comments are documentation-only. `qualification/python_source_comment_overlay.json` pins both the annotated `0.6.55` bytes and the exact pre-comment `0.6.54` bytes. In `0.6.56`, 44 annotated modules remain active; the old Type53 semantics qualification utility was moved byte-for-byte to `historical/python/xstar_parity_campaign/`. Removing only the marked block must still recover the `0.6.54` baseline for every annotated file.

## Atomic-database terminology

The XSTAR Manual Chapter 12 and Mendoza et al. (2021), Appendix A use two independent record identifiers:

- **data type**: how the constants in a database record are interpreted/evaluated (the central `ucalc` branch);
- **rate type**: how XSTAR consumes the returned rate(s) in ion balance, matrix assembly, thermal accounting, transfer, or publication.

The six integer record-header fields documented by the manual are data type, rate type, continuation flag, number of reals, number of integers, and number of characters. The Python comments explicitly preserve this distinction.

Appendix A documents the important current families such as Types 49/53 (partial photoionization), 50/91 (radiative lines), 51/98 (CHIANTI collision strengths), 70/99 (superlevels), 72 (autoionization), 76 (two-photon), 85/86/88 (K-shell data), and 95 (collisional ionization). Types 89/96/97 occur in the current `ucalc.f90` but are not enumerated in the supplied Appendix-A/Chapter-12 tables; comments therefore cite executable Fortran for those labels.

## Annotated Python modules

| Python file | Fortran authority | Concordance | Atomic-data note |
|---|---|---|---|
| `active_subsets.py` | setptrs.f90 plus calc_hmc*/calc_emis* source-index traversal | `DB-001; BACKEND-001` | yes |
| `atomic_database.py` | readtbl.f90 / setptrs.f90 / xstarsetup.f90 | `DB-001; INPUT-001` | yes |
| `bremsstrahlung.py` | bremem.f90 | `THERM-001` | no |
| `compact_active_atdb.py` | readtbl.f90 / setptrs.f90 plus calc_hmc*/ucalc record traversal | `DB-001; BACKEND-001` | yes |
| `compton.py` | comp2.f90 / cmpfnc.f90 | `THERM-001` | no |
| `constants.py` | constants.f90; literal-sensitive uses in rread1.f90 / dsec.f90 / trnfrc.f90 | `INPUT-001; THERM-001; RADIAL-001` | no |
| `cpp_backend_element.py` | calc_hmc_element.f90 / calc_hmc_ion.f90 / calc_ion_rates.f90 / levwkelement.f90 | `ION-001; LEVEL-001; MATRIX-001` | no |
| `cpp_backend_emissivity.py` | calc_emisab*.f90 / calc_emis*.f90 | `EMISAB-001; EMIS-001` | no |
| `cpp_backend_extra.py` | ucalc.f90 / calc_hmc_ion.f90; no direct Fortran backend-dispatch analogue | `BACKEND-001; MATRIX-001` | yes |
| `cpp_backend_final_recompute.py` | final xstar.f90 sequence / xstarcalc.f90 / pprint.f90 / writespectra*.f90 | `TERMINAL-001; FINAL-001` | no |
| `cpp_backend_matrix.py` | calc_hmc_ion.f90 / calc_hmc_element.f90 / msolvelucy.f90 / ucalc.f90 | `MATRIX-001; LEVEL-001` | yes |
| `cpp_backend_production_zone.py` | xstarcalc.f90 scientific boundary; no Fortran backend-dispatch analogue | `BACKEND-001; ARCH-001` | no |
| `cpp_backend_rates.py` | ucalc.f90 / calc_hmc_ion.f90 | `MATRIX-001; ION-001` | yes |
| `cpp_backend_spectral.py` | calc_emisab*.f90 / calc_emis*.f90 / linopac.f90 | `EMISAB-001; EMIS-001; TYPE50-001` | no |
| `cpp_backend_thermal.py` | calc_hmc_all.f90 / heatf.f90 / dsec.f90 | `THERM-001; DSEC-001` | no |
| `driver.py` | xstar.f90 / xstarcalc.f90 | `ARCH-001; BACKEND-001` | no |
| `dsec.py` | dsec.f90 | `DSEC-001; THERM-001` | no |
| `element_equilibrium.py` | calc_hmc_element.f90 / calc_hmc_ion.f90 / levwkelement.f90 / levwk.f90 / msolvelucy.f90 | `LEVEL-001; MATRIX-001; TERMINAL-001` | yes |
| `emergent_emissivity.py` | calc_emis_all.f90 / calc_emis_element.f90 / calc_emis_ion.f90 / rlbin.f90 / binemis.f90 / linopac.f90 | `EMIS-001; TYPE50-001` | yes |
| `emissivity.py` | calc_emisab_all.f90 / calc_emisab_element.f90 / calc_emisab_ion.f90 | `EMISAB-001; TERMINAL-001` | yes |
| `free_free.py` | freef.f90 | `THERM-001` | no |
| `gsmooth.py` | gsmooth.f90 / gsmooth2.f90 | `RADIAL-001; EMIS-001` | no |
| `heatt.py` | heatt.f90 | `RADIAL-001; STATE-001; EMIS-001` | yes |
| `ion_balance.py` | calc_ion_rates.f90 / istruc.f90 / ioneqm.f90 | `ION-001` | yes |
| `ionization.py` | phintfo.f90 / phint53.f90 / phint53hunt.f90 / phextrap.f90 / milne.f90 / enxt.f90 | `ION-001; MATRIX-001` | yes |
| `linear_algebra.py` | leqt2f.f90 / ludcmp.f90 / lubksb.f90 / mprove.f90 / msolvelucy.f90 | `LEVEL-001; MATRIX-001` | no |
| `local_zone.py` | calc_hmc_all.f90 / calc_hmc_element.f90 / calc_hmc_ion.f90 | `THERM-001; MATRIX-001; ION-001` | no |
| `native_fixed_program.py` | ucalc.f90 / calc_hmc_ion.f90 / calc_hmc_element.f90 | `MATRIX-001; LEVEL-001; BACKEND-001` | yes |
| `output_writers.py` | fstepr.f90 / fstepr2.f90 / fstepr3.f90 / fstepr4.f90 / writespectra*.f90 | `DETAIL-001; FINAL-001; TERMINAL-001` | yes |
| `physical_runner.py` | rread1.f90; xstar.f90; xstarcalc.f90 | `INPUT-001; ARCH-001; RADIAL-001` | no |
| `pprint_legacy.py` | pprint.f90 / nbinc.f90 / huntf.f90 | `STEP-001; TERMINAL-001` | no |
| `radial_control.py` | xstar.f90 radial/pass predicates and density/termination branches | `RADIAL-001; ARCH-001` | no |
| `radial_transfer.py` | xstar.f90 / step.f90 / trnfrc.f90 / heatt.f90 / stpcut.f90 / trnfrn.f90 | `ARCH-001; RADIAL-001; STATE-001` | no |
| `radiation.py` | bremsmap.f90 / nbinc.f90 / huntf.f90 | `ARCH-001; EMISAB-001` | no |
| `saved_radial_state.py` | savd.f90 / unsavd.f90 / rstepr*.f90 | `STATE-001; DETAIL-001; TERMINAL-001` | no |
| `source_real_energy_grid.py` | ener.f90 | `ARCH-001; INPUT-001` | no |
| `state.py` | globaldata modules; savd.f90 / unsavd.f90 / rstepr*.f90 | `STATE-001; RADIAL-001; TERMINAL-001` | no |
| `thermal_balance.py` | heatf.f90 / calc_hmc_all.f90 | `THERM-001` | no |
| `type50_profile_provenance.py` | ucalc.f90 label 50 / deleafnd.f90 / linopac.f90 | `TYPE50-001` | yes |
| `ucalc.py` | ucalc.f90 and its calt*/phint*/linopac leaf routines | `DB-001; ION-001; MATRIX-001; EMISAB-001; TYPE50-001` | yes |
| `ucalc_dispatch.py` | ucalc.f90 computed-GOTO data-type dispatch | `MATRIX-001; DB-001` | yes |
| `ucalc_inventory.py` | readtbl.f90 / setptrs.f90 / ucalc.f90 | `DB-001; MATRIX-001` | yes |
| `ucalc_leaves.py` | ucalc.f90 leaf dependencies including calt*, exintn, phextrap, spline/interpolation helpers | `MATRIX-001; TYPE50-001` | yes |
| `xstarcalc.py` | xstarcalc.f90 | `ARCH-001; DSEC-001; THERM-001; EMISAB-001; EMIS-001` | no |

## Archived annotated parity utility

`type53_semantics.py` is no longer an active runtime/developer module. Its exact annotated 0.6.55 bytes and pre-comment 0.6.54 hash remain recorded in `qualification/python_source_comment_overlay.json`, and the full history archive retains it at `historical/python/xstar_parity_campaign/src/xstar_tools/xstar/type53_semantics.py`. The active Type53 implementation correspondence is documented through `ucalc.py`, `ucalc_dispatch.py`, `ionization.py`, and the C++ rate/matrix paths.

## Verification

```bash
python tools/qualification/check_source_concordance.py
python tools/qualification/check_parity_freeze.py
python tools/qualification/check_source_concordance.py
```

The Python comment checker strips only the marked leading block and verifies byte identity with the recorded `0.6.54` baseline. This is stronger than an AST-only check and prevents executable changes from being hidden in the comment pass.

## 0.6.73 function-level expansion

The original leading correspondence blocks remain pinned historical evidence.
Version 0.6.73 adds a second, reversible `XSTAR-FUNCTION-COMMENT` overlay at
function definitions so maintainers can understand local purpose and physical
context without first opening the manual/papers. The older overlay checker
strips this newer layer before validating its original hashes; the dedicated
`check_source_function_comments.py` gate independently proves the new layer is
comment-only. See `function_commenting.md`.


> Since `0.6.90.3`, exact science-critical source bytes are enforced by `tools/qualification/check_parity_freeze.py`; closed comment-overlay replay manifests are retained by repository history rather than shipped in active releases.
