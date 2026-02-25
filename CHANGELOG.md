# CHANGELOG

All notable changes to `xstar-atomic` are documented here.

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
