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
  - `data_type=51`: Burgess--Tully 5-point collision strengths,
  - `data_type=56`: tabulated effective collision strengths,
  - `data_type=63`: implemented `nf != ni`, `|Delta l| = 1` branch and same-`n` l-mixing branch of the Bautista/XSTAR algorithm,
  - `data_type=98`: CHIANTI-2016-style Burgess--Tully collision strengths.
- Recombination and charge-exchange inventory/evaluation for:
  - `data_type=1`: Aldrovandi & Pequignot total RR,
  - `data_type=30`: hydrogenic total RR,
  - `data_type=38`: Badnell total RR,
  - `data_type=39`: Badnell total DR,
  - `data_type=2`: charge exchange with neutral hydrogen when explicitly requested.
- Direct-excitation line-emissivity table generation.
- CSV/HDF5 export bundles for plasma post-processing workflows.
- Line-based X-ray band emissivity exports via `--bands-kev`.
- Prototype level-population solver with connected-component diagnostics and source/sink hooks.
- Prototype radiative-branching cascade redistribution for source-injection experiments.


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

## 3. Important limitations

This is an alpha-stage research package. The following limitations are important:

- Not all XSTAR data types are decoded.
- The `data_type=63` same-`n` `l`-mixing / XSTAR `amcrs` branch is implemented in the collision decoder, but should still be compared against XSTAR outputs for final science.
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
  --electron-density-for-lmixing 1.0 \
  --component-mode ground \
  --linear-solver sparse \
  --out-lines-csv o8_lya_pop_lines.csv \
  --print-summary
```

Use `--linear-solver dense`, `--linear-solver sparse`, or `--linear-solver auto`.  The sparse solver uses `scipy.sparse.linalg.spsolve` when SciPy is available and falls back to dense least-squares if needed.

### 6.7 Plasma export bundles

```bash
xstar-atomic-export /path/to/atdb.fits \
  --ions "O VIII,Ne IX" \
  --temperatures 1e6 3e6 1e7 \
  --wavelength-min 1.0 --wavelength-max 40.0 \
  --formats csv,hdf5 \
  --out-dir atomic_export \
  --print-summary
```

This writes per-ion CSV products, optional HDF5 tables, and JSON manifests.  The export is intended for superwind, AGN outflow, and other plasma post-processing workflows.

### 6.8 X-ray band emissivity exports

Line-by-line emissivity tables are useful for detailed diagnostics, but post-processing of simulated outflows often needs integrated X-ray bands.  The export command supports line-based band sums with `--bands-kev`, using band specifications of the form `name:emin:emax` in keV.

```bash
PYTHONPATH=src python -m xstar_atomic.export /path/to/atdb.fits \
  --ions "O VIII,Ne IX" \
  --temperatures 1e6 3e6 1e7 \
  --wavelength-min 1.0 \
  --wavelength-max 40.0 \
  --bands-kev soft:0.5:2.0 osoft:0.3:0.6 med:0.6:1.0 hard:2.0:10.0 \
  --formats csv,hdf5 \
  --out-dir atomic_export \
  --print-summary
```

For each ion this writes:

```text
<ion>_band_emissivity.csv
<ion>_atomic.h5:/band_emissivity
```

The band-emissivity table contains:

```text
ion
band_name
energy_min_keV
energy_max_keV
temperature_K
n_lines_in_band
energy_emissivity_coeff_erg_cm3_s
photon_emissivity_coeff_cm3_s
methods_used
```

The coefficients are local line-emissivity coefficients per `n_e n_ion`, summed over the selected lines in each band.  They are not full plasma cooling functions unless combined with ion fractions and abundances.  Zero-line bands are retained with `n_lines_in_band=0`, `methods_used="none"`, and the ion label filled.

A validated Stage-4 test used four bands and three temperatures for O VIII and Ne IX, giving:

```text
4 bands × 3 temperatures = 12 band-emissivity rows per ion
```

The real-ATDB validation confirmed that CSV and HDF5 products contain `/band_emissivity`, that all zero-line bands keep the ion label, and that no `methods_used` entries are blank.

## 7. Testing

The test suite contains lightweight package tests and optional real-database smoke tests. To run tests that require the real XSTAR database:

```bash
XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits PYTHONPATH=src pytest -q
```

Without `XSTAR_ATDB_FITS`, tests requiring `atdb.fits` are skipped.  The v0.2.17 Stage-4 validation run passed 34 real-ATDB tests:

```text
34 passed in 113.49s
```

## 8. Examples

The `examples/` directory contains runnable scripts:

```text
01_o8_lya_lines.py
02_o8_lya_collisions.py
03_o8_lya_emissivity.py
04_oxygen_recombination_inventory.py
05_low_level_atdb_index.py
06_high_level_api_quickstart.py
07_collision_decoder_validation.py
08_compare_xstar_outputs.py
09_export_band_emissivity.py
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


## Collision-decoder validation

The package includes a validation helper for the currently difficult collision
rate decoders: type 51, type 98, and the same-`n` branch of type 63.  The helper
can inventory ATDB records, find representative ions with positive evaluated
rate coefficients, and run regression diagnostics for O VIII type-63 l-mixing.

```bash
PYTHONPATH=src python -m xstar_atomic.validation atdb.fits \
  --inventory --find-targets --data-types 51 98

PYTHONPATH=src python -m xstar_atomic.validation atdb.fits \
  --type63-same-n --element O --ion-stage 8 \
  --temperatures 1e6 --electron-density 1.0
```

The type-63 same-`n` diagnostic is a regression check of the Python port of the
XSTAR `amcrs/velimp` branch.  It should still be compared against XSTAR model
outputs before production use.

## XSTAR-output comparison validation examples

Saved XSTAR-vs-`xstar-atomic` comparison outputs are included under:

```text
docs/validation/xstar_outputs/
examples/reference_outputs/
```

These files document wavelength comparisons produced from XSTAR `xout_lines1.fits` output converted with `xstar_atomic.xstar_outputs` and compared with `examples/08_compare_xstar_outputs.py`.

### Included validation artifacts

| File | Purpose |
|---|---|
| `compare_o8_lya_wavelength.csv/json` | O VIII Ly-alpha wavelength and transition-ID validation |
| `compare_o8_lya_both.csv/json` | O VIII Ly-alpha wavelength plus emissivity-ratio diagnostics |
| `compare_o7_triplet_wavelength.csv/json` | O VII triplet/near-triplet wavelength and transition-ID validation |

### Main results

- O VIII Ly-alpha wavelengths agree with XSTAR to approximately `1e-5` Angstrom.
- O VII triplet/near-triplet wavelengths agree with XSTAR to approximately `1e-7`--`8e-7` Angstrom.
- O VII triplet rows are expected to show `no_matched_collision` in the direct-emissivity join; XSTAR emits them through its full plasma model, including population, recombination, cascade, and radiative-transfer physics.

### Reproduce a comparison

```bash
PYTHONPATH=src python -m xstar_atomic.xstar_outputs \
  xout_lines1.fits \
  --out-csv xstar_lines.csv \
  --print-summary

PYTHONPATH=src python examples/08_compare_xstar_outputs.py \
  /path/to/atdb.fits \
  xstar_lines.csv \
  --ion "O VIII" \
  --wavelength-column wavelength \
  --reference-column emit_outward \
  --mode wavelength \
  --temperature 1e6 \
  --wavelength-tolerance 0.02 \
  --out-csv compare_lines.csv \
  --out-json compare_lines.json
```

Use wavelength mode for database/line-identification validation. Absolute comparison of `xstar-atomic` local emissivity coefficients against XSTAR `emit_outward` requires a model-dependent normalization involving ion fractions, density, column, geometry, and radiative transfer.

## Stage-3 sparse level-population solver diagnostics

The level-population solver supports the XSTAR type-63 same-`n` l-mixing
collision decoder and can solve the statistical-equilibrium matrix with a dense
or sparse backend:

```bash
PYTHONPATH=src python -m xstar_atomic.solver ../xstar/data/atdb.fits \
  --element O \
  --ion-stage 8 \
  --wavelength-min 18.8 \
  --wavelength-max 19.1 \
  --temperatures 1e6 \
  --electron-densities 1.0 \
  --electron-density-for-lmixing 1.0 \
  --component-mode ground \
  --linear-solver sparse \
  --summary-json o8_sparse_solver_summary.json \
  --print-summary
```

Solver summaries now report matrix nonzero counts, matrix density, singular-value
rank estimates, condition numbers, residual norms, sparse availability, and
whether sparse solving was actually used.  The optional
`--prune-unconnected-levels` flag removes isolated levels before the solve while
preserving the ground level, output-line levels, and explicit source/sink levels.

For O VII triplet stress tests, use:

```bash
PYTHONPATH=src python examples/10_o7_triplet_sparse_solver.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_triplet_solver_example
```

This example writes an O VII triplet diagnostic table containing prototype
`R=f/i` and `G=(f+i)/r` ratios.  These ratios are useful for solver debugging,
but they are not final physical predictions unless the source/cascade model is
physically complete.

## Solver execution-time benchmarking

Use `examples/11_solver_timing.py` to compare end-to-end level-population solver
execution times.  The timing includes ATDB decoding, line/collision selection,
matrix assembly, the linear solve, and CSV/JSON output writing.  This makes the
example useful for practical workflow benchmarking rather than only timing the
linear algebra kernel.

Basic O VIII dense/sparse comparison:

```bash
PYTHONPATH=src python examples/11_solver_timing.py \
  ../xstar/data/atdb.fits \
  --repeat 3 \
  --out-dir solver_timing_example
```

Include the heavier O VII triplet sparse stress test:

```bash
PYTHONPATH=src python examples/11_solver_timing.py \
  ../xstar/data/atdb.fits \
  --include-o7 \
  --repeat 2 \
  --out-dir solver_timing_example \
  --out-csv solver_timing.csv
```

The output CSV contains columns such as:

```text
case, repeat_index, elapsed_s, solver_requested, solver_used,
sparse_used, matrix_size, matrix_nnz, matrix_density, condition_number,
linear_residual_linf, normalization_residual, summary_json
```

### Notes on a future C++ backend

The current sparse solve uses SciPy's compiled sparse linear-algebra routines,
so the linear solve itself is already handled by optimized native code when
`--linear-solver sparse` is available.  A C++ backend could still improve
performance for repeated production workflows by moving the following steps out
of pure Python:

- repeated ATDB record filtering and level/transition indexing,
- type-63/type-51/type-98 rate evaluation loops over many ions and temperatures,
- sparse matrix assembly for large level systems,
- repeated line/band emissivity aggregation over many temperature or density
  grid points,
- direct HDF5 export of packed numeric arrays.

The best development path is to keep Python as the public API and add an
optional compiled backend later, for example through `pybind11` or a small C
ABI extension.  The backend should be optional: the package should continue to
work in pure Python/SciPy mode for portability.

## Solver step profiling

The example `examples/12_profile_solver_steps.py` profiles the major stages of a
single solver run.  It separates wall-clock time for opening the ATDB file,
building the record index, extracting levels/lines/collisions, evaluating
collision rates, assembling the matrix, solving the matrix, and writing outputs.

```bash
PYTHONPATH=src python examples/12_profile_solver_steps.py \
  ../xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperature 1e6 --electron-density 1.0 \
  --linear-solver sparse \
  --out-dir solver_profile_example
```

This is the preferred diagnostic before adding an optional C++ backend.  The
compiled sparse solve itself is already provided by SciPy, so a future shared
library should first target ATDB filtering, record unpacking, collision-rate
evaluation loops, matrix assembly, and export aggregation.

## Prototype O VII recombination/cascade workflow

The example `examples/13_o7_recombination_cascade_workflow.py` implements the
current Stage-6 prototype workflow:

1. evaluate total O VIII -> O VII recombination records;
2. distribute the total source into selected O VII excited/high levels;
3. redistribute that prototype source through radiative branching;
4. feed the cascade source CSV into the sparse level-population solver;
5. compute O VII triplet `R=f/i` and `G=(f+i)/r` diagnostics;
6. optionally compare with an XSTAR `xout_lines1.fits` CSV conversion.

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_recomb_cascade_workflow \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv
```

This workflow is a sensitivity/prototype model.  The decoded oxygen RR/DR
records are total recombination rates, not true level-resolved recombination
cascade records.  The outputs should therefore be used to test the solver and
source-file interface, not as final physical O VII triplet predictions.


## Recommended array-backed NPZ index cache

The ATDB hierarchy scan is often the dominant startup cost because it walks more than one million packed records.  For repeated targeted workflows, use the array-backed NumPy/NPZ cache:

```bash
PYTHONPATH=src python examples/12_profile_solver_steps.py \
  ../xstar/data/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperature 1e6 --electron-density 1.0 \
  --linear-solver sparse \
  --index-cache \
  --index-cache-format npz \
  --out-dir solver_profile_npz_arrays_hit
```

In the validated O VIII sparse-solver profile, the uncached run took about `5.31 s`, while the NPZ array-backed cache-hit run took about `0.53 s`.  The `build_index` stage dropped from about `5.00 s` to about `0.058 s`.

The default cache file is `atdb.fits.xstar_atomic_index.npz`.  Use `--rebuild-index-cache` after changing or replacing `atdb.fits`.  Legacy pickle caching remains available with `--index-cache-format pickle`, but the NPZ array-backed path is recommended.

The solver, export, high-level API, and profiling examples can all use this cache.  For export workflows:

```bash
PYTHONPATH=src python -m xstar_atomic.export ../xstar/data/atdb.fits \
  --ions "O VIII,Ne IX" \
  --temperatures 1e6 3e6 1e7 \
  --wavelength-min 1.0 --wavelength-max 40.0 \
  --bands-kev soft:0.5:2.0 med:0.6:1.0 hard:2.0:10.0 \
  --formats csv,hdf5 \
  --index-cache --index-cache-format npz \
  --out-dir atomic_export_cached \
  --print-summary
```

The summary reports `index_cache_status` and `index_cache_path`; cache-hit runs should report statuses such as `npz_array_hit` or `array_memory`.

## Downloading and configuring `atdb.fits`

`xstar-atomic` does not bundle XSTAR's large `atdb.fits` file.  The package can
now remember a local XSTAR data directory in a small text file named
`datapath`.  Once this file is configured, high-level code can use
`ATDB()` or `XSTARAtomic()` without passing the FITS path each time.

Interactive download/configuration:

```bash
python -m xstar_atomic.data
```

or, after installation:

```bash
xstar-atomic-download-data
```

The helper reports the remote file size, asks whether to download the file
(pressing Enter means yes), asks for a destination directory, downloads with a
progress indicator, and stores the destination directory in `datapath`.
The default destination is:

```text
data
```

## Data download and path configuration

`xstar-atomic` does not bundle XSTAR's large `atdb.fits` file. The data helper can download the file or save the path to an existing local copy.

```bash
python -m xstar_atomic.data
# or, after installation
xstar-atomic-download-data
```

The helper reports the remote file size, asks whether to download (`Y` is the default when pressing Enter), asks for a destination directory, downloads with a single-line ASCII progress bar, and stores the selected data directory in `datapath`. In a source checkout, the default destination is the project-level `data/` directory and the persistent path file is the project-level `datapath`.

Example progress line:

```text
xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)
```

Default public source:

```text
https://heasarc.gsfc.nasa.gov/FTP/software/lheasoft/lheasoft6.36/heasoft-6.36/ftools/xstar/data/atdb.fits
```

Configure an existing file non-interactively:

```bash
python -m xstar_atomic.data --set-path /path/to/atdb.fits
python -m xstar_atomic.data --show
```

Top-level Python helpers:

```python
from xstar_atomic import (
    download_data,
    resolve_atdb_path,
    find_atdb_file,
    get_data_path,
    set_data_path,
)

path = download_data()
set_data_path('/path/to/xstar/data/atdb.fits')
path = resolve_atdb_path()
```

After configuration, the high-level API can omit the FITS path:

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic(index_cache=True, index_cache_format='npz')
lines = db.lines('O VIII', wavelength=(18.8, 19.1), slim=True)
```

Path resolution order:

```text
explicit path
XSTAR_ATDB_FITS
datapath
data/atdb.fits
interactive download/configuration
```


### Stage 6 cascade-yield source allocation

The O VII recombination/cascade workflow now supports a less purely statistical
source distribution for total O VIII -> O VII recombination.  The new
`selected-cascade-yield` mode weights each candidate source level by its
radiative-cascade probability of feeding user-selected target levels, such as
the O VII triplet upper levels.  This remains a prototype because the decoded
oxygen recombination records are total rates rather than true level-resolved
recombination feeds.

Example:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-cascade-yield \
  --cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0 \
  --cascade-weight-floor 0.02 \
  --out-dir o7_recomb_cascade_workflow \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

The workflow writes initial source rows, cascade-redistributed source rows,
cascade path diagnostics, sparse-solver populations and O VII triplet `R=f/i`
and `G=(f+i)/r` diagnostics.


### Stage-6 O VII triplet target maps

The recommended Stage-6 baseline is the equal-target map:

```bash
--source-mode selected-cascade-yield \
--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0
```

This preserved the good `G=(f+i)/r` agreement with the XSTAR O VII reference. For experiments that try to reduce `R=f/i` without strongly changing `G`, use a forbidden-to-intercombination shift preset such as:

```bash
--cascade-target-preset o7-triplet-f2i025-rkeep
```

which expands to `2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0`. It preserves the resonance target and approximately preserves the total triplet-target weight. Manual `--cascade-target-levels` overrides any preset.

### Stage-6 O VII cascade tuning scan

The equal-target `selected-cascade-yield` map remains the recommended Stage-6
baseline because it preserves the good XSTAR agreement in `G=(f+i)/r`:

```bash
--source-mode selected-cascade-yield \
--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0
```

For controlled experiments, the preferred presets now shift target weight from the forbidden upper level into the intercombination upper levels while preserving the resonance target and the total triplet-target weight. This is intended to reduce `R=f/i` without strongly moving `G=(f+i)/r` away from the equal-target baseline:

```text
o7-triplet-f2i010-rkeep -> 2:0.90,3:1.0333333333,4:1.0333333333,5:1.0333333333,7:1.0
o7-triplet-f2i015-rkeep -> 2:0.85,3:1.05,4:1.05,5:1.05,7:1.0
o7-triplet-f2i025-rkeep -> 2:0.75,3:1.0833333333,4:1.0833333333,5:1.0833333333,7:1.0
o7-triplet-f2i050-rkeep -> 2:0.50,3:1.1666666667,4:1.1666666667,5:1.1666666667,7:1.0
```

The older simple `fdown` presets remain available for reproducibility, but they reduced `G` too much in the first tuning scan.

Use the tuning scan helper to run the equal baseline plus the experimental
presets and summarize `R=f/i` and `G=(f+i)/r` relative to the saved XSTAR O VII
reference:

```bash
PYTHONPATH=src python examples/15_o7_cascade_tuning_scan.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_cascade_tuning_scan \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

The scan writes `o7_cascade_tuning_scan.csv` and a JSON summary. The aim is to
reduce `R` while keeping `G` close to the equal-target/XSTAR value; the equal
map should remain the baseline unless an experimental preset improves both.



### Type-68-aware O VII cascade tuning scan

After He-like collision data types 67/68/69 are enabled, O VII includes the
metastable-to-intercombination coupling from level 2 into levels 3, 4, and 5.
This gives the expected density-sensitive behavior in `R=f/i`, but it can make
the low-density `G=(f+i)/r` too small for the previous cascade-source map.
The type-68-aware scan keeps the equal triplet weights fixed and progressively
downweights the resonance target level 7:

```text
o7-triplet-type68-r095 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.95
o7-triplet-type68-r090 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.90
o7-triplet-type68-r085 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.85
o7-triplet-type68-r080 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.80
o7-triplet-type68-r075 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.75
o7-triplet-type68-r070 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.70
o7-triplet-type68-r060 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.60
o7-triplet-type68-r050 -> 2:1.0,3:1.0,4:1.0,5:1.0,7:0.50
```

Run the scan with:

```bash
PYTHONPATH=src python examples/17_o7_type68_cascade_tuning_scan.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_type68_cascade_tuning_scan \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

The scan writes `o7_type68_cascade_tuning_scan.csv`,
`o7_type68_cascade_tuning_scan_all_densities.csv`, and a JSON summary. Use this
scan after the type-67/68/69 He-like collision decoders are active. The equal
target map remains the reference baseline; the type-68-aware presets are
experiments for restoring `G` while preserving the density-sensitive `R` physics.

## Stage-6 O VII metastable/intercombination coupling diagnostic

The O VII triplet ratio `R=f/i` is sensitive to transfer from the forbidden-line upper level into the intercombination manifold.  Use `examples/16_o7_metastable_coupling_diagnostics.py` to inspect level 2 -> levels 3, 4, and 5 and compare `C_2j = n_e q_2j` against decoded radiative rates.

```bash
PYTHONPATH=src python examples/16_o7_metastable_coupling_diagnostics.py \
  ../xstar/data/atdb.fits \
  --temperature 1e6 \
  --electron-densities 1 1e4 1e8 1e10 1e12 \
  --index-cache --index-cache-format npz \
  --out-dir o7_metastable_coupling \
  --print-summary
```

The CSV output reports `q_2_to_j_cm3_s`, `C_2_to_j_s^-1`, decoded radiative A-values, and density estimates where collisional transfer becomes comparable to radiative decay.

## He-like collisional coupling diagnostics

Version 0.2.47 adds XSTAR He-like collision decoders for data types 67, 68, and 69. These are used to test whether O VII metastable/intercombination coupling is stored in ATDB outside the type-63 records. The diagnostic example writes both rate summaries and a full collision inventory for levels 2, 3, 4, and 5.

```bash
PYTHONPATH=src python examples/16_o7_metastable_coupling_diagnostics.py \
  ../xstar/data/atdb.fits \
  --temperature 1e6 \
  --electron-densities 1 1e4 1e8 1e10 1e12 \
  --index-cache --index-cache-format npz \
  --out-dir o7_metastable_coupling \
  --print-summary
```

Outputs include `o7_metastable_coupling_rates.csv`, `o7_metastable_coupling_collision_inventory.csv`, and `o7_metastable_coupling_summary.json`.
