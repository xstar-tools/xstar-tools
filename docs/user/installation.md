# Installation

## Python package

Milestone 8 will formalize wheel/native packaging. For the current source release:

```bash
python -m pip install .
```

For an editable development checkout:

```bash
python -m pip install -e '.[dev]'
```

Python dependencies are declared in `pyproject.toml` and include NumPy and Astropy.

## Documentation dependencies

```bash
python -m pip install -e '.[docs]'
```

## Native C++ runtime

`pure-python` needs no C++ runtime. Build the native libraries and standalone executable for the C++ modes:

```bash
make -C src/xstar_tools/xstar/cpp -j2
```

The build requires C++17 and CFITSIO. On GNU/libstdc++ systems, `FILESYSTEM_LIBS` defaults to `-lstdc++fs` for compatibility with toolchains that still need a separate filesystem compatibility library.

## Verify the environment

```bash
xstar-tools version
xstar-tools backends
xstar-tools doctor
```

For a specific mode:

```bash
xstar-tools doctor --require zone-cpp
```
