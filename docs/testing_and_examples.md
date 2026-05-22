# Testing and examples

`xstar-atomic` includes two levels of tests.

## Database-independent tests

These verify the package layout and can run anywhere:

```bash
pytest -q
```

## Real `atdb.fits` smoke tests

These tests require the XSTAR atomic database file and are skipped unless `XSTAR_ATDB_FITS` or `XSTAR_ATDB` is set:

```bash
XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits pytest -q
# or
XSTAR_ATDB=/path/to/xstar/data/atdb.fits pytest -q
```

The smoke tests validate:

- `ATDB.build_index()` returns 1,216,792 records, 30 elements, and 465 ions.
- O VIII Ly-alpha line extraction returns the expected two-line doublet near 18.97 Å.
- O VIII Ly-alpha collision extraction returns type-56 rates.
- O VIII Ly-alpha emissivity generation returns six rows for three temperatures.
- Oxygen recombination inventory separates electron recombination from charge exchange.

## Running examples without installing

From the source tree:

```bash
PYTHONPATH=src python examples/01_o8_lya_lines.py /path/to/xstar/data/atdb.fits
```

## Sphinx documentation

The package now includes a Sphinx documentation scaffold under:

```text
docs/sphinx/
```

Build it with:

```bash
python -m pip install -e .[docs]
cd docs/sphinx
make html
```

The HTML output will be created in:

```text
docs/sphinx/build/html/
```

The API pages use `sphinx.ext.autodoc`, so public modules/classes/functions should include docstrings. Inline comments are useful for maintainers, but Sphinx does not normally include them in the public API documentation.

## High-level API example

```bash
PYTHONPATH=src python examples/06_high_level_api_quickstart.py /path/to/xstar/data/atdb.fits
```


### Source-level failure diagnostics

`examples/36_source_level_failure_diagnostics.py` compares He-like source-fit outputs level by level. It is intended for the post-validation question of why O VII remains reachable while C V, Mg XI, and Ca XIX are not. It reports source level labels, fitted weights, f/i/r response contributions, zero-response flags, optional component populations, dominant radiative and collisional paths, and weak/pruned-level indicators.

## v0.4.64 bounded radial shell

```bash
PYTHONPATH=src python examples/134_validate_xstar_bounded_radial_shell.py \
  --out-dir xstar_bounded_radial_shell_source_validation_v0464 \
  --print-summary
```

The gate combines direct original-Fortran references for `step`, `trnfrc`,
`stpcut`, and `trnfrn` with first-pass caller-order tests. It also requires
explicit failure at untranslated `unsavd` and `gsmooth`, and confirms that no
output writer is entered.
