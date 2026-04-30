# xstar-atomic

### He-like validation summary tagging

`examples/34_summarize_helike_validation_runs.py` preserves condition-specific directory tags such as `ca19_xi3` and `ca19_xi4` in summary CSV/JSON/Markdown outputs.  This avoids merging multiple Ca XIX ionization-parameter grids into a single ambiguous `ca19` label.


### v0.2.97 note: He-like multi-ion validation summaries

The package now includes `examples/34_summarize_helike_validation_runs.py`, which summarizes completed He-like density-grid validation directories and optional XSTAR line-audit directories into CSV, JSON, and Markdown reports.  This is useful after running O VII, C V, Mg XI, or high-ionization Ca XIX grids because it records whether each density is reachable and whether complete XSTAR triplet targets were available.

Example:

```bash
PYTHONPATH=src python examples/34_summarize_helike_validation_runs.py \
  c5_solver_source_fit_density_xstar_grid \
  mg11_solver_source_fit_density_xstar_grid \
  ca19_xi3_solver_source_fit_density_xstar_grid \
  ca19_xi4_solver_source_fit_density_xstar_grid \
  --audit-dirs ca19_line_audit_ne1 ca19_line_audit_xi3_ne1 \
  --out-dir helike_validation_summary \
  --print-summary
```

### v0.2.96 note: Ca XIX ionization scans

For high-Z He-like ions such as Ca XIX, the default `log xi=1.5` XSTAR setup can produce lower charge states but no `ca_xix` triplet rows. Use the new `--rlogxi-grid` option in `examples/32_prepare_helike_xstar_density_grids.py` to prepare xi-tagged run directories and mapping files, for example:

```bash
PYTHONPATH=src python examples/32_prepare_helike_xstar_density_grids.py \
  --ions "Ca XIX" \
  --densities 1 1e4 1e8 1e10 1e12 \
  --rlogxi-grid 1.5 2 2.5 3 3.5 4 \
  --root . \
  --print-summary
```

This creates directories such as `xstar_runs/helike_type69/ca19_xi3_ne1/` and mapping files such as `xstar_test_run/xstar_ca19_xi3_density_grid_references.csv`. Run XSTAR and convert each xi grid, then audit with `examples/33_audit_helike_xstar_lines.py` to identify a grid that actually contains a complete Ca XIX f/i/r triplet target.


### v0.2.94 note

The non-O VII He-like validation workflow now performs stronger preflight checks on converted XSTAR triplet CSVs.  A mapping row must point to an existing CSV that contains usable forbidden, intercombination, and resonance rows with positive emissivity.  This catches cases such as Ca XIX where XSTAR ran but the converter produced zero matching triplet lines.  Non-O VII runs also now write ion-specific aliases for the legacy `o7_*` diagnostic filenames, for example `c5_solver_source_fit_summary.json` and `mg11_solver_source_fit_density_grid.csv`.  These C V/Mg XI/Ca XIX workflows remain exploratory; only the O VII density-grid suppress-resonance benchmark is currently validated.


### v0.2.83 note

This release standardizes the O VII density-grid benchmark inputs.  The package now keeps only compact density-specific converted XSTAR CSVs under `xstar_test_run/o7_ne*/xstar_o7_triplet_lines.csv`; solver-fit directories such as `o7_solver_source_fit_density_xstar_grid/` are generated outputs, not required inputs.  `examples/22_o7_solver_source_fit_density_xstar_grid.py` and the high-density diagnostics can use `--auto-xstar-test-run-grid`, and `examples/26_o7_high_density_rate_sensitivity.py` now rejects stale `ne=1e12` density-grid outputs whose XSTAR target is inconsistent with the validated density-specific reference.


### v0.2.82 note

This release freezes the v0.2.81 O VII type-69 mode comparison as a reference validation snapshot.  The packaged snapshots under `examples/reference_outputs/` and `docs/validation/xstar_outputs/` record that the default `include` network fails only at `ne=1e12 cm^-3`, while the diagnostic/experimental `suppress-resonance` mode reaches the density-specific XSTAR target there without degrading the lower-density benchmark rows.  The suppress-resonance mode remains validated only for this O VII high-density benchmark and is not a general physical default.

### v0.2.81 note

This release adds `examples/30_o7_density_grid_type69_mode_compare.py`, which runs the O VII density-grid source-fit benchmark in both type-69 modes: the original `include` network and the diagnostic/experimental `suppress-resonance` network.  It writes one merged CSV with the density, include/suppress-resonance R/G ratios, reachability flags, mismatch-improvement factors, source-weight L1 changes, and top fitted source levels.

`--collision-type69-ground-excitation-mode suppress-resonance` is intentionally marked diagnostic/experimental.  It suppresses type-69 excitation from the ground level into the He-like resonance upper level and is validated for the O VII high-density benchmark; it is not a general physical default.

### v0.2.80 note

This release fixes the row-level handling of `--collision-type69-ground-excitation-mode suppress-resonance`, so the full density-grid chain can now pass the diagnostic switch through to `xstar_atomic.solver` without rejecting unrelated collision rows.


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

## Preparing O VII density-dependent XSTAR references

Use `examples/23_prepare_o7_xstar_density_grid.py` to create the real XSTAR run plan needed by the density-dependent O VII comparison.  The helper writes one clean XSTAR run directory per density, each with a `run_xstar.sh` script containing the full XSTAR command, plus conversion scripts and the mapping CSV consumed by `examples/22_o7_solver_source_fit_density_xstar_grid.py`.

```bash
PYTHONPATH=src python examples/23_prepare_o7_xstar_density_grid.py \
  --root . \
  --mapping-csv xstar_test_run/xstar_o7_density_grid_references.csv \
  --print-summary
```

Run the generated XSTAR scripts externally:

```bash
bash xstar_runs/o7_ne1/run_xstar.sh
bash xstar_runs/o7_ne1e4/run_xstar.sh
bash xstar_runs/o7_ne1e8/run_xstar.sh
bash xstar_runs/o7_ne1e10/run_xstar.sh
bash xstar_runs/o7_ne1e12/run_xstar.sh
```

After each run produces `xout_lines1.fits`, convert the line files:

```bash
bash xstar_runs/o7_ne1/convert_o7_triplet.sh
bash xstar_runs/o7_ne1e4/convert_o7_triplet.sh
bash xstar_runs/o7_ne1e8/convert_o7_triplet.sh
bash xstar_runs/o7_ne1e10/convert_o7_triplet.sh
bash xstar_runs/o7_ne1e12/convert_o7_triplet.sh
```

Then run the true density-dependent XSTAR-grid comparison:

```bash
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

The diagnostic reads the outputs from examples 21/22 and writes component, source-weight, collision-rate, and JSON summaries.  It reports which normalized triplet component drives the mismatch, whether the XSTAR target is reachable, whether fitted source weights collapse onto a small number of levels, solver rank/residual/negative-population diagnostics, and type-68/69 level-2 to level-3/4/5 collision rates when `atdb.fits` is supplied.  This remains an empirical diagnostic; it does not provide physical level-resolved recombination rates.

### O VII high-density expanded source scan

`examples/25_o7_high_density_expanded_source_scan.py` tests whether the high-density O VII mismatch can be removed by expanding the empirical source-level set beyond the validated baseline.  It scans baseline, `n<=5`, `n<=6`, `n<=8`, and all-level source proxies against the density-specific XSTAR target from the density-grid workflow.

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

### O VII high-density type-69 transition sensitivity

After the high-density rate-family scan showed that reducing type-69 collision rates can recover the `ne=1e12 cm^-3` XSTAR O VII triplet target, v0.2.74 adds an individual-transition diagnostic:

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

This scan writes `o7_type69_transitions.csv`, `o7_type69_transition_sensitivity.csv`, and `o7_type69_transition_sensitivity_summary.json`. The record/pair scaling is diagnostic only and does not modify the atomic data.

### v0.2.75 O VII type-69 record audit

After `examples/27_o7_type69_transition_sensitivity.py` identifies the individual type-69 records that control the high-density O VII mismatch, version 0.2.75 adds a raw-record audit:

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

The audit writes `o7_type69_record_audit.csv`, `o7_type69_record_raw_audit.csv`, `o7_type69_record_temperature_grid.csv`, and `o7_type69_record_audit_summary.json`. These files expose the raw `idat`/`rdat` fields, decoded lower/upper levels, level labels, energy separations, statistical weights, `calt69` Upsilon values, excitation/de-excitation rates, detailed-balance checks, and any record-level sensitivity results inherited from the v0.2.74 scan. This is diagnostic only; it does not apply a physical correction.

### v0.2.77 ground-coupling diagnostic hotfix

Version 0.2.77 fixes the ground-coupling diagnostic introduced in v0.2.76.  Some example-20 summaries do not include a usable fitted-weights CSV path; the diagnostic now treats empty or directory paths as missing and falls back to the standard per-case outputs (`o7_source_fit_weights.csv` and `o7_solver_source_fit_weights.csv`).

### v0.2.76 O VII type-69 ground-coupling diagnostic

After the type-69 record audit, the next diagnostic isolates whether the
high-density O VII mismatch is caused by the whole record-22490 pair, by its
excitation direction, or by its de-excitation direction:

```bash
PYTHONPATH=src python examples/29_o7_type69_ground_coupling_diagnostic.py \
  ../xstar/data/atdb.fits \
  --auto-xstar-test-run-grid \
  --density 1e12 \
  --record 22490 \
  --linear-solver svd \
  --rank-deficient-action svd \
  --negative-population-action keep \
  --prune-null-rate-levels \
  --combined-source-total-rate 1.0 \
  --index-cache \
  --index-cache-path .xstar_atomic_cache/atdb_o7_index.npz \
  --out-dir o7_type69_ground_coupling_diagnostic \
  --print-summary
```

The script writes `o7_type69_ground_coupling_diagnostic.csv` and a JSON
summary.  Direction-specific cases use the diagnostic solver option
`--collision-record-direction-scale RECORD:DIRECTION:SCALE`; these cases are
not physical corrections by themselves, because they intentionally break
detailed balance to separate the lower-to-upper excitation and upper-to-lower
de-excitation influence of a single ATDB collision record.

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


Generated density-grid output directories are intentionally not bundled as package inputs. In particular, `o7_solver_source_fit_density_xstar_grid/`, `o7_high_density_rate_sensitivity/`, and `o7_density_grid_type69_mode_compare/` are reproducible outputs created by the examples, while the compact density-specific XSTAR line CSVs live under `xstar_test_run/o7_ne*/`.


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



Version 0.2.90 note: the density-grid front end now writes ion-specific He-like mapping templates.  If `xstar_test_run/xstar_c5_density_grid_references.csv` is missing, the generated template points to `xstar_test_run/c5_ne*/xstar_c5_triplet_lines.csv`; it no longer writes the O VII placeholder path.  Run the example 32 XSTAR scripts and converters first, or copy the converted triplet CSVs into those paths, then rerun the C V density-grid command.

Version 0.2.89 note: the He-like density-grid front end now detects stale non-O VII mapping CSVs that still point to the O VII placeholder file and repairs them when the correct converted per-density files exist under `xstar_test_run/<ion>_ne*/`.  For example, a C V mapping is repaired to use `xstar_test_run/c5_ne*/xstar_c5_triplet_lines.csv`, with the original mapping saved as a `.bak` file.

Version 0.2.91 note: the He-like density-grid front end now validates mapping CSV paths before launching the solver-fit subprocesses.  If a C V, Mg XI, or Ca XIX mapping points to files that are not present in the current package tree, the script stops with a clear message telling you to run the example 32 XSTAR/convert scripts in this tree, or to copy the converted `<ion>_ne*` folders from the tree where you generated them.  This prevents confusing downstream failures from missing files such as `xstar_test_run/c5_ne1/xstar_c5_triplet_lines.csv`.

### v0.2.92 He-like combined-solver triplet diagnostics

The solver-side triplet diagnostics are now generic for He-like ions. Combined simultaneous-solver validation can report R=f/i and G=(f+i)/r for C V, Mg XI, Ca XIX, and other He-like ions using level labels such as `1s1.2s1.3S_1`, `1s1.2p1.3P_J`, and `1s1.2p1.1P_1`. O VII wavelength-based fallback remains available for legacy O VII outputs.

### v0.2.93 robust printing for exploratory non-O VII He-like fits

The C V density-grid validation path can read the XSTAR C V triplet target, but some exploratory solver-side response matrices may have incomplete triplet diagnostics, for example a missing resonance component in a uniform or fitted response.  `examples/20_o7_solver_source_fit.py` now prints `NA` for missing uniform, fitted, or combined R/G values instead of formatting `None` as a floating-point value and aborting.  The JSON and CSV outputs continue to store missing values as `null`/blank so downstream density-grid summaries can mark the target as not reached rather than crashing.


### Auditing empty He-like XSTAR triplet conversions

If a prepared He-like density grid runs in XSTAR but the converter reports `n_lines=0`/`n_rows=0`, inspect the raw `xout_lines1.fits` file before trying the solver.  For example, for Ca XIX:

```bash
PYTHONPATH=src python examples/33_audit_helike_xstar_lines.py \
  xstar_runs/helike_type69/ca19_ne1/xout_lines1.fits \
  --expected-ion "Ca XIX" \
  --wavelength-min 3.0 \
  --wavelength-max 3.4 \
  --out-dir ca19_line_audit_ne1 \
  --print-rows
```

This reports all XSTAR ion labels, nearby rows in the wavelength window, and rows whose lower/upper labels look like He-like ground-to-`n=2` forbidden/intercombination/resonance transitions.  It is diagnostic only; an ion with empty triplet CSVs remains not testable until a complete XSTAR triplet target is found.


### He-like source-level failure diagnostics (v0.3.0)

After running the density-grid source-fit workflows, compare the fitted source vectors and response matrices at source-level resolution:

```bash
PYTHONPATH=src python examples/36_source_level_failure_diagnostics.py \
  o7_solver_source_fit_density_xstar_grid_type69_suppressed \
  c5_solver_source_fit_density_xstar_grid \
  mg11_solver_source_fit_density_xstar_grid \
  ca19_xi3_solver_source_fit_density_xstar_grid \
  ca19_xi4_solver_source_fit_density_xstar_grid \
  --out-dir helike_source_level_failure_diagnostics \
  --print-summary
```

For deeper atomic-rate annotation, pass the real XSTAR database:

```bash
PYTHONPATH=src python examples/36_source_level_failure_diagnostics.py \
  c5_solver_source_fit_density_xstar_grid \
  mg11_solver_source_fit_density_xstar_grid \
  ca19_xi3_solver_source_fit_density_xstar_grid \
  --fitsfile ../xstar/data/atdb.fits \
  --out-dir helike_source_level_failure_diagnostics \
  --print-summary
```

The output CSV/JSON/Markdown tables report the source level label/configuration, fitted weight, f/i/r response contribution, zero-response flags, optional source-component population, dominant radiative decay path, dominant collisional sink/source, and pruning/weak-connectivity flags. Older v0.2.x archives lack combined-solver population CSVs; rerunning the v0.3.0 workflows fills those population columns.
