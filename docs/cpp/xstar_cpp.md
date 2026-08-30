# `xstar-cpp`

`xstar-cpp` runs one native XSTAR calculation. It accepts either an XSTAR parameter file or direct `key=value` parameters.

## With `xstar.par`

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

Positional input is also accepted:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp xstar.par \
  --data-dir /path/to/xstar/data \
  --output-dir run_xstar
```

Direct values after the file override file values:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp \
  --input xstar.par \
  --output-dir run_override \
  density=1.0e+12 rlogxi=3 modelname='override_model'
```

## Without `xstar.par`

A realistic direct command is:

```bash
src/xstar_tools/xstar/cpp/xstar-cpp --output-dir run_xstar_direct \
  cfrac=0.4 temperature=100. lcpres=0 pressure=0.03 spectrum='pow' \
  spectun=0 trad=-1. density=1.0e+12 column=1.e+20 rlrad38=1.e+6 rlogxi=3 \
  habund=1 heabund=1 liabund=0 beabund=0 babund=0 cabund=1 \
  nabund=1 oabund=1 fabund=0 neabund=1 naabund=0 mgabund=1 \
  alabund=1 siabund=1 pabund=0 sabund=1 clabund=0 arabund=1 \
  kabund=0 caabund=1 scabund=0 tiabund=0 vabund=0 crabund=1 \
  mnabund=0 feabund=1 coabund=0 niabund=1 cuabund=0 znabund=0 \
  modelname='xstar_pg1211' abundtbl='xdef' nsteps=10 niter=99 \
  lwrite=1 lprint=1 lstep=0 emult=0.5 taumax=5. radexp=0. \
  xeemin=0.1 critf=1.e-6 vturbi=100. npass=1 ncn2=9999
```

## Atomic data

Explicit directory:

```bash
--data-dir /path/to/xstar/data
```

Explicit files:

```bash
--atomic-db /path/to/atdb.fits --coheat /path/to/coheat.dat
```

If omitted, the first existing `atdb.fits` is selected from: explicit parameter path, parameter-envelope directory, `$XSTAR_ATOMIC_DB`, `$XSTAR_ATDB_FITS`, `$XSTAR_DATA`, `$HEADAS/refdata`, `$XSTAR_HOME/data`, executable/package-local fallbacks, then the current directory. `coheat.dat` follows the analogous order using `$XSTAR_COHEAT` as its direct environment override.

After `heainit`, `$HEADAS/refdata/atdb.fits` and `$HEADAS/refdata/coheat.dat` are valid fallbacks. `$XSTAR_DATA` has precedence when set and valid.

## Process/thread distinction

`xstar-cpp --threads N` sets `OMP_NUM_THREADS` for one model. This is different from `xstar-xspec --processes N`, which launches up to N independent `xstar-cpp` OS processes.
