# CI and release engineering

The active CI policy is intentionally compact. Closed version-specific host
closure workflows are preserved in repository history rather than copied into
each release.

## Current always-on gates

`.github/workflows/ci.yml` installs the package with development dependencies,
runs generic repository/metadata policy checks, validates the frozen scientific
boundary and source concordance, then runs the current pytest regression suite.

The generic policy tools are:

- `tools/ci/check_tree_clean.py` — rejects generated build/cache artifacts;
- `tools/ci/check_package_metadata.py` — package-version/science/ABI consistency;
- `tools/ci/check_python_contract.py` — Python syntax/import/public API typing;
- `tools/ci/check_text_policy.py` — conservative text-format policy;
- `tools/qualification/check_parity_freeze.py` — exact scientific source/reference/ABI boundary;
- `tools/qualification/check_source_concordance.py` — current Fortran/Python/C++ correspondence map;
- `tools/release/check_release_candidate.py` — current release-tree boundary.

`.github/workflows/parity-freeze.yml` provides a lightweight standalone frozen
boundary check. `.github/workflows/pypi-release.yml` builds the configured
native wheel/sdist release matrix and publishes only for a matching published
GitHub release tag; manual runs build and validate without publishing. The
version is read from `pyproject.toml`; Linux ARM64 wheel checks use
`tools/release/validate_linux_arm64_wheels.py` rather than a version-locked
historical qualification script.

`.github/workflows/cross-platform-closure.yml` completed an independent five-host
CPython 3.13 native-wheel and installed-runtime regression in 0.6.91.4
(`FIVE_HOSTS=5`, `HOST_RESULT=ACCEPT`, 2026-10-08). This result is not a claim
that every CPython 3.9–3.14 release wheel was published or that a full
ARM64 real-model calculation was performed. ARM64 native physics and fixed-state
regression passed under the uniform platform-level standard. The optional
extra 0.6.91.2 full-model suite remains `REAL_MODEL_REFERENCE=NOT_RUN` pending
trusted external inputs, matching the fact that such full-model CI runs were
not required on macOS or Windows.

## Optional deeper qualification/report helpers

`tools/ci/check_science_results.py`, `require_science_assets.py`,
`report_benchmark_results.py`, and `performance_report.py` remain for controlled
scientific/performance qualification where external reference assets or
specialized runners are available. They are not historical replay gates.
