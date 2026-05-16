# CHANGELOG

## v0.3.204 - 2026-05-16

- Added `xstar_atomic.xstar_priority_native_type51_integration` and `examples/94_integrate_xstar_priority_native_type51.py`.
- The new controlled integration audit consumes the v0.3.199 priority matrix-balance products together with the validated v0.3.203 native type-51 parity products. It replaces every matching type-51 compact matrix term touching a selected row, including selected-selected internal terms and selected-external terms contributing to `-A_SE x_E`.
- Added exact capture-key matching with a unique structural fallback, one-use-only native-term accounting, duplicate-key detection, unused-parity-term detection, missing-population detection, and explicit failure when any type-51 insertion is unmatched.
- Reconstructs both the original all-probe system and the hybrid native-type-51/probe-other-family system, then compares aggregated compact entries, captured-population row residuals, external RHS values, matrix rank/conditioning, conditional populations, and linear residuals.
- Readiness requires complete replacement coverage, all selected rows touched by native type 51, a full-rank nonnegative hybrid solve, all selected rows within the population and row-balance tolerances, and negligible population movement relative to the all-probe reference.
- All non-type-51 families remain explicitly probe-backed, `native_priority_subset_matrix_closure_ready` remains false, and the production expanded compact-basis solver is unchanged. The next target is native type-50/type-71 external RHS closure, followed by exact live-radiation type 53 without an empirical approximately 44 factor.
- Removed the machine-specific root `datapath` file from the source/distribution manifest and added it to `.gitignore`. Runtime datapath creation remains supported, but release archives no longer embed a developer-local absolute ATDB path.
- Restored direct raw-record type-50 audit compatibility: rows carrying `data_type=50` and `rate_type=4` are recognized as radiative transitions even when the derived `kind="radiative_decay"` field is absent. This prevents valid explicit radiation-grid pumping audits from falling back to `not_type50_radiative_transition`.

## v0.3.203 - 2026-05-16

- Added `xstar_atomic.rates_type51`, a FITS-independent source-code translation of the XSTAR `ucalc.f90` data-type 51 branch, including the original five-point and general nine-point Burgess--Tully spline paths, the wavelength-dependent BT temperature floor, the ATDB transition-energy convention, detailed balance, and density-scaled `ans1`/`ans2`.
- Added `xstar_atomic.xstar_type51_native_parity` and `examples/93_audit_xstar_type51_native_parity.py`. The audit decodes the selected type-51 ATDB records, compares native excitation/de-excitation rates with the same XSTAR `ucalc` captures, reconstructs all touching compact `ajisi` terms, and aggregates the selected-selected internal compact entries.
- Corrected the interpretation of the legacy full-parity probe field named `xnx`: the instrumentation call passed `xee`, so the physical electron density for collisional rates is `n_e = xpx * xee`. The original CSV field is retained for compatibility and the audit records the corrected semantics explicitly.
- This is a parity/integration gate only. Native type-51 terms are not yet enabled in the production expanded compact-basis solver; type-50/type-71 external closure and the exact live-radiation type-53 implementation remain subsequent steps.

## v0.3.202 - 2026-05-16

- Added `xstar_atomic.xstar_priority_native_readiness` and `examples/92_audit_xstar_priority_native_readiness.py`.
- Consumes the validated v0.3.201 conditional-solve products and, when supplied, the v0.3.199 record-term table to separate selected-block couplings `A_SS` from the external closure term `-A_SE x_E`.
- Ranks each ATDB/XSTAR rate family by its absolute population-weighted influence, assigns a conservative native implementation status, and writes internal-family, external-RHS-family, row-dominance, and staged implementation-plan products.
- For the O VII six-row subsystem, type 51 supplies about 97.77% of the internal population-weighted coupling. Type 50 supplies about 99.06% of the external RHS, type 71 about 0.861%, and type 53 about 0.0795%; the top three external families account for about 99.99937%.
- Defines the minimum native port order as type 51 internal coupling, type 50 plus type 71 external closure, then exact live-radiation type 53. The approximately 44 type-53 discrepancy remains explicitly blocked on a source-equivalent `phint53` implementation and is not corrected empirically.
- Diagnostic/planning release only: no default rate formulas, compact matrix coefficients, RHS/normalization closure, or solver behavior changed.

## v0.3.201 - 2026-05-16

- Added `xstar_atomic.xstar_priority_conditional_solve` and `examples/91_audit_xstar_priority_conditional_solve.py`.
- Partitions the validated selected compact equations as `A_SS x_S + A_SE x_E = 0`, holds the 601 non-selected XSTAR compact populations fixed, and solves the six activated rows from `A_SS x_S = -A_SE x_E`.
- Writes selected matrix entries, external right-hand-side terms, rate-family RHS contributions, singular values, and row-by-row population comparisons.
- For the O VII priority rows `79,80,241,242,244,293`, the row-scaled 6x6 matrix is full rank with condition number about `5.8545`; all six conditional populations agree with the captured XSTAR values within the 0.5% tolerance, with a maximum relative difference of about `3.0341e-3`.
- This remains a probe-derived conditional solve. Native rate assembly, the 119-row active-basis solve, full RHS/normalization closure, and the type-53 approximately 44 scale correction remain future work.

## v0.3.199 - 2026-05-16

- Added `xstar_atomic.xstar_priority_matrix_balance` and `examples/90_audit_xstar_priority_matrix_balance.py`.
- Consumes a validated priority matrix-closure manifest and the captured XSTAR population-closure parity vector, aggregates record-level `ajisi(1,:)` insertions into compact `ipmat2` matrix entries, and evaluates the selected steady-state equations `A x` directly.
- Writes row-balance, rate-family contribution, aggregated compact-matrix entry, record-term, and population-vector products.
- For the O VII six-row priority subset (`79,80,241,242,244,293`), all six rows pass a 0.5% relative residual tolerance against the post-`msolvelucy` population vector; the maximum relative residual is about `1.7471e-3`.
- This is a consistency gate before native assembly. It does not alter the default Python matrix, RHS/normalization closure, native rate formulas, or enable the expanded-basis solve.

## v0.3.198 - 2026-05-16

- Fixed whole-run `latest-per-record` contamination in the priority-subset matrix-closure audit. Raw XSTAR probes contain records for every element, while the reconstructed compact block map describes only the selected element. The audit now filters selected `ucalc` captures to the reconstructed element `jkk_ion` blocks before loading and mapping matrix rows.
- Added `element_jkk_ions`, all-element/selected-element/excluded-record counts, and `element_probe_filter_mode` summary fields.
- Added `xstar_priority_matrix_closure_audit_element_filter_summary.csv` to document included and excluded `jkk_ion` blocks.
- The O VII v0.3.197 latest-per-record output contained 7,432 apparent unmapped endpoints, but all came from unrelated `jkk_ion=1,2,3`; the O-element block map is `jkk_ion=31--36`. These rows are now excluded before endpoint readiness is evaluated.
- Exact `calc_hmc_element` endpoint translation, shared parent-continuum aliases, and non-matrix `ucalc` metadata classification are unchanged. No native solver physics, rate formulas, RHS/normalization closure, or expanded-basis solve changed.

## v0.3.197 - 2026-05-15

- Corrected the priority-subset compact matrix endpoint mapping to follow the actual `calc_hmc_element.f90` assembly rule, `indbe = indbi + ipmat2`, rather than treating every `indbi` value as a level index inside the current ion block.
- Endpoints with `indbi > nlev` are now mapped into their intended adjacent-ion/superlevel compact rows instead of being reported as missing. This directly addresses all 75 false unmapped endpoints in the O VII v0.3.196 rank-73 audit.
- The audit now selects the requested occurrence for all probed ATDB records first, maps every selected Fortran matrix row, and only then filters records/terms touching the activated compact rows. This avoids preselection losses at cross-block endpoints.
- Added explicit classification of non-matrix `ucalc` metadata records. Records such as type-6/rate-13 rows with `idest2=0` intentionally produce no four-row `ajisi/indbi` insertion and no longer falsely fail matrix-manifest readiness.
- Added block-offset and non-matrix-record CSV products plus clearer matrix-record and selected-row readiness counts.
- `examples/89_audit_xstar_priority_matrix_closure.py` now defaults to `--occurrence-rank -1` (`latest-per-record`), which is the appropriate selection for a full-element manifest spanning ion blocks whose records can have unequal occurrence counts. A positive common occurrence rank remains available for controlled scans.
- This remains diagnostic/implementation-manifest infrastructure only. Native rate ports, RHS/normalization closure, and the expanded compact-basis solve are still disabled by default.

## v0.3.196 - 2026-05-15

- Added `xstar_atomic.xstar_priority_matrix_closure` and `examples/89_audit_xstar_priority_matrix_closure.py`.
- Joins the v0.3.195 activated compact-basis rows to the raw XSTAR `ucalc` and `calc_hmc_ion` probes at a common occurrence rank.
- Preserves shared parent-continuum / next-ion-ground aliases as one compact unknown with multiple physical roles.
- Maps the four Fortran `ajisi/indbi` insertions for every selected record into reconstructed compact `ipmat2` row/column coordinates.
- Writes physical-role, selected-record, compact-matrix-term, selected-row, family, unmapped-endpoint, and closure-requirement products.
- This is a source-code-derived implementation manifest only; native formula ports, RHS/normalization closure, and the expanded-basis solve remain disabled by default.

## v0.3.195 - 2026-05-15

- Added `xstar_atomic.xstar_priority_basis_expansion` and `examples/88_expand_xstar_priority_element_basis.py`.
- The new staged expansion consumes the v0.3.194 full-element scaffold and activates the smallest population-ranked subset of missing compact `ipmat2` rows needed for a requested solved-population coverage.
- Shared parent-continuum / next-ion-ground rows remain one compact unknown with explicit multiple physical roles; they are not duplicated as independent source rows.
- The audit writes an activation manifest, expanded compact-basis table, alias map, per-ion-block closure requirements, deferred-row table, JSON, and Markdown report.
- For the O VII solve-call 219 scaffold, the default 99.9999% target activates six rows (`293,241,244,242,80,79`) across `nionp=4,5,6`, raising represented XSTAR solved-population coverage from `0.991904690445624` to `0.9999999463123856`.
- This is basis-instantiation and closure-planning infrastructure only. Native matrix terms, RHS/normalization closure, and the full-element solve are still not enabled by default.

## v0.3.194 - 2026-05-15

- Added `xstar_atomic.xstar_full_element_basis` and `examples/87_build_xstar_full_element_basis_scaffold.py`.
- Consumes the v0.3.193 element-basis remap audit and creates one explicit Python-side scaffold row for every compact XSTAR `ipmat2` row.
- Existing Python rows retain physical mappings and shared parent-continuum aliases; unrepresented rows receive deterministic placeholder global indices.
- Writes missing-row priorities, ion-block coverage, and cumulative population-closure tiers so the native full-element implementation can be staged by physical importance.
- The scaffold is preparatory only: no default solver matrix, native rates, or closure equations are changed.

## v0.3.193 - 2026-05-15

- Added `xstar_atomic.xstar_element_basis_remap`.
- Added `examples/86_audit_xstar_element_basis_remap.py`.
- Reconstructs each selected XSTAR element solve as unique compact `ipmat2` rows while retaining duplicate parent-continuum/final-slot roles as explicit aliases.
- Remaps preserved Python population rows by `(ion_stage, level_index) -> (nionp_current, local_level_index)` instead of sequential `global_index + 1`.
- Writes exact basis rows, ion blocks, XSTAR role aliases, Python remap rows, Python alias groups, unmapped rows, and unrepresented XSTAR basis rows.
- Optionally joins the paired post-`msolvelucy` population probe to quantify solved-population coverage after the corrected remap.
- Diagnostic only; no default solver physics or matrix assembly changed.

## v0.3.192 - 2026-05-15

- Added `xstar_atomic.xstar_element_basis_probe` and `examples/85_prepare_xstar_element_basis_probe.py`.
- Prepares the next XSTAR debug product, `xstar_element_basis_probe.csv`, to capture the source-code element-basis topology inside `calc_hmc_element.f90`.
- The probe records `basis_solve_call_id`, `row_kind`, `ml_ion`, `klion`, `jkk_ion`, `nlev`, `ion_start_ipmat2`, `ion_start_ipmat`, `local_level_index`, `element_ipmat_index`, `xstar_ipmat2_index`, `nsup`, and `nion` for ion population rows, parent-continuum/shared-link rows, and the final parent-continuum slot.
- Writes conservative free-form Fortran helper plus three insertion snippets: begin of second-pass basis construction, ion-row capture after `x(mm+ipmat2)` mapping and before `ipmat2=ipmat2+nlev-1`, and final-row capture after the final `ipmat2=ipmat2+1`.
- This directly targets the v0.3.191 diagnosis that Python's current `xstar_ipmat2_index` mapping is not source-equivalent to XSTAR's full O-element basis.
- Diagnostic probe infrastructure only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.191 - 2026-05-15

- Added `xstar_atomic.xstar_population_basis_mapping` and `examples/84_diagnose_xstar_population_basis_mapping.py`.
- Consumes the population-closure parity audit products from example 83 and summarizes where the solved XSTAR element population lives in `nion`/`nsup`/`ipmat2` basis blocks.
- Writes basis-block, dominant-unmapped-row, Python-mapping-block, capture-scan, and implementation-plan CSVs.
- The O VII rank-73 diagnosis shows that Python's current `xstar_ipmat2_index` mapping covers only ~2.6e-6 of the selected XSTAR solved population; dominant rows are unmapped XSTAR rows such as ipmat2=575, 335, and 607.
- Diagnostic mapping/topology audit only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.190 - 2026-05-15

- Added `xstar_atomic.xstar_population_closure_parity` and `examples/83_audit_xstar_population_closure_parity.py`.
- Consumes the validated raw `xstar_population_closure_probe.csv`, selects an element occurrence such as O occurrence-rank 73 / latest, and compares the XSTAR before/after `msolvelucy` population vector against preserved Python solver population products.
- Writes capture-scan, overlap-row, and unmapped-XSTAR-row CSVs to quantify whether the current Python local basis covers XSTAR's full element `ipmat2` basis and whether overlapping rows agree.
- Diagnostic population/source closure audit only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.189 - 2026-05-15

- Added paired population-closure probe wrappers `xap_pbefore`/`xap_pafter` with shared `solve_call_id`.
- Added robust legacy validation/pairing for v0.3.188 population-closure CSVs with extra/unpaired captures.
- Added paired capture summary output for pre/post-`msolvelucy` diagnostics.

## v0.3.188 - 2026-05-15

- Added `xstar_atomic.xstar_population_closure_probe` and `examples/82_prepare_xstar_population_closure_probe.py`.
- Prepares the next XSTAR debug product, `xstar_population_closure_probe.csv`, captured in `calc_hmc_element.f90` immediately before and after `msolvelucy`.
- Writes a conservative free-form Fortran helper plus insertion snippets for before/after `msolvelucy`, a schema CSV, patch notes, and a validator for paired before/after population-vector captures.
- This targets the closure layer identified by v0.3.187: adjacent-ion parent coupling, superlevel source/sink closure, RHS/normalization, and pre/post-`msolvelucy` population parity.
- Instrumentation infrastructure only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.187 - 2026-05-15

- Fixed record-level family replay selector aliases so user-facing selectors such as `type50` also match legacy family keys such as `unknown:data_type_50_rate_type_4` / `data_type_50_rate_type_4`.
- Added `xstar_atomic.xstar_population_closure_diagnosis` and `examples/81_diagnose_xstar_population_closure_from_replay_scan.py`.
- The new diagnosis consumes the v0.3.186 family replay scan and decides whether exact-`ucalc` rate replay actually moves the O VII triplet population balance.
- For the current O VII blocker scan, the maximum population-fraction movement is only ~8.36e-7, so the next source-code-equivalent target is population/source closure: adjacent-ion parent coupling, superlevel source/sink closure, RHS/normalization, and pre/post-`msolvelucy` population parity.
- Diagnostic-only release: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.186 - 2026-05-15

Record-level replay family-isolation scan: adds `examples/80_scan_xstar_record_level_ucalc_replay_families.py`, which replays selected record-level families one at a time using Fortran `ucalc` ans1/ans2 branch rates and optionally re-solves each replay matrix. This separates which discrepant families actually move the O VII population balance. Diagnostic scan only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.185 - 2026-05-14

Record-level replay solve reporting update: adds population-based triplet diagnostics, line-triplet availability status, and writes original plus replay normalized solve products. No default physics changed.

## v0.3.184 - 2026-05-14

- Add controlled record-level `ucalc` matrix replay diagnostics.
- New module `xstar_atomic.xstar_record_level_replay` and example `examples/79_audit_xstar_record_level_ucalc_matrix_replay.py`.
- Consumes a selected record-level parity audit (for example O VII occurrence-rank 73), replaces selected Python matrix-row magnitudes with Fortran `ucalc` `ans1`/`ans2` branch values while preserving Python topology/signs, and writes replay matrix terms plus changed-term/family summaries.
- Optional `--run-solver` re-solves the original and replay matrices in environments with the full solver dependencies.
- Diagnostic replay scaffold only: no default solver physics, native rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.183 - 2026-05-14

- Add branch-aware record-level blocker diagnosis for source-code local matrix parity.
- Include type-99 parent/superlevel closure rows using `type99_records` when generic `record` is absent.
- Add per-record branch-ratio columns and recommended next actions for type-53, type-50, type-77, and type-99 closure blockers.

## v0.3.182 - 2026-05-14

- Adds local-state occurrence-rank selection to the record-level XSTAR matrix parity audit.
- `examples/78_audit_xstar_record_level_matrix_parity.py` now supports `--selection occurrence-rank --occurrence-rank N` and `--scan-occurrence-ranks` to diagnose which repeated XSTAR `ucalc` call epoch best corresponds to a preserved Python local matrix.
- This prevents over-interpreting the legacy `latest-per-record` comparison when a full XSTAR probe contains many zones/passes.
- Writes `xstar_record_level_matrix_parity_audit_occurrence_scan.csv` alongside the record and family summaries.
- Diagnostic selection infrastructure only: no solver physics, rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.181 - 2026-05-14

- Add record-level XSTAR local matrix parity audit.
- New module `xstar_atomic.xstar_record_level_parity` reads preserved Python full-global matrix terms plus instrumented XSTAR `xstar_ucalc_record_probe.csv` and `xstar_calc_hmc_ion_matrix_probe.csv`.
- New example `examples/78_audit_xstar_record_level_matrix_parity.py` selects the latest Fortran `ucalc` capture for each Python ATDB record, joins the four `calc_hmc_ion` matrix insertion rows, validates the Fortran `ans1/ans2 -> ajisi` self-consistency, and summarizes Python/Fortran matrix-rate agreement by record and family.
- This is a diagnostic parity-audit layer only; no solver physics, rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.180 - 2026-05-14

- Fixed full-parity probe association between `xstar_ucalc_record_probe.csv` and `xstar_calc_hmc_ion_matrix_probe.csv`.
- The matrix probe now writes the current `ucalc` capture id in `capture_index` and writes the independent matrix-row counter as `matrix_capture_index`.
- The validator now flags legacy v0.3.179-style independent matrix counters with `matrix_capture_index_status=independent_matrix_capture_index_needs_v03180_rerun` instead of reporting misleading one-row matrix groups.
- No solver physics, rate formula, parent/superlevel closure, or empirical triplet tuning changed.

# Changelog

## v0.3.179 - 2026-05-14

- Fixes the full-parity XSTAR probe link step by adding backward-compatible Fortran wrappers `xstar_atomic_probe_ucalc_record` and `xstar_atomic_probe_matrix_row` around the v0.3.178 short helper routines `xap_ucalc` and `xap_mrow`.
- This handles debug builds where `calc_hmc_ion.f90` still contains the older long-name insertion snippets while the helper was regenerated from v0.3.178.
- Instrumentation/link compatibility only: no solver physics, rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.178 - 2026-05-14

- Fixes the full-parity XSTAR probe helper generated in v0.3.176/v0.3.177 for the actual HEASoft/XSTAR `.f90` free-form compilation path.
- Replaces fixed-form continuation snippets with conservative free-form Fortran using trailing `&` continuation.
- Shortens probe helper routine names to `xap_ucalc` and `xap_mrow` to avoid older compiler/name-length surprises.
- Updates the `calc_hmc_ion.f90` insertion snippets to call `xap_ucalc` / `xap_mrow`.
- Adds a generated-helper syntax test using `gfortran` when available.
- No solver physics, rate formulas, parent/superlevel closure, or empirical triplet tuning changed.

## v0.3.177 - 2026-05-14

- Fixed the full local parity probe Fortran helper for HEASoft/XSTAR fixed-form compilation.
- Rewrote generated helper and insertion snippets with fixed-form continuation marks in column 6 instead of free-form `&`.
- No solver physics, rate formulas, or empirical triplet tuning changed.

# Changelog

## v0.3.176 - 2026-05-14

- Added `xstar_atomic.xstar_full_parity_probes` and `examples/77_prepare_xstar_full_parity_probes.py`.
- Added schemas/readers/validators for the two minimum XSTAR debug products needed for source-code-equivalent local matrix parity: `xstar_ucalc_record_probe.csv` and `xstar_calc_hmc_ion_matrix_probe.csv`.
- Added a debug-only Fortran helper plus insertion templates for `calc_hmc_ion.f90` immediately after `ucalc` and after each `ajisi/indbi` matrix insertion row.
- Reports whether the probes are ready for record-level `ucalc ans1..ans6` and matrix insertion parity, including missing columns and four-row insertion checks.
- No default solver physics, rate formulas, or empirical triplet tuning changed.

## v0.3.175 - 2026-05-14

- Added `xstar_atomic.xstar_full_parity_closure` for a source-code-equivalent local closure audit.
- Added `examples/76_audit_xstar_source_code_equivalent_local_closure.py`, which inventories preserved full-global matrix terms by source family and classifies rows as source-code kernel present, proxy/scaffold, mixed proxy/source, or incomplete parent/superlevel closure.
- The audit writes a family summary, required Fortran subroutine inventory, `ucalc` probe schema, `calc_hmc_ion` matrix-insertion probe schema, population probe schema, source snippet audit, Fortran probe notes, JSON, and Markdown.
- Explicitly identifies the blocking gaps for full local matrix/population parity: universal `ucalc` `ans1..ans6` parity, exact `calc_hmc_ion` `ajisi/indbi` row insertion parity, and source-code type-70/type-74/type-99 parent/superlevel closure.
- Audit/probe-planning release only: no solver physics, rate formulas, default matrix assembly, or empirical triplet tuning changed.

## v0.3.174 - 2026-05-14

- Added a controlled type-53 live-bremsam matrix-replacement solve audit: `audit_type53_live_bremsam_matrix_replacement(...)` and `write_type53_live_bremsam_matrix_replacement_audit(...)`.
- Added `examples/75_audit_xstar_type53_live_bremsam_matrix_replacement.py`, which consumes the example-74 live-bremsam `phint53` records, replaces only type-53 photoionization gain/loss rates in a preserved full-global matrix with live `phint53` ans1 values, and re-solves for f/i/r movement.
- The audit writes a replacement matrix, changed-term inventory, solve-comparison CSV, replacement normalized-solve CSV, JSON, and Markdown summary.
- This is a controlled diagnostic mode only; it does not change default solver physics, rate formulas, or empirical triplet tuning.

## v0.3.173 - 2026-05-13

- Added the first type-53 photoionization audit against instrumented XSTAR live rate-grid arrays: `audit_type53_live_bremsam_phint53(...)` and `write_type53_live_bremsam_phint53_audit(...)`.
- Added `examples/74_audit_xstar_type53_live_bremsam_phint53.py`, which reads `xstar_live_rate_grid_probe.csv`, selects a capture state, recomputes the `phint53.f90` photoionization `ans1` side on live `epim(:)` / `bremsam(:)`, and compares against preserved full-global type-53 matrix photoionization rows.
- The uploaded O VII live-rate-grid probe validates as 5 capture states and 4995 total grid points; using the final capture gives 30/30 triplet rows evaluated and 276/277 full rows evaluated.
- The audit finds the current Python matrix type-53 photoionization rows still exceed live-bremsam `phint53` rates by a median factor of about 44, so the previous normalization gap is not due to `xo01_detal4` alone. This points to the current solver matrix using the proxy `xstar-powerlaw` type-53 normalization rather than true XSTAR live `bremsam(:)`.
- Diagnostic/audit release only: no solver physics, rate formulas, or empirical triplet tuning changed.

## v0.3.172 - 2026-05-13

- Fix live-rate-grid probe validation for instrumented XSTAR runs that use placeholder zone/pass metadata for every `bremsmap` capture.
- The probe reader now splits sequential capture blocks when `grid_index` resets, so a CSV with repeated blocks of `grid_index=1..ncn2m` is read as multiple live states rather than one non-monotonic state.
- Adds readiness metadata `probe_block_split_method=nominal_key_then_grid_index_reset_v03172` and `n_probe_states_placeholder_zone_index`.
- No solver physics, rate formulas, or empirical triplet tuning changed.

## v0.3.171 - 2026-05-13

- Live-rate-grid probe instrumentation helper release only; no solver physics, rate formulas, or empirical triplet tuning changed.
- Added `examples/73_prepare_xstar_live_rate_grid_probe_patch.py` to write a standalone Fortran helper and `xstarcalc.f90` insertion block for local/debug XSTAR builds.
- Added `live_rate_grid_probe_fortran_helper(...)`, `live_rate_grid_probe_xstarcalc_insertion_block(...)`, `locate_xstarcalc_bremsmap_site(...)`, and `prepare_live_rate_grid_probe_patch_products(...)`.
- The helper writes `xstar_live_rate_grid_probe.csv` with live `epim(:)`, `bremsam(:)`, and `bremsint(:)` after `bremsmap` and before `calc_hmc_all/calc_hmc_ion`.
- The generated insertion block uses `temperature_K=t*1.d4` and `electron_density_cm^-3=xee*xpx` based on `xstarcalc.f90` units.
- Keeps the default `zone_expression=-1` as a safe placeholder because `xstarcalc.f90` may not have the radial shell index in scope; users can replace it with a real zone variable if available.

## v0.3.170 - 2026-05-13

- Added `xstar_atomic.xstar_live_rate_grid_probe` and `examples/72_prepare_xstar_live_rate_grid_probe.py`.
- Standardizes the live XSTAR rate-grid probe schema for `epim(:)`, `bremsam(:)`, and `bremsint(:)` immediately after `bremsmap` and before `calc_hmc_all`.
- Writes a guarded Fortran probe template and validates optional long-form probe CSVs.
- Diagnostic workflow only: no solver physics, rate formulas, or empirical triplet tuning changed.

- Source-provenance/instrumentation planning cleanup only; no solver physics, rate formulas, or empirical triplet tuning changed.
- Adds `audit_xstar_live_rate_grid_bremsa_path(...)` and `write_xstar_live_rate_grid_bremsa_path_audit(...)` to `xstar_atomic.xstar_source_provenance`.
- Adds `examples/71_audit_xstar_live_rate_grid_bremsa_path.py`, which extends the v0.3.167/v0.3.168 live-bremsa source audit through the XSTAR rate-grid handoff: `trnfrc.f90` high-resolution `bremsa(:)` -> `xstarcalc.f90` `bremsmap(...)` -> reduced-grid `epim(:)/bremsam(:)` -> `calc_hmc_all/calc_hmc_ion` -> `ucalc/phint53`.
- Records that exact type-53 photoionization parity requires exposing or reconstructing the live rate-grid `epim(:), bremsam(:), bremsint(:)` state immediately after `bremsmap`, not another `xo01_detal4` `zrems(1:5)` variant.
- Writes capture-column and instrumentation-step CSV files plus Fortran probe notes for a guarded XSTAR debug dump.
- Keeps Python as the transparent audit/orchestration layer while documenting that production RT-coupled rate/matrix kernels should move to the planned C++ backend after physics parity is complete.

## v0.3.169 - 2026-05-13

- Source-provenance/instrumentation planning cleanup only; no solver physics, rate formulas, or empirical triplet tuning changed.
- Adds `audit_xstar_live_rate_grid_bremsa_path(...)` and `write_xstar_live_rate_grid_bremsa_path_audit(...)` to `xstar_atomic.xstar_source_provenance`.
- Adds `examples/71_audit_xstar_live_rate_grid_bremsa_path.py`, which extends the v0.3.167/v0.3.168 live-bremsa source audit through the XSTAR rate-grid handoff: `trnfrc.f90` high-resolution `bremsa(:)` -> `xstarcalc.f90` `bremsmap(...)` -> reduced-grid `epim(:)/bremsam(:)` -> `calc_hmc_all/calc_hmc_ion` -> `ucalc/phint53`.
- Records that exact type-53 photoionization parity requires exposing or reconstructing the live rate-grid `epim(:), bremsam(:), bremsint(:)` state immediately after `bremsmap`, not another `xo01_detal4` `zrems(1:5)` variant.
- Writes capture-column and instrumentation-step CSV files plus Fortran probe notes for a guarded XSTAR debug dump.
- Keeps Python as the transparent audit/orchestration layer while documenting that production RT-coupled rate/matrix kernels should move to the planned C++ backend after physics parity is complete.

## v0.3.168 - 2026-05-13

- Bugfix/diagnostic cleanup only; no solver physics, rate formulas, or empirical triplet tuning changed.
- Improves `examples/70_audit_xstar_live_bremsa_source_path.py` so `--variant-summary-csv` can be a CSV file, an audit output directory, or an audit `.tar.gz`.
- Reports missing or mis-pointed variant-summary paths explicitly instead of silently printing `best_variant=None`.
- Keeps the source-code conclusion from v0.3.167: XSTAR live `trnfrc.f90` `bremsa(:)` uses `zremsz(:)` and is not written directly to `xo01_detal4.fits`; detail `zrems(1:5)` variants do not recover the live field.

## v0.3.167 - 2026-05-13

- Added a lightweight source-code provenance audit for the XSTAR live `bremsa(:)` radiation field; no solver physics changed.
- New module `xstar_atomic.xstar_source_provenance` with `audit_xstar_live_bremsa_source_path(...)`, `write_xstar_live_bremsa_source_path_audit(...)`, and `summarize_bremsa_variant_gap(...)`.
- New `examples/70_audit_xstar_live_bremsa_source_path.py` scans the XSTAR Fortran source for the `trnfrc.f90` live `bremsa(:)` construction, `phint53.f90` consumption, and the `savd.f90 -> fstepr4.f90` detail-output handoff.
- The audit records that live outward transfer uses `bremsa(jk)=zremsz(jk)*exp(-dpthc(1,jk))/(12.56*r19*r19)`, while `xo01_detal4.fits` is written from `zrems(1:5)`, opacity, emissivities, and continuum depths, not from live `bremsa(:)` or `zremsz(:)`.
- When supplied with the v0.3.166 example-69 variant summary, the audit classifies the O VII result as `source_path_confirmed_detail_variants_do_not_recover_live_bremsa`.
- This supports the next physics target: reconstruct or expose live `zremsz(:)/bremsa(:)` at the same `trnfrc -> xstarcalc -> calc_hmc_ion -> ucalc/phint53` call site, rather than treating `xo01_detal4` continuum columns as exact live-rate inputs.

## v0.3.166 - 2026-05-13

- Bugfix/performance compatibility cleanup for `examples/69_audit_xstar_type53_detail_phint53_bremsa_variants.py`; no solver physics changed.
- Fixed the NumPy 2.x compatibility bug caused by `getattr(np, "trapezoid", np.trapz)`, whose default argument is evaluated eagerly and crashes in environments where `np.trapz` has been removed.
- The vectorized phint53 bremsa-variant audit now uses `np.trapezoid` when available and a small local trapezoidal fallback otherwise.
- Updated audit metadata to `v0.3.166` and added regression coverage for NumPy builds without `np.trapz`.

## v0.3.165 - 2026-05-13

- Performance/diagnostic cleanup for `examples/69_audit_xstar_type53_detail_phint53_bremsa_variants.py`; no solver physics changed.
- Vectorized the type-53 `phint53` bremsa-variant integration by precomputing the cross-section/interpolation kernel once per record and evaluating all selected continuum variants together with array operations.
- Added `--variants`, `--fast`, `--profile`, and `--skip-records-csv` to control expensive diagnostic runs and reduce unnecessary full-sample output.
- Added timing/profile fields (`integration_seconds`, `total_seconds`, `n_vectorized_record_batches`, and `n_evaluated_variant_record_pairs`) to the audit summary and Markdown report.
- Documented that this remains a Python audit prototype; production RT-coupled rate, matrix, and transfer kernels should move to the planned C++ backend after physics parity is fixed.

## v0.3.164 - 2026-05-13

- Added a type-53 detail-continuum bremsa-variant audit to diagnose the v0.3.162/v0.3.163 photoionization normalization gap.
- New `audit_type53_detail_phint53_bremsa_variants(...)` and `write_type53_detail_phint53_bremsa_variants_audit(...)` helpers in `xstar_atomic.xstar_matrix_parity`.
- New `examples/69_audit_xstar_type53_detail_phint53_bremsa_variants.py` command-line audit.
- The audit recomputes type-53 `phint53` photoionization rates using multiple `xo01_detal4.fits` `zrems(1:5)`/attenuation/geometric reconstruction variants and scores whether any available detail-column variant matches the matrix without a free scale.
- It records the source-code distinction that `trnfrc.f90` uses live outward `zremsz(:)` for `bremsa(:)`, while `fstepr4.f90` writes `zrems(1:5,:)` detail columns and not `zremsz`.
- No solver physics or empirical triplet tuning changed.

## v0.3.160 - 2026-05-12

- Added source-code/local handoff parity auditing for XSTAR data type 68 He-like collision terms.
- New `audit_type68_collision_rates(...)` and `write_type68_collision_rate_audit(...)` helpers in `xstar_atomic.xstar_matrix_parity`.
- New `examples/65_audit_xstar_type68_collision_rates.py` command-line audit.
- The audit checks `directional_q_cm3_s * electron_density_cm^-3` against full-global matrix rates, verifies off-diagonal gain / diagonal loss partner placement, and reports triplet-touching coverage.
- No solver physics or empirical triplet tuning changed.

## v0.3.159 - 2026-05-12

- Added a source-code-equivalent type-71 superlevel cascade parity audit.
- Added `audit_type71_cascade_rates(...)` and `write_type71_cascade_rate_audit(...)` to `xstar_atomic.xstar_matrix_parity`.
- Added `examples/64_audit_xstar_type71_cascade_rates.py`, which checks the `calt71.f90` interpolated `Aij` handoff through the `ucalc.f90` type-71 branch into full-global matrix gain/loss terms.
- The audit reports term-level `matrix_rate - 10**type71_calt71_log10_aij` residuals, record-level gain/loss pair closure, partner placement, and triplet-destination/triplet-row coverage.
- O VII v0.3.156 products show 148/148 type-71 matrix terms match `calt71` Aij, 148/148 partner checks match, and 74/74 record-level gain/loss pairs close. With `--triplet-only`, 20/20 triplet-destination terms match and 10/10 record-level pairs close.
- No solver physics, source terms, or empirical triplet tuning changed.

## v0.3.157 - 2026-05-12

- Added `xstar_atomic.xstar_matrix_parity`, a source-code-parity audit layer that reads preserved full-global solver matrix terms and normalized-solve products from example 56.
- Added `examples/62_audit_xstar_local_matrix_parity.py` to rank matrix rate families by data type/source path and report which families feed or drain He-like f/i/r upper levels.
- The audit can ingest the example-61 type-50 detail audit CSV and mark audited type-50 rows as `detail_rate_and_matrix_parity_verified_for_audited_type50_lines` when all matrix rows match.
- This is an audit/triage release only: no empirical triplet tuning and no intentional solver-physics changes.

## v0.3.156 - 2026-05-12

- Propagate same-run detail-output covering fraction (`cfrac`) from `xo01_detal2.fits` depth rows into type-50 matrix assembly.
- Add a fallback `type50_cfrac` path for XSTAR line-escape evaluation when a transition row carries tau0 but not cfrac.
- Refine the detail-state type-50 audit to classify `matrix_cfrac_mismatch` separately from generic rate-evaluator mismatches.
- No intentional change to source terms or non-type-50 solver physics.

## v0.3.155 - 2026-05-12

- Added detail-state type-50 tau handoff from `xo01_detal2.fits` into the `xstar-local-state` solver preset when same-run detail outputs and an ATDB are available.
- Added `xstar_atomic.xstar_detail.build_detail_type50_depth_rows_for_solver(...)` to map `xo01_detal2.fits` line `tau_in`/`tau_out` rows onto ATDB type-50 lower/upper level indices for matrix assembly.
- Added the solver keyword `xstar_type50_depth_lines_csv` and safe `type50_escape_source=xstar-detail-lines` path so the population matrix can use detail-state `tau0(1:2,line)` values without reusing final `xout_lines1.fits` products.
- Improved the detail-state type-50 matrix audit classification: scalar 0.35 escape fallback mismatches are now reported as `matrix_tau0_missing_scalar_escape_proxy` rather than generic `rate_evaluator_mismatch`.
- No type-50 photoexcitation is forced; for `cfrac=1` the `ucalc.f90` photoexcitation branch remains zero.

## v0.3.154 - 2026-05-12

- Added solver-product preservation to `examples/56_reproduce_xstar_local_outputs.py` via `--write-solver-products` and `--solver-output-root`.
- Preserved solver products are written from the in-memory solver result using historical filenames such as `xstar_like_element_solver_full_global_matrix_terms.csv`, plus a products manifest.
- Benchmark comparison CSV/JSON rows now record paths to the preserved full-global matrix terms, normalized-solve comparison, and summary JSON.
- Added automatic matrix-term handoff to `examples/61_audit_xstar_detail_type50_rates.py` via `--benchmark-dir` / `--benchmark-comparisons-csv`.
- The detail-state type-50 audit now compares `ucalc.f90` escaped/photo rates against all matching matrix rows and classifies each residual as `matrix_matches_ucalc_rate`, `rate_evaluator_mismatch`, `matrix_placement_mismatch`, or `no_matching_matrix_term`.
- No solver physics changed.

## v0.3.153 - 2026-05-12

- Added `examples/61_audit_xstar_detail_type50_rates.py`, a row-by-row XSTAR detail-state type-50 audit for He-like triplet lines.
- Added public detail-audit helpers in `xstar_atomic.xstar_detail` for `pescl`, `ptmp1/ptmp2`, XSTAR-style `nbinc`, type-50 `vtherm`, and source-code type-50 rate rows.
- The audit reads `xo01_detal2.fits`/`xo01_detal4.fits`, matches selected O VII f/i/r line rows to ATDB type-50 records when available, computes escaped decay and photoexcitation using `calc_hmc_ion.f90` + `ucalc.f90` formulas, and writes CSV/JSON/Markdown products.
- Optional matrix-term CSV matching adds residual columns without changing solver physics.

## v0.3.152 - 2026-05-12

- Fixed XSTAR detail-state population when `xout_abund1.fits` contains a trailing all-zero sentinel ABUNDANCES row.
- The detail-state reader now carries forward the most recent valid plasma state for final/cumulative detail HDUs whose matching abundance row is a zero sentinel, avoiding misleading `T=0`, `ne=0`, and `logxi=0` summaries.
- Added `abundance_row_source` provenance to zone summaries and field-status outputs.
- Added regression coverage for O VII detail outputs with a zero abundance sentinel row.

## v0.3.151 - 2026-05-12

- Added `xstar_atomic.xstar_detail`, a detail-output reader that populates the Python live-state schema from XSTAR `xo01_detail.fits`, `xo01_detal2.fits`, `xo01_detal4.fits`, and `xout_abund1.fits`.
- Added lightweight BINTABLE parsing to the built-in FITS fallback so XSTAR detail products can be read even when `astropy` is unavailable.
- Added `examples/60_populate_xstar_live_state_from_detail.py` to write per-zone live-state summaries and field-status tables.
- No solver physics changed.

## v0.3.150 - 2026-05-12

- Added `xstar_atomic.xstar_state`, which defines explicit Python live-state containers needed for future XSTAR-output recreation:
  - `XSTARContinuumState` for `epi(:)`, `bremsa(:)`, `bremsint(:)`, and continuum optical depths.
  - `XSTARLineTransferState` for `tau0(1:2,line)`, optional `ptmp1/ptmp2`, and line emissivity/opacity arrays.
  - `XSTARZoneState` for zone-local `T`, `ne`, `cfrac`, `vturbi`, ion fractions, level populations, and heating/cooling maps.
  - `XSTARRunState` for the full run state across radial zones.
- Added `required_live_state_fields()`, `create_initial_xstar_run_state_from_input(...)`, and `write_xstar_state_skeleton(...)`.
- Added `examples/59_create_xstar_live_state_skeleton.py` to write JSON/Markdown/CSV state-schema products from an XSTAR command or `run_xstar.sh`.
- Extended the XSTAR recreation plan JSON with a `live_state_schema` section.
- No full XSTAR recreation or solver physics change yet; this release makes the required internal state explicit and reusable.

## v0.3.149 - 2026-05-11

- Adds the first Python XSTAR-output recreation planning layer.
- New module `xstar_atomic.xstar_run` parses shell-style `xstar key=value` command lines and `run_xstar.sh` files into normalized `XSTARInputParameters`.
- Adds `standard_xstar_output_products()`, `xstar_recreation_plan(...)`, and `write_xstar_recreation_plan(...)` to map `xo01_detail.fits`, `xo01_detal2.fits`, `xo01_detal3.fits`, `xo01_detal4.fits`, `xout_abund1.fits`, `xout_lines1.fits`, `xout_rrc1.fits`, `xout_cont1.fits`, and `xout_spect1.fits` onto the live XSTAR internal state required for source-code-parity recreation.
- Adds `examples/58_plan_xstar_output_recreation.py` and the console entry point `xstar-atomic-plan-xstar-run`.
- This is a planning/audit release only: it does not claim to run the full XSTAR thermal/ionization/radiative-transfer iteration or write exact replacement FITS products yet.

## v0.3.148 - 2026-05-11

- Restored the `xstar-local-state` benchmark preset to the historical examples/51--52 full-global validation branch.
- Stopped treating post-transfer `xout_lines1.fits` line depths as the live `tau0(:,:)` array used by `calc_hmc_ion.f90` in the population matrix.
- Stopped treating final `xout_cont1.fits`/`xout_spect1.fits` spectra as the live local `bremsa(:)` array for the default source-code-parity preset.
- Added `xstar-local-state-experimental-pumping` for explicitly unsafe output-table pumping experiments.
- Added `docs/helike_fortran_python_gap_audit.md` documenting the relevant XSTAR Fortran source path and the remaining exact-parity requirement.
- No empirical triplet scaling was added.

## v0.3.147 - 2026-05-11

- Corrects the first type-50 pumping benchmark path to use the same-run XSTAR `cfrac` parameter from the FITS `PARAMETERS` table when available.
- The `xstar-local-state` preset no longer assumes `cfrac=0`; if `cfrac` cannot be read, it falls back to `cfrac=1` to avoid unphysical maximum pumping.
- Adds `xstar_cfrac` / `xstar_cfrac_source` target metadata and comparison columns, plus `solver_type50_cfrac` diagnostics.
- Keeps type-50 line pumping opt-in through `xstar-line-escape-and-pumping`; no empirical scale factors are added.

## v0.3.146 - 2026-05-11

- Corrects the first type-50 line-pumping benchmark implementation after the v0.3.145 four-ion run showed severe over-pumping from the diagnostic `xstar-powerlaw` continuum.
- Adds same-run XSTAR continuum-spectrum support for the local-state benchmark: `xout_cont1.fits` or `xout_spect1.fits` is converted to a temporary UTF-8 CSV and passed to the full-global solver as an `xstar-output` radiation grid.
- Converts the XSTAR spectrum column (`transmitted` by default) to the internal `bremsa`-like grid using the source-code geometry from `trnfrc.f90`, `bremsa=zremsz*exp(-tau)/(12.56*(r/1e19)^2)`, with the selected local radius from `xout_abund1.fits`.
- Changes the `xstar-local-state` preset so type-50 pumping is evaluated only from the same-run XSTAR output spectrum when available; if no output spectrum is present, the pumping branch is not evaluated instead of falling back to an arbitrary power-law normalization.
- Adds diagnostic columns for the radiation spectrum path, selected column, conversion status, and number of grid points.
- Adds regression tests ensuring `xstar-output` pumping uses the explicit XSTAR output grid and does not silently fall back to the proxy continuum.

## v0.3.145 - 2026-05-11

- Fixes the first `xstar-line-escape-and-pumping` benchmark run, which failed on non-type-50 transitions with `cannot access local variable 'pumping_terms' where it is not associated with a value`.
- Initializes the type-50 pumping diagnostic payload for all bound-bound rows, including raw-A and non-type-50 transitions.
- Keeps type-50 photoexcitation injection opt-in through `xstar-line-escape-and-pumping`; no additional empirical scaling is added.

## v0.3.144 - 2026-05-11

- Added the first source-code-matched type-50 lower-to-upper photoexcitation / line-pumping matrix mode.
- New treatment alias: `xstar-line-escape-and-pumping`.  It keeps the XSTAR line-escape downward branch and injects the upward pumping branch from `ucalc.f90` type 50.
- The pumping rate uses the XSTAR algebra `sigma=0.02655*flin*lambda_cm/vtherm` and `ans1_postswap=sigma*bremsa(nb1)*vtherm/3e10*flinabs(ptmp1)*(1-cfrac)`, with `flinabs=1` as in `flinabs.f90`.
- Added XSTAR-style helpers for type-50 thermal velocity, oscillator-strength recovery from A-values/statistical weights, and `nbinc`-style bin selection on the explicit solver `epi`/`bremsa` grid.
- The `xstar-local-state` benchmark preset now uses `type50_bound_bound_treatment="xstar-line-escape-and-pumping"` with same-run line depths and the explicit diagnostic `xstar-powerlaw` `epi`/`bremsa` grid.
- Added regression tests for injected type-50 pumping matrix terms and the `cfrac=1` suppression path.
- This is the first opt-in physics implementation of type-50 pumping; comparison to the C V/O VII/Mg XI/Ca XIX same-run XSTAR benchmark should be inspected before making it a default predictive mode.

## v0.3.143 - 2026-05-11

- Added a controlled same-run line-depth matrix escape mode for local XSTAR reproduction benchmarks.
- The `xstar-local-state` benchmark preset now passes `type50_escape_source="xstar-reference-lines"`, so matching type-50 triplet transitions can use `depth_inward`/`depth_outward` from the same-run converted `xout_lines1.fits` reference table instead of the scalar 0.35 escape fallback.
- Added internal transition-depth matching by reversed level indices and wavelength, mirroring the XSTAR source-code flow where `calc_hmc_ion.f90` supplies `ptmp1`/`ptmp2` to `ucalc.f90` before type-50 rates are assembled.
- This is a benchmark/reproduction mode, not a final predictive radiation-transfer replacement: true arbitrary-condition reproduction still requires a source-code-matched local radiation field (`epi`, `bremsa(nb1)`, `flinabs`, and `cfrac`) and type-50 line pumping.

## v0.3.142 - 2026-05-11

- Fixed the local-state benchmark triplet-source preference used by `examples/56_reproduce_xstar_local_outputs.py`.
- The `xstar-local-state` solver benchmark now prefers `full_global_xstar_tau0_calc_emis_ion`, matching the historical examples 51--52 validation workflow.
- Kept `full_global_xstar_reference_depth_emit_outward_calc_emis_ion` available as a secondary diagnostic instead of using it as the default benchmark source when both branches are present.
- Added a regression test that fails if the benchmark again silently prefers the reference-depth postprocess branch over the historical tau0 branch.
- No solver physics changed; type-50 photoexcitation remains audit-only.

## v0.3.141 - 2026-05-11

- Added source-code-gap diagnostics to the He-like local-output reproduction benchmark.
- The comparison table now includes solver-to-XSTAR ratios for f/i/r/R/G, a residual-pattern label, same-run resonance-line depth/escape diagnostics, and solver type-50/radiation settings.
- Added `docs/helike_reproduction_source_code_diagnosis.md`, summarizing the XSTAR source-code path (`calc_hmc_ion.f90`, `ucalc.f90` type 50, `calc_emis_ion.f90`, `pescl.f90`) and the current likely gaps: audit-only type-50 photoexcitation, scalar matrix escape fallback, and proxy radiation-field normalization.
- No solver physics changed.  This release improves diagnosis/reporting only.

# Changelog

## v0.3.140 - 2026-05-11

- Fixed `--solver-preset xstar-local-state` in the He-like C/O/Mg/Ca benchmark suite.
- The benchmark no longer passes the binary/ascii FITS table `xout_lines1.fits` directly to the lower-level solver option `xstar_reference_lines_csv`, which expects a converted CSV file.
- When the local-state preset needs same-run XSTAR reference lines, the benchmark now writes the already-loaded selected XSTAR line rows to a temporary UTF-8 CSV and passes that CSV to `solve_element_reference`.
- This removes the `UnicodeDecodeError: 'utf-8' codec can't decode byte 0x80 ...` failure seen when the solver tried to read `xout_lines1.fits` as CSV.
- Added a regression test that verifies the local-state preset passes a `.csv` reference table, not a `.fits` file.
- No solver physics changed; this fixes benchmark plumbing so the real solver-vs-XSTAR residuals can be inspected.

## v0.3.139 - 2026-05-11

- Strengthen the He-like C/O/Mg/Ca same-run benchmark comparison after the API reorganization.
- Add solver and XSTAR diagnostic columns for `R=f/i`, `G=(f+i)/r`, and L2 distance to the exact same-run XSTAR triplet target.
- Record the solver triplet source used in the benchmark comparison so quick workflow summaries are not confused with the source-code-first full-global validation path.
- Prefer full-global / `calc_emis_ion` triplet summaries when present; use `summary.he_like_triplet` only as a fallback and mark it with a warning.
- Add `--solver-preset xstar-local-state` to `examples/56_reproduce_xstar_local_outputs.py`; the preset mirrors the solver settings generated by `examples/51_run_helike_local_state_validation.py`.
- Add `docs/helike_benchmark_diagnosis.md` summarizing the XSTAR source-code path (`calc_hmc_ion.f90`, `ucalc.f90`, `calc_emis_ion.f90`) and why the quick workflow-default solver can reproduce different residuals from the earlier local-state validation workflow.
- No solver physics changed; type-50 photoexcitation/line pumping remains audit-only.

## v0.3.138 - 2026-05-11

- Strengthened XSTAR ATDB path resolution for solver benchmarks and workflow APIs.
- If `XSTAR_ATDB` and `XSTAR_ATDB_FITS` are unset, the resolver now explicitly uses configured `datapath` files and can consult a `datapath` file in the current working tree.
- Added `get_data_paths()` so diagnostics can show all configured datapath candidates.
- Skips stale datapath entries and falls through to the next valid candidate before reporting that no `atdb.fits` was found.
- Source distributions no longer include a machine-specific `datapath` file; users configure it locally with `python -m xstar_atomic.data --set-path /path/to/atdb.fits`.
- No solver physics changed. The C V/O VII/Mg XI/Ca XIX benchmark residuals are unchanged and remain the next physics target.

## v0.3.137 - 2026-05-10

- Fixed the four-ion local-output benchmark solver mode so it accepts the common `XSTAR_ATDB` environment variable in addition to `XSTAR_ATDB_FITS`.
- Treats a blank `--atdb` value, such as `--atdb "$XSTAR_ATDB"` when the shell variable is unset, as not provided and falls back to the configured resolver instead of trying `./atdb.fits`.
- Lets the normal ATDB resolver handle `--atdb`, `XSTAR_ATDB_FITS`, `XSTAR_ATDB`, and saved `datapath` consistently during solver comparisons.
- The example summary now prints solver f/i/r values and comparison warnings, making failed solver setup visible immediately at the terminal.

## v0.3.136 - 2026-05-10

- Fixed the C V / O VII / Mg XI / Ca XIX XSTAR reproduction benchmark solver-comparison extraction.
- `examples/56_reproduce_xstar_local_outputs.py --run-solver` now reads the current solver's `summary["he_like_triplet"]` result and fills `solver_f_fraction`, `solver_i_fraction`, and `solver_r_fraction` when available.
- The benchmark no longer reports `solver_compared` when solver triplet fractions are missing; it reports `solver_no_triplet_values` with an explicit warning instead.
- Added regression tests for solver-summary triplet extraction and missing-triplet status handling.
- No solver physics changed; this release only fixes benchmark reporting/extraction.

## v0.3.135 - 2026-05-10

- Added a built-in standard C V / O VII / Mg XI / Ca XIX benchmark suite for `examples/56_reproduce_xstar_local_outputs.py` via `--standard-helike-suite --xstar-runs-root xstar_runs`.
- Added `default_helike_benchmark_cases(...)` and `write_default_helike_cases_csv(...)` to create the canonical four-ion case table programmatically or as an editable CSV.
- Improved the missing `--cases-csv` error message with a copy-pasteable case-table recipe and a pointer to `--standard-helike-suite`.
- Updated README, examples README, Markdown/LaTeX/Sphinx user-guide examples for the new one-command four-ion benchmark workflow.
- No solver physics changed; this remains exact XSTAR target extraction plus optional residual reporting.

## v0.3.134 - 2026-05-10

- Added `src/xstar_atomic/benchmark.py`, a same-run XSTAR local-output reproduction layer for C V, O VII, Mg XI, and Ca XIX benchmarks.
- Added `XSTARLocalTarget` and `XSTARBenchmarkComparison` result objects that keep the exact local state from `xout_abund1.fits` and exact He-like triplet target from `xout_lines1.fits` separate from any solver residual.
- Added public helpers `build_xstar_local_target(...)`, `reproduce_xstar_run(...)`, `run_xstar_benchmark_suite(...)`, `write_xstar_benchmark_outputs(...)`, and `write_xstar_benchmark_suite(...)`. These are exported at the top level and through `xstar_atomic.validate`/`XSTARAtomic.validate`.
- Added `examples/56_reproduce_xstar_local_outputs.py`, a CLI wrapper that writes local-state, triplet-target, selected-line, comparison, JSON, and Markdown benchmark products.
- Updated Markdown, LaTeX, and Sphinx user guides with the new same-run reproduction benchmark API and CLI example.
- Updated `examples/README.md` and the example-to-source migration map for example 56.
- No solver physics changed; type-50 photoexcitation remains audit-only. This release establishes exact XSTAR-output targets before further solver corrections.

## v0.3.133 - 2026-05-10

- Expanded `docs/user_guide.md`, `docs/user_guide.tex`, and `docs/sphinx/source/user_guide.rst` with function-by-function examples for the top-level workflow API, context classes, `RateEvaluation`, audit-only type-50 evaluation, and expert object namespaces.
- Fixed the LaTeX `Examples and source-module migration` table layout by using breakable path-style entries so long example filenames and API names no longer overlap.
- Updated documentation regression tests so the API examples are checked across Markdown, LaTeX, and Sphinx sources.
- No solver physics changed; type-50 photoexcitation / line pumping remains audit-only.

## v0.3.132 - 2026-05-10

- Expanded and clarified the public API documentation in `docs/user_guide.md` with a canonical workflow-first API section, a top-level function summary table, expert namespace examples, public namespace-module examples, and explicit notes about prototype/not-yet-final physics APIs.
- Rewrote `docs/sphinx/source/user_guide.rst` so the Sphinx user guide now mirrors the Markdown/LaTeX organization instead of remaining an older CLI-focused page.
- Expanded `docs/sphinx/source/api.rst` to include the workflow-first API (`xstar_atomic.workflow`), public namespaces (`rates`, `matrix`, `solve`, `validate`, `runs`), context objects, type-50 evaluator, and audit module.
- Expanded `docs/user_guide.tex` with the same workflow-first and expert API material and retained the LaTeX table of contents.
- Added documentation regression tests requiring the new public API names to appear in Markdown, LaTeX, and Sphinx docs.
- No solver physics changed; type-50 photoexcitation remains audit-only and is not injected into the population matrix.

## v0.3.131 - 2026-05-10

- Added the first workflow-first module-level public API layer inspired by the earlier `chianti-tools` review:
  - `open_database(...)`
  - `get_levels(...)`, `get_lines(...)`, `get_wavelengths(...)`, `get_energies(...)`
  - `match_line(...)`, `match_lines(...)`
  - `get_collisions(...)`, `get_photoionization(...)`, `get_recombination(...)`
  - `calc_emissivity(...)`, `calc_rate(...)`, `calc_triplet(...)`
  - `solve_populations(...)`, `build_matrix(...)` wrappers around the current solver workflow.
- Added `XSTARContext` plus `context_from_values(...)` and `context_from_xstar_run(...)` for lightweight local XSTAR contexts selected from `xout_abund1.fits`.
- Added namespace-style expert API attributes on `XSTARAtomic`:
  - `db.context.from_values(...)`, `db.context.from_xstar_run(...)`
  - `db.rates.type50(...)`
  - `db.audit.type50_line_pumping(...)`
  - `db.matrix.build_ion(...)`
  - `db.solve.ion(...)`
  - `db.validate.compare_xstar_run(...)`.
- Added public namespace modules `xstar_atomic.rates`, `xstar_atomic.solve`, `xstar_atomic.matrix`, `xstar_atomic.validate`, and `xstar_atomic.runs` as stable import locations for future API growth.
- Expanded Markdown and LaTeX docs with the new workflow-first API calls and expert namespace examples.
- Added API tests for public workflow functions and namespace modules.
- No solver physics changed; type-50 photoexcitation remains audit-only and is not injected into the population matrix.

## v0.3.130 - 2026-05-10

- Expanded `examples/README.md` so every example script has its own section with a copy-pasteable `bash` command block.
- Preserved the relevance-based example organization while replacing compact inline table commands with more readable per-example command blocks.
- Added documentation tests that verify all `examples/*.py` files are listed in `examples/README.md` and have a corresponding `bash` command block.
- No solver physics changed; type-50 photoexcitation remains audit-only.

## v0.3.129 - 2026-05-10

- Added `examples/README.md`, organizing all example scripts by workflow/relevance and giving a minimal command for each example. The README also adds recommended learning paths for new users, decoder development, emissivity/export work, O VII triplet development, full-global XSTAR validation, and Mg/Ca validation.
- Expanded `docs/user_guide.md` with a table of contents and a new public API cookbook covering database setup, line/level queries, collision and recombination products, local context objects, the audit-only type-50 evaluator, high-level `XSTARAtomic` convenience methods, source-code audits, and export workflows.
- Expanded `docs/user_guide.tex` with `\tableofcontents` after `\maketitle` and the same public API cookbook examples as the Markdown guide.
- Updated the package README and manifest so the examples README is discoverable and included in source distributions.
- No solver physics changed; type-50 photoexcitation remains audit-only.

## v0.3.128 - 2026-05-10

- Added `src/xstar_atomic/context.py` with public `LocalPlasmaState`, `RadiationField`, and `EscapeContext` containers for local XSTAR plasma, radiation, and escape/geometry state.
- Added `src/xstar_atomic/rates_type50.py` with the `RateEvaluation` result class and audit-only `evaluate_type50_bound_bound(...)` evaluator for the XSTAR `ucalc.f90` type-50 bound-bound radiative branch. The evaluator records pre-swap escaped decay, pre-swap photoexcitation, post-swap lower-to-upper photoexcitation, post-swap upper-to-lower escaped decay, sigma, `bremsa(nb1)`, `flinabs(ptmp1)`, `cfrac`, and `ptmp` terms when available.
- Added `src/xstar_atomic/audit.py` with reusable `type50_line_pumping(...)` audit workflow and `Type50LinePumpingAudit` return object.
- Converted `examples/55_audit_helike_type50_line_pumping.py` into a thin CLI wrapper around `xstar_atomic.audit.type50_line_pumping(...)`, preserving the previous command-line interface while making the audit callable as a public API.
- Added `XSTARAtomic.type50_rate(...)` and `XSTARAtomic.audit_type50_line_pumping(...)` convenience methods.
- Reorganized `docs/user_guide.md` and `docs/user_guide.tex` into a workflow-first structure similar to `chianti-tools`: installation/data setup, quick start, database access, context objects, source-code-aligned rate evaluators, matrix/solver workflows, XSTAR-output validation, audit workflows, example-to-source migration, tests, and roadmap.
- Added `docs/example_to_source_api_map.md`, identifying which example scripts should migrate into stable source modules as the API hardens.
- No solver physics changed; the type-50 line-pumping/photoexcitation implementation remains audit-only and no empirical triplet scale fitting was added.

## v0.3.127 - 2026-05-10

- Added `examples/55_audit_helike_type50_line_pumping.py`, a source-code-first audit for the missing XSTAR type-50 bound-bound photoexcitation / line-pumping path after all-ion local-state validation.
- The new audit records the XSTAR `ucalc.f90` type-50 source-code formula for the upward photoexcitation term, identifies the required radiation-field inputs (`epi`, `bremsa`, `flinabs`, `cfrac`, thermal velocity, and escape probabilities), and reports that the current `xstar-line-escape` population matrix has zero explicit photoexcitation into `1s2p 1P1`.
- The audit combines local-state case metadata, same-run XSTAR triplet targets, comparison summaries, and full-global matrix terms, but does not fit or apply any empirical triplet scale.
- No solver physics changed; this release documents the next source-code implementation target: port XSTAR `ucalc.f90` type-50 `ans2` line-pumping using the correct local radiation normalization before interpreting collision-rate scale residuals.

## v0.3.126 - 2026-05-10

- Added `examples/54_audit_helike_resonance_population_flux.py`, a source-code-first diagnostic that combines solved population fractions with full-global matrix terms to compute population-weighted feed and loss paths for the He-like resonance upper level `1s2p 1P1`.
- The new audit writes `helike_resonance_population_flux_summary.csv`, `helike_resonance_population_flux_detail.csv`, `helike_resonance_population_flux_audit.md`, and `helike_resonance_population_flux_audit.json`.
- The audit separates direct ground-to-resonance feed, collisional cascade/mixing feed, radiative cascade feed, explicit photoexcitation feed, and resonance losses. It also records a clearly marked linearized equivalent feed diagnostic but does not apply or fit any scale factor.
- On the user's all-ion local-state comparison, all four ions still have low resonance fractions and zero population-weighted explicit photoexcitation into `1s2p 1P1`, reinforcing that the next source-code target should be XSTAR bound-bound line pumping / local radiation normalization before any collision-rate scale interpretation.
- No solver physics changed and no empirical triplet scale fitting was added.

## v0.3.125 - 2026-05-09

- Added `examples/53_audit_helike_resonance_deficit.py`, a diagnostic-only audit for the common local-state residual in C V, O VII, Mg XI, and Ca XIX.
- The new audit reads `helike_local_state_cases.csv`, per-ion `xstar_detail_population_comparison_summary.json` files, same-run XSTAR triplet line CSVs, resonance-collisional-feed audits, radiation-context audits, and full-global matrix terms.
- It reports the resonance-fraction deficit, solver/target f/i/r residuals, XSTAR line depths, direct resonance-collisional feed sums by data type, diagnostic radiation-field provenance, and whether any nonzero photoexcitation terms into `1s2p 1P1` are present in the assembled matrix.
- Applied to the user’s all-ion local-state run, all four ions have solver `f` high, solver `r` low, and zero explicit nonzero photoexcitation into the resonance upper level in the assembled matrix audit. This points next to XSTAR line-pumping/radiation normalization and direct ground-to-resonance feeding, not per-ion triplet scale fitting.
- No solver physics changed and no empirical triplet scale fitting was added.

## v0.3.124 - 2026-05-09

- Fixed the default output label in `examples/51_run_helike_local_state_validation.py` so newly generated local-state solver directories use `v03124` instead of the stale `v03122` label.
- Added `examples/52_summarize_helike_local_state_comparison.py`, a diagnostic-only summary tool that combines `helike_local_state_cases.csv` with per-ion `xstar_detail_population_comparison_summary.json` files.
- The new summary reports local XSTAR `T/ne/log xi`, solver f/i/r, same-run XSTAR f/i/r, residuals, `R`, `G`, `L2`, and the common residual pattern across C V, O VII, Mg XI, and Ca XIX.
- Applied to the user’s v0.3.123 all-ion local-state output, the common residual is solver `f` high and solver `r` low for all four ions. This points to direct ground/resonance feeding and radiation/line-pumping normalization before any row-level type-56/type-63/type-68/type-69 rate interpretation.
- No solver physics changed and no empirical triplet scale fitting was added.

## v0.3.123 - 2026-05-09

- Fixed generated He-like local-state validation shell scripts from `examples/51_run_helike_local_state_validation.py`.
- Commands are now written with shell-quoted tokens, so ion names containing spaces, especially `C V` and `O VII`, are passed correctly to `python -m xstar_atomic.xstar_outputs --ion ...`.
- This fixes failures like `xstar_outputs.py: error: unrecognized arguments: V` in `compare_helike_local_state_solvers.sh`.
- No solver physics changed; no empirical triplet scale fitting was added.

## v0.3.122 - 2026-05-09

- Fixed `examples/51_run_helike_local_state_validation.py` density selection in `--selection-mode max` runs. When `--target-electron-density` and `--nearest-density` are supplied, the script now constrains to the closest available local XSTAR electron density before choosing the maximum He-like fraction. This prevents mixed-density trees from selecting ne≈1 cm^-3 C V/O VII/Ca XIX states when the requested validation target is ne≈1e8 cm^-3.
- The local-state comparison target now prefers the matched XSTAR run directory: if a selected `xout_abund1.fits` has a sibling `xout_lines1.fits`, the script uses a same-directory triplet CSV when present or auto-generates one under `auto_xstar_triplet_targets/`. Generic/preconverted target CSVs are now only fallback targets.
- Added provenance columns `target_csv_source` and `target_csv_source_policy` to clarify whether the comparison uses same-run XSTAR lines or a fallback target search.
- No solver physics changed and no empirical triplet scale fitting was added.
- Validation: `compileall` passed; selected pytest suite passed with 10 passed and 3 skipped.

## v0.3.121 - 2026-05-09

- Improved `examples/51_run_helike_local_state_validation.py` for He-like validation trees that contain C/O density-only runs such as `helike_type69/c5_ne1e8` and `helike_type69/o7_ne1e8`.
- The driver now records available local `log xi` and electron-density values when a requested `--log-xi` / density filter excludes an ion-specific XSTAR run. This makes it clear when C V/O VII are present but not at the requested `log xi=3` Mg/Ca condition.
- Added automatic triplet-target CSV creation from the matched XSTAR `xout_lines1.fits` when a preconverted `xstar_*_triplet_lines.csv` is absent. Generated CSVs are written under `auto_xstar_triplet_targets/`, and the compare script includes the conversion command before running `examples/43_compare_xstar_detail_populations.py`.
- This supports source-code-first local-state validation for C V, O VII, Mg XI, and Ca XIX from the same `xstar_runs` tree without requiring separate manual conversion steps.
- No solver physics changed and no empirical triplet scale fitting was added.

## v0.3.120 - 2026-05-09

- Improved `examples/51_run_helike_local_state_validation.py` for practical local-state validation against XSTAR `xout_abund1.fits` products.
- Added `--target-electron-density`, `--electron-density-tolerance-dex`, and `--nearest-density` so a grid containing multiple XSTAR density runs can be reduced to the requested local density, e.g. `ne≈1e8 cm^-3`, before generating solver commands.
- De-duplicated repeated `xout_abund1.fits` discoveries that arise when the same case appears in both copied and nested `mg_ca_triplet_targets` layouts.
- Stopped using unrelated Mg/Ca `xout_abund1.fits` tables as C V/O VII local states when no matching C/O XSTAR run directory is present. C/O are now marked as missing local state unless matching `c5`/`o7` XSTAR `xout_abund1.fits` cases exist.
- No solver physics changes and no empirical triplet scale fitting.

## v0.3.119 - 2026-05-09

- Added `examples/51_run_helike_local_state_validation.py`, a source-code-first driver that reads XSTAR `xout_abund1.fits` local-zone states and prepares/runs He-like solver comparisons at those local `T`, `ne`, and `log xi` conditions for C V, O VII, Mg XI, and Ca XIX.
- The new driver writes `helike_local_state_cases.csv`, `helike_local_state_zone_candidates.csv`, `helike_local_state_summary.json`, `helike_local_state_validation_plan.md`, and reproducible shell scripts for solver and comparison commands.
- Supports `--selection-mode grid|max` and `--log-xi` for either full local-state grids or a single selected log-xi comparison.
- Keeps the source-code-first policy: no empirical triplet scale fitting and no default solver-physics changes. The generated commands use XSTAR local `T` and `ne`; radiation normalization remains explicitly marked as not yet tied to XSTAR xi/transfer.
- On the supplied `xstar_runs` Mg/Ca grid, the driver finds usable local-state cases for Mg XI and Ca XIX but reports C V and O VII as missing/nonzero local-state targets in that specific run tree, because the Mg/Ca `xout_abund1.fits` files have zero C V and O VII He-like fractions.

# v0.3.118 - 2026-05-09

- Added a lightweight FITS ASCII-table fallback reader in `xstar_atomic.xstar_outputs` for XSTAR products such as `xout_abund1.fits`, so Mg/Ca local-state audits can read `ABUNDANCES`, `COLUMNS`, `HEATING`, and `COOLING` extensions even when `astropy` is unavailable.
- Updated `examples/50_mg_ca_xstar_local_state_audit.py` to use the shared XSTAR output reader and to find `xout_abund1.fits` in both `xstar_runs/mg_ca_triplet_targets/...` and `mg_ca_triplet_targets/...` layouts.
- Corrected the Mg/Ca local-state audit interpretation of XSTAR `ion_parameter`: for the standard Mg/Ca target grid this is the printed log10(xi) run value. The audit now writes `xstar_ion_parameter_raw`, `xstar_log_xi_local`, and derived linear `xstar_xi_erg_cm_s^-1`.
- Verified against the supplied `xstar_runs` archive: all 12 Mg/Ca target-grid cases now pair with `xout_abund1.fits`; explicit Mg XI/Ca XIX xi=3 solver outputs also pair successfully.
- No default solver physics changed; no empirical triplet scale fitting was added.

# v0.3.117 - 2026-05-09

- Improved `examples/50_mg_ca_xstar_local_state_audit.py` discovery for local Mg XI / Ca XIX validation.
- Added repeated `--solver-out-dir` support so one or more solver-output directories can be audited even when `--results-root` points only to an XSTAR target tree or an empty/nonexistent staging directory.
- Added a conservative current-working-directory fallback when `--results-root` has no Mg/Ca solver cases, preventing misleading `cases=0` results during local two-case Mg/Ca tests.
- Added provenance fields to the local-state audit summary: `n_discovered_solver_dirs`, `results_root`, `xstar_runs_root`, `cwd_fallback_enabled`, and zero-case guidance.
- No solver physics changes and no empirical triplet scale fitting. The Mg/Ca prerequisite remains preserving matching XSTAR `xout_abund1.fits` files before interpreting f/i/r, R, or G.

# v0.3.116 - 2026-05-09

XSTAR-local-state audit for Mg XI / Ca XIX validation.

- Adds `examples/50_mg_ca_xstar_local_state_audit.py`, a source-code-first diagnostic that checks whether each Mg XI / Ca XIX solver comparison has the matching XSTAR local gas state before interpreting f/i/r, R, or G.
- The audit searches for the matching XSTAR triplet target CSV and `xout_abund1.fits`, reads the XSTAR `ABUNDANCES` extension when present, and selects the first comparison zone by maximum He-like ion fraction (`Mg_XI` or `Ca_XIX`).
- The selected-zone table reports XSTAR radius, thickness, ionization parameter `xi`, `x_e`, `n_p`, inferred electron density, pressure, temperature in K, heat-balance error, and the He-like ion fraction.
- The audit compares these XSTAR local values against the solver assumptions (`temperature_K`, `electron_density_cm^-3`, `xstar-powerlaw` diagnostic bremsa normalization), and writes recommended rerun conditions when `xout_abund1.fits` is available.
- Adds generic FITS-table helpers in `xstar_atomic.xstar_outputs`: `list_fits_hdus`, `read_fits_table`, and `read_xout_abundances`.
- Updates `examples/47_prepare_mg_ca_xstar_triplet_targets.py` documentation so future Mg/Ca XSTAR runs explicitly preserve `xout_abund1.fits`; this file is required for local-zone validation.
- No triplet scale fitting and no default solver-physics change. The Mg/Ca mismatch should now be addressed by matching XSTAR local zone T/ne/xi and radiation normalization before row-level type-56/type-63/type-68/type-69 rate comparisons.

Validation: `python -m compileall -q src examples tests` passed; selected pytest suite passed in the container.

# v0.3.115 - 2026-05-09

Source-code-first Mg XI / Ca XIX audit bookkeeping update.

- Propagates collision-evaluator diagnostics from `build_collision_rates_for_T()` through `assemble_rate_matrix()` into the transition log, and then into `xstar_like_element_solver_global_bound_bound_matrix_terms.csv` / `xstar_like_element_solver_full_global_matrix_terms.csv`.
- Future Mg XI/Ca XIX solver outputs now retain row-level source-code audit fields for type-63 rows, including the XSTAR record-order mode, ans1/ans2 swap flag, forward/reverse coefficients, legacy energy-order comparison rates, and same-n l-mixing diagnostics.
- Future type-67/type-68 matrix products retain the XSTAR effective-temperature floor diagnostics added in v0.3.113.
- Updates `examples/49_mg_ca_triplet_source_path_audit.py` so it can audit either v0.3.111 or newer Mg/Ca output directories, not only `*v03111*` names.
- Adds explicit XSTAR source-branch mapping for type-56 tabulated effective collision strengths. This is important for Ca XIX, where many triplet-feeding bound-bound collisional rows are `linear_logT_type56` rather than type-63.
- Infers data type from `source_method` when the matrix row does not carry an explicit `data_type` column, so existing v0.3.114 outputs can still be classified as type 56/63/68/69 in the source-path audit.
- No default physics changed. `--resonance-collisional-feed-scale` remains diagnostic-only and defaults to 1.

Validation: `python -m compileall -q src examples tests` passed; selected pytest suite passed in the container.

# v0.3.114 - 2026-05-09

- Source-code-first type-63 alignment: n-changing type-63 collisions now follow the XSTAR `ucalc.f90` record-order convention. The evaluator uses ATDB `idest1/idest2` order for the `anl1/erc` branch, applies the literal `aa1` selector, applies the XSTAR `ans1/ans2` swap when `(nf.gt.ni).or.(lf.gt.li)`, and then maps the forward/reverse rates back to lower->upper and upper->lower coefficients for the Python matrix.
- The previous energy-ordered branch is retained as an audit-only diagnostic and written as `type63_energy_order_*` columns so Mg XI/Ca XIX and C V rows can be compared directly.
- Collision summaries now retain type-63 record-order endpoint labels, quantum numbers, statistical weights, and energies (`type63_initial_*`, `type63_final_*`) to support row-level source-code comparison against XSTAR debug/detail output.
- No empirical scale fitting or default diagnostic scale changes were added. The C V `--resonance-collisional-feed-scale` option remains diagnostic-only and defaults to 1.

# v0.3.113 - 2026-05-08

- Source-code alignment update for He-like type-67/type-68 collisions. The Python `calt67_upsilon` and `calt68_upsilon` evaluators now apply the same `ucalc.f90` temperature floor used by XSTAR before calling `calt67.f90`/`calt68.f90`: `temp = max(T, 2.8777e6 / wavelength_A)`.
- The collision evaluator now reports `xstar_calt67_68_effective_temperature_K` and `xstar_calt67_68_temperature_floor_applied` for type-67/type-68 rows, so Mg XI/Ca XIX audits can verify whether the source-code floor matters for each transition.
- Added `examples/49_mg_ca_triplet_source_path_audit.py`, a source-code-first Mg XI/Ca XIX triplet-path audit. It maps triplet-feeding rows to XSTAR branches (`ucalc` type 63/67/68/69 and type-50 escape), writes detail/summary CSVs, and explicitly avoids empirical scale fitting.
- No default diagnostic scale changes. `--resonance-collisional-feed-scale` remains diagnostic-only and defaults to 1.

Validation: `compileall` passed; selected pytest suite passed with expected skips.

## v0.3.112 - 2026-05-08

- Added `examples/48_sourcecode_first_mg_ca_validation.py`, a source-code-first Mg XI / Ca XIX validation audit.
- The new diagnostic compares solver outputs with XSTAR triplet CSV targets across the log-xi grid, flags xi-invariant solver states, and writes source-method audit rows tied to XSTAR Fortran files (`calc_hmc_element.f90`, `ucalc.f90`, `calt69.f90`, `amcrs.f90`, `velimp.f90`, `calc_emis_ion.f90`).
- This release intentionally does not add or search for empirical best-fit scale factors for Mg XI or Ca XIX. It records that XSTAR source-code alignment of radiation normalization and type-63/type-69 row-level rates should precede any scale interpretation.
- No default solver physics changed.

# v0.3.111 - 2026-05-08

- Added `examples/47_prepare_mg_ca_xstar_triplet_targets.py`, a targeted Mg XI/Ca XIX XSTAR target-plan helper. It writes reproducible XSTAR run scripts, `xout_lines1.fits` conversion scripts, a `xstar_runs/mg_ca_triplet_target_plan.csv` summary, and `xstar_runs/README_mg_ca_triplet_targets.md` containing solver and comparison commands.
- Default Mg/Ca target plans use `ne=1e8 cm^-3` and a log-xi grid `1.5,2.0,2.5,3.0,3.5,4.0`, because high-Z He-like ions may be absent at the C/O reference ionization parameter.
- Updated `examples/43_compare_xstar_detail_populations.py` so any supplied `--xstar-triplet-lines-csv` is used to derive the target f/i/r for the normal `full_global_xstar_tau0_calc_emis_ion` comparison. This prevents Mg XI/Ca XIX validation from silently comparing against the built-in C V target.
- No default population-matrix physics changed. The C V resonance-collisional-feed scale remains diagnostic-only and defaults to 1.

Validation: `compileall` passed; selected pytest suite passed with expected skips.

# v0.3.110 - 2026-05-08

- Fixed the internal `--resonance-collisional-feed-scale-scan` context. v0.3.109 rebuilt the scanned matrix with the requested resonance-feed scale but solved it with the default `explicit-current` topology and no ion-fraction closure, so `xstar_like_element_solver_resonance_collisional_feed_scale_scan.csv` could disagree with the top-level printed `full_global_xstar_tau0_calc_emis_ion` result.
- The scan now passes through the same `--full-global-topology`, `--ion-fraction-closure`, calc-ion-rates audit rows, temperature, and electron density used by the primary full-global solve.
- Added `full_global_topology` and `ion_fraction_closure` columns to the resonance-collisional feed scale scan output for provenance.
- No default physics changes: `--resonance-collisional-feed-scale` still defaults to 1 and remains diagnostic unless explicitly changed.

Validation: `compileall` passed.

# v0.3.109 - 2026-05-08

- Added `xstar_like_element_solver_resonance_collisional_feed_sourcecode_audit.csv`, a source-code-oriented diagnostic for the C V / He-like resonance upper `1s2p 1P1` collisional-feed rows.
- The source-code audit records the type-63/type-69 `ucalc`/`calt*` formula path, source/helper Fortran files, statistical weights, global-index energy gaps, best diagnostic scan scale, and the inferred missing feed rate implied by the C V scale scan.
- Corrected the internal `--resonance-collisional-feed-scale-scan` summary path to prefer the same `full_global_xstar_tau0_calc_emis_ion` comparison used by the top-level printed result, rather than the proxy normalized-topology summary row.
- Expanded the default scan grid from `1,1.5,2,2.5` to `1,1.5,2,2.5,3,3.25,3.5,4` so the C V diagnostic optimum near 3.25 is sampled by default.
- The empirical resonance-collisional scale remains diagnostic only. Default matrix physics remains `--resonance-collisional-feed-scale 1`; no core rates are changed unless the user explicitly supplies a different scale.

Validation: `compileall` passed; selected pytest suite passed with expected skips.

# v0.3.108 - 2026-05-08

- Added a direct collisional feed audit for the He-like resonance/singlet upper level `1s2p 1P1`.
- `examples/42_xstar_like_element_solver_demo.py` now supports `--resonance-collisional-feed-scale` to scale only direct collisional bound-bound matrix routes into `1s2p 1P1`, with paired source-loss terms scaled consistently.
- Added `--resonance-collisional-feed-scale-scan` and new outputs `xstar_like_element_solver_resonance_collisional_feed_audit.csv` and `xstar_like_element_solver_resonance_collisional_feed_scale_scan.csv`.
- The audit identifies data-type 56/63/67/68/69 collisional rows feeding the resonance upper level, reports the evaluated solver/XSTAR-calt path, and records whether the matrix rate has been scaled.
- No default physics changes: the new scale defaults to 1.0.

# v0.3.107 - 2026-05-08

- Extended `examples/46_cv_source_attribution_scan.py` for the C V high-forbidden/low-resonance residual after v0.3.104.
- Added direct bound-bound resonance/singlet feed diagnostics:
  - `cv_direct_bound_bound_source_attribution.csv`,
  - `cv_direct_bound_bound_resonance_singlet_scan.csv`.
- The new direct-bound-bound scan separates radiative/collisional feed into f, i, and r upper levels and adds a first-order 2-D f/r balance scan that boosts the resonance/singlet feed while optionally suppressing direct forbidden feed.
- This remains diagnostic-only: no core population matrix, type-50 line escape, type-71, type-77, type-99, type-53/type-74, or ion-fraction closure changes were made.

# v0.3.106 - 2026-05-08

- Improved `examples/46_cv_source_attribution_scan.py` after the v0.3.105 matrix-resolve scan showed no improvement over the stored C V baseline.
- Added population-weighted source attribution: `cv_population_weighted_source_attribution.csv`. This multiplies off-diagonal gains by the stored source-level population so raw type-71/type-99 rates from nearly unpopulated superlevels are not overinterpreted.
- Added a fixed-population first-order leverage scan: `cv_population_weighted_source_scan.csv`. This reports f/i/r, R, G, and L2 for population-weighted source-family scaling while keeping the v0.3.104 type-50 3P_J->3S1 line-escape/drain balance fixed.
- Added a matrix-recompute-vs-stored-baseline diagnostic in the summary JSON because post-processing a CSV roundtrip can differ from the in-memory `examples/42` solver result.
- No core population matrix/rate physics were changed.

# v0.3.105 - 2026-05-08

- Added `examples/46_cv_source_attribution_scan.py`, a diagnostic C V He-like triplet f/r source-attribution and source-group scan.
- The new example reads an existing `examples/42_xstar_like_element_solver_demo.py` output directory and writes:
  - `cv_source_family_attribution.csv`,
  - `cv_source_group_scan.csv`,
  - `cv_source_attribution_scan_summary.json`,
  - `cv_source_attribution_scan.md`.
- Source attribution now separates the requested C V families: type-71 cascades from `sprlevlt`/`sprlevls`/`superlev`, type-99 sources into `sprlevlt`/`sprlevls`/continuum-alias level 32, type-53 Milne inverse routes, type-74 inverse/direct diagnostic routes, and direct bound-bound radiative/collisional paths into triplet upper levels.
- The default scan focuses on the v0.3.104 C V residual (`f` high, `r` low, `i` nearly matched) and varies `type99_into_sprlevlt`, `type99_into_sprlevls`, and `type71_resonance_singlet_cascade`, while leaving all type-50 population-rate line-escape/drain rows fixed.
- The example can derive the C V target from `xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv` using `emit_outward`, or accept explicit `--target-f`, `--target-i`, and `--target-r`.
- No core population matrix/rate changes were made relative to v0.3.104.

## v0.3.104

- Added `--type50-bound-bound-treatment xstar-line-escape` for the XSTAR-like element solver.
- The new mode is a source-code-aligned type-50 population-rate path: when a transition row carries line optical depths, it evaluates the XSTAR `pescl(tau0)` escape channels and uses `A * (ptmp1 + ptmp2)` in the population matrix.
- Because true per-line `tau0` is still not available for every population-matrix transition, the interim fallback treats He-like intra-triplet `1s2p 3P_J -> 1s2s 3S1` drains as optically thin (`tau0=0`, `ptmp1+ptmp2=1.0`) while preserving the previous scalar escape-factor fallback for other missing-tau type-50 lines.
- Added audit columns to type-50 matrix terms: `xstar_tau1_for_type50_escape`, `xstar_tau2_for_type50_escape`, `xstar_cfrac_for_type50_escape`, `type50_line_escape_fallback_used`, and `type50_is_helike_3p_to_3s_drain`.
- Kept `xstar-escape` as the legacy scalar proxy and `xstar-escape-photoexcitation` as the diagnostic pumping proxy. No type-71, type-77, type-99, type-53/type-74 inverse, ion-fraction-closure, or reference-depth postprocessing behavior was intentionally changed.
- Added a focused regression test for `xstar-line-escape` fallback behavior.

Validation in this environment:

```text
compileall: passed
pytest tests/test_type50_line_escape.py tests/test_helike_triplet_balance_diagnostics.py tests/test_xstar_detail_population_compare_example.py tests/test_package_metadata.py tests/test_cli_smoke.py
9 passed, 3 skipped
```

## v0.3.103

- Made `examples/44_diagnose_helike_triplet_balance.py` recover the top-level solver triplet f/i/r summary from available summary products before optional audit diagnostics are read.
- Added fallback readers for `xstar_like_element_solver_summary.json`, `xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv`, and `xstar_like_element_solver_triplet.csv`.
- Missing optional audit CSVs still produce warnings/placeholders, but the printed case summary no longer degrades to `solver f/i/r=None` when comparison or solver summary products exist.
- No core population matrix, type-99, type-71, type-77, type-53/type-74, ion-fraction, or line-depth physics were changed.

# Changelog

## v0.3.102

- Made `examples/44_diagnose_helike_triplet_balance.py` robust to partially copied or older solver-output directories. Missing diagnostic audit CSVs are now treated as optional for the triplet-balance aggregator: the script records a warning, writes placeholder `missing_optional_audit` rows in the corresponding summary CSV, and continues collating the available triplet, type-50, type-71, type-99, and XSTAR-line-reference information.
- Added regression coverage for the missing-optional-audit path.
- Added the generated C V `ne=1e8` XSTAR triplet reference CSV at `xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv` from the local XSTAR 2.59g run/conversion workflow. Its `emit_outward` target is `f/i/r = 0.807706219 / 0.006633342 / 0.185660439`, `R = 121.765`, and `G = 4.38618`.
- No changes were made to the core population matrix, type-99 `calt99/phint53hunt`, type-71 `calt71`, type-77 `calt77`, type-53/type-74 inverse paths, ion-fraction closure, O VII reference-depth postprocess, or C V/O VII solver results.

## v0.3.101 - C V triplet-balance diagnostics and C V XSTAR reference preparation

- Added `examples/44_diagnose_helike_triplet_balance.py`, a diagnostic aggregator for full-global He-like solver outputs. It collates triplet component balances, type-50 3P_J -> 3S1 radiative drains, density-scaled 3S/3P collisional coupling, intercombination-feed categories, type-71 cascade feed into f/i/r, and type-99 superlevel-source branch proxies.
- Added `examples/45_prepare_c5_xstar_triplet_reference.py`, a targeted helper to create the C V `ne=1e8` XSTAR run/conversion plan and, when an existing `xout_lines1.fits` is supplied, convert it to `xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv`.
- Added regression tests for both new helpers.
- No core population-matrix, type-50, type-53, type-71, type-74, type-77, type-99, ion-fraction-closure, or O VII reference-depth postprocess rates were changed.

## v0.3.100 - Reference-depth scale warning for O VII validation

- Changed `examples/43_compare_xstar_detail_populations.py` so the validation-only comparison case `full_global_xstar_reference_depth_emit_outward_calc_emis_ion` no longer silently uses the default XSTAR reference depth scale when `--xstar-triplet-lines-csv` is supplied but `--xstar-reference-depth-scale` is omitted.
- The script still defaults to depth scale `1.0` for backward compatibility, but now prints: `Warning: Using default depth scale 1.0; O VII ne=1e8 validation used 0.37.`
- Applied the same warning behavior to `examples/42_xstar_like_element_solver_demo.py` when `--xstar-reference-lines-csv` is supplied without an explicit `--xstar-reference-depth-scale`.
- Added a regression test confirming that the warning is emitted and that the reference-depth postprocess output is still written.
- No changes were made to the population matrix, XSTAR `calt99/phint53hunt` type-99 path, type-71/type-77 paths, type-53/type-74 inverse paths, or the v0.3.99 O VII corrected result when `--xstar-reference-depth-scale 0.37` is supplied.

## v0.3.99 - O VII XSTAR reference-depth line escape validation

- Added optional XSTAR reference-line CSV support for the He-like triplet `calc_emis_ion` postprocessing path.  `examples/42_xstar_like_element_solver_demo.py` now accepts `--xstar-reference-lines-csv`, `--xstar-reference-value-column`, and `--xstar-reference-depth-scale`.
- `build_calc_emis_ion_triplet_emergent_rows()` can now match solver triplet lines to converted XSTAR `xout_lines1` CSV rows by component and wavelength, read `depth_inward`/`depth_outward`, evaluate the XSTAR `pescl` escape channels, and write an additional validation-only summary case named `xstar_reference_depth_emit_outward_calc_emis_ion`.
- `examples/43_compare_xstar_detail_populations.py` can now rerun the O VII comparison against a packaged XSTAR triplet-line target without rerunning the ATDB solver.  It writes `xstar_reference_depth_triplet_postprocess.csv` and, when requested with `--comparison-case full_global_xstar_reference_depth_emit_outward_calc_emis_ion`, reports the reference-depth corrected f/i/r, R, G, and L2 distance to the XSTAR `emit_outward` target.
- For the uploaded v0.3.98 O VII run and `xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv`, using `--xstar-reference-depth-scale 0.37` gives `f/i/r = 0.755947 / 0.157623 / 0.0864298`, `R = 4.79592`, `G = 10.5701`, and `L2 = 9.92e-4` relative to the XSTAR target `f/i/r = 0.756667 / 0.156942 / 0.0863914`.
- This is a validation/postprocessing fix for the O VII resonance line-output mismatch.  It does not change the core population matrix, type-99 physical assembly, type-71/type-77 rates, type-53/type-74 inverse paths, or ion-fraction closure.

## v0.3.98 - Type-99 target-stage destination assembly fix

- Fixed the remaining data-type 99 assembly bug for records whose source-audit row is carried on the adjacent parent ion stage while the destination level belongs to the target He-like ion.
- `build_global_superlevel_source_matrix_terms()` now prefers `target_ion_stage` for the destination/superlevel global-index lookup, using `record_ion_stage` only as fallback.
- This allows source-code type-99 rows with `idat(nidt-3)=0` and continuum-alias parent mapping to assemble physical `calt99/phint53hunt` matrix terms for the target-ion destination level instead of being evaluated in the audit but skipped in matrix construction.
- Retains the v0.3.97 default `--type99-source-fallback-mode physical-only`; legacy proxy rows remain disabled unless explicitly requested.
- No intentional changes to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.97

- Fixed the XSTAR `ucalc.f90` data-type 99 continuum-parent mapping for records with `idat(nidt-3) <= 0`.  These now map to `idest2 = nlev`, the target-ion continuum slot, rather than an invalid parent level zero.
- Under the existing `xstar-continuum-alias` / `xstar-continuum-alias-superlevels` full-global topology, that explicit target-ion continuum row aliases to the adjacent parent-ion ground row, matching the XSTAR `calc_hmc_element` `ipmat = ipmat + nlev - 1` convention.
- Added provenance fields for the continuum-alias type-99 path, including `type99_parent_maps_to_target_continuum_alias`, `type99_parent_global_index`, and `type99_parent_mapping_source = ucalc_idat_nidt_minus_3_zero_maps_to_target_continuum_alias`.
- Changed the default type-99 source fallback mode to `physical-only`: if `calt99/phint53hunt` cannot produce physical rates, the old `source_vector_gain_proxy` / scaffold proxy rows are skipped instead of assembled.  The legacy scaffold can be restored only for diagnostics with `--type99-source-fallback-mode legacy-proxy`.
- No intentional changes were made to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.96

- Fixed the remaining type-99 activation bug exposed by the v0.3.95 C V/O VII reruns.  The type-99 `calt99/phint53hunt` source-code path now looks up target and parent levels from the explicit global element index rather than the legacy per-ion population table, so ATDB superlevels such as C V `sprlevls/sprlevlt` and explicit parent excited levels are available during `ucalc`-style mapping.
- This also provides the statistical weights needed by the reconstructed `phint53hunt` Milne `ans2d` integral, allowing `ans2 = rec*xnx` rows to become matrix-ready when the source-code type-99 closure evaluates successfully.
- Physical type-99 rows should now appear in `xstar_like_element_solver_global_superlevel_source_matrix_terms.csv` with `assembly_status = assembled_global_type99_calt99_phint53hunt` for C V/O VII rows whose `calt99/phint53hunt` closure is valid.
- No intentional changes were made to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.95

- Fixed XSTAR `ucalc.f90` data-type 99 parent-level mapping after the v0.3.94 `calt99`/`phint53hunt` port.
- Mapped `idat(nidt-3)` to the explicit adjacent parent-ion level in the global matrix instead of using the target-ion continuum proxy row.
- Added parent-level provenance fields for type 99: `type99_ucalc_parent_ion_stage`, `type99_ucalc_parent_ion_level_index`, `type99_ucalc_idest2_local_matrix_level`, and `type99_parent_mapping_source`.
- Removed the incorrect direct-triplet-destination requirement for source-code type-99 assembly; destinations such as O VII levels 30/31 and C V levels 48/49 are allowed when their explicit parent levels exist.
- Physical type-99 rows now assemble as `assembled_global_type99_calt99_phint53hunt` against the explicit parent ion level when `calt99/phint53hunt` rates are available.
- No intentional changes to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.94

- Ported the XSTAR `calt99.f90` evaluator for data-type 99 superlevel bound-free records.
- Added a source-code type-99 `ucalc.f90`/`phint53hunt.f90` closure: `ans1` is the scaled photoionization rate and `ans2=rec*xnx` is the recombination source rate.
- Assembled real type-99 matrix terms for destination-to-parent photoionization and parent-to-destination recombination in the full global/Lucy matrix.
- Added `type99_calt99_*` and `type99_phint53hunt_*` fields to `xstar_like_element_solver_superlevel_cascade_audit.csv`.
- Added physical type-99 rows to `xstar_like_element_solver_global_superlevel_source_matrix_terms.csv` with `assembly_status=assembled_global_type99_calt99_phint53hunt`.
- Kept type-71 `calt71` and type-77 `calt77` active; no intentional changes were made to type-50 escape, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination, or `calc_ion_rates/istruc`.
- Selected validation passed (`5 passed, 4 skipped`); the full pytest suite was not completed in this environment due to timeout.


## v0.3.93

- Ported the XSTAR `calt77.f90` evaluator for data-type 77 collisional coupling between ATDB superlevels and spectroscopic levels.
- `calt77` now evaluates the source-code downward superlevel-to-spectroscopic rate `cul` by log-density/log-temperature interpolation and computes the upward spectroscopic-to-superlevel rate `clu = cul * exp(-1.43817e8/(wav*T)) / gg`, including the XSTAR `ucalc.f90` temperature floor `T=max(T,2.8777e6/wav)`.
- Type-77 records are now assembled into the global/Lucy matrix with XSTAR `ucalc` semantics: `ans1=clu` for spectroscopic -> superlevel and `ans2=cul` for superlevel -> spectroscopic.
- Type-71 `calt71` remains active. Type-77 is now a true matrix coupling, not a branch-count proxy.
- The superlevel cascade/coupling matrix CSV now reports `type77_calt77_*` fields and separates type-71 and type-77 source-code provenance.
- No intentional changes to type-50 matrix escape rates, inverse recombination, geometry-derived line optical-depth construction, `calc_emis_ion`, `calc_ion_rates/istruc`, triplet coupling/suppression behavior, or non-Lucy solvers.

## v0.3.92

- Ported the XSTAR `calt71.f90` evaluator for data type 71 radiative superlevel-to-spectroscopic cascade records.
- Type-71 audit rows now include source-code `type71_calt71_aij_s^-1`, wavelength, log-rate, grid dimensions, bracket indices, and evaluation status.
- Global type-71 cascade matrix assembly now uses `type71_calt71_aij_s^-1` when available instead of the old preview/scaffold value (`2.0` in many C V/O VII rows), with a legacy preview fallback only if calt71 cannot be evaluated.
- Type-71 branching weights now use calt71 A-values, so superlevel cascade branching and the full-global `xstar-lucy` path use the same source-code cascade rates.
- Kept the C V `full_global_xstar_tau0_calc_emis_ion` result as the regression benchmark and made no intentional changes to type-50 matrix rates, inverse recombination, geometry-derived line optical depth, `calc_emis_ion`, `calc_ion_rates/istruc`, triplet coupling/suppression, or non-Lucy solvers.


## v0.3.91

- Added `examples/43_compare_xstar_detail_populations.py` for the next validation milestone after the C V triplet match.
- The new comparison utility reads a full-global solver output directory, extracts population rows from `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`, reports the recommended `full_global_xstar_tau0_calc_emis_ion` triplet row, and writes CSV/JSON/Markdown validation products.
- Optional external XSTAR detail population tables can be supplied as CSV or FITS and are matched by ion stage plus level index.
- The utility defaults to C V (`--element C --he-like-stage 5`) and is prepared for the next O VII validation step via `--element O --he-like-stage 7`.
- No intentional solver, matrix, optical-depth, `calc_emis_ion`, type-50, inverse-recombination, or `calc_ion_rates/istruc` physics changes from v0.3.90.

## v0.3.90 - Print and document recommended full-global emergent triplet comparison

- Updated `examples/42_xstar_like_element_solver_demo.py --print-summary` so the compact terminal summary reports the recommended full-global emergent line-output row, `full_global_xstar_tau0_calc_emis_ion`, instead of the obsolete simple per-ion triplet baseline.
- The printed summary now includes the recommended comparison case name, full-global emergent `f/i/r`, `R`, `G`, and target-aware L2 distance when that row is available.
- Documented `full_global_xstar_tau0_calc_emis_ion` as the recommended XSTAR C V triplet validation comparison case in the README.
- No intentional changes to population solving, type-50 matrix rates, geometry-derived optical-depth construction, `calc_emis_ion` emergent-line formulas, inverse recombination, `calc_ion_rates -> istruc`, triplet coupling/suppression behavior, or non-Lucy solvers.

## v0.3.89 - Geometry-derived XSTAR type-50 tau0 column for calc_emis_ion

- Derives the type-50 line optical-depth column for the `calc_emis_ion.f90` triplet emergent-line path from the XSTAR source-code geometry/transfer quantity `xpx*xeltp*delr` by default.
- Added `--xstar-line-column-source geometry|auto|manual|rt|xstar`; the default `geometry` computes the column from density, abundance, and zone thickness instead of using a hand-tuned equivalent column.
- Added `--xstar-line-zone-thickness-cm`, `--xstar-line-hydrogen-density-cm3`, `--xstar-line-electron-per-hydrogen`, and `--xstar-line-element-abundance` to provide the local XSTAR zone context when available.
- Preserves backward compatibility: `--xstar-line-column-source manual` uses `--xstar-line-column-density`, and `auto` uses a nonzero manual column if supplied.
- Reports the resolved source, `xpx`, `xeltp`, `delr`, geometry column, manual column, and source-code formula in `xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv`.
- No intentional changes to population solving, type-50 matrix rates, inverse recombination, `calc_ion_rates -> istruc` metadata behavior, triplet coupling/suppression behavior, or non-Lucy solvers.

## v0.3.88 - Fix type-50 line opacity atomic-mass fallback crash

- Fixed a v0.3.87 runtime crash in `_xstar_atomic_mass_amu_from_symbol()` caused by an undefined `SYMBOL_TO_Z` fallback reference during the new type-50 line optical-depth context construction.
- The helper now uses the local `_XSTAR_APPROX_ATOMIC_MASS_AMU` table and falls back safely to `1.0` amu for unknown symbols.
- No intentional changes to line optical-depth physics, `calc_emis_ion` emergent-line formulas, population solving, type-50 matrix rates, inverse recombination, `calc_ion_rates -> istruc` behavior, triplet coupling/suppression, or non-Lucy solvers.

## v0.3.87 - XSTAR type-50 line tau0 optical-depth context for calc_emis_ion

- Added XSTAR source-code line optical-depth construction for triplet emergent-line post-processing.
- Added CLI options `--xstar-line-column-density`, `--xstar-line-vturb-km-s`, `--xstar-line-cfrac`, `--xstar-line-tau1-fraction`, and `--xstar-line-tau2-fraction`.
- Reconstructs type-50 oscillator strength `flin`, thermal/turbulent width `vtherm`, line cross section `sigvtherm`, lower-level column, directional `tau0(1/2)`, and component-specific `ptmp1/ptmp2=pescl(tau0)` values.
- The emergent triplet comparison now uses `xstar_tau0_calc_emis_ion` rather than the old common matrix escape proxy, while retaining raw and transparent cases for reference.
- No intentional changes to population solving, type-50 population matrix rates, inverse recombination, `calc_ion_rates -> istruc` metadata behavior, or non-Lucy solvers.

## v0.3.85

## v0.3.86 - XSTAR calc_emis_ion emergent triplet line construction

- Added `xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv`, which ports the XSTAR `calc_emis_ion.f90` triplet line-output construction for selected He-like triplet records.
- The new table reports the source-code channels `ptmp1` and `ptmp2`, transparent `tau0=0,cfrac=0` output, active matrix type-50 escape/pumping output, and attenuation relative to raw `pop*A*E`.
- Implemented the XSTAR `pescl.f90` line escape function and the `calc_emis_ion.f90` type-4/type-9 channel formulas.
- Uses the `ucalc.f90` type-50 source-code orientation after the internal swap: `ans1` is lower-to-upper photoexcitation/pumping and `ans2` is upper-to-lower escaped decay.
- Adds compact `full_global_raw_pop_A_E`, `full_global_transparent_tau0_calc_emis_ion`, and `full_global_matrix_escape_calc_emis_ion` summary rows to `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`.
- No intentional changes to the population solver, type-50 matrix rates, inverse recombination, `calc_ion_rates -> istruc` metadata behavior, triplet coupling/suppression options, or non-Lucy solvers.


- Implements the exact XSTAR `msolvelucy.f90` fixed-point sub-iteration for the full-global `xstar-lucy` path.
- Expands reconstructed two-rate pairs into a four-row `ajisb` list and uses that list for the source-code `riu/rui/ril/rli` `nit2` loop after each condensed superlevel solve.
- Removes the previous nonnegative clipping in the fixed-point update so the update uses the current `x(nn)` directly, matching the source routine.
- Reports fixed-point metadata in `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`: `xstar_msolvelucy_fixed_point_mode`, `xstar_msolvelucy_fixed_point_population_clipping`, `xstar_lucy_nit2_last`, `xstar_lucy_nit2_total`, and final `riu/rui/ril/rli` sums.
- Adds per-level final `xstar_msolvelucy_riu`, `xstar_msolvelucy_rui`, `xstar_msolvelucy_ril`, and `xstar_msolvelucy_rli` columns for population-row inspection.
- Keeps v0.3.83/v0.3.84 behavior that `calc_ion_rates -> istruc` targets are metadata/seed-structure information, not hard per-stage Lucy constraints.
- No intentional changes to type-50 escape rates, inverse-recombination rates, matrix term construction, triplet suppression/coupling options, or non-Lucy solvers.

## v0.3.84

- Implements the direct XSTAR `levwkelement` / `msolvelucy` population-construction step for the full-global `xstar-lucy` solver.
- Reconstructs XSTAR-like `ajisb` two-rate pairs from positive off-diagonal matrix rates and uses those pairs to build the condensed superlevel matrix with the same `rr(level)=x(level)/p(nsup)` weighting used in `msolvelucy.f90`.
- Replaces the previous direct dense-matrix condensation in the Lucy path with source-code-style `p`, `rr`, `bmatsup`, `ipmat2`, and `nsup` bookkeeping.
- Population rows now report XSTAR-style population-construction quantities: `xstar_ipmat2_index`, `xstar_nsup`, `xstar_superlevel_population_p`, `xstar_rr_fraction_within_superlevel`, `xstar_levwkelement_rnise`, `xstar_bileve_departure_coefficient`, and `xstar_xileve_emissivity_population`.
- Summary rows report `xstar_population_construction_mode`, `xstar_msolvelucy_uses_fortran_ajisb_pairs`, `xstar_msolvelucy_n_two_rate_pairs`, `xstar_msolvelucy_n_ajisb_entries_equivalent`, and final `p(superlevel)` JSON.
- Keeps v0.3.83 behavior that `calc_ion_rates -> istruc` targets are metadata/seed-structure information, not hard per-stage Lucy constraints.
- No intentional changes to type-50 escape rates, inverse-recombination rates, triplet coupling, suppression behavior, or default non-Lucy solvers.

# Changelog

## v0.3.99 - O VII XSTAR reference-depth line escape validation

- Added optional XSTAR reference-line CSV support for the He-like triplet `calc_emis_ion` postprocessing path.  `examples/42_xstar_like_element_solver_demo.py` now accepts `--xstar-reference-lines-csv`, `--xstar-reference-value-column`, and `--xstar-reference-depth-scale`.
- `build_calc_emis_ion_triplet_emergent_rows()` can now match solver triplet lines to converted XSTAR `xout_lines1` CSV rows by component and wavelength, read `depth_inward`/`depth_outward`, evaluate the XSTAR `pescl` escape channels, and write an additional validation-only summary case named `xstar_reference_depth_emit_outward_calc_emis_ion`.
- `examples/43_compare_xstar_detail_populations.py` can now rerun the O VII comparison against a packaged XSTAR triplet-line target without rerunning the ATDB solver.  It writes `xstar_reference_depth_triplet_postprocess.csv` and, when requested with `--comparison-case full_global_xstar_reference_depth_emit_outward_calc_emis_ion`, reports the reference-depth corrected f/i/r, R, G, and L2 distance to the XSTAR `emit_outward` target.
- For the uploaded v0.3.98 O VII run and `xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv`, using `--xstar-reference-depth-scale 0.37` gives `f/i/r = 0.755947 / 0.157623 / 0.0864298`, `R = 4.79592`, `G = 10.5701`, and `L2 = 9.92e-4` relative to the XSTAR target `f/i/r = 0.756667 / 0.156942 / 0.0863914`.
- This is a validation/postprocessing fix for the O VII resonance line-output mismatch.  It does not change the core population matrix, type-99 physical assembly, type-71/type-77 rates, type-53/type-74 inverse paths, or ion-fraction closure.

## v0.3.92

- Ported the XSTAR `calt71.f90` evaluator for data type 71 radiative superlevel-to-spectroscopic cascade records.
- Type-71 audit rows now include source-code `type71_calt71_aij_s^-1`, wavelength, log-rate, grid dimensions, bracket indices, and evaluation status.
- Global type-71 cascade matrix assembly now uses `type71_calt71_aij_s^-1` when available instead of the old preview/scaffold value (`2.0` in many C V/O VII rows), with a legacy preview fallback only if calt71 cannot be evaluated.
- Type-71 branching weights now use calt71 A-values, so superlevel cascade branching and the full-global `xstar-lucy` path use the same source-code cascade rates.
- Kept the C V `full_global_xstar_tau0_calc_emis_ion` result as the regression benchmark and made no intentional changes to type-50 matrix rates, inverse recombination, geometry-derived line optical depth, `calc_emis_ion`, `calc_ion_rates/istruc`, triplet coupling/suppression, or non-Lucy solvers.

## v0.3.83

- Fixed the `--ion-fraction-closure xstar-calc-ion-rates` interpretation by following the XSTAR source path more closely.  In `calc_hmc_element.f90`, `calc_ion_rates -> istruc` is used before `levwkelement` to determine ion limits and seed structure; `msolvelucy.f90` then solves the condensed superlevel system with a total number-conservation row, not with hard per-ion `istruc` constraints.
- The pre-matrix source-code-gated `pirti`/`rrrti` targets are still reported in `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv` and full-global metadata, but they are no longer applied as hard stage-normalization constraints during Lucy iteration.
- `xstar_istruc_ion_fraction_targets_applied` is now `False` for this source-code path, and `xstar_istruc_ion_fraction_targets_application_status` explains that XSTAR uses the rates for ion limits/levwkelement seeding rather than hard Lucy constraints.
- No intentional changes to type-50 rates, inverse-recombination rates, matrix assembly, triplet coupling, suppression behavior, or default `--ion-fraction-closure none` behavior.

## v0.3.82

- Tightened the pre-matrix XSTAR `calc_ion_rates` / `istruc` reconstruction to follow the visible `calc_ion_rates.f90` source-code gates instead of summing every level-resolved bound-free candidate.
- `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv` now marks each rate row with `calc_ion_rates_pirti_included`, `calc_ion_rates_rrrti_included`, `calc_ion_rates_total_included`, `calc_ion_rates_equation_role`, and `calc_ion_rates_inclusion_reason`.
- Level-resolved type-53 `phint53` Milne `rrrt`/`ans2`, independent `milne.f90` `alpha*ne`, and type-74 `calt74` weighted-alpha inverse terms are retained as recombination-side candidates but are explicitly excluded from the source-code `rrrti` total unless they are total rate-type 6/8 rows.
- The `--ion-fraction-closure xstar-calc-ion-rates` closure now derives its targets from source-code-gated `pirti`/`rrrti` totals. Candidate totals remain reported separately in metadata for comparison.
- No intentional changes to type-50 escape treatment, topology modes, triplet-coupling suppression, or default `--ion-fraction-closure none` behavior.

## v0.3.81

- Bug-fix release for the v0.3.80 pre-matrix XSTAR `calc_ion_rates` / `istruc` closure diagnostics.
- Fixed `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv` writing by returning `calc_ion_rates_istruc_audit` rows from `solve_element_reference(...)`.
- Fixed `xstar_istruc_ion_fraction_targets_json` population for `--ion-fraction-closure xstar-calc-ion-rates` / `calc-ion-rates`; v0.3.80 only applied target extraction for the legacy `xstar-istruc` spelling.
- Added explicit full-global metadata flags: `xstar_istruc_ion_fraction_targets_applied` and `xstar_istruc_ion_fraction_targets_application_status`, so runs report whether stage targets were applied, skipped due to missing/invalid targets, or not requested.
- No intentional solver, rate, matrix-assembly, type-50, inverse-recombination, triplet-coupling, suppression, or physical-behavior changes beyond the requested metadata/audit handoff fixes.

## v0.3.80

- Added `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv`, a pre-matrix XSTAR `calc_ion_rates` / `istruc` reconstruction for adjacent C V/C VI ion-stage closure.
- Added `--ion-fraction-closure xstar-calc-ion-rates` and changed `xstar-istruc` to use the pre-matrix ion-rate audit when available instead of summed full-global matrix entries.
- The audit separates available ion-stage rates into photoionization, radiative recombination, dielectronic recombination, collisional ionization, and three-body recombination contributions from type 53, type 74, type 1, and type 57 diagnostics.
- Full-global solve metadata now records whether ion-fraction targets came from the pre-matrix `calc_ion_rates` audit or the older assembled-matrix fallback.
- Default `--ion-fraction-closure none` remains unchanged; no default solver/rate behavior changes.

## v0.3.79

- Added experimental `--ion-fraction-closure none|xstar-istruc`.
- `xstar-istruc` derives a two-stage XSTAR `calc_ion_rates`/`istruc`-style ion fraction closure from summed inter-stage matrix rates, using `x_low=R/(I+R)` and `x_high=I/(I+R)`.
- The `xstar-lucy` population iteration can now apply these ion-stage targets during the level-population fixed-point update, so the aliased parent continuum/parent ground is constrained consistently with the adjacent-stage balance rather than only by global `sum n_i = 1`.
- Full-global output records `xstar_istruc_ion_fraction_closure_requested`, `xstar_istruc_ion_fraction_closure_status`, `xstar_istruc_ion_fraction_targets_json`, and `xstar_istruc_ion_fraction_flow_rates_json`.
- Existing behavior remains available with the default `--ion-fraction-closure none`.
- Validation: `4 passed, 1 skipped`.

## v0.3.78

Direct XSTAR `ucalc` inverse-recombination implementation step.

- Added `--inverse-recombination-mode xstar-ucalc` as an experimental source-code path, while keeping the older `type53-milne-diagnostic`, `type74-direct-diagnostic`, and `type53-type74` proxy modes for regression.
- In `xstar-ucalc` mode, the type-53 inverse matrix terms are assembled from the source-code `phint53.f90` Milne `ans2` audit (`source_code_phint53_milne_ans2_rrrt_s^-1`) instead of the older scaled detailed-balance proxy.
- In `xstar-ucalc` mode, type-74 inverse terms use the source-aligned `calt74` alpha path with the XSTAR `gglo/ggup` correction; the older direct type-74 inverse proxy is disabled for this mode.
- The assembled type-53 rows are still marked experimental because exact XSTAR runtime arrays (`ethion`, `ethtmp`, `emltlv`) and escape factors are reconstructed, but the full-global matrix now uses the audited source-code closure rather than empirical inverse-rate scaling.
- No intentional changes to type-50 treatment, topology modes, atomic data decoding, triplet-coupling suppression, or final `calc_emis` accounting.

## v0.3.77

Direct XSTAR-code implementation step for the full-global population path.

- Applies the XSTAR `calc_hmc_element.f90` continuum-alias rule at matrix-index level for `--full-global-topology xstar-continuum-alias` and `xstar-continuum-alias-superlevels`: explicit continuum / parent-continuum rows are remapped to the parent-ion ground row before assembling the dense full-global matrix. This is closer to XSTAR's `ipmat = ipmat + nlev - 1` topology than the v0.3.76 superlevel-membership-only alias.
- Initializes the `xstar-lucy` solver with an XSTAR `levwk.f90` / `levwkelement.f90`-style LTE/partition seed when temperature and electron density are available, falling back to statistical weights only if the source-code seed cannot be evaluated.
- Adds output metadata: `xstar_matrix_continuum_alias_count`, `xstar_matrix_continuum_alias_json`, and `xstar_lucy_population_seed_mode`.
- Keeps the existing `explicit-current` mode available for regression comparison. No intentional changes to atomic data decoding, type-50 escape semantics, type-53/type-74 rate values, triplet-coupling suppression, or final line-output accounting.

## v0.3.76

- Added experimental `--full-global-topology explicit-current|xstar-continuum-alias|xstar-continuum-alias-superlevels` for the full-global `xstar-lucy` solver.
- `explicit-current` is the default and preserves v0.3.75 behavior.
- `xstar-continuum-alias` maps continuum / parent-continuum rows into the same condensed Lucy group as the parent ion ground state, following the XSTAR `ipmat = ipmat + nlev - 1` topology.
- `xstar-continuum-alias-superlevels` also groups levels 2..nlev-1 into one excited `nsup` group per ion, matching the source-code `calc_hmc_element.f90` grouping rule.
- The modes are experimental diagnostics; they change only the condensed `xstar-lucy` membership used by the full-global normalized solve, not the assembled matrix terms or default physical/rate behavior.
- Full-global solve output now records `full_global_topology_requested`, `xstar_lucy_topology_mode`, and `xstar_lucy_super_keys_json`.

## v0.3.75

- Added `xstar_like_element_solver_xstar_matrix_topology_audit.csv`, an audit-only comparison between the current explicit Python global-index topology and the visible XSTAR `calc_hmc_element.f90` element matrix topology.
- The audit records the XSTAR `ipmat = ipmat + nlev - 1` continuum-alias rule, parent-ground alias candidates, and the XSTAR `nsup` grouping rule where level 1 is an independent ground group and levels 2..nlev-1 are grouped into one excited-state superlevel.
- Added summary columns showing how many current rows XSTAR would keep as independent rows versus condense or alias.
- No intentional changes to solver behavior, matrix assembly, type-50 treatment, recombination rates, triplet coupling, suppression behavior, or physical-rate behavior.

## v0.3.74

- Bug-fix release for the v0.3.73 Milne-integral audit handoff.
- Fixed `build_type53_type74_ucalc_closure_audit_rows(...)` so its signature accepts the new `type53_rate_audit_rows` keyword passed by `solve_element_reference(...)`.
- This restores the v0.3.71 closure audit and allows the v0.3.73 `phint53`/`milne` raw cross-section-grid join to run in the same demo call.
- No intentional solver, matrix assembly, type-50 treatment, inverse-recombination rate, triplet-coupling, suppression, or physical-rate behavior changes.

## v0.3.73

- Bug-fix release for the v0.3.72 `phint53` Milne integral audit.
- `xstar_like_element_solver_phint53_milne_integral_audit.csv` now reads the full type-53 raw real arrays from `type53_rate_audit_rows` when the later `type53_phint53_rate_audit_rows` do not carry the original cross-section grid.
- Adds `type53_cross_section_source` and `type53_n_cross_section_pairs_available` columns to make this provenance explicit.
- No intentional solver, matrix, type-50, recombination-rate, triplet-coupling, or physical-rate behavior changes.

## v0.3.72

- Added `xstar_like_element_solver_phint53_milne_integral_audit.csv`.
- Ported/source-audited the type-53 recombination-side `phint53.f90` Milne `ans2` integral terms, including the reconstructed LTE seed `rnist`, the `bbnurjp` factor, Boltzmann suppression, and `ptmp1+ptmp2` escape multiplier placeholder.
- Added a Python audit port of XSTAR `milne.f90` and `intin.f90`, matching the debug check in `ucalc.f90` where `alphamilne*xnx` is compared with `phint53` `ans2`.
- The new audit compares the source-code Milne estimates against the current Python type-53 Milne proxy and summarizes f/i/r/other component source rates.
- Diagnostic-only release: no intentional changes to solver behavior, matrix assembly, default `raw-A` behavior, type-50 escape diagnostics, inverse-recombination rates, triplet-coupling logic, suppression behavior, or physical-rate behavior.

## v0.3.71

- Added `xstar_like_element_solver_type53_type74_ucalc_closure_audit.csv`, a source-code-aligned read-only audit for the type-53/type-74 recombination closure that likely controls the remaining C V f/r mismatch after the type-50 escape correction.
- The new audit compares current Python proxy rates against XSTAR `ucalc.f90` semantics for:
  - type 53 `phint53` forward photoionization (`ans1`) and pending Milne inverse recombination (`ans2`) with LTE/Saha/statistical diagnostic ingredients;
  - type 74 `calt74` forward delta-photoionization and inverse DR alpha after the XSTAR `gglo/ggup` statistical-weight correction;
  - older direct type-74 inverse proxy rates versus the source-aligned `calt74` weighted alpha path.
- The audit writes per-record rows plus component summaries for f/i/r/other inverse-source proxies, so f/r source imbalance can be inspected without running another empirical scale scan.
- No solver, matrix assembly, default `raw-A` type-50 behavior, type-50 escape diagnostic semantics, inverse-recombination rates, or physical-rate behavior is intentionally changed.

## v0.3.70

- Added `xstar_like_element_solver_type50_escape_factor_scan.csv`, a controlled diagnostic scan over proxy XSTAR `ucalc` type-50 escape factors.
- Added `--type50-escape-factor-scan`, defaulting to `0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.75,1`.
- The scan rebuilds the bound-bound matrix with `type50_bound_bound_treatment=xstar-escape` for each factor, holds the other primary matrix components fixed, solves the full-global normalized system, and reports f/i/r, R, G, L2-to-target, target-aware deltas, and the summed `1s2p 3P_J -> 1s2s 3S1` raw/escaped rates.
- The default primary run remains unchanged unless the user explicitly selects `--type50-bound-bound-treatment xstar-escape` or `xstar-escape-photoexcitation`.
- The scan is diagnostic only until real XSTAR optical-depth, `pescl`/`pescv`, `bremsa`, and `flinabs` contexts are ported.

## v0.3.69

- Bug-fix release for v0.3.68.
- Fixes the v0.3.67 type-50 `xstar-escape` treatment so the assembled global bound-bound matrix uses the effective escaped rate in `signed_rate_s^-1`, not only in the audit `rate_s^-1` column.
- The affected rows are the off-diagonal gain and diagonal loss entries created by `build_global_bound_bound_matrix_terms(...)`; they now use `effective_rate` and `-effective_rate`.
- The default `raw-A` treatment remains numerically unchanged.
- No intentional changes to type-50 audit semantics, solver normalization, suppression logic, physical rate decoding, or `calc_emis` audits.

## v0.3.68

- Bug-fix release for v0.3.67.
- Fixes `build_global_superlevel_cascade_matrix_terms(...)` so type-71 superlevel cascade rows use `float(rate)` for their signed gain/loss terms instead of the undefined local variable `effective_rate`.
- This restores the full diagnostic demo path when `--type50-bound-bound-treatment xstar-escape` or `xstar-escape-photoexcitation` is used.
- No intentional solver, type-50 treatment, matrix-physics, triplet-coupling, suppression, or physical-rate behavior changes beyond fixing the writer/assembly NameError.

## v0.3.104 - 2026-05-08

- Added `--type50-bound-bound-treatment xstar-line-escape` for the XSTAR-like element solver.
- The new mode is a source-code-aligned type-50 population-rate path: when a transition row carries line optical depths, it evaluates the XSTAR `pescl(tau0)` escape channels and uses `A * (ptmp1 + ptmp2)` in the population matrix.
- Because true per-line `tau0` is still not available for every population-matrix transition, the interim fallback treats He-like intra-triplet `1s2p 3P_J -> 1s2s 3S1` drains as optically thin (`tau0=0`, `ptmp1+ptmp2=1.0`) while preserving the previous scalar escape-factor fallback for other missing-tau type-50 lines.
- Added audit columns to type-50 matrix terms: `xstar_tau1_for_type50_escape`, `xstar_tau2_for_type50_escape`, `xstar_cfrac_for_type50_escape`, `type50_line_escape_fallback_used`, and `type50_is_helike_3p_to_3s_drain`.
- Kept `xstar-escape` as the legacy scalar proxy and `xstar-escape-photoexcitation` as the diagnostic pumping proxy. No type-71, type-77, type-99, type-53/type-74 inverse, ion-fraction-closure, or reference-depth postprocessing behavior was intentionally changed.
- Added a focused regression test for `xstar-line-escape` fallback behavior.

Validation in this environment:

```text
compileall: passed
pytest tests/test_type50_line_escape.py tests/test_helike_triplet_balance_diagnostics.py tests/test_xstar_detail_population_compare_example.py tests/test_package_metadata.py tests/test_cli_smoke.py
9 passed, 3 skipped
```

## v0.3.103 - 2026-05-08

- Made `examples/44_diagnose_helike_triplet_balance.py` recover the top-level solver triplet f/i/r summary from available summary products before optional audit diagnostics are read.
- Added fallback readers for `xstar_like_element_solver_summary.json`, `xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv`, and `xstar_like_element_solver_triplet.csv`.
- Missing optional audit CSVs still produce warnings/placeholders, but the printed case summary no longer degrades to `solver f/i/r=None` when comparison or solver summary products exist.
- No core population matrix, type-99, type-71, type-77, type-53/type-74, ion-fraction, or line-depth physics were changed.

# Changelog

## v0.3.102 - 2026-05-08

- Made `examples/44_diagnose_helike_triplet_balance.py` robust to partially copied or older solver-output directories. Missing diagnostic audit CSVs are now treated as optional for the triplet-balance aggregator: the script records a warning, writes placeholder `missing_optional_audit` rows in the corresponding summary CSV, and continues collating the available triplet, type-50, type-71, type-99, and XSTAR-line-reference information.
- Added regression coverage for the missing-optional-audit path.
- Added the generated C V `ne=1e8` XSTAR triplet reference CSV at `xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv` from the local XSTAR 2.59g run/conversion workflow. Its `emit_outward` target is `f/i/r = 0.807706219 / 0.006633342 / 0.185660439`, `R = 121.765`, and `G = 4.38618`.
- No changes were made to the core population matrix, type-99 `calt99/phint53hunt`, type-71 `calt71`, type-77 `calt77`, type-53/type-74 inverse paths, ion-fraction closure, O VII reference-depth postprocess, or C V/O VII solver results.

## v0.3.101 - C V triplet-balance diagnostics and C V XSTAR reference preparation - 2026-05-07

- Added `examples/44_diagnose_helike_triplet_balance.py`, a diagnostic aggregator for full-global He-like solver outputs. It collates triplet component balances, type-50 3P_J -> 3S1 radiative drains, density-scaled 3S/3P collisional coupling, intercombination-feed categories, type-71 cascade feed into f/i/r, and type-99 superlevel-source branch proxies.
- Added `examples/45_prepare_c5_xstar_triplet_reference.py`, a targeted helper to create the C V `ne=1e8` XSTAR run/conversion plan and, when an existing `xout_lines1.fits` is supplied, convert it to `xstar_test_run/c5_ne1e8/xstar_c5_triplet_lines.csv`.
- Added regression tests for both new helpers.
- No core population-matrix, type-50, type-53, type-71, type-74, type-77, type-99, ion-fraction-closure, or O VII reference-depth postprocess rates were changed.

## v0.3.100 - Reference-depth scale warning for O VII validation - 2026-05-07

- Changed `examples/43_compare_xstar_detail_populations.py` so the validation-only comparison case `full_global_xstar_reference_depth_emit_outward_calc_emis_ion` no longer silently uses the default XSTAR reference depth scale when `--xstar-triplet-lines-csv` is supplied but `--xstar-reference-depth-scale` is omitted.
- The script still defaults to depth scale `1.0` for backward compatibility, but now prints: `Warning: Using default depth scale 1.0; O VII ne=1e8 validation used 0.37.`
- Applied the same warning behavior to `examples/42_xstar_like_element_solver_demo.py` when `--xstar-reference-lines-csv` is supplied without an explicit `--xstar-reference-depth-scale`.
- Added a regression test confirming that the warning is emitted and that the reference-depth postprocess output is still written.
- No changes were made to the population matrix, XSTAR `calt99/phint53hunt` type-99 path, type-71/type-77 paths, type-53/type-74 inverse paths, or the v0.3.99 O VII corrected result when `--xstar-reference-depth-scale 0.37` is supplied.

## v0.3.99 - O VII XSTAR reference-depth line escape validation - 2026-05-07

- Added optional XSTAR reference-line CSV support for the He-like triplet `calc_emis_ion` postprocessing path.  `examples/42_xstar_like_element_solver_demo.py` now accepts `--xstar-reference-lines-csv`, `--xstar-reference-value-column`, and `--xstar-reference-depth-scale`.
- `build_calc_emis_ion_triplet_emergent_rows()` can now match solver triplet lines to converted XSTAR `xout_lines1` CSV rows by component and wavelength, read `depth_inward`/`depth_outward`, evaluate the XSTAR `pescl` escape channels, and write an additional validation-only summary case named `xstar_reference_depth_emit_outward_calc_emis_ion`.
- `examples/43_compare_xstar_detail_populations.py` can now rerun the O VII comparison against a packaged XSTAR triplet-line target without rerunning the ATDB solver.  It writes `xstar_reference_depth_triplet_postprocess.csv` and, when requested with `--comparison-case full_global_xstar_reference_depth_emit_outward_calc_emis_ion`, reports the reference-depth corrected f/i/r, R, G, and L2 distance to the XSTAR `emit_outward` target.
- For the uploaded v0.3.98 O VII run and `xstar_test_run/o7_ne1e8/xstar_o7_triplet_lines.csv`, using `--xstar-reference-depth-scale 0.37` gives `f/i/r = 0.755947 / 0.157623 / 0.0864298`, `R = 4.79592`, `G = 10.5701`, and `L2 = 9.92e-4` relative to the XSTAR target `f/i/r = 0.756667 / 0.156942 / 0.0863914`.
- This is a validation/postprocessing fix for the O VII resonance line-output mismatch.  It does not change the core population matrix, type-99 physical assembly, type-71/type-77 rates, type-53/type-74 inverse paths, or ion-fraction closure.

## v0.3.98 - Type-99 target-stage destination assembly fix - 2026-05-07

- Fixed the remaining data-type 99 assembly bug for records whose source-audit row is carried on the adjacent parent ion stage while the destination level belongs to the target He-like ion.
- `build_global_superlevel_source_matrix_terms()` now prefers `target_ion_stage` for the destination/superlevel global-index lookup, using `record_ion_stage` only as fallback.
- This allows source-code type-99 rows with `idat(nidt-3)=0` and continuum-alias parent mapping to assemble physical `calt99/phint53hunt` matrix terms for the target-ion destination level instead of being evaluated in the audit but skipped in matrix construction.
- Retains the v0.3.97 default `--type99-source-fallback-mode physical-only`; legacy proxy rows remain disabled unless explicitly requested.
- No intentional changes to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.97 - 2026-05-07

- Fixed the XSTAR `ucalc.f90` data-type 99 continuum-parent mapping for records with `idat(nidt-3) <= 0`.  These now map to `idest2 = nlev`, the target-ion continuum slot, rather than an invalid parent level zero.
- Under the existing `xstar-continuum-alias` / `xstar-continuum-alias-superlevels` full-global topology, that explicit target-ion continuum row aliases to the adjacent parent-ion ground row, matching the XSTAR `calc_hmc_element` `ipmat = ipmat + nlev - 1` convention.
- Added provenance fields for the continuum-alias type-99 path, including `type99_parent_maps_to_target_continuum_alias`, `type99_parent_global_index`, and `type99_parent_mapping_source = ucalc_idat_nidt_minus_3_zero_maps_to_target_continuum_alias`.
- Changed the default type-99 source fallback mode to `physical-only`: if `calt99/phint53hunt` cannot produce physical rates, the old `source_vector_gain_proxy` / scaffold proxy rows are skipped instead of assembled.  The legacy scaffold can be restored only for diagnostics with `--type99-source-fallback-mode legacy-proxy`.
- No intentional changes were made to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.96 - 2026-05-07

- Fixed the remaining type-99 activation bug exposed by the v0.3.95 C V/O VII reruns.  The type-99 `calt99/phint53hunt` source-code path now looks up target and parent levels from the explicit global element index rather than the legacy per-ion population table, so ATDB superlevels such as C V `sprlevls/sprlevlt` and explicit parent excited levels are available during `ucalc`-style mapping.
- This also provides the statistical weights needed by the reconstructed `phint53hunt` Milne `ans2d` integral, allowing `ans2 = rec*xnx` rows to become matrix-ready when the source-code type-99 closure evaluates successfully.
- Physical type-99 rows should now appear in `xstar_like_element_solver_global_superlevel_source_matrix_terms.csv` with `assembly_status = assembled_global_type99_calt99_phint53hunt` for C V/O VII rows whose `calt99/phint53hunt` closure is valid.
- No intentional changes were made to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.95 - 2026-05-07

- Fixed XSTAR `ucalc.f90` data-type 99 parent-level mapping after the v0.3.94 `calt99`/`phint53hunt` port.
- Mapped `idat(nidt-3)` to the explicit adjacent parent-ion level in the global matrix instead of using the target-ion continuum proxy row.
- Added parent-level provenance fields for type 99: `type99_ucalc_parent_ion_stage`, `type99_ucalc_parent_ion_level_index`, `type99_ucalc_idest2_local_matrix_level`, and `type99_parent_mapping_source`.
- Removed the incorrect direct-triplet-destination requirement for source-code type-99 assembly; destinations such as O VII levels 30/31 and C V levels 48/49 are allowed when their explicit parent levels exist.
- Physical type-99 rows now assemble as `assembled_global_type99_calt99_phint53hunt` against the explicit parent ion level when `calt99/phint53hunt` rates are available.
- No intentional changes to type-50 escape rates, type-71 `calt71`, type-77 `calt77`, geometry-derived line optical depth, `calc_emis_ion`, inverse recombination modes, or `calc_ion_rates/istruc`.

## v0.3.93 - 2026-05-07

- Ported the XSTAR `calt77.f90` evaluator for data-type 77 collisional coupling between ATDB superlevels and spectroscopic levels.
- `calt77` now evaluates the source-code downward superlevel-to-spectroscopic rate `cul` by log-density/log-temperature interpolation and computes the upward spectroscopic-to-superlevel rate `clu = cul * exp(-1.43817e8/(wav*T)) / gg`, including the XSTAR `ucalc.f90` temperature floor `T=max(T,2.8777e6/wav)`.
- Type-77 records are now assembled into the global/Lucy matrix with XSTAR `ucalc` semantics: `ans1=clu` for spectroscopic -> superlevel and `ans2=cul` for superlevel -> spectroscopic.
- Type-71 `calt71` remains active. Type-77 is now a true matrix coupling, not a branch-count proxy.
- The superlevel cascade/coupling matrix CSV now reports `type77_calt77_*` fields and separates type-71 and type-77 source-code provenance.
- No intentional changes to type-50 matrix escape rates, inverse recombination, geometry-derived line optical-depth construction, `calc_emis_ion`, `calc_ion_rates/istruc`, triplet coupling/suppression behavior, or non-Lucy solvers.

## v0.3.92 - 2026-05-07

- Ported the XSTAR `calt71.f90` evaluator for data type 71 radiative superlevel-to-spectroscopic cascade records.
- Type-71 audit rows now include source-code `type71_calt71_aij_s^-1`, wavelength, log-rate, grid dimensions, bracket indices, and evaluation status.
- Global type-71 cascade matrix assembly now uses `type71_calt71_aij_s^-1` when available instead of the old preview/scaffold value (`2.0` in many C V/O VII rows), with a legacy preview fallback only if calt71 cannot be evaluated.
- Type-71 branching weights now use calt71 A-values, so superlevel cascade branching and the full-global `xstar-lucy` path use the same source-code cascade rates.
- Kept the C V `full_global_xstar_tau0_calc_emis_ion` result as the regression benchmark and made no intentional changes to type-50 matrix rates, inverse recombination, geometry-derived line optical depth, `calc_emis_ion`, `calc_ion_rates/istruc`, triplet coupling/suppression, or non-Lucy solvers.

## v0.3.91 - 2026-05-07

- Added `examples/43_compare_xstar_detail_populations.py` for the next validation milestone after the C V triplet match.
- The new comparison utility reads a full-global solver output directory, extracts population rows from `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`, reports the recommended `full_global_xstar_tau0_calc_emis_ion` triplet row, and writes CSV/JSON/Markdown validation products.
- Optional external XSTAR detail population tables can be supplied as CSV or FITS and are matched by ion stage plus level index.
- The utility defaults to C V (`--element C --he-like-stage 5`) and is prepared for the next O VII validation step via `--element O --he-like-stage 7`.
- No intentional solver, matrix, optical-depth, `calc_emis_ion`, type-50, inverse-recombination, or `calc_ion_rates/istruc` physics changes from v0.3.90.

## v0.3.90 - Print and document recommended full-global emergent triplet comparison - 2026-05-07

- Updated `examples/42_xstar_like_element_solver_demo.py --print-summary` so the compact terminal summary reports the recommended full-global emergent line-output row, `full_global_xstar_tau0_calc_emis_ion`, instead of the obsolete simple per-ion triplet baseline.
- The printed summary now includes the recommended comparison case name, full-global emergent `f/i/r`, `R`, `G`, and target-aware L2 distance when that row is available.
- Documented `full_global_xstar_tau0_calc_emis_ion` as the recommended XSTAR C V triplet validation comparison case in the README.
- No intentional changes to population solving, type-50 matrix rates, geometry-derived optical-depth construction, `calc_emis_ion` emergent-line formulas, inverse recombination, `calc_ion_rates -> istruc`, triplet coupling/suppression behavior, or non-Lucy solvers.

## v0.3.89 - Geometry-derived XSTAR type-50 tau0 column for calc_emis_ion - 2026-05-07

- Derives the type-50 line optical-depth column for the `calc_emis_ion.f90` triplet emergent-line path from the XSTAR source-code geometry/transfer quantity `xpx*xeltp*delr` by default.
- Added `--xstar-line-column-source geometry|auto|manual|rt|xstar`; the default `geometry` computes the column from density, abundance, and zone thickness instead of using a hand-tuned equivalent column.
- Added `--xstar-line-zone-thickness-cm`, `--xstar-line-hydrogen-density-cm3`, `--xstar-line-electron-per-hydrogen`, and `--xstar-line-element-abundance` to provide the local XSTAR zone context when available.
- Preserves backward compatibility: `--xstar-line-column-source manual` uses `--xstar-line-column-density`, and `auto` uses a nonzero manual column if supplied.
- Reports the resolved source, `xpx`, `xeltp`, `delr`, geometry column, manual column, and source-code formula in `xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv`.
- No intentional changes to population solving, type-50 matrix rates, inverse recombination, `calc_ion_rates -> istruc` metadata behavior, triplet coupling/suppression behavior, or non-Lucy solvers.

## v0.3.88 - Fix type-50 line opacity atomic-mass fallback crash - 2026-05-06

- Fixed a v0.3.87 runtime crash in `_xstar_atomic_mass_amu_from_symbol()` caused by an undefined `SYMBOL_TO_Z` fallback reference during the new type-50 line optical-depth context construction.
- The helper now uses the local `_XSTAR_APPROX_ATOMIC_MASS_AMU` table and falls back safely to `1.0` amu for unknown symbols.
- No intentional changes to line optical-depth physics, `calc_emis_ion` emergent-line formulas, population solving, type-50 matrix rates, inverse recombination, `calc_ion_rates -> istruc` behavior, triplet coupling/suppression, or non-Lucy solvers.

## v0.3.87 - XSTAR type-50 line tau0 optical-depth context for calc_emis_ion - 2026-05-06

- Added XSTAR source-code line optical-depth construction for triplet emergent-line post-processing.
- Added CLI options `--xstar-line-column-density`, `--xstar-line-vturb-km-s`, `--xstar-line-cfrac`, `--xstar-line-tau1-fraction`, and `--xstar-line-tau2-fraction`.
- Reconstructs type-50 oscillator strength `flin`, thermal/turbulent width `vtherm`, line cross section `sigvtherm`, lower-level column, directional `tau0(1/2)`, and component-specific `ptmp1/ptmp2=pescl(tau0)` values.
- The emergent triplet comparison now uses `xstar_tau0_calc_emis_ion` rather than the old common matrix escape proxy, while retaining raw and transparent cases for reference.
- No intentional changes to population solving, type-50 population matrix rates, inverse recombination, `calc_ion_rates -> istruc` metadata behavior, or non-Lucy solvers.

## v0.3.86 - XSTAR calc_emis_ion emergent triplet line construction - 2026-05-06

- Added `xstar_like_element_solver_calc_emis_ion_triplet_emergent.csv`, which ports the XSTAR `calc_emis_ion.f90` triplet line-output construction for selected He-like triplet records.
- The new table reports the source-code channels `ptmp1` and `ptmp2`, transparent `tau0=0,cfrac=0` output, active matrix type-50 escape/pumping output, and attenuation relative to raw `pop*A*E`.
- Implemented the XSTAR `pescl.f90` line escape function and the `calc_emis_ion.f90` type-4/type-9 channel formulas.
- Uses the `ucalc.f90` type-50 source-code orientation after the internal swap: `ans1` is lower-to-upper photoexcitation/pumping and `ans2` is upper-to-lower escaped decay.
- Adds compact `full_global_raw_pop_A_E`, `full_global_transparent_tau0_calc_emis_ion`, and `full_global_matrix_escape_calc_emis_ion` summary rows to `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`.
- No intentional changes to the population solver, type-50 matrix rates, inverse recombination, `calc_ion_rates -> istruc` metadata behavior, triplet coupling/suppression options, or non-Lucy solvers.


- Implements the exact XSTAR `msolvelucy.f90` fixed-point sub-iteration for the full-global `xstar-lucy` path.
- Expands reconstructed two-rate pairs into a four-row `ajisb` list and uses that list for the source-code `riu/rui/ril/rli` `nit2` loop after each condensed superlevel solve.
- Removes the previous nonnegative clipping in the fixed-point update so the update uses the current `x(nn)` directly, matching the source routine.
- Reports fixed-point metadata in `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`: `xstar_msolvelucy_fixed_point_mode`, `xstar_msolvelucy_fixed_point_population_clipping`, `xstar_lucy_nit2_last`, `xstar_lucy_nit2_total`, and final `riu/rui/ril/rli` sums.
- Adds per-level final `xstar_msolvelucy_riu`, `xstar_msolvelucy_rui`, `xstar_msolvelucy_ril`, and `xstar_msolvelucy_rli` columns for population-row inspection.
- Keeps v0.3.83/v0.3.84 behavior that `calc_ion_rates -> istruc` targets are metadata/seed-structure information, not hard per-stage Lucy constraints.
- No intentional changes to type-50 escape rates, inverse-recombination rates, matrix term construction, triplet suppression/coupling options, or non-Lucy solvers.

## v0.3.85 - 2026-05-06

- Implements the exact XSTAR `msolvelucy.f90` fixed-point sub-iteration for the full-global `xstar-lucy` path.
- Expands reconstructed two-rate pairs into a four-row `ajisb` list and uses that list for the source-code `riu/rui/ril/rli` `nit2` loop after each condensed superlevel solve.
- Removes the previous nonnegative clipping in the fixed-point update so the update uses the current `x(nn)` directly, matching the source routine.
- Reports fixed-point metadata in `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`: `xstar_msolvelucy_fixed_point_mode`, `xstar_msolvelucy_fixed_point_population_clipping`, `xstar_lucy_nit2_last`, `xstar_lucy_nit2_total`, and final `riu/rui/ril/rli` sums.
- Adds per-level final `xstar_msolvelucy_riu`, `xstar_msolvelucy_rui`, `xstar_msolvelucy_ril`, and `xstar_msolvelucy_rli` columns for population-row inspection.
- Keeps v0.3.83/v0.3.84 behavior that `calc_ion_rates -> istruc` targets are metadata/seed-structure information, not hard per-stage Lucy constraints.
- No intentional changes to type-50 escape rates, inverse-recombination rates, matrix term construction, triplet suppression/coupling options, or non-Lucy solvers.

## v0.3.84 - 2026-05-06

- Implements the direct XSTAR `levwkelement` / `msolvelucy` population-construction step for the full-global `xstar-lucy` solver.
- Reconstructs XSTAR-like `ajisb` two-rate pairs from positive off-diagonal matrix rates and uses those pairs to build the condensed superlevel matrix with the same `rr(level)=x(level)/p(nsup)` weighting used in `msolvelucy.f90`.
- Replaces the previous direct dense-matrix condensation in the Lucy path with source-code-style `p`, `rr`, `bmatsup`, `ipmat2`, and `nsup` bookkeeping.
- Population rows now report XSTAR-style population-construction quantities: `xstar_ipmat2_index`, `xstar_nsup`, `xstar_superlevel_population_p`, `xstar_rr_fraction_within_superlevel`, `xstar_levwkelement_rnise`, `xstar_bileve_departure_coefficient`, and `xstar_xileve_emissivity_population`.
- Summary rows report `xstar_population_construction_mode`, `xstar_msolvelucy_uses_fortran_ajisb_pairs`, `xstar_msolvelucy_n_two_rate_pairs`, `xstar_msolvelucy_n_ajisb_entries_equivalent`, and final `p(superlevel)` JSON.
- Keeps v0.3.83 behavior that `calc_ion_rates -> istruc` targets are metadata/seed-structure information, not hard per-stage Lucy constraints.
- No intentional changes to type-50 escape rates, inverse-recombination rates, triplet coupling, suppression behavior, or default non-Lucy solvers.

# Changelog

## v0.3.83 - 2026-05-06

- Fixed the `--ion-fraction-closure xstar-calc-ion-rates` interpretation by following the XSTAR source path more closely.  In `calc_hmc_element.f90`, `calc_ion_rates -> istruc` is used before `levwkelement` to determine ion limits and seed structure; `msolvelucy.f90` then solves the condensed superlevel system with a total number-conservation row, not with hard per-ion `istruc` constraints.
- The pre-matrix source-code-gated `pirti`/`rrrti` targets are still reported in `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv` and full-global metadata, but they are no longer applied as hard stage-normalization constraints during Lucy iteration.
- `xstar_istruc_ion_fraction_targets_applied` is now `False` for this source-code path, and `xstar_istruc_ion_fraction_targets_application_status` explains that XSTAR uses the rates for ion limits/levwkelement seeding rather than hard Lucy constraints.
- No intentional changes to type-50 rates, inverse-recombination rates, matrix assembly, triplet coupling, suppression behavior, or default `--ion-fraction-closure none` behavior.

## v0.3.82 - 2026-05-06

- Tightened the pre-matrix XSTAR `calc_ion_rates` / `istruc` reconstruction to follow the visible `calc_ion_rates.f90` source-code gates instead of summing every level-resolved bound-free candidate.
- `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv` now marks each rate row with `calc_ion_rates_pirti_included`, `calc_ion_rates_rrrti_included`, `calc_ion_rates_total_included`, `calc_ion_rates_equation_role`, and `calc_ion_rates_inclusion_reason`.
- Level-resolved type-53 `phint53` Milne `rrrt`/`ans2`, independent `milne.f90` `alpha*ne`, and type-74 `calt74` weighted-alpha inverse terms are retained as recombination-side candidates but are explicitly excluded from the source-code `rrrti` total unless they are total rate-type 6/8 rows.
- The `--ion-fraction-closure xstar-calc-ion-rates` closure now derives its targets from source-code-gated `pirti`/`rrrti` totals. Candidate totals remain reported separately in metadata for comparison.
- No intentional changes to type-50 escape treatment, topology modes, triplet-coupling suppression, or default `--ion-fraction-closure none` behavior.

## v0.3.81 - 2026-05-06

- Bug-fix release for the v0.3.80 pre-matrix XSTAR `calc_ion_rates` / `istruc` closure diagnostics.
- Fixed `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv` writing by returning `calc_ion_rates_istruc_audit` rows from `solve_element_reference(...)`.
- Fixed `xstar_istruc_ion_fraction_targets_json` population for `--ion-fraction-closure xstar-calc-ion-rates` / `calc-ion-rates`; v0.3.80 only applied target extraction for the legacy `xstar-istruc` spelling.
- Added explicit full-global metadata flags: `xstar_istruc_ion_fraction_targets_applied` and `xstar_istruc_ion_fraction_targets_application_status`, so runs report whether stage targets were applied, skipped due to missing/invalid targets, or not requested.
- No intentional solver, rate, matrix-assembly, type-50, inverse-recombination, triplet-coupling, suppression, or physical-behavior changes beyond the requested metadata/audit handoff fixes.

## v0.3.80 - 2026-05-06

- Added `xstar_like_element_solver_calc_ion_rates_istruc_audit.csv`, a pre-matrix XSTAR `calc_ion_rates` / `istruc` reconstruction for adjacent C V/C VI ion-stage closure.
- Added `--ion-fraction-closure xstar-calc-ion-rates` and changed `xstar-istruc` to use the pre-matrix ion-rate audit when available instead of summed full-global matrix entries.
- The audit separates available ion-stage rates into photoionization, radiative recombination, dielectronic recombination, collisional ionization, and three-body recombination contributions from type 53, type 74, type 1, and type 57 diagnostics.
- Full-global solve metadata now records whether ion-fraction targets came from the pre-matrix `calc_ion_rates` audit or the older assembled-matrix fallback.
- Default `--ion-fraction-closure none` remains unchanged; no default solver/rate behavior changes.

## v0.3.79 - 2026-05-06

- Added experimental `--ion-fraction-closure none|xstar-istruc`.
- `xstar-istruc` derives a two-stage XSTAR `calc_ion_rates`/`istruc`-style ion fraction closure from summed inter-stage matrix rates, using `x_low=R/(I+R)` and `x_high=I/(I+R)`.
- The `xstar-lucy` population iteration can now apply these ion-stage targets during the level-population fixed-point update, so the aliased parent continuum/parent ground is constrained consistently with the adjacent-stage balance rather than only by global `sum n_i = 1`.
- Full-global output records `xstar_istruc_ion_fraction_closure_requested`, `xstar_istruc_ion_fraction_closure_status`, `xstar_istruc_ion_fraction_targets_json`, and `xstar_istruc_ion_fraction_flow_rates_json`.
- Existing behavior remains available with the default `--ion-fraction-closure none`.
- Validation: `4 passed, 1 skipped`.

## v0.3.78 - 2026-05-06

Direct XSTAR `ucalc` inverse-recombination implementation step.

- Added `--inverse-recombination-mode xstar-ucalc` as an experimental source-code path, while keeping the older `type53-milne-diagnostic`, `type74-direct-diagnostic`, and `type53-type74` proxy modes for regression.
- In `xstar-ucalc` mode, the type-53 inverse matrix terms are assembled from the source-code `phint53.f90` Milne `ans2` audit (`source_code_phint53_milne_ans2_rrrt_s^-1`) instead of the older scaled detailed-balance proxy.
- In `xstar-ucalc` mode, type-74 inverse terms use the source-aligned `calt74` alpha path with the XSTAR `gglo/ggup` correction; the older direct type-74 inverse proxy is disabled for this mode.
- The assembled type-53 rows are still marked experimental because exact XSTAR runtime arrays (`ethion`, `ethtmp`, `emltlv`) and escape factors are reconstructed, but the full-global matrix now uses the audited source-code closure rather than empirical inverse-rate scaling.
- No intentional changes to type-50 treatment, topology modes, atomic data decoding, triplet-coupling suppression, or final `calc_emis` accounting.

## v0.3.77 - 2026-05-06

Direct XSTAR-code implementation step for the full-global population path.

- Applies the XSTAR `calc_hmc_element.f90` continuum-alias rule at matrix-index level for `--full-global-topology xstar-continuum-alias` and `xstar-continuum-alias-superlevels`: explicit continuum / parent-continuum rows are remapped to the parent-ion ground row before assembling the dense full-global matrix. This is closer to XSTAR's `ipmat = ipmat + nlev - 1` topology than the v0.3.76 superlevel-membership-only alias.
- Initializes the `xstar-lucy` solver with an XSTAR `levwk.f90` / `levwkelement.f90`-style LTE/partition seed when temperature and electron density are available, falling back to statistical weights only if the source-code seed cannot be evaluated.
- Adds output metadata: `xstar_matrix_continuum_alias_count`, `xstar_matrix_continuum_alias_json`, and `xstar_lucy_population_seed_mode`.
- Keeps the existing `explicit-current` mode available for regression comparison. No intentional changes to atomic data decoding, type-50 escape semantics, type-53/type-74 rate values, triplet-coupling suppression, or final line-output accounting.

## v0.3.76 - 2026-05-05

- Added experimental `--full-global-topology explicit-current|xstar-continuum-alias|xstar-continuum-alias-superlevels` for the full-global `xstar-lucy` solver.
- `explicit-current` is the default and preserves v0.3.75 behavior.
- `xstar-continuum-alias` maps continuum / parent-continuum rows into the same condensed Lucy group as the parent ion ground state, following the XSTAR `ipmat = ipmat + nlev - 1` topology.
- `xstar-continuum-alias-superlevels` also groups levels 2..nlev-1 into one excited `nsup` group per ion, matching the source-code `calc_hmc_element.f90` grouping rule.
- The modes are experimental diagnostics; they change only the condensed `xstar-lucy` membership used by the full-global normalized solve, not the assembled matrix terms or default physical/rate behavior.
- Full-global solve output now records `full_global_topology_requested`, `xstar_lucy_topology_mode`, and `xstar_lucy_super_keys_json`.

## v0.3.75 - 2026-05-05

- Added `xstar_like_element_solver_xstar_matrix_topology_audit.csv`, an audit-only comparison between the current explicit Python global-index topology and the visible XSTAR `calc_hmc_element.f90` element matrix topology.
- The audit records the XSTAR `ipmat = ipmat + nlev - 1` continuum-alias rule, parent-ground alias candidates, and the XSTAR `nsup` grouping rule where level 1 is an independent ground group and levels 2..nlev-1 are grouped into one excited-state superlevel.
- Added summary columns showing how many current rows XSTAR would keep as independent rows versus condense or alias.
- No intentional changes to solver behavior, matrix assembly, type-50 treatment, recombination rates, triplet coupling, suppression behavior, or physical-rate behavior.

## v0.3.74 - 2026-05-05

- Bug-fix release for the v0.3.73 Milne-integral audit handoff.
- Fixed `build_type53_type74_ucalc_closure_audit_rows(...)` so its signature accepts the new `type53_rate_audit_rows` keyword passed by `solve_element_reference(...)`.
- This restores the v0.3.71 closure audit and allows the v0.3.73 `phint53`/`milne` raw cross-section-grid join to run in the same demo call.
- No intentional solver, matrix assembly, type-50 treatment, inverse-recombination rate, triplet-coupling, suppression, or physical-rate behavior changes.

## v0.3.73 - 2026-05-05

- Bug-fix release for the v0.3.72 `phint53` Milne integral audit.
- `xstar_like_element_solver_phint53_milne_integral_audit.csv` now reads the full type-53 raw real arrays from `type53_rate_audit_rows` when the later `type53_phint53_rate_audit_rows` do not carry the original cross-section grid.
- Adds `type53_cross_section_source` and `type53_n_cross_section_pairs_available` columns to make this provenance explicit.
- No intentional solver, matrix, type-50, recombination-rate, triplet-coupling, or physical-rate behavior changes.

## v0.3.72 - 2026-05-05

- Added `xstar_like_element_solver_phint53_milne_integral_audit.csv`.
- Ported/source-audited the type-53 recombination-side `phint53.f90` Milne `ans2` integral terms, including the reconstructed LTE seed `rnist`, the `bbnurjp` factor, Boltzmann suppression, and `ptmp1+ptmp2` escape multiplier placeholder.
- Added a Python audit port of XSTAR `milne.f90` and `intin.f90`, matching the debug check in `ucalc.f90` where `alphamilne*xnx` is compared with `phint53` `ans2`.
- The new audit compares the source-code Milne estimates against the current Python type-53 Milne proxy and summarizes f/i/r/other component source rates.
- Diagnostic-only release: no intentional changes to solver behavior, matrix assembly, default `raw-A` behavior, type-50 escape diagnostics, inverse-recombination rates, triplet-coupling logic, suppression behavior, or physical-rate behavior.

## v0.3.71 - 2026-05-05

- Added `xstar_like_element_solver_type53_type74_ucalc_closure_audit.csv`, a source-code-aligned read-only audit for the type-53/type-74 recombination closure that likely controls the remaining C V f/r mismatch after the type-50 escape correction.
- The new audit compares current Python proxy rates against XSTAR `ucalc.f90` semantics for:
  - type 53 `phint53` forward photoionization (`ans1`) and pending Milne inverse recombination (`ans2`) with LTE/Saha/statistical diagnostic ingredients;
  - type 74 `calt74` forward delta-photoionization and inverse DR alpha after the XSTAR `gglo/ggup` statistical-weight correction;
  - older direct type-74 inverse proxy rates versus the source-aligned `calt74` weighted alpha path.
- The audit writes per-record rows plus component summaries for f/i/r/other inverse-source proxies, so f/r source imbalance can be inspected without running another empirical scale scan.
- No solver, matrix assembly, default `raw-A` type-50 behavior, type-50 escape diagnostic semantics, inverse-recombination rates, or physical-rate behavior is intentionally changed.

## v0.3.70 - 2026-05-05

- Added `xstar_like_element_solver_type50_escape_factor_scan.csv`, a controlled diagnostic scan over proxy XSTAR `ucalc` type-50 escape factors.
- Added `--type50-escape-factor-scan`, defaulting to `0.2,0.25,0.3,0.35,0.4,0.45,0.5,0.75,1`.
- The scan rebuilds the bound-bound matrix with `type50_bound_bound_treatment=xstar-escape` for each factor, holds the other primary matrix components fixed, solves the full-global normalized system, and reports f/i/r, R, G, L2-to-target, target-aware deltas, and the summed `1s2p 3P_J -> 1s2s 3S1` raw/escaped rates.
- The default primary run remains unchanged unless the user explicitly selects `--type50-bound-bound-treatment xstar-escape` or `xstar-escape-photoexcitation`.
- The scan is diagnostic only until real XSTAR optical-depth, `pescl`/`pescv`, `bremsa`, and `flinabs` contexts are ported.

## v0.3.69 - 2026-05-05

- Bug-fix release for v0.3.68.
- Fixes the v0.3.67 type-50 `xstar-escape` treatment so the assembled global bound-bound matrix uses the effective escaped rate in `signed_rate_s^-1`, not only in the audit `rate_s^-1` column.
- The affected rows are the off-diagonal gain and diagonal loss entries created by `build_global_bound_bound_matrix_terms(...)`; they now use `effective_rate` and `-effective_rate`.
- The default `raw-A` treatment remains numerically unchanged.
- No intentional changes to type-50 audit semantics, solver normalization, suppression logic, physical rate decoding, or `calc_emis` audits.

## v0.3.68 - 2026-05-05

- Bug-fix release for v0.3.67.
- Fixes `build_global_superlevel_cascade_matrix_terms(...)` so type-71 superlevel cascade rows use `float(rate)` for their signed gain/loss terms instead of the undefined local variable `effective_rate`.
- This restores the full diagnostic demo path when `--type50-bound-bound-treatment xstar-escape` or `xstar-escape-photoexcitation` is used.
- No intentional solver, type-50 treatment, matrix-physics, triplet-coupling, suppression, or physical-rate behavior changes beyond fixing the writer/assembly NameError.

# v0.3.67 - 2026-05-05

- Add `xstar_like_element_solver_type50_ucalc_rate_audit.csv`, a diagnostic audit of XSTAR `ucalc.f90` type-50 bound-bound rate semantics.
- Add `--type50-bound-bound-treatment raw-A|xstar-escape|xstar-escape-photoexcitation`. The default `raw-A` preserves v0.3.66 behavior.
- Add `--type50-escape-factor` and `--type50-photoexcitation-scale` controlled proxy parameters for diagnostic tests of escaped downward decay and lower-to-upper radiative pumping.
- The audit reports raw A-values, proxy `ptmp1/ptmp2`, escaped decay rates, pumping proxies, and the He-like `1s2p 3P_J -> 1s2s 3S1` UV drain sum.
- No intentional default solver, matrix assembly, triplet-coupling suppression, or physical-rate behavior changes when using the default `raw-A` mode.

## v0.3.66

- Fixed `write_element_solver_outputs` so `calc_emis_context_audit_rows` is defined from `result.get("calc_emis_context_audit", [])` before writing `xstar_like_element_solver_calc_emis_context_audit.csv`.
- Added the v0.3.65 context-audit summary into the output summary when rows are present.
- No intentional changes to the solver, matrix assembly, triplet-coupling treatment, suppression behavior, or physical rate behavior.

## v0.3.65

- Added `xstar_like_element_solver_calc_emis_context_audit.csv`, a diagnostic companion to the v0.3.64 transparent `calc_emis_ion` triplet audit.
- The new audit reports available matrix-population runtime context for each f/i/r candidate line: source-population-weighted feed (`alpha`), loss (`gamma`), dominant feed/loss components and records, current transparent `ucalc` placeholders, and abundance/escape placeholders.
- Added component-level required line-accounting multipliers (`target/current` and an intercombination-only scale) to test whether `calc_emis_ion` escape/net-emissivity/strong-line accounting could fix the remaining C V intercombination deficit without changing populations.
- No solver, matrix assembly, suppression treatment, or physical rate behavior is intentionally changed.

## v0.3.64

- Added `xstar_like_element_solver_calc_emis_triplet_audit.csv`, a `calc_emis_ion`-style line-output diagnostic for the He-like triplet.
- The audit reports, for each f/i/r candidate line, lower/upper level populations, A-values, photon energy, transparent `pop*A*E` emissivity, transparent `calc_emis_ion` channel proxies, `ans1/ans2` placeholders, `ptmp1/ptmp2` escape placeholders, and strong-line selection status.
- Added component-level summaries for f/i/r fractions under the transparent `calc_emis_ion` proxy so line-output/accounting differences can be separated from population-balance differences.
- No solver, matrix assembly, suppression treatment, or physical rate behavior is intentionally changed.

# Changelog

## v0.3.63

- Adds a controlled diagnostic switch for the suspicious He-like `1s2p 3P_J -> 1s2s 3S1` type-50 radiative population-transfer drains identified in v0.3.62.
- New CLI option: `--triplet-coupling-treatment normal|audit-only|suppress-3p-to-3s-radiative`.  The default `normal` leaves solver behavior unchanged.  The suppression mode removes only those three off-diagonal gains and their diagonal-loss partners from the primary full-global normalized solve.
- Adds `xstar_like_element_solver_triplet_coupling_suppression_comparison.csv`, which always compares the normal full-global XSTAR-Lucy solution against the diagnostic suppressed solution and lists the exact matrix terms removed in the suppressed case.
- The comparison keeps intercombination-to-ground, forbidden-to-ground, resonance, type-63 collisional `3S1 <-> 3P_J`, type-53, type-71, type-74, type-99, and type-1 terms intact.
- This is a matrix-semantics diagnostic only.  Suppressing type-50 `3P_J -> 3S1` terms is not treated as a physical correction unless follow-up source-code validation proves XSTAR excludes or reclassifies these records.

## v0.3.62

- Added `xstar_like_element_solver_triplet_coupling_record_audit.csv` for source-code-aligned validation of the direct `1s2s 3S1 <-> 1s2p 3P_J` coupling records that dominate the C V intercombination bottleneck.
- The audit selects f/i off-diagonal matrix terms and their diagonal partners, infers type-50 radiative A-value paths versus type-63/67/68/69 density-scaled collisional partners, and reports source-population-weighted feed/loss contributions.
- The summary highlights whether the large `3P_J -> 3S1` radiative-drain terms overwhelm collisional `3S1 -> 3P_J` feeds at the current density and radiation context.
- No solver or physical-rate behavior is intentionally changed.

## v0.3.61

- Added source-code-aligned triplet α/γ diagnostics for the full-global XSTAR-Lucy solution.
- New output: `xstar_like_element_solver_triplet_alpha_gamma_audit.csv`, which reports source-population-weighted `alpha = sum_j n_j R(i<-j)`, loss `gamma`, `alpha/gamma` population proxies, dominant feed/loss terms, and f/i/r component summaries.
- Added triplet emissivity/branching diagnostics.
- New output: `xstar_like_element_solver_triplet_emissivity_branch_audit.csv`, which lists f/i/r candidate line records with upper/lower levels, A-values, branching fractions from decoded lines, solved upper/lower populations, transparent `pop*A*E` emissivity proxies, and the missing XSTAR `calc_emis_ion` contexts (`ucalc` net emissivity, escape probabilities, `cfrac`, and strong-line filtering).
- No solver or physical-rate behavior is intentionally changed; this version is an audit layer to decide whether the remaining low intercombination component is a population-balance issue or a line-emissivity/branching/accounting issue.

## v0.3.60

- Added `xstar_like_element_solver_intercombination_feed_audit.csv`, a detailed audit of all current full-global matrix routes that feed, branch out of, or diagonally drain the He-like intercombination upper levels (`1s2p 3P_J`).
- Added `xstar_like_element_solver_triplet_component_balance_audit.csv`, summarising f/i/r populations, incoming rates, radiative losses, type-71 cascade feeds, type-53 Milne inverse feeds, type-74 inverse feeds, collisional couplings, and type-53 photoionization losses.
- Added summary entries for both new audits to `xstar_like_element_solver_summary.json` and the Markdown summary.
- No solver or physics rates are intentionally changed; v0.3.60 is an audit layer for the low-intercombination bottleneck identified by v0.3.59.

## v0.3.59

- Added a refined inverse-recombination scale scan around the promising C V region found in v0.3.58.
- Added `--type53-milne-refined-scale` and `--type74-inverse-refined-scale` to `examples/42_xstar_like_element_solver_demo.py`.
- Wrote `xstar_like_element_solver_inverse_recombination_refined_scale_scan.csv`, using a narrower default grid: type-53 Milne scales `1e9,3e9,1e10,3e10,1e11` and type-74 inverse scales `1e8,3e8,1e9,3e9,1e10,3e10,1e11,3e11,1e12`.
- Added target-aware columns to the refined scan, including f/r-only L2, intercombination absolute error, i/target ratio, and an intercombination-weighted diagnostic score.
- Kept the XSTAR-Lucy global solver and existing physical/proxy limitations unchanged.

## v0.3.58

- Improves the diagnostic radiation/bremsa context used by the type-53 `phint53` and type-74 `calt74` ports.
- Adds explicit XSTAR-style `epi`/`bremsa`/`bremsint` bookkeeping through `xstar_like_element_solver_bremsa_context.csv`.
- Adds configurable radiation controls to the demo: `--radiation-bremsa-scale`, `--radiation-energy-min-eV`, `--radiation-energy-max-eV`, `--radiation-n-energy-grid`, and `--radiation-powerlaw-index`.
- Extends `--radiation-field-mode` with `powerlaw`/`xstar-powerlaw`; the diagnostic bremsa array is now reused consistently by `phint53` and `calt74`.
- Keeps the full-global XSTAR-Lucy normalization solve unchanged: one row is replaced by `sum_i n_i = 1`, source-vector proxy rows are handled as before, and the solve remains diagnostic until real XSTAR radiation transfer, Milne inverse recombination, opacity/escape probabilities, physical type-99/type-1 rates, and closed continuum balance are ported.

## v0.3.57

- Adds a source-aligned type-74 `calt74` diagnostic path.
- Evaluates both `rate` and `alpha` following `xstarlib/src/calt74.f90`, including delta-resonance interpolation on the diagnostic radiation grid and the `ucalc` statistical-weight correction `alpha *= gglo/ggup`.
- Writes `xstar_like_element_solver_type74_calt74_rate_audit.csv` and `xstar_like_element_solver_global_type74_calt74_matrix_terms.csv`.
- The full-global matrix now prefers the source-aligned type-74 calt74 inverse topology rows when available, falling back to the older type-74 inverse proxy rows otherwise.
- Still diagnostic: absolute forward rates depend on placeholder `bremsa`, and parent-continuum closure remains pending.

## v0.3.56

- Checked the XSTAR source path for inverse recombination before extending the scaffold:
  type-53 calls `phint53`, and XSTAR also compares the recombination output against `milne(temp, ntmp, etmpp, stmpp, ett/13.6, ...)`; type-74 DR-delta rates are handled through `calt74(temp, ncn2, epi, bremsa, ..., rate, alpha)`, with `alpha` scaled by the lower/upper statistical-weight ratio.
- Added independent diagnostic inverse-recombination scale controls:
  `--type53-milne-scale` and `--type74-inverse-scale`.
- The first value of each scale list is used for the primary type-53 Milne/type-74 inverse audit and full-global matrix assembly; the full lists are used by `xstar_like_element_solver_inverse_recombination_scale_scan.csv`.
- Expanded `xstar_like_element_solver_inverse_recombination_scale_scan.csv` from a single placeholder row to independent type-53-Milne scans, independent type-74 inverse scans, and a compact cross-grid when the requested lists are modest.
- This remains a diagnostic/proxy scan: true XSTAR Milne inverse recombination, physical type-74 DR balance, real `bremsa` radiation context, opacity/escape probabilities, and closed continuum balance remain pending.

## v0.3.55

- Added `--inverse-recombination-mode none|type53-milne-diagnostic|type74-direct-diagnostic|type53-type74` to the element-solver demo.
- Added diagnostic type-53 Milne inverse-recombination scaffold outputs:
  - `xstar_like_element_solver_type53_milne_inverse_audit.csv`
  - `xstar_like_element_solver_global_type53_milne_matrix_terms.csv`
- Added diagnostic type-74 direct DR-delta inverse-recombination scaffold outputs:
  - `xstar_like_element_solver_type74_inverse_recombination_audit.csv`
  - `xstar_like_element_solver_global_type74_inverse_matrix_terms.csv`
- Added `xstar_like_element_solver_inverse_recombination_scale_scan.csv` as a first solve-context audit for inverse-recombination modes.
- The inverse terms are included in `xstar_like_element_solver_full_global_matrix_terms.csv` only when enabled by mode, but remain explicitly marked as diagnostic/proxy topology. True XSTAR Milne inverse recombination, physical type-74 DR balance, real radiation context, and closed continuum balance remain pending.

## v0.3.54

- Added a type-53 `phint53` scale scan for the full-global XSTAR-Lucy diagnostic path.
- `--type53-phint53-scale` now accepts comma-separated values, e.g. `1,1e5,1e10,1e15,1e18,1e20`; the first value is used for the primary audit/matrix, and all values are scanned in `xstar_like_element_solver_type53_phint53_scale_scan.csv`.
- Added `xstar_like_element_solver_radiation_normalization_audit.csv` to report the placeholder radiation-grid/bremsa normalization used by the first `phint53` forward-kernel diagnostic and the scale needed to reach reference total rates.
- Added summary metadata for the radiation-normalization audit and `phint53` scale scan.
- The phint53 kernel remains diagnostic: the real XSTAR radiation field, Milne inverse recombination, opacity/escape probabilities, and physical type-99/type-1 rates are still pending.

## v0.3.53

- Fixes the v0.3.52 `NameError: name '_sum_float' is not defined` crash in the type-53 `phint53` audit summary path.
- Adds a module-level `_sum_float(rows, col)` helper used by both `xstar_like_element_solver_type53_phint53_rate_audit.csv` and `xstar_like_element_solver_global_type53_phint53_matrix_terms.csv` summary generation.
- No intentional physics change: XSTAR-Lucy remains the preferred full-global diagnostic solver, and the type-53 `phint53` forward-kernel diagnostic remains a first audit/topology port with placeholder radiation context.

## v0.3.52

- Makes `--full-global-linear-solver xstar-lucy` the preferred/default diagnostic solver for the full-global path.
- Adds the first type-53 `phint53` photoionization-kernel diagnostic port.
- Adds `--type53-phint53-scale` for controlled rate scaling of the new phint53-kernel diagnostic.
- Writes `xstar_like_element_solver_type53_phint53_rate_audit.csv` with decoded type-53 cross-section pairs, placeholder radiation-grid integration diagnostics, and forward photoionization rates.
- Writes `xstar_like_element_solver_global_type53_phint53_matrix_terms.csv` with physical-kernel type-53 matrix topology rows.
- `xstar_like_element_solver_full_global_matrix_terms.csv` now prefers type-53 phint53-kernel rows when any are matrix-ready, and falls back to the older flat proxy topology otherwise.
- The phint53 forward photoionization kernel is ported, but the radiation field is still a placeholder; Milne inverse recombination, opacity/escape-probability context, and the real XSTAR continuum are still pending.

## v0.3.46

- Added a diagnostic global bound-bound+type71+type99-proxy+type53-flat-proxy solve comparison.
- New output: `xstar_like_element_solver_global_bound_bound_type71_type99_type53_proxy_solve_comparison.csv`.
- The extended diagnostic solve uses the existing He-like global-index block, nonphysical type-99 source-vector proxy rows, and type-53 flat photoionization proxy sinks via `sink_rates`.
- Type-53 off-diagonal parent-continuum topology rows are still not included in the local He-like solve because the full adjacent-ion parent-continuum population is not solved yet.
- No physical XSTAR `phint53` or Milne inverse-recombination rates are evaluated in this release.

## v0.3.45

- Added a diagnostic flat-field type-53 photoionization-rate proxy.
- Added `--type53-flat-proxy-scale` to `examples/42_xstar_like_element_solver_demo.py`.
- Added `xstar_like_element_solver_type53_flat_proxy_rate_audit.csv`.
- Added `xstar_like_element_solver_global_type53_flat_proxy_matrix_terms.csv`.
- The proxy maps `M[continuum_or_parent,bound] += rate_proxy` and `M[bound,bound] -= rate_proxy` topology only; it is not assembled into the solved matrix.
- Physical XSTAR `phint53`/Milne rates are still not evaluated.

## v0.3.44

- Fixes a helper-name collision introduced in v0.3.43: the table-building `_global_index_lookup(rows)` helper is preserved for global matrix scaffolds, and the single-row query helper used by the type-53 audit is renamed to `_global_index_lookup_one(rows, ion_stage, level_index)`.
- This fixes the `TypeError: _global_index_lookup() missing 2 required positional arguments` crash when running with `--radiation-field-mode`.
- No physics behavior is intentionally changed; type-53 remains audit/scaffold-only and is not assembled into the matrix.

## v0.3.43

- Adds the first Phase-E type-53 radiation-context scaffold for the XSTAR-like element solver.
- Adds `--radiation-field-mode none|flat|blackbody|table` to `examples/42_xstar_like_element_solver_demo.py`.
- Writes `xstar_like_element_solver_radiation_context.csv` describing the placeholder radiation grid/status needed by future `phint53` and Milne inverse-recombination ports.
- Writes `xstar_like_element_solver_type53_rate_audit.csv`, mapping type-53 records onto explicit bound-level and continuum/parent global indices where possible and reporting missing physical context.
- Does not evaluate physical type-53 photoionization or inverse recombination rates and does not assemble type-53 terms into the matrix.

## v0.3.42

- Fixes the v0.3.41 packaging/signature regression for `--type99-proxy-scale`: `solve_element_reference()` now actually accepts the `type99_proxy_scale` keyword and passes it into the type-99 proxy scale-scan builder.
- Adds no intended physics changes; the type-99 proxy scale scan remains diagnostic-only.

## v0.3.41

- Bug fix: add the missing `type99_proxy_scale` keyword argument to `solve_element_reference()`.
- This fixes the `TypeError: solve_element_reference() got an unexpected keyword argument 'type99_proxy_scale'` raised by `examples/42_xstar_like_element_solver_demo.py` in v0.3.40.
- No physics behavior is intentionally changed; the type-99 proxy scale scan remains diagnostic-only.

## v0.3.40

- Added a diagnostic type-99 proxy source scale scan for the global bound-bound+type71 block.
- `examples/42_xstar_like_element_solver_demo.py` now accepts `--type99-proxy-scale`, with comma-separated lists such as `0,1e-8,1e-6,1e-4,1e-2,1,1e2`.
- New output: `xstar_like_element_solver_type99_proxy_scale_scan.csv`.
- For each scale, the scan multiplies only the nonphysical type-99 `source_vector_gain_proxy` rows, solves the He-like global-index bound-bound+type71 diagnostic block, and reports f/i/r, R, G, L2 distance to the C V target, superlevel population sum, source totals, and solver status.
- Type-99 `phint53pl` physical rates are still not evaluated; this remains a diagnostic proxy-normalization scan and not the final element-wide coupled matrix solve.

## v0.3.39

- Added a diagnostic global bound-bound+type71+type99-proxy solve comparison for the pure-Python XSTAR-like element-solver scaffold.
- New output: `xstar_like_element_solver_global_bound_bound_type71_type99_proxy_solve_comparison.csv`.
- The comparison assembles the He-like global-index block from bound-bound matrix terms plus type-71 superlevel-cascade triplets, then adds v0.3.38 type-99 `source_vector_gain_proxy` rows to the source vector.
- Reports the resulting f/i/r, R, G, L2 distance to the C V XSTAR target, source-vector totals, superlevel population sum, and level-by-level population differences.
- The type-99 terms remain nonphysical proxy values based on audit coefficients/counts; no `phint53pl` physical rates are evaluated and the full element-wide adjacent-ion matrix is still not solved.

## v0.3.38

- Added a diagnostic global-index type-99 superlevel source scaffold.
- New output: `xstar_like_element_solver_global_superlevel_source_matrix_terms.csv`.
- Maps type-99 source candidates from `xstar_like_element_solver_superlevel_source_audit.csv` onto explicit superlevel `global_index` rows.
- Writes source-vector proxy rows and parent-continuum-to-superlevel matrix proxy rows when a parent-continuum/continuum mapping exists.
- Reports proxy basis, candidate records, type-71 branch fractions, and f/i/r source-weighted branch proxies for each mapped type-99 source group.
- These type-99 terms are not included in the solved matrix; physical `phint53pl`/radiation-field rate evaluation and full parent-continuum population balance are still future work.

## v0.3.37

- Fixed the v0.3.36 output handoff for the diagnostic global bound-bound+type-71 solve comparison.
- `solve_element_reference()` now returns `global_bound_bound_type71_solve_comparison` rows so `write_element_solver_outputs()` writes the populated `xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv` instead of an empty CSV.
- No physics behavior is intentionally changed; the extended global C V block remains a diagnostic scaffold and the full element-wide coupled matrix is not solved yet.

## v0.3.36

- Added a diagnostic global bound-bound+type-71 solve comparison for the pure-Python XSTAR-like element solver.
- The element-solver example now writes `xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv`.
- The comparison assembles the He-like intra-ion block from `xstar_like_element_solver_global_bound_bound_matrix_terms.csv`, adds the type-71 superlevel cascade matrix triplets from `xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv`, rebuilds the same adjacent source vector used by the current per-ion solve, solves the extended global-index block, and reports populations plus f/i/r, R, G, and L2 distance to the C V target.
- This remains a scaffold/equivalence diagnostic: type-70/type-74/type-99 superlevel source terms and full adjacent-ion balance are not yet assembled.

## v0.3.35

- Added the first global-index type-71 superlevel-cascade matrix scaffold for the pure-Python XSTAR-like element solver.
- `examples/42_xstar_like_element_solver_demo.py` now writes `xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv`.
- Type-71 radiative superlevel-to-spectroscopic cascade rows are mapped onto explicit `global_index` states and written as sparse-like triplets: `M[spectroscopic, superlevel] += A` and `M[superlevel, superlevel] -= A`.
- The output reports superlevel/spectroscopic global indices, level labels/kinds, triplet-feed flags, signed rates, skipped rows, and provenance.
- The type-71 terms are scaffold-only and are not yet included in the solved matrix; type-77, type-70, type-74, and type-99 paths remain diagnostic-only.

## v0.3.34

- Added a diagnostic global bound-bound-only solve comparison for the pure-Python XSTAR-like element solver.
- `examples/42_xstar_like_element_solver_demo.py` now writes `xstar_like_element_solver_global_bound_bound_solve_comparison.csv`.
- The comparison assembles the He-like ion intra-ion block from `xstar_like_element_solver_global_bound_bound_matrix_terms.csv`, rebuilds the same adjacent source vector used by the current per-ion solve, solves the global-index block with the existing statistical-equilibrium solver, and compares populations plus f/i/r, R, G against the old per-ion result.
- This is an equivalence/scaffold test only; the full element-wide C VI + C V matrix is not solved yet.

## v0.3.33

- Added the first diagnostic global bound-bound matrix scaffold for the pure-Python XSTAR-like element solver.
- New output: `xstar_like_element_solver_global_bound_bound_matrix_terms.csv`.
- Maps the current per-ion bound-bound radiative and collisional transition logs onto the explicit `global_index` rows introduced in v0.3.31/v0.3.32.
- For each bound-bound transition `from_level -> to_level`, writes sparse-like matrix triplet rows for the future global element matrix: an off-diagonal gain term `M[to, from] += rate` and a diagonal loss term `M[from, from] -= rate`.
- Includes global row/column indices, source/destination labels, level kinds, transition kind, signed rate, record number, and provenance.
- Adds `global_bound_bound_matrix_terms_summary` to the solver summary.
- This is still a scaffold: the global matrix is not solved yet, and bound-free/recombination/superlevel source terms remain diagnostic-only.

## v0.3.32

- Fixed the explicit element-wide global index classification introduced in v0.3.31.
- Labels such as `sprlevls` and `sprlevlt` are now classified as `level_kind=superlevel` with `is_superlevel=True`, matching the superlevel rows identified by the type-71/type-77/type-99 cascade/source audits.
- Continuum rows remain `level_kind=continuum` with `is_continuum=True`.
- Added explicit parent-continuum mapping fields to `xstar_like_element_solver_global_index.csv`: `parent_level_index` and `continuum_represents_parent`. Existing lower-ion continuum rows are annotated as representing the adjacent parent ion stage, typically parent level 1, instead of being duplicated by a placeholder.
- No global matrix terms are assembled yet; this is a structural correction before element-wide matrix assembly.

## v0.3.31

- Added an explicit element-wide global state index scaffold for the pure-Python XSTAR-like element solver.
- Writes `xstar_like_element_solver_global_index.csv` from `examples/42_xstar_like_element_solver_demo.py`.
- The global index includes one row per decoded selected-stage level plus explicit parent-continuum placeholder rows where needed for adjacent lower/upper ion stages.
- Columns include `global_index`, `ion_stage`, `level_index`, `level_kind`, `energy_eV`, `stat_weight`, `configuration`, `is_triplet_upper`, `is_superlevel`, and `is_continuum`.
- Adds a `global_index_summary` block to the summary JSON/Markdown.
- This is a structural Step-1 scaffold only; no global element matrix terms are assembled from the index yet.

## v0.3.30

- Fixes the v0.3.29 `--triplet-source-scale` scan crash by adding the missing `_xstar_triplet_target()` helper used to compute diagnostic L2 distances to the built-in C V ne=1e8 f/i/r target.
- Reuses the same target helper for the single-scale type-74 direct triplet-source injection comparison.
- No physics changes: the type-74 direct source scale scan remains diagnostic-only and is not assembled into the final element-wide matrix.

## v0.3.29

- Adds `--triplet-source-scale` to `examples/42_xstar_like_element_solver_demo.py` for diagnostic type-74 direct triplet-source injection.
- Supports one scale or a comma-separated scale list, e.g. `1,1e2,1e4,1e6,1e8,1e10`.
- Writes `xstar_like_element_solver_triplet_source_scale_scan.csv` with baseline, each scaled injected solve, and the C V XSTAR target row when available.
- Reports f/i/r, R, G, scaled injected source rate, solve status, and L2 distance to the XSTAR target for each scale.
- Keeps type-74 source scaling diagnostic-only; it is not the final element-wide XSTAR-like matrix assembly.

# Changelog

## v0.3.28

- Added `--triplet-source-mode none|type74-direct-diagnostic` to `examples/42_xstar_like_element_solver_demo.py`.
- Added an optional diagnostic before/after solve that injects evaluated type-74 direct triplet source rates into the current He-like ion source vector.
- New output: `xstar_like_element_solver_triplet_source_injection_comparison.csv`, reporting baseline f/i/r, type74-source-injected f/i/r, and the C V ne=1e8 XSTAR target comparison.
- The mode is off by default and remains diagnostic-only; it is not the final global element-wide matrix assembly.

## v0.3.27

- Added a diagnostic-only type-74 direct triplet-source evaluator.
- New output: `xstar_like_element_solver_type74_triplet_source_audit.csv`.
- Ports the recombination-alpha portion of XSTAR `calt74.f90` for type-74 records whose recombined/source level directly matches a He-like f/i/r triplet upper level.
- Applies the `ucalc.f90` statistical-weight correction `alpha *= g(recombined)/g(continuum)` with an explicit placeholder continuum weight until a global element matrix includes the parent continuum row.
- Reports candidate source rates into forbidden, intercombination, and resonance upper levels; computes a type-74-only f/i/r source-vector shape; and compares it to the C V ne=1e8 XSTAR target when applicable.
- Type 74 remains diagnostic-only and is not assembled into the population matrix.

## v0.3.26

- Added a diagnostic-only deep type-74 DR-delta linkage audit.
- Added `xstar_like_element_solver_type74_linkage_audit.csv`, with one row per type-74 record.
- Decodes both the parent/final side (`i5`/`i6`) and the recombined/source side (`i7`/`i8`) of type-74 records.
- Classifies whether the recombined/source level is spectroscopic, superlevel, or continuum; reports direct f/i/r triplet-upper candidates; checks same-numeric and valid type-71/type-77 superlevel branch links.
- Reports `possible_feed_route`, `branch_link_status`, and `why_no_branch_found_if_unlinked` so unlinked type-74 records can be diagnosed explicitly.
- Keeps all type-74 DR-delta linkage rows diagnostic-only; no `calt74`, Milne inverse, source, or cascade term is assembled into the element matrix.

## v0.3.25

- Added a diagnostic-only superlevel source × branch audit for type 70, 74, and 99 source-candidate records.
- Added `xstar_like_element_solver_superlevel_source_audit.csv`, grouping source candidates by record ion stage and superlevel and linking them to v0.3.24 type-71/type-77 branch fractions.
- Reported type-70/type-74/type-99 record lists, source-candidate counts, coefficient-magnitude previews, and count-based nonphysical `source_proxy_total`.
- Added source-weighted feed proxy columns such as `source_weighted_type71_feed_f_proxy`, `source_weighted_type71_feed_i_proxy`, `source_weighted_type71_feed_r_proxy`, and preferred-branch proxy columns.
- Kept all source × branch proxy rows diagnostic-only; no type-70/74/99 source or superlevel cascade term is assembled into the element matrix.

## v0.3.24

- Added a diagnostic-only superlevel branching audit for type 71 and type 77 superlevel-to-spectroscopic cascade records.
- Added `xstar_like_element_solver_superlevel_branching_audit.csv`, grouping outgoing superlevel cascade rows by superlevel and reporting `B_f`, `B_i`, `B_r`, and `B_triplet_total`.
- Type 71 branching uses radiative A-value-like weights from the audit rows; type 77 branching is explicitly reported as a count-proxy because the collisional superlevel rate evaluator is not yet ported.
- Added summary JSON/Markdown counts for dominant cascade components, forbidden-favored superlevels, and maximum triplet branching fractions.
- Kept all superlevel branching/cascade rows diagnostic-only; no type-71/type-77 rates are assembled into the element matrix.

## v0.3.23

- Added a diagnostic-only superlevel cascade audit for data types 70, 71, 74, 77, and 99 to the XSTAR-like element solver.
- Added `xstar_like_element_solver_superlevel_cascade_audit.csv`, which reports superlevel route kind, source-code/database provenance, candidate superlevel/spectroscopic levels, triplet-component feed classification, required physical context, and unsafe-to-assemble reasons.
- Added summary JSON/Markdown counts for superlevel cascade records, including type counts and whether any record directly targets He-like forbidden/intercombination/resonance upper levels.
- Kept all superlevel/cascade records diagnostic-only; no type-70/71/74/77/99 rates are assembled into the element matrix.

## v0.3.20

- Added `--type57-energy-convention {ucalc-eth,abs-rlev4,threshold-only,compare}` to `examples/42_xstar_like_element_solver_demo.py`.
- Threaded the selected type-57 convention into the source-code-guided adjacent-ion audit while keeping type 57 diagnostic-only and not assembled into the matrix.
- Added type-57 source-code provenance notes to the audit rows and summary output, documenting the visible `ucalc.f90` `ep=eth` branch versus the `calt57.f90` documented `ep=rlev(4)` convention.
- Added summary counts for nonzero type-57 rates under the `ucalc-eth`, `abs-rlev4`, and `threshold-only` diagnostics.

## v0.3.19

- Added a source-code-guided type-57 energy-convention audit to the XSTAR-like element solver.
- Kept the visible `ucalc.f90` convention (`ep=eth`) as the primary diagnostic columns while adding side-by-side `calt57.f90` documented absolute-`rlev(4)` diagnostics and threshold-only diagnostics.
- Added audit columns such as `type57_ep_ucalc_eth_eV`, `type57_ep_absolute_rlev4_eV`, `type57_abs_rlev4_cion_cm3_s`, `type57_abs_rlev4_rate_forward_s^-1`, `type57_threshold_only_cion_cm3_s`, and `type57_energy_convention_conflict`.
- Type-57 rates remain diagnostic-only and are not assembled into the element matrix.

## v0.3.17

- Added source-code-guided ucalc-style adjacent-ion coupling audit metadata to the pure-Python XSTAR-like element solver.
- Added diagnostic branch annotations for type 53, 57, 74, 95, and 99 records, including their XSTAR `ucalc.f90` roles, required physical context, and matrix role if implemented.
- Added a diagnostic Bryans type-95 collisional-ionization evaluator that reports approximate forward electron-impact ionization rates without assembling them into the production matrix.
- Added inferred XSTAR local level/continuum index columns (`idest1_guess`, `idest2_guess`, etc.) to adjacent-coupling audit rows.
- Added `xstar_like_element_solver_ucalc_adjacent_audit.csv` alongside the previous adjacent-coupling terms CSV.
- Kept type 53/74/99 photoionization/DR/superlevel records unassembled unless a physically complete radiation-field/continuum context is available.


## v0.3.16

- Fixed a v0.3.15 API mismatch in `solve_element_reference()` where the coupling-candidate cataloguer was called with adjacent-coupling assembly options that are only valid for `build_adjacent_coupling_terms()`.
- Restored `examples/42_xstar_like_element_solver_demo.py --adjacent-coupling-mode recombination-source` so the pure-Python element-solver scaffold runs and writes coupling audit outputs instead of failing at startup.
- Kept the separation between catalogued adjacent-ion candidate records and physically assembled/evaluated recombination-source terms.

## v0.3.9 - datapath-safe ATDB resolution for diagnostics

- Changed `xstar_atomic.data.resolve_atdb_path()` so an ordinary explicit `atdb.fits` argument no longer rewrites the persistent `datapath` file. Use `python -m xstar_atomic.data --set-path /path/to/atdb.fits`, `set_data_path(...)`, or `remember_explicit=True` only when intentionally configuring the shared data location.
- `resolve_atdb_path(..., prompt=False)` now raises a clear configuration error when no ATDB file is found instead of attempting a non-interactive download.
- Made `examples/39_scan_helike_source_level_blocks.py` and `examples/40_audit_signed_triplet_response.py` accept an optional `fitsfile`. If omitted, they resolve `atdb.fits` from `XSTAR_ATDB_FITS`, the saved `datapath`, or `data/atdb.fits`. If supplied, the path is passed through without changing `datapath`.
- Updated regression coverage for the new datapath behavior and dry-run diagnostics.

## v0.3.8 - signed/absolute He-like triplet response audit

- Added `examples/40_audit_signed_triplet_response.py`, a diagnostic that compares baseline, source-injected, absolute, and delta f/i/r triplet emissivities for each source level.
- The audit reports raw baseline and injected triplet components, normalized injected fractions, signed normalized delta responses, component-wise increase/decrease flags, sign patterns, and whether negative responses are caused by baseline subtraction.
- This diagnostic is intended to distinguish genuinely destructive population redistribution from response-matrix construction artifacts, normalization artifacts, or missing recombination/cascade source physics in non-O VII He-like ions.
- Added regression coverage for the new diagnostic's dry-run command/output path.

## v0.3.6 - robust He-like source-level block preflight

- Hardened `examples/39_scan_helike_source_level_blocks.py` after Ca XIX block scans failed before discovery when requested blocks included source levels not present for Ca XIX.
- Added ATDB level-table preflight in the block scanner. By default, requested source levels that do not exist for the selected ion are skipped before launching `examples/20_o7_solver_source_fit.py`.
- Added `--no-skip-invalid-source-levels` to recover the old behavior and `--skip-invalid-source-levels` as the explicit default.
- Block-scan CSV output now records requested levels, actually used levels, skipped invalid levels, and paths to per-block `example20.stdout.log` and `example20.stderr.log` files.
- Failed block warnings now point to the saved stderr log, making solver/preflight failures diagnosable instead of opaque.

## v0.3.3 - response-basis filter comparison

- Added `examples/37_filter_source_basis_response.py`, an offline diagnostic that refits He-like triplet targets after filtering the source-level response basis.
- The new utility compares four source bases for each density: all levels, zero-response levels removed, negative-response levels removed, and positive nonzero response levels only.
- Reports how many source levels survive each filter, whether the filtered basis can still match XSTAR f/i/r components, and how much of the original fitted weight was carried by zero-response or negative-response levels.
- Added regression coverage for the filtered-basis diagnostic using a synthetic response matrix with active, zero-response, and negative-response source levels.

## v0.3.2 - zero-response source accounting fix

- Fixed `examples/20_o7_solver_source_fit.py` so source levels with no positive f/i/r response remain zero-response columns instead of being normalized to artificial `1/3,1/3,1/3` vectors.
- Updated `examples/36_source_level_failure_diagnostics.py` to recompute normalized f/i/r fractions and fitted contribution columns from raw response amplitudes, making old v0.3.1 output folders diagnose correctly.
- Added `zero_response_fitted_weight_sum` and `negative_response_fitted_weight_sum` to density-level source diagnostics and console output.
- Added regression coverage for zero-response source levels so they are not converted into uniform triplet contributors.

## v0.3.0 - He-like source-level failure diagnostics

- Added `examples/36_source_level_failure_diagnostics.py` to compare fitted source vectors and response matrices at the individual source-level level across O VII, C V, Mg XI, and Ca XIX density-grid runs.
- The new diagnostic reports source level labels/configurations, fitted source weights, f/i/r response contributions, zero-response flags, optional source-component population sums, dominant radiative decay paths, dominant collisional sink/source paths, and pruning/weak-connectivity indicators.
- Extended `examples/20_o7_solver_source_fit.py` combined-source validation output to request solver population and transition CSVs (`o7_combined_solver_populations.csv`, `o7_combined_solver_transitions.csv`) so future source-level diagnostics can directly measure source-connected component populations and rate paths.
- The source-level diagnostic remains offline/exploratory and does not change the validated O VII `suppress-resonance` behavior or default solver physics.

## v0.2.99

- Added `examples/35_compare_helike_response_matrices.py`, an offline diagnostic that compares fitted source vectors, response matrices, and combined-solver validation behavior across He-like density-grid runs.
- The new comparison writes density-level CSV, run-level CSV, JSON, and Markdown reports identifying why O VII is reachable while C V, Mg XI, and Ca XIX grids are not.
- The diagnostic records XSTAR R/G ranges, fitted and combined R/G availability, simultaneous-solver residuals, response-matrix active-source counts, response-matrix conditioning, top fitted source levels, and a concise failure diagnosis.
- Added a regression test for the new comparison utility.

## v0.2.98

- Improved `examples/34_summarize_helike_validation_runs.py` reporting for multi-condition He-like validation grids.
- Density-grid summaries now prefer the output-directory stem as the run tag, preserving condition labels such as `ca19_xi3` and `ca19_xi4` instead of collapsing both to `ca19`.
- Line-audit summaries now use the audit-directory stem as the audit tag, so low-ionization and high-ionization Ca XIX audits remain distinct in console, CSV, JSON, and Markdown output.
- Updated the validation-summary regression test to require distinct Ca XIX xi/audit tags.

## v0.2.97

- Added `examples/34_summarize_helike_validation_runs.py`, a lightweight reporting utility for completed He-like density-grid validation products.
- The new summary tool reads one or more density-grid output directories from `examples/21`/`examples/22` and optional line-audit directories from `examples/33`.
- It writes machine-readable CSV/JSON and a Markdown report with per-ion status, XSTAR R/G ranges, reachable-density counts, non-null solver diagnostics, and warning counts.
- This makes the current multi-ion status explicit: O VII remains the only validated suppress-resonance benchmark, while C V, Mg XI, and Ca XIX high-xi runs are exploratory/non-validated until solver-side R/G diagnostics become reachable.
- Added `tests/test_helike_validation_summary_example.py` covering the new reporting workflow.

## v0.2.96

- Added ionization-parameter scan support to `examples/32_prepare_helike_xstar_density_grids.py` via `--rlogxi-grid`.
- The default single-`log xi` behavior is preserved, but multi-value grids now generate xi-tagged XSTAR run directories and mapping CSVs such as `ca19_xi3_ne1/` and `xstar_ca19_xi3_density_grid_references.csv`.
- This is intended for Ca XIX, where the default `log xi=1.5` XSTAR runs produced no `ca_xix` triplet rows; use a scan such as `--rlogxi-grid 1.5 2 2.5 3 3.5 4` to locate conditions that actually produce Ca XIX.
- Updated tests for the He-like XSTAR density-grid preparation helper.


## v0.2.95

- Added `examples/33_audit_helike_xstar_lines.py` to diagnose He-like XSTAR line-output files when a prepared triplet converter finds zero rows.
- The new audit reports XSTAR ion-label counts, all nearby wavelength-window rows, expected-ion rows at any wavelength, and rows with He-like ground-to-`n=2` triplet/resonance level labels.
- Documented the Ca XIX use case where XSTAR runs complete but `convert_ca19_triplet.sh` produces empty CSVs, meaning Ca XIX is not testable until a usable triplet target is located.

## v0.3.66 - 2026-05-05

- Fixed `write_element_solver_outputs` so `calc_emis_context_audit_rows` is defined from `result.get("calc_emis_context_audit", [])` before writing `xstar_like_element_solver_calc_emis_context_audit.csv`.
- Added the v0.3.65 context-audit summary into the output summary when rows are present.
- No intentional changes to the solver, matrix assembly, triplet-coupling treatment, suppression behavior, or physical rate behavior.

## v0.3.65 - 2026-05-05

- Added `xstar_like_element_solver_calc_emis_context_audit.csv`, a diagnostic companion to the v0.3.64 transparent `calc_emis_ion` triplet audit.
- The new audit reports available matrix-population runtime context for each f/i/r candidate line: source-population-weighted feed (`alpha`), loss (`gamma`), dominant feed/loss components and records, current transparent `ucalc` placeholders, and abundance/escape placeholders.
- Added component-level required line-accounting multipliers (`target/current` and an intercombination-only scale) to test whether `calc_emis_ion` escape/net-emissivity/strong-line accounting could fix the remaining C V intercombination deficit without changing populations.
- No solver, matrix assembly, suppression treatment, or physical rate behavior is intentionally changed.

## v0.3.64 - 2026-05-04

- Added `xstar_like_element_solver_calc_emis_triplet_audit.csv`, a `calc_emis_ion`-style line-output diagnostic for the He-like triplet.
- The audit reports, for each f/i/r candidate line, lower/upper level populations, A-values, photon energy, transparent `pop*A*E` emissivity, transparent `calc_emis_ion` channel proxies, `ans1/ans2` placeholders, `ptmp1/ptmp2` escape placeholders, and strong-line selection status.
- Added component-level summaries for f/i/r fractions under the transparent `calc_emis_ion` proxy so line-output/accounting differences can be separated from population-balance differences.
- No solver, matrix assembly, suppression treatment, or physical rate behavior is intentionally changed.

# Changelog

## v0.3.63 - 2026-05-04

- Adds a controlled diagnostic switch for the suspicious He-like `1s2p 3P_J -> 1s2s 3S1` type-50 radiative population-transfer drains identified in v0.3.62.
- New CLI option: `--triplet-coupling-treatment normal|audit-only|suppress-3p-to-3s-radiative`.  The default `normal` leaves solver behavior unchanged.  The suppression mode removes only those three off-diagonal gains and their diagonal-loss partners from the primary full-global normalized solve.
- Adds `xstar_like_element_solver_triplet_coupling_suppression_comparison.csv`, which always compares the normal full-global XSTAR-Lucy solution against the diagnostic suppressed solution and lists the exact matrix terms removed in the suppressed case.
- The comparison keeps intercombination-to-ground, forbidden-to-ground, resonance, type-63 collisional `3S1 <-> 3P_J`, type-53, type-71, type-74, type-99, and type-1 terms intact.
- This is a matrix-semantics diagnostic only.  Suppressing type-50 `3P_J -> 3S1` terms is not treated as a physical correction unless follow-up source-code validation proves XSTAR excludes or reclassifies these records.

## v0.3.62 - 2026-05-04

- Added `xstar_like_element_solver_triplet_coupling_record_audit.csv` for source-code-aligned validation of the direct `1s2s 3S1 <-> 1s2p 3P_J` coupling records that dominate the C V intercombination bottleneck.
- The audit selects f/i off-diagonal matrix terms and their diagonal partners, infers type-50 radiative A-value paths versus type-63/67/68/69 density-scaled collisional partners, and reports source-population-weighted feed/loss contributions.
- The summary highlights whether the large `3P_J -> 3S1` radiative-drain terms overwhelm collisional `3S1 -> 3P_J` feeds at the current density and radiation context.
- No solver or physical-rate behavior is intentionally changed.

## v0.3.61 - 2026-05-04

- Added source-code-aligned triplet α/γ diagnostics for the full-global XSTAR-Lucy solution.
- New output: `xstar_like_element_solver_triplet_alpha_gamma_audit.csv`, which reports source-population-weighted `alpha = sum_j n_j R(i<-j)`, loss `gamma`, `alpha/gamma` population proxies, dominant feed/loss terms, and f/i/r component summaries.
- Added triplet emissivity/branching diagnostics.
- New output: `xstar_like_element_solver_triplet_emissivity_branch_audit.csv`, which lists f/i/r candidate line records with upper/lower levels, A-values, branching fractions from decoded lines, solved upper/lower populations, transparent `pop*A*E` emissivity proxies, and the missing XSTAR `calc_emis_ion` contexts (`ucalc` net emissivity, escape probabilities, `cfrac`, and strong-line filtering).
- No solver or physical-rate behavior is intentionally changed; this version is an audit layer to decide whether the remaining low intercombination component is a population-balance issue or a line-emissivity/branching/accounting issue.

## v0.3.60 - 2026-05-04

- Added `xstar_like_element_solver_intercombination_feed_audit.csv`, a detailed audit of all current full-global matrix routes that feed, branch out of, or diagonally drain the He-like intercombination upper levels (`1s2p 3P_J`).
- Added `xstar_like_element_solver_triplet_component_balance_audit.csv`, summarising f/i/r populations, incoming rates, radiative losses, type-71 cascade feeds, type-53 Milne inverse feeds, type-74 inverse feeds, collisional couplings, and type-53 photoionization losses.
- Added summary entries for both new audits to `xstar_like_element_solver_summary.json` and the Markdown summary.
- No solver or physics rates are intentionally changed; v0.3.60 is an audit layer for the low-intercombination bottleneck identified by v0.3.59.

## v0.3.59 - 2026-05-04

- Added a refined inverse-recombination scale scan around the promising C V region found in v0.3.58.
- Added `--type53-milne-refined-scale` and `--type74-inverse-refined-scale` to `examples/42_xstar_like_element_solver_demo.py`.
- Wrote `xstar_like_element_solver_inverse_recombination_refined_scale_scan.csv`, using a narrower default grid: type-53 Milne scales `1e9,3e9,1e10,3e10,1e11` and type-74 inverse scales `1e8,3e8,1e9,3e9,1e10,3e10,1e11,3e11,1e12`.
- Added target-aware columns to the refined scan, including f/r-only L2, intercombination absolute error, i/target ratio, and an intercombination-weighted diagnostic score.
- Kept the XSTAR-Lucy global solver and existing physical/proxy limitations unchanged.

## v0.3.58 - 2026-05-04

- Improves the diagnostic radiation/bremsa context used by the type-53 `phint53` and type-74 `calt74` ports.
- Adds explicit XSTAR-style `epi`/`bremsa`/`bremsint` bookkeeping through `xstar_like_element_solver_bremsa_context.csv`.
- Adds configurable radiation controls to the demo: `--radiation-bremsa-scale`, `--radiation-energy-min-eV`, `--radiation-energy-max-eV`, `--radiation-n-energy-grid`, and `--radiation-powerlaw-index`.
- Extends `--radiation-field-mode` with `powerlaw`/`xstar-powerlaw`; the diagnostic bremsa array is now reused consistently by `phint53` and `calt74`.
- Keeps the full-global XSTAR-Lucy normalization solve unchanged: one row is replaced by `sum_i n_i = 1`, source-vector proxy rows are handled as before, and the solve remains diagnostic until real XSTAR radiation transfer, Milne inverse recombination, opacity/escape probabilities, physical type-99/type-1 rates, and closed continuum balance are ported.

## v0.3.57 - 2026-05-04

- Adds a source-aligned type-74 `calt74` diagnostic path.
- Evaluates both `rate` and `alpha` following `xstarlib/src/calt74.f90`, including delta-resonance interpolation on the diagnostic radiation grid and the `ucalc` statistical-weight correction `alpha *= gglo/ggup`.
- Writes `xstar_like_element_solver_type74_calt74_rate_audit.csv` and `xstar_like_element_solver_global_type74_calt74_matrix_terms.csv`.
- The full-global matrix now prefers the source-aligned type-74 calt74 inverse topology rows when available, falling back to the older type-74 inverse proxy rows otherwise.
- Still diagnostic: absolute forward rates depend on placeholder `bremsa`, and parent-continuum closure remains pending.

## v0.3.56 - 2026-05-04

- Checked the XSTAR source path for inverse recombination before extending the scaffold:
  type-53 calls `phint53`, and XSTAR also compares the recombination output against `milne(temp, ntmp, etmpp, stmpp, ett/13.6, ...)`; type-74 DR-delta rates are handled through `calt74(temp, ncn2, epi, bremsa, ..., rate, alpha)`, with `alpha` scaled by the lower/upper statistical-weight ratio.
- Added independent diagnostic inverse-recombination scale controls:
  `--type53-milne-scale` and `--type74-inverse-scale`.
- The first value of each scale list is used for the primary type-53 Milne/type-74 inverse audit and full-global matrix assembly; the full lists are used by `xstar_like_element_solver_inverse_recombination_scale_scan.csv`.
- Expanded `xstar_like_element_solver_inverse_recombination_scale_scan.csv` from a single placeholder row to independent type-53-Milne scans, independent type-74 inverse scans, and a compact cross-grid when the requested lists are modest.
- This remains a diagnostic/proxy scan: true XSTAR Milne inverse recombination, physical type-74 DR balance, real `bremsa` radiation context, opacity/escape probabilities, and closed continuum balance remain pending.

## v0.3.55 - 2026-05-04

- Added `--inverse-recombination-mode none|type53-milne-diagnostic|type74-direct-diagnostic|type53-type74` to the element-solver demo.
- Added diagnostic type-53 Milne inverse-recombination scaffold outputs:
  - `xstar_like_element_solver_type53_milne_inverse_audit.csv`
  - `xstar_like_element_solver_global_type53_milne_matrix_terms.csv`
- Added diagnostic type-74 direct DR-delta inverse-recombination scaffold outputs:
  - `xstar_like_element_solver_type74_inverse_recombination_audit.csv`
  - `xstar_like_element_solver_global_type74_inverse_matrix_terms.csv`
- Added `xstar_like_element_solver_inverse_recombination_scale_scan.csv` as a first solve-context audit for inverse-recombination modes.
- The inverse terms are included in `xstar_like_element_solver_full_global_matrix_terms.csv` only when enabled by mode, but remain explicitly marked as diagnostic/proxy topology. True XSTAR Milne inverse recombination, physical type-74 DR balance, real radiation context, and closed continuum balance remain pending.

## v0.3.54 - 2026-05-04

- Added a type-53 `phint53` scale scan for the full-global XSTAR-Lucy diagnostic path.
- `--type53-phint53-scale` now accepts comma-separated values, e.g. `1,1e5,1e10,1e15,1e18,1e20`; the first value is used for the primary audit/matrix, and all values are scanned in `xstar_like_element_solver_type53_phint53_scale_scan.csv`.
- Added `xstar_like_element_solver_radiation_normalization_audit.csv` to report the placeholder radiation-grid/bremsa normalization used by the first `phint53` forward-kernel diagnostic and the scale needed to reach reference total rates.
- Added summary metadata for the radiation-normalization audit and `phint53` scale scan.
- The phint53 kernel remains diagnostic: the real XSTAR radiation field, Milne inverse recombination, opacity/escape probabilities, and physical type-99/type-1 rates are still pending.

## v0.3.53 - 2026-05-04

- Fixes the v0.3.52 `NameError: name '_sum_float' is not defined` crash in the type-53 `phint53` audit summary path.
- Adds a module-level `_sum_float(rows, col)` helper used by both `xstar_like_element_solver_type53_phint53_rate_audit.csv` and `xstar_like_element_solver_global_type53_phint53_matrix_terms.csv` summary generation.
- No intentional physics change: XSTAR-Lucy remains the preferred full-global diagnostic solver, and the type-53 `phint53` forward-kernel diagnostic remains a first audit/topology port with placeholder radiation context.

## v0.3.52 - 2026-05-03

- Makes `--full-global-linear-solver xstar-lucy` the preferred/default diagnostic solver for the full-global path.
- Adds the first type-53 `phint53` photoionization-kernel diagnostic port.
- Adds `--type53-phint53-scale` for controlled rate scaling of the new phint53-kernel diagnostic.
- Writes `xstar_like_element_solver_type53_phint53_rate_audit.csv` with decoded type-53 cross-section pairs, placeholder radiation-grid integration diagnostics, and forward photoionization rates.
- Writes `xstar_like_element_solver_global_type53_phint53_matrix_terms.csv` with physical-kernel type-53 matrix topology rows.
- `xstar_like_element_solver_full_global_matrix_terms.csv` now prefers type-53 phint53-kernel rows when any are matrix-ready, and falls back to the older flat proxy topology otherwise.
- The phint53 forward photoionization kernel is ported, but the radiation field is still a placeholder; Milne inverse recombination, opacity/escape-probability context, and the real XSTAR continuum are still pending.

## v0.3.51 - 2026-05-03

- Replaced the v0.3.50 XSTAR-Lucy LU backend implementation with explicit local Numerical-Recipes-style helpers `_xstar_ludcmp`, `_xstar_lubksb`, and `_xstar_mprove`.
- The `--full-global-linear-solver xstar-lucy` path no longer delegates the LU step to `numpy.linalg.solve` and does not use `scipy.linalg.lu`; it now mirrors the XSTAR `leqt2f -> ludcmp/lubksb/mprove` structure more directly.
- Kept the solver diagnostic-only: the matrix still contains proxy/topology type-53, type-99, and type-1 rows rather than physical XSTAR `phint53`, `phint53pl`, or Milne inverse rates.

## v0.3.50 - 2026-05-03

- Added an XSTAR-style Lucy/LU full-global diagnostic solver mode for the normalized C VI+C V proxy-topology matrix.
- New/updated `--full-global-linear-solver xstar-lucy` mode follows the `msolvelucy` structure: initialize normalized populations, build a condensed superlevel matrix using fractional level populations, replace one condensed row by number conservation, solve using an LU-style dense solve plus iterative-improvement corrections, expand back to level populations, and apply a Lucy fixed-point update.
- The full-global normalized comparison CSV now records XSTAR-Lucy diagnostics including the number of condensed states, outer/inner iteration counts, final `diff`/`diff2`, LU-failure count, condensed rank/condition, and iterative-improvement residuals.
- Kept `svd`, `lstsq`, and direct dense solve modes as diagnostic alternatives; the XSTAR source path itself remains LU-based (`msolvelucy -> leqt2f -> ludcmp/lubksb/mprove`), not SVD-based.
- This remains a proxy-topology diagnostic: type-53, type-99, and type-1 rows still use diagnostic proxies rather than physical XSTAR `phint53`, `phint53pl`, or Milne inverse rates.

## v0.3.49 - 2026-05-03

- Checked the XSTAR source-code solver path used by the element population workflow: `calc_hmc_element` calls `msolvelucy`, which forms a condensed superlevel matrix, replaces one row with number conservation, and solves it through `leqt2f` using Numerical Recipes LU routines (`ludcmp`, `lubksb`) plus `mprove` iterative improvement.
- Added rank-aware controls for the diagnostic full-global normalized proxy-topology solve:
  - `--full-global-linear-solver solve|dense|lstsq|svd`
  - `--full-global-rank-deficient-action solve|lstsq|svd|error`
  - `--full-global-negative-population-action keep|clip|error`
  - `--no-full-global-prune-null-rate-levels`
- The full-global normalized comparison now defaults to `solver_requested=svd`, `rank_deficient_action=svd`, `negative_population_action=keep`, and `prune_null_rate_levels=true`, matching the earlier rank-aware He-like/O VII diagnostic-solver style.
- Added solver diagnostics to `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`, including requested solver, SVD cutoff, active/pruned global-index counts, matrix rank before/after normalization, normalization residual, and full-rate-matrix residual excluding the normalization row.
- This remains a diagnostic proxy-topology solve; type-53/type-99/type-1 proxy terms are not physical XSTAR rates.

## v0.3.48 - 2026-05-03

- Added the first diagnostic full global C VI+C V normalized solve.
- New output: `xstar_like_element_solver_full_global_normalized_solve_comparison.csv`.
- The solve assembles a dense matrix over all explicit `global_index` rows from `xstar_like_element_solver_full_global_matrix_terms.csv`.
- Only matrix triplet rows are included; source-vector proxy rows are deliberately excluded for this first normalized solve.
- One row is replaced by the normalization equation `sum_i n_i = 1`, and the diagnostic solution is compared against the existing per-ion C V triplet result.
- The solve remains nonphysical because the matrix still contains proxy topology terms for type-53/type-99/type-1 and does not yet use physical XSTAR `phint53`, Milne, or `phint53pl` rates.

## v0.3.47 - 2026-05-03

- Added the diagnostic full global C VI+C V matrix-topology scaffold for the Python XSTAR-like element solver.
- New output: `xstar_like_element_solver_full_global_matrix_terms.csv`.
- The new unified topology file combines:
  - C VI and C V bound-bound radiative/collisional matrix blocks;
  - C V type-71 superlevel-to-spectroscopic cascade matrix triplets;
  - type-99 parent-continuum-to-superlevel proxy topology rows and source-vector proxy rows;
  - type-53 flat photoionization proxy topology rows;
  - mappable type-1 recombination source-vector rows and parent-continuum topology proxy rows.
- Added a full-global matrix-term summary to the run summary.
- This is still a topology scaffold: no full C VI+C V normalized solve is performed, and type-53/type-99 proxy rows remain nonphysical diagnostics.

## v0.3.46 - 2026-05-03

- Added a diagnostic global bound-bound+type71+type99-proxy+type53-flat-proxy solve comparison.
- New output: `xstar_like_element_solver_global_bound_bound_type71_type99_type53_proxy_solve_comparison.csv`.
- The extended diagnostic solve uses the existing He-like global-index block, nonphysical type-99 source-vector proxy rows, and type-53 flat photoionization proxy sinks via `sink_rates`.
- Type-53 off-diagonal parent-continuum topology rows are still not included in the local He-like solve because the full adjacent-ion parent-continuum population is not solved yet.
- No physical XSTAR `phint53` or Milne inverse-recombination rates are evaluated in this release.

## v0.3.45 - 2026-05-03

- Added a diagnostic flat-field type-53 photoionization-rate proxy.
- Added `--type53-flat-proxy-scale` to `examples/42_xstar_like_element_solver_demo.py`.
- Added `xstar_like_element_solver_type53_flat_proxy_rate_audit.csv`.
- Added `xstar_like_element_solver_global_type53_flat_proxy_matrix_terms.csv`.
- The proxy maps `M[continuum_or_parent,bound] += rate_proxy` and `M[bound,bound] -= rate_proxy` topology only; it is not assembled into the solved matrix.
- Physical XSTAR `phint53`/Milne rates are still not evaluated.

## v0.3.44 - 2026-05-03

- Fixes a helper-name collision introduced in v0.3.43: the table-building `_global_index_lookup(rows)` helper is preserved for global matrix scaffolds, and the single-row query helper used by the type-53 audit is renamed to `_global_index_lookup_one(rows, ion_stage, level_index)`.
- This fixes the `TypeError: _global_index_lookup() missing 2 required positional arguments` crash when running with `--radiation-field-mode`.
- No physics behavior is intentionally changed; type-53 remains audit/scaffold-only and is not assembled into the matrix.

## v0.3.43 - 2026-05-03

- Adds the first Phase-E type-53 radiation-context scaffold for the XSTAR-like element solver.
- Adds `--radiation-field-mode none|flat|blackbody|table` to `examples/42_xstar_like_element_solver_demo.py`.
- Writes `xstar_like_element_solver_radiation_context.csv` describing the placeholder radiation grid/status needed by future `phint53` and Milne inverse-recombination ports.
- Writes `xstar_like_element_solver_type53_rate_audit.csv`, mapping type-53 records onto explicit bound-level and continuum/parent global indices where possible and reporting missing physical context.
- Does not evaluate physical type-53 photoionization or inverse recombination rates and does not assemble type-53 terms into the matrix.

## v0.3.42 - 2026-05-03

- Fixes the v0.3.41 packaging/signature regression for `--type99-proxy-scale`: `solve_element_reference()` now actually accepts the `type99_proxy_scale` keyword and passes it into the type-99 proxy scale-scan builder.
- Adds no intended physics changes; the type-99 proxy scale scan remains diagnostic-only.

## v0.3.41 - 2026-05-03

- Bug fix: add the missing `type99_proxy_scale` keyword argument to `solve_element_reference()`.
- This fixes the `TypeError: solve_element_reference() got an unexpected keyword argument 'type99_proxy_scale'` raised by `examples/42_xstar_like_element_solver_demo.py` in v0.3.40.
- No physics behavior is intentionally changed; the type-99 proxy scale scan remains diagnostic-only.

## v0.3.40 - 2026-05-02

- Added a diagnostic type-99 proxy source scale scan for the global bound-bound+type71 block.
- `examples/42_xstar_like_element_solver_demo.py` now accepts `--type99-proxy-scale`, with comma-separated lists such as `0,1e-8,1e-6,1e-4,1e-2,1,1e2`.
- New output: `xstar_like_element_solver_type99_proxy_scale_scan.csv`.
- For each scale, the scan multiplies only the nonphysical type-99 `source_vector_gain_proxy` rows, solves the He-like global-index bound-bound+type71 diagnostic block, and reports f/i/r, R, G, L2 distance to the C V target, superlevel population sum, source totals, and solver status.
- Type-99 `phint53pl` physical rates are still not evaluated; this remains a diagnostic proxy-normalization scan and not the final element-wide coupled matrix solve.

## v0.3.39 - 2026-05-02

- Added a diagnostic global bound-bound+type71+type99-proxy solve comparison for the pure-Python XSTAR-like element-solver scaffold.
- New output: `xstar_like_element_solver_global_bound_bound_type71_type99_proxy_solve_comparison.csv`.
- The comparison assembles the He-like global-index block from bound-bound matrix terms plus type-71 superlevel-cascade triplets, then adds v0.3.38 type-99 `source_vector_gain_proxy` rows to the source vector.
- Reports the resulting f/i/r, R, G, L2 distance to the C V XSTAR target, source-vector totals, superlevel population sum, and level-by-level population differences.
- The type-99 terms remain nonphysical proxy values based on audit coefficients/counts; no `phint53pl` physical rates are evaluated and the full element-wide adjacent-ion matrix is still not solved.

## v0.3.38 - 2026-05-02

- Added a diagnostic global-index type-99 superlevel source scaffold.
- New output: `xstar_like_element_solver_global_superlevel_source_matrix_terms.csv`.
- Maps type-99 source candidates from `xstar_like_element_solver_superlevel_source_audit.csv` onto explicit superlevel `global_index` rows.
- Writes source-vector proxy rows and parent-continuum-to-superlevel matrix proxy rows when a parent-continuum/continuum mapping exists.
- Reports proxy basis, candidate records, type-71 branch fractions, and f/i/r source-weighted branch proxies for each mapped type-99 source group.
- These type-99 terms are not included in the solved matrix; physical `phint53pl`/radiation-field rate evaluation and full parent-continuum population balance are still future work.

## v0.3.37 - 2026-05-02

- Fixed the v0.3.36 output handoff for the diagnostic global bound-bound+type-71 solve comparison.
- `solve_element_reference()` now returns `global_bound_bound_type71_solve_comparison` rows so `write_element_solver_outputs()` writes the populated `xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv` instead of an empty CSV.
- No physics behavior is intentionally changed; the extended global C V block remains a diagnostic scaffold and the full element-wide coupled matrix is not solved yet.

## v0.3.36 - 2026-05-02

- Added a diagnostic global bound-bound+type-71 solve comparison for the pure-Python XSTAR-like element solver.
- The element-solver example now writes `xstar_like_element_solver_global_bound_bound_type71_solve_comparison.csv`.
- The comparison assembles the He-like intra-ion block from `xstar_like_element_solver_global_bound_bound_matrix_terms.csv`, adds the type-71 superlevel cascade matrix triplets from `xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv`, rebuilds the same adjacent source vector used by the current per-ion solve, solves the extended global-index block, and reports populations plus f/i/r, R, G, and L2 distance to the C V target.
- This remains a scaffold/equivalence diagnostic: type-70/type-74/type-99 superlevel source terms and full adjacent-ion balance are not yet assembled.

## v0.3.35 - 2026-05-02

- Added the first global-index type-71 superlevel-cascade matrix scaffold for the pure-Python XSTAR-like element solver.
- `examples/42_xstar_like_element_solver_demo.py` now writes `xstar_like_element_solver_global_superlevel_cascade_matrix_terms.csv`.
- Type-71 radiative superlevel-to-spectroscopic cascade rows are mapped onto explicit `global_index` states and written as sparse-like triplets: `M[spectroscopic, superlevel] += A` and `M[superlevel, superlevel] -= A`.
- The output reports superlevel/spectroscopic global indices, level labels/kinds, triplet-feed flags, signed rates, skipped rows, and provenance.
- The type-71 terms are scaffold-only and are not yet included in the solved matrix; type-77, type-70, type-74, and type-99 paths remain diagnostic-only.

## v0.3.34 - 2026-05-02

- Added a diagnostic global bound-bound-only solve comparison for the pure-Python XSTAR-like element solver.
- `examples/42_xstar_like_element_solver_demo.py` now writes `xstar_like_element_solver_global_bound_bound_solve_comparison.csv`.
- The comparison assembles the He-like ion intra-ion block from `xstar_like_element_solver_global_bound_bound_matrix_terms.csv`, rebuilds the same adjacent source vector used by the current per-ion solve, solves the global-index block with the existing statistical-equilibrium solver, and compares populations plus f/i/r, R, G against the old per-ion result.
- This is an equivalence/scaffold test only; the full element-wide C VI + C V matrix is not solved yet.

## v0.3.33 - 2026-05-02

- Added the first diagnostic global bound-bound matrix scaffold for the pure-Python XSTAR-like element solver.
- New output: `xstar_like_element_solver_global_bound_bound_matrix_terms.csv`.
- Maps the current per-ion bound-bound radiative and collisional transition logs onto the explicit `global_index` rows introduced in v0.3.31/v0.3.32.
- For each bound-bound transition `from_level -> to_level`, writes sparse-like matrix triplet rows for the future global element matrix: an off-diagonal gain term `M[to, from] += rate` and a diagonal loss term `M[from, from] -= rate`.
- Includes global row/column indices, source/destination labels, level kinds, transition kind, signed rate, record number, and provenance.
- Adds `global_bound_bound_matrix_terms_summary` to the solver summary.
- This is still a scaffold: the global matrix is not solved yet, and bound-free/recombination/superlevel source terms remain diagnostic-only.

## v0.3.31 - 2026-05-02

- Added an explicit element-wide global state index scaffold for the pure-Python XSTAR-like element solver.
- Writes `xstar_like_element_solver_global_index.csv` from `examples/42_xstar_like_element_solver_demo.py`.
- The global index includes one row per decoded selected-stage level plus explicit parent-continuum placeholder rows where needed for adjacent lower/upper ion stages.
- Columns include `global_index`, `ion_stage`, `level_index`, `level_kind`, `energy_eV`, `stat_weight`, `configuration`, `is_triplet_upper`, `is_superlevel`, and `is_continuum`.
- Adds a `global_index_summary` block to the summary JSON/Markdown.
- This is a structural Step-1 scaffold only; no global element matrix terms are assembled from the index yet.

## v0.3.30 - 2026-05-02

- Fixes the v0.3.29 `--triplet-source-scale` scan crash by adding the missing `_xstar_triplet_target()` helper used to compute diagnostic L2 distances to the built-in C V ne=1e8 f/i/r target.
- Reuses the same target helper for the single-scale type-74 direct triplet-source injection comparison.
- No physics changes: the type-74 direct source scale scan remains diagnostic-only and is not assembled into the final element-wide matrix.

## v0.3.29 - 2026-05-02

- Adds `--triplet-source-scale` to `examples/42_xstar_like_element_solver_demo.py` for diagnostic type-74 direct triplet-source injection.
- Supports one scale or a comma-separated scale list, e.g. `1,1e2,1e4,1e6,1e8,1e10`.
- Writes `xstar_like_element_solver_triplet_source_scale_scan.csv` with baseline, each scaled injected solve, and the C V XSTAR target row when available.
- Reports f/i/r, R, G, scaled injected source rate, solve status, and L2 distance to the XSTAR target for each scale.
- Keeps type-74 source scaling diagnostic-only; it is not the final element-wide XSTAR-like matrix assembly.

# Changelog

## v0.3.28 - 2026-05-02

- Added `--triplet-source-mode none|type74-direct-diagnostic` to `examples/42_xstar_like_element_solver_demo.py`.
- Added an optional diagnostic before/after solve that injects evaluated type-74 direct triplet source rates into the current He-like ion source vector.
- New output: `xstar_like_element_solver_triplet_source_injection_comparison.csv`, reporting baseline f/i/r, type74-source-injected f/i/r, and the C V ne=1e8 XSTAR target comparison.
- The mode is off by default and remains diagnostic-only; it is not the final global element-wide matrix assembly.

## v0.3.27 - 2026-05-01

- Added a diagnostic-only type-74 direct triplet-source evaluator.
- New output: `xstar_like_element_solver_type74_triplet_source_audit.csv`.
- Ports the recombination-alpha portion of XSTAR `calt74.f90` for type-74 records whose recombined/source level directly matches a He-like f/i/r triplet upper level.
- Applies the `ucalc.f90` statistical-weight correction `alpha *= g(recombined)/g(continuum)` with an explicit placeholder continuum weight until a global element matrix includes the parent continuum row.
- Reports candidate source rates into forbidden, intercombination, and resonance upper levels; computes a type-74-only f/i/r source-vector shape; and compares it to the C V ne=1e8 XSTAR target when applicable.
- Type 74 remains diagnostic-only and is not assembled into the population matrix.

## v0.3.26 - 2026-05-01

- Added a diagnostic-only deep type-74 DR-delta linkage audit.
- Added `xstar_like_element_solver_type74_linkage_audit.csv`, with one row per type-74 record.
- Decodes both the parent/final side (`i5`/`i6`) and the recombined/source side (`i7`/`i8`) of type-74 records.
- Classifies whether the recombined/source level is spectroscopic, superlevel, or continuum; reports direct f/i/r triplet-upper candidates; checks same-numeric and valid type-71/type-77 superlevel branch links.
- Reports `possible_feed_route`, `branch_link_status`, and `why_no_branch_found_if_unlinked` so unlinked type-74 records can be diagnosed explicitly.
- Keeps all type-74 DR-delta linkage rows diagnostic-only; no `calt74`, Milne inverse, source, or cascade term is assembled into the element matrix.

## v0.3.25 - 2026-05-01

- Added a diagnostic-only superlevel source × branch audit for type 70, 74, and 99 source-candidate records.
- Added `xstar_like_element_solver_superlevel_source_audit.csv`, grouping source candidates by record ion stage and superlevel and linking them to v0.3.24 type-71/type-77 branch fractions.
- Reported type-70/type-74/type-99 record lists, source-candidate counts, coefficient-magnitude previews, and count-based nonphysical `source_proxy_total`.
- Added source-weighted feed proxy columns such as `source_weighted_type71_feed_f_proxy`, `source_weighted_type71_feed_i_proxy`, `source_weighted_type71_feed_r_proxy`, and preferred-branch proxy columns.
- Kept all source × branch proxy rows diagnostic-only; no type-70/74/99 source or superlevel cascade term is assembled into the element matrix.

## v0.3.24 - 2026-05-01

- Added a diagnostic-only superlevel branching audit for type 71 and type 77 superlevel-to-spectroscopic cascade records.
- Added `xstar_like_element_solver_superlevel_branching_audit.csv`, grouping outgoing superlevel cascade rows by superlevel and reporting `B_f`, `B_i`, `B_r`, and `B_triplet_total`.
- Type 71 branching uses radiative A-value-like weights from the audit rows; type 77 branching is explicitly reported as a count-proxy because the collisional superlevel rate evaluator is not yet ported.
- Added summary JSON/Markdown counts for dominant cascade components, forbidden-favored superlevels, and maximum triplet branching fractions.
- Kept all superlevel branching/cascade rows diagnostic-only; no type-71/type-77 rates are assembled into the element matrix.

## v0.3.23 - 2026-05-01

- Added a diagnostic-only superlevel cascade audit for data types 70, 71, 74, 77, and 99 to the XSTAR-like element solver.
- Added `xstar_like_element_solver_superlevel_cascade_audit.csv`, which reports superlevel route kind, source-code/database provenance, candidate superlevel/spectroscopic levels, triplet-component feed classification, required physical context, and unsafe-to-assemble reasons.
- Added summary JSON/Markdown counts for superlevel cascade records, including type counts and whether any record directly targets He-like forbidden/intercombination/resonance upper levels.
- Kept all superlevel/cascade records diagnostic-only; no type-70/71/74/77/99 rates are assembled into the element matrix.

## v0.3.20 - 2026-05-01

- Added `--type57-energy-convention {ucalc-eth,abs-rlev4,threshold-only,compare}` to `examples/42_xstar_like_element_solver_demo.py`.
- Threaded the selected type-57 convention into the source-code-guided adjacent-ion audit while keeping type 57 diagnostic-only and not assembled into the matrix.
- Added type-57 source-code provenance notes to the audit rows and summary output, documenting the visible `ucalc.f90` `ep=eth` branch versus the `calt57.f90` documented `ep=rlev(4)` convention.
- Added summary counts for nonzero type-57 rates under the `ucalc-eth`, `abs-rlev4`, and `threshold-only` diagnostics.

## v0.3.19 - 2026-05-01

- Added a source-code-guided type-57 energy-convention audit to the XSTAR-like element solver.
- Kept the visible `ucalc.f90` convention (`ep=eth`) as the primary diagnostic columns while adding side-by-side `calt57.f90` documented absolute-`rlev(4)` diagnostics and threshold-only diagnostics.
- Added audit columns such as `type57_ep_ucalc_eth_eV`, `type57_ep_absolute_rlev4_eV`, `type57_abs_rlev4_cion_cm3_s`, `type57_abs_rlev4_rate_forward_s^-1`, `type57_threshold_only_cion_cm3_s`, and `type57_energy_convention_conflict`.
- Type-57 rates remain diagnostic-only and are not assembled into the element matrix.

## v0.3.17 - 2026-05-01

- Added source-code-guided ucalc-style adjacent-ion coupling audit metadata to the pure-Python XSTAR-like element solver.
- Added diagnostic branch annotations for type 53, 57, 74, 95, and 99 records, including their XSTAR `ucalc.f90` roles, required physical context, and matrix role if implemented.
- Added a diagnostic Bryans type-95 collisional-ionization evaluator that reports approximate forward electron-impact ionization rates without assembling them into the production matrix.
- Added inferred XSTAR local level/continuum index columns (`idest1_guess`, `idest2_guess`, etc.) to adjacent-coupling audit rows.
- Added `xstar_like_element_solver_ucalc_adjacent_audit.csv` alongside the previous adjacent-coupling terms CSV.
- Kept type 53/74/99 photoionization/DR/superlevel records unassembled unless a physically complete radiation-field/continuum context is available.

## v0.3.16 - 2026-05-01

- Fixed a v0.3.15 API mismatch in `solve_element_reference()` where the coupling-candidate cataloguer was called with adjacent-coupling assembly options that are only valid for `build_adjacent_coupling_terms()`.
- Restored `examples/42_xstar_like_element_solver_demo.py --adjacent-coupling-mode recombination-source` so the pure-Python element-solver scaffold runs and writes coupling audit outputs instead of failing at startup.
- Kept the separation between catalogued adjacent-ion candidate records and physically assembled/evaluated recombination-source terms.

## v0.3.15 - prototype adjacent-ion coupling assembly - 2026-04-30

- Extended the pure-Python XSTAR-like element solver with explicit adjacent-ion coupling term construction.
- Added `build_adjacent_coupling_terms(...)` in `src/xstar_atomic/xstar_element_solver.py`. It evaluates implemented electron-recombination record classes and assembles them as prototype source-vector terms from the adjacent higher ion into the target ion.
- The implementation intentionally keeps XSTAR-sensitive data types such as 53, 57, 74, 95, and 99 in the audit table unless a rate can be evaluated with the currently available local physics. This avoids treating photoionization cross sections, DR resonance metadata, or collisional-ionization metadata as rates without XSTAR's radiation-field / ucalc context.
- `examples/42_xstar_like_element_solver_demo.py` now exposes `--adjacent-coupling-mode`, `--adjacent-coupling-source-mode`, `--adjacent-coupling-source-levels`, and `--include-charge-exchange`.
- The element-solver output now includes `xstar_like_element_solver_adjacent_coupling_terms.csv` with row-level `assembled` and `assembly_status` diagnostics.

## v0.3.14 - Pure-Python XSTAR-like element solver scaffold - 2026-04-30

- Added `src/xstar_atomic/xstar_element_solver.py`, a pure-Python reference scaffold for an XSTAR-like element-wide population workflow.
- Added `examples/42_xstar_like_element_solver_demo.py` to build ion-block diagnostics, line emissivities, populations, transition logs, and adjacent-ion coupling candidate catalogs.
- The new solver intentionally catalogs adjacent H-like/He-like coupling records but does not yet assemble full XSTAR recombination/photoionization coupling into the matrix. This replaces further empirical fitting with a source-code-guided architecture.
- Exposed `solve_element_reference` in the package namespace for future Python/C++ backend parity tests.

## v0.3.13 - target-aware absolute-response constraints - 2026-04-30

- Added `--absolute-fit-constraint-mode target-aware` to `examples/40_audit_signed_triplet_response.py` and `examples/41_fit_absolute_response_density_grid.py`.
- In target-aware mode, the maximum allowed intercombination fraction is derived from the XSTAR target at each density using `max(target_i_floor, target_i_factor * target_i)`, while remaining capped by any explicit user-supplied maximum.
- Pure-intercombination columns are automatically rejected when the target intercombination fraction is small, but are allowed again at high density when the XSTAR target itself is intercombination-rich.
- Absolute-response fit summaries now record the constraint mode, effective per-density constraints, and target-aware rejection counts so failed or over-filtered density points can be diagnosed.
- Added regression coverage for target-aware constraint helpers and kept explicit `../xstar/data/atdb.fits` examples as non-persistent paths that do not rewrite `datapath`.

## v0.3.12 - 2026-04-30

- Added constrained absolute-response fitting controls to `examples/40_audit_signed_triplet_response.py`.
- Added `--absolute-fit-reject-pure-i`, `--absolute-fit-pure-i-threshold`, and max/min normalized f/i/r column filters so pure-intercombination columns can be excluded from the absolute-response basis.
- Added `--absolute-fit-component-weights` (`uniform`, `auto`, or explicit f,i,r triple) and `--absolute-fit-weight-floor`; `auto` upweights small XSTAR target components to discourage fits that overproduce weak components.
- Propagated the same constrained absolute-response options through `examples/41_fit_absolute_response_density_grid.py` for density-grid scans.
- Added fit diagnostics for component weights, constraint rejection counts, and selected constraints to the JSON/CSV/Markdown outputs.
- Added tests for the constrained absolute-response helper functions and density-grid CLI propagation.

## v0.3.11 - absolute-response density-grid target scan - 2026-04-30

- Added `examples/41_fit_absolute_response_density_grid.py`, which runs the v0.3.10 absolute-response triplet fit across a list of electron densities and aggregates target/predicted f/i/r, R, G, L1/L2 errors, top source levels, and fit status.
- The new density-grid wrapper preserves explicit `../xstar/data/atdb.fits` usage in example commands while relying on the v0.3.9 datapath-safe resolver behavior: ordinary explicit paths are passed through and do not rewrite `datapath`.
- Added per-density command and log capture plus merged CSV/JSON/Markdown outputs for comparing absolute-response behavior over a full XSTAR density grid.
- Added dry-run regression coverage for the new density-grid wrapper.

## v0.3.10 - Absolute-response source fitting - 2026-04-30

- Added an absolute-response fitting mode to `examples/40_audit_signed_triplet_response.py`.
- New option `--fit-mode absolute-response` fits XSTAR target triplet fractions using positive source-injected absolute f/i/r emissivities, avoiding negative baseline-subtracted delta-response columns.
- Added `--xstar-lines-csv`, `--xstar-value-column`, `--absolute-fit-min-triplet-sum`, and `--fit-max-iter` controls.
- The audit now writes `helike_absolute_response_fit_weights.csv` plus fit diagnostics in `helike_signed_triplet_response_summary.json` and the Markdown report.
- This mode is intended to test whether C V, Mg XI, and Ca XIX failures are caused by delta-response construction rather than missing source levels.

- Changed `xstar_atomic.data.resolve_atdb_path()` so an ordinary explicit `atdb.fits` argument no longer rewrites the persistent `datapath` file. Use `python -m xstar_atomic.data --set-path /path/to/atdb.fits`, `set_data_path(...)`, or `remember_explicit=True` only when intentionally configuring the shared data location.
- `resolve_atdb_path(..., prompt=False)` now raises a clear configuration error when no ATDB file is found instead of attempting a non-interactive download.
- Made `examples/39_scan_helike_source_level_blocks.py` and `examples/40_audit_signed_triplet_response.py` accept an optional `fitsfile`. If omitted, they resolve `atdb.fits` from `XSTAR_ATDB_FITS`, the saved `datapath`, or `data/atdb.fits`. If supplied, the path is passed through without changing `datapath`.
- Updated regression coverage for the new datapath behavior and dry-run diagnostics.

## v0.3.9 - datapath-safe ATDB resolution for diagnostics - 2026-04-30

- Changed `xstar_atomic.data.resolve_atdb_path()` so an ordinary explicit `atdb.fits` argument no longer rewrites the persistent `datapath` file. `find_atdb_file(..., remember=False)` now also honors non-persistent explicit paths. Use `python -m xstar_atomic.data --set-path /path/to/atdb.fits`, `set_data_path(...)`, or `remember_explicit=True` only when intentionally configuring the shared data location.
- `resolve_atdb_path(..., prompt=False)` now raises a clear configuration error when no ATDB file is found instead of attempting a non-interactive download.
- Made `examples/39_scan_helike_source_level_blocks.py` and `examples/40_audit_signed_triplet_response.py` accept an optional `fitsfile`. If omitted, they resolve `atdb.fits` from `XSTAR_ATDB_FITS`, the saved `datapath`, or `data/atdb.fits`. If supplied, the path is passed through without changing `datapath`.
- Updated regression coverage for the new datapath behavior and dry-run diagnostics.

## v0.3.8 - signed/absolute He-like triplet response audit - 2026-04-30

- Added `examples/40_audit_signed_triplet_response.py`, a diagnostic that compares baseline, source-injected, absolute, and delta f/i/r triplet emissivities for each source level.
- The audit reports raw baseline and injected triplet components, normalized injected fractions, signed normalized delta responses, component-wise increase/decrease flags, sign patterns, and whether negative responses are caused by baseline subtraction.
- This diagnostic is intended to distinguish genuinely destructive population redistribution from response-matrix construction artifacts, normalization artifacts, or missing recombination/cascade source physics in non-O VII He-like ions.
- Added regression coverage for the new diagnostic's dry-run command/output path.

## v0.3.7 - Robust He-like block-scan preflight and XSTAR reference diagnostics - 2026-04-30

- Fixed `examples/39_scan_helike_source_level_blocks.py` source-level preflight, which incorrectly imported a non-existent `parse_element` helper from `xstar_atomic.lines`.
  The scanner now uses the existing `choose_z()` API.
- Added an explicit preflight check for the converted XSTAR triplet reference CSV supplied with `--xstar-lines-csv`.
  The scan now warns clearly when the CSV is missing, empty, has no matching ion rows, or lacks one of the f/i/r components needed to compute XSTAR R and G.
- Kept the v0.3.6 invalid-source-level filtering behavior, but improved the failure path so block-fit failures caused by missing/invalid XSTAR references are easier to diagnose before expensive scans are attempted.
- Documentation updated to mention the new v0.3.7 reference-preflight warning.

## v0.3.6 - robust He-like source-level block preflight - 2026-04-30

- Hardened `examples/39_scan_helike_source_level_blocks.py` after Ca XIX block scans failed before discovery when requested blocks included source levels not present for Ca XIX.
- Added ATDB level-table preflight in the block scanner. By default, requested source levels that do not exist for the selected ion are skipped before launching `examples/20_o7_solver_source_fit.py`.
- Added `--no-skip-invalid-source-levels` to recover the old behavior and `--skip-invalid-source-levels` as the explicit default.
- Block-scan CSV output now records requested levels, actually used levels, skipped invalid levels, and paths to per-block `example20.stdout.log` and `example20.stderr.log` files.
- Failed block warnings now point to the saved stderr log, making solver/preflight failures diagnosable instead of opaque.

## v0.3.5 - 2026-04-30

- Added `examples/39_scan_helike_source_level_blocks.py`, a broad source-level block-scan wrapper that runs `examples/20_o7_solver_source_fit.py` over inclusive level ranges such as `2:40`, `41:80`, then applies the discovered-basis diagnostic from example 38.
- The block scan writes exact child commands, per-block fit status, discovery summaries, source-level tables, JSON, and Markdown reports.
- Added dry-run support for planning expensive ATDB/XSTAR scans without executing solver runs.
- Added tests for the block-scan command generation and summary outputs.

## v0.3.4 - ion-specific He-like source-basis discovery - 2026-04-30

- Added `examples/38_discover_helike_source_basis.py`, an offline diagnostic that ranks sampled source levels by their raw forbidden/intercombination/resonance response and discovers ion-specific positive, nonzero source bases.
- The new utility writes per-source, per-density, and per-run CSV/JSON/Markdown reports, including discovered source-level lists that can be reused with `--source-levels` in follow-up example 20/22 runs.
- This diagnostic follows the v0.3.3 result that strict filtering of the reused O VII source-level basis leaves no positive nonzero source levels for C V, Mg XI, or Ca XIX in the current sampled basis.
- Added regression coverage for discovered-basis classification, summary output, and empty-run warnings.

## v0.3.3 - response-basis filter comparison - 2026-04-29

- Added `examples/37_filter_source_basis_response.py`, an offline diagnostic that refits He-like triplet targets after filtering the source-level response basis.
- The new utility compares four source bases for each density: all levels, zero-response levels removed, negative-response levels removed, and positive nonzero response levels only.
- Reports how many source levels survive each filter, whether the filtered basis can still match XSTAR f/i/r components, and how much of the original fitted weight was carried by zero-response or negative-response levels.
- Added regression coverage for the filtered-basis diagnostic using a synthetic response matrix with active, zero-response, and negative-response source levels.

## v0.3.2 - zero-response source accounting fix - 2026-04-29

- Fixed `examples/20_o7_solver_source_fit.py` so source levels with no positive f/i/r response remain zero-response columns instead of being normalized to artificial `1/3,1/3,1/3` vectors.
- Updated `examples/36_source_level_failure_diagnostics.py` to recompute normalized f/i/r fractions and fitted contribution columns from raw response amplitudes, making old v0.3.1 output folders diagnose correctly.
- Added `zero_response_fitted_weight_sum` and `negative_response_fitted_weight_sum` to density-level source diagnostics and console output.
- Added regression coverage for zero-response source levels so they are not converted into uniform triplet contributors.

## v0.3.1 - Source-level diagnostic robustness - 2026-04-29

- Fixed `examples/36_source_level_failure_diagnostics.py` to use the current `ATDB.build_index()` API when `--fitsfile` is supplied, with a defensive fallback for older local trees.
- Added explicit empty-run reporting when a density-grid directory contains no `fit_ne_*` outputs, which commonly means `examples/22` only wrote a template XSTAR mapping and exited.
- Changed source-level diagnostic summaries to report population availability as `available`/`unavailable` instead of misleading `pop=0` for older or incomplete run folders.
- Updated the Markdown interpretation guide for missing population/transition exports and template-only density-grid runs.

## v0.3.0 - He-like source-level failure diagnostics - 2026-04-29

- Added `examples/36_source_level_failure_diagnostics.py` to compare fitted source vectors and response matrices at the individual source-level level across O VII, C V, Mg XI, and Ca XIX density-grid runs.
- The new diagnostic reports source level labels/configurations, fitted source weights, f/i/r response contributions, zero-response flags, optional source-component population sums, dominant radiative decay paths, dominant collisional sink/source paths, and pruning/weak-connectivity indicators.
- Extended `examples/20_o7_solver_source_fit.py` combined-source validation output to request solver population and transition CSVs (`o7_combined_solver_populations.csv`, `o7_combined_solver_transitions.csv`) so future source-level diagnostics can directly measure source-connected component populations and rate paths.
- The source-level diagnostic remains offline/exploratory and does not change the validated O VII `suppress-resonance` behavior or default solver physics.

## v0.2.99 - 2026-04-29

- Added `examples/35_compare_helike_response_matrices.py`, an offline diagnostic that compares fitted source vectors, response matrices, and combined-solver validation behavior across He-like density-grid runs.
- The new comparison writes density-level CSV, run-level CSV, JSON, and Markdown reports identifying why O VII is reachable while C V, Mg XI, and Ca XIX grids are not.
- The diagnostic records XSTAR R/G ranges, fitted and combined R/G availability, simultaneous-solver residuals, response-matrix active-source counts, response-matrix conditioning, top fitted source levels, and a concise failure diagnosis.
- Added a regression test for the new comparison utility.

## v0.2.98 - 2026-04-29

- Improved `examples/34_summarize_helike_validation_runs.py` reporting for multi-condition He-like validation grids.
- Density-grid summaries now prefer the output-directory stem as the run tag, preserving condition labels such as `ca19_xi3` and `ca19_xi4` instead of collapsing both to `ca19`.
- Line-audit summaries now use the audit-directory stem as the audit tag, so low-ionization and high-ionization Ca XIX audits remain distinct in console, CSV, JSON, and Markdown output.
- Updated the validation-summary regression test to require distinct Ca XIX xi/audit tags.

## v0.2.97 - 2026-04-29

- Added `examples/34_summarize_helike_validation_runs.py`, a lightweight reporting utility for completed He-like density-grid validation products.
- The new summary tool reads one or more density-grid output directories from `examples/21`/`examples/22` and optional line-audit directories from `examples/33`.
- It writes machine-readable CSV/JSON and a Markdown report with per-ion status, XSTAR R/G ranges, reachable-density counts, non-null solver diagnostics, and warning counts.
- This makes the current multi-ion status explicit: O VII remains the only validated suppress-resonance benchmark, while C V, Mg XI, and Ca XIX high-xi runs are exploratory/non-validated until solver-side R/G diagnostics become reachable.
- Added `tests/test_helike_validation_summary_example.py` covering the new reporting workflow.

## v0.2.96 - 2026-04-29

- Added ionization-parameter scan support to `examples/32_prepare_helike_xstar_density_grids.py` via `--rlogxi-grid`.
- The default single-`log xi` behavior is preserved, but multi-value grids now generate xi-tagged XSTAR run directories and mapping CSVs such as `ca19_xi3_ne1/` and `xstar_ca19_xi3_density_grid_references.csv`.
- This is intended for Ca XIX, where the default `log xi=1.5` XSTAR runs produced no `ca_xix` triplet rows; use a scan such as `--rlogxi-grid 1.5 2 2.5 3 3.5 4` to locate conditions that actually produce Ca XIX.
- Updated tests for the He-like XSTAR density-grid preparation helper.

## v0.2.95 - 2026-04-29

- Added `examples/33_audit_helike_xstar_lines.py` to diagnose He-like XSTAR line-output files when a prepared triplet converter finds zero rows.
- The new audit reports XSTAR ion-label counts, all nearby wavelength-window rows, expected-ion rows at any wavelength, and rows with He-like ground-to-`n=2` triplet/resonance level labels.
- Documented the Ca XIX use case where XSTAR runs complete but `convert_ca19_triplet.sh` produces empty CSVs, meaning Ca XIX is not testable until a usable triplet target is located.

# v0.2.94 - 2026-04-29

- Hardened the exploratory non-O VII He-like density-grid workflow after the C V, Mg XI, and Ca XIX tests.
- `examples/22_o7_solver_source_fit_density_xstar_grid.py` now validates that each converted XSTAR triplet CSV is not only present but also contains usable forbidden, intercombination, and resonance rows with positive emissivity before launching the expensive subprocess chain. Empty Ca XIX converted CSVs now fail early with a clear message instead of reaching the generic `Could not read XSTAR He-like triplet R/G reference` error.
- `examples/20_o7_solver_source_fit.py` keeps legacy `o7_*` filenames for compatibility but also writes ion-specific aliases such as `c5_solver_source_fit_summary.json` and `mg11_solver_source_fit_summary.json` for non-O VII runs.
- `examples/21_o7_solver_source_fit_density_grid.py` now writes ion-specific density-grid aliases such as `c5_solver_source_fit_density_grid.csv` and uses generic He-like labels in its top-level summary/console heading.
- The C V and Mg XI density-grid outputs should still be treated as non-validated exploratory diagnostics: both show large mismatches/unreachable rows with the current solver/source model. O VII remains the only validated suppress-resonance benchmark.
- Added regression tests for rejecting empty converted triplet CSVs and accepting complete C V-style converted triplet CSVs.

# v0.2.93 - 2026-04-29

- Fixed non-O VII He-like exploratory source-fit reporting when one or more solver-side triplet ratios are unavailable.
- `examples/20_o7_solver_source_fit.py` now prints `NA` for missing uniform, fitted, or combined R/G diagnostics instead of aborting with a `NoneType.__format__` error.
- This lets C V density-grid runs continue after reading the XSTAR target even when the current solver-side response has no usable resonance or intercombination diagnostic.
- Added `tests/test_example20_optional_ratio_format.py`.

# v0.2.92 - 2026-04-29

- Generalized solver-side He-like triplet diagnostics in `src/xstar_atomic/solver.py` so combined simultaneous-solver validation can report R=f/i and G=(f+i)/r for C V, Mg XI, Ca XIX, and other He-like ions, not only O VII.
- The solver now classifies He-like triplet components from `upper_label`/level-label strings such as `1s1.2s1.3S_1`, `1s1.2p1.3P_J`, and `1s1.2p1.1P_1`, while preserving the historical O VII wavelength/level-number fallback.
- Fixed `examples/20_o7_solver_source_fit.py` printing so missing combined-validation R/G values are reported as `NA` instead of raising a `TypeError`.
- Added regression coverage for generic solver-side C V triplet diagnostics.

# v0.2.91 - 2026-04-28

- Added preflight validation for He-like density-grid mapping CSVs before launching the solver-fit subprocess chain.
- Non-O VII density-grid mappings now fail early with a clear message if converted XSTAR triplet CSVs such as `xstar_test_run/c5_ne*/xstar_c5_triplet_lines.csv` are missing in the current package tree.
- Stale non-O VII mappings that still point to `xstar_test_run/xstar_o7_triplet_lines.csv` are now rejected with an explicit diagnostic and regeneration/copy instructions.
- This avoids the confusing downstream `Could not read XSTAR He-like triplet R/G reference` error when users generated C V, Mg XI, or Ca XIX XSTAR products in a different working directory.

# v0.2.90 - 2026-04-28

- Fixed non-O VII density-grid template generation in `examples/22_o7_solver_source_fit_density_xstar_grid.py`.
- New missing mapping CSVs are now written with ion-specific He-like paths such as `xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv`, not the old O VII placeholder path.
- Updated template messages to instruct users to run the example 32 XSTAR/convert workflow if the listed converted triplet CSVs are missing.
- Added regression coverage for C V template generation so `xstar_c5_density_grid_references.csv` does not point to `xstar_o7_triplet_lines.csv`.

# v0.2.89 - 2026-04-28

- Fixed stale non-O VII He-like density-grid mapping propagation in `examples/22_o7_solver_source_fit_density_xstar_grid.py`.
- The density-grid front end now repairs old candidate-ion mapping CSVs, such as `xstar_test_run/xstar_c5_density_grid_references.csv`, when they still point to the O VII placeholder `xstar_test_run/xstar_o7_triplet_lines.csv` and the correct converted per-density files already exist under `xstar_test_run/<ion>_ne*/`.
- A `.bak` copy of the original mapping is preserved before in-place repair.
- This keeps generated solver-fit directories as outputs only while allowing C V, Mg XI, and Ca XIX density-grid comparisons to reuse converted XSTAR triplet CSVs generated by the v0.2.87 helper.

# v0.2.88 - 2026-04-28

- Generalized the XSTAR He-like triplet reference reader used by `examples/20_o7_solver_source_fit.py` and the density-grid wrappers so converted C V, Mg XI, Ca XIX, and other He-like triplet CSVs can be classified from `lower_level`/`upper_level` labels rather than O VII-only wavelengths.
- Fixed non-O VII density-grid validation runs such as C V, which previously failed with `Could not read XSTAR O VII triplet R/G reference` even when the converted XSTAR triplet CSV contained the correct five He-like components.
- Kept the O VII wavelength fallback for older O VII reference files while using label-based f/i/r classification for all He-like ions.

# v0.2.87 - 2026-04-28

- Added `examples/32_prepare_helike_xstar_density_grids.py`, a run-plan generator for density-specific XSTAR triplet grids for the non-O VII candidate ions identified by the He-like type-69 audit.
- The new helper prepares XSTAR run scripts, conversion scripts, per-ion mapping CSVs, a combined run-plan CSV, and a README for C V, Mg XI, and Ca XIX by default.
- The generated references are placed under `xstar_test_run/<ion>_ne*/` after conversion, so `examples/31_helike_type69_ground_resonance_validation.py` can detect them in follow-up audits.
- This release does not mark any additional ion as validated; it only prepares the external XSTAR density-grid runs needed before include-vs-suppress-resonance comparisons can be trusted beyond O VII.

# v0.2.86 - 2026-04-28

- Fixed the He-like type-69 ground-resonance validation audit for multi-letter element symbols.
  The audit now normalizes symbols before looking them up in the ATDB element table, so
  `Ne`, `Mg`, `Si`, `Ar`, `Ca`, and `Fe` are no longer reported as unknown symbols.
- Added regression coverage for normalized ATDB element lookup in
  `examples/31_helike_type69_ground_resonance_validation.py`.
- Clarified that zero-candidate or pending statuses for non-O VII ions are audit results
  and must not be interpreted as validation until density-specific XSTAR triplet grids are supplied.

# v0.2.85 - 2026-04-28

- Added `examples/31_helike_type69_ground_resonance_validation.py`, a broader He-like type-69 ground-resonance audit/validation-status tool.
- The new example audits candidate type-69 ground-to-resonance records for C V, N VI, O VII, Ne IX, Mg XI, Si XIII, S XV, Ar XVII, Ca XIX, and Fe XXV.
- The tool explicitly marks O VII as validated only when the packaged density-specific `xstar_test_run/o7_ne*/` references are present, and marks other He-like ions as pending until density-specific XSTAR triplet grids are supplied.
- Added tests for ion parsing, resonance-label detection, and validation-status classification.

# v0.2.84 - 2026-04-28

- Packaging cleanup: removed the empty generated-output directory `o7_solver_source_fit_density_xstar_grid/` from the source archive. This directory is produced by examples 21/22/30 and is not a package input.
- Packaging cleanup: removed transient `.pytest_cache/` artifacts from the archive.
- Added regression coverage that generated O VII density-grid output directories are not present in the package tree, while compact density-specific inputs remain under `xstar_test_run/o7_ne*/xstar_o7_triplet_lines.csv`.
- Clarified that `examples/26_o7_high_density_rate_sensitivity.py --auto-xstar-test-run-grid` is available in v0.2.83+; older working trees such as v0.2.80 do not expose that option.

# v0.2.83 - 2026-04-28

- Standardized the O VII density-dependent XSTAR benchmark inputs under `xstar_test_run/o7_ne*/xstar_o7_triplet_lines.csv`.
- Added `--auto-xstar-test-run-grid` support to `examples/22_o7_solver_source_fit_density_xstar_grid.py`, so density-specific compact XSTAR CSVs can be discovered automatically without requiring a root-level mapping CSV.
- Updated `examples/26_o7_high_density_rate_sensitivity.py` to accept `--auto-xstar-test-run-grid` or `--xstar-grid-summary-csv` directly, and to reject stale/generated density-grid directories whose `ne=1e12` XSTAR target is inconsistent with the validated density-specific reference.
- Updated `examples/30_o7_density_grid_type69_mode_compare.py` to use packaged `xstar_test_run` density references automatically when no mapping CSV is present.
- Kept generated density-grid solver directories as reproducible outputs, not required package inputs.
- Updated documentation to mark `o7_solver_source_fit_density_xstar_grid/` and related high-density diagnostic directories as outputs and to use the corrected LaTeX user guide baseline.

## v0.2.82

- Added reference snapshots for the v0.2.81 O VII type-69 mode comparison: `o7_density_grid_type69_mode_compare.csv` and `o7_density_grid_type69_mode_compare_summary.json` under both `examples/reference_outputs/` and `docs/validation/xstar_outputs/`.
- Added regression tests that lock in the benchmark behavior: the default `include` network is not reachable at `ne=1e12 cm^-3`, while diagnostic/experimental `suppress-resonance` is reachable and matches the density-specific XSTAR R/G target; lower-density rows remain reachable in both modes.
- Expanded documentation for the O VII high-density benchmark result and reiterated that `suppress-resonance` is a validated diagnostic switch for this benchmark, not a general physical default.

## v0.2.81

- Added `examples/30_o7_density_grid_type69_mode_compare.py`, a side-by-side O VII density-grid comparison of the original type-69 network (`include`) and the diagnostic `suppress-resonance` mode.
- The comparison runs the density-dependent XSTAR grid workflow for both modes, then writes `o7_density_grid_type69_mode_compare.csv` and a JSON summary with per-density R/G ratios, reachability flags, mismatch-improvement factors, source-weight L1 changes, and top fitted source levels.
- Documented that `--collision-type69-ground-excitation-mode suppress-resonance` is diagnostic/experimental: it is validated for the O VII high-density benchmark but is not a general physical default.

## v0.2.80

- Fixed `--collision-type69-ground-excitation-mode suppress-resonance` in `xstar_atomic.solver`.
  v0.2.79 validated the command-line propagation through examples 22 -> 21 -> 20, but the row-level
  mode handler incorrectly raised an error for non-resonance collision rows whenever the mode was
  `suppress-resonance`. The handler now validates the mode once, then applies suppression only to
  matching type-69 ground-to-resonance rows and leaves all other collision rows unchanged.
- Added a regression test that `suppress-resonance` leaves unrelated type-69 rows valid while suppressing
  the O VII ground-to-resonance excitation row.

## v0.2.79

- Fixed propagation of `--collision-type69-ground-excitation-mode` through the chained O VII density-grid workflow.  In v0.2.78, examples 21/22 forwarded the option to `examples/20_o7_solver_source_fit.py`, but example 20 did not expose the corresponding CLI parser option, causing an `unrecognized arguments` failure.
- Added a regression check that example 20 exposes the type-69 ground-excitation suppression option used by the v0.2.78 density-grid command.

## v0.2.78

- Added the diagnostic/experimental solver option `--collision-type69-ground-excitation-mode include|suppress-resonance|suppress-all`.  The `suppress-resonance` mode suppresses type-69 excitation from the ground level into the He-like resonance upper level while preserving the de-excitation direction; for the validated O VII case this targets record 22490, level 1 -> 7.
- Propagated the new mode through `examples/20_o7_solver_source_fit.py`, the density-grid front end (`examples/21/22`), the rate-sensitivity diagnostic (`examples/26`), and the ground-coupling diagnostic (`examples/29`).
- Extended `examples/29_o7_type69_ground_coupling_diagnostic.py` with built-in solver-switch cases for `suppress-resonance` and `suppress-all`, allowing direct comparison with the previous record/direction scaling experiments.
- Added regression coverage for the new switch and the O VII ground-resonance row selection logic.

## v0.2.77

- Hotfix for `examples/29_o7_type69_ground_coupling_diagnostic.py`: fixed `top_weight()` so empty or missing weights-path fields in the example-20 summary are not interpreted as `Path(".")`, which caused `IsADirectoryError` during the baseline case.
- The ground-coupling diagnostic now falls back to the standard per-case fit outputs (`o7_source_fit_weights.csv` and `o7_solver_source_fit_weights.csv`) when the summary omits a usable weights path.
- Added a regression test for the empty-path/directory fallback.

# Changelog

## v0.2.76

- Fixed the v0.2.75 O VII type-69 record-audit annotation lookup so `examples/28_o7_type69_record_audit.py` can find `o7_type69_transition_sensitivity.csv` when given either the CSV path, the output directory, or a parent directory.
- Added `examples/29_o7_type69_ground_coupling_diagnostic.py` to interpret the high-density record-22490 ground--resonance coupling.  The diagnostic compares baseline, record-scaled, all-type-69-scaled, record-removed, excitation-only, de-excitation-only, and direction-specific variants.
- Added solver support for diagnostic direction-specific collision scaling via `--collision-record-direction-scale RECORD:DIRECTION:SCALE`, propagated through `examples/20_o7_solver_source_fit.py`.  This is explicitly diagnostic and intentionally can break detailed balance to isolate excitation versus de-excitation effects.
- Added regression tests for the record-audit annotation lookup, ground-coupling case builder, and direction-scale parser.

## v0.2.75

- Added `examples/28_o7_type69_record_audit.py`, a targeted O VII high-density diagnostic that audits raw XSTAR type-69 records, with emphasis on records `22490`--`22495` and the record `22490` level `1 -> 7` channel identified by the v0.2.74 transition-sensitivity scan.
- The audit writes raw record metadata, decoded level labels/energies/statistical weights, Kato--Nakazaki `calt69` effective collision strengths, excitation/de-excitation coefficients, density-scaled rates, detailed-balance checks, and temperature-grid behavior.
- The audit can optionally ingest the v0.2.74 `o7_type69_transition_sensitivity.csv` output and annotate each record with its best sensitivity case and reachable scaling factors.
- Added regression tests for the new audit helper functions.


## v0.2.74

Added:
- Added `examples/27_o7_type69_transition_sensitivity.py`, a high-density O VII diagnostic that scans individual XSTAR type-69 collision records or level pairs to identify which transitions drive the `ne=1e12 cm^-3` triplet mismatch.
- Added diagnostic collision record scaling to `xstar_atomic.solver` via `--collision-record-scale RECORD:SCALE`; the existing O VII solver-source-fit example now propagates this option to all unit-source and combined-source solver calls.
- Added `tests/test_o7_type69_transition_sensitivity.py` for the transition-sensitivity helper logic.

Notes:
- This is a diagnostic sensitivity scan only. Record-specific or pair-specific scaling is not a physical correction by itself; it is intended to isolate the type-69 transition(s) that make the high-density XSTAR target reachable.

## v0.2.73

Added:
- Added `examples/26_o7_high_density_rate_sensitivity.py`, a high-density O VII rate-network sensitivity diagnostic for the `ne=1e12 cm^-3` mismatch.
- Added diagnostic collision-rate scaling controls to `xstar_atomic.solver`:
  - `--collision-rate-scale` for global evaluated electron-impact rates,
  - `--collision-data-type-scale DATA_TYPE:SCALE`,
  - `--collision-pair-scale LEVEL1:LEVEL2:SCALE`.
- Propagated the diagnostic collision-rate scaling options through `examples/20_o7_solver_source_fit.py` so empirical source fits can be repeated for scaled rate networks.
- Added `tests/test_o7_high_density_rate_sensitivity.py` for scan-case construction and scale specification checks.

Notes:
- The new rate scales are diagnostic sensitivity factors only. They do not modify the packaged atomic data and should not be interpreted as recommended physical rate corrections.
- The primary goal is to determine whether the high-density O VII mismatch is driven by type-68/69 or level-2-to-3/4/5 collisional coupling, or whether additional physics is required.

## v0.2.72

Added:
- `examples/25_o7_high_density_expanded_source_scan.py` for expanded O VII high-density source-level scans.
- The new diagnostic tests whether larger source bases (`baseline`, `n<=5`, `n<=6`, `n<=8`, and `all_levels`) can reach the density-specific XSTAR target at `ne=1e12 cm^-3`.
- `tests/test_o7_high_density_expanded_source_scan.py` dry-run coverage for CI-friendly source-set planning.


## v0.2.71

Added:
- Added `examples/24_o7_high_density_mismatch_diagnostics.py` to investigate the O VII high-density (`ne=1e12 cm^-3`) density-grid mismatch.
- The new diagnostic reads outputs from `examples/21`/`examples/22` and writes component, source-weight, collision-rate, and JSON summary diagnostics.
- It reports which triplet component drives the mismatch, whether the target is reachable, source-weight collapse metrics, solver diagnostics, and optional type-68/69 level-2 -> level-3/4/5 collision rates when `atdb.fits` is supplied.

Updated:
- Documented the high-density mismatch workflow in README, Markdown, LaTeX, and Sphinx example documentation.

## v0.2.70

Added:
- Added `examples/23_prepare_o7_xstar_density_grid.py`, which prepares real O VII XSTAR density-grid validation runs at `ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3`.
- The helper writes `xstar_runs/o7_ne*/run_xstar.sh` scripts containing the full XSTAR commands, `convert_o7_triplet.sh` scripts for converting `xout_lines1.fits` to O VII triplet CSV files, a density-to-CSV mapping file `xstar_o7_density_grid_references.csv`, a run-plan CSV, and `xstar_runs/README_o7_density_grid.md` containing all commands.
- Added tests for the run-preparation helper and generated command contents.

Notes:
- The helper does not run XSTAR.  It prepares reproducible external XSTAR commands and conversion commands so `examples/22_o7_solver_source_fit_density_xstar_grid.py` can later perform a true density-dependent XSTAR comparison once the XSTAR runs have been completed.

## v0.2.69

Fixed:
- Improved `examples/22_o7_solver_source_fit_density_xstar_grid.py` when the requested `--xstar-grid-summary-csv` file is missing. The wrapper now writes a template density-to-XSTAR-lines mapping CSV and exits with a clear message instead of failing with a raw `FileNotFoundError`.

Added:
- `--write-template-grid-csv` to create a starter density-reference mapping CSV.
- `--allow-placeholder-grid` for low-density-placeholder smoke tests only.
- Packaged template CSVs under `examples/reference_inputs/` and `docs/validation/xstar_inputs/`.

Notes:
- The template intentionally reuses the packaged low-density O VII reference as a placeholder for every row. Replace each `xstar_lines_csv` entry with a converted density-specific XSTAR line CSV before using it for scientific validation.

# CHANGELOG

## v0.2.68 - 2026-04-30

Density-dependent XSTAR references for the O VII density-grid diagnostic.

Added:
- Added `examples/22_o7_solver_source_fit_density_xstar_grid.py`, a density-dependent XSTAR reference front end for the O VII density-grid source-fit diagnostic.
- Added `--xstar-lines-csv-by-density DENSITY:CSV` and `--xstar-grid-summary-csv` support to `examples/21_o7_solver_source_fit_density_grid.py`, allowing each density to be compared against its own XSTAR line CSV instead of reusing a single low-density reference.
- Added reference snapshots for the O VII density-grid diagnostic under `examples/reference_outputs/` and `docs/validation/xstar_outputs/`.
- Added lightweight tests for density-specific XSTAR reference parsing, dry-run command generation, and the new example-22 front end.

Documentation:
- Added a short validated O VII diagnostic commands section to README, Markdown guide, LaTeX guide, and Sphinx examples.
- Added a top-level known-limitation note that empirical O VII fitted source weights are diagnostic and are not physical level-resolved recombination rates.
- Documented the density-dependent XSTAR mapping CSV format and repeated `--xstar-lines-csv-by-density` syntax.


## v0.2.67 - 2026-04-29

Data-path resolver and test isolation fixes.

Fixed:
- `resolve_atdb_path(path, prompt=False)` now treats an explicitly supplied path as strict precedence.  If that path is invalid, it raises a clear error instead of silently falling back to `XSTAR_ATDB_FITS` or a saved datapath.
- Updated data-path helper tests to use a minimal FITS-like file that passes the lightweight resolver validation added for zero-byte/truncated-file protection.
- Isolated data-path helper tests from the `XSTAR_ATDB_FITS` environment variable so full-suite runs with a real ATDB configured do not mask explicit-path behavior.

Notes:
- This is a bug-fix release for the v0.2.66 test failures observed when running `XSTAR_ATDB_FITS=../xstar/data/atdb.fits PYTHONPATH=src pytest -q`.

## v0.2.66 - 2026-04-28

Density-grid feasibility flags and clearer XSTAR-target labeling.

Changed:
- Updated `examples/21_o7_solver_source_fit_density_grid.py` so the reused XSTAR target is explicitly labeled as a low-density XSTAR O VII reference reused at all densities.
- Added fit-feasibility columns: `fit_success_vs_xstar` and `target_reachable`.
- Added ratio columns: `refitted_R_over_xstar`, `refitted_G_over_xstar`, `fixed_R_over_refitted`, and `fixed_G_over_refitted`.
- Added warning generation when the source-fit objective is large or the refitted combined R/G ratios remain outside tolerance, with explicit high-density wording for the type-68 coupling regime.
- The density-grid summary JSON now records the XSTAR target label, feasibility tolerances, warnings, and per-density feasibility flags.
- Added tests for the new density-grid feasibility logic and warning behavior without requiring full `atdb.fits`.

Notes:
- The current density-grid example still uses one XSTAR reference at all densities.  A later extension should allow density-dependent XSTAR references, for example `--xstar-lines-csv-by-density` or `--xstar-grid-summary-csv`.

## v0.2.65 - 2026-04-27

Density-grid O VII solver-source-fit diagnostic.

Added:
- Added `examples/21_o7_solver_source_fit_density_grid.py`, which runs the validated O VII full-solver source-fit workflow over a density grid.  The default grid is `ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3` at `T = 1e6 K`.
- The density-grid diagnostic reports both fixed-weight validation, using the reference `ne=1 cm^-3` fitted weights at all densities, and separately refitted weights at each density.
- The output CSV `o7_solver_source_fit_density_grid.csv` includes XSTAR R/G, fixed-weight R/G, refitted linear-response R/G, refitted combined simultaneous-solver R/G, matrix rank, condition number, residuals, negative-population diagnostics, and weight-change metrics relative to the reference density.
- The output JSON `o7_solver_source_fit_density_grid_summary.json` records per-density summary paths, fixed-weight validation products, solver diagnostics, and the largest source-weight changes.
- Added lightweight tests in `tests/test_o7_solver_source_fit_density_grid.py` for the new density-grid example, including dry-run command construction and reference-density ordering without requiring the full `atdb.fits`.

Notes:
- This diagnostic is intended to show whether the empirical fitted O VII source distribution is stable or density-dependent after type-68 metastable/intercombination coupling is active.
- The fitted weights remain empirical solver-response weights, not physical level-resolved recombination rates.

## v0.2.64 - 2026-04-26

Regression/reference checks for the validated O VII solver-source-fit workflow.

Added:
- Added compact saved reference output `examples/reference_outputs/o7_solver_source_fit_summary_reference.json` for the validated O VII full-solver source-fit diagnostic.  This reference stores the XSTAR R/G target, fitted linear-response R/G, combined simultaneous-solver R/G, SVD solver diagnostics, null-rate pruning diagnostics, and negative-population handling without requiring the full 830 MB `atdb.fits` in CI.
- Added `tests/test_o7_solver_source_fit_reference.py` with CI-friendly tests that verify:
  - fitted linear-response R/G matches the saved XSTAR reference,
  - combined-source validation agrees with the fitted linear-response prediction to tight tolerance,
  - the validated diagnostic path uses `linear_solver=svd`, `rank_deficient_action=svd`, `negative_population_action=keep`, and null-rate pruning,
  - the raw-response simplex fitting helper remains numerically reproducible.
- Added a warning in `examples/13_o7_recombination_cascade_workflow.py` when `selected-fit-weights` or `o7-xstar-fit` is used without `--solver-source-total-rate`.  The warning tells users to pass `--solver-source-total-rate 1.0` when consuming weights produced by `examples/20_o7_solver_source_fit.py` with the default `--source-rate=1.0`.
- Workflow summaries from `examples/13_o7_recombination_cascade_workflow.py` now include a `warnings` list so this source-amplitude warning is preserved in machine-readable outputs.

Notes:
- These tests are reference/regression tests for the validated diagnostic output, not full physical ATDB tests.  Full real-ATDB validation is still done by running examples 20 and 13 locally with the real XSTAR `atdb.fits`.
- The empirical fitted-source mode remains diagnostic and amplitude-dependent, not a physical level-resolved recombination model.

## v0.2.63 - 2026-04-25

Documentation update for the validated O VII full-solver source-fit path.

Changed:
- Updated README and Markdown user guide with the validated O VII solver settings: `--linear-solver svd`, `--rank-deficient-action svd`, `--negative-population-action keep`, and `--prune-null-rate-levels`.
- Documented that the combined-source validation in `examples/20_o7_solver_source_fit.py` matches the saved XSTAR O VII triplet ratios with `R/R_XSTAR = 1.00000146` and `G/G_XSTAR = 0.99999836` in the v0.2.62 validation run.
- Added the same validated command sequence to the recombination/cascade workflow documentation, including `--solver-source-total-rate 1.0` and the SVD/rank-aware solver controls.
- Updated the LaTeX user guide with a dedicated Stage-6 full-solver source-fit section and a compact diagnostic summary table.
- Updated Sphinx examples documentation with the same validated workflow and diagnostic caveats.

Notes:
- The fitted source weights remain empirical/diagnostic, not true level-resolved recombination rates.
- Direct dense or sparse solvers are not recommended for this O VII diagnostic unless residuals and combined-source validation are explicitly checked, because the matrix is rank-deficient and highly ill-conditioned.

## v0.2.62 - 2026-04-24

Automatic combined-source validation for the O VII solver-response source-fit diagnostic.

Added:
- `examples/20_o7_solver_source_fit.py` now runs one simultaneous combined-source validation solve after fitting the nonnegative source weights, unless `--skip-combined-validation` is supplied.
- The validation writes `combined_source_validation/o7_combined_fitted_sources.csv`, `o7_combined_solver_lines.csv`, `o7_combined_solver_triplet.csv`, and `o7_combined_solver_summary.json`.
- The top-level `o7_solver_source_fit_summary.json` now reports three R/G comparisons in one place: XSTAR reference, fitted linear-response prediction, and combined simultaneous-solver validation.
- Combined validation diagnostics include matrix rank/size, condition number, linear residuals, source/sink summary, null-rate pruning diagnostics, and raw negative-population counts/minimum/sum diagnostics.
- New options: `--skip-combined-validation` and `--combined-source-total-rate` for controlling the simultaneous validation solve.

Purpose:
- This prevents confusion between an exact response-matrix fit and the actual behavior when the fitted sources are injected together into the full statistical-equilibrium solver.

## v0.2.61 - 2026-04-23

Numerical solver hardening for Stage-6 O VII diagnostics.

Added:
- Rank-aware matrix handling in `xstar_atomic.solver` via `--rank-deficient-action warn|lstsq|svd|reject`.
- Explicit least-squares/SVD solver choices through `--linear-solver lstsq|svd` in addition to `dense|sparse|auto`.
- Per-solve null-rate pruning with `--prune-null-rate-levels` and `--null-rate-floor`, preserving ground, output, and source/sink levels.
- Negative-population controls: `--negative-population-action clip|zero-small|keep|reject` and `--negative-population-tol`.
- Residual diagnostics and optional rejection: `--residual-l2-max`, `--residual-linf-max`, and `--reject-large-residual`.
- Raw population diagnostics before any negative-population handling, including counts and absolute negative-population sum.
- `examples/20_o7_solver_source_fit.py` now defaults to SVD/rank-aware diagnostic solving, keeps raw negative populations by default, and passes null-rate pruning to unit-source solves.
- `examples/13_o7_recombination_cascade_workflow.py` now exposes the same solver-matrix treatment options and records them in the workflow summary.

Changed:
- Rank-deficient matrices are no longer treated as ordinary direct-solve cases by default; the default action is least-squares in the solver CLI and SVD in the O VII diagnostic examples.
- Negative populations are no longer clipped silently: the chosen action and raw negative-population diagnostics are always written to solver summaries.

Notes:
- The default library/CLI behavior remains compatible for general use (`clip` remains the solver default), while the O VII empirical diagnostic examples use `keep` to avoid introducing nonlinear clipping into response-matrix fits.

## v0.2.60 - 2026-04-22

- Corrected `examples/20_o7_solver_source_fit.py` so the empirical solver-response weights are fitted against the **raw full-solver triplet response amplitudes**, with the combined triplet vector normalized only for comparison to the XSTAR R/G target.
- This fixes the v0.2.54--v0.2.59 diagnostic inconsistency where the source-fit script could match XSTAR using per-level normalized response fractions, but the same weights did not reproduce the target when injected simultaneously into `examples/13_o7_recombination_cascade_workflow.py`.
- Added raw-response columns to `o7_source_fit_weights.csv` / `o7_solver_source_fit_weights.csv` so each fitted level shows its raw forbidden, intercombination, and resonance response per unit source.
- The fitted weights remain empirical/diagnostic and amplitude-dependent; continue using `--solver-source-total-rate 1.0` in the cascade workflow when applying weights generated with the default `--source-rate 1.0`.

## v0.2.59 - 2026-04-21

- Captures SciPy `MatrixRankWarning` during sparse statistical-equilibrium solves and falls back to the existing least-squares solver instead of printing repeated warning spam.
- This is especially useful for the O VII solver-response source-fit diagnostic, where some unit-source response matrices are rank-deficient because selected source levels do not independently constrain a unique sparse solution.
- The warning/fallback remains recorded in the solver summary via `solver_warning`; fitted source-response diagnostics should still be judged from the output summary ratios.

## v0.2.58 - 2026-04-20

- Added source-amplitude controls to `examples/13_o7_recombination_cascade_workflow.py`:
  - `--solver-source-scale` multiplies the source/sink CSV passed to the solver.
  - `--solver-source-total-rate` rescales the solver source CSV so the first T/ne block has a requested total source rate.
- This fixes the diagnostic mismatch where solver-response fitted weights from `examples/20_o7_solver_source_fit.py` were derived with unit source rate `1.0 s^-1`, but the cascade workflow applied them at the physical RR source scale (`~1.345e-12 s^-1` at ne=1), causing baseline collisional excitation to dominate.
- `examples/20_o7_solver_source_fit.py` now records `source_rate_s^-1`, `source_rate_note`, and `fit_source_rate_s^-1` in its outputs so the required workflow source amplitude is explicit.
- Recommended fitted-source workflow now uses `--solver-source-total-rate 1.0` when consuming default solver-response weights.

## v0.2.57 - 2026-04-19

Safety fix:
- Hardened NPZ hierarchy index-cache writing so it never uses or replaces the input `atdb.fits` path.
- The cache writer now rejects cache paths that resolve to the FITS file, uses a unique temporary filename in the cache directory, and verifies that the FITS file signature is unchanged before and after cache replacement.
- Added `--index-cache-path` to `examples/20_o7_solver_source_fit.py` so repeated unit-source solver runs can use an explicit cache file away from the XSTAR data file.

Recommended safe usage:

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit \
  --print-summary
```

## v0.2.56 - 2026-04-18

Fixed:
- Made explicit `--source-fit-weights-csv` paths strict, except for the documented legacy cascade-fit path `o7_cascade_source_fit/o7_source_fit_weights.csv`. This prevents a missing solver-response fit file such as `o7_solver_source_fit/o7_source_fit_weights.csv` from silently falling back to the packaged older cascade-fit reference by basename.

Added:
- Recombination summaries now record `source_fit_weights_csv_requested`, `source_fit_weights_csv_resolved`, `source_fit_weight_column`, and `n_source_fit_weights` so fitted-source workflow outputs show exactly which weight file was used.

Notes:
- The uploaded v0.2.55 solver-fit workflow used `solver_source_csv_mode=initial`, but its initial source weights matched the older packaged cascade-fit weights. This happened because the requested solver-response weights CSV was not found relative to the run directory and the basename fallback selected the packaged `o7_source_fit_weights.csv`. v0.2.56 fails fast instead.

## v0.2.55 - 2026-04-17

Fixed:
- Added lightweight `atdb.fits` path validation in the data resolver so empty, truncated, or wrong relative FITS paths fail with a clear message before Astropy raises a low-level `OSError: Empty or corrupt FITS file`.
- `python -m xstar_atomic.data --set-path ...` now rejects invalid `atdb.fits` candidates and suggests setting `XSTAR_ATDB_FITS` or the persistent datapath to the real local XSTAR atomic database.

Notes:
- This version does not change the O VII solver-response source-fit physics. It only improves diagnostics for the path problem seen when rerunning the v0.2.54 workflow with an empty/corrupt `../xstar/data/atdb.fits`.

## v0.2.54 - 2026-04-16

### Added
- Added `examples/20_o7_solver_source_fit.py`, a stricter O VII empirical diagnostic that fits source weights against the full `xstar_atomic.solver` unit-source response matrix rather than the simpler radiative cascade yield matrix.
- The new solver-response fit writes `o7_solver_response_matrix.csv`, `o7_solver_source_fit_weights.csv`, a compatibility alias `o7_source_fit_weights.csv`, and `o7_solver_source_fit_summary.json`.

### Changed
- Documented that the earlier cascade-yield source-fit weights are not expected to reproduce XSTAR R/G when injected into the full statistical-equilibrium solver, because the solver response includes radiative rates, branching, collisional coupling, and normalization effects beyond the cascade-yield matrix.

## v0.2.53 - 2026-04-15

Fixed:
  - examples/13_o7_recombination_cascade_workflow.py now feeds the initial fitted source CSV to the level-population solver for selected-fit-weights and o7-xstar-fit modes by default.
  - Added --solver-source-csv-mode auto|initial|cascade to make this behavior explicit and reproducible.
  - This avoids applying the radiative cascade twice: once in recombination.py and again inside the solver radiative network.

## v0.2.52 - 2026-04-14

Fixed:
- Resolved a path bug in `selected-fit-weights` workflows: missing relative weight CSV paths such as `o7_cascade_source_fit/o7_source_fit_weights.csv` are now resolved against packaged reference locations (`xstar_test_run/`, `examples/reference_outputs/`, and `docs/validation/xstar_outputs/`) when the basename exists there.
- Updated the explicit `selected-fit-weights` documentation examples to use the packaged reference file `xstar_test_run/o7_source_fit_weights.csv`.

## v0.2.51 - 2026-04-14

- Added diagnostic source mode `selected-fit-weights`, which reads fitted level-source weights from `--source-fit-weights-csv`.
- Added convenience source mode `o7-xstar-fit`, which uses `xstar_test_run/o7_source_fit_weights.csv` when no explicit weight CSV is provided.
- Added O VII source-fit reference products to `xstar_test_run/`, `examples/reference_outputs/`, and `docs/validation/xstar_outputs/`.
- Updated the O VII recombination/cascade workflow example to pass source-fit weight CSV options through to `xstar_atomic.recombination`.
- These modes are empirical/diagnostic only; they are not a replacement for true level-resolved recombination rates.

## v0.2.50 - 2026-04-13

- Added `examples/19_o7_cascade_source_fit.py`, a Stage-6 diagnostic for level-resolved O VII cascade-source construction from radiative yield matrices.
- The example builds `Y(source_level -> forbidden, intercombination, resonance)`, writes `o7_cascade_yield_matrix.csv`, fits nonnegative source weights against the saved XSTAR O VII `R=f/i` and `G=(f+i)/r` ratios, and writes `o7_source_fit_weights.csv` plus `o7_source_fit_summary.json`.
- Added helper tests for the nonnegative simplex projection and source-fit optimizer used by the diagnostic.

## v0.2.49 - 2026-04-12

- Added `examples/18_o7_type68_2d_cascade_tuning_scan.py`, a broader Stage-6 O VII type-68-aware tuning scan.
- The new scan varies both forbidden-to-intercombination redistribution and resonance-target suppression using maps of the form `2:(1-d),3:(1+d/3),4:(1+d/3),5:(1+d/3),7:r`.
- The scan writes compact, ranked, all-density CSV tables plus a JSON summary, so the best compromise against the XSTAR O VII `R=f/i` and `G=(f+i)/r` reference can be identified.
- Kept the equal-target `selected-cascade-yield` map as the documented Stage-6 baseline.

## v0.2.48 - 2026-04-11

### Added
- Added type-68-aware O VII cascade tuning presets that preserve equal triplet target weights while progressively downweighting the resonance target level 7: `o7-triplet-type68-r095`, `r090`, `r085`, `r080`, `r075`, `r070`, `r060`, and `r050`.
- Added `examples/17_o7_type68_cascade_tuning_scan.py` to run the equal baseline plus the type-68-aware resonance-weight grid, writing compact and all-density CSV/JSON summaries.

### Changed
- Documentation now distinguishes the pre-type-68 f2i/fdown scans from the type-68-aware resonance-weight scan needed after He-like collision types 67/68/69 are enabled.

## v0.2.47 - 2026-04-10

- Added He-like collisional-excitation decoders/evaluators for XSTAR data types 67, 68, and 69.
  - Type 67 follows `calt67`: `gamma = a + b log10(T) + c log10(T)^2`.
  - Type 68 follows `calt68`: `gamma = a + b log10(T/Z^3) + c log10(T/Z^3)^2`.
  - Type 69 follows `calt69`: Kato--Nakazaki He-like collision-strength fit.
- Extended `COLLISION_DATA_TYPES` to include 67, 68, and 69.
- Updated the O VII metastable/intercombination coupling diagnostic to write `o7_metastable_coupling_collision_inventory.csv`, which inventories all decoded/evaluated collision records involving the selected source/target levels.
- Added unit tests for the type-67/68/69 helper evaluators.

## v0.2.46 - 2026-04-09

Stage-6 diagnostic update.

Added:

- `examples/16_o7_metastable_coupling_diagnostics.py`, a focused O VII diagnostic for level 2 -> levels 3, 4, and 5.
- The diagnostic compares collisional transfer rates `C_2_to_j = n_e q_2j` with decoded radiative rates as a function of electron density.
- Outputs `o7_metastable_coupling_rates.csv` and `o7_metastable_coupling_summary.json`.

Notes:

- The equal-target `selected-cascade-yield` map remains the documented Stage-6 baseline.
- The new diagnostic is intended to determine whether the remaining high O VII `R=f/i` ratio is caused by under-coupled metastable/intercombination transfer or by source/cascade feeding.

## v0.2.45 - 2026-04-08

Stage-6 O VII cascade tuning update.

### Added
- Added forbidden-to-intercombination shift presets that preserve the resonance target and approximately preserve the total triplet-target weight:
  - `o7-triplet-f2i010-rkeep` -> `2:0.90,3:1.0333333333,4:1.0333333333,5:1.0333333333,7:1.0`
  - `o7-triplet-f2i015-rkeep` -> `2:0.85,3:1.05,4:1.05,5:1.05,7:1.0`
  - `o7-triplet-f2i025-rkeep` -> `2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0`
  - `o7-triplet-f2i050-rkeep` -> `2:0.50,3:1.1666666667,4:1.1666666667,5:1.1666666667,7:1.0`

### Changed
- Kept the equal-target map `2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` as the documented Stage-6 baseline.
- Updated `examples/15_o7_cascade_tuning_scan.py` so the default tuning scan now includes the new forbidden-to-intercombination shift presets before the older simple `fdown` comparison cases.
- Updated `o7-triplet-xstar-tuned` as a backward-compatible alias to the preferred `f2i025` shift experiment.
- Updated README, Markdown, LaTeX, and Sphinx documentation to describe the new Stage-6 tuning strategy: preserve `G=(f+i)/r` by keeping the total triplet/resonance balance close to the equal-target case while shifting source weight from forbidden to intercombination levels.

## v0.2.44 - 2026-04-07

### Added
- Added Stage-6 O VII cascade tuning presets that downweight the forbidden target while preserving the resonance target: `o7-triplet-fdown090-rkeep`, `o7-triplet-fdown085-rkeep`, and `o7-triplet-fdown075-rkeep`.
- Added `examples/15_o7_cascade_tuning_scan.py`, which runs the equal-target baseline plus forbidden-downweighted presets and writes CSV/JSON summaries of `R=f/i` and `G=(f+i)/r` relative to the saved XSTAR O VII reference.

### Changed
- Kept the equal-target map `2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` as the recommended Stage-6 baseline.
- Updated README, Markdown, LaTeX, and Sphinx documentation to describe the Stage-6 tuning scan workflow.

## v0.2.43 - 2026-04-06

Completed Stage-5 heavy-ion XSTAR wavelength validation.

- Added validated Mg XI, Mg XII, Si XIII, Si XIV, Fe XXV, and Fe XXVI XSTAR `xout_lines1.fits` artifacts under `xstar_test_run/`.
- Added converted selected-line CSV products for Mg/Si/Fe validation under `xstar_test_run/`.
- Added Mg/Si/Fe wavelength comparison CSV/JSON files under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Added tests checking the Mg/Si/Fe validation artifacts and wavelength matches.
- Updated README and Sphinx/Markdown comparison docs to mark Mg/Si/Fe Stage-5 validation as completed rather than pending.

## v0.2.42 - 2026-04-06

Stage-5 heavy-ion validation planning update.

- Added reproducible direct-XSTAR run recipes to `xstar_test_run/README.md` for Mg XI, Mg XII, Si XIII, Si XIV, Fe XXV, and Fe XXVI.
- Added suggested first-pass wavelength windows and `xstar_atomic.xstar_outputs` FITS-to-CSV commands for Mg/Si/Fe validation products.
- Added wavelength-comparison command templates for the corresponding `examples/08_compare_xstar_outputs.py` runs.
- Updated README and XSTAR comparison documentation to mark Mg/Si/Fe as the pending Stage-5 completion targets after the validated O/Ne workflow.

## v0.2.41 - 2026-04-05

- Fixed Sphinx ``user_guide.rst`` heading underline length for ``Downloading and configuring atdb.fits`` so ``make html`` builds without the title-underline warning.

## v0.2.40 - 2026-04-05

Fixed:

- Corrected the Sphinx user-guide heading underline for ``Downloading and configuring atdb.fits`` so ``make html`` builds without the title-underline warning.
- Kept the v0.2.39 documentation updates for ``download_data()``, data-path resolution, NPZ cache performance, and Stage-6 cascade workflow notes.

## v0.2.39 - 2026-04-05

Documentation and Stage-6 result update.

- Refreshed Markdown, LaTeX, and Sphinx documentation for the current data-management API: `download_data()`, `resolve_atdb_path()`, `find_atdb_file()`, `get_data_path()`, and `set_data_path()`.
- Documented path-resolution precedence: explicit path, `XSTAR_ATDB_FITS`, persistent `datapath`, project/package `data/atdb.fits`, then interactive download/configuration.
- Documented the single-line ASCII download progress bar and the source-tree default `data/` and `datapath` locations.
- Updated solver/cache documentation to recommend the array-backed NPZ cache path validated in v0.2.27/v0.2.28.
- Added Stage-6 result guidance: equal-target cascade-yield remains the recommended baseline; the `o7-triplet-fdown-rkeep` preset decreases `R=f/i` but also lowers `G=(f+i)/r`, so it is experimental.
- Fixed LaTeX listing styles using `ctpython` and `ctterminal`; Python listings now have syntax highlighting and terminal listings use a separate style.
- Normalized code listings so ion names appear as `O VIII`, not with visible-space markers.

## v0.2.38 - 2026-04-04

- Fixed `examples/13_o7_recombination_cascade_workflow.py` so the recommended equal O VII target map is only passed when no non-`none` `--cascade-target-preset` is selected.
- This prevents the default `--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` from overriding experimental presets such as `o7-triplet-fdown-rkeep`.
- The recommended Stage-6 baseline remains the equal-target map. The `o7-triplet-fdown-rkeep` preset remains an experimental forbidden-downweighted, resonance-preserved map.

## v0.2.37 - 2026-04-03

Stage-6 O VII cascade-source tuning update.

Changed:
- Keep the documented/recommended ``selected-cascade-yield`` target map as equal triplet targets: ``2:1.0,3:1.0,4:1.0,5:1.0,7:1.0``.
- Add a new forbidden-downweighted, resonance-preserved experimental preset: ``--cascade-target-preset o7-triplet-fdown-rkeep`` -> ``2:0.5,3:1.0,4:1.0,5:1.0,7:1.0``.
- Update ``o7-triplet-xstar-tuned`` as a backward-compatible alias to the new resonance-preserved map, replacing the earlier resonance-downweighted map.
- Update the Stage-6 workflow example and docs to avoid recommending the resonance-downweighted preset, which overestimated G=(f+i)/r.

## v0.2.36 - 2026-04-02

Fixed:
- Data-path helper round-trip test now removes ``XSTAR_ATDB_FITS`` during the isolated datapath test. This preserves the intended runtime precedence: explicit path, ``XSTAR_ATDB_FITS``, saved ``datapath``, project/package ``data/``, then interactive download/configuration.

Added:
- ``--cascade-target-preset o7-triplet-xstar-tuned`` for Stage-6 O VII triplet cascade-source experiments.
- The preset expands to ``2:0.6,3:1.0,4:1.0,5:1.0,7:0.4``.
- Manual ``--cascade-target-levels`` remains available and overrides the preset.

## v0.2.35 - 2026-04-01

Stage 6 recombination/cascade improvements:
- Added `selected-cascade-yield` recombination source allocation mode.
- Added `--cascade-target-levels` and `--cascade-weight-floor` to `xstar_atomic.recombination`.
- Updated the O VII recombination/cascade workflow example to use cascade-yield source weighting by default.
- Added unit coverage for cascade-yield source allocation helpers.

## v0.2.34 - 2026-03-31

- Added validated Ne IX / Ne X Stage-5 XSTAR comparison artifacts.
- Added `xstar_test_run/ne_xi25/xout_lines1.fits` and `xstar_test_run/ne_xi35/xout_lines1.fits`.
- Added converted CSV line lists for Ne IX triplet/near-triplet and Ne X Ly-alpha.
- Added saved comparison CSV/JSON outputs to `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Updated XSTAR comparison documentation from planned neon runs to completed validation examples.

## v0.2.33 - 2026-03-30

Documentation/examples:
- Added dedicated Stage-5 Ne IX and Ne X direct-XSTAR validation run commands to `xstar_test_run/README.md`.
- Added FITS-to-CSV and `examples/08_compare_xstar_outputs.py` commands for Ne IX He-like triplet/near-triplet and Ne X Ly-alpha wavelength comparisons.
- Updated XSTAR comparison documentation and Sphinx comparison page to list the planned Ne IX/Ne X validation products.

## v0.2.32 - 2026-03-29

Fixed:
  - Replaced multi-line download progress messages with a single in-place ASCII progress bar.
  - Download progress now displays as: `xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)`.

## v0.2.31 - 2026-03-28

Fixed:
- Store the source-tree ``datapath`` file at the project root (for example ``xstar_atomic/datapath``) rather than in ``src/xstar_atomic/``.
- Removed the packaged ``src/xstar_atomic/datapath`` data file from package-data/MANIFEST entries.
- Kept the project-level ``data/`` directory as the default ``atdb.fits`` download destination when running from ``PYTHONPATH=src``.

## v0.2.30 - 2026-03-27

Fixed:
- Changed the default interactive ``download_data()`` destination for source-tree use from ``src/xstar_atomic/data`` to the project-level ``data`` directory.
- Changed the source-tree ``datapath`` file location from ``src/xstar_atomic/datapath`` to the project-level ``datapath`` file, while retaining installed-package fallback behavior.

## v0.2.28 - 2026-03-25

Documentation/examples:
- Documented the validated array-backed NPZ cache performance from v0.2.27: O VIII sparse solver profile dropped from about 5.31 s uncached to about 0.53 s on an NPZ array-backed cache hit.
- Made the array-backed NPZ cache the recommended default for repeated solver, export, high-level API, and profiler workflows.
- Updated README, Markdown user guide, LaTeX user guide, and Sphinx user/examples pages with `--index-cache --index-cache-format npz` examples.
- Updated `examples/12_profile_solver_steps.py` documentation to use the recommended NPZ cache path.

## v0.2.27 - 2026-03-24

Fixed:
- Restored the public array-backed `ATDB.select_records(z=..., ion_stage=..., data_type=..., rate_type=...)` API by renaming the legacy materialized-list filter helper to `filter_records`.
- Fixed `examples/12_profile_solver_steps.py --index-cache --index-cache-format npz`, which failed in v0.2.26 because the legacy helper shadowed the new fast-selection method.

## v0.2.26 - 2026-03-23

Added:
- Added `ATDBIndexArrays`, an array-backed hierarchy index for fast targeted selection.
- Added `ATDB.build_index_arrays(...)` and `ATDB.select_records(...)`.
- NPZ cache hits can now filter numeric arrays and convert only selected rows to `IndexedRecord` objects.
- Updated solver, profiler, and high-level API paths to use array-backed selection for NPZ index caches.
- Added tests for array-backed selection/reconstruction.

Changed:
- `--index-cache-format npz` now avoids reconstructing all 1.2 million records in targeted solver/profiler/API paths.

## v0.2.25 - 2026-03-22

Fixed:
- Reworked the NPZ index cache into a slimmer numeric v2 layout.
- Avoided storing large repeated Unicode arrays for each ATDB record in the NPZ cache.
- Old v0.2.24 NPZ caches are now treated as stale and rebuilt automatically.

Changed:
- The compact cache still returns normal IndexedRecord objects for decoder compatibility, but reconstructs repeated labels from numeric fields and the small element/ion tables.

## v0.2.24 - 2026-03-21

Added:
- Added compact NumPy/NPZ hierarchy index cache support for `ATDB.build_index()`.
- `--index-cache` now defaults to the NPZ cache path `atdb.fits.xstar_atomic_index.npz`.
- Added `--index-cache-format npz|pickle` to hierarchy, solver, export, and solver-step profiler CLIs.
- Preserved legacy pickle cache support with `--index-cache-format pickle`.

Changed:
- `XSTARAtomic(..., index_cache=True)` now uses the NPZ cache by default.
- Cache status strings now distinguish `npz_hit`, `npz_written`, `pickle_hit`, and related states.

## v0.2.23 - 2026-03-20

Added:
- Optional on-disk ATDB hierarchy index caching via ``ATDB.build_index(use_cache=True)``.
- ``--index-cache`` and ``--rebuild-index-cache`` options for the hierarchy, solver, export, and solver-step profiling workflows.
- Cache metadata validation against the source ``atdb.fits`` file size, modification time, array lengths, and cache format version.
- Real-ATDB cache round-trip test for cache creation and cache hits.

Changed:
- Solver/export/profile summaries now report ``index_cache_status`` and ``index_cache_path`` when caching is used.

## v0.2.22 - 2026-03-19

### Fixed

- Fixed `examples/12_profile_solver_steps.py` by adding the missing
  `auto_recombination_cascade=False` default to the solver argument namespace used
  by the profiling workflow.

### Documentation

- Documented that an optional C++ backend can be implemented as a shared-object
  library while preserving the Python/SciPy reference backend.
- Added notes on the Stage-6 O VII recombination/cascade workflow: total O VIII
  -> O VII recombination is redistributed over selected O VII levels, radiative
  branching cascade sources are written to CSV, the sparse solver reads those
  sources, and prototype R=f/i and G=(f+i)/r diagnostics are compared with XSTAR
  triplet output ratios.

## v0.2.21 - 2026-03-18

### Added
- Added `examples/12_profile_solver_steps.py` to profile individual solver stages: ATDB open/read, index building, level/line/collision extraction, collision evaluation, matrix assembly, solve, and output writing.
- Added `examples/13_o7_recombination_cascade_workflow.py`, a prototype Stage-6 O VII workflow that builds recombination source CSVs, performs approximate radiative cascade redistribution, feeds the cascade source into the sparse solver, and compares O VII triplet diagnostics with an optional XSTAR line-output CSV.

### Notes
- Documented that an optional C++ backend can be implemented as a shared-object (`.so`) library loaded from Python, with the pure-Python/SciPy implementation retained as the reference/fallback path.
- The O VII cascade workflow remains a prototype: current oxygen RR/DR records are total recombination rates, not true level-resolved recombination-cascade records.

## v0.2.20 - 2026-03-17

### Added
- Added `examples/11_solver_timing.py` to benchmark end-to-end level-population solver execution times.
- The timing example compares O VIII dense and sparse solver modes and can optionally include the heavier O VII triplet sparse stress test.
- Timing CSV rows include elapsed wall time, solver used, sparse status, matrix size, nonzero count, density, condition number, and residual diagnostics.

### Documentation
- Updated the Markdown, LaTeX, and Sphinx user guides with solver timing commands and notes on when a C++ backend could improve performance.

## v0.2.19 - 2026-03-16

### Solver
- Improved Stage-3 level-population solver diagnostics for sparse and dense solves, including matrix nonzero counts, matrix density, singular-value/rank diagnostics, diagonal and row-sum ranges, residual norms, and explicit sparse-use flags.
- Added optional connectivity pruning with `--prune-unconnected-levels`, preserving ground, output, and explicit source/sink levels.
- Added source/sink vector summaries to solver JSON output, including nonzero level terms and source/sink totals for recombination/cascade source-file tests.
- Added O VII triplet diagnostic support with `--triplet-diagnostics` and `--out-triplet-csv`, reporting prototype `R=f/i` and `G=(f+i)/r` ratios when O VII triplet lines are selected.

### Documentation and examples
- Updated the user guide and examples for sparse solver runs, connectivity pruning, source/sink diagnostics, and O VII triplet diagnostics.
- Added `examples/10_o7_triplet_sparse_solver.py` as the Stage-3 solver stress-test example.

### Tests
- Added unit tests for solver diagnostics, pruning, source/sink summaries, and O VII triplet R/G helper calculations.

## v0.2.18 - 2026-03-15

### Documentation
- Updated the Markdown, LaTeX, and Sphinx user-guide material for the validated Stage-4 band-emissivity export workflow.
- Documented `--bands-kev`, `*_band_emissivity.csv`, and HDF5 `/band_emissivity` products.
- Recorded the v0.2.17 Stage-4 real-ATDB validation result: 34 passing tests, 12 band-emissivity rows per ion for four bands and three temperatures, nonblank `ion`, and `methods_used="none"` for zero-line bands.

### Examples
- Added `examples/09_export_band_emissivity.py` for CSV/HDF5 export of line-based X-ray band emissivity products.

## v0.2.17 - 2026-03-14

### Fixed
- Filled the `ion` field for all band-emissivity rows, including zero-line bands.
- Set `methods_used="none"` for zero-line band-emissivity rows.

### Tests
- Added unit and real-ATDB export tests that check band-emissivity rows do not contain blank ion names or blank method fields.

## v0.2.15 - 2026-03-13

### Added
- Added HDF5 export support to `xstar_atomic.export` via `--formats hdf5` or `--formats csv,hdf5`.
- Added a general CLI alias `xstar-atomic-export` while keeping `xstar-atomic-export-superwind` for backward compatibility.
- Added optional SciPy sparse-matrix support to the level-population solver via `--linear-solver sparse` or `--linear-solver auto`.
- Added tests for HDF5 export helpers and sparse-solver fallback/consistency.

### Changed
- Generalized export documentation and manifests for plasma post-processing workflows beyond superwinds, including AGN outflows.
- The export manifest is now written as `atomic_export_manifest.json` and also as the legacy `superwind_export_manifest.json`.


## v0.2.14 - 2026-03-12

### Added
- Added `xstar_test_run/` with direct-XSTAR `xout_lines1.fits` outputs, converted CSV line tables, and a README documenting the exact XSTAR commands and FITS-to-CSV conversion workflow.
- Added tests for packaged XSTAR test-run artifacts and conversion consistency.

### Documentation
- Updated XSTAR comparison documentation to reference `xstar_test_run/` and the included O VIII/O VII validation CSV files.

## v0.2.13 - 2026-03-11

### Added
- Added `xstar_test_run/` with direct-XSTAR `xout_lines1.fits` outputs, converted CSV line tables, and a README documenting the exact XSTAR commands and FITS-to-CSV conversion workflow.
- Added tests for packaged XSTAR test-run artifacts and conversion consistency.

### Documentation
- Updated XSTAR comparison documentation to reference `xstar_test_run/` and the included O VIII/O VII validation CSV files.

## v0.2.12 - 2026-03-10

### Added
- Added saved XSTAR-vs-`xstar-atomic` comparison outputs for O VIII Ly-alpha and the O VII triplet under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Added `docs/xstar_comparison_examples.md` documenting the XSTAR-output comparison workflow and validation results.
- Added Sphinx page `xstar_comparisons.rst` and linked it from the Sphinx index.

### Documentation
- Documented that O VIII Ly-alpha wavelength agreement is at the ~1e-5 Angstrom level.
- Documented that O VII triplet wavelength agreement is at the ~1e-7 to 8e-7 Angstrom level.
- Clarified that XSTAR model `emit_*` columns are not directly equivalent to local `xstar-atomic` emissivity coefficients without model-dependent normalization.

## v0.2.11 - 2026-03-09

Added:
- Extended ``examples/08_compare_xstar_outputs.py`` with explicit ``--mode`` choices: ``wavelength``, ``emissivity``, and ``both``.
- Added ``--out-csv`` and ``--out-json`` outputs for XSTAR-vs-xstar-atomic comparison tables.
- Added clearer warnings/notes that XSTAR model ``emit_*`` columns are not directly equivalent to local atomic emissivity coefficients.

## v0.2.10 - 2026-03-08

Fixed:
- Added `--wavelength-column` to `examples/08_compare_xstar_outputs.py`.
- The comparison example now auto-detects `wavelength_A` or `wavelength` columns in XSTAR-output CSV files.

## v0.2.9 - 2026-03-07

### Added
- Added `xstar_atomic.xstar_outputs` for reading XSTAR `xout_lines*.fits` files.
- Added CLI entry point `xstar-atomic-xstar-outputs` and module execution with `python -m xstar_atomic.xstar_outputs`.
- Supports CSV export, JSON summaries, and filtering by ion, wavelength, and emission columns.

## v0.2.8 - 2026-03-06

### Fixed
- Added the missing solver CLI argument `--electron-density-for-lmixing`.
- Fixed the real-ATDB solver status test failure caused by the solver referencing `args.electron_density_for_lmixing` without registering the argparse option.

## v0.2.7 - 2026-03-05

### Added
- Added a scientific validation status table to the Markdown and LaTeX user guides.
- Added `xstar_atomic.export` with CSV/JSON export helpers for superwind/Athena++ post-processing.
- Added CLI entry point `xstar-atomic-export-superwind`.
- Added `examples/08_compare_xstar_outputs.py` for comparing selected xstar-atomic outputs against user-supplied XSTAR CSV outputs.
- Added lightweight import tests for the export module.

### Improved
- Updated solver diagnostics to report that the XSTAR-derived type-63 same-n l-mixing collision decoder is enabled.
- Updated docs to reflect the implemented type-63 same-n l-mixing path and the current validation status of data types 51 and 98.

## v0.2.6 - 2026-03-04

### Added
- Added `tests/data/collision_type51_98_targets.csv`, generated from the collision validation inventory.
- Added API-level real-ATDB pytest coverage for representative collision `data_type=51` and `data_type=98` targets through `XSTARAtomic.collisions(...)`.
- Added a type-98 ion-alias API regression test using the `ne_ix` alias.

### Validation
- The type-51 API test validates a representative Burgess--Tully 5-point target against the inventory reference rate.
- The type-98 API test validates the Ne IX CHIANTI-style Burgess--Tully target against the inventory reference rate.

## v0.2.5 - 2026-03-03

### Fixed
- Restored the lightweight top-level `parse_ion` export so `from xstar_atomic import parse_ion` works again after the lazy-import cleanup.
- Kept the minimal top-level API limited to `ATDB`, `XSTARAtomic`, and `parse_ion`; decoder functions remain importable from their submodules.


## v0.2.4 - 2026-03-02

### Fixed
- Cleaned reStructuredText in module docstrings for the Sphinx API build.
- Fixed docutils warnings/errors in `photoionization`, `collisions`, and `recombination` module documentation.

## v0.2.3 - 2026-03-01

### Added
- Added `xstar_atomic.validation` with collision-decoder inventory and validation helpers.
- Added CLI entry point `xstar-atomic-validate-collisions`.
- Added `examples/07_collision_decoder_validation.py` for type 51/98 target discovery and type-63 same-`n` diagnostics.
- Added real-ATDB pytest checks for:
  - O VIII type-63 same-`n` l-mixing regression diagnostics.
  - Type 51 and type 98 inventory plus representative positive-rate targets when present in the local `atdb.fits`.

### Notes
- The type-63 same-`n` diagnostic checks the Python port of the XSTAR `amcrs/velimp` branch, but independent validation against XSTAR model outputs is still recommended for production science.

## v0.2.2 - 2026-02-28

### Fixed
- Corrected LaTeX backslash corruption in `docs/user_guide.tex` for the `center` and `tabular` environments.

## v0.2.1 - 2026-02-27

### Changed
- Simplified ``xstar_atomic.__init__`` to expose only ``ATDB``, ``XSTARAtomic``, and ``__version__``.
- Moved heavy decoder imports in ``api.py`` to lazy method-level imports.
- Preserved submodule-level imports such as ``xstar_atomic.collisions`` and ``xstar_atomic.recombination``.

### Fixed
- Avoids ``runpy`` warnings when executing CLI modules with ``python -m xstar_atomic.<module>`` after importing the package.

## v0.2.0 - 2026-02-26

### Added
- Implemented the type-63 same-`n` l-changing collision branch using the XSTAR `amcrs`/`velimp` ecm=0 logic.
- Added `electron_density_for_lmixing` to the high-level collision/emissivity APIs for the density-dependent impact-parameter cutoff used by same-`n` l-mixing.
- Added `--electron-density` to `xstar-atomic-collisions` and `--electron-density-for-lmixing` to emissivity/solver CLIs.
- Added diagnostic columns for same-`n` type-63 l-mixing: shell radiative sum, `cn`, selected `l` branch, and density.

### Improved
- Promoted collision data type 51 and 98 Burgess--Tully evaluators as supported collision-rate paths alongside type 56 and type 63.
- Updated package tests to check that real-ATDB type-63 same-`n` l-mixing returns finite evaluated rates when `XSTAR_ATDB_FITS` is supplied.

## v0.1.8 - 2026-02-25

### Documentation
- Added `\usepackage{amsmath,amssymb}` to the LaTeX user guide preamble for math support.


All notable changes to `xstar-atomic` are documented here.

## v0.1.7 - 2026-02-24

Fixed:
- Restored backward-compatible high-level API keys used by the examples:
  - `collisions()["matches"]` and `collisions()["evaluated_rates"]`.
  - `emissivity()["rows"]`.
  - `recombination()["summary"]`.
- Updated example/API behavior so the examples work with the current return dictionaries.

## v0.1.6 - 2026-02-23

### Added
- Added full user guide in Markdown: `docs/user_guide.md`.
- Added full user guide in LaTeX: `docs/user_guide.tex`.
- Added Sphinx documentation scaffold under `docs/sphinx/` using `sphinx.ext.autodoc`, `sphinx.ext.napoleon`, and the Read the Docs theme.
- Added Sphinx pages for user guide, examples, API reference, development notes, and changelog.
- Added `examples/06_high_level_api_quickstart.py`.
- Added optional `docs` dependency group with `sphinx` and `sphinx-rtd-theme`.

### Notes
- Sphinx API pages are generated from Python docstrings. Future public functions/classes should include clear docstrings.

## v0.1.5 - 2026-02-22

### Added
- Added flexible ion-name parsing in the high-level API. Accepted forms now include `O VIII`, `o viii`, `o_viii`, `O_VIII`, `O-VIII`, `OVIII`, and `o8`.
- Added unit tests for ion-name aliases.

## v0.1.4 - 2026-02-21

### Added
- Added real pytest smoke tests for the direct `atdb.fits` workflow.
- Added API smoke tests for:
  - low-level `ATDB.build_index()` counts,
  - O VIII Ly-alpha line extraction,
  - O VIII Ly-alpha collision-rate evaluation,
  - O VIII Ly-alpha emissivity table generation,
  - oxygen recombination inventory.
- Added CLI smoke tests using `python -m xstar_atomic.*` modules.
- Added `examples/` scripts:
  - `01_o8_lya_lines.py`,
  - `02_o8_lya_collisions.py`,
  - `03_o8_lya_emissivity.py`,
  - `04_oxygen_recombination_inventory.py`,
  - `05_low_level_atdb_index.py`.
- Added this versioned `CHANGELOG.md`.

### Notes
- Tests that require the real XSTAR database are skipped unless `XSTAR_ATDB_FITS` points to a readable `atdb.fits` file.
- Example test command:

  ```bash
  XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits pytest -q
  ```

## v0.1.3 - 2026-02-20

### Fixed
- Fixed the high-level `XSTARAtomic.emissivity()` wrapper by adding the missing `collision_data_type` default expected by the emissivity filters.

## v0.1.2 - 2026-02-19

### Fixed
- Fixed the high-level `XSTARAtomic.emissivity()` wrapper by adding the missing `include_superlevel_radiative` default expected by the emissivity filters.

## v0.1.1 - 2026-02-18

### Added
- Added the high-level `XSTARAtomic` API wrapper around the low-level `ATDB` reader.
- Added convenience methods for lines, collisions, recombination, and emissivity workflows.
- Kept `ATDB` as the low-level direct packed-FITS API.

## v0.1.0 - 2026-02-17

### Added
- Initial package refactor from validated standalone scripts.
- Added package namespace `xstar_atomic` and project name `xstar-atomic`.
- Added command-line modules for:
  - inspecting `atdb.fits`,
  - hierarchy reconstruction,
  - lines,
  - photoionization,
  - collisions,
  - recombination,
  - emissivity,
  - prototype level-population solving.

## v0.2.82 - 2026-04-28

- Added reference snapshots for the v0.2.81 O VII type-69 mode comparison: `o7_density_grid_type69_mode_compare.csv` and `o7_density_grid_type69_mode_compare_summary.json` under both `examples/reference_outputs/` and `docs/validation/xstar_outputs/`.
- Added regression tests that lock in the benchmark behavior: the default `include` network is not reachable at `ne=1e12 cm^-3`, while diagnostic/experimental `suppress-resonance` is reachable and matches the density-specific XSTAR R/G target; lower-density rows remain reachable in both modes.
- Expanded documentation for the O VII high-density benchmark result and reiterated that `suppress-resonance` is a validated diagnostic switch for this benchmark, not a general physical default.

## v0.2.81 - 2026-04-28

- Added `examples/30_o7_density_grid_type69_mode_compare.py`, a side-by-side O VII density-grid comparison of the original type-69 network (`include`) and the diagnostic `suppress-resonance` mode.
- The comparison runs the density-dependent XSTAR grid workflow for both modes, then writes `o7_density_grid_type69_mode_compare.csv` and a JSON summary with per-density R/G ratios, reachability flags, mismatch-improvement factors, source-weight L1 changes, and top fitted source levels.
- Documented that `--collision-type69-ground-excitation-mode suppress-resonance` is diagnostic/experimental: it is validated for the O VII high-density benchmark but is not a general physical default.

## v0.2.80 - 2026-04-28

- Fixed `--collision-type69-ground-excitation-mode suppress-resonance` in `xstar_atomic.solver`.
  v0.2.79 validated the command-line propagation through examples 22 -> 21 -> 20, but the row-level
  mode handler incorrectly raised an error for non-resonance collision rows whenever the mode was
  `suppress-resonance`. The handler now validates the mode once, then applies suppression only to
  matching type-69 ground-to-resonance rows and leaves all other collision rows unchanged.
- Added a regression test that `suppress-resonance` leaves unrelated type-69 rows valid while suppressing
  the O VII ground-to-resonance excitation row.

## v0.2.79 - 2026-04-27

- Fixed propagation of `--collision-type69-ground-excitation-mode` through the chained O VII density-grid workflow.  In v0.2.78, examples 21/22 forwarded the option to `examples/20_o7_solver_source_fit.py`, but example 20 did not expose the corresponding CLI parser option, causing an `unrecognized arguments` failure.
- Added a regression check that example 20 exposes the type-69 ground-excitation suppression option used by the v0.2.78 density-grid command.

## v0.2.78 - 2026-04-27

- Added the diagnostic/experimental solver option `--collision-type69-ground-excitation-mode include|suppress-resonance|suppress-all`.  The `suppress-resonance` mode suppresses type-69 excitation from the ground level into the He-like resonance upper level while preserving the de-excitation direction; for the validated O VII case this targets record 22490, level 1 -> 7.
- Propagated the new mode through `examples/20_o7_solver_source_fit.py`, the density-grid front end (`examples/21/22`), the rate-sensitivity diagnostic (`examples/26`), and the ground-coupling diagnostic (`examples/29`).
- Extended `examples/29_o7_type69_ground_coupling_diagnostic.py` with built-in solver-switch cases for `suppress-resonance` and `suppress-all`, allowing direct comparison with the previous record/direction scaling experiments.
- Added regression coverage for the new switch and the O VII ground-resonance row selection logic.

## v0.2.77 - 2026-04-27

- Hotfix for `examples/29_o7_type69_ground_coupling_diagnostic.py`: fixed `top_weight()` so empty or missing weights-path fields in the example-20 summary are not interpreted as `Path(".")`, which caused `IsADirectoryError` during the baseline case.
- The ground-coupling diagnostic now falls back to the standard per-case fit outputs (`o7_source_fit_weights.csv` and `o7_solver_source_fit_weights.csv`) when the summary omits a usable weights path.
- Added a regression test for the empty-path/directory fallback.

# Changelog

## v0.2.76 - 2026-04-27

- Fixed the v0.2.75 O VII type-69 record-audit annotation lookup so `examples/28_o7_type69_record_audit.py` can find `o7_type69_transition_sensitivity.csv` when given either the CSV path, the output directory, or a parent directory.
- Added `examples/29_o7_type69_ground_coupling_diagnostic.py` to interpret the high-density record-22490 ground--resonance coupling.  The diagnostic compares baseline, record-scaled, all-type-69-scaled, record-removed, excitation-only, de-excitation-only, and direction-specific variants.
- Added solver support for diagnostic direction-specific collision scaling via `--collision-record-direction-scale RECORD:DIRECTION:SCALE`, propagated through `examples/20_o7_solver_source_fit.py`.  This is explicitly diagnostic and intentionally can break detailed balance to isolate excitation versus de-excitation effects.
- Added regression tests for the record-audit annotation lookup, ground-coupling case builder, and direction-scale parser.

## v0.2.75 - 2026-04-27

- Added `examples/28_o7_type69_record_audit.py`, a targeted O VII high-density diagnostic that audits raw XSTAR type-69 records, with emphasis on records `22490`--`22495` and the record `22490` level `1 -> 7` channel identified by the v0.2.74 transition-sensitivity scan.
- The audit writes raw record metadata, decoded level labels/energies/statistical weights, Kato--Nakazaki `calt69` effective collision strengths, excitation/de-excitation coefficients, density-scaled rates, detailed-balance checks, and temperature-grid behavior.
- The audit can optionally ingest the v0.2.74 `o7_type69_transition_sensitivity.csv` output and annotate each record with its best sensitivity case and reachable scaling factors.
- Added regression tests for the new audit helper functions.

## v0.2.74 - 2026-04-27

Added:
- Added `examples/27_o7_type69_transition_sensitivity.py`, a high-density O VII diagnostic that scans individual XSTAR type-69 collision records or level pairs to identify which transitions drive the `ne=1e12 cm^-3` triplet mismatch.
- Added diagnostic collision record scaling to `xstar_atomic.solver` via `--collision-record-scale RECORD:SCALE`; the existing O VII solver-source-fit example now propagates this option to all unit-source and combined-source solver calls.
- Added `tests/test_o7_type69_transition_sensitivity.py` for the transition-sensitivity helper logic.

Notes:
- This is a diagnostic sensitivity scan only. Record-specific or pair-specific scaling is not a physical correction by itself; it is intended to isolate the type-69 transition(s) that make the high-density XSTAR target reachable.

## v0.2.73 - 2026-04-27

Added:
- Added `examples/26_o7_high_density_rate_sensitivity.py`, a high-density O VII rate-network sensitivity diagnostic for the `ne=1e12 cm^-3` mismatch.
- Added diagnostic collision-rate scaling controls to `xstar_atomic.solver`:
  - `--collision-rate-scale` for global evaluated electron-impact rates,
  - `--collision-data-type-scale DATA_TYPE:SCALE`,
  - `--collision-pair-scale LEVEL1:LEVEL2:SCALE`.
- Propagated the diagnostic collision-rate scaling options through `examples/20_o7_solver_source_fit.py` so empirical source fits can be repeated for scaled rate networks.
- Added `tests/test_o7_high_density_rate_sensitivity.py` for scan-case construction and scale specification checks.

Notes:
- The new rate scales are diagnostic sensitivity factors only. They do not modify the packaged atomic data and should not be interpreted as recommended physical rate corrections.
- The primary goal is to determine whether the high-density O VII mismatch is driven by type-68/69 or level-2-to-3/4/5 collisional coupling, or whether additional physics is required.

## v0.2.72 - 2026-04-27

Added:
- `examples/25_o7_high_density_expanded_source_scan.py` for expanded O VII high-density source-level scans.
- The new diagnostic tests whether larger source bases (`baseline`, `n<=5`, `n<=6`, `n<=8`, and `all_levels`) can reach the density-specific XSTAR target at `ne=1e12 cm^-3`.
- `tests/test_o7_high_density_expanded_source_scan.py` dry-run coverage for CI-friendly source-set planning.

## v0.2.71 - 2026-04-27

Added:
- Added `examples/24_o7_high_density_mismatch_diagnostics.py` to investigate the O VII high-density (`ne=1e12 cm^-3`) density-grid mismatch.
- The new diagnostic reads outputs from `examples/21`/`examples/22` and writes component, source-weight, collision-rate, and JSON summary diagnostics.
- It reports which triplet component drives the mismatch, whether the target is reachable, source-weight collapse metrics, solver diagnostics, and optional type-68/69 level-2 -> level-3/4/5 collision rates when `atdb.fits` is supplied.

Updated:
- Documented the high-density mismatch workflow in README, Markdown, LaTeX, and Sphinx example documentation.

## v0.2.70 - 2026-04-27

Added:
- Added `examples/23_prepare_o7_xstar_density_grid.py`, which prepares real O VII XSTAR density-grid validation runs at `ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3`.
- The helper writes `xstar_runs/o7_ne*/run_xstar.sh` scripts containing the full XSTAR commands, `convert_o7_triplet.sh` scripts for converting `xout_lines1.fits` to O VII triplet CSV files, a density-to-CSV mapping file `xstar_o7_density_grid_references.csv`, a run-plan CSV, and `xstar_runs/README_o7_density_grid.md` containing all commands.
- Added tests for the run-preparation helper and generated command contents.

Notes:
- The helper does not run XSTAR.  It prepares reproducible external XSTAR commands and conversion commands so `examples/22_o7_solver_source_fit_density_xstar_grid.py` can later perform a true density-dependent XSTAR comparison once the XSTAR runs have been completed.

## v0.2.69 - 2026-04-27

Fixed:
- Improved `examples/22_o7_solver_source_fit_density_xstar_grid.py` when the requested `--xstar-grid-summary-csv` file is missing. The wrapper now writes a template density-to-XSTAR-lines mapping CSV and exits with a clear message instead of failing with a raw `FileNotFoundError`.

Added:
- `--write-template-grid-csv` to create a starter density-reference mapping CSV.
- `--allow-placeholder-grid` for low-density-placeholder smoke tests only.
- Packaged template CSVs under `examples/reference_inputs/` and `docs/validation/xstar_inputs/`.

Notes:
- The template intentionally reuses the packaged low-density O VII reference as a placeholder for every row. Replace each `xstar_lines_csv` entry with a converted density-specific XSTAR line CSV before using it for scientific validation.

# CHANGELOG

## v0.2.68 - 2026-04-27

Density-dependent XSTAR references for the O VII density-grid diagnostic.

Added:
- Added `examples/22_o7_solver_source_fit_density_xstar_grid.py`, a density-dependent XSTAR reference front end for the O VII density-grid source-fit diagnostic.
- Added `--xstar-lines-csv-by-density DENSITY:CSV` and `--xstar-grid-summary-csv` support to `examples/21_o7_solver_source_fit_density_grid.py`, allowing each density to be compared against its own XSTAR line CSV instead of reusing a single low-density reference.
- Added reference snapshots for the O VII density-grid diagnostic under `examples/reference_outputs/` and `docs/validation/xstar_outputs/`.
- Added lightweight tests for density-specific XSTAR reference parsing, dry-run command generation, and the new example-22 front end.

Documentation:
- Added a short validated O VII diagnostic commands section to README, Markdown guide, LaTeX guide, and Sphinx examples.
- Added a top-level known-limitation note that empirical O VII fitted source weights are diagnostic and are not physical level-resolved recombination rates.
- Documented the density-dependent XSTAR mapping CSV format and repeated `--xstar-lines-csv-by-density` syntax.

## v0.2.67 - 2026-04-27

Data-path resolver and test isolation fixes.

Fixed:
- `resolve_atdb_path(path, prompt=False)` now treats an explicitly supplied path as strict precedence.  If that path is invalid, it raises a clear error instead of silently falling back to `XSTAR_ATDB_FITS` or a saved datapath.
- Updated data-path helper tests to use a minimal FITS-like file that passes the lightweight resolver validation added for zero-byte/truncated-file protection.
- Isolated data-path helper tests from the `XSTAR_ATDB_FITS` environment variable so full-suite runs with a real ATDB configured do not mask explicit-path behavior.

Notes:
- This is a bug-fix release for the v0.2.66 test failures observed when running `XSTAR_ATDB_FITS=../xstar/data/atdb.fits PYTHONPATH=src pytest -q`.

## v0.2.66 - 2026-04-27

Density-grid feasibility flags and clearer XSTAR-target labeling.

Changed:
- Updated `examples/21_o7_solver_source_fit_density_grid.py` so the reused XSTAR target is explicitly labeled as a low-density XSTAR O VII reference reused at all densities.
- Added fit-feasibility columns: `fit_success_vs_xstar` and `target_reachable`.
- Added ratio columns: `refitted_R_over_xstar`, `refitted_G_over_xstar`, `fixed_R_over_refitted`, and `fixed_G_over_refitted`.
- Added warning generation when the source-fit objective is large or the refitted combined R/G ratios remain outside tolerance, with explicit high-density wording for the type-68 coupling regime.
- The density-grid summary JSON now records the XSTAR target label, feasibility tolerances, warnings, and per-density feasibility flags.
- Added tests for the new density-grid feasibility logic and warning behavior without requiring full `atdb.fits`.

Notes:
- The current density-grid example still uses one XSTAR reference at all densities.  A later extension should allow density-dependent XSTAR references, for example `--xstar-lines-csv-by-density` or `--xstar-grid-summary-csv`.

## v0.2.65 - 2026-04-27

Density-grid O VII solver-source-fit diagnostic.

Added:
- Added `examples/21_o7_solver_source_fit_density_grid.py`, which runs the validated O VII full-solver source-fit workflow over a density grid.  The default grid is `ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3` at `T = 1e6 K`.
- The density-grid diagnostic reports both fixed-weight validation, using the reference `ne=1 cm^-3` fitted weights at all densities, and separately refitted weights at each density.
- The output CSV `o7_solver_source_fit_density_grid.csv` includes XSTAR R/G, fixed-weight R/G, refitted linear-response R/G, refitted combined simultaneous-solver R/G, matrix rank, condition number, residuals, negative-population diagnostics, and weight-change metrics relative to the reference density.
- The output JSON `o7_solver_source_fit_density_grid_summary.json` records per-density summary paths, fixed-weight validation products, solver diagnostics, and the largest source-weight changes.
- Added lightweight tests in `tests/test_o7_solver_source_fit_density_grid.py` for the new density-grid example, including dry-run command construction and reference-density ordering without requiring the full `atdb.fits`.

Notes:
- This diagnostic is intended to show whether the empirical fitted O VII source distribution is stable or density-dependent after type-68 metastable/intercombination coupling is active.
- The fitted weights remain empirical solver-response weights, not physical level-resolved recombination rates.

## v0.2.64 - 2026-04-26

Regression/reference checks for the validated O VII solver-source-fit workflow.

Added:
- Added compact saved reference output `examples/reference_outputs/o7_solver_source_fit_summary_reference.json` for the validated O VII full-solver source-fit diagnostic.  This reference stores the XSTAR R/G target, fitted linear-response R/G, combined simultaneous-solver R/G, SVD solver diagnostics, null-rate pruning diagnostics, and negative-population handling without requiring the full 830 MB `atdb.fits` in CI.
- Added `tests/test_o7_solver_source_fit_reference.py` with CI-friendly tests that verify:
  - fitted linear-response R/G matches the saved XSTAR reference,
  - combined-source validation agrees with the fitted linear-response prediction to tight tolerance,
  - the validated diagnostic path uses `linear_solver=svd`, `rank_deficient_action=svd`, `negative_population_action=keep`, and null-rate pruning,
  - the raw-response simplex fitting helper remains numerically reproducible.
- Added a warning in `examples/13_o7_recombination_cascade_workflow.py` when `selected-fit-weights` or `o7-xstar-fit` is used without `--solver-source-total-rate`.  The warning tells users to pass `--solver-source-total-rate 1.0` when consuming weights produced by `examples/20_o7_solver_source_fit.py` with the default `--source-rate=1.0`.
- Workflow summaries from `examples/13_o7_recombination_cascade_workflow.py` now include a `warnings` list so this source-amplitude warning is preserved in machine-readable outputs.

Notes:
- These tests are reference/regression tests for the validated diagnostic output, not full physical ATDB tests.  Full real-ATDB validation is still done by running examples 20 and 13 locally with the real XSTAR `atdb.fits`.
- The empirical fitted-source mode remains diagnostic and amplitude-dependent, not a physical level-resolved recombination model.

## v0.2.63 - 2026-04-25

Documentation update for the validated O VII full-solver source-fit path.

Changed:
- Updated README and Markdown user guide with the validated O VII solver settings: `--linear-solver svd`, `--rank-deficient-action svd`, `--negative-population-action keep`, and `--prune-null-rate-levels`.
- Documented that the combined-source validation in `examples/20_o7_solver_source_fit.py` matches the saved XSTAR O VII triplet ratios with `R/R_XSTAR = 1.00000146` and `G/G_XSTAR = 0.99999836` in the v0.2.62 validation run.
- Added the same validated command sequence to the recombination/cascade workflow documentation, including `--solver-source-total-rate 1.0` and the SVD/rank-aware solver controls.
- Updated the LaTeX user guide with a dedicated Stage-6 full-solver source-fit section and a compact diagnostic summary table.
- Updated Sphinx examples documentation with the same validated workflow and diagnostic caveats.

Notes:
- The fitted source weights remain empirical/diagnostic, not true level-resolved recombination rates.
- Direct dense or sparse solvers are not recommended for this O VII diagnostic unless residuals and combined-source validation are explicitly checked, because the matrix is rank-deficient and highly ill-conditioned.

## v0.2.62 - 2026-04-24

Automatic combined-source validation for the O VII solver-response source-fit diagnostic.

Added:
- `examples/20_o7_solver_source_fit.py` now runs one simultaneous combined-source validation solve after fitting the nonnegative source weights, unless `--skip-combined-validation` is supplied.
- The validation writes `combined_source_validation/o7_combined_fitted_sources.csv`, `o7_combined_solver_lines.csv`, `o7_combined_solver_triplet.csv`, and `o7_combined_solver_summary.json`.
- The top-level `o7_solver_source_fit_summary.json` now reports three R/G comparisons in one place: XSTAR reference, fitted linear-response prediction, and combined simultaneous-solver validation.
- Combined validation diagnostics include matrix rank/size, condition number, linear residuals, source/sink summary, null-rate pruning diagnostics, and raw negative-population counts/minimum/sum diagnostics.
- New options: `--skip-combined-validation` and `--combined-source-total-rate` for controlling the simultaneous validation solve.

Purpose:
- This prevents confusion between an exact response-matrix fit and the actual behavior when the fitted sources are injected together into the full statistical-equilibrium solver.

## v0.2.61 - 2026-04-23

Numerical solver hardening for Stage-6 O VII diagnostics.

Added:
- Rank-aware matrix handling in `xstar_atomic.solver` via `--rank-deficient-action warn|lstsq|svd|reject`.
- Explicit least-squares/SVD solver choices through `--linear-solver lstsq|svd` in addition to `dense|sparse|auto`.
- Per-solve null-rate pruning with `--prune-null-rate-levels` and `--null-rate-floor`, preserving ground, output, and source/sink levels.
- Negative-population controls: `--negative-population-action clip|zero-small|keep|reject` and `--negative-population-tol`.
- Residual diagnostics and optional rejection: `--residual-l2-max`, `--residual-linf-max`, and `--reject-large-residual`.
- Raw population diagnostics before any negative-population handling, including counts and absolute negative-population sum.
- `examples/20_o7_solver_source_fit.py` now defaults to SVD/rank-aware diagnostic solving, keeps raw negative populations by default, and passes null-rate pruning to unit-source solves.
- `examples/13_o7_recombination_cascade_workflow.py` now exposes the same solver-matrix treatment options and records them in the workflow summary.

Changed:
- Rank-deficient matrices are no longer treated as ordinary direct-solve cases by default; the default action is least-squares in the solver CLI and SVD in the O VII diagnostic examples.
- Negative populations are no longer clipped silently: the chosen action and raw negative-population diagnostics are always written to solver summaries.

Notes:
- The default library/CLI behavior remains compatible for general use (`clip` remains the solver default), while the O VII empirical diagnostic examples use `keep` to avoid introducing nonlinear clipping into response-matrix fits.

## v0.2.60 - 2026-04-22

- Corrected `examples/20_o7_solver_source_fit.py` so the empirical solver-response weights are fitted against the **raw full-solver triplet response amplitudes**, with the combined triplet vector normalized only for comparison to the XSTAR R/G target.
- This fixes the v0.2.54--v0.2.59 diagnostic inconsistency where the source-fit script could match XSTAR using per-level normalized response fractions, but the same weights did not reproduce the target when injected simultaneously into `examples/13_o7_recombination_cascade_workflow.py`.
- Added raw-response columns to `o7_source_fit_weights.csv` / `o7_solver_source_fit_weights.csv` so each fitted level shows its raw forbidden, intercombination, and resonance response per unit source.
- The fitted weights remain empirical/diagnostic and amplitude-dependent; continue using `--solver-source-total-rate 1.0` in the cascade workflow when applying weights generated with the default `--source-rate 1.0`.

## v0.2.59 - 2026-04-21

- Captures SciPy `MatrixRankWarning` during sparse statistical-equilibrium solves and falls back to the existing least-squares solver instead of printing repeated warning spam.
- This is especially useful for the O VII solver-response source-fit diagnostic, where some unit-source response matrices are rank-deficient because selected source levels do not independently constrain a unique sparse solution.
- The warning/fallback remains recorded in the solver summary via `solver_warning`; fitted source-response diagnostics should still be judged from the output summary ratios.

## v0.2.58 - 2026-04-20

- Added source-amplitude controls to `examples/13_o7_recombination_cascade_workflow.py`:
  - `--solver-source-scale` multiplies the source/sink CSV passed to the solver.
  - `--solver-source-total-rate` rescales the solver source CSV so the first T/ne block has a requested total source rate.
- This fixes the diagnostic mismatch where solver-response fitted weights from `examples/20_o7_solver_source_fit.py` were derived with unit source rate `1.0 s^-1`, but the cascade workflow applied them at the physical RR source scale (`~1.345e-12 s^-1` at ne=1), causing baseline collisional excitation to dominate.
- `examples/20_o7_solver_source_fit.py` now records `source_rate_s^-1`, `source_rate_note`, and `fit_source_rate_s^-1` in its outputs so the required workflow source amplitude is explicit.
- Recommended fitted-source workflow now uses `--solver-source-total-rate 1.0` when consuming default solver-response weights.

## v0.2.57 - 2026-04-19

Safety fix:
- Hardened NPZ hierarchy index-cache writing so it never uses or replaces the input `atdb.fits` path.
- The cache writer now rejects cache paths that resolve to the FITS file, uses a unique temporary filename in the cache directory, and verifies that the FITS file signature is unchanged before and after cache replacement.
- Added `--index-cache-path` to `examples/20_o7_solver_source_fit.py` so repeated unit-source solver runs can use an explicit cache file away from the XSTAR data file.

Recommended safe usage:

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit \
  --print-summary
```

## v0.2.56 - 2026-04-18

Fixed:
- Made explicit `--source-fit-weights-csv` paths strict, except for the documented legacy cascade-fit path `o7_cascade_source_fit/o7_source_fit_weights.csv`. This prevents a missing solver-response fit file such as `o7_solver_source_fit/o7_source_fit_weights.csv` from silently falling back to the packaged older cascade-fit reference by basename.

Added:
- Recombination summaries now record `source_fit_weights_csv_requested`, `source_fit_weights_csv_resolved`, `source_fit_weight_column`, and `n_source_fit_weights` so fitted-source workflow outputs show exactly which weight file was used.

Notes:
- The uploaded v0.2.55 solver-fit workflow used `solver_source_csv_mode=initial`, but its initial source weights matched the older packaged cascade-fit weights. This happened because the requested solver-response weights CSV was not found relative to the run directory and the basename fallback selected the packaged `o7_source_fit_weights.csv`. v0.2.56 fails fast instead.

## v0.2.55 - 2026-04-17

Fixed:
- Added lightweight `atdb.fits` path validation in the data resolver so empty, truncated, or wrong relative FITS paths fail with a clear message before Astropy raises a low-level `OSError: Empty or corrupt FITS file`.
- `python -m xstar_atomic.data --set-path ...` now rejects invalid `atdb.fits` candidates and suggests setting `XSTAR_ATDB_FITS` or the persistent datapath to the real local XSTAR atomic database.

Notes:
- This version does not change the O VII solver-response source-fit physics. It only improves diagnostics for the path problem seen when rerunning the v0.2.54 workflow with an empty/corrupt `../xstar/data/atdb.fits`.

## v0.2.54 - 2026-04-16

### Added
- Added `examples/20_o7_solver_source_fit.py`, a stricter O VII empirical diagnostic that fits source weights against the full `xstar_atomic.solver` unit-source response matrix rather than the simpler radiative cascade yield matrix.
- The new solver-response fit writes `o7_solver_response_matrix.csv`, `o7_solver_source_fit_weights.csv`, a compatibility alias `o7_source_fit_weights.csv`, and `o7_solver_source_fit_summary.json`.

### Changed
- Documented that the earlier cascade-yield source-fit weights are not expected to reproduce XSTAR R/G when injected into the full statistical-equilibrium solver, because the solver response includes radiative rates, branching, collisional coupling, and normalization effects beyond the cascade-yield matrix.

## v0.2.53 - 2026-04-15

Fixed:
  - examples/13_o7_recombination_cascade_workflow.py now feeds the initial fitted source CSV to the level-population solver for selected-fit-weights and o7-xstar-fit modes by default.
  - Added --solver-source-csv-mode auto|initial|cascade to make this behavior explicit and reproducible.
  - This avoids applying the radiative cascade twice: once in recombination.py and again inside the solver radiative network.

## v0.2.52 - 2026-04-14

Fixed:
- Resolved a path bug in `selected-fit-weights` workflows: missing relative weight CSV paths such as `o7_cascade_source_fit/o7_source_fit_weights.csv` are now resolved against packaged reference locations (`xstar_test_run/`, `examples/reference_outputs/`, and `docs/validation/xstar_outputs/`) when the basename exists there.
- Updated the explicit `selected-fit-weights` documentation examples to use the packaged reference file `xstar_test_run/o7_source_fit_weights.csv`.

## v0.2.51 - 2026-04-14

- Added diagnostic source mode `selected-fit-weights`, which reads fitted level-source weights from `--source-fit-weights-csv`.
- Added convenience source mode `o7-xstar-fit`, which uses `xstar_test_run/o7_source_fit_weights.csv` when no explicit weight CSV is provided.
- Added O VII source-fit reference products to `xstar_test_run/`, `examples/reference_outputs/`, and `docs/validation/xstar_outputs/`.
- Updated the O VII recombination/cascade workflow example to pass source-fit weight CSV options through to `xstar_atomic.recombination`.
- These modes are empirical/diagnostic only; they are not a replacement for true level-resolved recombination rates.

## v0.2.50 - 2026-04-13

- Added `examples/19_o7_cascade_source_fit.py`, a Stage-6 diagnostic for level-resolved O VII cascade-source construction from radiative yield matrices.
- The example builds `Y(source_level -> forbidden, intercombination, resonance)`, writes `o7_cascade_yield_matrix.csv`, fits nonnegative source weights against the saved XSTAR O VII `R=f/i` and `G=(f+i)/r` ratios, and writes `o7_source_fit_weights.csv` plus `o7_source_fit_summary.json`.
- Added helper tests for the nonnegative simplex projection and source-fit optimizer used by the diagnostic.

## v0.2.49 - 2026-04-12

- Added `examples/18_o7_type68_2d_cascade_tuning_scan.py`, a broader Stage-6 O VII type-68-aware tuning scan.
- The new scan varies both forbidden-to-intercombination redistribution and resonance-target suppression using maps of the form `2:(1-d),3:(1+d/3),4:(1+d/3),5:(1+d/3),7:r`.
- The scan writes compact, ranked, all-density CSV tables plus a JSON summary, so the best compromise against the XSTAR O VII `R=f/i` and `G=(f+i)/r` reference can be identified.
- Kept the equal-target `selected-cascade-yield` map as the documented Stage-6 baseline.

## v0.2.48 - 2026-04-11

### Added
- Added type-68-aware O VII cascade tuning presets that preserve equal triplet target weights while progressively downweighting the resonance target level 7: `o7-triplet-type68-r095`, `r090`, `r085`, `r080`, `r075`, `r070`, `r060`, and `r050`.
- Added `examples/17_o7_type68_cascade_tuning_scan.py` to run the equal baseline plus the type-68-aware resonance-weight grid, writing compact and all-density CSV/JSON summaries.

### Changed
- Documentation now distinguishes the pre-type-68 f2i/fdown scans from the type-68-aware resonance-weight scan needed after He-like collision types 67/68/69 are enabled.

## v0.2.47 - 2026-04-10

- Added He-like collisional-excitation decoders/evaluators for XSTAR data types 67, 68, and 69.
  - Type 67 follows `calt67`: `gamma = a + b log10(T) + c log10(T)^2`.
  - Type 68 follows `calt68`: `gamma = a + b log10(T/Z^3) + c log10(T/Z^3)^2`.
  - Type 69 follows `calt69`: Kato--Nakazaki He-like collision-strength fit.
- Extended `COLLISION_DATA_TYPES` to include 67, 68, and 69.
- Updated the O VII metastable/intercombination coupling diagnostic to write `o7_metastable_coupling_collision_inventory.csv`, which inventories all decoded/evaluated collision records involving the selected source/target levels.
- Added unit tests for the type-67/68/69 helper evaluators.

## v0.2.46 - 2026-04-09

Stage-6 diagnostic update.

Added:

- `examples/16_o7_metastable_coupling_diagnostics.py`, a focused O VII diagnostic for level 2 -> levels 3, 4, and 5.
- The diagnostic compares collisional transfer rates `C_2_to_j = n_e q_2j` with decoded radiative rates as a function of electron density.
- Outputs `o7_metastable_coupling_rates.csv` and `o7_metastable_coupling_summary.json`.

Notes:

- The equal-target `selected-cascade-yield` map remains the documented Stage-6 baseline.
- The new diagnostic is intended to determine whether the remaining high O VII `R=f/i` ratio is caused by under-coupled metastable/intercombination transfer or by source/cascade feeding.

## v0.2.45 - 2026-04-08

Stage-6 O VII cascade tuning update.

### Added
- Added forbidden-to-intercombination shift presets that preserve the resonance target and approximately preserve the total triplet-target weight:
  - `o7-triplet-f2i010-rkeep` -> `2:0.90,3:1.0333333333,4:1.0333333333,5:1.0333333333,7:1.0`
  - `o7-triplet-f2i015-rkeep` -> `2:0.85,3:1.05,4:1.05,5:1.05,7:1.0`
  - `o7-triplet-f2i025-rkeep` -> `2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0`
  - `o7-triplet-f2i050-rkeep` -> `2:0.50,3:1.1666666667,4:1.1666666667,5:1.1666666667,7:1.0`

### Changed
- Kept the equal-target map `2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` as the documented Stage-6 baseline.
- Updated `examples/15_o7_cascade_tuning_scan.py` so the default tuning scan now includes the new forbidden-to-intercombination shift presets before the older simple `fdown` comparison cases.
- Updated `o7-triplet-xstar-tuned` as a backward-compatible alias to the preferred `f2i025` shift experiment.
- Updated README, Markdown, LaTeX, and Sphinx documentation to describe the new Stage-6 tuning strategy: preserve `G=(f+i)/r` by keeping the total triplet/resonance balance close to the equal-target case while shifting source weight from forbidden to intercombination levels.

## v0.2.44 - 2026-04-07

### Added
- Added Stage-6 O VII cascade tuning presets that downweight the forbidden target while preserving the resonance target: `o7-triplet-fdown090-rkeep`, `o7-triplet-fdown085-rkeep`, and `o7-triplet-fdown075-rkeep`.
- Added `examples/15_o7_cascade_tuning_scan.py`, which runs the equal-target baseline plus forbidden-downweighted presets and writes CSV/JSON summaries of `R=f/i` and `G=(f+i)/r` relative to the saved XSTAR O VII reference.

### Changed
- Kept the equal-target map `2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` as the recommended Stage-6 baseline.
- Updated README, Markdown, LaTeX, and Sphinx documentation to describe the Stage-6 tuning scan workflow.

## v0.2.43 - 2026-04-06

Completed Stage-5 heavy-ion XSTAR wavelength validation.

- Added validated Mg XI, Mg XII, Si XIII, Si XIV, Fe XXV, and Fe XXVI XSTAR `xout_lines1.fits` artifacts under `xstar_test_run/`.
- Added converted selected-line CSV products for Mg/Si/Fe validation under `xstar_test_run/`.
- Added Mg/Si/Fe wavelength comparison CSV/JSON files under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Added tests checking the Mg/Si/Fe validation artifacts and wavelength matches.
- Updated README and Sphinx/Markdown comparison docs to mark Mg/Si/Fe Stage-5 validation as completed rather than pending.

## v0.2.42 - 2026-04-06

Stage-5 heavy-ion validation planning update.

- Added reproducible direct-XSTAR run recipes to `xstar_test_run/README.md` for Mg XI, Mg XII, Si XIII, Si XIV, Fe XXV, and Fe XXVI.
- Added suggested first-pass wavelength windows and `xstar_atomic.xstar_outputs` FITS-to-CSV commands for Mg/Si/Fe validation products.
- Added wavelength-comparison command templates for the corresponding `examples/08_compare_xstar_outputs.py` runs.
- Updated README and XSTAR comparison documentation to mark Mg/Si/Fe as the pending Stage-5 completion targets after the validated O/Ne workflow.

## v0.2.41 - 2026-04-05

- Fixed Sphinx ``user_guide.rst`` heading underline length for ``Downloading and configuring atdb.fits`` so ``make html`` builds without the title-underline warning.

## v0.2.40 - 2026-04-05

Fixed:

- Corrected the Sphinx user-guide heading underline for ``Downloading and configuring atdb.fits`` so ``make html`` builds without the title-underline warning.
- Kept the v0.2.39 documentation updates for ``download_data()``, data-path resolution, NPZ cache performance, and Stage-6 cascade workflow notes.

## v0.2.39 - 2026-04-05

Documentation and Stage-6 result update.

- Refreshed Markdown, LaTeX, and Sphinx documentation for the current data-management API: `download_data()`, `resolve_atdb_path()`, `find_atdb_file()`, `get_data_path()`, and `set_data_path()`.
- Documented path-resolution precedence: explicit path, `XSTAR_ATDB_FITS`, persistent `datapath`, project/package `data/atdb.fits`, then interactive download/configuration.
- Documented the single-line ASCII download progress bar and the source-tree default `data/` and `datapath` locations.
- Updated solver/cache documentation to recommend the array-backed NPZ cache path validated in v0.2.27/v0.2.28.
- Added Stage-6 result guidance: equal-target cascade-yield remains the recommended baseline; the `o7-triplet-fdown-rkeep` preset decreases `R=f/i` but also lowers `G=(f+i)/r`, so it is experimental.
- Fixed LaTeX listing styles using `ctpython` and `ctterminal`; Python listings now have syntax highlighting and terminal listings use a separate style.
- Normalized code listings so ion names appear as `O VIII`, not with visible-space markers.

## v0.2.38 - 2026-04-04

- Fixed `examples/13_o7_recombination_cascade_workflow.py` so the recommended equal O VII target map is only passed when no non-`none` `--cascade-target-preset` is selected.
- This prevents the default `--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0` from overriding experimental presets such as `o7-triplet-fdown-rkeep`.
- The recommended Stage-6 baseline remains the equal-target map. The `o7-triplet-fdown-rkeep` preset remains an experimental forbidden-downweighted, resonance-preserved map.

## v0.2.37 - 2026-04-03

Stage-6 O VII cascade-source tuning update.

Changed:
- Keep the documented/recommended ``selected-cascade-yield`` target map as equal triplet targets: ``2:1.0,3:1.0,4:1.0,5:1.0,7:1.0``.
- Add a new forbidden-downweighted, resonance-preserved experimental preset: ``--cascade-target-preset o7-triplet-fdown-rkeep`` -> ``2:0.5,3:1.0,4:1.0,5:1.0,7:1.0``.
- Update ``o7-triplet-xstar-tuned`` as a backward-compatible alias to the new resonance-preserved map, replacing the earlier resonance-downweighted map.
- Update the Stage-6 workflow example and docs to avoid recommending the resonance-downweighted preset, which overestimated G=(f+i)/r.

## v0.2.36 - 2026-04-02

Fixed:
- Data-path helper round-trip test now removes ``XSTAR_ATDB_FITS`` during the isolated datapath test. This preserves the intended runtime precedence: explicit path, ``XSTAR_ATDB_FITS``, saved ``datapath``, project/package ``data/``, then interactive download/configuration.

Added:
- ``--cascade-target-preset o7-triplet-xstar-tuned`` for Stage-6 O VII triplet cascade-source experiments.
- The preset expands to ``2:0.6,3:1.0,4:1.0,5:1.0,7:0.4``.
- Manual ``--cascade-target-levels`` remains available and overrides the preset.

## v0.2.35 - 2026-04-01

Stage 6 recombination/cascade improvements:
- Added `selected-cascade-yield` recombination source allocation mode.
- Added `--cascade-target-levels` and `--cascade-weight-floor` to `xstar_atomic.recombination`.
- Updated the O VII recombination/cascade workflow example to use cascade-yield source weighting by default.
- Added unit coverage for cascade-yield source allocation helpers.

## v0.2.34 - 2026-03-31

- Added validated Ne IX / Ne X Stage-5 XSTAR comparison artifacts.
- Added `xstar_test_run/ne_xi25/xout_lines1.fits` and `xstar_test_run/ne_xi35/xout_lines1.fits`.
- Added converted CSV line lists for Ne IX triplet/near-triplet and Ne X Ly-alpha.
- Added saved comparison CSV/JSON outputs to `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Updated XSTAR comparison documentation from planned neon runs to completed validation examples.

## v0.2.33 - 2026-03-30

Documentation/examples:
- Added dedicated Stage-5 Ne IX and Ne X direct-XSTAR validation run commands to `xstar_test_run/README.md`.
- Added FITS-to-CSV and `examples/08_compare_xstar_outputs.py` commands for Ne IX He-like triplet/near-triplet and Ne X Ly-alpha wavelength comparisons.
- Updated XSTAR comparison documentation and Sphinx comparison page to list the planned Ne IX/Ne X validation products.

## v0.2.32 - 2026-03-29

Fixed:
  - Replaced multi-line download progress messages with a single in-place ASCII progress bar.
  - Download progress now displays as: `xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)`.

## v0.2.31 - 2026-03-28

Fixed:
- Store the source-tree ``datapath`` file at the project root (for example ``xstar_atomic/datapath``) rather than in ``src/xstar_atomic/``.
- Removed the packaged ``src/xstar_atomic/datapath`` data file from package-data/MANIFEST entries.
- Kept the project-level ``data/`` directory as the default ``atdb.fits`` download destination when running from ``PYTHONPATH=src``.

## v0.2.30 - 2026-03-27

Fixed:
- Changed the default interactive ``download_data()`` destination for source-tree use from ``src/xstar_atomic/data`` to the project-level ``data`` directory.
- Changed the source-tree ``datapath`` file location from ``src/xstar_atomic/datapath`` to the project-level ``datapath`` file, while retaining installed-package fallback behavior.

## v0.2.28 - 2026-03-25

Documentation/examples:
- Documented the validated array-backed NPZ cache performance from v0.2.27: O VIII sparse solver profile dropped from about 5.31 s uncached to about 0.53 s on an NPZ array-backed cache hit.
- Made the array-backed NPZ cache the recommended default for repeated solver, export, high-level API, and profiler workflows.
- Updated README, Markdown user guide, LaTeX user guide, and Sphinx user/examples pages with `--index-cache --index-cache-format npz` examples.
- Updated `examples/12_profile_solver_steps.py` documentation to use the recommended NPZ cache path.

## v0.2.27 - 2026-03-24

Fixed:
- Restored the public array-backed `ATDB.select_records(z=..., ion_stage=..., data_type=..., rate_type=...)` API by renaming the legacy materialized-list filter helper to `filter_records`.
- Fixed `examples/12_profile_solver_steps.py --index-cache --index-cache-format npz`, which failed in v0.2.26 because the legacy helper shadowed the new fast-selection method.

## v0.2.26 - 2026-03-23

Added:
- Added `ATDBIndexArrays`, an array-backed hierarchy index for fast targeted selection.
- Added `ATDB.build_index_arrays(...)` and `ATDB.select_records(...)`.
- NPZ cache hits can now filter numeric arrays and convert only selected rows to `IndexedRecord` objects.
- Updated solver, profiler, and high-level API paths to use array-backed selection for NPZ index caches.
- Added tests for array-backed selection/reconstruction.

Changed:
- `--index-cache-format npz` now avoids reconstructing all 1.2 million records in targeted solver/profiler/API paths.

## v0.2.25 - 2026-03-22

Fixed:
- Reworked the NPZ index cache into a slimmer numeric v2 layout.
- Avoided storing large repeated Unicode arrays for each ATDB record in the NPZ cache.
- Old v0.2.24 NPZ caches are now treated as stale and rebuilt automatically.

Changed:
- The compact cache still returns normal IndexedRecord objects for decoder compatibility, but reconstructs repeated labels from numeric fields and the small element/ion tables.

## v0.2.24 - 2026-03-21

Added:
- Added compact NumPy/NPZ hierarchy index cache support for `ATDB.build_index()`.
- `--index-cache` now defaults to the NPZ cache path `atdb.fits.xstar_atomic_index.npz`.
- Added `--index-cache-format npz|pickle` to hierarchy, solver, export, and solver-step profiler CLIs.
- Preserved legacy pickle cache support with `--index-cache-format pickle`.

Changed:
- `XSTARAtomic(..., index_cache=True)` now uses the NPZ cache by default.
- Cache status strings now distinguish `npz_hit`, `npz_written`, `pickle_hit`, and related states.

## v0.2.23 - 2026-03-20

Added:
- Optional on-disk ATDB hierarchy index caching via ``ATDB.build_index(use_cache=True)``.
- ``--index-cache`` and ``--rebuild-index-cache`` options for the hierarchy, solver, export, and solver-step profiling workflows.
- Cache metadata validation against the source ``atdb.fits`` file size, modification time, array lengths, and cache format version.
- Real-ATDB cache round-trip test for cache creation and cache hits.

Changed:
- Solver/export/profile summaries now report ``index_cache_status`` and ``index_cache_path`` when caching is used.

## v0.2.22 - 2026-03-19

### Fixed

- Fixed `examples/12_profile_solver_steps.py` by adding the missing
  `auto_recombination_cascade=False` default to the solver argument namespace used
  by the profiling workflow.

### Documentation

- Documented that an optional C++ backend can be implemented as a shared-object
  library while preserving the Python/SciPy reference backend.
- Added notes on the Stage-6 O VII recombination/cascade workflow: total O VIII
  -> O VII recombination is redistributed over selected O VII levels, radiative
  branching cascade sources are written to CSV, the sparse solver reads those
  sources, and prototype R=f/i and G=(f+i)/r diagnostics are compared with XSTAR
  triplet output ratios.

## v0.2.21 - 2026-03-18

### Added
- Added `examples/12_profile_solver_steps.py` to profile individual solver stages: ATDB open/read, index building, level/line/collision extraction, collision evaluation, matrix assembly, solve, and output writing.
- Added `examples/13_o7_recombination_cascade_workflow.py`, a prototype Stage-6 O VII workflow that builds recombination source CSVs, performs approximate radiative cascade redistribution, feeds the cascade source into the sparse solver, and compares O VII triplet diagnostics with an optional XSTAR line-output CSV.

### Notes
- Documented that an optional C++ backend can be implemented as a shared-object (`.so`) library loaded from Python, with the pure-Python/SciPy implementation retained as the reference/fallback path.
- The O VII cascade workflow remains a prototype: current oxygen RR/DR records are total recombination rates, not true level-resolved recombination-cascade records.

## v0.2.20 - 2026-03-17

### Added
- Added `examples/11_solver_timing.py` to benchmark end-to-end level-population solver execution times.
- The timing example compares O VIII dense and sparse solver modes and can optionally include the heavier O VII triplet sparse stress test.
- Timing CSV rows include elapsed wall time, solver used, sparse status, matrix size, nonzero count, density, condition number, and residual diagnostics.

### Documentation
- Updated the Markdown, LaTeX, and Sphinx user guides with solver timing commands and notes on when a C++ backend could improve performance.

## v0.2.19 - 2026-03-16

### Solver
- Improved Stage-3 level-population solver diagnostics for sparse and dense solves, including matrix nonzero counts, matrix density, singular-value/rank diagnostics, diagonal and row-sum ranges, residual norms, and explicit sparse-use flags.
- Added optional connectivity pruning with `--prune-unconnected-levels`, preserving ground, output, and explicit source/sink levels.
- Added source/sink vector summaries to solver JSON output, including nonzero level terms and source/sink totals for recombination/cascade source-file tests.
- Added O VII triplet diagnostic support with `--triplet-diagnostics` and `--out-triplet-csv`, reporting prototype `R=f/i` and `G=(f+i)/r` ratios when O VII triplet lines are selected.

### Documentation and examples
- Updated the user guide and examples for sparse solver runs, connectivity pruning, source/sink diagnostics, and O VII triplet diagnostics.
- Added `examples/10_o7_triplet_sparse_solver.py` as the Stage-3 solver stress-test example.

### Tests
- Added unit tests for solver diagnostics, pruning, source/sink summaries, and O VII triplet R/G helper calculations.

## v0.2.18 - 2026-03-15

### Documentation
- Updated the Markdown, LaTeX, and Sphinx user-guide material for the validated Stage-4 band-emissivity export workflow.
- Documented `--bands-kev`, `*_band_emissivity.csv`, and HDF5 `/band_emissivity` products.
- Recorded the v0.2.17 Stage-4 real-ATDB validation result: 34 passing tests, 12 band-emissivity rows per ion for four bands and three temperatures, nonblank `ion`, and `methods_used="none"` for zero-line bands.

### Examples
- Added `examples/09_export_band_emissivity.py` for CSV/HDF5 export of line-based X-ray band emissivity products.

## v0.2.17 - 2026-03-14

### Fixed
- Filled the `ion` field for all band-emissivity rows, including zero-line bands.
- Set `methods_used="none"` for zero-line band-emissivity rows.

### Tests
- Added unit and real-ATDB export tests that check band-emissivity rows do not contain blank ion names or blank method fields.

## v0.2.15 - 2026-03-13

### Added
- Added HDF5 export support to `xstar_atomic.export` via `--formats hdf5` or `--formats csv,hdf5`.
- Added a general CLI alias `xstar-atomic-export` while keeping `xstar-atomic-export-superwind` for backward compatibility.
- Added optional SciPy sparse-matrix support to the level-population solver via `--linear-solver sparse` or `--linear-solver auto`.
- Added tests for HDF5 export helpers and sparse-solver fallback/consistency.

### Changed
- Generalized export documentation and manifests for plasma post-processing workflows beyond superwinds, including AGN outflows.
- The export manifest is now written as `atomic_export_manifest.json` and also as the legacy `superwind_export_manifest.json`.


## v0.2.14 - 2026-03-12

### Added
- Added `xstar_test_run/` with direct-XSTAR `xout_lines1.fits` outputs, converted CSV line tables, and a README documenting the exact XSTAR commands and FITS-to-CSV conversion workflow.
- Added tests for packaged XSTAR test-run artifacts and conversion consistency.

### Documentation
- Updated XSTAR comparison documentation to reference `xstar_test_run/` and the included O VIII/O VII validation CSV files.

## v0.2.13 - 2026-03-11

### Added
- Added `xstar_test_run/` with direct-XSTAR `xout_lines1.fits` outputs, converted CSV line tables, and a README documenting the exact XSTAR commands and FITS-to-CSV conversion workflow.
- Added tests for packaged XSTAR test-run artifacts and conversion consistency.

### Documentation
- Updated XSTAR comparison documentation to reference `xstar_test_run/` and the included O VIII/O VII validation CSV files.

## v0.2.12 - 2026-03-10

### Added
- Added saved XSTAR-vs-`xstar-atomic` comparison outputs for O VIII Ly-alpha and the O VII triplet under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Added `docs/xstar_comparison_examples.md` documenting the XSTAR-output comparison workflow and validation results.
- Added Sphinx page `xstar_comparisons.rst` and linked it from the Sphinx index.

### Documentation
- Documented that O VIII Ly-alpha wavelength agreement is at the ~1e-5 Angstrom level.
- Documented that O VII triplet wavelength agreement is at the ~1e-7 to 8e-7 Angstrom level.
- Clarified that XSTAR model `emit_*` columns are not directly equivalent to local `xstar-atomic` emissivity coefficients without model-dependent normalization.

## v0.2.11 - 2026-03-09

Added:
- Extended ``examples/08_compare_xstar_outputs.py`` with explicit ``--mode`` choices: ``wavelength``, ``emissivity``, and ``both``.
- Added ``--out-csv`` and ``--out-json`` outputs for XSTAR-vs-xstar-atomic comparison tables.
- Added clearer warnings/notes that XSTAR model ``emit_*`` columns are not directly equivalent to local atomic emissivity coefficients.

## v0.2.10 - 2026-03-08

Fixed:
- Added `--wavelength-column` to `examples/08_compare_xstar_outputs.py`.
- The comparison example now auto-detects `wavelength_A` or `wavelength` columns in XSTAR-output CSV files.

## v0.2.9 - 2026-03-07

### Added
- Added `xstar_atomic.xstar_outputs` for reading XSTAR `xout_lines*.fits` files.
- Added CLI entry point `xstar-atomic-xstar-outputs` and module execution with `python -m xstar_atomic.xstar_outputs`.
- Supports CSV export, JSON summaries, and filtering by ion, wavelength, and emission columns.

## v0.2.8 - 2026-03-06

### Fixed
- Added the missing solver CLI argument `--electron-density-for-lmixing`.
- Fixed the real-ATDB solver status test failure caused by the solver referencing `args.electron_density_for_lmixing` without registering the argparse option.

## v0.2.7 - 2026-03-05

### Added
- Added a scientific validation status table to the Markdown and LaTeX user guides.
- Added `xstar_atomic.export` with CSV/JSON export helpers for superwind/Athena++ post-processing.
- Added CLI entry point `xstar-atomic-export-superwind`.
- Added `examples/08_compare_xstar_outputs.py` for comparing selected xstar-atomic outputs against user-supplied XSTAR CSV outputs.
- Added lightweight import tests for the export module.

### Improved
- Updated solver diagnostics to report that the XSTAR-derived type-63 same-n l-mixing collision decoder is enabled.
- Updated docs to reflect the implemented type-63 same-n l-mixing path and the current validation status of data types 51 and 98.

## v0.2.6 - 2026-03-04

### Added
- Added `tests/data/collision_type51_98_targets.csv`, generated from the collision validation inventory.
- Added API-level real-ATDB pytest coverage for representative collision `data_type=51` and `data_type=98` targets through `XSTARAtomic.collisions(...)`.
- Added a type-98 ion-alias API regression test using the `ne_ix` alias.

### Validation
- The type-51 API test validates a representative Burgess--Tully 5-point target against the inventory reference rate.
- The type-98 API test validates the Ne IX CHIANTI-style Burgess--Tully target against the inventory reference rate.

## v0.2.5 - 2026-03-03

### Fixed
- Restored the lightweight top-level `parse_ion` export so `from xstar_atomic import parse_ion` works again after the lazy-import cleanup.
- Kept the minimal top-level API limited to `ATDB`, `XSTARAtomic`, and `parse_ion`; decoder functions remain importable from their submodules.


## v0.2.4 - 2026-03-02

### Fixed
- Cleaned reStructuredText in module docstrings for the Sphinx API build.
- Fixed docutils warnings/errors in `photoionization`, `collisions`, and `recombination` module documentation.

## v0.2.3 - 2026-03-01

### Added
- Added `xstar_atomic.validation` with collision-decoder inventory and validation helpers.
- Added CLI entry point `xstar-atomic-validate-collisions`.
- Added `examples/07_collision_decoder_validation.py` for type 51/98 target discovery and type-63 same-`n` diagnostics.
- Added real-ATDB pytest checks for:
  - O VIII type-63 same-`n` l-mixing regression diagnostics.
  - Type 51 and type 98 inventory plus representative positive-rate targets when present in the local `atdb.fits`.

### Notes
- The type-63 same-`n` diagnostic checks the Python port of the XSTAR `amcrs/velimp` branch, but independent validation against XSTAR model outputs is still recommended for production science.

## v0.2.2 - 2026-02-28

### Fixed
- Corrected LaTeX backslash corruption in `docs/user_guide.tex` for the `center` and `tabular` environments.

## v0.2.1 - 2026-02-27

### Changed
- Simplified ``xstar_atomic.__init__`` to expose only ``ATDB``, ``XSTARAtomic``, and ``__version__``.
- Moved heavy decoder imports in ``api.py`` to lazy method-level imports.
- Preserved submodule-level imports such as ``xstar_atomic.collisions`` and ``xstar_atomic.recombination``.

### Fixed
- Avoids ``runpy`` warnings when executing CLI modules with ``python -m xstar_atomic.<module>`` after importing the package.

## v0.2.0 - 2026-02-26

### Added
- Implemented the type-63 same-`n` l-changing collision branch using the XSTAR `amcrs`/`velimp` ecm=0 logic.
- Added `electron_density_for_lmixing` to the high-level collision/emissivity APIs for the density-dependent impact-parameter cutoff used by same-`n` l-mixing.
- Added `--electron-density` to `xstar-atomic-collisions` and `--electron-density-for-lmixing` to emissivity/solver CLIs.
- Added diagnostic columns for same-`n` type-63 l-mixing: shell radiative sum, `cn`, selected `l` branch, and density.

### Improved
- Promoted collision data type 51 and 98 Burgess--Tully evaluators as supported collision-rate paths alongside type 56 and type 63.
- Updated package tests to check that real-ATDB type-63 same-`n` l-mixing returns finite evaluated rates when `XSTAR_ATDB_FITS` is supplied.

## v0.1.8 - 2026-02-25

### Documentation
- Added `\usepackage{amsmath,amssymb}` to the LaTeX user guide preamble for math support.


All notable changes to `xstar-atomic` are documented here.

## v0.1.7 - 2026-02-24

Fixed:
- Restored backward-compatible high-level API keys used by the examples:
  - `collisions()["matches"]` and `collisions()["evaluated_rates"]`.
  - `emissivity()["rows"]`.
  - `recombination()["summary"]`.
- Updated example/API behavior so the examples work with the current return dictionaries.

## v0.1.6 - 2026-02-23

### Added
- Added full user guide in Markdown: `docs/user_guide.md`.
- Added full user guide in LaTeX: `docs/user_guide.tex`.
- Added Sphinx documentation scaffold under `docs/sphinx/` using `sphinx.ext.autodoc`, `sphinx.ext.napoleon`, and the Read the Docs theme.
- Added Sphinx pages for user guide, examples, API reference, development notes, and changelog.
- Added `examples/06_high_level_api_quickstart.py`.
- Added optional `docs` dependency group with `sphinx` and `sphinx-rtd-theme`.

### Notes
- Sphinx API pages are generated from Python docstrings. Future public functions/classes should include clear docstrings.

## v0.1.5 - 2026-02-22

### Added
- Added flexible ion-name parsing in the high-level API. Accepted forms now include `O VIII`, `o viii`, `o_viii`, `O_VIII`, `O-VIII`, `OVIII`, and `o8`.
- Added unit tests for ion-name aliases.

## v0.1.4 - 2026-02-21

### Added
- Added real pytest smoke tests for the direct `atdb.fits` workflow.
- Added API smoke tests for:
  - low-level `ATDB.build_index()` counts,
  - O VIII Ly-alpha line extraction,
  - O VIII Ly-alpha collision-rate evaluation,
  - O VIII Ly-alpha emissivity table generation,
  - oxygen recombination inventory.
- Added CLI smoke tests using `python -m xstar_atomic.*` modules.
- Added `examples/` scripts:
  - `01_o8_lya_lines.py`,
  - `02_o8_lya_collisions.py`,
  - `03_o8_lya_emissivity.py`,
  - `04_oxygen_recombination_inventory.py`,
  - `05_low_level_atdb_index.py`.
- Added this versioned `CHANGELOG.md`.

### Notes
- Tests that require the real XSTAR database are skipped unless `XSTAR_ATDB_FITS` points to a readable `atdb.fits` file.
- Example test command:

  ```bash
  XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits pytest -q
  ```

## v0.1.3 - 2026-02-20

### Fixed
- Fixed the high-level `XSTARAtomic.emissivity()` wrapper by adding the missing `collision_data_type` default expected by the emissivity filters.

## v0.1.2 - 2026-02-19

### Fixed
- Fixed the high-level `XSTARAtomic.emissivity()` wrapper by adding the missing `include_superlevel_radiative` default expected by the emissivity filters.

## v0.1.1 - 2026-02-18

### Added
- Added the high-level `XSTARAtomic` API wrapper around the low-level `ATDB` reader.
- Added convenience methods for lines, collisions, recombination, and emissivity workflows.
- Kept `ATDB` as the low-level direct packed-FITS API.

## v0.1.0 - 2026-02-17

### Added
- Initial package refactor from validated standalone scripts.
- Added package namespace `xstar_atomic` and project name `xstar-atomic`.
- Added command-line modules for:
  - inspecting `atdb.fits`,
  - hierarchy reconstruction,
  - lines,
  - photoionization,
  - collisions,
  - recombination,
  - emissivity,
  - prototype level-population solving.
