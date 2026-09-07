# 0.6.90.1 — CONDA_NATIVE_HOST_QUALIFICATION

This milestone qualifies the already-published `xstar-tools 0.6.89.5` conda-forge recipe on native POSIX hosts without reopening XSTAR science or public ABIs.

`0.6.90.1` is the qualification-tooling/source milestone. It is **not** treated as an already-published PyPI or conda package. Until a newer upstream release is actually published, the package under test is the immutable public PyPI `0.6.89.5` sdist with SHA-256:

```text
961b66b0ce0b3bc966a6322a3bef05e65879e1f09d50e8d4b9527030ad7a91b2
```

The repository copy under `conda/recipe/` is the exact accepted feedstock recipe/build script for that release. In particular, its `build.sh` retains the compatibility probe that uses the future `conda` profile when available and otherwise falls back to the accepted `pypi-linux` / `pypi-macos` profiles required by published `0.6.89.5`.

Qualification hosts:

- Linux x86_64 → `linux-64`
- macOS arm64 → `osx-arm64`
- macOS Intel x86_64 → `osx-64`

Each host copies the exact released recipe unchanged, supplies a qualification-only `variants.yaml`, builds with `rattler-build`, executes the recipe's native tests during build, then reruns the tests from the produced `.conda` package in a fresh environment.

Standalone `rattler-build` does not receive conda-forge's global pinning automatically. The host runner therefore supplies the current conda-forge compiler/C-standard-library values needed by `${{ compiler('cxx') }}` and `${{ stdlib('c') }}`:

```text
linux-64:   gxx 15, sysroot 2.17
osx-64:     clangxx 21, macosx_deployment_target 11.0
osx-arm64:  clangxx 21, macosx_deployment_target 11.0
Python:     3.13 qualification variant
```

The exact released recipe tests:

```text
xstar-tools version
xstar-cpp --version
xstar-cpp --abi
xstar-xspec --version
xstar-tools doctor --require zone-cpp --json
```

The source-side `.90.1` qualification still freezes science revision `0.6.48.12.3.45.3.3.8`, C API ABI `60487`, production-zone ABI `6048110`, fixed-state ABI `60486`, and XSPEC table ABI `1`.

Windows conda-native remains deferred. This does not change the accepted Windows PyPI/MSYS2 native support.
