# 0.6.90.2 — CONDA_FORGE_RELEASE_CLOSURE

`0.6.90.2` closes the conda packaging campaign against the public conda-forge distribution. It is a qualification/release-closure milestone; it does not claim that `0.6.90.2` itself is already published on PyPI or conda-forge.

## Public package under test

The immutable public package remains:

```text
xstar-tools 0.6.89.5
PyPI source SHA-256 961b66b0ce0b3bc966a6322a3bef05e65879e1f09d50e8d4b9527030ad7a91b2
```

The canonical public package page is `https://anaconda.org/conda-forge/xstar-tools`. The recipe under `conda/recipe/` is the exact accepted live conda-forge build-1 recipe for the immutable PyPI `0.6.89.5` source, including the published summary and description. The host runner requires canonical live-recipe content equivalence and retains byte-for-byte comparison for `build.sh`.

## Host matrix

The release-closure workflow installs the package directly from the public `conda-forge` channel on:

- `linux-64` — GitHub `ubuntu-24.04`;
- `osx-arm64` — GitHub `macos-15` (must exist publicly before closure can be accepted);
- `osx-64` — GitHub `macos-15-intel`.

Windows conda packages are not supported. Windows native users remain covered by the accepted PyPI/MSYS2 UCRT64/MinGW-w64 wheel line; MSVC and Windows MPI are not planned.

## Required public-install gates

Each host must create a fresh micromamba environment from `conda-forge` with `python=3.13` and `xstar-tools=0.6.89.5`, require conda feedstock build number `1`, then require:

- exact installed xstar-tools version and target subdir;
- conda-forge provenance for the installed package;
- `xstar-tools version`;
- `xstar-cpp --version` and `xstar-cpp --abi` (`60487`);
- `xstar-xspec --version`;
- `xstar-tools doctor --require zone-cpp --json`;
- external `cfitsio` as a separate conda package and no vendored CFITSIO inside `xstar_tools`;
- no `xstar-xspec-mpi` executable in the ordinary conda package;
- no standalone `xstar_backend_python` plugin;
- no bundled `atdb.fits`;
- installed package license metadata `GPL-3.0-only`;
- the pinned offline bremsstrahlung science smoke.

The host runner also downloads the live `recipe.yaml` and `build.sh` from the feedstock repository. The embedded `conda/recipe/recipe.yaml` is the accepted live build-1 recipe, so `recipe.yaml` must match the live feedstock after newline/trailing-whitespace/blank-separator normalization, while `build.sh` must match byte-for-byte. The PyPI source version and SHA-256 remain immutable; the conda build-number increment and published package metadata do not create a new PyPI source release.

The live feedstock now exposes build number `1` for `linux-64`, `osx-64`, and `osx-arm64`. Release closure still requires the three public-install host jobs to finish with `HOST_RESULT=ACCEPT`; publication alone is not treated as acceptance.

## Frozen boundaries

This milestone changes no science and no public ABI. It retains:

```text
science revision      0.6.48.12.3.45.3.3.8
C API ABI             60487
production-zone ABI   6048110
fixed-state ABI       60486
XSPEC table ABI       1
```

The only native-source differences from accepted `0.6.90.1` are package-version metadata in the C++ Makefile and XSPEC frontends.
