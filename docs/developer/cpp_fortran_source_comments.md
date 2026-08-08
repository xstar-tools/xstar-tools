# C++ / Fortran source-comment index

**Productization version:** `0.6.54`  
**Science revision:** `0.6.48.12.3.45.3.3.8`  
**Frozen C++ scientific baseline:** `0.6.48.12.3.44`

Every `.cpp`, `.h`, and `.hpp` file under `src/xstar_tools/xstar/cpp/` carries a marked `XSTAR-SOURCE-CORRESPONDENCE` comment block. The marked top-of-file blocks remain documentation-only and are pinned by `qualification/cpp_source_comment_overlay.json`. Version `0.6.54` also performs an approved non-science native-layout refactor: four version-labeled runtime headers receive stable names, `constants.def` moves into this C++ directory, and atomic-data comments are added from the XSTAR Manual Chapter 12 and Mendoza et al. (2021) Appendix A. `qualification/cpp_non_science_refactor_0_6_54.json` canonicalizes comments/whitespace and reverses only those approved path/identifier relocations; all 47 files must then match their `0.6.53` canonical non-comment hashes.

| C++ file | Fortran authority | Relation | Concordance |
|---|---|---|---|
| `canonical_thermal_term.hpp` | calc_hmc_all.f90; calc_hmc_element.f90; calc_hmc_ion.f90 | C++ representation helper; preserves source term identity and accumulation ownership rather than translating a single Fortran array type. | `THERM-001; MATRIX-001` |
| `coheat_table.h` | xstarsetup.f90 (coheat.dat load); cmpfnc.f90; comp2.f90 | Data-equivalent snapshot used by qualified native evaluation; interpolation semantics remain those of cmpfnc/hunt3. | `THERM-001` |
| `compact_arrays.hpp` | levwkelement.f90; levwk.f90; calc_hmc_ion.f90 | Storage transformation only; indices/endpoints must reproduce the Fortran compact basis and clamping semantics. | `LEVEL-001; MATRIX-001` |
| `compiled_case.cpp` | xstar.f90; xstarcalc.f90; pprint.f90; writespectra*.f90 | C++ infrastructure, not a direct Fortran routine translation; validates the same full-run scientific boundary. | `ARCH-001; BACKEND-001; FINAL-001` |
| `element_engine.cpp` | calc_hmc_element.f90; calc_hmc_ion.f90; calc_ion_rates.f90; istruc.f90; ioneqm.f90; levwkelement.f90; msolvelucy.f90 | Source-equivalent operator with different storage; source traversal/order, endpoint clamping, and solve invariants are qualified. | `ION-001; LEVEL-001; MATRIX-001; THERM-001` |
| `error_codes.hpp` | No direct Fortran routine. | Infrastructure only; must not alter scientific state or Fortran-equivalent control decisions. | `BACKEND-001` |
| `final_recompute_bridge.cpp` | final section of xstar.f90; xstarcalc.f90; pprint.f90; writespectra*.f90 | Source-lifetime bridge around the accepted fixed-state operator; output ownership follows the final Fortran sequence. | `TERMINAL-001; FINAL-001` |
| `fixed_state_engine.cpp` | calc_hmc_all.f90; calc_hmc_element.f90; calc_hmc_ion.f90; calc_emisab_all.f90; calc_emisab_element.f90; calc_emisab_ion.f90; calc_emis_all.f90; calc_emis_element.f90; calc_emis_ion.f90; ucalc.f90; linopac.f90 | Source-equivalent core with qualified optimized subkernels; ordering/lifetime/IEEE invariants are part of the contract. | `ION-001; MATRIX-001; THERM-001; EMISAB-001; EMIS-001; TYPE50-001` |
| `level_population.cpp` | leqt2f.f90; ludcmp.f90; lubksb.f90; mprove.f90; msolvelucy.f90 | Mathematically/source-order equivalent solver kernel; solution clamping/refinement behavior is part of qualification. | `LEVEL-001; MATRIX-001` |
| `line_emissivity.cpp` | calc_emisab_all.f90; calc_emisab_element.f90; calc_emisab_ion.f90; calc_emis_all.f90; calc_emis_element.f90; calc_emis_ion.f90; binemis.f90; linopac.f90; voigte.f90; huntf.f90; nbinc.f90 | Source-equivalent spectral producer; Type50/profile portions call qualified optimized-equivalent opacity kernels. | `EMISAB-001; EMIS-001; TYPE50-001` |
| `matrix_kernels.cpp` | calc_hmc_ion.f90; ucalc.f90; leqt2f.f90; msolvelucy.f90 | Source-equivalent matrix construction with compact C++ storage; source one-based endpoints and terminal clamps are preserved. | `MATRIX-001; LEVEL-001` |
| `opacity_kernels.cpp` | linopac.f90; voigte.f90; huntf.f90; nbinc.f90 | Optimized-equivalent: AVX2/cursor transformations may change execution shape but preserve accepted line order, active range, boundaries, and per-bin arithmetic. | `TYPE50-001; EMIS-001` |
| `rate_kernels.cpp` | ucalc.f90; calc_hmc_ion.f90; calc_emisab_ion.f90; linopac.f90 | Source-equivalent low-level kernels; unsuffixed REAL literal behavior and one-based matrix endpoints are preserved where observable. | `MATRIX-001; EMISAB-001; TYPE50-001` |
| `source_order_thermal_reducer.hpp` | calc_hmc_all.f90; calc_hmc_element.f90; calc_hmc_ion.f90 | Optimized storage/reduction helper constrained to reproduce the source accumulation ownership/order where roundoff is observable. | `THERM-001` |
| `source_real_energy_grid.hpp` | ener.f90 | Source-exact numeric helper for the accepted energy-grid construction. | `ARCH-001; INPUT-001` |
| `thermal_kernels.cpp` | heatt.f90; dsec.f90; calc_hmc_all.f90 | Source-exact controller arithmetic/order where qualified; fixed-state science evaluations are delegated to calc_hmc-equivalent engines. | `THERM-001; DSEC-001` |
| `type50_dsec_runtime_oracle.h` | linopac.f90 / Type50 ucalc context as exercised inside dsec.f90 | Reference/oracle data, not a Fortran code translation; captures accepted source-observable behavior. | `TYPE50-001; DSEC-001` |
| `type50_manifold_oracle.h` | ucalc.f90 Type50 producer context; calc_hmc_ion.f90; linopac.f90 | Reference/oracle data, not executable source correspondence. | `TYPE50-001; MATRIX-001` |
| `type53_row46_dsec_runtime_oracle.h` | ucalc.f90 Type53 branch; calc_hmc_ion.f90; dsec.f90 | Reference/oracle data, not a Fortran routine translation. | `MATRIX-001; DSEC-001` |
| `xstar_api.cpp` | Scientific boundary: xstar.f90 / xstarcalc.f90; no direct ABI analogue in Fortran. | Productization infrastructure over the Fortran-equivalent scientific boundary; no independent physics. | `BACKEND-001; ARCH-001` |
| `xstar_api.h` | Scientific boundary: xstar.f90 / xstarcalc.f90; no direct ABI analogue in Fortran. | Interface-only productization layer; scientific meaning comes from the mapped engines. | `BACKEND-001; ARCH-001` |
| `xstar_api.hpp` | No direct Fortran routine; wraps the xstar_api.h boundary around xstarcalc-equivalent execution. | Infrastructure only; must be behaviorally transparent to scientific results. | `BACKEND-001` |
| `xstar_atdb_runtime.cpp` | xstarsetup.f90; readtbl.f90; setptrs.f90; rread1.f90 | Source-exact identities/pointers with C++ storage; parameter/default-REAL details are preserved where qualified. | `DB-001; INPUT-001` |
| `xstar_atdb_runtime.hpp` | xstarsetup.f90; readtbl.f90; setptrs.f90; rread1.f90 | Storage/interface representation of the source reader and setptrs relationships. | `DB-001; INPUT-001` |
| `xstar_backend_common.hpp` | No direct Fortran routine; supports calc_hmc/calc_emis-equivalent backend kernels. | C++ infrastructure/storage only. | `BACKEND-001` |
| `xstar_backend_cpp.cpp` | Scientific boundary: xstarcalc.f90; no Fortran backend-dispatch analogue. | Productization dispatch only; selected component science is mapped in its owning files. | `BACKEND-001` |
| `xstar_backend_plugin.h` | No direct Fortran routine. | Infrastructure only; no physics or source arithmetic. | `BACKEND-001` |
| `xstar_backend_python.cpp` | Scientific boundary: xstarcalc.f90; no Fortran backend-dispatch analogue. | Productization bridge; does not redefine scientific equations. | `BACKEND-001` |
| `xstar_constants.h` | constants.f90; selected literal semantics in rread1.f90/trnfrc.f90 and scientific routines | Source-exact or qualification-pinned constants; do not normalize legacy values without science requalification. | `INPUT-001; THERM-001; RADIAL-001` |
| `xstar_element_engine.h` | calc_hmc_element.f90; calc_hmc_ion.f90; calc_ion_rates.f90; levwkelement.f90 | Interface representation of the mapped element fixed-state operator. | `ION-001; LEVEL-001; MATRIX-001` |
| `xstar_engine.cpp` | ucalc.f90 (including Type63); anl1.f90; calc_hmc_ion.f90 | Source-equivalent selected UCalc/anl1 branches and contribution construction; operation order is preserved where qualified. | `MATRIX-001; ION-001` |
| `xstar_final_recompute_bridge.h` | final xstar.f90 sequence; xstarcalc.f90 | Interface-only representation of the source terminal lifetime boundary. | `TERMINAL-001; FINAL-001` |
| `xstar_fixed_state_engine.h` | calc_hmc_all.f90; calc_hmc_element.f90; calc_hmc_ion.f90; calc_emisab_all.f90; calc_emisab_element.f90; calc_emisab_ion.f90; calc_emis_all.f90; calc_emis_element.f90; calc_emis_ion.f90 | Interface/storage representation; source scientific ownership remains in the mapped Fortran operators. | `MATRIX-001; THERM-001; EMISAB-001; EMIS-001` |
| `xstar_production_zone_bridge.h` | xstarcalc.f90 | C ABI wrapper around the xstarcalc-equivalent zone boundary; no independent physics. | `ARCH-001; BACKEND-001` |
| `xstar_python_bridge.h` | No direct Fortran routine; bridges Python control to xstarcalc-equivalent native components. | Infrastructure only; scientific ownership is delegated to mapped kernels. | `BACKEND-001` |
| `xstar_run_state.cpp` | savd.f90; unsavd.f90; rstepr*.f90; final state in xstar.f90 | Object-storage equivalent of source persisted/local lifetime state; publication ownership is intentionally separated from physical solve state. | `STATE-001; RADIAL-001; DETAIL-001; TERMINAL-001` |
| `xstar_run_state.hpp` | savd.f90; unsavd.f90; rstepr*.f90; pprint.f90; writespectra*.f90 | C++ storage model for source lifetimes and publication ownership. | `STATE-001; DETAIL-001; STEP-001; FINAL-001; TERMINAL-001` |
| `xstar_science_fits.cpp` | fstepr.f90; fstepr2.f90; fstepr3.f90; fstepr4.f90; writespectra.f90; writespectra2.f90; writespectra3.f90; writespectra4.f90; pprint.f90 option 12 publication | Source-equivalent publication with explicit source lifetime/REAL(4) writer semantics and accepted Ca/O structural exceptions. | `DETAIL-001; FINAL-001; TERMINAL-001; STEP-001` |
| `xstar_science_fits.hpp` | fstepr*.f90; writespectra*.f90 | Interface-only wrapper for the native publication owner. | `DETAIL-001; FINAL-001` |
| `xstar_spectral_engine.h` | calc_emisab_all.f90; calc_emisab_element.f90; calc_emisab_ion.f90; calc_emis_all.f90; calc_emis_element.f90; calc_emis_ion.f90; binemis.f90; linopac.f90 | Interface representation of source-equivalent spectral producers and qualified Type50 optimization. | `EMISAB-001; EMIS-001; TYPE50-001` |
| `xstar_standalone.cpp` | xstar.f90; xstarcalc.f90; step.f90; trnfrc.f90; trnfrn.f90; stpcut.f90; savd/unsavd.f90; pprint.f90; writespectra*.f90 | Source-equivalent controller with C++ state objects; branch/order/geometry/publication invariants are qualification-pinned. | `ARCH-001; RADIAL-001; STATE-001; STEP-001; FINAL-001; TERMINAL-001` |
| `xstar_standalone_internal.hpp` | No direct Fortran routine. | Infrastructure only; no scientific operation. | `BACKEND-001` |
| `xstar_step_log.cpp` | pprint.f90; nbinc.f90; huntf.f90 | Source-exact/source-equivalent print-option semantics where qualified; numerical science is separated from identity/order/inventory diagnostics. | `STEP-001; TERMINAL-001` |
| `xstar_step_log.hpp` | pprint.f90 | Interface-only wrapper around source-mapped pprint publication. | `STEP-001` |
| `xstar_thermal_engine.h` | heatt.f90; dsec.f90; calc_hmc_all.f90 | Interface representation of the source thermal controller/operator boundary. | `THERM-001; DSEC-001` |

## Verification

```bash
python tools/qualification/check_cpp_source_comments.py
python tools/qualification/check_parity_freeze.py
python tools/qualification/check_source_concordance.py
```

A scientific code change cannot be hidden inside this mechanism: the checker removes only the explicitly marked leading comment block and then hashes the remaining bytes against the frozen baseline.


## Python companion comments

The corresponding production Python modules are annotated in `0.6.55`; see `python_fortran_source_comments.md`. The Python pass uses the same authority hierarchy and records the Manual Chapter 12 / Mendoza et al. Appendix A distinction between ATDB data type (record formula) and rate type (downstream use).

## Archived C++ source-comment provenance

- `historical/cpp/retired_sources/opacity_type50_experiments.cpp` - retired Type50 12.3.26/12.3.27 experimental kernels; not part of the active native build.
- `historical/cpp/retired_sources/xstar_backend_common.cpp` - unused backend scaffold translation unit; production shared helpers remain in `xstar_backend_common.hpp`.
- The active C++ source/header set contains 45 files; no active header was removed in 0.6.57.
