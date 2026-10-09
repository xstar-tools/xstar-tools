# 0.6.91.3 — LINUX_ARM64_PACKAGING

This milestone adds native Linux `aarch64` wheel construction and **packaging**
qualification. It does not change the XSTAR solver, native C++ scientific code,
scientific algorithms, source hashes, or ABIs. The accepted science revision
remains **0.6.90.5.5** (including the Type-49/Mn scientific correction).

## Scope and independent acceptance

- Accepted prerequisite: `0.6.91.1 — LINUX_ARM64_BUILD` (`HOST_RESULT=ACCEPT`).
- Accepted packaging target: `manylinux_2_28_aarch64` repaired wheels, verified on
  **native** `ubuntu-24.04-arm`, using the existing `pypi-linux` Makefile
  profile and SHA-256-pinned CFITSIO **4.6.2** source.
- Native packaging qualifier: CPython 3.11 and 3.13; future PyPI release workflow
  builds the existing full CPython 3.9–3.14 matrix on ARM64, as on x86-64.
- `auditwheel repair` must vendor CFITSIO into the wheel and leave a working
  installed ELF loader closure. Isolated `cibuildwheel` test runs the *existing*
  `tools/packaging/pypi_release_linux_smoke.py` on **each** interpreter.
- The additional qualifier checks wheel filename and WHEEL tags, actual ELF64
  AArch64 code, all 13 expected non-embedding shared libraries and 5 native
  executables, pinned science revision `0.6.90.5.5`, ABI `60487` and `6048110`,
  native provenance, vendored CFITSIO, and external atomic-data boundary.
- PyPI release integration adds Linux ARM64 wheels to the aggregate artifact
  manifest and checks the ARM64 member is present before publishing. PyPI is
  **not** published by the standalone qualification workflow.
- No ARM32/piwheels wheel, MPI executable, `libxstar_backend_python` embedding
  plugin, `atdb.fits` or compiler-induced scientific algorithm changes.

**IMPORTANT:** The packaging gate is not a production astrophysics test. The
optional `0.6.91.2 — LINUX_ARM64_SCIENCE_QUALIFICATION` full-model reference
suite requires authentic pinned `atdb.fits`, model inputs and FORTRAN/C++
outputs. Its current `HOST_RESULT=NOT_RUN` must not be silently promoted to
`ACCEPT` because a wheel was built. ARM64 physics/fixed-state regression has
separate passing evidence under the uniform platform qualification standard.

**Acceptance state: ACCEPT (2026-10-08).** The native ARM64 workflow built and smoke-tested CPython 3.11 and 3.13 wheels, both passed Twine and the ELF/CFITSIO/provenance checks, and the host qualifier reported all six `LINUX_ARM64_PACKAGING_06913_*` gates as `ACCEPT`. This is packaging/runtime acceptance, not publication to PyPI or completion of the full real-model science gate. The later 0.6.91.4 five-host CPython 3.13 closure also passed.

## Run on GitHub Actions

Commit the version 0.6.91.3 source and open **Actions → Linux ARM64 packaging
0.6.91.3 → Run workflow**. The native runner first checks the accepted science
source-hash inventory and build metadata, then creates and repairs two wheels.
Each wheel is automatically installed and tested in the `cibuildwheel` isolated
environment. The final artifact checker must print:

```text
LINUX_ARM64_PACKAGING_06913_FREEZE=ACCEPT
LINUX_ARM64_PACKAGING_06913_SOURCE_CONTRACT=ACCEPT
LINUX_ARM64_PACKAGING_06913_WHEEL_METADATA=ACCEPT
LINUX_ARM64_PACKAGING_06913_ELF_AARCH64=ACCEPT
LINUX_ARM64_PACKAGING_06913_CFITSIO_BUNDLED=ACCEPT
LINUX_ARM64_PACKAGING_06913_HOST_RESULT=ACCEPT
```

A preliminary source-only check on any host is deliberately **NOT_RUN** as
native packaging qualification:

```bash
python -B tools/qualification/run_linux_arm64_packaging_host_0_6_91_3.py \
  --package "$PWD" --preflight-only
```

On a native Linux ARM64 runner with already repaired wheels:

```bash
python -B tools/qualification/run_linux_arm64_packaging_host_0_6_91_3.py \
  --package "$PWD" \
  --wheel-dir "$PWD/wheelhouse" \
  --output-root /tmp/linux_arm64_packaging_06913_evidence \
  --require-builds cp311 cp313
```

The strict verifier is only one part of acceptance: a green `cibuildwheel`
job is needed to establish the separate **clean-installed wheel** smoke for
each CPython version. The release matrix checks all six selected interpreters.

Do not treat artifacts produced by an x86-64 host, cross compilation alone, or
synthetic wheels from the unit tests as native ARM64 host acceptance. The
source archive and attached GitHub logs should be reviewed before closing the
milestone. See {doc}`linux_arm64_build_0_6_91_1` and
{doc}`linux_arm64_science_0_6_91_2` for the preceding gates.
