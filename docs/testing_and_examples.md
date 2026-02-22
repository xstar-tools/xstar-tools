# Testing and examples

`xstar-atomic` includes two levels of tests.

## Database-independent tests

These verify the package layout and can run anywhere:

```bash
pytest -q
```

## Real `atdb.fits` smoke tests

These tests require the XSTAR atomic database file and are skipped unless `XSTAR_ATDB_FITS` is set:

```bash
XSTAR_ATDB_FITS=/path/to/xstar/data/atdb.fits pytest -q
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
