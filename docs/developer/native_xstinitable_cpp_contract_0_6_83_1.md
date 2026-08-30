# 0.6.83.1 native xstinitable command contract

## Purpose

`0.6.83` reproduced the canonical XSTAR 2.59g `xstinitable.lis` byte-for-byte, but that file targeted the historical Fortran executable (`xstar key=value ...`). `0.6.83.1` makes the native XSTAR frontend the production default while retaining the Fortran contract explicitly.

## CLI

The native planner supports both a HEASoft/IRAF-style parameter file and direct overrides:

```bash
xstar-xspec-initable \
  --input xstinitable.par \
  --data-dir /path/to/xstar/data \
  --output-dir run-init
```

```bash
xstar-xspec-initable \
  --output-dir run-init \
  columnsof=1e20 columntyp=2 column=1e21 columnnst=2 columnint=1 \
  rlogxisof=1 rlogxityp=2 rlogxi=3 rlogxinst=3 rlogxiint=0
```

Trailing `key=value` arguments override values loaded from `--input`.

### XSTAR target selection

```bash
--xstar cpp       # default
--xstar fortran   # explicit legacy-compatible mode
```

Aliases `-xstar` and `-data-dir` are accepted for compatibility with user command conventions.

## Generated `xstinitable.lis`

For the default native mode:

```text
xstar-cpp --data-dir /path/to/xstar/data spectrum='pow' ... loopcontrol=1
```

If `--data-dir` is omitted, the command begins simply with `xstar-cpp spectrum=...`.

For explicit Fortran mode:

```text
xstar spectrum='pow' ... loopcontrol=1
```

The `--data-dir` option is not emitted in Fortran mode. This is deliberate so the accepted `0.6.83` historical `.lis` remains byte-exact.

## Frozen semantics

Changing the target executable does not alter:

- the 39 physical-parameter order;
- constant/additive/interpolated classification;
- float32 interpolation values;
- additive expansion;
- highest-index-fastest Cartesian order;
- 1-based `loopcontrol`;
- `xstinitable.fits` scientific/table payload.

The first canonical fixture remains:

```text
NINTPARM=2
NADDPARM=0
jobs=6
loopcontrol=1..6
```

with `(column,rlogxi)` order `(1e20,1)`, `(1e20,2)`, `(1e20,3)`, `(1e21,1)`, `(1e21,2)`, `(1e21,3)`.

## Scope boundary

`0.6.83.1` does not assign per-job output directories and does not execute the grid. Those concerns belong to the serial native XSTAR2XSPEC orchestrator in `0.6.84`.

The existing `xstar-cpp` frontend source is unchanged from accepted `0.6.83`; it already accepts both `--input xstar.par` and direct trailing `name=value` parameters.
