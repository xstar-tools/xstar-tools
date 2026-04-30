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


## Stage-6 two-parameter O VII type-68 cascade scan

The equal-target `selected-cascade-yield` map remains the recommended Stage-6 baseline:

```bash
--source-mode selected-cascade-yield \
--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0
```

After the type 67/68/69 He-like collision decoders are enabled, the remaining O VII triplet mismatch should be explored with a two-parameter scan.  The helper

```bash
PYTHONPATH=src python examples/18_o7_type68_2d_cascade_tuning_scan.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_type68_2d_cascade_tuning_scan \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

scans maps of the form

```text
2:(1-d),3:(1+d/3),4:(1+d/3),5:(1+d/3),7:r
```

where `d` shifts source weight from the forbidden level into the intercombination levels and `r` controls resonance feeding.  The output files are:

```text
o7_type68_2d_cascade_tuning_scan.csv
o7_type68_2d_cascade_tuning_scan_ranked.csv
o7_type68_2d_cascade_tuning_scan_all_densities.csv
o7_type68_2d_cascade_tuning_scan_summary.json
```

The ranked table uses a simple relative squared-error score in `R=f/i` and `G=(f+i)/r` relative to the saved XSTAR O VII reference.

## Stage-6 cascade source-fit diagnostic

The example `examples/19_o7_cascade_source_fit.py` is a diagnostic tool for the remaining O VII recombination/cascade problem. It builds a radiative cascade yield matrix,

```text
Y(source level -> forbidden, intercombination, resonance)
```

where the forbidden component uses level 2, the intercombination component uses levels 3, 4, and 5, and the resonance component uses level 7 by default. It then compares simple statistical source weights with a fitted nonnegative source-weight vector that best reproduces the saved XSTAR O VII triplet ratios.

```bash
PYTHONPATH=src python examples/19_o7_cascade_source_fit.py \
  ../xstar/data/atdb.fits \
  --index-cache --index-cache-format npz \
  --out-dir o7_cascade_source_fit \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

Outputs:

```text
o7_cascade_yield_matrix.csv
o7_source_fit_weights.csv
o7_source_fit_summary.json
```

The fitted weights are not a final physical recombination model. They are intended to show which source levels would need enhanced or suppressed recombination feeding if the current radiative cascade network is forced to reproduce the XSTAR O VII `R=f/i` and `G=(f+i)/r` ratios.


### Stage-6 empirical source-fit mode

The O VII cascade source-fit diagnostic writes `o7_source_fit_weights.csv`. These weights can be reused as an empirical diagnostic source allocation with:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-fit-weights \
  --source-fit-weights-csv xstar_test_run/o7_source_fit_weights.csv \
  --out-dir o7_recomb_cascade_workflow_fit_weights \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

A convenience diagnostic mode is also available:

```bash
--source-mode o7-xstar-fit
```

When no explicit `--source-fit-weights-csv` is supplied, this mode looks for the packaged/source-tree reference file `xstar_test_run/o7_source_fit_weights.csv`. These fitted weights are empirical diagnostics derived from the current O VII/XSTAR comparison, not true level-resolved recombination rates.

### Stage-6 full-solver source-fit diagnostic

The cascade-yield fit in `examples/19_o7_cascade_source_fit.py` is useful for testing the radiative branching network, but its fitted weights are not guaranteed to reproduce the same R/G ratios when injected into the full statistical-equilibrium solver.  For the stricter full-solver diagnostic, use the rank-aware SVD treatment that was validated against the saved XSTAR O VII triplet reference:

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit \
  --print-summary
```

The recommended diagnostic solver settings are:

```text
linear_solver = svd
rank_deficient_action = svd
negative_population_action = keep
prune_null_rate_levels = true
source_total_rate = 1.0 s^-1
```

These settings are important because the O VII statistical-equilibrium matrix is rank-deficient and highly ill-conditioned.  In the validation run, the combined-source solve used `numpy.linalg.svd_lstsq`, had matrix rank `231/238`, condition number about `3.1e18`, residuals `linear_residual_l2 ~ 0.0032` and `linear_residual_linf ~ 0.0032`, and one raw negative population retained for diagnostic linearity.  Null-rate pruning removed levels `44`, `45`, and `241`.

The script automatically performs a combined-source validation solve after fitting the weights.  Its summary reports the XSTAR R/G target, the fitted linear-response R/G prediction, and the actual simultaneous-solver R/G result, together with matrix rank, condition number, residuals, null-rate pruning diagnostics, source/sink summaries, and negative-population diagnostics.  Use `--skip-combined-validation` only when you want the older response-matrix-only behavior.

A validated v0.2.62 run gave:

```text
XSTAR R=3.20837 G=10.5622
Fitted linear-response R=3.20838 G=10.5622
Combined simultaneous-solver R=3.20838 G=10.5622
R/R_XSTAR = 1.00000146
G/G_XSTAR = 0.99999836
```

The compatible output weights can then be used with the recombination/cascade workflow.  Use the same SVD/rank-aware solver treatment and scale the solver source CSV to the same total source rate used by the fit:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-fit-weights \
  --source-fit-weights-csv o7_solver_source_fit/o7_source_fit_weights.csv \
  --solver-source-csv-mode initial \
  --solver-source-total-rate 1.0 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --out-dir o7_recomb_cascade_workflow_solver_fit \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

These weights are empirical diagnostics, not physical level-resolved recombination rates.  The recommended SVD path is the validated path for this O VII/XSTAR-fit diagnostic; direct dense or sparse solves should not be trusted for this rank-deficient matrix unless their residual and combined-source validation diagnostics are checked.

For package regression tests, the validated v0.2.62 O VII source-fit summary is saved as `examples/reference_outputs/o7_solver_source_fit_summary_reference.json`.  The lightweight CI tests in `tests/test_o7_solver_source_fit_reference.py` verify the saved XSTAR R/G match, the agreement between fitted linear-response and combined simultaneous-solver validation, and the recommended SVD/null-rate-pruning solver treatment without requiring the full `atdb.fits` file.  When using `examples/13_o7_recombination_cascade_workflow.py` with `selected-fit-weights` or `o7-xstar-fit`, v0.2.64 emits a warning unless `--solver-source-total-rate` is supplied, because the empirical weights are amplitude-dependent.


### Validated O VII diagnostic commands

The validated O VII empirical solver-source-fit path is:

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit \
  --print-summary
```

The matching cascade-workflow validation should use the same total source amplitude:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-fit-weights \
  --source-fit-weights-csv o7_solver_source_fit/o7_source_fit_weights.csv \
  --solver-source-csv-mode initial \
  --solver-source-total-rate 1.0 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --out-dir o7_recomb_cascade_workflow_solver_fit \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

Reference snapshots for the density-grid diagnostic are saved in `examples/reference_outputs/o7_solver_source_fit_density_grid.csv` and `examples/reference_outputs/o7_solver_source_fit_density_grid_summary.json`.

### Known limitation of empirical O VII weights

The O VII fitted source weights in these examples are empirical diagnostics.  They are fitted to reproduce XSTAR triplet ratios for a specified solver setup, density, source-level set, and total source amplitude.  They are not physical level-resolved recombination rates and should not be used as a substitute for a recombination/cascade source model derived from atomic data.

### O VII density-grid source-fit diagnostic

After validating the empirical O VII full-solver source fit at `ne = 1 cm^-3`, use `examples/21_o7_solver_source_fit_density_grid.py` to test whether the fitted source distribution is stable with density.  The default grid is:

```text
ne = 1, 1e4, 1e8, 1e10, 1e12 cm^-3
```

Run:

```bash
PYTHONPATH=src python examples/21_o7_solver_source_fit_density_grid.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit_density_grid \
  --print-summary
```

This script runs the validated `examples/20_o7_solver_source_fit.py` workflow at each density, then also validates the fixed `ne=1 cm^-3` source weights at every density.  It writes:

```text
o7_solver_source_fit_density_grid/o7_solver_source_fit_density_grid.csv
o7_solver_source_fit_density_grid/o7_solver_source_fit_density_grid_summary.json
```

The CSV reports the reused low-density XSTAR R/G reference, fixed-`ne=1` R/G, refitted linear-response R/G, refitted combined simultaneous-solver R/G, matrix rank, condition number, residuals, negative-population diagnostics, and source-weight changes relative to the reference density.  In v0.2.66 it also adds `fit_success_vs_xstar` and `target_reachable` feasibility flags; `refitted_R_over_xstar`, `refitted_G_over_xstar`, `fixed_R_over_refitted`, and `fixed_G_over_refitted` ratio columns; and per-density warnings when the fit objective is large or the refitted combined R/G ratios remain outside tolerance.  The XSTAR target label is written explicitly as a low-density reference reused at all densities unless a later density-dependent XSTAR reference-table option is added.  This is a diagnostic for density dependence of the empirical source distribution after type-68 metastable/intercombination coupling; the fitted weights remain empirical and should not be interpreted as physical level-resolved recombination rates.


For density-dependent XSTAR reference products, use `examples/22_o7_solver_source_fit_density_xstar_grid.py`.  This front end calls the same density-grid machinery but requires one XSTAR line CSV per density, so each density is compared against its own XSTAR target rather than against the reused low-density reference.

A mapping CSV can be written as:

```text
electron_density_cm^-3,xstar_lines_csv,xstar_value_column,xstar_target_label
1,xstar_o7_ne1_lines.csv,emit_outward,O VII XSTAR ne=1
1e10,xstar_o7_ne1e10_lines.csv,emit_outward,O VII XSTAR ne=1e10
1e12,xstar_o7_ne1e12_lines.csv,emit_outward,O VII XSTAR ne=1e12
```

Run:

```bash
Before running the density-specific grid, create a starter mapping CSV and replace each placeholder `xstar_lines_csv` value with the converted XSTAR line CSV for that density:

```bash
PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \
  --write-template-grid-csv xstar_test_run/xstar_o7_density_grid_references.template.csv
```

Then run the grid with the edited mapping file:

PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit_density_xstar_grid \
  --print-summary
```

Alternatively, supply repeated `--xstar-lines-csv-by-density DENSITY:CSV` arguments.  The output CSV keeps `xstar_target_is_reused_low_density_reference=false` and records the XSTAR CSV path and target label used for each density.



### Preparing real O VII XSTAR density-grid references

`examples/22_o7_solver_source_fit_density_xstar_grid.py` needs one converted XSTAR O VII triplet CSV per density.  If those runs do not exist yet, generate the run plan with:

```bash
PYTHONPATH=src python examples/23_prepare_o7_xstar_density_grid.py \
  --root . \
  --mapping-csv xstar_test_run/xstar_o7_density_grid_references.csv \
  --print-summary
```

The helper writes `xstar_runs/o7_ne*/run_xstar.sh` scripts with the full XSTAR commands, `convert_o7_triplet.sh` conversion scripts, `xstar_o7_density_grid_references.csv`, and `xstar_runs/README_o7_density_grid.md` containing the complete workflow.  Run XSTAR externally, convert each `xout_lines1.fits`, then run example 22 with the generated mapping CSV.  The empirical O VII fitted source weights remain diagnostic, not physical level-resolved recombination rates.

The compact density-specific XSTAR reference inputs are stored under `xstar_test_run/o7_ne*/xstar_o7_triplet_lines.csv`. The density-grid solver directories such as `o7_solver_source_fit_density_xstar_grid/` are generated outputs and are not required package inputs.

### O VII high-density mismatch diagnostic

After running the density-dependent XSTAR-grid comparison, use `examples/24_o7_high_density_mismatch_diagnostics.py` to focus on the high-density failure case, usually `ne=1e12 cm^-3`:

```bash
PYTHONPATH=src python examples/24_o7_high_density_mismatch_diagnostics.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --density 1e12 \
  --reference-density 1 \
  --index-cache \
  --out-dir o7_high_density_mismatch \
  --print-summary
```

The diagnostic reads the outputs from examples 21/22 and writes:

- `o7_high_density_component_mismatch.csv`, comparing normalized forbidden/intercombination/resonance fractions against the XSTAR target;
- `o7_high_density_source_weight_changes.csv`, showing how the fitted source weights changed relative to the reference density;
- `o7_high_density_collision_rates.csv`, when `atdb.fits` is supplied, with type-68/69 level-2 to level-3/4/5 collision rates;
- `o7_high_density_mismatch_summary.json`, collecting the component, weight, solver, and collision diagnostics.

This is intended to identify whether the high-density mismatch is driven by a triplet-component imbalance, source-weight collapse, metastable/intercombination collisional coupling, or a missing high-n/source-level contribution.  The fitted weights remain empirical and should not be interpreted as physical level-resolved recombination rates.

### O VII high-density expanded source-level scan

Version 0.2.72 adds `examples/25_o7_high_density_expanded_source_scan.py`, a diagnostic for the remaining high-density (`ne=1e12 cm^-3`) O VII mismatch.  It reruns the validated solver-response fit with progressively larger empirical source-level sets, such as the validated baseline, `n<=5`, `n<=6`, `n<=8`, and an all-level source proxy, and reports whether any set can reach the density-specific XSTAR R/G target.

```bash
PYTHONPATH=src python examples/25_o7_high_density_expanded_source_scan.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --density 1e12 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_high_density_expanded_source_scan \
  --print-summary
```

The output `o7_high_density_expanded_source_scan.csv` lists the fitted R/G values, R/XSTAR and G/XSTAR ratios, reachability flag, top fitted source level, effective number of source weights, and matrix diagnostics for each source set.  The scan remains empirical/diagnostic; it does not turn the fitted source weights into physical recombination rates.

### O VII high-density rate-sensitivity diagnostic

`examples/26_o7_high_density_rate_sensitivity.py` scans temporary diagnostic
scale factors for selected collision-rate families after the expanded source
scan has shown that source-level expansion alone does not recover the
`ne=1e12 cm^-3` XSTAR O VII target.  It supports scans of the symmetric
level-2-to-3/4/5 metastable coupling and the XSTAR type-68/type-69 decoded
collision blocks.  These scale factors are diagnostics only; they do not change
the atomic database.

```bash
PYTHONPATH=src python examples/26_o7_high_density_rate_sensitivity.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --density 1e12 \
  --families metastable,type68,type69 \
  --scales 0.1,0.2,0.5,1,2,5,10 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_high_density_rate_sensitivity \
  --print-summary
```

The output `o7_high_density_rate_sensitivity_scan.csv` reports the best R/G,
R/XSTAR, G/XSTAR, component mismatch, and solver diagnostics for each scaled
network.

### O VII type-69 transition-sensitivity diagnostic

Version 0.2.74 adds `examples/27_o7_type69_transition_sensitivity.py` to isolate which type-69 collision records or level pairs drive the high-density O VII mismatch. It follows the density-dependent XSTAR-grid and rate-family diagnostics, and should be run after `examples/22` and `examples/26` have identified a high-density mismatch that is sensitive to type-69 scaling.

```bash
PYTHONPATH=src python examples/27_o7_type69_transition_sensitivity.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --density 1e12 \
  --scan-mode record \
  --scales 0.1,0.2,0.5,2,5,10 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_type69_transition_sensitivity \
  --print-summary
```

The scan writes an inventory of decoded type-69 transitions and a table of record- or pair-specific sensitivity cases. The collision scaling is a diagnostic probe, not a physical correction.

### O VII type-69 record audit

Version 0.2.75 adds `examples/28_o7_type69_record_audit.py` for auditing the specific type-69 records identified by the transition-sensitivity diagnostic. The default target is records `22490`--`22495`, with particular emphasis on the `22490` level `1 -> 7` channel.

```bash
PYTHONPATH=src python examples/28_o7_type69_record_audit.py \
  ../xstar/data/atdb.fits \
  --records 22490,22491,22492,22493,22494,22495 \
  --density 1e12 \
  --audit-temperature 1e6 \
  --temperature-grid 1e5,3e5,1e6,3e6,1e7 \
  --transition-sensitivity o7_type69_transition_sensitivity \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_type69_record_audit \
  --print-summary
```

The output tables contain raw `idat`/`rdat`, decoded level metadata, Kato--Nakazaki `calt69` rates, density-scaled excitation/de-excitation rates, detailed-balance checks, and optional annotations from the v0.2.74 sensitivity scan. This audit is intended to determine whether the record-level decoding is internally consistent before any physical reinterpretation of the high-density type-69 network is attempted.

### v0.2.77 ground-coupling diagnostic hotfix

Version 0.2.77 fixes the ground-coupling diagnostic introduced in v0.2.76.  Some example-20 summaries do not include a usable fitted-weights CSV path; the diagnostic now treats empty or directory paths as missing and falls back to the standard per-case outputs (`o7_source_fit_weights.csv` and `o7_solver_source_fit_weights.csv`).

### v0.2.76 O VII type-69 ground-coupling diagnostic

`examples/29_o7_type69_ground_coupling_diagnostic.py` follows the v0.2.74 and
v0.2.75 diagnostics by focusing on type-69 record 22490, the ground--resonance
O VII channel.  It repeats the solver-source fit for baseline, record-scaled,
all-type-69-scaled, record-removed, excitation-only, de-excitation-only, and
direction-specific cases.  The new diagnostic solver switch
`--collision-record-direction-scale RECORD:DIRECTION:SCALE` is deliberately for
interpretation only, since it can break detailed balance.

### v0.2.78 diagnostic type-69 ground-excitation suppression switch

Version 0.2.78 adds a controlled diagnostic/experimental solver option for the high-density O VII investigation:

```bash
--collision-type69-ground-excitation-mode include|suppress-resonance|suppress-all
```

The default, `include`, preserves the original v0.2.77 behavior.  `suppress-resonance` suppresses only type-69 excitation from the ground level into the He-like resonance upper level while preserving the reverse/de-excitation rate.  For the validated O VII high-density case this is record 22490, level `1 -> 7` (`1s2.1S_0 -> 1s.2p 1P_1`).  `suppress-all` suppresses all type-69 excitation out of the ground level and is broader.

Example density-grid rerun using the targeted switch:

```bash
PYTHONPATH=src python examples/22_o7_solver_source_fit_density_xstar_grid.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --collision-type69-ground-excitation-mode suppress-resonance \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit_density_xstar_grid_type69_suppressed \
  --print-summary
```

The option is diagnostic and should not yet be treated as a final physical correction.  It makes the v0.2.77 conclusion reproducible with a single switch: the high-density O VII XSTAR target is recovered when the ground-to-resonance type-69 excitation path is suppressed while de-excitation is retained.


### O VII type-69 mode comparison (v0.2.81)

`examples/30_o7_density_grid_type69_mode_compare.py` runs the density-dependent O VII source-fit grid twice: once with the original type-69 handling (`include`) and once with the diagnostic/experimental `suppress-resonance` mode.  It merges the two grid outputs into `o7_density_grid_type69_mode_compare.csv`, including density, XSTAR R/G targets, include-mode R/G and reachability, suppress-resonance R/G and reachability, mismatch-improvement factors, source-weight L1 changes, and top fitted source levels.

The `suppress-resonance` mode suppresses type-69 excitation from the ground level into the He-like resonance upper level while preserving de-excitation.  For the O VII benchmark this corresponds to record 22490 (`1s2.1S_0 -> 1s.2p 1P_1`).  This mode is diagnostic/experimental: it is validated for the O VII high-density benchmark and should not be treated as a general physical default.


### v0.2.83 density-grid input layout

The density-dependent O VII examples no longer require a root-level `xstar_o7_density_grid_references.csv` or a pre-existing `o7_solver_source_fit_density_xstar_grid/` directory.  The compact packaged inputs are the converted XSTAR triplet CSVs under `xstar_test_run/o7_ne*/xstar_o7_triplet_lines.csv`.  Use `--auto-xstar-test-run-grid` to discover those inputs.  Density-grid solver directories remain generated outputs.  Example 26 also validates the selected `ne=1e12` XSTAR target when reading a generated density-grid directory, so stale placeholder outputs fail clearly instead of silently using the wrong target.

#### O VII high-density benchmark result snapshot (v0.2.82)

The v0.2.81 comparison output is now packaged as a reference validation snapshot under `examples/reference_outputs/` and `docs/validation/xstar_outputs/`:

```text
o7_density_grid_type69_mode_compare.csv
o7_density_grid_type69_mode_compare_summary.json
```

The snapshot records the side-by-side result for the density-specific XSTAR grid.  In the default `include` mode, all rows through `ne=1e10 cm^-3` remain reachable, but the `ne=1e12 cm^-3` row fails with approximately `R/G = 0.0378 / 3.202`.  In the diagnostic/experimental `suppress-resonance` mode, the high-density row becomes reachable with approximately `R/G = 0.08307 / 4.5197`, matching the XSTAR target `R/G = 0.083064 / 4.51966`.

This is a benchmark validation result for O VII only.  The `suppress-resonance` option should remain explicitly diagnostic/experimental until tested against additional He-like ions, temperatures, and full XSTAR model configurations.


Example command:

```bash
PYTHONPATH=src python examples/30_o7_density_grid_type69_mode_compare.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_density_grid_type69_mode_compare \
  --print-summary
```


### He-like type-69 ground-resonance validation audit

Example 31 broadens the O VII type-69 investigation to other He-like ions.  It audits candidate type-69 ground-to-resonance excitation records for ions such as C V, N VI, O VII, Ne IX, Mg XI, Si XIII, S XV, Ar XVII, Ca XIX, and Fe XXV, and writes candidate and validation-status tables.  The script does not mark non-O VII ions as validated unless density-specific XSTAR triplet grids are supplied; without those external references they remain `pending_xstar_density_grid`.  O VII is the currently validated benchmark because the package includes compact converted density-specific XSTAR references under `xstar_test_run/o7_ne*/`.

```bash
PYTHONPATH=src python examples/31_helike_type69_ground_resonance_validation.py \
  ../xstar/data/atdb.fits \
  --ions "C V,N VI,O VII,Ne IX,Mg XI,Si XIII,S XV,Ar XVII,Ca XIX,Fe XXV" \
  --temperature-grid 1e6 \
  --density 1e12 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_helike_index.npz \
  --out-dir helike_type69_ground_resonance_validation \
  --print-summary
```

This keeps `suppress-resonance` as a diagnostic/experimental O VII benchmark mode until similar density-grid XSTAR validation exists for other He-like ions.



Version 0.2.88 note: the density-grid wrappers now use an ion-generic He-like triplet reader for converted XSTAR line CSVs.  The reader classifies the forbidden, intercombination, and resonance components from `lower_level`/`upper_level` labels such as `1s1.2s1.3S_1`, `1s1.2p1.3P_J`, and `1s1.2p1.1P_1`, so C V, Mg XI, Ca XIX, and similar He-like grids can be fitted with the same workflow used for O VII.

### Preparing non-O VII He-like XSTAR density grids

Example 32 prepares the external XSTAR density-grid runs needed to test whether the O VII `suppress-resonance` behavior also appears for other candidate He-like ions.  By default it prepares C V, Mg XI, and Ca XIX, the non-O VII ions with candidate type-69 ground-to-resonance records in the audit.  The helper writes run scripts and conversion scripts only; it does not run XSTAR and does not validate those ions by itself.

```bash
PYTHONPATH=src python examples/32_prepare_helike_xstar_density_grids.py \
  --ions "C V,Mg XI,Ca XIX" \
  --densities 1 1e4 1e8 1e10 1e12 \
  --root . \
  --print-summary
```

After running XSTAR externally and converting `xout_lines1.fits`, the generated per-ion mappings, such as `xstar_test_run/xstar_c5_density_grid_references.csv`, `xstar_test_run/xstar_mg11_density_grid_references.csv`, and `xstar_test_run/xstar_ca19_density_grid_references.csv`, can be used for ion-specific density-grid comparisons.  Until those converted XSTAR triplet grids are supplied and compared, only O VII should be treated as validated.


Version 0.2.89 note: the He-like density-grid front end now detects stale non-O VII mapping CSVs that still point to the O VII placeholder file and repairs them when the correct converted per-density files exist under `xstar_test_run/<ion>_ne*/`.  For example, a C V mapping is repaired to use `xstar_test_run/c5_ne*/xstar_c5_triplet_lines.csv`, with the original mapping saved as a `.bak` file.

### He-like density-grid mapping preflight checks

Starting in v0.2.91, the density-grid front end validates non-O VII mapping CSVs before launching the solver-fit subprocess chain.  For candidate ions such as C V, Mg XI, and Ca XIX, the mapping must point to converted triplet files in the current working tree, for example `xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv`.  If the files were generated in an older package directory, copy the corresponding `c5_ne*`, `mg11_ne*`, or `ca19_ne*` folders into the current `xstar_test_run/` directory before rerunning the density-grid fit.


### v0.2.94 He-like density-grid workflow note

Non-O VII He-like density-grid mappings are now checked before the solver-fit subprocess chain starts.  Each converted XSTAR CSV must contain usable forbidden, intercombination, and resonance triplet rows; empty converted files, such as a Ca XIX extraction that finds zero rows, are rejected early with an actionable message.  Diagnostic outputs keep backward-compatible `o7_*` filenames but also provide ion-specific aliases for C V, Mg XI, Ca XIX, and other candidate He-like ions.


### v0.2.95 auditing empty He-like XSTAR line conversions

When a prepared non-O VII He-like XSTAR run completes but the converter reports `n_lines=0`/`n_rows=0`, use Example 33 to inspect the raw `xout_lines1.fits` line table before attempting the solver chain.  This is especially useful for Ca XIX, where the current prepared grid may complete in XSTAR but produce empty converted triplet CSVs.

```bash
PYTHONPATH=src python examples/33_audit_helike_xstar_lines.py \
  xstar_runs/helike_type69/ca19_ne1/xout_lines1.fits \
  --expected-ion "Ca XIX" \
  --wavelength-min 3.0 \
  --wavelength-max 3.4 \
  --out-dir ca19_line_audit_ne1 \
  --print-rows
```

The audit reports the XSTAR ion labels present in the file, rows in the wavelength window regardless of ion label, rows for the expected ion at any wavelength, and rows whose level labels look like He-like ground-to-`n=2` forbidden/intercombination/resonance transitions.  If no complete triplet target is found, the ion remains not testable for the density-grid validation.


### He-like XSTAR ionization-parameter scans (v0.2.96)

`examples/32_prepare_helike_xstar_density_grids.py` supports `--rlogxi-grid` for ions whose default XSTAR run does not produce the expected He-like triplet rows. This is especially useful for Ca XIX: the default `log xi=1.5` run can finish successfully while `xout_lines1.fits` contains no `ca_xix` rows. A scan such as `--rlogxi-grid 1.5 2 2.5 3 3.5 4` writes xi-tagged run directories and mapping CSVs so each ionization condition can be audited independently before a density-grid solver comparison is attempted.


### Source-level failure diagnostics

`examples/36_source_level_failure_diagnostics.py` compares He-like source-fit outputs level by level. It is intended for the post-validation question of why O VII remains reachable while C V, Mg XI, and Ca XIX are not. It reports source level labels, fitted weights, f/i/r response contributions, zero-response flags, optional component populations, dominant radiative and collisional paths, and weak/pruned-level indicators.


### v0.3.3 response-basis filter comparison

`examples/37_filter_source_basis_response.py` refits completed He-like density-grid outputs after removing zero-response and/or negative-response source levels. This diagnostic tests whether non-O VII failures are caused by a contaminated source basis or by the target lying outside the clean positive-response source span.


### v0.3.4 ion-specific source-basis discovery

Use `examples/38_discover_helike_source_basis.py` after response-matrix generation to classify sampled source levels by raw f/i/r response and write ion-specific discovered source-level candidate lists. This is diagnostic/exploratory and does not change default solver physics.

### v0.3.8 signed/absolute triplet-response audit

`examples/40_audit_signed_triplet_response.py` runs a baseline solver calculation and one source-injected calculation per requested level. It writes `helike_signed_triplet_response_audit.csv`, `helike_signed_triplet_response_commands.csv`, `helike_signed_triplet_response_summary.json`, and `helike_signed_triplet_response_audit.md`. The audit compares baseline f/i/r emissivities, source-injected f/i/r emissivities, delta responses, signed normalized delta vectors, sign patterns, and component-wise increase/decrease flags. It is designed to test whether negative non-O VII response columns are caused by baseline subtraction, normalization artifacts, or genuinely destructive population redistribution.

Example:

```bash
PYTHONPATH=src python examples/40_audit_signed_triplet_response.py \
  ../xstar/data/atdb.fits \
  --element C --ion-stage 5 \
  --temperature 1000000 --electron-density 1e8 \
  --wavelength-min 40 --wavelength-max 42 \
  --source-levels 2:80 \
  --index-cache --index-cache-path .xstar_atomic_cache/atdb_c5_index.npz \
  --out-dir c5_signed_triplet_response_audit \
  --print-summary
```

### v0.3.13 target-aware absolute-response constraints

`examples/40_audit_signed_triplet_response.py` and `examples/41_fit_absolute_response_density_grid.py` now support target-aware absolute-response constraints. This mode uses the XSTAR target triplet fractions at each density to choose the allowed intercombination range for source-response columns. It is intended for C V-like cases where low-density targets require strict rejection of intercombination-rich columns, but high-density targets must allow intercombination-rich columns.

Example C V density-grid run:

```bash
PYTHONPATH=src python examples/41_fit_absolute_response_density_grid.py \
  ../xstar/data/atdb.fits \
  --element C --ion-stage 5 \
  --temperature 1000000 \
  --electron-densities 1,1e4,1e8,1e10,1e12 \
  --wavelength-min 40 --wavelength-max 42 \
  --source-levels 2:80 \
  --xstar-lines-csv-template 'xstar_test_run/c5_ne{ne_tag}/xstar_c5_triplet_lines.csv' \
  --absolute-fit-component-weights auto \
  --absolute-fit-constraint-mode target-aware \
  --absolute-fit-target-i-factor 3 \
  --absolute-fit-target-i-floor 0.05 \
  --index-cache \
  --index-cache-path-template '.xstar_atomic_cache/atdb_c5_{ne_tag}.npz' \
  --out-dir c5_absolute_response_density_grid_target_aware \
  --print-summary
```

The explicit `../xstar/data/atdb.fits` path is passed through for the run and does not rewrite persistent `datapath`.
