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



## Stage-5 XSTAR comparison runs

The `xstar_test_run/README.md` file records reproducible direct-XSTAR commands
for validation runs. Current documented runs include:

- O VIII / Ne IX high-ionization line validation.
- O VII triplet and high-density O VII triplet validation.
- Ne IX and Ne X focused runs for Stage-5 wavelength comparisons.
- Validated Mg XI/Mg XII, Si XIII/Si XIV, and Fe XXV/Fe XXVI Stage-5 wavelength comparisons.

The Ne-focused and Mg/Si/Fe-focused workflows convert `xout_lines1.fits` to CSV with
`python -m xstar_atomic.xstar_outputs`, then compare wavelengths with
`examples/08_compare_xstar_outputs.py`. The first validated Ne target products are:

```text
xstar_ne9_triplet_lines.csv
compare_ne9_triplet_wavelength.csv/json
xstar_ne10_lya_lines.csv
compare_ne10_lya_wavelength.csv/json
```


Additional Stage-5 validated heavy-ion targets are:

```text
Mg XI  He-like triplet region: 9.0--9.4 Angstrom
Mg XII Ly-alpha region:        8.35--8.50 Angstrom
Si XIII He-like triplet region: 6.55--6.80 Angstrom
Si XIV Ly-alpha region:        6.10--6.25 Angstrom
Fe XXV K-alpha region:         1.83--1.88 Angstrom
Fe XXVI Ly-alpha region:       1.76--1.80 Angstrom
```

These Mg/Si/Fe validation products are now included: `xout_lines1.fits` artifacts under `xstar_test_run/`, selected-line CSV files, and comparison CSV/JSON files under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`. All selected Mg/Si/Fe lines match within the 0.02 Angstrom tolerance used for the wavelength checks.


Validated Mg/Si/Fe wavelength results included in this release:

```text
Mg XI   5/5 matched, max |Delta lambda| = 4.52e-6 Angstrom
Mg XII  2/2 matched, max |Delta lambda| = 1.96e-6 Angstrom
Si XIII 5/5 matched, max |Delta lambda| = 3.51e-6 Angstrom
Si XIV  2/2 matched, max |Delta lambda| = 3.89e-6 Angstrom
Fe XXV  4/4 matched, max |Delta lambda| = 4.10e-6 Angstrom
Fe XXVI 2/2 matched, max |Delta lambda| = 3.55e-6 Angstrom
```

As with the O VIII and O VII examples, these comparisons validate line
identification and wavelength decoding. XSTAR `emit_inward`/`emit_outward`
columns are full model outputs and are not directly normalized to local
`xstar-atomic` emissivity coefficients.

## Data download and path configuration

`xstar-atomic` does not bundle the large XSTAR `atdb.fits` file. Use the data helper to download it or save the path to an existing copy:

```bash
python -m xstar_atomic.data
# or, after installation
xstar-atomic-download-data
```

The helper reports the remote file size, asks whether to download (pressing Enter means yes), asks for a destination directory, downloads with a single-line ASCII progress bar, and stores the selected data directory in `datapath`. In a source checkout the default destination is the project-level `data/` directory and the persistent path file is the project-level `datapath`, not `src/xstar_atomic/datapath`.

Example progress line:

```text
xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)
```

The default public source is:

```text
https://heasarc.gsfc.nasa.gov/FTP/software/lheasoft/lheasoft6.36/heasoft-6.36/ftools/xstar/data/atdb.fits
```

If you already have `atdb.fits`, decline the download and enter the full path, or configure it non-interactively:

```bash
python -m xstar_atomic.data --set-path /path/to/atdb.fits
python -m xstar_atomic.data --show
```

Programmatic helpers are available from the top-level package:

```python
from xstar_atomic import (
    download_data,
    resolve_atdb_path,
    find_atdb_file,
    get_data_path,
    set_data_path,
)

# Interactive download/configuration.
atdb_path = download_data()

# Or save an existing local file for future sessions.
set_data_path('/path/to/xstar/data/atdb.fits')
atdb_path = resolve_atdb_path()
```

After configuration, the high-level API can omit the FITS path:

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic(index_cache=True, index_cache_format='npz')
lines = db.lines('O VIII', wavelength=(18.8, 19.1), slim=True)
```

Path resolution order is:

```text
explicit path
XSTAR_ATDB_FITS
datapath
data/atdb.fits
interactive download/configuration
```

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


## Plasma post-processing export

Create compact CSV/JSON/HDF5 atomic products for selected ions.  The exporter is intended for superwinds, AGN outflows, and other plasma post-processing workflows:

```bash
PYTHONPATH=src python -m xstar_atomic.export ./xstar/data/atdb.fits \
  --ions "O VIII,Ne IX" \
  --temperatures 1e6 3e6 1e7 \
  --wavelength-min 1.0 --wavelength-max 30.0 \
  --formats csv,hdf5 \
  --out-dir atomic_export \
  --print-summary
```

The export writes levels, lines, collision records/rates, photoionization summaries, emissivity rows, JSON manifests, and optional per-ion HDF5 files.  The installable CLI aliases are `xstar-atomic-export` and the backward-compatible `xstar-atomic-export-superwind`.

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


### Included XSTAR validation runs

The source distribution includes `xstar_test_run/`, which contains small direct-XSTAR `xout_lines1.fits` outputs and converted CSV line tables for:

- O VIII / Ne IX high-ionization validation.
- O VII triplet validation.
- O VII high-density triplet validation.

See `xstar_test_run/README.md` and `docs/xstar_comparison_examples.md` for the exact XSTAR commands and the `xstar_atomic.xstar_outputs` conversion commands.

### Band emissivity export

Broad-band line emissivity products can be generated with ``--bands-kev``:

```bash
PYTHONPATH=src python -m xstar_atomic.export /path/to/atdb.fits \
  --ions "O VIII,Ne IX" \
  --temperatures 1e6 3e6 1e7 \
  --wavelength-min 1.0 --wavelength-max 40.0 \
  --bands-kev soft:0.5:2.0 osoft:0.3:0.6 med:0.6:1.0 hard:2.0:10.0 \
  --formats csv,hdf5 \
  --out-dir atomic_export \
  --print-summary
```

This writes ``*_band_emissivity.csv`` and, for HDF5 exports, a ``/band_emissivity`` group.

The Stage-4 validation run passed 34 real-ATDB tests and confirmed 12 band-emissivity rows per ion for four bands and three temperatures. Zero-line bands keep nonblank ion labels and use `methods_used="none"`.


### Band-emissivity export notes

Band-emissivity rows keep the ion label even for bands with zero selected lines, and use `methods_used="none"` for zero-line bands. This makes CSV/HDF5 exports easier to ingest in simulation post-processing workflows.

### Stage-3 sparse solver and O VII triplet diagnostics

The level-population solver supports dense, sparse, and auto linear solvers:

```bash
PYTHONPATH=src python -m xstar_atomic.solver /path/to/atdb.fits \
  --element O --ion-stage 8 \
  --wavelength-min 18.8 --wavelength-max 19.1 \
  --temperatures 1e6 \
  --electron-densities 1.0 \
  --electron-density-for-lmixing 1.0 \
  --component-mode ground \
  --linear-solver sparse \
  --summary-json o8_sparse_solver_summary.json \
  --print-summary
```

For O VII triplet stress tests, run:

```bash
PYTHONPATH=src python examples/10_o7_triplet_sparse_solver.py \
  /path/to/atdb.fits \
  --out-dir o7_triplet_solver_example
```

The solver reports sparse/dense matrix diagnostics and can write prototype
O VII triplet `R=f/i` and `G=(f+i)/r` diagnostics. These are solver validation
outputs, not final physical line-ratio predictions unless the recombination and
cascade source model is complete.
### Solver timing example

Benchmark dense and sparse level-population solver modes end-to-end:

```bash
PYTHONPATH=src python examples/11_solver_timing.py /path/to/atdb.fits \
  --repeat 3 \
  --out-dir solver_timing_example
```

Include the heavier O VII triplet sparse stress test:

```bash
PYTHONPATH=src python examples/11_solver_timing.py /path/to/atdb.fits \
  --include-o7 \
  --repeat 2 \
  --out-dir solver_timing_example \
  --out-csv solver_timing.csv
```

The timing CSV reports elapsed wall time plus matrix size, nonzero count,
sparsity, condition number, solver backend, and residual diagnostics.  The
current sparse solver already uses SciPy's compiled sparse linear algebra; a
future optional C++ backend would mainly accelerate repeated record filtering,
rate evaluation, matrix assembly, and production export loops.


### ATDB index caching

The solver-step profiler showed that repeated workflows are dominated by `build_index`, not by the sparse linear solve.  You can enable an optional on-disk hierarchy cache for repeated runs:

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

The first cached run writes a file named similar to:

```text
atdb.fits.xstar_atomic_index.npz
```

A later run with `--index-cache` should report `index_cache_status="hit"` and skip the full hierarchy scan.  Use `--rebuild-index-cache` after changing or replacing `atdb.fits`.

The same cache options are available in the solver and export CLIs:

```bash
PYTHONPATH=src python -m xstar_atomic.solver /path/to/atdb.fits ... --index-cache
PYTHONPATH=src python -m xstar_atomic.export /path/to/atdb.fits ... --index-cache
```

From Python:

```python
from xstar_atomic import XSTARAtomic

db = XSTARAtomic("xstar/data/atdb.fits", index_cache=True)
print(db.db.index_cache_status)
```

The cache stores the decoded hierarchy objects and validates them against the source FITS file size, modification time, array lengths, and cache format version.

### Solver step profiling and O VII recombination/cascade workflow

`xstar-atomic` includes two solver-development examples that are useful before
building an optional compiled backend.

Profile individual solver stages:

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

Prototype O VII recombination/cascade source workflow:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_recomb_cascade_workflow \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv
```

A future compiled backend can be distributed as an optional shared-object
library (`.so`) loaded by Python.  The best first targets are ATDB filtering,
record unpacking, collision-rate loops, sparse matrix assembly, and band/export
aggregation; SciPy already provides compiled sparse linear solvers.


### Recommended array-backed NPZ index cache

For repeated workflows, use the array-backed NumPy/NPZ cache.  It stores the hierarchy as numeric arrays, filters by element/ion/data type, and converts only selected rows to `IndexedRecord` objects.  This is now the recommended path for solvers, exports, high-level API calls, and profiling.

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

On the validated O VIII sparse-solver profile, the cache-hit path reduced the run from about `5.31 s` uncached to about `0.53 s` with an NPZ array-backed cache hit.  The `build_index` stage dropped from about `5.00 s` to about `0.058 s`.

The default cache file is `atdb.fits.xstar_atomic_index.npz`.  Use `--rebuild-index-cache` after replacing or modifying `atdb.fits`.  Legacy pickle caching remains available with `--index-cache-format pickle`, but NPZ array-backed caching is preferred for targeted workflows.

The same cache options are accepted by the solver and export CLIs:

```bash
PYTHONPATH=src python -m xstar_atomic.export /path/to/atdb.fits \
  --ions "O VIII,Ne IX" \
  --temperatures 1e6 3e6 1e7 \
  --wavelength-min 1.0 --wavelength-max 40.0 \
  --bands-kev soft:0.5:2.0 med:0.6:1.0 hard:2.0:10.0 \
  --formats csv,hdf5 \
  --index-cache --index-cache-format npz \
  --out-dir atomic_export_cached
```

Download progress is shown on one in-place ASCII progress-bar line, for example:

```text
xstar data: downloading atdb.fits [#####-----------------------]  20% (166.5 MB/830.7 MB)
```


### Ne IX / Ne X Stage-5 XSTAR comparison artifacts

The package includes saved Ne IX and Ne X direct-XSTAR line-output artifacts under `xstar_test_run/`, plus comparison CSV/JSON outputs under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`. The Ne IX triplet/near-triplet and Ne X Ly-alpha wavelength comparisons both match all selected XSTAR lines within 0.02 Angstrom.


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

The recommended Stage-6 baseline remains the equal-target cascade-yield map:

```bash
--source-mode selected-cascade-yield \
--cascade-target-levels 2:1.0,3:1.0,4:1.0,5:1.0,7:1.0
```

This baseline preserved the good `G=(f+i)/r` agreement with the XSTAR O VII reference. For experiments that try to reduce `R=f/i` without strongly changing `G`, use a forbidden-to-intercombination shift preset such as:

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


### O VII metastable/intercombination coupling diagnostics

Stage 6 includes a focused diagnostic for the density-sensitive O VII triplet coupling between the forbidden-line upper level and the intercombination manifold.  It inspects level 2 -> levels 3, 4, and 5 and compares collisional transfer rates with decoded radiative rates over a density grid.

```bash
PYTHONPATH=src python examples/16_o7_metastable_coupling_diagnostics.py \
  ../xstar/data/atdb.fits \
  --temperature 1e6 \
  --electron-densities 1 1e4 1e8 1e10 1e12 \
  --index-cache --index-cache-format npz \
  --out-dir o7_metastable_coupling \
  --print-summary
```

The outputs are `o7_metastable_coupling_rates.csv` and `o7_metastable_coupling_summary.json`.  This diagnostic does not change the cascade source model; it shows whether collisional transfer can compete with forbidden-level radiative decay at the densities of interest.

### He-like collisional coupling diagnostics

Version 0.2.47 adds XSTAR He-like collision decoders for data types 67, 68, and 69. These are important for testing whether O VII metastable/intercombination coupling is present in `atdb.fits` outside the previously decoded type-63 collision records. The O VII diagnostic now also writes a collision inventory for all records involving levels 2, 3, 4, and 5:

```bash
PYTHONPATH=src python examples/16_o7_metastable_coupling_diagnostics.py \
  ../xstar/data/atdb.fits \
  --temperature 1e6 \
  --electron-densities 1 1e4 1e8 1e10 1e12 \
  --index-cache --index-cache-format npz \
  --out-dir o7_metastable_coupling \
  --print-summary
```

New output:

```text
o7_metastable_coupling/o7_metastable_coupling_collision_inventory.csv
```

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

### Stage-6 two-parameter O VII type-68 cascade scan

After enabling He-like type 67/68/69 collisions, the package includes a broader O VII triplet scan that varies both forbidden/intercombination redistribution and resonance suppression while keeping the equal-target map as the reference baseline:

```bash
PYTHONPATH=src python examples/18_o7_type68_2d_cascade_tuning_scan.py \
  ../xstar/data/atdb.fits \
  --out-dir o7_type68_2d_cascade_tuning_scan \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

For a forbidden-to-intercombination shift `d` and resonance weight `r`, the scan uses:

```text
2:(1-d), 3:(1+d/3), 4:(1+d/3), 5:(1+d/3), 7:r
```

It writes compact, ranked, and all-density CSV tables plus a JSON summary.

### Stage-6 cascade source-fit diagnostic

For O VII, empirical target-weight scans indicate that the remaining mismatch is likely tied to the unknown level-resolved recombination source distribution. The diagnostic example `examples/19_o7_cascade_source_fit.py` builds a radiative cascade yield matrix,

```text
Y(source level -> forbidden, intercombination, resonance)
```

then solves for nonnegative source weights that best reproduce the saved XSTAR O VII triplet ratios `R=f/i` and `G=(f+i)/r`.

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
o7_cascade_source_fit/o7_cascade_yield_matrix.csv
xstar_test_run/o7_source_fit_weights.csv
o7_cascade_source_fit/o7_source_fit_summary.json
```

This is a diagnostic tool, not a final physical recombination model. It asks what source-level distribution would be required by the current radiative cascade network to reproduce XSTAR-like O VII triplet ratios.



### Stage-6 full-solver source-fit diagnostic

The cascade-yield fit in `examples/19_o7_cascade_source_fit.py` is useful for testing the radiative branching network, but its fitted weights are not guaranteed to reproduce the same R/G ratios when injected into the full statistical-equilibrium solver.  For that stricter test, use:

```bash
PYTHONPATH=src python examples/20_o7_solver_source_fit.py \
  ../xstar/data/atdb.fits \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_solver_source_fit \
  --print-summary
```

The script also performs an automatic combined-source validation solve after fitting the weights.  Its summary reports the XSTAR R/G target, the fitted linear-response R/G prediction, and the actual simultaneous-solver R/G result, together with matrix rank, condition number, residuals, and negative-population diagnostics.  Use `--skip-combined-validation` only when you want the older response-matrix-only behavior.

The compatible output weights can then be used with the recombination/cascade workflow:

```bash
PYTHONPATH=src python examples/13_o7_recombination_cascade_workflow.py \
  ../xstar/data/atdb.fits \
  --source-mode selected-fit-weights \
  --source-fit-weights-csv o7_solver_source_fit/o7_source_fit_weights.csv \
  --solver-source-csv-mode initial \
  --solver-source-total-rate 1.0 \
  --out-dir o7_recomb_cascade_workflow_solver_fit \
  --xstar-lines-csv xstar_test_run/xstar_o7_triplet_lines.csv \
  --print-summary
```

These weights are empirical diagnostics, not physical level-resolved recombination rates.

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
