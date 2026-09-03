# 0.6.89.1.3 — PIP_SOURCE_LINE_ENDING_EQUIVALENCE_CLOSURE

## Scope

Qualification-only closure on `0.6.89.1.2` apart from normal package-version metadata.

`0.6.89.1.2` is preserved as:

- Linux GCC x86_64: ACCEPT
- macOS arm64: ACCEPT
- macOS Intel x86_64: ACCEPT
- Windows MSYS2 UCRT64/AMD64: REJECT at `PIP_PYTHON_CONFIG_PATH_EQUIVALENCE_CLOSURE_068912_BUILD_SUPPORT_BYTE_IDENTICAL`

The Windows rejection occurred before native wheel construction. The same packaging implementation had already built successfully on Windows in `0.6.89.1.1`.

## Root cause

The `.89.1.2` source checker compared raw SHA-256 bytes for `build_support.py` and `src/xstar_tools/native_runtime.py` against canonical LF hashes. Windows Git checkout may materialize ordinary text files with CRLF line endings. The source semantics therefore remained unchanged while the raw byte hash changed.

## Closure

`0.6.89.1.3` normalizes `CRLF` and lone `CR` to `LF` for these qualification-only text hashes. The accepted canonical LF SHA-256 values remain unchanged:

- `build_support.py`: `93fbfcb4987def93853daa1a22c67077f0cc8b6a13b28f2f8d50baf4b546b3f8`
- `src/xstar_tools/native_runtime.py`: `c764699e128f7c0c457124001d26ddafa587859a7e737c417d2b117998ea3bd1`

The checker also creates synthetic CRLF copies and requires them to normalize to those same hashes.

The host runner writes `host_context.json` before source qualification so an early rejection still leaves an uploadable diagnostic artifact.

## Frozen boundaries

No change to:

- scientific implementation or science freeze `0.6.48.12.3.45.3.3.8`;
- public C API ABI `60487`;
- production-zone ABI `6048110`;
- native artifact set;
- ordinary-wheel MPI exclusion;
- external `atdb.fits` policy;
- `build_support.py` implementation logic;
- `src/xstar_tools/native_runtime.py` implementation logic.
