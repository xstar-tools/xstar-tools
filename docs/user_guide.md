# xstar-atomic User Guide

`xstar-atomic` is a Python package for reading, decoding, and evaluating atomic data from XSTAR's packed atomic database file, usually named `atdb.fits` and distributed under `xstar/data/atdb.fits`.

The package is designed for research workflows that need direct access to XSTAR atomic records, line lists, rate coefficients, emissivity tables, and prototype level-population calculations. It is intentionally separate from `PyXSTARdb`/`PyXstar`: `xstar-atomic` focuses on direct decoding and physics evaluation of the released packed FITS database.

## 1. What this package reads

The public XSTAR `atdb.fits` file is not a normal multi-table atomic database. It contains four packed arrays:

```text
POINTERS
REALS
INTEGERS
CHARS
```

Each physical database record is reconstructed from these arrays. The package rebuilds the XSTAR hierarchy:

```text
element -> ion -> levels -> radiative/collisional/photoionization/recombination records
```

The low-level reader is `ATDB`. The high-level user interface is `XSTARAtomic`.

## 2. Current capabilities

The package currently includes:

- Packed FITS decoding of `POINTERS`, `REALS`, `INTEGERS`, and `CHARS`.
- Element, ion, and record indexing.
- Level extraction for `data_type=6`.
- Radiative-line extraction for `data_type=50`.
- Photoionization extraction for `data_type=53` and inventory support for related bound-free records.
- Collisional excitation extraction/evaluation for:
  - `data_type=56`: tabulated effective collision strengths,
  - `data_type=63`: implemented `nf != ni`, `|Delta l| = 1` branch of the Bautista `n,l` algorithm.
- Recombination and charge-exchange inventory/evaluation for:
  - `data_type=1`: Aldrovandi & Pequignot total RR,
  - `data_type=30`: hydrogenic total RR,
  - `data_type=38`: Badnell total RR,
  - `data_type=39`: Badnell total DR,
  - `data_type=2`: charge exchange with neutral hydrogen when explicitly requested.
- Direct-excitation line-emissivity table generation.
- Prototype level-population solver with connected-component diagnostics and source/sink hooks.
- Prototype radiative-branching cascade redistribution for source-injection experiments.

## 3. Important limitations

This is an alpha-stage research package. The following limitations are important:

- Not all XSTAR data types are decoded.
- The `data_type=63` same-`n` `l`-mixing / XSTAR `amcrs` branch is not yet implemented.
- True level-resolved recombination/cascade records have not been identified in the currently decoded oxygen records.
- Recombination source redistribution modes are prototypes unless true level-resolved recombination data are available.
- The level-population solver is a diagnostic prototype, not a full replacement for XSTAR.
- Results should be validated against XSTAR outputs, published atomic values, or other atomic databases before scientific publication.

## 4. Installation

From the package directory:

```bash
python -m pip install -e .
```

For development and tests:

```bash
python -m pip install -e .[dev]
```

For Sphinx documentation:

```bash
python -m pip install -e .[docs]
```

You can also run the package without installing it:

```bash
PYTHONPATH=src python -m xstar_atomic.lines /path/to/atdb.fits \
  --element O --ion-stage 8 \
  --line-search --wavelength-min 18.8 --wavelength-max 19.1
```

## 5. Quick Python API examples

### 5.1 Open the database

```python
from xstar_atomic import XSTARAtomic, ATDB

db = XSTARAtomic("/path/to/xstar/data/atdb.fits")
```

### 5.2 Low-level database index

```python
from xstar_atomic import ATDB

atdb = ATDB("/path/to/xstar/data/atdb.fits")
records, elements, ions = atdb.build_index()
print(len(records), len(elements), len(ions))
```

For the tested XSTAR database this returns approximately:

```text
1216792 30 465
```

### 5.3 Extract O VIII Ly-alpha lines

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic("/path/to/xstar/data/atdb.fits")
lines = db.lines("O VIII", wavelength=(18.8, 19.1), slim=True)

for line in lines:
    print(line["wavelength_A"], line["lower_label"], "->", line["upper_label"])
```

Equivalent ion-name forms are accepted:

```python
db.lines("O VIII")
db.lines("o viii")
db.lines("o_viii")
db.lines("O-VIII")
db.lines("OVIII")
db.lines("o8")
```

### 5.4 Evaluate collisional excitation rates

```python
coll = db.collisions(
    "O VIII",
    lower_level=1,
    wavelength=(18.8, 19.1),
    temperatures=[1e6, 3e6, 1e7],
)

print(coll.keys())
print(len(coll["summary"]), len(coll["evaluated"]))
```

The `evaluated` rows include quantities such as:

```text
upsilon
q_excitation_cm3_s
q_deexcitation_cm3_s
eval_method
```

### 5.5 Recombination inventory

```python
recomb = db.recombination(element="O", temperatures=[1e6])
print(len(recomb["records"]))
print(len(recomb["evaluated"]))
```

Electron recombination and charge exchange are separated by `source_kind`:

```text
electron_recombination
charge_exchange_H0
```

### 5.6 Build an O VIII Ly-alpha emissivity table

```python
emiss = db.emissivity(
    "O VIII",
    wavelength=(18.8, 19.1),
    temperatures=[1e6, 3e6, 1e7],
)

print(emiss["summary"])
print(emiss["emissivity"][0])
```

The emissivity table reports direct-excitation coefficients approximately of the form:

```text
line_photon_emissivity_coeff_cm3_s = q_ij(T) * branching_ratio
line_energy_emissivity_coeff_erg_cm3_s = q_ij(T) * branching_ratio * photon_energy
```

These coefficients are per `n_e n_ion`.

## 6. Command-line interface

After installation, the package provides these commands:

```text
xstar-atomic-inspect
xstar-atomic-hierarchy
xstar-atomic-lines
xstar-atomic-photoionization
xstar-atomic-collisions
xstar-atomic-recombination
xstar-atomic-emissivity
xstar-atomic-solver
```

### 6.1 Inspect the database

```bash
xstar-atomic-inspect /path/to/atdb.fits --summary
```

### 6.2 Search for O VIII Ly-alpha lines

```bash
xstar-atomic-lines /path/to/atdb.fits \
  --element O --ion-stage 8 \
  --line-search --wavelength-min 18.8 --wavelength-max 19.1
```

### 6.3 Evaluate collisions

```bash
xstar-atomic-collisions /path/to/atdb.fits \
  --element O --ion-stage 8 \
  --search --lower-level 1 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7
```

### 6.4 Build an emissivity CSV

```bash
xstar-atomic-emissivity /path/to/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7 \
  --out-csv o8_lya_emissivity.csv \
  --print-summary
```

### 6.5 Recombination inventory

```bash
xstar-atomic-recombination /path/to/atdb.fits \
  --element O \
  --temperatures 1e6 \
  --summary
```

### 6.6 Prototype solver

```bash
xstar-atomic-solver /path/to/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 3e6 1e7 \
  --electron-densities 1.0 \
  --component-mode ground \
  --out-lines-csv o8_lya_pop_lines.csv \
  --print-summary
```

## 7. Testing

The test suite contains lightweight package tests and optional real-database smoke tests. To run tests that require the real XSTAR database:

```bash
XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits PYTHONPATH=src pytest -q
```

Without `XSTAR_ATDB_FITS`, tests requiring `atdb.fits` are skipped.

## 8. Examples

The `examples/` directory contains runnable scripts:

```text
01_o8_lya_lines.py
02_o8_lya_collisions.py
03_o8_lya_emissivity.py
04_oxygen_recombination_inventory.py
05_low_level_atdb_index.py
06_high_level_api_quickstart.py
```

Run them without installing by setting `PYTHONPATH`:

```bash
PYTHONPATH=src python examples/06_high_level_api_quickstart.py /path/to/atdb.fits
```

## 9. Sphinx documentation

The package includes a Sphinx documentation scaffold under:

```text
docs/sphinx/
```

Build HTML documentation with:

```bash
python -m pip install -e .[docs]
cd docs/sphinx
make html
```

The generated HTML will be under:

```text
docs/sphinx/build/html/
```

The Sphinx API pages use `sphinx.ext.autodoc`, which reads Python docstrings from modules, classes, and functions. New public functions should therefore include clear docstrings in the code.

## 10. Development notes

Recommended near-term development priorities:

1. Complete missing rate decoders, especially collision `data_type=51`, `98`, and the same-`n` branch of `data_type=63`.
2. Continue searching for true level-resolved recombination/cascade records or implement an external cascade model.
3. Add sparse-matrix support to the level-population solver.
4. Validate line rates and emissivities against XSTAR output, AtomDB/APEC where applicable, and published benchmarks.
5. Add more tests for Fe K, Fe UTA, Ne X, Mg XII, and Si XIV workflows.


## Collision decoder coverage

The collision module evaluates the following XSTAR ATDB collision paths:

| data_type | Meaning | Status |
|---:|---|---|
| 51 | Burgess--Tully scaled OP/CHIANTI collision strengths | evaluated |
| 56 | tabulated effective collision strengths | evaluated |
| 63 | Bautista algorithmic `n,l` collisions | evaluated for `n_f != n_i, |\Delta l|=1` and same-`n` l-mixing |
| 98 | CHIANTI-2016-style Burgess--Tully scaled collision strengths | evaluated |

Same-`n` type-63 l-mixing follows the XSTAR `amcrs`/`velimp` ecm=0 branch. Because this branch uses an impact-parameter cutoff, provide `electron_density_for_lmixing` when calling the high-level API if the default `1 cm^-3` is not appropriate.

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic("xstar/data/atdb.fits")
rates = db.collisions(
    "O VIII",
    data_type=63,
    temperatures=[1e6],
    electron_density_for_lmixing=1.0,
)
```
