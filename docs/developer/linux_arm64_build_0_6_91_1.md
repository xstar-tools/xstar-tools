# Linux ARM64 build qualification (0.6.91.1)

`0.6.91.1 — LINUX_ARM64_BUILD` is a native **Linux aarch64/ARM64 compilation,
link, and loader** qualification milestone. It does **not** add scientific
algorithms, expand the scientific acceptance envelope, or publish ARM64 wheels.

## Scope and acceptance

- Build the existing full **non-MPI** XSTAR C++ targets using GNU Make and GNU
  C++17 (`make PLATFORM=linux all`). Do not use `-march=native`, LTO, PGO,
  `-Ofast`, or `-ffast-math`; preserve the existing strict FP-contract flags.
- Test on an actual native Linux `aarch64` host, with 64-bit pointers and an
  AArch64-target GCC. Cross-compiled and emulated results are **not** accepted
  as native-host evidence.
- Require every native executable and shared library to be ELF64/AArch64,
  have resolvable dynamic dependencies, and pass CLI/backend loading smoke
  checks. All **14 shared libraries and 5 executables** must be produced.
- Run existing metadata, science freeze, source concordance, and Mn/Type-49
  refreeze checks before compilation. Verify frozen source hashes again after
  compiling; no frozen scientific source bytes or ABI values may change.
- Keep runtime artifacts and logs outside the source tree, and publish a JSON
  result plus per-stage logs even when a build is rejected.

**Acceptance state:** pending real native ARM64 GitHub Actions host run. Only
`LINUX_ARM64_BUILD_06911_HOST_RESULT=ACCEPT` from the host-build mode is an
ARM64 build acceptance signal. A preflight-only ACCEPT on x86-64 is not.

## GitHub Actions

Run **Actions → Linux ARM64 native build 0.6.91.1 → Run workflow**. The workflow
uses GitHub's `ubuntu-24.04-arm` native runner and installs `build-essential`,
`binutils`, `pkg-config`, `libcfitsio-dev`, and Python development headers.
The generated evidence is uploaded as an Actions artifact whether the host
build succeeds or fails. A single `make all` also compiles the optional
Python-embedding backend; **MPI is not part of this milestone**.

## Run on a local Linux ARM64 machine

From the unpacked project root:

```bash
sudo apt-get update
sudo apt-get install -y build-essential binutils libcfitsio-dev pkg-config python3-dev
python3 -B tools/qualification/run_linux_arm64_build_host_0_6_91_1.py \
  --package "$PWD" \
  --output-root "$(dirname "$PWD")/run_linux_arm64_build_06911_host" \
  --jobs 2
```

The output root must be new and **outside** the package tree. The compiled
working copy is kept at `run_linux_arm64_build_06911_host/package/` and logs at
`run_linux_arm64_build_06911_host_preflight_logs/`.

For an architecture-independent **source-policy preflight** only:

```bash
python3 -B tools/qualification/run_linux_arm64_build_host_0_6_91_1.py \
  --package "$PWD" --preflight-only
```

This never reports host ACCEPT. The accepted compiler/library policy remains
Linux x86-64, macOS ARM64/x86-64, and Windows UCRT64 until the ARM64 host build
is independently qualified.

## Exclusions and next steps

- **0.6.91.2 — LINUX_ARM64_SCIENCE_QUALIFICATION:** numerical comparison with
  frozen FORTRAN XSTAR 2.59g and accepted xstar-tools references.
- **0.6.91.3 — LINUX_ARM64_PACKAGING:** manylinux/aarch64 wheel creation and
  installation qualification. This milestone does not alter cibuildwheel.
- **0.6.91.4 — CROSS_PLATFORM_CLOSURE:** Linux x86-64, macOS, and Windows
  regression requalification and documentation acceptance.
- 32-bit ARM (`armhf`), piwheels, and Raspberry Pi benchmarks are out of scope.

The science revision remains **0.6.90.5.5** with exactly the same frozen
source hashes, XSTAR C API ABI **60487**, production-zone ABI **6048110**,
and existing fixed-state and XSPEC-table ABIs. Any proposed science change
must be managed separately; ARM64 build enablement is not a science refreeze.
