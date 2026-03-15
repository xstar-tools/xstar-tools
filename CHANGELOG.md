# CHANGELOG

## v0.2.18 - 2026-03-15

### Documentation
- Updated the Markdown, LaTeX, and Sphinx user-guide material for the validated Stage-4 band-emissivity export workflow.
- Documented `--bands-kev`, `*_band_emissivity.csv`, and HDF5 `/band_emissivity` products.
- Recorded the v0.2.17 Stage-4 real-ATDB validation result: 34 passing tests, 12 band-emissivity rows per ion for four bands and three temperatures, nonblank `ion`, and `methods_used="none"` for zero-line bands.

### Examples
- Added `examples/09_export_band_emissivity.py` for CSV/HDF5 export of line-based X-ray band emissivity products.

## v0.2.17 - 2026-03-14

### Fixed
- Filled the `ion` field for all band-emissivity rows, including zero-line bands.
- Set `methods_used="none"` for zero-line band-emissivity rows.

### Tests
- Added unit and real-ATDB export tests that check band-emissivity rows do not contain blank ion names or blank method fields.

## v0.2.15 - 2026-03-13

### Added
- Added HDF5 export support to `xstar_atomic.export` via `--formats hdf5` or `--formats csv,hdf5`.
- Added a general CLI alias `xstar-atomic-export` while keeping `xstar-atomic-export-superwind` for backward compatibility.
- Added optional SciPy sparse-matrix support to the level-population solver via `--linear-solver sparse` or `--linear-solver auto`.
- Added tests for HDF5 export helpers and sparse-solver fallback/consistency.

### Changed
- Generalized export documentation and manifests for plasma post-processing workflows beyond superwinds, including AGN outflows.
- The export manifest is now written as `atomic_export_manifest.json` and also as the legacy `superwind_export_manifest.json`.


## v0.2.14 - 2026-03-12

### Added
- Added `xstar_test_run/` with direct-XSTAR `xout_lines1.fits` outputs, converted CSV line tables, and a README documenting the exact XSTAR commands and FITS-to-CSV conversion workflow.
- Added tests for packaged XSTAR test-run artifacts and conversion consistency.

### Documentation
- Updated XSTAR comparison documentation to reference `xstar_test_run/` and the included O VIII/O VII validation CSV files.

## v0.2.13 - 2026-03-11

### Added
- Added `xstar_test_run/` with direct-XSTAR `xout_lines1.fits` outputs, converted CSV line tables, and a README documenting the exact XSTAR commands and FITS-to-CSV conversion workflow.
- Added tests for packaged XSTAR test-run artifacts and conversion consistency.

### Documentation
- Updated XSTAR comparison documentation to reference `xstar_test_run/` and the included O VIII/O VII validation CSV files.

## v0.2.12 - 2026-03-10

### Added
- Added saved XSTAR-vs-`xstar-atomic` comparison outputs for O VIII Ly-alpha and the O VII triplet under `docs/validation/xstar_outputs/` and `examples/reference_outputs/`.
- Added `docs/xstar_comparison_examples.md` documenting the XSTAR-output comparison workflow and validation results.
- Added Sphinx page `xstar_comparisons.rst` and linked it from the Sphinx index.

### Documentation
- Documented that O VIII Ly-alpha wavelength agreement is at the ~1e-5 Angstrom level.
- Documented that O VII triplet wavelength agreement is at the ~1e-7 to 8e-7 Angstrom level.
- Clarified that XSTAR model `emit_*` columns are not directly equivalent to local `xstar-atomic` emissivity coefficients without model-dependent normalization.

## v0.2.11 - 2026-03-09

Added:
- Extended ``examples/08_compare_xstar_outputs.py`` with explicit ``--mode`` choices: ``wavelength``, ``emissivity``, and ``both``.
- Added ``--out-csv`` and ``--out-json`` outputs for XSTAR-vs-xstar-atomic comparison tables.
- Added clearer warnings/notes that XSTAR model ``emit_*`` columns are not directly equivalent to local atomic emissivity coefficients.

## v0.2.10 - 2026-03-08

Fixed:
- Added `--wavelength-column` to `examples/08_compare_xstar_outputs.py`.
- The comparison example now auto-detects `wavelength_A` or `wavelength` columns in XSTAR-output CSV files.

## v0.2.9 - 2026-03-07

### Added
- Added `xstar_atomic.xstar_outputs` for reading XSTAR `xout_lines*.fits` files.
- Added CLI entry point `xstar-atomic-xstar-outputs` and module execution with `python -m xstar_atomic.xstar_outputs`.
- Supports CSV export, JSON summaries, and filtering by ion, wavelength, and emission columns.

## v0.2.8 - 2026-03-06

### Fixed
- Added the missing solver CLI argument `--electron-density-for-lmixing`.
- Fixed the real-ATDB solver status test failure caused by the solver referencing `args.electron_density_for_lmixing` without registering the argparse option.

## v0.2.7 - 2026-03-05

### Added
- Added a scientific validation status table to the Markdown and LaTeX user guides.
- Added `xstar_atomic.export` with CSV/JSON export helpers for superwind/Athena++ post-processing.
- Added CLI entry point `xstar-atomic-export-superwind`.
- Added `examples/08_compare_xstar_outputs.py` for comparing selected xstar-atomic outputs against user-supplied XSTAR CSV outputs.
- Added lightweight import tests for the export module.

### Improved
- Updated solver diagnostics to report that the XSTAR-derived type-63 same-n l-mixing collision decoder is enabled.
- Updated docs to reflect the implemented type-63 same-n l-mixing path and the current validation status of data types 51 and 98.

## v0.2.6 - 2026-03-04

### Added
- Added `tests/data/collision_type51_98_targets.csv`, generated from the collision validation inventory.
- Added API-level real-ATDB pytest coverage for representative collision `data_type=51` and `data_type=98` targets through `XSTARAtomic.collisions(...)`.
- Added a type-98 ion-alias API regression test using the `ne_ix` alias.

### Validation
- The type-51 API test validates a representative Burgess--Tully 5-point target against the inventory reference rate.
- The type-98 API test validates the Ne IX CHIANTI-style Burgess--Tully target against the inventory reference rate.

## v0.2.5 - 2026-03-03

### Fixed
- Restored the lightweight top-level `parse_ion` export so `from xstar_atomic import parse_ion` works again after the lazy-import cleanup.
- Kept the minimal top-level API limited to `ATDB`, `XSTARAtomic`, and `parse_ion`; decoder functions remain importable from their submodules.


## v0.2.4 - 2026-03-02

### Fixed
- Cleaned reStructuredText in module docstrings for the Sphinx API build.
- Fixed docutils warnings/errors in `photoionization`, `collisions`, and `recombination` module documentation.

## v0.2.3 - 2026-03-01

### Added
- Added `xstar_atomic.validation` with collision-decoder inventory and validation helpers.
- Added CLI entry point `xstar-atomic-validate-collisions`.
- Added `examples/07_collision_decoder_validation.py` for type 51/98 target discovery and type-63 same-`n` diagnostics.
- Added real-ATDB pytest checks for:
  - O VIII type-63 same-`n` l-mixing regression diagnostics.
  - Type 51 and type 98 inventory plus representative positive-rate targets when present in the local `atdb.fits`.

### Notes
- The type-63 same-`n` diagnostic checks the Python port of the XSTAR `amcrs/velimp` branch, but independent validation against XSTAR model outputs is still recommended for production science.

## v0.2.2 - 2026-02-28

### Fixed
- Corrected LaTeX backslash corruption in `docs/user_guide.tex` for the `center` and `tabular` environments.

## v0.2.1 - 2026-02-27

### Changed
- Simplified ``xstar_atomic.__init__`` to expose only ``ATDB``, ``XSTARAtomic``, and ``__version__``.
- Moved heavy decoder imports in ``api.py`` to lazy method-level imports.
- Preserved submodule-level imports such as ``xstar_atomic.collisions`` and ``xstar_atomic.recombination``.

### Fixed
- Avoids ``runpy`` warnings when executing CLI modules with ``python -m xstar_atomic.<module>`` after importing the package.

## v0.2.0 - 2026-02-26

### Added
- Implemented the type-63 same-`n` l-changing collision branch using the XSTAR `amcrs`/`velimp` ecm=0 logic.
- Added `electron_density_for_lmixing` to the high-level collision/emissivity APIs for the density-dependent impact-parameter cutoff used by same-`n` l-mixing.
- Added `--electron-density` to `xstar-atomic-collisions` and `--electron-density-for-lmixing` to emissivity/solver CLIs.
- Added diagnostic columns for same-`n` type-63 l-mixing: shell radiative sum, `cn`, selected `l` branch, and density.

### Improved
- Promoted collision data type 51 and 98 Burgess--Tully evaluators as supported collision-rate paths alongside type 56 and type 63.
- Updated package tests to check that real-ATDB type-63 same-`n` l-mixing returns finite evaluated rates when `XSTAR_ATDB_FITS` is supplied.

## v0.1.8 - 2026-02-25

### Documentation
- Added `\usepackage{amsmath,amssymb}` to the LaTeX user guide preamble for math support.


All notable changes to `xstar-atomic` are documented here.

## v0.1.7 - 2026-02-24

Fixed:
- Restored backward-compatible high-level API keys used by the examples:
  - `collisions()["matches"]` and `collisions()["evaluated_rates"]`.
  - `emissivity()["rows"]`.
  - `recombination()["summary"]`.
- Updated example/API behavior so the examples work with the current return dictionaries.

## v0.1.6 - 2026-02-23

### Added
- Added full user guide in Markdown: `docs/user_guide.md`.
- Added full user guide in LaTeX: `docs/user_guide.tex`.
- Added Sphinx documentation scaffold under `docs/sphinx/` using `sphinx.ext.autodoc`, `sphinx.ext.napoleon`, and the Read the Docs theme.
- Added Sphinx pages for user guide, examples, API reference, development notes, and changelog.
- Added `examples/06_high_level_api_quickstart.py`.
- Added optional `docs` dependency group with `sphinx` and `sphinx-rtd-theme`.

### Notes
- Sphinx API pages are generated from Python docstrings. Future public functions/classes should include clear docstrings.

## v0.1.5 - 2026-02-22

### Added
- Added flexible ion-name parsing in the high-level API. Accepted forms now include `O VIII`, `o viii`, `o_viii`, `O_VIII`, `O-VIII`, `OVIII`, and `o8`.
- Added unit tests for ion-name aliases.

## v0.1.4 - 2026-02-21

### Added
- Added real pytest smoke tests for the direct `atdb.fits` workflow.
- Added API smoke tests for:
  - low-level `ATDB.build_index()` counts,
  - O VIII Ly-alpha line extraction,
  - O VIII Ly-alpha collision-rate evaluation,
  - O VIII Ly-alpha emissivity table generation,
  - oxygen recombination inventory.
- Added CLI smoke tests using `python -m xstar_atomic.*` modules.
- Added `examples/` scripts:
  - `01_o8_lya_lines.py`,
  - `02_o8_lya_collisions.py`,
  - `03_o8_lya_emissivity.py`,
  - `04_oxygen_recombination_inventory.py`,
  - `05_low_level_atdb_index.py`.
- Added this versioned `CHANGELOG.md`.

### Notes
- Tests that require the real XSTAR database are skipped unless `XSTAR_ATDB_FITS` points to a readable `atdb.fits` file.
- Example test command:

  ```bash
  XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits pytest -q
  ```

## v0.1.3 - 2026-02-20

### Fixed
- Fixed the high-level `XSTARAtomic.emissivity()` wrapper by adding the missing `collision_data_type` default expected by the emissivity filters.

## v0.1.2 - 2026-02-19

### Fixed
- Fixed the high-level `XSTARAtomic.emissivity()` wrapper by adding the missing `include_superlevel_radiative` default expected by the emissivity filters.

## v0.1.1 - 2026-02-18

### Added
- Added the high-level `XSTARAtomic` API wrapper around the low-level `ATDB` reader.
- Added convenience methods for lines, collisions, recombination, and emissivity workflows.
- Kept `ATDB` as the low-level direct packed-FITS API.

## v0.1.0 - 2026-02-17

### Added
- Initial package refactor from validated standalone scripts.
- Added package namespace `xstar_atomic` and project name `xstar-atomic`.
- Added command-line modules for:
  - inspecting `atdb.fits`,
  - hierarchy reconstruction,
  - lines,
  - photoionization,
  - collisions,
  - recombination,
  - emissivity,
  - prototype level-population solving.
