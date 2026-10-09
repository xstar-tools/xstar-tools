# 0.6.91.4 — CROSS_PLATFORM_CLOSURE

This milestone is a **non-science, non-MPI, cross-platform release regression**
that verifies a repaired and installed native wheel on each of five hosts:

| Host | GitHub Actions runner | Native PyPI wheel |
|---|---|---|
| Linux x86_64 | `ubuntu-24.04` | `cp313-manylinux_2_28_x86_64` |
| Linux aarch64 | `ubuntu-24.04-arm` | `cp313-manylinux_2_28_aarch64` |
| macOS arm64 | `macos-15` | `cp313-macosx_11_0_arm64` |
| macOS Intel x86_64 | `macos-15-intel` | `cp313-macosx_11_0_x86_64` |
| Windows AMD64 | `windows-2025` (MSYS2 UCRT64/MinGW-w64) | `cp313-win_amd64` |

The new `cross-platform-closure.yml` **does not publish to PyPI**.
It builds one wheel per host using the same pinned CFITSIO and the existing
`cibuildwheel` build, repair and *clean-installed* smoke test contracts as the
normal release workflow. The post-build host validator
`tools/qualification/run_cross_platform_closure_host_0_6_91_4.py` verifies
science freeze, source concordance, package version and ABIs; host architecture;
repaired wheel tag and WHEEL/METADATA; every native artifact; native-build
provenance; packaged CFITSIO; and that neither MPI, standalone Python
embedding nor `atdb.fits` are in a wheel. It writes `result.json` outside
the source tree, including an error on rejection. Source tests and synthetic
unit tests are **not** a substitute for a native green host run.

**Acceptance policy (satisfied on 2026-10-08):** Each of the five host jobs must independently report
`CROSS_PLATFORM_CLOSURE_06914_HOST_RESULT=ACCEPT`, after the corresponding
`cibuildwheel` isolated smoke tests completed successfully. An independent aggregate job must also report `CROSS_PLATFORM_CLOSURE_06914_HOST_RESULT=ACCEPT` with exactly five matching, source-version-bound reports. Failure or missing
evidence from any host means the milestone is **pending or rejected**, never
fully accepted. `workflow_dispatch` can start the experiment without a release
tag or publication.

## Accepted host evidence (2026-10-08)

The GitHub Actions five-host run and its uploaded host artifacts met the acceptance policy above. All five native CPython 3.13 build/repair/clean-install smoke jobs reported `CROSS_PLATFORM_CLOSURE_06914_HOST_RESULT=ACCEPT`. The separate aggregate report confirmed:

```text
CROSS_PLATFORM_CLOSURE_06914_FIVE_HOSTS=5
CROSS_PLATFORM_CLOSURE_06914_HOST_RESULT=ACCEPT
```

The host evidence records the following SHA-256 digests for the qualified **wheel files** (not source archives):

| Host | Wheel SHA-256 |
|---|---|
| Linux x86_64 | `08177a12e7c5816943b5ad0e13e37a24570883f73cda71b8e0fcc1b953d6b94f` |
| Linux aarch64 | `c4063caa06d5ab509f1a9b6f30a2883dbfec8c5f93a9b7b16d70673aabdf516a` |
| macOS arm64 | `6346f690dd4b41a147a11fa0cb0c4eb33936f60200c051cdc6c31ab84b8ded4f` |
| macOS x86_64 | `f8e4417e94ae89f13a644590dd6cdf7b9f0ba33e314d2e256757c9445c2d0321` |
| Windows AMD64 | `fa56e92f7fe255d86e7e62f22f623a31c1b994f7b92c9a797cc0886a83584c91` |

All five reports identify package `0.6.91.4`, frozen science revision `0.6.90.5.5`, C API ABI `60487`, and production-zone ABI `6048110`. Wheel integrity checks also passed. This formally **closes 0.6.91.4 as ACCEPTED** without modifying the 51 frozen science-source files. The ARM64 Tier 1 native physics and fixed-state regression checks also passed; the optional Tier 2 full-model ARM64 science gate from 0.6.91.2 remains `NOT_RUN` and is not overridden by wheel acceptance. Complete XSTAR models with the external atomic database were not a prerequisite for the other accepted hosts either.

## Release engineering policy

The normal `.github/workflows/pypi-release.yml` retains the release wheel
matrix (currently CPython 3.9–3.14) and publishes only on a matching GitHub
release tag. It invokes the **reusable**, version-independent ARM64 validator
`tools/release/validate_linux_arm64_wheels.py` instead of the historical
`run_linux_arm64_packaging_host_0_6_91_3.py`, and obtains the package
version from `pyproject.toml`. The science revision is a separate accepted
freeze policy from `qualification/parity_freeze.json`. Historic qualification
scripts and acceptance evidence are not rewritten when releasing new versions.

The milestone updates *no frozen XSTAR scientific source files* and changes no
scientific tolerances or C API/production-zone/fixed-state/XSPEC ABIs. The
accepted science revision is **0.6.90.5.5**. Linux ARM64 build acceptance
(0.6.91.1) and ARM64 wheel packaging acceptance (0.6.91.3) are already
recorded. **Optional 0.6.91.2 full-model ARM64 comparison remains
`NOT_RUN`**, pending externally provided independently accepted SHA-256 pinned
`atdb.fits` and FORTRAN/accepted-C++ model outputs. This additional comparison
is not required by the uniform platform-level qualification contract; no
package build may promote that **unexecuted full-model** status to `ACCEPT`.

Conda-forge support remains Linux x86_64 and macOS arm64/x86_64 only.
Windows conda, Windows MSVC and Windows MPI are not supported. ARM32/piwheels
is outside the scope of this ARM64 release campaign.
