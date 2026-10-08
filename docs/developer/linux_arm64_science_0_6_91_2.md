# 0.6.91.2 — LINUX_ARM64_SCIENCE_QUALIFICATION

This milestone extends the **accepted** native Linux ARM64 compilation/linking
closure (0.6.91.1) to scientific regression verification. It introduces **no**
scientific algorithm, frozen C++ science file, atomic indexing, or ABI changes.
The accepted science revision remains **0.6.90.5.5** (including the Mn/Type-49
source early exit).

## Two separate evidence tiers

1. **Always runnable on Linux aarch64:** six native C++ physical-kernel
   self-tests (including spectral contributions, thermal heating/cooling,
   convergence), fixed-state/batch self-tests, and a native fixed-state
   replay. Generated STEP, visited-record inventory and FITS values are
   compared with the retained `0.6.88.6.1` frozen cross-platform reference.
   Discrete identities must match exactly. Cross-host floats are compared
   numerically, not through raw binary hashes. The reference is an **ABI 60486
   synthetic scaffold**, not an astrophysical production benchmark.
2. **Mandatory for formal scientific host acceptance:** full, real atomic-data
   XSTAR runs for at least one single-element case and one multi-element case
   with `mnabund=1`. Inputs, `atdb.fits`, `coheat.dat`, and the preexisting
   FORTRAN/accepted C++ reference outputs must all be SHA-256 pinned and
   independently produced before the ARM64 run. The case outputs must include
   `xout_step.log`, `xout_abund1.fits`, `xout_spect1.fits`, and `xout_cont1.fits`.
   The unchanged source STEP science comparator and strict normalized-L1
   FITS data comparison are applied. Absent external science assets cause
   `HOST_RESULT=NOT_RUN`, **not** an artificial acceptance.

The release archive deliberately does **not** include `atdb.fits`, full
reference spectra, or FORTRAN benchmark artifacts. No scientific reference is
regenerated on ARM64 to establish a new baseline.

## Run on native GitHub ARM64

Push the source package to the branch; open Actions ->
**Linux ARM64 science qualification 0.6.91.2** -> **Run workflow**.
The workflow uses `ubuntu-24.04-arm`, GCC, Python 3.13, Astropy and CFITSIO.
Without external assets it runs Tier 1 and uploads its evidence but the
workflow **does not pass**: the result is `HOST_RESULT=NOT_RUN`, which is
insufficient for full scientific host acceptance. A native runner returning
0 is not itself an ACCEPT result:
read `LINUX_ARM64_SCIENCE_06912_HOST_RESULT`.

To enable Tier 2, prepare one `tar.gz` archive containing the following tree:

```text
manifest.json
 data/
   atdb.fits
   coheat.dat
 cases/
   mg11_ne1e8/
     xstar.par
     reference/xout_step.log
     reference/xout_abund1.fits
     reference/xout_spect1.fits
     reference/xout_cont1.fits
   all_elements_mn/
     xstar.par
     reference/xout_step.log
     reference/xout_abund1.fits
     reference/xout_spect1.fits
     reference/xout_cont1.fits
```

Use the template
`qualification/linux_arm64_science_0_6_91_2/reference_manifest.example.json`.
Replace **every** placeholder digest with the actual SHA-256 of that file.
For the Mn case explicitly set `mnabund=1` in `xstar.par` (or the standard
comma-separated XSTAR parameter format), and use a reference already produced
on an accepted platform. Never derive or update the golden product from the
ARM64 output. The source tree does not attempt to interpret an arbitrary
unverified benchmark archive as an accepted reference.

Upload the archive to a controlled HTTPS endpoint and configure the repository
Actions secrets:

- `ARM64_SCIENCE_ASSET_URL`: HTTPS URL to the prepared archive
- `ARM64_SCIENCE_ASSET_SHA256`: exact digest of the **archive** itself

For a private URL requiring an authentication header, stage the files on a
self-hosted runner instead; the provided workflow's `curl` expects a URL
already accessible to the GitHub runner. The downloaded archive is checksum
verified before extraction, and each file is checked again against the
manifest. Do not place private atomic data in the public repository.

Alternatively, on a native aarch64 host where the bundle is already present:

```bash
python -B tools/qualification/run_linux_arm64_science_host_0_6_91_2.py \
  --package "$PWD" \
  --output-root /tmp/linux_arm64_science_06912 \
  --jobs 2 \
  --data-dir /path/to/science-suite/data \
  --science-cases /path/to/science-suite
```

**Science-gate policy:** exact discrete record identities; numerical frozen
scaffold comparison with `rel_tol=1e-10`, no float32/raw FITS digest
requirements; required real-model FITS fields with normalized L1 strictly
below 0.01 and zero-baseline protection; frozen STEP comparator unchanged.
These are technical gate definitions, not new or loosened scientific source
acceptance criteria. Case provenance and numerical results must be reviewed
before formal acceptance. MPI and ARM32 remain out of scope.

## Expected status labels

```text
LINUX_ARM64_SCIENCE_06912_FREEZE=ACCEPT
LINUX_ARM64_SCIENCE_06912_NATIVE_BUILD=ACCEPT
LINUX_ARM64_SCIENCE_06912_FIXED_STATE_REFERENCE=ACCEPT
LINUX_ARM64_SCIENCE_06912_NATIVE_PHYSICS_TESTS=ACCEPT
LINUX_ARM64_SCIENCE_06912_REAL_MODEL_REFERENCE=NOT_RUN  # without suite
LINUX_ARM64_SCIENCE_06912_HOST_RESULT=NOT_RUN
```

Full acceptance requires the last two labels to be `ACCEPT`, together with
unchanged science hashes and checked external reference provenance. Logs and
`result.json` are uploaded even on rejected GitHub Actions runs.

## 0.6.91.2.1 — CI test harness closure (2026-10-08)

The native ARM64 0.6.91.2 evidence established `FREEZE=ACCEPT`,
`NATIVE_BUILD=ACCEPT`, `FIXED_STATE_REFERENCE=ACCEPT`, and
`NATIVE_PHYSICS_TESTS=ACCEPT`. Because neither `ARM64_SCIENCE_ASSET_URL` nor
`ARM64_SCIENCE_ASSET_SHA256` was configured, `REAL_MODEL_REFERENCE=NOT_RUN`
and `HOST_RESULT=NOT_RUN` are **correct**. The full-science acceptance gate
is intentionally still mandatory.

Independently, Python CI raised test-only failures that are repaired in
0.6.91.2.1:

1. `test_generated_python_caches_are_absent` now checks tracked files using
   `git ls-files`; `pytest` itself may create untracked cache directories.
   In a source archive without a `.git` index, this particular tracked-file
   test is skipped (source cleanliness is enforced during packaging).
2. The IEEE FITS comparator unit test now constructs a tiny strided FITS
   binary table rather than reading `xout_cont1.fits` from a historical
   reference directory that contains only CSV/JSON scientific products.
   This synthetic table tests the comparator only; it is **not** a science
   baseline, cannot contribute to the `REAL_MODEL_REFERENCE` gate, and never
   changes an accepted reference.
3. `setuptools>=77` is explicitly installed in development and CI environments
   because Python 3.13 does not guarantee it is preinstalled in the test
   interpreter. The existing `build_support.py` still imports it normally.

To run the tests locally, ensure the development dependencies are installed
and disable unnecessary Python bytecode output:

```bash
python -m pip install -e '.[dev]'
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=./src python -m pytest -p no:cacheprovider -q
```

The repository can only complete ARM64 scientific host acceptance after a
real-model reference bundle with checked provenance is supplied. No source
modification, pytest skip, or new synthetic reference can replace that
requirement. The two GitHub Actions secrets must be configured together and
must identify an accessible immutable archive and its SHA-256 digest.
