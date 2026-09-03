# 0.6.89.2.1 — PYPI_NATIVE_WHEEL_LINUX_PREFLIGHT_DEPENDENCY_CLOSURE

`0.6.89.2.1` is a qualification/workflow closure on the `0.6.89.2` Linux PyPI native-wheel candidate.

## Predecessor result

All six `0.6.89.2` GitHub Actions selectors rejected before cibuildwheel started. The source checker loaded `build_support.py`, whose build-hook implementation imports setuptools, but the fresh `actions/setup-python` qualification interpreter had not installed the project's PEP 517 build-system requirements. The observed failure was:

```text
ModuleNotFoundError: No module named 'setuptools'
```

This was a release-workflow preflight dependency-ordering defect, not a C++ build, auditwheel, ABI, or science failure.

## Closure

The workflow now installs the requirements already declared by `[build-system]` before source qualification:

```bash
python -m pip install --upgrade "setuptools>=77" wheel
```

The new source checker also reports a missing setuptools installation as an explicit `SETUPTOOLS_AVAILABLE=REJECT` gate instead of exposing an uncaught traceback.

## Frozen production contract

The following implementation is retained from `0.6.89.2`:

- `build_support.py`;
- `src/xstar_tools/native_runtime.py`;
- the `pypi-linux` native artifact profile;
- `manylinux_2_28_x86_64` policy;
- cibuildwheel 4.2.1;
- pinned CFITSIO 4.6.2 source build and SHA-256;
- auditwheel repair;
- CPython 3.9 through 3.14 selectors;
- exclusion of `libxstar_backend_python.so` only from the PyPI Linux profile;
- exclusion of MPI from ordinary wheels;
- external `atdb.fits` policy;
- science revision `0.6.48.12.3.45.3.3.8`;
- C API ABI `60487` and production-zone ABI `6048110`.

Package-version metadata and qualification/smoke markers advance to `0.6.89.2.1`.

## GitHub acceptance

Run **PyPI native Linux wheels**. Every selector must reach both the repaired-wheel smoke and artifact checks and end with:

```text
PYPI_NATIVE_WHEEL_LINUX_PREFLIGHT_DEPENDENCY_CLOSURE_068921_SMOKE_RESULT=ACCEPT
PYPI_NATIVE_WHEEL_LINUX_PREFLIGHT_DEPENDENCY_CLOSURE_068921_ARTIFACT_RESULT=ACCEPT
PYPI_NATIVE_WHEEL_LINUX_PREFLIGHT_DEPENDENCY_CLOSURE_068921_GITHUB_JOB_RESULT=ACCEPT
```

Only those six completed jobs close the Linux PyPI wheel milestone.
