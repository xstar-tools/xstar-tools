# 0.6.91.5 — CONDA_FORGE_LINUX_ARM64_ENABLEMENT

**Status: ACCEPTED and closed (2026-10-09).**

This milestone adds **public conda-forge Linux AArch64 (`linux-aarch64`) distribution** without modifying the frozen science implementation, accepted numerical tolerances, or native ABI contracts.

## Public conda-forge acceptance evidence

The separate [xstar-tools-feedstock](https://github.com/conda-forge/xstar-tools-feedstock) enabled:

```yaml
provider:
  osx_arm64: azure
  linux_aarch64: default
```

The rerender in [feedstock PR #6](https://github.com/conda-forge/xstar-tools-feedstock/pull/6) generated Linux AArch64 build jobs and the feedstock CI passed. Public-channel availability was independently confirmed with:

```bash
conda search --override-channels -c conda-forge --subdir linux-aarch64 xstar-tools
```

On 2026-10-09, the channel reported **xstar-tools 0.6.90.5.8** for Python 3.11, 3.12, 3.13, 3.14, and 3.15 (five published builds, build number 0). This is the evidence for accepting **Linux ARM64 architecture enablement**. It does not mean the newer 0.6.91.5 source release has been published to conda-forge.

To install using an ARM64 Linux conda environment:

```bash
conda install --override-channels -c conda-forge xstar-tools
xstar-cpp --version
xstar-xspec --version
xstar-tools doctor --require zone-cpp --json
```

## Optional source-repository qualification

The repository retains `.github/workflows/conda-linux-aarch64.yml`. This job builds a local source distribution on native `ubuntu-24.04-arm`, runs `rattler-build` for `linux-aarch64` using the conda-forge CFITSIO dependency, installs the resulting package in a clean environment, and checks:

- science-source hashes and both public ABI contracts;
- ELF64/AArch64 executables and shared libraries;
- use of conda-managed `cfitsio`, not vendored CFITSIO;
- absence of the external atomic database (`atdb.fits`);
- Python imports, version commands and native backend discovery.

Successful optional evidence reports `CONDA_LINUX_ARM64_06915_HOST_RESULT=ACCEPT`. This standalone workflow **does not need to run to accept the published conda-forge platform**; the separate feedstock CI and confirmed public availability provide that evidence.

## Feedstock recipe updates

The feedstock and the source repository are distinct. `conda/feedstock-linux-aarch64/conda-forge.yml` is retained as a historical configuration example, not an automatically applied feedstock setting. Source-version updates must use a genuinely published PyPI source distribution with its verified SHA-256. A new source version is not automatically available through conda-forge solely because ARM64 platform support is enabled.

For maintainers preparing a subsequent recipe update, the existing helper accepts an actual published source archive:

```bash
python -B tools/packaging/prepare_conda_linux_aarch64.py \
  --package "$PWD" \
  --sdist /path/to/published/xstar_tools-VERSION.tar.gz \
  --mode feedstock \
  --published-sha256 THE_ACTUAL_PYPI_SHA256 \
  --output-recipe /tmp/conda-feedstock-recipe \
  --feedstock-config /path/to/xstar-tools-feedstock/conda-forge.yml \
  --output-feedstock-config /tmp/xstar-conda-forge.yml
```

## Scientific and packaging boundary

This is a **distribution-platform closure**, not a new full-model science result. `atdb.fits` remains external, CFITSIO is supplied by conda-forge, the normal package excludes MPI, and Windows conda packaging remains unsupported. The accepted scientific revision is **0.6.90.5.5**, with C API ABI **60487** and production-zone ABI **6048110**. No scientific source files or numerical acceptance criteria changed.
