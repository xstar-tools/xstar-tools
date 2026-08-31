# macOS native build compile closure — 0.6.88.3.1

`0.6.88.3.1` closes the compile defect found by native Apple-Clang qualification of `0.6.88.3` without widening the portability scope.

The inherited macOS contract remains Apple `clang++`, `.dylib` shared libraries, `-dynamiclib`, `@rpath/libxstar_*.dylib` install names, `@loader_path` runtime search, and CFITSIO discovery through explicit overrides, `pkg-config`, Homebrew, then the linker-default fallback.

Apple builds cannot use the Linux/glibc `::exp10` extension in the Type-77 special exact-match branch. The closure therefore uses `0x1.c2ccf22133138p-4` only under `__APPLE__`. This literal has IEEE-754 bits `0x3fbc2ccf22133138`, matching the frozen canonical Linux/glibc result. Non-Apple builds retain the original `::exp10(rec)` expression.

The GitHub Actions macOS matrix must use Python 3.12 and install `pytest` explicitly before qualification. The host runner accepts an optional `--predecessor`; omitting it skips only provenance/source-diff checks, not native build/runtime/regression gates.

Typical CI qualification command:

```bash
python3 tools/qualification/run_macos_native_build_compile_closure_host_0_6_88_3_1.py \
  --package "$PWD" \
  --output-root "$PWD/run_macos_native_build_compile_closure_068831_host" \
  --jobs 4
```

When an unpacked `0.6.88.3` predecessor is available, add:

```text
--predecessor /path/to/xstar_tools-0.6.88.3
```
