# 0.6.88.4.1 — MACOS_WARNING_CLEANUP

This release is a warning-only portability closure on top of `0.6.88.4 — PORTABLE_PROCESS_LAYER`.

## Scope

Apple Clang reported intentionally dormant helpers/constants and libc++'s C++17 deprecation of
`std::shared_ptr::unique()`. Linux GCC produced no corresponding warnings in the accepted `.88.4` build.

The cleanup is deliberately Apple-only:

- `xstar_compiler_warnings.hpp` defines `XSTAR_APPLE_MAYBE_UNUSED` as `[[maybe_unused]]` only for Apple Clang and as empty elsewhere.
- The exact declarations seen in the arm64/x86_64 GitHub Actions logs are annotated; none are deleted.
- The existing `bound_free_payload_v06823087.unique()` expression remains the non-Apple branch unchanged.
- Apple Clang suppresses only `-Wdeprecated-declarations` around that single call; no global `-Wno-*` flags are added.
- No physics arithmetic, controller/traversal ordering, contribution/accumulation order, cutoff, publication rule, ABI, output schema, or process-layer semantics are changed.

## Qualification

Linux is the preservation oracle. Required gates are:

1. source/focused qualification and Linux dry-run equivalence to `.88.4`;
2. full Linux native build and `make test`;
3. same-host `.88.4` versus `.88.4.1` fixed-state output byte equivalence;
4. GitHub Actions `macos-15` and `macos-15-intel` full native build/regression;
5. `MACOS_WARNING_CLEANUP_068841_HOST_WARNING_FREE_BUILD=ACCEPT` on both macOS runners.

The macOS warning-free gate scans the native build log for any `warning:` diagnostic, so this release does not hide future warnings globally.
