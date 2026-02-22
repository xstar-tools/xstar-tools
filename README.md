# xstar-atomic

`xstar-atomic` is an early research Python package for direct access to XSTAR's packed atomic database FITS file, usually:

```text
xstar/data/atdb.fits
```

Unlike ordinary FITS atomic databases, `atdb.fits` is organized as four packed arrays:

```text
POINTERS, REALS, INTEGERS, CHARS
```

This package decodes those arrays, reconstructs the element/ion/level/process hierarchy, and provides first-pass physics extractors and emissivity tools.

## Current status

This is an alpha/development package created by refactoring validated standalone scripts. The following pieces are working or partially working:

- Packed FITS record decoding.
- Element, ion, and level hierarchy reconstruction.
- Level decoder for XSTAR `data_type=6`.
- Radiative line decoder for `data_type=50`.
- Photoionization cross-section decoder for `data_type=53`.
- Collisional excitation decoders:
  - `data_type=56` tabulated effective collision strengths.
  - `data_type=63` Bautista `n,l` algorithmic branch for `nf != ni` and `|Δl| = 1`.
- Recombination / charge-exchange extractors:
  - `data_type=1`, `30`, `38`, `39` electron recombination total rates.
  - `data_type=2` charge exchange with neutral H when explicitly requested.
- Direct emissivity-table builder.
- Prototype level-population solver with connected-component diagnostics and source/sink hooks.
- Prototype cascade source redistribution using radiative branching.

Important limitations:

- Not all XSTAR data types are decoded.
- True level-resolved recombination/cascade records have not been found in the currently decoded oxygen records.
- Same-`n` `l`-mixing for `data_type=63` / XSTAR `amcrs` is not yet implemented.
- The level-population solver is a diagnostic prototype, not a full replacement for XSTAR.

## Installation

From the package directory:

```bash
python -m pip install -e .
```

## Command-line tools

After installation, these commands are available:

```bash
xstar-atomic-inspect
xstar-atomic-hierarchy
xstar-atomic-lines
xstar-atomic-photoionization
xstar-atomic-collisions
xstar-atomic-recombination
xstar-atomic-emissivity
xstar-atomic-solver
```

## Examples

Inspect the packed database:

```bash
xstar-atomic-inspect ./xstar/data/atdb.fits --summary
```

Extract O VIII Ly-alpha lines:

```bash
xstar-atomic-lines ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --line-search --wavelength-min 18.8 --wavelength-max 19.1
```

Evaluate O VIII Ly-alpha collisional excitation:

```bash
xstar-atomic-collisions ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --search --lower-level 1 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7
```

Build an O VIII Ly-alpha emissivity table:

```bash
xstar-atomic-emissivity ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7 \
  --out-csv o8_lya_emissivity.csv --print-summary
```

Run the prototype level-population solver on the ground-connected component:

```bash
xstar-atomic-solver ./xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7 \
  --electron-densities 1.0 \
  --component-mode ground \
  --out-lines-csv o8_lya_pop_lines.csv --print-summary
```

## Python API example

```python
from xstar_atomic import ATDB

atdb = ATDB("./xstar/data/atdb.fits")
records, elements, ions = atdb.build_index()
print(len(records), len(elements), len(ions))
```

High-level convenience API:

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic("./xstar/data/atdb.fits")

# Reuses the same validated decoders as the command-line tools.
lya = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)
coll = db.collisions("O VIII", lower_level=1, wavelength=(18.8, 19.1), temperatures=[1e6, 3e6, 1e7])
emiss = db.emissivity("O VIII", wavelength=(18.8, 19.1), temperatures=[1e6, 3e6, 1e7])
recomb = db.recombination(element="O", temperatures=[1e6])

print(len(lya))
print(emiss["summary"])
```

The low-level `ATDB` API remains available for direct packed-FITS access, while `XSTARAtomic` is the recommended science-facing wrapper for rates, emissivities, and solver-related workflows.

## Testing

Run metadata/layout tests without the XSTAR database:

```bash
pytest -q
```

Run the real `atdb.fits` smoke tests by setting `XSTAR_ATDB_FITS`:

```bash
XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits pytest -q
```

The ATDB-dependent tests validate the same O VIII/O VII workflows used during development, including O VIII Ly-alpha lines, collisions, emissivity, and oxygen recombination inventory.

## Example scripts

The `examples/` directory contains runnable scripts that work without installing the package when `PYTHONPATH=src` is set:

```bash
PYTHONPATH=src python examples/01_o8_lya_lines.py /path/to/xstar/data/atdb.fits
PYTHONPATH=src python examples/02_o8_lya_collisions.py /path/to/xstar/data/atdb.fits
PYTHONPATH=src python examples/03_o8_lya_emissivity.py /path/to/xstar/data/atdb.fits
PYTHONPATH=src python examples/04_oxygen_recombination_inventory.py /path/to/xstar/data/atdb.fits
PYTHONPATH=src python examples/05_low_level_atdb_index.py /path/to/xstar/data/atdb.fits
```

## Changelog

See `CHANGELOG.md`.

## Development roadmap

See `docs/TODO.md`.
