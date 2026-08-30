# `xstar-cpp`

`xstar-cpp` is the first-class Python-free native frontend for one XSTAR model.

## Parameter file

```bash
xstar-cpp \
  --input xstar.par \
  --data-dir /path/to/xstar/data \
  --output run1
```

The positional form is equivalent:

```bash
xstar-cpp xstar.par --data-dir /path/to/xstar/data --output run1
```

## Direct parameters

A parameter file is optional. Supply XSTAR values directly:

```bash
xstar-cpp \
  --data-dir /path/to/xstar/data \
  --output run_direct \
  spectrum=pow temperature=100 density=1e8 column=1e20 rlogxi=1 \
  cfrac=1 niter=0 ncn2=9999 modelname=direct_cpp_example
```

Direct values can override a file:

```bash
xstar-cpp --input xstar.par --output run_override density=1e10 rlogxi=2
```

## Core options

```text
--input PATH
--data-dir DIR
--input-dir DIR
--output DIR / --output-dir DIR
--atomic-db PATH
--coheat PATH
```

## Native frontend extensions

```text
--json-summary FILE
--provenance FILE
--progress none|text|json
--threads N
--profile FILE
--deterministic
--print-option N
--parameters-out FILE
--abi
--version
```

`--threads N` sets `OMP_NUM_THREADS` in the native run environment. It is unrelated to `xstar-xspec --workers N`, which creates independent OS processes.

## Atomic-data selection

Explicit `--data-dir` is the simplest reproducible contract. If it is absent, the runtime discovers `atdb.fits` and `coheat.dat` independently.

`atdb.fits` precedence:

1. explicit parameter-envelope path (`atomic_database`, `atomic_db`, `atdb`);
2. parameter-envelope sibling `atdb.fits`;
3. `XSTAR_ATOMIC_DB`;
4. `XSTAR_ATDB_FITS`;
5. `XSTAR_DATA/atdb.fits`;
6. `HEADAS/refdata/atdb.fits`;
7. `XSTAR_HOME/data/atdb.fits`;
8. executable-relative data directories;
9. package/source fallback;
10. current-directory `atdb.fits`.

`coheat.dat` precedence:

1. explicit parameter-envelope path (`coheat_file`, `coheat`);
2. parameter-envelope sibling `coheat.dat`;
3. `XSTAR_COHEAT`;
4. `XSTAR_DATA/coheat.dat`;
5. `HEADAS/refdata/coheat.dat`;
6. `XSTAR_HOME/data/coheat.dat`;
7. executable-relative data directories;
8. package/source fallback;
9. current-directory `coheat.dat`.

The first existing regular file wins. See {doc}`../user/atomic_data` for the exact path list and MPI guidance.

## Compatibility interfaces

The machine-oriented production interface remains available:

```bash
xstar-cpp run-production \
  --parameters parameters.json \
  --output-dir native-run
```

The public frontend delegates scientific execution to the qualified native production implementation; frontend conveniences do not create a separate science path.
