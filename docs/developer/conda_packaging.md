# Conda and conda-forge packaging

The current packaging line is `0.6.90 — CONDA_PACKAGING_REFRESH`, `0.6.90.1 — CONDA_NATIVE_HOST_QUALIFICATION`, and `0.6.90.2 — CONDA_FORGE_RELEASE_CLOSURE`. The released recipe uses the conda-forge v1 `recipe.yaml` format; `.90.1` qualified native builds with `rattler-build`, while `.90.2` verifies clean installation from the public conda-forge channel.

## Current public package

The public conda-forge/feedstock package currently tracks the published PyPI release:

```text
xstar-tools 0.6.89.5
SHA-256 961b66b0ce0b3bc966a6322a3bef05e65879e1f09d50e8d4b9527030ad7a91b2
```

`0.6.90.1` is a qualification/source milestone and is not treated as an already-published PyPI artifact. Host qualification therefore uses the exact accepted `0.6.89.5` recipe and source checksum rather than rewriting the recipe to an unpublished version.

## Current platform policy

- `linux-64`: native XSTAR runtime
- `osx-arm64`: native XSTAR runtime
- `osx-64`: native XSTAR runtime
- `win-64`: deferred for conda-native qualification

Windows native XSTAR remains supported through the accepted PyPI/MSYS2 UCRT64 line; the deferral applies only to the conda toolchain contract.

## Native package boundary

The `0.6.90+` source tree provides `XSTAR_TOOLS_NATIVE_PROFILE=conda` for future releases. The already-published `0.6.89.5` source predates that profile, so the accepted feedstock `build.sh` probes for it and otherwise falls back to the qualified `pypi-linux` / `pypi-macos` native profiles.

Both paths preserve the intended package boundary:

- build the non-MPI native runtime;
- exclude the optional standalone Python-embedding plugin;
- link against CFITSIO supplied by conda;
- keep `atdb.fits` external;
- preserve the frozen science revision and public ABIs.

The canonical released recipe lives at `conda/recipe/recipe.yaml` and is byte-for-byte the accepted `0.6.89.5` feedstock recipe supplied for this qualification.

## 0.6.90.1 host qualification

`.github/workflows/conda-native-host-qualification.yml` exercises three native hosts. Each job copies the released recipe unchanged, supplies a qualification-only `variants.yaml`, runs `rattler-build build --test native`, then re-runs `rattler-build test` on the produced `.conda` artifact in a fresh environment.

The extra variants file is necessary only because standalone `rattler-build` does not automatically receive conda-forge's global compiler/C-stdlib pinning. The host runner supplies the current conda-forge values for `cxx_compiler`, `cxx_compiler_version`, `c_stdlib`, `c_stdlib_version`, and Python 3.13.

The exact released recipe tests:

- `xstar-tools version`;
- `xstar-cpp --version`;
- `xstar-cpp --abi`;
- `xstar-xspec --version`;
- `xstar-tools doctor --require zone-cpp --json`.

Source-side `.90.1` qualification separately freezes science revision `0.6.48.12.3.45.3.3.8` and the accepted public ABIs.

## 0.6.90.2 public release closure

`.github/workflows/conda-forge-release-closure.yml` installs the already-published `xstar-tools 0.6.89.5` package directly from the public conda-forge channel on the same three POSIX hosts. It verifies the live feedstock recipe/build script against the accepted released copies, checks conda package provenance and external CFITSIO, replays native CLI/ABI/doctor checks, confirms the ordinary package remains MPI-free and without the Python-embedding plugin or `atdb.fits`, validates GPL-3.0-only installed metadata, and runs the pinned offline science smoke.

After all three hosts return `CONDA_FORGE_RELEASE_CLOSURE_06902_HOST_RESULT=ACCEPT`, the conda packaging campaign is closed.
