# Reading XSTAR output products

`xstar_tools.xstar_outputs` provides lightweight readers for standard XSTAR FITS products. Where possible it uses Astropy; selected XSTAR table products also have a small internal FITS fallback for minimal diagnostic environments.

```python
from xstar_tools.xstar_outputs import (
    list_fits_hdus,
    read_xout_abundances,
    read_xout_lines,
    read_xout_parameters,
    read_xout_spectra,
)

lines = read_xout_lines("run1/xout_lines1.fits")
spectra = read_xout_spectra("run1/xout_spect1.fits")
params = read_xout_parameters("run1/xout_spect1.fits")
abund = read_xout_abundances("run1/xout_abund1.fits")
hdus = list_fits_hdus("run1/xout_spect1.fits")
```

## Generic table access

```python
from xstar_tools.xstar_outputs import read_fits_table, read_fits_table_hdus

rows = read_fits_table("run1/xout_lines1.fits", "XSTAR_LINES")
```

## Filtering and CSV conversion

```python
from xstar_tools.xstar_outputs import filter_rows, write_csv, write_xout_spectra_csv

selected = filter_rows(lines, ion="O VIII")
write_csv(selected, "o8_lines.csv")
write_xout_spectra_csv(spectra, "spectrum.csv")
```

The line-emission columns in XSTAR outputs are model-dependent radiative-transfer quantities. Do not equate them directly with local atomic emissivity coefficients unless the ion fractions, geometry, density, and radiative-transfer assumptions are matched.

A command-line interface is also installed as `xstar-tools-xstar-outputs` for conversion/inspection workflows.
