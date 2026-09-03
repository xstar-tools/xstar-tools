# 0.6.89.2.2 — PYPI_LINUX_PROFILE_BUILD_TARGET_CLOSURE

`0.6.89.2.2` closes the first actual manylinux build failure observed in the `0.6.89.2.1` six-selector GitHub Actions run.

The predecessor correctly defined a `pypi-linux` **artifact** profile that excluded `libxstar_backend_python.so`, but `build_support.py` still invoked `make all`. The ordinary `all` target intentionally contains the standalone Python-embedding plugin. In the manylinux CPython 3.9 build, `python3-config --embed --ldflags` requested `-lpython3.9`, while the manylinux interpreter did not provide a linkable `libpython3.9.so`; the native wheel therefore failed before auditwheel.

The closure keeps ordinary/source behavior unchanged and adds a packaging-only Makefile target:

```text
pypi-linux
```

It contains all normal physics/runtime libraries, `libxstar_api`, `libxstar_backend_cpp`, `xstar_cpp`, `xstar-cpp`, `xstar-xspec-initable`, `xstar-xspec-table`, and `xstar-xspec`, but does not build `libxstar_backend_python` or MPI. `build_support.py` maps the `full` profile to `make all` and the `pypi-linux` profile to `make pypi-linux`.

No scientific kernel, traversal order, accumulation order, ABI, atomic-data policy, or MPI policy changes in this closure.

Acceptance requires all six cibuildwheel selectors (`cp39` through `cp314`) to build, repair, install, smoke-test, and pass repaired-wheel artifact inspection.
