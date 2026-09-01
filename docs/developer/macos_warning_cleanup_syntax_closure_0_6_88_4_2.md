# 0.6.88.4.2 — MACOS_WARNING_CLEANUP_SYNTAX_CLOSURE

This release is a syntax-only closure on top of `0.6.88.4.1 — MACOS_WARNING_CLEANUP`.

## Host finding

The `.88.4.1` GitHub Actions result split by architecture:

- `macos-15` arm64: full ACCEPT, including warning-free build and regression.
- `macos-15-intel` x86_64: source qualification ACCEPT, then compile REJECT in `opacity_kernels.cpp` because Apple Clang rejected the macro expansion `[[maybe_unused]] static inline ...` with `error: an attribute list cannot appear here`.

This is a warning-cleanup annotation-placement defect, not a science/runtime/link/process-layer defect.

## Production change

Only `src/xstar_tools/xstar/cpp/xstar_compiler_warnings.hpp` changes semantically relative to `.88.4.1`:

```cpp
#if defined(__APPLE__) && defined(__clang__)
#define XSTAR_APPLE_MAYBE_UNUSED __attribute__((unused))
...
#else
#define XSTAR_APPLE_MAYBE_UNUSED
...
#endif
```

The Clang/GNU-style `__attribute__((unused))` is valid in the existing pre-declaration position used for both functions and variables. All warning-site `.cpp` files remain byte-identical to `.88.4.1`; no declarations are moved or deleted.

The scoped Apple-Clang suppression around the existing `std::shared_ptr::unique()` call is carried forward unchanged. No global `-Wno-*` flags are added.

## Frozen behavior

No physics arithmetic, controller/traversal ordering, contribution/accumulation order, cutoff, publication rule, ABI, output schema, process-layer behavior, or Linux compiler flag changes are permitted.

Off Apple Clang, `XSTAR_APPLE_MAYBE_UNUSED` still expands to nothing, so Linux preprocessing/runtime behavior remains the `.88.4.1`/`.88.4` behavior.

## Qualification

Before macOS rerun:

1. direct Clang syntax smoke must compile the exact existing function/variable macro positions without warnings;
2. all warning-site `.cpp` files must be byte-identical to `.88.4.1`;
3. Linux `make -Bn all` must be equivalent after package-version normalization;
4. Linux full build and `make test` must pass;
5. fixed-state products must match the frozen `.88.4.1` hashes exactly.

Formal host acceptance requires both GitHub Actions runners to return:

```text
MACOS_WARNING_CLEANUP_SYNTAX_CLOSURE_068842_HOST_WARNING_FREE_BUILD=ACCEPT
MACOS_WARNING_CLEANUP_SYNTAX_CLOSURE_068842_HOST_MACOS_REGRESSION=ACCEPT
MACOS_WARNING_CLEANUP_SYNTAX_CLOSURE_068842_HOST_RESULT=ACCEPT
```
