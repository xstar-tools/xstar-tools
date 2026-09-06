# 0.6.89.5 — PYPI_CROSS_PLATFORM_RELEASE_CLOSURE

`0.6.89.5` is the unified PyPI release candidate built on the formally accepted platform-specific wheel baselines:

- Linux x86_64: `0.6.89.2.2`;
- macOS arm64/x86_64: `0.6.89.3`;
- Windows AMD64: `0.6.89.4.5`.

The milestone changes release/version metadata and release orchestration only. The frozen science revision remains `0.6.48.12.3.45.3.3.8`; public C API ABI `60487`, production-zone ABI `6048110`, fixed-state ABI `60486`, and XSPEC table ABI `1` remain unchanged.

## Release set

The GitHub workflow `.github/workflows/pypi-cross-platform-release.yml` builds and tests:

- 6 CPython 3.9–3.14 `manylinux_2_28_x86_64` wheels;
- 6 CPython 3.9–3.14 `macosx_11_0_arm64` wheels;
- 6 CPython 3.9–3.14 `macosx_11_0_x86_64` wheels;
- 6 CPython 3.9–3.14 `win_amd64` wheels;
- one `xstar_tools-0.6.89.5.tar.gz` sdist.

The aggregate release therefore contains exactly 25 publishable distributions. A Python-only `py3-none-any` control wheel is forbidden from the release bundle.

## Native build hosts

No local macOS or Windows machine is required. GitHub-hosted native runners perform the macOS and Windows builds/tests. The aggregate job runs on Linux and only collects already-qualified distribution artifacts.

## Frozen platform contracts

Linux retains the accepted `pypi-linux` Make target, pinned CFITSIO 4.6.2 build, `manylinux_2_28_x86_64` container, and auditwheel repair.

macOS retains `pypi-macos`, pinned CFITSIO 4.6.2, `MACOSX_DEPLOYMENT_TARGET=11.0`, native arm64/x86_64 runners, and delocate repair. No `universal2` wheel is emitted.

Windows retains `pypi-windows`, the UCRT64/MinGW-w64 toolchain, pinned shared CFITSIO 4.6.2, explicit CFITSIO metadata propagation, and delvewheel repair using `--ignore-existing --analyze-existing --analyze-existing-exes` so XSTAR DLLs remain in-package while external CFITSIO/MinGW runtime DLLs are vendored.

All ordinary release wheels exclude MPI, the standalone Python-embedding plugin, C++ implementation sources, and `atdb.fits`. Package metadata remains `GPL-3.0` and includes the GNU GPL Version 3 license text.

## Acceptance gates

Each of the 24 wheel jobs must pass its platform-specific clean-install smoke, artifact checker, and `twine check`. The sdist must pass `twine check`. The final aggregate job must verify the exact 24 wheel filenames plus the one sdist, validate version/license/native metadata, reject a universal control wheel, and emit SHA-256 checksums.

Formal acceptance requires the aggregate job to end with:

```text
PYPI_CROSS_PLATFORM_RELEASE_CLOSURE_06895_BUNDLE_RESULT=ACCEPT
PYPI_CROSS_PLATFORM_RELEASE_CLOSURE_06895_GITHUB_RESULT=ACCEPT
```

Publication is intentionally separate from this workflow. After acceptance, the exact aggregate artifact can be uploaded first to TestPyPI and then unchanged to PyPI.
