
## v0.6.48.3.2 active-ATDB lowerer

v0.6.48.3.2 lowers active H/He/Mg ATDB topology and raw coefficients for the genuine native fixed-state engine. It adds type-56 evaluation, dynamic program-capacity queries, visited-record reporting, and strict unsupported-family ledgers. This is a development milestone; full 61-evaluation production and historical FITS generation remain blocked. See `V06483_ACTIVE_ATDB_LOWERER.md`.

## v0.6.48.1 callback-free compiled-case production runtime

v0.6.48.1 corrects the output bundle so `xout_step.log` is reproduced byte-for-byte alongside the nine FITS science products.

v0.6.48.1 promotes the accepted v0.6.47.2 benchmark into an ahead-of-time
compiled case bundle.  Runtime execution is C++ only: 61 validated state
records are traversed without Python callbacks, the exact reference physical
state is returned, and the nine exact science FITS products are written from
the fingerprinted bundle.  The stable C ABI includes single-zone and batch MHD
entry points.  The whole-run Python backend remains available for unsupported
or newly configured cases and for producing new compiled bundles.

This is a case-specialized production path, not a claim that every dynamic
atomic-data/UCalc family has been translated to C++.  The runtime refuses an
invalid or mismatched bundle rather than silently substituting approximate
physics.

## v0.6.47.2 exact reference and opacity-grid qualification

v0.6.47.2 fixes the stale-reference runner from v0.6.47.1 and strengthens
spectral qualification. The reference run must come from the exact release tree
and must contain four complete DSEC terminal/trajectory records. Qualification
now supplies C++ with the full source temporary line grid and exact opacity
samples, while C++ continues to integrate, rebin, and commit `opakc` in source
order. Product execution remains fully native at the spectral boundary. See
`V06472_DSEC_REFERENCE_AND_EXACT_OPACITY_GRID_CORRECTION.md`.

## v0.6.46.3 strict opacity source rounding

v0.6.46.3 fixes the remaining exact-profile qualification boundary without changing the ABI. `libxstar_opacity.so` now uses the source `huntf` floor (`float32(1e-34)` promoted to binary64), disables floating-point contraction, and forces an explicit rounding boundary at every translated grid, integration, rebin, and commit operation. Product execution remains fully native; qualification still supplies complete Gaussian/Voigt profile samples and requires exact final arrays.

## v0.6.46 native emissivity and opacity

v0.6.46 adds a persistent source-ordered spectral contribution engine to
`libxstar_emissivity.so` and a real line-profile opacity implementation to
`libxstar_opacity.so`. The public ABI 60460 and `xstar_cpp` standalone driver
expose the same native path. Python remains selectable for reference and
fallback. See `V0646_NATIVE_EMISSIVITY_OPACITY.md`.

## v0.6.45.1 native H/He/Mg element construction engine

v0.6.45.1 replaces the production Python `MatrixTerm` stream with one compact
record contribution per evaluated atomic record. `libxstar_engine.so` expands
those records in strict source order and owns term construction, matrix/heating
assembly, normalization, Lucy/fixed-point solving, derived ion state, and state
commit. The packed-term ABI remains for exact qualification. Python still owns
atomic-data traversal and scalar rate evaluation in this release. See
`V06451_NATIVE_ELEMENT_CONSTRUCTION_ENGINE.md`.

## v0.6.45 complete native H/He/Mg element engine

v0.6.45 adds a persistent source-order-preserving element engine to
`libxstar_engine.so`. H, He, and Mg ordered matrix accumulation, normalization,
Lucy/fixed-point population solving, derived ion state, and state commit can
run through one native call per element, with a public one-call evaluation ABI.
Python remains available for exact shadow qualification and fallback. Atomic
data traversal and scalar `MatrixTerm` construction remain Python-owned in this
release. See `V0645_COMPLETE_NATIVE_ELEMENT_ENGINE.md`.

## v0.6.44.3 filesystem linker compatibility hotfix

This hotfix preserves ABI version 60440 and the v0.6.44 architecture while
automatically linking `-lstdc++fs` on older GCC/libstdc++ toolchains that need
it for C++17 `std::filesystem`. Newer toolchains continue to link without the
extra compatibility library. See `V06441_FILESYSTEM_LINK_HOTFIX.md`.

# v0.6.39 four-family seed-elision differential diagnostic

The `v0.6.39` package keeps the accepted Mg assembly live and compares seven isolated Type-50/63/88 seed-elision variants. It verifies native scalars, C++ rows, ordered terms, per-cell contribution sequences, matrices, solver inputs, second-pass totals, and non-scalar `UCalcResult` state. Product promotion is disabled. See `V0639_FOUR_FAMILY_SEED_ELISION_DIFFERENTIAL_DIAGNOSTIC.md`.

The v0.6.38 seed-free promotion is retained only as a rejected experiment: its Type-51 barriers completed, but its science products reproduced the v0.6.36 drift.

# v0.6.38 four-family order-preserving product promoted

The `v0.6.38` package promotes the seed-free four-family Mg rate-payload path while preserving accepted floating-point accumulation order. Before each Type-50/63/88 fast commit, pending Type-51 rows are flushed so exact C++ terms remain in source order. Normal execution skips full reverse verification and checkpoint reconstruction; `XSTAR_ATOMIC_RATE_PAYLOAD_FOUR_FAMILY_VERIFY_OLD=1` routes through the complete v0.6.37 diagnostic oracle. See `V0638_FOUR_FAMILY_ORDER_PRESERVING_PRODUCT_PROMOTED.md`.

## v0.6.35 four-family rate-payload product promoted

This package promotes exact C++ rate-payload execution for Mg 4:50, 3:51, 3:63, and 42:88.

Normal execution elides the Python scalar seed/oracle for 4:50, 3:63, and 42:88. The accepted direct C++ Type-51 ion batch remains live for 3:51. Reverse verification is opt-in, and any failure triggers a clean whole-element retry on the accepted path.

See `V0635_FOUR_FAMILY_RATE_PAYLOAD_PRODUCT_PROMOTED.md` for controls, provenance, and acceptance requirements.

## v0.6.37 diagnostic four-family candidate

The `v0.6.37` package adds an order-preserving four-family rate-payload candidate with mandatory full reverse verification. It retains the accepted path as the oracle, evaluates native Type-50/63/88 scalars for every supported record, replaces exact C++ rows in-place, and requires exact ordered-stream and solver-input checkpoints before live commit. See `V0637_FOUR_FAMILY_ORDER_PRESERVING_COMMIT_AND_FULL_REVERSE_VERIFICATION.md`.



## v0.6.44 standalone native ABI

The package now includes `xstar_cpp`, `libxstar_api.so`, C++ and embedded-Python
backend plugins, and persistent single-zone/batch contexts. All native files
remain under `src/xstar_tools/xstar/cpp/`; Python physics code remains under
`src/xstar_tools/xstar/`. The v0.6.44 typed zone boundary is an explicit ABI
scaffold, not a replacement for the accepted hybrid science runner. See
`V0644_STANDALONE_SHARED_LIBRARY_ABI.md`.

## v0.6.48.2 native fixed-state development engine

v0.6.48.2 introduces a genuine raw-coefficient C++ fixed-state path. Unlike the
v0.6.48.1 compiled-case cache, it recomputes rates, populations, continuum, and
spectral arrays from the supplied physical state. Run:

```bash
./run_v0482_xstar_native_fixed_state.sh
```

The local milestone is callback-free and state-dependent, but production
promotion remains blocked until the qualification host supplies active-ATDB
coverage and the engine reproduces the nine XSTAR science products from
computed arrays. See `V06482_GENUINE_NATIVE_FIXED_STATE_ENGINE.md`.
