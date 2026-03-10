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
- Same-`n` `l`-mixing for `data_type=63` / XSTAR `amcrs` is implemented as a Python port, but should still be compared against XSTAR outputs for final science.
- The level-population solver is a diagnostic prototype, not a full replacement for XSTAR.


## Scientific validation status

The table below summarizes the current scientific status of the main decoder paths.  ``Validated`` means covered by real-``atdb.fits`` tests and internal consistency checks; it does not replace comparison against full XSTAR model outputs for publication-quality work.

| Component | XSTAR data type(s) | Current status | Validation examples |
|---|---:|---|---|
| Packed FITS reader / hierarchy | pointers/reals/integers/chars | Validated | 1,216,792 records, 30 elements, 465 ions |
| Levels | 6 | Validated | O VIII and O VII level indexing and labels |
| Radiative lines | 50 | Validated | O VIII Ly-alpha, O VII triplet, Ne X, Fe XXVI checks |
| Photoionization grids | 53 | Validated for ordinary OP-style grids | O VIII and O VII ground thresholds |
| Collisions, tabulated Upsilon | 56 | Validated | O VIII Ly-alpha rates and emissivity rows |
| Collisions, Bautista n,l, nf != ni | 63 | Validated internally | O VII/O VIII direct-excitation records |
| Collisions, same-n l-mixing | 63 | Implemented and regression-tested | O VIII same-n diagnostic; compare with XSTAR for final science |
| Collisions, Burgess--Tully 5-point | 51 | Implemented and API-tested | Representative real-ATDB target tests |
| Collisions, CHIANTI 2016 BT | 98 | Implemented and API-tested | Ne IX representative target test |
| Electron recombination totals | 1, 30, 38, 39 | Implemented for total rates | Oxygen RR/DR inventory |
| Charge exchange with H0 | 2 | Implemented when explicitly requested | Low-ion oxygen CX inventory |
| True level-resolved recombination/cascades | various/unknown | Not yet identified in decoded records | Prototype source/cascade hooks only |
| Level-population solver | combined | Prototype | Connected-component and source/sink diagnostics |

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


## Collision-decoder validation tools

`xstar-atomic` includes a validation helper for collision-rate decoder development.
It can inventory ions containing selected collision data types, find representative
evaluable records, and run a type-63 same-`n` l-mixing diagnostic.

```bash
PYTHONPATH=src python -m xstar_atomic.validation ../xstar/data/atdb.fits \
  --inventory \
  --find-targets \
  --data-types 51 98 \
  --targets-csv collision_type51_98_targets.csv

PYTHONPATH=src python -m xstar_atomic.validation ../xstar/data/atdb.fits \
  --type63-same-n \
  --element O \
  --ion-stage 8 \
  --temperatures 1e6 \
  --electron-density 1.0
```

The same checks are available in `examples/07_collision_decoder_validation.py`.

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


### Flexible ion names

The high-level `XSTARAtomic` API accepts several common ion spellings:

```python
db.lines("O VIII", wavelength=(18.8, 19.1))
db.lines("o viii", wavelength=(18.8, 19.1))
db.lines("o_viii", wavelength=(18.8, 19.1))
db.lines("OVIII", wavelength=(18.8, 19.1))
db.lines("o8", wavelength=(18.8, 19.1))
```

## User guide and documentation

Full user guides are included in both Markdown and LaTeX:

```text
docs/user_guide.md
docs/user_guide.tex
```

A Sphinx documentation scaffold using the Read the Docs theme is included under:

```text
docs/sphinx/
```

Build the Sphinx HTML documentation with:

```bash
python -m pip install -e .[docs]
cd docs/sphinx
make html
```

Sphinx API pages use `sphinx.ext.autodoc`, which reads Python docstrings from modules, classes, and functions. New public functions should include docstrings so they appear correctly in the generated API reference.

### Collision decoder status

`xstar-atomic` currently evaluates the main supported collision-rate paths:

- `data_type=56`: tabulated effective collision strengths, interpolated in `log10(T/K)`.
- `data_type=63`: Bautista `n,l` algorithmic collisions, including both `n_f != n_i, |\Delta l|=1` and same-`n` l-mixing through the XSTAR `amcrs`/`velimp` branch.
- `data_type=51`: Burgess--Tully scaled collision strengths.
- `data_type=98`: CHIANTI-2016-style Burgess--Tully scaled collision strengths.

Same-`n` l-mixing depends weakly on the electron density through the impact-parameter cutoff. In the Python API, pass `electron_density_for_lmixing=...` to `collisions()` or `emissivity()` when this matters.


## Superwind/Athena++ export

Create compact CSV/JSON atomic products for selected ions:

```bash
PYTHONPATH=src python -m xstar_atomic.export ./xstar/data/atdb.fits \
  --ions "O VIII,Ne IX" \
  --temperatures 1e6 3e6 1e7 \
  --wavelength-min 1.0 --wavelength-max 30.0 \
  --out-dir atomic_export \
  --print-summary
```

The export writes levels, lines, collision records/rates, photoionization summaries, emissivity rows, and JSON manifests.

### Reading XSTAR output FITS files

Convert an XSTAR `xout_lines1.fits` file to CSV for validation against `xstar-atomic` outputs:

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs xout_lines1.fits \
  --out-csv xstar_lines.csv \
  --print-summary
```

You can also filter by ion and wavelength:

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs xout_lines1.fits \
  --ion "O VIII" --wavelength-min 18.8 --wavelength-max 19.1 \
  --out-csv xstar_o8_lya_lines.csv --print-summary
```


## XSTAR comparison validation examples

Saved O VIII Ly-alpha and O VII triplet comparisons against XSTAR `xout_lines1.fits` outputs are included under:

```text
docs/validation/xstar_outputs/
examples/reference_outputs/
```

See `docs/xstar_comparison_examples.md` for commands and interpretation. These examples validate line identification and wavelengths; absolute ratios against XSTAR `emit_inward`/`emit_outward` require model-dependent normalization.
