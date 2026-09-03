# 0.6.89.1.2 — PIP_PYTHON_CONFIG_PATH_EQUIVALENCE_CLOSURE

## Purpose

Close the macOS-only source-qualification rejection exposed after the Windows
Python-config discovery repair in `0.6.89.1.1`.

`0.6.89.1.1` is retained historically as:

- Windows MSYS2 UCRT64/AMD64: **ACCEPT**.
- macOS arm64: **REJECT** at `EXTENSIONLESS_SIBLING_DISCOVERY`.
- macOS Intel x86_64: **REJECT** at `EXTENSIONLESS_SIBLING_DISCOVERY`.
- Linux: not rerun for `.89.1.1`.

## Root cause

The production helper in `build_support.py` resolves the directory containing
the active interpreter before probing extensionless `python3-config` and
`python-config` siblings. This is intentional and remains unchanged.

The predecessor source checker created a temporary path and then required:

```python
discovered == config.as_posix()
```

On GitHub macOS a temporary directory may be represented as `/var/...`, while
`Path.resolve()` canonicalizes the same filesystem location as `/private/var/...`.
The two strings differ even though they name the same file.

## Closure

The `0.6.89.1.2` checker requires:

```python
Path(discovered).resolve() == config.resolve()
```

and independently verifies that:

- the discovered file exists;
- the returned helper path uses forward slashes;
- explicit `PYTHON_CONFIG` override still has first precedence;
- normal PATH discovery still precedes sibling fallback.

The host runner is platform-neutral and can be used unchanged on Linux, macOS
arm64, macOS x86_64, and Windows UCRT64.

## Frozen boundaries

- `build_support.py`: byte-identical to `0.6.89.1.1`.
- `src/xstar_tools/native_runtime.py`: byte-identical to `0.6.89.1.1`.
- science revision: `0.6.48.12.3.45.3.3.8`.
- public C API ABI: `60487`.
- production-zone ABI: `6048110`.
- ordinary wheels do not include `xstar-xspec-mpi`.
- `atdb.fits` remains external.
