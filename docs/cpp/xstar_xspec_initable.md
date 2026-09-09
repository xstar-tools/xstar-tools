# `xstar-xspec-initable`

`xstar-xspec-initable` is the native XSTAR2XSPEC grid planner. It creates:

```text
xstinitable.lis
xstinitable.fits
```

The default command contract targets `xstar-cpp`.

## From `xstinitable.par`

```bash
xstar-xspec-initable \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir plan
```

## From direct values

```bash
xstar-xspec-initable \
  --output-dir plan \
  rlogxityp=2 rlogxisof=0 rlogxi=5 rlogxinst=6 rlogxiint=0 \
  columntyp=2 columnsof=1e20 column=1e24 columnnst=9 columnint=1
```

Trailing `key=value` arguments override values loaded from `--input`.

## Options

| Option | Meaning |
|---|---|
| `--xstar cpp|fortran`, `-xstar` | command target; `cpp` is the default |
| `--input PATH` | HEASoft/IRAF-style `xstinitable.par` |
| `--data-dir DIR`, `-data-dir DIR` | data directory embedded in generated `xstar-cpp` lines |
| `--output-dir DIR` | destination for `.lis` and `.fits` planner products |
| `--help`, `-h` | help |

`--xstar fortran` preserves the canonical historical `xstar key=value` command contract. It does not change the grid definition itself.

The generated `xstinitable.fits` is the canonical metadata input for `xstar-xspec-table` and the complete `xstar-xspec`/`xstar-xspec-mpi` pipelines.
