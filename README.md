## v0.6.44.1 filesystem linker compatibility hotfix

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
