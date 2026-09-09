# `xstar-xspec-table`

`xstar-xspec-table` converts loopcontrol-ordered `xout_spect1.fits` files into the four canonical-compatible XSPEC table products:

```text
xout_ain.fits
xout_aout.fits
xout_mtable.fits
xout_etable.fits
```

## Canonical native metadata

```bash
xstar-xspec-table \
  --initable plan/xstinitable.fits \
  --output-dir tables \
  jobs/000001/xout_spect1.fits \
  jobs/000002/xout_spect1.fits
```

The spectra must be listed in planner `loopcontrol` order.

## Legacy characterization metadata

The older metadata-text contract remains available for regression/compatibility work:

```bash
xstar-xspec-table \
  --metadata CONFIG \
  --output-dir tables \
  xout_spect1_1.fits xout_spect1_2.fits
```

Exactly one of `--initable` or `--metadata` is required.

## Options

| Option | Meaning |
|---|---|
| `--initable PATH` | native/canonical `xstinitable.fits` metadata |
| `--metadata PATH` | legacy characterization metadata text |
| `--output-dir DIR` | destination for the four table products |
| positional spectra | one or more `xout_spect1.fits` files in loopcontrol order |
| `--help`, `-h` | help |

For ordinary production use, prefer `--initable`. The complete `xstar-xspec` driver invokes this stage automatically after all grid jobs succeed.
